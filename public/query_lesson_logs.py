"""操作日志查询工具 (deshengoa.de_admin_action_logs + de_school_hour_logs)

用法:
  python3 query_lesson_logs.py <creator_id> [start end] [--action 关键词]
      按管理员 id(=de_admin_users.id) 查操作日志, created_at 正序
      同时输出 de_school_hour_logs 中 creator=该 id 的校区课时变动日志
      start/end 可选, 格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS (end 为日期时含当天)
  python3 query_lesson_logs.py --lesson <lesson_id>
      按课程 id(de_student_hour_lessons.id) 查相关日志

示例:
  python3 query_lesson_logs.py 17399 2026-10-18 2026-10-18
  python3 query_lesson_logs.py 17399 --action 课程评价
  python3 query_lesson_logs.py 91
"""
import json
import select
import socket
import sys
import threading
from datetime import datetime, timedelta

import paramiko
import pymysql

# ===== 连接配置(与 ssh.py 相同, 经代理 CONNECT + SSH 隧道访问内网 RDS) =====
PROXY = ('127.0.0.1', 18080)
SSH_HOST = '8.141.117.235'
SSH_PORT = 22
SSH_USER = 'dev_risou'
SSH_PASS = 'TLiRisou2008'

DB_HOST = 'rm-2zel54y4czcyl911h.mysql.rds.aliyuncs.com'
DB_PORT = 3306
DB_USER = 'deshengoa'
DB_PASS = 'EZayyR4qDu7vA3EwSdeKAE8n'
DB_NAME = 'deshengoa'

ID_KEYS = {'id', 'lesson_id', 'lessonId', 'lessonIdList', 'ids'}


def proxy_connect_socket(host, port):
    s = socket.create_connection(PROXY, timeout=20)
    s.sendall(f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n'.encode())
    buf = b''
    while b'\r\n\r\n' not in buf:
        chunk = s.recv(4096)
        if not chunk:
            raise RuntimeError('proxy closed during CONNECT')
        buf += chunk
    if ' 200' not in buf.split(b'\r\n', 1)[0].decode(errors='replace'):
        raise RuntimeError(f'CONNECT failed: {buf[:120]!r}')
    return s


def ssh_client():
    s = proxy_connect_socket(SSH_HOST, SSH_PORT)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS, sock=s,
              look_for_keys=False, allow_agent=False, timeout=30, banner_timeout=30)
    return c


def open_bridge(client, remote_host, remote_port):
    srv = socket.socket()
    srv.bind(('127.0.0.1', 0))
    srv.listen(32)
    local_port = srv.getsockname()[1]

    def pump(a, b):
        try:
            while True:
                r, _, _ = select.select([a, b], [], [], 120)
                if not r:
                    break
                if a in r:
                    d = a.recv(65536)
                    if not d:
                        break
                    b.sendall(d)
                if b in r:
                    d = b.recv(65536)
                    if not d:
                        break
                    a.sendall(d)
        except Exception:
            pass
        finally:
            for x in (a, b):
                try:
                    x.close()
                except Exception:
                    pass

    def acceptor():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                break
            ch = client.get_transport().open_channel(
                'direct-tcpip', (remote_host, remote_port), ('127.0.0.1', 0))
            threading.Thread(target=pump, args=(c, ch), daemon=True).start()

    threading.Thread(target=acceptor, daemon=True).start()
    return local_port


def connect():
    client = ssh_client()
    port = open_bridge(client, DB_HOST, DB_PORT)
    conn = pymysql.connect(host='127.0.0.1', port=port, user=DB_USER, password=DB_PASS,
                           db=DB_NAME, charset='utf8mb4', connect_timeout=20,
                           cursorclass=pymysql.cursors.DictCursor)
    return client, conn


def fmt(v):
    """尽量把 JSON 字符串压成一行中文友好的格式。"""
    if v is None:
        return '(空)'
    if isinstance(v, str) and v.strip():
        try:
            v = json.loads(v)
        except Exception:
            return v
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'))


def parse_date(s, end=False):
    fmts = ['%Y-%m-%d', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S']
    for f in fmts:
        try:
            d = datetime.strptime(s, f)
            if end and f == '%Y-%m-%d':
                d = d + timedelta(days=1) - timedelta(seconds=1)
            return d.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    raise SystemExit(f'日期格式不对: {s} (用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)')


def find_matches(node, lesson_id, path='$'):
    hits = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f'{path}.{k}'
            if k in ID_KEYS and (v == lesson_id or str(v) == str(lesson_id)):
                hits.append(p)
            elif k in ID_KEYS and isinstance(v, list) and lesson_id in v:
                hits.append(p)
            hits += find_matches(v, lesson_id, p)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits += find_matches(v, lesson_id, f'{path}[{i}]')
    return hits


def query_creator(cur, creator_id, start, end, action_kw):
    """按 creator id 查日志, 返回 (用户信息, 日志列表, 统计, action分布, 课时日志列表, log_type分布)"""
    cur.execute('SELECT id, name, username, disabled FROM de_admin_users WHERE id=%s', (creator_id,))
    user = cur.fetchone()
    cond, args = ['creator=%s'], [creator_id]
    if start:
        cond.append('created_at>=%s')
        args.append(start)
    if end:
        cond.append('created_at<=%s')
        args.append(end)
    if action_kw:
        cond.append('action LIKE %s')
        args.append(f'%{action_kw}%')
    where = ' AND '.join(cond)
    cur.execute(f'SELECT COUNT(*) AS c, MIN(created_at) AS mn, MAX(created_at) AS mx '
                f'FROM de_admin_action_logs WHERE {where}', args)
    stat = cur.fetchone()
    cur.execute(f'SELECT id, user_id, action, msg, content, ip, created_at '
                f'FROM de_admin_action_logs WHERE {where} ORDER BY created_at ASC, id ASC', args)
    rows = cur.fetchall()
    cur.execute(f'SELECT action, COUNT(*) AS c FROM de_admin_action_logs WHERE {where} '
                f'GROUP BY action ORDER BY c DESC', args)
    by_action = cur.fetchall()
    # 校区课时变动日志 (时间过滤同样生效, --action 不适用)
    hcond, hargs = ['creator=%s'], [creator_id]
    if start:
        hcond.append('created_at>=%s')
        hargs.append(start)
    if end:
        hcond.append('created_at<=%s')
        hargs.append(end)
    hwhere = ' AND '.join(hcond)
    cur.execute(f'SELECT COUNT(*) AS c, MIN(created_at) AS mn, MAX(created_at) AS mx '
                f'FROM de_school_hour_logs WHERE {hwhere}', hargs)
    hstat = cur.fetchone()
    cur.execute(f'SELECT id, school_id, log_type, hour_count, rel_school_id, to_student_id, '
                f'ip_address, remark, created_at, hour_type, order_id, deleted_at '
                f'FROM de_school_hour_logs WHERE {hwhere} ORDER BY created_at ASC, id ASC', hargs)
    hour_rows = cur.fetchall()
    cur.execute(f'SELECT log_type, COUNT(*) AS c FROM de_school_hour_logs WHERE {hwhere} '
                f'GROUP BY log_type ORDER BY c DESC', hargs)
    return user, rows, stat, by_action, hour_rows, hstat, cur.fetchall()


def query_lesson(cur, lesson_id):
    cur.execute('SELECT id, student_id, teacher_id, start_time, hour_count, state '
                'FROM de_student_hour_lessons WHERE id=%s', (lesson_id,))
    lesson = cur.fetchone()
    cur.execute('SELECT id, creator, user_id, action, msg, content, ip, created_at '
                'FROM de_admin_action_logs WHERE content LIKE %s ORDER BY created_at ASC, id ASC',
                (f'%{lesson_id}%',))
    logs = []
    for r in cur.fetchall():
        try:
            c = json.loads(r['content']) if r['content'] else {}
        except Exception:
            c = {}
        paths = find_matches(c, lesson_id)
        if paths:
            r['_paths'] = paths
            r['_c'] = c
            logs.append(r)
    return lesson, logs


def school_names(cur, sids):
    """取校区名, 表/字段不存在则返回空映射。"""
    sids = {s for s in sids if s}
    if not sids:
        return {}
    ph = ','.join(['%s'] * len(sids))
    try:
        cur.execute(f'SELECT id, name FROM de_schools WHERE id IN ({ph})', list(sids))
        return {r['id']: r['name'] for r in cur.fetchall()}
    except Exception:
        return {}


def show_hour_logs(cur, creator_id, hour_rows, hstat, by_ltype, rng):
    print(f'===== 校区课时变动日志 (de_school_hour_logs, creator={creator_id}) =====')
    print(f'{hstat["c"]} 条, 时间 {hstat["mn"]} ~ {hstat["mx"]} {rng and f"[过滤:{rng}]"}')
    print('类型分布: ' + ', '.join(f'{r["log_type"]}×{r["c"]}' for r in by_ltype) or '(无)')
    names = school_names(cur, {r['school_id'] for r in hour_rows} | {r['rel_school_id'] for r in hour_rows})
    def sname(sid):
        return f'{sid}({names[sid]})' if sid in names else str(sid)
    for i, r in enumerate(hour_rows, 1):
        dead = '  [已作废]' if r['deleted_at'] else ''
        to = f'  学生={r["to_student_id"]}' if r['to_student_id'] else ''
        rel = f'  对方校区={sname(r["rel_school_id"])}' if r['rel_school_id'] else ''
        print(f'--- #{i} 日志id={r["id"]}  时间={r["created_at"]}  type={r["log_type"]}  '
              f'课时={r["hour_count"]}  校区={sname(r["school_id"])}{to}{rel}  IP={r["ip_address"]}{dead}')
        extra = []
        if r['remark']:
            extra.append(f'remark: {r["remark"]}')
        if r['order_id']:
            extra.append(f'order_id={r["order_id"]}')
        if r['hour_type']:
            extra.append(f'hour_type={r["hour_type"]}')
        if extra:
            print(f'    ' + '  '.join(extra))
    if not hour_rows:
        print('(无课时变动日志)')


def show_creator(cur, creator_id, start, end, action_kw):
    user, rows, stat, by_action, hour_rows, hstat, by_ltype = query_creator(cur, creator_id, start, end, action_kw)
    rng = f'{start or ""} ~ {end or ""}'.strip(' ~')
    if user:
        print(f'===== 操作人: id={user["id"]} {user["name"]} ({user["username"]}) '
              f'disabled={user["disabled"]} =====')
    else:
        print(f'===== creator id={creator_id} (de_admin_users 中未找到) =====')
    print(f'日志 {stat["c"]} 条, 时间 {stat["mn"]} ~ {stat["mx"]} {rng and f"[过滤:{rng}]"}'
          + (f' [action过滤:{action_kw}]' if action_kw else ''))
    print('操作类型分布: ' + ', '.join(f'{r["action"]}×{r["c"]}' for r in by_action))
    print()
    for i, r in enumerate(rows, 1):
        print(f'--- #{i} 日志id={r["id"]}  时间={r["created_at"]}  '
              f'action={r["action"]}  IP={r["ip"]}')
        if r['msg']:
            print(f'    msg: {r["msg"]}')
        print(f'    content: {fmt(r["content"])}')
    if not rows:
        print('(无日志)')
    print()
    show_hour_logs(cur, creator_id, hour_rows, hstat, by_ltype, rng)


def show_lesson(cur, lesson_id):
    lesson, logs = query_lesson(cur, lesson_id)
    print(f'===== 课程 de_student_hour_lessons id={lesson_id} =====')
    print(json.dumps(lesson, ensure_ascii=False, default=str) if lesson else '(课程不存在)')
    print(f'\n===== 操作日志 {len(logs)} 条 (created_at 正序) =====')
    names = {}
    uids = {r['creator'] for r in logs if r['creator']}
    if uids:
        ph = ','.join(['%s'] * len(uids))
        cur.execute(f'SELECT id, name, username FROM de_admin_users WHERE id IN ({ph})', list(uids))
        names = {u['id']: u for u in cur.fetchall()}
    for i, r in enumerate(logs, 1):
        u = names.get(r['creator'])
        cu = f"{r['creator']}({u['name']}/{u['username']})" if u else f"{r['creator']}(未找到用户)"
        print(f'\n--- #{i} 日志id={r["id"]}  时间={r["created_at"]}')
        print(f'    操作人 creator={cu}  action={r["action"]}  IP={r["ip"]}')
        print(f'    匹配位置: {", ".join(r["_paths"])}')
        c = r['_c']
        if 'old' in c:
            print(f'    old(改之前): {fmt(c["old"])}')
        if 'request' in c:
            print(f'    request: {fmt(c["request"])}')
        rest = {k: v for k, v in c.items() if k not in ('old', 'request')}
        if rest:
            print(f'    content其他字段: {fmt(rest)}')
    if not logs:
        print('(未找到相关日志)')


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)
    action_kw = None
    if '--action' in argv:
        i = argv.index('--action')
        action_kw = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    client, conn = connect()
    try:
        with conn.cursor() as cur:
            if argv[0] == '--lesson':
                show_lesson(cur, int(argv[1]))
            else:
                creator_id = int(argv[0])
                start = parse_date(argv[1]) if len(argv) > 1 else None
                end = parse_date(argv[2], end=True) if len(argv) > 2 else None
                show_creator(cur, creator_id, start, end, action_kw)
    finally:
        conn.close()
        client.close()


if __name__ == '__main__':
    main()
