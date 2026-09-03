"""SCALPBOT dashboard -- :8798. Read-only view of the paper ledger."""
from __future__ import annotations
import json, time, html, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "research" / "midcap" / "scalpbot_ledger.jsonl"
CFG = ROOT / "research" / "midcap" / "scalpbot_config.json"
API = "https://frontend-api-v3.pump.fun/coins"
_cache = {"ts": 0, "px": {}}

CSS = """*{box-sizing:border-box}body{margin:0;background:#0a0d10;color:#d5dbe3;
font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.wrap{max-width:1100px;margin:0 auto;padding:20px}
h1{font-size:15px;margin:0;letter-spacing:.16em;text-transform:uppercase;color:#eef2f7}
.sub{color:#79838f;font-size:11px;margin:3px 0 18px}
.k{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:18px}
.c{background:#111619;border:1px solid #1d242b;border-radius:7px;padding:11px 13px}
.c .l{color:#6c7681;font-size:10px;letter-spacing:.11em;text-transform:uppercase}
.c .v{font-size:20px;margin-top:4px;font-variant-numeric:tabular-nums;color:#eef2f7}
.pos{color:#48c78e}.neg{color:#e06c6c}.dim{color:#6c7681}
table{width:100%;border-collapse:collapse}
th{text-align:right;color:#6c7681;font-size:10px;letter-spacing:.1em;text-transform:uppercase;
padding:7px 9px;border-bottom:1px solid #1d242b}
th:first-child,td:first-child{text-align:left}
td{text-align:right;padding:7px 9px;border-bottom:1px solid #141a1f;font-variant-numeric:tabular-nums}
.s{color:#8a939f;font-size:11px;letter-spacing:.11em;text-transform:uppercase;margin:20px 0 7px}
.warn{background:#1b1509;border:1px solid #46330f;color:#dfae52;padding:10px 13px;border-radius:6px;
margin-bottom:16px;font-size:12px}
.pill{display:inline-block;padding:1px 7px;border-radius:9px;font-size:10px;
background:#1d242b;color:#8a939f;letter-spacing:.08em}
"""

def live_px():
    if time.time() - _cache["ts"] < 40: return _cache["px"]
    px = {}
    try:
        for sort in ("market_cap", "last_trade_timestamp"):
            for i in range(6):
                req = urllib.request.Request(
                    f"{API}?offset={i*50}&limit=50&sort={sort}&order=DESC&includeNsfw=true",
                    headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=12) as r:
                    d = json.loads(r.read())
                for c in (d if isinstance(d, list) else d.get("coins") or []):
                    if c.get("mint") and c.get("usd_market_cap"):
                        px[c["mint"]] = float(c["usd_market_cap"])
    except Exception:
        pass
    if px: _cache.update(ts=time.time(), px=px)
    return _cache["px"]

def read():
    open_, closed, boot = {}, [], None
    if LEDGER.exists():
        with LEDGER.open() as f:
            for line in f:
                try: r = json.loads(line)
                except Exception: continue
                if r.get("ev") == "OPEN": open_[r["mint"]] = r
                elif r.get("ev") == "CLOSE": open_.pop(r["mint"], None); closed.append(r)
                elif r.get("ev") == "BOOT": boot = r
    return open_, closed, boot

def page():
    open_, closed, boot = read()
    cfg = json.loads(CFG.read_text()) if CFG.exists() else {}
    px = live_px()
    size = cfg.get("position_usd", 5.0); toll = cfg.get("toll_pct", 3.0)
    realised = sum(c.get("pnl_usd", 0) for c in closed)
    unreal = sum(size * (px[m] / p["entry_mcap"] - 1)
                 for m, p in open_.items() if m in px and p.get("entry_mcap"))
    wins = sum(1 for c in closed if c.get("pnl_usd", 0) > 0)
    wr = wins / len(closed) * 100 if closed else 0
    def cls(v): return "pos" if v > 0 else ("neg" if v < 0 else "dim")
    orows = ""
    for m, p in sorted(open_.items(), key=lambda kv: kv[1]["ts"]):
        cur = px.get(m); e = p.get("entry_mcap") or 0
        r = (cur / e - 1) * 100 if (cur and e) else None
        held = (time.time() * 1000 - p["ts"]) / 60000
        orows += (f"<tr><td>{html.escape(str(p.get('sym'))[:14])}</td>"
                  f"<td>${e:,.0f}</td><td>{('$%s'%format(cur,',.0f')) if cur else '-'}</td>"
                  f"<td class={cls(r or 0)}>{('%+.2f%%'%r) if r is not None else '-'}</td>"
                  f"<td class={cls((r or 0))}>{('$%+.2f'%(size*r/100)) if r is not None else '-'}</td>"
                  f"<td>{held:.0f}m</td></tr>")
    crows = ""
    for c in sorted(closed, key=lambda x: -x["ts"])[:20]:
        n = c.get("net_pct", 0)
        crows += (f"<tr><td>{html.escape(str(c.get('sym'))[:14])}</td>"
                  f"<td><span class=pill>{html.escape(str(c.get('why')))}</span></td>"
                  f"<td class={cls(c.get('ret_pct',0))}>{c.get('ret_pct',0):+.2f}%</td>"
                  f"<td class={cls(n)}>{n:+.2f}%</td>"
                  f"<td class={cls(c.get('pnl_usd',0))}>${c.get('pnl_usd',0):+.2f}</td>"
                  f"<td>{c.get('held_min',0):.0f}m</td></tr>")
    e = cfg.get("entry", {}); x = cfg.get("exit", {})
    return f"""<div class=wrap>
<h1>Scalpbot</h1><div class=sub>paper &middot; armed={cfg.get('armed')} &middot; {time.strftime('%H:%M:%S')}</div>
<div class=warn><b>PAPER. UNVALIDATED.</b> No wallet, no keys, no transaction code &mdash; this bot
cannot spend money. Its rules come from 39 minutes of live data with 4 statistical clusters and have
NOT passed a gate. This is a forward track record being built, not a proven edge.</div>
<div class=k>
<div class=c><div class=l>realised</div><div class="v {cls(realised)}">${realised:+.2f}</div></div>
<div class=c><div class=l>unrealised</div><div class="v {cls(unreal)}">${unreal:+.2f}</div></div>
<div class=c><div class=l>total</div><div class="v {cls(realised+unreal)}">${realised+unreal:+.2f}</div></div>
<div class=c><div class=l>open</div><div class=v>{len(open_)}</div></div>
<div class=c><div class=l>closed</div><div class=v>{len(closed)}</div></div>
<div class=c><div class=l>win rate</div><div class=v>{wr:.0f}%</div></div>
</div>
<div class=s>Open positions</div>
<table><tr><th>coin</th><th>entry mcap</th><th>now</th><th>move</th><th>p&amp;l</th><th>held</th></tr>
{orows or '<tr><td colspan=6 class=dim>none</td></tr>'}</table>
<div class=s>Closed trades (net of {toll}% toll)</div>
<table><tr><th>coin</th><th>why</th><th>gross</th><th>net</th><th>p&amp;l</th><th>held</th></tr>
{crows or '<tr><td colspan=6 class=dim>none yet</td></tr>'}</table>
<div class=sub style="margin-top:16px">entry: age {e.get('min_age_h')}-{e.get('max_age_h')}h &middot;
mcap ${e.get('min_mcap',0):,.0f}-${e.get('max_mcap',0):,.0f} &middot; max {e.get('max_pct_of_ath')} of ATH
&nbsp;|&nbsp; exit: stop {x.get('stop_pct')}% &middot; target {x.get('target_pct')}% &middot;
max hold {x.get('max_hold_min')}m &middot; size ${size}</div></div>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        try: body = f"<!doctype html><meta charset=utf-8><title>Scalpbot</title><style>{CSS}</style>{page()}"
        except Exception as ex: body = f"<pre>{html.escape(str(ex))}</pre>"
        b = body.encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.send_header("Refresh", "20")
        self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8798), H).serve_forever()
