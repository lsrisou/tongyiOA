'use strict';

const demo = require('./demo');

// 支持两种注入方式：
// 1) DASH_CONFIG：单个 JSON 变量，包含数据库与跳板机连接信息（推荐，规避环境变量数量限制）
// 2) DB_HOST / DB_USER / ... 等独立变量
function readConfig() {
  let raw = {};
  if (process.env.DASH_CONFIG) {
    try {
      raw = JSON.parse(process.env.DASH_CONFIG);
    } catch (err) {
      console.error('[config] DASH_CONFIG is not valid JSON: ' + err.message);
    }
  }
  return {
    db: {
      host: raw.dbHost || process.env.DB_HOST,
      port: Number(raw.dbPort || process.env.DB_PORT || 3306),
      user: raw.dbUser || process.env.DB_USER,
      password: raw.dbPassword || process.env.DB_PASSWORD,
      database: raw.dbName || process.env.DB_NAME
    },
    ssh: {
      host: raw.sshHost || process.env.SSH_HOST,
      port: Number(raw.sshPort || process.env.SSH_PORT || 22),
      user: raw.sshUser || process.env.SSH_USER,
      password: raw.sshPassword || process.env.SSH_PASSWORD
    }
  };
}

const CONF = readConfig();
const DB = CONF.db;
const SSH = CONF.ssh;

const TODAY_PERIOD = {
  start: 'CURDATE()',
  end: 'CURDATE() + INTERVAL 1 DAY'
};
const YESTERDAY_PERIOD = {
  start: 'CURDATE() - INTERVAL 1 DAY',
  end: 'CURDATE()'
};

function periodWhere(field, p) {
  // start_time 是 bigint 时间戳，其余（finished_at/updated_at/created_at）是 datetime
  if (field === 'start_time') {
    return 'start_time >= UNIX_TIMESTAMP(' + p.start + ') AND start_time < UNIX_TIMESTAMP(' + p.end + ')';
  }
  return field + ' >= ' + p.start + ' AND ' + field + ' < ' + p.end;
}

let conn = null;
let lastError = null;
let lastErrorAt = 0;

function dropConnection() {
  if (!conn) return;
  try { conn.destroy(); } catch (err) { /* ignore */ }
  conn = null;
}

function recordError(err) {
  lastError = err;
  lastErrorAt = Date.now();
}

async function connectDirect() {
  const mysql = require('mysql2/promise');
  const connection = await mysql.createConnection({
    host: DB.host,
    port: DB.port,
    user: DB.user,
    password: DB.password,
    database: DB.database,
    connectTimeout: 6000
  });
  coreEmitter(connection).on('error', function () {
    if (conn === connection) dropConnection();
  });
  return connection;
}

// mysql2 的 promise 连接可能在 .connection 上暴露原生 EventEmitter
function coreEmitter(connection) {
  const core = connection.connection || connection;
  return typeof core.on === 'function' ? core : { on: function () {} };
}

async function connectViaSsh() {
  const { Client } = require('ssh2');
  const mysql = require('mysql2/promise');
  const client = new Client();

  const stream = await new Promise(function (resolve, reject) {
    client.once('ready', function () {
      client.forwardOut('127.0.0.1', 0, DB.host, DB.port, function (err, s) {
        if (err) { client.end(); reject(err); return; }
        resolve(s);
      });
    });
    client.once('error', reject);
    client.connect({
      host: SSH.host,
      port: SSH.port,
      username: SSH.user,
      password: SSH.password,
      readyTimeout: 12000
    });
  });

  const connection = await mysql.createConnection({
    user: DB.user,
    password: DB.password,
    database: DB.database,
    stream: stream,
    connectTimeout: 8000
  });
  coreEmitter(connection).on('error', function () {
    if (conn === connection) dropConnection();
  });
  stream.on('close', function () {
    if (conn === connection) dropConnection();
  });
  connection.__ssh = client;
  return connection;
}

async function getConnection() {
  if (conn) return conn;
  if (lastError && Date.now() - lastErrorAt < 60000) throw lastError;

  try {
    conn = await connectDirect();
  } catch (directErr) {
    if (!SSH.host) {
      recordError(directErr);
      throw directErr;
    }
    try {
      conn = await connectViaSsh();
      console.log('[db] connected via ssh tunnel');
    } catch (sshErr) {
      recordError(sshErr);
      throw sshErr;
    }
  }
  conn.on('error', function () { dropConnection(); });
  return conn;
}

async function scalar(connection, sql) {
  const [rows] = await connection.query(sql);
  return rows.length ? Number(rows[0].value) || 0 : 0;
}

const TEACH_LEVELS = {
  0: '助教',
  10: '教练',
  20: '银牌教练',
  30: '金牌教练',
  35: '白金教练',
  40: '王牌教练',
  43: '钻石教练',
  45: '初级专家',
  50: '高级专家',
  60: '特级专家'
};

const ROLE_LABELS = {
  school_pre_teacher: '预备教练',
  school_dean: '教务',
  school_headmaster: '校长',
  school_premaster: '预备校长',
  school_deputymaster: '副校长',
  top_manager: '总部管理员',
  top_dean: '总部教务',
  top_treasurer: '总部财务',
  school_salesman: '课程顾问',
  school_pre_master: '预备校长',
  school_counsellor: '学习顾问',
  school_treasurer: '财务',
  school_promoter: '市场',
  company_manager: '公司管理员'
};

function resolveRole(roleId, teachLevel) {
  if (roleId === 'school_teacher') {
    return TEACH_LEVELS[Number(teachLevel)] || TEACH_LEVELS[0];
  }
  if (ROLE_LABELS[roleId]) return ROLE_LABELS[roleId];
  // 未登记的角色直接回显 role_id，便于后续补字典
  return roleId || '';
}

function actionLevel(action) {
  if (/退课|退约|退款|驳回|取消|禁用|删除/.test(action)) return 'error';
  if (/转化成功|通过|签署|新增|创建|报名/.test(action)) return 'success';
  if (/修改|编辑|审核|调整/.test(action)) return 'warn';
  return 'info';
}

function parseCourseId(content) {
  if (!content) return 0;
  try {
    const obj = JSON.parse(String(content).replace(/^\uFEFF/, '').trim());
    let request = Array.isArray(obj.request) ? obj.request[0] : obj.request;
    if (request) {
      const id = Number(request.id || request.ID);
      if (id) return id;
    }
    const old = Array.isArray(obj.old) ? obj.old[0] : obj.old;
    return old ? Number(old.ID || old.id) || 0 : 0;
  } catch (err) {
    return 0;
  }
}

async function loadEvents(connection) {
  const [rows] = await connection.query(
    "SELECT l.action, DATE_FORMAT(l.created_at, '%H:%i') AS time_text, " +
    "LEFT(l.content, 2000) AS content, " +
    "u_op.name AS op_name, u_op.role_id AS op_role_id, u_op.teach_level AS op_teach_level, " +
    "u_target.name AS target_name, s.name AS school_name " +
    'FROM de_admin_action_logs l ' +
    'LEFT JOIN de_admin_users u_op ON u_op.id = l.creator ' +
    'LEFT JOIN de_admin_users u_target ON u_target.id = l.user_id AND l.user_id <> 0 ' +
    'LEFT JOIN de_schools s ON s.id = l.school_id AND l.school_id <> 0 ' +
    'ORDER BY l.id DESC LIMIT 20'
  );
  return rows.map(function (row) {
    var who = (row.op_name || '系统') + ' · ' + resolveRole(row.op_role_id, row.op_teach_level);
    var extra = [];
    if (row.target_name) extra.push('对 ' + row.target_name);
    if (row.school_name) extra.push('@ ' + row.school_name);
    // 特殊：修改教练级别 显示 old_level → new_level
    var diff = '';
    if (row.action === '修改教练级别' && row.content) {
      try {
        var c = JSON.parse(row.content);
        var oldTl = TEACH_LEVELS[Number(c.old_level)];
        var newTl = TEACH_LEVELS[Number(c.new_level)];
        if (oldTl && newTl && oldTl !== newTl) diff = oldTl + ' → ' + newTl;
      } catch (e) { /* ignore */ }
    }
    return {
      time: row.time_text,
      action: row.action,
      level: actionLevel(row.action || ''),
      operator: who,
      target: row.target_name || '',
      school: row.school_name || '',
      tail: extra.join(' '),
      role: resolveRole(row.op_role_id, row.op_teach_level),
      courseId: parseCourseId(row.content),
      diff: diff
    };
  });
}

async function collect(connection, period) {
  const trialHours = await scalar(connection,
    'SELECT COALESCE(SUM(hour_count), 0) AS value FROM de_student_hour_lessons ' +
    'WHERE deleted_at IS NULL AND ' + periodWhere('start_time', period) + ' AND trial_lesson_id <> 0');
  const regularHours = await scalar(connection,
    'SELECT COALESCE(SUM(hour_count), 0) AS value FROM de_student_hour_lessons ' +
    'WHERE deleted_at IS NULL AND ' + periodWhere('start_time', period) + ' AND trial_lesson_id = 0');

  // 转化率：分子=period 内 state 变 4（updated_at），分母=period 内完课（finished_at）
  const [conversionRows] = await connection.query(
    'SELECT ' +
    '(SELECT COUNT(*) FROM de_trial_hour_lessons WHERE deleted_at IS NULL ' +
    ' AND ' + periodWhere('finished_at', period) + ') AS total, ' +
    '(SELECT COUNT(*) FROM de_trial_hour_lessons WHERE pay_state = 1 AND state = 4 AND student_id > 0 ' +
    ' AND ' + periodWhere('updated_at', period) + ') AS converted');

  const schoolChargeAmount = await scalar(connection,
    "SELECT COALESCE(SUM(price), 0) / 100 AS value FROM de_orders " +
    "WHERE deleted_at IS NULL AND state = 2 AND " + periodWhere('created_at', period) +
    " AND type_id = 'school_point_charge'");
  const trialPayAmount = await scalar(connection,
    "SELECT COALESCE(SUM(price), 0) / 100 AS value FROM de_orders " +
    "WHERE deleted_at IS NULL AND state = 2 AND " + periodWhere('created_at', period) +
    " AND type_id = 'trial_lesson'");

  const total = Number(conversionRows[0].total) || 0;
  const converted = Number(conversionRows[0].converted) || 0;

  return {
    trialHours: trialHours,
    regularHours: regularHours,
    conversionRate: total ? converted / total * 100 : 0,
    conversionDetail: { converted: converted, total: total },
    schoolChargeAmount: schoolChargeAmount,
    trialPayAmount: trialPayAmount
  };
}

/**
 * 返回大屏所需的全部指标。
 * 连接参数来自 DASH_CONFIG（JSON）或独立环境变量，未配置或查询失败时回落到演示数据。
 */
async function loadLevelHours(connection) {
  const [rows] = await connection.query(
    "SELECT u.teach_level, ROUND(SUM(l.hour_count), 1) AS h " +
    "FROM de_student_hour_lessons l " +
    "JOIN de_admin_users u ON u.id = l.teacher_id " +
    "WHERE l.start_time >= UNIX_TIMESTAMP(CURDATE()) " +
    "AND l.start_time <  UNIX_TIMESTAMP(CURDATE() + INTERVAL 1 DAY) " +
    "AND l.deleted_at IS NULL " +
    "GROUP BY u.teach_level " +
    "ORDER BY h DESC"
  );
  const levelNames = { 0: '助教', 10: '教练', 20: '银牌教练', 30: '金牌教练',
    35: '白金教练', 40: '王牌教练', 43: '钻石教练', 45: '初级专家',
    50: '高级专家', 60: '特级专家' };
  return rows.map(function (r) {
    return { name: levelNames[Number(r.teach_level)] || ('等级' + r.teach_level),
             value: Number(r.h) || 0 };
  }).filter(function (d) { return d.value > 0; });
}

/** 左2：今日校区课时排行 TOP 6 */
async function loadSchoolRank(connection) {
  const [rows] = await connection.query(
    'SELECT s.name AS name, ROUND(SUM(l.hour_count), 1) AS h ' +
    'FROM de_student_hour_lessons l ' +
    'JOIN de_schools s ON s.id = l.school_id ' +
    'WHERE l.school_id <> 0 ' +
    'AND s.deleted_at IS NULL ' +
    'AND l.start_time >= UNIX_TIMESTAMP(CURDATE()) ' +
    'AND l.start_time <  UNIX_TIMESTAMP(CURDATE() + INTERVAL 1 DAY) ' +
    'AND l.deleted_at IS NULL ' +
    'GROUP BY l.school_id ' +
    'ORDER BY h DESC LIMIT 6'
  );
  return rows.map(function (r) {
    return { name: r.name || '未知校区', value: Number(r.h) || 0 };
  });
}

/** 右3：今日教练课时 TOP 6 */
async function loadTeacherRank(connection) {
  const [rows] = await connection.query(
    'SELECT u.name AS name, ROUND(SUM(l.hour_count), 1) AS h ' +
    'FROM de_student_hour_lessons l ' +
    'JOIN de_admin_users u ON u.id = l.teacher_id ' +
    'WHERE l.start_time >= UNIX_TIMESTAMP(CURDATE()) ' +
    'AND l.start_time <  UNIX_TIMESTAMP(CURDATE() + INTERVAL 1 DAY) ' +
    'AND l.deleted_at IS NULL ' +
    'GROUP BY l.teacher_id ' +
    'ORDER BY h DESC LIMIT 6'
  );
  return rows.map(function (r) {
    return { name: r.name || '未知', value: Number(r.h) || 0 };
  });
}

/** 左3：教练利用率 / 满荷率 / 今日进度（3 个圆环 0~100） */
async function loadLoad(connection) {
  const [todayT] = await connection.query(
    'SELECT COUNT(DISTINCT teacher_id) AS value FROM de_student_hour_lessons ' +
    'WHERE start_time >= UNIX_TIMESTAMP(CURDATE()) ' +
    'AND start_time <  UNIX_TIMESTAMP(CURDATE() + INTERVAL 1 DAY) ' +
    'AND deleted_at IS NULL'
  );
  const todayTeachers = Number(todayT[0].value) || 0;
  const [totalT] = await connection.query(
    "SELECT COUNT(*) AS value FROM de_admin_users WHERE role_id = 'school_teacher' AND deleted_at IS NULL"
  );
  const totalTeachers = Number(totalT[0].value) || 1;
  const util = Math.round(todayTeachers * 100 / totalTeachers);

  const [fullT] = await connection.query(
    'SELECT COUNT(*) AS value FROM (' +
    '  SELECT teacher_id FROM de_student_hour_lessons ' +
    '  WHERE start_time >= UNIX_TIMESTAMP(CURDATE()) ' +
    '  AND start_time <  UNIX_TIMESTAMP(CURDATE() + INTERVAL 1 DAY) ' +
    '  AND deleted_at IS NULL ' +
    '  GROUP BY teacher_id HAVING SUM(hour_count) >= 4' +
    ') t'
  );
  const fullHour = Number(fullT[0].value) || 0;
  const fullRate = todayTeachers ? Math.round(fullHour * 100 / todayTeachers) : 0;

  const [yestH] = await connection.query(
    'SELECT COALESCE(SUM(hour_count), 0) AS value FROM de_student_hour_lessons ' +
    'WHERE deleted_at IS NULL AND trial_lesson_id = 0 ' +
    'AND start_time >= UNIX_TIMESTAMP(CURDATE() - INTERVAL 1 DAY) ' +
    'AND start_time <  UNIX_TIMESTAMP(CURDATE())'
  );
  const [todayH] = await connection.query(
    'SELECT COALESCE(SUM(hour_count), 0) AS value FROM de_student_hour_lessons ' +
    'WHERE deleted_at IS NULL AND trial_lesson_id = 0 ' +
    'AND start_time >= UNIX_TIMESTAMP(CURDATE()) ' +
    'AND start_time <  UNIX_TIMESTAMP(CURDATE() + INTERVAL 1 DAY)'
  );
  const yestReg = Number(yestH[0].value) || 1;
  const todayReg = Number(todayH[0].value) || 0;
  const progress = Math.round(Math.min(100, todayReg * 100 / yestReg));

  return [
    { name: '教练利用率', value: util },
    { name: '教练满荷率', value: fullRate },
    { name: '今日课时进度', value: progress }
  ];
}

/** 中下2：今日订单渠道占比（条形图，0~100 百分比） */
async function loadRegion(connection) {
  const TYPE_NAMES = {
    school_point_charge: '校区充值',
    hour_contract: '课程包签约',
    trial_lesson: '体验课支付',
    school_goods: '校区商品',
    school_class: '班级报名',
    teacher_reward: '教练奖励'
  };
  const [rows] = await connection.query(
    'SELECT type_id, ROUND(SUM(price) / 100, 0) AS amt ' +
    'FROM de_orders ' +
    'WHERE deleted_at IS NULL AND state = 2 AND DATE(created_at) = CURDATE() ' +
    'GROUP BY type_id ' +
    'ORDER BY amt DESC'
  );
  const total = rows.reduce(function (s, r) { return s + Number(r.amt); }, 0) || 1;
  return rows.map(function (r) {
    return {
      name: TYPE_NAMES[r.type_id] || String(r.type_id),
      value: Math.round(Number(r.amt) * 100 / total)
    };
  });
}

/** 中下1：今日核心运营指标（mini-stats 4 项） */
async function loadCore(connection) {
  const [todayT] = await connection.query(
    'SELECT COUNT(DISTINCT teacher_id) AS value FROM de_student_hour_lessons ' +
    'WHERE start_time >= UNIX_TIMESTAMP(CURDATE()) ' +
    'AND start_time <  UNIX_TIMESTAMP(CURDATE() + INTERVAL 1 DAY) ' +
    'AND deleted_at IS NULL'
  );
  const todayTeachers = Number(todayT[0].value) || 0;
  const [totalT] = await connection.query(
    "SELECT COUNT(*) AS value FROM de_admin_users WHERE role_id = 'school_teacher' AND deleted_at IS NULL"
  );
  const totalTeachers = Number(totalT[0].value) || 1;
  const utilRate = Math.round(todayTeachers * 100 / totalTeachers);

  const [fullT] = await connection.query(
    'SELECT COUNT(*) AS value FROM (' +
    '  SELECT teacher_id FROM de_student_hour_lessons ' +
    '  WHERE start_time >= UNIX_TIMESTAMP(CURDATE()) ' +
    '  AND start_time <  UNIX_TIMESTAMP(CURDATE() + INTERVAL 1 DAY) ' +
    '  AND deleted_at IS NULL ' +
    '  GROUP BY teacher_id HAVING SUM(hour_count) >= 4' +
    ') t'
  );
  const fullHour = Number(fullT[0].value) || 0;
  const fullRate = todayTeachers ? Math.round(fullHour * 100 / todayTeachers) : 0;

  const [yestH] = await connection.query(
    'SELECT COALESCE(SUM(hour_count), 0) AS value FROM de_student_hour_lessons ' +
    'WHERE deleted_at IS NULL AND trial_lesson_id = 0 ' +
    'AND start_time >= UNIX_TIMESTAMP(CURDATE() - INTERVAL 1 DAY) ' +
    'AND start_time <  UNIX_TIMESTAMP(CURDATE())'
  );
  const [todayH] = await connection.query(
    'SELECT COALESCE(SUM(hour_count), 0) AS value FROM de_student_hour_lessons ' +
    'WHERE deleted_at IS NULL AND trial_lesson_id = 0 ' +
    'AND start_time >= UNIX_TIMESTAMP(CURDATE()) ' +
    'AND start_time <  UNIX_TIMESTAMP(CURDATE() + INTERVAL 1 DAY)'
  );
  const yestReg = Number(yestH[0].value) || 1;
  const todayReg = Number(todayH[0].value) || 0;
  const progressRate = Math.round(Math.min(100, todayReg * 100 / yestReg));

  const [charge] = await connection.query(
    "SELECT COALESCE(SUM(price), 0) / 100 AS value FROM de_orders " +
    "WHERE deleted_at IS NULL AND state = 2 AND " +
    "created_at >= CURDATE() - INTERVAL 6 DAY AND created_at < CURDATE() " +
    "AND type_id = 'school_point_charge'"
  );
  const [todayCharge] = await connection.query(
    "SELECT COALESCE(SUM(price), 0) / 100 AS value FROM de_orders " +
    "WHERE deleted_at IS NULL AND state = 2 AND DATE(created_at) = CURDATE() " +
    "AND type_id = 'school_point_charge'"
  );
  const avgCharge7 = Number(charge[0].value) / 7 || 1;
  const todayChargeVal = Number(todayCharge[0].value) || 0;
  const chargeRate = Math.round(Math.min(100, todayChargeVal * 100 / avgCharge7));

  return [
    { name: '教练利用率', value: todayTeachers.toLocaleString('en-US') + ' / ' + totalTeachers, unit: ' 人', percent: utilRate },
    { name: '教练满荷率', value: fullHour + ' / ' + todayTeachers, unit: ' 人', percent: fullRate },
    { name: '今日正课进度', value: todayReg.toFixed(1), unit: ' h', percent: progressRate },
    { name: '充值达成率', value: '¥' + Math.round(todayChargeVal).toLocaleString('en-US'), unit: '', percent: chargeRate }
  ];
}

async function loadWeeklyLessons(connection) {
  const [rows] = await connection.query(
    "SELECT CONCAT(FROM_UNIXTIME(start_time,'%m-%d'), ' ', " +
    "CASE DAYOFWEEK(FROM_UNIXTIME(start_time)) " +
    "WHEN 2 THEN '周一' WHEN 3 THEN '周二' WHEN 4 THEN '周三' WHEN 5 THEN '周四' " +
    "WHEN 6 THEN '周五' WHEN 7 THEN '周六' WHEN 1 THEN '周日' END) AS d, " +
    "SUM(CASE WHEN trial_lesson_id = 0 THEN hour_count ELSE 0 END) AS regular_h, " +
    "SUM(CASE WHEN trial_lesson_id <> 0 THEN hour_count ELSE 0 END) AS trial_h " +
    "FROM de_student_hour_lessons " +
    "WHERE deleted_at IS NULL " +
    "AND start_time >= UNIX_TIMESTAMP(CURDATE() - INTERVAL 6 DAY) " +
    "AND start_time <  UNIX_TIMESTAMP(CURDATE() + INTERVAL 1 DAY) " +
    "GROUP BY FROM_UNIXTIME(start_time,'%Y-%m-%d') " +
    "ORDER BY MIN(start_time)"
  );
  return {
    labels: rows.map(function (r) { return r.d; }),
    regular: rows.map(function (r) { return Number(r.regular_h) || 0; }),
    trial: rows.map(function (r) { return Number(r.trial_h) || 0; })
  };
}

async function loadMetrics() {
  if (!DB.host) return demo();

  try {
    const db = await getConnection();
    const today = await collect(db, TODAY_PERIOD);
    const yesterday = await collect(db, YESTERDAY_PERIOD);

    const data = demo();
    data.kpis.trialHours = today.trialHours;
    data.kpis.regularHours = today.regularHours;
    data.kpis.conversionRate = today.conversionRate;
    data.kpis.schoolChargeAmount = today.schoolChargeAmount;
    data.kpis.trialPayAmount = today.trialPayAmount;
    data.kpis.conversionDetail = today.conversionDetail;
    data.yesterday = yesterday;
    try {
      data.events = await loadEvents(db);
    } catch (eventErr) {
      console.error('[db] events query failed:', eventErr.message);
      data.events = [];
    }
    try {
      data.weekLessons = await loadWeeklyLessons(db);
    } catch (weekErr) {
      console.error('[db] weekly query failed:', weekErr.message);
    }
    try {
      data.channel = await loadLevelHours(db);
    } catch (chErr) {
      console.error('[db] level-hours query failed:', chErr.message);
    }
    try {
      data.rank = await loadSchoolRank(db);
    } catch (rErr) {
      console.error('[db] school-rank query failed:', rErr.message);
    }
    try {
      data.teacherRank = await loadTeacherRank(db);
    } catch (trErr) {
      console.error('[db] teacher-rank query failed:', trErr.message);
    }
    try {
      data.load = await loadLoad(db);
    } catch (lErr) {
      console.error('[db] load query failed:', lErr.message);
    }
    try {
      data.region = await loadRegion(db);
    } catch (regErr) {
      console.error('[db] region query failed:', regErr.message);
    }
    try {
      data.core = await loadCore(db);
    } catch (cErr) {
      console.error('[db] core query failed:', cErr.message);
    }
    data.source = 'db';
    data.updatedAt = new Date().toISOString();
    return data;
  } catch (err) {
    console.error('[db] query failed:', err.message);
    dropConnection();
    const fallback = demo();
    fallback.error = 'db_unavailable';
    return fallback;
  }
}

module.exports = { loadMetrics };
