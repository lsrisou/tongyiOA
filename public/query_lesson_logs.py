"""操作日志查询工具 (deshengoa.de_admin_action_logs)

用法:
  python3 query_lesson_logs.py <creator_id> [start end] [--action 关键词]
      按管理员 id(=de_admin_users.id, 即日志 creator 字段) 查操作日志, created_at 正序
      start/end 可选, 格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS (end 为日期时含当天)
  python3 query_lesson_logs.py --lesson <lesson_id>
      按课程 id(de_student_hour_lessons.id) 查相关日志

示例:
  python3 query_lesson_logs.py 17399 2026-10-18 2026-10-18
  python3 query_lesson_logs.py 17399 --action 课程评价
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
    """按 creator id 查日志, 返回 (用户信息, 日志列表, 各action统计)"""
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
    return user, rows, stat, cur.fetchall()


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


def show_creator(cur, creator_id, start, end, action_kw):
    user, rows, stat, by_action = query_creator(cur, creator_id, start, end, action_kw)
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
