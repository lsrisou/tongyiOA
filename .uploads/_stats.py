import sys
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/workspace/.uploads')
import ssh

tz = ZoneInfo("Asia/Shanghai")
cur = ssh.conn.cursor()

cur.execute("SELECT @@global.time_zone, @@session.time_zone, NOW()")
print("DB时区:", cur.fetchone())

level_map = {30: '超级事业部', 60: '校区合伙人'}

checkpoints = [
    ("截止2025年年底", datetime(2025, 12, 31, 23, 59, 59, tzinfo=tz)),
    ("截止2026年6月底", datetime(2026, 6, 30, 23, 59, 59, tzinfo=tz)),
    ("截止2026年10月底", datetime(2026, 10, 31, 23, 59, 59, tzinfo=tz)),
]

print(f"{'时点':<18}{'超级事业部':>10}{'校区合伙人':>12}{'合计':>10}")
print("-" * 52)
for label, dt in checkpoints:
    ts = int(dt.timestamp())
    cur.execute("""
        SELECT level, COUNT(*) FROM deshengoa.de_schools
        WHERE company_id = 0 AND deleted_at IS NULL AND join_at <= %s
        GROUP BY level
    """, (ts,))
    counts = dict(cur.fetchall())
    a = counts.get(30, 0)
    b = counts.get(60, 0)
    other = {k: v for k, v in counts.items() if k not in (30, 60)}
    print(f"{label:<18}{a:>10}{b:>12}{a + b + sum(other.values()):>10}")
    if other:
        print("  其他level:", other)

# 各年度新增明细，辅助核对
print("\n=== 各年新增(未删除) ===")
cur.execute("""
    SELECT YEAR(FROM_UNIXTIME(join_at)) y, level, COUNT(*)
    FROM deshengoa.de_schools
    WHERE company_id = 0 AND deleted_at IS NULL
    GROUP BY y, level ORDER BY y, level
""")
for r in cur.fetchall():
    print(r)
