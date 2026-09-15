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

db_configs = [
    {
        'name': 'deshengoa',
        'host': 'rm-2zel54y4czcyl911h.mysql.rds.aliyuncs.com',
        'port': 3306,
        'user': 'deshengoa',
        'passwd': 'EZayyR4qDu7vA3EwSdeKAE8n',
        'db': 'deshengoa',
    },
    {
        'name': 'tongyiedu',
        'host': 'rm-2zeud24li0c5tkt2r.mysql.rds.aliyuncs.com',
        'port': 3306,
        'user': 'tyuser',
        'passwd': 'NzrxD4P3p0gkPJz3KWhZ4I',
        'db': 'tongyiedu',
    },
    {
        'name': 'tongyiedu_analysis',
        'host': 'rm-2zetutg9456f757u9.mysql.rds.aliyuncs.com',
        'port': 3306,
        'user': 'tyedu',
        'passwd': 'YpDcaxw4fQWTR0DLz7ocKhZPMy0Z1',
        'db': 'tongyiedu_analysis',
    },
]


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


def query_via_transport(transport, cfg, sql, params=None, fetch='all'):
    chan = transport.open_channel(
        'direct-tcpip',
        (cfg['host'], cfg['port']),
        ('127.0.0.1', 0),
    )
    conn = pymysql.connect(
        host='127.0.0.1',
        user=cfg['user'],
        passwd=cfg['passwd'],
        db=cfg['db'],
        charset='utf8mb4',
        defer_connect=True,
    )
    conn.connect(sock=chan)
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(sql, params or ())
    if fetch == 'all':
        result = cur.fetchall()
    elif fetch == 'one':
        result = cur.fetchone()
    else:
        result = None
    cur.close()
    conn.close()
    chan.close()
    return result


print("正在通过代理建立 SSH 隧道...")
transport = open_ssh_client()
print("SSH 隧道建立成功\n")

for cfg in db_configs:
    try:
        rows = query_via_transport(transport, cfg, "SHOW TABLES", fetch='all')
        tables = [list(r.values())[0] for r in rows if list(r.values())[0].startswith('de_')]
        print(f"=== [{cfg['name']}] 共 {len(tables)} 张 de_ 表 ===")
        for t in sorted(tables):
            print(f"  {t}")
        print()
    except Exception as e:
        print(f"[{cfg['name']}] 查询失败: {e}\n")

transport.close()
print("查询完成")
