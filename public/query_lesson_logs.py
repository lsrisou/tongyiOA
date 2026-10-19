"""用法: python3 query_lesson_logs.py <lesson_id>

按课程 id(de_student_hour_lessons.id) 查询 de_admin_action_logs 中的操作日志:
- 匹配 content JSON 里 request.id(以及 old/其他位置的 id) == 课程id
- 按 created_at 正序输出: 时间 / 操作人(de_admin_users) / action / content / old / request / IP
"""
import json
import select
import socket
import sys
import threading

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


def find_matches(node, lesson_id, path='$'):
    """递归查找 content JSON 中 key 为 id 类字段且值等于课程id的位置。"""
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


def fmt(v):
    if v is None:
        return '(空)'
    if isinstance(v, str) and v.strip():
        try:
            return json.dumps(json.loads(v), ensure_ascii=False, separators=(',', ':'))
        except Exception:
            return v
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'))


def main():
    if len(sys.argv) < 2:
        print('用法: python3 query_lesson_logs.py <lesson_id>')
        sys.exit(1)
    lesson_id = int(sys.argv[1])

    client = ssh_client()
    port = open_bridge(client, DB_HOST, DB_PORT)
    conn = pymysql.connect(host='127.0.0.1', port=port, user=DB_USER, password=DB_PASS,
                           db=DB_NAME, charset='utf8mb4', connect_timeout=20,
                           cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, student_id, teacher_id, start_time, hour_count, state '
                        'FROM de_student_hour_lessons WHERE id=%s', (lesson_id,))
            lesson = cur.fetchone()
            print(f'===== 课程 de_student_hour_lessons id={lesson_id} =====')
            print(json.dumps(lesson, ensure_ascii=False, default=str) if lesson else '(课程不存在)')

            # LIKE 预过滤后由 Python 精确匹配 JSON 路径
            cur.execute(
                'SELECT id, region, school_id, user_id, creator, action, msg, content, ip, created_at '
                'FROM de_admin_action_logs '
                'WHERE content LIKE %s ORDER BY created_at ASC, id ASC',
                (f'%{lesson_id}%',))
            rows = cur.fetchall()

            logs = []
            for r in rows:
                try:
                    c = json.loads(r['content']) if r['content'] else {}
                except Exception:
                    c = {}
                paths = find_matches(c, lesson_id)
                if paths:
                    r['_content_json'] = c
                    r['_paths'] = paths
                    logs.append(r)

            print(f'\n===== 操作日志 {len(logs)} 条 (created_at 正序) =====')
            if not logs:
                print('(未找到相关日志)')

            user_ids = set()
            for r in logs:
                for k in ('creator', 'user_id'):
                    if r.get(k):
                        user_ids.add(r[k])
            names = {}
            if user_ids:
                ph = ','.join(['%s'] * len(user_ids))
                cur.execute(f'SELECT id, name, username FROM de_admin_users WHERE id IN ({ph})',
                            list(user_ids))
                names = {u['id']: u for u in cur.fetchall()}

            for i, r in enumerate(logs, 1):
                c = r['_content_json']
                cu = names.get(r['creator'])
                cu_s = f"{r['creator']}({cu['name']}/{cu['username']})" if cu else f"{r['creator']}(未找到用户)"
                print(f'\n--- #{i} 日志id={r["id"]}  时间={r["created_at"]}')
                print(f'    操作人 creator={cu_s}  user_id={r["user_id"]}  action={r["action"]}  IP={r["ip"]}')
                if r['msg']:
                    print(f'    msg: {r["msg"]}')
                print(f'    匹配位置: {", ".join(r["_paths"])}')
                if 'old' in c:
                    print(f'    old(改之前): {fmt(c["old"])}')
                if 'request' in c:
                    print(f'    request: {fmt(c["request"])}')
                rest = {k: v for k, v in c.items() if k not in ('old', 'request')}
                if rest:
                    print(f'    content其他字段: {fmt(rest)}')
    finally:
        conn.close()
        client.close()


if __name__ == '__main__':
    main()
