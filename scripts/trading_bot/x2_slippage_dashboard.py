#!/usr/bin/env python3
"""X2_FLOWSTREAK capacity dashboard — one clean question, one clean answer.

Serves a single, uncluttered page for the one decision that matters right now: can X2_FLOWSTREAK (the
1-of-598 correction-survivor) fill a real rebalance inside its 17.9 bp/side breakeven? It reads the
harness output `research/data/x2_slippage/result.json` and renders the headline verdict, the capacity
curve (per-side all-in cost vs book AUM, against the breakeven line), the cost breakdown, and honest
provenance. No trading, no orders — a read-only view of a measurement.

    python -m scripts.trading_bot.x2_slippage_dashboard        # serves 127.0.0.1:8794
"""
from __future__ import annotations

import html
import json
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESULT = ROOT / "research" / "data" / "x2_slippage" / "result.json"
PREREG = "research/trading_bot/X2_FLOWSTREAK_SLIPPAGE_PREREGISTRATION.md"
HOST, PORT = "127.0.0.1", 8794
BREAKEVEN_BP = 17.9

VERDICT_COLOR = {"SIZE": "#1a9e5f", "SIZE-DOWN": "#c99a00", "KILL": "#d0453b",
                 "POC": "#5b6bd6", "PENDING": "#7a7f87"}


def _load():
    try:
        return json.loads(RESULT.read_text())
    except (OSError, ValueError):
        return None


def _fmt(x, nd=2, suffix=""):
    if x is None:
        return "—"
    try:
        return f"{float(x):,.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return html.escape(str(x))


def _capacity_svg(curve: list[dict]) -> str:
    """Per-side all-in cost (bp) vs AUM (log-x), with the breakeven line. Pure inline SVG, no deps."""
    pts = [(c.get("aum_usd"), c.get("cost_bp_per_side")) for c in curve
           if c.get("aum_usd") and c.get("cost_bp_per_side") is not None]
    if len(pts) < 2:
        return '<div class="empty">capacity curve pending</div>'
    import math
    W, H, PADL, PADR, PADT, PADB = 720, 320, 64, 24, 24, 44
    xs = [math.log10(a) for a, _ in pts]
    ys = [c for _, c in pts]
    ymax = max(max(ys), BREAKEVEN_BP) * 1.15
    xmin, xmax = min(xs), max(xs)
    def X(lx): return PADL + (lx - xmin) / (xmax - xmin or 1) * (W - PADL - PADR)
    def Y(v): return H - PADB - (v / (ymax or 1)) * (H - PADT - PADB)
    # gridlines + y labels
    grid = []
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        v = ymax * frac
        y = Y(v)
        grid.append(f'<line x1="{PADL}" y1="{y:.1f}" x2="{W-PADR}" y2="{y:.1f}" class="grid"/>'
                    f'<text x="{PADL-8}" y="{y+4:.1f}" class="ylab" text-anchor="end">{v:.0f}</text>')
    # x labels at each AUM point
    xlab = []
    for a, _ in pts:
        x = X(math.log10(a))
        lab = f"${a/1e6:.1f}M" if a >= 1e6 else f"${a/1e3:.0f}k"
        xlab.append(f'<text x="{x:.1f}" y="{H-PADB+18:.1f}" class="xlab" text-anchor="middle">{lab}</text>')
    # breakeven line
    yb = Y(BREAKEVEN_BP)
    be = (f'<line x1="{PADL}" y1="{yb:.1f}" x2="{W-PADR}" y2="{yb:.1f}" class="breakeven"/>'
          f'<text x="{W-PADR}" y="{yb-6:.1f}" class="belab" text-anchor="end">breakeven {BREAKEVEN_BP} bp</text>')
    # cost polyline + dots
    poly = " ".join(f"{X(math.log10(a)):.1f},{Y(c):.1f}" for a, c in pts)
    dots = "".join(f'<circle cx="{X(math.log10(a)):.1f}" cy="{Y(c):.1f}" r="4" class="dot"/>'
                   f'<text x="{X(math.log10(a)):.1f}" y="{Y(c)-10:.1f}" class="dlab" text-anchor="middle">{c:.1f}</text>'
                   for a, c in pts)
    return (f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" '
            f'aria-label="per-side cost versus book size">{"".join(grid)}{be}'
            f'<polyline points="{poly}" class="costline"/>{dots}{"".join(xlab)}'
            f'<text x="{PADL}" y="14" class="axtitle">per-side all-in cost (bp)</text></svg>')


def _page() -> str:
    d = _load()
    if d is None:
        body = ('<div class="card"><div class="verdict" style="background:#7a7f87">AWAITING FIRST '
                'MEASUREMENT</div><p class="sub">The harness has not written a result yet. This page '
                'refreshes itself; the capacity curve appears once the design-window PoC completes.</p></div>')
        return _shell(body)
    verdict = str(d.get("verdict", "PENDING")).upper()
    vkey = "POC" if verdict.startswith("POC") else verdict.split("-")[0] if verdict.startswith("SIZE-") else verdict
    color = VERDICT_COLOR.get(verdict if verdict in VERDICT_COLOR else vkey, "#7a7f87")
    window = html.escape(str(d.get("window", "?")))
    is_poc = "poc" in verdict.lower() or window == "design"
    curve = d.get("capacity_curve") or []
    cov = d.get("coverage") or {}
    comp = d.get("per_side_cost_components") or {}

    rows = "".join(
        f'<tr><td>{_fmt(c.get("aum_usd"),0)}</td>'
        f'<td class="num">{_fmt(c.get("cost_bp_per_side"),1," bp")}</td>'
        f'<td class="num {"pos" if (c.get("net_mean_R") or 0)>0 else "neg"}">{_fmt(c.get("net_mean_R"),4)}</td>'
        f'<td class="num">{_fmt(c.get("t"),2)}</td></tr>'
        for c in curve)

    poc_banner = ('<div class="poc">⚠ PoC on the DESIGN window (2023–2024) — a method check, not the '
                  'decision. The frozen verdict is evaluated on the held-out 2025–2026 window.</div>'
                  if is_poc else "")

    body = f"""
    <div class="grid">
      <section class="card hero">
        <div class="verdict" style="background:{color}">{html.escape(verdict)}</div>
        <div class="herometa">
          <div><span class="k">max tradeable AUM</span><span class="v">{_fmt(d.get("max_tradeable_aum_usd"),0)}</span></div>
          <div><span class="k">rebalances</span><span class="v">{_fmt(d.get("n_rebalances"),0)}</span></div>
          <div><span class="k">names / rebal (med)</span><span class="v">{_fmt(d.get("n_names_median"),0)}</span></div>
          <div><span class="k">breakeven</span><span class="v">{BREAKEVEN_BP} bp/side</span></div>
        </div>
      </section>
      {poc_banner}
      <section class="card">
        <h2>Capacity — can we fill inside the breakeven?</h2>
        {_capacity_svg(curve)}
        <table><thead><tr><th>book AUM ($)</th><th>cost/side</th><th>net mean R</th><th>t</th></tr></thead>
        <tbody>{rows or '<tr><td colspan=4 class="empty">no curve yet</td></tr>'}</tbody></table>
      </section>
      <section class="card cols">
        <div>
          <h2>Per-side cost breakdown</h2>
          <ul class="kv">
            <li><span>modeled slippage</span><b>{_fmt(comp.get("slippage_bp"),1," bp")}</b></li>
            <li><span>taker fee</span><b>{_fmt(comp.get("fee_bp"),1," bp")}</b></li>
            <li><span>half-spread</span><b>{_fmt(comp.get("half_spread_bp"),1," bp")}</b></li>
          </ul>
        </div>
        <div>
          <h2>Coverage &amp; provenance</h2>
          <ul class="kv">
            <li><span>window</span><b>{window}</b></li>
            <li><span>names with depth</span><b>{_fmt(cov.get("names_with_depth"),0)}</b></li>
            <li><span>rebal notional covered</span><b>{_fmt((cov.get("frac_rebalance_notional_covered") or 0)*100,0,"%")}</b></li>
            <li><span>data</span><b>free Binance bookDepth (±1%)</b></li>
          </ul>
        </div>
      </section>
      <p class="foot">Model: ±1% band, uniform-density walk + fee + half-spread. Frozen rule &amp; caveats in
      <code>{PREREG}</code>. Generated {_fmt(d.get("generated_unix"),0)} · {html.escape(str(d.get("note","")))}</p>
    </div>"""
    return _shell(body)


def _shell(body: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="20">
<title>X2_FLOWSTREAK Capacity</title><style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#1a1d22;--sub:#5b6169;--line:#e6e8ec;--accent:#5b6bd6;--pos:#1a9e5f;--neg:#d0453b}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1216;--card:#171b21;--ink:#e8eaed;--sub:#9aa0a8;--line:#262b32;--accent:#7d8cf0;--pos:#3fca86;--neg:#e8695f}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:820px;margin:0 auto;padding:28px 20px 60px}}
.top{{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:18px}}
.top h1{{font-size:19px;margin:0;letter-spacing:-.2px}}.top .tag{{font-size:12px;color:var(--sub)}}
.grid{{display:flex;flex-direction:column;gap:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px}}
.card h2{{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--sub);margin:0 0 14px}}
.hero{{display:flex;align-items:center;gap:24px;flex-wrap:wrap}}
.verdict{{color:#fff;font-weight:700;font-size:20px;letter-spacing:.04em;padding:12px 20px;border-radius:10px}}
.herometa{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 28px;flex:1;min-width:260px}}
.herometa .k{{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--sub)}}
.herometa .v{{font-size:18px;font-weight:650;font-variant-numeric:tabular-nums}}
.poc{{background:color-mix(in srgb,var(--accent) 12%,transparent);border:1px solid var(--accent);
color:var(--ink);border-radius:10px;padding:11px 14px;font-size:13px}}
.chart{{width:100%;height:auto;display:block;margin-bottom:8px}}
.grid line.grid{{stroke:var(--line);stroke-width:1}}.breakeven{{stroke:var(--neg);stroke-width:1.5;stroke-dasharray:5 4}}
.belab{{fill:var(--neg);font-size:11px;font-weight:600}}.costline{{fill:none;stroke:var(--accent);stroke-width:2.5}}
.dot{{fill:var(--accent)}}.dlab{{fill:var(--sub);font-size:10px;font-variant-numeric:tabular-nums}}
.ylab,.xlab{{fill:var(--sub);font-size:11px;font-variant-numeric:tabular-nums}}.axtitle{{fill:var(--sub);font-size:11px}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px}}
th{{text-align:left;color:var(--sub);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
padding:6px 8px;border-bottom:1px solid var(--line)}}td{{padding:7px 8px;border-bottom:1px solid var(--line)}}
td.num{{text-align:right}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
.cols{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}}
ul.kv{{list-style:none;margin:0;padding:0}}ul.kv li{{display:flex;justify-content:space-between;
padding:7px 0;border-bottom:1px solid var(--line)}}ul.kv span{{color:var(--sub)}}
ul.kv b{{font-variant-numeric:tabular-nums}}
.sub{{color:var(--sub)}}.empty{{color:var(--sub);text-align:center;padding:18px}}
.foot{{color:var(--sub);font-size:12px;line-height:1.6}}code{{background:var(--line);padding:1px 5px;border-radius:4px;font-size:11px}}
@media(max-width:560px){{.cols,.herometa{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<div class="top"><h1>X2_FLOWSTREAK · Capacity Decision</h1>
<span class="tag">the 1-of-598 survivor — does it fill inside breakeven?</span></div>
{body}</div></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") in ("", "/x2", "/index.html") or self.path == "/":
            payload = _page().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path.rstrip("/") == "/result.json":
            payload = (RESULT.read_bytes() if RESULT.exists() else b"{}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):  # silence
        pass


def main() -> int:
    print(f"X2_FLOWSTREAK capacity dashboard: http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
