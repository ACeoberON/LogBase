import os
import sys
import time
import json
import subprocess
import atexit
from datetime import datetime, timedelta
from dotenv import load_dotenv
import psycopg2
import psutil
import win32gui
import win32process
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ==========================================
# [0] PyInstaller 절대 경로 인식 패치
# ==========================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==========================================
# [1] 시스템 설정 및 인프라 오케스트레이션
# ==========================================
PG_BIN   = os.path.join(BASE_DIR, 'pgsql', 'bin', 'pg_ctl.exe')
PG_DATA  = os.path.join(BASE_DIR, 'pgsql', 'data')
LOG_FILE = os.path.join(BASE_DIR, 'pgsql', 'logfile.log')
PG_PORT  = "5433"
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# --- 필터 설정 ---
TEMP_EXTENSIONS = ('.tmp', '.crdownload', '.part', '.download', '.partial')
TEMP_PREFIXES   = ('~$',)
DEBOUNCE_SECONDS = 5          # 파일시스템 노이즈 제거
SESSION_MINUTES  = 10         # 작업 세션 묶기

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] config.json 로드 실패: {e}")
        return {"watch_paths": [], "allowed_apps": []}

CONFIG       = load_config()
WATCH_PATHS  = CONFIG.get("watch_paths", [])
ALLOWED_APPS = CONFIG.get("allowed_apps", [])

def start_local_db():
    print(f"\n[LogBase 인프라] 기준 경로: {BASE_DIR}")
    print("[LogBase 인프라] 파이썬 백엔드가 로컬 요새(DB)를 가동합니다...")

    # PostgreSQL이 이미 실행 중이면 재사용 (중복 기동 방지)
    status = subprocess.run(
        [PG_BIN, "-D", PG_DATA, "status"],
        creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    if status.returncode == 0:
        print("  -> DB가 이미 실행 중입니다. 재사용합니다.")
        return

    # 혹시 남아있는 pid 파일 제거
    pid_file = os.path.join(PG_DATA, "postmaster.pid")
    if os.path.exists(pid_file):
        os.remove(pid_file)

    if not os.path.exists(PG_DATA):
        print("  -> 최초 실행: DB 인프라 자동 세팅 중...")
        initdb = os.path.join(BASE_DIR, 'pgsql', 'bin', 'initdb.exe')
        subprocess.run(
            [initdb, "-U", "postgres", "-A", "trust", "-E", "utf8", "--locale=C"],
            creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    subprocess.run(
        [PG_BIN, "-D", PG_DATA, "-l", LOG_FILE, "-o", f"-p {PG_PORT}", "start"],
        creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(2)

def stop_local_db():
    print("\n[LogBase 인프라] 시스템 종료. DB를 안전하게 닫습니다...")
    subprocess.run(
        [PG_BIN, "-D", PG_DATA, "stop"],
        creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

atexit.register(stop_local_db)

# ==========================================
# [2] DB 연결 및 쿼리 파이프라인
# ==========================================
load_dotenv(os.path.join(BASE_DIR, ".env"))

class DBConnector:
    def __init__(self):
        try:
            self.conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                database=os.getenv("DB_NAME", "postgres"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASS", ""),
                port=os.getenv("DB_PORT", "5433")
            )
            self._initialize_table()
            print("[SUCCESS] 데이터 파이프라인 연결 완료.")
        except Exception as e:
            print(f"[ERROR] 파이프라인 연결 실패: {e}")

    def _initialize_table(self):
        cur = self.conn.cursor()
        # file_path에 UNIQUE 없이 생성 (세션별 히스토리 누적)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS file_logs (
                id        SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                file_path TEXT NOT NULL,
                metadata  JSONB NOT NULL
            );
        """)
        # 기존 스키마에서 UNIQUE 제약이 남아있을 경우 자동 제거 (마이그레이션)
        cur.execute("""
            ALTER TABLE file_logs
            DROP CONSTRAINT IF EXISTS file_logs_file_path_key;
        """)
        self.conn.commit()
        cur.close()

    def update_session(self, file_path, now, metadata):
        """같은 세션 내 재저장: 가장 최근 레코드의 timestamp와 metadata만 갱신"""
        try:
            cur = self.conn.cursor()
            cur.execute("""
                UPDATE file_logs
                SET timestamp = %s, metadata = %s
                WHERE id = (
                    SELECT id FROM file_logs
                    WHERE file_path = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                )
            """, (now, json.dumps(metadata, ensure_ascii=False), file_path))
            self.conn.commit()
            cur.close()
            print(f"  -> [세션 갱신] {os.path.basename(file_path)}")
        except Exception as e:
            print(f"[ERROR] 세션 갱신 실패: {e}")
            self.conn.rollback()

    def insert_log(self, payload):
        """새 세션 시작: 신규 레코드 INSERT"""
        try:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO file_logs (timestamp, file_path, metadata)
                VALUES (%s, %s, %s)
            """, (
                payload['time'],
                payload['path'],
                json.dumps(payload['metadata'], ensure_ascii=False)
            ))
            self.conn.commit()
            cur.close()
            print(f"  -> [새 세션 기록] {os.path.basename(payload['path'])}")
        except Exception as e:
            print(f"[ERROR] DB 저장 실패: {e}")
            self.conn.rollback()

# ==========================================
# [3] 맥락(Context) 추출 로직
# ==========================================
def get_active_window_info():
    try:
        hwnd = win32gui.GetForegroundWindow()
        window_title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        app_exe = process.name()
        return {"app_exe": app_exe.lower(), "window_title": window_title}
    except Exception:
        return {"app_exe": "unknown", "window_title": "unknown"}

# ==========================================
# [4] 파일 이벤트 감시 및 필터링
# ==========================================
def is_temp_file(path):
    """임시 파일 여부 판별"""
    return (
        any(path.endswith(ext) for ext in TEMP_EXTENSIONS) or
        any(p in path for p in TEMP_PREFIXES)
    )

class MyFileEventHandler(FileSystemEventHandler):
    def __init__(self, db_connector):
        self.db = db_connector
        self.last_event_time = {}   # 파일별 마지막 이벤트 시각 (디바운스용)
        self.last_logged     = {}   # 파일별 마지막 DB 기록 시각 (세션 윈도우용)

    def _process(self, path, event_type):
        if is_temp_file(path):
            return

        context = get_active_window_info()
        if context["app_exe"] not in ALLOWED_APPS:
            return

        now = datetime.now()

        # [1단계] 5초 디바운스: 파일시스템 노이즈 제거
        last_evt = self.last_event_time.get(path)
        if last_evt and (now - last_evt).total_seconds() < DEBOUNCE_SECONDS:
            return
        self.last_event_time[path] = now

        # [2단계] 10분 세션 윈도우: INSERT vs UPDATE 판단
        metadata = {**context, "event_type": event_type}
        last_log = self.last_logged.get(path)

        print(f"\n[이벤트 포착] 타입: {event_type} | 앱: {context['app_exe']} | 파일: {os.path.basename(path)}")

        if last_log and (now - last_log) < timedelta(minutes=SESSION_MINUTES):
            # 같은 세션 → UPDATE
            self.db.update_session(path, now, metadata)
        else:
            # 새 세션 → INSERT
            self.db.insert_log({"time": now, "path": path, "metadata": metadata})

        self.last_logged[path] = now

    def on_created(self, event):
        if not event.is_directory:
            self._process(event.src_path, "created")

    def on_modified(self, event):
        if not event.is_directory:
            self._process(event.src_path, "modified")

    def on_moved(self, event):
        # Atomic Save 대응 (메모장 등): 최종 경로(dest_path) 기준으로 처리
        if not event.is_directory:
            self._process(event.dest_path, "moved")

# ==========================================
# [5] 메인 루프 (Watchdog 다중 폴더 감시)
# ==========================================
def start_watchdog():
    db_connector = DBConnector()
    observer     = Observer()
    event_handler = MyFileEventHandler(db_connector)

    if not WATCH_PATHS:
        print("[경고] 감시할 폴더가 config.json에 없습니다. settings_ui에서 폴더를 추가해주세요.")
        # 폴더가 없어도 프로세스는 유지 (settings_ui에서 재시작 가능하도록)
        while True:
            time.sleep(5)

    for path in WATCH_PATHS:
        if os.path.exists(path):
            observer.schedule(event_handler, path, recursive=True)
            print(f"[센서 부착 완료] 타겟 폴더: {path}")
        else:
            print(f"[오류] 존재하지 않는 경로입니다 (무시됨): {path}")

    print("\n[LogBase 백그라운드 엔진 가동 중] (종료하려면 Ctrl+C 입력)\n")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_local_db()
    start_watchdog()
