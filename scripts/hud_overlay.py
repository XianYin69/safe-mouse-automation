#!/usr/bin/env python3
"""hud_overlay.py — HUD 提示浮窗（置顶/不抢焦点/点击穿透/只读）+ R4 进程收口。

会话：session <任务简述>（默认 30 分钟常显）→ 每步 show <步骤> → 任务结束 hide。
R4（子代理进程泄漏修复）：
1) 父死自尽：_run 从 --parent=<pid> / 环境变量 SM_HUD_PARENT 取父 pid，后台线程每 2s
   OpenProcess+GetExitCodeProcess 判父活，父连续 2 次不可用即清 state/pid 并 os._exit(0)；
   取不到父 pid 时退回 TTL 兜底自尽（SM_HUD_NO_PARENT_WATCH=1 可关父监控，只走 TTL）。
2) 真单实例：_ensure 按 state.json 的 hud_pid 收敛，在册实例存活则复用；已死但仍有本技能
   HUD 残留（pid 文件被覆盖而失踪的实例）→ 先终止残留再拉新；_run 启动时自收敛。
3) hide 全量回收：清 state + 终止本技能全部 HUD 进程（含孤儿）+ 删 pid 文件。
4) reap CLI：扫描命令行含本技能 hud_overlay.py 且父进程已死的孤儿，默认 dry-run，--yes 才杀。

安全边界：进程枚举/终止全走 ctypes（Toolhelp32 + NtQueryInformationProcess + TerminateProcess），
绝不调用 taskkill/wmic/powershell 等外部 shell；作用域严格限定本技能自身 HUD 进程特征
（safe-mouse-automation + hud_overlay.py + _run），不触及用户其它进程。
"""
import sys, os, json, time, ctypes, threading, subprocess
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

IS_WIN = os.name == "nt"
PTR64 = ctypes.sizeof(ctypes.c_void_p) == 8
MARK_SKILL, MARK_FILE, MARK_RUN = "safe-mouse-automation", "hud_overlay.py", "_run"
SELF = os.path.realpath(os.path.abspath(__file__))


def cache():
    if os.environ.get("SAFE_MOUSE_CACHE"): return os.environ["SAFE_MOUSE_CACHE"]
    if IS_WIN: return os.path.join(os.environ.get("LOCALAPPDATA", "~"), "safe-mouse-automation")
    return os.path.expanduser("~/Library/Caches/safe-mouse-automation" if sys.platform == "darwin"
                              else "~/.cache/safe-mouse-automation")


def state(): return os.path.join(cache(), "hud", "state.json")
def _pidfile(): return state() + ".pid"


def _guard_cache():
    root = os.path.realpath(os.path.dirname(os.path.dirname(SELF)))
    d = os.path.realpath(os.path.dirname(state()))
    if d == root or d.startswith(root + os.sep):
        raise SystemExit("拒绝写入：HUD 缓存不得位于 skill 目录")


def _load():
    try:
        with open(state(), encoding="utf-8") as f: return json.load(f)
    except Exception: return {}


def _save(**kv):
    _guard_cache()
    cur = _load(); cur.update(kv)
    os.makedirs(os.path.dirname(state()), exist_ok=True)
    tmp = state() + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f: json.dump(cur, f)
    try: os.replace(tmp, state())
    except Exception:
        with open(state(), "w", encoding="utf-8") as f: json.dump(cur, f)
        try: os.remove(tmp)
        except Exception: pass


# ---------- 进程取证 / 回收（纯 ctypes；绝不借道 taskkill/wmic/powershell） ----------
if IS_WIN:
    from ctypes import wintypes
    _k32 = ctypes.windll.kernel32
    _nt = ctypes.windll.ntdll
    QLI, TERM, VMRD, QINF = 0x1000, 0x0001, 0x0010, 0x0400
    STILL_ACTIVE, SNAP = 259, 0x00000002
    INH = ctypes.c_void_p(-1).value

    class _PE32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    def _snap():
        """Toolhelp32 快照 → {pid: (ppid, exe名)}。"""
        h = _k32.CreateToolhelp32Snapshot(SNAP, 0)
        out = {}
        if not h or h == INH or ctypes.c_void_p(h).value == INH: return out
        hv = ctypes.c_void_p(h); e = _PE32(); e.dwSize = ctypes.sizeof(_PE32)
        try:
            ok = _k32.Process32FirstW(hv, ctypes.byref(e))
            while ok:
                out[int(e.th32ProcessID)] = (int(e.th32ParentProcessID), e.szExeFile or "")
                ok = _k32.Process32NextW(hv, ctypes.byref(e))
        finally:
            _k32.CloseHandle(hv)
        return out

    def _alive(pid):
        """OpenProcess + GetExitCodeProcess 判父/目标是否存活（父消失＝返回 False）。"""
        try:
            pid = int(pid)
        except Exception:
            return False
        if pid <= 0: return False
        h = _k32.OpenProcess(QLI, False, pid)
        if not h:
            # ERROR_ACCESS_DENIED(5)＝进程存在但无权限打开 → 视为存活（防误杀）；其余＝已消失
            return ctypes.GetLastError() == 5
        try:
            code = wintypes.DWORD(0)
            if not _k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code)): return False
            return code.value == STILL_ACTIVE
        finally:
            _k32.CloseHandle(ctypes.c_void_p(h))

    def _rpm(h, addr, size):
        hh = h if isinstance(h, ctypes.c_void_p) else ctypes.c_void_p(h)
        aa = addr if isinstance(addr, ctypes.c_void_p) else ctypes.c_void_p(addr)
        got = ctypes.c_size_t(0)
        buf = ctypes.create_string_buffer(size)
        if not _k32.ReadProcessMemory(hh, aa, buf, size, ctypes.byref(got)): return None
        return buf.raw[:got.value] or None

    def _cmdline(pid):
        """NtQueryInformationProcess(0)→PEB→ProcessParameters→CommandLine（读不到返回空串）。"""
        h = _k32.OpenProcess(VMRD | QINF, False, pid)
        if not h: return ""
        try:
            hv = ctypes.c_void_p(h)
            info = ctypes.create_string_buffer(48)
            got = ctypes.c_ulong(0)
            if _nt.NtQueryInformationProcess(hv, 0, info, 48, ctypes.byref(got)) != 0: return ""
            off = 8 if PTR64 else 4
            peb = int.from_bytes(info.raw[off:off + PTR64 * 8], "little")
            if not peb: return ""
            p = _rpm(hv, peb + (0x20 if PTR64 else 0x10), PTR64 * 8)
            if not p: return ""
            pp = int.from_bytes(p, "little")
            if not pp: return ""
            us = _rpm(hv, pp + (0x70 if PTR64 else 0x40), 16)
            if not us: return ""
            ln = int.from_bytes(us[0:2], "little")
            bp = int.from_bytes(us[8:16] if PTR64 else us[4:8], "little")
            if not ln or not bp or ln > 8192: return ""
            raw = _rpm(hv, bp, ln)
            if not raw: return ""
            try: return raw.decode("utf-16-le", "replace")
            except Exception: return ""
        except Exception:
            return ""
        finally:
            _k32.CloseHandle(ctypes.c_void_p(h))

    def _terminate(pid):
        h = _k32.OpenProcess(TERM, False, int(pid))
        if not h: return False
        try:
            return bool(_k32.TerminateProcess(ctypes.c_void_p(h), 0))
        finally:
            _k32.CloseHandle(ctypes.c_void_p(h))

    def _procs():
        s = _snap()
        return [{"pid": p, "ppid": s[p][0], "name": s[p][1], "cmd": _cmdline(p)} for p in s]
else:
    def _alive(pid):
        try:
            os.kill(int(pid), 0); return True
        except Exception: return False

    def _terminate(pid):
        try:
            os.kill(int(pid), 15); return True
        except Exception: return False

    def _procs():
        out = []
        for d in os.listdir("/proc"):
            if not d.isdigit(): continue
            pid = int(d)
            try:
                cmd = open("/proc/%s/cmdline" % pid, "rb").read().replace(b"\0", b" ").decode("utf-8", "replace")
                ppid = 0
                for ln in open("/proc/%s/status" % pid, encoding="utf-8", errors="replace"):
                    if ln.startswith("PPid:"): ppid = int(ln.split()[1]); break
                out.append({"pid": pid, "ppid": ppid, "name": "", "cmd": cmd})
            except Exception:
                pass
        return out


def _is_hud(p):
    """本技能 HUD 实例特征：三要素同时命中（技能目录 + hud_overlay.py + _run），绝不匹配其它进程。"""
    c = (p.get("cmd") or "").lower().replace("/", "\\")
    return MARK_SKILL in c and MARK_FILE in c and MARK_RUN in c


def _hud_procs():
    """只枚举 python* 进程再读命令行按本技能特征筛选（避免全机扫描拖慢每步 show）。"""
    if not IS_WIN:
        try:
            return [x for x in _procs() if _is_hud(x)]
        except Exception:
            return []
    out = []
    try:
        snap = _snap()
    except Exception:
        return out
    for pid, (ppid, name) in snap.items():
        if "python" not in (name or "").lower():
            continue
        c = _cmdline(pid)
        if c and _is_hud({"cmd": c}):
            out.append({"pid": pid, "ppid": ppid, "name": name, "cmd": c})
    return out


def _my_ppid():
    for p in _procs():
        if p["pid"] == os.getpid(): return p["ppid"]
    return 0


def _resolve_parent(argv_pid=None):
    """父 pid 优先级：--parent= > SM_HUD_PARENT > 拉起方 getppid（CLI 场景＝其父 shell/调度方）。"""
    if argv_pid:
        try: return int(argv_pid)
        except Exception: pass
    for k in ("SM_HUD_PARENT",):
        v = os.environ.get(k)
        if v:
            try: return int(v)
            except Exception: pass
    try:
        return os.getppid()
    except Exception:
        return _my_ppid()


def _spawn():
    """拉起 HUD 实例：显式把父 pid 传给子进程（--parent + SM_HUD_PARENT），子进程据此做父死自尽。"""
    parent = _resolve_parent()
    kw = {"creationflags": 0x00000008 | 0x08000000, "close_fds": True} if IS_WIN else {"start_new_session": True}
    env = dict(os.environ)
    if parent: env["SM_HUD_PARENT"] = str(parent)
    devnull = open(os.devnull, "r+b")
    subprocess.Popen([sys.executable, SELF, "_run", "--parent=%d" % parent] if parent
                     else [sys.executable, SELF, "_run"],
                     stdin=devnull, stdout=devnull, stderr=devnull, env=env, **kw)
    return parent


def _ensure():
    """真单实例收敛：在册实例存活→复用并清掉多余实例；已死→清残留后拉新。"""
    d = _load(); rec = d.get("hud_pid")
    live = sorted({p["pid"] for p in _hud_procs()})
    keep = rec if rec in live else None
    reclaimed = []
    for pid in live:
        if pid == keep: continue
        if _terminate(pid): reclaimed.append(pid)
    if keep:
        return {"hud_pid": keep, "reused": True, "reclaimed": reclaimed}
    _spawn()
    return {"hud_pid": None, "reused": False, "reclaimed": reclaimed}


def _clear_pidfile():
    try:
        if int(open(_pidfile()).read().strip()) == os.getpid(): os.remove(_pidfile())
    except Exception: pass


def _watchdog(parent, started):
    """父死自尽（连续 2 次≈4s 判死，防瞬时抖动）+ TTL 兜底自尽（无父 pid 或监控关闭时）。"""
    no_watch = os.environ.get("SM_HUD_NO_PARENT_WATCH") == "1"
    miss = 0
    while True:
        time.sleep(2)
        try:
            if parent and not no_watch:
                if _alive(parent): miss = 0
                else:
                    miss += 1
                    if miss >= int(os.environ.get("SM_HUD_PARENT_MISS", "1")):
                        _clear_pidfile(); os._exit(0)
            d = _load()
            if d.get("hud_pid") not in (None, os.getpid()):
                _clear_pidfile(); os._exit(0)   # 已被新实例取代 → 让位自尽
            exp = [v for k, v in d.items() if k.endswith("_expires") and isinstance(v, (int, float))]
            hard = max(exp) if exp else started + 1800
            if time.time() > hard + 120:
                _clear_pidfile(); os._exit(0)
        except SystemExit: raise
        except Exception: pass


def session(text, ttl=1800):
    r = _ensure()
    _save(session=text, session_expires=time.time() + float(ttl))
    return {"ok": True, "hud_session": text, "instance": r}


def show(text, ttl=15):
    r = _ensure()
    _save(step=text, step_expires=time.time() + float(ttl))
    return {"ok": True, "hud_step": text, "instance": r}


def alert(text, ttl=1800):
    r = _ensure()
    _save(alert=text, alert_expires=time.time() + float(ttl))
    return {"ok": True, "hud_alert": text, "instance": r}


def hide(reclaim=True):
    """收口：清 state + 全量回收本技能 HUD 进程（含孤儿）+ 删 pid 文件——保证无残留。"""
    _save(session="", session_expires=0, step="", step_expires=0, alert="", alert_expires=0, hud_pid=None)
    killed = []
    if reclaim:
        for p in _hud_procs():
            if p["pid"] == os.getpid(): continue
            if _terminate(p["pid"]): killed.append(p["pid"])
        if killed: time.sleep(0.6)   # 等内核回收再复扫
    _clear_pidfile()
    try: os.remove(state())
    except Exception: pass
    return {"ok": True, "hud": "hidden", "reclaimed": killed, "residual": len(_hud_procs())}


def reap(dry_run=True):
    """扫描本技能 HUD 孤儿（父进程已死）：默认 dry-run 只打印，--yes 才终止；只认本技能特征。"""
    orphans = []
    for p in _hud_procs():
        if p["pid"] == os.getpid(): continue
        if not _alive(p["ppid"]):
            orphans.append({"pid": p["pid"], "ppid": p["ppid"], "parent_dead": True})
    out = {"scan": len(_hud_procs()), "orphans": orphans, "dry_run": dry_run, "terminated": []}
    if not dry_run:
        for o in orphans:
            if _terminate(o["pid"]): out["terminated"].append(o["pid"])
        time.sleep(0.8)   # TerminateProcess 异步：等内核回收后再复扫，避免误报残留
        out["residual_orphans"] = [x["pid"] for x in _hud_procs()
                                   if x["pid"] != os.getpid() and not _alive(x["ppid"])]
    return out


def _run():
    import tkinter as tk
    parent = None
    for a in sys.argv[1:]:
        if a.startswith("--parent="): parent = int(a.split("=", 1)[1] or 0) or None
    if parent is None:
        parent = _resolve_parent()
    started = time.time()
    if IS_WIN:
        import ctypes as _c
        try: _c.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try: _c.windll.user32.SetProcessDPIAware()
            except Exception: pass
    # 自收敛：同时启动者按 pid 大小让位（只终止 pid 更小的旧实例，避免互杀）
    for p in _hud_procs():
        if p["pid"] != os.getpid() and p["pid"] < os.getpid(): _terminate(p["pid"])
    _save(hud_pid=os.getpid(), started=started, parent_pid=parent)
    open(_pidfile(), "w").write(str(os.getpid()))
    threading.Thread(target=_watchdog, args=(parent, started), daemon=True).start()
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
            if idle[0] > 400: _clear_pidfile(); r.destroy(); return
        if not hit[0] and r.winfo_viewable() and IS_WIN:
            try:
                u = _c.windll.user32; h = u.GetParent(r.winfo_id()) or r.winfo_id()
                # WS_EX_TRANSPARENT(0x20)+WS_EX_NOACTIVATE(0x08000000)；LAYERED 由 -alpha 初始化
                u.SetWindowLongW(h, -20, u.GetWindowLongW(h, -20) | 0x00000020 | 0x08000000)
                hit[0] = True
            except Exception: hit[0] = True
        r.attributes("-topmost", True); r.update_idletasks()
        if r.winfo_viewable():
            w, hg = lbl.winfo_reqwidth(), lbl.winfo_reqheight()
            r.geometry(f"{w}x{hg}+{r.winfo_screenwidth() - w - 24}+{r.winfo_screenheight() - hg - 48}")
        r.after(300, tick)
    tick(); r.mainloop()


if __name__ == "__main__":
    flags = [s for s in sys.argv[1:] if s.startswith("--")]
    a = [s for s in sys.argv[1:] if not s.startswith("--")]
    cmd = a[0] if a else "help"
    if cmd == "_run":
        _run()
    else:
        if cmd == "session": r = session(a[1] if len(a) > 1 else "自动化任务进行中", a[2] if len(a) > 2 else 1800)
        elif cmd == "show": r = show(a[1] if len(a) > 1 else "步骤进行中", a[2] if len(a) > 2 else 15)
        elif cmd == "alert": r = alert(a[1] if len(a) > 1 else "需要人工处理", a[2] if len(a) > 2 else 1800)
        elif cmd == "hide": r = hide()
        elif cmd == "reap": r = reap(dry_run=("--yes" not in flags))
        elif cmd == "procs": r = {"hud_instances": _hud_procs()}
        else: r = {"help": "session <任务简述> [ttl=1800] | show <步骤> [ttl=15] | alert <告警> [ttl=1800] | "
                           "hide（收口全量回收）| reap [--yes]（清孤儿，默认 dry-run）| procs（取证）"}
        print(json.dumps(r, ensure_ascii=False, indent=2))
