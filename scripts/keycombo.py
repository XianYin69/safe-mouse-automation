#!/usr/bin/env python3
"""keycombo.py — 组合键统一解析 + 修饰键残留守卫（real_input / virtual_mouse 共用，R6）。

**本模块是纯函数 + 只读探测层，不含任何注入 API，也绝不 import real_input**
（real_input 反过来依赖本模块；曾出现双向 import 造成循环导入、键盘通道整体瘫痪）。

修根因（2026-10-04 用户键盘被卡死事故）：
① real_input.press_keys 把 `sh = vk in {...}` 写在 `if vk is None: return ...` 的同一 if 体内，
   vk 有效时 sh 永不绑定 → 任何合法组合键 NameError，且异常发生在修饰键 down 之后、up 之前。
② down/up 分散成多次 SendInput、无 try/finally → 进程被 taskkill/看门狗杀掉或半途异常时
   Ctrl/Alt 永久停在按下态 → 用户键盘像被重映射（卡死根因）。
规范：注入必须**成对 + 原子**（一个序列一次提交），异常路径无条件补发尚未释放的 KEYUP。

VK 以 winuser.h 为准：LSHIFT=0xA0 RSHIFT=0xA1 LCONTROL=0xA2 RCONTROL=0xA3
LMENU=0xA4 RMENU=0xA5 LWIN=0x5B RWIN=0x5C；右侧键 KEYUP 必须带 KEYEVENTF_EXTENDEDKEY，
左侧键**不带**（带错标志会释放不掉，正是粘滞的另一成因）。
"""
import sys, os, atexit, ctypes
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

IS_WIN = sys.platform == "win32"
U = ctypes.windll.user32 if IS_WIN else None
if U is not None:      # GetAsyncKeyState 返回 SHORT：显式声明 restype 防符号位误判
    try:
        U.GetAsyncKeyState.restype = ctypes.c_short
        U.GetAsyncKeyState.argtypes = [ctypes.c_int]
    except Exception:
        pass

KEK, KUP_F, KUNI, KSC = 0x0001, 0x0002, 0x0004, 0x0008   # KEYEVENTF_*

MODS = {"ctrl": 0x11, "control": 0x11, "alt": 0x12, "menu": 0x12, "option": 0x12,
        "shift": 0x10, "win": 0x5B, "cmd": 0x5B, "super": 0x5B, "meta": 0x5B,
        "lshift": 0xA0, "rshift": 0xA1, "lctrl": 0xA2, "rctrl": 0xA3,
        "lalt": 0xA4, "ralt": 0xA5, "lwin": 0x5B, "rwin": 0x5C, "apps": 0x5D}
# vk → 可读名（通用码 + 左右实例，winuser.h 真值）；粘滞释放只查这些键，绝不碰普通键
MOD_KEYS = {0x11: "ctrl", 0xA2: "ctrl_l", 0xA3: "ctrl_r",
            0x12: "alt", 0xA4: "alt_l", 0xA5: "alt_r",
            0x10: "shift", 0xA0: "shift_l", 0xA1: "shift_r",
            0x5B: "win_l", 0x5C: "win_r", 0x5D: "apps"}
# 右侧/扩展键：KEYUP 必须带 KEYEVENTF_EXTENDEDKEY，否则释放不掉（粘滞成因之一）。
# 0xA2/0xA4 是**左** Ctrl/Alt，不属扩展码，绝不能带 KEK。
EXTENDED_KEYS = {0xA1, 0xA3, 0xA5, 0x5B, 0x5C, 0x5D, 0x2D, 0x2E,
                 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x6F}
SHIFTED_KEYS = {0xBB, 0xDB, 0xDD, 0xDC, 0xBA, 0xDE}   # 需 Shift 才出字符（沿用旧集合，只修作用域）
MONITOR_VKS = tuple(MOD_KEYS.keys())                  # 粘滞探测范围

BASE = {**{c: 0x41 + i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")},
        **{str(i): 0x30 + i for i in range(10)},
        "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B,
        "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "ins": 0x2D, "home": 0x24,
        "end": 0x23, "pgup": 0x21, "pgdn": 0x22, "up": 0x26, "down": 0x28,
        "left": 0x25, "right": 0x27, "prtsc": 0x2C,
        "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA, "'": 0xDE,
        ",": 0xBC, ".": 0xBE, "/": 0xBF, "`": 0xC0}
for _i in range(1, 13):
    BASE["f" + str(_i)] = 0x6F + _i

NAME_OF_VK = dict(MOD_KEYS)
for _n, _v in BASE.items():
    NAME_OF_VK.setdefault(_v, _n)

def vk_of(k):
    if k is None:
        return None
    return BASE.get(k) or BASE.get(k.upper()) or BASE.get(k.lower())

def is_extended(vk):
    return vk in EXTENDED_KEYS

def parse_combo(combo):
    """唯一解析入口（real_input 与 virtual_mouse 共用）：'ctrl+shift+z' / 'ctrl alt del' → 计划。

    返回 {"ok","parts","mods","shift","shift_extra","vk","key_name","held_modifiers",
          "down","up","reason"}；ok=False 时 down/up 为空——调用方必须保证**未注入任何按键**。
    纯函数：不碰任何注入 API，可 --dry 直接打印（打印即注入序列，防「打印对、注入错」）。
    """
    parts = [p.strip().lower() for p in str(combo or "").replace("+", " ").split() if p.strip()]
    empty = {"parts": parts, "mods": [], "shift": False, "shift_extra": False, "vk": None,
             "key_name": None, "held_modifiers": [], "down": [], "up": []}
    if not parts:
        return dict(empty, ok=False, reason="空组合键（未注入任何按键）")
    bad_mod = next((p for p in parts[:-1] if p not in MODS), None)
    if bad_mod:
        return dict(empty, ok=False, mods=[MODS[p] for p in parts[:-1] if p in MODS],
                    reason="未知修饰键: %s（未注入任何按键）" % bad_mod)
    vk = vk_of(parts[-1])
    if vk is None:
        return dict(empty, ok=False, mods=[MODS[p] for p in parts[:-1]],
                    reason="未知按键: %s（未注入任何按键）" % parts[-1])
    mods, seen = [], set()
    for p in parts[:-1]:
        if MODS[p] not in seen:
            seen.add(MODS[p]); mods.append(MODS[p])
    shift_extra = (vk in SHIFTED_KEYS) and (0x10 not in seen)   # 修根因①：独立成句
    held = mods + ([0x10] if shift_extra else [])
    return {"ok": True, "parts": parts, "mods": mods, "shift": shift_extra,
            "shift_extra": shift_extra, "vk": vk, "key_name": parts[-1],
            "held_modifiers": held, "down": held + [vk],
            "up": [vk] + list(reversed(held)), "reason": ""}

HELD = set()      # 本进程注入过、尚未确认释放的修饰 vk（兜底只动这些，绝不动用户正按的键）

def event_plan(plan):
    """解析结果 → 注入事件清单（--dry 打印的与实际注入的**同源**，防「打印对、注入错」）。"""
    if not plan.get("ok"):
        return []
    ev = [{"event": "keydown", "vk": v, "name": NAME_OF_VK.get(v, "?"),
           "extended": is_extended(v)} for v in plan["down"]]
    ev += [{"event": "keyup", "vk": v, "name": NAME_OF_VK.get(v, "?"),
            "extended": is_extended(v)} for v in plan["up"]]
    return ev

def stuck_modifiers(vks=None):
    """只读探测：GetAsyncKeyState 高位＝1 即按下态。返回 vk 列表；零注入、零副作用。"""
    if U is None:
        return []
    want = set(int(v) for v in vks) if vks else set(MONITOR_VKS)
    out = []
    for vk in MONITOR_VKS:
        if vk not in want:
            continue
        try:
            if (U.GetAsyncKeyState(vk) & 0x8000) != 0:
                out.append(vk)
        except Exception:
            pass
    return out

def release_all_modifiers(emit=None, scope="stuck", dry=False):
    """修饰键残留守卫：探测按下态 → 交后端 emit(vks) 一次原子批补发 KEYUP → 返回释放清单。

    本模块**自身不含任何注入 API**（emit=None 时只探测不动作），注入实现留在后端：
    real＝SendInput 批量、virtual＝PostMessage 到目标窗口。
    dry=True 只报清单零注入；scope="owned" 只兜本进程 HELD 里的键（绝不动用户正按的键）。
    """
    det = stuck_modifiers()
    if scope == "owned":
        det = [v for v in det if v in HELD]
    res = {"ok": True, "released": [NAME_OF_VK.get(v, hex(v)) for v in det],
           "released_vk": [hex(v) for v in det], "count": len(det),
           "dry": bool(dry), "injected": 0, "scope": scope}
    if dry or not det:
        if dry and det:
            res["would_release"] = list(res["released"])
        return res
    if emit is None:
        res["skipped"] = "no-emitter（keycombo 自身不注入）"
        return res
    r = emit(det) or {}
    res["injected"] = int(r.get("injected", 0))
    for v in det:
        HELD.discard(v)
    return res

def install_exit_guards(emit, signals=("SIGINT", "SIGTERM", "SIGBREAK")):
    """atexit + 信号兜底：退出/被中断前无条件释放 HELD 中本进程按下的修饰键。
    非主线程 signal.signal 抛 ValueError → 只保留 atexit，绝不抛栈。
    注：TerminateProcess 类硬杀不执行回调，所以「一次原子批」才是根治手段。"""
    def _flush():
        try:
            return release_all_modifiers(emit=emit, scope="owned")
        except Exception:
            return {"ok": False}
    atexit.register(_flush)
    import signal as _sig
    hooked = []
    for name in signals:
        s = getattr(_sig, name, None)
        if s is None:
            continue
        try:
            prev = _sig.getsignal(s)
            _sig.signal(s, lambda *a: (_flush(), (prev(*a) if callable(prev) else sys.exit(1))))
            hooked.append(name)
        except Exception:
            pass
    return {"atexit": True, "signals": hooked}

def verify_pairing(plan):
    """不变式：每个 keydown 都有配对 keyup（计数相等 + 释放序＝vk 先、修饰键逆序）。纯函数。"""
    if not plan.get("ok"):
        return {"paired": None, "reason": plan.get("reason", "解析失败")}
    from collections import Counter
    d, u = Counter(plan["down"]), Counter(plan["up"])
    ok = (d == u) and (plan["up"] == [plan["down"][-1]] + list(reversed(plan["held_modifiers"])))
    return {"paired": ok, "down": plan["down"], "up": plan["up"],
            "down_names": [NAME_OF_VK.get(v, "?") for v in plan["down"]],
            "up_names": [NAME_OF_VK.get(v, "?") for v in plan["up"]]}

def _backend_emitter():
    """惰性取后端 KEYUP 发射器（**绝不**模块级 import real_input：双向依赖曾致循环导入）。

    本模块仍不含注入 API——注入实现留在后端：real_input._emit_keyups 一次 SendInput 原子批
    **只发 KEYUP**，绝不按下任何键、绝不发 keydown。取不到后端返回 None，release 退化为只报清单。
    直跑本脚本时模块名＝__main__，先把 sys.modules['keycombo'] 指向本实例，
    免得 real_input 再加载第二份 keycombo 造成 HELD/键表两处漂移。
    """
    if not IS_WIN:
        return None
    try:
        if "keycombo" not in sys.modules:
            sys.modules["keycombo"] = sys.modules.get(__name__) or sys.modules["__main__"]
        import real_input
        f = getattr(real_input, "_emit_keyups", None)
        return f if callable(f) else None
    except Exception:
        return None

if __name__ == "__main__":
    import json
    a = [s for s in sys.argv[1:] if not s.startswith("--")]
    cmd = a[0] if a else "help"
    DRY = "--dry" in sys.argv
    if cmd == "parse":
        p = parse_combo(" ".join(a[1:]))
        print(json.dumps({"plan": p, "events": event_plan(p), "pairing": verify_pairing(p),
                          "mode": "read-only", "injected": 0}, ensure_ascii=False, indent=2))
    elif cmd == "stuck":
        print(json.dumps({"mode": "read-only", "injected": 0,
                          "stuck": [NAME_OF_VK.get(v, hex(v)) for v in stuck_modifiers()],
                          "stuck_vk": [hex(v) for v in stuck_modifiers()],
                          "note": "本模块自身不注入；真释放走 keycombo.py release --yes（只补 KEYUP，须同意）或 real_input.py release [--dry]"},
                         ensure_ascii=False, indent=2))
    elif cmd == "check":
        cases = ["ctrl+alt+del", "ctrl+s", "ctrl+shift+z", "ctrl+=", "shift+a", "win+d",
                 "alt+f4", "ctrl+alt+delete", "ctrl+shift+s", "ctrl+1", "ctrl+alt+shift+f12"]
        rows, bad = [], 0
        for c in cases:
            p = parse_combo(c); v = verify_pairing(p)
            if not p.get("ok") or not v.get("paired"):
                bad += 1
            rows.append({"combo": c, "ok": p.get("ok"), "shift_extra": p.get("shift_extra"),
                         "events": len(event_plan(p)), **v})
        print(json.dumps({"ok": bad == 0, "failed": bad, "cases": rows, "injected": 0,
                          "mode": "read-only",
                          "stuck_now": [NAME_OF_VK.get(v, hex(v)) for v in stuck_modifiers()]},
                         ensure_ascii=False, indent=2))
        sys.exit(0 if bad == 0 else 1)
    elif cmd == "release":
        # 只补 KEYUP（绝不按下任何键）：--dry 只报告零注入；真注入须 --yes（前台 SendInput，须同意）
        scope = "stuck"
        for _s in sys.argv[1:]:
            if _s.startswith("--scope="):
                scope = (_s.split("=", 1)[1].strip() or "stuck")
        if scope not in ("stuck", "owned"):
            scope = "stuck"
        if DRY:
            r = release_all_modifiers(emit=None, scope=scope, dry=True)
            r["mode"] = "read-only"
        elif "--yes" not in sys.argv:
            r = release_all_modifiers(emit=None, scope=scope, dry=True)
            r["mode"] = "read-only"
            r["refused"] = "consent"
            r["hint"] = "真释放会向前台补发 KEYUP，须带 --yes 表示同意（只补 KEYUP，绝不按下任何键）"
        else:
            emit = _backend_emitter()
            r = release_all_modifiers(emit=emit, scope=scope, dry=False)
            r["mode"] = "real-keyup-only" if emit else "read-only"
            if not emit:
                r["skipped"] = "后端不可用（real_input._emit_keyups）：只报清单，零注入"
        r["keydown_sent"] = 0
        r["injected"] = int(r.get("injected", 0))
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("用法: parse <combo> | stuck | check | release [--dry] [--yes] [--scope=stuck|owned]")
        print("  parse / check：纯函数解析与 down/up 成对自检；stuck：只读探测——三者全程零注入。")
        print("  release：直连 release_all_modifiers()，**只补 KEYUP、绝不按下任何键**。")
        print("    --dry  只报清单零注入；不带 --yes 亦只报清单（refused=consent）。")
        print("    --yes  真释放（前台 SendInput，须同意）；--scope=owned 只兜本进程在册键。")
