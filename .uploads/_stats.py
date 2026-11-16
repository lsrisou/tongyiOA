import sys
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/workspace/.uploads')
import ssh

tz = ZoneInfo("Asia/Shanghai")
cur = ssh.conn.cursor()

checkpoints = [
    ("截止2025年年底", datetime(2025, 12, 31, 23, 59, 59, tzinfo=tz)),
    ("截止2026年6月底", datetime(2026, 6, 30, 23, 59, 59, tzinfo=tz)),
    ("截止2026年10月底", datetime(2026, 10, 31, 23, 59, 59, tzinfo=tz)),
]

def query(ts, only_deleted=None):
    sql = """
        SELECT level, COUNT(*) FROM deshengoa.de_schools
        WHERE company_id = 0 AND join_at <= %s
    """
    if only_deleted is True:
        sql += " AND deleted_at IS NOT NULL"
    elif only_deleted is False:
        sql += " AND deleted_at IS NULL"
    sql += " GROUP BY level"
    cur.execute(sql, (ts,))
    return dict(cur.fetchall())

for label, dt in checkpoints:
    ts = int(dt.timestamp())
    live = query(ts, False)
    dead = query(ts, True)
    all_ = query(ts, None)
    print(f"\n=== {label} ===")
    print(f"{'状态':<10}{'超级事业部(30)':>16}{'校区合伙人(60)':>16}{'合计':>10}")
    for name, d in (("未删除", live), ("已删除", dead), ("总计", all_)):
        a, b = d.get(30, 0), d.get(60, 0)
        other = {k: v for k, v in d.items() if k not in (30, 60)}
        total = sum(d.values())
        extra = f"  其他level={other}" if other else ""
        print(f"{name:<10}{a:>16}{b:>16}{total:>10}{extra}")

print("\n=== 各年新增(含已删除) ===")
cur.execute("""
    SELECT YEAR(FROM_UNIXTIME(join_at)) y,
           SUM(deleted_at IS NULL) live,
           SUM(deleted_at IS NOT NULL) dead,
           COUNT(*) total
    FROM deshengoa.de_schools
    WHERE company_id = 0
    GROUP BY y ORDER BY y
""")
print(f"{'年份':<8}{'未删除':>10}{'已删除':>10}{'合计':>10}")
for y, live, dead, total in cur.fetchall():
    print(f"{str(y):<8}{live or 0:>10}{dead or 0:>10}{total:>10}")
