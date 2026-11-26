import ssh
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

YEAR, MONTH = 2026, 8
import sys
if len(sys.argv) > 1:
    MONTH = int(sys.argv[1])
START = f'{YEAR}-{MONTH:02d}-01 00:00:00'
END = f'{YEAR}-{MONTH+1:02d}-01 00:00:00' if MONTH < 12 else f'{YEAR+1}-01-01 00:00:00'

cur = ssh.conn.cursor()

def ranking(role_filter_sql, title):
    sql = f"""
        SELECT u.id AS user_id, u.name AS user_name, u.school_id,
               s.name AS school_name,
               SUM(l.amount) AS total_fen, COUNT(*) AS cnt
        FROM deshengoa.de_user_point_logs l
        JOIN deshengoa.de_admin_users u ON u.id = l.user_id
        LEFT JOIN deshengoa.de_schools s ON s.id = u.school_id
        WHERE l.created_at >= %s AND l.created_at < %s
          AND l.type_id != 5
          AND l.amount > 0
          AND u.deleted_at IS NULL
          AND {role_filter_sql}
        GROUP BY u.id, u.name, u.school_id, s.name
        ORDER BY total_fen DESC
        LIMIT 50
    """
    cur.execute(sql, (START, END))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return rows

coach_rows = ranking("u.role_id IN ('school_teacher','school_pre_teacher')", '教练')
dean_rows = ranking("u.role_id = 'school_dean'", '教务')
head_rows = ranking("u.role_id = 'school_headmaster'", '校长')
deputy_rows = ranking("u.role_id = 'school_deputymaster'", '副校长')

# 汇总
def summarize(rows):
    if not rows:
        return 0, 0
    total = sum(r['total_fen'] for r in rows)
    return len(rows), total

coach_n, coach_total = summarize(coach_rows)
dean_n, dean_total = summarize(dean_rows)
head_n, head_total = summarize(head_rows)
deputy_n, deputy_total = summarize(deputy_rows)

print(f"===== {YEAR}-{MONTH:02d} 教练收入 TOP15 (共 {coach_n} 人, 合计 {coach_total/100:,.2f} 元) =====")
for i, r in enumerate(coach_rows[:15], 1):
    print(f"{i:>2}. {r['user_name']:<10} {str(r['school_name']):<20} {r['total_fen']/100:>12,.2f} 元  ({r['cnt']}笔)")

print(f"\n===== {YEAR}-{MONTH:02d} 教务收入 TOP15 (共 {dean_n} 人, 合计 {dean_total/100:,.2f} 元) =====")
for i, r in enumerate(dean_rows[:15], 1):
    print(f"{i:>2}. {r['user_name']:<10} {str(r['school_name']):<20} {r['total_fen']/100:>12,.2f} 元  ({r['cnt']}笔)")

print(f"\n===== {YEAR}-{MONTH:02d} 校长收入 TOP10 (共 {head_n} 人, 合计 {head_total/100:,.2f} 元, 多为提现故为负) =====")
for i, r in enumerate(head_rows[:10], 1):
    print(f"{i:>2}. {r['user_name']:<10} {str(r['school_name']):<20} {r['total_fen']/100:>12,.2f} 元  ({r['cnt']}笔)")

print(f"\n===== {YEAR}-{MONTH:02d} 副校长收入 TOP10 (共 {deputy_n} 人, 合计 {deputy_total/100:,.2f} 元) =====")
for i, r in enumerate(deputy_rows[:10], 1):
    print(f"{i:>2}. {r['user_name']:<10} {str(r['school_name']):<20} {r['total_fen']/100:>12,.2f} 元  ({r['cnt']}笔)")

# 导出 Excel
wb = Workbook()
header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
header_font = Font(bold=True, color="FFFFFF")
center = Alignment(horizontal='center')
right = Alignment(horizontal='right')

def write_sheet(ws, rows, label):
    ws.title = label
    headers = ['排名', '用户ID', '姓名', '学校', '收入(元)', '笔数']
    for c, h in enumerate(headers, 1):
        cell = ws.cell(1, c, h)
        cell.fill = header_fill; cell.font = header_font; cell.alignment = center
    for i, r in enumerate(rows, 1):
        ws.cell(i+1, 1, i).alignment = center
        ws.cell(i+1, 2, r['user_id']).alignment = center
        ws.cell(i+1, 3, r['user_name'])
        ws.cell(i+1, 4, r['school_name'])
        amt = ws.cell(i+1, 5, round(r['total_fen']/100, 2)); amt.alignment = right; amt.number_format = '#,##0.00'
        ws.cell(i+1, 6, r['cnt']).alignment = center
    ws.column_dimensions['A'].width = 6
    ws.column_dimensions['B'].width = 10
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 22
    ws.column_dimensions['E'].width = 14
    ws.column_dimensions['F'].width = 8

write_sheet(wb.active, coach_rows, '教练收入TOP50')
ws2 = wb.create_sheet()
write_sheet(ws2, dean_rows, '教务收入TOP50')
ws3 = wb.create_sheet()
write_sheet(ws3, head_rows, '校长收入TOP50')
ws4 = wb.create_sheet()
write_sheet(ws4, deputy_rows, '副校长收入TOP50')

filename = f'{YEAR}年{MONTH:02d}月教练教务收入排行.xlsx'
wb.save(filename)
print(f"\n已导出: {filename}")
cur.close()
ssh.conn.close()
