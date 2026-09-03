#!/usr/bin/env python3
"""Launchpad Observatory server — measured launch-curve economics for every Solana launchpad, on one page.

    python -m scripts.trading_bot.memebot.observatory_server              # 127.0.0.1:8796
    python -m scripts.trading_bot.memebot.observatory_server --port 8798  # anywhere else

WHAT THIS SERVES
----------------
    GET /            the single page (inline CSS + JS; the only external asset is a Google Fonts link)
    GET /api/state   json.dumps(observatory.build_state())
    GET /api/health  {"ok": true, ...}

Nothing else. There is no POST route at all: this process cannot write a file, cannot place an order,
cannot touch a wallet, and makes no network call of its own — `build_state()` is a disk read over the
frozen registry, the on-disk LaunchLab census and the multi-venue tape. Re-measuring the census is a
deliberate `python -m ...observatory --refresh`, never something a page poll can trigger.

THE ARGUMENT THE PAGE MAKES
---------------------------
A pump.fun-style bonding curve is HARD-FLOORED at its launch price — 0 of 3,239 curves in research/b11a
ever traded below their first observed price. So the downside of an on-curve entry is bounded by the
premium you paid above that floor, and the only upside that is not a market forecast is the graduation
multiple X, which is a fixed point of the curve rather than an outcome. That collapses venue selection
to one line of algebra:

    EV(m) = (1 + (X-1)p)/m - 1 - toll         m* = (1 + (X-1)p) / (1 + toll)

and the graph draws it. The finding it makes visible is an efficiency result, not an edge: X spans an
order of magnitude across real venues but the prize term (X-1)p collapses into 0.077-0.286, so every
credible break-even sits between m*=1.055 and m*=1.260. The prize and the base rate cancel out. There
is no free venue — there is only "did you buy near the floor".

HONESTY RULES BAKED INTO THE RENDER
-----------------------------------
* Every economic number is `venues.py`'s. This file computes no economics; it formats them.
* Where the registry REFUSES a number (Boop's multiple: damping_term=31 makes the curve non-CP and the
  two plain-CP readings disagree 15.15x vs 23.36x; Heaven: no bonding curve exists at all) the page
  prints the refusal TEXT, never a substitute figure.
* An unknown value is an em-dash. No zero-filling, no interpolation.
* A config whose p exceeds venues.MAX_LOTTERY_P is an instant-liquidity vehicle, not a graduation
  lottery, so its enormous apparent EV at the floor is an artefact. Those series start hidden on the
  graph — keyed on the registry constant, not on a hardcoded venue list — and one click restores them.
* An empty tape renders as an empty tape with the collector's own reason, never as a fabricated row.

READ-ONLY. Bound to 127.0.0.1 (8795 is the arena dashboard, 8794 the X2 cost dashboard).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import observatory as OBS
from . import venues as V

HOST, PORT = "127.0.0.1", 8796
STATE_TTL = 4.0                  # server-side memo; build_state() is a disk read, but not a free one

_LOCK = threading.Lock()
_CACHE: dict = {"at": 0.0, "state": None}


def state_view(*, force: bool = False) -> dict:
    """build_state() behind a short TTL so N browser tabs cost one disk pass, not N."""
    with _LOCK:
        fresh = _CACHE["state"] is not None and (time.time() - _CACHE["at"]) < STATE_TTL
        if fresh and not force:
            return _CACHE["state"]
    state = OBS.build_state()
    with _LOCK:
        _CACHE["at"], _CACHE["state"] = time.time(), state
    return state


# =====================================================================================================
# THE PAGE
# =====================================================================================================
_PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
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
body{background:var(--bg);color:var(--text);font:12.5px/1.45 var(--sans);-webkit-font-smoothing:antialiased;
     text-rendering:optimizeLegibility}
.wrap{max-width:1560px;margin:0 auto;padding:0 20px 64px}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.pos{color:var(--mint)}.neg{color:var(--red)}.warn{color:var(--amber)}.dim{color:var(--text3)}.dim2{color:var(--text2)}

/* ---------- header ---------- */
header.top{display:flex;align-items:flex-end;gap:18px;flex-wrap:wrap;padding:20px 0 14px;
           border-bottom:1px solid var(--line2)}
h1{margin:0;font:600 16px/1.2 var(--sans);letter-spacing:.2px}
.sub{font:400 11px/1.3 var(--sans);color:var(--text3);margin-top:3px}
.hspace{flex:1}
.hmeta{display:flex;gap:22px;align-items:flex-end}
.hm{text-align:right}
.hm .k{font:600 9px/1 var(--sans);letter-spacing:.9px;text-transform:uppercase;color:var(--text3)}
.hm .v{font:500 11.5px/1.4 var(--mono);color:var(--text2);font-variant-numeric:tabular-nums;margin-top:3px}
.live{display:inline-flex;align-items:center;gap:7px;font:700 9.5px/1 var(--mono);letter-spacing:1px;
      color:var(--mint);border:1px solid rgba(62,224,143,.30);background:var(--mint-bg);padding:5px 9px}
.live.stale{color:var(--amber);border-color:rgba(232,177,83,.32);background:var(--amber-bg)}
.live.dead{color:var(--red);border-color:rgba(255,77,77,.32);background:var(--red-bg)}
.dot{width:6px;height:6px;background:currentColor;display:inline-block;animation:pulse 2.2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}

/* ---------- kpi strip ---------- */
.strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));border:1px solid var(--line);
       background:var(--panel);margin-top:16px}
.cell{padding:11px 13px 12px;border-right:1px solid var(--line);min-width:0}
.cell:last-child{border-right:0}
.cell .lbl{font:600 9px/1 var(--sans);letter-spacing:.9px;text-transform:uppercase;color:var(--text3);
           white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cell .val{font:500 17px/1.25 var(--mono);font-variant-numeric:tabular-nums;margin-top:7px;letter-spacing:-.2px}
.cell .sub{font:400 10px/1.35 var(--sans);color:var(--text2);margin-top:4px;
           overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ---------- panels ---------- */
.panel{border:1px solid var(--line);background:var(--panel);margin-top:16px}
.phead{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:9px 13px;background:var(--bg2);
       border-bottom:1px solid var(--line)}
.ptitle{font:600 10px/1 var(--sans);letter-spacing:1.15px;text-transform:uppercase;color:var(--text2)}
.pnote{font:400 10px/1.4 var(--sans);color:var(--text3)}
.phead .hspace{flex:1}
.pbody{padding:12px 13px}
.formula{font:400 11px/1 var(--mono);color:var(--text2);background:var(--panel2);border:1px solid var(--line);
         padding:5px 9px;white-space:nowrap}

/* ---------- chart ---------- */
.chartwrap{position:relative;padding:8px 12px 2px}
svg.chart{display:block;width:100%;height:286px;overflow:visible}
.axis-lbl{font:400 9.5px var(--mono);fill:var(--text3)}
.axis-name{font:500 9.5px var(--sans);fill:var(--text3);letter-spacing:.7px;text-transform:uppercase}
.readout{position:absolute;pointer-events:none;opacity:0;transition:opacity .09s;background:rgba(13,15,18,.97);
         border:1px solid var(--line2);padding:8px 10px;min-width:186px;z-index:5;
         box-shadow:0 6px 22px rgba(0,0,0,.55)}
.readout .rt{font:600 9px/1 var(--sans);letter-spacing:.9px;text-transform:uppercase;color:var(--text3);
             padding-bottom:6px;margin-bottom:6px;border-bottom:1px solid var(--line)}
.rrow{display:flex;align-items:center;gap:7px;font:400 10.5px/1.7 var(--mono);font-variant-numeric:tabular-nums}
.rrow .sw{width:8px;height:8px;flex:0 0 8px}
.rrow .rn{flex:1;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:112px}
.legend{display:flex;flex-wrap:wrap;gap:5px;padding:4px 13px 12px}
.lg{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);background:var(--panel2);
    padding:4px 9px;cursor:pointer;user-select:none;transition:border-color .12s,opacity .12s}
.lg:hover{border-color:var(--line2)}
.lg.off{opacity:.38}
.lg .sw{width:9px;height:9px}
.lg .nm{font:500 10.5px/1 var(--sans)}
.lg .ms{font:400 10px/1 var(--mono);color:var(--text3);font-variant-numeric:tabular-nums}
.lg.off .nm{text-decoration:line-through}
.band{display:flex;gap:12px;align-items:flex-start;margin:0 13px 13px;padding:10px 12px;background:var(--panel2);
      border:1px solid var(--line);border-left:2px solid var(--amber)}
.band .bv{font:500 13px/1.2 var(--mono);color:var(--amber);white-space:nowrap;font-variant-numeric:tabular-nums}
.band .bt{font:400 10.5px/1.55 var(--sans);color:var(--text2)}

/* ---------- tables ---------- */
.tscroll{overflow-x:auto;max-height:none}
table{width:100%;border-collapse:collapse}
thead th{position:sticky;top:0;z-index:2;background:var(--bg2);font:600 9.5px/1 var(--sans);letter-spacing:.8px;
         text-transform:uppercase;color:var(--text3);text-align:left;padding:9px 8px;
         border-bottom:1px solid var(--line2);white-space:nowrap}
thead th.r{text-align:right}
tbody td{padding:8px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
tbody tr:hover{background:var(--row)}
tbody tr.sub-r:hover{background:transparent}
td.num{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
td.nm{white-space:nowrap}
.vname{font:500 12px/1.25 var(--sans)}
.vid{font:400 9.5px/1.3 var(--mono);color:var(--text3);margin-top:2px}
.refuse{padding:0 11px 11px 11px;border-bottom:1px solid var(--line)}
.refuse .rbox{border-left:2px solid var(--amber);background:var(--panel2);padding:8px 11px;
              font:400 11px/1.6 var(--sans);color:var(--text2);max-width:1180px}
.refuse .rk{font:700 9px/1 var(--mono);letter-spacing:.7px;color:var(--amber);text-transform:uppercase;
            display:block;margin-bottom:5px}
.cavlist{margin:5px 0 0;padding:0 0 0 13px;font:400 10px/1.55 var(--sans);color:var(--text3)}
.excl td{background:rgba(255,77,77,.03)}

/* ---------- badges + monogram ---------- */
.badge{display:inline-block;font:700 9px/1 var(--mono);letter-spacing:.6px;text-transform:uppercase;
       padding:3px 7px;border:1px solid;white-space:nowrap}
td.st{white-space:nowrap}
td.st .badge{display:block;margin-bottom:3px}
td.st .badge:last-child{margin-bottom:0}
.b-mint{color:var(--mint);border-color:rgba(62,224,143,.32);background:var(--mint-bg)}
.b-red{color:var(--red);border-color:rgba(255,77,77,.32);background:var(--red-bg)}
.b-amber{color:var(--amber);border-color:rgba(232,177,83,.32);background:var(--amber-bg)}
.b-dim{color:var(--text3);border-color:var(--line2);background:var(--panel2)}
.tok{display:flex;align-items:center;gap:9px;min-width:0}
.mg{width:22px;height:22px;flex:0 0 22px;display:grid;place-items:center;border:1px solid var(--line2);
    font:700 9.5px/1 var(--mono)}
.tk{min-width:0}
.tsym{display:flex;align-items:center;gap:6px;font:600 12px/1.2 var(--sans);white-space:nowrap}
.tmint{font:400 9.5px/1.3 var(--mono);color:var(--text3);margin-top:2px;white-space:nowrap}
.cp{font:700 8px/1 var(--mono);letter-spacing:.5px;color:var(--text3);border:1px solid var(--line2);
    padding:2px 4px;cursor:pointer;transition:color .12s,border-color .12s}
.cp:hover{color:var(--mint);border-color:rgba(62,224,143,.4)}
.cp.done{color:var(--mint);border-color:rgba(62,224,143,.4)}

/* ---------- empty / provenance ---------- */
.empty{padding:34px 18px;text-align:center}
.empty .eh{font:600 12px/1.4 var(--sans);color:var(--text2)}
.empty .eb{font:400 11px/1.65 var(--sans);color:var(--text3);max-width:640px;margin:8px auto 0}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:0}
.gcol{padding:12px 14px;border-right:1px solid var(--line)}
.gcol:last-child{border-right:0}
.gh{font:600 9px/1 var(--sans);letter-spacing:.9px;text-transform:uppercase;color:var(--text3);margin-bottom:9px}
dl.kv{margin:0;display:grid;grid-template-columns:auto 1fr;gap:5px 14px;align-items:baseline}
dl.kv dt{font:400 10px/1.5 var(--sans);color:var(--text3);white-space:nowrap}
dl.kv dd{margin:0;font:400 10.5px/1.5 var(--mono);color:var(--text2);word-break:break-all;
         font-variant-numeric:tabular-nums}
dl.kv dd.pos{color:var(--mint)}dl.kv dd.neg{color:var(--red)}dl.kv dd.warn{color:var(--amber)}
.prose{font:400 11px/1.65 var(--sans);color:var(--text2);max-width:760px}
.prose b{color:var(--text);font-weight:600}
ul.unlocks{margin:8px 0 0;padding-left:15px;font:400 11px/1.7 var(--sans);color:var(--text2)}
ul.unlocks li{margin-bottom:3px}
footer.ft{margin-top:18px;padding-top:12px;border-top:1px solid var(--line);
          font:400 10px/1.6 var(--mono);color:var(--text3);word-break:break-word}
.err{margin-top:16px;border:1px solid rgba(255,77,77,.32);background:var(--red-bg);padding:11px 13px;
     font:400 11px/1.6 var(--mono);color:var(--red)}
</style></head>
<body>
<div class="wrap">

  <header class="top">
    <div>
      <h1>Launchpad Observatory</h1>
      <div class="sub" id="subtitle">measured launch-curve economics across every Solana launchpad</div>
    </div>
    <div class="hspace"></div>
    <div class="hmeta">
      <div class="hm"><div class="k">census measured</div><div class="v" id="h-census">—</div></div>
      <div class="hm"><div class="k">data source</div><div class="v" id="h-src">—</div></div>
      <div class="hm"><div class="k">state built</div><div class="v" id="h-built">—</div></div>
      <div><span class="live" id="h-live"><span class="dot"></span><span id="h-live-t">CONNECTING</span></span></div>
    </div>
  </header>

  <div id="err"></div>

  <!-- 2. KPI STRIP -->
  <div class="strip" id="strip"></div>

  <!-- 3. THE GRAPH -->
  <div class="panel">
    <div class="phead">
      <span class="ptitle">EV vs entry premium</span>
      <span class="pnote">buy near the floor and you are paid; buy high and you are not</span>
      <span class="hspace"></span>
      <span class="formula" id="f-ev">—</span>
      <span class="formula" id="f-be">—</span>
    </div>
    <div class="chartwrap" id="chartwrap">
      <svg class="chart" id="chart" preserveAspectRatio="none"></svg>
      <div class="readout" id="readout"></div>
    </div>
    <div class="legend" id="legend"></div>
    <div class="band" id="band"></div>
  </div>

  <!-- 4. VENUE ECONOMICS -->
  <div class="panel">
    <div class="phead">
      <span class="ptitle">Venue economics</span>
      <span class="pnote">X = graduation multiple · p = graduation rate · m* = break-even entry premium · every number is the frozen registry's</span>
      <span class="hspace"></span>
      <span class="pnote" id="venue-note"></span>
    </div>
    <div class="tscroll">
      <table id="venues">
        <thead><tr>
          <th style="min-width:196px">Venue</th><th>Chain</th>
          <th class="r" title="the deterministic graduation multiple, derived from the curve geometry">X</th>
          <th class="r" title="protocol toll: per side / round trip">Toll</th>
          <th class="r" title="measured graduation rate">p</th>
          <th class="r" title="census size / graduations in it">n/grad</th>
          <th class="r" title="break-even entry premium: m* = (1 + (X-1)p) / (1 + toll)">m*</th>
          <th class="r" title="EV at m = 1, i.e. buying AT the floor">EV @ floor</th>
          <th class="r" title="the prize term (X-1)p — the entire upside of the frame">(X&minus;1)p</th>
          <th>Status</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <!-- 5. LIVE LAUNCHES -->
  <div class="panel">
    <div class="phead">
      <span class="ptitle">Live launches</span>
      <span class="pnote" id="tape-note">—</span>
      <span class="hspace"></span>
      <span id="tape-badges"></span>
    </div>
    <div id="tape-body"></div>
  </div>

  <!-- appendix: the label ledger + provenance -->
  <div class="panel">
    <div class="phead"><span class="ptitle">Label ledger</span>
      <span class="pnote">what the label wall was, and what the free-RPC census just unlocked</span></div>
    <div class="grid2" id="ledger"></div>
  </div>

  <div class="panel">
    <div class="phead"><span class="ptitle">Measurement provenance</span>
      <span class="pnote">every constant on this page traces to one of these</span></div>
    <div class="grid2" id="prov"></div>
  </div>

  <footer class="ft" id="footer">—</footer>
</div>
<script>
"use strict";
/* venues.MAX_LOTTERY_P, injected from the registry so the "instant-liquidity, not a lottery" cut is
   the registry's threshold and never a number typed into this page. */
const MAX_LOTTERY_P = __MAX_LOTTERY_P__;
const REF_VENUE = "pump.fun";     // the reference curve: the only one that carries the area fill
const POLL_MS = 5000;

const S = {data:null, hidden:null, hoverM:null};

/* ---------- formatting: an unknown value is an em-dash, never a zero ---------- */
const DASH = "—";
const isNum = v => typeof v === "number" && isFinite(v);
const fx = (v,d) => isNum(v) ? v.toFixed(d) : DASH;
const fint = v => isNum(v) ? v.toLocaleString("en-US") : DASH;
const fpct = (v,d) => isNum(v) ? (v*100).toFixed(d)+"%" : DASH;
const fsign = (v,d) => isNum(v) ? (v>=0?"+":"")+(v*100).toFixed(d)+"%" : DASH;
const esc = s => String(s==null?"":s).replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const short = (s,h,t) => !s ? DASH : (s.length<=h+t+1 ? s : s.slice(0,h)+"…"+s.slice(-t));

/* ---------- venue colours ---------- */
const VCOLOR = {"pump.fun":"#3ee08f","letsbonk":"#e8b153","raydium_own":"#5aa9f2","moonshot_dbc":"#c86fb0",
                "dbc_gybk":"#8b7bd8","dbc_bkom":"#6fc8c0","dbc_axvr":"#b8814f","dbc_gei2":"#9aa3b0",
                "dbc_7unp":"#ff4d4d"};
const vcol = id => VCOLOR[id] || "#7f8794";

/* deterministic monogram hue from the mint string */
function hueOf(s){ let h=0; for(let i=0;i<(s||"").length;i++) h=(h*31+s.charCodeAt(i))>>>0; return h%360; }

function copyBtn(text){
  return '<span class="cp" data-copy="'+esc(text)+'">COPY</span>';
}
document.addEventListener("click", ev => {
  const el = ev.target.closest(".cp"); if(!el) return;
  const t = el.getAttribute("data-copy") || "";
  const done = () => { el.textContent="COPIED"; el.classList.add("done");
                       setTimeout(()=>{el.textContent="COPY"; el.classList.remove("done");}, 1100); };
  if(navigator.clipboard && navigator.clipboard.writeText){ navigator.clipboard.writeText(t).then(done, done); }
  else { const ta=document.createElement("textarea"); ta.value=t; document.body.appendChild(ta); ta.select();
         try{document.execCommand("copy");}catch(e){} document.body.removeChild(ta); done(); }
});

/* =====================================================================================================
   1. HEADER
   ===================================================================================================== */
function renderHeader(d){
  document.getElementById("subtitle").textContent = d.subtitle || "";
  const c = d.census || {};
  document.getElementById("h-census").textContent = c.available ? (c.measured_utc || DASH) : "MISSING";
  const cost = (d.kpis||{}).census_cost_usd;
  document.getElementById("h-src").textContent =
    (c.available ? "free public RPC" : "no census on disk") + (isNum(cost) ? " · $"+cost.toFixed(0) : "");
  document.getElementById("h-built").textContent = d.generated_utc || DASH;

  const h = (d.tape||{}).health || {};
  const pill = document.getElementById("h-live"), txt = document.getElementById("h-live-t");
  pill.className = "live" + (h.ok ? "" : (h.status ? " stale" : " dead"));
  txt.textContent = h.status ? String(h.status) : (d.tape && d.tape.rows ? "TAPE IDLE" : "NO COLLECTOR");
  pill.title = [h.reason, isNum(h.age_s) ? "last event "+h.age_s.toFixed(1)+"s ago" : null]
                 .filter(Boolean).join(" · ");
}

/* =====================================================================================================
   2. KPI STRIP
   ===================================================================================================== */
function bestCredible(d){
  const ids = new Set(((d.ev_curves||{}).credible_venue_ids)||[]);
  let best = null;
  for(const s of ((d.ev_curves||{}).series)||[]){
    if(!ids.has(s.venue_id)) continue;
    if(!best || s.breakeven_premium_m_star > best.breakeven_premium_m_star) best = s;
  }
  return best;
}
function renderStrip(d){
  const k = d.kpis||{}, c = d.census||{}, t = d.tape||{}, best = bestCredible(d);
  const grads = ((t.per_venue)||{});
  let taped = 0; for(const v of Object.values(grads)) taped += (v.graduation||0);
  const cells = [
    ["Venues tracked", fint(k.venues_in_registry),
     fint(k.venues_with_full_economics)+" with full economics · "+
     fint(k.venues_refusing_a_multiple)+" refuse an X", ""],
    ["Curves censused", fint(k.launchlab_curves),
     c.available ? "LaunchLab PoolState · status@17" : "no census on disk", ""],
    ["Graduation labels", fint(k.launchlab_graduations),
     "permanent, survivorship-free", "pos"],
    ["Graduation rate p", isNum(k.launchlab_p) ? (k.launchlab_p*100).toFixed(4)+"%" : DASH,
     fint(k.launchlab_graduations)+" of "+fint(k.launchlab_curves)+" curves", ""],
    ["Best break-even m*", best ? fx(best.breakeven_premium_m_star,4) : DASH,
     best ? esc(best.venue_id)+" · credible venues only ("+fint((k.prize_term_band||{}).n_credible)+")"
          : "no credible venue", "pos"],
    ["Labels vs b11a", isNum(k.label_multiple_vs_b11a) ? k.label_multiple_vs_b11a.toFixed(1)+"×" : DASH,
     "82 → "+fint(k.launchlab_graduations)+" graduation labels", "pos"],
    /* three states, not two: a verified chain, a BROKEN chain (a real finding, in red), and no tape
       on disk at all — which is an absence, not a failure. */
    ["Live tape rows", fint(k.tape_rows),
     t.chain_verified === true  ? "chain-verified · "+fint(taped)+" graduations" :
     t.chain_verified === false ? "CHAIN BROKEN: "+(t.refused ? "see panel" : "hash mismatch")
                                : "no tape on disk",
     t.chain_verified === false ? "neg" : t.chain_verified === true ? "" : "dim"],
  ];
  document.getElementById("strip").innerHTML = cells.map(([l,v,s,cls]) =>
    '<div class="cell"><div class="lbl">'+esc(l)+'</div>'+
    '<div class="val '+cls+'">'+v+'</div><div class="sub" title="'+esc(s)+'">'+s+'</div></div>').join("");
}

/* =====================================================================================================
   3. THE GRAPH — EV(m) per venue
   ===================================================================================================== */
function visibleSeries(d){
  const all = ((d.ev_curves||{}).series)||[];
  return all.filter(s => !S.hidden.has(s.venue_id));
}
function niceStep(range, target){
  if(!(range>0)) return 1;
  const raw = range/target, mag = Math.pow(10, Math.floor(Math.log10(raw))), n = raw/mag;
  const s = n<=1 ? 1 : n<=2 ? 2 : n<=2.5 ? 2.5 : n<=5 ? 5 : 10;
  return s*mag;
}
function chartGeom(d){
  const svg = document.getElementById("chart");
  const W = Math.max(560, svg.clientWidth || svg.parentNode.clientWidth || 900);
  const H = 286, L = 62, R = 20, T = 16, B = 42;
  const ev = d.ev_curves||{}, mMin = isNum(ev.m_min)?ev.m_min:1, mMax = isNum(ev.m_max)?ev.m_max:2;
  const vis = visibleSeries(d);
  let lo = 0, hi = 0;
  for(const s of vis) for(const p of s.points){ if(!isNum(p[1])) continue;
    if(p[1]<lo) lo=p[1]; if(p[1]>hi) hi=p[1]; }
  if(hi-lo < 0.08){ hi = Math.max(hi, 0.05); lo = Math.min(lo, -0.05); }
  const pad = (hi-lo)*0.08; lo -= pad; hi += pad;
  const x = m => L + (m-mMin)/(mMax-mMin) * (W-L-R);
  const y = e => T + (hi-e)/(hi-lo) * (H-T-B);
  return {svg,W,H,L,R,T,B,mMin,mMax,lo,hi,x,y,vis};
}
function drawChart(d){
  const g = chartGeom(d);
  const parts = [];
  g.svg.setAttribute("viewBox", "0 0 "+g.W+" "+g.H);

  /* y gridlines */
  const step = niceStep(g.hi-g.lo, 6);
  const first = Math.ceil(g.lo/step)*step;
  for(let v=first; v<=g.hi+1e-9; v+=step){
    const yy = g.y(v);
    parts.push('<line x1="'+g.L+'" y1="'+yy.toFixed(1)+'" x2="'+(g.W-g.R)+'" y2="'+yy.toFixed(1)+
               '" stroke="var(--line)" stroke-width="1"/>');
    parts.push('<text class="axis-lbl" x="'+(g.L-9)+'" y="'+(yy+3.2).toFixed(1)+'" text-anchor="end">'+
               (v>=0?"+":"")+(v*100).toFixed(step>=0.5?0:1)+'%</text>');
  }
  /* x gridlines every 0.05, labels every 0.1 */
  for(let m=g.mMin; m<=g.mMax+1e-9; m+=0.05){
    const xx = g.x(m), major = Math.abs((m*100)%10) < 0.5 || Math.abs((m*100)%10-10) < 0.5;
    parts.push('<line x1="'+xx.toFixed(1)+'" y1="'+g.T+'" x2="'+xx.toFixed(1)+'" y2="'+(g.H-g.B)+
               '" stroke="var(--line)" stroke-width="1" opacity="'+(major?1:0.45)+'"/>');
    if(major) parts.push('<text class="axis-lbl" x="'+xx.toFixed(1)+'" y="'+(g.H-g.B+15)+
                         '" text-anchor="middle">'+m.toFixed(2)+'</text>');
  }
  /* axis frame */
  parts.push('<line x1="'+g.L+'" y1="'+(g.H-g.B)+'" x2="'+(g.W-g.R)+'" y2="'+(g.H-g.B)+
             '" stroke="var(--line2)" stroke-width="1"/>');
  parts.push('<line x1="'+g.L+'" y1="'+g.T+'" x2="'+g.L+'" y2="'+(g.H-g.B)+
             '" stroke="var(--line2)" stroke-width="1"/>');

  /* the EV = 0 reference: dashed amber. above it you are paid, below it you are not. */
  if(g.lo <= 0 && g.hi >= 0){
    const y0 = g.y(0);
    parts.push('<line x1="'+g.L+'" y1="'+y0.toFixed(1)+'" x2="'+(g.W-g.R)+'" y2="'+y0.toFixed(1)+
               '" stroke="var(--amber)" stroke-width="1.25" stroke-dasharray="5 4" opacity=".85"/>');
    parts.push('<text class="axis-lbl" x="'+(g.W-g.R-4)+'" y="'+(y0-6).toFixed(1)+
               '" text-anchor="end" fill="var(--amber)" opacity=".9">EV = 0 · break-even</text>');
  }

  const path = s => s.points.filter(p=>isNum(p[1]))
      .map((p,i)=>(i?"L":"M")+g.x(p[0]).toFixed(1)+" "+g.y(p[1]).toFixed(1)).join(" ");

  /* the reference venue carries the ONLY area fill — seven stacked fills read as an opaque slab and
     hide the exact thing the graph exists to show, the zero crossing. */
  const ref = g.vis.find(s => s.venue_id === REF_VENUE);
  if(ref && g.lo <= 0 && g.hi >= 0){
    const y0 = g.y(0);
    /* clipped to ABOVE the zero line: the shaded region is the part of the premium range where the
       reference venue actually pays. Filling under the curve past m* would tint the losing half green. */
    parts.push('<clipPath id="paidclip"><rect x="'+g.L+'" y="'+g.T+'" width="'+(g.W-g.L-g.R)+
               '" height="'+Math.max(0,(y0-g.T)).toFixed(1)+'"/></clipPath>');
    parts.push('<path clip-path="url(#paidclip)" d="'+path(ref)+' L '+g.x(g.mMax).toFixed(1)+' '+y0.toFixed(1)+
               ' L '+g.x(g.mMin).toFixed(1)+' '+y0.toFixed(1)+
               ' Z" fill="'+vcol(REF_VENUE)+'" opacity=".085"/>');
    parts.push('<text class="axis-lbl" x="'+(g.W-g.R-4)+'" y="'+(y0-22).toFixed(1)+
               '" text-anchor="end" fill="'+vcol(REF_VENUE)+'" opacity=".75">\u25b2 paid</text>');
    parts.push('<text class="axis-lbl" x="'+(g.W-g.R-4)+'" y="'+(y0+16).toFixed(1)+
               '" text-anchor="end" fill="var(--red)" opacity=".6">\u25bc not paid</text>');
  }
  for(const s of g.vis){
    const isRef = s.venue_id === REF_VENUE;
    parts.push('<path d="'+path(s)+'" fill="none" stroke="'+vcol(s.venue_id)+'" stroke-width="'+
               (isRef?2:1.25)+'" opacity="'+(isRef?1:.88)+'" stroke-linejoin="round"/>');
  }
  /* every venue's break-even crossing, marked on the zero line */
  for(const s of g.vis){
    const ms = s.breakeven_premium_m_star;
    if(!isNum(ms) || ms < g.mMin || ms > g.mMax || g.lo > 0 || g.hi < 0) continue;
    const cx = g.x(ms), cy = g.y(0), isRef = s.venue_id === REF_VENUE;
    parts.push('<circle cx="'+cx.toFixed(1)+'" cy="'+cy.toFixed(1)+'" r="'+(isRef?4:3)+
               '" fill="var(--bg)" stroke="'+vcol(s.venue_id)+'" stroke-width="'+(isRef?2:1.25)+'"/>');
    if(isRef){
      parts.push('<line x1="'+cx.toFixed(1)+'" y1="'+cy.toFixed(1)+'" x2="'+cx.toFixed(1)+'" y2="'+
                 (g.T+14)+'" stroke="'+vcol(s.venue_id)+'" stroke-width="1" stroke-dasharray="2 3" opacity=".5"/>');
      parts.push('<text class="axis-lbl" x="'+(cx+6).toFixed(1)+'" y="'+(g.T+13)+'" fill="'+vcol(s.venue_id)+
                 '">m* = '+ms.toFixed(4)+'</text>');
    }
  }
  /* emphasised end point on the reference curve */
  if(ref){
    const last = ref.points[ref.points.length-1];
    if(isNum(last[1])){
      parts.push('<circle cx="'+g.x(last[0]).toFixed(1)+'" cy="'+g.y(last[1]).toFixed(1)+
                 '" r="7" fill="'+vcol(REF_VENUE)+'" opacity=".16"/>');
      parts.push('<circle cx="'+g.x(last[0]).toFixed(1)+'" cy="'+g.y(last[1]).toFixed(1)+
                 '" r="3" fill="'+vcol(REF_VENUE)+'"/>');
    }
  }
  /* axis names */
  const ev = d.ev_curves||{};
  parts.push('<text class="axis-name" x="'+((g.L+g.W-g.R)/2).toFixed(0)+'" y="'+(g.H-6)+
             '" text-anchor="middle">'+esc(ev.x_axis||"entry premium m")+'</text>');
  parts.push('<text class="axis-name" transform="translate(13,'+((g.T+g.H-g.B)/2).toFixed(0)+') rotate(-90)"'+
             ' text-anchor="middle">'+esc(ev.y_axis||"expected return")+'</text>');

  if(!g.vis.length){
    parts.push('<text class="axis-name" x="'+(g.W/2).toFixed(0)+'" y="'+((g.H-g.B)/2).toFixed(0)+
               '" text-anchor="middle" fill="var(--text3)">every series is hidden — click a legend chip</text>');
  }
  /* crosshair layer, filled by the hover handler */
  parts.push('<g id="xhair"></g>');
  /* mouse capture */
  parts.push('<rect id="xcap" x="'+g.L+'" y="'+g.T+'" width="'+(g.W-g.L-g.R)+'" height="'+(g.H-g.T-g.B)+
             '" fill="transparent" style="cursor:crosshair"/>');
  g.svg.innerHTML = parts.join("");

  const cap = document.getElementById("xcap");
  cap.addEventListener("mousemove", e => { S.hoverM = mFromEvent(e, g); drawCrosshair(d); });
  cap.addEventListener("mouseleave", () => { S.hoverM = null; drawCrosshair(d); });
  drawCrosshair(d);
}
function mFromEvent(e, g){
  const r = g.svg.getBoundingClientRect();
  const px = (e.clientX - r.left) * (g.W / r.width);
  const m = g.mMin + (px - g.L)/(g.W-g.L-g.R) * (g.mMax-g.mMin);
  return Math.min(g.mMax, Math.max(g.mMin, m));
}
function evAt(s, m){
  /* read the registry's own sampled series; no interpolation of economics, just of the pixel grid */
  const pts = s.points; if(!pts.length) return null;
  const step = (pts[pts.length-1][0]-pts[0][0])/(pts.length-1);
  let i = Math.round((m-pts[0][0])/step);
  i = Math.min(pts.length-1, Math.max(0, i));
  return {m: pts[i][0], ev: pts[i][1]};
}
function drawCrosshair(d){
  const layer = document.getElementById("xhair"), box = document.getElementById("readout");
  if(!layer || !box) return;
  if(S.hoverM == null){ layer.innerHTML = ""; box.style.opacity = 0; return; }
  const g = chartGeom(d), xx = g.x(S.hoverM), out = [];
  out.push('<line x1="'+xx.toFixed(1)+'" y1="'+g.T+'" x2="'+xx.toFixed(1)+'" y2="'+(g.H-g.B)+
           '" stroke="var(--line2)" stroke-width="1"/>');
  const rows = [];
  for(const s of g.vis){
    const v = evAt(s, S.hoverM); if(!v || !isNum(v.ev)) continue;
    const yy = g.y(v.ev);
    if(yy >= g.T-1 && yy <= g.H-g.B+1)
      out.push('<circle cx="'+xx.toFixed(1)+'" cy="'+yy.toFixed(1)+'" r="2.6" fill="'+vcol(s.venue_id)+'"/>');
    rows.push({id:s.venue_id, ev:v.ev});
  }
  layer.innerHTML = out.join("");
  rows.sort((a,b)=>b.ev-a.ev);
  box.innerHTML = '<div class="rt">m = '+S.hoverM.toFixed(3)+' · '+
                  ((S.hoverM-1)*100).toFixed(1)+'% over floor</div>' +
    rows.slice(0,8).map(r => '<div class="rrow"><span class="sw" style="background:'+vcol(r.id)+'"></span>'+
      '<span class="rn">'+esc(r.id)+'</span><span class="'+(r.ev>=0?"pos":"neg")+'">'+
      fsign(r.ev,2)+'</span></div>').join("");
  const wrap = document.getElementById("chartwrap");
  const scale = (g.svg.getBoundingClientRect().width || g.W) / g.W;
  const left = 12 + xx*scale + 14;
  box.style.left = (left + 210 > wrap.clientWidth ? left - 236 : left) + "px";
  box.style.top = "22px";
  box.style.opacity = 1;
}
function renderChartFurniture(d){
  const ev = d.ev_curves||{};
  document.getElementById("f-ev").textContent = ev.formula_ev || DASH;
  document.getElementById("f-be").textContent = ev.formula_breakeven || DASH;

  const credible = new Set(ev.credible_venue_ids||[]);
  document.getElementById("legend").innerHTML = (ev.series||[]).map(s => {
    const off = S.hidden.has(s.venue_id);
    const cav = (s.caveats||[]).length;
    return '<span class="lg'+(off?" off":"")+'" data-vid="'+esc(s.venue_id)+'" title="'+
      esc((cav ? s.caveats.join("\n\n") : "no caveats · census large enough to believe") +
          "\n\nclick to " + (off?"show":"hide")) + '">'+
      '<span class="sw" style="background:'+vcol(s.venue_id)+'"></span>'+
      '<span class="nm">'+esc(s.venue_id)+'</span>'+
      '<span class="ms">m*&nbsp;'+fx(s.breakeven_premium_m_star,3)+'</span>'+
      (credible.has(s.venue_id) ? '' : '<span class="badge b-amber">CAVEAT'+(cav>1?" ×"+cav:"")+'</span>')+
      '</span>';
  }).join("");
  document.querySelectorAll(".lg").forEach(el => el.addEventListener("click", () => {
    const id = el.getAttribute("data-vid");
    if(S.hidden.has(id)) S.hidden.delete(id); else S.hidden.add(id);
    renderChartFurniture(S.data); drawChart(S.data);
  }));

  const b = (d.kpis||{}).prize_term_band || {};
  document.getElementById("band").innerHTML =
    '<div class="bv">(X−1)p ∈ ['+fx(b.min,3)+', '+fx(b.max,3)+']</div>'+
    '<div class="bt">'+esc(b.note||"")+'</div>';
}

/* =====================================================================================================
   4. VENUE ECONOMICS
   ===================================================================================================== */
function renderVenues(d){
  const NCOL = 10, out = [];
  for(const v of d.venues||[]){
    const refused = !!v.graduation_multiple_refusal;
    const cav = (v.caveats||[]).length;
    let status;
    if(refused)                       status = '<span class="badge b-amber" title="the registry refuses a number here">REFUSES X</span>';
    else if(!isNum(v.graduation_rate_p)) status = '<span class="badge b-amber">NO p</span>';
    else if(cav)                      status = '<span class="badge b-amber" title="'+esc(v.caveats.join("\n\n"))+'">CAVEAT'+(cav>1?" ×"+cav:"")+'</span>';
    else                              status = '<span class="badge b-mint">CREDIBLE</span>';
    const ver = v.verified_onchain
      ? '<span class="badge b-mint" title="program id and account layout read on chain">ON-CHAIN</span>'
      : '<span class="badge b-red">UNVERIFIED</span>';
    const evf = v.ev_at_floor_m_1;
    out.push('<tr>'+
      '<td class="nm" title="'+esc(v.venue_id+"  program "+(v.program_id||DASH)+
              (v.platform_config?"  config "+v.platform_config:""))+'">'+
        '<div class="vname">'+esc(v.display_name||v.venue_id)+'</div>'+
        '<div class="vid">'+esc(v.venue_id)+' · '+esc((v.curve_kind||DASH).replace(/_/g," "))+'</div></td>'+
      '<td class="nm dim2">'+esc(v.chain||DASH)+'</td>'+
      '<td class="num">'+(isNum(v.graduation_multiple_x)
            ? fx(v.graduation_multiple_x,4)+'×'
            : '<span class="warn">'+DASH+'</span>')+'</td>'+
      '<td class="num dim2" title="per side / round trip">'+fpct(v.toll_per_side,2)+
        ' <span class="dim">/ '+fpct(v.toll_round_trip,1)+'</span></td>'+
      '<td class="num">'+(isNum(v.graduation_rate_p)?(v.graduation_rate_p*100).toFixed(4)+"%":
            '<span class="warn">'+DASH+'</span>')+'</td>'+
      '<td class="num dim2" title="'+esc(v.p_basis||"")+'">'+fint(v.p_n)+
        (isNum(v.p_grads)?' <span class="dim">/'+fint(v.p_grads)+'</span>':'')+'</td>'+
      '<td class="num"><b>'+fx(v.breakeven_premium_m_star,4)+'</b></td>'+
      '<td class="num '+(isNum(evf)?(evf>=0?"pos":"neg"):"")+'">'+fsign(evf,2)+'</td>'+
      '<td class="num dim2">'+fx(v.prize_term_Xm1p,4)+'</td>'+
      '<td class="st">'+status+ver+'</td></tr>');

    if(refused){
      out.push('<tr class="sub-r"><td class="refuse" colspan="'+NCOL+'"><div class="rbox">'+
        '<span class="rk">registry refuses a graduation multiple — the refusal is the finding</span>'+
        esc(v.graduation_multiple_refusal)+'</div></td></tr>');
    } else if(cav){
      out.push('<tr class="sub-r"><td class="refuse" colspan="'+NCOL+'"><div class="rbox">'+
        '<span class="rk">caveats on this rank</span><ul class="cavlist">'+
        v.caveats.map(c=>'<li>'+esc(c)+'</li>').join("")+'</ul></div></td></tr>');
    }
  }
  /* excluded: launchpads that are big but are not on Solana */
  for(const [id, x] of Object.entries(d.not_on_solana||{})){
    out.push('<tr class="excl"><td class="nm"><div class="vname">'+esc(id)+'</div>'+
      '<div class="vid">excluded · not a Solana launchpad</div></td>'+
      '<td class="nm dim2">'+esc(x.chain||DASH)+'</td>'+
      '<td class="num warn">'+DASH+'</td><td class="num dim">'+DASH+'</td>'+
      '<td class="num warn">'+DASH+'</td><td class="num dim">'+DASH+'</td><td class="num dim">'+DASH+'</td>'+
      '<td class="num dim">'+DASH+'</td><td class="num dim">'+DASH+'</td>'+
      '<td class="st"><span class="badge b-red">EXCLUDED</span></td></tr>');
    const why = [];
    if(x.source) why.push(x.source);
    if(x.scale) why.push(x.scale);
    if(x.bnb_graduation) why.push("graduation: "+x.bnb_graduation);
    if(x.solana_squatter_config) why.push("the Solana config carrying this name is a squatter: "+x.solana_squatter_config);
    out.push('<tr class="sub-r"><td class="refuse" colspan="'+NCOL+'"><div class="rbox">'+
      '<span class="rk">excluded from the Solana frame</span>'+
      esc(id)+' launches on '+esc(x.chain||"another chain")+
      ', so its curve is not readable from a Solana RPC and no number here would be a measurement. '+
      esc(why.join(" · "))+'</div></td></tr>');
  }
  document.querySelector("#venues tbody").innerHTML = out.join("");

  const td = d.toll_discrepancy||{};
  if(td.verdict) document.getElementById("venue-note").textContent =
    "toll: arena fill books "+fpct(td.arena_fill_py_round_trip,1)+" round trip — "+td.verdict;
}

/* =====================================================================================================
   5. LIVE LAUNCHES
   ===================================================================================================== */
function renderTape(d){
  const t = d.tape||{}, badges = [], body = document.getElementById("tape-body");
  if(t.chain_verified === true) badges.push('<span class="badge b-mint" title="'+esc(t.head_sha256||"")+
        '">CHAIN VERIFIED</span>');
  else if(t.chain_verified === false) badges.push('<span class="badge b-red">CHAIN BROKEN</span>');
  for(const [vid, c] of Object.entries(t.per_venue||{}))
    badges.push('<span class="badge b-dim">'+esc(vid)+' '+fint(c.create||0)+'C / '+fint(c.graduation||0)+'G</span>');
  if(isNum(t.span_hours)) badges.push('<span class="badge b-dim">'+t.span_hours.toFixed(2)+'H SPAN</span>');
  document.getElementById("tape-badges").innerHTML = badges.join(" ");
  document.getElementById("tape-note").textContent = t.recent_window_note || "";

  const rows = [].concat(t.recent_creates||[], t.recent_graduations||[])
                 .sort((a,b)=>(b.sequence||0)-(a.sequence||0)).slice(0,40);
  if(!rows.length){
    const reason = t.refused || t.empty_reason ||
      "the multi-venue collector is not running, so there is nothing to show. Run "+
      "`python -m scripts.trading_bot.memebot.multivenue_tape --listen` to start it.";
    const h = t.health||{};
    body.innerHTML = '<div class="empty"><div class="eh">No taped launches</div>'+
      '<div class="eb">'+esc(reason)+'</div>'+
      (h.status ? '<div class="eb dim">collector status: '+esc(h.status)+
                  (h.reason?' — '+esc(h.reason):'')+'</div>' : '')+
      '<div class="eb dim">The registry and the census do not depend on this feed. '+
      'This panel stays empty rather than inventing a row.</div></div>';
    return;
  }
  const now = Date.parse(d.generated_utc||"") || Date.now();
  /* a graduation row carries no metadata of its own — the pool event has no name or symbol. Where the
     SAME mint's create is in the taped window, its symbol is a real taped fact and is reused (starred,
     and said so in the tooltip). Where it is not, the cell is an em-dash: never a stand-in. */
  const byMint = {};
  for(const c of (t.recent_creates||[])) if(c.mint && (c.symbol||c.name)) byMint[c.mint] = c;
  const cells = rows.map(r => {
    const mint = r.mint||"", h = hueOf(mint), src = byMint[mint];
    const inherited = !r.symbol && !!src;
    const sym = r.symbol || (src ? src.symbol : null);
    const nm  = r.name   || (src ? src.name   : null);
    const mono = (sym||mint||"?").replace(/[^A-Za-z0-9]/g,"").slice(0,2).toUpperCase() || "?";
    const grad = r.kind === "graduation";
    const ageS = isNum(r.received_unix_nanos) ? (now - r.received_unix_nanos/1e6)/1000 : null;
    const age = !isNum(ageS) ? DASH : ageS < 90 ? Math.max(0,Math.round(ageS))+"s"
                : ageS < 5400 ? (ageS/60).toFixed(1)+"m" : (ageS/3600).toFixed(1)+"h";
    return '<tr>'+
      '<td><div class="tok"><div class="mg" style="background:hsl('+h+',18%,20%);color:hsl('+h+',34%,68%)">'+
        esc(mono)+'</div><div class="tk"><div class="tsym"'+
        (inherited ? ' title="symbol read from this mint\u2019s own create row on the tape"' : '')+'>'+
        (sym ? esc(sym)+(inherited ? '<span class="dim">*</span>' : '')
             : '<span class="dim">'+DASH+'</span>')+' '+copyBtn(mint)+'</div>'+
        '<div class="tmint" title="'+esc(mint)+'">'+esc(short(mint,8,6))+'</div></div></div></td>'+
      '<td class="nm dim2">'+(nm ? esc(nm) : '<span class="dim">'+DASH+'</span>')+'</td>'+
      '<td class="nm"><span class="badge b-dim">'+esc(r.venue||DASH)+'</span></td>'+
      '<td class="nm"><span class="badge '+(grad?"b-mint":"b-amber")+'">'+(grad?"GRADUATED":"CREATE")+'</span></td>'+
      '<td class="num dim2">'+fint(r.slot)+'</td>'+
      '<td class="num dim2">'+fint(r.sequence)+'</td>'+
      '<td class="num dim2">'+esc(r.received_utc||DASH)+'</td>'+
      '<td class="num">'+age+'</td>'+
      '<td class="nm dim">'+esc(short(r.pool_id,6,5))+'</td></tr>';
  }).join("");
  body.innerHTML = '<div class="tscroll"><table><thead><tr>'+
    '<th style="min-width:210px">Token</th><th>Name</th><th>Venue</th><th>State</th>'+
    '<th class="r">Slot</th><th class="r">Seq</th><th class="r">Taped (UTC)</th><th class="r">Age</th>'+
    '<th>Pool</th></tr></thead><tbody>'+cells+'</tbody></table></div>';
}

/* =====================================================================================================
   appendix: label ledger + provenance
   ===================================================================================================== */
function renderLedger(d){
  const L = d.label_ledger||{}, b = L.b11a||{}, ll = L.launchlab||{};
  document.getElementById("ledger").innerHTML =
    '<div class="gcol"><div class="gh">the wall · research/b11a</div><dl class="kv">'+
      '<dt>creates</dt><dd>'+fint(b.creates)+'</dd>'+
      '<dt>graduations</dt><dd>'+fint(b.graduations)+'</dd>'+
      '<dt>p</dt><dd>'+fpct(b.graduation_rate_p,4)+'</dd>'+
      '<dt>curves w/ price history</dt><dd>'+fint(b.curves_with_price_history)+'</dd>'+
      '<dt>traded below launch</dt><dd class="pos">'+fint(b.curves_that_traded_below_launch_price)+'</dd>'+
      '<dt>floor cohort</dt><dd>'+fint(b.floor_cohort)+'</dd>'+
      '<dt>…of which graduated</dt><dd class="neg">'+fint(b.floor_cohort_positives)+'</dd>'+
    '</dl><div class="prose" style="margin-top:10px">'+esc(b.wall||"")+'</div></div>'+
    '<div class="gcol"><div class="gh">the unlock · launchlab census</div><dl class="kv">'+
      '<dt>curves</dt><dd>'+fint(ll.curves)+'</dd>'+
      '<dt>graduations</dt><dd class="pos">'+fint(ll.graduations)+'</dd>'+
      '<dt>p</dt><dd>'+fpct(ll.graduation_rate_p,4)+'</dd>'+
      '<dt>cost</dt><dd class="pos">$'+(isNum(ll.cost_usd)?ll.cost_usd.toFixed(0):DASH)+'</dd>'+
      '<dt>measured</dt><dd>'+esc(ll.measured_utc||DASH)+'</dd>'+
      '<dt>label multiple</dt><dd class="pos">'+(isNum(L.multiple)?L.multiple.toFixed(1)+"×":DASH)+'</dd>'+
    '</dl><div class="prose" style="margin-top:10px">'+esc(ll.why_comparable||"")+'</div>'+
    '<ul class="unlocks">'+(L.unlocks||[]).filter(Boolean).map(u=>'<li>'+esc(u)+'</li>').join("")+'</ul></div>';
}
function renderProv(d){
  const p = d.provenance||{}, c = d.census||{};
  const idls = Object.entries(p.pinned_idls||{})
    .map(([k,v])=>'<dt>'+esc(k)+'</dt><dd>'+esc(short(v,10,8))+'</dd>').join("");
  document.getElementById("prov").innerHTML =
    '<div class="gcol"><div class="gh">registry + pinned idls</div><dl class="kv">'+
      '<dt>registry sha256</dt><dd>'+esc(short(p.registry_sha256,12,10))+'</dd>'+
      '<dt>idl status</dt><dd class="'+(p.pinned_idl_status==="verified"?"pos":"neg")+'">'+
        esc(p.pinned_idl_status||DASH)+'</dd>'+ idls +
      '<dt>free rpc</dt><dd>'+esc(p.free_rpc||DASH)+'</dd>'+
    '</dl><div class="prose" style="margin-top:10px"><b>Law.</b> '+esc(p.law||"")+'</div>'+
    '<div class="prose" style="margin-top:8px"><b>Floor.</b> '+esc(p.floor_result||"")+'</div></div>'+
    '<div class="gcol"><div class="gh">launchlab census</div><dl class="kv">'+
      '<dt>program</dt><dd>'+esc(c.program||DASH)+'</dd>'+
      '<dt>method</dt><dd>'+esc(c.method||DASH)+'</dd>'+
      '<dt>source</dt><dd>'+esc(c.source||DASH)+'</dd>'+
      '<dt>funding</dt><dd>'+fint((c.counts||{}).funding)+'</dd>'+
      '<dt>awaiting migration</dt><dd>'+fint((c.counts||{}).awaiting_migration)+'</dd>'+
      '<dt>migrated</dt><dd class="pos">'+fint((c.counts||{}).migrated)+'</dd>'+
      '<dt>elapsed</dt><dd>'+(c.elapsed_seconds
         ? Object.entries(c.elapsed_seconds).map(([k,v])=>k+" "+v+"s").join(" · ") : DASH)+'</dd>'+
    '</dl>'+(c.cross_check ? '<div class="prose" style="margin-top:10px"><b>Cross-check.</b> '+
      esc(c.cross_check.note||"")+'</div>' : '')+'</div>';
}

/* =====================================================================================================
   POLL LOOP
   ===================================================================================================== */
function renderAll(d){
  S.data = d;
  if(S.hidden === null){
    /* a config whose p is above the registry's lottery threshold is an instant-liquidity vehicle, not a
       graduation lottery: its EV at the floor is an artefact that would flatten every real curve into
       one line. Start it hidden; the legend chip restores it. */
    S.hidden = new Set(((d.ev_curves||{}).series||[])
      .filter(s => isNum(s.p) && s.p > MAX_LOTTERY_P).map(s => s.venue_id));
  }
  renderHeader(d); renderStrip(d); renderChartFurniture(d); drawChart(d);
  renderVenues(d); renderTape(d); renderLedger(d); renderProv(d);
  document.getElementById("footer").textContent = d.footer || "";
}
async function poll(){
  try{
    const r = await fetch("/api/state", {cache:"no-store"});
    if(!r.ok) throw new Error("HTTP "+r.status);
    const d = await r.json();
    document.getElementById("err").innerHTML = "";
    renderAll(d);
  }catch(e){
    document.getElementById("err").innerHTML =
      '<div class="err">state fetch failed: '+esc(e.message||e)+
      ' — the page is showing the last good state, not a fresh one.</div>';
  }
  setTimeout(poll, POLL_MS);
}
let rt = null;
window.addEventListener("resize", () => {
  clearTimeout(rt); rt = setTimeout(() => { if(S.data) drawChart(S.data); }, 140);
});
poll();
</script>
</body></html>
"""
_PAGE = _PAGE.replace("__MAX_LOTTERY_P__", repr(float(V.MAX_LOTTERY_P)))
PAGE_BYTES = _PAGE.encode("utf-8")


# =====================================================================================================
# THE SERVER
# =====================================================================================================
class Handler(BaseHTTPRequestHandler):
    server_version = "LaunchpadObservatory/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):        # one line per request is noise on a 5s poll
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass                              # a tab closed mid-poll is not an error

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):                         # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/":
            self._send(200, PAGE_BYTES, "text/html; charset=utf-8")
        elif path == "/api/state":
            try:
                self._json(200, state_view())
            except Exception as exc:          # a broken read is a visible finding, not a blank page
                self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        elif path == "/api/health":
            self._json(200, {"ok": True, "service": "launchpad-observatory", "port": self.server.server_port,
                             "read_only": True, "state_ttl_s": STATE_TTL})
        else:
            self._json(404, {"ok": False, "error": f"no route {path}",
                             "routes": ["/", "/api/state", "/api/health"]})

    def do_POST(self):                        # noqa: N802
        # There is deliberately no write or refresh route. Re-measuring the census is an explicit
        # `python -m scripts.trading_bot.memebot.observatory --refresh`, never a thing a page can do.
        self._json(405, {"ok": False, "error": "read-only server: no POST route exists",
                         "refresh_census": "python -m scripts.trading_bot.memebot.observatory --refresh"})


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="Launchpad Observatory — read-only dashboard server")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--selftest", action="store_true",
                    help="build the state and the page once, print a summary, exit without binding")
    args = ap.parse_args(argv)

    if args.selftest:
        t0 = time.time()
        st = state_view(force=True)
        k = st["kpis"]
        print(f"state ok in {time.time()-t0:.2f}s · schema {st['schema']} · {len(st['venues'])} venues · "
              f"{len(st['ev_curves']['series'])} EV series · census "
              f"{'available' if st['census'].get('available') else 'MISSING'} · tape {k['tape_rows']} rows")
        print(f"page {len(PAGE_BYTES):,} bytes · MAX_LOTTERY_P={V.MAX_LOTTERY_P} · "
              f"routes / /api/state /api/health")
        return 0

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    print(f"Launchpad Observatory: http://{args.host}:{args.port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
