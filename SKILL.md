---
name: safe-mouse-automation
description: >-
  通过 Python 脚本直接模拟鼠标操作用户电脑，截图确认操作结果，类似 EasyEDAssistant
  的双链路模式但面向桌面自动化；内置安全门禁，禁止执行危险操作（删除、系统修改、任意命令执行）。
---

# Safe Mouse Automation

通过 Python（`pyautogui`）模拟鼠标移动、点击、拖拽、滚动，配合截图验证操作前后状态，
实现安全的桌面自动化流程。

## 1. 工作流程

1. **识别意图**：判断用户需要执行的桌面操作目标。
2. **安全检查**：所有操作经过 [`scripts/safety_gate.py`](scripts/safety_gate.py) 门禁——
   危险操作（文件删除、系统修改、注册表写入、任意 shell 命令）一律拒绝并报告用户。
3. **截图记录前态**：[`scripts/screenshot_verify.py`](scripts/screenshot_verify.py) 捕获操作前屏幕状态。
4. **执行鼠标操作**：[`scripts/mouse_ops.py`](scripts/mouse_ops.py) 执行移动/点击/拖拽/滚动。
5. **截图验证后态**：捕获操作后屏幕状态，与前态比对确认操作生效。
6. **报告**：返回操作摘要（动作、坐标、前后截图路径、验证结果）。

## 2. 安全约束（铁律）

- **禁止操作**：文件删除、格式化、注册表修改、系统服务变更、执行任意 shell 命令。
- **用户确认**：涉及修改性操作（如拖拽文件到回收站、右键菜单选择删除项）前必须请求用户确认。
- **坐标可见**：所有鼠标坐标必须在屏幕分辨率范围内，越界自动拒绝。
- **截图留痕**：每次操作前后各存一张截图，路径写入操作日志。
- **超时熔断**：连续操作达 50 次未收到用户新指令，自动暂停并请求确认。

详细安全策略见 [`references/safety-policy.md`](references/safety-policy.md)。
使用示例与集成方式见 [`references/usage-guide.md`](references/usage-guide.md)。

## 3. 运行时约定

- 脚本以 `python <SKILL_DIR>/scripts/<name>.py` 调用，`<SKILL_DIR>` 为本 skill 安装根目录。
- 截图保存到用户工作区 `./tmp/screenshots/` 下。
- 依赖 `pyautogui`、`Pillow`；缺失时脚本自动检测并提示安装。
