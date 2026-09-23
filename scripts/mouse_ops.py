#!/usr/bin/env python3
"""mouse_ops.py — 安全鼠标操作：移动、点击、拖拽、滚动；坐标越界一律拒绝。"""
import sys, json
DANGEROUS = ("delete", "format", "regedit", "shutdown", "reboot", "taskkill", "del ", "rm -")

def check_safety(action, x=0, y=0):
    bad = next((d for d in DANGEROUS if d in action.lower()), None)
    if bad: return {"allowed": False, "reason": f"危险关键词: {bad}"}
    import pyautogui; w, h = pyautogui.size()
    if not (0 <= x <= w and 0 <= y <= h): return {"allowed": False, "reason": f"坐标越界 ({x},{y})，屏幕 {w}x{h}"}
    return {"allowed": True}

def move(x, y, duration=0.3):
    chk = check_safety("move", x, y)
    if not chk["allowed"]: return chk
    import pyautogui; pyautogui.moveTo(x, y, duration=duration)
    return {"ok": True, "action": "move", "pos": (x, y)}

def click(x, y, button="left", clicks=1, duration=0.3):
    chk = check_safety("click", x, y)
    if not chk["allowed"]: return chk
    import pyautogui; pyautogui.moveTo(x, y, duration=duration); pyautogui.click(button=button, clicks=clicks)
    return {"ok": True, "action": "click", "pos": (x, y), "button": button}

def drag(sx, sy, ex, ey, duration=0.5):
    for px, py in ((sx, sy), (ex, ey)):
        chk = check_safety("drag", px, py)
        if not chk["allowed"]: return chk
    import pyautogui; pyautogui.moveTo(sx, sy, duration=duration)
    pyautogui.dragTo(ex, ey, duration=duration, button="left")
    return {"ok": True, "action": "drag", "from": (sx, sy), "to": (ex, ey)}

def scroll(x, y, clicks=-3, duration=0.3):
    chk = check_safety("scroll", x, y)
    if not chk["allowed"]: return chk
    import pyautogui; pyautogui.moveTo(x, y, duration=duration); pyautogui.scroll(clicks)
    return {"ok": True, "action": "scroll", "pos": (x, y), "clicks": clicks}

if __name__ == "__main__":
    a = [s for s in sys.argv[1:] if not s.startswith("--")]; cmd = a[0] if a else "help"; I = lambda i: int(a[i]) if len(a) > i else 0
    try:
        if cmd == "move": r = move(I(1), I(2))
        elif cmd == "click": r = click(I(1), I(2), a[3] if len(a) > 3 else "left")
        elif cmd == "drag": r = drag(I(1), I(2), I(3), I(4))
        elif cmd == "scroll": r = scroll(I(1), I(2), I(3) or -3)
        elif cmd == "position": import pyautogui; r = {"pos": pyautogui.position()}
        else: r = {"help": "move|click|drag|scroll|position <args>"}
    except ImportError: r = {"error": "pyautogui 未安装，运行: pip install pyautogui Pillow"}
    except Exception as e: r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
