#!/usr/bin/env python3
"""app_ops.py — 应用直接操作通道（后台，不用命令行驱动）：看界面、点控件、走菜单、填输入框。
UIA 枚举/Invoke/SetValue（不需要前台/可见，被遮挡照常生效）+ 经典 Win32 菜单经
GetMenu/PostMessage WM_COMMAND（零鼠标、零焦点）。配合 learn.py：先 get <app> 召回已知控件/菜单，
未命中用 controls/menus 探索，操作成功验证后 put/op 回写，下次直达。
命令: controls <窗口子串> [n] | act <窗口子串> <元素名> | set <窗口子串> <元素名> <文本>
      menus <窗口子串> | menu <窗口子串> <一级/二级>"""
import sys, os, json, ctypes, time
from ctypes import wintypes
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
u = ctypes.windll.user32
WM_COMMAND = 0x0111
MF_BYPOSITION = 0x0400
MF_POPUP = 0x0010
INTERACTIVE = ("ButtonControl", "EditControl", "HyperlinkControl", "TabItemControl", "ListItemControl",
               "ComboBoxControl", "CheckBoxControl", "RadioButtonControl", "MenuItemControl",
               "SliderControl", "DocumentControl", "MenuBarItemControl")
u.PostMessageW.restype = ctypes.c_bool
u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u.SendMessageW.restype = ctypes.c_ssize_t
u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_ssize_t]
u.GetMenu.restype = ctypes.c_void_p
u.GetSubMenu.restype = ctypes.c_void_p
u.GetMenuItemID.restype = ctypes.c_uint
u.GetMenuItemCount.restype = ctypes.c_int
u.GetMenuStringW.restype = ctypes.c_int
u.SetMenu.restype = ctypes.c_bool

def _ua():
    try:
        import uiautomation as ua
        ua.SetGlobalSearchTimeout(4)
        return ua
    except ImportError:
        return None

def _win(ua, sub):
    best = None
    for w in ua.GetRootControl().GetChildren():
        try:
            if sub.lower() in (w.Name or "").lower():
                if not w.IsOffscreen: return w
                best = best or w
        except Exception:
            continue
    return best

def _find(win, name):
    from browser_ops import _find
    return _find(win, name)

def controls(win_sub, limit=120):
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    w = _win(ua, win_sub)
    if not w: return {"error": f"未找到窗口: {win_sub}"}
    from browser_ops import _els
    out = []
    for c in _els(w):
        try:
            nm = (c.Name or "").strip()
            if not nm or c.ControlTypeName not in INTERACTIVE: continue
            r = c.BoundingRectangle
            if r.right - r.left <= 0 and c.ControlTypeName != "MenuItemControl": continue
            out.append({"name": nm[:60], "type": c.ControlTypeName[:-7], "id": c.AutomationId[:30],
                        "rect": [r.left, r.top, r.right, r.bottom]})
            if len(out) >= limit: break
        except Exception:
            continue
    return {"window": (w.Name or "")[:60], "count": len(out), "controls": out}

def act(win_sub, el_name):
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    w = _win(ua, win_sub)
    if not w: return {"error": f"未找到窗口: {win_sub}"}
    el = _find(w, el_name)
    if el is None: return {"ok": False, "reason": f"未找到控件: {el_name}", "window": (w.Name or "")[:60]}
    from browser_ops import _act
    via = _act(el)
    return {"ok": bool(via), "action": "act", "element": (el.Name or "")[:60], "via": via,
            "type": el.ControlTypeName, "mode": "uia-background"}

def setv(win_sub, el_name, text):
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    w = _win(ua, win_sub)
    if not w: return {"error": f"未找到窗口: {win_sub}"}
    el = _find(w, el_name)
    if el is None: return {"ok": False, "reason": f"未找到输入框: {el_name}"}
    try:
        p = el.GetValuePattern()
        if p is not None:
            p.SetValue(text)
            return {"ok": True, "action": "set", "element": (el.Name or "")[:60], "mode": "uia-background"}
    except Exception:
        pass
    return {"ok": False, "reason": "该控件不支持 ValuePattern.SetValue（可用 virtual_mouse type 或 act 聚焦后输入）"}

def _menu_text(hm, i):
    b = ctypes.create_unicode_buffer(256)
    u.GetMenuStringW(hm, i, b, 256, MF_BYPOSITION)
    return b.value

def _menu_tree(hm, depth=0):
    out = []
    for i in range(u.GetMenuItemCount(hm)):
        item = {"text": _menu_text(hm, i), "id": u.GetMenuItemID(hm, i)}
        sub = u.GetSubMenu(hm, i)
        if sub and depth < 1: item["sub"] = _menu_tree(sub, depth + 1)
        out.append(item)
    return out

def _hwnd_of(ua, win_sub):
    w = _win(ua, win_sub)
    return (w.NativeWindowHandle if w else None), ((w.Name or "")[:60] if w else "")

def menus(win_sub):
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    h, title = _hwnd_of(ua, win_sub)
    if not h: return {"error": f"未找到窗口: {win_sub}"}
    hm = u.GetMenu(h)
    if not hm: return {"error": "无经典 Win32 菜单（现代应用可能用自绘菜单——改用 controls/act）", "window": title}
    return {"window": title, "menu": _menu_tree(hm)}

def menu(win_sub, path):
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    h, title = _hwnd_of(ua, win_sub)
    if not h: return {"error": f"未找到窗口: {win_sub}"}
    hm = u.GetMenu(h)
    if not hm: return {"error": "无经典 Win32 菜单", "window": title}
    parts = [p.strip() for p in path.split("/") if p.strip()]
    cur, items, mid = hm, None, None
    for lvl, want in enumerate(parts):
        n = u.GetMenuItemCount(cur)
        hit = None
        for i in range(n):
            t = _menu_text(cur, i)
            if t == want: hit = i; break
            if hit is None and want.lower() in t.lower(): hit = i
        if hit is None: return {"ok": False, "reason": f"菜单未找到: {want}（路径 {path}）",
                                "options": [_menu_text(cur, i) for i in range(min(n, 20))]}
        sub = u.GetSubMenu(cur, hit)
        if lvl < len(parts) - 1:
            if not sub: return {"ok": False, "reason": f"“{want}”不是子菜单"}
            cur = sub
        else:
            mid = u.GetMenuItemID(cur, hit)
    if mid is None or mid == -1: return {"ok": False, "reason": f"末级“{parts[-1]}”无命令 ID"}
    u.PostMessageW(h, WM_COMMAND, mid, 0)
    return {"ok": True, "action": "menu", "path": path, "cmd": mid, "window": title, "mode": "wm-command-background"}

if __name__ == "__main__":
    a = [s for s in sys.argv[1:] if not s.startswith("--")]; cmd = a[0] if a else "help"
    try:
        if cmd == "controls": r = controls(a[1], int(a[2]) if len(a) > 2 else 120)
        elif cmd == "act": r = act(a[1], a[2])
        elif cmd == "set": r = setv(a[1], a[2], " ".join(a[3:]))
        elif cmd == "menus": r = menus(a[1])
        elif cmd == "menu": r = menu(a[1], a[2])
        else: r = {"help": "controls <窗口> [n] | act <窗口> <元素名> | set <窗口> <元素名> <文本> | menus <窗口> | menu <窗口> <一级/二级>"}
    except Exception as e: r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
