---
description: safe-mouse-automation for Claude
---
# safe-mouse-automation
桌面自动化：Win32 走 PostMessage（virtual_mouse），浏览器走 CDP（browser_cdp，内核级模拟点击、
抗遮挡、不碰物理光标/焦点），HUD 会话全程显示任务简述+步骤，批量执行加速。
先过 safety_gate，后台截图验证用 screenshot_verify window（PrintWindow）或 CDP shot；
仅当应用忽略虚拟消息且用户明确同意后才回退 real_input（SendInput）前台方式；
严禁为测试改动用户前台窗口；任务结束 hud hide。
