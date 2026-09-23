# 使用指南

## 依赖安装

```bash
pip install pyautogui Pillow
```

## 缓存目录（红线：不写入 skill 目录）

- Windows `%LOCALAPPDATA%\safe-mouse-automation\screenshots\`；macOS `~/Library/Caches/safe-mouse-automation/screenshots/`；Linux `~/.cache/...` 同构路径。
- 环境变量 `SAFE_MOUSE_CACHE` 可重定向；解析结果落在 skill 根内时脚本直接拒绝。
- 查看当前缓存根：`python <SKILL_DIR>/scripts/screenshot_verify.py dir`

## 典型工作流

### 1. 点击操作（含截图验证）

```bash
python <SKILL_DIR>/scripts/screenshot_verify.py capture before   # 前态 → 输出 JSON.path
python <SKILL_DIR>/scripts/mouse_ops.py click 500 300 left       # 执行点击
python <SKILL_DIR>/scripts/screenshot_verify.py capture after    # 后态 → 输出 JSON.path
python <SKILL_DIR>/scripts/screenshot_verify.py compare <before路径> <after路径>
```

capture/compare 均输出 JSON；把前两条 capture 返回的 `path` 填入 compare 命令即可。

### 2. 拖拽 / 滚动 / 取坐标

```bash
python <SKILL_DIR>/scripts/mouse_ops.py drag 100 200 400 500
python <SKILL_DIR>/scripts/mouse_ops.py scroll 640 360 -3
python <SKILL_DIR>/scripts/mouse_ops.py position
```

### 3. 安全检查

```bash
python <SKILL_DIR>/scripts/safety_gate.py check "del important.txt"  # → {"allowed": false, "reason": "文件删除"}
python <SKILL_DIR>/scripts/safety_gate.py list                       # 列出禁止项与允许项
```

## 与其他技能集成

- 类似 EasyEDAssistant 的双链路模式：CLI 脚本执行 + 截图验证；可作通用桌面自动化层供其他技能调用。
- 所有操作经 `safety_gate.py` 门禁，不通过则拒绝执行。

## 注意事项

- 屏幕分辨率变化时需重新确认坐标；多显示器下 `pyautogui` 默认主屏；操作间隔建议 ≥ 300ms。
