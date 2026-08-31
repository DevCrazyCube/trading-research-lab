#!/usr/bin/env python3
"""
AFTERSHOCK · PAC / LWS — "Quiet Desk" live paper-trade dashboard.

A single self-contained http.server (Python standard library ONLY) that serves
one calm, focused trading view at http://127.0.0.1:8793/ :

  1. a stat strip (6 tiles),
  2. ONE hero graph  — the cumulative net-SOL equity curve, LWS vs NULL,
  3. ONE live tape   — the newest buys/sells from the feed.

It reads five LOCAL files (no network, no auth) and computes the curve / tiles /
tape server-side, returning one JSON blob to a ~2s client poll:

  research/trading_bot/aftershock/AFTERSHOCK_PAC_LWS_SCENARIO_LEDGER.jsonl
  research/trading_bot/aftershock/AFTERSHOCK_PAC_LWS_NULL_SCENARIO_LEDGER.jsonl
  research/data/aftershock/pac_lws/feed_events.jsonl
  research/data/aftershock/pac_lws/creation_registry.jsonl
  research/data/aftershock/pac_lws/feed_health.json

The two scenario ledgers MAY NOT EXIST YET or be EMPTY (the runner is being
built in parallel). Every read is guarded: a missing/empty ledger yields empty
arrays and zeroed / "—" tiles, and the page renders the honest empty state
("Awaiting first resolved trade") instead of crashing.

Run:
    python3 scripts/trading_bot/aftershock/pac_lws_dashboard.py
    # then open http://127.0.0.1:8793/
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths — resolve the repo root from this file's location so the dashboard can
# be launched from anywhere. scripts/trading_bot/aftershock/<this> -> parents[3]
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parents[3]

LEDGER_LWS = ROOT / "research/trading_bot/aftershock/AFTERSHOCK_PAC_LWS_SCENARIO_LEDGER.jsonl"
LEDGER_NULL = ROOT / "research/trading_bot/aftershock/AFTERSHOCK_PAC_LWS_NULL_SCENARIO_LEDGER.jsonl"
FEED_EVENTS = ROOT / "research/data/aftershock/pac_lws/feed_events.jsonl"
CREATION_REGISTRY = ROOT / "research/data/aftershock/pac_lws/creation_registry.jsonl"
FEED_HEALTH = ROOT / "research/data/aftershock/pac_lws/feed_health.json"

HOST = "127.0.0.1"   # localhost only — never bind 0.0.0.0
PORT = 8793

LAMPORTS_PER_SOL = 1_000_000_000
TAPE_ROWS = 48       # newest feed rows sent to the client (not a firehose)

# --------------------------------------------------------------------------- #
# Tiny stat-keyed cache so a growing file is not fully re-parsed every poll.
# Keyed on (size, mtime_ns); recomputed only when the file actually changes.
# --------------------------------------------------------------------------- #
_CACHE: dict[str, tuple] = {}


def _cached(path: Path, builder):
    """Return builder(path) memoized on the file's (size, mtime). Guarded."""
    try:
        st = path.stat()
        key = (st.st_size, st.st_mtime_ns)
    except OSError:
        return builder(None)  # missing file -> let builder return its empty shape
    prev = _CACHE.get(str(path))
    if prev is not None and prev[0] == key:
        return prev[1]
    value = builder(path)
    _CACHE[str(path)] = (key, value)
    return value


def _iter_json_lines(path: Path):
    """Yield parsed JSON objects from a .jsonl file; skip blanks/garbage."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except (ValueError, TypeError):
                    continue
    except OSError:
        return


def _tail_lines(path: Path, n: int) -> list[str]:
    """Return the last n non-empty lines of a file, cheaply, via a backward seek."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            end = fh.tell()
            block = 65536
            pos = end
            data = b""
            # read backward until we have more than n newlines, or hit the start
            while pos > 0 and data.count(b"\n") <= n:
                step = min(block, pos)
                pos -= step
                fh.seek(pos)
                data = fh.read(step) + data
            lines = [ln for ln in data.split(b"\n") if ln.strip()]
            return [ln.decode("utf-8", "replace") for ln in lines[-n:]]
    except OSError:
        return []


def _count_lines(path: Path) -> int:
    """Fast newline count over a file; 0 if missing/unreadable."""
    def build(p):
        if p is None:
            return 0
        try:
            total = 0
            with p.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    total += chunk.count(b"\n")
            return total
        except OSError:
            return 0
    return _cached(path, build)


# --------------------------------------------------------------------------- #
# Ledger reduction — one pass -> the equity curve points + funnel counts.
# --------------------------------------------------------------------------- #
def _read_ledger(path: Path) -> dict:
    """
    Reduce one scenario ledger to everything the dashboard needs.

    Returns:
        points:      [{"t": <sec>, "net": <cumulative net SOL>}, ...] over resolved rows
        net_sol:     final cumulative net SOL (0.0 if none)
        resolved:    count of kind=="resolved"
        filled:      count of kind=="entry_filled"
        decisions:   count of kind=="entry_decision"
        vetoed:      count of kind in {entry_vetoed, entry_rejected}
        unexitable:  count of resolved rows with unexitable_full_loss==True
    """
    def build(p):
        empty = {
            "points": [], "net_sol": 0.0, "resolved": 0, "filled": 0,
            "decisions": 0, "vetoed": 0, "unexitable": 0,
        }
        if p is None:
            return empty
        resolved_rows = []
        filled = decisions = vetoed = unexitable = 0
        for obj in _iter_json_lines(p):
            kind = obj.get("kind")
            if kind == "resolved":
                ts = obj.get("resolved_unix_nanos")
                num = obj.get("net_return_num")
                if ts is None or num is None:
                    continue
                resolved_rows.append((ts, num, bool(obj.get("unexitable_full_loss"))))
            elif kind == "entry_filled":
                filled += 1
            elif kind == "entry_decision":
                decisions += 1
            elif kind == "entry_vetoed":
                vetoed += 1

        resolved_rows.sort(key=lambda r: r[0])
        points = []
        running = 0
        for ts, num, unex in resolved_rows:
            running += num
            if unex:
                unexitable += 1
            points.append({"t": ts / 1e9, "net": running / LAMPORTS_PER_SOL})

        return {
            "points": points,
            "net_sol": (running / LAMPORTS_PER_SOL) if resolved_rows else 0.0,
            "resolved": len(resolved_rows),
            "filled": filled,
            "decisions": decisions,
            "vetoed": vetoed,
            "unexitable": unexitable,
        }
    return _cached(path, build)


def _read_coverage(registry_path: Path, feed_path: Path) -> tuple[int, int]:
    """(reconciled distinct mints, total created distinct mints). The `reconciled` flag lives on the
    FEED events (a mint's first trade reconciled to its seeded t0 state), not on the registry — so
    coverage = distinct mints with a reconciled trade / distinct created mints. (0, 0) if missing."""
    creates = set()
    for obj in _iter_json_lines(registry_path):
        m = obj.get("mint")
        if m:
            creates.add(m)
    recon = set()
    for obj in _iter_json_lines(feed_path):
        if obj.get("reconciled") is True:
            m = obj.get("mint")
            if m:
                recon.add(m)
    return (len(recon & creates), len(creates))


def _read_tape(path: Path) -> list[dict]:
    """Newest-first list of the last TAPE_ROWS feed events (lean projection)."""
    rows = []
    for line in _tail_lines(path, TAPE_ROWS):
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        ts = obj.get("received_unix_nanos")
        rows.append({
            "is_buy": bool(obj.get("is_buy")),
            "sol": (obj.get("sol_amount") or 0) / LAMPORTS_PER_SOL,
            "mint": obj.get("mint") or "",
            "slot": obj.get("slot"),
            "t": (ts / 1e9) if ts else None,
            "anchored": bool(obj.get("anchored")),
            "reconciled": obj.get("reconciled") is True,
        })
    rows.reverse()  # newest on top
    return rows


def _read_health() -> dict:
    """feed_health.json projection + a present/stale flag. Never raises."""
    try:
        obj = json.loads(FEED_HEALTH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"present": False, "status": "STALE", "lag": None,
                "observed_sec": None, "instrument_id": None}
    obs = obj.get("observed_unix_nanos")
    return {
        "present": True,
        "status": obj.get("status") or "UNKNOWN",
        "lag": obj.get("head_slot_lag"),
        "observed_sec": (obs / 1e9) if obs else None,
        "instrument_id": obj.get("instrument_id"),
    }


# --------------------------------------------------------------------------- #
# /api/state — assemble the single JSON blob for the client poll.
# --------------------------------------------------------------------------- #
def build_state() -> dict:
    lws = _read_ledger(LEDGER_LWS)
    null = _read_ledger(LEDGER_NULL)
    recon, creates = _read_coverage(CREATION_REGISTRY, FEED_EVENTS)
    tape = _read_tape(FEED_EVENTS)
    feed_count = _count_lines(FEED_EVENTS)
    health = _read_health()

    open_book = max(lws["filled"] - lws["resolved"], 0)
    # veto rate = B20B vetoes / (vetoes + admitted decisions); entry_rejected (coverage floor) is not a veto
    veto_attempts = lws["vetoed"] + lws["decisions"]
    veto_rate = (lws["vetoed"] / veto_attempts * 100.0) if veto_attempts else None
    coverage = (recon / creates * 100.0) if creates else None
    unex_pct = (lws["unexitable"] / lws["resolved"] * 100.0) if lws["resolved"] else 0.0

    tiles = {
        "net_sol_lws": lws["net_sol"],
        "net_sol_null": null["net_sol"],
        "vs_null": lws["net_sol"] - null["net_sol"],
        "resolved": lws["resolved"],
        "open": open_book,
        "unexitable": lws["unexitable"],
        "unexitable_pct": unex_pct,
        "veto_rate": veto_rate,
        "veto_v": lws["vetoed"],
        "veto_d": veto_attempts,
        "coverage": coverage,
        "coverage_r": recon,
        "coverage_c": creates,
        "null_present": LEDGER_NULL.exists(),
    }

    return {
        "equity_lws": lws["points"],
        "equity_null": null["points"],
        "tape": tape,
        "feed_count": feed_count,
        "tiles": tiles,
        "health": health,
    }


# --------------------------------------------------------------------------- #
# The single static page — Quiet Desk. Inline HTML + CSS + JS, no build step,
# no external chart lib (inline SVG), no external network.
# --------------------------------------------------------------------------- #
PAGE = r"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AFTERSHOCK · PAC / LWS</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root{
    --ground:#0F1216; --panel:#171B22; --hair:#262C35; --hair-lit:#39424E;
    --muted:#828B98; --ink:#E7EAEF;
    --amber:#D6A85B; --buy:#57B98C; --sell:#CB6F6A;
    --inter:'Inter',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{
    margin:0; background:var(--ground); color:var(--ink);
    font-family:var(--inter); font-size:14px;
    -webkit-font-smoothing:antialiased;
  }
  .num{font-family:var(--mono); font-variant-numeric:tabular-nums; font-feature-settings:"tnum" 1;}
  .kick{font-size:11px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted);}

  /* ---- desk frame: centered, capped, single-screen ---------------------- */
  .desk{
    max-width:1600px; margin:0 auto; height:100vh;
    display:grid; grid-template-rows:auto auto minmax(0,1fr) 28vh;
    background:var(--ground);
  }

  /* ---- 1. chrome -------------------------------------------------------- */
  .chrome{
    display:flex; align-items:center; justify-content:space-between;
    padding:14px 30px; gap:16px;
  }
  .wm{display:flex; align-items:center; gap:12px;}
  .wm .mark{font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--muted);}
  .pill{
    font-size:10px; letter-spacing:.1em; text-transform:uppercase; color:var(--muted);
    border:1px solid var(--hair); border-radius:999px; padding:3px 9px;
  }
  .live{display:flex; align-items:center; gap:9px; font-size:11px; letter-spacing:.06em;
        text-transform:uppercase; color:var(--muted);}
  .dot{width:8px; height:8px; border-radius:50%; background:var(--amber);
       box-shadow:0 0 0 0 rgba(214,168,91,.45); animation:breathe 3s ease-in-out infinite;}
  @keyframes breathe{
    0%,100%{box-shadow:0 0 0 0 rgba(214,168,91,.40);}
    50%{box-shadow:0 0 0 5px rgba(214,168,91,0);}
  }

  /* ---- 2. stat strip ---------------------------------------------------- */
  .strip{display:flex; border-top:1px solid var(--hair);}
  .tile{
    flex:1 1 0; padding:14px 24px; min-width:0;
    display:flex; flex-direction:column; gap:3px;
  }
  .tile + .tile{border-left:1px solid var(--hair);}
  .tile .val{font-family:var(--mono); font-variant-numeric:tabular-nums; font-weight:500;
             font-size:26px; line-height:1.05; color:var(--ink);}
  .tile .val.amber{color:var(--amber);}
  .tile .val.sell{color:var(--sell);}
  .tile .lab{font-size:11px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted);}
  .tile .sub{font-family:var(--mono); font-variant-numeric:tabular-nums;
             font-size:11px; color:var(--muted);}

  /* ---- 3. hero curve ---------------------------------------------------- */
  .hero{border-top:1px solid var(--hair); padding:16px 30px 8px; display:flex;
        flex-direction:column; min-height:0;}
  .hero-head{display:flex; align-items:baseline; justify-content:space-between; gap:16px;}
  .hero-key{display:flex; align-items:center; gap:18px; font-size:11px; color:var(--muted);}
  .hero-key .k{display:flex; align-items:center; gap:7px; letter-spacing:.04em;}
  .swatch{width:16px; height:2px; border-radius:2px; display:inline-block;}
  .swatch.lws{background:var(--amber);}
  .swatch.null{background:var(--muted); height:0; border-top:2px dashed var(--muted);}
  #chart{flex:1 1 auto; min-height:0; position:relative;}
  #chart svg{display:block; width:100%; height:100%;}

  /* ---- 4. tape ---------------------------------------------------------- */
  .tape{border-top:1px solid var(--hair); display:flex; flex-direction:column; min-height:0;
        padding:0 30px 12px;}
  .tape-head{display:flex; align-items:center; justify-content:space-between;
             padding:12px 0 8px; font-size:11px; letter-spacing:.06em;
             text-transform:uppercase; color:var(--muted);}
  .tape-head .split{font-family:var(--mono); font-variant-numeric:tabular-nums;}
  .tape-body{flex:1 1 auto; overflow-y:auto; min-height:0; background:var(--panel);
             border-radius:4px;}
  .tape-empty{display:flex; align-items:center; justify-content:center; height:100%;
              color:var(--muted); font-size:12px; letter-spacing:.04em;}
  .row{
    display:grid; grid-template-columns:14px 46px 82px 1fr 62px 12px;
    align-items:center; gap:12px; height:29px; padding:0 14px;
    font-family:var(--mono); font-variant-numeric:tabular-nums; font-size:12.5px;
    color:var(--muted);
  }
  .row .tick{width:8px; height:8px; border-radius:2px; justify-self:center;}
  .row.buy .side{color:var(--buy);} .row.buy .tick{background:var(--buy);}
  .row.sell .side{color:var(--sell);} .row.sell .tick{background:var(--sell);}
  .row .side{font-size:11px; letter-spacing:.05em;}
  .row .sol{text-align:right; color:var(--ink);}
  .row .mint{color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
  .row .rt{text-align:right; color:var(--muted); font-size:11px;}
  .row .integ{width:7px; height:7px; border-radius:50%; justify-self:center;
              border:1px solid var(--muted);}
  .row .integ.on{background:var(--muted); border-color:var(--muted);}
  .row.dust{opacity:.55;}
  .row.fresh{animation:slidein .15s ease-out;}
  @keyframes slidein{from{opacity:0; transform:translateY(-6px);} to{opacity:1; transform:none;}}

  /* ---- narrow ----------------------------------------------------------- */
  @media (max-width:820px){
    .desk{height:auto; grid-template-rows:none; display:block;}
    .strip{flex-wrap:wrap;}
    .tile{flex:1 1 33%; border-top:1px solid var(--hair);}
    .tile + .tile{border-left:none;}
    .hero{height:52vh;}
    .tape{height:44vh;}
  }
  /* scrollbar — quiet */
  .tape-body::-webkit-scrollbar{width:8px;}
  .tape-body::-webkit-scrollbar-thumb{background:var(--hair); border-radius:8px;}
  .tape-body::-webkit-scrollbar-track{background:transparent;}
</style>
</head>
<body>
<div class="desk">

  <!-- 1. chrome -->
  <header class="chrome">
    <div class="wm">
      <span class="mark">AFTERSHOCK · PAC / LWS</span>
      <span class="pill">PAPER · READ-ONLY</span>
    </div>
    <div class="live"><span class="dot" id="dot"></span><span id="liveline">connecting…</span></div>
  </header>

  <!-- 2. stat strip -->
  <section class="strip" id="strip">
    <div class="tile"><div class="val amber num" id="t-net">—</div><div class="lab">Net SOL · LWS</div><div class="sub" id="t-net-sub">no trades yet</div></div>
    <div class="tile"><div class="val num" id="t-resolved">0</div><div class="lab">Resolved</div><div class="sub" id="t-resolved-sub">0 open</div></div>
    <div class="tile"><div class="val num" id="t-unex">0</div><div class="lab">Unexitable</div><div class="sub" id="t-unex-sub">0% of resolved</div></div>
    <div class="tile"><div class="val num" id="t-open">0</div><div class="lab">Open Book</div><div class="sub">positions live</div></div>
    <div class="tile"><div class="val num" id="t-veto">—</div><div class="lab">B20B Veto</div><div class="sub" id="t-veto-sub">0 / 0 decisions</div></div>
    <div class="tile"><div class="val num" id="t-cov">—</div><div class="lab">Coverage</div><div class="sub" id="t-cov-sub">0 / 0 reconciled</div></div>
  </section>

  <!-- 3. hero curve -->
  <section class="hero">
    <div class="hero-head">
      <span class="kick">Cumulative Net SOL · LWS vs NULL</span>
      <div class="hero-key">
        <span class="k"><span class="swatch lws"></span>LWS</span>
        <span class="k" id="key-null"><span class="swatch null"></span>NULL</span>
      </div>
    </div>
    <div id="chart"></div>
  </section>

  <!-- 4. tape -->
  <section class="tape">
    <div class="tape-head"><span>Live Tape · buys / sells</span><span class="split" id="tape-split">—</span></div>
    <div class="tape-body" id="tape-body">
      <div class="tape-empty">tape idle · awaiting events</div>
    </div>
  </section>

</div>

<script>
"use strict";
// --------- palette (mirrors CSS so the SVG stays in the same grammar) ------
const C = {
  ground:'#0F1216', panel:'#171B22', hair:'#262C35', hairLit:'#39424E',
  muted:'#828B98', ink:'#E7EAEF', amber:'#D6A85B', buy:'#57B98C', sell:'#CB6F6A'
};
const SVGNS='http://www.w3.org/2000/svg';
let CHART=null;          // last-drawn scale params, for the hover crosshair
let lastFirstT=null;     // track newest tape row so only genuinely new rows animate

// --------- formatting helpers ---------------------------------------------
function fmtSigned(v,dp){ const s=v>=0?'+':'−'; return s+Math.abs(v).toFixed(dp); }
function fmtSol(v){ return fmtSigned(v,3); }
function shortMint(m){ return (m&&m.length>10)? m.slice(0,4)+'…'+m.slice(-4) : (m||'—'); }
function pad2(n){ return (n<10?'0':'')+n; }
function hhmm(sec){ const d=new Date(sec*1000); return pad2(d.getHours())+':'+pad2(d.getMinutes()); }
function relTime(sec){
  if(sec==null) return '';
  let d=Math.max(0,(Date.now()/1000)-sec);
  if(d<60) return Math.floor(d)+'s';
  if(d<3600) return Math.floor(d/60)+'m';
  if(d<86400) return Math.floor(d/3600)+'h';
  return Math.floor(d/86400)+'d';
}
function el(tag,cls,txt){ const e=document.createElement(tag); if(cls)e.className=cls; if(txt!=null)e.textContent=txt; return e; }

// --------- nice axis scaling ----------------------------------------------
function niceNum(range,round){
  if(range<=0) return 1;
  const exp=Math.floor(Math.log10(range)), f=range/Math.pow(10,exp);
  let nf; if(round){ nf=f<1.5?1:f<3?2:f<7?5:10; } else { nf=f<=1?1:f<=2?2:f<=5?5:10; }
  return nf*Math.pow(10,exp);
}
function niceScale(lo,hi,n){
  if(lo===hi){ lo-=1; hi+=1; }
  const range=niceNum(hi-lo,false), step=niceNum(range/Math.max(1,n-1),true);
  const nlo=Math.floor(lo/step)*step, nhi=Math.ceil(hi/step)*step;
  const ticks=[];
  for(let v=nlo; v<=nhi+step*0.5; v+=step) ticks.push(+v.toFixed(9));
  return {lo:nlo,hi:nhi,step:step,ticks:ticks};
}

// --------- the hero curve --------------------------------------------------
function drawChart(state){
  const host=document.getElementById('chart');
  const W=host.clientWidth||800, H=host.clientHeight||300;
  const L=58,R=98,T=22,B=30, plotW=Math.max(10,W-L-R), plotH=Math.max(10,H-T-B);
  const lws=state.equity_lws||[], nul=state.equity_null||[];
  const hasData = lws.length>0 || nul.length>0;

  // x/y domains ---------------------------------------------------------
  let t0,t1,vlo,vhi;
  if(hasData){
    let ts=[], vs=[0];
    for(const p of lws){ ts.push(p.t); vs.push(p.net); }
    for(const p of nul){ ts.push(p.t); vs.push(p.net); }
    t0=Math.min.apply(null,ts); t1=Math.max.apply(null,ts);
    if(t0===t1){ t0-=30; t1+=30; }
    vlo=Math.min.apply(null,vs); vhi=Math.max.apply(null,vs);
  } else {
    const now=Date.now()/1000; t0=now-300; t1=now; vlo=-1; vhi=1;
  }
  const ys=niceScale(vlo,vhi,4);
  const xOf=t=> L+(t-t0)/((t1-t0)||1)*plotW;
  const yOf=v=> T+(ys.hi-v)/((ys.hi-ys.lo)||1)*plotH;
  CHART={L,R,T,B,W,H,plotW,plotH,t0,t1,ys,xOf,yOf,lws,nul};

  const svg=document.createElementNS(SVGNS,'svg');
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  svg.setAttribute('preserveAspectRatio','none');

  // defs: soft amber area fill
  const defs=document.createElementNS(SVGNS,'defs');
  defs.innerHTML='<linearGradient id="fillA" x1="0" y1="0" x2="0" y2="1">'+
    '<stop offset="0%" stop-color="'+C.amber+'" stop-opacity="0.14"/>'+
    '<stop offset="100%" stop-color="'+C.amber+'" stop-opacity="0"/></linearGradient>';
  svg.appendChild(defs);

  const mk=(tag,attrs)=>{ const e=document.createElementNS(SVGNS,tag);
    for(const k in attrs) e.setAttribute(k,attrs[k]); return e; };

  // horizontal gridlines (no vertical grid) + y ticks
  for(const v of ys.ticks){
    const y=yOf(v), zero=Math.abs(v)<1e-9;
    svg.appendChild(mk('line',{x1:L,y1:y,x2:W-R,y2:y,
      stroke: zero?C.hairLit:C.hair, 'stroke-width': zero?1.4:1}));
    const lab=mk('text',{x:L-10,y:y+3.5,'text-anchor':'end','font-size':11,fill:C.muted});
    lab.setAttribute('font-family','JetBrains Mono, monospace');
    lab.style.fontVariantNumeric='tabular-nums';
    lab.textContent=(v>=0?'':'−')+Math.abs(v).toFixed(2);
    svg.appendChild(lab);
  }
  // x ticks (~4 sparse HH:MM)
  const XT=4;
  for(let i=0;i<=XT;i++){
    const t=t0+(t1-t0)*i/XT, x=xOf(t);
    const lab=mk('text',{x:x,y:H-10,'text-anchor':i===0?'start':(i===XT?'end':'middle'),
      'font-size':11,fill:C.muted});
    lab.setAttribute('font-family','JetBrains Mono, monospace');
    lab.textContent=hhmm(t);
    svg.appendChild(lab);
  }

  function pathD(pts){
    if(!pts.length) return '';
    let d='M '+xOf(pts[0].t).toFixed(1)+' '+yOf(pts[0].net).toFixed(1);
    for(let i=1;i<pts.length;i++) d+=' L '+xOf(pts[i].t).toFixed(1)+' '+yOf(pts[i].net).toFixed(1);
    return d;
  }

  if(hasData){
    // NULL first (muted, dashed, behind)
    if(nul.length){
      svg.appendChild(mk('path',{d:pathD(nul),fill:'none',stroke:C.muted,
        'stroke-width':1.5,'stroke-dasharray':'4 3','opacity':0.75,
        'stroke-linejoin':'round'}));
    }
    // LWS area fill + line
    if(lws.length){
      const d=pathD(lws);
      const area=d+` L ${xOf(lws[lws.length-1].t).toFixed(1)} ${yOf(ys.lo).toFixed(1)}`+
                 ` L ${xOf(lws[0].t).toFixed(1)} ${yOf(ys.lo).toFixed(1)} Z`;
      svg.appendChild(mk('path',{d:area,fill:'url(#fillA)',stroke:'none'}));
      svg.appendChild(mk('path',{d:d,fill:'none',stroke:C.amber,'stroke-width':2,
        'stroke-linejoin':'round','stroke-linecap':'round'}));
    }
    // endpoints + floating chips
    endpoint(svg,mk,lws,C.amber,'LWS');
    endpoint(svg,mk,nul,C.muted,'NULL');
  } else {
    // honest empty state — framed chart, centered message + live sub-line
    const cx=L+plotW/2, cy=T+plotH/2;
    const m=mk('text',{x:cx,y:cy-4,'text-anchor':'middle','font-size':14,fill:C.muted});
    m.setAttribute('font-family','Inter, sans-serif');
    m.textContent='Awaiting first resolved trade';
    svg.appendChild(m);
    const sub=mk('text',{x:cx,y:cy+18,'text-anchor':'middle','font-size':11.5,fill:C.muted});
    sub.setAttribute('font-family','JetBrains Mono, monospace');
    sub.setAttribute('opacity','0.8');
    sub.textContent=emptySubline(state);
    svg.appendChild(sub);
  }

  // hover layer -----------------------------------------------------------
  const cross=mk('g',{}); cross.style.display='none'; svg.appendChild(cross);
  const cline=mk('line',{y1:T,y2:H-B,stroke:C.amber,'stroke-width':1,'opacity':0.6});
  cross.appendChild(cline);
  const readBg=mk('rect',{rx:3,fill:C.panel,stroke:C.hair,'stroke-width':1,height:22});
  const readTx=mk('text',{'font-size':11,fill:C.ink,y:T+14});
  readTx.setAttribute('font-family','JetBrains Mono, monospace');
  readTx.style.fontVariantNumeric='tabular-nums';
  cross.appendChild(readBg); cross.appendChild(readTx);

  const hit=mk('rect',{x:L,y:T,width:plotW,height:plotH,fill:'transparent'});
  hit.style.cursor='crosshair';
  hit.addEventListener('mousemove',ev=>{
    if(!hasData){ return; }
    const r=svg.getBoundingClientRect();
    const sx=(ev.clientX-r.left)*(W/r.width);
    const t=t0+(sx-L)/plotW*(t1-t0);
    const a=nearest(lws,t), b=nearest(nul,t);
    const x=Math.max(L,Math.min(W-R,sx));
    cline.setAttribute('x1',x); cline.setAttribute('x2',x);
    let parts=[hhmm(t)];
    if(a) parts.push('LWS '+fmtSol(a.net));
    if(b) parts.push('NULL '+fmtSol(b.net));
    if(a&&b) parts.push('Δ '+fmtSol(a.net-b.net));
    readTx.textContent=parts.join('  ·  ');
    // position readout box, kept inside the plot
    const tw=readTx.getComputedTextLength?readTx.getComputedTextLength():parts.join('  ·  ').length*6.4;
    let bx=Math.min(x+8, W-R-tw-14); bx=Math.max(L+2,bx);
    readBg.setAttribute('x',bx-6); readBg.setAttribute('y',T+2);
    readBg.setAttribute('width',tw+12);
    readTx.setAttribute('x',bx);
    cross.style.display='';
  });
  hit.addEventListener('mouseleave',()=>{ cross.style.display='none'; });
  svg.appendChild(hit);

  host.innerHTML=''; host.appendChild(svg);
}

function endpoint(svg,mk,pts,color,label){
  if(!pts.length) return;
  const last=pts[pts.length-1];
  const x=CHART.xOf(last.t), y=CHART.yOf(last.net);
  svg.appendChild(mk('circle',{cx:x,cy:y,r:3.2,fill:color}));
  // floating chip on the panel gutter at the right edge
  const isL=label==='LWS';
  const txt=fmtSol(last.net)+' SOL';
  const w=txt.length*6.6+16, cx=CHART.W-CHART.R+10;
  let cy=Math.max(CHART.T+11, Math.min(CHART.H-CHART.B-11, y));
  svg.appendChild(mk('rect',{x:cx,y:cy-11,rx:3,width:w,height:22,
    fill:C.panel,stroke:isL?color:C.hair,'stroke-width':1}));
  const tx=mk('text',{x:cx+8,y:cy+4,'font-size':11.5,fill:isL?color:C.muted});
  tx.setAttribute('font-family','JetBrains Mono, monospace');
  tx.style.fontVariantNumeric='tabular-nums';
  tx.textContent=txt;
  svg.appendChild(tx);
}

function nearest(pts,t){
  if(!pts.length) return null;
  let best=pts[0],bd=Math.abs(pts[0].t-t);
  for(const p of pts){ const d=Math.abs(p.t-t); if(d<bd){bd=d;best=p;} }
  return best;
}

function emptySubline(state){
  const fc=(state.feed_count||0).toLocaleString('en-US');
  const open=(state.tiles&&state.tiles.open)||0;
  if(open>0) return open+' positions open · awaiting first exit';
  return 'feed live · '+fc+' buys/sells observed · 0 positions resolved';
}

// --------- tiles -----------------------------------------------------------
function drawTiles(t){
  const set=(id,v)=>{ const e=document.getElementById(id); if(e)e.textContent=v; };
  const cls=(id,c)=>{ const e=document.getElementById(id); if(e)e.className='val num'+(c?(' '+c):''); };

  // 1 NET SOL · LWS
  if(t.resolved>0){
    set('t-net',fmtSol(t.net_sol_lws));
    cls('t-net', t.net_sol_lws<0 ? 'sell' : 'amber');
    set('t-net-sub','vs NULL '+fmtSol(t.vs_null));
  } else {
    set('t-net','—'); cls('t-net','amber'); set('t-net-sub','no trades yet');
  }
  // 2 RESOLVED
  set('t-resolved',String(t.resolved)); set('t-resolved-sub',t.open+' open');
  // 3 UNEXITABLE
  set('t-unex',String(t.unexitable));
  cls('t-unex', t.unexitable>0 ? 'sell' : '');
  set('t-unex-sub', (t.resolved>0? t.unexitable_pct.toFixed(0):'0')+'% of resolved');
  // 4 OPEN BOOK
  set('t-open',String(t.open));
  // 5 B20B VETO
  set('t-veto', t.veto_rate==null ? '—' : t.veto_rate.toFixed(1)+'%');
  set('t-veto-sub', t.veto_v+' / '+t.veto_d+' decisions');
  // 6 COVERAGE
  set('t-cov', t.coverage==null ? '—' : t.coverage.toFixed(0)+'%');
  set('t-cov-sub', t.coverage_r+' / '+t.coverage_c+' reconciled');

  // NULL key annotation
  const kn=document.getElementById('key-null');
  if(kn){ kn.style.opacity = t.null_present ? '1' : '0.5';
    kn.lastChild.textContent = t.null_present ? 'NULL' : 'NULL · awaiting'; }
}

// --------- tape ------------------------------------------------------------
function drawTape(tape){
  const body=document.getElementById('tape-body');
  const split=document.getElementById('tape-split');
  if(!tape || tape.length===0){
    body.innerHTML='<div class="tape-empty">tape idle · awaiting events</div>';
    split.textContent='—'; lastFirstT=null; return;
  }
  let buys=0,sells=0;
  for(const e of tape){ if(e.is_buy)buys++; else sells++; }
  split.textContent=buys+' buys · '+sells+' sells';

  const newestT = tape[0].t;
  const frag=document.createDocumentFragment();
  for(const e of tape){
    const dust = e.sol < 0.0005;
    const r=el('div','row '+(e.is_buy?'buy':'sell')+(dust?' dust':''));
    if(lastFirstT!=null && e.t!=null && e.t>lastFirstT) r.classList.add('fresh');
    r.appendChild(el('span','tick'));
    r.appendChild(el('span','side',e.is_buy?'BUY':'SELL'));
    r.appendChild(el('span','sol',e.sol.toFixed(3)));
    r.appendChild(el('span','mint',shortMint(e.mint)));
    r.appendChild(el('span','rt',relTime(e.t)));
    const integ=el('span','integ'+((e.anchored||e.reconciled)?' on':''));
    r.appendChild(integ);
    frag.appendChild(r);
  }
  body.innerHTML=''; body.appendChild(frag);
  lastFirstT=newestT;
}

// --------- chrome liveness -------------------------------------------------
function drawHealth(h){
  const line=document.getElementById('liveline');
  const dot=document.getElementById('dot');
  if(!h || !h.present){
    line.textContent='FEED STALE'; dot.style.background=C.amber; return;
  }
  const fresh = (h.status==='FRESH');
  const ago = h.observed_sec!=null ? relTime(h.observed_sec) : '—';
  const lag = h.lag!=null ? h.lag : '—';
  line.textContent = fresh
    ? ('FEED FRESH · lag '+lag+' · updated '+ago+' ago')
    : ('FEED '+(h.status||'STALE')+' · updated '+ago+' ago');
  dot.style.background=C.amber; // amber = ours/live, always
}

// --------- poll loop -------------------------------------------------------
async function poll(){
  try{
    const res=await fetch('/api/state',{cache:'no-store'});
    if(!res.ok) throw new Error('http '+res.status);
    const s=await res.json();
    window.__last=s;                       // kept for resize redraws
    drawHealth(s.health);
    drawTiles(s.tiles||{});
    drawChart(s);
    drawTape(s.tape||[]);
  }catch(e){
    const line=document.getElementById('liveline');
    if(line) line.textContent='reconnecting…';
  }
}
// redraw only the curve on resize (cheap; tiles/tape unaffected by width)
window.addEventListener('resize',()=>{ if(window.__last) drawChart(window.__last); });
poll();
setInterval(poll,2000);
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# HTTP server
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/index.html":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/state":
            try:
                body = json.dumps(build_state()).encode("utf-8")
            except Exception as exc:  # never 500 the poll — return an empty shell
                body = json.dumps({
                    "equity_lws": [], "equity_null": [], "tape": [],
                    "feed_count": 0, "tiles": {}, "health": {"present": False},
                    "error": str(exc),
                }).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, *args):  # keep the console quiet / calm
        return


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"AFTERSHOCK · PAC / LWS — Quiet Desk dashboard")
    print(f"  serving   http://{HOST}:{PORT}/")
    print(f"  repo root {ROOT}")
    print(f"  ledgers   {'present' if LEDGER_LWS.exists() else 'absent (empty state)'} · "
          f"feed {'present' if FEED_EVENTS.exists() else 'absent'}")
    print("  Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
