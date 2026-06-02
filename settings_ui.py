import sys
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import psutil

# --- [PyInstaller 호환성 패치] ---
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# ---------------------------------

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "watch_paths": [],
    "allowed_apps": ["chrome.exe", "code.exe", "winword.exe", "powerpnt.exe", "excel.exe", "hwp.exe"]
}

# ==========================================
# [공통] 앱 검색 및 선택 다이얼로그
# ==========================================
class AppSelectDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("앱 검색 및 추가")
        self.geometry("350x450")
        self.resizable(False, False)
        self.result = None

        common_apps = {"chrome.exe", "code.exe", "winword.exe", "excel.exe", "powerpnt.exe", "hwp.exe", "notepad.exe", "kakao.exe"}
        try:
            running_apps = {p.info['name'].lower() for p in psutil.process_iter(['name']) if p.info['name'] and p.info['name'].endswith('.exe')}
        except:
            running_apps = set()

        self.all_apps = sorted(list(common_apps | running_apps))

        tk.Label(self, text="🔍 프로그램 이름 검색 (예: chrome):", font=("맑은 고딕", 10, "bold")).pack(pady=(15, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.update_list)
        tk.Entry(self, textvariable=self.search_var, width=40).pack(pady=5)

        self.listbox = tk.Listbox(self, width=40, height=15, font=("맑은 고딕", 9))
        self.listbox.pack(pady=5)
        self.listbox.bind('<Double-1>', self.on_select)

        tk.Button(self, text="이 앱 추가하기", command=self.on_select, bg="#e0f7fa", width=20, font=("맑은 고딕", 9, "bold")).pack(pady=10)

        self.update_list()
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def update_list(self, *args):
        search_term = self.search_var.get().lower()
        self.listbox.delete(0, tk.END)
        for app in self.all_apps:
            if search_term in app:
                self.listbox.insert(tk.END, app)

    def on_select(self, event=None):
        selection = self.listbox.curselection()
        if selection:
            self.result = self.listbox.get(selection[0])
            self.destroy()


# ==========================================
# [탭 1] 설정 패널
# ==========================================
class SettingsTab(tk.Frame):
    def __init__(self, parent, config, save_callback):
        super().__init__(parent)
        self.config = config
        self.save_callback = save_callback
        self._build_ui()

    def _build_ui(self):
        # --- 감시 폴더 영역 ---
        tk.Label(self, text="📁 감시할 데이터 폴더 목록", font=("맑은 고딕", 11, "bold")).pack(pady=(15, 5))
        self.folder_listbox = tk.Listbox(self, width=60, height=6, font=("맑은 고딕", 9))
        self.folder_listbox.pack(pady=5)

        folder_btn_frame = tk.Frame(self)
        folder_btn_frame.pack(pady=5)
        tk.Button(folder_btn_frame, text="새 폴더 추가 (+)", command=self.add_folder, width=14, bg="#e0f7fa").pack(side=tk.LEFT, padx=5)
        tk.Button(folder_btn_frame, text="선택 폴더 삭제 (-)", command=self.remove_folder, width=14, bg="#ffebee").pack(side=tk.LEFT, padx=5)

        tk.Frame(self, height=2, bd=1, relief=tk.SUNKEN).pack(fill=tk.X, padx=20, pady=15)

        # --- 화이트리스트 영역 ---
        tk.Label(self, text="🛡️ 데이터 수집을 허용할 앱 (Whitelist)", font=("맑은 고딕", 11, "bold")).pack(pady=5)
        self.app_listbox = tk.Listbox(self, width=60, height=6, font=("맑은 고딕", 9))
        self.app_listbox.pack(pady=5)

        app_btn_frame = tk.Frame(self)
        app_btn_frame.pack(pady=5)
        tk.Button(app_btn_frame, text="앱 리스트에서 찾기", command=self.add_app, width=16, bg="#e0f7fa").pack(side=tk.LEFT, padx=5)
        tk.Button(app_btn_frame, text="선택 앱 삭제 (-)", command=self.remove_app, width=14, bg="#ffebee").pack(side=tk.LEFT, padx=5)

        tk.Frame(self, height=2, bd=1, relief=tk.SUNKEN).pack(fill=tk.X, padx=20, pady=15)

        # --- 저장 버튼 ---
        tk.Button(self, text="최종 설정 저장", command=self.save_callback, width=20, height=2, bg="#c8e6c9", font=("맑은 고딕", 10, "bold")).pack(pady=5)

        self.refresh_listboxes()

    def refresh_listboxes(self):
        self.folder_listbox.delete(0, tk.END)
        for path in self.config.get("watch_paths", []):
            self.folder_listbox.insert(tk.END, path)

        self.app_listbox.delete(0, tk.END)
        for app in self.config.get("allowed_apps", []):
            self.app_listbox.insert(tk.END, app)

    def is_safe_directory(self, target_path, max_limit=10000):
        blacklist = ["\\windows", "\\program files", "\\appdata", "\\programdata"]
        lower_path = target_path.lower()
        if any(b in lower_path for b in blacklist):
            return False, "OS 시스템 폴더나 프로그램 설치 폴더는 감시할 수 없습니다."
        if len(target_path) <= 3 and target_path.endswith("\\"):
            return False, "드라이브 전체(C:\\ 등)는 감시할 수 없습니다."
        item_count = 0
        try:
            for root, dirs, files in os.walk(target_path):
                item_count += len(dirs) + len(files)
                if item_count > max_limit:
                    return False, f"내부 파일이 너무 많습니다 (>{max_limit}개).\n시스템 부하를 막기 위해 더 세부적인 하위 폴더를 선택해 주세요."
        except PermissionError:
            return False, "관리자 권한이 필요한 접근 불가 폴더입니다."
        return True, "안전"

    def add_folder(self):
        folder_selected = filedialog.askdirectory(title="감시할 폴더를 선택하세요")
        if folder_selected:
            folder_selected = os.path.normpath(folder_selected)
            is_safe, error_msg = self.is_safe_directory(folder_selected)
            if not is_safe:
                messagebox.showwarning("보안 경고", error_msg)
                return
            if folder_selected not in self.config.get("watch_paths", []):
                self.config.setdefault("watch_paths", []).append(folder_selected)
                self.refresh_listboxes()

    def remove_folder(self):
        selected = self.folder_listbox.curselection()
        if selected:
            del self.config["watch_paths"][selected[0]]
            self.refresh_listboxes()

    def add_app(self):
        dialog = AppSelectDialog(self.master.master)
        if dialog.result:
            if dialog.result not in self.config.get("allowed_apps", []):
                self.config.setdefault("allowed_apps", []).append(dialog.result)
                self.refresh_listboxes()

    def remove_app(self):
        selected = self.app_listbox.curselection()
        if selected:
            del self.config["allowed_apps"][selected[0]]
            self.refresh_listboxes()


# ==========================================
# [탭 2] 로그 조회 패널
# ==========================================
class LogViewerTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.log_data = {}  # tree item id → full file path
        # --- 상단 필터 영역 ---
        filter_frame = tk.Frame(self)
        filter_frame.pack(fill=tk.X, padx=15, pady=(15, 5))

        tk.Label(filter_frame, text="📅 날짜:", font=("맑은 고딕", 9)).pack(side=tk.LEFT)
        self.date_filter_var = tk.StringVar(value="전체")
        self.date_filter_combo = ttk.Combobox(filter_frame, textvariable=self.date_filter_var, width=13, state="readonly", font=("맑은 고딕", 9))
        self.date_filter_combo.pack(side=tk.LEFT, padx=(5, 12))

        tk.Label(filter_frame, text="🔍 파일명:", font=("맑은 고딕", 9)).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        tk.Entry(filter_frame, textvariable=self.search_var, width=16, font=("맑은 고딕", 9)).pack(side=tk.LEFT, padx=(5, 12))

        tk.Label(filter_frame, text="앱:", font=("맑은 고딕", 9)).pack(side=tk.LEFT)
        self.app_filter_var = tk.StringVar(value="전체")
        self.app_filter_combo = ttk.Combobox(filter_frame, textvariable=self.app_filter_var, width=13, state="readonly", font=("맑은 고딕", 9))
        self.app_filter_combo.pack(side=tk.LEFT, padx=(5, 12))

        tk.Button(filter_frame, text="🔄 새로고침", command=self.load_logs, bg="#e3f2fd", font=("맑은 고딕", 9, "bold"), width=10).pack(side=tk.LEFT)

        # --- 테이블 영역 ---
        table_frame = tk.Frame(self)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        columns = ("timestamp", "filename", "event_type", "app", "window_title")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=18)

        self.tree.heading("timestamp", text="시간")
        self.tree.heading("filename", text="파일명")
        self.tree.heading("event_type", text="이벤트")
        self.tree.heading("app", text="앱")
        self.tree.heading("window_title", text="창 제목")

        self.tree.column("timestamp", width=135, anchor="center")
        self.tree.column("filename", width=140)
        self.tree.column("event_type", width=70, anchor="center")
        self.tree.column("app", width=100, anchor="center")
        self.tree.column("window_title", width=190)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 행 클릭 시 전체 경로 표시
        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)

        # --- 하단 경로 표시 영역 ---
        path_frame = tk.Frame(self, bg="#f5f5f5", relief=tk.SUNKEN, bd=1)
        path_frame.pack(fill=tk.X, padx=15, pady=(4, 2))
        tk.Label(path_frame, text="경로:", font=("맑은 고딕", 8), bg="#f5f5f5", fg="gray").pack(side=tk.LEFT, padx=5)
        self.path_var = tk.StringVar(value="행을 클릭하면 전체 경로가 표시됩니다.")
        tk.Label(path_frame, textvariable=self.path_var, font=("맑은 고딕", 8), bg="#f5f5f5", fg="#333", anchor="w").pack(side=tk.LEFT, fill=tk.X)

        # --- 하단 상태바 ---
        self.status_var = tk.StringVar(value="새로고침 버튼을 눌러 로그를 불러오세요.")
        tk.Label(self, textvariable=self.status_var, font=("맑은 고딕", 8), fg="gray").pack(pady=(2, 8))

    def _on_row_select(self, event):
        selected = self.tree.selection()
        if selected:
            self.path_var.set(self.log_data.get(selected[0], ""))

    def load_logs(self):
        try:
            import psycopg2
            from dotenv import load_dotenv
            load_dotenv(os.path.join(BASE_DIR, ".env"))

            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                database=os.getenv("DB_NAME", "postgres"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASS", ""),
                port=os.getenv("DB_PORT", "5433")
            )
            cur = conn.cursor()
            cur.execute("SELECT timestamp, file_path, metadata FROM file_logs ORDER BY timestamp DESC LIMIT 200;")
            rows = cur.fetchall()
            cur.close()
            conn.close()

            # 날짜 필터 목록 갱신 (최신순)
            dates = sorted(set(row[0].strftime("%Y-%m-%d") for row in rows), reverse=True)
            self.date_filter_combo["values"] = ["전체"] + dates

            # 앱 필터 목록 갱신
            apps = sorted(set(row[2].get("app_exe", "unknown") for row in rows))
            self.app_filter_combo["values"] = ["전체"] + apps

            # 필터 적용
            search_term = self.search_var.get().lower()
            app_filter = self.app_filter_var.get()
            date_filter = self.date_filter_var.get()

            self.tree.delete(*self.tree.get_children())
            self.log_data.clear()
            count = 0
            for row in rows:
                ts = row[0].strftime("%Y-%m-%d %H:%M:%S")
                full_path = row[1]
                filename = os.path.basename(full_path)
                app_exe = row[2].get("app_exe", "unknown")
                window = row[2].get("window_title", "")

                if date_filter != "전체" and not ts.startswith(date_filter):
                    continue
                if search_term and search_term not in filename.lower():
                    continue
                if app_filter != "전체" and app_exe != app_filter:
                    continue

                event_type_map = {"created": "생성", "modified": "수정", "moved": "저장"}
                event_type = event_type_map.get(row[2].get("event_type", ""), "-")
                item_id = self.tree.insert("", tk.END, values=(ts, filename, event_type, app_exe, window))
                self.log_data[item_id] = full_path
                count += 1

            self.status_var.set(f"총 {count}개 기록 표시 중  (전체 {len(rows)}건 중 필터 적용)")

        except Exception as e:
            self.status_var.set(f"[오류] DB 연결 실패: {e}  — main.exe가 실행 중인지 확인하세요.")


# ==========================================
# 메인 앱 (탭 컨테이너)
# ==========================================
class LogBaseUI:
    def __init__(self, root):
        self.root = root
        self.root.title("LogBase 관제 센터 (SILA)")
        self.root.geometry("720x620")
        self.root.resizable(False, False)

        self.config = self.load_config()

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True)

        # 탭 1: 설정
        self.settings_tab = SettingsTab(notebook, self.config, self.save_config)
        notebook.add(self.settings_tab, text="  ⚙️ 설정  ")

        # 탭 2: 로그 조회
        self.log_tab = LogViewerTab(notebook)
        notebook.add(self.log_tab, text="  📋 로그 조회  ")

        # 로그 탭 선택 시 자동 새로고침
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _on_tab_change(self, event):
        selected = event.widget.index("current")
        if selected == 1:
            self.log_tab.load_logs()

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return DEFAULT_CONFIG
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return DEFAULT_CONFIG

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)

            engine_restarted = False
            if getattr(sys, 'frozen', False):
                import time, subprocess

                # 1. PostgreSQL 먼저 즉시 강제 종료
                pg_ctl  = os.path.join(BASE_DIR, 'pgsql', 'bin', 'pg_ctl.exe')
                pg_data = os.path.join(BASE_DIR, 'pgsql', 'data')
                if os.path.exists(pg_ctl):
                    subprocess.run(
                        [pg_ctl, "-D", pg_data, "stop", "-m", "fast"],
                        creationflags=0x08000000,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    time.sleep(1)

                # 2. 모든 main.exe 프로세스 종료 후 완전히 죽을 때까지 대기
                targets = [p for p in psutil.process_iter(['name', 'pid'])
                           if p.info['name'] == 'main.exe']
                for proc in targets:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                # 최대 5초간 완전 종료 확인
                for _ in range(10):
                    time.sleep(0.5)
                    still_alive = [p for p in psutil.process_iter(['name'])
                                   if p.info['name'] == 'main.exe']
                    if not still_alive:
                        break

                time.sleep(0.5)

                # 3. 새 main.exe 기동 (내부에서 pg_ctl status 확인 후 start)
                main_exe_path = os.path.join(BASE_DIR, "main.exe")
                if os.path.exists(main_exe_path):
                    subprocess.Popen([main_exe_path], creationflags=0x08000000 | 0x00000008)  # CREATE_NO_WINDOW | DETACHED_PROCESS
                    engine_restarted = True

            msg = "설정이 성공적으로 저장되었습니다."
            if engine_restarted:
                msg += "\n(백그라운드 엔진이 새 설정으로 자동 재시작되었습니다.)"

            messagebox.showinfo("저장 완료", msg)
            self.settings_tab.refresh_listboxes()

        except Exception as e:
            messagebox.showerror("저장 실패", f"설정 저장 중 오류가 발생했습니다: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = LogBaseUI(root)
    root.mainloop()
