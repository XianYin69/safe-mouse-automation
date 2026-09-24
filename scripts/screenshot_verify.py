#!/usr/bin/env python3
"""screenshot_verify.py — 截图捕获与比对；缓存一律写用户缓存目录，绝不写入 skill 目录。"""
import sys, os, time, json
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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
    img = ImageGrab.grab(bbox=region, all_screens=True) if region else ImageGrab.grab(all_screens=True)
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

def capture_window(title_part, label=""):
    """PrintWindow 抓取指定标题子串的可见顶层窗口——不激活、不置顶、被遮挡也能截，零前台打扰。"""
    if sys.platform != "win32": return {"error": "仅 Windows 支持窗口抓取"}
    import ctypes
    from ctypes import wintypes
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    found = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1)
                if title_part in b.value: found.append(h)
        return True
    u.EnumWindows(CB(cb), 0)
    if not found: return {"error": f"未找到含“{title_part}”的可见窗口"}
    h = found[0]
    class RECT(ctypes.Structure): _fields_ = [("l", wintypes.LONG), ("t", wintypes.LONG), ("r", wintypes.LONG), ("b", wintypes.LONG)]
    rc = RECT(); u.GetWindowRect(h, ctypes.byref(rc))
    w, ht = rc.r - rc.l, rc.b - rc.t
    if w < 80 or ht < 80: return {"error": "窗口过小或已最小化"}
    hdc = u.GetWindowDC(h); mem = g.CreateCompatibleDC(hdc); bmp = g.CreateCompatibleBitmap(hdc, w, ht)
    g.SelectObject(mem, bmp)
    ok = u.PrintWindow(h, mem, 2)  # PW_RENDERFULLCONTENT：Chromium 必须
    class BI(ctypes.Structure):
        _fields_ = [("s", wintypes.DWORD), ("w", wintypes.LONG), ("h", wintypes.LONG), ("p", wintypes.WORD),
                    ("b", wintypes.WORD), ("c", wintypes.DWORD), ("i", wintypes.DWORD), ("x", wintypes.LONG),
                    ("y", wintypes.LONG), ("u", wintypes.DWORD), ("m", wintypes.DWORD)]
    bmi = BI(40, w, -ht, 1, 32, 0, 0, 0, 0, 0, 0); buf = ctypes.create_string_buffer(w * ht * 4)
    got = g.GetDIBits(mem, bmp, 0, ht, buf, ctypes.byref(bmi), 0)
    g.DeleteObject(bmp); g.DeleteDC(mem); u.ReleaseDC(h, hdc)
    if not (ok and got): return {"error": "PrintWindow 失败（窗口可能尚未渲染，稍后重试）"}
    try:
        from PIL import Image
    except ImportError:
        return {"error": "Pillow 未安装，运行: pip install Pillow"}
    img = Image.frombuffer("RGBA", (w, ht), buf, "raw", "BGRA", 0, 1).convert("RGB")
    path = os.path.join(ensure_dir(), f"{label or title_part}_{time.strftime('%H%M%S')}.png")
    img.save(path); return {"path": path, "size": img.size, "hwnd": h}

if __name__ == "__main__":
    args = sys.argv[1:]; cmd = args[0] if args else "help"
    if cmd == "capture": r = capture(label=args[1] if len(args) > 1 else "")
    elif cmd == "window": r = capture_window(args[1], args[2] if len(args) > 2 else "") if len(args) > 1 else {"error": "需要标题子串"}
    elif cmd == "compare": r = compare(args[1], args[2]) if len(args) > 2 else {"error": "需要两张图片路径"}
    elif cmd == "dir": r = {"dir": ensure_dir()}
    else: r = {"help": "capture [label] | window <标题子串> [label] | compare <a> <b> | dir"}
    print(json.dumps(r, ensure_ascii=False, indent=2))
