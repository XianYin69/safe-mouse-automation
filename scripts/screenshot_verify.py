#!/usr/bin/env python3
"""screenshot_verify.py — 截图捕获与比对；缓存一律写用户缓存目录，绝不写入 skill 目录。"""
import sys, os, time, json

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def cache_base():
    if os.environ.get("SAFE_MOUSE_CACHE"): return os.environ["SAFE_MOUSE_CACHE"]
    if os.name == "nt":
        return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "safe-mouse-automation")
    return os.path.expanduser("~/Library/Caches/safe-mouse-automation" if sys.platform == "darwin"
                              else "~/.cache/safe-mouse-automation")

def ensure_dir(sub="screenshots"):
    d = os.path.join(cache_base(), sub); root = os.path.realpath(SKILL_ROOT); real = os.path.realpath(d)
    if real == root or real.startswith(root + os.sep):
        raise SystemExit("拒绝写入：缓存文件不得写入 skill 目录，请检查 SAFE_MOUSE_CACHE")
    os.makedirs(d, exist_ok=True); return d

def capture(region=None, label=""):
    try:
        from PIL import ImageGrab
    except ImportError:
        return {"error": "Pillow 未安装，运行: pip install Pillow"}
    path = os.path.join(ensure_dir(), f"{label or 'screen'}_{time.strftime('%H%M%S')}.png")
    img = ImageGrab.grab(bbox=region) if region else ImageGrab.grab()
    img.save(path); return {"path": path, "size": img.size}

def compare(path_a, path_b, threshold=0.95):
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return {"error": "Pillow 未安装，运行: pip install Pillow"}
    a, b = Image.open(path_a), Image.open(path_b)
    if a.size != b.size: return {"error": "尺寸不一致", "a": a.size, "b": b.size}
    hist = ImageChops.difference(a, b).histogram()
    total = sum(hist); ratio = sum(hist[0::256]) / total if total else 1.0
    return {"similarity": round(ratio, 4), "changed": ratio < threshold, "passed": ratio >= threshold}

if __name__ == "__main__":
    args = sys.argv[1:]; cmd = args[0] if args else "help"
    if cmd == "capture": r = capture(label=args[1] if len(args) > 1 else "")
    elif cmd == "compare": r = compare(args[1], args[2]) if len(args) > 2 else {"error": "需要两张图片路径"}
    elif cmd == "dir": r = {"dir": ensure_dir()}
    else: r = {"help": "capture [label] | compare <a> <b> | dir"}
    print(json.dumps(r, ensure_ascii=False, indent=2))
