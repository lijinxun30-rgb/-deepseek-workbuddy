[README.md](https://github.com/user-attachments/files/33661456/README.md)
# 融合版桌宠（DeepSeek + WorkBuddy）

两只 Windows 桌面宠物，共享一套"双账本"能力：同时盯着你的 **DeepSeek 余额（¥）** 和
**WorkBuddy 积分**，消费/充值/积分变动时播放不同动画和气泡，还能跟她聊天。

> 本仓库是**脱敏空白版**：不含任何 API Key、账本、日志。按下面步骤配置后即可使用。

## 两只宠物

| 目录 | 是什么 | 大脑 |
|---|---|---|
| `workbuddy-pet/` | PowerShell + WinForms 桌宠（Q版小女仆，桌面悬浮、右键菜单、音效、积分轮询、点击卖萌） | DeepSeek（对话）+ WorkBuddy 云脑（聊天页，扣积分） |
| `balance-pet/` | Electron 桌宠（dsh-pet 补丁版）：双轨余额轮询、四类事件四种演出、点击播报、双轨汇报 | DeepSeek（对话/碎碎念/余额官方接口） |

## 目录结构

```
workbuddy-pet/            ← PowerShell 桌宠（双击 启动WorkBuddy桌宠.vbs）
  dsh_pet.ps1             主程序（内嵌 C#）
  wb_chat_server.cjs      对话服务（WorkBuddy 云脑，端口 30812）
  wb_cloud_config.example.json ← 云脑配置模板（复制为 wb_cloud_config.json 后填写）
  sprite.png / ico / mp3  素材

balance-pet/              ← Electron 余额桌宠（双击 启动余额桌宠.vbs）
  启动余额桌宠.vbs        启动器（强制冷重启 + 自动拉起桥）
  balance_bridge.py       Python 桥（端口 30802：余额/积分轮询、记账、演出、菜单后端）
  patch_standalone.py     给 npm 安装的 dsh-pet 打补丁（对话脑/菜单/点击播报）
  apikey.txt.example      DeepSeek Key 模板（复制为 apikey.txt 后填写）
```

## 安装步骤

### 0. 依赖
- Windows 10/11
- [Node.js](https://nodejs.org)（WorkBuddy 用户可直接用托管 node）
- Python 3.8+（跑桥，仅标准库）
- `npm i -g dsh-pet`（Electron 桌宠本体，来自 npm）

### 1. 余额桌宠（balance-pet）
```powershell
# 1) 把 balance-pet 文件夹放到 D:\dsh-pet（脚本按此路径读写账本）
# 2) 填 DeepSeek Key
copy apikey.txt.example apikey.txt   # 编辑，粘贴你的 sk- 开头 Key
# 3) 打补丁（每次 npm 升级 dsh-pet 后重跑）
python patch_standalone.py
# 4) 双击 启动余额桌宠.vbs
```

### 2. WorkBuddy 桌宠（workbuddy-pet）
```powershell
# 1) 双击 启动WorkBuddy桌宠.vbs 即可跑基础功能（积分轮询/演示/设置）
# 2) 对话功能：需要 WorkBuddy 云脑配置
copy wb_cloud_config.example.json wb_cloud_config.json
#    编辑，填入你的云应用 endpoint + publishableKey（WorkBuddy 云服务创建应用后可得）
```

### 3. 断账数据
首次运行后会自动生成 `ledger.json` / `ledger_credits.json` / `state.ini` 等，
这些都已在 `.gitignore` 里，**不要提交**。

## 功能一览

- **四类事件四种演出**：¥扣费→吃Token / ¥充值→收红包 / 积分消耗→忙碌点按 / 积分增加→拆礼物
- **点击宠物身体**：两连发播报（第一条两本余额，第二条今日收支）
- **右键菜单**：收支汇报 / WorkBuddy▸（积分汇报两连发、测试积分消耗/增加、查积分）/ 对话 / 演示 / 设置
- **对话**：带真实账本档案 + 多轮记忆，能答"今天花了多少"
- **积分轮询**：WorkBuddy 官方 meter 接口，凭据自动从本机 WorkBuddy 会话取

## 隐私

所有凭据（DeepSeek Key、云脑 publishableKey、WorkBuddy 会话 Cookie）都只存在
本地文件里（`apikey.txt` / `wb_cloud_config.json`），已被 `.gitignore` 排除，请勿提交或分享。

## 许可

本项目代码部分按 MIT 发布。`dsh-pet` 本体为独立 npm 包，版权归其原作者，遵循其自身许可。
