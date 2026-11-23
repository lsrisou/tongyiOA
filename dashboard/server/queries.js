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

/**
 * 返回大屏所需的全部指标。
 * 连接参数来自 DASH_CONFIG（JSON）或独立环境变量，未配置或查询失败时回落到演示数据。
 */
async function loadMetrics() {
  if (!DB.host) return demo();

  try {
    const db = await getConnection();

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

    const trialHours = await scalar(db, trialHoursSql);
    const regularHours = await scalar(db, regularHoursSql);
    const [conversionRows] = await db.query(conversionSql);
    const schoolChargeAmount = await scalar(db, schoolChargeSql);
    const trialPayAmount = await scalar(db, trialPaySql);

    const totalTrials = Number(conversionRows[0].total) || 0;
    const converted = Number(conversionRows[0].converted) || 0;

    const data = demo();
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
    dropConnection();
    const fallback = demo();
    fallback.error = 'db_unavailable';
    return fallback;
  }
}

module.exports = { loadMetrics };
