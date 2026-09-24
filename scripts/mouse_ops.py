#!/usr/bin/env python3
"""mouse_ops.py — 前台操作统一入口（须先征得用户同意！）：Windows 走 real_input(SendInput)，
打扰用户，默认请用 virtual_mouse.py 后台模式；其他平台回退 pyautogui。坐标越界一律拒绝。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import real_input
DANGEROUS = ("delete", "format", "regedit", "shutdown", "reboot", "taskkill", "del ", "rm -")
PYAUTO = not real_input.IS_WIN

def check_safety(action, x=0, y=0):
    bad = next((d for d in DANGEROUS if d in action.lower()), None)
    if bad: return {"allowed": False, "reason": f"危险关键词: {bad}"}
    if real_input.IS_WIN:
        if not real_input._in_screen(x, y): return {"allowed": False, "reason": f"坐标越界 ({x},{y})"}
    else:
        import pyautogui; w, h = pyautogui.size()
        if not (0 <= x <= w and 0 <= y <= h): return {"allowed": False, "reason": f"坐标越界 ({x},{y})，屏幕 {w}x{h}"}
    return {"allowed": True}

def _pa(fn, *args, **kw):
    import pyautogui
    if fn == "move": pyautogui.moveTo(*args, **kw)
    elif fn == "click": pyautogui.click(*args, **kw)
    elif fn == "dragTo": pyautogui.dragTo(*args, **kw)
    elif fn == "scroll": pyautogui.scroll(*args, **kw)
    elif fn == "typewrite": pyautogui.typewrite(*args, **kw)
    elif fn == "hotkey": pyautogui.hotkey(*args)
    return {"ok": True, "mode": "pyautogui"}

def move(x, y, duration=0.3):
    chk = check_safety("move", x, y)
    if not chk["allowed"]: return chk
    return real_input.move(x, y, min(duration, 0.3)) if real_input.IS_WIN else _pa("move", x, y, duration=duration)

def click(x, y, button="left", clicks=1, duration=0.3):
    chk = check_safety("click", x, y)
    if not chk["allowed"]: return chk
    if real_input.IS_WIN: return real_input.click(x, y, button, clicks, min(duration, 0.3))
    _pa("move", x, y, duration=duration); return _pa("click", button=button, clicks=clicks)

def drag(sx, sy, ex, ey, duration=0.5):
    for px, py in ((sx, sy), (ex, ey)):
        chk = check_safety("drag", px, py)
        if not chk["allowed"]: return chk
    if real_input.IS_WIN: return real_input.drag(sx, sy, ex, ey, duration=duration)
    _pa("move", sx, sy, duration=duration); return _pa("dragTo", ex, ey, duration=duration, button="left")

def scroll(x, y, clicks=-3, duration=0.3):
    chk = check_safety("scroll", x, y)
    if not chk["allowed"]: return chk
    if real_input.IS_WIN: return real_input.scroll(x, y, clicks)
    _pa("move", x, y, duration=duration); return _pa("scroll", clicks)

def type_text(text):
    chk = check_safety("type " + text)
    return real_input.type_text(text) if chk["allowed"] else chk

def press_keys(combo):
    chk = check_safety("key " + combo)
    if not chk["allowed"]: return chk
    return real_input.press_keys(combo) if real_input.IS_WIN else _pa("hotkey", *[p.strip() for p in combo.split("+")])

if __name__ == "__main__":
    a = [s for s in sys.argv[1:] if not s.startswith("--")]; cmd = a[0] if a else "help"; I = lambda i: int(a[i]) if len(a) > i else 0
    try:
        if cmd == "move": r = move(I(1), I(2))
        elif cmd == "click": r = click(I(1), I(2), a[3] if len(a) > 3 else "left", 2 if "--double" in sys.argv else 1)
        elif cmd == "drag": r = drag(I(1), I(2), I(3), I(4))
        elif cmd == "scroll": r = scroll(I(1), I(2), I(3) or -3)
        elif cmd == "type": r = type_text(a[1] if len(a) > 1 else "")
        elif cmd == "key": r = press_keys(a[1] if len(a) > 1 else "")
        elif cmd == "position": r = real_input._cursor_pos() if real_input.IS_WIN else __import__("pyautogui").position(); r = {"pos": r}
        else: r = {"help": "move|click|drag|scroll|type|key|position <args>"}
    except ImportError: r = {"error": "pyautogui 未安装，运行: pip install pyautogui Pillow"}
    except Exception as e: r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
