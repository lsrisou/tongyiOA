import socket
import select
import threading
import paramiko
import pymysql as mysql
from datetime import datetime, timedelta

# Proxy (egress path) - HTTP CONNECT proxy
PROXY_HOST = '127.0.0.1'
PROXY_PORT = 18080

# SSH connection
ssh_host = '8.141.117.235'
ssh_port = 22
ssh_username = 'dev_risou'
ssh_password = 'TLiRisou2008'

# Database connection (office system - deshengoa)
db_host = 'rm-2zel54y4czcyl911h.mysql.rds.aliyuncs.com'
db_port = 3306
db_username = 'deshengoa'
db_password = 'EZayyR4qDu7vA3EwSdeKAE8n'
db_name = 'deshengoa'

USER_ID = 230  # 吴青玲 (手机号 13629927416)


def make_proxy_socket(target_host, target_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(30)
    s.connect((PROXY_HOST, PROXY_PORT))
    req = (
        f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
        f"Host: {target_host}:{target_port}\r\n"
        f"User-Agent: ssh-tunnel\r\n"
        f"\r\n"
    ).encode()
    s.sendall(req)
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = s.recv(4096)
        if not chunk:
            raise Exception(f"Proxy closed connection. Got: {resp!r}")
        resp += chunk
    status_line = resp.split(b"\r\n", 1)[0]
    if b" 200 " not in status_line and not status_line.endswith(b" 200"):
        raise Exception(f"Proxy CONNECT failed: {status_line!r}; full: {resp!r}")
    return s


def forward(local_sock, chan):
    try:
        while True:
            r, _, _ = select.select([local_sock, chan], [], [], 1)
            if local_sock in r:
                data = local_sock.recv(4096)
                if not data:
                    break
                chan.sendall(data)
            if chan in r:
                data = chan.recv(4096)
                if not data:
                    break
                local_sock.sendall(data)
    except Exception:
        pass
    finally:
        for s in (local_sock, chan):
            try:
                s.close()
            except Exception:
                pass


def query_db():
    print(f"Connecting to SSH {ssh_host}:{ssh_port} via proxy {PROXY_HOST}:{PROXY_PORT} ...")
    sock = make_proxy_socket(ssh_host, ssh_port)
    transport = paramiko.Transport(sock)
    transport.connect(username=ssh_username, password=ssh_password)
    print("SSH transport established.")

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    local_port = listener.getsockname()[1]
    print(f"Local forwarder listening on 127.0.0.1:{local_port} -> {db_host}:{db_port}")

    stop = threading.Event()

    def accept_loop():
        while not stop.is_set():
            try:
                client, _ = listener.accept()
            except Exception:
                break
            try:
                chan = transport.open_channel(
                    "direct-tcpip", (db_host, db_port), ("127.0.0.1", 0)
                )
            except Exception as e:
                client.close()
                continue
            t = threading.Thread(target=forward, args=(client, chan), daemon=True)
            t.start()

    threading.Thread(target=accept_loop, daemon=True).start()

    try:
        conn = mysql.connect(
            host='127.0.0.1', port=local_port,
            user=db_username, password=db_password,
            database=db_name, charset='utf8mb4',
        )
        cur = conn.cursor()

        # Time window: last 60 days from the latest record date (2026-10-08)
        # Use 2026-08-08 ~ now
        since = "2026-08-08 00:00:00"
        print(f"\nQuerying records since {since} for user_id = {USER_ID}")
        print("=" * 80)

        # Total count in window
        cur.execute(
            "SELECT COUNT(*) FROM de_user_action_logs WHERE user_id = %s AND created_at >= %s",
            (USER_ID, since),
        )
        total = cur.fetchone()[0]
        print(f"Total records in window: {total}")

        # Action distribution
        print("\n-- Action type distribution --")
        cur.execute(
            "SELECT action, COUNT(*) AS cnt FROM de_user_action_logs "
            "WHERE user_id = %s AND created_at >= %s GROUP BY action ORDER BY cnt DESC",
            (USER_ID, since),
        )
        for r in cur.fetchall():
            print(f"  {r[0]}: {r[1]}")

        # Time range
        print("\n-- Time range --")
        cur.execute(
            "SELECT MIN(created_at), MAX(created_at) FROM de_user_action_logs "
            "WHERE user_id = %s AND created_at >= %s",
            (USER_ID, since),
        )
        r = cur.fetchone()
        print(f"  earliest: {r[0]}")
        print(f"  latest:   {r[1]}")

        # Login frequency by day
        print("\n-- Login frequency by day --")
        cur.execute(
            "SELECT DATE(created_at) AS d, COUNT(*) AS cnt, "
            "GROUP_CONCAT(DISTINCT action) AS actions "
            "FROM de_user_action_logs WHERE user_id = %s AND created_at >= %s "
            "GROUP BY DATE(created_at) ORDER BY d",
            (USER_ID, since),
        )
        rows = cur.fetchall()
        print(f"  active days: {len(rows)}")
        print(f"  {'date':12s} {'count':>6s}  actions")
        for r in rows:
            print(f"  {str(r[0]):12s} {r[1]:6d}  {r[2]}")

        # Distinct IPs (top, with count + time)
        print("\n-- Distinct IPs (top 30 by count) --")
        cur.execute(
            "SELECT ip, COUNT(*) AS cnt, MIN(created_at), MAX(created_at) "
            "FROM de_user_action_logs WHERE user_id = %s AND created_at >= %s "
            "GROUP BY ip ORDER BY cnt DESC LIMIT 30",
            (USER_ID, since),
        )
        for r in cur.fetchall():
            print(f"  {str(r[0]):18s} cnt={r[1]:4d}  first={r[2]}  last={r[3]}")

        # Distinct user agents
        print("\n-- Distinct user agents (top 30 by count) --")
        cur.execute(
            "SELECT user_agent, COUNT(*) AS cnt, MIN(created_at), MAX(created_at) "
            "FROM de_user_action_logs WHERE user_id = %s AND created_at >= %s "
            "GROUP BY user_agent ORDER BY cnt DESC LIMIT 30",
            (USER_ID, since),
        )
        for r in cur.fetchall():
            ua = (r[0] or "")[:170]
            print(f"  cnt={r[1]:4d}  first={r[2]}  last={r[3]}")
            print(f"    UA: {ua}")

        # Full detail of all records in window, oldest first
        print("\n-- Full detail (oldest -> newest) --")
        cur.execute(
            "SELECT id, action, ip, user_agent, created_at FROM de_user_action_logs "
            "WHERE user_id = %s AND created_at >= %s ORDER BY created_at ASC",
            (USER_ID, since),
        )
        rows = cur.fetchall()
        for i, r in enumerate(rows, 1):
            ua = (r[3] or "")[:110]
            print(f"  #{i:3d} id={r[0]:6d} {str(r[4]):23s} action={r[1]:10s} ip={str(r[2]):16s} UA={ua}")

        cur.close()
        conn.close()
    finally:
        stop.set()
        try:
            listener.close()
        except Exception:
            pass
        transport.close()


if __name__ == "__main__":
    query_db()
