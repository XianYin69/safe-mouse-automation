#!/usr/bin/env python3
"""app_ops.py — 应用界面操作（R2 去特殊化后）：UIA **只读**枚举与定位，动作一律交给统一后端
input_ops.py 在元素矩形中心发出后台模拟鼠标/键盘事件。

已删除的"捷径"（不再作为动作路径）：UIA Invoke/Toggle/Select、ValuePattern.SetValue、
经典菜单 WM_COMMAND。它们要么绕过输入级模拟、要么改变控件内部状态而不产生真实鼠标键盘事件，
与本技能「一切动作＝模拟鼠标+键盘」的单一后端原则冲突。只读枚举（controls/menus）保留。

命令: controls <窗口子串> [n] | locate <窗口子串> <元素名>
      | click <窗口子串> <元素名> [--button=left|right] [--double]
      | set <窗口子串> <元素名> <文本...>        # = 先点击该控件，再后台模拟键盘打字
      | menu <窗口子串> <一级/二级>              # = 真实鼠标点击菜单条坐标（不再 WM_COMMAND）
      | menus <窗口子串>                        # 只读枚举经典菜单文本
"""
import sys, os, json, ctypes, time
from ctypes import wintypes
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import input_ops

u = ctypes.windll.user32
INTERACTIVE = ("ButtonControl", "EditControl", "HyperlinkControl", "TabItemControl", "ListItemControl",
               "ComboBoxControl", "CheckBoxControl", "RadioButtonControl", "MenuItemControl",
               "SliderControl", "DocumentControl", "MenuBarItemControl")


def _ua():
    try:
        import uiautomation as ua
        ua.SetGlobalSearchTimeout(4)
        return ua
    except ImportError:
        return None


def _win(ua, sub):
    """只读枚举顶层窗口（不激活、不置前）。"""
    best = None
    for w in ua.GetRootControl().GetChildren():
        try:
            if sub.lower() in (w.Name or "").lower():
                if not w.IsOffscreen:
                    return w
                best = best or w
        except Exception:
            continue
    return best


def controls(win_sub, limit=120):
    """只读：枚举 UIA 控件名 + 屏幕矩形（动作请用 click/set，坐标由此处矩形得出）。"""
    ua = _ua()
    if not ua:
        return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    w = _win(ua, win_sub)
    if not w:
        return {"error": f"未找到窗口: {win_sub}"}
    from browser_ops import _els
    out = []
    for c in _els(w):
        try:
            nm = (c.Name or "").strip()
            if not nm or c.ControlTypeName not in INTERACTIVE:
                continue
            r = c.BoundingRectangle
            if r.right - r.left <= 0 and c.ControlTypeName != "MenuItemControl":
                continue
            out.append({"name": nm[:60], "type": c.ControlTypeName[:-7], "id": c.AutomationId[:30],
                        "rect": [r.left, r.top, r.right, r.bottom],
                        "screen_xy": [(r.left + r.right) // 2, (r.top + r.bottom) // 2]})
            if len(out) >= limit:
                break
        except Exception:
            continue
    return {"window": (w.Name or "")[:60], "count": len(out), "controls": out, "read_only": True}


def locate(win_sub, el_name):
    return input_ops.locate(win_sub, el_name)


def click(win_sub, el_name, button="left", double=False):
    """动作＝在该元素矩形中心发后台模拟鼠标点击（统一后端，不再 UIA Invoke）。"""
    p = locate(win_sub, el_name)
    if not p.get("ok"):
        return p
    r = input_ops.act("double" if double else "click", p["x"], p["y"], button=button, double=double)
    r["element"], r["rect"], r["action"] = p["element"], p["rect"], ("double" if double else "click")
    r["backend"] = "postmessage-mouse-keyboard"
    return r


def setv(win_sub, el_name, text):
    """填输入框＝先真实模拟点击该控件聚焦，再向该窗口焦点控件后台投递 WM_CHAR（不再 SetValue）。"""
    c = click(win_sub, el_name)
    if not c.get("ok"):
        return {"ok": False, "reason": "聚焦点击失败：" + str(c.get("reason")), "step": "click"}
    time.sleep(0.25)
    p = locate(win_sub, el_name)
    t = input_ops.act("type", p["x"], p["y"], text)
    t["action"], t["element"], t["backend"] = "type", p.get("element"), "postmessage-mouse-keyboard"
    t["note"] = "若画面无变化：该应用可能忽略合成输入——须征得用户同意后才可用 real_input.py 前台兜底"
    return t


def menus(win_sub):
    """只读：枚举经典 Win32 菜单树文本（不再执行 WM_COMMAND）。"""
    ua = _ua()
    if not ua:
        return {"error": "uiautomation 未安装"}
    w = _win(ua, win_sub)
    if not w:
        return {"error": f"未找到窗口: {win_sub}"}
    h = w.NativeWindowHandle
    hm = u.GetMenu(h)
    if not hm:
        return {"error": "无经典 Win32 菜单（现代自绘菜单请用 controls 找元素后 click）", "read_only": True}
    MF_BYPOSITION, MF_POPUP = 0x400, 0x10
    u.GetMenu.restype = ctypes.c_void_p
    u.GetSubMenu.restype = ctypes.c_void_p
    u.GetMenuItemID.restype = ctypes.c_uint
    u.GetMenuItemCount.restype = ctypes.c_int
    u.GetMenuStringW.restype = ctypes.c_int

    def txt(m, i):
        b = ctypes.create_unicode_buffer(256)
        u.GetMenuStringW(m, i, b, 256, MF_BYPOSITION)
        return b.value

    def tree(m, depth=0):
        out = []
        for i in range(u.GetMenuItemCount(m)):
            it = {"text": txt(m, i), "id": u.GetMenuItemID(m, i)}
            sub = u.GetSubMenu(m, i)
            if sub and depth < 1:
                it["sub"] = tree(sub, depth + 1)
            out.append(it)
        return out

    return {"window": (w.Name or "")[:60], "menu": tree(hm), "read_only": True,
            "note": "执行菜单请走 menu（真实鼠标点击菜单条坐标），不再用 WM_COMMAND"}


def menu(win_sub, path):
    """执行菜单＝逐级**真实模拟鼠标点击**菜单项坐标（R2：不再 PostMessage WM_COMMAND）。"""
    parts = [p.strip() for p in path.split("/") if p.strip()]
    steps = []
    for lvl, name in enumerate(parts):
        p = locate(win_sub, name)
        if not p.get("ok"):
            return {"ok": False, "reason": f"第 {lvl + 1} 级菜单项定位失败: {name}", "path": path,
                    "detail": p, "hint": "自绘菜单先 controls 看真实元素名"}
        r = input_ops.act("click", p["x"], p["y"], button="left")
        steps.append({"level": lvl + 1, "text": p.get("element"), "screen": [p["x"], p["y"]],
                      "ok": r.get("ok")})
        time.sleep(0.35)
    return {"ok": all(s["ok"] for s in steps), "action": "menu", "path": path, "steps": steps,
            "backend": "postmessage-mouse-keyboard", "mode": "virtual"}


if __name__ == "__main__":
    a = [s for s in sys.argv[1:] if not s.startswith("--")]
    cmd = a[0] if a else "help"
    btn = "right" if "--button=right" in sys.argv else "left"
    dbl = "--double" in sys.argv
    try:
        if cmd == "controls":
            r = controls(a[1], int(a[2]) if len(a) > 2 else 120)
        elif cmd == "locate":
            r = locate(a[1], a[2])
        elif cmd == "click":
            r = click(a[1], a[2], btn, dbl)
        elif cmd == "set":
            r = setv(a[1], a[2], " ".join(a[3:]))
        elif cmd == "menus":
            r = menus(a[1])
        elif cmd == "menu":
            r = menu(a[1], a[2])
        else:
            r = {"help": __doc__}
    except Exception as e:
        r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
