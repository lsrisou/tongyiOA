import os
import sys
import socket

# 沙箱环境通过 HTTP 代理访问外网，需在导入 ssh.py 前让 socket 走 HTTP CONNECT 代理。
# 真实环境无 HTTP_PROXY 环境变量时，以下逻辑不生效，不影响原有连接方式。
_http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')

if _http_proxy:
    from urllib.parse import urlparse
    _parsed = urlparse(_http_proxy)
    _proxy_host = _parsed.hostname
    _proxy_port = _parsed.port or 8080
    _no_proxy = os.environ.get('NO_PROXY', '').lower()

    _orig_socket = socket.socket

    class _ProxiedSocket(_orig_socket):
        def connect(self, addr):
            host, port = addr[0], addr[1]
            # 本地地址（127.0.0.1 / localhost）不走代理，避免影响 MySQL 本地隧道端口
            if host in ('127.0.0.1', 'localhost', '::1') or f'.{host}' in _no_proxy:
                return _orig_socket.connect(self, addr)
            _orig_socket.connect(self, (_proxy_host, _proxy_port))
            req = f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n'
            self.sendall(req.encode())
            resp = self.recv(8192)
            if b'200' not in resp.split(b'\r\n')[0]:
                raise ConnectionError(f'Proxy CONNECT failed: {resp.decode(errors="replace")}')

    socket.socket = _ProxiedSocket

# 添加项目根目录到路径，便于导入 public/ssh.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from public.ssh import conn, server


def query_headmaster_count():
    """
    查询 deshengoa 库 de_admin_users 表中校长人数。
    role_id 字段值为 school_headmaster 表示校长，deleted_at 为空表示未删除。
    """
    cursor = conn.cursor()
    try:
        sql = (
            "SELECT COUNT(*) FROM de_admin_users "
            "WHERE role_id = 'school_headmaster' "
            "AND deleted_at IS NULL"
        )
        cursor.execute(sql)
        count = cursor.fetchone()[0]
        return count
    finally:
        cursor.close()


if __name__ == '__main__':
    try:
        total = query_headmaster_count()
        print(f"校长人数: {total}")
    finally:
        conn.close()
        server.stop()
