#!/usr/bin/env python3
"""Launchpad Observatory dashboard — the measured launch-curve economics, on one page.

    python -m scripts.trading_bot.memebot.observatory_dashboard      # 127.0.0.1:8796

Renders `observatory.build_state()` and nothing else. Every number on the page came from `venues.py`
(the frozen, measured registry), the on-disk LaunchLab census, or the live multi-venue tape. Where the
registry REFUSES a number — Boop's multiple, Heaven's whole EV frame — the cell is an em-dash and the
refusal text is the tooltip. Nothing is fabricated, interpolated or rounded into existence.

  * a KPI strip of the headline measurements
  * THE EV CURVE: EV(m) = (1 + (X-1)p)/m - 1 - toll for every venue whose X, p and toll are all
    established, with the break-even premium m* marked. This is the whole argument in one picture.
  * a venue table with the monogram/copy/badge treatment of the other memebot dashboards
  * the LaunchLab census + the label ledger (82 -> 13,694)
  * the live tape's most recent creates and graduations

READ-ONLY. No order path, no wallet, no writes. Bound to 127.0.0.1. Port 8796 (8795 is the arena,
8794 the X2 cost dashboard). A census refresh is a deliberate POST to /api/refresh_census, never a poll.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import observatory as OBS

HOST, PORT = "127.0.0.1", 8796
STATE_TTL = 5.0                    # server-side memo; the state is a disk read, not a network call

_LOCK = threading.Lock()
_CACHE: dict = {"at": 0.0, "state": None}


def state_view() -> dict:
    with _LOCK:
        if _CACHE["state"] is not None and (time.time() - _CACHE["at"]) < STATE_TTL:
            return _CACHE["state"]
    state = OBS.build_state()
    with _LOCK:
        _CACHE.update({"at": time.time(), "state": state})
    return state


PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Launchpad Observatory</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0a0b0e;--bg2:#0d0f12;--panel:#0f1216;--panel2:#12161b;--row:#111419;--line:#1b1f26;--line2:#242a33;
--text:#d5dbe3;--text2:#8a93a0;--text3:#59616d;--mint:#3ee08f;--mint-bg:rgba(62,224,143,.10);
--red:#ff4d4d;--red-bg:rgba(255,77,77,.10);--amber:#e8b153;--amber-bg:rgba(232,177,83,.10);
--mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
--sans:"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
*{box-sizing:border-box;border-radius:0!important}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:12.5px/1.45 var(--sans);-webkit-font-smoothing:antialiased}
.num,.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.pos{color:var(--mint)} .neg{color:var(--red)} .warn{color:var(--amber)} .dim{color:var(--text3)}
.wrap{max-width:1500px;margin:0 auto;padding:0 18px 40px}

header{border-bottom:1px solid var(--line);background:var(--bg2);padding:16px 0 14px;margin-bottom:16px}
header .wrap{padding-bottom:0}
h1{margin:0;font-size:15px;font-weight:600;letter-spacing:-.1px}
.tag{font-size:10.5px;color:var(--text2);margin-top:3px}
.hdr-row{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
.hdr-right{font-family:var(--mono);font-size:10px;color:var(--text3);text-align:right;line-height:1.6}

.strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));border:1px solid var(--line);
background:var(--panel);margin-bottom:16px}
.cell{padding:11px 13px;border-right:1px solid var(--line)}
.cell:last-child{border-right:none}
.lbl{font-size:9px;letter-spacing:.9px;text-transform:uppercase;color:var(--text3);font-weight:600}
.val{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:17px;margin-top:5px;line-height:1.1}
.sub{font-size:10px;color:var(--text2);margin-top:4px}

.panel{border:1px solid var(--line);background:var(--panel);margin-bottom:16px}
.phead{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;
padding:10px 13px;border-bottom:1px solid var(--line);background:var(--bg2)}
.ptitle{font-size:11px;font-weight:600;letter-spacing:.4px;text-transform:uppercase}
.pnote{font-size:10px;color:var(--text2);font-family:var(--mono)}
.pbody{padding:13px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:1000px){.grid2{grid-template-columns:1fr}}

.chart{width:100%;height:290px;display:block}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;padding:10px 13px 2px;border-top:1px solid var(--line)}
.lg{display:flex;align-items:center;gap:6px;font-size:10.5px;font-family:var(--mono);cursor:pointer;
padding:2px 0;user-select:none}
.lg .sw{width:11px;height:2px;flex:0 0 11px}
.lg.off{opacity:.32}
.lg .mstar{color:var(--text3)}

table{width:100%;border-collapse:collapse}
thead th{position:sticky;top:0;z-index:2;background:var(--bg2);font-size:9.5px;letter-spacing:.8px;
text-transform:uppercase;color:var(--text3);font-weight:600;text-align:right;padding:8px 10px;
border-bottom:1px solid var(--line2);white-space:nowrap}
thead th.l{text-align:left}
tbody td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:right;
font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
tbody td.l{text-align:left;font-family:var(--sans)}
tbody tr:hover{background:var(--row)}
tbody tr.muted td{color:var(--text3)}

.tok{display:flex;align-items:center;gap:9px}
.mono-sq{width:22px;height:22px;flex:0 0 22px;border:1px solid var(--line2);display:flex;
align-items:center;justify-content:center;font-family:var(--mono);font-size:10px;font-weight:700}
.tok-txt{min-width:0}
.tok-sym{font-weight:700;font-size:12px;display:flex;align-items:center;gap:6px}
.tok-sub{font-family:var(--mono);font-size:9.5px;color:var(--text3);margin-top:1px}
.cp{font-family:var(--mono);font-size:9px;color:var(--text3);border:1px solid var(--line2);
padding:0 4px;cursor:pointer;line-height:14px}
.cp:hover{color:var(--text);border-color:var(--text3)}
.cp.ok{color:var(--mint);border-color:var(--mint)}

.badge{display:inline-block;font-family:var(--mono);font-weight:700;font-size:9px;padding:2px 7px;
text-transform:uppercase;border:1px solid;letter-spacing:.4px}
.b-mint{color:var(--mint);background:var(--mint-bg);border-color:rgba(62,224,143,.42)}
.b-red{color:var(--red);background:var(--red-bg);border-color:rgba(255,77,77,.42)}
.b-amber{color:var(--amber);background:var(--amber-bg);border-color:rgba(232,177,83,.42)}
.b-dim{color:var(--text3);background:transparent;border-color:var(--line2)}

.scroll{overflow-x:auto}
.tall{max-height:420px;overflow-y:auto}
.kv{display:flex;justify-content:space-between;gap:14px;padding:6px 0;border-bottom:1px solid var(--line);
font-size:11.5px}
.kv:last-child{border-bottom:none}
.kv .k{color:var(--text2)} .kv .v{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right}
.bars{margin-top:4px}
.barrow{display:grid;grid-template-columns:74px 1fr 96px;gap:10px;align-items:center;padding:7px 0}
.bartrack{height:8px;background:var(--panel2);border:1px solid var(--line)}
.barfill{height:100%;display:block}
.note{font-size:10.5px;color:var(--text2);line-height:1.55;margin-top:10px}
ul.unlocks{margin:8px 0 0;padding-left:16px;font-size:11px;color:var(--text2);line-height:1.6}
ul.unlocks li{margin-bottom:4px}
footer{font-family:var(--mono);font-size:10px;color:var(--text3);padding-top:6px}
.err{border:1px solid rgba(255,77,77,.42);background:var(--red-bg);color:var(--red);padding:9px 13px;
font-family:var(--mono);font-size:11px;margin-bottom:16px}
button.act{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.6px;
background:transparent;color:var(--text2);border:1px solid var(--line2);padding:4px 9px;cursor:pointer}
button.act:hover{color:var(--text);border-color:var(--text3)}
button.act:disabled{opacity:.45;cursor:default}

/* --- live activity: the only part of this page that is supposed to move --------------------- */
.livegrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));
background:var(--panel2);border-bottom:1px solid var(--line)}
.lcell{padding:9px 13px;border-right:1px solid var(--line)}
.lcell:last-child{border-right:none}
.lval{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:19px;line-height:1.1;margin-top:4px}
.lval.hero{font-size:24px;color:var(--amber);font-weight:600}
.livechart{width:100%;height:250px;display:block}
.pulse{display:inline-block;width:6px;height:6px;background:var(--mint);margin-right:7px;
vertical-align:middle}
.pulse.on{animation:blink 2s steps(1,end) infinite}
.pulse.stale{background:var(--amber);animation:none}
.pulse.dead{background:var(--red);animation:none}
@keyframes blink{0%,54%{opacity:1}55%,100%{opacity:.16}}
@keyframes bump{0%{background:var(--amber-bg)}100%{background:transparent}}
.bump{animation:bump 1.6s ease-out}
.ratio{display:grid;grid-template-columns:1fr 1.35fr;border-top:1px solid var(--line)}
.ratiocell{padding:10px 13px;border-right:1px solid var(--line)}
.ratiocell:last-child{border-right:none}
.pline{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:11.5px;
display:flex;justify-content:space-between;gap:12px;padding:3px 0}
.warnbox{border-left:2px solid var(--amber);background:var(--amber-bg);padding:7px 10px;
font-size:10.5px;color:var(--text2);line-height:1.55;margin-top:9px}
</style></head><body>

<header><div class="wrap"><div class="hdr-row">
  <div>
    <h1>Launchpad Observatory</h1>
    <div class="tag">measured launch-curve economics across every Solana launchpad &middot;
      <span class="mono">EV(m) = (1 + (X&minus;1)p)/m &minus; 1 &minus; toll</span></div>
  </div>
  <div class="hdr-right" id="hdr">&mdash;</div>
</div></div></header>

<div class="wrap">
  <div id="err"></div>
  <div class="strip" id="strip"></div>

  <div class="panel">
    <div class="phead">
      <div class="ptitle"><span class="pulse" id="pulse"></span>Live activity &mdash; launches per minute, off the verified tape</div>
      <div class="pnote"><span id="livechain">&mdash;</span> &middot; updated <span id="ago" class="warn">&mdash;</span> ago</div>
    </div>
    <div class="livegrid" id="livestrip"></div>
    <div class="pbody" style="padding-bottom:4px"><svg class="livechart" id="livechart" preserveAspectRatio="none"></svg></div>
    <div class="ratio">
      <div class="ratiocell">
        <div class="lbl">Observed flow ratio</div>
        <div class="lval warn" id="flowval">&mdash;</div>
        <div class="sub" id="flowlbl">&mdash;</div>
        <div class="sub" id="lagline" style="margin-top:7px">&mdash;</div>
      </div>
      <div class="ratiocell">
        <div class="lbl">Cohort graduation rate p &mdash; measured, not from this feed</div>
        <div id="cohortp" style="margin-top:5px"></div>
      </div>
    </div>
    <div class="pbody" style="padding-top:10px">
      <div class="warnbox" id="flownote">&mdash;</div>
      <div class="note" id="livefoot">&mdash;</div>
    </div>
  </div>

  <div class="panel">
    <div class="phead">
      <div class="ptitle">The EV curve &mdash; analytical, moves only when the census is re-measured</div>
      <div class="pnote" id="evnote">&mdash;</div>
    </div>
    <div class="pbody" style="padding-bottom:4px"><svg class="chart" id="chart" preserveAspectRatio="none"></svg></div>
    <div class="legend" id="legend"></div>
    <div class="pbody" style="padding-top:8px"><div class="note" id="evfoot">&mdash;</div></div>
  </div>

  <div class="panel">
    <div class="phead">
      <div class="ptitle">Venue economics</div>
      <div class="pnote" id="vnote">&mdash;</div>
    </div>
    <div class="scroll"><table id="vtable">
      <thead><tr>
        <th class="l">Venue</th><th class="l">Curve</th><th>X</th><th>p</th><th>n</th><th>grads</th>
        <th>toll /side</th><th>toll r/t</th><th>(X&minus;1)p</th><th>m*</th><th>EV @ floor</th>
        <th class="l">Rank</th>
      </tr></thead>
      <tbody id="vbody"></tbody>
    </table></div>
    <div class="pbody"><div class="note" id="vfoot">&mdash;</div></div>
  </div>

  <div class="grid2">
    <div class="panel">
      <div class="phead">
        <div class="ptitle">LaunchLab census</div>
        <button class="act" id="refresh">Re-measure</button>
      </div>
      <div class="pbody">
        <div id="census"></div>
        <div class="bars" id="censusbars"></div>
        <div class="note" id="censusnote">&mdash;</div>
      </div>
    </div>

    <div class="panel">
      <div class="phead">
        <div class="ptitle">Label ledger</div>
        <div class="pnote" id="lednote">&mdash;</div>
      </div>
      <div class="pbody">
        <div id="ledger"></div>
        <ul class="unlocks" id="unlocks"></ul>
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="phead">
      <div class="ptitle">Live multi-venue tape</div>
      <div class="pnote" id="tapenote">&mdash;</div>
    </div>
    <div class="scroll tall"><table id="ttable">
      <thead><tr>
        <th class="l">Token</th><th class="l">Venue</th><th class="l">Kind</th>
        <th>slot</th><th class="l">seen (utc)</th><th class="l">signature</th><th>seq</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table></div>
    <div class="pbody"><div class="note" id="tapefoot">&mdash;</div></div>
  </div>

  <footer id="foot">&mdash;</footer>
</div>

<script>
const EM = "—";
const OFF = new Set();              // legend toggles, venue_id -> hidden
let LAST = null, SCALED = false;

const nf = (x, d) => (x === null || x === undefined || !isFinite(x)) ? EM
  : Number(x).toLocaleString("en-US", {minimumFractionDigits: d, maximumFractionDigits: d});
const pct = (x, d) => (x === null || x === undefined || !isFinite(x)) ? EM : (x * 100).toFixed(d) + "%";
const int = x => (x === null || x === undefined || !isFinite(x)) ? EM : Number(x).toLocaleString("en-US");
const esc = s => String(s === null || s === undefined ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const sign = x => (x === null || x === undefined || !isFinite(x)) ? "" : (x > 0 ? "pos" : (x < 0 ? "neg" : ""));

// deterministic hue from a mint/id string -> the monogram square
function hue(s){ let h = 0; s = String(s || ""); for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360; return h; }
function monogram(id, label){
  const h = hue(id);
  return '<span class="mono-sq" style="background:hsl(' + h + ',18%,20%);color:hsl(' + h + ',34%,68%)">'
    + esc(String(label || "?").slice(0, 2).toUpperCase()) + '</span>';
}
function trunc(s, a = 4, b = 4){
  s = String(s || ""); return s.length <= a + b + 1 ? s : s.slice(0, a) + "…" + s.slice(-b);
}
function copyCell(text){
  return text ? '<span class="cp" data-copy="' + esc(text) + '">COPY</span>' : "";
}
document.addEventListener("click", e => {
  const el = e.target.closest("[data-copy]"); if (!el) return;
  navigator.clipboard.writeText(el.dataset.copy).then(() => {
    el.classList.add("ok"); el.textContent = "OK";
    setTimeout(() => { el.classList.remove("ok"); el.textContent = "COPY"; }, 900);
  }).catch(() => {});
});

// ---- the EV curve ---------------------------------------------------------------------------------
const PALETTE = ["#3ee08f","#e8b153","#5b8dd6","#c07de0","#e0705b","#4fc9c0","#9aa7b6","#d6c04f","#7f8fa6"];

function drawChart(st){
  const svg = document.getElementById("chart");
  const series = (st.ev_curves && st.ev_curves.series || []).filter(s => !OFF.has(s.venue_id));
  const W = 1000, H = 290, L = 52, R = 16, T = 14, B = 30;
  if (!series.length){ svg.setAttribute("viewBox", "0 0 " + W + " " + H); svg.innerHTML = ""; return; }

  const xs = [st.ev_curves.m_min, st.ev_curves.m_max];
  // Scale to the VISIBLE series. The near-certain-completion configs (p > MAX_LOTTERY_P) sit at
  // EV ~ +1160% and would flatten every real lottery curve into one flat line, so they start hidden
  // (see the legend) — but if a reader re-enables one, clip rather than destroy the scale.
  let lo = 0, hi = 0;
  series.forEach(s => s.points.forEach(p => { if (p[1] < lo) lo = p[1]; if (p[1] > hi) hi = p[1]; }));
  if (hi > 1.5) hi = 1.5;
  lo = Math.max(lo, -0.9); hi = Math.max(hi, 0.30);
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;

  const X = m => L + (m - xs[0]) / (xs[1] - xs[0]) * (W - L - R);
  const Y = v => T + (hi - v) / (hi - lo) * (H - T - B);

  let g = "";
  // horizontal gridlines + y labels
  const yticks = 6;
  for (let i = 0; i <= yticks; i++){
    const v = lo + (hi - lo) * i / yticks, y = Y(v);
    g += '<line x1="' + L + '" y1="' + y.toFixed(1) + '" x2="' + (W - R) + '" y2="' + y.toFixed(1)
       + '" stroke="var(--line)" stroke-width="1"/>';
    g += '<text x="' + (L - 7) + '" y="' + (y + 3).toFixed(1) + '" text-anchor="end" font-size="9" '
       + 'font-family="var(--mono)" fill="var(--text3)">' + (v * 100).toFixed(0) + '%</text>';
  }
  // vertical gridlines + x labels
  for (let m = 1.0; m <= 2.0001; m += 0.2){
    const x = X(m);
    g += '<line x1="' + x.toFixed(1) + '" y1="' + T + '" x2="' + x.toFixed(1) + '" y2="' + (H - B)
       + '" stroke="var(--line)" stroke-width="1"/>';
    g += '<text x="' + x.toFixed(1) + '" y="' + (H - B + 14) + '" text-anchor="middle" font-size="9" '
       + 'font-family="var(--mono)" fill="var(--text3)">' + m.toFixed(1) + 'x</text>';
  }
  // the zero line: the whole point of the picture is where each curve crosses it
  const y0 = Y(0);
  g += '<line x1="' + L + '" y1="' + y0.toFixed(1) + '" x2="' + (W - R) + '" y2="' + y0.toFixed(1)
     + '" stroke="var(--amber)" stroke-width="1" stroke-dasharray="4 4" opacity=".85"/>';
  g += '<text x="' + (W - R - 4) + '" y="' + (y0 - 6).toFixed(1) + '" text-anchor="end" font-size="9" '
     + 'font-family="var(--mono)" fill="var(--amber)">EV = 0 &#183; break-even</text>';

  const clip = v => Math.max(lo, Math.min(hi, v));
  const path = s => "M" + s.points.map(p => X(p[0]).toFixed(1) + "," + Y(clip(p[1])).toFixed(1)).join(" L");
  // ONE area fill, on the reference venue. Seven stacked fills at opacity .085 accumulate into an
  // opaque slab below the zero line and destroy the very crossing the chart exists to show, so the
  // emphasis goes to pump.fun (the venue every KPI quotes) and the rest are lines.
  const lead = series.find(s => s.venue_id === "pump.fun") || series[0];
  const leadColour = PALETTE[st.ev_curves.series.findIndex(s => s.venue_id === lead.venue_id) % PALETTE.length];
  g += '<path d="' + path(lead) + ' L' + X(xs[1]).toFixed(1) + ',' + y0.toFixed(1)
     + ' L' + X(xs[0]).toFixed(1) + ',' + y0.toFixed(1) + ' Z" fill="' + leadColour + '" opacity=".09"/>';

  series.forEach(s => {
    const i = st.ev_curves.series.findIndex(q => q.venue_id === s.venue_id);
    const c = PALETTE[i % PALETTE.length];
    const isLead = s.venue_id === lead.venue_id;
    g += '<path d="' + path(s) + '" fill="none" stroke="' + c + '" stroke-width="' + (isLead ? 2 : 1.25)
       + '" opacity="' + (isLead ? 1 : .72) + '"/>';
    // the break-even crossing m* — where this venue stops being worth buying
    const ms = s.breakeven_premium_m_star;
    if (ms !== null && ms >= xs[0] && ms <= xs[1]){
      g += '<circle cx="' + X(ms).toFixed(1) + '" cy="' + y0.toFixed(1) + '" r="' + (isLead ? 4 : 2.8)
         + '" fill="' + c + '" stroke="var(--bg)" stroke-width="1.5"/>';
    }
    const last = s.points[s.points.length - 1];
    g += '<circle cx="' + X(last[0]).toFixed(1) + '" cy="' + Y(clip(last[1])).toFixed(1)
       + '" r="' + (isLead ? 3.5 : 2) + '" fill="' + c + '"/>';
  });
  // name the emphasised curve at its own end point
  const le = lead.points[lead.points.length - 1];
  g += '<text x="' + (X(le[0]) - 8).toFixed(1) + '" y="' + (Y(clip(le[1])) - 11).toFixed(1)
     + '" text-anchor="end" font-size="10" font-family="var(--mono)" fill="' + leadColour + '">'
     + lead.venue_id + ' m*=' + lead.breakeven_premium_m_star.toFixed(4) + '</text>';
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  svg.innerHTML = g;

  document.getElementById("legend").innerHTML = (st.ev_curves.series || []).map((s, i) => {
    const c = PALETTE[i % PALETTE.length];
    return '<span class="lg' + (OFF.has(s.venue_id) ? " off" : "") + '" data-venue="' + esc(s.venue_id) + '">'
      + '<span class="sw" style="background:' + c + '"></span>' + esc(s.venue_id)
      + ' <span class="mstar">m*=' + nf(s.breakeven_premium_m_star, 3)
      + (s.caveats.length ? ' ⚠' : '') + '</span></span>';
  }).join("");
}
document.getElementById("legend").addEventListener("click", e => {
  const el = e.target.closest("[data-venue]"); if (!el || !LAST) return;
  const v = el.dataset.venue; OFF.has(v) ? OFF.delete(v) : OFF.add(v);
  drawChart(LAST);
});

// ---- the LIVE series ------------------------------------------------------------------------------
// The EV curve above is algebra and is supposed to sit still. THIS is the arrival process, bucketed by
// each taped row's own observed timestamp, and it must visibly redraw as minutes land. The window ends
// at the CURRENT minute, so if the collector dies the line walks down to zero instead of freezing —
// a stall has to look like a stall.
let LAST_POLL_MS = 0, LAST_GRADS = null;

function drawLive(st){
  const svg = document.getElementById("livechart");
  const ls = st.live_series || {};
  const B = ls.buckets || [];
  const W = 1000, H = 250, L = 46, R = 62, T = 16, BM = 28, RAIL = 28;
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  if (!B.length){
    svg.innerHTML = '<text x="' + (W / 2) + '" y="' + (H / 2) + '" text-anchor="middle" font-size="11" '
      + 'font-family="var(--mono)" fill="var(--text3)">'
      + esc(ls.empty_reason || "no rows on the tape — nothing drawn, and nothing invented")
      + '</text>';
    return;
  }
  const axisY = H - BM, railTop = axisY - RAIL, n = B.length;
  const X = i => (n === 1) ? (L + (W - L - R) / 2) : L + i / (n - 1) * (W - L - R);
  let peak = 0; B.forEach(b => { if (b.creates > peak) peak = b.creates; });
  const hi = Math.max(peak * 1.15, 5);
  const Y = v => railTop - (Math.max(0, v) / hi) * (railTop - T);

  let g = "";
  // horizontal gridlines + creates/min labels
  for (let i = 0; i <= 4; i++){
    const v = hi * i / 4, y = Y(v);
    g += '<line x1="' + L + '" y1="' + y.toFixed(1) + '" x2="' + (W - R) + '" y2="' + y.toFixed(1)
       + '" stroke="var(--line)" stroke-width="1"/>'
       + '<text x="' + (L - 7) + '" y="' + (y + 3).toFixed(1) + '" text-anchor="end" font-size="9" '
       + 'font-family="var(--mono)" fill="var(--text3)">' + Math.round(v) + '</text>';
  }
  // vertical gridlines + UTC minute labels
  const step = Math.max(1, Math.ceil(n / 9));
  for (let i = 0; i < n; i += step){
    const x = X(i);
    g += '<line x1="' + x.toFixed(1) + '" y1="' + T + '" x2="' + x.toFixed(1) + '" y2="' + axisY
       + '" stroke="var(--line)" stroke-width="1"/>'
       + '<text x="' + x.toFixed(1) + '" y="' + (axisY + 15) + '" text-anchor="middle" font-size="9" '
       + 'font-family="var(--mono)" fill="var(--text3)">'
       + esc(String(B[i].minute_utc).slice(11, 16)) + '</text>';
  }
  g += '<line x1="' + L + '" y1="' + axisY + '" x2="' + (W - R) + '" y2="' + axisY
     + '" stroke="var(--line2)" stroke-width="1"/>';

  // the session mean, so the eye can see whether the current minute is fast or slow
  const mean = ls.creates_per_min_session;
  if (mean !== null && mean !== undefined && isFinite(mean)){
    const ym = Y(mean);
    g += '<line x1="' + L + '" y1="' + ym.toFixed(1) + '" x2="' + (W - R) + '" y2="' + ym.toFixed(1)
       + '" stroke="var(--text3)" stroke-width="1" stroke-dasharray="3 5" opacity=".8"/>'
       + '<text x="' + (W - R + 5) + '" y="' + (ym + 3).toFixed(1) + '" font-size="9" '
       + 'font-family="var(--mono)" fill="var(--text3)">mean ' + mean.toFixed(1) + '</text>';
  }

  // creates per minute: filled area + 2px line. The minute now in progress is INCOMPLETE, so it is
  // drawn dashed and excluded from the fill — an unfinished minute is not a collapse in launches.
  const pts = B.map((b, i) => [X(i), Y(b.creates)]);
  const partial = !!B[n - 1].partial;
  const solid = partial ? pts.slice(0, n - 1) : pts;
  if (solid.length){
    const d = "M" + solid.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L");
    g += '<path d="' + d + ' L' + solid[solid.length - 1][0].toFixed(1) + ',' + railTop
       + ' L' + solid[0][0].toFixed(1) + ',' + railTop + ' Z" fill="var(--mint)" opacity=".09"/>';
    g += '<path d="' + d + '" fill="none" stroke="var(--mint)" stroke-width="2" '
       + 'stroke-linejoin="round" stroke-linecap="round"/>';
  }
  if (partial && solid.length){
    const a = solid[solid.length - 1], b = pts[n - 1];
    g += '<path d="M' + a[0].toFixed(1) + ',' + a[1].toFixed(1) + ' L' + b[0].toFixed(1) + ','
       + b[1].toFixed(1) + '" fill="none" stroke="var(--mint)" stroke-width="2" '
       + 'stroke-dasharray="3 3" opacity=".55"/>';
  }

  // GRADUATIONS get their own lane. They are rare and they are the point, so they are never averaged
  // into the creates line — each one is a discrete amber mark on the minute it actually landed.
  g += '<text x="' + (L - 7) + '" y="' + (axisY - 7) + '" text-anchor="end" font-size="9" '
     + 'font-family="var(--mono)" fill="var(--amber)">grad</text>';
  B.forEach((b, i) => {
    if (!b.graduations) return;
    const x = X(i), h = 7 + 5 * Math.min(b.graduations, 3), ty = axisY - h;
    g += '<line x1="' + x.toFixed(1) + '" y1="' + axisY + '" x2="' + x.toFixed(1) + '" y2="'
       + ty.toFixed(1) + '" stroke="var(--amber)" stroke-width="1.5" opacity=".85"/>'
       + '<path d="M' + x.toFixed(1) + ',' + (ty - 4.6).toFixed(1) + ' L' + (x + 3.7).toFixed(1) + ','
       + ty.toFixed(1) + ' L' + x.toFixed(1) + ',' + (ty + 4.6).toFixed(1) + ' L' + (x - 3.7).toFixed(1)
       + ',' + ty.toFixed(1) + ' Z" fill="var(--amber)"/>';
    if (b.graduations > 1){
      g += '<text x="' + x.toFixed(1) + '" y="' + (ty - 8).toFixed(1) + '" text-anchor="middle" '
         + 'font-size="8.5" font-family="var(--mono)" fill="var(--amber)">' + b.graduations + '</text>';
    }
  });

  // the emphasised endpoint — the dot the eye tracks between polls
  const e = pts[n - 1], last = B[n - 1];
  g += '<circle cx="' + e[0].toFixed(1) + '" cy="' + e[1].toFixed(1)
     + '" r="7" fill="var(--mint)" opacity=".18"/>'
     + '<circle cx="' + e[0].toFixed(1) + '" cy="' + e[1].toFixed(1)
     + '" r="3.6" fill="var(--mint)" stroke="var(--bg)" stroke-width="1.5"/>'
     + '<text x="' + (W - R + 5) + '" y="' + (e[1] - 6).toFixed(1) + '" font-size="10" '
     + 'font-family="var(--mono)" fill="var(--mint)">' + last.creates + '/min</text>'
     + '<text x="' + (W - R + 5) + '" y="' + (e[1] + 7).toFixed(1) + '" font-size="8.5" '
     + 'font-family="var(--mono)" fill="var(--text3)">' + (partial ? "partial" : "closed") + '</text>';

  svg.innerHTML = g;
}

function renderLive(st){
  const ls = st.live_series || {};
  const secs = ls.seconds_since_last_row;
  const pulse = document.getElementById("pulse");
  pulse.className = "pulse " + (secs === null || secs === undefined ? "dead"
    : (secs < 30 ? "on" : (secs < 180 ? "stale" : "dead")));

  const chain = ls.chain_ok === true ? '<span class="badge b-mint">CHAIN VERIFIED</span>'
    : (ls.chain_ok === false ? '<span class="badge b-red">CHAIN REFUSED</span>'
                             : '<span class="badge b-dim">NO CHAIN</span>');
  document.getElementById("livechain").innerHTML = chain
    + ' <span class="mono">seq ' + int(ls.head_sequence) + ' &middot; '
    + esc(String(ls.head_sha256 || "").slice(0, 10)) + ' &middot; last row '
    + (secs === null || secs === undefined ? EM : secs.toFixed(1) + "s") + ' ago</span>';

  const cells = [
    ["Tape rows", int(ls.head_sequence), "hash-chained", "", ""],
    ["Creates observed", int(ls.cumulative_creates), "this session", "", ""],
    ["Graduations observed", int(ls.graduations_observed), "this session", "hero", "gradcell"],
    ["Creates / min", nf(ls.creates_per_min_recent, 1),
      "mean of last " + int(ls.recent_rate_window_minutes) + " closed min", "pos", ""],
    ["Peak / min", int(ls.peak_creates_per_min), "best closed minute", "", ""],
    // nf() already returns the em-dash for null/undefined/non-finite, and isFinite(null) is TRUE in
    // JS, so the unit is appended off nf's result rather than off an isFinite guard that null passes.
    ["Session span", nf(ls.session_span_minutes, 1) === EM ? EM : nf(ls.session_span_minutes, 1) + " min",
      "first row to last", "", ""],
    ["Window drawn", ls.buckets_available ? int(ls.buckets_available) + " min" : EM,
      (ls.coverage && ls.coverage.truncated_tail) ? "bounded read — earlier omitted"
                                                  : "of " + int(ls.window_minutes_requested) + " requested", "", ""],
  ];
  document.getElementById("livestrip").innerHTML = cells.map(c =>
    '<div class="lcell"' + (c[4] ? ' id="' + c[4] + '"' : "") + '>'
    + '<div class="lbl">' + esc(c[0]) + '</div>'
    + '<div class="lval ' + c[3] + '">' + c[1] + '</div>'
    + '<div class="sub">' + esc(c[2]) + '</div></div>').join("");

  // flash the hero when a graduation actually lands
  const gr = ls.graduations_observed;
  if (LAST_GRADS !== null && isFinite(gr) && gr > LAST_GRADS){
    const cell = document.getElementById("gradcell");
    if (cell){ cell.classList.remove("bump"); void cell.offsetWidth; cell.classList.add("bump"); }
  }
  if (isFinite(gr)) LAST_GRADS = gr;

  drawLive(st);

  // the flow ratio, kept visually apart from p and labelled as what it is
  const fr = ls.flow_ratio_graduations_per_1000_creates;
  document.getElementById("flowval").textContent =
    isFinite(fr) && fr !== null ? nf(fr, 1) + " / 1,000 creates" : EM;
  document.getElementById("flowlbl").textContent = ls.flow_ratio_label || EM;

  // The MEASURED create -> graduation lag. This is on screen because it is the evidence for the
  // warning beside it: an earlier draft justified the refusal by asserting the graduating coins were
  // "created hours or days ago", which this tape contradicts outright. Show the number, not the story.
  const lg = ls.create_to_graduation_latency || {};
  document.getElementById("lagline").innerHTML = (lg.matched_pairs
    ? 'measured create&nbsp;&rarr;&nbsp;graduation lag: median <span class="mono warn">'
      + nf(lg.median_seconds, 1) + 's</span> <span class="dim">(' + int(lg.median_slots)
      + ' slots)</span>, ' + int(lg.same_transaction_as_the_create) + ' of '
      + int(lg.matched_pairs) + ' in the <span class="warn">same transaction</span> as the create. '
      + int(lg.graduations_with_no_taped_create) + ' graduations had no taped create.'
    : 'create &rarr; graduation lag: no matched pairs on the tape yet');
  document.getElementById("cohortp").innerHTML = (ls.cohort_p_reference || []).map(r =>
    '<div class="pline"><span class="dim">' + esc(r.venue_id) + '</span>'
    + '<span>' + pct(r.graduation_rate_p, 4) + ' <span class="dim">'
    + int(r.p_grads) + ' / ' + int(r.p_n) + '</span></span></div>').join("")
    + '<div class="sub" style="margin-top:6px">' + esc(ls.cohort_p_note || "") + '</div>';
  document.getElementById("flownote").innerHTML = '<b class="warn">Read this before quoting the ratio.</b> '
    + esc(ls.flow_ratio_note || "");

  const cov = ls.coverage || {};
  document.getElementById("livefoot").textContent =
    "Buckets are cut on each taped row's own observed timestamp, from " + esc(cov.from_utc || EM)
    + " to " + esc(cov.to_utc || EM) + " UTC. " + esc(cov.note || "")
    + ". Session " + esc(ls.session_first_utc || EM) + " → " + esc(ls.session_last_utc || EM)
    + ", " + int(ls.window_creates) + " creates and " + int(ls.window_graduations)
    + " graduations inside the drawn window"
    // guarded: an empty match map would otherwise leave a dangling ", ." in the sentence
    + (Object.keys(ls.graduations_matched_to_a_taped_create || {}).length
        ? ", " + Object.entries(ls.graduations_matched_to_a_taped_create)
            .map(([v, m]) => v + " " + m + " matched to a create we also taped").join(", ")
        : "")
    + ". The window ends at the current UTC minute, so a dead collector walks the line to zero"
    + " rather than freezing it.";
}

setInterval(() => {
  const el = document.getElementById("ago");
  if (!el || !LAST_POLL_MS) return;
  const s = (Date.now() - LAST_POLL_MS) / 1000;
  el.textContent = s.toFixed(0) + "s";
  el.className = s > 12 ? "neg" : "warn";
}, 1000);

// ---- render ---------------------------------------------------------------------------------------
function render(st){
  LAST = st;
  LAST_POLL_MS = Date.now();
  renderLive(st);
  // First paint only: hide the instant-liquidity configs. p > 0.5 is venues.py's own MAX_LOTTERY_P —
  // above it the config is not a graduation lottery at all, so its EV sits two orders of magnitude
  // above every real curve. Hidden by DEFAULT, never dropped: one click puts it back.
  if (!SCALED){
    SCALED = true;
    (st.ev_curves.series || []).forEach(s => { if (s.p > 0.5) OFF.add(s.venue_id); });
  }
  const k = st.kpis || {};
  document.getElementById("hdr").innerHTML =
    esc(st.generated_utc) + "<br>registry " + esc((st.provenance.registry_sha256 || "").slice(0, 12))
    + " &middot; idl " + esc(st.provenance.pinned_idl_status);

  document.getElementById("strip").innerHTML = [
    ["Venues", int(k.venues_in_registry), k.venues_verified_onchain + " verified on-chain", ""],
    ["Full economics", int(k.venues_with_full_economics),
      k.venues_refusing_a_multiple + " refuse a multiple", ""],
    ["Credible ranks", int(k.credible_ranks), "census large enough to believe", ""],
    ["pump.fun m*", nf(k.pumpfun_breakeven_m_star, 4), "break-even entry premium", "warn"],
    ["EV at floor", pct(k.pumpfun_ev_at_floor, 2), "pump.fun, m = 1.00", sign(k.pumpfun_ev_at_floor)],
    ["LaunchLab curves", int(k.launchlab_curves), "PoolState accounts, all time", ""],
    ["Graduations", int(k.launchlab_graduations), "p = " + pct(k.launchlab_p, 4), ""],
    ["Label multiple", nf(k.label_multiple_vs_b11a, 1) + "x", "vs b11a's 82 labels", "pos"],
    ["Prize band (X−1)p", nf(k.prize_term_band.min, 3) + "–" + nf(k.prize_term_band.max, 3),
      k.prize_term_band.n_credible + " credible venues", "warn"],
    ["Tape rows", int(k.tape_rows), "hash-chained", k.tape_rows ? "" : "dim"],
    ["Census cost", k.census_cost_usd === 0 ? "$0.00" : EM, "free public RPC", "pos"],
  ].map(c => '<div class="cell"><div class="lbl">' + esc(c[0]) + '</div>'
    + '<div class="val ' + c[3] + '">' + c[1] + '</div>'
    + '<div class="sub">' + esc(c[2]) + '</div></div>').join("");

  // --- EV curve
  const cv = st.ev_curves;
  drawChart(st);
  document.getElementById("evnote").textContent =
    "STATIC BY CONSTRUCTION · " + cv.series.length + " venues · m = entry price / floor price · "
    + cv.formula_breakeven;
  document.getElementById("evfoot").innerHTML =
    "<b>This chart does not move, and that is correct.</b> Every input is a constant: X is curve algebra, p is a census, the toll is a published fee. It redraws only when the census is re-measured. The moving picture is the live-activity panel above. "
    + esc(cv.prize_term_band.note) + " Band: <span class=\"mono warn\">"
    + nf(cv.prize_term_band.min, 4) + " – " + nf(cv.prize_term_band.max, 4)
    + "</span>. " + esc(st.provenance.floor_result)
    + " Click a legend entry to toggle a series; ⚠ flags a rank the registry itself caveats, and the"
    + " two near-certain-completion configs start hidden because they are instant-liquidity vehicles,"
    + " not graduation lotteries.";

  // --- venue table
  document.getElementById("vnote").textContent = st.venues.length + " registry rows · ranked by m* descending, refusing venues last";
  document.getElementById("vbody").innerHTML = st.venues.map(v => {
    const refuses = !!v.graduation_multiple_refusal;
    const cav = v.caveats || [];
    let badge;
    if (refuses) badge = '<span class="badge b-red" title="' + esc(v.graduation_multiple_refusal) + '">REFUSED</span>';
    else if (!v.tradeable) badge = '<span class="badge b-amber">NO p</span>';
    else if (!cav.length) badge = '<span class="badge b-mint">CREDIBLE</span>';
    else badge = '<span class="badge b-amber" title="' + esc(cav.join(" — ")) + '">CAVEAT ×' + cav.length + '</span>';
    const id = v.platform_config || v.program_id;
    const xcell = refuses
      ? '<span class="dim" title="' + esc(v.graduation_multiple_refusal) + '">' + EM + '</span>'
      : nf(v.graduation_multiple_x, 4) + "x";
    return '<tr class="' + (refuses || !v.tradeable ? "muted" : "") + '">'
      + '<td class="l"><div class="tok">' + monogram(id, v.venue_id)
        + '<div class="tok-txt"><div class="tok-sym">' + esc(v.venue_id) + copyCell(id) + '</div>'
        + '<div class="tok-sub" title="' + esc(v.display_name) + '">' + esc(trunc(id, 6, 6))
        + ' · ' + esc(v.quote_symbol) + '</div></div></div></td>'
      + '<td class="l dim" style="font-size:10.5px">' + esc(v.curve_kind.replace(/_/g, " ")) + '</td>'
      + '<td>' + xcell + '</td>'
      + '<td>' + (v.graduation_rate_p === null ? EM : pct(v.graduation_rate_p, 4)) + '</td>'
      + '<td class="dim">' + int(v.p_n) + '</td>'
      + '<td class="dim">' + int(v.p_grads) + '</td>'
      + '<td>' + (v.toll_per_side === null ? EM : pct(v.toll_per_side, 2)) + '</td>'
      + '<td>' + (v.toll_round_trip === null ? EM : pct(v.toll_round_trip, 2)) + '</td>'
      + '<td>' + nf(v.prize_term_Xm1p, 4) + '</td>'
      + '<td class="warn">' + nf(v.breakeven_premium_m_star, 4) + '</td>'
      + '<td class="' + sign(v.ev_at_floor_m_1) + '">' + pct(v.ev_at_floor_m_1, 2) + '</td>'
      + '<td class="l">' + badge + '</td></tr>';
  }).join("");
  document.getElementById("vfoot").innerHTML =
    "X is <b>derived</b> from measured curve constants by " + esc(st.provenance.law)
    + " — never a market outcome. A REFUSED multiple is a venue whose curve this registry cannot"
    + " close in closed form; hover the em-dash for the reason. Live arena fill books "
    + pct(st.toll_discrepancy.arena_fill_py_round_trip, 1) + " round trip vs pump.fun's measured "
    + pct(st.toll_discrepancy.pumpfun_measured_protocol_round_trip, 1) + ": "
    + esc(st.toll_discrepancy.verdict) + ".";

  // --- census
  const c = st.census;
  if (!c.available){
    document.getElementById("census").innerHTML = '<div class="err">census unavailable: ' + esc(c.error) + '</div>';
    document.getElementById("censusbars").innerHTML = "";
    document.getElementById("censusnote").textContent = "";
  } else {
    document.getElementById("census").innerHTML = [
      ["Measured", esc(c.measured_utc)],
      ["Source", esc(c.source)],
      ["Method", esc(c.method)],
      ["Total curves", int(c.total_curves)],
      ["Graduated", int(c.graduations)],
      ["Graduation rate p", pct(c.graduation_rate_p, 4)],
      ["Elapsed", nf(Object.values(c.elapsed_seconds || {}).reduce((a, b) => a + b, 0), 1) + " s"],
      ["Cost", c.cost_usd === 0 ? "$0.00" : EM],
    ].map(r => '<div class="kv"><span class="k">' + r[0] + '</span><span class="v">' + r[1] + '</span></div>').join("");
    const cols = {funding: "var(--text3)", awaiting_migration: "var(--amber)", migrated: "var(--mint)"};
    const tot = c.total_curves || 1;
    document.getElementById("censusbars").innerHTML = Object.entries(c.counts || {}).map(([k2, v]) => {
      const w = Math.max(v / tot * 100, v > 0 ? 0.35 : 0);
      return '<div class="barrow"><span class="dim mono" style="font-size:9.5px">' + esc(k2.slice(0, 9)) + '</span>'
        + '<span class="bartrack"><span class="barfill" style="width:' + w.toFixed(3) + '%;background:' + cols[k2] + '"></span></span>'
        + '<span class="mono" style="text-align:right;font-size:10.5px">' + int(v)
        + ' <span class="dim">' + (v / tot * 100).toFixed(3) + '%</span></span></div>';
    }).join("");
    const cc = c.cross_check || {};
    document.getElementById("censusnote").textContent =
      (c.derived && c.derived.survivorship || "") + (cc.note ? " " + cc.note : "");
  }

  // --- ledger
  const L = st.label_ledger;
  document.getElementById("lednote").textContent = L.multiple ? L.multiple + "x more labels" : EM;
  document.getElementById("ledger").innerHTML = [
    ["b11a graduations", int(L.b11a.graduations) + " <span class=\"dim\">of " + int(L.b11a.creates) + " creates</span>"],
    ["b11a floor cohort", int(L.b11a.floor_cohort) + " <span class=\"neg\">→ " + int(L.b11a.floor_cohort_positives) + " positives</span>"],
    ["Curves below launch price", '<span class="pos">' + int(L.b11a.curves_that_traded_below_launch_price)
      + " <span class=\"dim\">of " + int(L.b11a.curves_with_price_history) + "</span></span>"],
    ["LaunchLab curves", int(L.launchlab.curves)],
    ["LaunchLab graduations", '<span class="pos">' + int(L.launchlab.graduations) + "</span>"],
    ["Label multiple", '<span class="pos">' + nf(L.multiple, 1) + "x</span>"],
    ["Cost", L.launchlab.cost_usd === 0 ? '<span class="pos">$0.00</span>' : EM],
  ].map(r => '<div class="kv"><span class="k">' + r[0] + '</span><span class="v">' + r[1] + '</span></div>').join("");
  document.getElementById("unlocks").innerHTML =
    '<li><b>The wall:</b> ' + esc(L.b11a.wall) + '</li>'
    + '<li><b>Why comparable:</b> ' + esc(L.launchlab.why_comparable) + '</li>'
    + (L.unlocks || []).filter(Boolean).map(u => '<li>' + esc(u) + '</li>').join("");

  // --- tape
  const t = st.tape;
  const hz = t.health || {};
  const chainBadge = t.chain_verified === false
    ? '<span class="badge b-red">CHAIN REFUSED</span>'
    : (t.rows ? '<span class="badge b-mint">CHAIN VERIFIED</span>' : '<span class="badge b-dim">NO ROWS</span>');
  const healthBadge = hz.status === "CONNECTED" ? '<span class="badge b-mint">CONNECTED</span>'
    : (hz.status ? '<span class="badge b-amber">' + esc(hz.status) + '</span>' : '<span class="badge b-dim">UNKNOWN</span>');
  document.getElementById("tapenote").innerHTML =
    chainBadge + " " + healthBadge + ' <span class="mono">' + int(t.rows) + " rows · "
    + Object.entries(t.per_venue || {}).map(([v, cts]) =>
        esc(v) + " " + cts.create + "c/" + cts.graduation + "g").join(" · ") + "</span>";

  const rows = [].concat(t.recent_graduations || [], t.recent_creates || [])
    .sort((a, b) => (b.received_unix_nanos || 0) - (a.received_unix_nanos || 0)).slice(0, 60);
  document.getElementById("tbody").innerHTML = rows.length ? rows.map(r => {
    const id = r.mint || r.pool_id || "";
    const kb = r.kind === "graduation" ? '<span class="badge b-mint">GRADUATED</span>'
                                       : '<span class="badge b-dim">CREATE</span>';
    return '<tr><td class="l"><div class="tok">' + monogram(id, r.symbol || r.venue)
      + '<div class="tok-txt"><div class="tok-sym">' + esc(r.symbol || EM) + copyCell(id) + '</div>'
      + '<div class="tok-sub" title="' + esc(r.name || "") + '">' + esc(trunc(id, 6, 6)) + '</div></div></div></td>'
      + '<td class="l dim" style="font-size:10.5px">' + esc(r.venue) + '</td>'
      + '<td class="l">' + kb + '</td>'
      + '<td class="dim">' + int(r.slot) + '</td>'
      + '<td class="l dim" style="font-family:var(--mono);font-size:10.5px">' + esc(r.received_utc || EM) + '</td>'
      + '<td class="l dim" style="font-family:var(--mono);font-size:10px">' + esc(trunc(r.signature, 8, 8))
        + " " + copyCell(r.signature) + '</td>'
      + '<td class="dim">' + int(r.sequence) + '</td></tr>';
  }).join("") : '<tr><td class="l dim" colspan="7">' + esc(t.empty_reason || t.refused || "no rows") + '</td></tr>';
  document.getElementById("tapefoot").textContent =
    t.tape_path + " · " + esc(t.recent_window_note || "")
    + (t.span_hours !== null && t.span_hours !== undefined ? " · span " + t.span_hours + "h" : "");

  document.getElementById("foot").textContent = st.footer;
  document.getElementById("err").innerHTML = "";
}

async function poll(){
  try {
    const r = await fetch("/api/state", {cache: "no-store"});
    const st = await r.json();
    if (st.error) { document.getElementById("err").innerHTML = '<div class="err">' + esc(st.error) + '</div>'; return; }
    render(st);
  } catch (e) {
    document.getElementById("err").innerHTML = '<div class="err">poll failed: ' + esc(e.message) + '</div>';
  }
}

document.getElementById("refresh").addEventListener("click", async ev => {
  const b = ev.target; b.disabled = true; b.textContent = "Measuring…";
  try {
    const r = await fetch("/api/refresh_census", {method: "POST"});
    const j = await r.json();
    b.textContent = j.ok ? "Done · " + j.elapsed_seconds + "s" : "Failed";
    if (!j.ok) document.getElementById("err").innerHTML = '<div class="err">census refresh: ' + esc(j.error) + '</div>';
    await poll();
  } catch (e) {
    b.textContent = "Failed";
    document.getElementById("err").innerHTML = '<div class="err">census refresh: ' + esc(e.message) + '</div>';
  }
  setTimeout(() => { b.disabled = false; b.textContent = "Re-measure"; }, 2500);
});

poll();
setInterval(poll, 5000);
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def do_GET(self):  # noqa: N802
        route = self.path.split("?", 1)[0].rstrip("/")
        if route in ("", "/index.html"):
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif route == "/api/state":
            try:
                body = json.dumps(state_view(), default=str).encode()
            except Exception as exc:  # noqa: BLE001 — never 500 the poll; report it honestly
                body = json.dumps({"error": f"{type(exc).__name__}: {exc}"[:300]}).encode()
            self._send(200, body, "application/json")
        elif route == "/api/health":
            self._send(200, json.dumps({"ok": True, "port": PORT}).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):  # noqa: N802
        """The ONLY network call this server can make, and only when a human clicks it."""
        if self.path.split("?", 1)[0].rstrip("/") != "/api/refresh_census":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        try:
            result = OBS.refresh_census()
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
        if result.get("ok"):
            with _LOCK:
                _CACHE["state"] = None                 # force the next poll to re-read the new census
        self._send(200, json.dumps(result, default=str).encode(), "application/json")

    def log_message(self, *a):                          # silence default request logging
        pass


def main() -> int:
    print(f"Launchpad Observatory: http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
