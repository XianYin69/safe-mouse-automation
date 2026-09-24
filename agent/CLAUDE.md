---
description: safe-mouse-automation for Claude
---
# safe-mouse-automation
桌面自动化：Win32 走 PostMessage（virtual_mouse），浏览器走 CDP（browser_cdp，内核级模拟点击、
抗遮挡、不碰物理光标/焦点），打开/定位桌面软件走 desktop_ops（枚举桌面图标/资源管理器项 + PostMessage
双击，不用命令行），直接操作应用界面走 app_ops（UIA 枚举控件/Invoke/SetValue + 经典 Win32 菜单 WM_COMMAND
零鼠标执行），学习功能 learn.py 把软件路径/启动链/控件名/菜单路径沉淀到 SMS 临时目录（get 召回、put/op 回写）。
真人验证门禁 human_gate.py：检测到验证码/登录墙立即停止任务，HUD 显示红色⚠告警（类型/证据/需用户操作），
等待用户手动完成后才继续；绝不绕过验证。HUD 会话全程显示任务简述+步骤，批量执行加速。
先过 safety_gate，后台截图验证用 screenshot_verify window（PrintWindow）或 CDP shot；
仅当应用忽略虚拟消息且用户明确同意后才回退 real_input（SendInput）前台方式；
严禁为测试改动用户前台窗口；任务结束 hud hide。
