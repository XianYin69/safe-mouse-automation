# dependence（依赖清单）

SMS 安装本技能时按此清单同检同净化：**只检查、不自动安装**（缺项只报错，见下方红线）。

## 技能级依赖（必需）

| 技能 | 承担能力 | 入口脚本 | 缺失表现 | 路径解析 |
|---|---|---|---|---|
| `screen-vision` | 窗口枚举/截取、视觉识别、像素通道统计 | `scripts/sw.py`、`scripts/recognize.py`、`scripts/describe.py` | `screenshot_verify.py` 返回 `{"error":"screen-vision 未安装或路径不对，请设 SCREEN_VISION_HOME"}` 且 exit 1 | env `SCREEN_VISION_HOME`（指技能根或 `scripts` 皆可）> `~/.kilocode/skills/screen-vision/scripts` |

- `screenshot_verify.py` 是**纯委托层**：自研 PrintWindow 抓窗口、像素直方图比对、全屏抓取**已废除**。
- 安装方式：经 SMS 技能注册表安装 `screen-vision`；**本技能不代跑安装、不 pip 安装、缺失不回退自研**。
- 遮挡语义：screen-vision 截**屏幕矩形像素**，被遮挡会截进遮挡内容，且**无全屏截取模式**；
  抗遮挡优先 `browser_cdp.py shot`（页面级）或先 `ShowWindow(SW_SHOWNOACTIVATE)` 恢复再截。

## Python 包（本技能脚本直接依赖）

| 包 | 版本（实测） | 用途 | 缺失表现 |
|---|---|---|---|
| `websocket-client` | 1.9.2 | `browser_cdp.py` CDP 通道 | 对应子命令 import 失败报错 |
| `uiautomation` | 2.0.29 | `app_ops/desktop_ops/browser_ops/human_gate` UIA 枚举与操作 | 对应子命令报错 |
| `pyautogui` | 0.9.54 | 仅非 Windows 平台回退（`mouse_ops.py`） | Windows 上不需要 |

- 虚拟输入（`virtual_mouse.py`）与 HUD（`hud_overlay.py`）为纯标准库（ctypes/tkinter）。
- `Pillow` 现由 **screen-vision 侧**使用（截取与像素统计），本技能脚本不再直接 import。

建议命令（用户自行确认后执行，本技能不代跑）：
`python -m pip install websocket-client uiautomation`

## 上游服务

- SMS 原生大模型网关（`ask`/`objects` 用）：`config.json` 的 `llm_gateway.base_url`；
  网关未启用 → screen-vision 报错即原样透传，不重试、不回退。

## 运行时

- Python 3.14.5（实测；3.10+ 应可用，未验证）；Windows 10/11。
