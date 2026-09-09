"""通过HTTP代理建立SSH隧道连接内网MySQL的辅助模块"""
import socket
import threading
import paramiko
import pymysql as mysql

PROXY_HOST = '127.0.0.1'
PROXY_PORT = 18080

# SSH连接参数
SSH_HOST = '8.141.117.235'
SSH_PORT = 22
SSH_USER = 'dev_risou'
SSH_PASS = 'TLiRisou2008'

# 数据库连接参数(统一AI用户库 tongyiedu) —— 业务数据所在
DB_HOST = 'rm-2zeud24li0c5tkt2r.mysql.rds.aliyuncs.com'
DB_PORT = 3306
DB_USER = 'tyuser'
DB_PASS = 'NzrxD4P3p0gkPJz3KWhZ4I'
DB_NAME = 'tongyiedu'

# 备用连接配置(可按需切换)
DB_CONFIGS = {
    'tongyiedu': {  # 统一AI用户(业务)
        'host': 'rm-2zeud24li0c5tkt2r.mysql.rds.aliyuncs.com', 'port': 3306,
        'user': 'tyuser', 'passwd': 'NzrxD4P3p0gkPJz3KWhZ4I', 'name': 'tongyiedu'},
    'analysis': {  # 统一AI资源(分析)
        'host': 'rm-2zetutg9456f757u9.mysql.rds.aliyuncs.com', 'port': 3306,
        'user': 'tyedu', 'passwd': 'YpDcaxw4fQWTR0DLz7ocKhZPMy0Z1', 'name': 'tongyiedu_analysis'},
    'deshengoa': {  # 办公系统
        'host': 'rm-2zel54y4czcyl911h.mysql.rds.aliyuncs.com', 'port': 3306,
        'user': 'deshengoa', 'passwd': 'EZayyR4qDu7vA3EwSdeKAE8n', 'name': 'deshengoa'},
}


def _proxy_socket(target_host, target_port, timeout=30):
    """通过HTTP代理CONNECT建立TCP连接,返回已就绪的socket"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((PROXY_HOST, PROXY_PORT))
    req = (f'CONNECT {target_host}:{target_port} HTTP/1.1\r\n'
           f'Host: {target_host}:{target_port}\r\n\r\n').encode()
    s.send(req)
    resp = b''
    while b'\r\n\r\n' not in resp:
        chunk = s.recv(4096)
        if not chunk:
            break
        resp += chunk
    first = resp.split(b'\r\n', 1)[0].decode(errors='ignore')
    if '200' not in first:
        s.close()
        raise RuntimeError(f'代理CONNECT失败: {first}')
    return s


class _LocalForwarder:
    """本地TCP转发: 每个本地连接建立一个新的SSH direct-tcpip通道"""

    def __init__(self, transport, remote_host, remote_port):
        self.transport = transport
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('127.0.0.1', 0))
        self.server.listen(5)
        self.local_port = self.server.getsockname()[1]
        self._stop = False
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while not self._stop:
            try:
                client, _ = self.server.accept()
            except Exception:
                break
            t = threading.Thread(target=self._handle, args=(client,), daemon=True)
            t.start()

    def _handle(self, client):
        try:
            chan = self.transport.open_channel('direct-tcpip',
                                               (self.remote_host, self.remote_port),
                                               ('127.0.0.1', 0))
            if chan is None:
                client.close()
                return
            self._pump(client, chan)
        except Exception:
            try:
                client.close()
            except Exception:
                pass

    @staticmethod
    def _pump(a, b):
        def fwd(src, dst):
            try:
                while True:
                    data = src.recv(4096)
                    if not data:
                        break
                    dst.sendall(data)
            except Exception:
                pass
            finally:
                try:
                    dst.close()
                except Exception:
                    pass
        t1 = threading.Thread(target=fwd, args=(a, b), daemon=True)
        t2 = threading.Thread(target=fwd, args=(b, a), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    def stop(self):
        self._stop = True
        try:
            self.server.close()
        except Exception:
            pass


class DBTunnel:
    def __init__(self):
        self.transport = None
        self.forwarders = {}  # config_key -> _LocalForwarder

    def connect(self):
        print("建立SSH连接(经HTTP代理)...")
        sock = _proxy_socket(SSH_HOST, SSH_PORT)
        self.transport = paramiko.Transport(sock)
        self.transport.connect(username=SSH_USER, password=SSH_PASS)
        print("SSH连接成功")

    def _get_forwarder(self, key):
        if key not in self.forwarders:
            cfg = DB_CONFIGS[key]
            print(f"建立到[{key}]({cfg['host']}:{cfg['port']})的本地转发...")
            self.forwarders[key] = _LocalForwarder(self.transport, cfg['host'], cfg['port'])
            print(f"[{key}] 本地转发端口: 127.0.0.1:{self.forwarders[key].local_port}")
        return self.forwarders[key]

    def get_conn(self, key='tongyiedu', db_name=None):
        cfg = DB_CONFIGS[key]
        fwd = self._get_forwarder(key)
        return mysql.connect(host='127.0.0.1', port=fwd.local_port,
                             user=cfg['user'], password=cfg['passwd'],
                             database=db_name or cfg['name'], charset='utf8mb4')

    def close(self):
        for f in self.forwarders.values():
            try:
                f.stop()
            except Exception:
                pass
        try:
            if self.transport:
                self.transport.close()
        except Exception:
            pass


if __name__ == '__main__':
    tunnel = DBTunnel()
    tunnel.connect()
    conn = tunnel.get_conn()
    cur = conn.cursor()
    print("=== 所有数据库 ===")
    cur.execute("SHOW DATABASES")
    for r in cur.fetchall():
        print(r[0])
    cur.close()
    conn.close()
    tunnel.close()
    print("完成")
