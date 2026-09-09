# -*- coding: utf-8 -*-
"""暑假(2026-07-15 ~ 2026-09-01)正式课统计 - HTML报告生成器"""
import datetime
from datetime import timezone, timedelta

# 服务器为UTC时区,报告需显示北京时间(Asia/Shanghai, UTC+8)
CN_TZ = timezone(timedelta(hours=8))
import html
import os
from sshdb import DBTunnel

# ---- 时间口径 ----
# 服务器为UTC时区,datetime 默认按UTC解释,需显式指定北京时间(UTC+8)
DATE_START = datetime.datetime(2026, 7, 15, 0, 0, 0, tzinfo=CN_TZ)
DATE_END = datetime.datetime(2026, 9, 1, 0, 0, 0, tzinfo=CN_TZ)
T_START = int(DATE_START.timestamp())
T_END = int(DATE_END.timestamp())

# 教练等级标签(按业务定义)
LEVEL_LABEL = {
    0: '助教', 10: '教练', 20: '银牌教练', 30: '金牌教练', 35: '白金教练',
    40: '王牌教练', 43: '钻石教练', 45: '初级专家', 50: '高级专家', 60: '特级专家',
}


def lvl_label(v):
    if v is None:
        return '未知等级'
    return LEVEL_LABEL.get(int(v), f'等级{int(v)}')


def fnum(x, dec=0):
    """数字格式化,千分位"""
    if x is None:
        return '-'
    f = float(x)
    s = f'{f:,.{dec}f}'
    return s


def fmoney(x):
    """分 -> 元,千分位,2位小数"""
    if x is None:
        return '-'
    return f'{float(x) / 100:,.2f}'


def esc(s):
    return html.escape(str(s) if s is not None else '')


def main():
    tunnel = DBTunnel()
    tunnel.connect()
    conn = tunnel.get_conn('deshengoa')
    cur = conn.cursor()

    # 基础过滤片段(统一使用别名 l.)
    # 口径: lesson_type=1(正式课) + deleted_at IS NULL(未软删除) + state=1(有效课,排除作废占位)
    # 说明: state=2 为排课后取消/作废的占位记录,全部 hour_count=0,会污染上课数,已排除
    # 已验证: state=1 内业务键(学生+老师+开始时间)完全唯一,无重复
    base = ("l.lesson_type=1 AND l.deleted_at IS NULL AND l.state=1 "
            "AND l.start_time>=%s AND l.start_time<%s" % (T_START, T_END))
    comp = base + " AND l.star_confirm=1"

    # ===== 1. 正式课 上课数 / 完课数 (按次数 & 课时) =====
    cur.execute(f"""
        SELECT COUNT(*), COALESCE(SUM(l.hour_count),0)
        FROM de_student_hour_lessons l WHERE {base}
    """)
    attend_cnt, attend_hours = cur.fetchone()

    cur.execute(f"""
        SELECT COUNT(*), COALESCE(SUM(l.hour_count),0)
        FROM de_student_hour_lessons l WHERE {comp}
    """)
    done_cnt, done_hours = cur.fetchone()
    done_rate_cnt = (float(done_cnt) / float(attend_cnt) * 100) if attend_cnt else 0
    done_rate_hr = (float(done_hours) / float(attend_hours) * 100) if attend_hours else 0

    # ===== 2. 完课数据统计 =====
    # 2a 各等级教练 排课占比 (排课=正式课全部)
    cur.execute(f"""
        SELECT COALESCE(tls.teach_level, -1) AS lvl,
               COUNT(*) AS lessons, COALESCE(SUM(l.hour_count),0) AS hours
        FROM de_student_hour_lessons l
        LEFT JOIN de_teacher_level_statuses tls ON tls.id = l.teacher_id
        WHERE {base}
        GROUP BY tls.teach_level
        ORDER BY lessons DESC
    """)
    level_rows = cur.fetchall()
    level_total_lessons = sum(r[1] for r in level_rows) or 1
    level_total_hours = sum(float(r[2]) for r in level_rows) or 1

    # 2b 好评率 (完课中)
    cur.execute(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN l.star>0 THEN 1 ELSE 0 END) AS rated,
               SUM(CASE WHEN l.star=5 THEN 1 ELSE 0 END) AS star5,
               SUM(CASE WHEN l.star=3 THEN 1 ELSE 0 END) AS star3,
               SUM(CASE WHEN l.star=1 THEN 1 ELSE 0 END) AS star1
        FROM de_student_hour_lessons l WHERE {comp}
    """)
    rr = cur.fetchone()
    rate_total, rated, star5, star3, star1 = rr
    praise_rate = (float(star5) / float(rated) * 100) if rated else 0

    # 2c 课时费 & 总部收入 (完课)
    # 总部收入 = 总部教练课时抽成,来自 de_top_point_logs.amount(type_id=4),按 hour_lesson_id 关联
    cur.execute(f"""
        SELECT COALESCE(SUM(l.teacher_point),0) AS teacher_fee,
               COALESCE(SUM(t.amount),0) AS hq_income,
               COALESCE(SUM(l.hour_count),0) AS hours,
               COUNT(DISTINCT l.id) AS cnt
        FROM de_student_hour_lessons l
        LEFT JOIN de_top_point_logs t ON t.hour_lesson_id = l.id AND t.type_id = 4
        WHERE {comp}
    """)
    fr = cur.fetchone()
    teacher_fee, hq_income, fee_hours, fee_cnt = fr
    fee_per_hour = (float(teacher_fee) / float(fee_hours)) if fee_hours else 0  # 分/课时
    hq_per_hour = (float(hq_income) / float(fee_hours)) if fee_hours else 0

    # ===== 3. 交付中心排行 (按完课课时) =====
    cur.execute(f"""
        SELECT COALESCE(s.name, CONCAT('未知中心#', l.teach_school_id)) AS name,
               COUNT(*) AS lessons,
               COALESCE(SUM(l.hour_count),0) AS hours,
               COALESCE(SUM(l.teacher_point),0) AS tfee,
               SUM(CASE WHEN l.star=5 THEN 1 ELSE 0 END) AS s5,
               SUM(CASE WHEN l.star>0 THEN 1 ELSE 0 END) AS sr
        FROM de_student_hour_lessons l
        LEFT JOIN de_schools s ON s.id = l.teach_school_id AND s.deleted_at IS NULL
        WHERE {comp}
        GROUP BY l.teach_school_id, s.name
        ORDER BY hours DESC
    """)
    center_rows = cur.fetchall()
    center_total_hours = sum(float(r[2]) for r in center_rows) or 1

    cur.close()
    conn.close()
    tunnel.close()

    # ============ 渲染 HTML ============
    gen_time = datetime.datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')

    # 概览卡片
    cards = [
        ('正式课上课数', fnum(attend_cnt), '节', '#2563eb'),
        ('正式课上课课时', fnum(attend_hours, 2), '课时', '#2563eb'),
        ('完课数', fnum(done_cnt), '节', '#16a34a'),
        ('完课课时', fnum(done_hours, 2), '课时', '#16a34a'),
        ('完课率(按次数)', f'{done_rate_cnt:.1f}', '%', '#9333ea'),
        ('完课率(按课时)', f'{done_rate_hr:.1f}', '%', '#9333ea'),
    ]

    # 各等级教练 排课占比 行
    lvl_trs = ''
    max_lvl_lessons = max((r[1] for r in level_rows), default=1)
    for lvl, lessons, hours in level_rows:
        lab = lvl_label(-1 if lvl == -1 else lvl)
        pct_l = float(lessons) / level_total_lessons * 100
        pct_h = float(hours) / level_total_hours * 100
        bar_w = lessons / max_lvl_lessons * 100
        lvl_trs += f"""
        <tr>
          <td class="lbl">{esc(lab)}</td>
          <td>{fnum(lessons)}</td>
          <td>{fnum(hours,2)}</td>
          <td>{pct_l:.1f}%</td>
          <td>{pct_h:.1f}%</td>
          <td class="bar-cell"><div class="bar" style="width:{bar_w:.1f}%"></div></td>
        </tr>"""

    # 交付中心排行 行
    ctr_trs = ''
    max_ctr_hours = max((float(r[2]) for r in center_rows), default=1)
    for name, lessons, hours, tfee, s5, sr in center_rows:
        hpct = float(hours) / center_total_hours * 100
        pr = (float(s5) / float(sr) * 100) if sr else 0
        bar_w = float(hours) / max_ctr_hours * 100
        ctr_trs += f"""
        <tr>
          <td class="lbl">{esc(name)}</td>
          <td>{fnum(lessons)}</td>
          <td class="num-strong">{fnum(hours,2)}</td>
          <td>{hpct:.1f}%</td>
          <td>{fmoney(tfee)}</td>
          <td>{pr:.1f}%</td>
          <td class="bar-cell"><div class="bar bar-g" style="width:{bar_w:.1f}%"></div></td>
        </tr>"""

    praise_cards = f"""
        <div class="mini-card"><div class="mini-label">完课总数</div><div class="mini-val">{fnum(rate_total)}</div></div>
        <div class="mini-card"><div class="mini-label">已评价数</div><div class="mini-val">{fnum(rated)}</div></div>
        <div class="mini-card hl"><div class="mini-label">好评数(star=5)</div><div class="mini-val">{fnum(star5)}</div></div>
        <div class="mini-card"><div class="mini-label">中评数(star=3)</div><div class="mini-val">{fnum(star3)}</div></div>
        <div class="mini-card"><div class="mini-label">差评数(star=1)</div><div class="mini-val">{fnum(star1)}</div></div>
        <div class="mini-card hl2"><div class="mini-label">好评率</div><div class="mini-val">{praise_rate:.1f}%</div></div>"""

    fee_cards = f"""
        <div class="mini-card hl"><div class="mini-label">课时费总额(教师)</div><div class="mini-val">{fmoney(teacher_fee)}<span class="unit">元</span></div></div>
        <div class="mini-card"><div class="mini-label">平均课时费</div><div class="mini-val">{fee_per_hour/100:,.2f}<span class="unit">元/课时</span></div></div>
        <div class="mini-card hl2"><div class="mini-label">总部/平台收入</div><div class="mini-val">{fmoney(hq_income)}<span class="unit">元</span></div></div>
        <div class="mini-card"><div class="mini-label">平均总部收入</div><div class="mini-val">{hq_per_hour/100:,.2f}<span class="unit">元/课时</span></div></div>"""

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>暑假正式课统计报告 ({DATE_START:%Y-%m-%d} ~ {DATE_END:%Y-%m-%d})</title>
<style>
  :root{{--bg:#f5f7fa;--card:#fff;--ink:#1f2937;--mut:#6b7280;--bd:#e5e7eb;
          --pri:#2563eb;--grn:#16a34a;--prp:#9333ea;--amber:#d97706;}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
       background:var(--bg);color:var(--ink);line-height:1.5;padding:24px;}}
  .wrap{{max-width:1180px;margin:0 auto;}}
  .head{{background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;padding:28px 32px;border-radius:14px;
        box-shadow:0 6px 20px rgba(37,99,235,.18);margin-bottom:22px;}}
  .head h1{{font-size:24px;font-weight:700;}}
  .head .sub{{margin-top:8px;opacity:.92;font-size:14px;}}
  .head .meta{{margin-top:10px;font-size:12px;opacity:.8;}}
  section{{background:var(--card);border-radius:12px;padding:22px 26px;margin-bottom:22px;
           box-shadow:0 1px 3px rgba(0,0,0,.05);border:1px solid var(--bd);}}
  h2{{font-size:18px;font-weight:700;margin-bottom:14px;padding-bottom:10px;border-bottom:2px solid var(--bd);
      display:flex;align-items:center;gap:8px;}}
  h2 .n{{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:8px;
         background:var(--pri);color:#fff;font-size:14px;}}
  .cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}}
  .card{{border-radius:10px;padding:18px 20px;color:#fff;box-shadow:0 4px 12px rgba(0,0,0,.08);}}
  .card .t{{font-size:13px;opacity:.95;}}
  .card .v{{font-size:30px;font-weight:800;margin-top:6px;letter-spacing:.5px;}}
  .card .u{{font-size:14px;font-weight:600;margin-left:4px;opacity:.9;}}
  .mini-row{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;}}
  .mini-card{{background:#f9fafb;border:1px solid var(--bd);border-radius:10px;padding:14px 12px;text-align:center;}}
  .mini-card.hl{{background:#ecfdf5;border-color:#a7f3d0;}}
  .mini-card.hl2{{background:#eff6ff;border-color:#bfdbfe;}}
  .mini-label{{font-size:12px;color:var(--mut);}}
  .mini-val{{font-size:22px;font-weight:700;margin-top:4px;}}
  .mini-val .unit{{font-size:12px;font-weight:600;color:var(--mut);margin-left:3px;}}
  table{{width:100%;border-collapse:collapse;font-size:14px;margin-top:6px;}}
  th,td{{padding:10px 12px;text-align:right;border-bottom:1px solid var(--bd);}}
  th{{background:#f3f4f6;font-weight:600;color:#374151;font-size:13px;}}
  th:first-child,td:first-child{{text-align:left;}}
  td.lbl{{font-weight:600;color:#1f2937;}}
  td.num-strong{{font-weight:700;color:var(--pri);}}
  tr:hover td{{background:#fafbfc;}}
  .bar-cell{{width:30%;}}
  .bar{{height:14px;background:linear-gradient(90deg,#60a5fa,#2563eb);border-radius:7px;min-width:2px;}}
  .bar-g{{background:linear-gradient(90deg,#86efac,#16a34a);}}
  .note{{margin-top:16px;padding:12px 16px;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;
         font-size:12px;color:#92400e;line-height:1.7;}}
  .note b{{color:#78350f;}}
  .tag{{display:inline-block;background:#e0e7ff;color:#3730a3;font-size:11px;font-weight:600;
        padding:2px 8px;border-radius:6px;margin-left:8px;}}
  .rank{{display:inline-block;width:22px;height:22px;border-radius:50%;text-align:center;line-height:22px;
         font-size:12px;font-weight:700;color:#fff;background:#9ca3af;}}
  .rank.r1{{background:#f59e0b;}}.rank.r2{{background:#9ca3af;}}.rank.r3{{background:#b45309;}}
  @media(max-width:760px){{.cards{{grid-template-columns:repeat(2,1fr);}}.mini-row{{grid-template-columns:repeat(3,1fr);}}}}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <h1>暑假正式课统计报告</h1>
    <div class="sub">统计区间：{DATE_START:%Y年%m月%d日} — {DATE_END:%Y年%m月%d日} （有效正式课 {fnum(attend_cnt)} 节）</div>
    <div class="meta">报告生成时间：{gen_time}</div>
  </div>

  <section>
    <h2><span class="n">1</span>正式课 上课数 / 完课数</h2>
    <div class="cards">
      <div class="card" style="background:linear-gradient(135deg,#1e40af,#3b82f6)">
        <div class="t">上课数（按次数）</div><div class="v">{fnum(attend_cnt)}<span class="u">节</span></div></div>
      <div class="card" style="background:linear-gradient(135deg,#1d4ed8,#2563eb)">
        <div class="t">上课数（按课时）</div><div class="v">{fnum(attend_hours,2)}<span class="u">课时</span></div></div>
      <div class="card" style="background:linear-gradient(135deg,#15803d,#22c55e)">
        <div class="t">完课数（按次数）</div><div class="v">{fnum(done_cnt)}<span class="u">节</span></div></div>
      <div class="card" style="background:linear-gradient(135deg,#166534,#16a34a)">
        <div class="t">完课数（按课时）</div><div class="v">{fnum(done_hours,2)}<span class="u">课时</span></div></div>
      <div class="card" style="background:linear-gradient(135deg,#6d28d9,#9333ea)">
        <div class="t">完课率（按次数）</div><div class="v">{done_rate_cnt:.1f}<span class="u">%</span></div></div>
      <div class="card" style="background:linear-gradient(135deg,#7c3aed,#a855f7)">
        <div class="t">完课率（按课时）</div><div class="v">{done_rate_hr:.1f}<span class="u">%</span></div></div>
    </div>
  </section>

  <section>
    <h2><span class="n">2</span>完课数据统计</h2>

    <h3 style="margin:14px 0 10px;font-size:15px;color:#374151;">2.1 各等级教练排课占比</h3>
    <table>
      <thead><tr><th>教练等级</th><th>排课次数</th><th>排课课时</th><th>次数占比</th><th>课时占比</th><th>次数分布</th></tr></thead>
      <tbody>{lvl_trs}</tbody>
    </table>

    <h3 style="margin:24px 0 10px;font-size:15px;color:#374151;">2.2 好评率</h3>
    <div class="mini-row">{praise_cards}</div>

    <h3 style="margin:24px 0 10px;font-size:15px;color:#374151;">2.3 课时费 & 总部收入</h3>
    <div class="mini-row" style="grid-template-columns:repeat(4,1fr);">{fee_cards}</div>
  </section>

  <section>
    <h2><span class="n">3</span>交付中心课时排行</h2>
    <table>
      <thead><tr><th>排名</th><th>交付中心</th><th>完课数</th><th>完课课时</th><th>课时占比</th><th>课时费(元)</th><th>好评率</th><th>课时分布</th></tr></thead>
      <tbody>"""
    # 注入排名
    ctr_body = ''
    for i, (name, lessons, hours, tfee, s5, sr) in enumerate(center_rows, 1):
        hpct = float(hours) / center_total_hours * 100
        pr = (float(s5) / float(sr) * 100) if sr else 0
        bar_w = float(hours) / max_ctr_hours * 100
        rk = f'<span class="rank r{i}">{i}</span>' if i <= 3 else f'<span class="rank">{i}</span>'
        ctr_body += f"""
        <tr>
          <td style="text-align:center">{rk}</td>
          <td class="lbl">{esc(name)}</td>
          <td>{fnum(lessons)}</td>
          <td class="num-strong">{fnum(hours,2)}</td>
          <td>{hpct:.1f}%</td>
          <td>{fmoney(tfee)}</td>
          <td>{pr:.1f}%</td>
          <td class="bar-cell"><div class="bar bar-g" style="width:{bar_w:.1f}%"></div></td>
        </tr>"""
    html_doc += ctr_body + f"""</tbody>
    </table>
  </section>

  <div style="text-align:center;color:#9ca3af;font-size:12px;padding:8px 0 20px;">
    本报告由数据统计脚本自动生成 · {gen_time}
  </div>
</div>
</body>
</html>"""

    out_path = '/workspace/public/summer_stats_2026.html'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html_doc)
    print(f"HTML已生成: {out_path}")
    print(f"概览: 上课{attend_cnt}节/{fnum(attend_hours,2)}课时, 完课{done_cnt}节/{fnum(done_hours,2)}课时, 好评率{praise_rate:.1f}%")
    print(f"课时费{fmoney(teacher_fee)}元, 总部收入{fmoney(hq_income)}元")
    print(f"交付中心数: {len(center_rows)}")


if __name__ == '__main__':
    main()
