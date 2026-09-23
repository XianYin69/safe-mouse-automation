# 安全策略

## 禁止操作清单

| 类别 | 关键词/模式 | 说明 |
|------|------------|------|
| 文件删除 | `del`, `rm`, `rmdir`, `Remove-Item -Recurse -Force` | 禁止任何形式的文件删除 |
| 磁盘格式化 | `format`, `diskpart`, `fdisk`, `mkfs`, `dd if=` | 禁止低级磁盘操作 |
| 注册表修改 | `reg add/delete/import`, `regedit` | 禁止注册表写入 |
| 系统关机/重启 | `shutdown`, `reboot`, `Stop-Computer` | 禁止系统电源操作 |
| 进程终止 | `taskkill`, `kill` | 禁止进程管理 |
| 任意命令执行 | `cmd /c`, `powershell -Command`, `sudo`, `runas` | 禁止提权与任意 shell |
| 用户/组管理 | `net user`, `net localgroup` | 禁止账户操作 |
| 服务变更 | `sc config/delete/stop`, `net stop` | 禁止服务管理 |
| 防火墙/网络 | `netsh`, `firewall`, `iptables` | 禁止网络配置变更 |

## 允许操作

鼠标移动、左/右/双击、拖拽、滚动、截图捕获、截图比对。

## 缓存与留痕（红线）

- 截图、tmp、日志等缓存文件一律不得写入 skill 目录（含 `<SKILL_DIR>/tmp`、`__pycache__` 等）。
- 默认落用户缓存目录：Windows `%LOCALAPPDATA%\safe-mouse-automation\`，
  macOS `~/Library/Caches/safe-mouse-automation/`，Linux `~/.cache/safe-mouse-automation/`。
- 可用环境变量 `SAFE_MOUSE_CACHE` 重定向；目标若解析到 skill 根内，脚本直接拒绝执行。

## 用户确认要求

- 涉及右键菜单中的修改性选项（如"删除"、"重命名后移动"）→ 必须请求用户确认。
- 拖拽文件到回收站区域 → 必须请求用户确认。
- 连续自动化操作超过 50 次 → 自动暂停，请求用户确认继续。
- 所有操作前后的截图必须保存，路径写入操作日志。
