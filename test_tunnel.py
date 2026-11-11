"""测试 TCP 转发是否正常工作"""
import socket
import threading
import time

PROXY_HOST = '127.0.0.1'
PROXY_PORT = 18080
DB_HOST = 'rm-2zetutg9456f757u9.mysql.rds.aliyuncs.com'
DB_PORT = 3306


def create_proxy_tunnel():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((PROXY_HOST, PROXY_PORT))
    req = f"CONNECT {DB_HOST}:{DB_PORT} HTTP/1.1\r\nHost: {DB_HOST}:{DB_PORT}\r\n\r\n"
    sock.sendall(req.encode())
    resp = b''
    while b'\r\n\r\n' not in resp:
        chunk = sock.recv(4096)
        if not chunk: break
        resp += chunk
    print("代理响应:", resp.split(b'\r\n')[0].decode())
    if b'200' not in resp.split(b'\r\n')[0]:
        raise Exception("CONNECT failed")
    sock.settimeout(None)
    return sock


def forward(src, dst, label):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                print(f"[{label}] src closed")
                break
            print(f"[{label}] recv {len(data)} bytes: {data[:50]}...")
            dst.sendall(data)
    except Exception as e:
        print(f"[{label}] error: {e}")
    finally:
        try: dst.shutdown(socket.SHUT_WR)
        except: pass


print("创建代理隧道...")
remote = create_proxy_tunnel()
print("隧道建立成功!")
print("\n等待 MySQL 服务器发送握手包...")
remote.settimeout(10)
try:
    data = remote.recv(4096)
    print(f"收到 MySQL 数据: {len(data)} bytes")
    print(f"内容: {data[:200]}")
    print(f"Hex: {data[:50].hex()}")
except Exception as e:
    print(f"超时或错误: {e}")

remote.close()
print("测试结束")
