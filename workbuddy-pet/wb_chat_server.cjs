// WorkBuddy 桌宠 · 对话服务
// 走 WorkBuddy 云脑（glm-5.3-flash，扣 WorkBuddy 积分），带人设 + 双账档案 + 记忆。
// 由桌宠右键「对话」拉起；无请求 15 分钟自动退出，也可点页面「退出」结束。
//
// 首次使用：
//   1. 把 wb_cloud_config.example.json 复制为 wb_cloud_config.json，
//      填入你自己的 WorkBuddy 云应用 endpoint 和 publishableKey。
//   2. 确认已安装 WorkBuddy 托管 node（~/.workbuddy/binaries/node/versions/），
//      且其全局 node_modules 里有 @tencent-ai/workbuddy-cloud-sdk。
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');

// ---------- 自动定位 WorkBuddy 云 SDK（不写死用户名） ----------
function findSDK() {
  const root = path.join(os.homedir(), '.workbuddy', 'binaries', 'node', 'versions');
  let vers = [];
  try { vers = fs.readdirSync(root).sort().reverse(); } catch (e) {}
  for (const v of vers) {
    const p = path.join(root, v, 'node_modules', '@tencent-ai', 'workbuddy-cloud-sdk');
    if (fs.existsSync(path.join(p, 'package.json'))) return p;
  }
  return null;
}
const SDK = findSDK();
if (!SDK) {
  console.error('[wb-chat] 未找到 @tencent-ai/workbuddy-cloud-sdk，请先安装到 WorkBuddy 托管 node 的全局 node_modules');
  process.exit(1);
}
const { createWorkBuddyCloud } = require(SDK);

// ---------- 云脑配置（外置，凭据不入库） ----------
const CFG_FILE = path.join(__dirname, 'wb_cloud_config.json');
if (!fs.existsSync(CFG_FILE)) {
  console.error('[wb-chat] 缺少 ' + CFG_FILE + '（复制 wb_cloud_config.example.json 并填入你的云应用配置）');
  process.exit(1);
}
const CLOUD_CFG = JSON.parse(fs.readFileSync(CFG_FILE, 'utf8'));

const PORT = 30812;
const DIR = __dirname;
const MEM_FILE = path.join(DIR, 'chat_memory.json');
const IDLE_MS = 15 * 60 * 1000;
// 余额桌宠的数据目录（账本所在，默认 D:/dsh-pet，可在 wb_cloud_config.json 里改 ledgerDir）
const LEDGER_DIR = (CLOUD_CFG.ledgerDir || 'D:/dsh-pet').replace(/\\/g, '/');

const cloud = createWorkBuddyCloud({
  endpoint: CLOUD_CFG.endpoint,
  publishableKey: CLOUD_CFG.publishableKey,
});

// ---------- 账本 ----------
function readJson(p) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return null; }
}
function dayKey(t) {
  const d = new Date(t);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate());
}
function todaySpend(entries) {
  const today = dayKey(Date.now());
  let s = 0, n = 0;
  for (const e of entries || []) {
    if (e.kind === 'demo') continue;
    if (dayKey(e.ts) === today && e.delta < 0) { s += -e.delta; n++; }
  }
  return { s, n };
}
function buildSystem() {
  let sys = '你是主人桌面上的Q版蓝发小女仆，说话自然、俏皮、简短，不要啰嗦，不要解释你自己，不要提你是AI。';
  const lg = readJson(LEDGER_DIR + '/ledger.json');
  if (lg) {
    const { s, n } = todaySpend(lg.entries);
    const bal = lg.lastBalance != null ? Number(lg.lastBalance).toFixed(2) + ' 元' : '未知';
    sys += '\n\n[DeepSeek 余额] ' + bal + '；今日支出 ¥' + s.toFixed(2) + '（' + n + ' 笔）。';
  }
  const cg = readJson(LEDGER_DIR + '/ledger_credits.json');
  if (cg) {
    const { s, n } = todaySpend(cg.entries);
    const bal = cg.lastBalance != null ? Number(cg.lastBalance).toFixed(1) + ' 积分' : '未知';
    sys += '\n[WorkBuddy 积分] ' + bal + '；今日消耗 ' + s.toFixed(1) + ' 分（' + n + ' 笔）。';
  }
  sys += '\n回答涉及钱/积分时用上面的真实数据，不要编造。';
  return sys;
}

// ---------- 记忆 ----------
function loadMem() {
  const m = readJson(MEM_FILE);
  return Array.isArray(m) ? m : [];
}
function saveMem(msgs) {
  try { fs.writeFileSync(MEM_FILE, JSON.stringify(msgs.slice(-40), null, 0), 'utf8'); } catch (e) {}
}

// ---------- LLM ----------
async function ask(text, history) {
  const messages = [{ role: 'system', content: buildSystem() }];
  for (const m of history.slice(-12)) messages.push(m);
  messages.push({ role: 'user', content: text });
  let out = '';
  for await (const ch of cloud.llm.chat.completions.create({
    model: 'glm-5.3-flash',
    messages,
    stream: true,
    temperature: 0.85,
  })) {
    const d = ch.choices && ch.choices[0] && ch.choices[0].delta;
    if (d && d.content) out += d.content;
  }
  return out.trim();
}

// ---------- 页面 ----------
const PAGE = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WorkBuddy 桌宠 · 对话</title>
<style>
*{box-sizing:border-box}
body{margin:0;height:100vh;display:flex;flex-direction:column;background:#0d1117;color:#e6edf3;font:15px/1.55 "Microsoft YaHei",system-ui,sans-serif}
header{display:flex;align-items:center;gap:10px;padding:12px 16px;background:#161b22;border-bottom:1px solid #21262d}
header .dot{width:9px;height:9px;border-radius:50%;background:#3fb950;box-shadow:0 0 8px #3fb950}
header b{font-weight:600}
header .sub{color:#8b949e;font-size:12px;margin-left:auto}
#log{flex:1;overflow-y:auto;padding:18px 16px;display:flex;flex-direction:column;gap:10px}
.row{display:flex;gap:8px;max-width:86%}
.row.me{align-self:flex-end;flex-direction:row-reverse}
.av{width:28px;height:28px;border-radius:50%;flex:0 0 28px;display:flex;align-items:center;justify-content:center;font-size:14px}
.row.pet .av{background:#1f6feb33;border:1px solid #1f6feb}
.row.me .av{background:#3fb95022;border:1px solid #3fb950}
.bub{padding:9px 13px;border-radius:12px;white-space:pre-wrap;word-break:break-word}
.row.pet .bub{background:#161b22;border:1px solid #21262d;border-top-left-radius:4px}
.row.me .bub{background:#1f6feb;color:#fff;border-top-right-radius:4px}
.tip{color:#8b949e;font-size:12px;text-align:center;margin:6px 0}
footer{display:flex;gap:8px;padding:12px 16px;background:#161b22;border-top:1px solid #21262d}
#in{flex:1;background:#0d1117;border:1px solid #30363d;border-radius:8px;color:#e6edf3;padding:10px 12px;font:15px/1.4 inherit;outline:none}
#in:focus{border-color:#1f6feb}
button{background:#1f6feb;border:0;color:#fff;border-radius:8px;padding:0 18px;font-size:15px;cursor:pointer}
button:disabled{opacity:.5;cursor:not-allowed}
#quit{background:#21262d;color:#8b949e;padding:0 12px;font-size:13px}
</style></head><body>
<header><span class="dot"></span><b>WorkBuddy 桌宠</b><span class="sub">WorkBuddy 云脑 · glm-5.3-flash</span></header>
<div id="log"><div class="tip">她在听～问她余额、积分，或者随便聊两句</div></div>
<footer><input id="in" placeholder="说点什么…" autocomplete="off"><button id="send">发送</button><button id="quit">退出</button></footer>
<script>
const log=document.getElementById('log'),inp=document.getElementById('in'),btn=document.getElementById('send');
function add(role,text){const r=document.createElement('div');r.className='row '+role;
r.innerHTML='<div class="av">'+(role==='pet'?'🎀':'🧑')+'</div><div class="bub"></div>';
r.querySelector('.bub').textContent=text;log.appendChild(r);log.scrollTop=log.scrollHeight;return r;}
async function send(){const t=inp.value.trim();if(!t)return;inp.value='';add('me',t);btn.disabled=true;
const wait=add('pet','…');
try{const r=await fetch('/send',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({text:t})});
const j=await r.json();wait.querySelector('.bub').textContent=j.reply||('（出错了：'+(j.reason||'未知'))+')';}
catch(e){wait.querySelector('.bub').textContent='（连接断了）';}
btn.disabled=false;inp.focus();log.scrollTop=log.scrollHeight;}
btn.onclick=send;inp.addEventListener('keydown',e=>{if(e.key==='Enter')send();});
document.getElementById('quit').onclick=async()=>{try{await fetch('/quit',{method:'POST'})}catch(e){};document.body.innerHTML='<div style="padding:40px;text-align:center;color:#8b949e">已退出，可以关掉这个页面了</div>';};
inp.focus();
</script></body></html>`;

// ---------- HTTP ----------
let idleTimer = null;
function touch() {
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = setTimeout(() => { try { server.close(); } catch (e) {} process.exit(0); }, IDLE_MS);
}

const server = http.createServer((req, res) => {
  touch();
  if (req.method === 'GET' && (req.url === '/' || req.url.startsWith('/?'))) {
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    return res.end(PAGE);
  }
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' });
    return res.end('{"ok":true}');
  }
  if (req.method === 'POST' && req.url === '/quit') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end('{"ok":true}');
    return setTimeout(() => process.exit(0), 100);
  }
  if (req.method === 'POST' && req.url === '/send') {
    let body = '';
    req.on('data', (c) => { body += c; if (body.length > 1e6) req.destroy(); });
    req.on('end', async () => {
      let text = '';
      try { text = (JSON.parse(body).text || '').trim(); } catch (e) {}
      if (!text) {
        res.writeHead(200, { 'content-type': 'application/json' });
        return res.end('{"ok":false,"reason":"empty"}');
      }
      try {
        const hist = loadMem();
        const reply = await ask(text, hist);
        hist.push({ role: 'user', content: text }, { role: 'assistant', content: reply });
        saveMem(hist);
        res.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ ok: true, reply }));
      } catch (e) {
        res.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ ok: false, reason: String((e && e.message) || e) }));
      }
    });
    return;
  }
  res.writeHead(404);
  res.end('not found');
});

server.on('error', (e) => {
  if (e && e.code === 'EADDRINUSE') { process.exit(0); } // 已在跑
  process.exit(1);
});
server.listen(PORT, '127.0.0.1', () => { touch(); });
