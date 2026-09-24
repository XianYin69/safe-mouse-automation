---
description: safe-mouse-automation agent 指令
---
使用 safe-mouse-automation skill 完成桌面自动化：一切鼠标与键盘操作默认在后台执行——
Win32 应用用 virtual_mouse.py（PostMessage），浏览器用 browser_cdp.py（CDP 内核级模拟点击，
被遮挡照常生效），全程不移动物理光标、不抢焦点、不改变前台窗口。
HUD 会话必须全程显示：任务开始 session <简述>，每步 show <步骤>，任务结束才 hide。
验证用 screenshot_verify.py window（PrintWindow 抗遮挡）或 CDP shot；窗口被最小化只允许
SW_SHOWNOACTIVATE 恢复。危险操作一律经 safety_gate 拒绝；禁止 SetForegroundWindow/前台试错；
前台 SendInput（real_input.py/--real）仅经用户明确同意后使用。
