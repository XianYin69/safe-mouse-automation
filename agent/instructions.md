---
description: safe-mouse-automation agent 指令
---
使用 safe-mouse-automation skill 完成桌面自动化：一切鼠标与键盘操作默认在后台执行——
Win32 应用用 virtual_mouse.py（PostMessage），浏览器用 browser_cdp.py（CDP 内核级模拟点击，
被遮挡照常生效），打开/定位桌面软件用 desktop_ops.py（枚举桌面图标/资源管理器项 + PostMessage
双击打开，不用命令行启动），直接操作应用界面用 app_ops.py（UIA 枚举控件/Invoke/SetValue +
经典 Win32 菜单 WM_COMMAND 零鼠标执行），全程不移动物理光标、不抢焦点、不改变前台窗口。
**学习功能 learn.py**：操作前 `get <软件名>` 召回已知路径/启动链/控件名/菜单路径，成功后 `put/op` 回写
（缓存在 SMS 临时目录 <SMS_HOME>/tmp/safe-mouse-automation/learn.json）。
**真人验证门禁 human_gate.py**：检测到验证码/登录墙/人机验证时立即停止任务，HUD 显示红色⚠告警
（类型/证据/需用户操作），等待用户手动完成后才继续；绝不尝试绕过验证。
HUD 会话必须全程显示：任务开始 session <简述>，每步 show <步骤>，任务结束才 hide。
验证用 screenshot_verify.py window（PrintWindow 抗遮挡）或 CDP shot；窗口被最小化只允许
SW_SHOWNOACTIVATE 恢复。危险操作一律经 safety_gate 拒绝；禁止 SetForegroundWindow/前台试错；
前台 SendInput（real_input.py/--real）仅经用户明确同意后使用。
