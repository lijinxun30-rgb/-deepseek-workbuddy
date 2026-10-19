# -*- coding: utf-8 -*-
"""
patch_standalone.py — 给 dsh-pet 的 lib/standalone.js 注入 DeepSeek 能力
（对话/碎碎念走 deepseek-chat；余额走官方接口；凭据读 D:/dsh-pet/apikey.txt）

幂等：已打过补丁则跳过；有 .orig 备份则始终从 .orig 重新打（保证可重复）。
npm 升级 dsh-pet 后重跑本脚本即可。
"""
import shutil
import sys
import os

def _find_nm():
    """自动定位 WorkBuddy 托管 node 的全局 node_modules（含 dsh-pet 的最新版本）。"""
    root = os.path.join(os.path.expanduser('~'), '.workbuddy', 'binaries', 'node', 'versions')
    if not os.path.isdir(root):
        raise SystemExit('未找到 WorkBuddy 托管 node 目录: ' + root)
    for v in sorted(os.listdir(root), reverse=True):
        cand = os.path.join(root, v, 'node_modules')
        if os.path.isdir(os.path.join(cand, 'dsh-pet')):
            return cand.replace('\\', '/')
    raise SystemExit('未找到已安装的 dsh-pet，请先安装: npm i -g dsh-pet')


NM = _find_nm()

TARGET = NM + '/node_modules/dsh-pet/lib/standalone.js'
ORIG = TARGET + '.orig'
MARK = '/*__DSH_PET_BRIDGE_PATCH__*/'

ANCHOR_AGENT = (
    'agentDefaultModel: { currentSelection: () => ({\n'
    '\t\t\tprovider: STANDALONE_PROVIDER,\n'
    '\t\t\tmodel: ""\n'
    '\t\t}) },'
)
REPL_AGENT = (
    'agentDefaultModel: { currentSelection: () => ({\n'
    '\t\t\tprovider: "deepseek-official",\n'
    '\t\t\tmodel: "deepseek-chat"\n'
    '\t\t}) }, ' + MARK
)

ANCHOR_CRED = 'credentials: { resolve: async () => void 0 },'
REPL_CRED = (
    'credentials: { resolve: async (ref) => {\n'
    '\t\t\ttry {\n'
    '\t\t\t\tconst v = readFileSync("D:/dsh-pet/apikey.txt", "utf8").trim();\n'
    '\t\t\t\tif (v.startsWith("sk-")) return { value: v };\n'
    '\t\t\t} catch (e) {}\n'
    '\t\t\treturn void 0;\n'
    '\t\t} }, ' + MARK
)

ANCHOR_LLM = (
    'llm: {\n'
    '\t\t\tlistProviders: () => [],\n'
    '\t\t\tlistModels: async () => [],\n'
    '\t\t\tresolveModelInfo: async () => void 0,\n'
    '\t\t\tstream: () => ({ [Symbol.asyncIterator]() {\n'
    '\t\t\t\treturn { next: async () => {\n'
    '\t\t\t\t\tthrow new Error("dsh-pet standalone: 独立模式未接入模型（碎碎念/对话不可用）");\n'
    '\t\t\t\t} };\n'
    '\t\t\t} })\n'
    '\t\t}'
)
REPL_LLM = (
    'llm: {\n'
    '\t\t\tlistProviders: () => ["deepseek-official"],\n'
    '\t\t\tlistModels: async () => ["deepseek-chat"],\n'
    '\t\t\tresolveModelInfo: async () => void 0,\n'
    '\t\t\tstream: (options) => {\n'
    '\t\t\t\tlet key = "";\n'
    '\t\t\t\ttry { key = readFileSync("D:/dsh-pet/apikey.txt", "utf8").trim(); } catch (e) {}\n'
    '\t\t\t\tif (!key.startsWith("sk-")) return { [Symbol.asyncIterator]() { return { next: async () => { throw new Error("dsh-pet-bridge: 未找到 DeepSeek API Key（D:/dsh-pet/apikey.txt）"); } }; } };;\n'
    '\t\t\t\tconst msgs = [];\n'
    '\t\t\t\tlet sys = options.system ? String(options.system) : "你是主人桌面上的Q版蓝发小女仆。说话自然、俏皮、简短，不要啰嗦，不要解释你自己，不要提你是AI。";\n'
    '\t\t\t\ttry {\n'
    '\t\t\t\t\tconst lg = JSON.parse(readFileSync("D:/dsh-pet/ledger.json", "utf8"));\n'
    '\t\t\t\t\tconst dk = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");\n'
    '\t\t\t\t\tconst nowD = new Date(), today = dk(nowD), week = nowD.getTime() - 6048e5;\n'
    '\t\t\t\t\tlet tS = 0, tE = 0, tN = 0, wS = 0, wE = 0;\n'
    '\t\t\t\t\tconst real = (lg.entries || []).filter((e) => e.kind !== "demo");\n'
    '\t\t\t\t\tfor (const e of real) {\n'
    '\t\t\t\t\t\tconst d = new Date(e.ts);\n'
    '\t\t\t\t\t\tif (dk(d) === today) { if (e.delta < 0) { tS -= e.delta; tN++; } else tE += e.delta; }\n'
    '\t\t\t\t\t\tif (d.getTime() >= week) { if (e.delta < 0) wS -= e.delta; else wE += e.delta; }\n'
    '\t\t\t\t\t}\n'
    '\t\t\t\t\tconst bal = lg.lastBalance != null ? "¥" + Number(lg.lastBalance).toFixed(2) : "未知";\n'
    '\t\t\t\t\tconst recent = (lg.entries || []).slice(-8).reverse().map((e) => {\n'
    '\t\t\t\t\t\tconst d = new Date(e.ts);\n'
    '\t\t\t\t\t\treturn dk(d) + " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0") + (e.delta < 0 ? " 扣 " : " 充 +") + Math.abs(e.delta).toFixed(2) + (e.kind === "demo" ? "(演示)" : "");\n'
    '\t\t\t\t\t}).join("；");\n'
    '\t\t\t\t\tsys += "\\n\\n[收支档案]当前余额:" + bal + "\\n今日:支出¥" + tS.toFixed(2) + "(" + tN + "笔) 收入¥" + tE.toFixed(2) + "\\n近7天:支出¥" + wS.toFixed(2) + " 收入¥" + wE.toFixed(2) + (recent ? "\\n最近记录:" + recent : "\\n最近无收支记录") + "\\n(回答涉及钱的问题时用这些数据，口语化报数；演示笔数不算真实收支)";\n'
    '\t\t\t\t} catch (e) {}\n'
    '\t\t\t\ttry {\n'
    '\t\t\t\t\tconst cg = JSON.parse(readFileSync("D:/dsh-pet/ledger_credits.json", "utf8"));\n'
    '\t\t\t\t\tconst dk2 = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");\n'
    '\t\t\t\t\tconst nowD2 = new Date(), today2 = dk2(nowD2), week2 = nowD2.getTime() - 6048e5;\n'
    '\t\t\t\t\tlet cS = 0, cE = 0, cN = 0, cwS = 0, cwE = 0;\n'
    '\t\t\t\t\tconst creal = (cg.entries || []).filter((e) => e.kind !== "demo");\n'
    '\t\t\t\t\tfor (const e of creal) {\n'
    '\t\t\t\t\t\tconst d = new Date(e.ts);\n'
    '\t\t\t\t\t\tif (dk2(d) === today2) { if (e.delta < 0) { cS -= e.delta; cN++; } else cE += e.delta; }\n'
    '\t\t\t\t\t\tif (d.getTime() >= week2) { if (e.delta < 0) cwS -= e.delta; else cwE += e.delta; }\n'
    '\t\t\t\t\t}\n'
    '\t\t\t\t\tconst cbal = cg.lastBalance != null ? Number(cg.lastBalance).toFixed(1) + " 积分" : "未知";\n'
    '\t\t\t\t\tconst crec = (cg.entries || []).slice(-5).reverse().map((e) => {\n'
    '\t\t\t\t\t\tconst d = new Date(e.ts);\n'
    '\t\t\t\t\t\treturn dk2(d) + " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0") + (e.delta < 0 ? " 耗 " : " 增 +") + Math.abs(e.delta).toFixed(1);\n'
    '\t\t\t\t\t}).join("；");\n'
    '\t\t\t\t\tsys += "\\n\\n[WorkBuddy积分档案]当前:" + cbal + "\\n今日消耗" + cS.toFixed(1) + "分(" + cN + "笔)" + "\\n(WorkBuddy 积分和 DeepSeek 余额是两本独立的账，回答时别混单位)";\n'
    '\t\t\t\t} catch (e) {}\n'
    '\t\t\t\tmsgs.push({ role: "system", content: sys });\n'
    '\t\t\t\tfor (const m of options.messages || []) {\n'
    '\t\t\t\t\tconst t = (m.content || []).map((c) => (c && c.text) || "").join("");\n'
    '\t\t\t\t\tif (t) msgs.push({ role: m.role === "assistant" ? "assistant" : "user", content: t });\n'
    '\t\t\t\t}\n'
    '\t\t\t\treturn { [Symbol.asyncIterator]() {\n'
    '\t\t\t\t\tlet sent = false;\n'
    '\t\t\t\t\treturn { next: async () => {\n'
    '\t\t\t\t\t\tif (sent) return { done: true };\n'
    '\t\t\t\t\t\tsent = true;\n'
    '\t\t\t\t\t\tconst res = await fetch("https://api.deepseek.com/chat/completions", {\n'
    '\t\t\t\t\t\t\tmethod: "POST",\n'
    '\t\t\t\t\t\t\theaders: { "Content-Type": "application/json", Authorization: "Bearer " + key },\n'
    '\t\t\t\t\t\t\tbody: JSON.stringify({ model: "deepseek-chat", messages: msgs, temperature: options.temperature == null ? 0.8 : options.temperature, max_tokens: 500, stream: false }),\n'
    '\t\t\t\t\t\t\tsignal: options.signal\n'
    '\t\t\t\t\t\t});\n'
    '\t\t\t\t\t\tif (!res.ok) throw new Error("deepseek chat HTTP " + res.status);\n'
    '\t\t\t\t\t\tconst data = await res.json();\n'
    '\t\t\t\t\t\tconst text = data && data.choices && data.choices[0] && data.choices[0].message ? String(data.choices[0].message.content || "") : "";\n'
    '\t\t\t\t\t\tif (!text) throw new Error("deepseek chat 返回为空");\n'
    '\t\t\t\t\t\treturn { done: false, value: { type: "text", text } };\n'
    '\t\t\t\t\t} };\n'
    '\t\t\t\t} };\n'
    '\t\t\t}\n'
    '\t\t}, ' + MARK
)


def main():
    ok = patch_standalone()
    ok2 = patch_sprite_menu()
    ok3 = patch_helper_gpu()
    sys.exit(0 if (ok and ok2 and ok3) else 1)


HELPER = NM + '/node_modules/dsh-pet/runtime/electron-helper/main.js'
HELPER_ORIG = HELPER + '.orig'
HELPER_MARK = '/*__DSH_PET_GPU_FALLBACK__*/'

ANCHOR_GPU = "app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');"
REPL_GPU = (
    ANCHOR_GPU + "\n" +
    HELPER_MARK + " app.commandLine.appendSwitch('enable-unsafe-swiftshader');"
    " // GPU 崩溃时允许软件渲染回退\n" +
    HELPER_MARK + " app.commandLine.appendSwitch('in-process-gpu');"
    " // GPU 内嵌主进程：消灭独立 GPU 进程（安全软件注入 DLL 使其必崩 0xC0000005）\n" +
    HELPER_MARK + " app.commandLine.appendSwitch('disable-gpu-sandbox');"
    " // GPU 无沙箱：防注入冲突"
)


def patch_helper_gpu():
    """Electron v43：GPU 进程崩溃不再自动回退软件渲染 -> 'GPU process isn't usable. Goodbye.'
    打开 enable-unsafe-swiftshader 恢复回退，GPU 驱动抽风时宠物窗口仍能显示。"""
    if not os.path.exists(HELPER_ORIG):
        shutil.copy2(HELPER, HELPER_ORIG)
        print('已备份 -> main.js.orig')
    src = open(HELPER_ORIG, encoding='utf-8').read()
    if src.count(ANCHOR_GPU) != 1:
        print('main.js 锚点异常（gpu=%d），dsh-pet 版本可能变了，跳过' % src.count(ANCHOR_GPU))
        return False
    out = src.replace(ANCHOR_GPU, REPL_GPU, 1)
    with open(HELPER, 'w', encoding='utf-8', newline='') as f:
        f.write(out)
    print('main.js patch 完成：GPU 软件渲染回退已开启')
    return True


SPRITE = NM + '/node_modules/dsh-pet/runtime/electron-helper/sprite.js'
SPRITE_ORIG = SPRITE + '.orig'
SPRITE_MARK = '/*__DSH_PET_QUIT_MENU__*/'

ANCHOR_TOOLS = "      { label: '重载配置', action: 'reload' },\n    );"
REPL_TOOLS = (
    "      { label: '重载配置', action: 'reload' },\n"
    "      " + SPRITE_MARK + " { label: '退出', action: 'quit-app' },\n    );"
)

ANCHOR_BAL = "if (this.pet.balanceEnabled) tools.push({ label: '查看余额', action: 'show-balance' });"
REPL_BAL = (
    ANCHOR_BAL + "\n"
    "    " + SPRITE_MARK + " tools.push({ label: '吃Token', action: 'demo-spend' }, { label: '收红包', action: 'demo-topup' });\n"
    "    " + SPRITE_MARK + " tools.push({ label: 'WorkBuddy', children: [\n"
    "      { label: '积分汇报', action: 'wb-report' },\n"
    "      { label: '测试积分消耗', action: 'wb-demo-spend' },\n"
    "      { label: '测试积分增加', action: 'wb-demo-topup' },\n"
    "      { label: '查积分', action: 'wb-report' }] });"
)

ANCHOR_ACT = "    if (!leaf.anim) return;"
REPL_ACT = (
    "    if (leaf.action === 'quit-app') {\n"
    "      " + SPRITE_MARK + " fetch('http://127.0.0.1:3080/shutdown', { method: 'POST', mode: 'no-cors' }).catch(() => {});\n"
    "      return;\n"
    "    }\n"
    "    if (leaf.action === 'demo-spend' || leaf.action === 'demo-topup') {\n"
    "      " + SPRITE_MARK + " fetch('http://127.0.0.1:30802/demo', { method: 'POST', mode: 'no-cors', body: JSON.stringify({ type: leaf.action === 'demo-spend' ? 'spend' : 'topup' }) }).catch(() => {});\n"
    "      return;\n"
    "    }\n"
    "    if (leaf.action === 'wb-report') {\n"
    "      " + SPRITE_MARK + " fetch('http://127.0.0.1:30802/wb-report', { method: 'POST', mode: 'no-cors' }).catch(() => {});\n"
    "      return;\n"
    "    }\n"
    "    if (leaf.action === 'report') {\n"
    "      " + SPRITE_MARK + " fetch('http://127.0.0.1:30802/report', { method: 'POST', mode: 'no-cors' }).catch(() => {});\n"
    "      return;\n"
    "    }\n"
    "    if (leaf.action === 'wb-demo-spend' || leaf.action === 'wb-demo-topup') {\n"
    "      " + SPRITE_MARK + " fetch('http://127.0.0.1:30802/demo', { method: 'POST', mode: 'no-cors', body: JSON.stringify({ type: leaf.action === 'wb-demo-spend' ? 'credit-spend' : 'credit-topup' }) }).catch(() => {});\n"
    "      return;\n"
    "    }\n"
    "    if (!leaf.anim) return;"
)

# ---- 点击宠物身体（等价“点耳朵”）→ 自动播报双账（DeepSeek ¥ + WorkBuddy 积分）----
# 锚点：onClick 内点击动画前那一行（orig 唯一）。耳朵单独热区因精灵动画/位移会漂，
# 不可靠；点身体是等价的稳健手势，且最好 QA。保留原点击卖萌动画。
CLICK_MARK = '/*__DSH_PET_CLICK_REPORT__*/'
ANCHOR_CLICK = "    this.pendingSquash = true; // 等新点击动画切到前台后 Q 弹（压新首帧，与浏览器一致）"
REPL_CLICK = (
    ANCHOR_CLICK + "\n"
    "    " + CLICK_MARK + " try { fetch('http://127.0.0.1:30802/report', { method: 'POST', mode: 'no-cors' }).catch(function(){}); } catch (e) {}\n"
)


def patch_sprite_menu():
    """桌宠右键菜单加「退出」：host POST /shutdown，桥跟退，Electron 窗随 effect 关闭"""
    if not os.path.exists(SPRITE_ORIG):
        shutil.copy2(SPRITE, SPRITE_ORIG)
        print('已备份 -> sprite.js.orig')
    src = open(SPRITE_ORIG, encoding='utf-8').read()
    if src.count(ANCHOR_TOOLS) != 1 or src.count(ANCHOR_ACT) != 1 or src.count(ANCHOR_BAL) != 1 or src.count(ANCHOR_CLICK) != 1:
        print('sprite.js 锚点异常（tools=%d, act=%d, bal=%d, click=%d），dsh-pet 版本可能变了，跳过' % (
            src.count(ANCHOR_TOOLS), src.count(ANCHOR_ACT), src.count(ANCHOR_BAL), src.count(ANCHOR_CLICK)))
        return False
    out = (src.replace(ANCHOR_TOOLS, REPL_TOOLS, 1)
              .replace(ANCHOR_BAL, REPL_BAL, 1)
              .replace(ANCHOR_ACT, REPL_ACT, 1)
              .replace(ANCHOR_CLICK, REPL_CLICK, 1))
    with open(SPRITE, 'w', encoding='utf-8', newline='') as f:
        f.write(out)
    print('sprite.js patch 完成：右键菜单新增「退出」+ 点击宠物身体播报双账')
    return True


def patch_standalone():
    if not os.path.exists(ORIG):
        shutil.copy2(TARGET, ORIG)
        print('已备份原文件 -> standalone.js.orig')
    src = open(ORIG, encoding='utf-8').read()

    if MARK in src and ANCHOR_AGENT not in src:
        print('看起来已经打过补丁（从 .orig 重打以保证干净）')

    n = src.count(ANCHOR_AGENT) + src.count(ANCHOR_CRED) + src.count(ANCHOR_LLM)
    if n != 3:
        print('锚点命中数 = %d（应为 3），dsh-pet 版本可能变了，终止' % n)
        sys.exit(1)

    out = src.replace(ANCHOR_AGENT, REPL_AGENT, 1)
    out = out.replace(ANCHOR_CRED, REPL_CRED, 1)
    out = out.replace(ANCHOR_LLM, REPL_LLM, 1)

    assert out.count(MARK) >= 3
    with open(TARGET, 'w', encoding='utf-8', newline='') as f:
        f.write(out)
    print('patch 完成：')
    print('  - 对话/碎碎念 -> deepseek-chat（读 D:/dsh-pet/apikey.txt）')
    print('  - 余额 -> deepseek-official 官方接口（凭据同上）')
    print('  - 备份在 standalone.js.orig，重跑本脚本可恢复重打')


if __name__ == '__main__':
    main()
