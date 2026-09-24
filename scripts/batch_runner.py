#!/usr/bin/env python3
"""batch_runner.py — 加快整体流程：单进程执行步骤清单，默认后台虚拟输入（PostMessage，零打扰）+HUD 提示。
--real 前台真输入回退（移动物理光标/改焦点，须先取得用户同意）；--physical 为 pyautogui 非 Windows 回退。"""
import sys, os, json, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safety_gate, mouse_ops, virtual_mouse, real_input, hud_overlay, screenshot_verify

def _op(st, mode, dur):
    x, y, b = st.get("x", 0), st.get("y", 0), st.get("button", "left")
    op = st.get("op")
    if mode == "virtual" and virtual_mouse.supported():
        if op == "click": return virtual_mouse.click(x, y, b, st.get("double", False))
        if op == "scroll": return virtual_mouse.scroll(x, y, st.get("amount", -3))
        if op == "drag": return virtual_mouse.drag(x, y, st["ex"], st["ey"])
        if op == "move": return {"ok": True, "note": "虚拟模式无需移动光标"}
        if op == "type": return virtual_mouse.type_text(x, y, st.get("text", ""))
        if op == "key": return virtual_mouse.key_combo(x, y, st.get("combo", ""))
    if op in ("type", "key"):
        return mouse_ops.type_text(st.get("text", "")) if op == "type" else mouse_ops.press_keys(st.get("combo", ""))
    if op == "click": return mouse_ops.click(x, y, b, 2 if st.get("double") else 1, duration=dur)
    if op == "scroll": return mouse_ops.scroll(x, y, st.get("amount", -3), duration=dur)
    if op == "drag": return mouse_ops.drag(x, y, st["ex"], st["ey"], duration=dur)
    if op == "move": return mouse_ops.move(x, y, duration=dur)
    if op == "shot": return screenshot_verify.capture(label=st.get("label", "step"))
    return {"ok": False, "reason": "不支持的动作: " + str(op)}

def run(steps, mode="virtual", delay=0.15, guard=None):
    out, dur = [], 0.05 if mode in ("real", "physical") else 0.0
    n = len(steps)
    for i, st in enumerate(steps):
        g = safety_gate.check(f"{st.get('op')} {json.dumps(st, ensure_ascii=False)}")
        if not g["allowed"]:
            out.append({"step": i, "blocked": g["reason"]}); continue
        hud_overlay.show(f"[{i + 1}/{n}] {st.get('desc') or st.get('op')} ({st.get('x', '-')},{st.get('y', '-')})", ttl=max(10, (n - i) * 3))
        out.append({"step": i, **_op(st, mode, dur)})
        if guard:
            import human_gate
            hg = human_gate.check(guard)
            if hg.get("blocked"):
                out.append({"step": i, "human_gate": "stopped", "hits": hg["hits"]})
                return {"mode": mode, "steps": n, "stopped_at": i, "human_gate": hg,
                        "done": sum(1 for r in out if r.get("ok")), "results": out}
        if i < n - 1: time.sleep(delay)
    # 不自动 hide：HUD 会话行持续显示，任务整体结束时由调用方 hud_overlay.hide()
    return {"mode": mode, "steps": n, "done": sum(1 for r in out if r.get("ok")), "results": out}

if __name__ == "__main__":
    flags = [x for x in sys.argv[1:] if x.startswith("--")]; args = [x for x in sys.argv[1:] if not x.startswith("--")]
    mode = "physical" if "--physical" in flags else "real" if "--real" in flags else "virtual"
    if mode != "virtual" and not real_input.IS_WIN: mode = "physical"
    delay = float(next((f.split("=", 1)[1] for f in flags if f.startswith("--delay=")), 0.15))
    guard = next((f.split("=", 1)[1] for f in flags if f.startswith("--guard=")), None)
    try:
        src = args[0] if args else "help"
        steps = json.load(open(src, encoding="utf-8-sig")) if os.path.isfile(src) else json.loads(src)
        r = run(steps, mode, delay, guard) if isinstance(steps, list) and steps else {"error": "步骤清单为空"}
    except Exception as e: r = {"error": str(e), "help": "run <steps.json> [--virtual|--real|--physical] [--delay=0.15] [--guard=<窗口子串>]"}
    print(json.dumps(r, ensure_ascii=False, indent=2))
