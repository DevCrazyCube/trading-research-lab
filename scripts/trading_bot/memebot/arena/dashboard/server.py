#!/usr/bin/env python3
"""MEME ARENA dashboard — one clean read-only page: a verdict card per arm (N/target, mean net-R with the
CLUSTER-bootstrap CI, chain-verified badge), an equity curve, live open positions, and the honesty panel
(fill basis, gate tier, stuck-open/rug counts). No trading — a view of the frozen forward measurement.

    python -m scripts.trading_bot.memebot.arena.dashboard.server        # 127.0.0.1:8795
"""
from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import runtime as RT

HOST, PORT = "127.0.0.1", 8795
VCOL = {"PASS": "#1a9e5f", "COLLECTING": "#5b6bd6", "UNDECIDED_EXTEND": "#c99a00",
        "PASS_TO_CONFIRMATION": "#1a9e5f", "PASS_PENDING_SENSITIVITY": "#c99a00",
        "KILL": "#d0453b", "NOT_ACTIVE": "#d0453b", "INVALID": "#d0453b", "UNSET": "#7a7f87"}


def _fmt(x, nd=4):
    return "—" if x is None else (f"{x:,.{nd}f}" if isinstance(x, (int, float)) else html.escape(str(x)))


def _equity_svg(rows: list[dict]) -> str:
    res = [r for r in rows if r.get("kind") == "resolved"]
    if len(res) < 2:
        return '<div class="empty">equity curve appears after 2 resolved trades</div>'
    eq, cum = [], 0.0
    for r in res:
        cum += r.get("net_return", 0.0)
        eq.append(cum)
    W, H, P = 640, 150, 28
    lo, hi = min(eq + [0]), max(eq + [0])
    rng = (hi - lo) or 1
    def X(i): return P + i / (len(eq) - 1) * (W - 2 * P)
    def Y(v): return H - P - (v - lo) / rng * (H - 2 * P)
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(eq))
    zero = Y(0)
    color = "#1a9e5f" if eq[-1] >= 0 else "#d0453b"
    return (f'<svg viewBox="0 0 {W} {H}" class="eq"><line x1="{P}" y1="{zero:.1f}" x2="{W-P}" '
            f'y2="{zero:.1f}" class="zero"/><polyline points="{pts}" fill="none" stroke="{color}" '
            f'stroke-width="2"/><text x="{W-P}" y="{Y(eq[-1])-6:.1f}" text-anchor="end" '
            f'class="eqlab" fill="{color}">{eq[-1]:+.3f}R</text></svg>')


def _card(arm) -> str:
    rep = RT.report_arm(arm)
    rows = RT._ledger(arm)._rows() if rep.get("verdict") != "NOT_ACTIVE" else []
    v = rep["verdict"]
    col = VCOL.get(v, "#7a7f87")
    ci = (f'[{_fmt(rep.get("ci_lo"))}, {_fmt(rep.get("ci_hi"))}]'
          if rep.get("ci_lo") is not None else "—")
    state = RT._load(RT.DATA / arm.instrument / "state.json", {"open": {}})
    opens = state.get("open", {})
    oprows = "".join(
        f'<tr><td class="mono">{html.escape(m[:10])}…</td><td class="num">{_fmt(p.get("entry_price"),8)}</td>'
        f'<td class="num">{_fmt(p.get("peak"),8)}</td><td class="num">{_fmt(p.get("entry_delay_min"),0)}m</td></tr>'
        for m, p in list(opens.items())[:10])
    chain = "✓ chain" if rep.get("chain_ok") else "✗ CHAIN BROKEN"
    return f"""
    <section class="card">
      <div class="chead">
        <div><h2>{html.escape(arm.instrument)}</h2><span class="basis">{html.escape(rep['basis'])} fill · {chain}</span></div>
        <div class="verdict" style="background:{col}">{html.escape(v)}</div>
      </div>
      <div class="metrics">
        <div><span class="k">resolved</span><span class="val">{rep['resolved']} / {rep['target_n']}</span></div>
        <div><span class="k">open</span><span class="val">{rep['open']}</span></div>
        <div><span class="k">mean net-R</span><span class="val {'pos' if (rep.get('mean') or 0)>0 else 'neg'}">{_fmt(rep.get('mean'))}</span></div>
        <div><span class="k">bootstrap CI (mint+day)</span><span class="val">{ci}</span></div>
      </div>
      {_equity_svg(rows)}
      <div class="reason">{html.escape(rep.get('reason',''))}</div>
      <table><thead><tr><th>open mint</th><th>entry</th><th>peak</th><th>delay</th></tr></thead>
      <tbody>{oprows or '<tr><td colspan=4 class="empty">no open positions</td></tr>'}</tbody></table>
    </section>"""


def _page() -> str:
    cards = "".join(_card(a) for a in RT._registered_arms())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="20">
<title>MEME ARENA</title><style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#1a1d22;--sub:#5b6169;--line:#e6e8ec;--pos:#1a9e5f;--neg:#d0453b}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1216;--card:#171b21;--ink:#e8eaed;--sub:#9aa0a8;--line:#262b32;--pos:#3fca86;--neg:#e8695f}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:760px;margin:0 auto;padding:26px 18px 60px}}
.top{{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:16px}}
.top h1{{font-size:18px;margin:0;letter-spacing:-.2px}}.top .tag{{font-size:12px;color:var(--sub)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:16px}}
.chead{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px}}
.chead h2{{font-size:15px;margin:0}}.basis{{font-size:11px;color:var(--sub)}}
.verdict{{color:#fff;font-weight:700;font-size:12px;letter-spacing:.04em;padding:6px 12px;border-radius:8px;white-space:nowrap}}
.metrics{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px 20px;margin-bottom:12px}}
.metrics .k{{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--sub)}}
.metrics .val{{font-size:16px;font-weight:650;font-variant-numeric:tabular-nums}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
.eq{{width:100%;height:auto;display:block;margin:6px 0}}.zero{{stroke:var(--line);stroke-width:1;stroke-dasharray:4 3}}
.eqlab{{font-size:11px;font-weight:600;font-variant-numeric:tabular-nums}}
.reason{{font-size:12px;color:var(--sub);margin:6px 0 12px}}
table{{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}}
th{{text-align:left;color:var(--sub);font-weight:500;font-size:10px;text-transform:uppercase;letter-spacing:.05em;padding:5px 6px;border-bottom:1px solid var(--line)}}
td{{padding:5px 6px;border-bottom:1px solid var(--line)}}td.num{{text-align:right}}.mono{{font-family:ui-monospace,monospace}}
.empty{{color:var(--sub);text-align:center;padding:12px}}
</style></head><body><div class="wrap">
<div class="top"><h1>🏟️ MEME ARENA</h1><span class="tag">frozen multi-arm forward test · honest fills · paper only</span></div>
{cards}</div></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") in ("", "/index.html"):
            payload = _page().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


def main() -> int:
    print(f"MEME ARENA dashboard: http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
