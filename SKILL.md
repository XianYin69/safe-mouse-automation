---
name: safe-mouse-automation
description: >
  通过 Python 脚本在后台模拟鼠标与键盘操作用户电脑，截图确认操作结果；默认虚拟输入
  （PostMessage）不移动物理光标、不抢焦点、不打扰前台，含点击/滚轮/拖拽与打字/快捷键；
  SendInput 前台真输入为征得同意后的回退；HUD 浮窗置顶提示当前操作不打扰用户，
  批量执行加快整体流程；内置安全门禁禁止危险操作，缓存不落 skill 目录。
license: MIT
metadata:
  category: automation
---
使用 `safe-mouse-automation` skill 来完成用户请求。

# Safe Mouse Automation

**一切操作默认在后台执行，绝不打扰前台用户**：**虚拟输入**（PostMessage 鼠标+键盘，不移动物理
光标、不抢焦点、不改变前台窗口）配合 **HUD 浮窗**（置顶、点击穿透、不抢焦点、只读提示）与
**批量执行**。仅当目标应用忽略合成消息且截图验证无变化时，**征得用户同意后**才可用
`real_input.py`（SendInput）前台回退。

## 1. 工作流程

1. **识别意图**：确定目标操作，优先编排为步骤清单（`scripts/batch_runner.py` 一次进程跑完，最快）。
2. **安全检查**：每步经过 [`scripts/safety_gate.py`](scripts/safety_gate.py) 门禁——
   危险操作（文件删除、系统修改、注册表写入、任意 shell 命令）一律拒绝并报告用户。
3. **截图记录前态**：[`scripts/screenshot_verify.py`](scripts/screenshot_verify.py) 后台捕获操作前屏幕状态。
4. **后台执行操作**：[`scripts/virtual_mouse.py`](scripts/virtual_mouse.py) 虚拟点击/滚轮/拖拽/
   打字/快捷键（`type` 支持 Unicode，`key` 支持组合键），单条命令或 `batch_runner.py` 批量
   （op: click/scroll/drag/move/type/key/shot）。HUD 自动显示当前步骤（[`scripts/hud_overlay.py`](scripts/hud_overlay.py)）。
   **禁止**自行调用 `SetForegroundWindow`、移动物理光标或操作焦点窗口。
5. **截图验证后态**：比对前后状态；若画面未变化（部分应用忽略虚拟消息），**必须征得用户同意**
   后方可回退 [`scripts/real_input.py`](scripts/real_input.py)（SendInput）/ [`scripts/mouse_ops.py`](scripts/mouse_ops.py)。
6. **报告**：返回操作摘要（动作、坐标、模式、前后截图路径、验证结果）。

## 2. 安全约束（铁律）

- **禁止操作**：文件删除、格式化、注册表修改、系统服务变更、执行任意 shell 命令。
- **后台优先**：一切输入/截图默认走 PostMessage 后台通道；**任何情况下不得**自行
  `SetForegroundWindow`、移动物理光标、切换焦点或在用户前台窗口上执行测试。
- **前台需同意**：仅当虚拟消息被目标应用忽略且截图验证无变化时，先征得用户同意，
  才可用 `real_input.py`（SendInput）前台回退；测试与验证一律用自有隔离窗口进行。
- **用户确认**：涉及修改性操作（如拖拽文件到回收站、右键菜单选择删除项）前必须请求用户确认。
- **坐标可见**：所有鼠标坐标必须在屏幕分辨率范围内，越界自动拒绝。
- **HUD 不打扰**：提示浮窗必须置顶、不抢焦点、点击穿透，只读展示，不接受任何输入。
- **截图留痕**：每次操作前后各存一张截图，路径写入操作摘要。
- **超时熔断**：连续操作达 50 次未收到用户新指令，自动暂停并请求确认。
- **缓存外置**：截图/HUD 状态/日志等缓存文件不得写入本 skill 目录，一律落用户缓存目录。

详细安全策略见 [`references/safety-policy.md`](references/safety-policy.md)。
使用示例与集成方式见 [`references/usage-guide.md`](references/usage-guide.md)。

## 3. 运行时约定

- 脚本以 `python <SKILL_DIR>/scripts/<name>.py` 调用，`<SKILL_DIR>` 为本 skill 安装根目录。
- 缓存根：`%LOCALAPPDATA%\safe-mouse-automation\`（Windows；macOS/Linux 同级），env `SAFE_MOUSE_CACHE` 覆盖；
  HUD 状态在其 `hud\` 子目录，截图在 `screenshots\`。
- 依赖 `Pillow`（截图）与 `pyautogui`（仅非 Windows 平台回退）；虚拟输入、HUD 为纯标准库（ctypes/tkinter）。
- 速度：批量模式步间延时默认 150ms；虚拟消息即发即达，无需移动时长。
