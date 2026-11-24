'use strict';

// 演示数据：数据库未就绪或查询失败时使用，保证大屏始终有内容
function traffic24h() {
  var labels = [], visits = [], study = [], ai = [];
  for (var i = 0; i < 24; i++) {
    var t = i / 23;
    labels.push((i < 10 ? '0' : '') + i + ':00');
    visits.push(Math.round(28000 + 16000 * Math.sin(t * Math.PI * 1.15 - 0.4) + 4200 * Math.sin(t * 9)));
    study.push(Math.round(16000 + 11000 * Math.sin(t * Math.PI * 1.05 - 0.9) + 2800 * Math.cos(t * 7)));
    ai.push(Math.round(11000 + 9000 * Math.sin(t * Math.PI * 1.2 - 0.2) + 2400 * Math.sin(t * 11 + 1)));
  }
  return { labels: labels, visits: visits, study: study, ai: ai };
}

function demo() {
  return {
    source: 'demo',
    updatedAt: new Date().toISOString(),
    kpis: {
      // visits 仅用于渠道环图中心的演示总数，不在 KPI 卡片展示
      visits: 128642,
      trialHours: 36.5,
      regularHours: 218.5,
      conversionRate: 18.8,
      schoolChargeAmount: 52680.00,
      trialPayAmount: 3990.00,
      conversionDetail: { converted: 9, total: 48 }
    },
    yesterday: {
      trialHours: 41.0,
      regularHours: 302.5,
      conversionRate: 14.6,
      schoolChargeAmount: 38600.00,
      trialPayAmount: 2150.00,
      conversionDetail: { converted: 14, total: 96 }
    },
    trend: {
      labels: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
      learners: [8200, 9100, 8600, 10400, 11200, 12600, 11800],
      completed: [4200, 4800, 4500, 5600, 6100, 6800, 6600]
    },
    traffic: traffic24h(),
    weekLessons: {
      labels: ['06-18','06-19','06-20','06-21','06-22','06-23','06-24'],
      regular: [488.5, 464.5, 711.2, 2923.2, 2734.2, 434.8, 375.0],
      trial:   [ 59.0,  52.0,  95.0,  347.0,  362.0,  73.0,  24.0]
    },
    region: [
      { name: '华东', value: 92 }, { name: '华南', value: 78 },
      { name: '华北', value: 66 }, { name: '西南', value: 54 },
      { name: '华中', value: 41 }
    ],
    rank: [
      { name: '计算机学院', value: 9820 }, { name: '人工智能学院', value: 8740 },
      { name: '数学与统计学院', value: 7320 }, { name: '外国语学院', value: 6180 },
      { name: '经济管理学院', value: 5240 }, { name: '艺术设计学院', value: 4310 }
    ],
    load: [
      { name: 'CPU', value: 62 }, { name: '内存', value: 78 }, { name: '带宽', value: 45 }
    ],
    channel: [
      { name: '移动端', value: 42 }, { name: 'Web 端', value: 28 },
      { name: '小程序', value: 18 }, { name: '开放 API', value: 12 }
    ],
    ai: [
      { name: '智能问答', value: 92 }, { name: '作业批改', value: 84 },
      { name: '学情分析', value: 76 }, { name: '语音评测', value: 68 },
      { name: '内容生成', value: 61 }
    ],
    core: [
      { name: '日均学习时长', value: '48.6', unit: ' min', percent: 82 },
      { name: '课程资源总量', value: '12,480', unit: ' 门', percent: 68 },
      { name: '师生互动次数', value: '86,320', unit: ' 次', percent: 74 },
      { name: '智能推荐命中率', value: '93.2', unit: ' %', percent: 93 }
    ],
    events: []
  };
}

module.exports = demo;
