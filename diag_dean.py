import socket
import warnings
warnings.filterwarnings("ignore")

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


print("正在通过代理建立 SSH 隧道...")
transport = open_ssh_client()
print("SSH 隧道建立成功\n")

# 1. de_student_hour_lessons 表结构
print("=== de_student_hour_lessons 表结构 ===")
cols = query_via_transport(transport, "DESCRIBE de_student_hour_lessons", fetch='all')
for c in cols:
    print(f"  {c['Field']}: {c['Type']} (Null={c['Null']}, Default={c['Default']})")
print()

# 2. 该 dean 的数据范围
print(f"=== dean_id={dean_id} 的数据范围 ===")
rng = query_via_transport(transport, """
    SELECT COUNT(*) AS cnt, MIN(start_time) AS min_t, MAX(start_time) AS max_t,
           SUM(hour_count) AS sum_hours
    FROM de_student_hour_lessons WHERE dean_id = %s
""", (dean_id,), fetch='one')
print(f"  总记录数: {rng['cnt']}, 最早: {rng['min_t']}, 最晚: {rng['max_t']}, 总课时: {rng['sum_hours']}")
print()

# 3. 按年月统计
print(f"=== dean_id={dean_id} 按年月统计 ===")
ym_rows = query_via_transport(transport, """
    SELECT DATE_FORMAT(start_time, '%%Y-%%m') AS ym, COUNT(*) AS cnt, SUM(hour_count) AS hours
    FROM de_student_hour_lessons WHERE dean_id = %s
    GROUP BY DATE_FORMAT(start_time, '%%Y-%%m')
    ORDER BY ym
""", (dean_id,), fetch='all')
for r in ym_rows:
    print(f"  {r['ym']}: 记录数={r['cnt']}, 课时={r['hours']}")
print()

# 4. 检查 start_time 的时区/存储格式 - 抽样几条
print(f"=== dean_id={dean_id} 抽样 5 条 ===")
samples = query_via_transport(transport, """
    SELECT id, student_id, start_time, hour_count, dean_id
    FROM de_student_hour_lessons WHERE dean_id = %s
    ORDER BY start_time DESC LIMIT 5
""", (dean_id,), fetch='all')
for s in samples:
    print(f"  {s}")
print()

# 5. 确认 dean 在 de_admin_users 中的记录
print(f"=== dean_id={dean_id} 在 de_admin_users 中的记录 ===")
dean = query_via_transport(transport, """
    SELECT u.id, u.name, u.school_id, u.role_id, s.name AS school_name
    FROM de_admin_users u LEFT JOIN de_schools s ON u.school_id = s.id
    WHERE u.id = %s
""", (dean_id,), fetch='one')
print(f"  {dean}")
print()

# 6. 查看 de_schools 表结构(确认 name 字段是名称还是编码)
print("=== de_schools 表结构 ===")
scols = query_via_transport(transport, "DESCRIBE de_schools", fetch='all')
for c in scols:
    print(f"  {c['Field']}: {c['Type']}")
print()

# 7. school_id=23 的学校完整记录
print("=== de_schools id=23 的完整记录 ===")
school = query_via_transport(transport, "SELECT * FROM de_schools WHERE id = 23", fetch='one')
print(f"  {school}")

transport.close()
print("\n查询完成")
