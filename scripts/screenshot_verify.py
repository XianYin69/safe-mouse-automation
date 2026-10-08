#!/usr/bin/env python3
"""screenshot_verify.py — 截图与视觉验证的**纯委托层**：一律委托 screen-vision 技能。

已废除的自研实现：Win32 GDI 窗口 DC 抓取整段、像素直方图差异比对、屏幕矩形全屏抓取。
本模块只做路径解析、子进程委托与算术胶水，不含任何视觉代码，也不直接取像。
缓存一律写用户缓存目录，绝不写入 skill 目录。
"""
import sys, os, time, json, subprocess
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = "screen-vision"
MISSING = "screen-vision 未安装或路径不对，请设 SCREEN_VISION_HOME"
OBJ_PROMPT = "列出界面上的可交互元素（按钮/输入框/文本/图标等）及其位置与用途"


def cache_base():
    if os.environ.get("SAFE_MOUSE_CACHE"): return os.environ["SAFE_MOUSE_CACHE"]
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(base, "safe-mouse-automation")
    return os.path.expanduser("~/Library/Caches/safe-mouse-automation" if sys.platform == "darwin"
                              else "~/.cache/safe-mouse-automation")

def ensure_dir(sub="screenshots"):
    d = os.path.join(cache_base(), sub)
    root = os.path.realpath(SKILL_ROOT); real = os.path.realpath(d)
    if real == root or real.startswith(root + os.sep):
        raise SystemExit("拒绝写入：缓存文件不得写入 skill 目录，请检查 SAFE_MOUSE_CACHE")
    os.makedirs(d, exist_ok=True); return d


def sv_scripts():
    """screen-vision 脚本目录解析：env SCREEN_VISION_HOME（技能根或 scripts 目录皆可）
    > C:/Users/User/AppData/Local/SMS/skills/screen-vision/scripts。找不到返回 None——只报错，绝不自动安装、
    绝不回退自研实现。"""
    env = os.environ.get("SCREEN_VISION_HOME")
    if env:
        cands = [os.path.join(env, "scripts"), env]  # 显式设了就以它为准，设错要暴露而非静默回退
    else:
        cands = [os.path.join(os.environ.get("SMS_SKILLS") or os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "SMS", "skills"),
                              "screen-vision", "scripts")]
    for c in cands:
        need = ("sw.py", "describe.py", "recognize.py")
        if all(os.path.isfile(os.path.join(c, n)) for n in need):
            return c
    return None


def sv_call(script, argv):
    """委托一个 screen-vision 脚本：返回 (ok, payload)。
    rc≠0 或 stdout 非 JSON → 原样透传 stderr 文本，不重试、不猜。"""
    d = sv_scripts()
    if not d: return False, {"error": MISSING}
    cmd = [sys.executable, "-B", os.path.join(d, script)] + [str(x) for x in argv]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        return False, {"error": f"调用 screen-vision 失败: {e}"}
    if p.returncode != 0:
        err = (p.stderr or "").strip() or f"screen-vision {script} 退出码 {p.returncode}"
        return False, {"error": err}
    try:
        return True, json.loads(p.stdout)
    except ValueError:
        return False, {"error": "screen-vision 输出非 JSON: " + (p.stdout or "")[:400]}


def _out_path(stem):
    return os.path.join(ensure_dir(), f"{stem}_{time.strftime('%H%M%S')}.png")


def _shot_result(r, extra=None):
    out = {"path": r.get("image"), "size": tuple(r.get("size") or ()), "window": r.get("window"),
           "engine": ENGINE}
    if extra: out.update(extra)
    return out

MIN_W, MIN_H = 200, 200


def _big_enough(row):
    box = row.get("box") or [0, 0, 0, 0]
    return box[2] - box[0] >= MIN_W and box[3] - box[1] >= MIN_H


def top_visible_index():
    """z-order 最靠前的「可截应用窗口」下标。pygetwindow 会把 1x1 壳层窗口与「开始/任务栏」
    排在最前，直接 --index 0 会被 screen-vision 以「尺寸异常」拒绝或截到无关小控件，
    故按其 list 的 visible_state + box 取首个 >= 200x200 的可见窗口；退化再取首个 visible，
    仍无则回 0。数据全部来自 screen-vision 自身枚举，本层不猜、不重试。"""
    ok, rows = sv_call("sw.py", ["list"])
    if not ok or not isinstance(rows, list): return 0
    for row in rows:
        if row.get("visible_state") == "visible" and _big_enough(row): return row.get("index", 0)
    for row in rows:
        if row.get("visible_state") == "visible": return row.get("index", 0)
    return 0


def capture(region=None, label="", index=None):
    """向后兼容入口：全屏抓取已废除，委托 sw.py capture --index N（默认＝z-order 顶层可用窗口）。
    screen-vision 拒绝该窗口时原样透传其报错，本层不重试、不回退自研实现。"""
    if region is not None:
        return {"error": "region 截取已废除，改用 window <标题子串>"}
    idx = top_visible_index() if index is None else index
    ok, r = sv_call("sw.py", ["capture", "--index", str(idx), "--out", _out_path(label or "top")])
    if not ok: return r
    return _shot_result(r, {"note": "全屏截取已废除，现为顶层窗口截取；需指定目标请用 window <标题>"})


def capture_window(title_part, label=""):
    """委托 sw.py capture --title 子串——截的是屏幕矩形像素（非旧自研的窗口 DC 渲染抓取）：
    被遮挡会截进遮挡内容，需抗遮挡请走 browser_cdp.py shot。"""
    if not title_part: return {"error": "需要标题子串"}
    ok, r = sv_call("sw.py", ["capture", "--title", title_part,
                              "--out", _out_path(label or title_part)])
    if not ok: return r
    return _shot_result(r, {"note": "屏幕矩形截取：被遮挡会截进遮挡内容，可先 SW_SHOWNOACTIVATE 恢复再截"})


def _channels(path):
    """委托 describe.py 取像素通道统计块（mean_rgb / gray_mean / contrast / gray_hist_8）。"""
    ok, r = sv_call("describe.py", ["--image", path])
    if not ok: return False, r
    ch = r.get("channels")
    if not ch: return False, {"error": "describe.py 未返回 channels 块"}
    return True, ch


def _num_dist(a, b, scale):
    """两个标量的归一化距离（0..1）。"""
    try:
        return min(1.0, abs(float(a) - float(b)) / scale)
    except (TypeError, ValueError):
        return 1.0


def _vec_dist(a, b, scale):
    """等长数值序列逐元素绝对差均值 / scale（0..1）。"""
    if not a or not b or len(a) != len(b): return 1.0
    return min(1.0, sum(abs(float(x) - float(y)) for x, y in zip(a, b)) / len(a) / scale)


def _hist_dist(a, b):
    """两个 8 分箱占比向量的 L1 距离 /2（0..1）。"""
    if not a or not b or len(a) != len(b): return 1.0
    return min(1.0, sum(abs(float(x) - float(y)) for x, y in zip(a, b)) / 2.0)


def compare(path_a, path_b, threshold=0.95):
    """前后态比对：委托 describe.py 的像素通道统计做归一化数值距离——纯算术胶水，
    本模块不 import PIL、不做任何视觉运算。"""
    for p in (path_a, path_b):
        if not os.path.isfile(p): return {"error": f"图片不存在: {p}"}
    ok, ca = _channels(path_a)
    if not ok: return ca
    ok, cb = _channels(path_b)
    if not ok: return cb
    d = {"rgb": round(_vec_dist(ca.get("mean_rgb"), cb.get("mean_rgb"), 255.0), 4),
         "gray_mean": round(_num_dist(ca.get("gray_mean"), cb.get("gray_mean"), 255.0), 4),
         "gray_std": round(_num_dist(ca.get("contrast"), cb.get("contrast"), 128.0), 4),
         "bins": round(_hist_dist(ca.get("gray_hist_8"), cb.get("gray_hist_8")), 4)}
    sim = round(1.0 - (0.35 * d["rgb"] + 0.20 * d["gray_mean"]
                       + 0.15 * d["gray_std"] + 0.30 * d["bins"]), 4)
    return {"similarity": sim, "changed": sim < threshold, "passed": sim >= threshold,
            "threshold": threshold, "delta": d, "engine": "screen-vision/describe"}


def ask(target, prompt, structured=False):
    """委托 recognize.py ask：target 为已存在的文件则 --image，否则按窗口标题子串 --title。
    structured=True 时并入契约 v2（objects[].screen_xy 为屏幕物理像素绝对坐标，可直接喂
    virtual_mouse 点击）。"""
    if not target or not prompt: return {"error": "需要 <标题子串|图片路径> <问题>"}
    src = ["--image", target] if os.path.isfile(target) else ["--title", target]
    argv = ["ask"] + src + ["--prompt", prompt] + (["--structured"] if structured else [])
    ok, r = sv_call("recognize.py", argv)
    if not ok: return r
    r["engine"] = "screen-vision/recognize"
    return r


def objects(target):
    """委托 recognize.py ask --structured：结构化元素清单（含 screen_xy 可点坐标）。"""
    return ask(target, OBJ_PROMPT, structured=True)


HELP = ("capture [label] [--index=N] | window <标题子串> [label] | compare <a> <b> [threshold] | "
        "ask <标题子串|图片路径> <问题> [--structured] | objects <标题子串|图片路径> | dir")

if __name__ == "__main__":
    args = sys.argv[1:]; cmd = args[0] if args else "help"
    flags = [x for x in args if x.startswith("--")]
    if cmd == "capture":
        pos = [x for x in args[1:] if not x.startswith("--")]
        idx = next((f.split("=", 1)[1] for f in flags if f.startswith("--index=")), None)
        r = capture(label=pos[0] if pos else "", index=idx)
    elif cmd == "window":
        pos = [x for x in args[1:] if not x.startswith("--")]
        r = capture_window(pos[0], pos[1] if len(pos) > 1 else "") if pos else {"error": "需要标题子串"}
    elif cmd == "compare":
        pos = [x for x in args[1:] if not x.startswith("--")]
        r = compare(pos[0], pos[1], float(pos[2])) if len(pos) > 2 else \
            (compare(pos[0], pos[1]) if len(pos) > 1 else {"error": "需要两张图片路径"})
    elif cmd == "ask":
        pos = [x for x in args[1:] if not x.startswith("--")]
        r = ask(pos[0], pos[1], "--structured" in flags) if len(pos) > 1 else \
            {"error": "需要 <标题子串|图片路径> <问题>"}
    elif cmd == "objects":
        pos = [x for x in args[1:] if not x.startswith("--")]
        r = objects(pos[0]) if pos else {"error": "需要 <标题子串|图片路径>"}
    elif cmd == "dir":
        r = {"dir": ensure_dir()}
    else:
        r = {"help": HELP, "engine": ENGINE,
             "note": "视觉能力全部委托 screen-vision；自研窗口 DC 抓取与像素比对已废除"}
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if isinstance(r, dict) and r.get("error"): sys.exit(1)
