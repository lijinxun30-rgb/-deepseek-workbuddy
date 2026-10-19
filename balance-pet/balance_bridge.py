# -*- coding: utf-8 -*-
r"""
余额桌宠桥 v5 —— 双轨整合版（一个软件管两本账）：
  轨① DeepSeek 余额（¥）：5 秒轮询官方接口
      · 扣钱 → 「吃Token」+ 打击音 + 逐分飘字
      · 充值 → 「收红包」+ 金币音 + 进账气泡
      · 账本 D:\dsh-pet\ledger.json（单位 ¥）
  轨② WorkBuddy 积分（credits）：20 秒轮询官方 meter 接口（会话凭据自动多源获取）
      · 消耗 → 「工作状态-忙碌点按」+ "WorkBuddy 消耗 N 积分（剩 M）"
      · 增加 → 「拆礼物」+ 金币音 + "积分 +N（共 M）"
      · 账本 D:\dsh-pet\ledger_credits.json（单位 积分）
  两条轨的档案都会注入对话 system（AI 两本账都懂）。
  网页对话 /send 转发 host 原生 /chat；/demo 支持四类演示；/report 双轨汇报；/stop 停机。
  host(3080) 挂了 → 桥自动退出。零第三方依赖。
"""
import json
import socket
import threading
import time
import os
import sys
import ctypes
import subprocess
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "pet.log")
LEDGER = os.path.join(HERE, "ledger.json")                # ¥ 账本
LEDGER_CR = os.path.join(HERE, "ledger_credits.json")     # 积分账本
HIT_MP3 = os.path.join(HERE, "hit.mp3")
COIN_MP3 = os.path.join(HERE, "coin.mp3")
PID_FILE = os.path.join(HERE, "pet_bridge.pid")        # 单例：新桥启动先杀旧桥


def _pid_alive(pid):
    try:
        r = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, encoding="gbk", errors="replace", timeout=5)
        return str(pid) in r.stdout
    except Exception:
        return False


def _kill_pid(pid):
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=5)
    except Exception:
        pass


def acquire_singleton():
    """确保只有一个桥在跑：启动前杀掉旧实例（PID 文件 + 占端口进程双保险）。"""
    # 1) 杀 PID 文件里记录的旧实例
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f:
                old = f.read().strip()
            if old.isdigit() and _pid_alive(int(old)):
                _kill_pid(int(old))
                time.sleep(0.6)
    except Exception:
        pass
    # 2) 杀仍占用聊天端口的孤儿进程（无 PID 文件的旧版）
    try:
        r = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, encoding="gbk", errors="replace", timeout=8)
        for line in r.stdout.splitlines():
            if ":30802" in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit() and pid != str(os.getpid()):
                    _kill_pid(int(pid))
                    time.sleep(0.6)
    except Exception:
        pass
    # 3) 记录自身 PID
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

BASE = "http://127.0.0.1:3080/dsh-pet-7340"
LOCK_PORT = 30801
CHAT_PORT = 30802
BALANCE_URL = "https://api.deepseek.com/user/balance"
CHAT_URL = "https://api.deepseek.com/chat/completions"
METER_URL = "https://www.workbuddy.cn/billing/meter/get-user-resource-summary"
POLL_SEC = 5
CRED_POLL_SEC = 20
STEP_CREDITS = 10.0        # 积分每 10 分播一档演出（旧版同款步长）
TOPUP_MIN = 1.0            # 积分上涨≥1 才算增加

PERSONA = ("你是主人桌面上的Q版蓝发小女仆。说话自然、俏皮、简短，不要啰嗦，"
           "不要解释你自己，不要提你是AI。")


def log(msg):
    line = "[%s] %s" % (time.strftime("%m-%d %H:%M:%S"), msg)
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 1_000_000:
            os.remove(LOG_FILE)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        if sys.stdout is not None:
            print(line)
    except Exception:
        pass


def http_json(url, payload=None, headers=None, timeout=20, method=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def pet_post(path, payload, pet=None, timeout=90):
    url = BASE + path + (("?pet=" + pet) if pet else "")
    return http_json(url, payload, {"Content-Type": "application/json"},
                     timeout=timeout, method="POST")


def read_key():
    try:
        with open(os.path.join(HERE, "apikey.txt"), "r", encoding="utf-8-sig") as f:
            k = f.read().strip()
        return k if k.startswith("sk-") else None
    except Exception:
        return None


# ---------------- 音效 ----------------
_winmm = ctypes.windll.winmm
_ali = [0]

def mci_play(path):
    if not os.path.exists(path):
        return
    try:
        _ali[0] += 1
        a = "bp%d" % _ali[0]
        p = path.replace("/", "\\")
        _winmm.mciSendStringW('open "%s" alias %s' % (p, a), None, 0, None)
        _winmm.mciSendStringW('play %s' % a, None, 0, None)
        threading.Timer(10.0, lambda: _winmm.mciSendStringW('close %s' % a, None, 0, None)).start()
    except Exception:
        pass


# ---------------- 轨①：DeepSeek 余额（¥） ----------------
def query_balance(key):
    data = http_json(BALANCE_URL, headers={"Authorization": "Bearer " + key,
                                           "Accept": "application/json"}, timeout=10)
    if not data.get("is_available"):
        return None
    for info in data.get("balance_infos", []):
        if info.get("currency") == "CNY":
            return float(info.get("total_balance", "0") or 0)
    return None


def load_ledger(path=LEDGER):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("entries"), list):
            return d
    except Exception:
        pass
    return {"lastBalance": None, "entries": []}


def save_ledger(d, path=LEDGER):
    try:
        d["entries"] = d["entries"][-500:]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def record(path, delta, balance, kind):
    d = load_ledger(path)
    d["lastBalance"] = balance
    d["entries"].append({"ts": int(time.time() * 1000),
                         "delta": round(delta, 2), "balance": balance, "kind": kind})
    save_ledger(d, path)


def play_spend(last, bal, demo=False):
    """¥ 扣钱：逐分飘字 + 打击音 + 吃Token。demo=True 只演出不计账。"""
    cents = int(round((last - bal) * 100))
    if cents <= 0:
        return
    try:
        pet_post("/anim", {"name": "吃Token"}, pet="main")
    except Exception:
        pass
    for i in range(min(cents, 30)):
        remain = cents - i
        text = "-0.01" if remain == 1 else "-0.01（还剩 %d 下）" % (remain - 1)
        mci_play(HIT_MP3)
        try:
            pet_post("/broadcast", {"text": text}, pet="main")
        except Exception:
            pass
        time.sleep(0.25)
    record(LEDGER, -cents / 100.0, bal, "demo" if demo else "real")
    log("¥扣费演出：%d 分（%.2f -> %.2f）%s" % (cents, last, bal, " [演示]" if demo else ""))


def play_topup(last, bal, demo=False):
    """¥ 充值：收红包 + 金币音。demo=True 只演出不计账。"""
    diff = bal - last
    mci_play(COIN_MP3)
    record(LEDGER, diff, bal, "demo" if demo else "real")
    try:
        pet_post("/anim", {"name": "收红包"}, pet="main")
        pet_post("/broadcast", {"text": "+%.2f 元进账啦，谢谢主人～" % diff}, pet="main")
    except Exception:
        pass
    log("¥充值演出：+%.2f（%.2f -> %.2f）" % (diff, last, bal))


# ---------------- 轨②：WorkBuddy 积分 ----------------
def read_wb_cookie():
    for p in (r'D:\workbuddy-pet\cookie.txt',
              os.path.join(os.path.expanduser('~'), '.workbuddy-pet', 'cookie.txt'),
              os.path.join(os.path.expanduser('~'), 'TokenHub', 'src', 'config.json')):
        try:
            raw = open(p, 'r', encoding='utf-8-sig').read().strip()
            if not raw:
                continue
            if p.endswith('.json'):
                v = json.loads(raw).get('workbuddy_token', '')
            else:
                v = raw
            if v:
                return v, p
        except Exception:
            continue
    return None, None


CRED, CRED_SRC = read_wb_cookie()


def meter_credits():
    if not CRED:
        raise RuntimeError("未找到 WorkBuddy 会话凭据")
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36 Edg/155.0.0.0',
        'Referer': 'https://www.workbuddy.cn/profile/plans-usage',
        'Origin': 'https://www.workbuddy.cn',
        'X-Client-Platform': 'web',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    if '=' in CRED:
        headers['Cookie'] = CRED
    else:
        headers['Authorization'] = 'Bearer ' + CRED
    data = http_json(METER_URL, {}, headers, timeout=20, method='POST')
    if data.get('code') != 0:
        raise RuntimeError("meter code=%s" % data.get('code'))
    return float(data['data']['TotalCredits'])


def play_credit_spend(last, cr, demo=False):
    """积分消耗：忙碌点按 + 汇总气泡。demo=True 时只演出、不计入真实账本。"""
    drop = last - cr
    try:
        pet_post("/anim", {"name": "工作状态-忙碌点按"}, pet="main")
        pet_post("/broadcast", {"text": "WorkBuddy 消耗 %.0f 积分（剩 %.0f）" % (drop, cr)},
                 pet="main")
    except Exception:
        pass
    record(LEDGER_CR, -drop, cr, "demo" if demo else "real")
    log("积分消耗演出：-%.1f（%.1f -> %.1f）%s" % (drop, last, cr, " [演示]" if demo else ""))


def play_credit_topup(last, cr, demo=False):
    """积分增加：拆礼物 + 金币音。demo=True 时只演出、不计入真实账本。"""
    mci_play(COIN_MP3)
    record(LEDGER_CR, cr - last, cr, "demo" if demo else "real")
    try:
        pet_post("/anim", {"name": "拆礼物"}, pet="main")
        pet_post("/broadcast", {"text": "积分 +%0.f（共 %.0f）" % (cr - last, cr)}, pet="main")
    except Exception:
        pass
    log("积分增加演出：+%.1f（%.1f -> %.1f）%s" % (cr - last, last, cr, " [演示]" if demo else ""))


# ---------------- 统计（双轨） ----------------
def summarize(path=LEDGER, unit="¥"):
    d = load_ledger(path)
    now = time.time()
    day0 = time.strftime("%Y-%m-%d")
    week = now - 7 * 86400
    tS = tE = wS = wE = 0.0
    n = 0
    for e in d.get("entries", []):
        if e.get("kind") == "demo":
            continue
        t = e["ts"] / 1000.0
        dl = e["delta"]
        if time.strftime("%Y-%m-%d", time.localtime(t)) == day0:
            if dl < 0:
                tS += -dl
                n += 1
            else:
                tE += dl
        if t >= week:
            if dl < 0:
                wS += -dl
            else:
                wE += dl
    bal = (("%.2f" % d["lastBalance"]) + (" 元" if unit == "¥" else " 积分")
           if d.get("lastBalance") is not None else "未知")
    fmt = "%%s %s%%.2f%%s" % (("-" if unit == "¥" else "-"),)
    recent = ["%s %s%.2f%s" % (time.strftime("%m-%d %H:%M", time.localtime(e["ts"] / 1000.0)),
                               "-" if e["delta"] < 0 else "+", abs(e["delta"]),
                               "(演示)" if e.get("kind") == "demo" else "")
              for e in d.get("entries", [])[-5:]][::-1]
    return bal, tS, n, tE, wS, wE, recent


# ---------------- 网页 ----------------
CHAT_PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>余额桌宠 · 对话</title><style>
body{margin:0;background:#101418;color:#e8e6e3;font:15px/1.6 system-ui,"Microsoft YaHei";display:flex;flex-direction:column;height:100vh}
header{padding:12px 16px;background:#161b22;border-bottom:1px solid #2a2f36;font-weight:600;display:flex;justify-content:space-between;align-items:center}
#log{flex:1;overflow-y:auto;padding:14px 16px}
.msg{margin:8px 0;max-width:78%;padding:8px 12px;border-radius:12px;white-space:pre-wrap;word-break:break-word}
.me{background:#1f6feb22;border:1px solid #1f6feb55;margin-left:auto;text-align:left}
.her{background:#1c2128;border:1px solid #30363d}
.tip{text-align:center;color:#8b949e;font-size:12px;margin:6px 0}
form{display:flex;gap:8px;padding:10px 12px;background:#161b22;border-top:1px solid #2a2f36}
input{flex:1;background:#0d1117;border:1px solid #30363d;border-radius:8px;color:#e8e6e3;padding:9px 12px;font-size:15px;outline:none}
button{background:#238636;border:0;border-radius:8px;color:#fff;padding:9px 18px;font-size:15px;cursor:pointer}
button.demo{background:#9e6a03;padding:6px 12px;font-size:13px}
button:disabled{opacity:.5}
</style></head><body>
<header><span>余额桌宠 · 双轨账本（DeepSeek ¥ + WorkBuddy 积分）</span><button id="stop" style="background:#da3633;padding:6px 14px;font-size:14px">⏻ 停止桌宠</button></header>
<div style="display:flex;gap:8px;padding:8px 12px;background:#161b22;border-bottom:1px solid #2a2f36;flex-wrap:wrap">
<button class="demo" data-t="spend">💸 测试扣费</button>
<button class="demo" data-t="topup">🧧 测试充值</button>
<button class="demo" data-t="credit-spend" style="background:#8957e5">🔵 测试积分消耗</button>
<button class="demo" data-t="credit-topup" style="background:#8957e5">🟣 测试积分增加</button>
<button class="demo" data-t="report" style="background:#1f6feb">📊 收支汇报</button>
</div>
<div id="log"><div class="tip">她同时懂两本账：DeepSeek 余额（¥）和 WorkBuddy 积分</div></div>
<form onsubmit="return send()"><input id="t" autocomplete="off" placeholder="输入…"><button id="b">发送</button></form>
<script>
const log=document.getElementById('log');
function add(cls,t){const d=document.createElement('div');d.className='msg '+cls;d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight;}
document.querySelectorAll('button.demo').forEach(btn=>{btn.onclick=async()=>{
  btn.disabled=true;try{const r=await fetch('/demo',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({type:btn.dataset.t})});const j=await r.json();add('tip',j.ok?(j.text||'已播放'):'失败：'+(j.reason||''));}catch(e){add('tip','失败：'+e);}
  btn.disabled=false;};});
document.getElementById('stop').onclick=async()=>{
  if(!confirm('停止桌宠？（服务、后台进程全部退出）'))return;
  try{await fetch('/stop',{method:'POST'});}catch(e){}
  add('tip','已停止，桌宠已完全退出，可以关闭本页面了');
  document.getElementById('stop').disabled=true;
};
async function send(){const i=document.getElementById('t'),b=document.getElementById('b');const t=i.value.trim();if(!t)return false;
add('me',t);i.value='';b.disabled=true;const w=add('her','…');
try{const r=await fetch('/send',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({text:t})});
const j=await r.json();w.textContent=j.ok?j.reply:('失败：'+(j.reason||'未知'));}catch(e){w.textContent='失败：'+e;}
b.disabled=false;i.focus();return false;}
document.getElementById('t').focus();
</script></body></html>"""


class ChatHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, CHAT_PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, '{"ok":false,"reason":"not-found"}')

    def do_POST(self):
        if self.path == "/stop":
            try:
                http_json("http://127.0.0.1:3080/shutdown", payload={},
                          timeout=5, method="POST")
            except Exception:
                pass
            return self._send(200, '{"ok":true,"stopping":true}')
        if self.path == "/demo":
            try:
                n = int(self.headers.get("Content-Length", "0"))
                kind = json.loads(self.rfile.read(n).decode("utf-8")).get("type", "")
                if kind == "spend":                      # ¥ 扣费演示
                    play_spend(22.34, 22.33, demo=True)
                    text = "已播放：吃Token + 打击音（演示不计账）"
                elif kind == "topup":                    # ¥ 充值演示
                    play_topup(22.33, 25.33, demo=True)
                    text = "已播放：收红包 + 金币音（演示不计账）"
                elif kind == "credit-spend":             # 积分消耗演示
                    play_credit_spend(714.07, 704.07, demo=True)
                    text = "已播放：忙碌点按（演示不计账）"
                elif kind == "credit-topup":             # 积分增加演示
                    play_credit_topup(704.07, 734.07, demo=True)
                    text = "已播放：拆礼物 + 金币音（演示不计账）"
                elif kind == "report":                   # 双轨汇报
                    bal, tS, n, tE, wS, wE, rec = summarize(LEDGER, "¥")
                    cbal, cS, cn, cE, cwS, cwE, crec = summarize(LEDGER_CR, "积分")
                    text = ("双轨汇报～DeepSeek 余额 %s，今天支出 ¥%.2f（%d 笔）；"
                            "WorkBuddy 积分 %s，今天消耗 %.1f 分。") % (bal, tS, n, cbal, cS)
                else:
                    return self._send(200, '{"ok":false,"reason":"unknown-type"}')
                return self._send(200, json.dumps({"ok": True, "text": text},
                                                  ensure_ascii=False))
            except Exception as e:
                log("演示失败: %r" % e)
                return self._send(200, json.dumps({"ok": False, "reason": str(e)},
                                                  ensure_ascii=False))
        if self.path == "/wb-report":
            """积分查询两连发：第一条=剩余积分，第二条=收支明细。"""
            try:
                cbal, cS, cn, cE, cwS, cwE, crec = summarize(LEDGER_CR, "积分")
                try:
                    pet_post("/anim", {"name": "余额-钱袋如常"}, pet="main")
                    pet_post("/broadcast",
                             {"text": "当前积分：%s" % cbal}, pet="main")
                except Exception:
                    pass
                time.sleep(2.0)
                text2 = "今日消耗 %.1f 分（%d 笔）" % (cS, cn)
                try:
                    pet_post("/broadcast", {"text": text2}, pet="main")
                except Exception:
                    pass
                log("积分两连发: %s | %s" % (cbal, text2[:60]))
                return self._send(200, json.dumps(
                    {"ok": True, "text": cbal, "text2": text2}, ensure_ascii=False))
            except Exception as e:
                return self._send(200, json.dumps({"ok": False, "reason": str(e)},
                                                  ensure_ascii=False))
        if self.path == "/report":
            try:
                bal, tS, n, tE, wS, wE, rec = summarize(LEDGER, "¥")
                cbal, cS, cn, cE, cwS, cwE, crec = summarize(LEDGER_CR, "积分")
                # 两连发：第一条=两本余额（同时报），第二条=两本今日收支
                t1 = "余额：【DeepSeek】%s｜【WorkBuddy】%s" % (bal, cbal)
                t2 = ("今日收支：【DeepSeek】支出 ¥%.2f（%d 笔）收入 ¥%.2f；"
                      "【WorkBuddy】消耗 %.1f 分（%d 笔）进账 %.1f 分") % (
                          tS, n, tE, cS, cn, cE)
                try:
                    pet_post("/anim", {"name": "余额-钱袋如常"}, pet="main")
                    pet_post("/broadcast", {"text": t1}, pet="main")
                except Exception:
                    pass
                time.sleep(2.0)
                try:
                    pet_post("/broadcast", {"text": t2}, pet="main")
                except Exception:
                    pass
                log("双轨汇报(2连发): %s | %s" % (t1, t2[:60]))
                return self._send(200, json.dumps(
                    {"ok": True, "text": t1, "text2": t2}, ensure_ascii=False))
            except Exception as e:
                return self._send(200, json.dumps({"ok": False, "reason": str(e)},
                                                  ensure_ascii=False))
        if self.path == "/send":
            try:
                n = int(self.headers.get("Content-Length", "0"))
                text = json.loads(self.rfile.read(n).decode("utf-8")).get("text", "").strip()
                if not text:
                    return self._send(200, '{"ok":false,"reason":"empty"}')
                resp = pet_post("/chat", {"text": text}, pet="main")
                if not resp.get("ok"):
                    return self._send(200, json.dumps(
                        {"ok": False, "reason": resp.get("message", "生成失败")},
                        ensure_ascii=False))
                time.sleep(1.5)
                with urllib.request.urlopen(BASE + "/state", timeout=5) as r:
                    st = json.loads(r.read())
                reply = st["pets"]["main"]["say"]["data"].get("text", "")
                return self._send(200, json.dumps({"ok": True, "reply": reply},
                                                  ensure_ascii=False))
            except Exception as e:
                log("对话失败: %r" % e)
                return self._send(200, json.dumps({"ok": False, "reason": str(e)},
                                                  ensure_ascii=False))
        self._send(404, '{"ok":false,"reason":"not-found"}')


def start_chat_server():
    srv = ThreadingHTTPServer(("127.0.0.1", CHAT_PORT), ChatHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log("对话页已就绪 http://127.0.0.1:%d/" % CHAT_PORT)


def main():
    acquire_singleton()

    key = read_key()
    if not key:
        log("apikey.txt 缺失，桥退出")
        return
    if not CRED:
        log("未找到 WorkBuddy 会话凭据——积分轨暂停（¥ 轨正常）")
    else:
        log("WorkBuddy 积分凭据来源: " + CRED_SRC)

    ready = False
    for _ in range(120):
        try:
            http_json("http://127.0.0.1:3080/health", timeout=3)
            ready = True
            break
        except Exception:
            time.sleep(1)
    if not ready:
        log("standalone 服务 120 秒内未就绪，桥退出")
        return

    try:
        start_chat_server()
    except OSError:
        log("对话端口被占，跳过")

    log("余额桥 v5 双轨启动（¥ %ds + 积分 %ds）" % (POLL_SEC, CRED_POLL_SEC))
    last = None
    cr_last = None
    fail = 0
    cred_fail = 0

    while True:
        try:
            http_json("http://127.0.0.1:3080/health", timeout=3)
        except Exception:
            log("standalone 已退出，桥跟着退出")
            return

        # 轨① ¥
        try:
            bal = query_balance(key)
            fail = 0
        except Exception as e:
            fail += 1
            if fail == 12:
                log("¥ 余额查询连续失败 1 分钟: %r" % e)
            bal = None
        if bal is not None:
            if last is None:
                text = "余额 ¥%.2f，两本账我都看着呢" % bal
                log(text)
                try:
                    pet_post("/broadcast", {"text": text}, pet="main")
                except Exception:
                    pass
                record(LEDGER, 0, bal, "real")
                last = bal
            elif bal < last:
                play_spend(last, bal)
                last = bal
            elif bal > last:
                play_topup(last, bal)
                last = bal

        # 轨② 积分
        if CRED:
            try:
                cr = meter_credits()
                cred_fail = 0
            except Exception as e:
                cred_fail += 1
                if cred_fail == 3:
                    log("积分查询连续失败: %r" % e)
                    try:
                        pet_post("/broadcast",
                                 {"text": "积分查不到了…主人去 WorkBuddy 重新登录下？"},
                                 pet="main")
                    except Exception:
                        pass
                cr = None
            if cr is not None:
                if cr_last is None:
                    text = "WorkBuddy 积分 %.0f，也归我管啦" % cr
                    log(text)
                    try:
                        pet_post("/broadcast", {"text": text}, pet="main")
                    except Exception:
                        pass
                    cr_last = cr
                elif cr < cr_last - 0.01:
                    play_credit_spend(cr_last, cr)
                    cr_last = cr
                elif cr > cr_last + TOPUP_MIN:
                    play_credit_topup(cr_last, cr)
                    cr_last = cr
                elif abs(cr - cr_last) > 0.01:
                    cr_last = cr

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
