#!/usr/bin/env python3
"""screenshot_verify.py — 截图捕获与比对：操作前后各存一张，支持区域截图与像素差异检测。"""
import sys, os, time, json

def ensure_dir(workdir):
    d = os.path.join(workdir, "tmp", "screenshots")
    os.makedirs(d, exist_ok=True)
    return d

def capture(workdir=None, region=None, label=""):
    """截全屏或区域；返回保存路径。"""
    try:
        from PIL import ImageGrab
    except ImportError:
        return {"error": "Pillow 未安装，运行: pip install Pillow"}
    d = ensure_dir(workdir or os.getcwd())
    ts = time.strftime("%H%M%S")
    name = f"{label or 'screen'}_{ts}.png" if label else f"screen_{ts}.png"
    path = os.path.join(d, name)
    img = ImageGrab.grab(bbox=region) if region else ImageGrab.grab()
    img.save(path)
    return {"path": path, "size": img.size}

def compare(path_a, path_b, threshold=0.95):
    """比对两张截图相似度，返回差异比与是否通过。"""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return {"error": "Pillow 未安装"}
    a, b = Image.open(path_a), Image.open(path_b)
    if a.size != b.size:
        return {"error": "尺寸不一致", "a": a.size, "b": b.size}
    diff = ImageChops.difference(a, b)
    bbox = diff.getbbox()
    import itertools
    hist = diff.histogram()
    total = sum(hist)
    identical = sum(hist[0::256])
    ratio = identical / total if total else 1.0
    return {"similarity": round(ratio, 4), "changed": ratio < threshold,
            "diff_bbox": bbox, "passed": ratio >= threshold}

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cmd = args[0] if args else "help"
    if cmd == "capture":
        r = capture(label=args[1] if len(args) > 1 else "")
    elif cmd == "compare":
        r = compare(args[1], args[2]) if len(args) > 2 else {"error": "需要两张图片路径"}
    else:
        r = {"help": "capture [label] | compare <a> <b>"}
    print(json.dumps(r, ensure_ascii=False, indent=2))
