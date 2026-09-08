#!/usr/bin/env python3
"""Local control dashboard for the research agent graph + trading bot.

    python scripts/agent_graph/server.py         # then open http://localhost:8787

Stdlib only. Serves a multi-page SPA (dashboard.html + app.css + app.js) and a small JSON API:
  GET  /api/state      graph state: agenda, live runs, running agents' activity
  GET  /api/control    loop control flags (paused / batch / run_requested)
  GET  /api/portfolio  Alpaca PAPER account: equity, cash, positions   (live)
  GET  /api/orders     recent Alpaca orders                            (live)
  GET  /api/history    Alpaca portfolio equity history                 (live)
  GET  /api/accounts   configured accounts (masked)
  POST /api/loop/*     pause | resume | batch | reclaim | request-run
  POST /api/task/*     add | update | delete   (edits agenda.json)

Trading endpoints are READ-ONLY against the PAPER account. Placing/cancelling live orders and adding
real-money wallets are owner-gated and intentionally NOT exposed here.
"""
import glob
import importlib.util
import json
import os
import pathlib
import re
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
AGENDA = HERE / "agenda.json"
CONTROL = HERE / "control.json"
STATIC = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript"}
WF_ROOTS = glob.glob(os.path.expanduser("~/.claude/projects/-home-anont-meme/*/subagents/workflows"))
PORT = int(os.environ.get("GRAPH_UI_PORT", "8787"))
RUNNING_WINDOW = 900.0   # 15 min: agents often block in long foreground jobs (data fetches, backtests,
                         # `until` wait-loops) and write nothing to their transcript meanwhile. A tight
                         # window wrongly flips a busy-but-quiet agent to "idle". The real done-signal is
                         # a result in the journal; the window only bounds how long we call a
                         # result-less agent "running" before assuming its workflow died.
MAX_ACTIVITY = 14
TASK_RE = re.compile(r"TASK\s+(T\w+)")
CONTROL_DEFAULT = {"paused": False, "batch": 3, "run_requested": False, "updated_at": None}

ALPACA_TRADE = "https://paper-api.alpaca.markets"
_cache = {}   # ttl cache for slow external calls


# ---------- env / alpaca ----------
def load_env():
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def alpaca(path, params=None, ttl=12):
    key = ("alpaca", path, tuple(sorted((params or {}).items())))
    now = time.time()
    if key in _cache and now - _cache[key][0] < ttl:
        return _cache[key][1]
    env = load_env()
    kid, sec = env.get("ALPACA_API_KEY_ID"), env.get("ALPACA_API_SECRET_KEY")
    if not kid or not sec:
        return {"_error": "no Alpaca keys in .env"}
    url = f"{ALPACA_TRADE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        _cache[key] = (now, data)
        return data
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_detail": e.read()[:200].decode("utf-8", "ignore")}
    except Exception as e:
        return {"_error": str(e)}


# ---------- transcript parsing (control page live view) ----------
def _blocks(obj):
    m = obj.get("message", obj)
    c = m.get("content") if isinstance(m, dict) else None
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


def _clip(s, n=200):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "…"


def parse_agent_file(path):
    task_id, role, activity = None, None, []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                for b in _blocks(obj):
                    if not isinstance(b, dict):
                        continue
                    t = b.get("type")
                    if t == "text":
                        txt = (b.get("text") or "").strip()
                        if role is None and "independent skeptic" in txt:
                            role = "verify"
                        elif role is None and "advancing one research task" in txt:
                            role = "execute"
                        if task_id is None:
                            mm = TASK_RE.search(txt)
                            if mm:
                                task_id = mm.group(1)
                        if txt and "HARD GUARDRAILS" not in txt and "independent skeptic" not in txt:
                            activity.append({"kind": "text", "text": _clip(txt, 240)})
                    elif t == "thinking":
                        th = (b.get("thinking") or "").strip()
                        if th:
                            activity.append({"kind": "think", "text": _clip(th, 240)})
                    elif t == "tool_use":
                        inp = b.get("input", {})
                        hint = inp.get("file_path") or inp.get("command") or inp.get("pattern") or inp.get("description") or ""
                        activity.append({"kind": "tool", "name": b.get("name", "?"), "text": _clip(hint, 160)})
                    elif t == "tool_result":
                        c = b.get("content")
                        if isinstance(c, list):
                            c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                        activity.append({"kind": "result", "text": _clip(c, 140)})
    except FileNotFoundError:
        pass
    return task_id, role, activity[-MAX_ACTIVITY:]


def read_run(wf_dir, full=True):
    wf = pathlib.Path(wf_dir)
    journal = {}
    jpath = wf / "journal.jsonl"
    if jpath.exists():
        for line in jpath.read_text().splitlines():
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("type") == "result":
                journal[o.get("agentId")] = o.get("result")
    if not full:
        agents = []
        for aid, result in journal.items():
            role = "verify" if isinstance(result, dict) and "verdict" in result else "execute"
            agents.append({"agentId": (aid or "?")[:10], "task": (result or {}).get("id", "?"),
                           "role": role, "state": "done", "result": result, "activity": [], "touched": 0})
        return {"id": wf.name, "mtime": wf.stat().st_mtime, "agents": agents}
    agents = []
    now = time.time()
    for f in sorted(glob.glob(str(wf / "agent-*.jsonl"))):
        if f.endswith(".meta.json"):
            continue
        aid = pathlib.Path(f).stem.replace("agent-", "")
        task_id, role, activity = parse_agent_file(f)
        result = journal.get(aid)
        if result is None:
            for k, v in journal.items():
                if k.startswith(aid) or aid.startswith(k):
                    result = v
                    break
        if role is None and isinstance(result, dict):
            role = "verify" if "verdict" in result else "execute"
        if task_id is None and isinstance(result, dict):
            task_id = result.get("id")
        touched = os.path.getmtime(f)
        running = result is None and (now - touched) < RUNNING_WINDOW
        agents.append({"agentId": aid[:10], "task": task_id or "?", "role": role or "execute",
                       "state": "running" if running else ("done" if result is not None else "idle"),
                       "result": result, "activity": activity, "touched": touched})
    return {"id": wf.name, "mtime": wf.stat().st_mtime, "agents": agents}


# ---------- agenda / control state ----------
def load_agenda():
    return json.loads(AGENDA.read_text()) if AGENDA.exists() else {"tasks": []}


def save_agenda(a):
    a["updated_at"] = int(time.time())
    tmp = AGENDA.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(a, indent=2) + "\n")
    tmp.replace(AGENDA)


def load_control():
    c = dict(CONTROL_DEFAULT)
    if CONTROL.exists():
        try:
            c.update(json.loads(CONTROL.read_text()))
        except Exception:
            pass
    return c


def save_control(c):
    c["updated_at"] = int(time.time())
    tmp = CONTROL.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(c, indent=2) + "\n")
    tmp.replace(CONTROL)


def build_state():
    agenda = load_agenda()
    runs, dirs = [], []
    for r in WF_ROOTS:
        dirs += glob.glob(os.path.join(r, "wf_*"))
    def _live(d):
        now = time.time()
        for f in glob.glob(os.path.join(d, "agent-*.jsonl")):
            if f.endswith(".meta.json"):
                continue
            try:
                if now - os.path.getmtime(f) < RUNNING_WINDOW:
                    return True
            except OSError:
                pass
        return False

    for i, d in enumerate(sorted(dirs, key=os.path.getmtime, reverse=True)[:8]):
        try:
            # Full-parse the 2 newest AND any run with a recently-touched agent (i.e. still live),
            # so a just-completed run can never hide a currently-running one.
            runs.append(read_run(d, full=(i < 2 or _live(d))))
        except Exception as e:
            runs.append({"id": os.path.basename(d), "error": str(e), "agents": []})
    any_running = any(a["state"] == "running" for run in runs for a in run["agents"])
    fwd = ROOT / "research" / "trading_bot" / "FORWARD_STATUS.txt"
    forward_test = fwd.read_text().strip() if fwd.exists() else None
    return {"agenda": agenda, "goal": agenda.get("goal", ""), "model": "Opus 5.0",
            "control": load_control(), "notify": notify_status(), "forward_test": forward_test,
            "runs": runs, "any_running": any_running, "generated_at": time.time()}


# ---------- trading views ----------
def portfolio_view():
    acct = alpaca("/v2/account")
    pos = alpaca("/v2/positions")
    connected = "_error" not in acct
    return {"connected": connected, "account": acct if connected else {"_error": acct.get("_error")},
            "positions": pos if isinstance(pos, list) else [], "error": acct.get("_error")}


def notify_status():
    env = load_env()
    return {"configured": bool(env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID")),
            "has_token": bool(env.get("TELEGRAM_BOT_TOKEN")), "has_chat": bool(env.get("TELEGRAM_CHAT_ID"))}


def notify_test():
    try:
        p = ROOT / "scripts" / "operator_notify.py"
        spec = importlib.util.spec_from_file_location("operator_notify", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.load_env()
        ok = m.send("Agent graph — test notification. Telegram wiring works. ✅")
        return {"ok": bool(ok)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:180]}


def accounts_view():
    env = load_env()
    def mask(v):
        return (v[:4] + "…" + v[-3:]) if v and len(v) > 9 else ("set" if v else None)
    acct = alpaca("/v2/account")
    alp_ok = "_error" not in acct
    out = [{
        "name": "Alpaca (paper)", "kind": "equities/ETF/short", "mode": "paper",
        "id": mask(env.get("ALPACA_API_KEY_ID")), "status": "connected" if alp_ok else "error",
        "detail": (f"equity ${float(acct.get('equity',0)):,.2f}" if alp_ok else acct.get("_error", "")),
        "can_trade": True, "live": False,
    }, {
        "name": "Solana RPC", "kind": "crypto (read-only)", "mode": "read-only",
        "id": mask(env.get("SOLANA_RPC_URL")), "status": "configured" if env.get("SOLANA_RPC_URL") else "none",
        "detail": "research endpoint — no signing wallet configured", "can_trade": False, "live": False,
    }]
    return {"accounts": out}


# ---------- mutations ----------
def do_action(path, body):
    if path == "/api/loop/pause":
        c = load_control(); c["paused"] = True; save_control(c); return c
    if path == "/api/loop/resume":
        c = load_control(); c["paused"] = False; save_control(c); return c
    if path == "/api/loop/batch":
        c = load_control(); c["batch"] = max(1, int(body.get("batch", 3))); save_control(c); return c
    if path == "/api/loop/request-run":
        c = load_control(); c["run_requested"] = True; save_control(c); return c
    if path == "/api/notify/test":
        return notify_test()
    if path == "/api/loop/reclaim":
        a = load_agenda(); n = 0
        for t in a["tasks"]:
            if t["status"] == "running":
                t["status"] = "pending"; n += 1
        save_agenda(a); return {"reclaimed": n}
    if path == "/api/task/add":
        a = load_agenda()
        n = len(a["tasks"]) + 1
        a["tasks"].append({
            "id": body.get("id") or f"T{n}_new",
            "title": body.get("title", "untitled"), "kind": body.get("kind", "research"),
            "priority": int(body.get("priority", 99)), "deps": body.get("deps", []),
            "status": "pending", "why": body.get("why", ""), "acceptance": body.get("acceptance", ""),
            "guardrails": body.get("guardrails", []), "artifacts": body.get("artifacts", []),
            "result": None, "verdict": None})
        save_agenda(a); return {"added": a["tasks"][-1]["id"]}
    if path == "/api/task/approve":
        a = load_agenda(); tid = body.get("id"); hit = None
        for t in a["tasks"]:
            if t["id"] == tid:
                t["status"] = "approved"; t["approved_at"] = int(time.time()); hit = t["id"]
        # Report what this unblocks: pending tasks whose deps are now all satisfied.
        done = {t["id"] for t in a["tasks"] if t["status"] in ("verified", "approved")}
        unblocked = [t["id"] for t in a["tasks"]
                     if t["status"] == "pending" and all(d in done for d in t.get("deps", []))]
        save_agenda(a)
        if unblocked:                       # nudge the loop to pick them up next tick
            c = load_control(); c["run_requested"] = True; save_control(c)
        return {"approved": hit, "unblocked": unblocked}
    if path == "/api/task/run":
        # Launch a not-yet-run task: set it pending and flag a run so the loop dispatches it.
        a = load_agenda(); tid = body.get("id"); hit = None
        for t in a["tasks"]:
            if t["id"] == tid:
                t["status"] = "pending"; t.pop("started_at", None); hit = t["id"]
        save_agenda(a)
        c = load_control(); c["run_requested"] = True; save_control(c)
        return {"queued": hit, "note": "set to pending; the loop will dispatch it on the next tick"}
    if path == "/api/task/update":
        a = load_agenda(); tid = body.get("id"); hit = None
        for t in a["tasks"]:
            if t["id"] == tid:
                if "priority" in body: t["priority"] = int(body["priority"])
                if "status" in body: t["status"] = body["status"]
                hit = t["id"]
        save_agenda(a); return {"updated": hit}
    if path == "/api/task/delete":
        a = load_agenda(); tid = body.get("id")
        before = len(a["tasks"])
        a["tasks"] = [t for t in a["tasks"] if t["id"] != tid]
        save_agenda(a); return {"deleted": before - len(a["tasks"])}
    return {"_error": f"unknown action {path}"}


# ---------- http ----------
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name):
        p = HERE / name
        if not p.exists() or p.parent != HERE:
            return self._json({"_error": "not found"}, 404)
        body = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", STATIC.get(p.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/state":
                return self._json(build_state())
            if path == "/api/control":
                return self._json(load_control())
            if path == "/api/portfolio":
                return self._json(portfolio_view())
            if path == "/api/orders":
                return self._json({"orders": alpaca("/v2/orders", {"status": "all", "limit": 50})})
            if path == "/api/history":
                return self._json(alpaca("/v2/account/portfolio/history", {"period": "1M", "timeframe": "1D"}))
            if path == "/api/accounts":
                return self._json(accounts_view())
            if path == "/api/notify/status":
                return self._json(notify_status())
            if path in ("/", "/index.html"):
                return self._file("dashboard.html")
            if path.lstrip("/") in ("app.css", "app.js", "dashboard.html"):
                return self._file(path.lstrip("/"))
            return self._json({"_error": "not found"}, 404)
        except Exception as e:
            return self._json({"_error": str(e)}, 500)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except Exception:
            body = {}
        try:
            return self._json(do_action(path, body))
        except Exception as e:
            return self._json({"_error": str(e)}, 500)


if __name__ == "__main__":
    print(f"agent-graph control dashboard -> http://localhost:{PORT}  (Ctrl-C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
