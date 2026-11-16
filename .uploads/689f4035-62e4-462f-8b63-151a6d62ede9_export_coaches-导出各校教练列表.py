import ssh
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

cursor = ssh.conn.cursor()

school_sql = """
    SELECT id, name
    FROM deshengoa.de_schools
    WHERE deleted_at IS NULL AND company_id = 0
    ORDER BY id ASC
"""
cursor.execute(school_sql)
columns = [desc[0] for desc in cursor.description]
schools = [dict(zip(columns, row)) for row in cursor.fetchall()]

wb = Workbook()
ws = wb.active
ws.title = '各校教练列表'

headers = ['学校ID', '学校名称', '教练ID', '教练姓名', '性别', '创建时间']
for col, header in enumerate(headers, 1):
    cell = ws.cell(row=1, column=col)
    cell.value = header
    cell.alignment = Alignment(horizontal='center', vertical='center')
    cell.font = Font(bold=True)

row_num = 2
for school in schools:
    sid = school['id']
    sname = school['name']

    coach_sql = """
        SELECT id, username, name, gender, created_at, role_id
        FROM deshengoa.de_admin_users
        WHERE role_id IN ('school_teacher', 'school_pre_teacher') AND school_id = %s AND deleted_at IS NULL
        ORDER BY FIELD(role_id, 'school_teacher', 'school_pre_teacher'), id ASC
    """
    cursor.execute(coach_sql, (sid,))
    columns = [desc[0] for desc in cursor.description]
    coaches = [dict(zip(columns, row)) for row in cursor.fetchall()]

    for coach in coaches:
        gender_str = '男' if coach['gender'] == 1 else '女' if coach['gender'] == 2 else ''
        created = str(coach['created_at']).split('.')[0] if coach['created_at'] else ''
        ws.cell(row=row_num, column=1, value=sid).alignment = Alignment(horizontal='center')
        ws.cell(row=row_num, column=2, value=sname).alignment = Alignment(horizontal='center')
        ws.cell(row=row_num, column=3, value=coach['id']).alignment = Alignment(horizontal='center')
        ws.cell(row=row_num, column=4, value=coach['name']).alignment = Alignment(horizontal='center')
        ws.cell(row=row_num, column=5, value=gender_str).alignment = Alignment(horizontal='center')
        ws.cell(row=row_num, column=6, value=created).alignment = Alignment(horizontal='center')
        row_num += 1

    print(f'学校 {sid} ({sname}): {len(coaches)} 名教练')

ws.column_dimensions['A'].width = 10
ws.column_dimensions['B'].width = 24
ws.column_dimensions['C'].width = 10
ws.column_dimensions['D'].width = 14
ws.column_dimensions['E'].width = 8
ws.column_dimensions['F'].width = 22

filename = '各校教练列表.xlsx'
wb.save(filename)
print(f'\n{filename} 导出成功，共 {row_num - 2} 名教练')

cursor.close()
ssh.conn.close()
