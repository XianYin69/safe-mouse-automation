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
import keycombo

U = ctypes.windll.user32 if sys.platform == "win32" else None


def _init_dpi():
    """坐标契约＝**屏幕物理像素**（与 screen-vision 的 screen_xy 一致）。
    未声明 DPI 感知的进程里 WindowFromPoint/ScreenToClient 用的是虚拟化坐标，
    150% 缩放屏上会把点击投到偏 1.5 倍的位置——这里显式声明 per-monitor-v2。
    可用 env SAFE_MOUSE_NO_DPI_AWARE=1 关闭。"""
    if U is None or os.environ.get("SAFE_MOUSE_NO_DPI_AWARE") == "1":
        return "unaware"
    try:
        if U.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2); return "per-monitor"
    except Exception:
        pass
    try:
        U.SetProcessDPIAware(); return "system"
    except Exception:
        return "unaware"


DPI_MODE = _init_dpi()
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
    lp = 1 | (scan << 16) | ((1 << 24) if keycombo.is_extended(vk) else 0)   # 单一表，防漂移
    return lp | (0xC0000000 if up else 0)

def _post(hwnd, msgs, cleanup=None):
    """投递合成消息（不移动物理光标、不抢焦点）。cleanup＝成对兜底回调：
    中途 PostMessageW 失败或返回 0 时用 cleanup(已投递前缀) 生成补发序列
    （已 KDOWN 的键全部 KUP），绝不留下半按状态；回报 posted/injected 计数与失败原因。"""
    sent, failed = [], None
    for m, wp, lp in msgs:
        try:
            ok = bool(U.PostMessageW(hwnd, m, wp, lp))
        except Exception as e:
            failed, ok = "PostMessageW 异常: %s" % e, False
        if not ok:
            failed = failed or ("PostMessageW(%s) 返回 0" % hex(m))
            if cleanup:
                try:
                    for cm, cwp, clp in cleanup(sent):
                        U.PostMessageW(hwnd, cm, cwp, clp); sent.append((cm, cwp, clp))
                except Exception:
                    pass
            break
        sent.append((m, wp, lp))
    r = {"ok": failed is None, "hwnd": hwnd, "mode": "virtual",
         "steps": len(sent), "posted": len(sent), "injected": len(sent)}
    if failed: r["reason"] = failed
    return r


def _kbd_release_pairs(posted):
    """成对兜底：从已投递前缀取所有 KDOWN 的 vk，生成对应 KUP 尾巴（逆序）。"""
    held = [wp for m, wp, lp in posted if m == KDOWN]
    return [(KUP, vk, _klp(vk, up=True)) for vk in reversed(held)]


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

def _release_stuck_in_window(hwnd, stuck=None):
    """注入前置守卫（virtual 通道·修根因③）：GetAsyncKeyState **只读**检出粘滞修饰键 →
    向**目标窗口** PostMessage 配对 KUP。后台路径绝不 SendInput 物理注入（R3），物理层残留
    由 real_input.release_all_modifiers 在用户同意后经前台通道处理。返回释放清单。"""
    if stuck is None:
        stuck = real_input.stuck_modifiers()
    if not stuck:
        return {"checked": True, "released": [], "injected": 0, "channel": "virtual"}
    n = 0
    for s in stuck:
        try:
            if U.PostMessageW(hwnd, KUP, s["vk"], _klp(s["vk"], up=True)):
                n += 1
        except Exception:
            pass
    return {"checked": True, "released": [s["name"] for s in stuck], "injected": n,
            "channel": "virtual",
            "note": "物理层残留请经 real_input.release_all_modifiers（前台通道，须用户同意）"}


def key_combo(x, y, combo, hwnd=None, dry=False):
    if not supported():
        return {"ok": False, "action": "key", "combo": combo, "mode": "virtual",
                "injected": 0, "reason": "非 Windows（未注入任何按键）"}
    p = real_input.parse_combo(combo)              # E：与 real_input 共用解析，防两处逻辑漂移
    if not p["ok"]:
        return {"ok": False, "action": "key", "combo": combo, "mode": "virtual",
                "injected": 0, "reason": p["reason"]}
    if hwnd and not U.IsWindow(int(hwnd)):          # 早退：明确声明未注入（修根因④）
        return {"ok": False, "action": "key", "combo": combo, "mode": "virtual",
                "injected": 0, "reason": f"hwnd 无效/已销毁: {hwnd}（未注入任何按键）"}
    h = _focus(hwnd or _hit(x, y))
    if not h:
        return {"ok": False, "action": "key", "combo": combo, "mode": "virtual",
                "injected": 0, "reason": f"({x},{y}) 未命中窗口（未注入任何按键）"}
    mods = list(p["mods"])
    if p["shift"] and 0x10 not in mods:
        mods.append(0x10)
    seq = [(KDOWN, m, _klp(m)) for m in mods]
    seq += [(KDOWN, p["vk"], _klp(p["vk"])), (KUP, p["vk"], _klp(p["vk"], up=True))]
    seq += [(KUP, m, _klp(m, up=True)) for m in reversed(mods)]
    if dry:                                      # 干跑：只回报计划，零注入
        return {"ok": True, "action": "key", "combo": combo, "mode": "virtual",
                "dry": True, "hwnd": h, "planned": len(seq), "injected": 0,
                "mods": [real_input.MOD_KEYS.get(m, hex(m)) for m in mods]}
    guard = _release_stuck_in_window(h)             # 注入前清粘滞残留（virtual 通道）
    r = _post(h, seq, cleanup=_kbd_release_pairs)   # 统一成对兜底：失败即补发全部 KEYUP
    r["released_stuck"] = guard["released"]
    r.update({"action": "key", "combo": combo, "hwnd": h, "planned": len(seq),
              "pairing": "down/up 成对（_post cleanup）"})
    return r


if __name__ == "__main__":
    a = [s for s in sys.argv[1:] if not s.startswith("--")]; cmd = a[0] if a else "help"; F = lambda i: float(a[i]) if len(a) > i else 0
    try:
        if cmd == "click": r = click(F(1), F(2), a[3] if len(a) > 3 else "left", "--double" in sys.argv)
        elif cmd == "scroll": r = scroll(F(1), F(2), int(F(3)) or -3)
        elif cmd == "drag": r = drag(F(1), F(2), F(3), F(4))
        elif cmd == "type": r = type_text(F(1), F(2), " ".join(a[3:]) if len(a) > 3 else "")
        elif cmd == "key": r = key_combo(F(1), F(2), a[3] if len(a) > 3 else "",
                                         dry="--dry" in sys.argv)
        elif cmd == "mods": r = {"action": "mods", "mode": "read-only", "injected": 0,
                                 "stuck": real_input.stuck_modifiers()}
        elif cmd == "release":
            hh = int(a[1]) if len(a) > 1 else 0
            if "--dry" in sys.argv or not hh:
                r = {"action": "release", "mode": "read-only", "injected": 0, "dry": True,
                     "stuck": real_input.stuck_modifiers(), "hwnd": hh or None}
            else:
                r = _release_stuck_in_window(hh)
        else: r = {"help": "click x y [button] [--double] | scroll x y n | drag sx sy ex ey | type x y <文本> | key x y <ctrl+s> [--dry] | mods | release <hwnd> [--dry]"}
    except Exception as e: r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
