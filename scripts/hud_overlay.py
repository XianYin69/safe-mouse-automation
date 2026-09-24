#!/usr/bin/env python3
"""hud_overlay.py — HUD 提示浮窗：置顶、不抢焦点、点击穿透，只读展示。
会话规则：任务开始 session <任务简述>（全程常显，默认 30 分钟），每步 show <步骤>（短时效），
任务结束才 hide；session 与 step 分行渲染，两者都过期/为空时自动 withdraw，空闲 120s 进程自退。"""
import sys, os, json, time, subprocess
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def cache():
    if os.environ.get("SAFE_MOUSE_CACHE"): return os.environ["SAFE_MOUSE_CACHE"]
    if os.name == "nt": return os.path.join(os.environ.get("LOCALAPPDATA", "~"), "safe-mouse-automation")
    return os.path.expanduser("~/Library/Caches/safe-mouse-automation" if sys.platform == "darwin" else "~/.cache/safe-mouse-automation")

def state(): return os.path.join(cache(), "hud", "state.json")

def _load():
    try: return json.load(open(state(), encoding="utf-8"))
    except Exception: return {}

def _save(**kv):
    root = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = os.path.dirname(state())
    if os.path.realpath(d) == root or os.path.realpath(d).startswith(root + os.sep):
        raise SystemExit("拒绝写入：HUD 缓存不得位于 skill 目录")
    cur = _load(); cur.update(kv)
    os.makedirs(d, exist_ok=True); json.dump(cur, open(state(), "w", encoding="utf-8"))

def _alive():
    try:
        os.kill(int(open(state() + ".pid").read().strip()), 0); return True
    except Exception: return False

def _spawn():
    kw = {"creationflags": 0x00000008 | 0x08000000, "close_fds": True} if os.name == "nt" else {"start_new_session": True}
    devnull = open(os.devnull, "r+b")
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "_run"], stdin=devnull, stdout=devnull, stderr=devnull, **kw)

def _ensure():
    if not _alive(): _spawn()

def session(text, ttl=1800):
    _save(session=text, session_expires=time.time() + float(ttl)); _ensure()
    return {"ok": True, "hud_session": text}

def show(text, ttl=15):
    _save(step=text, step_expires=time.time() + float(ttl)); _ensure()
    return {"ok": True, "hud_step": text}

def alert(text, ttl=1800):
    """真人验证/登录墙等需人工介入的告警行（红色⚠，默认 30 分钟，优先于 session/step 显示）。"""
    _save(alert=text, alert_expires=time.time() + float(ttl)); _ensure()
    return {"ok": True, "hud_alert": text}

def hide():
    _save(session="", session_expires=0, step="", step_expires=0, alert="", alert_expires=0)
    return {"ok": True, "hud": "hidden"}

def _kill_stale():
    if os.name != "nt": return
    try:
        ps = "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | " \
             "Where-Object { $_.CommandLine -match 'hud_overlay' -and $_.ProcessId -ne $PID } | ForEach-Object ProcessId"
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=15).stdout
        for pid in [int(x) for x in out.split() if x.strip().isdigit() and int(x) != os.getpid()]:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=10)
    except Exception: pass

def _run():
    import tkinter as tk
    _kill_stale()
    if os.name == "nt":  # DPI 感知：按物理像素定位
        import ctypes
        try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try: ctypes.windll.user32.SetProcessDPIAware()
            except Exception: pass
    r = tk.Tk(); r.overrideredirect(True); r.configure(bg="#1e1e2e")
    r.attributes("-topmost", True); r.attributes("-alpha", 0.85)
    lbl = tk.Label(r, font=("Segoe UI", 10), bg="#1e1e2e", fg="#a6e3a1", padx=12, pady=6, justify="left")
    lbl.pack(); hit = [False]; idle = [0]
    def tick():
        d = _load(); now = time.time(); lines = []; red = False
        if d.get("alert") and now < d.get("alert_expires", 0):
            lines.append("⚠ " + d["alert"]); red = True
        if d.get("session") and now < d.get("session_expires", 0): lines.append("◆ " + d["session"])
        if d.get("step") and now < d.get("step_expires", 0): lines.append("  " + d["step"])
        t = "\n".join(lines)
        if t:
            idle[0] = 0; lbl.config(text=t, fg="#f38ba8" if red else "#a6e3a1")
            if not r.winfo_viewable(): r.deiconify()
        elif r.winfo_viewable():
            r.withdraw(); idle[0] += 1
            if idle[0] > 400: r.destroy(); return  # 空闲 120s 自动退出
        if not hit[0] and r.winfo_viewable() and os.name == "nt":
            # 穿透+不抢焦点设在顶层帧窗口；LAYERED 由 -alpha 正确初始化
            import ctypes
            u = ctypes.windll.user32; h = u.GetParent(r.winfo_id()) or r.winfo_id()
            u.SetWindowLongW(h, -20, u.GetWindowLongW(h, -20) | 0x00000020 | 0x08000000)
            hit[0] = True
        r.attributes("-topmost", True); r.update_idletasks()
        if r.winfo_viewable():
            w, hg = lbl.winfo_reqwidth(), lbl.winfo_reqheight()
            r.geometry(f"{w}x{hg}+{r.winfo_screenwidth() - w - 24}+{r.winfo_screenheight() - hg - 48}")
        r.after(300, tick)
    open(state() + ".pid", "w").write(str(os.getpid())); tick(); r.mainloop()

if __name__ == "__main__":
    a = [s for s in sys.argv[1:] if not s.startswith("--")]; cmd = a[0] if a else "help"
    if cmd == "_run": _run()
    else:
        if cmd == "session": r = session(a[1] if len(a) > 1 else "自动化任务进行中", a[2] if len(a) > 2 else 1800)
        elif cmd == "show": r = show(a[1] if len(a) > 1 else "步骤进行中", a[2] if len(a) > 2 else 15)
        elif cmd == "alert": r = alert(a[1] if len(a) > 1 else "需要人工处理", a[2] if len(a) > 2 else 1800)
        elif cmd == "hide": r = hide()
        else: r = {"help": "session <任务简述> [ttl秒=1800] | show <步骤> [ttl秒=15] | alert <告警> [ttl秒=1800] | hide"}
        print(json.dumps(r, ensure_ascii=False, indent=2))
