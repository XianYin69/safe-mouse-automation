#!/usr/bin/env python3
"""human_gate.py — 真人验证门禁：检测到验证码/人机验证/登录墙时**立即停止任务**并在 HUD 显示
详细信息（哪个应用、哪种验证、证据文本、等待用户手动完成）。绝不尝试绕过或破解验证。
检测源：窗口标题+UIA 控件文本（check）、浏览器页面正文（web）、全部可见窗口（scan）。
命令: check <窗口子串> | web [--port=9223 --match=子串] | scan | clear   退出码: 0=正常 3=需人工"""
import sys, os, json, re, subprocess
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hud_overlay

HARD = [("验证码", "captcha"), ("人机验证", "human-verify"), ("安全验证", "security-verify"),
        ("滑动拼图", "slider"), ("拖动滑块", "slider"), ("拼图验证", "puzzle"), ("短信验证码", "sms-code"),
        ("扫码登录", "qr-login"), ("智能验证", "smart-verify"), ("点击按钮进行验证", "verify"),
        ("请完成验证", "verify"), ("recaptcha", "captcha"), ("verify you are (a )?human|are you a robot", "human-verify"),
        ("geetest", "captcha"), ("防水墙", "captcha"), ("hcaptcha", "captcha")]
SOFT = [("请登录", "login"), ("账号登录", "login"), ("手机号登录", "login"), ("欢迎登录", "login"),
        ("登录后查看", "login-gate"), ("请先登录", "login"), ("登录以管理", "login"), ("登录以", "login"),
        ("密码", "login-form"), ("sign in", "login"), ("log in", "login"), ("login", "login")]
BARE_LOGIN = ("登录", "login")  # 裸"登录"仅在页面主体极短（登录墙特征）时判定，避免电商导航栏误报

def _scan_text(text):
    hits = []
    low = (text or "").lower()
    for pat, kind in HARD:
        if re.search(pat.lower(), low): hits.append({"kind": kind, "pattern": pat, "hard": True})
    if not hits:
        for pat, kind in SOFT:
            if re.search(pat.lower(), low): hits.append({"kind": kind, "pattern": pat, "hard": False})
        if not hits and BARE_LOGIN[0] in (text or "") and len((text or "").strip()) < 400:
            hits.append({"kind": BARE_LOGIN[1], "pattern": BARE_LOGIN[0], "hard": False})
    return hits

def _win_texts(sub):
    import ctypes
    u = ctypes.windll.user32
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    titles = []
    def cb(h, _):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1)
                if sub.lower() in b.value.lower(): titles.append(b.value)
        return True
    u.EnumWindows(CB(cb), 0)
    names = []
    try:
        import uiautomation as ua
        for w in ua.GetRootControl().GetChildren():
            try:
                if sub.lower() in (w.Name or "").lower():
                    names.append(w.Name or "")
                    from browser_ops import _els
                    for i, c in enumerate(_els(w)):
                        if i > 400: break
                        try:
                            nm = (c.Name or "").strip()
                            if nm: names.append(nm)
                        except Exception: continue
                    break
            except Exception: continue
    except ImportError:
        pass
    return titles, names

def check(sub):
    titles, names = _win_texts(sub)
    hits = _scan_text(" ".join(titles))
    if not hits:
        for nm in names:
            hits = _scan_text(nm)
            if hits: break
    if hits:
        ev = (titles or names)[:3]
        alert(sub, hits, ev)
        return {"blocked": True, "stop": True, "window": sub, "hits": hits, "evidence": ev,
                "action_required": "请用户在屏幕上手动完成验证/登录后回复继续"}
    return {"blocked": False, "window": sub}

def alert(win, hits, ev):
    kinds = "/".join(sorted({h["kind"] for h in hits}))[:28]
    ev0 = str(ev[0])[:28] if ev else ""
    hud_overlay.alert(f"需人工验证[{win[:16]}] 类型={kinds} 证据={ev0} 请手动完成后告知继续", 1800)

def web(port=None, match=""):
    args = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_cdp.py")]
    if port: args.append(f"--port={port}")
    if match: args.append(f"--match={match}")
    js = "document.title + ' | ' + (document.body ? document.body.innerText.slice(0, 2500) : '')"
    out = subprocess.run(args + ["eval", js], capture_output=True, text=True, timeout=60).stdout
    try:
        text = json.loads(out).get("value") or ""
    except Exception:
        text = out
    hits = _scan_text(text)
    if hits:
        alert(match or "browser", hits, [text[:80]])
        return {"blocked": True, "stop": True, "via": "cdp", "hits": hits, "evidence": text[:120],
                "action_required": "请用户在浏览器中手动完成验证/登录后回复继续"}
    return {"blocked": False, "via": "cdp"}

def scan():
    import ctypes
    u = ctypes.windll.user32
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    titles = []
    def cb(h, _):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1)
                titles.append(b.value)
        return True
    u.EnumWindows(CB(cb), 0)
    bad = [{"window": t, "hits": _scan_text(t)} for t in titles if _scan_text(t)]
    return {"blocked": bool(bad), "matches": bad}

if __name__ == "__main__":
    a = [s for s in sys.argv[1:] if not s.startswith("--")]
    fl = [s for s in sys.argv[1:] if s.startswith("--")]
    cmd = a[0] if a else "help"
    port = next((f.split("=", 1)[1] for f in fl if f.startswith("--port=")), None)
    match = next((f.split("=", 1)[1] for f in fl if f.startswith("--match=")), "")
    if cmd == "check": r = check(a[1])
    elif cmd == "web": r = web(port, match)
    elif cmd == "scan": r = scan()
    elif cmd == "clear": r = hud_overlay.hide()
    else: r = {"help": "check <窗口子串> | web [--port= --match=] | scan | clear"}
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(3 if r.get("blocked") else 0)
