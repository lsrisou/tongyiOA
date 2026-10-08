import socket
import select
import threading
import paramiko
import pymysql as mysql

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

PHONE = '13629927416'


def make_proxy_socket(target_host, target_port):
    """Create a TCP socket tunneled through the HTTP CONNECT proxy."""
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
        try:
            local_sock.close()
        except Exception:
            pass
        try:
            chan.close()
        except Exception:
            pass


def query_db():
    # 1. Open SSH via the HTTP proxy
    print(f"Connecting to SSH {ssh_host}:{ssh_port} via proxy {PROXY_HOST}:{PROXY_PORT} ...")
    sock = make_proxy_socket(ssh_host, ssh_port)
    transport = paramiko.Transport(sock)
    transport.connect(username=ssh_username, password=ssh_password)
    print("SSH transport established.")

    # 2. Start a local TCP listener that forwards to the MySQL RDS via SSH channel
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
                print(f"Failed to open channel: {e}")
                client.close()
                continue
            t = threading.Thread(target=forward, args=(client, chan), daemon=True)
            t.start()

    acc = threading.Thread(target=accept_loop, daemon=True)
    acc.start()

    try:
        # 3. Connect MySQL over the local forwarder
        conn = mysql.connect(
            host='127.0.0.1',
            port=local_port,
            user=db_username,
            password=db_password,
            database=db_name,
            charset='utf8mb4',
        )
        cur = conn.cursor()

        # 4. Inspect schemas of the two tables
        print("=" * 60)
        print("Table de_admin_users columns:")
        print("=" * 60)
        cur.execute("SHOW COLUMNS FROM de_admin_users")
        for row in cur.fetchall():
            print(row)

        print("\n" + "=" * 60)
        print("Table de_user_action_logs columns:")
        print("=" * 60)
        cur.execute("SHOW COLUMNS FROM de_user_action_logs")
        for row in cur.fetchall():
            print(row)

        # 5. Find user by phone number (username field)
        print("\n" + "=" * 60)
        print(f"Looking up user with username = {PHONE}")
        print("=" * 60)
        cur.execute(
            "SELECT id, username, name, disabled, created_at, updated_at, "
            "last_login_time, tongyi_user_id "
            "FROM de_admin_users WHERE username = %s",
            (PHONE,),
        )
        user_row = cur.fetchone()
        if not user_row:
            # try mobile/phone fields too
            print("Not found by username, trying mobile/phone fields ...")
            cur.execute("SHOW COLUMNS FROM de_admin_users")
            cols = [r[0] for r in cur.fetchall()]
            candidate_cols = [c for c in cols if 'mobile' in c.lower() or 'phone' in c.lower()]
            for c in candidate_cols:
                cur.execute(f"SELECT id, username, name FROM de_admin_users WHERE `{c}` = %s", (PHONE,))
                user_row = cur.fetchone()
                if user_row:
                    print(f"Found via column {c}")
                    break
        if not user_row:
            print(f"No user found for phone {PHONE}")
        else:
            print("User found:")
            print(user_row)
            user_id = user_row[0]

            # 6. Summary stats for login action logs for this user
            print("\n" + "=" * 60)
            print(f"Login action logs analysis for user_id = {user_id}")
            print("=" * 60)

            # Total count
            cur.execute("SELECT COUNT(*) FROM de_user_action_logs WHERE user_id = %s", (user_id,))
            total = cur.fetchone()[0]
            print(f"Total log records: {total}")

            # Action type distribution
            print("\n-- Action type distribution --")
            cur.execute(
                "SELECT action, COUNT(*) AS cnt FROM de_user_action_logs "
                "WHERE user_id = %s GROUP BY action ORDER BY cnt DESC",
                (user_id,),
            )
            for r in cur.fetchall():
                print(f"  {r[0]}: {r[1]}")

            # Time range
            print("\n-- Time range --")
            cur.execute(
                "SELECT MIN(created_at), MAX(created_at) FROM de_user_action_logs WHERE user_id = %s",
                (user_id,),
            )
            r = cur.fetchone()
            print(f"  earliest: {r[0]}")
            print(f"  latest:   {r[1]}")

            # Distinct IPs with counts (top 30)
            print("\n-- Distinct IPs (top 30 by count) --")
            cur.execute(
                "SELECT ip, COUNT(*) AS cnt, MIN(created_at), MAX(created_at) "
                "FROM de_user_action_logs WHERE user_id = %s "
                "GROUP BY ip ORDER BY cnt DESC LIMIT 30",
                (user_id,),
            )
            for r in cur.fetchall():
                print(f"  {str(r[0]):18s} cnt={r[1]:4d}  first={r[2]}  last={r[3]}")

            # Distinct user agents with counts (top 30)
            print("\n-- Distinct user agents (top 30 by count) --")
            cur.execute(
                "SELECT user_agent, COUNT(*) AS cnt, MIN(created_at), MAX(created_at) "
                "FROM de_user_action_logs WHERE user_id = %s "
                "GROUP BY user_agent ORDER BY cnt DESC LIMIT 30",
                (user_id,),
            )
            for r in cur.fetchall():
                ua = (r[0] or "")[:160]
                print(f"  cnt={r[1]:4d}  first={r[2]}  last={r[3]}")
                print(f"    UA: {ua}")

            # Most recent 80 records in detail
            print("\n-- Most recent 80 records (detail) --")
            cur.execute(
                "SELECT id, action, ip, user_agent, created_at FROM de_user_action_logs "
                "WHERE user_id = %s ORDER BY id DESC LIMIT 80",
                (user_id,),
            )
            rows = cur.fetchall()
            print(f"Showing {len(rows)} records:")
            for i, r in enumerate(rows, 1):
                ua = (r[3] or "")[:120]
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
