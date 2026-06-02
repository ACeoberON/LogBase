import psycopg2
import os

try:
    print("\n[SILA 요새 검문소] 백그라운드 엔진이 수집한 최근 5개 기록\n" + "="*60)
    conn = psycopg2.connect(host="localhost", database="postgres", user="postgres", password="", port="5433")
    cur = conn.cursor()
    
    cur.execute("SELECT timestamp, file_path, metadata FROM file_logs ORDER BY timestamp DESC LIMIT 5;")
    rows = cur.fetchall()
    
    if not rows:
        print("텅 비어있습니다. 설정된 폴더에서 허용된 앱으로 파일을 건드려보세요.")
    else:
        for row in rows:
            time_str = row[0].strftime("%Y-%m-%d %H:%M:%S")
            file_name = os.path.basename(row[1])
            app_name = row[2].get('app_exe', 'unknown')
            window = row[2].get('window_title', 'unknown')
            
            print(f"[{time_str}] 📁 {file_name}")
            print(f"   └─ 💻 앱: {app_name} | 🪟 창 제목: {window}\n")
            
    cur.close()
    conn.close()
except Exception as e:
    print(f"[ERROR] DB 접속 실패. 요새가 꺼져있습니다: {e}")