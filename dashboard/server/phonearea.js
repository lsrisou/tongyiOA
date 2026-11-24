'use strict';

// 手机号段归属地（省）查询。
// phone.dat 为 xluohome/phonedata 的号段库：
//   [0,4)  版本号；[4,8) 索引区起始偏移（小端 int32）
//   索引项 9 字节：[0,4) 号段前 7 位，[4,8) 归属地记录偏移，[8] 运营商
//   记录为 "省|市|邮编|区号\0"
const fs = require('fs');
const path = require('path');

let prefixes = null;
let provinceCodes = null;
let provinceNames = [];

function load() {
  if (prefixes) return;
  const buf = fs.readFileSync(path.join(__dirname, 'phone.dat'));
  const first = buf.readInt32LE(4);
  const count = Math.floor((buf.length - first) / 9);
  prefixes = new Int32Array(count);
  provinceCodes = new Uint8Array(count);
  const seen = Object.create(null);
  for (let i = 0; i < count; i++) {
    const off = first + i * 9;
    prefixes[i] = buf.readInt32LE(off);
    const rec = buf.readInt32LE(off + 4);
    const end = buf.indexOf(0, rec);
    const prov = buf.toString('utf8', rec, end).split('|')[0];
    if (seen[prov] === undefined) {
      seen[prov] = provinceNames.length;
      provinceNames.push(prov);
    }
    provinceCodes[i] = seen[prov];
  }
}

function provinceOf(phone) {
  const num = String(phone == null ? '' : phone).trim();
  if (!/^1\d{10}$/.test(num)) return null;
  load();
  const key = Number(num.slice(0, 7));
  let lo = 0;
  let hi = prefixes.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const cur = prefixes[mid];
    if (cur === key) return provinceNames[provinceCodes[mid]];
    if (cur < key) lo = mid + 1;
    else hi = mid - 1;
  }
  return null;
}

module.exports = { provinceOf };
