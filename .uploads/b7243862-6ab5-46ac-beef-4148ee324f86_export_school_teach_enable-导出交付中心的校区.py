import ssh
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from datetime import datetime

cursor = ssh.conn.cursor()


def fetch_records(limit=None):
    sql = f"""
        SELECT
            school.id AS school_id,
            school.name AS school_name,
            school.teach_start_at,
            school.teach_end_at,
            log.id AS log_id,
            log.creator,
            admin.name AS creator_name,
            log.content,
            log.created_at
        FROM deshengoa.de_schools AS school
        LEFT JOIN deshengoa.de_admin_action_logs AS log
            ON log.school_id = school.id
           AND log.content LIKE '%"teachEnable":true%'
        LEFT JOIN deshengoa.de_admin_users AS admin ON admin.id = log.creator
        WHERE school.teach_enable = 1
        ORDER BY log.created_at ASC
    """
    if limit is not None:
        sql += f" LIMIT {limit}"
    cursor.execute(sql)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    dates_by_school = {}
    for rs in rows:
        s = dict(zip(columns, rs))
        if s['log_id'] is None:
            continue
        dates_by_school.setdefault(s['school_id'], []).append(
            s['created_at'].strftime('%Y-%m-%d %H:%M:%S'))

    latest_by_school = {}
    for rs in rows:
        s = dict(zip(columns, rs))
        if s['log_id'] is None:
            continue
        school_id = s['school_id']
        if school_id not in latest_by_school or s['log_id'] > latest_by_school[school_id]['log_id']:
            latest_by_school[school_id] = s

    school_names = {}
    school_start = {}
    school_end = {}
    for rs in rows:
        s = dict(zip(columns, rs))
        school_names[s['school_id']] = s['school_name']
        school_start[s['school_id']] = datetime.fromtimestamp(s['teach_start_at']).strftime('%Y-%m-%d') if s['teach_start_at'] else ''
        school_end[s['school_id']] = datetime.fromtimestamp(s['teach_end_at']).strftime('%Y-%m-%d') if s['teach_end_at'] else ''

    records = []
    for school_id in sorted(school_names):
        s = latest_by_school.get(school_id)
        if s is None:
            records.append({
                '校区ID': school_id,
                '校区名称': school_names[school_id],
                '操作日志ID': '',
                '操作人': '',
                '代理类型': '交付中心',
                '交付期开始日期': school_start[school_id],
                '交付期结束日期': school_end[school_id],
                '最后标记交付中心日期（历史变更日期）': '无记录',
                '_多次标记': False,
            })
            continue
        dates = dates_by_school[school_id]
        multiple = len(dates) > 1
        records.append({
            '校区ID': s['school_id'],
            '校区名称': s['school_name'],
            '操作日志ID': s['log_id'],
            '操作人': s['creator_name'],
            '代理类型': '交付中心',
            '交付期开始日期': school_start[school_id],
            '交付期结束日期': school_end[school_id],
            '最后标记交付中心日期（历史变更日期）': f"{s['created_at'].strftime('%Y-%m-%d %H:%M:%S')} ({', '.join(dates)})" if multiple else dates[0],
            '_多次标记': multiple,
        })
    return records


def export_to_excel(records):
    filename = f"校区记录-标记交付中心-{datetime.now().strftime('%Y%m%d')}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "标记交付中心"

    headers = ['校区ID', '校区名称', '操作日志ID', '操作人', '代理类型', '交付期开始日期', '交付期结束日期', '最后标记交付中心日期（历史变更日期）']
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col)
        cell.value = header
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.fill = header_fill
        cell.font = header_font

    for row_idx, r in enumerate(records, 2):
        for col_idx, key in enumerate(headers, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=r[key])
            cell.alignment = Alignment(horizontal='center')
        if r.get('_多次标记'):
            date_cell = ws.cell(row=row_idx, column=len(headers))
            date_cell.fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
        ws.cell(row=row_idx, column=len(headers)).alignment = Alignment(horizontal='left')

    ws.column_dimensions['A'].width = 10
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 14
    ws.column_dimensions['D'].width = 14
    ws.column_dimensions['E'].width = 14
    ws.column_dimensions['F'].width = 16
    ws.column_dimensions['G'].width = 16
    ws.column_dimensions['H'].width = 30

    wb.save(filename)
    print(f"导出成功: {filename}")
    print(f"共 {len(records)} 条记录")


if __name__ == '__main__':
    records = fetch_records(limit=None)
    export_to_excel(records)
