#!/usr/bin/env python3
"""safety_gate.py — 安全门禁：检查操作是否危险，列出禁止项，请求用户确认。"""
import sys, json, re
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BLOCKED = [
    {"pattern": r"del\s|rm\s|rmdir|Remove-Item.*-Recurse.*-Force", "reason": "文件删除"},
    {"pattern": r"format\s|diskpart|fdisk", "reason": "磁盘格式化"},
    {"pattern": r"reg\s+(add|delete|import)|regedit", "reason": "注册表修改"},
    {"pattern": r"shutdown|reboot|restart|Stop-Computer", "reason": "系统关机/重启"},
    {"pattern": r"taskkill|kill\s|taskkill", "reason": "进程终止"},
    {"pattern": r"sudo|runas|cmd\s/c|powershell.*-Command", "reason": "任意命令执行"},
    {"pattern": r"net\s(user|localgroup)|lusrmgr", "reason": "用户/组管理"},
    {"pattern": r"sc\s(config|delete|stop)|net\sstop", "reason": "系统服务变更"},
    {"pattern": r"netsh|firewall|iptables", "reason": "防火墙/网络配置"},
    {"pattern": r"mkfs|dd\sif=", "reason": "低级磁盘写入"},
]

ALLOWED = ["move", "click", "double_click", "right_click", "drag", "scroll", "screenshot", "capture", "compare", "type", "key"]

def check(action):
    for b in BLOCKED:
        if re.search(b["pattern"], action, re.IGNORECASE):
            return {"allowed": False, "reason": b["reason"], "pattern": b["pattern"]}
    return {"allowed": True}

def is_mouse_op(action):
    return action.lower().strip() in ALLOWED

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cmd = args[0] if args else "help"
    if cmd == "check" and len(args) > 1:
        r = check(" ".join(args[1:]))
    elif cmd == "list":
        r = {"blocked": [b["reason"] for b in BLOCKED], "allowed": ALLOWED}
    else:
        r = {"help": "check <action> | list"}
    print(json.dumps(r, ensure_ascii=False, indent=2))
