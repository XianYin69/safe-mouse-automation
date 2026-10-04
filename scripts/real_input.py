#!/usr/bin/env python3
"""real_input.py — 前台真输入回退（须先征得用户同意！）：SendInput 系统级注入，会移动物理光标、
改变焦点窗口，直接打扰用户。默认一律使用 virtual_mouse.py 后台方式；仅当目标应用忽略合成
PostMessage（Chromium/Electron/DirectUI）且截图验证无变化时，经用户确认后才调用本模块。
鼠标：move/click/drag/scroll；键盘：type（任意 Unicode 文本）与 key（组合快捷键）。"""
import sys, os, time, ctypes, atexit, signal
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
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

# ── 键盘注入（2026-10-04 事故根治：注入必须成对 + 原子）────────────────
# 解析与修饰键表交 keycombo（纯函数、不 import 本模块，避免循环导入）；
# 本模块只做 SendInput 投递与兜底，是 real 通道的唯一按键出口。
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keycombo

MODS = keycombo.MODS
BASE = keycombo.BASE
MOD_KEYS = keycombo.MOD_KEYS
SHIFT_NEEDED = keycombo.SHIFTED_KEYS          # 兼容旧名
_EXTENDED = keycombo.EXTENDED_KEYS            # 兼容旧名
KEK = keycombo.KEK                            # KEYEVENTF_EXTENDEDKEY
vk_of = keycombo.vk_of
parse_combo = keycombo.parse_combo
_OUTSTANDING = []                             # 本进程已按下、尚未确认抬起的修饰 vk（兼容旧名）
_INJECTED_ANY = False

def _kbd(vk, up=False, ext=None):
    """KEYBDINPUT：KEYUP 带 KRU；右侧/扩展键带 KEK（不带就释放不掉＝粘滞成因）。scan 供忽略 wVk 的布局。"""
    if ext is None:
        ext = keycombo.is_extended(vk)
    flags = (KRU if up else 0) | (KEK if ext else 0)
    try:
        scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
    except Exception:
        scan = 0
    return _mk(INPUT_KEYBOARD, "ki", KEYBDINPUT(vk, scan, flags, 0, None))

def _fire_many(items):
    """一次 SendInput 提交整批＝原子批；返回**实际插入**的事件数（部分失败据此算谁还按着）。"""
    n = len(items)
    if not n or not IS_WIN:
        return 0
    try:
        return int(SendInput(n, (INPUT * n)(*items), ctypes.sizeof(INPUT)))
    except Exception:
        return 0

def _fire_n(*inputs):
    return _fire_many(list(inputs))

def stuck_modifiers():
    """只读取证：GetAsyncKeyState 查当前按下态修饰键 → [{"vk","name"}]；零注入、零副作用。"""
    return [{"vk": v, "name": keycombo.NAME_OF_VK.get(v, hex(v))}
            for v in keycombo.stuck_modifiers()]

def _mark_held(vks):
    for v in vks:
        keycombo.HELD.add(v)
        if v not in _OUTSTANDING:
            _OUTSTANDING.append(v)

def _unmark_held(vks):
    for v in vks:
        keycombo.HELD.discard(v)
        if v in _OUTSTANDING:
            _OUTSTANDING.remove(v)

def _emit_keyups(vks):
    """real 通道释放实现：一次性 SendInput 批量提交全部 KEYUP（含扩展码）。"""
    vks = [int(v) for v in (vks or [])]
    names = [keycombo.NAME_OF_VK.get(v, hex(v)) for v in vks]
    if not vks:
        return {"injected": 0, "released": [], "mode": "real"}
    return {"injected": _fire_n(*[_kbd(v, up=True) for v in vks]),
            "released": names, "mode": "real"}

def release_all_modifiers(dry=False, keys=None, scope="stuck", emit=None):
    """B：对处于按下态的修饰键补发 KEYUP（一次原子批）。dry=True 只报告不注入。
    keys＝只处理这些 vk；scope="owned" 只兜本进程在册键；emit＝自定义投递（默认 SendInput）。"""
    det = keycombo.stuck_modifiers()
    if keys is not None:
        ks = set(int(k) for k in keys)
        det = [v for v in det if v in ks]
    if scope == "owned":
        det = [v for v in det if v in keycombo.HELD]
    names = [keycombo.NAME_OF_VK.get(v, hex(v)) for v in det]
    r = {"ok": True, "action": "release", "dry": bool(dry), "checked": len(keycombo.MONITOR_VKS),
         "stuck": names, "released": [], "released_vk": [hex(v) for v in det],
         "injected": 0, "mode": "read-only" if dry else "real"}
    if dry or not det:
        if dry and det:
            r["would_release"] = list(names)
        return r
    res = (emit or _emit_keyups)(det) or {}
    r["injected"] = int(res.get("injected", 0))
    r["released"] = list(names)
    _unmark_held(det)
    return r

def _pre_guard():
    """C：注入前置守卫——发现「非本进程发起」的修饰键处于按下态（粘滞残留）先释放再注入。
    用户自己正物理按住 Ctrl 时可设 env SAFE_MOUSE_SKIP_STICK_GUARD=1 跳过。"""
    if not IS_WIN or os.environ.get("SAFE_MOUSE_SKIP_STICK_GUARD") == "1":
        return {"checked": False, "skipped": True, "released": []}
    mine = set(keycombo.HELD)
    stuck = [v for v in keycombo.stuck_modifiers() if v not in mine]
    if not stuck:
        return {"checked": True, "skipped": False, "released": []}
    res = release_all_modifiers(keys=stuck)
    return {"checked": True, "skipped": False, "released": res["released"],
            "injected": res["injected"], "stuck": res["stuck"]}

def _safe_release(vks):
    """finally 兜底专用：释放动作本身出错绝不上抛（否则掩盖原始异常）。"""
    try:
        return _emit_keyups(vks)
    except Exception as e:
        return {"injected": 0, "error": str(e)}

def _safe_release_keys(vks):
    """finally 兜底专用（按 keys 过滤）：释放动作本身出错**绝不上抛**——
    否则掩盖 SendInput 的原始异常，且后续 _unmark_held 不执行、在册键残留。"""
    try:
        return release_all_modifiers(keys=list(vks))
    except Exception as e:
        return {"injected": 0, "released": [], "error": str(e)}


def _held_after(events, n, mods):
    """按实际提交的事件前缀推算仍处按下态的修饰键（部分失败时精确定位待补发的键）。"""
    held = []
    for e in events[:max(0, n)]:
        vk = e["vk"]
        if vk not in mods:
            continue
        if e["event"] == "keydown":
            if vk not in held:
                held.append(vk)
        elif vk in held:
            held.remove(vk)
    return held

_GUARDS_ON = False

def _install_exit_guards():
    """D：atexit + SIGINT/SIGTERM/SIGBREAK 兜底（委托 keycombo，只兜本进程在册键）。
    注：TerminateProcess 类硬杀不执行回调，所以「一次原子批」才是根治手段。"""
    global _GUARDS_ON
    if _GUARDS_ON or not IS_WIN:
        return {"installed": False}
    _GUARDS_ON = True
    try:
        return keycombo.install_exit_guards(_safe_release)
    except Exception as e:
        return {"installed": False, "error": str(e)}

def _exit_release():
    """只释放本进程按下且仍未抬起的修饰键；本进程从未注入过则完全不碰键盘。"""
    if not _INJECTED_ANY or not keycombo.HELD:
        return {"released": []}
    return release_all_modifiers(scope="owned")

def type_text(text):
    bad = next((d for d in DANGEROUS if d in str(text).lower()), None)
    if bad: return {"ok": False, "reason": f"文本含危险关键词: {bad}", "injected": 0, "mode": "real"}
    guard = _pre_guard()                        # C：注入前置守卫
    units = str(text).encode("utf-16-le")
    batch = []
    for i in range(0, len(units), 2):
        code = int.from_bytes(units[i:i + 2], "little")
        batch.append(_mk(INPUT_KEYBOARD, "ki", KEYBDINPUT(0, code, KFU, 0, None)))
        batch.append(_mk(INPUT_KEYBOARD, "ki", KEYBDINPUT(0, code, KFU | KRU, 0, None)))
    global _INJECTED_ANY
    _install_exit_guards()
    _INJECTED_ANY = True
    n = _fire_many(batch)                       # A：整段一次原子批（down/up 天然成对）
    r = {"ok": n > 0, "action": "type", "chars": len(text), "mode": "real",
         "atomic_batch": n, "injected": n}
    if guard.get("released"): r["released_stuck"] = guard["released"]
    return r

def press_keys(combo, dry=False, release_first=True):
    """A：整条组合键＝一个 INPUT 序列、一次 SendInput 原子批
    （mods down → vk down → vk up → mods up 逆序）；try/finally 无条件补发尚未释放的修饰键 up。
    dry=True 只回报计划（零注入、零守卫副作用）；解析交 keycombo.parse_combo（根因①已消除）。"""
    global _INJECTED_ANY
    plan = keycombo.parse_combo(combo)
    if not plan.get("ok"):
        return {"ok": False, "action": "key", "combo": combo, "mode": "real",
                "injected": 0, "reason": plan["reason"]}
    events = keycombo.event_plan(plan)
    mods = plan["held_modifiers"]
    if dry:
        return {"ok": True, "action": "key", "combo": combo, "mode": "real", "dry": True,
                "injected": 0, "planned": len(events), "sequence": events,
                "mods": [keycombo.NAME_OF_VK.get(v, hex(v)) for v in mods],
                "pairing": keycombo.verify_pairing(plan)}
    if release_first:
        try:
            guard = _pre_guard()
        except Exception as e:                       # 守卫故障不抛栈：降级放行并留痕
            guard = {"released": [], "checked": False, "guard_error": str(e)}
    else:
        guard = {"released": [], "skipped": "guard-off"}
    _install_exit_guards()
    _mark_held(mods)
    _INJECTED_ANY = True
    err, injected, remaining = None, 0, list(mods)
    try:
        injected = _fire_many([_kbd(e["vk"], up=(e["event"] == "keyup")) for e in events])
        remaining = _held_after(events, injected, mods) if injected else list(mods)
        if injected == 0:
            err = "SendInput 返回 0（可能被 UIPI 拦截或桌面已切换）"
        elif injected < len(events):
            err = "SendInput 部分提交 %d/%d" % (injected, len(events))
    except Exception as e:
        err = "SendInput 异常: %s" % e
    finally:
        if injected and remaining:
            fix = _safe_release(remaining)                    # 半批：这些键确实还按着
        elif remaining:
            fix = _safe_release_keys(remaining)                  # 未确认：只释放探测到按下的键
        else:
            fix = {"injected": 0, "released": []}
        _unmark_held(mods)
    r = {"ok": err is None, "action": "key", "combo": combo, "mode": "real",
         "atomic_batch": len(events), "injected": injected,
         "events_submitted": injected, "events_expected": len(events),
         "mods": [keycombo.NAME_OF_VK.get(v, hex(v)) for v in mods],
         "cleanup_released": fix.get("released", []),
         "pairing": keycombo.verify_pairing(plan), "sequence": events}
    if err: r["reason"] = err
    if guard.get("released"): r["released_stuck"] = guard["released"]
    return r


def _cursor_pos():
    p = wintypes.POINT(); ctypes.windll.user32.GetCursorPos(ctypes.byref(p)); return p.x, p.y

if __name__ == "__main__":
    import json
    ARGV = sys.argv[1:]
    DRY = "--dry" in ARGV
    a = [s for s in ARGV if not s.startswith("--")]
    cmd = a[0] if a else "help"
    F = lambda i: float(a[i]) if len(a) > i else 0
    try:
        if cmd == "move": r = move(F(1), F(2))
        elif cmd == "click": r = click(F(1), F(2), a[3] if len(a) > 3 else "left", 2 if "--double" in ARGV else 1)
        elif cmd == "drag": r = drag(F(1), F(2), F(3), F(4))
        elif cmd == "scroll": r = scroll(F(1), F(2), int(F(3)) or -3)
        elif cmd == "type": r = type_text(a[1] if len(a) > 1 else "")
        elif cmd == "key":
            r = (release_all_modifiers(dry=DRY) if "--release-all" in ARGV
                 else press_keys(a[1] if len(a) > 1 else "", dry=DRY,
                                 release_first=("--no-guard" not in ARGV)))
        elif cmd == "release": r = release_all_modifiers(dry=DRY)          # B：救回用户键盘
        elif cmd == "mods": r = {"action": "mods", "mode": "read-only", "injected": 0,
                                 "stuck": stuck_modifiers()}               # 只读，零注入
        else: r = {"help": "move x y | click x y [button] [--double] | drag sx sy ex ey | "
                           "scroll x y n | type <文本> | key <ctrl+s> [--dry] | "
                           "release [--dry] | mods | --release-all: key 子命令＝只释放不注入，其它子命令＝动作后附带清粘滞修饰键，配 --dry 则纯只读"}
    except Exception as e: r = {"error": str(e)}
    if "--release-all" in ARGV and cmd != "key" and isinstance(r, dict):   # 全局：任何动作后清残留
        r["release_all"] = release_all_modifiers(dry=DRY)
    print(json.dumps(r, ensure_ascii=False, indent=2))
