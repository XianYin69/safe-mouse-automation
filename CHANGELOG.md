# CHANGELOG

## 2026-10-02 — 屏幕视觉能力改为依赖 screen-vision（自研实现废除）

- **`scripts/screenshot_verify.py` 重写为纯委托层**：删除自研 Win32 GDI 窗口抓取整段
  （EnumWindows + PrintWindow/GetDIBits + 位图回读）、`PIL.ImageChops` 像素直方图比对、
  `ImageGrab` 全屏抓取；改为 subprocess 委托 screen-vision 的 `sw.py` / `describe.py` /
  `recognize.py`，本层只做路径解析与算术胶水（不 import PIL/ctypes）。
- **向后兼容保留**：模块名 `screenshot_verify`、子命令 `capture/window/compare/dir`、
  函数签名 `capture(region=None, label="")` / `compare(path_a, path_b, threshold=0.95)` /
  `capture_window(title_part, label="")`、`cache_base()` 与 `ensure_dir()`（`browser_cdp.py` 依赖）、
  「拒绝写入 skill 目录」守卫与 stdout UTF-8 重配置。
- **新增子命令/函数**：`ask <窗口|图片> <问题> [--structured]`、`objects <窗口|图片>`
  （契约 v2，`screen_xy` 为屏幕物理像素绝对坐标，可直接喂 `virtual_mouse`）。
- **依赖解析**：env `SCREEN_VISION_HOME`（技能根或 `scripts` 皆可）> `~/.kilocode/skills/screen-vision/scripts`；
  缺失只返回 error 并 exit 1，**不自动安装、不回退自研**；委托失败原样透传 stderr，不重试不猜。
- **行为差异（须知）**：screen-vision 截**屏幕矩形像素**，被遮挡会截进遮挡内容，且**无全屏截取模式**；
  `capture` 现为 z-order 顶层窗口截取并附 `note`；`region` 参数已废除（返回 error）。
  抗遮挡优先 `browser_cdp.py shot` 或先 `ShowWindow(SW_SHOWNOACTIVATE)` 恢复再截——遮挡不停止任务。
- **文档同步**：`SKILL.md`（步骤4/6、铁律「遮挡不停止」、依赖条目、description）、
  `README.md`（能力表、示例、依赖）、`references/usage-guide.md`（小节更名「截图与视觉验证（委托
  screen-vision）」）、`agent/instructions.md`、`agent/agent_prompt.md`、`agent/CLAUDE.md`、
  `agent/.cursorrules` 中的 PrintWindow 表述全部更正。
- **新增依赖清单**：`dependence/dependence.md` + `dependence/deps.json`，把 `screen-vision`
  登记为**技能级依赖**（`Pillow` 降级为 screen-vision 侧的间接依赖）。
