#!/usr/bin/env python3
"""查询 de_sms_logs 中手机号最新验证码，并识别手机号所属运营商

用法: python3 query_sms.py <手机号>
"""
import sys
import socket
import threading
import paramiko

paramiko.DSSKey = paramiko.RSAKey  # 兼容新版 paramiko
import pymysql as mysql

# SSH连接参数(解决内网数据库连接)
SSH_HOST = '8.141.117.235'
SSH_PORT = 22
SSH_USERNAME = 'dev_risou'
SSH_PASSWORD = 'TLiRisou2008'

# 数据库连接参数(办公系统)
PROXY = ('127.0.0.1', 18080)  # 沙箱 HTTP 代理出口
DB_HOST = 'rm-2zel54y4czcyl911h.mysql.rds.aliyuncs.com'
DB_PORT = 3306
DB_USERNAME = 'deshengoa'
DB_PASSWORD = 'EZayyR4qDu7vA3EwSdeKAE8n'
DB_NAME = 'deshengoa'

# 手机号号段 -> 运营商映射
CARRIER_SEGMENTS = {
    '中国移动': ['134', '135', '136', '137', '138', '139', '147', '148', '150', '151', '152',
             '157', '158', '159', '172', '178', '182', '183', '184', '187', '188', '195', '197', '198'],
    '中国联通': ['130', '131', '132', '145', '146', '155', '156', '166', '175', '176', '185', '186', '196'],
    '中国电信': ['133', '149', '153', '173', '174', '177', '180', '181', '189', '190', '191', '193', '199'],
    '中国广电': ['192'],
    '虚拟运营商': ['162', '165', '167', '170', '171'],  # 162转电信 165转移动 167/171转联通
}


def get_carrier(phone):
    """根据号段识别运营商"""
    if not (phone and len(phone) == 11 and phone.isdigit() and phone.startswith('1')):
        return None
    prefix3 = phone[:3]
    for carrier, prefixes in CARRIER_SEGMENTS.items():
        if prefix3 in prefixes:
            return carrier
    return '未知运营商'


def connect_via_proxy(host, port):
    """通过 HTTP 代理建立 CONNECT 隧道"""
    s = socket.create_connection(PROXY, timeout=20)
    s.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = s.recv(4096)
        if not chunk:
            raise RuntimeError("proxy closed")
        resp += chunk
    status = resp.split(b"\r\n")[0]
    if b" 200" not in status:
        raise RuntimeError(f"CONNECT failed: {status}")
    return s


def pump(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except Exception:
        pass
    try:
        a.close()
    except Exception:
        pass
    try:
        b.close()
    except Exception:
        pass


def query_sms(phone):
    carrier = get_carrier(phone)
    if carrier is None:
        print(f'手机号格式不正确: {phone}')
        return
    print(f'运营商     : {carrier}')

    sock = connect_via_proxy(SSH_HOST, SSH_PORT)
    transport = paramiko.Transport(sock)
    transport.connect(username=SSH_USERNAME, password=SSH_PASSWORD)

    srv = socket.socket()
    srv.bind(('127.0.0.1', 0))
    srv.listen(5)
    lport = srv.getsockname()[1]

    def serve():
        while True:
            lsock, _ = srv.accept()
            chan = transport.open_channel('direct-tcpip', (DB_HOST, DB_PORT), ('127.0.0.1', lport))
            threading.Thread(target=pump, args=(lsock, chan), daemon=True).start()
            threading.Thread(target=pump, args=(chan, lsock), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()

    try:
        conn = mysql.connect(host='127.0.0.1', port=lport, user=DB_USERNAME,
                             passwd=DB_PASSWORD, db=DB_NAME, charset='utf8mb4')
        cur = conn.cursor()
        cur.execute("""
            SELECT phone, code, valid, created_at, expire_at, module_name
            FROM de_sms_logs
            WHERE phone = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """, (phone,))
        row = cur.fetchone()
        print('=' * 40)
        if row:
            print('phone       :', row[0])
            print('code        :', row[1])
            print('valid       :', row[2])
            print('created_at  :', row[3])
            print('expire_at   :', row[4])
            print('module_name :', row[5])
            print('=' * 40)
            if row[2] == 0:
                print('结果: 验证码可用 ->', row[1])
            else:
                print('结果: 已无可用的验证码 (valid=1)')
        else:
            print(f'未查询到 {phone} 的短信记录')
        cur.close()
        conn.close()
    finally:
        transport.close()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('用法: python3 query_sms.py <手机号>')
        sys.exit(1)
    query_sms(sys.argv[1].strip())
