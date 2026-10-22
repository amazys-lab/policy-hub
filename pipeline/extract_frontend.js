const fs = require('fs');
const path = require('path');
// 仓内相对（T3 · 2026-10-09）：源 = 仓 server/static/client.html；产物 = 本目录 _frontend.json
const SRC = path.join(__dirname, '..', 'server', 'static', 'client.html');
const OUT = path.join(__dirname, '_frontend.json');
const src = fs.readFileSync(SRC, 'utf8');

function grab(marker) {
  const i = src.indexOf(marker);
  if (i < 0) throw new Error('marker not found: ' + marker);
  const s = src.indexOf('{', i + marker.length);
  let depth = 0, inStr = null, esc = false;
  for (let j = s; j < src.length; j++) {
    const ch = src[j];
    if (inStr) {
      if (esc) { esc = false; continue; }
      if (ch === '\\') { esc = true; continue; }
      if (ch === inStr) inStr = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { inStr = ch; continue; }
    if (ch === '{') depth++;
    else if (ch === '}') { depth--; if (depth === 0) return src.slice(s, j + 1); }
  }
  throw new Error('unbalanced braces: ' + marker);
}

const FORM = eval('(' + grab('const FORM') + ')');
const CITY_FIELDS = eval('(' + grab('const CITY_FIELDS') + ')');
const FIELD_TPL = eval('(' + grab('const FIELD_TPL') + ')');
const BOX_DOM = eval('(' + grab('const BOX_DOM') + ')');
const SUBJECT_WANT = eval('(' + grab('const SUBJECT_WANT') + ')');
let HK_EXTRA = {};
try { HK_EXTRA = eval('(' + grab('const HK_EXTRA') + ')'); } catch (e) { console.error('HK_EXTRA 未找到:', e.message); }

const boxIds = ['empBox', 'hkBox', 'osBox', 'entBox', 'hsBox', 'topicBox', 'clientBox'];
const pos = {};
boxIds.forEach(id => { pos[id] = src.indexOf('id="' + id + '"'); });
const staticFields = {};
boxIds.forEach(id => {
  const start = pos[id];
  if (start < 0) return;
  const later = boxIds.map(x => pos[x]).filter(x => x > start);
  const end = later.length ? Math.min.apply(null, later) : src.length;
  const seg = src.slice(start, end);
  const re = /data-field="([^"]+)"/g;
  let m; const out = new Set();
  while ((m = re.exec(seg))) out.add(m[1]);
  staticFields[id] = Array.from(out);
});

const formAvail = {};
Object.keys(FORM).forEach(k => {
  const cfg = FORM[k]; const s = new Set();
  if (cfg.tags && cfg.tags.field) s.add(cfg.tags.field);
  if (cfg.tags2 && cfg.tags2.field) s.add(cfg.tags2.field);
  (cfg.nums || []).forEach(n => s.add(n[0]));
  (cfg.bools || []).forEach(b => s.add(b[0]));
  (cfg.radio || []).forEach(r => s.add(r[0]));
  if (!s.has('identities')) s.add('identities');
  formAvail[k] = Array.from(s).sort();
});

// 标签选项值：renderForm 渲染的 chip = [[value,label],...]，value 即画像里存进 identities/ent_types 的字符串
const tagValues = {};
Object.keys(FORM).forEach(k => {
  const cfg = FORM[k]; const o = {};
  if (cfg.tags) o[cfg.tags.field || 'identities'] = (cfg.tags.options || []).map(x => x[0]);
  if (cfg.tags2 && cfg.tags2.field) o[cfg.tags2.field] = (cfg.tags2.options || []).map(x => x[0]);
  tagValues[k] = o;
});
// 静态盒里的标签控件（entBox 的 data-ff/data-val 成对出现）
const staticTagValues = {};
boxIds.forEach(id => {
  const start = pos[id];
  if (start < 0) return;
  const later = boxIds.map(x => pos[x]).filter(x => x > start);
  const end = later.length ? Math.min.apply(null, later) : src.length;
  const seg = src.slice(start, end);
  const re = /data-ff="([^"]+)"\s+data-val="([^"]+)"|data-val="([^"]+)"\s+data-ff="([^"]+)"/g;
  const o = {}; let m;
  while ((m = re.exec(seg))) {
    const ff = m[1] || m[4], val = m[2] || m[3];
    (o[ff] = o[ff] || []).push(val);
  }
  if (Object.keys(o).length) staticTagValues[id] = o;
});

const payload = {
  _src: SRC,
  formAvail,
  tagValues,
  staticTagValues,
  staticFields,
  // ★ 本仓不带城市数据：字段池是统一模板（FIELD_TPL），按 schema 登记的城市码展开，
  //   让字段契约文件仍能按城市码查（CITY_FIELDS 里的显式条目优先）。
  cityFields: (function () {
    const o = {};
    let codes = [];
    try {
      const sch = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'policy_hub', 'common', 'schema.json'), 'utf8'));
      codes = Object.keys(sch.city_code || {});
    } catch (e) { console.error('schema.json 读取失败，字段契约只保留显式覆盖:', e.message); }
    codes.forEach(c => { o[c] = FIELD_TPL; });
    Object.keys(CITY_FIELDS).forEach(c => { o[c] = CITY_FIELDS[c]; });
    return o;
  })(),
  hkExtra: HK_EXTRA,
  boxDom: BOX_DOM,
  subjectWant: SUBJECT_WANT,
  formLabels: (function () {
    const L = {};
    Object.keys(FORM).forEach(k => {
      const cfg = FORM[k]; const o = {};
      (cfg.nums || []).forEach(n => o[n[0]] = n[1]);
      (cfg.bools || []).forEach(b => o[b[0]] = b[1]);
      (cfg.radio || []).forEach(r => o[r[0]] = r[1]);
      if (cfg.tags && cfg.tags.field) o[cfg.tags.field] = cfg.tags.title || '身份标签';
      L[k] = o;
    });
    return L;
  })(),
  formByKind: (function () {
    const o = {};
    Object.keys(FORM).forEach(k => {
      const cfg = FORM[k];
      o[k] = {
        nums: (cfg.nums || []).map(n => n[0]),
        bools: (cfg.bools || []).map(b => b[0]),
        radio: (cfg.radio || []).map(r => r[0]),
        tagField: (cfg.tags && cfg.tags.field) || 'identities',
        tagField2: (cfg.tags2 && cfg.tags2.field) || null
      };
    });
    return o;
  })()
};

fs.writeFileSync(OUT, JSON.stringify(payload, null, 1), 'utf8');

// ── 内联脚本抽取件 `_inline.js` ─────────────────────────────────────────────
// ★ 为什么由本脚本生成（2026-10-15）：
//   前端共**三处副本**（client.html / demo_api.html / _inline.js），铁律是「三处同源」。
//   但 `_inline.js` 是 client.html 内联脚本的**抽取件**，此前靠人工脚本打补丁同步 ——
//   实测它已静默停更到 B1 之前（与 client.html 的 `CITY_NAMES` 共同前缀只有 1326 字符，
//   `order` 还停在 14 码），"同源"名存实亡。
//   抽取件必须**派生**、不能**手改** ⇒ 与 `_frontend.json` 一起在本脚本重生成。
//   受 `tests/test_city_onboarding.py::test_rc7` 守（分叉即红）。
const INLINE = path.join(__dirname, '_inline.js');
const blocks = [];
const reScript = /<script[^>]*>([\s\S]*?)<\/script>/g;
let m;
while ((m = reScript.exec(src)) !== null) blocks.push(m[1]);
if (blocks.length !== 1) {
  // 多于一块 ⇒ 抽取配方不再成立，宁可报错也不写出一个「看着像对的」错文件
  throw new Error('client.html 内联 <script> 块数 = ' + blocks.length + '（应为 1），抽取配方需更新');
}
fs.writeFileSync(INLINE, blocks[0], 'utf8');

console.log('wrote ' + OUT);
console.log('wrote ' + INLINE + '（内联抽取件, ' + blocks[0].length + ' 字符）');
console.log('kinds: ' + Object.keys(formAvail).join(', '));
Object.keys(formAvail).forEach(k => console.log('  FORM[' + k + '] 控件字段数 = ' + formAvail[k].length));
Object.keys(staticFields).forEach(b => console.log('  静态盒 ' + b + ' data-field = ' + staticFields[b].length));
console.log('CITY_FIELDS 城市数 = ' + Object.keys(CITY_FIELDS).length);
