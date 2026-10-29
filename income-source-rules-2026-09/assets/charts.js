(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  function fmtMoney(v) {
    var s = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return (v < 0 ? '-' : '') + s + ' 元';
  }

  // ---------- Chart 1: income sources ----------
  var sources = [
    { name: '小时课上课收入', value: 1635191.25, pct: '65.20%' },
    { name: '小时课，交付中心服务费', value: 238092.77, pct: '9.49%' },
    { name: '小时课课程服务收入', value: 225620.68, pct: '9.00%' },
    { name: '总部教练课时抽成', value: 149489.75, pct: '5.96%' },
    { name: '推荐校区课时奖励收入', value: 89681.25, pct: '3.58%' },
    { name: '间接校区课时奖励收入', value: 88988.75, pct: '3.55%' },
    { name: '小时课教务推荐奖励', value: 37733.35, pct: '1.50%' },
    { name: '股东课时奖励收入', value: 16172.00, pct: '0.64%' },
    { name: '理事课时奖励收入', value: 12779.75, pct: '0.51%' },
    { name: '小时课，校区招生服务费', value: 7407.00, pct: '0.30%' },
    { name: '事业部课时奖励收入', value: 5964.75, pct: '0.24%' },
    { name: '分销补发（推荐/间接）', value: 965.00, pct: '0.04%' },
    { name: '课程服务收入（非小时课）', value: 105.00, pct: '0.00%' },
    { name: '教学校区课时奖励扣减', value: -361.80, pct: '-0.01%' }
  ];

  var chart1 = echarts.init(document.getElementById('chart-sources'), null, { renderer: 'svg' });
  chart1.setOption({
    animation: false,
    grid: { left: 200, right: 92, top: 24, bottom: 34, containLabel: false },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendToBody: true,
      formatter: function (params) {
        var p = params[0];
        return p.name + '<br/>金额：<b>' + fmtMoney(p.value) + '</b><br/>占比：' + p.data.pct;
      }
    },
    xAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: {
        color: muted,
        fontSize: 11,
        formatter: function (v) {
          if (Math.abs(v) >= 10000) return (v / 10000).toFixed(0) + '万';
          return v;
        }
      }
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: sources.map(function (d) { return d.name; }),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: ink, fontSize: 12, width: 186, overflow: 'truncate' }
    },
    series: [{
      type: 'bar',
      barWidth: '62%',
      data: sources.map(function (d) {
        return {
          value: d.value,
          pct: d.pct,
          itemStyle: { color: d.value < 0 ? muted : (d.value >= 1000000 ? accent : accent + 'cc') }
        };
      }),
      label: {
        show: true,
        position: 'right',
        distance: 6,
        color: muted,
        fontSize: 11,
        formatter: function (p) { return p.data.pct; }
      }
    }]
  });
  window.addEventListener('resize', function () { chart1.resize(); });

  // ---------- Chart 2: billing mechanism ----------
  var mechanism = [
    { name: '基础收入', value: 65.20 },
    { name: '按比例拆分', value: 25.95 },
    { name: '固定课时奖励', value: 8.52 },
    { name: '特殊与调整', value: 0.32 }
  ];

  var chart2 = echarts.init(document.getElementById('chart-mechanism'), null, { renderer: 'svg' });
  chart2.setOption({
    animation: false,
    color: [accent, accent2, muted, accent2 + '88'],
    tooltip: {
      trigger: 'item',
      appendToBody: true,
      formatter: function (p) {
        return p.name + '<br/>占比：<b>' + p.value.toFixed(2) + '%</b>';
      }
    },
    legend: {
      bottom: 8,
      icon: 'circle',
      itemWidth: 9,
      itemHeight: 9,
      textStyle: { color: muted, fontSize: 12 }
    },
    series: [{
      type: 'pie',
      radius: ['40%', '66%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: bg2, borderWidth: 2 },
      label: {
        color: ink,
        fontSize: 12,
        formatter: function (p) {
          return p.value >= 5 ? p.name + '\n' + p.value.toFixed(2) + '%' : '';
        }
      },
      labelLine: { show: false },
      data: mechanism
    }]
  });
  window.addEventListener('resize', function () { chart2.resize(); });

  // ---------- Mermaid ----------
  if (window.mermaid) {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'neutral',
      securityLevel: 'loose',
      themeVariables: {
        fontFamily: 'WorkSans, PingFang SC, Microsoft YaHei, Noto Sans SC, sans-serif',
        fontSize: '13px',
        primaryColor: '#e8eff3',
        primaryTextColor: '#17212b',
        primaryBorderColor: '#1d4e6b',
        lineColor: '#8a949d',
        secondaryColor: '#f6ecd9',
        tertiaryColor: '#ffffff'
      },
      flowchart: { curve: 'basis', nodeSpacing: 34, rankSpacing: 42 }
    });
    mermaid.run({ querySelector: '.mermaid' });
  }
})();
