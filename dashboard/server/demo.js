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
      labels: ['06-18 周三','06-19 周四','06-20 周五','06-21 周六','06-22 周日','06-23 周一','06-24 周二'],
      regular: [488.5, 464.5, 711.2, 2923.2, 2734.2, 434.8, 375.0],
      trial:   [ 59.0,  52.0,  95.0,  347.0,  362.0,  73.0,  24.0]
    },
    region: [
      { name: '校区充值', value: 90 }, { name: '课程包签约', value: 8 },
      { name: '体验课支付', value: 2 }
    ],
    rank: [
      { name: '高新校区', value: 9.0 }, { name: '曲江校区', value: 7.0 },
      { name: '经开校区', value: 6.5 }, { name: '雁塔校区', value: 5.0 },
      { name: '碑林校区', value: 4.5 }, { name: '长安校区', value: 3.5 },
      { name: '未央校区', value: 3.0 }, { name: '莲湖校区', value: 2.5 },
      { name: '新城校区', value: 2.0 }, { name: '灞桥校区', value: 1.5 },
      { name: '临潼校区', value: 1.5 }, { name: '阎良校区', value: 1.2 },
      { name: '户县校区', value: 1.0 }, { name: '周至校区', value: 1.0 },
      { name: '蓝田校区', value: 0.8 }, { name: '高陵校区', value: 0.8 },
      { name: '咸阳秦都校区', value: 0.6 }, { name: '咸阳渭城校区', value: 0.6 },
      { name: '渭南临渭校区', value: 0.5 }, { name: '宝鸡渭滨校区', value: 0.4 }
    ],
    teacherRank: [
      { name: '张兴伟', value: 3.0 }, { name: '孟夏', value: 3.0 },
      { name: '彦楠', value: 3.0 }, { name: '陆金莲', value: 3.0 },
      { name: '张老师', value: 3.0 }, { name: '陈菡', value: 3.0 },
      { name: '李静', value: 2.5 }, { name: '王芳', value: 2.5 },
      { name: '赵磊', value: 2.0 }, { name: '刘洋', value: 2.0 },
      { name: '孙悦', value: 2.0 }, { name: '周敏', value: 1.5 },
      { name: '吴强', value: 1.5 }, { name: '郑洁', value: 1.5 },
      { name: '冯凯', value: 1.0 }, { name: '朱琳', value: 1.0 },
      { name: '何鹏', value: 1.0 }, { name: '许晴', value: 0.5 },
      { name: '马超', value: 0.5 }, { name: '林雪', value: 0.5 }
    ],
    load: [
      { name: '教练利用率', value: 11 },
      { name: '教练满荷率', value: 48 },
      { name: '今日课时进度', value: 89 }
    ],
    channel: [
      { name: '金牌教练', value: 5403.8 }, { name: '银牌教练', value: 3428.5 },
      { name: '王牌教练', value: 1946.0 }, { name: '教练', value: 606.0 },
      { name: '白金教练', value: 327.0 }, { name: '钻石教练', value: 177.0 },
      { name: '初级专家', value: 135.3 }, { name: '助教', value: 83.0 },
      { name: '高级专家', value: 41.8 }, { name: '特级专家', value: 4.0 }
    ],
    core: [
      { name: '教练利用率', value: '1,917 / 16,885', unit: ' 人', percent: 11 },
      { name: '教练满荷率', value: '921 / 1,917', unit: ' 人', percent: 48 },
      { name: '今日正课进度', value: '385.0', unit: ' h', percent: 89 },
      { name: '充值达成率', value: '¥19,764', unit: '', percent: 12 }
    ],
    events: [],
    schoolMap: {
      total: 6341,
      unknown: 35,
      provinces: [
        { name: '四川', value: 619 }, { name: '湖北', value: 573 },
        { name: '江西', value: 549 }, { name: '浙江', value: 526 },
        { name: '湖南', value: 509 }, { name: '江苏', value: 319 },
        { name: '新疆', value: 309 }, { name: '山东', value: 301 },
        { name: '北京', value: 290 }, { name: '河北', value: 270 },
        { name: '内蒙古', value: 252 }, { name: '广东', value: 242 },
        { name: '河南', value: 206 }, { name: '贵州', value: 138 },
        { name: '福建', value: 136 }, { name: '甘肃', value: 118 },
        { name: '陕西', value: 117 }, { name: '重庆', value: 111 },
        { name: '天津', value: 109 }, { name: '上海', value: 107 }
      ]
    }
  };
}

module.exports = demo;
