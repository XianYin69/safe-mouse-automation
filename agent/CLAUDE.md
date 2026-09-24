---
description: safe-mouse-automation for Claude
---
# safe-mouse-automation
桌面自动化：虚拟鼠标/键盘（PostMessage）全程后台执行，不占物理光标、不抢焦点，HUD 浮窗提示操作不打扰用户，批量执行加速。
先过 safety_gate，再 virtual_mouse/batch_runner，后台截图验证；仅当应用忽略虚拟消息且用户明确同意后才回退
real_input（SendInput）前台方式；严禁为测试改动用户前台窗口。
