"""Dashboard for the mid-cap flow screen. Read-only; serves on :8797."""
from __future__ import annotations
import json, time, html
from http.server import BaseHTTPRequestHandler, HTTPServer
from scripts.trading_bot.memebot import midcap_eval as E

CSS = """
*{box-sizing:border-box}body{margin:0;background:#0b0e11;color:#d7dce3;
font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.wrap{max-width:1180px;margin:0 auto;padding:18px}
h1{font-size:15px;margin:0 0 2px;letter-spacing:.14em;text-transform:uppercase;color:#e9eef5}
.sub{color:#7d8794;font-size:11px;margin-bottom:16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.kpi{background:#12171d;border:1px solid #1e252e;border-radius:6px;padding:10px 12px}
.kpi .k{color:#6f7885;font-size:10px;letter-spacing:.1em;text-transform:uppercase}
.kpi .v{font-size:19px;margin-top:3px;color:#e9eef5;font-variant-numeric:tabular-nums}
.warn{background:#1d1608;border:1px solid #4a3410;color:#e0b055;padding:10px 12px;
border-radius:6px;margin-bottom:16px;font-size:12px}
table{width:100%;border-collapse:collapse;margin-bottom:8px}
th{text-align:right;color:#6f7885;font-size:10px;letter-spacing:.09em;text-transform:uppercase;
padding:6px 8px;border-bottom:1px solid #1e252e}
th:first-child,td:first-child{text-align:left}
td{text-align:right;padding:6px 8px;border-bottom:1px solid #151b22;font-variant-numeric:tabular-nums}
.sec{color:#8b95a3;font-size:11px;letter-spacing:.1em;text-transform:uppercase;margin:16px 0 6px}
.early{color:#4ec9a0}.late{color:#e06c6c}.dim{color:#6f7885}
.bar{height:3px;background:#1e252e;border-radius:2px;overflow:hidden;margin-top:6px}
.bar>i{display:block;height:100%;background:#4ec9a0}
"""

def page():
    snaps, meta = E.load()
    if not snaps:
        return "<div class='wrap'><h1>Mid-cap flow screen</h1><p class=dim>No snapshots yet.</p></div>"
    ts = sorted(snaps)
    span_h = (ts[-1] - ts[0]) / 3_600_000 if len(ts) > 1 else 0.0
    mints = len({r["mint"] for v in snaps.values() for r in v})
    n2h = len(E.forward_returns(snaps, 7_200_000))
    pct = min(100, n2h / 400 * 100)
    sc = sorted(E.score_snapshot(snaps[ts[-1]]), key=lambda f: f["late"])
    def rows(fs, cls):
        o = []
        for f in fs:
            r = f["r"]
            o.append(f"<tr><td>{html.escape(str(r['sym'])[:14])}</td>"
                     f"<td class={cls}>{f['late']:+.2f}</td>"
                     f"<td>{r['buys']['h1']}/{r['sells']['h1']}</td>"
                     f"<td>{r['chg'].get('h1')}</td><td>{r['chg'].get('h24')}</td>"
                     f"<td>${r['liq_usd']:,.0f}</td>"
                     f"<td>${(r['vol'].get('h24') or 0):,.0f}</td></tr>")
        return "".join(o)
    hdr = ("<tr><th>token</th><th>LATE</th><th>h1 buys/sells</th><th>h1 %</th>"
           "<th>h24 %</th><th>liquidity</th><th>vol 24h</th></tr>")
    return f"""<div class=wrap>
<h1>Mid-cap flow screen</h1>
<div class=sub>prereg 3f235481 &middot; frozen before collection &middot; updated {time.strftime('%H:%M:%S')}</div>
<div class=warn><b>UNVALIDATED.</b> This is a hypothesis under test, not a buy signal. GATE 1 needs 400
resolved +2h returns before any effect may be read. Most likely declared outcome: the spread is
smaller than the 3% round-trip toll, i.e. untradeable.
<div class=bar><i style="width:{pct:.1f}%"></i></div>
<span class=dim>GATE 1 progress {n2h}/400 resolved +2h returns</span></div>
<div class=kpis>
<div class=kpi><div class=k>snapshots</div><div class=v>{len(snaps)}</div></div>
<div class=kpi><div class=k>span</div><div class=v>{span_h:.1f}h</div></div>
<div class=kpi><div class=k>distinct mints</div><div class=v>{mints}</div></div>
<div class=kpi><div class=k>scored now</div><div class=v>{len(sc)}</div></div>
<div class=kpi><div class=k>+2h resolved</div><div class=v>{n2h}</div></div>
</div>
<div class=sec>Most EARLY &mdash; accelerating, buy-skewed, sells not yet rotating in</div>
<table>{hdr}{rows(sc[:8], 'early')}</table>
<div class=sec>Most LATE &mdash; decelerating, flow at parity, sells rotating in first</div>
<table>{hdr}{rows(sc[-8:], 'late')}</table>
<div class=sub style="margin-top:14px">LATE = -z(decel) - z(rotation) - z(imb_h1), cross-sectional
within snapshot. decel = chg.m5*12 - chg.h1; rotation = imb(m5) - imb(h6); imb(w) = (buys-sells)/(buys+sells).</div>
</div>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body = f"<!doctype html><meta charset=utf-8><title>Mid-cap flow</title><style>{CSS}</style>{page()}"
        except Exception as e:
            body = f"<pre>error: {html.escape(str(e))}</pre>"
        b = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Refresh", "30")
        self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8797), H).serve_forever()
