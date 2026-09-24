#!/usr/bin/env python3
"""learn.py — 学习功能：把"哪个软件在哪、用什么通道打开、坐标/窗口特征"沉淀为本地经验，
操作前 get 召回（免重复探索），成功后 put 回写。缓存优先写 <SMS_HOME>/tmp/safe-mouse-automation/
learn.json（向 SMS 临时目录开放；SMS_HOME 解析同 SMS：env > %LOCALAPPDATA%\\SMS），
不可写时回退 SAFE_MOUSE_CACHE/learn.json；绝不落 skill 目录。"""
import sys, os, json, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def sms_home():
    if os.environ.get("SMS_HOME"): return os.environ["SMS_HOME"]
    la = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(la, "SMS")

def store_dir():
    d = os.path.join(sms_home(), "tmp", "safe-mouse-automation")
    try:
        os.makedirs(d, exist_ok=True); return d
    except Exception:
        base = os.environ.get("SAFE_MOUSE_CACHE") or os.path.join(
            os.environ.get("LOCALAPPDATA", "~"), "safe-mouse-automation")
        os.makedirs(base, exist_ok=True); return base

def path(): return os.path.join(store_dir(), "learn.json")

def load():
    try: return json.load(open(path(), encoding="utf-8"))
    except Exception: return {}

def save(d):
    json.dump(d, open(path(), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def put(app, **kv):
    d = load(); e = d.setdefault(app, {}); e.update(kv)
    e["updated"] = time.strftime("%Y-%m-%d %H:%M:%S"); e["hits"] = int(e.get("hits", 0))
    save(d); return {"ok": True, "app": app, "file": path(), "fields": sorted(kv)}

def get(app=None):
    d = load()
    if app is None: return {"apps": sorted(d), "file": path()}
    e = d.get(app)
    if e: e["hits"] = int(e.get("hits", 0)) + 1; save(d)
    return e or {"miss": app}

def note(app, text):
    """追加一条经验备注（如"开始菜单是UWP，PostMessage无效，走桌面图标"）。"""
    d = load(); e = d.setdefault(app, {}); notes = e.setdefault("notes", [])
    if text not in notes: notes.append(text)
    e["updated"] = time.strftime("%Y-%m-%d %H:%M:%S"); save(d)
    return {"ok": True, "app": app, "notes": len(notes)}

def op(app, action, spec):
    """记录某应用某操作的学习成果：op foobar "播放/暂停" '{"via":"app_ops.act","element":"播放"}'"""
    d = load(); e = d.setdefault(app, {}); o = e.setdefault("ops", {})
    o[action] = spec; e["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save(d); return {"ok": True, "app": app, "action": action, "ops": len(o)}

if __name__ == "__main__":
    a = [s for s in sys.argv[1:] if not s.startswith("--")]; cmd = a[0] if a else "help"
    try:
        if cmd == "put":
            js = a[2] if len(a) > 2 else "{}"
            if js.startswith("@"): js = open(js[1:], encoding="utf-8").read()
            r = put(a[1], **json.loads(js)) if len(a) > 1 else {"error": "需要 app"}
        elif cmd == "get": r = get(a[1] if len(a) > 1 else None)
        elif cmd == "op":
            js = a[3] if len(a) > 3 else "{}"
            if js.startswith("@"): js = open(js[1:], encoding="utf-8").read()
            r = op(a[1], a[2], json.loads(js)) if len(a) > 2 else {"error": "需要 app action json"}
        elif cmd == "ops":
            e = load().get(a[1], {}) if len(a) > 1 else {}
            r = {"app": a[1] if len(a) > 1 else None, "ops": e.get("ops", {})}
        elif cmd == "note": r = note(a[1], a[2]) if len(a) > 2 else {"error": "需要 app 与 文本"}
        elif cmd == "del":
            d = load(); d.pop(a[1], None); save(d); r = {"ok": True, "removed": a[1]}
        else: r = {"help": "put <app> <json|@file> | get [app] | op <app> <动作> <json|@file> | ops <app> | note <app> <文本> | del <app>", "file": path()}
    except Exception as e: r = {"error": str(e)}
    print(json.dumps(r, ensure_ascii=False, indent=2))
