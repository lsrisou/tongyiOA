"""导出各角色逐月收入排行（Excel）

用法:
    python export_income_rank_monthly.py                 # 默认导出 2026-08 / 09 / 10
    python export_income_rank_monthly.py 2026-08 2026-09 2026-10
    python export_income_rank_monthly.py 2026-08 2026-09 --top 10
    python export_income_rank_monthly.py 2026 1 2 3 --top all   # 全部人员
"""
import os
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ssh.py 与本脚本同目录，或放在 ./public 下
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, 'public'))
import ssh  # noqa: E402

DEFAULT_MONTHS = ['2026-08', '2026-09', '2026-10']
TOP_N = None  # None 表示导出全部人员

# 角色 -> 过滤条件
ROLES = [
    ('教练', "u.role_id IN ('school_teacher','school_pre_teacher')"),
    ('教务', "u.role_id = 'school_dean'"),
    ('校长', "u.role_id = 'school_headmaster'"),
    ('副校长', "u.role_id = 'school_deputymaster'"),
]


def parse_months(argv):
    """解析 ['2026-08', '2026-09', ...] 或 ['2026', '8', '9', '10']"""
    if not argv:
        return DEFAULT_MONTHS, TOP_N
    top_n = TOP_N
    if '--top' in argv:
        i = argv.index('--top')
        value = argv[i + 1]
        top_n = None if value.lower() == 'all' else int(value)
        argv = argv[:i] + argv[i + 2:]
    if all('-' in a for a in argv):
        months = argv
    else:
        year = argv[0]
        months = [f'{year}-{int(m):02d}' for m in argv[1:]]
    return months, top_n


def month_bounds(ym):
    """返回自然月的 [开始, 结束) 时间字符串"""
    y, m = (int(x) for x in ym.split('-'))
    start = f'{y}-{m:02d}-01 00:00:00'
    end = f'{y}-{m + 1:02d}-01 00:00:00' if m < 12 else f'{y + 1}-01-01 00:00:00'
    return start, end


def month_label(ym):
    y, m = ym.split('-')
    return f'{y}年{int(m)}月'


cur = ssh.conn.cursor()


def fetch(role_sql, months):
    """按 用户 x 月份 聚合收入(分)"""
    start, _ = month_bounds(months[0])
    _, end = month_bounds(months[-1])
    sql = f"""
        SELECT u.id AS user_id, u.name AS user_name, u.school_id,
               s.name AS school_name,
               DATE_FORMAT(l.created_at, '%%Y-%%m') AS ym,
               SUM(l.amount) AS total_fen, COUNT(*) AS cnt
        FROM deshengoa.de_user_point_logs l
        JOIN deshengoa.de_admin_users u ON u.id = l.user_id
        LEFT JOIN deshengoa.de_schools s ON s.id = u.school_id
        WHERE l.created_at >= %s AND l.created_at < %s
          AND l.type_id != 5
          AND l.amount > 0
          AND u.deleted_at IS NULL
          AND {role_sql}
        GROUP BY u.id, u.name, u.school_id, s.name, ym
    """
    cur.execute(sql, (start, end))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    users = {}
    for r in rows:
        u = users.setdefault(r['user_id'], {
            'user_id': r['user_id'],
            'user_name': r['user_name'],
            'school_name': r['school_name'],
            'months': {m: 0 for m in months},
        })
        u['months'][r['ym']] = r['total_fen']
    result = list(users.values())
    for u in result:
        u['total_fen'] = sum(u['months'].values())
    result.sort(key=lambda u: (-u['total_fen'], str(u['user_name'])))
    return result


def write_sheet(ws, title, rows, months, top_n):
    ws.title = title
    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')
    center = Alignment(horizontal='center', vertical='center')
    right = Alignment(horizontal='right')
    total_fill = PatternFill(start_color='DCE6F1', end_color='DCE6F1', fill_type='solid')

    headers = ['排名', '用户ID', '姓名', '学校'] + [month_label(m) for m in months] + ['合计(元)']
    for c, h in enumerate(headers, 1):
        cell = ws.cell(1, c, h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center

    for i, u in enumerate(rows[:top_n], 1):
        ws.cell(i + 1, 1, i).alignment = center
        ws.cell(i + 1, 2, u['user_id']).alignment = center
        ws.cell(i + 1, 3, u['user_name'])
        ws.cell(i + 1, 4, u['school_name'])
        for j, m in enumerate(months):
            cell = ws.cell(i + 1, 5 + j, round(u['months'][m] / 100, 2))
            cell.number_format = '#,##0.00'
            cell.alignment = right
        total = ws.cell(i + 1, 5 + len(months), round(u['total_fen'] / 100, 2))
        total.number_format = '#,##0.00'
        total.alignment = right
        total.font = Font(bold=True)
        total.fill = total_fill

    if not rows:
        ws.cell(2, 1, '无数据').alignment = center

    widths = [6, 10, 12, 24] + [13] * len(months) + [15]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'E2'


months, top_n = parse_months(sys.argv[1:])
data = {name: fetch(sql, months) for name, sql in ROLES}

wb = Workbook()
first = True
for name, _ in ROLES:
    ws = wb.active if first else wb.create_sheet()
    first = False
    write_sheet(ws, f'{name}收入排行', data[name], months, top_n)

y0, m0 = months[0].split('-')
y1, m1 = months[-1].split('-')
span = f'{y0}年{int(m0):02d}-{int(m1):02d}月' if y0 == y1 and len(months) > 1 else '_'.join(months)
suffix = '' if top_n is None else f'TOP{top_n}'
filename = f'{span}各角色收入排行{suffix}.xlsx'
wb.save(filename)

for name, _ in ROLES:
    rows = data[name]
    total = sum(r['total_fen'] for r in rows)
    print(f'===== {name} (共 {len(rows)} 人, 合计 {total / 100:,.2f} 元) =====')
    for i, u in enumerate(rows[:10], 1):
        vals = '  '.join(f'{u["months"][m] / 100:>10,.2f}' for m in months)
        print(f'{i:>2}. {str(u["user_name"]):<8} {str(u["school_name"]):<18} {vals}  | {u["total_fen"] / 100:>12,.2f}')
    print()

print(f'已导出: {filename}')
cur.close()
ssh.conn.close()
