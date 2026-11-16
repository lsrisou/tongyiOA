import sys
sys.path.insert(0, '/workspace/.uploads')
import ssh

cur = ssh.conn.cursor()

print("=== type_id 分布(未删除) ===")
cur.execute("""
    SELECT type_id, level, COUNT(*) FROM deshengoa.de_schools
    WHERE company_id = 0 AND deleted_at IS NULL
    GROUP BY type_id, level ORDER BY type_id, level
""")
for r in cur.fetchall():
    print(r)

print("\n=== 每年 join_at 数量(未删除) ===")
cur.execute("""
    SELECT YEAR(FROM_UNIXTIME(join_at)) y, COUNT(*) FROM deshengoa.de_schools
    WHERE company_id = 0 AND deleted_at IS NULL GROUP BY y ORDER BY y
""")
for r in cur.fetchall():
    print(r)

print("\n=== 是否有字典/类型表 ===")
cur.execute("SHOW TABLES LIKE '%type%'")
for r in cur.fetchall():
    print(r)
cur.execute("SHOW TABLES LIKE '%level%'")
for r in cur.fetchall():
    print(r)
