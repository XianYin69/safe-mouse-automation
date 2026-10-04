# 使用指南

## 依赖安装

```bash
pip install Pillow websocket-client   # 截图 + CDP 浏览器通道
pip install uiautomation              # UIA 备用通道（实验性）
pip install pyautogui                 # 仅非 Windows 平台回退
```

## 缓存目录（红线：不写入 skill 目录）

- Windows `%LOCALAPPDATA%\safe-mouse-automation\`（screenshots\ 与 hud\ 子目录）；
  macOS `~/Library/Caches/`、Linux `~/.cache/` 同构路径；env `SAFE_MOUSE_CACHE` 可重定向。
- 查看当前缓存根：`python <SKILL_DIR>/scripts/screenshot_verify.py dir`

## HUD 会话（使用 skill 期间必须全程显示）

```bash
python <SKILL_DIR>/scripts/hud_overlay.py session "任务: 查询XX价格" 3600   # 任务开始，第一行常显
python <SKILL_DIR>/scripts/hud_overlay.py show "[2/5] 点击下一页" 20        # 每步更新第二行
python <SKILL_DIR>/scripts/hud_overlay.py hide                              # 仅任务整体结束
```

batch_runner 每步自动 `show`，并在**收口时（含异常收口）自动 hide**（`--keep-hud` 可保留浮窗继续观察，
此时仍须由调用方自行 hide）。浮窗置顶、点击穿透、不抢焦点；空闲 120s 显示进程自动退出。

## HUD 进程收口与孤儿回收（R4）

```bash
python <SKILL_DIR>/scripts/hud_overlay.py procs            # 取证：列出本技能全部 HUD 实例（pid/ppid/命令行）
python <SKILL_DIR>/scripts/hud_overlay.py hide             # 收口：清 state + 全量回收（含孤儿），返回 residual
python <SKILL_DIR>/scripts/hud_overlay.py reap             # 只打印“父进程已死”的本技能孤儿（默认 dry-run）
python <SKILL_DIR>/scripts/hud_overlay.py reap --yes       # 真终止这些孤儿
```

- `_run` 拉起时接收 `--parent=<pid>`（或环境变量 `SM_HUD_PARENT`），后台线程每 2s 判父活，
  父消失即自尽并清 pid/state 文件；取不到父 pid 时退回 TTL 兜底自尽（`SM_HUD_NO_PARENT_WATCH=1`
  可关父监控，仅用于测试人造孤儿）。
- `_ensure` 真单实例：按 state.json 的 `hud_pid` 收敛——在册实例存活则复用并终止多余实例；
  在册 pid 已死但仍有残留（pid 文件被覆盖而失踪）则先终止残留再拉新，保证并存数恒为 1。
- 验收：`hide`/`reap --yes` 之后 `procs` 必须为空，且
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` 里命令行含
  `safe-mouse-automation\scripts\hud_overlay.py _run` 的进程数＝0。

## 学习功能（操作前召回，成功后回写）

```bash
python <SKILL_DIR>/scripts/learn.py get [软件名]        # 召回已知路径/启动链（无参列出全部）
python <SKILL_DIR>/scripts/learn.py put <软件名> @rec.json   # 回写经验（JSON 从文件读，免转义）
python <SKILL_DIR>/scripts/learn.py note <软件名> "开始菜单是UWP，走桌面图标"   # 追加备注
python <SKILL_DIR>/scripts/learn.py del <软件名>
```

缓存优先写 `<SMS_HOME>/tmp/safe-mouse-automation/learn.json`（向 SMS 临时目录开放，SMS_HOME 解析
env > `%LOCALAPPDATA%\SMS`），不可写回退 `SAFE_MOUSE_CACHE/learn.json`；绝不落 skill 目录。
记录字段建议：`exe`（绝对路径）、`launch_chain`（怎么点开的）、`channel`（用的哪个通道）、`gui`/`verified`。

## 桌面软件纯鼠标通道（不用命令行启动）

```bash
python <SKILL_DIR>/scripts/desktop_ops.py windows                 # 列可见顶层窗口（验证用）
python <SKILL_DIR>/scripts/desktop_ops.py icons                   # 枚举桌面图标 + 真实屏幕坐标
python <SKILL_DIR>/scripts/desktop_ops.py open "此电脑"            # PostMessage 双击桌面图标
python <SKILL_DIR>/scripts/desktop_ops.py items "Shell"           # 列资源管理器窗口内的项
python <SKILL_DIR>/scripts/desktop_ops.py openitem "Shell" "syncthing-windows"   # 双击进入/运行
python <SKILL_DIR>/scripts/desktop_ops.py click <hwnd> <x> <y>    # 向任意窗口 PostMessage 单击
```

UIA 取真实屏幕矩形，向目标 SysListView32 PostMessage `WM_LBUTTONDBLCLK`（不动物理光标、不抢焦点）。
最小化的任务窗口自动 `SW_SHOWNOACTIVATE` 恢复。典型链：`open <桌面图标>` → `items <窗口>` →
`openitem <窗口> <子项>` 逐层进入，最后 `openitem <窗口> xxx.exe` 运行，再 `learn put` 记录。

## 应用界面通道（UIA 只读定位 → 坐标上模拟点击/打字）

```bash
python <SKILL_DIR>/scripts/app_ops.py controls "窗口标题子串" [n]   # 只读枚举 UIA 控件（名称/类型/矩形/screen_xy）
python <SKILL_DIR>/scripts/app_ops.py locate "窗口" "元素名"         # 只读解析元素 → 屏幕坐标（不做动作）
python <SKILL_DIR>/scripts/app_ops.py click "窗口" "元素名"          # 在该矩形中心发后台模拟点击
python <SKILL_DIR>/scripts/app_ops.py set "窗口" "输入框名" "文本"   # 先模拟点击聚焦，再后台打字（非 SetValue）
python <SKILL_DIR>/scripts/app_ops.py menus "窗口"                   # 只读枚举经典 Win32 菜单树
python <SKILL_DIR>/scripts/app_ops.py menu "窗口" "文件/打开"        # 逐级真实鼠标点击菜单条（不再 WM_COMMAND）
```

UIA 在本技能中**只读**（不需要前台/可见，被遮挡照常取到矩形）；动作一律落到矩形中心坐标发后台模拟鼠标/键盘事件，不再有 Invoke/SetValue/WM_COMMAND 之类捷径。
配合 learn：`learn op <软件名> <动作> '{"via":"input_ops.click","win":"记事本","element":"文件/打开"}'` 记录，
下次 `learn get <软件名>` 直接命中照做。

## 真人验证门禁（验证码/登录墙立即停止 + HUD 告警）

```bash
python <SKILL_DIR>/scripts/human_gate.py check "窗口标题子串"   # 检测窗口标题+UIA 文本，命中即停止+HUD alert
python <SKILL_DIR>/scripts/human_gate.py web --port=9224 --match=百度   # 检测浏览器页面正文
python <SKILL_DIR>/scripts/human_gate.py scan                  # 扫描全部可见窗口
python <SKILL_DIR>/scripts/human_gate.py clear                 # 清除 HUD 告警
```

命中时 HUD 显示红色⚠告警行（类型/证据/需用户操作），任务立即停止，等待用户手动完成后继续。
batch_runner `--guard=<窗口子串>` 每步自动检测，命中即中止。**绝不尝试绕过验证。**

## 统一输入后端（R2·本技能唯一动作出口）

```bash
python <SKILL_DIR>/scripts/input_ops.py click 960 540 left [--double]
python <SKILL_DIR>/scripts/input_ops.py double 960 540
python <SKILL_DIR>/scripts/input_ops.py rclick 960 540
python <SKILL_DIR>/scripts/input_ops.py drag 100 200 400 500
python <SKILL_DIR>/scripts/input_ops.py scroll 960 540 -3
python <SKILL_DIR>/scripts/input_ops.py type 960 540 你好 hello
python <SKILL_DIR>/scripts/input_ops.py key 960 540 "ctrl+shift+s"
python <SKILL_DIR>/scripts/input_ops.py click --win="无标题 - 记事本" "文本编辑器"   # 只读 UIA 解析坐标
python <SKILL_DIR>/scripts/input_ops.py resolve --win="窗口子串" "元素名"           # 只看坐标不动作
```

坐标一律为**屏幕物理像素**（与 screen-vision 的 `screen_xy` 同坐标系，`virtual_mouse` 导入时声明
per-monitor-v2 DPI 感知）。每次调用返回 `mode` 与 `focus_audit.before/after/unchanged`
（`GetForegroundWindow` / `GetCursorPos` / 键盘焦点），`focus_changed=true` 即为实现缺陷。
带 `--win` 时先只读 UIA 定位，再在该矩形中心发合成事件；给定 `hwnd` 时校验坐标命中的确是
目标窗口或其子窗口，否则 `refused:"ownership"` 拒绝投递（防误伤用户前台窗口）。

## 浏览器通道策略（R1·先用 browser_channel 定通道）

```bash
python <SKILL_DIR>/scripts/browser_channel.py policy          # 看四级顺序与禁令
python <SKILL_DIR>/scripts/browser_channel.py windows         # 只读枚举用户已运行的 Edge/Chrome 窗口
python <SKILL_DIR>/scripts/browser_channel.py plan            # 本次该走哪个通道（不启动进程）
python <SKILL_DIR>/scripts/browser_channel.py ensure <url>    # 按需执行（attach/已有端口时不启动）
```

顺序：**attach 用户已在跑的窗口**（真实 profile·已登录）→ 探测已开远调端口（9222/9223/9224）→
本技能专属**持久 profile**（`<SMS_HOME>/tmp/safe-mouse-automation/browser-profile`，登录一次长期记住）→
仅 `--ephemeral` 才一次性 profile。**绝不**默认 `%TEMP%` 空 profile，**绝不**反问用户为何没登录。

## attach 真实浏览器取文本（R5·`browser_ops.py grab`）

```bash
python <SKILL_DIR>/scripts/browser_ops.py dump "Edge" 40          # 只读枚举（修好：不再 elements=[]）
python <SKILL_DIR>/scripts/browser_ops.py grab "OAuth application settings"
python <SKILL_DIR>/scripts/browser_ops.py grab "OAuth" --copy      # 再后台 Ctrl+A/Ctrl+C 读剪贴板
python <SKILL_DIR>/scripts/browser_ops.py grab "OAuth" --grep=client --mask   # 写盘取证：token 全掩码
```

`grab` 是本技能**唯一取文本入口**：附着用户已在跑的真实窗口（R1，不新起进程/profile、绝不反问
"你为什么没登录"）→ 在 **TabItem** 矩形中心后台模拟点击切页（R2 合成鼠标）→ 等 Chromium a11y
懒加载（`lazy_wait` 回报 tries/seconds/named）→ **只读** UIA 取正文 → 单列疑似 token
（`ghp_`/`github_pat_`/`Iv1./Iv2.`/`Ov23li./Iv23li.`/`sk-`/32~40 位 hex + 标签邻近值）。
**明文只回 stdout，日志/链/落盘一律掩码（前6后4）**——要存档就带 `--mask`。
UIA 取不到时退 `screenshot_verify.py window <标题> <label>` + `ask <窗口> <问题>` 视觉读数并说明。

窗口被用户遮挡**不停止**：带 `hwnd` 的动作定向投递给目标窗口（`occluded_ok=True`，
回报 `occluded_by` 痕迹）；不带该标志时仍按 ownership 护栏 `refused:"ownership"` 拒绝。

## 剪贴板读回（R5·`clip_ops.py`，纯 ctypes）

```bash
python <SKILL_DIR>/scripts/clip_ops.py probe          # 自测：快照→写→读→还原
python <SKILL_DIR>/scripts/clip_ops.py list           # 当前剪贴板有哪些格式
python <SKILL_DIR>/scripts/clip_ops.py snapshot 取数前  # → {"id":"2026...-600"}
python <SKILL_DIR>/scripts/clip_ops.py read           # CF_UNICODETEXT / CF_HTML / CF_DIB
python <SKILL_DIR>/scripts/clip_ops.py restore last   # 归还用户原内容（必须做）
```

只用 user32/kernel32（`OpenClipboard(NULL)` 不关联窗口→不创建/切换前台），**绝不**借道
`powershell`/`clip.exe`/`Get-Clipboard`（属"任意命令执行"）。快照落
`%LOCALAPPDATA%\safe-mouse-automation\clip\`，不落 skill 目录；格式不可用/被占用/延迟渲染失效
一律有限重试后返回 `{"error":…}`，不抛栈。

## 浏览器后台通道（CDP 输入级模拟，抗遮挡）

```bash
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 open "https://example.com"
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example clickel "text=下一页"
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example click 400 300 left
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example scroll 640 400 800
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example type "搜索词"
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example key "ctrl+a"
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example eval "document.title"
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example eval "@script.js"   # JS 从文件读
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example shot label_before   # 页面级截图存证
```

CDP 的 `Input.dispatchMouseEvent` 是浏览器内核级模拟鼠标点击——**窗口被用户遮挡、不在前台、
未聚焦全部生效**，不移动物理光标、不抢焦点。`clickel` 支持 CSS 选择器与 `text=文本` 定位
（自动 scrollIntoView 后取矩形）。`open` 自动带 `--remote-allow-origins=*`（Edge 必须，否则 WS 403）。
`eval` 可直接从 DOM 提取数据（价格列表等），配合 `shot` 截图留痕。

## 批量流程（桌面 Win32 应用，默认后台虚拟输入）

```bash
python <SKILL_DIR>/scripts/batch_runner.py steps.json                 # 默认且仅默认走统一后台后端
python <SKILL_DIR>/scripts/batch_runner.py steps.json --real --consent=yes   # 前台兜底：必须显式带同意凭据
```

- 步骤文件为 JSON 数组（op: click/scroll/drag/move/type/key/shot），一次进程连续执行；
  type 步骤带 `"x","y","text"`（文本打到该坐标窗口内的焦点控件），key 步骤带 `"combo"`（如 `"ctrl+s"`）；
  HUD 自动 `show` 当前步骤（session 行需任务开始时自行开启）。
- `--real` 前台真输入回退（SendInput，**会打扰用户，须先取得同意**）；
  `--physical` pyautogui 非 Windows 回退；`--delay=0.15` 调步间间隔。
- Windows PowerShell 下内联 JSON 的双引号会被剥离：请先把步骤存为 steps.json 再传文件路径（脚本容忍 BOM）。

## 单步：后台虚拟输入（Win32 应用，不占物理光标、不抢焦点）

```bash
python <SKILL_DIR>/scripts/virtual_mouse.py click 500 300 left [--double]
python <SKILL_DIR>/scripts/virtual_mouse.py scroll 640 360 -3
python <SKILL_DIR>/scripts/virtual_mouse.py drag 100 200 400 500
python <SKILL_DIR>/scripts/virtual_mouse.py type 500 300 你好 hello
python <SKILL_DIR>/scripts/virtual_mouse.py key 500 300 "ctrl+shift+s"
```

PostMessage 直达坐标处窗口（键盘经 GetGUIThreadInfo 解析其焦点子控件）。
Chromium/Electron/DirectUI 类应用忽略合成消息——浏览器一律改用上面的 CDP 通道。

## 前台回退（须用户同意，会移动物理光标/改变焦点）

```bash
python <SKILL_DIR>/scripts/real_input.py click 500 300 left [--double]
python <SKILL_DIR>/scripts/real_input.py type "文本"
python <SKILL_DIR>/scripts/real_input.py key "ctrl+s"
```

`mouse_ops.py` 提供同命令并自动回退 pyautogui（非 Windows）。开发与自动化测试禁止使用前台通道，
应在自有隔离窗口（隐藏/offscreen 父窗口 + 标准控件）内用 PostMessage 直接验证。

## 截图与视觉验证（委托 screen-vision）

`screenshot_verify.py` 现为**纯委托层**：不含任何自研视觉代码，一律调 screen-vision 的脚本
（`sw.py` 截取 / `describe.py` 像素统计 / `recognize.py` 视觉识别）。旧自研 PrintWindow 抓窗口、
像素直方图比对、全屏抓取**均已废除**。

```bash
python <SKILL_DIR>/scripts/screenshot_verify.py window "无标题 - 记事本" t1   # → sw.py capture --title
python <SKILL_DIR>/scripts/screenshot_verify.py capture t0                 # → 顶层窗口（全屏已废除）
python <SKILL_DIR>/scripts/screenshot_verify.py compare <a> <b> [阈值]      # → describe.py 像素统计数值比对
python <SKILL_DIR>/scripts/screenshot_verify.py ask "无标题 - 记事本" "输入框里是什么"  # → recognize.py ask
python <SKILL_DIR>/scripts/screenshot_verify.py objects "无标题 - 记事本"   # → ask --structured
python <SKILL_DIR>/scripts/screenshot_verify.py dir
```

遮挡语义（务必知悉）：screen-vision 截的是**屏幕矩形像素**，窗口被遮挡时会把遮挡内容一起截进来，
它**没有全屏截取模式**；被遮挡时优先用 `browser_cdp.py shot`（页面级抗遮挡），或先
`browser_ops.py restore` / ShowWindow(SW_SHOWNOACTIVATE) 恢复窗口再截（不激活、不抢焦点），
也可改用 UIA / `eval` 取非像素证据——**不得因遮挡中止任务**。
`compare` 只做算术胶水：取 `describe.py` 的 mean_rgb / 灰度均值 / 标准差 / 8 分箱算归一化数值距离。
`objects`（契约 v2）里每个元素的 `screen_xy` 是屏幕物理像素绝对坐标，可直接喂 `virtual_mouse` 点击。
screen-vision 缺失时只报错（exit 1）并提示设 `SCREEN_VISION_HOME`，本技能不自动安装、不回退自研。

## 组合键注入（keycombo / real_input / mouse_ops·成对 down/up 红线）

**红线：注入必须成对 down/up。** 修饰键（Ctrl/Alt/Shift/Win）一旦发出 `KEYDOWN` 就**必须**在同一条
代码路径里发出配对的 `KEYUP`——只发 down 不补 up 会让用户键盘**像被重映射**（打字全变快捷键、
点击变拖拽），且用户自己无法自救。`real_input.press_keys` 为此有四道机制，缺一不可：

| 机制 | 实现 | 作用 |
|------|------|------|
| A 原子批 | `_fire_many` 一次 `SendInput` 发完整序列 `mods down → vk down → vk up → mods up 逆序` | 把「发了 down 没发 up」的窗口压到最小；硬杀（TerminateProcess）不跑回调，故这是**根治**手段 |
| B try/finally | `finally: _release_held(mods)`；`release_all_modifiers(dry=, keys=)` | 半批/异常路径补发仍未抬起的修饰键；`release` 命令即「救回用户键盘」 |
| C 前置守卫 | `released_stuck()` / `_pre_guard()`（`GetAsyncKeyState` 只读） | 注入**前**检出「非本进程发起」的粘滞修饰键，先释放再放行 |
| D 退出兜底 | `_install_exit_guards()`：`atexit` + `SIGINT/SIGTERM/SIGBREAK` | 退出/中断前释放本进程欠下的 KEYUP；只认 HELD 记账，**绝不**释放别人按下的键 |
HELD 记账：`_OUTSTANDING`＝本进程「已按下、尚未确认抬起」的修饰 vk，`_INJECTED_ANY`＝本进程是否发过
键盘事件；本进程从未注入过则退出兜底**完全不碰键盘**。右侧/扩展键（alt_r/ctrl_r/win_l/win_r/shift_r）
的 `KEYUP` 必须带 `KEXT`，否则释放不掉。用户自己正物理按住 Ctrl 时可设
env `SAFE_MOUSE_SKIP_STICK_GUARD=1` 跳过前置守卫（否则会把它当粘滞残留释放掉）。

`keycombo.py` 是**门面**：不含任何键表与解析逻辑，`MODS/BASE/SHIFT_NEEDED/MOD_KEYS/parse_combo/
vk_of/stuck_modifiers/release_all_modifiers/released_stuck` 全部**转发**自 `real_input`（唯一实现，
防两处逻辑漂移；`virtual_mouse.py` 亦经 `real_input.parse_combo` 共用同一解析）。

```bash
# 门面（默认零注入；release 例外，见下）
python <SKILL_DIR>/scripts/keycombo.py parse ctrl+shift+s   # 只读：down/up 计划 + 配对不变式
python <SKILL_DIR>/scripts/keycombo.py stuck                # 只读取证：当前按下态修饰键
python <SKILL_DIR>/scripts/keycombo.py release --dry        # 只报告 would_release（零注入）
python <SKILL_DIR>/scripts/keycombo.py release --yes    # 真补 KEYUP（前台 SendInput，须同意）
python <SKILL_DIR>/scripts/keycombo.py check                # 跨 real/virtual 干跑自检（零注入）
# 真注入（前台通道·须先征得用户同意）
python <SKILL_DIR>/scripts/real_input.py key "ctrl+shift+s"        # 原子批 + finally + 前置守卫
python <SKILL_DIR>/scripts/real_input.py key "ctrl+shift+s" --dry  # 只打印计划，injected=0
python <SKILL_DIR>/scripts/real_input.py key --release-all         # 全量补 up（不带组合键名）
python <SKILL_DIR>/scripts/real_input.py key --release-all --dry   # 只看 would_release 清单
python <SKILL_DIR>/scripts/real_input.py release [--dry]           # 同 release_all_modifiers
python <SKILL_DIR>/scripts/real_input.py mods                      # 只读按下态（零注入）
python <SKILL_DIR>/scripts/mouse_ops.py key "ctrl+s" [--dry]       # 透传：危险词门禁 + 委托 real_input
python <SKILL_DIR>/scripts/mouse_ops.py key --release-all [--dry]
python <SKILL_DIR>/scripts/mouse_ops.py release [--dry]            # 透传 release_all_modifiers
python <SKILL_DIR>/scripts/mouse_ops.py mods
```

**`--dry` 语义**：只读干跑——`injected=0`、不跑前置守卫、不碰用户键盘，打印的就是将要注入的序列
（down/up 计划与注入端**同源**，防「打印对、注入错」）。`check` 全绿＝两后端配对不变式成立且零注入。
**粘滞自救三步**（用户反馈「键盘像被重映射 / 快捷键乱触发 / 点图标变成拖拽」时）：
① `keycombo.py stuck`（或 `real_input.py mods`）**只读**确认哪些修饰键停在按下态；
② `keycombo.py release --dry` 看 `would_release` 清单，确认要补的是哪几个键；
③ **征得用户同意**后 `keycombo.py release --yes` 一次原子批补 `KEYUP`——补 up 属前台 SendInput，
**不得**未经同意默认执行；若清单里的键是用户**正物理按住**的，带 env
`SAFE_MOUSE_SKIP_STICK_GUARD=1` 或改由用户松手，别抢着释放。

**回归自检**：`python <SKILL_DIR>/scripts/keycombo.py check` 断言 11 例组合键
（含 `ctrl+alt+del` / `ctrl+=` / `win+d` / `ctrl+alt+shift+f12`）在 real 与 virtual 两后端
`paired=true`、`planned_real == planned_virtual`、`injected=0`，失败 exit 1；
与 `safety_gate.py focus-audit` 一样属改动后必跑项。

**`keycombo.py release` 的门禁（代码即文档）**：默认**只读**（等价 `--dry`，回报 `would_release`、
`injected:0`、`mode:"read-only"`）；**不带 `--yes` 一律不注入**，并回 `refused:"consent"` 与提示。
真释放须 `release --yes`（只补 KEYUP、**绝不**发 keydown，`keydown_sent:0` 恒成立），
`--scope=owned` 只还本进程在册键。脚本化调用一律**先 `--dry` 看清单、再经用户同意 `--yes`**。

**virtual 通道同样有守卫与成对兜底（R6 补充）**：`virtual_mouse.py key x y <combo> [--dry]` 注入前跑
`_release_stuck_in_window(h)`（只向**目标窗口** PostMessage 配对 KUP，**绝不** SendInput 物理注入，守 R3），
回报 `released_stuck`；投递失败由 `_post(..., cleanup=_kbd_release_pairs)` 按已投前缀补发全部 KUP；
`hwnd` 无效/已销毁**早退**并回报 `injected:0` + `reason:"hwnd 无效/已销毁 …（未注入任何按键）"`；
CLI 另有 `mods`（只读按下态）与 `release <hwnd> [--dry]`。
`real_input.py` 的 `--release-all` 是**全局**开关：`key` 子命令＝只释放不注入，其它子命令＝动作后
附带清粘滞（配 `--dry` 则纯只读）。粘滞探测表 `MOD_KEYS` 含 `0x5D apps`（共 12 键），
`MONITOR_VKS` 由它派生；`finally` 的兜底释放走 `_safe_release_keys()`，**绝不让释放动作二次抛错**
掩盖 SendInput 的原始异常。

## 与其他技能集成 / 注意事项

- 单一动作后端：PostMessage 合成鼠标/键盘（Win32）与 CDP `Input.dispatch*`（浏览器）；UIA **只读**定位；
  前台 SendInput 不属于后台路径，须用户显式同意（`--consent=`）才可用。
- 回归自检：`python <SKILL_DIR>/scripts/safety_gate.py focus-audit`（禁用 API 静态扫描，违规 exit 1）。
- 所有操作经 `safety_gate.py` 门禁；分辨率/多屏变化需重取坐标；`mouse_ops.py position` 仅读不写。
