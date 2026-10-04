#!/usr/bin/env python3
"""batch_runner.py — 单进程执行步骤清单，**默认且仅默认**走统一后台输入后端 input_ops.py
（PostMessage 合成鼠标/键盘，零打扰）+ HUD 提示。

R3：后台路径**绝不**回退到物理输入。--real / --physical 会移动物理光标、改变焦点，
必须同时显式带 --consent=<用户同意凭据或字样> 才允许，否则拒绝执行并如实报告。
每步自动做焦点审计（前台窗口/物理光标/键盘焦点前后必须一致）。

步骤 JSON 数组元素: {"op":"click|double|rclick|move|drag|scroll|type|key|shot", "x":..,"y":..,
  "button":"left|right","double":true,"ex":..,"ey":..,"amount":-3,"text":"..","combo":"ctrl+s",
  "label":"..","desc":"..","win":"窗口子串","element":"元素名"}
带 "win"+"element" 时由只读 UIA 定位解析成屏幕坐标（R2：动作仍落到坐标点击）。
用法: python -B batch_runner.py steps.json [--virtual] [--real --consent=yes] [--delay=0.15] [--guard=<窗口>]
"""
import sys, os, json, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safety_gate, input_ops, hud_overlay, screenshot_verify  # 不再 import mouse_ops/real_input：后台路径禁止静默回退物理输入


def _resolve(st):
    """步骤 → (x, y, hwnd)。优先 win/element 只读定位，否则用显式坐标。"""
    if st.get("win") and st.get("element"):
        p = input_ops.locate(st["win"], st["element"])
        if not p.get("ok"):
            return None, None, None, p
        return p["x"], p["y"], p.get("hwnd"), {"element": p.get("element"), "via": "uia-read-only"}
    if st.get("win") and st.get("element2"):
        p1 = input_ops.locate(st["win"], st["element"])
        p2 = input_ops.locate(st["win"], st["element2"])
        if not (p1.get("ok") and p2.get("ok")):
            return None, None, None, {"reason": "元素定位失败", "from": p1, "to": p2}
        return p1["x"], p1["y"], p1.get("hwnd"), {"from": p1.get("element"), "to": p2.get("element"),
                                                  "ex": p2["x"], "ey": p2["y"], "via": "uia-read-only"}
    return st.get("x", 0), st.get("y", 0), None, {"coords": [st.get("x", 0), st.get("y", 0)]}


def _op(st, consent=None):
    op = st.get("op")
    if op == "shot":
        return screenshot_verify.capture(label=st.get("label", "step"))
    if op == "hud":
        return hud_overlay.show(st.get("text", ""), st.get("ttl", 15))
    x, y, hwnd, target = _resolve(st)
    if x is None:
        return {"ok": False, "reason": "目标定位失败", "detail": target}
    ex, ey = st.get("ex", target.get("ex") if isinstance(target, dict) else None), \
        st.get("ey", target.get("ey") if isinstance(target, dict) else None)
    btn = st.get("button", "left")
    dbl = bool(st.get("double"))
    if op == "click":
        r = input_ops.act("click", x, y, button=btn, double=dbl, hwnd=hwnd)
    elif op == "double":
        r = input_ops.act("double", x, y, button=btn, hwnd=hwnd)
    elif op == "rclick":
        r = input_ops.act("rclick", x, y, hwnd=hwnd)
    elif op == "move":
        r = input_ops.act("move", x, y, hwnd=hwnd)
    elif op == "drag":
        r = input_ops.act("drag", x, y, ex, ey)
    elif op == "scroll":
        r = input_ops.act("scroll", x, y, st.get("amount", -3))
    elif op == "type":
        r = input_ops.act("type", x, y, st.get("text", ""))
    elif op == "key":
        r = input_ops.act("key", x, y, st.get("combo", ""))
    else:
        return {"ok": False, "reason": "不支持的动作: " + str(op)}
    r["target"] = target
    if r.get("focus_changed") and consent:
        r["note"] = "物理回退已获用户同意（--consent），非默认路径"
    return r


def run(steps, mode="virtual", delay=0.15, guard=None, consent=None):
    if mode in ("real", "physical") and not consent:
        return {"ok": False, "refused": "focus-stealing", "mode": mode,
                "reason": "R3：--real/--physical 会移动物理光标并改变焦点，必须显式带 --consent=<用户同意> 才允许",
                "default": "去掉该旗标即走统一后台后端（input_ops / PostMessage）"}
    out, focus_hits = [], []
    n = len(steps)
    base = input_ops.focus_state()
    for i, st in enumerate(steps):
        g = safety_gate.check(f"{st.get('op')} {json.dumps(st, ensure_ascii=False)}")
        if not g["allowed"]:
            out.append({"step": i, "blocked": g["reason"]}); continue
        hud_overlay.show(f"[{i + 1}/{n}] {st.get('desc') or st.get('op')} ({st.get('x', '-')},{st.get('y', '-')})",
                         ttl=max(10, (n - i) * 3))
        res = _op(st, consent)
        out.append({"step": i, **(res if isinstance(res, dict) else {"result": res})})
        if res.get("focus_changed"):
            focus_hits.append(i)
        if guard:
            import human_gate
            hg = human_gate.check(guard)
            if hg.get("blocked"):
                out.append({"step": i, "human_gate": "stopped", "hits": hg["hits"]})
                return {"mode": mode, "steps": n, "stopped_at": i, "human_gate": hg,
                        "done": sum(1 for r in out if r.get("ok")), "results": out}
        if i < n - 1:
            time.sleep(delay)
    after = input_ops.focus_state()
    return {"mode": mode, "backend": "postmessage-mouse-keyboard", "steps": n,
            "done": sum(1 for r in out if r.get("ok")),
            "focus_unchanged": base == after, "focus_baseline": base, "focus_final": after,
            "steps_with_focus_change": focus_hits, "results": out}


if __name__ == "__main__":
    flags = [x for x in sys.argv[1:] if x.startswith("--")]
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    mode = "physical" if "--physical" in flags else "real" if "--real" in flags else "virtual"
    consent = next((f.split("=", 1)[1] for f in flags if f.startswith("--consent=")), None)
    delay = float(next((f.split("=", 1)[1] for f in flags if f.startswith("--delay=")), 0.15))
    guard = next((f.split("=", 1)[1] for f in flags if f.startswith("--guard=")), None)
    keep_hud = "--keep-hud" in flags
    try:
        src = args[0] if args else "help"
        steps = json.load(open(src, encoding="utf-8-sig")) if os.path.isfile(src) else json.loads(src)
        r = run(steps, mode, delay, guard, consent) if isinstance(steps, list) and steps else {"error": "步骤清单为空"}
    except Exception as e:
        r = {"error": str(e), "help": "run <steps.json> [--virtual] [--real --consent=yes] [--delay=0.15] [--guard=窗口>] [--keep-hud]"}
    finally:
        # R4 收口：任务结束（含异常）必须回收 HUD 进程，杜绝孤儿残留
        if not keep_hud:
            try:
                r["hud_reclaim"] = hud_overlay.hide()
            except Exception as e:
                r["hud_reclaim"] = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
