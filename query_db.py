"""完整统计 - 修复版"""
import socket, threading, time, pymysql, paramiko

PROXY_HOST='127.0.0.1'; PROXY_PORT=18080
SSH_HOST='8.141.117.235'; SSH_PORT=22; SSH_USER='dev_risou'; SSH_PASS='TLiRisou2008'
DB_HOST='rm-2zetutg9456f757u9.mysql.rds.aliyuncs.com'; DB_PORT=3306
DB_USER='tyedu'; DB_PASS='YpDcaxw4fQWTR0DLz7ocKhZPMy0Z1'; DB_NAME='tongyiedu_analysis'
LOCAL_PORT=23306

def create_proxy_socket(h,p):
    s=socket.socket(); s.settimeout(15); s.connect((PROXY_HOST,PROXY_PORT))
    s.sendall(f"CONNECT {h}:{p} HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n".encode())
    r=b''
    while b'\r\n\r\n' not in r:
        c=s.recv(4096)
        if not c: break
        r+=c
    s.settimeout(None); return s

ssh_sock=create_proxy_socket(SSH_HOST,SSH_PORT)
transport=paramiko.Transport(ssh_sock); transport.connect(username=SSH_USER,password=SSH_PASS)
server=socket.socket(); server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
server.bind(('127.0.0.1',LOCAL_PORT)); server.listen(5)
def forward(src,dst):
    try:
        while True:
            d=src.recv(65536)
            if not d: break
            dst.sendall(d)
    except: pass
    try: dst.close(); src.close()
    except: pass
def handle(c):
    ch=transport.open_channel('direct-tcpip',(DB_HOST,DB_PORT),('127.0.0.1',0))
    threading.Thread(target=forward,args=(c,ch),daemon=True).start()
    threading.Thread(target=forward,args=(ch,c),daemon=True).start()
    time.sleep(600)
threading.Thread(target=lambda:[threading.Thread(target=handle,args=(c,),daemon=True).start() for c,_ in iter(server.accept,None)],daemon=True).start()
time.sleep(1)

conn=pymysql.connect(host='127.0.0.1',port=LOCAL_PORT,user=DB_USER,password=DB_PASS,database=DB_NAME,charset='utf8mb4',connect_timeout=30)
cursor=conn.cursor()

# ============ 1. 请求日志中视频/知识点相关 URL 统计 ============
print("="*70)
print("【1】请求日志 - 视频/知识点相关 API 调用统计 (最近月表 tifen_request_log_202611)")
print("="*70)

LATEST_LOG = 'tifen_request_log_202611'
print(f"\n  按 request_url 分组 - 视频相关 TOP:")
cursor.execute(f"""
    SELECT request_url, COUNT(*) as cnt 
    FROM `{LATEST_LOG}` 
    WHERE request_url LIKE '%video%' OR request_url LIKE '%Video%'
    GROUP BY request_url 
    ORDER BY cnt DESC 
    LIMIT 20
""")
for row in cursor.fetchall():
    print(f"    {row[1]:>8,}  {row[0]}")

print(f"\n  按 request_url 分组 - 知识点/学习相关 TOP:")
cursor.execute(f"""
    SELECT request_url, COUNT(*) as cnt 
    FROM `{LATEST_LOG}` 
    WHERE request_url LIKE '%knowledge%' OR request_url LIKE '%point%' 
       OR request_url LIKE '%study%' OR request_url LIKE '%learn%'
       OR request_url LIKE '%course%' OR request_url LIKE '%chapter%'
       OR request_url LIKE '%resource%' OR request_url LIKE '%ceping%'
       OR request_url LIKE '%homework%'
    GROUP BY request_url 
    ORDER BY cnt DESC 
    LIMIT 20
""")
for row in cursor.fetchall():
    print(f"    {row[1]:>8,}  {row[0]}")

# ============ 2. 历史请求日志汇总 ============
print(f"\n{'='*70}")
print("【2】请求日志 - 视频 API 历史汇总 (2026年至今)")
print("="*70)

cursor.execute("SHOW TABLES LIKE 'tifen_request_log_2026%'")
tables_2026 = [t[0] for t in cursor.fetchall()]

video_total = 0
for t in tables_2026:
    try:
        cursor.execute(f"""
            SELECT SUM(CASE WHEN request_url LIKE '%video%' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN request_url LIKE '%knowledge%' OR request_url LIKE '%point%' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN request_url LIKE '%ceping%' THEN 1 ELSE 0 END)
            FROM `{t}`
        """)
        v, k, c = cursor.fetchone()
        m = t.split('_')[-1]
        print(f"  {t}: 视频请求={v or 0:>8,}  知识点={k or 0:>8,}  测评={c or 0:>8,}")
        video_total += v or 0
    except Exception as e:
        print(f"  {t}: 错误 {e}")

# ============ 3. tifen_user_book_view 章节点击完整统计 ============
print(f"\n{'='*70}")
print("【3】章节点击完整汇总 (tifen_user_book_view 系列)")
print("="*70)

all_view_tables = ['tifen_user_book_view_1', 'tifen_user_book_view_20', 'tifen_user_book_view_33']

print(f"\n  各平台明细:")
print(f"  {'表名':<30} {'点击总数':>12} {'独立用户':>12} {'有效章节点击':>14}")
print(f"  {'-'*72}")
total_clicks = 0; total_valid = 0; total_users_set = set()
for table in all_view_tables:
    cursor.execute(f"SELECT COUNT(*), COUNT(DISTINCT user_id), SUM(CASE WHEN chapter_id > 0 THEN 1 ELSE 0 END) FROM `{table}`")
    total, users, valid = cursor.fetchone()
    total_clicks += total
    total_valid += valid
    cursor.execute(f"SELECT DISTINCT user_id FROM `{table}`")
    for u in cursor.fetchall():
        total_users_set.add(u[0])
    print(f"  {table:<30} {total:>12,} {users:>12,} {valid:>14,}")
print(f"  {'合计':<30} {total_clicks:>12,} {len(total_users_set):>12,} {total_valid:>14,}")

# 合并后 TOP 章节
print(f"\n  全部合并后 TOP 20 章节点击:")
union_sql = " UNION ALL ".join([f"SELECT chapter_id, book_id FROM `{t}` WHERE chapter_id > 0" for t in all_view_tables])
cursor.execute(f"""
    SELECT chapter_id, book_id, COUNT(*) as clicks
    FROM ({union_sql}) all_views
    GROUP BY chapter_id, book_id
    ORDER BY clicks DESC
    LIMIT 20
""")
print(f"  {'排名':>4}  {'chapter_id':>12}  {'book_id':>10}  {'点击数':>10}")
print(f"  {'-'*42}")
for i, row in enumerate(cursor.fetchall(), 1):
    print(f"  {i:>4}  {row[0]:>12,}  {row[1]:>10,}  {row[2]:>10,}")

# ============ 4. log_user_study 学习日志 ============
print(f"\n{'='*70}")
print("【4】log_user_study 学习日志")
print("="*70)
for table in ['log_user_study_1', 'log_user_study_20', 'log_user_study_33', 'log_user_study_400']:
    cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
    cnt = cursor.fetchone()[0]
    cursor.execute(f"DESCRIBE `{table}`")
    cols = [c[0] for c in cursor.fetchall()]
    print(f"\n  [{table}]  {cnt:,} 行  字段: {', '.join(cols)}")
    cursor.execute(f"SELECT * FROM `{table}` ORDER BY id DESC LIMIT 3")
    names = [d[0] for d in cursor.description]
    for row in cursor.fetchall():
        d = dict(zip(names, row))
        # 截断
        for k, v in list(d.items()):
            if isinstance(v, str) and len(v) > 120:
                d[k] = v[:120] + "..."
        print(f"    示例: {d}")

# ============ 5. log_user_course 课程日志 ============
print(f"\n{'='*70}")
print("【5】log_user_course 课程日志")
print("="*70)
for table in ['log_user_course_1', 'log_user_course_20', 'log_user_course_33', 'log_user_course_400']:
    cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
    cnt = cursor.fetchone()[0]
    cursor.execute(f"DESCRIBE `{table}`")
    cols = [c[0] for c in cursor.fetchall()]
    print(f"\n  [{table}]  {cnt:,} 行  字段: {', '.join(cols)}")
    cursor.execute(f"SELECT * FROM `{table}` ORDER BY id DESC LIMIT 2")
    names = [d[0] for d in cursor.description]
    for row in cursor.fetchall():
        d = dict(zip(names, row))
        for k, v in list(d.items()):
            if isinstance(v, str) and len(v) > 120:
                d[k] = v[:120] + "..."
        print(f"    示例: {d}")

# ============ 6. 教师知识点投放统计 ============
print(f"\n{'='*70}")
print("【6】tifen_teacher_daily_statistics 教师日常统计")
print("="*70)
cursor.execute("SELECT COUNT(*) FROM tifen_teacher_daily_statistics")
print(f"  总行数: {cursor.fetchone()[0]:,}")
cursor.execute("SELECT * FROM tifen_teacher_daily_statistics ORDER BY id DESC LIMIT 3")
names = [d[0] for d in cursor.description]
for row in cursor.fetchall():
    print(f"  {dict(zip(names, row))}")

print(f"\n  知识点投放 (knowledge_cast_num) 汇总:")
cursor.execute("""
    SELECT log_date, SUM(knowledge_cast_num) as total_cast
    FROM tifen_teacher_daily_statistics
    WHERE knowledge_cast_num > 0
    GROUP BY log_date
    ORDER BY log_date DESC
    LIMIT 15
""")
for row in cursor.fetchall():
    print(f"    {row[0]}  投放 {row[1]:>8,} 次")

cursor.close()
conn.close()
transport.close()
print("\n查询完成!")
