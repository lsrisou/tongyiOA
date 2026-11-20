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
    data.source = 'db';

    // TODO: 用真实 SQL 替换下列占位逻辑（等待表结构与口径确认）
    // 示例：
    // const [rows] = await db.query(
    //   'SELECT COUNT(*) AS c FROM user_log WHERE created_at >= CURDATE()'
    // );
    // data.kpis.visits = rows[0].c;

    const [rows] = await db.query('SELECT 1 AS ok');
    if (!rows || !rows.length) throw new Error('empty result');

    data.source = 'demo';
    data.note = 'sql_pending';
    return data;
  } catch (err) {
    console.error('[db] query failed:', err.message);
    const fallback = demo();
    fallback.error = 'db_unavailable';
    return fallback;
  }
}

module.exports = { loadMetrics };
