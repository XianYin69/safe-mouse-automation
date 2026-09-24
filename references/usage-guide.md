# 使用指南

## 依赖安装

```bash
pip install Pillow websocket-client   # 截图 + CDP 浏览器通道
pip install uiautomation              # UIA 备用通道（实验性）
pip install pyautogui                 # 仅非 Windows 平台回退
```

## 缓存目录（红线：不写入 skill 目录）

- Windows `%LOCALAPPDATA%\safe-mouse-automation\`（screenshots\ 与 hud\ 子目录）；
  macOS `~/Library/Caches/`、Linux `~/.cache/` 同构路径；env `SAFE_MOUSE_CACHE` 可重定向。
- 查看当前缓存根：`python <SKILL_DIR>/scripts/screenshot_verify.py dir`

## HUD 会话（使用 skill 期间必须全程显示）

```bash
python <SKILL_DIR>/scripts/hud_overlay.py session "任务: 查询XX价格" 3600   # 任务开始，第一行常显
python <SKILL_DIR>/scripts/hud_overlay.py show "[2/5] 点击下一页" 20        # 每步更新第二行
python <SKILL_DIR>/scripts/hud_overlay.py hide                              # 仅任务整体结束
```

batch_runner 每步自动 `show`，但**不再自动 hide**——由调用方在任务结束时 hide。
浮窗置顶、点击穿透、不抢焦点；空闲 120s 显示进程自动退出。

## 学习功能（操作前召回，成功后回写）

```bash
python <SKILL_DIR>/scripts/learn.py get [软件名]        # 召回已知路径/启动链（无参列出全部）
python <SKILL_DIR>/scripts/learn.py put <软件名> @rec.json   # 回写经验（JSON 从文件读，免转义）
python <SKILL_DIR>/scripts/learn.py note <软件名> "开始菜单是UWP，走桌面图标"   # 追加备注
python <SKILL_DIR>/scripts/learn.py del <软件名>
```

缓存优先写 `<SMS_HOME>/tmp/safe-mouse-automation/learn.json`（向 SMS 临时目录开放，SMS_HOME 解析
env > `%LOCALAPPDATA%\SMS`），不可写回退 `SAFE_MOUSE_CACHE/learn.json`；绝不落 skill 目录。
记录字段建议：`exe`（绝对路径）、`launch_chain`（怎么点开的）、`channel`（用的哪个通道）、`gui`/`verified`。

## 桌面软件纯鼠标通道（不用命令行启动）

```bash
python <SKILL_DIR>/scripts/desktop_ops.py windows                 # 列可见顶层窗口（验证用）
python <SKILL_DIR>/scripts/desktop_ops.py icons                   # 枚举桌面图标 + 真实屏幕坐标
python <SKILL_DIR>/scripts/desktop_ops.py open "此电脑"            # PostMessage 双击桌面图标
python <SKILL_DIR>/scripts/desktop_ops.py items "Shell"           # 列资源管理器窗口内的项
python <SKILL_DIR>/scripts/desktop_ops.py openitem "Shell" "syncthing-windows"   # 双击进入/运行
python <SKILL_DIR>/scripts/desktop_ops.py click <hwnd> <x> <y>    # 向任意窗口 PostMessage 单击
```

UIA 取真实屏幕矩形，向目标 SysListView32 PostMessage `WM_LBUTTONDBLCLK`（不动物理光标、不抢焦点）。
最小化的任务窗口自动 `SW_SHOWNOACTIVATE` 恢复。典型链：`open <桌面图标>` → `items <窗口>` →
`openitem <窗口> <子项>` 逐层进入，最后 `openitem <窗口> xxx.exe` 运行，再 `learn put` 记录。

## 浏览器后台通道（Edge/Chrome 首选，抗遮挡）

```bash
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 open "https://example.com"
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example clickel "text=下一页"
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example click 400 300 left
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example scroll 640 400 800
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example type "搜索词"
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example key "ctrl+a"
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example eval "document.title"
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example eval "@script.js"   # JS 从文件读
python <SKILL_DIR>/scripts/browser_cdp.py --port=9224 --match=example shot label_before   # 页面级截图存证
```

CDP 的 `Input.dispatchMouseEvent` 是浏览器内核级模拟鼠标点击——**窗口被用户遮挡、不在前台、
未聚焦全部生效**，不移动物理光标、不抢焦点。`clickel` 支持 CSS 选择器与 `text=文本` 定位
（自动 scrollIntoView 后取矩形）。`open` 自动带 `--remote-allow-origins=*`（Edge 必须，否则 WS 403）。
`eval` 可直接从 DOM 提取数据（价格列表等），配合 `shot` 截图留痕。

## 批量流程（桌面 Win32 应用，默认后台虚拟输入）

```bash
python <SKILL_DIR>/scripts/batch_runner.py steps.json
```

- 步骤文件为 JSON 数组（op: click/scroll/drag/move/type/key/shot），一次进程连续执行；
  type 步骤带 `"x","y","text"`（文本打到该坐标窗口内的焦点控件），key 步骤带 `"combo"`（如 `"ctrl+s"`）；
  HUD 自动 `show` 当前步骤（session 行需任务开始时自行开启）。
- `--real` 前台真输入回退（SendInput，**会打扰用户，须先取得同意**）；
  `--physical` pyautogui 非 Windows 回退；`--delay=0.15` 调步间间隔。
- Windows PowerShell 下内联 JSON 的双引号会被剥离：请先把步骤存为 steps.json 再传文件路径（脚本容忍 BOM）。

## 单步：后台虚拟输入（Win32 应用，不占物理光标、不抢焦点）

```bash
python <SKILL_DIR>/scripts/virtual_mouse.py click 500 300 left [--double]
python <SKILL_DIR>/scripts/virtual_mouse.py scroll 640 360 -3
python <SKILL_DIR>/scripts/virtual_mouse.py drag 100 200 400 500
python <SKILL_DIR>/scripts/virtual_mouse.py type 500 300 你好 hello
python <SKILL_DIR>/scripts/virtual_mouse.py key 500 300 "ctrl+shift+s"
```

PostMessage 直达坐标处窗口（键盘经 GetGUIThreadInfo 解析其焦点子控件）。
Chromium/Electron/DirectUI 类应用忽略合成消息——浏览器一律改用上面的 CDP 通道。

## 前台回退（须用户同意，会移动物理光标/改变焦点）

```bash
python <SKILL_DIR>/scripts/real_input.py click 500 300 left [--double]
python <SKILL_DIR>/scripts/real_input.py type "文本"
python <SKILL_DIR>/scripts/real_input.py key "ctrl+s"
```

`mouse_ops.py` 提供同命令并自动回退 pyautogui（非 Windows）。开发与自动化测试禁止使用前台通道，
应在自有隔离窗口（隐藏/offscreen 父窗口 + 标准控件）内用 PostMessage 直接验证。

## 抗遮挡截图验证

```bash
python <SKILL_DIR>/scripts/screenshot_verify.py capture before          # 全屏
python <SKILL_DIR>/scripts/screenshot_verify.py window "无标题 - 记事本" t1   # PrintWindow 抓指定窗口
python <SKILL_DIR>/scripts/screenshot_verify.py compare <a> <b>
```

`window` 用 PrintWindow 抓目标窗口——被遮挡/不在前台也能截到其内容；任务窗口被最小化时
先 `browser_ops.py restore` 或 ShowWindow(SW_SHOWNOACTIVATE) 恢复（不激活、不抢焦点）。

## 与其他技能集成 / 注意事项

- 三通道：PostMessage（Win32）→ CDP（浏览器）→ UIA（实验性备用）；前台 SendInput 仅经用户同意。
- 所有操作经 `safety_gate.py` 门禁；分辨率/多屏变化需重取坐标；`mouse_ops.py position` 仅读不写。
