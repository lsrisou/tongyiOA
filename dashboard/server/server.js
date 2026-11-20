'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { loadMetrics } = require('./queries');

const PORT = Number(process.env.PORT || 8000);
const PUBLIC_DIR = path.join(__dirname, 'public');
const CACHE_MS = 15000;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2'
};

let cache = { at: 0, data: null };

async function getMetrics() {
  if (cache.data && Date.now() - cache.at < CACHE_MS) return cache.data;
  const data = await loadMetrics();
  cache = { at: Date.now(), data };
  return data;
}

function sendJson(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'Content-Length': Buffer.byteLength(body)
  });
  res.end(body);
}

function serveStatic(req, res, urlPath) {
  const rel = urlPath === '/' ? 'index.html' : urlPath.replace(/^\/+/, '');
  const filePath = path.join(PUBLIC_DIR, path.normalize(rel));
  if (!filePath.startsWith(PUBLIC_DIR + path.sep) && filePath !== PUBLIC_DIR) {
    res.writeHead(403); res.end('Forbidden'); return;
  }
  fs.readFile(filePath, (err, buf) => {
    if (err) { res.writeHead(404); res.end('Not Found'); return; }
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(filePath).toLowerCase()] || 'application/octet-stream',
      'Cache-Control': 'no-cache'
    });
    res.end(buf);
  });
}

const server = http.createServer(async (req, res) => {
  const urlPath = decodeURIComponent((req.url || '/').split('?')[0]);

  if (urlPath === '/api/health') {
    sendJson(res, 200, { ok: true, port: PORT });
    return;
  }

  if (urlPath === '/api/metrics') {
    try {
      const data = await getMetrics();
      sendJson(res, 200, data);
    } catch (err) {
      console.error('[api] metrics failed:', err.message);
      sendJson(res, 500, { source: 'error', message: 'metrics unavailable' });
    }
    return;
  }

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405); res.end('Method Not Allowed'); return;
  }

  serveStatic(req, res, urlPath);
});

server.listen(PORT, '0.0.0.0', () => {
  console.log('dashboard server listening on 0.0.0.0:' + PORT);
});

process.on('SIGTERM', () => server.close(() => process.exit(0)));
