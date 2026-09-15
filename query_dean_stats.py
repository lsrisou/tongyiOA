import socket
import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timezone, timedelta
import paramiko
import pymysql

PROXY_HOST = '127.0.0.1'
PROXY_PORT = 18080

ssh_host = '8.141.117.235'
ssh_port = 22
ssh_username = 'dev_risou'
ssh_password = 'TLiRisou2008'

cfg = {
    'name': 'deshengoa',
    'host': 'rm-2zel54y4czcyl911h.mysql.rds.aliyuncs.com',
    'port': 3306,
    'user': 'deshengoa',
    'passwd': 'EZayyR4qDu7vA3EwSdeKAE8n',
    'db': 'deshengoa',
}

dean_id = 7600
dean_name = '胡蝶'

# 8月份 北京时间(UTC+8) 的 Unix 时间戳范围
BJ = timezone(timedelta(hours=8))
aug_start_ts = int(datetime(2026, 8, 1, 0, 0, 0, tzinfo=BJ).timestamp())   # 1785513600
aug_end_ts   = int(datetime(2026, 9, 1, 0, 0, 0, tzinfo=BJ).timestamp())   # 1788192000


def make_proxy_socket(target_host, target_port, timeout=30):
    s = socket.create_connection((PROXY_HOST, PROXY_PORT), timeout=timeout)
    req = (
        f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
        f"Host: {target_host}:{target_port}\r\n\r\n"
    ).encode()
    s.sendall(req)
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    first_line = buf.split(b"\r\n", 1)[0].decode("utf-8", "ignore")
    if "200" not in first_line:
        s.close()
        raise RuntimeError(f"代理 CONNECT 失败: {first_line}")
    return s


def open_ssh_client():
    sock = make_proxy_socket(ssh_host, ssh_port, timeout=30)
    transport = paramiko.Transport(sock)
    transport.connect(username=ssh_username, password=ssh_password)
    return transport


def query_via_transport(transport, sql, params=None, fetch='all'):
    chan = transport.open_channel('direct-tcpip', (cfg['host'], cfg['port']), ('127.0.0.1', 0))
    conn = pymysql.connect(host='127.0.0.1', user=cfg['user'], passwd=cfg['passwd'], db=cfg['db'], charset='utf8mb4', defer_connect=True)
    conn.connect(sock=chan)
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(sql, params or ())
    result = cur.fetchall() if fetch == 'all' else cur.fetchone()
    cur.close()
    conn.close()
    chan.close()
    return result


def ts_to_bj_str(ts):
    if ts is None:
        return ''
    return datetime.fromtimestamp(int(ts), tz=BJ).strftime('%Y-%m-%d %H:%M:%S')


print("正在通过代理建立 SSH 隧道...")
transport = open_ssh_client()
print("SSH 隧道建立成功\n")
print(f"查询范围: 8月份(北京时间) -> start_time in [{aug_start_ts}, {aug_end_ts})")
print(f"  即 {ts_to_bj_str(aug_start_ts)} ~ {ts_to_bj_str(aug_end_ts-1)}\n")

# 1. 校验教务信息
dean = query_via_transport(transport, """
    SELECT u.id AS dean_id, u.name AS dean_name, u.school_id, u.role_id, s.name AS school_name
    FROM de_admin_users u
    LEFT JOIN de_schools s ON u.school_id = s.id
    WHERE u.id = %s
""", (dean_id,), fetch='one')

print("=== 教务信息 ===")
if not dean:
    print(f"未找到 dean_id={dean_id} 的教务记录")
    transport.close()
    raise SystemExit(0)
print(f"教务ID: {dean['dean_id']}, 教务姓名: {dean['dean_name']}, role_id: {dean['role_id']}, school_id: {dean['school_id']}, 学校名称(de_schools.name): {dean['school_name']}")

# 2. 8月份课时明细(按 start_time Unix 时间戳筛选)
lessons = query_via_transport(transport, """
    SELECT
        l.id AS lesson_id,
        l.student_id,
        st.name AS student_name,
        l.start_time,
        l.end_time,
        l.hour_count,
        l.subject_id,
        l.lesson_type,
        l.hour_type,
        l.state,
        l.deleted_at,
        l.remark
    FROM de_student_hour_lessons l
    LEFT JOIN de_students st ON l.student_id = st.id
    WHERE l.dean_id = %s
      AND l.start_time >= %s
      AND l.start_time <  %s
    ORDER BY l.start_time ASC, l.id ASC
""", (dean_id, aug_start_ts, aug_end_ts), fetch='all')

print("\n=== 8月份课时明细 ===")
print(f"共 {len(lessons)} 条课程记录 (含全部 state; deleted_at 非空表示已软删除)")
total_hours = 0.0
active_hours = 0.0
deleted_count = 0
header = f"{'序号':<4}{'课程ID':<10}{'学生ID':<10}{'学生姓名':<14}{'上课时间(北京)':<22}{'课时':<6}{'state':<6}{'删除':<4}"
print(header)
print("-" * len(header.encode('utf-8')) + "-" * 40)
for i, r in enumerate(lessons, 1):
    st_name = r.get('student_name') or ''
    st_str = ts_to_bj_str(r['start_time'])
    hc = r['hour_count']
    hc_val = float(hc) if hc is not None else 0.0
    total_hours += hc_val
    if r['deleted_at'] is None:
        active_hours += hc_val
    else:
        deleted_count += 1
    del_mark = '是' if r['deleted_at'] is not None else ''
    print(f"{i:<4}{r['lesson_id']!s:<10}{r['student_id']!s:<10}{st_name:<14}{st_str:<22}{r['hour_count']!s:<6}{r['state']!s:<6}{del_mark:<4}")

print("\n=== 8月份课时统计 ===")
print(f"教务姓名: {dean_name} (ID={dean_id})")
print(f"学校名称: {dean['school_name']} (school_id={dean['school_id']})")
print(f"课程记录数(全部): {len(lessons)}")
print(f"课时总数(全部): {total_hours}")
print(f"  其中已软删除记录: {deleted_count} 条")
print(f"  有效课时(未删除): {active_hours}")

# 3. 按学生汇总(仅未删除)
student_rows = query_via_transport(transport, """
    SELECT
        l.student_id,
        st.name AS student_name,
        COUNT(*) AS lesson_count,
        SUM(l.hour_count) AS total_hours
    FROM de_student_hour_lessons l
    LEFT JOIN de_students st ON l.student_id = st.id
    WHERE l.dean_id = %s
      AND l.start_time >= %s
      AND l.start_time <  %s
      AND l.deleted_at IS NULL
    GROUP BY l.student_id, st.name
    ORDER BY total_hours DESC
""", (dean_id, aug_start_ts, aug_end_ts), fetch='all')

print("\n=== 按学生汇总(仅未软删除) ===")
print(f"{'学生ID':<10}{'学生姓名':<14}{'课程数':<8}{'课时总数':<10}")
print("-" * 45)
stu_total_hours = 0.0
stu_total_lessons = 0
for r in student_rows:
    name = r['student_name'] or ''
    h = float(r['total_hours']) if r['total_hours'] is not None else 0.0
    stu_total_hours += h
    stu_total_lessons += r['lesson_count']
    print(f"{r['student_id']!s:<10}{name:<14}{r['lesson_count']!s:<8}{r['total_hours']!s:<10}")
print("-" * 45)
print(f"{'合计':<24}{stu_total_lessons:<8}{stu_total_hours:<10}")

transport.close()
print("\n查询完成")
