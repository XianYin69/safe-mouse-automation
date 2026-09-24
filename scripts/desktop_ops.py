#!/usr/bin/env python3
"""desktop_ops.py — 桌面软件纯鼠标通道（后台 PostMessage 双击，不动物理光标/不抢焦点/不用命令行启动）：
用 UI Automation 枚举桌面图标与资源管理器项（拿到真实屏幕矩形），向目标控件 PostMessage
WM_LBUTTONDBLCLK 打开软件/进入文件夹。Chromium 类不吃 PostMessage——浏览器用 browser_cdp.py。
命令: windows | win <标题子串> | icons | open <图标名> | items <窗口标题子串> |
      openitem <窗口标题子串> <项名> | dbl <hwnd> <x> <y> | click <hwnd> <x> <y>"""
import sys, os, json, ctypes, time
from ctypes import wintypes
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
u = ctypes.windll.user32
WM_MOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x0200, 0x0201, 0x0202, 0x0203

def _mklp(x, y): return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)

def _ua():
    try:
        import uiautomation as ua
        ua.SetGlobalSearchTimeout(4)
        return ua
    except ImportError:
        return None

def top_windows():
    res = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1)
                r = wintypes.RECT(); u.GetWindowRect(h, ctypes.byref(r))
                res.append({"hwnd": h, "title": b.value, "rect": [r.left, r.top, r.right, r.bottom]})
        return True
    u.EnumWindows(CB(cb), 0)
    return res

def _desktop_ctrl(ua):
    for w in ua.GetRootControl().GetChildren():
        try:
            if (w.Name or "") == "Program Manager" or "Progman" in (w.ClassName or ""):
                lv = w.ListControl(ClassName="SysListView32") or w.Control(ClassName="SysListView32")
                if lv and lv.Exists(maxSearchSeconds=2): return lv
        except Exception:
            continue
    return None

def _items_of(container):
    out = []
    try:
        for it in container.GetChildren():
            try:
                nm = (it.Name or "").strip()
                if not nm: continue
                r = it.BoundingRectangle
                if r.right - r.left <= 0: continue
                out.append({"name": nm, "x": (r.left + r.right) // 2, "y": (r.top + r.bottom) // 2,
                            "rect": [r.left, r.top, r.right, r.bottom]})
            except Exception:
                continue
    except Exception:
        pass
    return out

def desktop_icons():
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    lv = _desktop_ctrl(ua)
    if not lv: return {"error": "未找到桌面 ListView", "found": False}
    return {"found": True, "icons": _items_of(lv)}

def _listview_hwnd():
    prog = u.FindWindowW("Progman", None)
    dv = u.FindWindowExW(prog, None, "SHELLDLL_DefView", None) if prog else None
    if not dv:
        w = None
        while True:
            w = u.FindWindowExW(None, w, "WorkerW", None)
            if not w: break
            dv = u.FindWindowExW(w, None, "SHELLDLL_DefView", None)
            if dv: break
    out = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        b = ctypes.create_unicode_buffer(256); u.GetClassNameW(h, b, 256)
        if b.value == "SysListView32": out.append(h)
        return True
    if dv: u.EnumChildWindows(dv, CB(cb), 0)
    return out[0] if out else None

def _explorer_listview(title_sub):
    ua = _ua()
    cands = []
    for w in ua.GetRootControl().GetChildren():
        try:
            if title_sub.lower() in (w.Name or "").lower():
                cands.append(w)
        except Exception:
            continue
    for w in cands:  # 优先未最小化窗口
        try:
            if w.NativeWindowHandle and u.IsIconic(w.NativeWindowHandle):
                u.ShowWindow(w.NativeWindowHandle, 4)  # SW_SHOWNOACTIVATE：恢复不抢焦点
                time.sleep(1.0)
        except Exception:
            pass
    for w in cands:
        try:
            if w.IsOffscreen: continue
            lv = w.ListControl()
            if lv and lv.Exists(maxSearchSeconds=3):
                lvh = lv.NativeWindowHandle or w.NativeWindowHandle
                return lv, lvh
        except Exception:
            continue
    return None, None

def _dblclick_screen(lvhwnd, sx, sy):
    r = wintypes.RECT(); u.GetWindowRect(lvhwnd, ctypes.byref(r))
    cx, cy = sx - r.left, sy - r.top
    u.PostMessageW(lvhwnd, WM_MOVE, 0, _mklp(cx, cy))
    u.PostMessageW(lvhwnd, WM_LBUTTONDOWN, 0x0001, _mklp(cx, cy))
    u.PostMessageW(lvhwnd, WM_LBUTTONUP, 0, _mklp(cx, cy))
    u.PostMessageW(lvhwnd, WM_LBUTTONDBLCLK, 0x0001, _mklp(cx, cy))
    u.PostMessageW(lvhwnd, WM_LBUTTONUP, 0, _mklp(cx, cy))

def open_icon(name):
    d = desktop_icons()
    if "error" in d: return d
    hit = next((i for i in d["icons"] if name.lower() in i["name"].lower()), None)
    if not hit: return {"ok": False, "reason": f"桌面未找到图标: {name}", "icons": [i["name"] for i in d["icons"]][:40]}
    lv = _listview_hwnd()
    if not lv: return {"ok": False, "reason": "未找到桌面 SysListView32 句柄"}
    _dblclick_screen(lv, hit["x"], hit["y"])
    return {"ok": True, "action": "double-click", "icon": hit["name"], "screen": [hit["x"], hit["y"]], "mode": "postmessage-mouse"}

def open_item(title_sub, name):
    lv, hwnd = _explorer_listview(title_sub)
    if not lv: return {"ok": False, "reason": f"窗口内未找到列表: {title_sub}"}
    hit = next((i for i in _items_of(lv) if name.lower() in i["name"].lower()), None)
    if not hit: return {"ok": False, "reason": f"列表内未找到项: {name}", "items": [i["name"] for i in _items_of(lv)][:40]}
    _dblclick_screen(hwnd, hit["x"], hit["y"])
    return {"ok": True, "action": "double-click", "item": hit["name"], "screen": [hit["x"], hit["y"]],
            "window": title_sub, "mode": "postmessage-mouse"}

def items(title_sub):
    ua = _ua()
    if not ua: return {"error": "uiautomation 未安装"}
    lv, hwnd = _explorer_listview(title_sub)
    if not lv: return {"error": f"未找到窗口列表: {title_sub}"}
    return {"window": title_sub, "items": _items_of(lv)}

if __name__ == "__main__":
    a = [s for s in sys.argv[1:] if not s.startswith("--")]; cmd = a[0] if a else "help"
    try:
        if cmd == "windows": r = [{"hwnd": w["hwnd"], "title": w["title"][:60], "rect": w["rect"]} for w in top_windows()]
        elif cmd == "win": r = [w for w in top_windows() if a[1].lower() in w["title"].lower()]
        elif cmd == "icons": r = desktop_icons()
        elif cmd == "items": r = items(a[1])
        elif cmd == "open": r = open_icon(a[1])
        elif cmd == "openitem": r = open_item(a[1], a[2])
        elif cmd == "dbl": _dblclick_screen(int(a[1]), int(a[2]), int(a[3])); r = {"ok": True, "action": "double-click", "hwnd": int(a[1])}
        elif cmd == "click":
            h, x, y = int(a[1]), int(a[2]), int(a[3])
            u.PostMessageW(h, WM_LBUTTONDOWN, 0x0001, _mklp(x, y)); u.PostMessageW(h, WM_LBUTTONUP, 0, _mklp(x, y))
            r = {"ok": True, "action": "click", "hwnd": h}
        else: r = {"help": "windows | win <标题子串> | icons | open <图标名> | items <窗口> | openitem <窗口> <项名> | dbl <hwnd> <x> <y> | click <hwnd> <x> <y>"}
    except Exception as e: r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
