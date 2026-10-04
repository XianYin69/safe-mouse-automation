#!/usr/bin/env python3
"""browser_cdp.py — 浏览器后台通道（Chrome DevTools Protocol）：浏览器内核级模拟鼠标点击/滚轮/
打字/快捷键，窗口被遮挡、不在前台、未聚焦全部生效；不移动物理光标、不抢焦点、不激活窗口。
适用 Edge/Chrome；依赖 pip install websocket-client。坐标一律为页面 CSS 像素（与 getBoundingClientRect 一致）。
命令: open <url> | targets | eval <js> | click <x> <y> [left|right] [--double] | clickel <css选择器|text=文本>
      | type <文本> | key <组合键如ctrl+a/Enter> | scroll <x> <y> <dy> | shot [label] | navigate <url>
命令: attach  |  通道顺序(R1): 附着已运行窗口 > 探测已开远调端口 > 本技能专属持久 profile > 仅 --ephemeral 才一次性 profile（绝不默认 %TEMP% 空 profile）
通用参数: --port=9223 --match=<url或标题子串>"""
import sys, os, json, time, base64, subprocess, urllib.request
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def _flag(name, default=None):
    for a in sys.argv:
        if a.startswith(name + "="): return a.split("=", 1)[1]
    return default

PORT = int(_flag("--port", "9223"))
MATCH = _flag("--match", "") or ""

def targets():
    return json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=5)) and \
           json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5))

def page():
    try: ts = targets()
    except Exception: return None
    pages = [t for t in ts if t.get("type") == "page" and not t.get("url", "").startswith(("edge://", "chrome://"))]
    if MATCH: pages = [p for p in pages if MATCH.lower() in (p.get("url", "") + p.get("title", "")).lower()]
    return pages[0] if pages else None

def ws():
    p = page()
    if not p: raise RuntimeError(f"无匹配 CDP 页面 (port={PORT}, match={MATCH!r})；先执行 open")
    import websocket
    return websocket.create_connection(p["webSocketDebuggerUrl"], timeout=20), p

_id = [0]
def cmd(c, method, **params):
    _id[0] += 1; mid = _id[0]
    c.send(json.dumps({"id": mid, "method": method, "params": params}))
    while True:
        r = json.loads(c.recv())
        if r.get("id") == mid:
            if "error" in r: raise RuntimeError(r["error"].get("message", str(r["error"])))
            return r.get("result", {})

def ev(c, expr):
    r = cmd(c, "Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
    if r.get("exceptionDetails"): raise RuntimeError(str(r["exceptionDetails"])[:200])
    return r.get("result", {}).get("value")

def dispatch_click(c, x, y, button="left", double=False):
    cc = 2 if double else 1
    cmd(c, "Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=button, clickCount=cc)
    cmd(c, "Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button=button, clickCount=cc)

def find_pos(c, sel):
    if sel.startswith("text="):
        find = ("const els = [...document.querySelectorAll('a,button,[role=button],input[type=submit],span,div')];"
                " const e = els.find(x => (x.innerText || x.value || '').trim() === t) || els.find(x => (x.innerText || '').includes(t));")
        js = ("(() => { const t = %s; %s if (!e) return null; e.scrollIntoView({block: 'center'});"
              " return new Promise(r => setTimeout(() => { const b = e.getBoundingClientRect();"
              " r(b.width * b.height > 0 ? {x: b.x + b.width / 2, y: b.y + b.height / 2, text: (e.innerText || '').trim().slice(0, 40)} : null); }, 500)); })()"
              % (json.dumps(sel[5:]), find))
    else:
        js = ("(() => { const e = document.querySelector(%s); if (!e) return null; e.scrollIntoView({block: 'center'});"
              " return new Promise(r => setTimeout(() => { const b = e.getBoundingClientRect();"
              " r(b.width * b.height > 0 ? {x: b.x + b.width / 2, y: b.y + b.height / 2, text: (e.innerText || '').trim().slice(0, 40)} : null); }, 500)); })()"
              % json.dumps(sel))
    return ev(c, js)

def main():
    a = [s for s in sys.argv[1:] if not s.startswith("--")]; cmdn = a[0] if a else "help"
    if cmdn == "open":
        # R1: never default to a throwaway %TEMP% profile (user real browser is already logged in).
        # Order: attach running window -> probe existing CDP port -> skill-owned PERSISTENT profile
        # -> one-off profile only with explicit --ephemeral.
        import browser_channel
        url = a[1] if len(a) > 1 else "about:blank"
        res = browser_channel.ensure(url, _flag("--port", str(PORT)),
                                     "--ephemeral" in sys.argv, _flag("--browser", "msedge"))
        if res.get("channel") == "attach":
            return {"ok": True, "channel": "attach", "cdp": False, "windows": res["windows"],
                    "next": "动作走统一后台输入后端: python -B scripts/input_ops.py click <x> <y>",
                    "note": res["note"]}
        if res.get("channel") == "cdp-existing":
            globals()["PORT"] = int(res["port"])
            return {"ok": True, "channel": "cdp-existing", "port": PORT,
                    "browser": res.get("browser"), "note": "附着用户已在跑的实例（真实 profile），未新起进程"}
        globals()["PORT"] = int(res.get("port") or PORT)
        if res.get("ok") is False:
            return res
        return {"ok": True, "channel": res["channel"], "port": PORT, "profile": res.get("profile"),
                "persistent": res.get("persistent"), "login_hint": res.get("login_hint")}
    if cmdn in ("help", ""):
        return {"help": __doc__}
    if cmdn == "attach":
        import browser_channel
        return {"channel": "attach", "windows": browser_channel.browser_windows(),
                "usage": "python -B scripts/input_ops.py click <x> <y>  # 矩形内后台模拟点击，不激活窗口"}
    c, p = ws()
    try:
        cmd(c, "Runtime.enable"); cmd(c, "Page.enable")
        if cmdn == "targets":
            return [{"title": t.get("title", "")[:60], "url": t.get("url", "")[:90]} for t in targets() if t.get("type") == "page"]
        if cmdn == "eval":
            expr = a[1] if len(a) > 1 else "document.title"
            if expr.startswith("@"): expr = open(expr[1:], encoding="utf-8").read()
            return {"value": ev(c, expr)}
        if cmdn == "click":
            dispatch_click(c, float(a[1]), float(a[2]), a[3] if len(a) > 3 else "left", "--double" in sys.argv)
            return {"ok": True, "action": "click", "x": float(a[1]), "y": float(a[2]), "mode": "cdp-background"}
        if cmdn == "clickel":
            pos = find_pos(c, a[1])
            if not pos: return {"ok": False, "reason": f"页面内未找到元素: {a[1]}"}
            dispatch_click(c, pos["x"], pos["y"], "left", "--double" in sys.argv)
            return {"ok": True, "action": "click", "element": pos, "mode": "cdp-background"}
        if cmdn == "type":
            cmd(c, "Input.insertText", text=" ".join(a[1:])); return {"ok": True, "action": "type", "mode": "cdp-background"}
        if cmdn == "key":
            combo = a[1] if len(a) > 1 else ""
            m = {"ctrl": ("Control", 17), "alt": ("Alt", 18), "shift": ("Shift", 16), "meta": ("Meta", 91)}
            parts = [x.strip().lower() for x in combo.replace("+", " ").split()]
            mods = [m[x] for x in parts[:-1] if x in m]
            key = parts[-1] if parts else ""
            named = {"enter": ("Enter", 13, "Enter"), "tab": ("Tab", 9, "Tab"), "esc": ("Escape", 27, "Escape"),
                     "backspace": ("Backspace", 8, "Backspace"), "delete": ("Delete", 46, "Delete"),
                     "space": (" ", 32, "Space"), "up": ("ArrowUp", 38, "ArrowUp"), "down": ("ArrowDown", 40, "ArrowDown"),
                     "left": ("ArrowLeft", 37, "ArrowLeft"), "right": ("ArrowRight", 39, "ArrowRight")}
            if key in named: k, vk, code = named[key]
            elif len(key) == 1: k, vk, code = key, ord(key.upper()), ("Key" + key.upper() if key.isalpha() else key)
            else: return {"ok": False, "reason": f"未知按键: {key}"}
            mk = [{"key": n, "code": "Key" + n[0], "windowsVirtualKeyCode": v, "nativeVirtualKeyCode": v} for n, v in mods]
            base = {"key": k, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
            for typ in ("keyDown", "keyUp"):
                for mm in mk: cmd(c, "Input.dispatchKeyEvent", type=typ, **mm)
                cmd(c, "Input.dispatchKeyEvent", type=typ, **base)
                if typ == "keyDown" and len(k) == 1: cmd(c, "Input.dispatchKeyEvent", type="char", text=k, **base)
            return {"ok": True, "action": "key", "combo": combo, "mode": "cdp-background"}
        if cmdn == "scroll":
            cmd(c, "Input.dispatchMouseEvent", type="mouseWheel", x=float(a[1]), y=float(a[2]), deltaX=0, deltaY=float(a[3]))
            return {"ok": True, "action": "scroll", "mode": "cdp-background"}
        if cmdn == "shot":
            r = cmd(c, "Page.captureScreenshot", format="png")
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import screenshot_verify
            path = os.path.join(screenshot_verify.ensure_dir(), f"cdp_{a[1] if len(a) > 1 else 'shot'}_{time.strftime('%H%M%S')}.png")
            open(path, "wb").write(base64.b64decode(r["data"]))
            return {"path": path, "via": "cdp"}
        if cmdn == "navigate":
            cmd(c, "Page.navigate", url=a[1]); time.sleep(2)
            return {"ok": True, "url": ev(c, "location.href")}
        return {"help": __doc__}
    finally:
        c.close()

if __name__ == "__main__":
    try:
        r = main()
    except Exception as e:
        r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
