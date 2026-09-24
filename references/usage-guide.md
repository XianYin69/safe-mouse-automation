# 使用指南

## 依赖安装

```bash
pip install Pillow            # 截图需要；虚拟输入/HUD 为纯标准库实现
pip install pyautogui         # 仅非 Windows 平台回退需要
```

## 缓存目录（红线：不写入 skill 目录）

- Windows `%LOCALAPPDATA%\safe-mouse-automation\`（screenshots\ 与 hud\ 子目录）；
  macOS `~/Library/Caches/`、Linux `~/.cache/` 同构路径；env `SAFE_MOUSE_CACHE` 可重定向。
- 查看当前缓存根：`python <SKILL_DIR>/scripts/screenshot_verify.py dir`

## 推荐：批量流程（最快，默认后台虚拟输入 + HUD，零打扰）

```bash
python <SKILL_DIR>/scripts/batch_runner.py steps.json
```

- 步骤文件为 JSON 数组（op: click/scroll/drag/move/type/key/shot），一次进程连续执行；
  type 步骤带 `"x","y","text"`（文本打到该坐标窗口内的焦点控件），key 步骤带 `"combo"`（如 `"ctrl+s"`）；
  HUD 自动显示 `[i/n] desc`，结束自动隐藏；物理光标与前台焦点全程不动。
- `--real` 前台真输入回退（SendInput，**会打扰用户，须先取得同意**）；
  `--physical` pyautogui 非 Windows 回退；`--delay=0.15` 调步间间隔。
- Windows PowerShell 下内联 JSON 的双引号会被剥离：请先把步骤存为 steps.json 再传文件路径（脚本容忍 BOM）。

## 单步：后台虚拟输入（默认，不占物理光标、不抢焦点）

```bash
python <SKILL_DIR>/scripts/virtual_mouse.py click 500 300 left [--double]
python <SKILL_DIR>/scripts/virtual_mouse.py scroll 640 360 -3
python <SKILL_DIR>/scripts/virtual_mouse.py drag 100 200 400 500
python <SKILL_DIR>/scripts/virtual_mouse.py type 500 300 你好 hello    # Unicode 文本→坐标窗口焦点控件
python <SKILL_DIR>/scripts/virtual_mouse.py key 500 300 "ctrl+shift+s"
```

PostMessage 直达坐标处窗口（键盘经 GetGUIThreadInfo 解析其焦点子控件）。
Chromium/Electron/DirectUI 类应用常忽略合成消息；截图验证无变化时，**征得用户同意**再用前台回退。

## 前台回退（须用户同意，会移动物理光标/改变焦点）

```bash
python <SKILL_DIR>/scripts/real_input.py click 500 300 left [--double]
python <SKILL_DIR>/scripts/real_input.py type "文本"
python <SKILL_DIR>/scripts/real_input.py key "ctrl+s"
```

`mouse_ops.py` 提供同命令并自动回退 pyautogui（非 Windows）。开发与自动化测试禁止使用前台通道，
应在自有隔离窗口（隐藏/offscreen 父窗口 + 标准控件）内用 PostMessage 直接验证。

## HUD 提示浮窗（单独控制）

```bash
python <SKILL_DIR>/scripts/hud_overlay.py show "正在第 2/5 步：点击确认" 30   # 置顶、穿透、默认 15s 过期
python <SKILL_DIR>/scripts/hud_overlay.py hide
```

常驻显示进程自动拉起，状态文件外置；批量模式无需手动调用。无文本时浮窗自动 withdraw 不占屏幕。

## 典型工作流（后台执行 + 截图验证）

```bash
python <SKILL_DIR>/scripts/screenshot_verify.py capture before
python <SKILL_DIR>/scripts/virtual_mouse.py click 500 300 left
python <SKILL_DIR>/scripts/screenshot_verify.py capture after
python <SKILL_DIR>/scripts/screenshot_verify.py compare <before路径> <after路径>
```

## 与其他技能集成 / 注意事项

- 双链路模式：CLI 脚本执行 + 后台截图验证；可作通用桌面自动化层，所有操作经 `safety_gate.py` 门禁。
- 分辨率/多屏变化需重取坐标；`mouse_ops.py position` 仅读取光标位置，不改动任何状态。
