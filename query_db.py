"""
各学段 2026年10月 视频点击率统计

数据口径:
- 点击来源: tongyiedu_analysis.log_user_course_{plate} (course_id > 0, log_date 2026-10)
- 课程主数据: tyeducation.tifen_course
    is_folder = 0  (有效课程, 非文件夹)
    type_id = 1    (章节视频)
    type_id = 2    (知识点视频)
- 学段对应: plate_id 1=小学, 20=初中, 33=高中

点击率 = 被点击的课程数 / 有效课程总数
"""
import socket, threading, time, pymysql, paramiko

PROXY_HOST='127.0.0.1'; PROXY_PORT=18080
SSH_HOST='8.141.117.235'; SSH_PORT=22; SSH_USER='dev_risou'; SSH_PASS='TLiRisou2008'
DB_HOST='rm-2zetutg9456f757u9.mysql.rds.aliyuncs.com'; DB_PORT=3306
DB_USER='tyedu'; DB_PASS='YpDcaxw4fQWTR0DLz7ocKhZPMy0Z1'
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

conn=pymysql.connect(host='127.0.0.1',port=LOCAL_PORT,user=DB_USER,password=DB_PASS,charset='utf8mb4',connect_timeout=30)
cursor=conn.cursor()

# 配置
STAGES = [
    ('小学',  1,  'log_user_course_1'),
    ('初中',  20, 'log_user_course_20'),
    ('高中',  33, 'log_user_course_33'),
]

TYPE_LABEL = {1: '章节视频', 2: '知识点视频'}
DATE_START = '2026-10-01'
DATE_END   = '2026-11-01'

print("="*80)
print("各学段 2026年10月 视频点击率统计")
print("口径: 点击率 = 被点击的课程数 / 有效课程总数 (is_folder=0, type_id IN 1,2)")
print("="*80)

# ============ 先拿到各 type_id 的有效课程总数 ============
cursor.execute("USE tyeducation")
print("\n【有效课程总基数】tyeducation.tifen_course (is_folder=0)")
total_base = {}
for tid in [1, 2]:
    cursor.execute("SELECT COUNT(*) FROM tifen_course WHERE is_folder=0 AND type_id=%s", (tid,))
    cnt = cursor.fetchone()[0]
    total_base[tid] = cnt
    print(f"  type_id={tid} {TYPE_LABEL[tid]}: {cnt:,}")

# 全部有效课程（不区分学段，主库是全量的）
cursor.execute("SELECT COUNT(*) FROM tifen_course WHERE is_folder=0 AND type_id IN (1,2)")
all_total = cursor.fetchone()[0]
print(f"  合计: {all_total:,}")

# ============ 分学段统计 ============
print(f"\n{'='*80}")
print("【各学段 2026-10 点击率明细】")
print(f"{'='*80}")

summary = []

for stage_name, plate_id, log_table in STAGES:
    print(f"\n{'─'*80}")
    print(f"▶ {stage_name} (plate_id={plate_id}, 日志表={log_table})")
    print(f"{'─'*80}")

    cursor.execute("USE tongyiedu_analysis")

    # 该学段 10月 总日志数 & 有效 course_id 日志数
    cursor.execute(f"""
        SELECT COUNT(*), SUM(CASE WHEN course_id > 0 THEN 1 ELSE 0 END),
               COUNT(DISTINCT user_id), COUNT(DISTINCT CASE WHEN course_id > 0 THEN user_id END)
        FROM `{log_table}`
        WHERE log_date >= '{DATE_START}' AND log_date < '{DATE_END}'
    """)
    total_logs, valid_logs, total_users, active_users = cursor.fetchone()
    print(f"  10月日志总条数: {total_logs:,}  有效(course_id>0): {valid_logs:,}")
    print(f"  总活跃用户数: {total_users:,}  有课程行为用户: {active_users:,}")

    cursor.execute("USE tyeducation")

    stage_row = {'stage': stage_name}

    for tid, tlabel in TYPE_LABEL.items():
        # 该类型有效课程总数
        cursor.execute("SELECT COUNT(*) FROM tifen_course WHERE is_folder=0 AND type_id=%s", (tid,))
        total_courses = cursor.fetchone()[0]

        # 被点击的 distinct course_id 数（10月内）
        cursor.execute(f"""
            SELECT COUNT(DISTINCT l.course_id)
            FROM tongyiedu_analysis.`{log_table}` l
            JOIN tyeducation.tifen_course c ON l.course_id = c.id
            WHERE l.log_date >= '{DATE_START}' AND l.log_date < '{DATE_END}'
              AND l.course_id > 0
              AND c.is_folder = 0
              AND c.type_id = %s
        """, (tid,))
        clicked_courses = cursor.fetchone()[0]

        # 总点击次数
        cursor.execute(f"""
            SELECT COUNT(*)
            FROM tongyiedu_analysis.`{log_table}` l
            JOIN tyeducation.tifen_course c ON l.course_id = c.id
            WHERE l.log_date >= '{DATE_START}' AND l.log_date < '{DATE_END}'
              AND l.course_id > 0
              AND c.is_folder = 0
              AND c.type_id = %s
        """, (tid,))
        total_clicks = cursor.fetchone()[0]

        # 点击用户数
        cursor.execute(f"""
            SELECT COUNT(DISTINCT l.user_id)
            FROM tongyiedu_analysis.`{log_table}` l
            JOIN tyeducation.tifen_course c ON l.course_id = c.id
            WHERE l.log_date >= '{DATE_START}' AND l.log_date < '{DATE_END}'
              AND l.course_id > 0
              AND c.is_folder = 0
              AND c.type_id = %s
        """, (tid,))
        clicking_users = cursor.fetchone()[0]

        rate = (clicked_courses / total_courses * 100) if total_courses > 0 else 0
        user_rate = (clicking_users / total_users * 100) if total_users > 0 else 0

        stage_row[tlabel] = {
            'total_courses': total_courses,
            'clicked_courses': clicked_courses,
            'total_clicks': total_clicks,
            'clicking_users': clicking_users,
            'total_users': total_users,
            'rate': rate,
            'user_rate': user_rate,
        }

        print(f"\n  【{tlabel}】")
        print(f"    有效课程总数: {total_courses:,}")
        print(f"    被点击课程数: {clicked_courses:,}  ({rate:.2f}%)")
        print(f"    总点击次数:   {total_clicks:,}")
        print(f"    点击用户数:   {clicking_users:,} / {total_users:,} ({user_rate:.2f}%)")

    summary.append(stage_row)

# ============ 汇总对比表 ============
print(f"\n{'='*80}")
print("【汇总对比】各学段 2026年10月 点击率")
print(f"{'='*80}")

header = f"{'学段':>6}  | {'类型':>8}  | {'课程总数':>10}  | {'被点击数':>10}  | {'点击率':>8}  | {'点击次数':>10}  | {'点击用户':>8}  | {'用户占比':>8}"
print(header)
print('─' * len(header))

for row in summary:
    for tid in [1, 2]:
        d = row[TYPE_LABEL[tid]]
        print(
            f"{row['stage']:>6}  | {TYPE_LABEL[tid]:>8}  | "
            f"{d['total_courses']:>10,}  | {d['clicked_courses']:>10,}  | "
            f"{d['rate']:>7.2f}%  | {d['total_clicks']:>10,}  | "
            f"{d['clicking_users']:>8,}  | {d['user_rate']:>7.2f}%"
        )

cursor.close()
conn.close()
transport.close()
print("\n统计完成!")
