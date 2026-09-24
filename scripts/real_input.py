#!/usr/bin/env python3
"""real_input.py — 前台真输入回退（须先征得用户同意！）：SendInput 系统级注入，会移动物理光标、
改变焦点窗口，直接打扰用户。默认一律使用 virtual_mouse.py 后台方式；仅当目标应用忽略合成
PostMessage（Chromium/Electron/DirectUI）且截图验证无变化时，经用户确认后才调用本模块。
鼠标：move/click/drag/scroll；键盘：type（任意 Unicode 文本）与 key（组合快捷键）。"""
import sys, time, ctypes
from ctypes import wintypes

IS_WIN = sys.platform == "win32"
if IS_WIN:  # DPI 感知：坐标/截图/注入统一按物理像素，避免缩放屏上打偏
    try: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass
SendInput, mouse_event = (ctypes.windll.user32.SendInput, ctypes.windll.user32.mouse_event) if IS_WIN else (None, None)
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MF, MR, MW, MD, MU, MHW = 0x0001, 0x0002, 0x0020, 0x0008, 0x0010, 0x0004
KFU, KRU = 0x0004, 0x0002
ABS, VDIS = 0x8000, 0x4000
BTN = {"left": (MF, MR), "right": (MD, MU), "middle": (MHW, MW)}
DANGEROUS = ("delete", "format", "regedit", "shutdown", "reboot", "taskkill", "del ", "rm -")

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]
class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]

def _fire(*inputs): SendInput(len(inputs), (INPUT * len(inputs))(*inputs), ctypes.sizeof(INPUT))
def _mk(t, k, d): return INPUT(type=t, u=_U(**{k: d}))

def bounds():
    SMX, SMY, SMXV, SMYV, SMCX, SMCY = 0, 1, 76, 77, 80, 81
    g = ctypes.windll.user32.GetSystemMetrics
    return g(SMXV), g(SMYV), g(SMX) or g(SMCX), g(SMY) or g(SMCY)

def _norm(x, y):
    ox, oy, vw, vh = bounds()
    nx = int((x - ox) * 65535 / max(1, vw - 1)); ny = int((y - oy) * 65535 / max(1, vh - 1))
    return nx - (1 << 32 if nx >= (1 << 31) else 0), ny - (1 << 32 if ny >= (1 << 31) else 0)

def _mouse(flags, x=0, y=0, data=0):
    _fire(_mk(INPUT_MOUSE, "mi", MOUSEINPUT(x, y, data, flags, 0, None)))

def _in_screen(x, y):
    ox, oy, w, h = bounds()
    return ox <= x < ox + w and oy <= y < oy + h

def move(x, y, duration=0.0):
    if not _in_screen(x, y): return {"ok": False, "reason": f"坐标越界 ({x},{y})"}
    steps = max(0, min(24, int(duration * 60)))
    if steps:
        p = _cursor_pos()
        for i in range(1, steps + 1):
            nx, ny = p[0] + (x - p[0]) * i / steps, p[1] + (y - p[1]) * i / steps
            _mouse(ABS, *_norm(nx, ny)); time.sleep(duration / steps)
    _mouse(ABS, *_norm(x, y))
    return {"ok": True, "action": "move", "pos": (x, y), "mode": "real"}

def click(x, y, button="left", clicks=1, duration=0.0):
    if not _in_screen(x, y): return {"ok": False, "reason": f"坐标越界 ({x},{y})"}
    d, u = BTN[button]; r = move(x, y, duration)
    if not r.get("ok"): return r
    for _ in range(max(1, int(clicks))):
        _mouse(d); time.sleep(0.02); _mouse(u); time.sleep(0.04)
    return {"ok": True, "action": "click", "pos": (x, y), "button": button, "clicks": int(clicks), "mode": "real"}

def drag(sx, sy, ex, ey, steps=12, duration=0.3):
    for px, py in ((sx, sy), (ex, ey)):
        if not _in_screen(px, py): return {"ok": False, "reason": f"坐标越界 ({px},{py})"}
    move(sx, sy); _mouse(MF); time.sleep(0.05)
    for i in range(1, steps + 1):
        _mouse(ABS, *_norm(sx + (ex - sx) * i / steps, sy + (ey - sy) * i / steps))
        time.sleep(duration / steps)
    time.sleep(0.05); _mouse(MR)
    return {"ok": True, "action": "drag", "from": (sx, sy), "to": (ex, ey), "mode": "real"}

def scroll(x, y, amount=-3):
    if not _in_screen(x, y): return {"ok": False, "reason": f"坐标越界 ({x},{y})"}
    move(x, y); _mouse(0x0800, data=int(amount * 120) & 0xFFFFFFFF)
    return {"ok": True, "action": "scroll", "amount": amount, "mode": "real"}

def type_text(text):
    bad = next((d for d in DANGEROUS if d in text.lower()), None)
    if bad: return {"ok": False, "reason": f"文本含危险关键词: {bad}"}
    units = str(text).encode("utf-16-le")
    for i in range(0, len(units), 2):
        code = int.from_bytes(units[i:i + 2], "little")
        _fire(_mk(INPUT_KEYBOARD, "ki", KEYBDINPUT(0, code, KFU, 0, None)))
        _fire(_mk(INPUT_KEYBOARD, "ki", KEYBDINPUT(0, code, KFU | KRU, 0, None)))
    return {"ok": True, "action": "type", "chars": len(text), "mode": "real"}

MODS = {"ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B, "cmd": 0x5B}
BASE = {**{c: 0x41 + i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")},
        **{str(i): 0x30 + i for i in range(10)},
        "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08,
        "delete": 0x2E, "ins": 0x2D, "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
        "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA, "'": 0xDE,
        ",": 0xBC, ".": 0xBE, "/": 0xBF, "`": 0xC0}
for _i in range(1, 13): BASE["f" + str(_i)] = 0x6F + _i

def vk_of(k):
    return BASE.get(k) or BASE.get(k.upper()) or BASE.get(k.lower())

def press_keys(combo):
    parts = [p.strip().lower() for p in combo.replace("+", " ").split() if p.strip()]
    if not parts: return {"ok": False, "reason": "空组合键"}
    mods = [MODS[p] for p in parts[:-1] if p in MODS]
    if len(mods) != len(parts) - 1: return {"ok": False, "reason": f"未知修饰键: {parts[:-1]}"}
    vk = vk_of(parts[-1])
    if vk is None: return {"ok": False, "reason": f"未知按键: {parts[-1]}"}; sh = vk in {0xBB, 0xDB, 0xDD, 0xDC, 0xBA, 0xDE}
    seq = mods + ([0x10] if sh else [])
    for m in seq: _fire(_mk(INPUT_KEYBOARD, "ki", KEYBDINPUT(m, 0, 0, 0, None)))
    _fire(_mk(INPUT_KEYBOARD, "ki", KEYBDINPUT(vk, 0, 0, 0, None)))
    _fire(_mk(INPUT_KEYBOARD, "ki", KEYBDINPUT(vk, 0, KRU, 0, None)))
    for m in reversed(seq): _fire(_mk(INPUT_KEYBOARD, "ki", KEYBDINPUT(m, 0, KRU, 0, None)))
    return {"ok": True, "action": "key", "combo": combo, "mode": "real"}

def _cursor_pos():
    p = wintypes.POINT(); ctypes.windll.user32.GetCursorPos(ctypes.byref(p)); return p.x, p.y

if __name__ == "__main__":
    import json
    a = [s for s in sys.argv[1:] if not s.startswith("--")]; cmd = a[0] if a else "help"
    F = lambda i: float(a[i]) if len(a) > i else 0
    try:
        if cmd == "move": r = move(F(1), F(2))
        elif cmd == "click": r = click(F(1), F(2), a[3] if len(a) > 3 else "left", 2 if "--double" in sys.argv else 1)
        elif cmd == "drag": r = drag(F(1), F(2), F(3), F(4))
        elif cmd == "scroll": r = scroll(F(1), F(2), int(F(3)) or -3)
        elif cmd == "type": r = type_text(a[1] if len(a) > 1 else "")
        elif cmd == "key": r = press_keys(a[1] if len(a) > 1 else "")
        else: r = {"help": "move x y | click x y [button] [--double] | drag sx sy ex ey | scroll x y n | type <文本> | key <ctrl+s>"}
    except Exception as e: r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
