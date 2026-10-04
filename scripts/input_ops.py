#!/usr/bin/env python3
"""input_ops.py — R2 统一输入后端（本技能**唯一**动作入口）：所有动作都是「后台模拟鼠标/键盘事件」。

单一后端原则：
  Win32 目标 → PostMessage WM_MOUSEMOVE / WM_LBUTTONDOWN|UP|DBLCLK / WM_RBUTTONDOWN|UP /
              WM_MOUSEWHEEL / WM_KEYDOWN / WM_KEYUP / WM_CHAR（virtual_mouse.py）
  浏览器目标 → CDP Input.dispatchMouseEvent / Input.dispatchKeyEvent（输入级模拟，--cdp=<port>）
UIA 在本技能中**只允许只读枚举与定位**（取控件名 + 屏幕矩形）；真正的动作一律落到该矩形
中心坐标上发出模拟点击/按键——不再有 UIA Invoke/Toggle/Select/SetValue、不再有 WM_COMMAND。

焦点红线（R3）：每次调用前后自动比对 GetForegroundWindow 与 GetCursorPos，必须完全一致，
否则回报 focus_changed=true（并附前后值）。绝不 SetForegroundWindow / 移动物理光标。

命令（坐标 或 --win=<窗口子串> + 元素名 二选一）:
  click <x> <y> [left|right] [--double]        | click --win=<窗口> "<元素名>" [--button=right]
  double <x> <y>                               | double --win=<窗口> "<元素名>"
  rclick <x> <y>                               | rclick --win=<窗口> "<元素名>"
  move <x> <y>                                 | move --win=<窗口> "<元素名>"
  drag <sx> <sy> <ex> <ey>                     | drag --win=<窗口> "<起点元素>" "<终点元素>"
  scroll <x> <y> <格数>                         | scroll --win=<窗口> "<元素名>" <格数>
  type <x> <y> <文本...>                        | type --win=<窗口> "<元素名>" <文本...>
  key <x> <y> <ctrl+s>                          | key --win=<窗口> "<元素名>" <ctrl+s>
  resolve --win=<窗口> "<元素名>"               # 只读：看元素解析到的屏幕坐标
  browser <port> <click|x|type|scroll> ...      # 走 CDP 输入级模拟（浏览器目标）
通用: --tolerance=<px> 元素名匹配容差；--report 打印焦点审计明细。
"""
import sys, os, json, time, ctypes
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ctypes import wintypes
import virtual_mouse

U = ctypes.windll.user32 if sys.platform == "win32" else None


def focus_state():
    """前台窗口 + 物理光标 + 键盘焦点控件（只读，用于前后比对）。"""
    if not U:
        return {}
    pt = wintypes.POINT()
    U.GetCursorPos(ctypes.byref(pt))
    fg = U.GetForegroundWindow()
    kf = None
    if fg:
        gi = virtual_mouse._GTI(ctypes.sizeof(virtual_mouse._GTI))
        tid = U.GetWindowThreadProcessId(fg, None)
        if U.GetGUIThreadInfo(tid, ctypes.byref(gi)):
            kf = gi.hwndFocus
    return {"foreground": fg, "cursor": [pt.x, pt.y], "keyboard_focus": kf}


def locate(win_sub, el_name, tolerance=0):
    """只读 UIA 枚举定位：返回元素屏幕矩形中心坐标。**不做任何动作、不激活窗口。**"""
    import browser_ops  # 仅用其只读枚举工具（_ua/_win/_els/_find）
    ua = browser_ops._ua()
    if not ua:
        return {"ok": False, "reason": "uiautomation 未安装（只读定位也依赖它）"}
    win, err = browser_ops._win(ua, win_sub, allow_profile=True)
    if err:
        return {"ok": False, "reason": err.get("error"), "hint": "窗口标题子串不对？先 desktop_ops.py windows"}
    el = browser_ops._find(win, el_name)
    if el is None:
        return {"ok": False, "reason": f"未找到元素: {el_name}", "window": (win.Name or "")[:60]}
    r = el.BoundingRectangle
    if r.right - r.left <= 0 or r.bottom - r.top <= 0:
        return {"ok": False, "reason": f"元素 {el_name} 矩形为空（可能未渲染/已折叠）",
                "type": el.ControlTypeName}
    return {"ok": True, "x": (r.left + r.right) // 2, "y": (r.top + r.bottom) // 2,
            "rect": [r.left, r.top, r.right, r.bottom], "element": (el.Name or "")[:60],
            "type": el.ControlTypeName[:-7], "offscreen": bool(el.IsOffscreen),
            "hwnd": win.NativeWindowHandle, "via": "uia-read-only"}


def _audit(fn, *a, **k):
    """统一执行包装：后台动作 + 前后焦点/光标审计（R3 硬规则）。"""
    b = focus_state()
    res = fn(*a, **k) or {}
    time.sleep(0.05)
    e = focus_state()
    same = (b.get("foreground") == e.get("foreground") and b.get("cursor") == e.get("cursor")
            and b.get("keyboard_focus") == e.get("keyboard_focus"))
    res.setdefault("mode", "virtual")
    res["focus_audit"] = {"before": b, "after": e, "unchanged": same}
    if not same:
        res["focus_changed"] = True
        res["warning"] = "后台路径不应改变前台窗口/物理光标/键盘焦点——请检查该动作实现"
    return res


def owns_or_child(hwnd, x, y):
    """R3 安全护栏：给定 hwnd 时必须确认坐标命中的是它本身或其子窗口，
    否则合成消息会打到坐标底下的**别人**窗口——一律拒绝。"""
    hit = virtual_mouse._hit(x, y)
    if not hit or not hwnd:
        return False, hit
    if hit == hwnd:
        return True, hit
    GA_PARENT = 3
    cur = hit
    for _ in range(24):
        if not cur:
            break
        if cur == hwnd:
            return True, hit
        cur = U.GetAncestor(cur, GA_PARENT)
    return False, hit


def act(action, x, y, *rest, **kw):
    """把动作落到坐标上的合成鼠标/键盘事件（唯一后端：virtual_mouse / PostMessage）。"""
    h = kw.get("hwnd")
    occluded = None
    if h:
        ok_own, hit = owns_or_child(h, x, y)
        if not ok_own:
            # 「遮挡不停止」：显式带 hwnd 时消息只投给该窗口本身，绝不落到遮挡者，
            # 故调用方声明 occluded_ok=True 可继续（仍留 occluded_by 审计痕迹）。
            if kw.get("occluded_ok"):
                occluded = {"hit_hwnd": hit, "target_hwnd": h,
                            "note": "坐标被其它窗口遮挡，已改为定向投递给目标 hwnd"}
            else:
                return {"ok": False, "refused": "ownership", "hwnd": h, "hit_hwnd": hit,
                        "reason": f"坐标 ({x},{y}) 命中的不是目标窗口 {h}，拒绝投递"
                                  f"（防误伤用户前台窗口；确认为遮挡可传 occluded_ok=True）"}
    if action == "click":
        r = _audit(virtual_mouse.click, x, y, kw.get("button", "left"), kw.get("double", False), h)
        if occluded:
            r["occluded_by"] = occluded
        return r
    if action == "double":
        return _audit(virtual_mouse.click, x, y, kw.get("button", "left"), True, h)
    if action == "rclick":
        return _audit(virtual_mouse.click, x, y, "right", False, h)
    if action == "move":
        hh = h or virtual_mouse._hit(x, y)
        if not hh:
            return {"ok": False, "reason": f"({x},{y}) 未命中窗口"}
        return _audit(virtual_mouse._post, hh, [(virtual_mouse.MOVE, 0, virtual_mouse._lp(hh, x, y))])
    if action == "drag":
        return _audit(virtual_mouse.drag, x, y, rest[0], rest[1], hwnd=h)
    if action == "scroll":
        return _audit(virtual_mouse.scroll, x, y, int(rest[0]) if rest else -3, h)
    if action == "type":
        r = _audit(virtual_mouse.type_text, x, y, rest[0] if rest else "", h)
        if occluded:
            r["occluded_by"] = occluded
        return r
    if action == "key":
        r = _audit(virtual_mouse.key_combo, x, y, rest[0] if rest else "", h)
        if occluded:
            r["occluded_by"] = occluded
        return r
    return {"ok": False, "reason": "未知动作: " + str(action)}


def _flag(name, default=None):
    for a in sys.argv:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def _screen_ok(x, y):
    if not U:
        return True
    return 0 <= x <= U.GetSystemMetrics(0) and 0 <= y <= U.GetSystemMetrics(1)




def main():
    flags = [s for s in sys.argv[1:] if s.startswith("--")]
    pos = [s for s in sys.argv[1:] if not s.startswith("--")]
    action = pos[0] if pos else "help"
    if action in ("help", ""):
        return {"help": __doc__}
    if action == "resolve":
        return locate(_flag("--win", ""), " ".join(pos[1:]))
    nums, words = [], []
    for s in pos[1:]:
        try:
            nums.append(float(s))
        except ValueError:
            words.append(s)
    win_sub = _flag("--win")
    hwnd = None
    if win_sub:
        if not words:
            return {"ok": False, "reason": "--win 需要元素名"}
        el_name = words[0]
        if action == "drag":
            p1 = locate(win_sub, el_name)
            p2 = locate(win_sub, words[1] if len(words) > 1 else el_name)
            if not (p1.get("ok") and p2.get("ok")):
                return {"ok": False, "reason": "元素定位失败", "from": p1, "to": p2}
            x, y, extra, hwnd = p1["x"], p1["y"], (p2["x"], p2["y"]), p1.get("hwnd")
            target = {"from": p1["element"], "to": p2["element"], "via": "uia-read-only"}
        else:
            p = locate(win_sub, el_name)
            if not p.get("ok"):
                return p
            x, y, hwnd = p["x"], p["y"], p.get("hwnd")
            extra = tuple(nums)
            target = {"element": p["element"], "type": p["type"], "rect": p["rect"], "via": "uia-read-only"}
        words = words[1:]
    else:
        x = nums[0] if nums else 0
        y = nums[1] if len(nums) > 1 else 0
        extra = tuple(nums[2:])
        target = {"coords": [x, y]}
    if action == "type":
        extra = (" ".join(words),)
    elif action == "key":
        extra = (words[0] if words else "",)
    elif action == "scroll":
        extra = (int(extra[0]) if extra else -3,)
    if action != "move" and not _screen_ok(x, y):
        return {"ok": False, "reason": f"坐标越界 ({x},{y})：超出屏幕范围"}
    kw = {"button": words[0] if (action in ("click",) and words and words[0] in ("left", "right"))
          else ("right" if action == "rclick" else "left"),
          "double": "--double" in flags or action == "double", "hwnd": hwnd}
    r = act(action, x, y, *extra, **kw)
    r["target"], r["backend"], r["action"] = target, "postmessage-mouse-keyboard", action
    return r


if __name__ == "__main__":
    try:
        out = main()
    except Exception as e:
        out = {"error": str(e), "help": "python -B scripts/input_ops.py help"}
    print(json.dumps(out, ensure_ascii=False, indent=2))
