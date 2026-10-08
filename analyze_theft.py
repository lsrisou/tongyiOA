import socket
import select
import threading
import paramiko
import pymysql as mysql
from datetime import datetime, timedelta

PROXY_HOST = '127.0.0.1'
PROXY_PORT = 18080
ssh_host = '8.141.117.235'
ssh_port = 22
ssh_username = 'dev_risou'
ssh_password = 'TLiRisou2008'
db_host = 'rm-2zel54y4czcyl911h.mysql.rds.aliyuncs.com'
db_port = 3306
db_username = 'deshengoa'
db_password = 'EZayyR4qDu7vA3EwSdeKAE8n'
db_name = 'deshengoa'
USER_ID = 230  # 吴青玲 13629927416


def make_proxy_socket(target_host, target_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(30)
    s.connect((PROXY_HOST, PROXY_PORT))
    req = (
        f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
        f"Host: {target_host}:{target_port}\r\n"
        f"User-Agent: ssh-tunnel\r\n\r\n"
    ).encode()
    s.sendall(req)
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = s.recv(4096)
        if not chunk:
            raise Exception(f"Proxy closed. Got: {resp!r}")
        resp += chunk
    status_line = resp.split(b"\r\n", 1)[0]
    if b" 200 " not in status_line and not status_line.endswith(b" 200"):
        raise Exception(f"CONNECT failed: {status_line!r}")
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
        for x in (local_sock, chan):
            try:
                x.close()
            except Exception:
                pass


def classify_ua(ua):
    """把 user_agent 归类为粗粒度设备标识"""
    if not ua:
        return "(空UA)"
    ua = ua.lower()
    # 设备型号
    if "v2054a" in ua:
        model = "vivo_V2054A"
    elif "mxw-an00" in ua:
        model = "荣耀_MXW-AN00"
    elif "m2011k2c" in ua:
        model = "红米K40_M2011K2C"
    elif "v2307a" in ua:
        model = "vivo_V2307A"
    elif "iphone" in ua or "cpu iphone" in ua:
        model = "iPhone"
    elif "macintosh" in ua:
        model = "Mac"
    elif "windows nt" in ua:
        model = "Windows-PC"
    else:
        model = "其他"
    # 是否微信内置
    if "micromessenger" in ua:
        app = "微信内置浏览器"
    elif "windowswechat" in ua:
        app = "微信PC客户端"
    elif "edg/" in ua:
        app = "Edge浏览器"
    elif "chrome/" in ua and "micromessenger" not in ua:
        app = "Chrome浏览器"
    else:
        app = ""
    return f"{model} / {app}" if app else model


def ip_subnet(ip):
    if not ip:
        return "(空)"
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3]) + ".x"
    return ip


def analyze():
    print(f"Connecting SSH via proxy ...")
    sock = make_proxy_socket(ssh_host, ssh_port)
    transport = paramiko.Transport(sock)
    transport.connect(username=ssh_username, password=ssh_password)
    print("SSH transport established.")

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    local_port = listener.getsockname()[1]
    print(f"Local forwarder: 127.0.0.1:{local_port} -> {db_host}:{db_port}")

    stop = threading.Event()

    def accept_loop():
        while not stop.is_set():
            try:
                client, _ = listener.accept()
            except Exception:
                break
            try:
                chan = transport.open_channel("direct-tcpip", (db_host, db_port), ("127.0.0.1", 0))
            except Exception:
                client.close()
                continue
            threading.Thread(target=forward, args=(client, chan), daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()

    try:
        conn = mysql.connect(
            host='127.0.0.1', port=local_port,
            user=db_username, password=db_password,
            database=db_name, charset='utf8mb4',
        )
        cur = conn.cursor()

        # 拉最近 6 个月全部记录（按时间升序）做时序分析
        since = "2026-04-08 00:00:00"
        cur.execute(
            "SELECT id, action, ip, user_agent, created_at FROM de_user_action_logs "
            "WHERE user_id = %s AND created_at >= %s ORDER BY created_at ASC",
            (USER_ID, since),
        )
        rows = list(cur.fetchall())
        print(f"\n近6个月({since}至今)记录数: {len(rows)}")
        print("=" * 100)

        # 1) 按设备指纹分类统计
        print("\n【1】设备指纹分布(近6个月)")
        from collections import Counter, defaultdict
        dev_counter = Counter()
        for r in rows:
            dev_counter[classify_ua(r[3])] += 1
        for k, v in dev_counter.most_common():
            print(f"  {v:4d}  {k}")

        # 2) 异常时段登录(深夜 0:00-6:00 或 凌晨 1:00-5:00)
        print("\n【2】异常时段登录(00:00-06:00)")
        print(f"  {'time':23s} {'action':10s} {'ip':16s} {'device':40s}")
        abnormal = [r for r in rows if r[4].hour < 6]
        for r in abnormal:
            print(f"  {str(r[4]):23s} {str(r[1]):10s} {str(r[2]):16s} {classify_ua(r[3]):40s}")
        print(f"  异常时段登录次数: {len(abnormal)}")

        # 3) 时序：相邻两次登录的间隔 + IP/设备变化
        print("\n【3】时序与跳变分析(相邻登录间隔<3小时 或 IP子网/设备突变)")
        print(f"  {'time':23s} {'action':10s} {'ip':16s} {'subnet':14s} {'device':35s} {'gap':>8s}")
        prev = None
        for r in rows:
            t = r[4]
            ip = r[2]
            ua = r[3]
            sub = ip_subnet(ip)
            dev = classify_ua(ua)
            gap_str = ""
            flag = ""
            if prev:
                gap = (t - prev[4]).total_seconds()
                if gap < 3600 * 3:
                    gap_str = f"{int(gap//60)}min"
                    # 子网变化 or 设备变化
                    if sub != ip_subnet(prev[2]) or dev != classify_ua(prev[3]):
                        flag = "  <<< 短时+IP/设备变化"
                    else:
                        flag = "  (短时同设备)"
                else:
                    gap_str = f"{gap/3600:.1f}h"
            print(f"  {str(t):23s} {str(r[1]):10s} {str(ip):16s} {sub:14s} {dev:35s} {gap_str:>8s}{flag}")
            prev = r

        # 4) 同一天多 IP 子网登录(疑似多地并发)
        print("\n【4】同一天出现多个不同IP子网的日期(疑似多端并发)")
        by_day = defaultdict(set)
        day_records = defaultdict(list)
        for r in rows:
            d = r[4].date()
            by_day[d].add(ip_subnet(r[2]))
            day_records[d].append(r)
        multi_days = [(d, subs) for d, subs in by_day.items() if len(subs) >= 2]
        multi_days.sort()
        for d, subs in multi_days:
            print(f"\n  {d}  子网数={len(subs)}")
            for sub in sorted(subs):
                print(f"     子网 {sub}")
            for r in day_records[d]:
                print(f"       {str(r[4]):23s} {str(r[1]):10s} ip={str(r[2]):16s}  {classify_ua(r[3])}")

        # 5) 全部 password 操作记录(改密历史)
        print("\n【5】密码操作记录(action=password) 历史全量")
        cur.execute(
            "SELECT id, action, ip, user_agent, created_at FROM de_user_action_logs "
            "WHERE user_id = %s AND action = 'password' ORDER BY created_at ASC",
            (USER_ID,),
        )
        for r in cur.fetchall():
            print(f"  {str(r[4]):23s} ip={str(r[2]):16s}  {classify_ua(r[3])}")

        # 6) 失败登录尝试(若有 put-login 频繁)
        print("\n【6】put-login(登录提交尝试)按日分布")
        cur.execute(
            "SELECT DATE(created_at), COUNT(*) FROM de_user_action_logs "
            "WHERE user_id = %s AND action='put-login' AND created_at >= %s "
            "GROUP BY DATE(created_at) ORDER BY 1",
            (USER_ID, since),
        )
        for r in cur.fetchall():
            print(f"  {r[0]}  {r[1]}")

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
    analyze()
