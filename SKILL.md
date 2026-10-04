---
name: safe-mouse-automation
description: >
  通过 Python 脚本在后台模拟鼠标与键盘操作用户电脑，截图确认操作结果；一切动作经**统一输入后端**
  input_ops.py 发出合成事件（Win32＝PostMessage 鼠标/键盘，浏览器＝CDP Input.dispatch*），
  不移动物理光标、不抢焦点、不打扰前台，含点击/滚轮/拖拽与打字/快捷键；UIA 仅用于**只读**枚举定位，
  不再有 Invoke/SetValue/WM_COMMAND 之类动作捷径；浏览器优先**附着用户已经在跑的真实浏览器窗口**
  （已登录、带收藏扩展），其次探测已开远调端口，再次本技能专属**持久 profile**，
  绝不默认 %TEMP% 空 profile、绝不反问用户为何没登录；桌面软件走 desktop_ops 纯鼠标双击
  （枚举桌面图标/资源管理器项，不用命令行启动）；学习功能 learn 把软件路径/启动链沉淀到
  SMS 临时目录，操作前召回成功后回写；
  HUD 浮窗全程置顶提示任务信息（置顶/穿透/不抢焦点）；SendInput 前台真输入为征得同意后的回退；
  批量执行加快整体流程；内置安全门禁禁止危险操作，缓存不落 skill 目录；屏幕视觉（窗口枚举/
  截取/视觉识别/像素统计）一律委托 screen-vision 技能，本技能不含自研视觉实现。
license: MIT
metadata:
  category: automation
---

使用 `safe-mouse-automation` skill 来完成用户请求。

# Safe Mouse Automation

**一切操作默认在后台执行，绝不打扰前台用户**：**虚拟输入**（PostMessage 鼠标+键盘，不移动物理
光标、不抢焦点、不改变前台窗口）配合 **CDP 浏览器通道**（`browser_cdp.py` 内核级模拟鼠标点击/打字，
被遮挡/非前台照常生效）、**桌面软件鼠标通道**（`desktop_ops.py` 枚举桌面图标/资源管理器项并 PostMessage
双击打开，纯鼠标定位不用命令行）、**应用界面通道**（`app_ops.py` UIA **只读**枚举定位 → 在该矩形坐标发模拟点击/打字，
不再有 Invoke/SetValue/WM_COMMAND 捷径）、**统一输入后端**（`input_ops.py`＝本技能唯一动作出口，自带焦点前后审计）、**学习功能**（`learn.py` 把"软件在哪、怎么操作"沉淀到
SMS 临时目录，操作前召回免重复探索）、**真人验证门禁**（`human_gate.py` 检测验证码/登录墙立即停止
并在 HUD 显示详细信息）配合 **HUD 会话浮窗**（全程置顶显示任务简述+当前步骤）与**批量执行**。
仅当目标应用忽略合成消息且截图验证无变化时，**征得用户同意后**才可用 `real_input.py`（SendInput）前台回退。

## 1. 工作流程

1. **识别意图 + 学习召回**：确定目标操作；先 `learn.py get <软件名>` 召回已知路径/启动链/操作方式，
   命中则直接照做（免重复探索）。优先编排为步骤清单（`scripts/batch_runner.py` 一次进程跑完）。
2. **安全检查**：每步经过 [`scripts/safety_gate.py`](scripts/safety_gate.py) 门禁——
   危险操作（文件删除、系统修改、注册表写入、任意 shell 命令）一律拒绝并报告用户。
3. **HUD 会话开启**：任务开始即 `hud_overlay.py session <任务简述> [ttl]`（默认 30 分钟，全程常显）；
   每步 `hud_overlay.py show <步骤>` 更新第二行；**仅任务整体结束才 `hide`**——`hide` 现除清 state 外还
   **全量回收本技能 HUD 进程（含孤儿）**并返回 `residual`（必须为 0）；`batch_runner` 在收口时（含异常
   收口）**自动调用 hide**，派发对话收口前须补一次 `hud_overlay.py reap --yes` 兜底清残留（R4）。
4. **截图记录前态**：[`scripts/screenshot_verify.py`](scripts/screenshot_verify.py) 现为**纯委托层**
   （内部调 screen-vision，无自研视觉）：`window <标题子串> [label]` 抓指定窗口（→ `sw.py capture --title`）、
   `capture [label]` 抓 z-order 顶层窗口（→ `sw.py capture --index`，**全屏抓取已废除**，要指定目标用 `window`）。
   浏览器仍用 `browser_cdp.py shot`（页面级截图，抗遮挡）。
5. **后台执行操作**：
   - **统一输入后端（R2·本技能唯一动作出口，首选）**：[`scripts/input_ops.py`](scripts/input_ops.py)
     `click/double/rclick/move/drag/scroll/type/key`——坐标或 `--win=<窗口> <元素名>`（只读 UIA 解析坐标），
     每次调用回报 `mode` 与 `focus_audit`（前台窗口/物理光标/键盘焦点前后值 + unchanged 布尔）。
     底层即 [`scripts/virtual_mouse.py`](scripts/virtual_mouse.py) 的 PostMessage 合成事件
     （op: click/scroll/drag/move/type/key/shot）；批量用 `batch_runner.py`（同样只走该后端）。
   - **打开/定位桌面软件**（不用命令行）：[`scripts/desktop_ops.py`](scripts/desktop_ops.py)
     `icons` 枚举桌面图标、`open <图标名>` PostMessage 双击打开、`items <窗口>` 列资源管理器项、
     `openitem <窗口> <项名>` 双击进入文件夹/运行程序；`windows/win` 列窗口验证。
   - **直接操作应用界面**：[`scripts/app_ops.py`](scripts/app_ops.py) `controls <窗口>` **只读**枚举 UIA 控件
     （名称/类型/屏幕矩形/`screen_xy`）、`locate <窗口> <元素名>` 只读取坐标、
     `click <窗口> <元素名>`＝在该矩形中心发后台模拟点击、`set <窗口> <元素名> <文本>`＝先点击聚焦再后台打字、
     `menus <窗口>` 只读枚举经典菜单、`menu <窗口> <一级/二级>`＝逐级真实鼠标点击菜单条坐标。
     **已废除的动作捷径**：UIA Invoke/Toggle/Select、ValuePattern.SetValue、菜单 WM_COMMAND。
   - **浏览器通道策略（R1）——先用 [`scripts/browser_channel.py`](scripts/browser_channel.py) 定通道**：
     `policy` 看顺序、`windows` 只读枚举用户已在跑的 Edge/Chrome 窗口（标题+屏幕矩形）、
     `plan` 给出本次该走的通道、`ensure <url>` 按需执行。严格按序：
     ① **attach 用户已经在跑的浏览器窗口**（真实 profile、已登录、带收藏扩展）——只读枚举拿矩形，
     动作交 `input_ops.py` 在该坐标发后台模拟鼠标/键盘，不新起进程、不新 profile、不激活窗口；
     ② 需要 CDP 时先**探测已存在的远调端口**（`--port` > 9222/9223/9224，GET /json/version），能连就连；
     ③ 连不上才用**本技能专属持久 profile**（`<SMS_HOME>/tmp/safe-mouse-automation/browser-profile`，
     跨次复用；需登录时明确告诉用户「在这里登录一次，以后一直记住」，绝不重复要求登录）；
     ④ 仅用户**明确**要干净/无痕会话时才允许一次性 profile（`--ephemeral`）。
     **绝不**默认 `%TEMP%` 空 profile（旧缺陷：无收藏/未登录→误报登录墙→反问用户为何没登录）。
     CDP 输入级模拟仍可用：[`scripts/browser_cdp.py`](scripts/browser_cdp.py)
     `attach/open/navigate/click/clickel/type/key/scroll/eval/shot`（`open` 现自动走上述策略）。
  - **取文本唯一入口 `grab`（R5·attach 已验证可读真实登录页）**：[`scripts/browser_ops.py`](scripts/browser_ops.py)
    `grab <标题或Tab名子串> [--copy] [--grep=token] [--mask]`——附着用户已在跑的真实窗口 →
    在该 **TabItem** 矩形中心后台模拟点击切页 → 等 Chromium a11y 懒加载 → **只读** UIA 取正文 →
    单列疑似 token（`ghp_`/`github_pat_`/`Iv1./Iv2.`/`Ov23li./Iv23li.`/`sk-`/32~40 位 hex +
    「Client ID/secret/token 标签邻近值」）。`--copy` 再后台 Ctrl+A/Ctrl+C 经
    [`scripts/clip_ops.py`](scripts/clip_ops.py) 读回并**还原用户剪贴板**。
    **日志/链一律掩码（前6后4），明文只出现在 stdout**（写盘取证请带 `--mask`）。
    窗口被用户遮挡时**不停止**：带 `hwnd` 的动作定向投递给目标窗口（`occluded_ok`，留 `occluded_by` 痕迹）。
   - **真人验证门禁**：[`scripts/human_gate.py`](scripts/human_gate.py) `check <窗口子串>` 检测验证码/
     登录墙/人机验证，命中即**停止任务**并在 HUD 显示详细信息（类型/证据/需用户操作）；
     `web --port= --match=` 检测浏览器页面；`scan` 扫描全部可见窗口。batch_runner `--guard=<窗口>`
     每步自动检测，命中即中止。**绝不尝试绕过验证。**
   - **禁止**自行调用 `SetForegroundWindow`、移动物理光标或操作焦点窗口；
     任务窗口被最小化时仅允许 `ShowWindow(SW_SHOWNOACTIVATE)` 恢复显示（不抢焦点）。
     回归自检：`python -B scripts/safety_gate.py focus-audit` 静态扫描 `scripts/*.py` 中
     `SetForegroundWindow/BringWindowToTop/SwitchToThisWindow/AttachThreadInput/SetCursorPos/
     mouse_event/keybd_event/SetFocus` 以及非 `SW_SHOWNOACTIVATE(4)` 的 `ShowWindow` 调用，
     命中即 exit 1（白名单：`real_input.py`/`mouse_ops.py` 的前台兜底；注释与文档行不计）。
6. **截图验证后态**：`compare <a> <b>` 比对前后状态——委托 screen-vision `describe.py` 的像素通道统计
   （mean_rgb / 灰度均值 / 标准差 / 8 分箱）算归一化数值距离，本层只做算术胶水；要看懂画面用
   `ask <窗口|图片> <问题>`（→ `recognize.py ask`）、`objects <窗口|图片>`（→ `ask --structured`，
   契约 v2 的 `screen_xy` 是屏幕物理像素绝对坐标，可直接喂 `virtual_mouse` 点击）。
   虚拟消息被忽略且画面无变化时，**征得用户同意**后方可回退 [`scripts/real_input.py`](scripts/real_input.py)
   （SendInput）/ [`scripts/mouse_ops.py`](scripts/mouse_ops.py)。
7. **学习回写 + 报告**：成功操作软件后 `learn.py put <软件名> <json>` 记录 exe 路径、启动链、
   控件名/菜单路径（`learn.py op <软件名> <动作> <json>` 记录单个操作），下次 `get` 直接命中；
   返回操作摘要（动作、坐标、模式、前后截图路径、验证结果），最后 `hud_overlay.py hide`（全量回收）；
   若任务异常结束或不确定是否残留，再跑 `hud_overlay.py procs` 取证 + `reap --yes` 清孤儿——
   **验收标准＝收口后本技能 HUD 进程数为 0**（R4）。

## 2. 安全约束（铁律）

- **禁止操作**：文件删除、格式化、注册表修改、系统服务变更、执行任意 shell 命令。
- **真人验证必停**：检测到验证码/人机验证/登录墙时**立即停止任务**，HUD 显示详细信息（类型/证据/
  需用户操作），等待用户手动完成后才继续；**绝不尝试绕过、破解或自动提交验证**。
- **单一动作后端（R2）**：本技能一切动作必须是**合成鼠标/键盘事件**——Win32 走 PostMessage
  `WM_MOUSEMOVE/WM_LBUTTONDOWN|UP|DBLCLK/WM_RBUTTON*/WM_MOUSEWHEEL/WM_KEYDOWN|UP/WM_CHAR`，
  浏览器走 CDP `Input.dispatchMouseEvent/dispatchKeyEvent`。UIA **只允许只读枚举与定位**
  （取控件名 + 屏幕矩形），动作必须落到该矩形中心坐标点击；**禁止** UIA Invoke/Toggle/Select、
  ValuePattern.SetValue、菜单 WM_COMMAND、命令行式启动等非鼠标键盘捷径。
  统一入口 `scripts/input_ops.py`，每次调用回报所用模式（virtual / cdp-input / 兜底原因）。
- **后台优先（R3）**：一切输入/截图默认走 PostMessage/CDP/UIA(只读) 后台通道；**任何情况下不得**
  `SetForegroundWindow`、`BringWindowToTop`、`SwitchToThisWindow`、`AttachThreadInput`、
  移动物理光标、切换焦点或在用户前台窗口上执行测试。最小化窗口只允许
  `ShowWindow(SW_SHOWNOACTIVATE)` 恢复显示；若目标最小化时确实无法操作，**如实报告，不得激活**。
  每次动作自动做焦点审计（`GetForegroundWindow`/`GetCursorPos`/键盘焦点前后必须一致）。
  测试与验证一律在**自有隔离窗口**（`WS_EX_NOACTIVATE` 父窗 + 标准控件）内进行。
- **遮挡不停止**：用户随时可能盖住任务窗口——screen-vision 截的是**屏幕矩形像素**（非旧自研的窗口 DC
  渲染抓取），被遮挡会把遮挡内容一起截进来；因此被遮挡时**优先用 CDP shot**（页面级抗遮挡），或先
  `ShowWindow(SW_SHOWNOACTIVATE)` 恢复窗口再截，或改用 UIA / `eval` 等非像素通道取证据；
  交互一律用 PostMessage/UIA/CDP（不需要前台）；**不得因窗口被遮挡而中止任务**。
- **前台需同意**：仅当虚拟消息被目标应用忽略且截图验证无变化时，先征得用户同意，
  才可用 `real_input.py`（SendInput）前台回退；测试与验证一律用自有隔离窗口进行。
- **用户确认**：涉及修改性操作（如拖拽文件到回收站、右键菜单选择删除项）前必须请求用户确认。
- **坐标可见**：所有鼠标坐标必须在屏幕分辨率范围内，越界自动拒绝。
- **HUD 全程显示**：使用本 skill 期间 HUD 必须常显任务简述与当前步骤（session+step 双行），
  置顶、不抢焦点、点击穿透、只读展示；任务结束才 hide，空闲 120s 进程自退。
- **HUD 进程零残留（R4 铁律）**：HUD 子进程必须随派发方退出而亡——`_run` 从 `--parent=<pid>` /
  环境变量 `SM_HUD_PARENT` 取父 pid，每 2s `OpenProcess+GetExitCodeProcess` 判父活，父消失即自尽；
  取不到父 pid 时退回 TTL 兜底自尽。`_ensure` 必须**真单实例**（按 state.json 的 `hud_pid` 收敛，
  不一致先终止旧实例再拉新）；`hide` 全量回收；`reap` 只清理**命令行含本技能 hud_overlay.py 特征且
  父进程已死**的孤儿（默认 dry-run，`--yes` 才终止）。进程枚举/终止一律 ctypes（Toolhelp32 +
  NtQueryInformationProcess + TerminateProcess），**绝不借道 taskkill/wmic/powershell**，
  作用域严格限定本技能自身 HUD 进程，不触及用户其它进程。
- **截图留痕**：每次操作前后各存一张截图，路径写入操作摘要。
- **超时熔断**：连续操作达 50 次未收到用户新指令，自动暂停并请求确认。
- **剪贴板只走 ctypes（R5）**：读回文本一律经 `clip_ops.py`（OpenClipboard(NULL)/GetClipboardData/GlobalAlloc），**绝不**借道 `powershell`/`clip.exe`/`Get-Clipboard`；取前先 `snapshot()`、取完必须 `restore()` 归还用户原内容。
- **缓存外置**：截图/HUD 状态/日志等缓存文件不得写入本 skill 目录，一律落用户缓存目录。

详细安全策略见 [`references/safety-policy.md`](references/safety-policy.md)。
使用示例与集成方式见 [`references/usage-guide.md`](references/usage-guide.md)。

## 3. 运行时约定

- 脚本以 `python <SKILL_DIR>/scripts/<name>.py` 调用，`<SKILL_DIR>` 为本 skill 安装根目录。
- 缓存根：`%LOCALAPPDATA%\safe-mouse-automation\`（Windows；macOS/Linux 同级），env `SAFE_MOUSE_CACHE` 覆盖；
  HUD 状态在其 `hud\` 子目录，截图在 `screenshots\`。
- **学习缓存**：`learn.py` 优先写 `<SMS_HOME>/tmp/safe-mouse-automation/learn.json`（向 SMS 临时目录开放；
  SMS_HOME 解析 env > `%LOCALAPPDATA%\SMS`），不可写回退 `SAFE_MOUSE_CACHE/learn.json`；记录软件 exe 路径、
  启动链、通道、验证方式，操作前 `get` 召回、成功后 `put` 回写。绝不落 skill 目录。
- **技能级依赖 `screen-vision`**（窗口枚举/截取/视觉识别/像素统计，清单见
  [`dependence/dependence.md`](dependence/dependence.md)）：`screenshot_verify.py` 的全部视觉能力委托它，
  路径解析 env `SCREEN_VISION_HOME`（可指技能根或 `scripts`）> `~/.kilocode/skills/screen-vision`；
  **缺失只报错（exit 1），绝不自动安装、绝不回退自研实现**；自研 PrintWindow 抓窗口与像素直方图
  比对**已废除**（screen-vision 截屏幕矩形像素，被遮挡会截进遮挡内容，无全屏模式）。
- 依赖：`websocket-client`（CDP 浏览器通道）、`uiautomation`（UIA 桌面操作）、`pyautogui`（仅非 Windows
  回退）；虚拟输入/HUD 为纯标准库（ctypes/tkinter）；`Pillow` 现由 screen-vision 侧使用，本技能脚本不再直接依赖。
- **浏览器通道（R1）**：顺序由 `browser_channel.py` 决定——attach 用户已运行窗口 → 探测已开远调端口
  → 本技能专属**持久 profile** → 仅 `--ephemeral` 才一次性 profile。持久 profile 固定为
  `<SMS_HOME>/tmp/safe-mouse-automation/browser-profile`（env `SAFE_MOUSE_BROWSER_PROFILE` 覆盖），
  跨次复用、登录一次长期记住；**绝不**使用 `%TEMP%\browser-cdp-profile` 之类一次性空 profile。
  真启动时命令形如 `msedge --user-data-dir=<持久profile> --remote-debugging-port=<port>
  --remote-allow-origins=* --no-first-run <url>`（标志必须带，否则 Edge 进程复用/WS 拒绝导致失败）。
- **登录墙处理（R1）**：`human_gate` 命中登录类关键词时先返回 `policy`（该附着哪个真实窗口重试），
  **禁止**反问用户「你为什么没登录」；确认仍有墙时只报告「在哪个窗口/哪个 profile 看到的墙」。
- **坐标契约＝屏幕物理像素**：`virtual_mouse.py` 导入时声明 DPI 感知（per-monitor-v2，
  env `SAFE_MOUSE_NO_DPI_AWARE=1` 可关），与 screen-vision 的 `screen_xy` 同一坐标系；
  给定 `hwnd` 时 `input_ops` 会校验坐标命中的确是该窗口或其子窗口，否则**拒绝投递**（防误伤用户窗口）。
- 速度：批量模式步间延时默认 150ms；虚拟消息即发即达，无需移动时长。
