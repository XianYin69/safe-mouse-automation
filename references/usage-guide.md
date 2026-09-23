# 使用指南

## 依赖安装

```bash
pip install pyautogui Pillow
```

## 典型工作流

### 1. 点击操作（含截图验证）

```bash
# 截图前态
python <SKILL_DIR>/scripts/screenshot_verify.py capture before

# 执行点击
python <SKILL_DIR>/scripts/mouse_ops.py click 500 300 left

# 截图后态
python <SKILL_DIR>/scripts/screenshot_verify.py capture after

# 比对验证
python <SKILL_DIR>/scripts/screenshot_verify.py compare tmp/screenshots/before_*.png tmp/screenshots/after_*.png
```

### 2. 拖拽操作

```bash
python <SKILL_DIR>/scripts/mouse_ops.py drag 100 200 400 500
```

### 3. 安全检查

```bash
# 检查操作是否危险
python <SKILL_DIR>/scripts/safety_gate.py check "del important.txt"
# → {"allowed": false, "reason": "文件删除"}

# 列出禁止项
python <SKILL_DIR>/scripts/safety_gate.py list
```

## 与其他技能集成

- 类似 EasyEDAssistant 的双链路模式：CLI 脚本执行 + 截图验证。
- 可作为通用桌面自动化层供其他技能调用。
- 所有操作经 `safety_gate.py` 门禁，不通过则拒绝执行。

## 注意事项

- 屏幕分辨率变化时需重新确认坐标。
- 多显示器环境下 `pyautogui` 默认主屏坐标。
- 操作间隔建议 ≥ 300ms，避免系统来不及响应。
