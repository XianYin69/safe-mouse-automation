#!/usr/bin/env python3
"""virtual_mouse.py — 后台虚拟输入（默认模式）：PostMessage 鼠标+键盘，不移动物理光标、
不抢焦点、不改变前台窗口，零打扰。适用传统 Win32 消息窗口；个别应用（Chromium/Electron/
DirectUI）忽略合成消息时，截图验证无变化，征得用户同意后才可改用 real_input.py 前台方式。"""
import sys, os, json, ctypes
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ctypes import wintypes
import real_input

U = ctypes.windll.user32 if sys.platform == "win32" else None
MOVE, LDOWN, LUP, RDOWN, RUP, DBLCLK, MWHEEL = 0x0200, 0x0201, 0x0202, 0x0204, 0x0205, 0x0203, 0x020A
KDOWN, KUP, CHAR = 0x0100, 0x0101, 0x0102
MODS = real_input.MODS

def supported(): return U is not None

def _hit(x, y): return U.WindowFromPoint(wintypes.POINT(int(x), int(y)))

def _lp(hwnd, x, y):
    p = wintypes.POINT(int(x), int(y)); U.ScreenToClient(hwnd, ctypes.byref(p))
    return (p.y << 16) | (p.x & 0xFFFF)

def _klp(vk, up=False):
    scan = U.MapVirtualKeyW(vk, 0)
    lp = 1 | (scan << 16) | ((1 << 24) if vk in {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D} else 0)
    return lp | (0xC0000000 if up else 0)

def _post(hwnd, msgs):
    for m, wp, lp in msgs: U.PostMessageW(hwnd, m, wp, lp)
    return {"ok": True, "hwnd": hwnd, "mode": "virtual", "steps": len(msgs)}

class _GTI(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.ULONG), ("flags", wintypes.ULONG), ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]

def _focus(hwnd):
    if not hwnd: return None
    gi = _GTI(ctypes.sizeof(_GTI)); tid = U.GetWindowThreadProcessId(hwnd, None)
    return (U.GetGUIThreadInfo(tid, ctypes.byref(gi)) and gi.hwndFocus) or hwnd

def click(x, y, button="left", double=False, hwnd=None):
    if not supported(): return {"ok": False, "reason": "非 Windows"}
    h = hwnd or _hit(x, y)
    if not h: return {"ok": False, "reason": f"({x},{y}) 未命中窗口"}
    lp = _lp(h, x, y)
    d, u, mk = (LDOWN, LUP, 0x0001) if button == "left" else (RDOWN, RUP, 0x0002)
    seq = [(MOVE, mk if double else 0, lp)]
    seq += ([(d, mk, lp), (u, 0, lp), (DBLCLK, mk, lp), (u, 0, lp)] if double else [(d, mk, lp), (u, 0, lp)])
    return _post(h, seq)

def scroll(x, y, amount=-3, hwnd=None):
    if not supported(): return {"ok": False, "reason": "非 Windows"}
    h = hwnd or _hit(x, y)
    if not h: return {"ok": False, "reason": "未命中窗口"}
    lp = _lp(h, x, y) | ((int(amount * 120) & 0xFFFF) << 16)
    return _post(h, [(MOVE, 0, _lp(h, x, y)), (MWHEEL, 0x0001, lp)])

def drag(sx, sy, ex, ey, steps=8, hwnd=None):
    if not supported(): return {"ok": False, "reason": "非 Windows"}
    h = hwnd or _hit(sx, sy)
    if not h: return {"ok": False, "reason": "起点未命中窗口"}
    seq = []
    for i in range(steps + 1):
        x, y = sx + (ex - sx) * i / steps, sy + (ey - sy) * i / steps
        seq.append((LDOWN if i == 0 else MOVE, 0x0001 if i < steps else 0, _lp(h, x, y)))
    seq.append((LUP, 0, _lp(h, ex, ey)))
    return _post(h, seq)

def type_text(x, y, text, hwnd=None):
    if not supported(): return {"ok": False, "reason": "非 Windows"}
    bad = next((d for d in real_input.DANGEROUS if d in text.lower()), None)
    if bad: return {"ok": False, "reason": f"文本含危险关键词: {bad}"}
    h = _focus(hwnd or _hit(x, y))
    if not h: return {"ok": False, "reason": "未命中窗口"}
    units = str(text).encode("utf-16-le")
    msgs = [(CHAR, int.from_bytes(units[i:i + 2], "little"), 1) for i in range(0, len(units), 2)]
    return _post(h, msgs)

def key_combo(x, y, combo, hwnd=None):
    if not supported(): return {"ok": False, "reason": "非 Windows"}
    parts = [p.strip().lower() for p in combo.replace("+", " ").split() if p.strip()]
    vk = real_input.vk_of(parts[-1]) if parts else None
    if not parts or vk is None or any(p not in MODS for p in parts[:-1]):
        return {"ok": False, "reason": f"无法解析组合键: {combo}"}
    h = _focus(hwnd or _hit(x, y))
    if not h: return {"ok": False, "reason": "未命中窗口"}
    mods = [MODS[p] for p in parts[:-1]]
    seq = [(KDOWN, m, _klp(m)) for m in mods]
    seq += [(KDOWN, vk, _klp(vk)), (KUP, vk, _klp(vk, up=True))]
    seq += [(KUP, m, _klp(m, up=True)) for m in reversed(mods)]
    return _post(h, seq)

if __name__ == "__main__":
    a = [s for s in sys.argv[1:] if not s.startswith("--")]; cmd = a[0] if a else "help"; F = lambda i: float(a[i]) if len(a) > i else 0
    try:
        if cmd == "click": r = click(F(1), F(2), a[3] if len(a) > 3 else "left", "--double" in sys.argv)
        elif cmd == "scroll": r = scroll(F(1), F(2), int(F(3)) or -3)
        elif cmd == "drag": r = drag(F(1), F(2), F(3), F(4))
        elif cmd == "type": r = type_text(F(1), F(2), " ".join(a[3:]) if len(a) > 3 else "")
        elif cmd == "key": r = key_combo(F(1), F(2), a[3] if len(a) > 3 else "")
        else: r = {"help": "click x y [button] [--double] | scroll x y n | drag sx sy ex ey | type x y <文本> | key x y <ctrl+s>"}
    except Exception as e: r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
