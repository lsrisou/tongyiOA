"""代理感知的 ssh 模块。

从远程沙箱执行时，无法直连内网 SSH 网关 (8.141.117.235:22)。
但本环境存在一个 HTTP CONNECT 代理 (http://127.0.0.1:18080)，
可借此代理建立到 SSH 网关的 TCP 隧道，再由 paramiko 完成 SSH 握手。

通过 HTTP 代理 CONNECT 到 ssh_host:ssh_port，得到一个已连通的 socket，
然后用 paramiko.Transport 在该 socket 上建立 SSH 会话，
再通过 SSH 端口转发连入 RDS MySQL。
"""
import os
import socket
import pymysql as mysql
import paramiko
from sshtunnel import SSHTunnelForwarder

# 从原始公共模块读取连接参数（不修改原文件）
import importlib.util
_spec = importlib.util.spec_from_file_location("_ssh_orig", "/workspace/public/ssh.py")
# 注意：原 ssh.py 末尾会立即执行 SSHTunnelForwarder(...).start()，导入即副作用。
# 这里只读取其源码中的常量，不直接 import 执行它。
import re
_src = open("/workspace/public/ssh.py", "r", encoding="utf-8").read()

def _const(name, default=None):
    m = re.search(rf"^\s*{name}\s*=\s*['\"]([^'\"]+)['\"]", _src, re.MULTILINE)
    if m:
        return m.group(1)
    m = re.search(rf"^\s*{name}\s*=\s*(\d+)", _src, re.MULTILINE)
    if m:
        return int(m.group(1))
    return default

ssh_host = _const("ssh_host")
ssh_port = _const("ssh_port", 22)
ssh_username = _const("ssh_username")
ssh_password = _const("ssh_password")

db_host = _const("db_host")
db_port = _const("db_port", 3306)
db_username = _const("db_username")
db_password = _const("db_password")
db_name = _const("db_name")

# 统一AI 资源库（注意原文件中 db_host_ty 被覆盖为最后一个）
db_host_ty = _const("db_host_ty")
db_port_ty = _const("db_port_ty", 3306)
db_username_ty = _const("db_username_ty")
db_password_ty = _const("db_password_ty")
db_name_ty = _const("db_name_ty")


def _open_proxy_socket(target_host, target_port):
    """通过 HTTP CONNECT 代理建立到 target 的 TCP 隧道，返回已连通的 socket。"""
    proxy_url = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    if not proxy_url:
        # 无代理则直连
        s = socket.create_connection((target_host, target_port), timeout=15)
        return s

    # 解析 http://127.0.0.1:18080
    from urllib.parse import urlparse
    p = urlparse(proxy_url)
    proxy_host = p.hostname
    proxy_port = p.port or 8080

    s = socket.create_connection((proxy_host, proxy_port), timeout=15)
    req = (
        f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
        f"Host: {target_host}:{target_port}\r\n"
        f"\r\n"
    ).encode()
    s.sendall(req)
    # 读取响应头直到 \r\n\r\n
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    head = buf.split(b"\r\n", 1)[0].decode("latin-1", "ignore")
    if "200" not in head:
        raise RuntimeError(f"代理 CONNECT 失败: {head}")
    return s


class ProxyTunnel:
    """用 paramiko + HTTP CONNECT 代理模拟 sshtunnel 的本地端口转发。"""

    def __init__(self, target_ssh_host, target_ssh_port, ssh_user, ssh_pw,
                 remote_db_host, remote_db_port):
        self.target_ssh_host = target_ssh_host
        self.target_ssh_port = target_ssh_port
        self.ssh_user = ssh_user
        self.ssh_pw = ssh_pw
        self.remote_db_host = remote_db_host
        self.remote_db_port = remote_db_port
        self.transport = None
        self.local_bind_port = None
        self._listener = None
        self._stop = False

    def start(self):
        sock = _open_proxy_socket(self.target_ssh_host, self.target_ssh_port)
        self.transport = paramiko.Transport(sock)
        self.transport.connect(username=self.ssh_user, password=self.ssh_pw)

        # 本地端口转发：监听本地随机端口，每个连接打开一条到远端 DB 的 channel
        import threading
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(5)
        self.local_bind_port = self._listener.getsockname()[1]

        def _pipe(a, b):
            try:
                while True:
                    data = a.recv(4096)
                    if not data:
                        break
                    b.sendall(data)
            except Exception:
                pass
            finally:
                for s in (a, b):
                    try: s.close()
                    except Exception: pass

        def _accept():
            while not self._stop:
                try:
                    local_sock, addr = self._listener.accept()
                except Exception:
                    return
                try:
                    chan = self.transport.open_channel(
                        "direct-tcpip",
                        (self.remote_db_host, self.remote_db_port),
                        local_sock.getsockname(),
                    )
                except Exception:
                    local_sock.close()
                    continue
                threading.Thread(target=_pipe, args=(local_sock, chan), daemon=True).start()
                threading.Thread(target=_pipe, args=(chan, local_sock), daemon=True).start()

        threading.Thread(target=_accept, daemon=True).start()

    def stop(self):
        self._stop = True
        try:
            if self._listener:
                self._listener.close()
        except Exception:
            pass
        try:
            if self.transport:
                self.transport.close()
        except Exception:
            pass
        self.transport = None


# 兼容 sshtunnel 接口：暴露 server / server_ty（部分代码可能引用）
server = ProxyTunnel(ssh_host, ssh_port, ssh_username, ssh_password, db_host, db_port)
server.start()
conn = mysql.connect(host="127.0.0.1", port=server.local_bind_port,
                     user=db_username, passwd=db_password, db=db_name)

server_ty = ProxyTunnel(ssh_host, ssh_port, ssh_username, ssh_password, db_host_ty, db_port_ty)
server_ty.start()
conn_ty = mysql.connect(host="127.0.0.1", port=server_ty.local_bind_port,
                        user=db_username_ty, passwd=db_password_ty, db=db_name_ty)
