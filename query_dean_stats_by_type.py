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

# 课程类型字典
LESSON_TYPES = {
    1: '正式课',
    2: '自交付课',
    3: '体验课',
    4: '预备教练试课',
}

BJ = timezone(timedelta(hours=8))
aug_start_ts = int(datetime(2026, 8, 1, 0, 0, 0, tzinfo=BJ).timestamp())
aug_end_ts   = int(datetime(2026, 9, 1, 0, 0, 0, tzinfo=BJ).timestamp())


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

# 教务信息
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
print(f"教务ID: {dean['dean_id']}, 教务姓名: {dean['dean_name']}, role_id: {dean['role_id']}, school_id: {dean['school_id']}, 学校名称(de_schools.name): {dean['school_name']}\n")

# 1. 按 lesson_type 统计(仅未软删除)
print("=== 按 lesson_type 统计(仅未软删除) ===")
type_rows = query_via_transport(transport, """
    SELECT
        l.lesson_type,
        COUNT(*) AS lesson_count,
        SUM(l.hour_count) AS total_hours
    FROM de_student_hour_lessons l
    WHERE l.dean_id = %s
      AND l.start_time >= %s
      AND l.start_time <  %s
      AND l.deleted_at IS NULL
    GROUP BY l.lesson_type
    ORDER BY l.lesson_type
""", (dean_id, aug_start_ts, aug_end_ts), fetch='all')

print(f"{'lesson_type':<12}{'类型说明':<14}{'课程数':<8}{'课时总数':<10}")
print("-" * 45)
grand_count = 0
grand_hours = 0.0
for r in type_rows:
    lt = r['lesson_type']
    desc = LESSON_TYPES.get(int(lt), '未知类型') if lt is not None else 'NULL'
    h = float(r['total_hours']) if r['total_hours'] is not None else 0.0
    grand_count += r['lesson_count']
    grand_hours += h
    print(f"{lt!s:<12}{desc:<14}{r['lesson_count']!s:<8}{h:<10}")
print("-" * 45)
print(f"{'合计':<26}{grand_count:<8}{grand_hours:<10}")

# 2. 按学生 + lesson_type 交叉统计(仅未软删除)
print("\n=== 按学生 × lesson_type 交叉统计(仅未软删除) ===")
cross_rows = query_via_transport(transport, """
    SELECT
        l.student_id,
        st.name AS student_name,
        l.lesson_type,
        COUNT(*) AS lesson_count,
        SUM(l.hour_count) AS total_hours
    FROM de_student_hour_lessons l
    LEFT JOIN de_students st ON l.student_id = st.id
    WHERE l.dean_id = %s
      AND l.start_time >= %s
      AND l.start_time <  %s
      AND l.deleted_at IS NULL
    GROUP BY l.student_id, st.name, l.lesson_type
    ORDER BY l.student_id, l.lesson_type
""", (dean_id, aug_start_ts, aug_end_ts), fetch='all')

# 组织成以学生为单位的横向汇总
student_agg = {}
for r in cross_rows:
    sid = r['student_id']
    name = r['student_name'] or ''
    if sid not in student_agg:
        student_agg[sid] = {'name': name, 'count': 0, 'hours': 0.0, 'types': {}}
    student_agg[sid]['name'] = name
    student_agg[sid]['count'] += r['lesson_count']
    h = float(r['total_hours']) if r['total_hours'] is not None else 0.0
    student_agg[sid]['hours'] += h
    student_agg[sid]['types'][int(r['lesson_type'])] = {
        'count': r['lesson_count'], 'hours': h
    }

# 按总课时降序
sorted_students = sorted(student_agg.items(), key=lambda kv: kv[1]['hours'], reverse=True)

# 表头
header_cols = ['学生ID', '学生姓名']
for lt in sorted(LESSON_TYPES.keys()):
    header_cols.append(f'{LESSON_TYPES[lt]}课数')
    header_cols.append(f'{LESSON_TYPES[lt]}课时')
header_cols += ['总课数', '总课时']
print(' '.join(header_cols))
print('-' * 130)

# 列合计
col_totals = {lt: {'count': 0, 'hours': 0.0} for lt in LESSON_TYPES}
total_count_all = 0
total_hours_all = 0.0
for sid, agg in sorted_students:
    row = [str(sid), agg['name']]
    for lt in sorted(LESSON_TYPES.keys()):
        t = agg['types'].get(lt, {'count': 0, 'hours': 0.0})
        row.append(str(t['count']))
        row.append(f"{t['hours']:.2f}")
        col_totals[lt]['count'] += t['count']
        col_totals[lt]['hours'] += t['hours']
    row.append(str(agg['count']))
    row.append(f"{agg['hours']:.2f}")
    total_count_all += agg['count']
    total_hours_all += agg['hours']
    print(' '.join(f"{c:<10}" for c in row))

print('-' * 130)
row = ['合计', '']
for lt in sorted(LESSON_TYPES.keys()):
    row.append(str(col_totals[lt]['count']))
    row.append(f"{col_totals[lt]['hours']:.2f}")
row.append(str(total_count_all))
row.append(f"{total_hours_all:.2f}")
print(' '.join(f"{c:<10}" for c in row))

transport.close()
print("\n查询完成")
