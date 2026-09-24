# safe-mouse-automation

**后台桌面自动化 skill**：通过 Python 脚本模拟鼠标与键盘操作，截图确认结果，全程不移动物理光标、
不抢焦点、不打扰前台用户。支持桌面 Win32 应用、浏览器（Edge/Chrome）、以及验证码/登录墙自动检测停止。

## 核心能力

| 通道 | 脚本 | 适用场景 | 特点 |
|------|------|----------|------|
| PostMessage 虚拟输入 | `virtual_mouse.py` | 桌面 Win32 应用 | 不动物理光标、不抢焦点 |
| CDP 浏览器通道 | `browser_cdp.py` | Edge/Chrome | 内核级模拟鼠标点击，抗遮挡，可 eval 取数据 |
| 桌面软件鼠标通道 | `desktop_ops.py` | 打开/定位桌面软件 | 枚举桌面图标/资源管理器项，PostMessage 双击，不用命令行 |
| 应用直接操作 | `app_ops.py` | 操作应用界面 | UIA 枚举控件/Invoke/SetValue + 经典菜单 WM_COMMAND 零鼠标 |
| 真人验证门禁 | `human_gate.py` | 验证码/登录墙检测 | 命中即停止任务 + HUD 红色⚠告警，绝不绕过验证 |
| 学习功能 | `learn.py` | 软件路径/操作经验 | 操作前召回、成功后回写，缓存存 SMS 临时目录 |
| HUD 会话浮窗 | `hud_overlay.py` | 全程任务提示 | 置顶/穿透/不抢焦点，session+step+alert 三行 |
| 批量执行 | `batch_runner.py` | 高速多步操作 | 单进程跑完步骤清单，支持 `--guard` 每步验证门禁 |
| 安全门禁 | `safety_gate.py` | 危险操作拦截 | 文件删除/格式化/注册表/关机/杀命令一律拒绝 |
| 截图验证 | `screenshot_verify.py` | 前后态比对 | PrintWindow 抗遮挡截图 + 像素差异比对 |
| 前台回退 | `real_input.py` | 应用忽略虚拟消息时 | SendInput 真输入，**须先征得用户同意** |

## 安装

```bash
pip install Pillow uiautomation websocket-client
# pyautogui 仅非 Windows 平台回退需要
```

## 快速开始

```bash
# 1. 开启 HUD 会话
python scripts/hud_overlay.py session "任务: 查询商品价格" 3600

# 2. 打开浏览器并搜索（CDP 后台，不碰物理光标）
python scripts/browser_cdp.py --port=9224 open "https://example.com"
python scripts/browser_cdp.py --port=9224 --match=example clickel "text=搜索"

# 3. 检测验证墙（命中即停止 + HUD 告警）
python scripts/human_gate.py web --port=9224 --match=example

# 4. 提取页面数据
python scripts/browser_cdp.py --port=9224 --match=example eval "document.title"

# 5. 截图验证
python scripts/screenshot_verify.py capture before
python scripts/screenshot_verify.py window "窗口标题" after
python scripts/screenshot_verify.py compare <before> <after>

# 6. 学习回写 + 结束
python scripts/learn.py put example '{"exe":"...","launch_chain":"...","channel":"cdp"}'
python scripts/hud_overlay.py hide
```

## 安全约束（铁律）

- **真人验证必停**：检测到验证码/人机验证/登录墙时立即停止任务，HUD 显示详细信息，等待用户手动完成；绝不绕过。
- **后台优先**：所有输入/截图默认走 PostMessage/CDP/UIA/WM_COMMAND 后台通道；不得自行 `SetForegroundWindow`。
- **前台需同意**：仅当虚拟消息被忽略且截图验证无变化时，征得用户同意后才可用 `real_input.py`（SendInput）。
- **危险操作拒绝**：文件删除、格式化、注册表修改、系统服务变更、任意 shell 命令一律拒绝。
- **缓存外置**：截图/HUD 状态/学习记录等缓存不得写入 skill 目录，一律落用户缓存或 SMS 临时目录。

## 运行时约定

- 脚本以 `python <SKILL_DIR>/scripts/<name>.py` 调用。
- 缓存根：`%LOCALAPPDATA%\safe-mouse-automation\`（Windows），env `SAFE_MOUSE_CACHE` 覆盖。
- 学习缓存：`<SMS_HOME>/tmp/safe-mouse-automation/learn.json`（SMS_HOME 解析 env > `%LOCALAPPDATA%\SMS`）。
- 浏览器 CDP 启动：`msedge --user-data-dir=<临时> --remote-debugging-port=<port> --remote-allow-origins=* --no-first-run <url>`。

## 依赖

- `Pillow`（截图）、`uiautomation`（UIA 桌面操作）、`websocket-client`（CDP 浏览器通道）
- `pyautogui`（仅非 Windows 平台回退）
- 虚拟输入/HUD 为纯标准库（ctypes/tkinter）

## License

MIT
