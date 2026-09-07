import socket
import threading
import select
import paramiko
import pymysql

ssh_host = '8.141.117.235'
ssh_port = 22
ssh_username = 'dev_risou'
ssh_password = 'TLiRisou2008'
db_host = 'rm-2zel54y4czcyl911h.mysql.rds.aliyuncs.com'
db_port = 3306
db_username = 'deshengoa'
db_password = 'EZayyR4qDu7vA3EwSdeKAE8n'
db_name = 'deshengoa'
proxy_host = '127.0.0.1'
proxy_port = 18080

import sys
WITHDRAW_ID = sys.argv[1] if len(sys.argv) > 1 else '47028'

default_teacher = {
    1: '直接邀请合伙人', 2: '间接邀请合伙人', 3: '直接邀请会员', 4: '间接邀请会员',
    5: '提现', 6: '开课分成', 7: '小时课上课薪资', 8: '学校发放的奖励',
    9: '体验课奖励', 10: '教练结算', 11: '教务服务费', 12: '提现退回',
    13: '提分奖励结余', 14: '教练提分奖励', 15: '教务服务费-上级教务奖励',
}
default_school = {
    1: '学校开课（开通班型）', 2: '下级校区课时奖励', 3: '间接校区课时奖励',
    4: '教学校区课时奖励', 5: '奖励教练', 6: '校区结算', 7: '创建约课支出',
    8: '约课退费收入', 9: '充值', 10: '充值退款', 11: '提现', 12: '提现退回',
    13: '约课提分奖励结余', 14: '约课续费支出', 15: '理事课时奖励',
    16: '股东课时奖励', 17: '事业部课时奖励',
}


def open_via_http_proxy(target_host, target_port, timeout=20):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((proxy_host, proxy_port))
    req = ("CONNECT {h}:{p} HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n"
           .format(h=target_host, p=target_port).encode())
    s.sendall(req)
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(1024)
        if not chunk:
            break
        buf += chunk
    if b" 200 " not in buf.split(b"\r\n", 1)[0]:
        raise RuntimeError("Proxy CONNECT failed: " + buf.decode(errors="replace"))
    return s


def make_conn():
    ssh_sock = open_via_http_proxy(ssh_host, ssh_port)
    transport = paramiko.Transport(ssh_sock)
    transport.connect(username=ssh_username, password=ssh_password)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    local_port = server.getsockname()[1]
    server.listen(5)
    server.settimeout(120)

    def serve():
        while True:
            try:
                client_sock, _ = server.accept()
            except Exception:
                break
            threading.Thread(target=handle, args=(client_sock, transport),
                              daemon=True).start()

    def handle(client_sock, transport):
        try:
            chan = transport.open_channel(
                kind="direct-tcpip",
                dest_addr=(db_host, db_port),
                src_addr=("127.0.0.1", 0),
            )
            if chan is None:
                client_sock.close()
                return
            pipe(client_sock, chan)
        except Exception:
            try:
                client_sock.close()
            except Exception:
                pass

    def pipe(a, b):
        while True:
            r, _, _ = select.select([a, b], [], [], 1)
            if a in r:
                data = a.recv(4096)
                if not data:
                    break
                b.sendall(data)
            if b in r:
                data = b.recv(4096)
                if not data:
                    break
                a.sendall(data)
        try:
            a.close()
            b.close()
        except Exception:
            pass

    threading.Thread(target=serve, daemon=True).start()
    conn = pymysql.connect(host="127.0.0.1", port=local_port,
                           user=db_username, passwd=db_password,
                           db=db_name, charset="utf8mb4")
    return conn, transport


def fmt_yuan(cents):
    cents = int(cents or 0)
    sign = '-' if cents < 0 else ''
    return f"{sign}{abs(cents)/100:.2f}"


conn, transport = make_conn()
cur = conn.cursor(pymysql.cursors.DictCursor)

# 1. 取提现记录
cur.execute("""
    SELECT id, type_id, school_id, user_id, user_name, amount, fee,
           send_amount, off_amount, state, reason, order_number,
           out_trade_no, balance, phone, created_at, handled_at,
           finished_at
    FROM de_point_withdraws
    WHERE id = %s
""", (WITHDRAW_ID,))
w = cur.fetchone()
if not w:
    print(f"未找到 ID={WITHDRAW_ID} 的提现记录")
    cur.close()
    conn.close()
    transport.close()
    raise SystemExit(0)

print("=" * 90)
print(f"提现记录 ID = {w['id']}")
print("=" * 90)
type_label = '个人提现' if w['type_id'] == 1 else ('校区提现' if w['type_id'] == 2 else f"未知({w['type_id']})")
print(f"  type_id        : {w['type_id']}  ({type_label})")
print(f"  user_id        : {w['user_id']}")
print(f"  school_id      : {w['school_id']}")
print(f"  user_name      : {w['user_name']}")
print(f"  phone          : {w['phone']}")
print(f"  amount(分)     : {w['amount']}  -> ¥{fmt_yuan(w['amount'])}")
print(f"  fee(手续费,分) : {w['fee']}  -> ¥{fmt_yuan(w['fee'])}")
print(f"  send_amount    : {w['send_amount']}  -> ¥{fmt_yuan(w['send_amount'])}")
print(f"  off_amount     : {w['off_amount']}  -> ¥{fmt_yuan(w['off_amount'])}")
print(f"  balance(分)    : {w['balance']}  -> ¥{fmt_yuan(w['balance'])}")
print(f"  state          : {w['state']}")
print(f"  reason         : {w['reason']}")
print(f"  order_number   : {w['order_number']}")
print(f"  out_trade_no   : {w['out_trade_no']}")
print(f"  created_at     : {w['created_at']}")
print(f"  handled_at     : {w['handled_at']}")
print(f"  finished_at    : {w['finished_at']}")

# 2. 根据类型查日志
print()
print("=" * 90)
print("关联的积分/账户明细日志（提现 5/11、提现退回 12，按时间倒序）")
print("=" * 90)

if w['type_id'] == 1:
    # 个人提现：de_user_point_logs，user_id 对应，type_id 5(提现)/12(提现退回)
    cur.execute("""
        SELECT id, type_id, amount, withdraw_amount, balance, msg, created_at,
               rel_id, log_group, from_uid, order_id
        FROM de_user_point_logs
        WHERE user_id = %s AND type_id IN (5, 12)
        ORDER BY created_at DESC
        LIMIT 50
    """, (w['user_id'],))
    rows = cur.fetchall()
    log_table = 'de_user_point_logs'
    lookup = default_teacher
elif w['type_id'] == 2:
    # 校区提现：de_school_point_logs，school_id 对应，type_id 11(提现)/12(提现退回)
    cur.execute("""
        SELECT id, type_id, amount, withdraw_amount, balance, msg, created_at,
               rel_id, log_group, to_user_id, order_id
        FROM de_school_point_logs
        WHERE school_id = %s AND type_id IN (11, 12)
        ORDER BY created_at DESC
        LIMIT 50
    """, (w['school_id'],))
    rows = cur.fetchall()
    log_table = 'de_school_point_logs'
    lookup = default_school
else:
    rows = []
    log_table = '?'
    lookup = {}

print(f"来源表: {log_table}  |  共 {len(rows)} 条")
print("-" * 90)
hdr = f"{'log_id':>10} | {'type_id':>7} | {'type':<14} | {'amount':>12} | {'withdraw_amt':>14} | {'balance':>12} | {'created_at':<23} | {'rel_id':>10} | {'log_group':>9} | msg"
print(hdr)
print("-" * 90)
for r in rows:
    t = lookup.get(int(r['type_id']), f"type{r['type_id']}")
    msg = (r['msg'] or '').replace('\n', ' ')[:60]
    print(f"{r['id']:>10} | {r['type_id']:>7} | {t:<14} | "
          f"{fmt_yuan(r['amount']):>12} | {fmt_yuan(r['withdraw_amount']):>14} | "
          f"{fmt_yuan(r['balance']):>12} | {str(r['created_at']):<23} | "
          f"{str(r['rel_id']):>10} | {str(r['log_group']):>9} | {msg}")

# 3. 寻找与本提现金额、时间、rel_id 匹配的日志
print()
print("=" * 90)
print(f"尝试匹配本提现 (amount={w['amount']}分=¥{fmt_yuan(w['amount'])}) 的日志")
print("=" * 90)

match_key_cols = []
if w['type_id'] == 1:
    match_key_cols = ['rel_id', 'withdraw_amount', 'amount', 'log_group']
elif w['type_id'] == 2:
    match_key_cols = ['rel_id', 'withdraw_amount', 'amount', 'log_group']

# 找候选匹配
def matches(log, target_amount):
    # 优先用 withdraw_amount；为空则用 amount
    for col in ('withdraw_amount', 'amount'):
        v = log.get(col)
        if v is not None and int(v) == int(target_amount):
            return col
    return None

candidates = []
for r in rows:
    col = matches(r, w['amount'])
    if col:
        candidates.append((r, col))

print(f"\n按金额匹配 (amount={w['amount']}分) 命中 {len(candidates)} 条候选:")
print("-" * 90)
for r, col in candidates:
    t = lookup.get(int(r['type_id']), f"type{r['type_id']}")
    print(f"  log_id={r['id']:>10} | type={t:<14} | {col}={fmt_yuan(r[col])} "
          f"| amount={fmt_yuan(r['amount'])} | balance={fmt_yuan(r['balance'])} "
          f"| rel_id={r['rel_id']} | log_group={r['log_group']} "
          f"| created_at={r['created_at']} | msg={r['msg']}")

# 进一步：按 rel_id == WITHDRAW_ID 精确匹配
print()
by_rel = [r for r in rows if r['rel_id'] is not None and str(r['rel_id']) == str(w['id'])]
print(f"按 rel_id == {w['id']} 精确匹配: {len(by_rel)} 条")
for r in by_rel:
    t = lookup.get(int(r['type_id']), f"type{r['type_id']}")
    print(f"  log_id={r['id']:>10} | type={t:<14} | amount={fmt_yuan(r['amount'])} "
          f"| withdraw_amount={fmt_yuan(r['withdraw_amount'])} "
          f"| balance={fmt_yuan(r['balance'])} | created_at={r['created_at']} | msg={r['msg']}")

# 4. 汇总：依据最可能的匹配集合求和
print()
print("=" * 90)
print("合理性核对")
print("=" * 90)

# 策略：
# 1) 如果有 rel_id 精确匹配本提现的日志，则以这些日志为准；
# 2) 否则用金额匹配的候选；
# 3) 否则放宽到用户/校区名下全部提现+提现退回日志（仅展示，标注未精确匹配）。
chosen = by_rel if by_rel else ([r for r, _ in candidates] if candidates else rows)
chosen_source = "rel_id 精确匹配" if by_rel else (
    "金额匹配" if candidates else "用户/校区名下全部提现/退回日志(未精确匹配,仅供参考)")

# 提现扣款(负金额或type=5/11) - 退回(正金额或type=12)
withdraw_total = 0  # 实际从账户扣除的提现金额(应为正数表示扣减)
for r in chosen:
    a = int(r['amount'] or 0)
    t = int(r['type_id'])
    # type=5(teacher提现) 或 11(school提现) 表示扣款
    # type=12 表示退回(加回账户)
    if (w['type_id'] == 1 and t == 5) or (w['type_id'] == 2 and t == 11):
        withdraw_total += abs(a)
    elif t == 12:
        withdraw_total -= abs(a)
    else:
        # 用 amount 正负号
        withdraw_total += a

print(f"匹配来源   : {chosen_source}")
print(f"匹配日志数 : {len(chosen)}")
print(f"提现记录金额 (amount)           : {w['amount']} 分 = ¥{fmt_yuan(w['amount'])}")
print(f"匹配日志净扣款 (提现-退回, 正=扣): {withdraw_total} 分 = ¥{fmt_yuan(withdraw_total)}")

diff = int(w['amount']) - withdraw_total
ok = "✓ 一致 (合理)" if diff == 0 else f"✗ 差异 {diff} 分 = ¥{fmt_yuan(diff)}"
print(f"差异 (amount - 净扣款)         : {diff} 分 = ¥{fmt_yuan(diff)}  -> {ok}")

cur.close()
conn.close()
transport.close()
