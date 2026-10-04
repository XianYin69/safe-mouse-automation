#!/usr/bin/env python3
"""clip_ops.py — 纯 ctypes 剪贴板读/写/快照还原（不激活窗口、不抢焦点、不动物理光标）。

为什么需要它：本技能此前**全量 grep 无任何剪贴板代码**，「后台点击 → Ctrl+A/Ctrl+C → 读回」
这条取文本链路是断的（Chromium/Electron 忽略 PostMessage、UIA 又拿不全正文时，
剪贴板是唯一非像素、非前台的取数通道）。

红线：
- 只用 user32/kernel32（OpenClipboard / GetClipboardData / SetClipboardData / GlobalAlloc…），
  **绝不**借道 powershell / clip.exe / Get-Clipboard / Set-Clipboard（属"任意命令执行"）。
- 读之前先 snapshot() 用户旧内容，取完必须 restore() —— 用户剪贴板原样归还。
- 格式不可用 / 被别的进程占用 / 延迟渲染取不到数据 → 如实返回 {"error":...}，绝不抛栈崩溃。
- OpenClipboard(NULL)：不关联任何窗口，因此不会创建或切换前台窗口。
- 快照缓存落 %LOCALAPPDATA%\\safe-mouse-automation\\clip\\，**绝不写 skill 目录**。

CLI：
  python clip_ops.py list                     # 当前剪贴板有哪些格式
  python clip_ops.py read [CF_UNICODETEXT|CF_HTML|CF_DIB]
  python clip_ops.py write <文本>              # 写文本（自动先快照，便于 restore last）
  python clip_ops.py snapshot [label]         # 快照 → {"id":...}
  python clip_ops.py restore <id|last>        # 还原（并删除该快照）
  python clip_ops.py drop <id|last>           # 丢弃快照不还原
  python clip_ops.py probe                    # 自测：快照→写→读→还原
"""
import sys, os, json, time, base64, ctypes
from ctypes import wintypes

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13

_std_names = {1: "CF_TEXT", 2: "CF_BITMAP", 3: "CF_METAFILEPICT", 7: "CF_OEMTEXT",
              8: "CF_DIB", 9: "CF_DIF", 10: "CF_TIFF", 11: "CF_SYLK",
              13: "CF_UNICODETEXT", 14: "CF_ENHMETAFILE", 15: "CF_HDROP",
              16: "CF_LOCALE", 17: "CF_DIBV5"}
_alias = {"CF_TEXT": 1, "CF_BITMAP": 2, "CF_DIB": 8, "CF_DIBV5": 17, "CF_HDROP": 15,
          "CF_OEMTEXT": 7, "CF_LOCALE": 16, "CF_UNICODETEXT": CF_UNICODETEXT,
          "CF_RTF": 0xC0AC, "TEXT": CF_UNICODETEXT}
_html_id = [None]


class ClipError(RuntimeError):
    pass


def fmt_id(name):
    """格式名 → 剪贴板格式 id（自定义格式走 RegisterClipboardFormatW，取不到返回 None）。"""
    n = (name or "CF_UNICODETEXT").upper()
    if n in _alias:
        return _alias[n]
    if n in ("CF_HTML", "HTML", "HTML FORMAT"):
        if _html_id[0] is None:
            _html_id[0] = user32.RegisterClipboardFormatW("HTML Format") or 0
        return _html_id[0] or None
    probe = n[3:] if n.startswith("CF_") else n
    got = user32.RegisterClipboardFormatW(probe)
    return got or None


user32.OpenClipboard.restype = ctypes.c_bool
user32.IsClipboardFormatAvailable.restype = ctypes.c_bool
user32.EnumClipboardFormats.argtypes = [ctypes.c_uint]
user32.EnumClipboardFormats.restype = ctypes.c_uint
user32.GetClipboardFormatNameW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClipboardFormatNameW.restype = ctypes.c_int
user32.GetClipboardData.argtypes = [ctypes.c_uint]
user32.GetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.EmptyClipboard.restype = ctypes.c_bool
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = ctypes.c_uint
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.restype = ctypes.c_bool
kernel32.GetLastError.restype = ctypes.c_ulong


def _open():
    if not user32.OpenClipboard(None):
        raise ClipError("OpenClipboard 失败 err=%d（剪贴板被别的进程占用）"
                        % kernel32.GetLastError())


def _close():
    user32.CloseClipboard()


def _locked(fn, tries=12, sleep=0.05):
    """瞬时占用：有限重试；仍失败抛 ClipError 由调用方转成 error 字段。"""
    last = None
    for _ in range(int(tries)):
        try:
            return fn()
        except ClipError as e:
            last = e
            time.sleep(sleep)
    raise last


def available_formats():
    """只读：列出当前剪贴板全部格式（含自定义格式名）。"""
    def go():
        _open()
        try:
            out = []; f = 0
            while True:
                f = user32.EnumClipboardFormats(f)
                if not f:
                    break
                buf = ctypes.create_unicode_buffer(256)
                n = user32.GetClipboardFormatNameW(f, buf, 255)
                out.append({"id": f, "name": buf.value if n else _std_names.get(f, "CF_%d" % f)})
            return {"ok": True, "formats": out}
        finally:
            _close()
    try:
        return _locked(go)
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}


def _grab(fid):
    def go():
        if not user32.IsClipboardFormatAvailable(fid):
            raise ClipError("格式不可用: id=%d" % fid)
        _open()
        try:
            h = user32.GetClipboardData(fid)
            if not h:
                raise ClipError("GetClipboardData=NULL err=%d（延迟渲染源已失效？）"
                                % kernel32.GetLastError())
            size = kernel32.GlobalSize(h)
            if not size:
                raise ClipError("GlobalSize=0（空数据）")
            p = kernel32.GlobalLock(h)
            if not p:
                raise ClipError("GlobalLock 失败 err=%d" % kernel32.GetLastError())
            try:
                return ctypes.string_at(p, size)
            finally:
                kernel32.GlobalUnlock(h)
        finally:
            _close()
    return _locked(go)


def read(fmt="CF_UNICODETEXT"):
    """读某格式：文本→text，二进制→b64。不可用/取不到 → {"error":...}，绝不抛栈。"""
    fid = fmt_id(fmt)
    if not fid:
        return {"error": "未知剪贴板格式: %s" % fmt}
    try:
        raw = _grab(fid)
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}
    if fid == CF_UNICODETEXT:
        txt = raw.decode("utf-16-le", "replace").rstrip("\x00")
        return {"ok": True, "format": "CF_UNICODETEXT", "chars": len(txt),
                "bytes": len(raw), "text": txt}
    if fid == fmt_id("CF_HTML"):
        txt = raw.decode("utf-8", "replace")
        return {"ok": True, "format": "HTML Format", "chars": len(txt),
                "bytes": len(raw), "text": txt}
    b64 = base64.b64encode(raw).decode()
    return {"ok": True, "format": "id=%d" % fid, "bytes": len(raw), "b64": b64}


def _set_many(pairs):
    """一次 OpenClipboard + EmptyClipboard 写多个格式（还原快照时保住全部格式）。
    SetClipboardData 成功后所有权归系统 —— 绝不再 GlobalFree。"""
    def go():
        _open()
        try:
            if not user32.EmptyClipboard():
                raise ClipError("EmptyClipboard 失败 err=%d" % kernel32.GetLastError())
            done = []
            for fid, data in pairs:
                if not data:
                    continue
                h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                if not h:
                    raise ClipError("GlobalAlloc(%d) 失败" % len(data))
                p = kernel32.GlobalLock(h)
                if not p:
                    kernel32.GlobalFree(h)
                    raise ClipError("GlobalLock 失败 err=%d" % kernel32.GetLastError())
                ctypes.memmove(p, data, len(data))
                kernel32.GlobalUnlock(h)
                if not user32.SetClipboardData(fid, h):
                    kernel32.GlobalFree(h)
                    raise ClipError("SetClipboardData(id=%d) 失败 err=%d"
                                    % (fid, kernel32.GetLastError()))
                done.append(fid)
            return done
        finally:
            _close()
    return _locked(go)


def write_text(text):
    """写 CF_UNICODETEXT（调用方应先 snapshot()，之后 restore() 归还用户内容）。"""
    data = (text or "").encode("utf-16-le") + b"\x00\x00"
    try:
        _set_many([(CF_UNICODETEXT, data)])
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}
    return {"ok": True, "chars": len(text or ""), "bytes": len(data)}


# CF_BITMAP/CF_METAFILEPICT/CF_ENHMETAFILE 是 GDI 句柄而非 HGLOBAL，不可 GlobalLock → 跳过
_HANDLE_FMTS = {2, 3, 14}
_SNAP_CAP = 8 * 1024 * 1024


def _cache_root():
    d = os.environ.get("SAFE_MOUSE_CACHE")
    if not d:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "safe-mouse-automation")
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.normcase(os.path.abspath(d)).startswith(os.path.normcase(skill_root)):
        raise ClipError("缓存目录不得落在 skill 目录内: %s" % d)
    os.makedirs(os.path.join(d, "clip"), exist_ok=True)
    return d


def _snap_file():
    return os.path.join(_cache_root(), "clip", "snapshots.json")


def _snap_load():
    try:
        with open(_snap_file(), encoding="utf-8") as f:
            db = json.load(f)
        return db if isinstance(db, dict) else {}
    except Exception:
        return {}


def _snap_save(db):
    with open(_snap_file(), "w", encoding="utf-8") as f:
        json.dump(db, f)


def snapshot(label=""):
    """把用户当前剪贴板原样存进缓存，返回快照 id。取完数据必须 restore()。"""
    keep = {}; skipped = []

    def go():
        _open()
        try:
            ids = []; f = 0
            while True:
                f = user32.EnumClipboardFormats(f)
                if not f:
                    break
                ids.append(f)
            return ids
        finally:
            _close()
    try:
        ids = _locked(go)
    except Exception as e:
        return {"error": "枚举剪贴板格式失败: %s" % e}
    total = 0
    for fid in ids:
        if fid in _HANDLE_FMTS:
            skipped.append("id=%d(handle)" % fid)
            continue
        try:
            raw = _grab(fid)
        except Exception:
            skipped.append("id=%d(取不到)" % fid)
            continue
        if total + len(raw) > _SNAP_CAP:
            skipped.append("id=%d(超容量上限)" % fid)
            continue
        total += len(raw)
        keep[str(fid)] = base64.b64encode(raw).decode()
    sid = time.strftime("%Y%m%d-%H%M%S") + "-%03d" % (int(time.time() * 1000) % 1000)
    db = _snap_load()
    db[sid] = {"label": label, "ts": time.time(), "formats": keep, "bytes": total}
    try:
        _snap_save(db)
    except Exception as e:
        return {"error": "快照写盘失败: %s" % e}
    return {"ok": True, "id": sid, "kept": sorted(keep.keys()), "bytes": total,
            "skipped": skipped, "was_empty": not keep, "file": _snap_file()}


def restore(sid="last"):
    """还原快照（并删除该条）——用户剪贴板原样归还；快照为空＝恢复成空剪贴板。"""
    db = _snap_load()
    if sid == "last":
        if not db:
            return {"error": "无快照可还原"}
        sid = max(db, key=lambda k: db[k]["ts"])
    rec = db.get(sid)
    if not rec:
        return {"error": "快照不存在: %s" % sid}
    pairs = []
    for f, b64 in (rec.get("formats") or {}).items():
        try:
            pairs.append((int(f), base64.b64decode(b64)))
        except Exception:
            continue
    try:
        done = _set_many(pairs) if pairs else _clear()
    except Exception as e:
        return {"error": "还原失败: %s" % e, "id": sid}
    db.pop(sid, None)
    try:
        _snap_save(db)
    except Exception:
        pass
    return {"ok": True, "id": sid, "restored_formats": done,
            "note": "empty" if not pairs else "restored"}


def _clear():
    def go():
        _open()
        try:
            user32.EmptyClipboard()
            return []
        finally:
            _close()
    return _locked(go)


def drop(sid="last"):
    """丢弃快照不还原（确认不需要归还时用）。"""
    db = _snap_load()
    if sid == "last" and db:
        sid = max(db, key=lambda k: db[k]["ts"])
    had = db.pop(sid, None) is not None
    try:
        _snap_save(db)
    except Exception as e:
        return {"error": str(e)}
    return {"ok": True, "dropped": sid, "existed": had}


def probe():
    """自测：快照 → 写标记 → 读回 → 还原，全程不激活窗口。"""
    mark = "__sm_clip_probe_%d__" % int(time.time())
    s = snapshot("probe")
    if not s.get("ok"):
        return {"stage": "snapshot", **s}
    before = read("CF_UNICODETEXT").get("text")
    w = write_text(mark)
    if not w.get("ok"):
        restore(s["id"]); return {"stage": "write", **w}
    r = read("CF_UNICODETEXT")
    back = restore(s["id"])
    after = read("CF_UNICODETEXT").get("text")
    return {"ok": bool(r.get("ok") and r.get("text") == mark and back.get("ok")),
            "wrote": mark, "read_back_ok": r.get("ok"), "read_chars": r.get("chars"),
            "restored_ok": back.get("ok"), "user_text_preserved": (before == after),
            "before_len": len(before or ""), "after_len": len(after or "")}


if __name__ == "__main__":
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "help"
    pos = [a for a in argv[1:] if not a.startswith("--")]
    try:
        if cmd == "list":
            r = available_formats()
        elif cmd == "read":
            r = read(pos[0] if pos else "CF_UNICODETEXT")
        elif cmd == "write":
            txt = " ".join(pos)
            auto = snapshot("auto-before-write")
            r = write_text(txt)
            if auto.get("ok"):
                r["snapshot_id"] = auto["id"]
                r["hint"] = "用完 python clip_ops.py restore %s" % auto["id"]
        elif cmd == "snapshot":
            r = snapshot(pos[0] if pos else "")
        elif cmd == "restore":
            r = restore(pos[0] if pos else "last")
        elif cmd == "drop":
            r = drop(pos[0] if pos else "last")
        elif cmd == "probe":
            r = probe()
        else:
            r = {"help": __doc__}
    except Exception as e:
        r = {"error": "%s: %s" % (type(e).__name__, e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
