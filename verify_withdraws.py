#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提现金额合理性核对脚本

用法:
    python3 verify_withdraws.py                      # 核对全部提现 ID
    python3 verify_withdraws.py 47028 46754 12345   # 核对指定 ID
    python3 verify_withdraws.py --range 46000:47000 # 核对 ID 区间
    python3 verify_withdraws.py --state 1           # 仅核对某 state
    python3 verify_withdraws.py --recent 100         # 仅核对最近 100 条
    python3 verify_withdraws.py --since 2026-09-01   # 仅核对 created_at >= 该日期

逻辑:
    - de_point_withdraws.type_id = 1 (个人提现) -> 查 de_user_point_logs (user_id 关联,
      type_id 5=提现, 12=提现退回)
    - de_point_withdraws.type_id = 2 (校区提现) -> 查 de_school_point_logs (school_id 关联,
      type_id 11=提现, 12=提现退回)
    - 通过 rel_id 精确匹配本提现的日志，再按金额匹配、时间匹配兜底
    - amount 单位为分，日志 amount 正负表示加/扣
    - 合理 = 提现记录金额 与 关联日志净扣款(提现-退回) 相等
"""
import argparse
import socket
import threading
import select
import sys
import time

import paramiko
import pymysql

# ------------------------------------------------------------------
# 连接参数（与 /workspace/public/ssh.py 一致）
# ------------------------------------------------------------------
SSH_HOST = '8.141.117.235'
SSH_PORT = 22
SSH_USER = 'dev_risou'
SSH_PWD = 'TLiRisou2008'
DB_HOST = 'rm-2zel54y4czcyl911h.mysql.rds.aliyuncs.com'
DB_PORT = 3306
DB_USER = 'deshengoa'
DB_PWD = 'EZayyR4qDu7vA3EwSdeKAE8n'
DB_NAME = 'deshengoa'
PROXY_HOST = '127.0.0.1'
PROXY_PORT = 18080

# type_id -> 含义
TEACHER_TYPES = {
    1: '直接邀请合伙人', 2: '间接邀请合伙人', 3: '直接邀请会员',
    4: '间接邀请会员', 5: '提现', 6: '开课分成', 7: '小时课上课薪资',
    8: '学校发放的奖励', 9: '体验课奖励', 10: '教练结算', 11: '教务服务费',
    12: '提现退回', 13: '提分奖励结余', 14: '教练提分奖励',
    15: '教务服务费-上级教务奖励',
}
SCHOOL_TYPES = {
    1: '学校开课（开通班型）', 2: '下级校区课时奖励', 3: '间接校区课时奖励',
    4: '教学校区课时奖励', 5: '奖励教练', 6: '校区结算', 7: '创建约课支出',
    8: '约课退费收入', 9: '充值', 10: '充值退款', 11: '提现', 12: '提现退回',
    13: '约课提分奖励结余', 14: '约课续费支出', 15: '理事课时奖励',
    16: '股东课时奖励', 17: '事业部课时奖励',
}


# ------------------------------------------------------------------
# 通过 HTTP CONNECT 代理 + SSH 跳板建立到内网 MySQL 的本地转发
# ------------------------------------------------------------------
def open_via_http_proxy(host, port, timeout=20):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((PROXY_HOST, PROXY_PORT))
    s.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
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
    ssh_sock = open_via_http_proxy(SSH_HOST, SSH_PORT)
    transport = paramiko.Transport(ssh_sock)
    transport.connect(username=SSH_USER, password=SSH_PWD)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    local_port = srv.getsockname()[1]
    srv.listen(8)
    srv.settimeout(180)

    def pipe(a, b):
        while True:
            r, _, _ = select.select([a, b], [], [], 1)
            if a in r:
                d = a.recv(8192)
                if not d:
                    break
                b.sendall(d)
            if b in r:
                d = b.recv(8192)
                if not d:
                    break
                a.sendall(d)
        try:
            a.close(); b.close()
        except Exception:
            pass

    def handle(client_sock):
        try:
            chan = transport.open_channel(
                kind="direct-tcpip",
                dest_addr=(DB_HOST, DB_PORT),
                src_addr=("127.0.0.1", 0))
            if chan is None:
                client_sock.close(); return
            pipe(client_sock, chan)
        except Exception:
            try: client_sock.close()
            except Exception: pass

    def serve():
        while True:
            try:
                cs, _ = srv.accept()
            except Exception:
                break
            threading.Thread(target=handle, args=(cs,), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    conn = pymysql.connect(host="127.0.0.1", port=local_port,
                           user=DB_USER, passwd=DB_PWD,
                           db=DB_NAME, charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    return conn, transport


def yuan(cents):
    c = int(cents or 0)
    return f"{c/100:.2f}" if c >= 0 else f"-{abs(c)/100:.2f}"


# ------------------------------------------------------------------
# 单条提现核对
# ------------------------------------------------------------------
def verify_one(cur, withdraw_id, verbose=True):
    cur.execute("""
        SELECT id, type_id, school_id, user_id, user_name, amount, fee,
               send_amount, off_amount, state, reason, order_number,
               out_trade_no, balance, phone, created_at, handled_at, finished_at
        FROM de_point_withdraws
        WHERE id = %s
    """, (withdraw_id,))
    w = cur.fetchone()
    if not w:
        return {"id": withdraw_id, "status": "not_found"}

    type_id = int(w['type_id'])
    if type_id == 1:
        log_table, log_pk, log_id_col = "de_user_point_logs", "user_id", w['user_id']
        type_withdraw, type_return = 5, 12
        lookup = TEACHER_TYPES
    elif type_id == 2:
        log_table, log_pk, log_id_col = "de_school_point_logs", "school_id", w['school_id']
        type_withdraw, type_return = 11, 12
        lookup = SCHOOL_TYPES
    else:
        return {"id": withdraw_id, "status": "unknown_type",
                "type_id": type_id, "amount": w['amount']}

    # 统计本提现是该 user/school 名下（同 type_id）的第几次提现，并定位上一次提现
    seq_col = 'user_id' if type_id == 1 else 'school_id'
    cur.execute("""
        SELECT id, created_at, amount, balance
        FROM de_point_withdraws
        WHERE type_id = %s AND %s = %s AND deleted_at IS NULL
        ORDER BY created_at ASC, id ASC
    """ % ("%s", seq_col, "%s"), (type_id, log_id_col))
    seq_rows = cur.fetchall()
    seq_ids = [r['id'] for r in seq_rows]
    withdraw_seq = seq_ids.index(withdraw_id) + 1 if withdraw_id in seq_ids else None
    withdraw_total = len(seq_ids)

    # 定位上一次提现（同 user/school、同 type_id、created_at < 当前）
    cur.execute("""
        SELECT id, created_at, amount, balance
        FROM de_point_withdraws
        WHERE type_id = %s AND %s = %s AND deleted_at IS NULL
          AND created_at < %s
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    """ % ("%s", seq_col, "%s", "%s"), (type_id, log_id_col, w['created_at']))
    prev_w = cur.fetchone()
    prev_created_at = prev_w['created_at'] if prev_w else None
    prev_withdraw_id = prev_w['id'] if prev_w else None

    # 拉取上一次提现 ~ 本次提现 之间的所有流水明细（全部 type_id）
    if prev_created_at:
        sql = f"""
            SELECT id, type_id, amount, withdraw_amount, balance, msg,
                   rel_id, log_group, created_at
            FROM {log_table}
            WHERE {log_pk} = %s
              AND created_at > %s
              AND created_at <= %s
            ORDER BY created_at ASC, id ASC
        """
        cur.execute(sql, (log_id_col, prev_created_at, w['created_at']))
    else:
        # 没有上一次提现：取本次提现之前（含）的全部流水
        sql = f"""
            SELECT id, type_id, amount, withdraw_amount, balance, msg,
                   rel_id, log_group, created_at
            FROM {log_table}
            WHERE {log_pk} = %s
              AND created_at <= %s
            ORDER BY created_at ASC, id ASC
        """
        cur.execute(sql, (log_id_col, w['created_at']))
    detail_rows = cur.fetchall()

    # 单独取本次提现对应的扣款日志（rel_id 精确匹配）
    sql = f"""
        SELECT id, type_id, amount, withdraw_amount, balance, msg,
               rel_id, log_group, created_at
        FROM {log_table}
        WHERE {log_pk} = %s AND type_id IN (%s, %s)
          AND rel_id = %s
        ORDER BY created_at DESC
    """
    cur.execute(sql, (log_id_col, type_withdraw, type_return, withdraw_id))
    withdraw_logs = cur.fetchall()

    # 计算两次提现之间的流水净收入（仅非提现/退回类流水）
    # 收入类(amount>0)累加，支出类(amount<0)累加
    # 提现扣款(type=5/11)和提现退回(type=12)是边界事件，不计入收入/支出
    income_total = 0   # 收入合计(正)
    expense_total = 0  # 支出合计(正，取绝对值)
    for r in detail_rows:
        a = int(r['amount'] or 0)
        t = int(r['type_id'])
        if t == type_withdraw or t == type_return:
            continue  # 跳过提现扣款/退回日志（边界事件，非业务收支）
        if a > 0:
            income_total += a
        else:
            expense_total += abs(a)

    # 净流水 = 收入 - 支出（仅业务收支，不含提现/退回）
    net_flow = income_total - expense_total
    # 本次提现金额
    withdraw_amount = int(w['amount'])
    # 本次提现后剩余余额(balance 字段是提现前的余额)
    remaining_after = int(w['balance']) - withdraw_amount if w['balance'] is not None else 0
    # 上次提现后剩余余额 = 上次提现时余额 - 上次提现金额
    remaining_after_prev = 0
    if prev_w:
        remaining_after_prev = int(prev_w['balance'] or 0) - int(prev_w['amount'] or 0)

    # 合理性：净流水 = (本次提现金额 + 本次剩余) - 上次剩余
    # 即两次提现之间的收入应等于本次提现+本次剩余-上次剩余
    expected = (withdraw_amount + (remaining_after if remaining_after > 0 else 0)) - remaining_after_prev
    diff = net_flow - expected
    ok = (diff == 0)

    if verbose:
        print("=" * 92)
        print(f"提现 ID = {withdraw_id}")
        print("=" * 92)
        kind = "个人提现" if type_id == 1 else "校区提现"
        print(f"  类型        : type_id={type_id} ({kind})")
        seq_str = f"第 {withdraw_seq} 次提现（共 {withdraw_total} 次）" if withdraw_seq else "第 ? 次提现"
        print(f"  提现次序    : {seq_str}")
        print(f"  {log_pk:<10}: {log_id_col}  用户/姓名: {w.get('user_name')}  手机: {w.get('phone')}")
        print(f"  提现金额    : {w['amount']} 分 = ¥{yuan(w['amount'])}")
        print(f"  手续费 fee  : {w['fee']} 分 = ¥{yuan(w['fee'])}   实际到账 send_amount: ¥{yuan(w['send_amount'])}")
        print(f"  提现时余额  : ¥{yuan(w['balance'])}   状态 state: {w['state']}")
        print(f"  created_at  : {w['created_at']}   out_trade_no: {w.get('out_trade_no')}")
        print(f"  reason      : {w.get('reason') or ''}")
        if prev_w:
            print(f"  上次提现    : ID={prev_withdraw_id}  created_at={prev_created_at}  "
                  f"金额=¥{yuan(prev_w['amount'])}  提现前余额=¥{yuan(prev_w['balance'])}  "
                  f"剩余=¥{yuan(int(prev_w['balance'])-int(prev_w['amount']))}")
        else:
            print(f"  上次提现    : 无（本次为首次提现）")
        print()

        # 流水明细
        print(f"流水明细（{log_table}，{log_pk}={log_id_col}，从上次提现到本次提现，共 {len(detail_rows)} 条）")
        print("-" * 110)
        print(f"  {'log_id':>10} | {'type_id':>7} | {'type':<22} | {'amount':>12} | {'balance':>12} | {'created_at':<23} | {'rel_id':>10} | msg")
        print("-" * 110)
        for r in detail_rows:
            t = int(r['type_id'])
            tn = lookup.get(t, f"type{t}")
            # 标记本次提现扣款
            mark = " <- 本次提现" if (r['rel_id'] is not None and str(r['rel_id']) == str(withdraw_id)) else ""
            msg = (r.get('msg') or '').replace('\n', ' ')[:40] + mark
            print(f"  {r['id']:>10} | {t:>7} | {tn:<22} | "
                  f"¥{yuan(r['amount']):>11} | ¥{yuan(r['balance']):>11} | "
                  f"{str(r['created_at']):<23} | {str(r['rel_id']):>10} | {msg}")
        print("-" * 110)
        print(f"  收入合计   : ¥{yuan(income_total)}    支出合计: ¥{yuan(expense_total)}    "
              f"(仅业务收支，不含提现扣款/退回)")
        print()

        # 本次提现对应的扣款日志
        print(f"本次提现扣款日志（rel_id={withdraw_id}，共 {len(withdraw_logs)} 条）")
        if withdraw_logs:
            print(f"  {'log_id':>10} | {'type':<10} | {'amount':>10} | {'balance':>10} | created_at          | msg")
            print("  " + "-" * 88)
            for r in withdraw_logs:
                tn = lookup.get(int(r['type_id']), f"type{r['type_id']}")
                msg = (r.get('msg') or '').replace('\n', ' ')[:50]
                print(f"  {r['id']:>10} | {tn:<10} | ¥{yuan(r['amount']):>9} | ¥{yuan(r['balance']):>9} | {r['created_at']} | {msg}")
        else:
            print("  （未找到 rel_id 精确匹配的扣款日志）")
        print()

        # 合理性核对
        print("合理性核对")
        print("-" * 70)
        print(f"  两次提现之间净流水(收入-支出)          : ¥{yuan(net_flow)}")
        print(f"  本次提现金额                            : ¥{yuan(withdraw_amount)}")
        print(f"  本次提现后剩余余额                      : ¥{yuan(remaining_after) if remaining_after > 0 else '0.00'}")
        print(f"  上次提现后剩余余额                      : ¥{yuan(remaining_after_prev)}")
        print(f"  期望值(本次提现+本次剩余-上次剩余)       : ¥{yuan(expected)}")
        print(f"  差异(净流水 - 期望值)                    : ¥{yuan(diff)}")
        print(f"  结论                                   : {'✓ 合理（一致）' if ok else '✗ 异常（不一致）'}")
        print()

    return {
        "id": withdraw_id,
        "status": "ok" if ok else "mismatch",
        "type_id": type_id,
        "amount": int(w['amount']),
        "net_flow": net_flow,
        "expected": expected,
        "diff": diff,
        "income_total": income_total,
        "expense_total": expense_total,
        "detail_count": len(detail_rows),
        "prev_withdraw_id": prev_withdraw_id,
        "prev_created_at": prev_created_at,
        "prev_amount": int(prev_w['amount']) if prev_w else None,
        "prev_balance": int(prev_w['balance']) if prev_w else None,
        "withdraw_seq": withdraw_seq,
        "withdraw_total": withdraw_total,
        "state": int(w['state']),
        "user_name": w.get('user_name'),
        "user_id": w.get('user_id'),
        "school_id": w.get('school_id'),
    }


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="提现金额合理性核对")
    p.add_argument('ids', nargs='*', help='要核对的提现 ID（多个空格分隔）')
    p.add_argument('--range', dest='id_range',
                   help='ID 区间 start:end (左闭右闭)')
    p.add_argument('--state', type=int, help='只核对某个 state')
    p.add_argument('--recent', type=int, help='只核对最近 N 条')
    p.add_argument('--since', help='只核对 created_at >= 该日期 (YYYY-MM-DD)')
    p.add_argument('--quiet', action='store_true', help='只输出汇总表，不打印单条详情')
    return p.parse_args()


def fetch_ids(cur, args):
    if args.ids:
        return [int(x) for x in args.ids]
    if args.id_range:
        a, b = args.id_range.split(':')
        return [("range", int(a), int(b))]
    # 从 DB 取
    sql = "SELECT id FROM de_point_withdraws WHERE deleted_at IS NULL"
    params = []
    if args.state is not None:
        sql += " AND state = %s"; params.append(args.state)
    if args.since:
        sql += " AND created_at >= %s"; params.append(args.since)
    sql += " ORDER BY id DESC"
    if args.recent:
        sql += f" LIMIT {int(args.recent)}"
    cur.execute(sql, params)
    return [r['id'] for r in cur.fetchall()]


def main():
    args = parse_args()
    conn, transport = make_conn()
    cur = conn.cursor()

    ids = fetch_ids(cur, args)
    # 处理 range 模式
    final_ids = []
    for x in ids:
        if isinstance(x, tuple) and x[0] == "range":
            a, b = x[1], x[2]
            cur.execute("SELECT id FROM de_point_withdraws WHERE id BETWEEN %s AND %s "
                        "AND deleted_at IS NULL ORDER BY id", (a, b))
            final_ids.extend([r['id'] for r in cur.fetchall()])
        else:
            final_ids.append(x)
    ids = final_ids

    print(f"\n待核对提现 ID 共 {len(ids)} 条\n")
    if not ids:
        print("没有需要核对的 ID")
        return

    results = []
    for i, wid in enumerate(ids, 1):
        if not args.quiet:
            print(f"\n[{i}/{len(ids)}] 核对 ID={wid}")
        try:
            r = verify_one(cur, wid, verbose=not args.quiet)
            results.append(r)
        except Exception as e:
            print(f"  [ERROR] ID={wid}: {e}")
            results.append({"id": wid, "status": "error", "error": str(e)})

    # 汇总表
    print("\n" + "=" * 130)
    print("汇总")
    print("=" * 130)
    print(f"{'id':>8} | {'type':<6} | {'user/school':<14} | {'第N次':>8} | {'state':>5} | "
          f"{'上次提现日期':<19} | {'上次金额':>10} | {'本次提现':>10} | "
          f"{'净流水':>10} | {'diff':>8} | {'明细数':>6} | 结论")
    print("-" * 130)
    n_ok = n_bad = n_err = n_nf = 0
    for r in results:
        st = r.get('status')
        if st == 'ok':
            n_ok += 1; tag = '✓ 合理'
        elif st == 'mismatch':
            n_bad += 1; tag = '✗ 异常'
        elif st == 'not_found':
            n_nf += 1; tag = '未找到'
        elif st == 'unknown_type':
            n_bad += 1; tag = '✗ 未知类型'
        else:
            n_err += 1; tag = '错误'
        us = r.get('school_id') or r.get('user_id') or ''
        us = f"u{r['user_id']}" if r.get('type_id') == 1 and r.get('user_id') else (
             f"s{r['school_id']}" if r.get('type_id') == 2 and r.get('school_id') else str(us))
        seq_disp = (f"{r.get('withdraw_seq','?')}/{r.get('withdraw_total','?')}"
                    if r.get('withdraw_seq') else "-")
        prev_date = str(r.get('prev_created_at',''))[:19] if r.get('prev_created_at') else '(首次)'
        prev_amt = f"¥{yuan(r.get('prev_amount',0) or 0)}" if r.get('prev_amount') is not None else '-'
        print(f"{r['id']:>8} | {('个人' if r.get('type_id')==1 else '校区' if r.get('type_id')==2 else '?'):<6} | "
              f"{us:<14} | {seq_disp:>8} | {str(r.get('state','')):>5} | "
              f"{prev_date:<19} | {prev_amt:>10} | "
              f"¥{yuan(r.get('amount',0)):>9} | ¥{yuan(r.get('net_flow',0) or 0):>9} | "
              f"¥{yuan(r.get('diff',0) or 0):>7} | {str(r.get('detail_count','')):>6} | {tag}")

    print("-" * 130)
    print(f"合计 {len(results)} 条  |  合理 {n_ok}  |  异常 {n_bad}  |  未找到 {n_nf}  |  错误 {n_err}")
    print()

    # 列出异常 ID
    bad = [r for r in results if r.get('status') in ('mismatch', 'unknown_type')]
    if bad:
        print("⚠ 异常 ID 列表：")
        for r in bad:
            prev_date = str(r.get('prev_created_at',''))[:19] if r.get('prev_created_at') else '(首次)'
            print(f"  ID={r['id']}  diff=¥{yuan(r.get('diff',0) or 0)}  "
                  f"amount=¥{yuan(r.get('amount',0))}  net_flow=¥{yuan(r.get('net_flow',0) or 0)}  "
                  f"expected=¥{yuan(r.get('expected',0) or 0)}  "
                  f"prev={r.get('prev_withdraw_id')}({prev_date})")
        print()

    cur.close(); conn.close(); transport.close()


if __name__ == '__main__':
    main()
