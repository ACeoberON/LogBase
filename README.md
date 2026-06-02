# LogBase (SILA)

> **로컬 기반 개인 데이터 주권 인프라**
> 기업 클라우드에 의존하지 않는 Zero-Install 파일 활동 감시 데몬

---

## 개요

LogBase는 지정된 폴더의 파일 변경 이벤트를 감지하고, 해당 작업을 수행한 **앱(Process)** 과 **창 제목(Window Title)** 맥락을 추출하여 로컬 PostgreSQL에 영구 기록하는 백그라운드 데몬입니다.

- 외부 서버 없음 — 모든 데이터가 내 PC에만 저장
- 무설치(Zero-Install) — PostgreSQL 포터블 버전 내장
- 스텔스 동작 — 백그라운드에서 콘솔 창 없이 실행

---

## 시스템 요구사항

- Windows 10 / 11 (64bit)
- Python 3.10 이상 (소스 실행 시)
- 필요 패키지: `watchdog`, `psycopg2`, `psutil`, `pywin32`, `python-dotenv`

---

## 설치 및 실행

### 1. 저장소 클론

```bash
git clone https://github.com/your-repo/LogBase.git
cd LogBase
```

### 2. PostgreSQL 포터블 설치

`pgsql/` 폴더에 PostgreSQL 포터블 버전을 배치합니다.
구조는 다음과 같아야 합니다:

```
LogBase/
├── pgsql/
│   └── bin/
│       ├── pg_ctl.exe
│       ├── initdb.exe
│       └── psql.exe
```

> PostgreSQL 포터블 다운로드: https://www.postgresql.org/download/windows/

### 3. 환경 변수 설정

`.env` 파일을 프로젝트 루트에 생성합니다:

```
DB_HOST=localhost
DB_NAME=postgres
DB_USER=postgres
DB_PASS=
DB_PORT=5433
```

### 4. 패키지 설치 (소스 실행 시)

```bash
pip install watchdog psycopg2-binary psutil pywin32 python-dotenv
```

---

## 사용 방법

### 백그라운드 엔진 시작

```bash
# 소스 실행
python main.py

# 또는 빌드된 실행 파일
main.exe
```

### 설정 UI 실행

```bash
# 소스 실행
python settings_ui.py

# 또는 빌드된 실행 파일
settings_ui.exe
```

설정 UI에서:
1. **⚙️ 설정 탭** — 감시할 폴더 추가 및 허용 앱(Whitelist) 관리
2. **📋 로그 조회 탭** — 수집된 파일 활동 로그 검색 및 확인

---

## 핵심 아키텍처

```
[파일 이벤트 발생]
       ↓
[Whitelist 필터링] — 허용된 앱이 아니면 Drop
       ↓
[임시 파일 필터] — .tmp, .crdownload 등 제거
       ↓
[5초 디바운스] — 파일시스템 노이즈 제거
       ↓
[10분 세션 윈도우] — 같은 세션이면 UPDATE, 새 세션이면 INSERT
       ↓
[PostgreSQL 영구 기록]
```

### 수집 데이터 구조

| 컬럼 | 설명 |
|------|------|
| `timestamp` | 이벤트 발생 시각 |
| `file_path` | 파일 전체 경로 |
| `metadata.app_exe` | 작업 앱 이름 |
| `metadata.window_title` | 창 제목 |
| `metadata.event_type` | 이벤트 종류 (created / modified / moved) |

---

## 방어 로직

- **Early Exit 필터링**: 하위 항목 10,000개 초과 폴더 및 루트 드라이브(C:\\) 감시 차단
- **Atomic Save 대응**: `on_moved` 핸들러로 메모장 등의 임시파일→실제파일 저장 방식 처리
- **세션 기반 중복 제거**: 동일 파일 10분 이내 재저장 시 UPDATE로 처리
- **DB 안전 기동/종료**: `pg_ctl status` 확인 후 기동, `atexit`으로 안전 종료

---

## 빌드 (PyInstaller)

```bash
pip install pyinstaller

pyinstaller --onefile --noconsole main.py
pyinstaller --onefile --noconsole settings_ui.py
```

빌드 후 `dist/` 폴더의 `.exe` 파일을 프로젝트 루트로 복사하세요.

---

## 라이선스

MIT License
