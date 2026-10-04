#!/usr/bin/env python3
"""browser_channel.py — R1 浏览器通道策略（本技能唯一浏览器决策入口）。

铁律：**绝不**为用户已经在跑、已经登录的浏览器另开一次性 %TEMP% 空 profile
（旧 browser_cdp.py open 的缺陷：--user-data-dir=%TEMP%\browser-cdp-profile → 无收藏/无扩展/未登录
→ human_gate 报登录墙 → 反过来质问用户「你为什么没登录」，不可接受）。

严格按序（命中即止）：
 1) attach  附着用户**已经在跑**的 Edge/Chrome 窗口（真实 profile、已登录）：只读枚举窗口
    标题+屏幕矩形（UIA 只读，不激活/不置前/不动物理光标），动作交给统一输入后端
    scripts/input_ops.py 在该矩形坐标上发后台模拟鼠标/键盘。
 2) cdp-existing  需要 CDP 时先探测已存在的远调端口（--port > 9222/9223/9224，GET /json/version），
    能连就直接附着，不新起进程。
 3) cdp-persistent  连不上才用**本技能专属持久 profile**（固定路径、跨次复用）启动；
    若需登录，明确告诉用户「在这个窗口登录一次，以后一直记住」，绝不重复要求登录。
 4) ephemeral  仅当用户明确要「干净/无痕会话」时才允许一次性 profile（须显式 --ephemeral）。

命令: policy | windows [标题子串] [--match=] | plan [--port=] [--profile=] [--ephemeral] |
      ensure [--port=] [--profile=] [--ephemeral] [--browser=msedge|chrome] <url>
"""
import sys, os, json, time, shutil, subprocess, urllib.request
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BROWSER_KEYS = ("edge", "msedge", "chrome", "chromium", "浏览器", "google chrome")
PROBE_PORTS = (9222, 9223, 9224)


def _flag(name, default=None):
    for a in sys.argv:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def persistent_profile():
    """本技能专属**持久** profile：跨次复用，登录一次长期记住。绝不落 skill 目录、绝不用 %TEMP%。"""
    if _flag("--profile"):
        return os.path.abspath(os.path.expandvars(_flag("--profile")))
    env = os.environ.get("SAFE_MOUSE_BROWSER_PROFILE")
    if env:
        return os.path.abspath(os.path.expandvars(env))
    sms_home = os.environ.get("SMS_HOME") or os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SMS")
    p = os.path.join(sms_home, "tmp", "safe-mouse-automation", "browser-profile")
    if os.path.realpath(p).lower().startswith(os.path.realpath(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).lower()):
        raise SystemExit("拒绝：profile 不得位于 skill 目录")
    return p


def cdp_alive(port, timeout=1.2):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace")).get("Browser", "")
    except Exception:
        return None


def find_cdp_port(prefer=None):
    """探测已存在的远调端口（含用户浏览器/已起实例），能连就连。"""
    ports = ([int(prefer)] if prefer else []) + [p for p in PROBE_PORTS if str(p) != str(prefer)]
    for pt in ports:
        if cdp_alive(pt):
            return pt, cdp_alive(pt)
    return None, None


def browser_windows():
    """只读枚举 Edge/Chrome 顶层窗口（Win32 EnumWindows，不激活不置前）：标题+屏幕矩形+hwnd。"""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    res = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _):
        if not u.IsWindowVisible(h):
            return True
        n = u.GetWindowTextLengthW(h)
        if not n:
            return True
        b = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, b, n + 1)
        cls = ctypes.create_unicode_buffer(128)
        u.GetClassNameW(h, cls, 128)
        t = b.value.lower()
        if not any(k in t for k in BROWSER_KEYS):
            return True
        r = wintypes.RECT()
        u.GetWindowRect(h, ctypes.byref(r))
        res.append({"hwnd": h, "title": b.value, "class": cls.value,
                    "rect": [r.left, r.top, r.right, r.bottom],
                    "minimized": bool(u.IsIconic(h)),
                    "screen_xy": [(r.left + r.right) // 2, (r.top + r.bottom) // 2]})
        return True

    u.EnumWindows(CB(cb), 0)
    return res




def plan(port=None, ephemeral=False):
    """按 R1 顺序给出应走的通道（不启动任何东西、不激活任何窗口）。"""
    wins = browser_windows()
    pt, br = find_cdp_port(port)
    if pt:
        return {"channel": "cdp-existing", "port": pt, "browser": br,
                "note": "附着已存在的远调端口（用户已在跑的实例），不新起进程、不新 profile"}
    if wins:
        return {"channel": "attach", "windows": wins,
                "note": "附着用户已经在跑的浏览器窗口（真实 profile·已登录）：动作经 input_ops.py "
                        "在该窗口矩形坐标上发后台模拟鼠标/键盘；不激活、不置前、不动物理光标"}
    if ephemeral:
        return {"channel": "cdp-ephemeral", "profile": None,
                "note": "用户显式要求干净/无痕会话，才允许一次性 profile"}
    return {"channel": "cdp-persistent", "profile": persistent_profile(),
            "note": "无已运行窗口可附着：用本技能专属持久 profile 启动（跨次复用）。"
                    "若遇登录墙，请用户在**这个**窗口登录一次，以后一直记住；绝不重复要求登录"}


def ensure(url="about:blank", port=None, ephemeral=False, browser="msedge"):
    """R1 编排入口：返回本次该走的通道；只有 persistent/ephemeral 才真的启动进程。"""
    p = plan(port, ephemeral)
    if p["channel"] in ("attach", "cdp-existing"):
        return p
    if ephemeral:
        prof = os.path.join(os.environ.get("TEMP", "/tmp"), "safe-mouse-ephemeral-%d" % int(time.time()))
    else:
        prof = p.get("profile") or persistent_profile()
    exe = shutil.which(browser) or {
        "msedge": os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        "chrome": os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe")}.get(browser, browser)
    pt = int(port) if port else 9223
    os.makedirs(prof, exist_ok=True)
    subprocess.Popen([exe, f"--user-data-dir={prof}", f"--remote-debugging-port={pt}",
                      "--remote-allow-origins=*", "--no-first-run", "--no-default-browser-check", url])
    for _ in range(30):
        time.sleep(1)
        if cdp_alive(pt):
            return {"channel": "cdp-ephemeral" if ephemeral else "cdp-persistent", "port": pt,
                    "profile": prof, "persistent": not ephemeral, "url": url,
                    "login_hint": (None if ephemeral else
                                   "首次需要登录时：请用户在此窗口登录一次，该 profile 跨次复用、以后一直记住")}
    return {"ok": False, "reason": f"{pt} 端口 30s 内未就绪（是否已有同端口实例？）", "profile": prof}


def _cli():
    a = [s for s in sys.argv[1:] if not s.startswith("--")]
    cmdn = a[0] if a else "help"
    ep = "--ephemeral" in sys.argv
    pr = _flag("--port")
    if cmdn == "policy":
        return {"order": ["attach(用户已运行窗口·真实profile·已登录)", "cdp-existing(探测已开远调端口)",
                          "cdp-persistent(本技能专属持久profile)", "cdp-ephemeral(仅用户显式要求干净会话)"],
                "forbidden": ["%TEMP% 一次性空 profile 作为默认", "反问用户为何没登录"],
                "persistent_profile": persistent_profile(), "ephemeral_flag": ep}
    if cmdn == "windows":
        w = browser_windows()
        m = (_flag("--match") or (a[1] if len(a) > 1 else "")).lower()
        return [x for x in w if not m or m in x["title"].lower()]
    if cmdn == "plan":
        return plan(pr, ep)
    if cmdn == "ensure":
        return ensure(a[1] if len(a) > 1 else "about:blank", pr, ep, _flag("--browser", "msedge"))
    return {"help": __doc__}


if __name__ == "__main__":
    try:
        r = _cli()
    except Exception as e:
        r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
