---
name: safe-mouse-automation
description: >
  通过 Python 脚本在后台模拟鼠标与键盘操作用户电脑，截图确认操作结果；默认虚拟输入
  （PostMessage/CDP）不移动物理光标、不抢焦点、不打扰前台，含点击/滚轮/拖拽与打字/快捷键；
  浏览器走 CDP 内核级模拟点击、桌面软件走 desktop_ops 纯鼠标双击（枚举桌面图标/资源管理器项，
  不用命令行启动）；学习功能 learn 把软件路径/启动链沉淀到 SMS 临时目录，操作前召回成功后回写；
  HUD 浮窗全程置顶提示任务信息（置顶/穿透/不抢焦点）；SendInput 前台真输入为征得同意后的回退；
  批量执行加快整体流程；内置安全门禁禁止危险操作，缓存不落 skill 目录。
license: MIT
metadata:
  category: automation
---

使用 `safe-mouse-automation` skill 来完成用户请求。

# Safe Mouse Automation

**一切操作默认在后台执行，绝不打扰前台用户**：**虚拟输入**（PostMessage 鼠标+键盘，不移动物理
光标、不抢焦点、不改变前台窗口）配合 **CDP 浏览器通道**（`browser_cdp.py` 内核级模拟鼠标点击/打字，
被遮挡/非前台照常生效）、**桌面软件鼠标通道**（`desktop_ops.py` 枚举桌面图标/资源管理器项并 PostMessage
双击打开，纯鼠标定位不用命令行）、**学习功能**（`learn.py` 把"软件在哪、怎么开"沉淀到 SMS 临时目录，
操作前召回免重复探索）配合 **HUD 会话浮窗**（全程置顶显示任务简述+当前步骤）与**批量执行**。
仅当目标应用忽略合成消息且截图验证无变化时，**征得用户同意后**才可用 `real_input.py`（SendInput）前台回退。

## 1. 工作流程

1. **识别意图 + 学习召回**：确定目标操作；先 `learn.py get <软件名>` 召回已知路径/启动链，
   命中则直接照做（免重复探索）。优先编排为步骤清单（`scripts/batch_runner.py` 一次进程跑完）。
2. **安全检查**：每步经过 [`scripts/safety_gate.py`](scripts/safety_gate.py) 门禁——
   危险操作（文件删除、系统修改、注册表写入、任意 shell 命令）一律拒绝并报告用户。
3. **HUD 会话开启**：任务开始即 `hud_overlay.py session <任务简述> [ttl]`（默认 30 分钟，全程常显）；
   每步 `hud_overlay.py show <步骤>` 更新第二行；**仅任务整体结束才 `hide`**（batch_runner 不再自动隐藏）。
4. **截图记录前态**：[`scripts/screenshot_verify.py`](scripts/screenshot_verify.py) `capture` 全屏或
   `window <标题子串>` PrintWindow 抓目标窗口（被遮挡/非前台同样可截）。
5. **后台执行操作**：
   - 桌面 Win32 应用：[`scripts/virtual_mouse.py`](scripts/virtual_mouse.py) 点击/滚轮/拖拽/打字/快捷键
     （op: click/scroll/drag/move/type/key/shot），或 `batch_runner.py` 批量。
   - **打开/定位桌面软件**（不用命令行）：[`scripts/desktop_ops.py`](scripts/desktop_ops.py)
     `icons` 枚举桌面图标、`open <图标名>` PostMessage 双击打开、`items <窗口>` 列资源管理器项、
     `openitem <窗口> <项名>` 双击进入文件夹/运行程序；`windows/win` 列窗口验证。UIA 取真实屏幕坐标，
     最小化窗口自动 SW_SHOWNOACTIVATE 恢复（不抢焦点）。
   - **浏览器（Edge/Chrome）必须用 [`scripts/browser_cdp.py`](scripts/browser_cdp.py)**：
     `open/navigate/click/clickel/type/key/scroll/eval/shot`——CDP 内核级模拟鼠标点击，
     窗口被遮挡同样生效、不碰物理光标；`eval` 可直接取页面数据（如价格），`shot` 页面级截图存证。
   - **禁止**自行调用 `SetForegroundWindow`、移动物理光标或操作焦点窗口；
     任务窗口被最小化时仅允许 `ShowWindow(SW_SHOWNOACTIVATE)` 恢复显示（不抢焦点）。
6. **截图验证后态**：比对前后状态（`compare`）；虚拟消息被忽略且画面无变化时，**征得用户同意**
   后方可回退 [`scripts/real_input.py`](scripts/real_input.py)（SendInput）/ [`scripts/mouse_ops.py`](scripts/mouse_ops.py)。
7. **学习回写 + 报告**：成功打开/运行软件后 `learn.py put <软件名> <json>` 记录 exe 路径、启动链、
   验证方式（下次 `get` 直接命中）；返回操作摘要（动作、坐标、模式、前后截图路径、验证结果），最后 `hud_overlay.py hide`。

## 2. 安全约束（铁律）

- **禁止操作**：文件删除、格式化、注册表修改、系统服务变更、执行任意 shell 命令。
- **后台优先**：一切输入/截图默认走 PostMessage/CDP 后台通道；**任何情况下不得**自行
  `SetForegroundWindow`、移动物理光标、切换焦点或在用户前台窗口上执行测试。
- **遮挡不停止**：用户随时可能盖住任务窗口——验证一律用 PrintWindow/CDP shot（抗遮挡），
  交互一律用 PostMessage/UIA/CDP（不需要前台）；不得因窗口被遮挡而中止任务。
- **前台需同意**：仅当虚拟消息被目标应用忽略且截图验证无变化时，先征得用户同意，
  才可用 `real_input.py`（SendInput）前台回退；测试与验证一律用自有隔离窗口进行。
- **用户确认**：涉及修改性操作（如拖拽文件到回收站、右键菜单选择删除项）前必须请求用户确认。
- **坐标可见**：所有鼠标坐标必须在屏幕分辨率范围内，越界自动拒绝。
- **HUD 全程显示**：使用本 skill 期间 HUD 必须常显任务简述与当前步骤（session+step 双行），
  置顶、不抢焦点、点击穿透、只读展示；任务结束才 hide，空闲 120s 进程自退。
- **截图留痕**：每次操作前后各存一张截图，路径写入操作摘要。
- **超时熔断**：连续操作达 50 次未收到用户新指令，自动暂停并请求确认。
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
- 依赖：`Pillow`（截图）、`websocket-client`（CDP 浏览器通道）、`uiautomation`（UIA 备用，实验性）；
  `pyautogui` 仅非 Windows 回退；虚拟输入/HUD 为纯标准库（ctypes/tkinter）。
- 浏览器后台通道：`msedge --user-data-dir=<临时目录> --remote-debugging-port=<port>
  --remote-allow-origins=* --no-first-run <url>`（`browser_cdp.py open` 自动执行；
  标志必须带，否则 Edge 进程复用/WS 拒绝导致失败）。
- 速度：批量模式步间延时默认 150ms；虚拟消息即发即达，无需移动时长。
