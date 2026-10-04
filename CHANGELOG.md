# CHANGELOG

## 2026-10-03 — R5：attach 真实浏览器取文本链路打通（clip_ops + grab + dump 空树修复）

- **实测根因（dump 返回 `elements=[]`）**：Edge 窗口下有 6 个 `DocumentControl`，前 5 个 `Name` 为空、
  各只 1 个子节点（depth 7/9/10 的包装层），真正的页面 doc 在 **depth 11**；旧 `_doc()` 用 `d<8` 的
  BFS 命中第一个空 Name 包装层就返回 → 子树只有 1 个节点。且旧 `dump` 用 `IsOffscreen` 一票否决，
  刚恢复的节点被全滤掉。Chromium a11y 树**懒加载**（实测 t0=330 节点、t+3s=660）。
- **修法**：`_docs()` 全深度（depth≤40、节点≤4000）收集候选 → `_pick()` 按「Name 非空 → 子节点多 →
  深度大」选真页面 doc；`_doc(wait_named=…)` 轮询到具名节点>0（回报 `lazy_wait` 的 tries/seconds/named）；
  `dump` 不再因 `IsOffscreen` 丢弃，改标 `offscreen:true` 并回报 `root`/`count`。
  实测同一窗口 `dump` 由 `elements=[]` → 8 个具名可点元素（含 `screen_xy`），`root:"document"`。
- **新增 `scripts/clip_ops.py`（纯 ctypes 剪贴板）**：`list/read/write/snapshot/restore/drop/probe`。
  `OpenClipboard(NULL)` 不关联窗口故不创建/切换前台；`EnumClipboardFormats` 全量快照（跳过
  CF_BITMAP/METAFILEPICT/ENHMETAFILE 这类 GDI 句柄格式，8MB 上限），还原时**一次** `EmptyClipboard`
  + 多格式 `SetClipboardData`（成功后所有权归系统，绝不 `GlobalFree`）；占用/延迟渲染失效/格式
  不可用一律有限重试后返回 `{"error":…}` 不抛栈。**绝不借道 powershell/clip.exe/Get-Clipboard**
  （属"任意命令执行"）。快照落 `%LOCALAPPDATA%\safe-mouse-automation\clip\`，不落 skill 目录。
  `probe` 实测：快照→写标记→读回→还原，用户原 32 字符内容 `user_text_preserved:true`。
- **新增唯一取文本入口 `browser_ops.py grab <标题或Tab名子串> [--copy] [--grep=] [--mask]`**：
  附着用户已在跑的真实窗口（R1：不新起进程、不新 profile、绝不反问"你为什么没登录"）→
  在 **TabItem** 矩形中心后台模拟点击切页 → 等 a11y 懒加载 → **只读** UIA 取正文
  （`Name` + `ValuePattern`/`LegacyIAccessible` 只读取值，不 SetValue）→ 单列疑似 token。
  特征表补 `Ov23li./Iv23li.`（旧表漏 GitHub OAuth Client ID 形态）并加
  「Client ID/secret/token 标签邻近值」兜底；**日志/链一律掩码（前6后4），明文只回 stdout**
  （写盘取证带 `--mask`）。
- **遮挡不停止（R3 兼容）**：`input_ops` 的 ownership 护栏实测**判断正确**——用户 Windows Terminal
  （`CASCADIA_HOSTING_WINDOW_CLASS`）同矩形盖住 Edge 标签条，`WindowFromPoint` 返回遮挡者子窗
  `DRAG_BAR_WINDOW_CLASS`。因显式带 `hwnd` 时 PostMessage 只投给目标窗口本身、绝不落到遮挡者，
  新增 `occluded_ok=True` 放行并留 `occluded_by` 审计痕迹（默认行为不变，仍 `refused:"ownership"`）。
- **真跑验收（严格只读）**：用户 Edge（账号 XianYin69，15 标签）`grab "OAuth application settings"`
  → `doc_name:"OAuth application settings"`、`uia_lines:140`、Client ID 命中
  `kind:"oauth_client_id"` 掩码 `Ov23li…1pGY`（明文只出现在 stdout 一次），
  `focus_unchanged:true`（前台窗口/物理光标/键盘焦点前后完全一致）。
  **未点** Generate/Update client secret、未删除/重命名/新建任何 App。
  **Client secret 结论**：页面 UIA 正文只有 "Client secrets / Generate a new client secret" 按钮，
  全树 0 个 32~40 位 hex —— GitHub 仅在**生成那一刻**显示一次 secret，故**只读拿不到**，
  需用户本人在页面上生成（属改动账号的操作，本技能不代做）。

## 2026-10-03 — R4：子代理进程泄漏修复（HUD 父死自尽 + 真单实例 + 收口全量回收）
- **取证**：本技能派发对话收口后残留两个孤儿 `python.exe ...\hud_overlay.py _run`（pid 9740 / 30184，
  父 12432 / 4572 均已不存在），且两实例并存＝单实例收敛失效；由调度方手工 taskkill 收掉。
- **父死自尽**：`_run` 接收 `--parent=<pid>` / 环境变量 `SM_HUD_PARENT`（`_spawn` 自动透传拉起方父 pid），
  后台线程每 2s `OpenProcess+GetExitCodeProcess` 判父活，父消失即清 state/pid 文件并 `os._exit(0)`；
  取不到父 pid 退回 TTL 兜底自尽（`SM_HUD_NO_PARENT_WATCH=1` 关父监控、`SM_HUD_PARENT_MISS` 调容错次数）。
  `OpenProcess` 因 ACCESS_DENIED 失败视为存活，防误杀。
- **真单实例**：`_ensure` 改为「state.json 的 `hud_pid` + 全量枚举」双路收敛——在册实例存活则复用并终止
  多余实例；在册 pid 已死但仍有残留（旧缺陷：pid 文件被覆盖使旧实例失踪、无人回收）则先终止残留再拉新；
  `_run` 启动时自收敛（只终止 pid 更小的旧实例，避免同时启动者互杀），并新增「已被新实例取代则让位自尽」。
- **hide 全量回收**：`hide` 除清 state 外，枚举并终止本技能全部 HUD 进程（含孤儿）、删 pid 文件，
  返回 `reclaimed` / `residual`（TerminateProcess 异步，回收后 settle 再复扫）。
- **新增 CLI**：`hud_overlay.py reap [--yes]`（只清「命令行含本技能 hud_overlay.py 特征且父已死」的孤儿，
  默认 dry-run）、`hud_overlay.py procs`（取证列实例）。
- **batch_runner 收口**：任务结束（含异常结束）在 `finally` 中强制 `hud_overlay.hide()` 并在结果里回报
  `hud_reclaim`；`--keep-hud` 可显式保留浮窗（此时由调用方自行 hide）。
- **安全边界**：进程枚举/终止全走 ctypes（Toolhelp32 + NtQueryInformationProcess + TerminateProcess），
  不借道 taskkill/wmic/powershell；作用域严格限定本技能自身 HUD 进程特征，见
  `references/safety-policy.md`「进程回收的唯一例外（R4）」。
- **验收（真跑·tmp/r4_acceptance.py → r4_acceptance_result.json）**：T1 人造父进程退出后 HUD 于 1.62s
  自尽；T2 连续 `_ensure` 三次存活实例恒为 1；T2b 伪造 pid 不一致 → 旧实例被收敛、并存数回到 1；
  T3 `hide` 后残留 0；T4 人造孤儿 `reap` dry-run 不动、`reap --yes` 清零；T5 batch_runner 收口
  `residual=0`；`safety_gate.py focus-audit` 违规 0；CIM 复查本技能特征进程数 0。

## 2026-10-03 — 重构：统一后台输入后端（R2）+ 浏览器附着真实 profile（R1）+ 全程不抢焦点（R3）

- **R1 浏览器通道**：新增 `scripts/browser_channel.py` 作唯一浏览器决策入口，严格按序
  `attach 用户已在跑的 Edge/Chrome 窗口（真实 profile·已登录）→ 探测已开远调端口(9222/9223/9224)
  → 本技能专属持久 profile（`<SMS_HOME>/tmp/safe-mouse-automation/browser-profile`，跨次复用）
  → 仅 `--ephemeral` 才一次性 profile`。`browser_cdp.py open` 改为调用该策略并新增 `attach` 子命令，
  **删除** `%TEMP%\browser-cdp-profile` 一次性空 profile 默认值；`human_gate` 命中登录类关键词时
  先返回 `policy`（该附着哪个真实窗口重试），HUD 文案与返回值均**不再**质问用户「为何没登录」。

- **R2 统一输入后端**：新增 `scripts/input_ops.py`——本技能唯一动作出口
  （click/double/rclick/move/drag/scroll/type/key），参数可为屏幕坐标或 `--win=<窗口> <元素名>`
  （内部只读 UIA 解析成矩形中心），每次调用回报 `mode` 与 `focus_audit`。
  `app_ops.py` 去特殊化：删除 UIA Invoke/Toggle/Select、ValuePattern.SetValue、菜单 WM_COMMAND；
  `controls/menus` 保留为只读枚举，`click/set/menu` 改为「只读定位 → 坐标上发合成鼠标/键盘」。
  `browser_ops.py` 删除 `_act`（Invoke 族）与 SetValue，`click/type_text` 委托 input_ops，
  并放开「仅 InPrivate」限制以允许附着用户真实浏览器窗口；`desktop_ops.py` 双击/单击
  统一改调 `virtual_mouse`，不再自行拼消息序列。

- **R3 焦点静默**：`browser_ops._ensure_visible` 去掉 `ShowWindow(SW_SHOW)` 激活与 `SetWindowPos`
  挪窗，只允许 `SW_SHOWNOACTIVATE`；`batch_runner.py` 删除「虚拟不支持就静默落到 mouse_ops 物理输入」
  的回退——`--real/--physical` 必须显式带 `--consent=<用户同意>` 否则拒绝执行，并逐步+整体比对
  前台窗口/物理光标/键盘焦点。新增 `safety_gate.py focus-audit` 静态扫描
  （SetForegroundWindow/BringWindowToTop/SwitchToThisWindow/AttachThreadInput/SetCursorPos/
  mouse_event/keybd_event/SetFocus + 非 SW_SHOWNOACTIVATE 的 ShowWindow），违规 exit 1；
  白名单仅 `real_input.py`/`mouse_ops.py` 前台兜底，注释与文档行不计。

- **验收中发现并修掉的真实缺陷**：① `virtual_mouse.py` 未声明 DPI 感知——150% 缩放屏上
  「屏幕物理像素」坐标被虚拟化，点击/打字投递错位；现导入时声明 per-monitor-v2
  （env `SAFE_MOUSE_NO_DPI_AWARE=1` 可关）。② `input_ops.act` 原先丢弃 type/key 的 `hwnd`，
  WM_CHAR 可能打到坐标底下的**别人**窗口；现透传 hwnd 并加 ownership 校验，
  命中窗口非目标或其子窗口时 `refused:"ownership"` 拒绝投递。③ `hud_overlay._kill_stale`
  原用外部 shell 查询并强杀其他解释器进程，违反本技能「禁止进程终止/禁止任意 shell」，已移除
  （残留浮窗由 tkinter 空闲 120s 自退兜底）。

- **文档同步**：`SKILL.md`（description、§1 浏览器/应用通道、§2 铁律新增单一后端与焦点红线、
  §3 profile 与坐标契约）、`references/usage-guide.md`（新增「统一输入后端」「浏览器通道策略」两节、
  app_ops 命令表、batch `--consent`）、`references/safety-policy.md`（允许后台键盘消息的条件、
  R1/R2/R3 三条红线）、`README.md` 通道表。
- **验收（真跑，产物见 SMS_TMP/refactor/evidence）**：A1 `focus-audit` exit 0 零命中；
  A1b 植入 3 处违规被抓 exit 1（证明自检非空转）；A2 只读枚举到用户真实 Edge 窗口（14 标签页·个人 profile）
  且 `GetForegroundWindow`/`GetCursorPos`/键盘焦点前后完全一致；A3 自有隔离窗口
  （WS_EX_NOACTIVATE 自绘）完成 click+type，`WM_GETTEXT`/进程内缓冲读回 `HELLO9421` 与点击点，
  严格阈值 0.999 下截图 `changed=true`；A4 `browser_cdp.py open` 返回 `channel=attach`、未新建任何 %TEMP% profile；
  A5 `input_ops` CLI 冒烟 ok。日志 `acceptance_log.json`、`a3b_input_ops.json`。


## 2026-10-02 — 屏幕视觉能力改为依赖 screen-vision（自研实现废除）

- **`scripts/screenshot_verify.py` 重写为纯委托层**：删除自研 Win32 GDI 窗口抓取整段
  （EnumWindows + PrintWindow/GetDIBits + 位图回读）、`PIL.ImageChops` 像素直方图比对、
  `ImageGrab` 全屏抓取；改为 subprocess 委托 screen-vision 的 `sw.py` / `describe.py` /
  `recognize.py`，本层只做路径解析与算术胶水（不 import PIL/ctypes）。
- **向后兼容保留**：模块名 `screenshot_verify`、子命令 `capture/window/compare/dir`、
  函数签名 `capture(region=None, label="")` / `compare(path_a, path_b, threshold=0.95)` /
  `capture_window(title_part, label="")`、`cache_base()` 与 `ensure_dir()`（`browser_cdp.py` 依赖）、
  「拒绝写入 skill 目录」守卫与 stdout UTF-8 重配置。
- **新增子命令/函数**：`ask <窗口|图片> <问题> [--structured]`、`objects <窗口|图片>`
  （契约 v2，`screen_xy` 为屏幕物理像素绝对坐标，可直接喂 `virtual_mouse`）。
- **依赖解析**：env `SCREEN_VISION_HOME`（技能根或 `scripts` 皆可）> `~/.kilocode/skills/screen-vision/scripts`；
  缺失只返回 error 并 exit 1，**不自动安装、不回退自研**；委托失败原样透传 stderr，不重试不猜。
- **行为差异（须知）**：screen-vision 截**屏幕矩形像素**，被遮挡会截进遮挡内容，且**无全屏截取模式**；
  `capture` 现为 z-order 顶层窗口截取并附 `note`；`region` 参数已废除（返回 error）。
  抗遮挡优先 `browser_cdp.py shot` 或先 `ShowWindow(SW_SHOWNOACTIVATE)` 恢复再截——遮挡不停止任务。
- **文档同步**：`SKILL.md`（步骤4/6、铁律「遮挡不停止」、依赖条目、description）、
  `README.md`（能力表、示例、依赖）、`references/usage-guide.md`（小节更名「截图与视觉验证（委托
  screen-vision）」）、`agent/instructions.md`、`agent/agent_prompt.md`、`agent/CLAUDE.md`、
  `agent/.cursorrules` 中的 PrintWindow 表述全部更正。
- **新增依赖清单**：`dependence/dependence.md` + `dependence/deps.json`，把 `screen-vision`
  登记为**技能级依赖**（`Pillow` 降级为 screen-vision 侧的间接依赖）。
