#!/usr/bin/env python3
"""hud_overlay.py — HUD 提示浮窗：置顶、不抢焦点、点击穿透，显示当前自动化操作，不打扰用户。"""
import sys, os, json, time, subprocess

def cache():
    if os.environ.get("SAFE_MOUSE_CACHE"): return os.environ["SAFE_MOUSE_CACHE"]
    if os.name == "nt": return os.path.join(os.environ.get("LOCALAPPDATA", "~"), "safe-mouse-automation")
    return os.path.expanduser("~/Library/Caches/safe-mouse-automation" if sys.platform == "darwin" else "~/.cache/safe-mouse-automation")

def state(): return os.path.join(cache(), "hud", "state.json")

def _write(text, ttl):
    d = os.path.dirname(state()); root = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.realpath(d) == root or os.path.realpath(d).startswith(root + os.sep):
        raise SystemExit("拒绝写入：HUD 缓存不得位于 skill 目录")
    os.makedirs(d, exist_ok=True)
    json.dump({"text": text, "expires": time.time() + ttl}, open(state(), "w", encoding="utf-8"))

def _alive():
    try:
        os.kill(int(open(state() + ".pid").read().strip()), 0); return True
    except Exception: return False

def _spawn():
    kw = {"creationflags": 0x00000008 | 0x08000000, "close_fds": True} if os.name == "nt" else {"start_new_session": True}
    devnull = open(os.devnull, "r+b")
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "_run"], stdin=devnull, stdout=devnull, stderr=devnull, **kw)

def show(text, ttl=15):
    _write(text, float(ttl))
    if not _alive(): _spawn()
    return {"ok": True, "hud": text}

def hide():
    _write("", 0); return {"ok": True, "hud": "hidden"}

def _run():
    import tkinter as tk
    if os.name == "nt":  # DPI 感知：按物理像素定位，避免浮窗偏小/错位
        import ctypes
        try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try: ctypes.windll.user32.SetProcessDPIAware()
            except Exception: pass
    r = tk.Tk(); r.overrideredirect(True); r.configure(bg="#1e1e2e")
    r.attributes("-topmost", True); r.attributes("-alpha", 0.8)
    lbl = tk.Label(r, font=("Segoe UI", 10), bg="#1e1e2e", fg="#a6e3a1", padx=12, pady=6)
    lbl.pack(); hit = [False]
    def tick():
        try: d = json.load(open(state(), encoding="utf-8"))
        except Exception: d = {}
        t = d.get("text", "") if time.time() < d.get("expires", 0) else ""
        if t:
            lbl.config(text=t)
            if not r.winfo_viewable(): r.deiconify()
        elif r.winfo_viewable(): r.withdraw()
        if not hit[0] and r.winfo_viewable() and os.name == "nt":
            # 穿透+不抢焦点必须设在顶层帧窗口上；LAYERED 交给 -alpha 正确初始化
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
        if cmd == "show": r = show(a[1] if len(a) > 1 else "自动化运行中", a[2] if len(a) > 2 else 15)
        elif cmd == "hide": r = hide()
        else: r = {"help": "show <text> [ttl秒] | hide"}
        print(json.dumps(r, ensure_ascii=False, indent=2))
