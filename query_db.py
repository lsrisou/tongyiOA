"""
各学段 2026年7月、8月、10月 视频点击率对比

口径:
- 点击来源: tongyiedu_analysis.log_user_course_{1|20|33} (course_id > 0)
- 课程主数据: tyeducation.tifen_course (is_folder=0, type_id: 1章节, 2知识点)
- 点击率 = 被点击课程数 / 有效课程总数
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

STAGES    = [('小学',1,'log_user_course_1'),('初中',20,'log_user_course_20'),('高中',33,'log_user_course_33')]
MONTHS    = [
    ('2026年7月', '2026-07-01', '2026-08-01'),
    ('2026年8月', '2026-08-01', '2026-09-01'),
    ('2026年10月','2026-10-01', '2026-11-01'),
]
TYPE_LABEL = {1:'章节视频', 2:'知识点视频'}

# 拿课程总基数
cursor.execute("USE tyeducation")
BASE = {}
for tid in [1,2]:
    cursor.execute("SELECT COUNT(*) FROM tifen_course WHERE is_folder=0 AND type_id=%s", (tid,))
    BASE[tid] = cursor.fetchone()[0]

print("="*100)
print("各学段 2026年7月 / 8月 / 10月 视频点击率对比")
print(f"课程基数: type_id=1 章节视频 {BASE[1]:,} 条 | type_id=2 知识点视频 {BASE[2]:,} 条")
print("="*100)

# 月度 × 学段 × 类型 统计
results = {}

for month_label, dstart, dend in MONTHS:
    print(f"\n{'═'*100}")
    print(f"▶ {month_label}  (log_date: {dstart} ~ {dend})")
    print(f"{'═'*100}")

    for stage_name, plate_id, log_table in STAGES:
        cursor.execute("USE tongyiedu_analysis")

        # 学段该月活跃用户数
        cursor.execute(f"""
            SELECT COUNT(DISTINCT user_id)
            FROM `{log_table}`
            WHERE log_date >= '{dstart}' AND log_date < '{dend}'
        """)
        stage_users = cursor.fetchone()[0]

        print(f"\n  [{stage_name}] 活跃用户 {stage_users:,}")

        results[(month_label, stage_name)] = {}

        for tid, tlabel in TYPE_LABEL.items():
            cursor.execute("USE tyeducation")

            cursor.execute(f"""
                SELECT COUNT(DISTINCT l.course_id), COUNT(*), COUNT(DISTINCT l.user_id)
                FROM tongyiedu_analysis.`{log_table}` l
                JOIN tyeducation.tifen_course c ON l.course_id = c.id
                WHERE l.log_date >= '{dstart}' AND l.log_date < '{dend}'
                  AND l.course_id > 0
                  AND c.is_folder = 0
                  AND c.type_id = %s
            """, (tid,))
            clicked, clicks, click_users = cursor.fetchone()
            rate = clicked / BASE[tid] * 100 if BASE[tid] else 0
            user_rate = click_users / stage_users * 100 if stage_users else 0

            results[(month_label, stage_name)][tid] = {
                'clicked': clicked, 'clicks': clicks, 'click_users': click_users,
                'rate': rate, 'user_rate': user_rate, 'stage_users': stage_users,
            }
            print(f"    {tlabel}: 被点击 {clicked:,}/{BASE[tid]:,} ({rate:.2f}%) | 总点击 {clicks:,} | 用户 {click_users:,}/{stage_users:,} ({user_rate:.2f}%)")

# ============ 趋势对比表 ============
print(f"\n{'='*100}")
print("【汇总趋势对比表】")
print(f"{'='*100}")

# 表1: 点击率 %
print(f"\n▶ 各学段各类型 点击率 (%) —— 月度对比")
header = f"{'学段':>6}  |  {'类型':>8}  |" + "".join(f" {m.split('年')[1].split('月')[0]:>6}月  |" for m,_,_ in MONTHS)
print(header)
print('─'*len(header))
for stage_name, _, _ in STAGES:
    for tid in [1, 2]:
        vals = []
        for m,_,_ in MONTHS:
            r = results[(m, stage_name)][tid]['rate']
            vals.append(f"{r:.2f}%")
        print(f"{stage_name:>6}  |  {TYPE_LABEL[tid]:>8}  |" + "".join(f" {v:>7}  |" for v in vals))

# 表2: 被点击课程数
print(f"\n▶ 各学段各类型 被点击课程数 —— 月度对比")
header = f"{'学段':>6}  |  {'类型':>8}  |" + "".join(f" {m:>10}  |" for m,_,_ in MONTHS)
print(header)
print('─'*len(header))
for stage_name, _, _ in STAGES:
    for tid in [1, 2]:
        vals = []
        for m,_,_ in MONTHS:
            vals.append(f"{results[(m, stage_name)][tid]['clicked']:,}")
        print(f"{stage_name:>6}  |  {TYPE_LABEL[tid]:>8}  |" + "".join(f" {v:>10}  |" for v in vals))

# 表3: 总点击次数
print(f"\n▶ 各学段各类型 总点击次数 —— 月度对比")
header = f"{'学段':>6}  |  {'类型':>8}  |" + "".join(f" {m:>12}  |" for m,_,_ in MONTHS)
print(header)
print('─'*len(header))
for stage_name, _, _ in STAGES:
    for tid in [1, 2]:
        vals = []
        for m,_,_ in MONTHS:
            vals.append(f"{results[(m, stage_name)][tid]['clicks']:,}")
        print(f"{stage_name:>6}  |  {TYPE_LABEL[tid]:>8}  |" + "".join(f" {v:>12}  |" for v in vals))

# 表4: 用户占比（有行为的活跃用户 %）
print(f"\n▶ 各学段各类型 点击用户占比 (%) —— 月度对比")
header = f"{'学段':>6}  |  {'类型':>8}  |" + "".join(f" {m.split('年')[1].split('月')[0]:>6}月  |" for m,_,_ in MONTHS)
print(header)
print('─'*len(header))
for stage_name, _, _ in STAGES:
    for tid in [1, 2]:
        vals = []
        for m,_,_ in MONTHS:
            vals.append(f"{results[(m, stage_name)][tid]['user_rate']:.2f}%")
        print(f"{stage_name:>6}  |  {TYPE_LABEL[tid]:>8}  |" + "".join(f" {v:>7}  |" for v in vals))

# 活跃用户数参考
print(f"\n▶ 各学段 活跃用户数（参考基数）")
for stage_name, _, _ in STAGES:
    vals = []
    for m,_,_ in MONTHS:
        vals.append(f"{results[(m, stage_name)][1]['stage_users']:,}")
    print(f"  {stage_name}:  " + "".join(f" {m}: {v}  " for (m,_,_), v in zip(MONTHS, vals)))

cursor.close()
conn.close()
transport.close()
print("\n完成!")
