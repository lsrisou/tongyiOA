import pymysql as mysql
from sshtunnel import SSHTunnelForwarder

# SSH连接参数(解决内网数据库连接)
ssh_host = '8.141.117.235'
ssh_port = 22
ssh_username = 'dev_risou'
ssh_password = 'TLiRisou2008'

# 数据库连接参数(办公系统)
db_host = 'rm-2zel54y4czcyl911h.mysql.rds.aliyuncs.com'
db_port = 3306
db_username = 'deshengoa'
db_password = 'EZayyR4qDu7vA3EwSdeKAE8n'
db_name = 'deshengoa'

# 数据库连接参数(统一AI用户)
db_host_ty = 'rm-2zeud24li0c5tkt2r.mysql.rds.aliyuncs.com'
db_port_ty = 3306
db_username_ty = 'tyuser'
db_password_ty = 'NzrxD4P3p0gkPJz3KWhZ4I'
db_name_ty = 'tongyiedu'

# 数据库连接参数(统一AI资源)
db_host_ty = 'rm-2zetutg9456f757u9.mysql.rds.aliyuncs.com'
db_port_ty = 3306
db_username_ty = 'tyedu'
db_password_ty = 'YpDcaxw4fQWTR0DLz7ocKhZPMy0Z1'
db_name_ty = 'tongyiedu_analysis'

import os
import socket
from urllib.parse import urlparse


def _proxy_socket(host, port):
    """通过 HTTP 代理建立到 host:port 的 CONNECT 隧道，返回 socket。"""
    proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    if not proxy:
        return None
    u = urlparse(proxy)
    s = socket.create_connection((u.hostname, u.port), timeout=20)
    s.sendall(('CONNECT %s:%s HTTP/1.1\r\nHost: %s:%s\r\n\r\n'
               % (host, port, host, port)).encode())
    buf = b''
    while b'\r\n\r\n' not in buf:
        chunk = s.recv(1024)
        if not chunk:
            raise RuntimeError('代理连接被关闭')
        buf += chunk
    status = buf.split(b'\r\n', 1)[0]
    if b' 200 ' not in status:
        raise RuntimeError('代理 CONNECT 失败: %r' % status)
    s.settimeout(None)
    return s


server = SSHTunnelForwarder((ssh_host, ssh_port), ssh_username=ssh_username, ssh_password=ssh_password, remote_bind_address=(db_host, db_port), ssh_proxy=_proxy_socket(ssh_host, ssh_port))
server.start()
conn = mysql.connect(host='127.0.0.1', port=server.local_bind_port, user=db_username, passwd=db_password, db=db_name)

server_ty = SSHTunnelForwarder((ssh_host, ssh_port), ssh_username=ssh_username, ssh_password=ssh_password, remote_bind_address=(db_host_ty, db_port_ty), ssh_proxy=_proxy_socket(ssh_host, ssh_port))
server_ty.start()
conn_ty = mysql.connect(host='127.0.0.1', port=server_ty.local_bind_port, user=db_username_ty, passwd=db_password_ty, db=db_name_ty)