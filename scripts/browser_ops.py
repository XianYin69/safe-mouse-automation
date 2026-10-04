#!/usr/bin/env python3
"""browser_ops.py — 浏览器窗口**只读**枚举/定位（UIA 只读）+ 动作委托统一后端 input_ops.py。

R1：本技能**要**操作用户自己已经在跑的浏览器窗口（真实 profile、已登录），故不再拒绝
非 InPrivate 窗口；只读枚举拿标题+屏幕矩形，动作在矩形坐标上发后台模拟鼠标/键盘。
R2：已删除 UIA Invoke/Toggle/Select/DoDefaultAction/ValuePattern.SetValue 等"非鼠标键盘"捷径。
R3：只允许 ShowWindow(SW_SHOWNOACTIVATE=4)；绝不 SetForegroundWindow / 置前 / 动物理光标。
依赖：pip install uiautomation。

子命令：dump / click / type / wait / restore / **grab**（唯一取文本入口，见 grab 文档）。
"""
import sys, json, time, re
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from collections import deque

SW_SHOWNOACTIVATE = 4
# Chromium/Electron 忽略 PostMessage 合成输入（实测），故 grab 的 --copy 只是尽力而为
_NAMED_TYPES = ("TextControl", "EditControl", "ButtonControl", "HyperlinkControl",
                "ListItemControl", "TabItemControl", "ComboBoxControl", "DocumentControl",
                "CheckBoxControl", "RadioButtonControl", "GroupControl")


def _ua():
    try:
        import uiautomation as ua
        ua.SetGlobalSearchTimeout(4)
        return ua
    except ImportError:
        return None


def _win(ua, sub, allow_profile=True):
    """只读找窗口。allow_profile 保留形参以兼容旧调用，默认允许用户真实 profile 窗口（R1）。"""
    for w in ua.GetRootControl().GetChildren():
        try:
            if sub.lower() in (w.Name or "").lower() and not w.IsOffscreen:
                return w, None
        except Exception:
            continue
    for w in ua.GetRootControl().GetChildren():
        try:
            if sub.lower() in (w.Name or "").lower():
                return w, None
        except Exception:
            continue
    return None, {"error": f"未找到窗口: {sub}"}


def _walk(root, depth=40, limit=4000):
    """BFS（带深度上限/节点上限），异常即跳过该支——只读，不做任何动作。"""
    q = deque([(root, 0)]); n = 0
    while q and n < limit:
        c, d = q.popleft(); n += 1
        yield c, d
        if d < depth:
            try:
                for k in c.GetChildren():
                    q.append((k, d + 1))
            except Exception:
                pass


def _named(root, cap=4000):
    """子树里有多少个"具名"节点（Chromium a11y 懒加载的判据）。"""
    hits = 0
    for c, _d in _walk(root, 40, cap):
        try:
            if (c.Name or "").strip():
                hits += 1
        except Exception:
            pass
    return hits


def _docs(win, depth=40):
    """全深度收集 DocumentControl（旧实现 d<8 走不到页面子树——实测页面 doc 在 depth 11）。"""
    out = []
    for c, d in _walk(win, depth, 4000):
        try:
            if d > 0 and c.ControlTypeName == "DocumentControl":
                out.append((c, d))
        except Exception:
            continue
    return out


def _pick(docs):
    """从候选 DocumentControl 里挑真页面 doc：Name 非空优先 → 子节点多 → 深度大。"""
    best = None; best_key = None
    for c, d in docs:
        try:
            nm = (c.Name or "").strip()
            kids = len(c.GetChildren())
        except Exception:
            continue
        key = (1 if nm else 0, kids, -d)
        if best_key is None or key > best_key:
            best, best_key = c, key
    return best


def _doc(win, wait_named=0.0, probe_cap=1200):
    """选真正的页面 DocumentControl（全深度，不再停在空 Name 包装层）。

    旧缺陷（实测）：Edge 窗口下 6 个 DocumentControl，前 5 个 Name 为空、各只 1 个子节点
    （depth 7/9/10 包装层），页面 doc 在 depth 11 —— 旧 _doc 用 d<8 的 BFS 返回第一个空
    Name 包装层，dump 只走到 1 个节点 → elements=[]。
    Chromium a11y 树懒加载（实测 t0=330 节点、t+3s=660）→ wait_named>0 时轮询到具名节点>0。
    """
    best = _pick(_docs(win))
    info = {"tries": 0, "seconds": 0.0}
    if best is not None and wait_named > 0:
        t0 = time.time(); tries = 0
        while time.time() - t0 < float(wait_named):
            tries += 1
            n = _named(best, probe_cap)
            if n > 0:
                info = {"tries": tries, "seconds": round(time.time() - t0, 1), "named": n}
                break
            time.sleep(0.6)
            cand = _pick(_docs(win))          # 懒加载后可能才出现具名 doc，重选一次
            if cand is not None:
                best = cand
        else:
            info = {"tries": tries, "seconds": round(time.time() - t0, 1),
                    "named": _named(best, probe_cap) if best is not None else 0,
                    "exhausted": True}
    if best is not None:
        best._lazy_wait = info
    return best


def _els(root, limit=60000, depth=30):
    for c, _d in _walk(root, depth, limit):
        yield c


def _find(win, name):
    doc = _doc(win)
    best = None; off_exact = None; off_best = None
    for c in _els(doc or win):
        try:
            nm = c.Name or ""
            if not nm.strip():
                continue
            vis = not c.IsOffscreen
        except Exception:
            continue
        if nm == name:
            if vis:
                return c
            off_exact = off_exact or c
        elif name.lower() in nm.lower() and c.ControlTypeName in (
                "ButtonControl", "EditControl", "HyperlinkControl", "TabItemControl",
                "ListItemControl", "ComboBoxControl", "TextControl", "DocumentControl"):
            if vis and best is None:
                best = c
            if not vis and off_best is None:
                off_best = c
    return best or off_exact or off_best


def restore(win_sub, allow_profile=True):
    """R3：仅 SW_SHOWNOACTIVATE 恢复最小化窗口——显示但不激活、不抢前台焦点。"""
    ua = _ua()
    if not ua:
        return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    win, err = _win(ua, win_sub, allow_profile)
    if err:
        return err
    import ctypes
    hwnd = win.NativeWindowHandle
    was_min = bool(ctypes.windll.user32.IsIconic(hwnd))
    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    time.sleep(1.0)
    return {"ok": True, "restored_from_minimized": was_min, "hwnd": hwnd,
            "activate": False, "mode": "SW_SHOWNOACTIVATE"}


def _ensure_visible(win):
    """最小化→SW_SHOWNOACTIVATE 恢复；被遮挡**不需要**处理（后台输入不要求可见）。
    绝不 SetForegroundWindow / BringWindowToTop。"""
    import ctypes
    try:
        u = ctypes.windll.user32; hwnd = win.NativeWindowHandle
        if u.IsIconic(hwnd) or not u.IsWindow(hwnd):
            u.ShowWindow(hwnd, SW_SHOWNOACTIVATE); time.sleep(1.0)
        r = win.BoundingRectangle
        if r.right - r.left <= 0 or r.bottom - r.top <= 0:
            u.ShowWindow(hwnd, SW_SHOWNOACTIVATE); time.sleep(1.0)
            return True
    except Exception:
        pass
    return False


def _rect_center(el):
    r = el.BoundingRectangle
    return (r.left + r.right) // 2, (r.top + r.bottom) // 2


def click(win_sub, el_name, allow_profile=True):
    """R2：点击＝只读 UIA 定位矩形中心 → 统一后端发后台模拟鼠标事件。"""
    import input_ops
    ua = _ua()
    if not ua:
        return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    win, err = _win(ua, win_sub, allow_profile)
    if err:
        return err
    el = _find(win, el_name)
    if el is None:
        return {"ok": False, "reason": f"未找到元素: {el_name}", "window": (win.Name or "")[:60]}
    x, y = _rect_center(el)
    r = input_ops.act("click", x, y, hwnd=win.NativeWindowHandle)
    r.update({"action": "click", "element": (el.Name or "")[:60], "screen": [x, y],
              "backend": "postmessage-mouse-keyboard", "locate": "uia-read-only",
              "note": "Chromium 忽略 PostMessage 合成输入——无变化请改用 browser_cdp.py"})
    return r


def type_text(win_sub, el_name, text, allow_profile=True):
    """R2：填字＝模拟点击聚焦 → 向该窗口焦点控件后台投递 WM_CHAR（不再 SetValue）。"""
    import input_ops
    ua = _ua()
    if not ua:
        return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    win, err = _win(ua, win_sub, allow_profile)
    if err:
        return err
    el = _find(win, el_name)
    if el is None:
        return {"ok": False, "reason": f"未找到输入框: {el_name}"}
    x, y = _rect_center(el)
    c = input_ops.act("click", x, y, button="left")
    time.sleep(0.25)
    t = input_ops.act("type", x, y, text)
    t.update({"action": "type", "element": (el.Name or "")[:60],
              "backend": "postmessage-mouse-keyboard", "click_ok": c.get("ok"),
              "note": "Chromium 常忽略 PostMessage——浏览器请优先 browser_cdp.py"})
    return t


def dump(win_sub, limit=80, allow_profile=True, wait_named=3.0):
    """只读：枚举可交互元素名 + 屏幕矩形（动作请交 input_ops/app_ops 的坐标点击）。

    修 R1 缺陷：① 根节点交 _doc()（全深度 + 具名优先，不再停在空 Name 包装层）；
    ② IsOffscreen 不再一票否决——刚恢复/未渲染的节点照样收，标 offscreen=true。
    """
    ua = _ua()
    if not ua:
        return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    win, err = _win(ua, win_sub, allow_profile)
    if err:
        return err
    _ensure_visible(win)
    doc = _doc(win, wait_named=wait_named)
    out = []
    for c in _els(doc or win):
        try:
            nm = (c.Name or "").strip()
            if not nm or c.ControlTypeName not in (
                    "ButtonControl", "EditControl", "HyperlinkControl", "TabItemControl",
                    "ListItemControl", "ComboBoxControl"):
                continue
            r = c.BoundingRectangle
            if r.right - r.left <= 0 or r.bottom - r.top <= 0:
                continue
            out.append({"name": nm[:50], "type": c.ControlTypeName[:-7],
                        "rect": [r.left, r.top, r.right, r.bottom],
                        "screen_xy": [(r.left + r.right) // 2, (r.top + r.bottom) // 2],
                        "offscreen": bool(c.IsOffscreen)})
            if len(out) >= limit:
                break
        except Exception:
            continue
    return {"window": (win.Name or "")[:80], "root": "document" if doc is not None else "window",
            "lazy_wait": getattr(doc, "_lazy_wait", None) if doc is not None else None,
            "elements": out, "count": len(out), "read_only": True}


def wait(win_sub, el_name, seconds=15, allow_profile=True):
    """只读轮询等元素出现（不做任何动作、不激活窗口）。"""
    ua = _ua()
    if not ua:
        return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    t0 = time.time()
    while time.time() - t0 < float(seconds):
        win, err = _win(ua, win_sub, allow_profile)
        if not err and _find(win, el_name) is not None:
            return {"ok": True, "found": el_name, "waited": round(time.time() - t0, 1),
                    "read_only": True}
        time.sleep(0.8)
    return {"ok": False, "reason": f"超时未见元素: {el_name}"}


# ── grab：唯一取文本入口（attach 真实窗口 → 后台点击 Tab → 只读 UIA 取正文）──────
# 疑似凭据特征（实测缺陷：旧表漏了 GitHub OAuth Client ID 的 Ov23li/Iv23li 形态）
_TOKEN_PATTERNS = [
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,220}\b")),
    ("gh_prefix", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,60}\b")),
    ("Iv1_Iv2", re.compile(r"\bIv[12]\.[0-9a-fA-F]{16,40}\b")),
    ("oauth_client_id", re.compile(r"\b(?:Ov23li|Iv23li|Ov23|Iv23)[A-Za-z0-9]{8,40}\b")),
    ("sk_", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,64}\b")),
    ("hex32_40", re.compile(r"\b[0-9a-fA-F]{32,40}\b")),
]
# 标签邻近取值：GitHub 把 Client ID 的值单独成行，光靠前缀表覆盖不到所有形态
_LABEL = re.compile(r"(?i)\b(client[\s_-]?id|client[\s_-]?secret|oauth[\s_-]?secret|"
                    r"api[\s_-]?key|access[\s_-]?token|token|secret)\b")
_CAND = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9_.\-]{15,}\b")
_STOP = re.compile(r"(?i)(github\.com|https?://|docs\.|marketplace|application|"
                   r"notification|redirect|description|password|undefined|cookies)")


def _hexish(v):
    return re.fullmatch(r"(?i)[0-9a-f]{20,40}", v) is not None


def _looks_credential(v):
    v = (v or "").strip(" .,:;|")
    if not (16 <= len(v) <= 64) or not _CAND.fullmatch(v):
        return False
    if _STOP.search(v) or "/" in v or "@" in v:
        return False
    if not (any(ch.isdigit() for ch in v) and any(ch.isalpha() for ch in v)):
        return False
    if v.islower() and not _hexish(v):
        return False        # 纯小写词（用户名/路径）不算凭据
    return True

def mask(s):
    """日志/链一律掩码（前6后4）；明文只出现在 stdout。"""
    s = s or ""
    if len(s) <= 12:
        return "*" * len(s)
    return s[:6] + "…" + s[-4:]


def find_tokens(src):
    """单列疑似 token：前缀特征 + 「标签邻近」两路（明文只回 stdout，日志/链一律掩码）。"""
    found = []; seen = set()

    def add(kind, v):
        v = (v or "").strip(" .,:;|")
        if v and v not in seen:
            seen.add(v)
            found.append({"kind": kind, "value": v, "masked": mask(v), "len": len(v)})
    src = src or ""
    for kind, rx in _TOKEN_PATTERNS:
        for m in rx.finditer(src):
            add(kind, m.group(0))
    lines = src.splitlines()
    for i, ln in enumerate(lines):
        mm = _LABEL.search(ln)
        if not mm:
            continue
        cands = [c.group(0) for c in _CAND.finditer(ln[mm.end():])]
        if not cands:                       # 值常在标签的下一行（GitHub 即如此）
            for j in range(i + 1, min(i + 4, len(lines))):
                nxt = lines[j].strip()
                if not nxt:
                    continue
                cands = [c.group(0) for c in _CAND.finditer(nxt)]
                if cands:
                    break
        for c in cands:
            if _looks_credential(c):
                add("label:%s" % mm.group(1).lower().replace(" ", "_"), c)
    return found


def _val(c):
    """只读取控件文本：Name + ValuePattern.Value（读，不写——R2 只禁 SetValue）。"""
    out = []
    try:
        nm = (c.Name or "").strip()
        if nm:
            out.append(nm)
    except Exception:
        pass
    try:
        if hasattr(c, "GetValuePattern"):
            vp = c.GetValuePattern()
            v = ((getattr(vp, "CurrentValue", None) or getattr(vp, "Value", None) or "").strip()
                 if vp else "")
            if v and v not in out:
                out.append(v)
    except Exception:
        pass
    try:
        if len(out) < 2:
            li = c.GetLegacyIAccessiblePattern()
            lv = (getattr(li, "Value", "") or "").strip() if li else ""
            if lv and lv not in out:
                out.append(lv)
    except Exception:
        pass
    return " | ".join(out)


def _page_text(doc, limit=4000):
    """只读遍历页面子树，按文档顺序拼正文（含相邻标签，便于识别 Client ID 归属）。"""
    lines = []
    for c in _els(doc, limit=60000, depth=40):
        try:
            if c.ControlTypeName not in _NAMED_TYPES:
                continue
            t = _val(c)
        except Exception:
            continue
        if t:
            lines.append(t)
            if len(lines) >= limit:
                break
    return lines


def grab(target, do_copy=False, grep=None, limit=400, allow_profile=True,
         settle=1.2, wait_named=4.0):
    """唯一取文本入口：附着用户已在跑的真实浏览器窗口（R1）→ 在该 Tab 矩形中心后台模拟
    点击（R2 合成鼠标）→ 等 a11y 懒加载渲染 → 只读 UIA 取正文 → 输出疑似 token。

    target 先按 TabItem 名匹配，匹配不到再按窗口标题匹配（R1：绝不另开空 profile、
    绝不反问用户为何没登录）。--copy 再后台 Ctrl+A/Ctrl+C 经 clip_ops 读回并还原剪贴板。
    全程不 SetForegroundWindow、不动物理光标（focus_audit 自证）。
    """
    import input_ops
    ua = _ua()
    if not ua:
        return {"error": "uiautomation 未安装，运行: pip install uiautomation"}
    win = None; tab = None; tabs = []
    for w in ua.GetRootControl().GetChildren():
        try:
            nm = w.Name or ""
        except Exception:
            continue
        if not any(k in nm for k in ("Edge", "Chrome", "Chromium", "Brave", "Vivaldi")) \
                and (target or "").lower() not in nm.lower():
            continue
        _ensure_visible(w)
        cand = []
        for c in _els(w, limit=8000, depth=14):
            try:
                if c.ControlTypeName == "TabItemControl" and (c.Name or "").strip():
                    cand.append(c)
            except Exception:
                continue
        hit = None
        for c in cand:
            if target.lower() in (c.Name or "").lower():
                hit = c; break
        if hit is not None:
            win, tab = w, hit
            tabs = [(c.Name or "")[:60] for c in cand]
            break
        if win is None and cand:
            win = w
            tabs = [(c.Name or "")[:60] for c in cand]
    if win is None:
        win, err = _win(ua, target, allow_profile)
        if err:
            return dict(err, tabs_seen=tabs,
                        policy="R1：附着用户已在跑的真实窗口；未找到请核对浏览器窗口标题/Tab 名")

    if tab is None:
        for c in _els(win, limit=8000, depth=14):
            try:
                if c.ControlTypeName == "TabItemControl" and \
                        target.lower() in (c.Name or "").lower():
                    tab = c; break
            except Exception:
                continue
    out = {"window": (win.Name or "")[:80], "hwnd": win.NativeWindowHandle,
           "tabs_seen": tabs[:20], "read_only": True, "channel": "attach-real-window"}
    if tab is not None:
        x, y = _rect_center(tab)
        out["tab"] = (tab.Name or "")[:60]
        r = input_ops.act("click", x, y, hwnd=win.NativeWindowHandle, occluded_ok=True)
        r["screen"] = [x, y]
        out["tab_click"] = r
        time.sleep(settle)
    else:
        out["tab_click"] = {"skipped": "未匹配到 TabItem，按当前活动标签读取"}
    doc = _doc(win, wait_named=wait_named)
    out["doc_name"] = ((doc.Name if doc else "") or "")[:60]
    out["lazy_wait"] = getattr(doc, "_lazy_wait", None) if doc is not None else None
    lines = _page_text(doc or win, limit=limit)
    out["uia_lines"] = len(lines)
    out["text"] = "\n".join(lines)
    out["text_preview"] = out["text"][:600]

    if do_copy:
        import clip_ops
        cx, cy = _rect_center(doc or win)
        snap = clip_ops.snapshot("grab-%s" % (target or "")[:20])
        out["clip_snapshot"] = {"ok": snap.get("ok"), "id": snap.get("id"),
                                "kept": snap.get("kept"), "bytes": snap.get("bytes")}
        if not snap.get("ok"):
            out["copy"] = {"error": "快照失败，放弃 Ctrl+C（不污染用户剪贴板）: %s"
                                  % snap.get("error")}
        else:
            clip_ops._set_many([(clip_ops.CF_UNICODETEXT, b"\x00\x00")])
            ca = input_ops.act("key", cx, cy, "ctrl+a", hwnd=win.NativeWindowHandle,
                               occluded_ok=True)
            time.sleep(0.35)
            cc = input_ops.act("key", cx, cy, "ctrl+c", hwnd=win.NativeWindowHandle,
                               occluded_ok=True)
            time.sleep(0.6)
            rd = clip_ops.read("CF_UNICODETEXT")
            out["copy"] = {"ctrl_a": {"ok": ca.get("ok"), "mode": ca.get("mode")},
                           "ctrl_c": {"ok": cc.get("ok"), "mode": cc.get("mode")},
                           "chars": rd.get("chars"),
                           "error": rd.get("error"),
                           "note": "Chromium 常忽略 PostMessage 合成键——读不到即如实报告，"
                                   "不抢焦点回退（须用户同意才用 real_input.py）"}
            if rd.get("ok") and rd.get("text"):
                out["clip_text"] = rd["text"]
            rs = clip_ops.restore(snap["id"])
            out["clip_restored"] = {"ok": rs.get("ok"), "error": rs.get("error")}

    # 疑似 token 提取（明文只回 stdout；日志/链一律掩码）
    src = out.get("clip_text") or out.get("text") or ""
    found = find_tokens(src)
    if grep:  # 只保留与关键词同行的命中，便于定位
        kw = grep.lower()
        ctx = [l for l in src.splitlines() if kw in l.lower()][:20]
        out["grep_context"] = ctx
        found = [f for f in found if grep.lower() in f["value"].lower()
                 or any(grep.lower() in l.lower() for l in ctx)] or found
    out["tokens"] = found
    out["tokens_masked"] = [{"kind": f["kind"], "masked": f["masked"]} for f in found]
    fa = []
    tc = out.get("tab_click") or {}
    if isinstance(tc, dict) and tc.get("focus_audit"):
        fa.append(dict(tc["focus_audit"], step="tab_click"))
    cp = out.get("copy") or {}
    for k in ("ctrl_a", "ctrl_c"):
        v = cp.get(k) or {}
        if isinstance(v, dict) and v.get("focus_audit"):
            fa.append(dict(v["focus_audit"], step=k))
    out["focus_audits"] = fa
    out["focus_unchanged"] = (all(bool(a.get("unchanged", True)) for a in fa)
                              if fa else None)
    if len(out.get("text") or "") > 4000:
        out["text"] = out["text"][:4000]
        out["text_truncated"] = True
    return out


def _flagval(name):
    for a in sys.argv:
        if a.startswith("--%s=" % name):
            return a.split("=", 1)[1]
    return None


if __name__ == "__main__":
    ap = not ("--no-profile" in sys.argv)
    flags = [s for s in sys.argv[1:] if s.startswith("--")]
    a = [s for s in sys.argv[1:] if not s.startswith("--")]
    cmd = a[0] if a else "help"
    try:
        if cmd == "dump":
            r = dump(a[1], int(a[2]) if len(a) > 2 else 80, ap)
        elif cmd == "click":
            r = click(a[1], a[2], ap)
        elif cmd == "type":
            r = type_text(a[1], a[2], " ".join(a[3:]), ap)
        elif cmd == "wait":
            r = wait(a[1], a[2], a[3] if len(a) > 3 else 15, ap)
        elif cmd == "restore":
            r = restore(a[1], ap)
        elif cmd == "grab":
            r = grab(a[1], do_copy=("--copy" in flags), grep=_flagval("grep"),
                     limit=int(_flagval("limit") or 400), allow_profile=ap,
                     settle=float(_flagval("settle") or 1.2),
                     wait_named=float(_flagval("wait") or 4.0))
            if "--mask" in flags:      # 日志/链用：token 全掩码
                r["text"] = None
                for f in r.get("tokens") or []:
                    f["value"] = f["masked"]
                if r.get("clip_text"):
                    r["clip_text"] = "(masked)"
        else:
            r = {"help": __doc__}
    except Exception as e:
        r = {"error": "%s: %s" % (type(e).__name__, e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
