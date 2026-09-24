#!/usr/bin/env python3
"""browser_ops.py — 后台浏览器操作（UI Automation）：目标窗口被遮挡/不在前台同样生效，
不移动物理光标、不抢焦点、不激活窗口。Chromium 忽略 PostMessage 合成输入，故浏览器点击/
输入一律走 UIA Invoke/SetValue（默认仅允许 InPrivate 任务窗口，防误操作个人浏览器）。
依赖：pip install uiautomation。"""
import sys, json, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from collections import deque

def _ua():
    try:
        import uiautomation as ua
        ua.SetGlobalSearchTimeout(4)
        return ua
    except ImportError:
        return None

def _win(ua, sub, allow_profile=False):
    for w in ua.GetRootControl().GetChildren():
        try:
            nm = w.Name or ""
            if sub.lower() in nm.lower() and not w.IsOffscreen:
                if not allow_profile and "InPrivate" not in nm and "隐私" not in nm:
                    return None, {"error": f"拒绝操作非 InPrivate 窗口: {nm[:60]}（防误碰用户个人浏览器）"}
                return w, None
        except Exception:
            continue
    return None, {"error": f"未找到窗口: {sub}"}

def _doc(win):
    q = deque([(win, 0)])
    while q:
        c, d = q.popleft()
        try:
            if d > 0 and c.ControlTypeName == "DocumentControl": return c
        except Exception: pass
        if d < 8:
            try:
                for k in c.GetChildren(): q.append((k, d + 1))
            except Exception: pass
    return None

def _els(root, limit=60000, depth=30):
    stack = [(root, 0)]; n = 0
    while stack and n < limit:
        c, d = stack.pop(); n += 1
        yield c
        if d < depth:
            try:
                for k in c.GetChildren(): stack.append((k, d + 1))
            except Exception: pass

def restore(win_sub, allow_profile=False):
    """SW_SHOWNOACTIVATE 恢复最小化/隐藏的任务窗口：显示但不激活、不抢前台焦点。"""
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    win, err = _win(ua, win_sub, allow_profile)
    if err: return err
    import ctypes
    hwnd = win.NativeWindowHandle
    was_min = ctypes.windll.user32.IsIconic(hwnd)
    ctypes.windll.user32.ShowWindow(hwnd, 4 if was_min else 1)
    time.sleep(1.0)
    return {"ok": True, "restored_from_minimized": bool(was_min), "hwnd": hwnd}

def _ensure_visible(win, allow_profile=False):
    """恢复最小化/拉回屏内：SW_SHOWNOACTIVATE + SWP_NOZORDER|NOACTIVATE——
    被其他窗口遮挡完全没关系（UIA Invoke 不需要可见前台），但最小化会冻结渲染树。"""
    import ctypes
    try:
        u = ctypes.windll.user32; hwnd = win.NativeWindowHandle
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 4); time.sleep(1.0)
        r = win.BoundingRectangle
        if r.right - r.left <= 0 or r.bottom - r.top <= 0:
            u.ShowWindow(hwnd, 4); time.sleep(1.0); r = win.BoundingRectangle
        sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
        if r.left < 0 or r.top < 0 or r.right > sw * 2 or r.bottom > sh * 2:
            u.SetWindowPos(hwnd, 0, 60, 60, min(1500, sw - 120), min(1100, sh - 120), 0x0010 | 0x0020)
            time.sleep(1.0)
            return True
    except Exception: pass
    return False

def _find(win, name):
    doc = _doc(win)
    best = None; off_exact = None; off_best = None
    for c in _els(doc or win):
        try:
            nm = c.Name or ""
            if not nm.strip(): continue
            vis = not c.IsOffscreen
        except Exception: continue
        if nm == name:
            if vis: return c
            off_exact = off_exact or c
        elif name.lower() in nm.lower() and c.ControlTypeName in (
                "ButtonControl", "EditControl", "HyperlinkControl", "TabItemControl",
                "ListItemControl", "ComboBoxControl", "TextControl", "DocumentControl"):
            if vis and best is None: best = c
            if not vis and off_best is None: off_best = c
    return best or off_exact or off_best

def _act(el):
    for getter, fn in (("GetInvokePattern", lambda p: p.Invoke()),
                       ("GetTogglePattern", lambda p: p.Toggle()),
                       ("GetSelectionItemPattern", lambda p: p.Select()),
                       ("GetLegacyIAccessiblePattern", lambda p: p.DoDefaultAction())):
        try:
            p = getattr(el, getter)()
        except Exception:
            p = None
        if p is not None:
            try:
                fn(p); return getter[3:-7]
            except Exception:
                continue
    return None

def _scroll_into(el):
    try:
        p = el.GetScrollItemPattern()
        if p is not None:
            p.ScrollIntoView(); time.sleep(0.6); return True
    except Exception: pass
    return False

def click(win_sub, el_name, allow_profile=False):
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    win, err = _win(ua, win_sub, allow_profile)
    if err: return err
    _ensure_visible(win)
    el = _find(win, el_name)
    if el is None: return {"ok": False, "reason": f"未找到元素: {el_name}", "window": win.Name[:60]}
    scrolled = False
    try:
        if el.IsOffscreen: scrolled = _scroll_into(el)
    except Exception: pass
    pat = _act(el)
    return {"ok": bool(pat), "action": "click", "element": (el.Name or "")[:60], "via": pat,
            "scrolled_into_view": scrolled, "type": el.ControlTypeName, "mode": "uia-background"}

def type_text(win_sub, el_name, text, allow_profile=False):
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    win, err = _win(ua, win_sub, allow_profile)
    if err: return err
    _ensure_visible(win)
    el = _find(win, el_name)
    if el is None: return {"ok": False, "reason": f"未找到输入框: {el_name}"}
    try:
        p = el.GetValuePattern()
        if p is not None:
            p.SetValue(text)
            return {"ok": True, "action": "type", "element": (el.Name or "")[:60], "mode": "uia-background"}
    except Exception: pass
    return {"ok": False, "reason": "该元素不支持 ValuePattern.SetValue"}

def dump(win_sub, limit=80, allow_profile=False):
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    win, err = _win(ua, win_sub, allow_profile)
    if err: return err
    _ensure_visible(win)
    out = []
    root = _doc(win) or win
    for c in _els(root):
        try:
            nm = (c.Name or "").strip()
            if not nm or c.IsOffscreen or c.ControlTypeName not in (
                    "ButtonControl", "EditControl", "HyperlinkControl", "TabItemControl",
                    "ListItemControl", "ComboBoxControl"): continue
            r = c.BoundingRectangle
            if r.right - r.left <= 0 or r.bottom - r.top <= 0: continue
            out.append({"name": nm[:50], "type": c.ControlTypeName[:-7], "rect": [r.left, r.top, r.right, r.bottom]})
            if len(out) >= limit: break
        except Exception: continue
    return {"window": win.Name[:80], "elements": out}

def wait(win_sub, el_name, seconds=15, allow_profile=False):
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    t0 = time.time()
    while time.time() - t0 < float(seconds):
        win, err = _win(ua, win_sub, allow_profile)
        if not err and _find(win, el_name) is not None:
            return {"ok": True, "found": el_name, "waited": round(time.time() - t0, 1)}
        time.sleep(0.8)
    return {"ok": False, "reason": f"超时未见元素: {el_name}"}

if __name__ == "__main__":
    ap = "--allow-profile" in sys.argv
    a = [s for s in sys.argv[1:] if not s.startswith("--")]; cmd = a[0] if a else "help"
    try:
        if cmd == "click": r = click(a[1], a[2], ap)
        elif cmd == "type": r = type_text(a[1], a[2], " ".join(a[3:]), ap)
        elif cmd == "dump": r = dump(a[1], int(a[2]) if len(a) > 2 else 80, ap)
        elif cmd == "wait": r = wait(a[1], a[2], a[3] if len(a) > 3 else 15, ap)
        elif cmd == "restore": r = restore(a[1] if len(a) > 1 else "", ap)
        else: r = {"help": "click <窗口子串> <元素名> | type <窗口子串> <元素名> <文本> | dump <窗口子串> [n] | wait <窗口子串> <元素名> [秒]"}
    except Exception as e: r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
