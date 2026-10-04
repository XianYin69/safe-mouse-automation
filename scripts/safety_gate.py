#!/usr/bin/env python3
"""safety_gate.py — 安全门禁：检查操作是否危险，列出禁止项，请求用户确认。"""
import sys, os, json, re
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

# ---------- R3 focus-audit：静态扫描禁用 API（回归用，非零退出码＝存在违规） ----------
import tokenize

FOCUS_FORBIDDEN = [
    (r"SetForegroundWindow", "激活/抢前台焦点"),
    (r"BringWindowToTop", "置前窗口"),
    (r"SwitchToThisWindow", "切换前台窗口"),
    (r"AttachThreadInput", "窃取他线程输入绑定"),
    (r"SetCursorPos", "移动物理光标"),
    (r"mouse_event\s*\(", "物理鼠标事件"),
    (r"keybd_event\s*\(", "物理键盘事件"),
    (r"SetFocus\s*\(", "直接改键盘焦点"),
]
# 前台兜底白名单：real_input.py 的 SendInput/物理输入（须用户显式同意才走）
FOCUS_WHITELIST = {"real_input.py": ["SendInput", "SetCursorPos", "mouse_event", "keybd_event",
                                     "SetForegroundWindow", "BringWindowToTop"],
                   "mouse_ops.py": ["SetCursorPos", "mouse_event", "keybd_event", "SendInput"]}
SHOWWINDOW_OK = {"4", "SW_SHOWNOACTIVATE"}


def _code_lines(src):
    """返回「代码行」集合：排除注释行与字符串/文档行（避免文档措辞被误判为违规）。"""
    import io as _io
    lines = src.splitlines()
    skip = set()
    try:
        for tok in tokenize.generate_tokens(_io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                skip.update(range(tok.start[0], tok.end[0] + 1))
    except Exception:
        pass
    return {i + 1: t for i, t in enumerate(lines) if (i + 1) not in skip}


def focus_audit(root=None):
    import re
    d = root or os.path.dirname(os.path.abspath(__file__))
    hits = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".py"):
            continue
        p = os.path.join(d, fn)
        try:
            src = open(p, encoding="utf-8").read()
        except Exception as e:
            hits.append({"file": fn, "line": 0, "api": "<read>", "why": str(e)})
            continue
        wl = FOCUS_WHITELIST.get(fn, [])
        for ln, text in _code_lines(src).items():
            for pat, why in FOCUS_FORBIDDEN:
                if re.search(pat, text):
                    if any(w.lower() in text.lower() for w in wl):
                        continue
                    hits.append({"file": fn, "line": ln, "api": pat.rstrip("(\\s*"),
                                 "why": why, "code": text.strip()[:120]})
            for m in re.finditer(r"ShowWindow\s*\(\s*[^,]+,\s*([^)]+?)\)", text):
                arg = m.group(1).strip()
                if arg not in SHOWWINDOW_OK:
                    hits.append({"file": fn, "line": ln, "api": "ShowWindow(activate)",
                                 "why": f"ShowWindow 第二参={arg}，只允许 SW_SHOWNOACTIVATE(4)",
                                 "code": text.strip()[:120]})
    return {"ok": not hits, "violations": len(hits), "hits": hits,
            "scanned": [f for f in sorted(os.listdir(d)) if f.endswith(".py")],
            "whitelist": FOCUS_WHITELIST}

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cmd = args[0] if args else "help"
    if cmd == "check" and len(args) > 1:
        r = check(" ".join(args[1:]))
    elif cmd == "list":
        r = {"blocked": [b["reason"] for b in BLOCKED], "allowed": ALLOWED}
    elif cmd == "focus-audit":
        r = focus_audit(args[1] if len(args) > 1 else None)
    else:
        r = {"help": "check <action> | list | focus-audit [scripts目录]"}
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if cmd == "focus-audit" and not r.get("ok"):
        sys.exit(1)
