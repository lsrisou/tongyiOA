import ssh
import os
import webbrowser
from datetime import datetime, timedelta


def build_html(school_stats, school_names_order):
    css = """
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      body { font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
             background: #f0f2f5; color: #333; padding: 30px; }
      .container { max-width: 1400px; margin: 0 auto; }
      h1 { text-align: center; font-size: 28px; color: #1a1a2e; margin-bottom: 8px; }
      .subtitle { text-align: center; color: #888; font-size: 14px; margin-bottom: 30px; }
      .card { background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.08);
              padding: 24px; margin-bottom: 24px; }
      .card h2 { font-size: 18px; color: #1a1a2e; margin-bottom: 16px;
                 padding-bottom: 10px; border-bottom: 2px solid #e8e8e8; }
      table { width: 100%; border-collapse: collapse; font-size: 14px; }
      th { background: #f8f9ff; padding: 10px 12px; text-align: center; font-weight: 600; color: #555; }
      td { padding: 8px 12px; text-align: center; border-bottom: 1px solid #f0f0f0; }
      tr:hover td { background: #fafbff; }
      .tag { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px; font-weight: 600; white-space: nowrap; }
      .tag-ok { background: #e6f7ec; color: #1a7d3a; }
      .tag-warn { background: #fff7e6; color: #b8860b; }
      .tag-cancel { background: #fff0f0; color: #c0392b; }
      .tag-info { background: #e6f0ff; color: #2c5f8a; }
      .tag-muted { background: #f5f5f5; color: #999; }
      .tag-primary { background: #e6f0ff; color: #4a6cf7; }
      .school-header { font-size: 16px; font-weight: 700; color: #1a1a2e; }
      .stat-num { font-size: 22px; font-weight: 700; color: #4a6cf7; }
      .stat-label { font-size: 12px; color: #888; }
      .stat-box { display: inline-block; margin: 0 18px; text-align: center; }
      .overview-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 24px; }
      .overview-item { background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.08); padding: 20px; text-align: center; }
      .overview-item h3 { font-size: 16px; color: #1a1a2e; margin-bottom: 12px; }
      .overview-item .num { font-size: 32px; font-weight: 700; color: #4a6cf7; }
      .overview-item .label { font-size: 13px; color: #888; margin-top: 4px; }
      .pct-bar { height: 10px; border-radius: 5px; background: #e8e8e8; overflow: hidden; margin-top: 4px; }
      .pct-bar .fill { height: 100%; border-radius: 5px; background: linear-gradient(90deg, #4a6cf7, #6c8cff); }
      .channel { font-size: 12px; font-weight: 600; color: #888; }
      .channel-online { color: #4a6cf7; }
      .channel-offline { color: #e67e22; }
      .summary-table th { background: #4a6cf7; color: #fff; }
      .summary-table td { font-size: 14px; }
      .summary-table tr:hover td { background: #f0f4ff; }
      .school-card { background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.08);
                     padding: 24px; margin-bottom: 24px; }
      .school-card h2 { font-size: 18px; color: #1a1a2e; margin-bottom: 16px;
                        padding-bottom: 10px; border-bottom: 2px solid #e8e8e8; display: flex; align-items: center; gap: 12px; }
      .school-card h2 .badge { background: #4a6cf7; color: #fff; padding: 2px 10px; border-radius: 10px; font-size: 13px; }
      .metrics { display: flex; gap: 30px; margin-bottom: 20px; flex-wrap: wrap; }
      .metric { text-align: center; }
      .metric .num { font-size: 28px; font-weight: 700; color: #4a6cf7; }
      .metric .label { font-size: 12px; color: #888; margin-top: 2px; }
    </style>
    """

    status_tags = {
        '未支付（新申请）': 'tag-cancel',
        '已支付（新申请未接待）': 'tag-warn',
        '已支付（待排课）': 'tag-info',
        '已支付（进行中）': 'tag-info',
        '已支付（待结算）': 'tag-warn',
        '已支付（已完课：待转化）': 'tag-info',
        '已支付（已完课：已转化）': 'tag-ok',
        '已支付（已完课：不转化）': 'tag-muted',
        '已退课': 'tag-cancel',
        '线下已支付（新申请未接待）': 'tag-warn',
        '线下已支付（待排课）': 'tag-info',
        '线下已支付（进行中）': 'tag-info',
        '线下已支付（待结算）': 'tag-warn',
        '线下已支付（已完课：待转化）': 'tag-info',
        '线下已支付（已完课：已转化）': 'tag-ok',
        '线下已支付（已完课：不转化）': 'tag-muted',
        '已退课（线下）': 'tag-cancel',
    }

    def channel_label(ch):
        if ch == '在线':
            return '<span class="channel channel-online">● 在线</span>'
        return '<span class="channel channel-offline">● 线下</span>'

    def make_status_rows(status_list):
        if not status_list:
            return '<tr><td colspan="5" style="color:#999;">暂无数据</td></tr>'
        max_cnt = max((r['cnt'] for r in status_list), default=1)
        if max_cnt == 0:
            max_cnt = 1
        out = ''
        for r in status_list:
            bar_w = r['cnt'] / max_cnt * 100
            amount_yuan = r['total_point'] / 100
            tag_cls = status_tags.get(r['label'], 'tag-muted')
            out += f'<tr><td><span class="tag {tag_cls}">{r["label"]}</span></td><td>{r["cnt"]:,}</td><td>{r["pct"]}</td><td>{amount_yuan:,.2f}</td><td><div class="pct-bar"><div class="fill" style="width:{bar_w:.1f}%"></div></div></td></tr>\n'
        return out

    # Overview summary table
    summary_rows = ''
    total_trial = 0
    total_contract = 0
    for name in school_names_order:
        s = school_stats[name]
        trial_total = s['trial_total']
        contract_count = s['contract_student_count']
        total_trial += trial_total
        total_contract += contract_count
        summary_rows += f'''<tr>
            <td class="school-header">{name}（{s['id']}）</td>
            <td><span class="stat-num">{trial_total}</span></td>
            <td><span class="stat-num" style="color:#c0392b;">{s['unpaid']}</span></td>
            <td><span class="stat-num" style="color:#b8860b;">{s['paid_new']}</span></td>
            <td><span class="stat-num" style="color:#2c5f8a;">{s['paid_schedule']}</span></td>
            <td><span class="stat-num" style="color:#2c5f8a;">{s['paid_ongoing']}</span></td>
            <td><span class="stat-num" style="color:#b8860b;">{s['paid_settle']}</span></td>
            <td><span class="stat-num" style="color:#2c5f8a;">{s['paid_done_convert']}</span></td>
            <td><span class="stat-num" style="color:#1a7d3a;">{s['paid_done_converted']}</span></td>
            <td><span class="stat-num" style="color:#999;">{s['paid_done_no_convert']}</span></td>
            <td><span class="stat-num" style="color:#c0392b;">{s['trial_refunded']}</span></td>
            <td><span class="stat-num">{contract_count}</span></td>
        </tr>'''

    # Detail cards per school
    detail_cards = ''
    for name in school_names_order:
        s = school_stats[name]
        all_status = s['online_status'] + s['offline_status']
        total_amount = sum(r['total_point'] for r in all_status) / 100

        detail_cards += f'''
    <div class="school-card">
      <h2><span class="badge">🏫</span> {name}（{s['id']}）</h2>
      <div class="metrics">
        <div class="metric"><div class="num">{s['trial_total']}</div><div class="label">体验课总数</div></div>
        <div class="metric"><div class="num" style="color:#e67e22;">{s['trial_paid']}</div><div class="label">已支付</div></div>
        <div class="metric"><div class="num" style="color:#1a7d3a;">{s['trial_converted']}</div><div class="label">已转化</div></div>
        <div class="metric"><div class="num" style="color:#c0392b;">{s['trial_refunded']}</div><div class="label">已退课</div></div>
        <div class="metric"><div class="num" style="color:#b8860b;">{total_amount:,.2f}</div><div class="label">体验课总金额（元）</div></div>
        <div class="metric"><div class="num" style="color:#4a6cf7;">{s['contract_student_count']}</div><div class="label">正价课学生人数</div></div>
      </div>
      <table>
        <thead><tr><th>渠道</th><th>状态</th><th>数量</th><th>占比</th><th>金额（元）</th><th>分布</th></tr></thead>
        <tbody>
          {make_status_rows(s['online_status'])}
          {make_status_rows(s['offline_status'])}
        </tbody>
      </table>
    </div>'''

    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    one_month_ago = (now - timedelta(days=30)).strftime('%Y-%m-%d')
    today = now.strftime('%Y-%m-%d')
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>学校体验课与正价课统计</title>{css}</head>
<body>
<div class="container">
  <h1>📊 学校体验课与正价课统计</h1>
  <p class="subtitle">生成时间：{now_str} ｜ 学校数：{len(school_names_order)}</p>

  <div class="card">
    <h2>📋 总览</h2>
    <table class="summary-table">
      <thead><tr><th>学校名称</th><th>体验课总数</th><th>未支付（新申请）</th><th>已支付（新申请未接待）</th><th>已支付（待排课）</th><th>已支付（进行中）</th><th>已支付（待结算）</th><th>已支付（已完课：待转化）</th><th>已支付（已完课：已转化）</th><th>已支付（已完课：不转化）</th><th>已退课</th><th>正价课学生数</th></tr></thead>
      <tbody>
        {summary_rows}
        <tr style="font-weight:700;background:#f8f9ff;">
          <td>合计</td>
          <td>{total_trial}</td>
          <td style="color:#c0392b;">{sum(s['unpaid'] for s in school_stats.values())}</td>
          <td style="color:#b8860b;">{sum(s['paid_new'] for s in school_stats.values())}</td>
          <td style="color:#2c5f8a;">{sum(s['paid_schedule'] for s in school_stats.values())}</td>
          <td style="color:#2c5f8a;">{sum(s['paid_ongoing'] for s in school_stats.values())}</td>
          <td style="color:#b8860b;">{sum(s['paid_settle'] for s in school_stats.values())}</td>
          <td style="color:#2c5f8a;">{sum(s['paid_done_convert'] for s in school_stats.values())}</td>
          <td style="color:#1a7d3a;">{sum(s['paid_done_converted'] for s in school_stats.values())}</td>
          <td style="color:#999;">{sum(s['paid_done_no_convert'] for s in school_stats.values())}</td>
          <td style="color:#c0392b;">{sum(s['trial_refunded'] for s in school_stats.values())}</td>
          <td style="color:#4a6cf7;">{total_contract}</td>
        </tr>
      </tbody>
    </table>
    <p style="margin-top:12px;color:#888;font-size:13px;">📅 统计时间段：<strong>{one_month_ago}</strong> 至 <strong>{today}</strong>（最近30天）</p>
  </div>

  {detail_cards}

  <p style="text-align:center;color:#aaa;font-size:12px;padding:20px 0;">学校体验课与正价课统计 · de_trial_hour_lessons · de_student_lesson_contracts</p>
</div>
</body>
</html>"""
    return html


def main():
    cursor = ssh.conn.cursor()

    school_names = ['任忠侠', '王永鹏', '张小波', '殷海强', '宁静', '罗莹']

    placeholders = ','.join(['%s'] * len(school_names))
    cursor.execute(f"SELECT id, name FROM deshengoa.de_schools WHERE name IN ({placeholders})", school_names)
    schools = cursor.fetchall()
    school_id_map = {}
    for sid, sname in schools:
        school_id_map[sname] = sid

    print(f'找到学校: {list(school_id_map.keys())}')

    school_stats = {}
    for name in school_names:
        if name not in school_id_map:
            print(f'  ⚠ 未找到学校: {name}')
            continue

        sid = school_id_map[name]
        stats = {
            'id': sid,
            'trial_total': 0,
            'trial_paid': 0,
            'trial_converted': 0,
            'trial_refunded': 0,
            'online_status': [],
            'offline_status': [],
            'contract_student_count': 0,
            'paid_new': 0,
            'paid_schedule': 0,
            'paid_ongoing': 0,
            'paid_settle': 0,
            'paid_done_convert': 0,
            'paid_done_converted': 0,
            'paid_done_no_convert': 0,
            'unpaid': 0,
        }

        # 查询体验课状态分布（最近1个月，在线渠道）
        cursor.execute(f'''
            SELECT
              CASE
                WHEN pay_state = 0 AND state = 6 THEN '未支付（新申请）'
                WHEN pay_state = 1 AND state = 6 THEN '已支付（新申请未接待）'
                WHEN pay_state = 1 AND state = 3 THEN '已支付（待排课）'
                WHEN pay_state = 1 AND state = 1 AND start_time >= UNIX_TIMESTAMP(NOW()) THEN '已支付（进行中）'
                WHEN pay_state = 1 AND state = 1 AND end_time < UNIX_TIMESTAMP(NOW()) THEN '已支付（待结算）'
                WHEN pay_state = 1 AND state = 4 AND student_id = 0 THEN '已支付（已完课：待转化）'
                WHEN pay_state = 1 AND state = 4 AND student_id > 0 THEN '已支付（已完课：已转化）'
                WHEN pay_state = 1 AND state = 5 THEN '已支付（已完课：不转化）'
                WHEN pay_state IN (0, 1, 3) AND state = 2 THEN '已退课'
              END AS label,
              COUNT(*) AS cnt,
              COALESCE(SUM(pay_point), 0) AS total_point
            FROM deshengoa.de_trial_hour_lessons
            WHERE pay_state IN (0, 1, 3) AND school_id = %s
              AND created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
            GROUP BY label
            HAVING label IS NOT NULL
            ORDER BY FIELD(label,
              '未支付（新申请）',
              '已支付（新申请未接待）',
              '已支付（待排课）',
              '已支付（进行中）',
              '已支付（待结算）',
              '已支付（已完课：待转化）',
              '已支付（已完课：已转化）',
              '已支付（已完课：不转化）',
              '已退课')
        ''', (sid,))
        rows = cursor.fetchall()
        subtotal = sum(r[1] for r in rows)
        stats['trial_total'] += subtotal

        for r in rows:
            label = r[0]
            cnt = r[1]
            total_point = int(r[2])
            pct = f'{cnt / subtotal * 100:.1f}%' if subtotal > 0 else '0%'
            stats['online_status'].append({
                'label': label,
                'cnt': cnt,
                'pct': pct,
                'total_point': total_point,
            })
            if '已支付' in label and '已转化' in label:
                stats['trial_converted'] += cnt
                stats['paid_done_converted'] += cnt
            elif '已退课' in label:
                stats['trial_refunded'] += cnt
            elif label == '未支付（新申请）':
                stats['unpaid'] += cnt
            else:
                stats['trial_paid'] += cnt
                if '新申请未接待' in label:
                    stats['paid_new'] += cnt
                elif '待排课' in label:
                    stats['paid_schedule'] += cnt
                elif '进行中' in label:
                    stats['paid_ongoing'] += cnt
                elif '待结算' in label:
                    stats['paid_settle'] += cnt
                elif '已完课：待转化' in label:
                    stats['paid_done_convert'] += cnt
                elif '已完课：不转化' in label:
                    stats['paid_done_no_convert'] += cnt

        # 查询体验课状态分布（最近1个月，线下渠道）
        cursor.execute(f'''
            SELECT
              CASE
                WHEN state = 6 THEN '线下已支付（新申请未接待）'
                WHEN state = 3 THEN '线下已支付（待排课）'
                WHEN state = 1 AND start_time >= UNIX_TIMESTAMP(NOW()) THEN '线下已支付（进行中）'
                WHEN state = 1 AND end_time < UNIX_TIMESTAMP(NOW()) THEN '线下已支付（待结算）'
                WHEN state = 4 AND student_id = 0 THEN '线下已支付（已完课：待转化）'
                WHEN state = 4 AND student_id > 0 THEN '线下已支付（已完课：已转化）'
                WHEN state = 5 THEN '线下已支付（已完课：不转化）'
                WHEN state = 2 THEN '已退课（线下）'
              END AS label,
              COUNT(*) AS cnt,
              COALESCE(SUM(pay_point), 0) AS total_point
            FROM deshengoa.de_trial_hour_lessons
            WHERE pay_state = 2 AND school_id = %s
              AND created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
            GROUP BY label
            HAVING label IS NOT NULL
            ORDER BY FIELD(label,
              '线下已支付（新申请未接待）',
              '线下已支付（待排课）',
              '线下已支付（进行中）',
              '线下已支付（待结算）',
              '线下已支付（已完课：待转化）',
              '线下已支付（已完课：已转化）',
              '线下已支付（已完课：不转化）',
              '已退课（线下）')
        ''', (sid,))
        rows = cursor.fetchall()
        subtotal_offline = sum(r[1] for r in rows)
        stats['trial_total'] += subtotal_offline

        for r in rows:
            label = r[0]
            cnt = r[1]
            total_point = int(r[2])
            pct = f'{cnt / subtotal_offline * 100:.1f}%' if subtotal_offline > 0 else '0%'
            stats['offline_status'].append({
                'label': label,
                'cnt': cnt,
                'pct': pct,
                'total_point': total_point,
            })
            if '已转化' in label:
                stats['trial_converted'] += cnt
                stats['paid_done_converted'] += cnt
            elif '已退课' in label:
                stats['trial_refunded'] += cnt
            else:
                stats['trial_paid'] += cnt
                if '新申请未接待' in label:
                    stats['paid_new'] += cnt
                elif '待排课' in label:
                    stats['paid_schedule'] += cnt
                elif '进行中' in label:
                    stats['paid_ongoing'] += cnt
                elif '待结算' in label:
                    stats['paid_settle'] += cnt
                elif '已完课：待转化' in label:
                    stats['paid_done_convert'] += cnt
                elif '已完课：不转化' in label:
                    stats['paid_done_no_convert'] += cnt

        # 查询正价课学生人数（最近1个月）
        cursor.execute(f'''
            SELECT COUNT(DISTINCT student_id)
            FROM deshengoa.de_student_lesson_contracts
            WHERE school_id = %s
              AND created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
        ''', (sid,))
        contract_count = cursor.fetchone()[0]
        stats['contract_student_count'] = contract_count

        print(f'  ✅ {name}: 体验课 {stats["trial_total"]} 条, 正价课学生 {contract_count} 人')
        school_stats[name] = stats

    cursor.close()
    ssh.conn.close()

    found_names = [name for name in school_names if name in school_stats]
    html = build_html(school_stats, found_names)

    out_path = os.path.join(os.path.dirname(__file__), '学校体验课与正价课统计.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'\nHTML 已生成：{out_path}')

    chrome_paths = [
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Chromium.app/Contents/MacOS/Chromium',
    ]
    chrome_found = None
    for p in chrome_paths:
        if os.path.isfile(p):
            chrome_found = p
            break
    if chrome_found:
        webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(chrome_found))
        webbrowser.get('chrome').open('file://' + out_path)
        print('已在 Chrome 中打开')
    else:
        webbrowser.open('file://' + out_path)
        print('已在默认浏览器中打开')


if __name__ == '__main__':
    main()
