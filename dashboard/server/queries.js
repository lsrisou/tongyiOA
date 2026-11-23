'use strict';

const demo = require('./demo');

let pool = null;

function getPool() {
  if (pool) return pool;
  const mysql = require('mysql2/promise');
  pool = mysql.createPool({
    host: process.env.DB_HOST,
    port: Number(process.env.DB_PORT || 3306),
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME,
    connectionLimit: 4,
    connectTimeout: 8000,
    waitForConnections: true
  });
  return pool;
}

const TODAY_LESSON = [
  'deleted_at IS NULL',
  'start_time >= UNIX_TIMESTAMP(CURDATE())',
  'start_time < UNIX_TIMESTAMP(CURDATE() + INTERVAL 1 DAY)'
].join(' AND ');

const TODAY_ORDER = [
  'deleted_at IS NULL',
  'created_at >= CURDATE()',
  'created_at < CURDATE() + INTERVAL 1 DAY',
  'state = 2'
].join(' AND ');

async function scalar(db, sql) {
  const [rows] = await db.query(sql);
  return rows.length ? Number(rows[0].value) || 0 : 0;
}

/**
 * 返回大屏所需的全部指标。
 * 数据库连接通过环境变量注入：DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME。
 * 未配置 DB_HOST，或查询失败时，自动回落到演示数据。
 */
async function loadMetrics() {
  if (!process.env.DB_HOST) return demo();

  try {
    const db = getPool();
    const data = demo();

    const trialHoursSql =
      'SELECT COALESCE(SUM(hour_count), 0) AS value FROM de_student_hour_lessons ' +
      'WHERE ' + TODAY_LESSON + ' AND trial_lesson_id <> 0';
    const regularHoursSql =
      'SELECT COALESCE(SUM(hour_count), 0) AS value FROM de_student_hour_lessons ' +
      'WHERE ' + TODAY_LESSON + ' AND trial_lesson_id = 0';
    const conversionSql =
      'SELECT COUNT(*) AS total, ' +
      'COALESCE(SUM(pay_state = 1 AND state = 4 AND student_id > 0), 0) AS converted ' +
      'FROM de_trial_hour_lessons WHERE ' + TODAY_LESSON;
    const schoolChargeSql =
      "SELECT COALESCE(SUM(price), 0) / 100 AS value FROM de_orders WHERE " + TODAY_ORDER +
      " AND type_id = 'school_point_charge'";
    const trialPaySql =
      "SELECT COALESCE(SUM(price), 0) / 100 AS value FROM de_orders WHERE " + TODAY_ORDER +
      " AND type_id = 'trial_lesson'";

    const [trialHours, regularHours, conversionRows, schoolChargeAmount, trialPayAmount] =
      await Promise.all([
        scalar(db, trialHoursSql),
        scalar(db, regularHoursSql),
        db.query(conversionSql).then(([rows]) => rows[0]),
        scalar(db, schoolChargeSql),
        scalar(db, trialPaySql)
      ]);

    const totalTrials = Number(conversionRows.total) || 0;
    const converted = Number(conversionRows.converted) || 0;

    data.kpis.trialHours = trialHours;
    data.kpis.regularHours = regularHours;
    data.kpis.conversionRate = totalTrials ? converted / totalTrials * 100 : 0;
    data.kpis.schoolChargeAmount = schoolChargeAmount;
    data.kpis.trialPayAmount = trialPayAmount;
    data.kpis.conversionDetail = { converted: converted, total: totalTrials };
    data.source = 'db';
    data.updatedAt = new Date().toISOString();
    return data;
  } catch (err) {
    console.error('[db] query failed:', err.message);
    const fallback = demo();
    fallback.error = 'db_unavailable';
    return fallback;
  }
}

module.exports = { loadMetrics };
