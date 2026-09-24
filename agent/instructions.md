---
description: safe-mouse-automation agent 指令
---
使用 safe-mouse-automation skill 完成桌面自动化：一切鼠标与键盘操作默认在后台执行
（virtual_mouse.py：PostMessage，不移动物理光标、不抢焦点、不改变前台窗口）、
HUD 浮窗提示当前操作（置顶/穿透/不抢焦点）、batch_runner 批量加速；危险操作一律经 safety_gate 拒绝。
禁止自行 SetForegroundWindow/移动光标/操作用户前台窗口；仅当目标应用忽略合成消息且经用户明确同意后，
才可用 real_input.py（SendInput）前台回退；测试一律在自有隔离窗口进行。
