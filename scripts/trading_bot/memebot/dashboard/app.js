/* MEMEBOT paper terminal — read-only SPA with two pages (hash router):
     #/                portfolio: dense token table + summary strip
     #/token/{pool}    token detail: candlestick chart w/ bot buy/sell markers + stats
   Live-polls the local JSON API. No trading, no wallet, no mutation. */
"use strict";

const state = {
  positions: {open: [], closed: []},
  summary: null,
  tab: "open",
  sort: {key: "pnl_r", dir: -1},
  hideControl: true,   // default: hide control/null observations so the table shows the live PASS book
  chartLib: null,
  route: null,          // {name:'portfolio'} | {name:'token', pool} | {name:'evo'}
  coin: null,           // last loaded coin detail
  evo: null,            // last loaded evolutionary population snapshot
  pac: null,            // fail-closed PAC performance + measurement status
  ohlcvCache: {},       // pool|tf -> {t, data}
  chart: null,          // live lightweight-charts instance (token page)
  chartSeries: null,
  chartKey: null,       // pool|tf currently drawn
  tokenMounted: null,   // pool whose STATIC token-page shell is currently built in the DOM
  tokenBuilding: false, // true while renderTokenPage's initial fetch+build is in flight
};

/* ---------------- formatting ---------------- */
const fmtPrice = (v) => {
  if (v == null) return "—";
  if (v === 0) return "$0";
  const a = Math.abs(v);
  if (a >= 1) return "$" + v.toFixed(4);
  return "$" + v.toPrecision(4);
};
const fmtUsd = (v) => {
  if (v == null) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return "$" + (v/1e9).toFixed(2) + "B";
  if (a >= 1e6) return "$" + (v/1e6).toFixed(2) + "M";
  if (a >= 1e3) return "$" + (v/1e3).toFixed(1) + "K";
  return "$" + v.toFixed(0);
};
const fmtPct = (v) => v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1) + "%";
const fmtR   = (v) => v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(2) + "R";
const fmtAge = (m) => {
  if (m == null) return "—";
  if (m < 60) return m.toFixed(0) + "m";
  if (m < 1440) return (m/60).toFixed(1) + "h";
  return (m/1440).toFixed(1) + "d";
};
const sgn = (v) => v == null ? "" : (v > 0 ? "pos" : (v < 0 ? "neg" : "muted"));
const esc = (s) => (s==null?"":String(s)).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const logoImg = (pool, sym, cls) =>
  `<img class="${cls||''}" src="/api/logo/${encodeURIComponent(pool)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;

async function getJSON(url){
  const r = await fetch(url, {cache:"no-store"});
  if(!r.ok) throw new Error("HTTP "+r.status);
  return r.json();
}

/* ---------------- live indicator ---------------- */
function setLive(ok, txt){
  const d = document.getElementById("liveDot");
  d.className = "ld " + (ok ? "on" : "err");
  document.getElementById("liveText").textContent = txt || (ok ? "live" : "offline");
}
function stampUpdated(){
  document.getElementById("updAt").textContent = "updated " + new Date().toLocaleTimeString();
}

/* ---------------- router ---------------- */
function parseRoute(){
  const h = location.hash.replace(/^#/, "");
  const m = h.match(/^\/token\/(.+)$/);
  if (m) return {name:"token", pool: decodeURIComponent(m[1])};
  if (h === "/evo") return {name:"evo"};
  if (h === "/pac") return {name:"pac"};
  if (h === "/exit") return {name:"exit"};
  if (h === "/aftershock") return {name:"aftershock"};
  if (h === "/aftershock-v2") return {name:"av2"};
  if (h === "/aftershock-v3") return {name:"av3"};
  if (h === "/aftershock-v4") return {name:"av4"};
  if (h === "/aftershock-v5") return {name:"av5"};
  return {name:"portfolio"};
}
function highlightNav(){
  const name = state.route ? state.route.name : "portfolio";
  document.querySelectorAll(".navlink").forEach(a => {
    const r = a.dataset.route;
    // token detail is reached from the portfolio, so keep PORTFOLIO lit there too
    a.classList.toggle("on", r === name || (r === "portfolio" && name === "token"));
  });
}
function onRoute(){
  // Tear down any live chart + its resize observer when leaving the token page, and forget the
  // mounted shell so re-entering rebuilds cleanly (no leaked chart instances / observers).
  if (state.chart){ try{ state.chart.remove(); }catch(e){} state.chart = null; state.chartSeries = null; state.chartKey = null; }
  if (drawLW._ro){ try{ drawLW._ro.disconnect(); }catch(e){} }
  state.tokenMounted = null;
  state.route = parseRoute();
  highlightNav();
  if (state.route.name === "token") renderTokenPage(state.route.pool);
  else if (state.route.name === "pac") renderPAC();
  else if (state.route.name === "evo") renderEvo();
  else if (state.route.name === "exit") renderExit();
  else if (state.route.name === "aftershock") renderAftershock();
  else if (state.route.name === "av2") renderAftershockV2({family:"av2"});
  else if (state.route.name === "av3") renderAftershockV2({family:"av3"});
  else if (state.route.name === "av4") renderAftershockV2({family:"av4"});
  else if (state.route.name === "av5") renderAftershockV2({family:"av5"});
  else renderPortfolio();
}

/* ================= PAGE 1 — PORTFOLIO ================= */
const COLS = [
  {k:"symbol", t:"Token", l:true},
  {k:"variant", t:"Var", l:true},
  {k:"entry_price_usd", t:"Entry"},
  {k:"current_price_usd", t:"Price"},
  {k:"pnl_pct", t:"P&L %"},
  {k:"pnl_r", t:"R"},
  {k:"market_cap_usd", t:"MCap"},
  {k:"liquidity_usd", t:"Liq"},
  {k:"age_minutes", t:"Age"},
  {k:"status", t:"Status", l:true},
];

function currentRows(){
  let rows;
  if(state.tab === "open") rows = state.positions.open.slice();
  else if(state.tab === "closed") rows = state.positions.closed.slice();
  else rows = state.positions.open.concat(state.positions.closed);
  if(state.hideControl) rows = rows.filter(r => !r.control);
  if(state.liveOnly) rows = rows.filter(r => r.live);   // only coins still trading (moving charts)
  const {key, dir} = state.sort;
  rows.sort((a,b) => {
    // LIVE coins (still trading) always float above dead ones, so opening the page / clicking the top
    // row lands on a moving chart. Within each liveness group, sort by more-recent-candles first, then
    // fall back to the user's chosen column sort.
    const al = (a.status==="OPEN" && a.live)?1:0, bl = (b.status==="OPEN" && b.live)?1:0;
    if(al !== bl) return bl - al;
    if(al && bl){
      const ca = a.recent_candles||0, cb = b.recent_candles||0;
      if(ca !== cb) return cb - ca;   // most-active first among live coins
    }
    let x = a[key], y = b[key];
    if(x == null && y == null) return 0;
    if(x == null) return 1; if(y == null) return -1;
    if(typeof x === "string") return dir * x.localeCompare(y);
    return dir * (x - y);
  });
  return rows;
}

function renderPortfolio(){
  const app = document.getElementById("app");
  app.innerHTML = `
    <section id="strip" class="strip"></section>
    <div class="pagehd">
      <h2>Portfolio</h2>
      <div class="tabs" id="tabs">
        <button class="tab" data-tab="open">Open <span class="cnt" id="cO">0</span></button>
        <button class="tab" data-tab="closed">Closed <span class="cnt" id="cC">0</span></button>
        <button class="tab" data-tab="all">All</button>
      </div>
      <span class="grow"></span>
      <label class="ctltoggle"><input type="checkbox" id="liveOnly"> live only <span class="rowlive on" style="position:static;display:inline-block;vertical-align:middle"></span></label>
      <label class="ctltoggle"><input type="checkbox" id="hideControl"> hide control/null</label>
    </div>
    <div class="tablewrap">
      <table class="grid"><thead id="pHead"></thead><tbody id="pBody"></tbody></table>
    </div>
    <div id="truncNote" class="truncnote"></div>`;
  document.querySelectorAll("#tabs .tab").forEach(b => {
    b.classList.toggle("on", b.dataset.tab === state.tab);
    b.onclick = () => { state.tab = b.dataset.tab;
      document.querySelectorAll("#tabs .tab").forEach(x=>x.classList.toggle("on", x===b)); renderRows(); };
  });
  const hc = document.getElementById("hideControl");
  hc.checked = state.hideControl;
  hc.onchange = e => { state.hideControl = e.target.checked; renderRows(); };
  const lo = document.getElementById("liveOnly");
  if(lo){ lo.checked = !!state.liveOnly;
    lo.onchange = e => { state.liveOnly = e.target.checked; renderRows(); }; }
  renderStrip(); renderHead(); renderRows();
}

function renderStrip(){
  const s = state.summary; if(!s){ return; }
  const scr = s.pass_expectancy || {};
  const cells = [
    {lbl:"Paper invested", val:(s.invested_sol ?? 0).toFixed(2)+" SOL", sub:`${s.open_positions} open`, cls:""},
    {lbl:"Total P&L (PASS)", val:fmtR(s.cum_R_pass), sub:`${s.resolved_pass} resolved`, cls:sgn(s.cum_R_pass)},
    {lbl:"Win rate", val:(s.win_rate==null?"—":(s.win_rate*100).toFixed(0)+"%"), sub:"realised", cls:""},
    {lbl:"Expectancy /trade", val:(scr.expectancy_R==null?"—":fmtR(scr.expectancy_R)), sub:"net of ~3% toll · not a verdict", cls:sgn(scr.expectancy_R)},
    {lbl:"Control null", val:fmtR(s.cum_R_control), sub:`${s.resolved_control} reject-coins`, cls:sgn(s.cum_R_control)},
  ];
  document.getElementById("strip").innerHTML = cells.map(c =>
    `<div class="cell"><div class="lbl">${esc(c.lbl)}</div><div class="val ${c.cls}">${esc(c.val)}</div><div class="sub">${esc(c.sub)}</div></div>`).join("");
}

function renderHead(){
  document.getElementById("pHead").innerHTML = "<tr>" + COLS.map(c => {
    const ar = state.sort.key===c.k ? `<span class="ar">${state.sort.dir<0?"▼":"▲"}</span>` : "";
    return `<th class="${c.l?"l":""}" data-k="${c.k}">${c.t}${ar}</th>`;
  }).join("") + "</tr>";
  document.getElementById("pHead").onclick = ev => {
    const th = ev.target.closest("th"); if(!th) return;
    const k = th.dataset.k;
    if(state.sort.key===k) state.sort.dir *= -1; else state.sort = {key:k, dir:-1};
    renderHead(); renderRows();
  };
}

function renderRows(){
  const cO = document.getElementById("cO"), cC = document.getElementById("cC");
  // The server caps the closed payload to the most-recent slice; show the TRUE total on the tab.
  const closedTotal = (state.positions.closed_total != null) ? state.positions.closed_total : state.positions.closed.length;
  if(cO) cO.textContent = state.positions.open.length;
  if(cC) cC.textContent = closedTotal;
  const rows = currentRows();
  const body = document.getElementById("pBody");
  if(!body) return;
  const noteEl = document.getElementById("truncNote");
  if(noteEl){
    const trunc = state.positions.closed_truncated && state.tab !== "open";
    noteEl.textContent = trunc
      ? `showing ${state.positions.closed_shown} most-recent of ${closedTotal} closed — full history is in the ledgers`
      : "";
  }
  body.innerHTML = rows.map(r => {
    const st = String(r.status||"").toLowerCase();
    const badge = (r.control && r.status!=="OPEN")
      ? `<span class="badge b-null">${esc(r.status)}</span>`
      : `<span class="badge b-${esc(st)}">${esc(r.status)}</span>`;
    const hint = r.live_hint && r.live_hint!=="OPEN" ? `<span class="hint">${esc(r.live_hint)}</span>` : "";
    const full = (r.name && r.name !== r.symbol) ? esc(r.name) : "";
    const livedot = r.status==="OPEN"
      ? `<span class="rowlive ${r.live?'on':'off'}" title="${r.live?('trading now — '+(r.recent_candles||0)+' recent candles'):'idle / dead — no recent trades'}"></span>`
      : "";
    return `<tr data-pool="${esc(r.pool_address)}">
      <td class="l"><div class="coin">${logoImg(r.pool_address)}<div class="nm">
        <div class="sym">${livedot}${esc(r.symbol)}</div>
        <div class="full">${full}</div></div></div></td>
      <td class="l"><span class="vtag">${esc(r.variant)}</span></td>
      <td>${fmtPrice(r.entry_price_usd)}</td>
      <td>${fmtPrice(r.current_price_usd)}</td>
      <td class="${sgn(r.pnl_pct)}">${fmtPct(r.pnl_pct)}</td>
      <td class="${sgn(r.pnl_r)}">${fmtR(r.pnl_r)}</td>
      <td class="muted">${fmtUsd(r.market_cap_usd)}</td>
      <td class="muted">${fmtUsd(r.liquidity_usd)}</td>
      <td class="muted">${fmtAge(r.age_minutes)}</td>
      <td class="l">${badge}${hint}</td>
    </tr>`;
  }).join("") || `<tr><td class="empty l" colspan="${COLS.length}">no positions in this view</td></tr>`;
  body.querySelectorAll("tr[data-pool]").forEach(tr =>
    tr.onclick = () => { location.hash = "#/token/" + encodeURIComponent(tr.dataset.pool); });
}

/* ================= PAGE 2 — TOKEN DETAIL ================= */

// Timeframe selector. The server tells us which frames actually have data for THIS coin
// (tf_available / tf_counts): the sub-minute 1s/5s frames live ONLY in the local memestream cache, so
// they're greyed out (disabled) when this coin has no such candles yet — instead of a click silently
// snapping back to 1m. 1m+ are GeckoTerminal-backed and always offered.
function tfState(d){
  const avail = (d && d.tf_available) || {};
  const counts = (d && d.tf_counts) || {};
  return ["1s", "5s", "1m", "5m", "15m", "1h"].map(tf => {
    const localOnly = (tf === "1s" || tf === "5s");
    const ok = localOnly ? (avail[tf] !== false && (counts[tf] || 0) > 0) : (avail[tf] !== false);
    const cnt = (localOnly && counts[tf]) ? ` (${counts[tf]})` : "";
    return {tf, ok, label: tf + cnt};
  });
}

/* ---------------------------------------------------------------------------
   TOKEN PAGE — split into a STATIC shell (built ONCE per token on navigation)
   and DYNAMIC updates (every 6s poll). The chart element and its lightweight-
   charts instance are created ONCE and reused; the 6s poll only pushes fresh
   TEXT and fresh candle DATA in place. Nothing rebuilds #app or #chart on a
   poll, so the chart never flashes "loading candles…" or resets.
   --------------------------------------------------------------------------- */

// Called on route change (onRoute). Fetches once, then builds the static shell.
async function renderTokenPage(pool){
  const app = document.getElementById("app");
  app.innerHTML = `<a class="back" href="#/">&larr; Portfolio</a><div class="empty">loading ${esc(pool.slice(0,8))}…</div>`;
  state.tokenMounted = null;
  state.tokenBuilding = true;
  let d;
  try { d = await getJSON("/api/coin/" + encodeURIComponent(pool)); }
  catch(e){ state.tokenBuilding = false;
    app.innerHTML = `<a class="back" href="#/">&larr; Portfolio</a><div class="empty">failed to load token</div>`; return; }
  // route may have changed while the fetch was in flight — don't clobber a newer page
  if(!state.route || state.route.name !== "token" || state.route.pool !== pool){ state.tokenBuilding = false; return; }
  if(d._error){ state.tokenBuilding = false;
    app.innerHTML = `<a class="back" href="#/">&larr; Portfolio</a><div class="empty">${esc(d._error)}</div>`; return; }
  try { buildTokenPage(d); }
  catch(e){
    console.error("token page build:", e);
    app.innerHTML = `<a class="back" href="#/">&larr; Portfolio</a><div class="empty">render error: ${esc(String(e && e.message || e))}</div>`;
  } finally { state.tokenBuilding = false; }
}

// Build the STATIC layout for a token ONCE: header (with id'd dynamic price/P&L slots), the timeframe
// bar (handlers wired here, once), an EMPTY persistent #chart, and an empty #statcol. Then populate the
// dynamic parts and draw the first chart. state.tokenMounted marks this pool's shell as live.
function buildTokenPage(d){
  state.coin = d;
  state.tf = "1m";   // opening a fresh coin starts at 1m; the selection then persists across polls
  // fresh shell => any prior chart instance is gone with the old DOM; reset so loadChart recreates
  if(state.chart){ try{ state.chart.remove(); }catch(e){} }
  state.chart = null; state.chartSeries = null; state.chartKey = null;

  const row = d.row||{}, verdict = d.screen_verdict || "?";
  document.getElementById("app").innerHTML = `
    <a class="back" href="#/">&larr; Portfolio</a>
    <div class="tpage">
      <div class="thead">
        ${logoImg(d.pool_address)}
        <div class="tt">
          <div class="tsym">${esc(row.symbol)} <span class="vtag">${esc(d.variant)}</span>
            <span class="verdict ${esc(verdict)}">${esc(verdict)}</span></div>
          <div class="tfull">${esc(row.name||"")} · ${esc(d.pool_address.slice(0,12))}…<span id="tExit"></span></div>
        </div>
        <div class="tprice">
          <div class="p num" id="tPrice">—</div>
          <div class="pl num" id="tPnl">—</div>
        </div>
      </div>
      <div class="tbody">
        <div class="chartcol">
          <div class="chartbar">
            <span class="lg"><span class="tri up">▲</span> bot BUY</span>
            <span class="lg"><span class="tri dn">▼</span> bot SELL</span>
            <span class="lg"><span class="ln" style="border-color:var(--red)"></span> stop</span>
            <span class="lg"><span class="ln" style="border-color:var(--mint)"></span> target</span>
            <span class="tf" id="tf">${tfState(d).map(b =>
              `<button class="tfbtn${b.tf===state.tf?" on":""}${b.ok?"":" disabled"}" data-tf="${b.tf}"${b.ok?"":" disabled"}${b.ok?"":` title="no ${b.tf} candles for this coin yet"`}>${b.label}</button>`).join("")}</span>
          </div>
          <div class="chartstatus" id="chartStatus">&nbsp;</div>
          <div id="chart"><div class="msg">loading candles…</div></div>
        </div>
        <div class="statcol" id="statcol"></div>
      </div>
    </div>`;

  // Timeframe buttons: handlers wired ONCE here. A poll only patches their labels/disabled state,
  // never re-creates them, so these handlers survive for the life of the page.
  document.querySelectorAll("#tf button").forEach(b => b.onclick = () => {
    if(b.disabled) return;   // greyed-out frame (no data for this coin) — ignore the click
    if(state.tf === b.dataset.tf) return;
    state.tf = b.dataset.tf;   // remember the selection so the 6s poll's redraw doesn't reset it to 1m
    document.querySelectorAll("#tf button").forEach(x=>x.classList.toggle("on", x===b));
    // explicit user switch => rebuild the chart for the new frame (fetches fresh candles)
    if(state.chart){ try{state.chart.remove();}catch(e){} }
    state.chart = null; state.chartSeries = null; state.chartKey = null;
    const box = document.getElementById("chart");
    if(box) box.innerHTML = `<div class="msg">loading ${esc(b.dataset.tf)} candles…</div>`;
    loadChart(state.coin, b.dataset.tf);
  });

  state.tokenMounted = d.pool_address;
  updateTokenPage(d);          // fills dynamic text + stat column, and draws the first chart (loadChart)
}

// Called every 6s for the SAME token. NO DOM rebuild of #app or #chart: update the header/stat TEXT in
// place, patch the timeframe buttons in place, and push fresh candle DATA into the EXISTING chart.
function updateTokenPage(d){
  state.coin = d;
  const row = d.row||{}, live = d.live||{}, e = d.entry||{};
  const price = d.is_open ? live.price_usd : row.exit_price_usd;

  // --- header price / P&L / exit line (textContent only; logo <img> is never touched → no reload) ---
  const priceEl = document.getElementById("tPrice");
  if(priceEl) priceEl.textContent = fmtPrice(price);
  const pnlEl = document.getElementById("tPnl");
  if(pnlEl){ pnlEl.textContent = `${fmtPct(row.pnl_pct)} · ${fmtR(row.pnl_r)}`; pnlEl.className = "pl num " + sgn(row.pnl_r); }
  const exitEl = document.getElementById("tExit");
  if(exitEl) exitEl.innerHTML = d.resolution
    ? `<span class="muted"> · exit ${esc(d.resolution.resolution_reason)} @ ${fmtPrice(d.resolution.exit_price_usd)} · held ${fmtAge(d.resolution.held_minutes)}</span>` : "";

  // --- timeframe buttons: patch label/disabled/on in place (handlers preserved) ---
  const st = tfState(d);
  document.querySelectorAll("#tf button").forEach(b => {
    const s = st.find(x => x.tf === b.dataset.tf); if(!s) return;
    b.disabled = !s.ok; b.classList.toggle("disabled", !s.ok);
    if(!s.ok) b.title = `no ${s.tf} candles for this coin yet`; else b.removeAttribute("title");
    if(b.textContent !== s.label) b.textContent = s.label;
    b.classList.toggle("on", b.dataset.tf === (state.tf || "1m"));
  });

  // --- stat column: no chart / no <img> inside, so a text rebuild here can't flicker the chart ---
  const sc = document.getElementById("statcol");
  if(sc) sc.innerHTML = statColHTML(d);

  // --- chart DATA in place (reuses the existing chart instance; preserves zoom/pan) ---
  loadChart(d, state.tf || "1m");
}

// Inner HTML of the stat column — pure text, safe to rebuild each poll.
function statColHTML(d){
  const row = d.row||{}, live = d.live||{}, e = d.entry||{}, verdict = d.screen_verdict || "?";
  const price = d.is_open ? live.price_usd : row.exit_price_usd;
  const liq = live.liquidity_usd ?? row.liquidity_usd;

  const flags = [];
  const sells = live.sells, buys = live.buys, sellers = live.sellers;
  flags.push(sellers>0 || sells>0
    ? {c:"ok", t:"Sells present in feed — not an obvious honeypot"}
    : {c:"warn", t:"No sells seen in window — exit liquidity unconfirmed"});
  flags.push((liq!=null && liq>=3000)
    ? {c:"ok", t:`Liquidity ${fmtUsd(liq)} ≥ screen floor`}
    : {c:"bad", t:`Thin liquidity ${fmtUsd(liq)}`});
  if (buys!=null && live.buyers) flags.push(buys/live.buyers <= 4
    ? {c:"ok", t:`Buys/buyer ${(buys/live.buyers).toFixed(1)} — no wash-buy flag`}
    : {c:"warn", t:`Buys/buyer ${(buys/live.buyers).toFixed(1)} — concentrated buying`});
  flags.push(d.control
    ? {c:"warn", t:"CONTROL / null — screen REJECTED this coin (benchmark)"}
    : {c:"ok", t:"Screen PASS — no red flag on free-feed proxies"});

  const stat = (k,v) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${v}</span></div>`;
  // Source of each stat, so the panel can honestly tag it. Ordering server-side is:
  //   live/chain  ->  GeckoTerminal  ->  entry feed_snapshot  ->  "—".
  // chain_filled = filled live from the Chainstack candle cache/RPC (GT is usually 429-starved);
  // entry_filled = filled from the frozen ENTRY snapshot (a DEAD coin's "how it looked when we bought").
  const cf = new Set(live.chain_filled || []), ef = new Set(live.entry_filled || []);
  const chainTag = `<span class="muted"> · chain</span>`, entryTag = `<span class="muted"> · @entry</span>`;
  const anyChain = (ks)=>ks.some(k=>cf.has(k)), anyEntry = (ks)=>ks.some(k=>ef.has(k));
  const tagFor = (ks)=> anyChain(ks) ? chainTag : (anyEntry(ks) ? entryTag : "");
  const mktTag  = tagFor(["price_usd","market_cap_usd","liquidity_usd","fdv_usd","volume_usd_m5"]);
  const flowTag = tagFor(["buyers","buys","sells","sellers"]);
  return `
    <div class="statgrp"><div class="h">Market${mktTag}</div>
      ${stat("Price", fmtPrice(price))}
      ${stat("Market cap", fmtUsd(live.market_cap_usd ?? row.market_cap_usd))}
      ${stat("Liquidity", fmtUsd(liq))}
      ${stat("FDV", fmtUsd(live.fdv_usd))}
      ${stat("Volume 5m", fmtUsd(live.volume_usd_m5))}
    </div>
    <div class="statgrp"><div class="h">Flow${d.flow?" · live 1s cache 60s":flowTag}</div>
      ${stat("Unique buyers", live.buyers ?? "—")}
      ${stat("Buys / sells", `${live.buys ?? "—"} / ${live.sells ?? "—"}`)}
      ${stat("Sellers", live.sellers ?? "—")}
      ${d.flow ? stat("Net flow 60s", `<span class="${sgn(d.flow.net)}">${d.flow.net>=0?"+":""}${fmtUsd(d.flow.net)}</span>`) : ""}
      ${d.flow ? stat("Buy fraction", d.flow.buy_frac==null?"—":(d.flow.buy_frac*100).toFixed(0)+"%") : ""}
    </div>
    <div class="statgrp"><div class="h">Bot position — ${esc(d.variant)}</div>
      ${stat("Entry", fmtPrice(e.entry_price_usd))}
      ${stat("Stop", `<span class="neg">${fmtPrice(e.stop_price_usd)}</span>`)}
      ${stat("Target", `<span class="pos">${fmtPrice(e.target_price_usd)}</span>`)}
      ${stat("Size", (e.size_sol ?? "—")+" SOL")}
      ${stat("Horizon", (e.horizon_minutes ?? "—")+" min")}
      ${stat("P&L", `<span class="${sgn(row.pnl_r)}">${fmtPct(row.pnl_pct)} · ${fmtR(row.pnl_r)}</span>`)}
      ${stat("Status", `<span class="badge b-${String(row.status||"").toLowerCase()}">${esc(row.status)}</span>`)}
    </div>
    <div class="statgrp"><div class="h">Security / behaviour</div>
      <div class="flags">${flags.map(f=>`<div class="flag"><span class="dot ${f.c}"></span>${esc(f.t)}</div>`).join("")}</div>
    </div>
    <div class="statgrp reasons"><div class="h">Screen decision — ${esc(verdict)}</div>
      <ul>${(d.screen_reasons||["—"]).map(r=>`<li>${esc(r)}</li>`).join("")}</ul>
    </div>`;
}

/* ---------------- chart ---------------- */
async function loadChart(d, tf){
  const box = document.getElementById("chart");
  if(!box || !d) return;
  const key = `${d.pool_address}|${tf}`;
  let cache = state.ohlcvCache[key];
  const fresh = cache && (Date.now() - cache.t) < 8000;
  if(!fresh){
    // pass the bot's entry time so the server can guarantee the BUY marker is within the candle range
    const buy = (d.markers||[]).find(m=>m.type==="buy" && m.utc);
    const since = buy ? Math.floor(new Date(buy.utc).getTime()/1000) : "";
    try {
      const data = await getJSON(`/api/ohlcv/${encodeURIComponent(d.pool_address)}?tf=${tf}&limit=600&since=${since}`);
      cache = {t: Date.now(), data};
      state.ohlcvCache[key] = cache;
    } catch(e){ if(!cache) { if(!state.chart) box.innerHTML = `<div class="msg" style="color:var(--red)">candle fetch failed</div>`; return; } }
  }
  // Stale-fetch guard: while we were awaiting, the user may have navigated away (a new #chart, or none)
  // or switched timeframe. Dropping the stale result here stops old-frame candles from clobbering the
  // freshly selected chart — and keeps a live chart on screen instead of flashing an error.
  if(document.getElementById("chart") !== box) return;
  if(tf !== (state.tf || "1m")) return;
  let candles = (cache.data.candles)||[];
  const e = d.entry||{};
  // MOST memecoins we hold are dead/thin: no local 1s candles and GeckoTerminal's 1m history is
  // rate-limited, so `candles` is empty for ~all coins. Rather than a blank "no candles" panel (which
  // reads as "the chart is broken"), synthesise a minimal price line from the data we ALWAYS have —
  // the frozen entry price at entry time and the current live price now — so the chart still shows the
  // trade context (entry, stop, target, buy/sell markers) instead of nothing.
  if(candles.length < 2){
    const nowSec = Math.floor(Date.now()/1000);
    const entryP = e.entry_price_usd;
    const buy = (d.markers||[]).find(m=>m.type==="buy" && m.utc);
    const entrySec = buy ? Math.floor(new Date(buy.utc).getTime()/1000)
      : (e.decided_utc ? Math.floor(new Date(e.decided_utc).getTime()/1000) : nowSec-600);
    const row = d.row||{}, live = d.live||{};
    const curP = (d.is_open ? (live.price_usd ?? row.current_price_usd) : row.exit_price_usd) ?? entryP;
    if(entryP != null || curP != null){
      const p0 = entryP ?? curP, p1 = curP ?? entryP;
      // a flat candle at entry and one at now → the draw path renders a line with stop/target + markers
      const synth = [
        {time: Math.min(entrySec, nowSec-1), open:p0, high:p0, low:p0, close:p0, volume:0},
        {time: nowSec, open:p1, high:Math.max(p0,p1), low:Math.min(p0,p1), close:p1, volume:0},
      ];
      // keep whatever single real candle exists, then the synthetic anchor
      candles = candles.length ? candles.concat([{time:nowSec, open:candles[candles.length-1].close,
        high:candles[candles.length-1].close, low:candles[candles.length-1].close, close:curP ?? p1, volume:0}]) : synth;
      box.dataset.synthetic = "1";
    } else {
      // only paint the "no data" message on the FIRST load; never wipe a chart that's already drawn
      if(!state.chart) box.innerHTML = `<div class="msg">no price data yet for this coin${cache.data.error?` (rate-limited, retrying)`:""}</div>`;
      return;
    }
  } else { delete box.dataset.synthetic; }
  const lines = {entry:e.entry_price_usd, stop:e.stop_price_usd, target:e.target_price_usd};
  const markers = (d.markers||[]).filter(m=>m.utc).map(m => ({
    utc:m.utc, price:m.price, type:m.type, label:m.label,
  }));
  let drew = false;
  if(state.chartLib){
    try{ drawLW(box, key, candles, markers, lines); drew = true; }
    catch(err){ console.error("lightweight-charts draw failed, using canvas:", err);
      state.chart = null; state.chartSeries = null; state.chartKey = null;
      try{ drawCanvas(box, candles, markers, lines); drew = true; }catch(e2){ if(!state.chart) box.innerHTML = `<div class="msg">chart unavailable</div>`; }
    }
  } else {
    try{ drawCanvas(box, candles, markers, lines); drew = true; }catch(e2){ if(!state.chart) box.innerHTML = `<div class="msg">chart unavailable</div>`; }
  }
  if(drew) setChartStatus(tf, candles.length, cache.data, box.dataset.synthetic === "1");
}

// Subtle freshness line under the chart bar: a pulsing green dot + frame + candle count + clock.
// Updated on every successful (re)draw so the owner can see the chart is live without any flicker.
function setChartStatus(tf, n, data, synthetic){
  const el = document.getElementById("chartStatus");
  if(!el) return;
  const src = synthetic ? "entry→now line" : (data && data.source ? data.source : (data && data.local_count ? "local cache" : "—"));
  const bar = synthetic ? "no candles yet — showing trade context" : `${n} ${esc(tf)} candles`;
  el.innerHTML = `<span class="livedot"></span>live · ${bar} · ${esc(src)} · ${new Date().toLocaleTimeString()}`;
}

function drawLW(box, key, candles, markers, lines){
  const LW = state.chartLib;
  const cdata = candles.map(c => ({time:c.time, open:c.open, high:c.high, low:c.low, close:c.close}));
  const mk = markers.map(m => ({
    time: Math.floor(new Date(m.utc).getTime()/1000),
    position: m.type==="buy" ? "belowBar" : "aboveBar",
    color: m.type==="buy" ? "#3ee08f" : "#ff4d4d",
    shape: m.type==="buy" ? "arrowUp" : "arrowDown",
    text: m.label,
  })).sort((a,b)=>a.time-b.time);

  if(state.chart && state.chartKey === key && state.chartSeries){
    // live update: same chart, just refresh data (keeps zoom)
    state.chartSeries.setData(cdata);
    if(mk.length) state.chartSeries.setMarkers(mk);
    return;
  }
  box.innerHTML = "";
  // Memecoin prices are ~1e-6, which the default 2-decimal price format renders as a useless "0.00"
  // (making entry/stop/target labels all read 0.00 and look like one line). Format tiny prices with
  // real significant digits so the axis + the entry/stop/target price-line labels show true values.
  const pfmt = (p) => (p==null||isNaN(p)) ? "" : (Math.abs(p)>=1 ? p.toFixed(4) : Number(p).toPrecision(4));
  const chart = LW.createChart(box, {
    width: box.clientWidth, height: box.clientHeight,
    layout:{background:{color:"transparent"}, textColor:"#8a93a0", fontFamily:"ui-monospace,monospace", fontSize:10},
    grid:{vertLines:{color:"rgba(36,42,51,.5)"}, horzLines:{color:"rgba(36,42,51,.5)"}},
    timeScale:{timeVisible:true, secondsVisible:false, borderColor:"#242a33"},
    rightPriceScale:{borderColor:"#242a33"},
    crosshair:{mode:0},
    localization:{ priceFormatter: pfmt },
  });
  const s = chart.addCandlestickSeries({
    upColor:"#3ee08f", downColor:"#ff4d4d", borderVisible:false,
    wickUpColor:"#3ee08f", wickDownColor:"#ff4d4d",
    priceFormat:{ type:"custom", formatter: pfmt, minMove: 1e-9 },
  });
  s.setData(cdata);
  const pl = (p,color,title) => p && s.createPriceLine({price:p, color, lineWidth:1, lineStyle:2, title, axisLabelVisible:true});
  pl(lines.entry, "#8a93a0", "entry");
  pl(lines.stop, "#ff4d4d", "stop");
  pl(lines.target, "#3ee08f", "target");
  if(mk.length) s.setMarkers(mk);
  chart.timeScale().fitContent();
  state.chart = chart; state.chartSeries = s; state.chartKey = key;
  if(!drawLW._ro){
    drawLW._ro = new ResizeObserver(() => {
      if(state.chart){ const b=document.getElementById("chart"); if(b) state.chart.applyOptions({width:b.clientWidth, height:b.clientHeight}); }
    });
  }
  drawLW._ro.disconnect(); drawLW._ro.observe(box);
}

// Canvas fallback (no CDN / offline)
function drawCanvas(box, candles, markers, lines){
  box.innerHTML = "";
  const W = box.clientWidth||700, H = box.clientHeight||440, pad={l:8,r:70,t:12,b:24};
  const cv = document.createElement("canvas"), dpr = window.devicePixelRatio||1;
  cv.width=W*dpr; cv.height=H*dpr; cv.style.width=W+"px"; cv.style.height=H+"px";
  box.appendChild(cv);
  const ctx = cv.getContext("2d"); ctx.scale(dpr,dpr);
  let lo=Math.min(...candles.map(c=>c.low), lines.stop||Infinity);
  let hi=Math.max(...candles.map(c=>c.high), lines.target||-Infinity);
  if(!isFinite(lo)) lo=Math.min(...candles.map(c=>c.low));
  if(!isFinite(hi)) hi=Math.max(...candles.map(c=>c.high));
  const padY=(hi-lo)*0.08||hi*0.01; lo-=padY; hi+=padY;
  const iw=W-pad.l-pad.r, ih=H-pad.t-pad.b;
  const x=i=>pad.l+(candles.length<=1?iw/2:(i/(candles.length-1))*iw);
  const y=p=>pad.t+(1-(p-lo)/(hi-lo))*ih;
  const cw=Math.max(1.5,Math.min(9, iw/candles.length*0.62));
  ctx.strokeStyle="rgba(36,42,51,.6)"; ctx.fillStyle="#59616d"; ctx.font="10px ui-monospace,monospace"; ctx.textBaseline="middle";
  for(let g=0;g<=4;g++){ const p=lo+(hi-lo)*g/4, yy=y(p);
    ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(W-pad.r,yy);ctx.stroke();
    ctx.fillText(p.toPrecision(3), W-pad.r+5, yy); }
  candles.forEach((c,i)=>{ const up=c.close>=c.open, col=up?"#3ee08f":"#ff4d4d", cx=x(i);
    ctx.strokeStyle=col; ctx.fillStyle=col; ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(cx,y(c.high));ctx.lineTo(cx,y(c.low));ctx.stroke();
    const yo=y(c.open), yc=y(c.close); ctx.fillRect(cx-cw/2, Math.min(yo,yc), cw, Math.max(1,Math.abs(yc-yo))); });
  const lvl=(p,col,txt)=>{ if(!p) return; const yy=y(p);
    ctx.strokeStyle=col; ctx.setLineDash([4,3]); ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(W-pad.r,yy);ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle=col; ctx.fillText(txt, pad.l+3, yy-7); };
  lvl(lines.entry,"#8a93a0","entry"); lvl(lines.stop,"#ff4d4d","stop"); lvl(lines.target,"#3ee08f","target");
  (markers||[]).forEach(m=>{ const t=new Date(m.utc).getTime()/1000; let bi=0,bd=Infinity;
    candles.forEach((c,i)=>{const dd=Math.abs(c.time-t); if(dd<bd){bd=dd;bi=i;}});
    const cx=x(bi), py=m.price?y(m.price):(m.type==="buy"?y(candles[bi].low)+14:y(candles[bi].high)-14);
    ctx.fillStyle=m.type==="buy"?"#3ee08f":"#ff4d4d"; ctx.font="bold 14px ui-monospace,monospace"; ctx.textAlign="center";
    ctx.fillText(m.type==="buy"?"▲":"▼", cx, py); ctx.textAlign="left"; });
}

/* ================= PAGE 3 — EVOLUTION / TACTIC POPULATION ================= */
// A read-only MONITOR of the evolutionary variant engine (scripts/trading_bot/memebot_evo). Every
// number is BEHAVIOUR, not a result: no genome is a winner until it reaches the N_min trade minimum
// AND beats the K-corrected noise bar sqrt(2 ln K) — and even then only on a fresh out-of-sample slice.
const EVO_COLS = [
  {t:"#",                                          l:false},
  {t:"Genome",                                     l:true},
  {t:"Tactic — horizon / stop / target / exits",   l:true},
  {t:"Entered",                                    l:false},
  {t:"Open",                                       l:false},
  {t:"Resolved PASS",                              l:false},
  {t:"Behaviour exp.",                             l:false},
  {t:"Maturity",                                   l:true},
  {t:"Status",                                     l:true},
];

function renderEvo(){
  const app = document.getElementById("app");
  app.innerHTML = `
    <section id="evoStrip" class="strip"></section>
    <div class="evobanner" id="evoBanner">${esc(state.evo && state.evo.framing || "")}</div>
    <div class="pagehd">
      <h2>Evolution · tactic population</h2>
      <span class="pill">forward-selection monitor · behaviour, not evidence</span>
    </div>
    <div class="evoverdictbar" id="evoVerdict"></div>
    <div class="tablewrap evotablewrap">
      <table class="grid evogrid"><thead id="evoHead"></thead><tbody id="evoBody"></tbody></table>
    </div>`;
  document.getElementById("evoHead").innerHTML = "<tr>" +
    EVO_COLS.map(c => `<th class="${c.l?"l":""}">${esc(c.t)}</th>`).join("") + "</tr>";
  renderEvoView();
}

function renderEvoView(){
  const e = state.evo;
  const strip = document.getElementById("evoStrip");
  if(!strip) return;                       // skeleton not mounted yet
  const banner = document.getElementById("evoBanner");
  if(banner && e && e.framing) banner.textContent = e.framing;
  if(!e){ return; }

  if(e._error){
    strip.innerHTML = `<div class="cell"><div class="lbl">evo engine</div>
      <div class="val neg">unavailable</div><div class="sub">${esc(e._error)}</div></div>`;
    const body = document.getElementById("evoBody");
    if(body) body.innerHTML = `<tr><td class="empty l" colspan="${EVO_COLS.length}">evolutionary engine not readable right now</td></tr>`;
    const vb = document.getElementById("evoVerdict"); if(vb) vb.innerHTML = "";
    return;
  }

  const bar = e.K_corrected_noise_bar_SE;
  const cells = [
    {lbl:"Generation",         val:(e.generation ?? "—"),                                  sub:"selection rounds"},
    {lbl:"Population",         val:(e.population_size ?? "—"),                              sub:"active genomes"},
    {lbl:"K evaluated",        val:(e.K_genomes_ever_evaluated ?? "—"),                    sub:"distinct genomes ever"},
    {lbl:"Noise bar √(2 ln K)",val:(bar==null?"—":bar.toFixed(2))+" SE",                   sub:"multiple-testing floor"},
    {lbl:"Resolved trades",    val:(e.resolved_pass_trades_total ?? "—"),                  sub:"forward paper"},
    {lbl:"Mature genomes",     val:(e.mature_genomes ?? "—"),                              sub:`≥ ${e.N_min_eval ?? "?"} trades`, cls:(e.mature_genomes>0?"":"muted")},
  ];
  strip.innerHTML = cells.map(c =>
    `<div class="cell"><div class="lbl">${esc(c.lbl)}</div><div class="val ${c.cls||""}">${esc(c.val)}</div><div class="sub">${esc(c.sub)}</div></div>`).join("");

  const vb = document.getElementById("evoVerdict");
  if(vb) vb.innerHTML = `<span class="vlbl">VERDICT</span>${esc(e.verdict || "—")}`;

  renderEvoRows();
}

function renderEvoRows(){
  const e = state.evo, body = document.getElementById("evoBody");
  if(!body || !e) return;
  const rows = e.leaderboard || [];
  body.innerHTML = rows.map(r => {
    const cls = r.killed ? "killed" : "";
    const nm = r.seed_name ? `<span class="seedname">${esc(r.seed_name)}</span>` : "";
    const maturity = r.mature
      ? `<span class="badge b-mature">mature</span>`
      : `<span class="badge b-imm">${esc(r.resolved_pass)}/${esc(e.N_min_eval)}</span>`;
    const status = r.killed
      ? `<span class="badge b-null">killed</span>`
      : `<span class="badge b-alive">alive</span>`;
    // clears the bar on THIS slice — explicitly NOT a verdict; must repeat on a fresh slice to be real
    const barflag = r.beats_bar
      ? `<span class="barflag" title="clears the K-corrected bar on this slice — unconfirmed, behaviour only">△ bar (unconfirmed)</span>`
      : "";
    const entered = r.entered==null ? "—"
      : `${r.entered}<span class="submini" title="PASS (signal) / CONTROL (null) entries — the frozen screen sends ~84% to the control arm">&nbsp;(${r.entered_pass ?? "?"}p/${r.entered_control ?? "?"}c)</span>`;
    return `<tr class="${cls}">
      <td class="muted">${esc(r.rank)}</td>
      <td class="l"><span class="mono">${esc(r.short)}</span>${nm}</td>
      <td class="l tactic">${esc(r.tactic_summary)}</td>
      <td title="coins this genome actually bought (PASS signal + CONTROL null)">${entered}</td>
      <td class="muted" title="still-open positions (not yet resolved)">${esc(r.open ?? "—")}</td>
      <td title="resolved PASS-arm (signal) trades — maturity counts THESE only">${esc(r.resolved_pass)}</td>
      <td class="behav" title="population expectancy — BEHAVIOUR, not a result">${fmtR(r.mean_R)}</td>
      <td class="l">${maturity}</td>
      <td class="l">${status}${barflag}</td>
    </tr>`;
  }).join("") || `<tr><td class="empty l" colspan="${EVO_COLS.length}">no genomes in the population</td></tr>`;
}

/* ================= PAGE — EXIT-SCALP (exitability-first fast-scalp) ================= */
function pctFmt(x){ return (x==null) ? "—" : (100*x).toFixed(0)+"%"; }

function renderExit(){
  const app = document.getElementById("app");
  app.innerHTML = `
    <section id="exitStrip" class="strip"></section>
    <div class="evobanner" id="exitBanner">${esc(state.exit && state.exit.framing || "")}</div>
    <div class="pagehd">
      <h2>Exit-Scalp · exitability-first</h2>
      <span class="pill">buy only what you can sell · leave before the exit closes</span>
    </div>
    <div class="evoverdictbar" id="exitVerdict"></div>
    <div class="pagehd"><h3 style="margin:0">Unexitable-dump rate — the decider (lower is better)</h3></div>
    <div class="tablewrap"><table class="grid"><thead id="exitCmpHead"></thead><tbody id="exitCmpBody"></tbody></table></div>
    <div class="pagehd"><h3 style="margin:0">Trades</h3>
      <span class="pill" id="exitTradeTabs"></span></div>
    <div class="tablewrap"><table class="grid"><thead id="exitHead"></thead><tbody id="exitBody"></tbody></table></div>`;
  document.getElementById("exitCmpHead").innerHTML =
    "<tr><th class='l'>Variant</th><th>Dump rate</th><th>Dumps</th><th>PASS resolved</th></tr>";
  document.getElementById("exitHead").innerHTML =
    "<tr><th class='l'>Token</th><th>State</th><th>Entry</th><th>Exit/Now</th><th>R</th><th class='l'>Reason</th></tr>";
  renderExitView();
}

function renderExitView(){
  const e = state.exit;
  const strip = document.getElementById("exitStrip");
  if(!strip) return;
  const banner = document.getElementById("exitBanner");
  if(banner && e && e.framing) banner.textContent = e.framing;
  if(!e) return;
  if(e._error){
    strip.innerHTML = `<div class="cell"><div class="lbl">exit-scalp</div><div class="val neg">unavailable</div><div class="sub">${esc(e._error)}</div></div>`;
    return;
  }
  const d = e.dump || {};
  const cells = [
    {lbl:"Pot growth · SCORE", val:(e.expectancy_R==null?"—":fmtR(e.expectancy_R)+"/trade"), sub:`cum ${fmtR(e.cum_R)} · this is the score`, cls:(e.expectancy_R!=null? (e.expectancy_R>0?"pos":"neg"):"muted")},
    {lbl:"Dump rate · kill-gate", val:pctFmt(d.dump_rate), sub:`${d.unexitable_dumps??0}/${d.pass_resolved??0} PASS · constraint, not score`, cls:(d.dump_rate!=null && d.dump_rate<0.20?"pos":(d.dump_rate!=null?"neg":"muted"))},
    {lbl:"PASS resolved", val:(e.resolved_pass??0)+" / "+(e.minimum??30), sub:"toward first verdict"},
    {lbl:"Exit horizon", val:(e.horizon_minutes??"—")+"m", sub:"fast — out before the drain"},
    {lbl:"Exit-path rule", val:"≥"+((e.screen&&e.screen.min_sellers)??"?")+" sellers", sub:"proven exit demanded"},
    {lbl:"Liquidity floor", val:"$"+(((e.screen&&e.screen.min_reserve_usd)||0)/1000)+"k", sub:"depth to exit through"},
  ];
  strip.innerHTML = cells.map(c =>
    `<div class="cell"><div class="lbl">${esc(c.lbl)}</div><div class="val ${c.cls||""}">${esc(c.val)}</div><div class="sub">${esc(c.sub)}</div></div>`).join("");
  const vb = document.getElementById("exitVerdict");
  if(vb) vb.innerHTML = `<span class="vlbl">VERDICT</span>${esc(e.verdict || "—")} · <span class="muted">kill ${esc(e.kill_verdict||"?")}</span>`;

  // dump-rate comparison across variants
  const cmp = document.getElementById("exitCmpBody");
  if(cmp){
    const rows = (e.dump_rate_comparison||[]).slice().sort((a,b)=>((a.dump_rate??9)-(b.dump_rate??9)));
    cmp.innerHTML = rows.map(r => {
      const me = r.instrument_id === "MEMEBOT_EXIT" ? " on" : "";
      const cls = r.dump_rate==null?"muted":(r.dump_rate<0.20?"pos":"neg");
      return `<tr class="${me}"><td class="l mono">${esc(r.instrument_id)}</td>
        <td class="${cls}">${pctFmt(r.dump_rate)}</td><td>${esc(r.unexitable_dumps??0)}</td>
        <td class="muted">${esc(r.pass_resolved??0)}</td></tr>`;
    }).join("") || `<tr><td class="empty l" colspan="4">no resolved trades yet</td></tr>`;
  }

  // trades
  const body = document.getElementById("exitBody");
  const open = (e.open_positions||[]), closed = (e.closed_positions||[]);
  const tabs = document.getElementById("exitTradeTabs");
  if(tabs) tabs.textContent = `${open.length} open · ${closed.length} closed`;
  const orow = p => `<tr><td class="l">${esc(p.symbol||p.pool||"—")}</td><td><span class="badge b-alive">open</span></td>
    <td>${esc(p.entry_price_usd??"—")}</td><td>${esc(p.current_price_usd??"—")}</td>
    <td>${fmtR(p.pnl_r)}</td><td class="l muted">held ${esc(p.held_minutes??"—")}m</td></tr>`;
  const crow = p => `<tr><td class="l">${esc(p.symbol||p.pool||"—")}</td><td class="muted">closed</td>
    <td>${esc(p.entry_price_usd??"—")}</td><td>${esc(p.exit_price_usd??"—")}</td>
    <td>${fmtR(p.realized_r)}</td><td class="l ${String(p.resolution_reason||"").includes("UNEXIT")?"neg":""}">${esc(p.resolution_reason||"—")}</td></tr>`;
  body.innerHTML = (open.map(orow).join("") + closed.map(crow).join(""))
    || `<tr><td class="empty l" colspan="6">no trades yet — the exit-first screen is selective</td></tr>`;
}

/* ================= PAGE — AFTERSHOCK (rug-absorption survivor) ================= */
function sparkline(vals){
  if(!vals || !vals.length) return "";
  const w=260, h=44, n=vals.length, mn=Math.min(...vals,1), mx=Math.max(...vals,1);
  const rng=(mx-mn)||1;
  const pts=vals.map((v,i)=>`${(i/(Math.max(1,n-1)))*w},${h-((v-mn)/rng)*(h-6)-3}`).join(" ");
  const last=vals[vals.length-1], up=last>=1;
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none">
    <line x1="0" y1="${h-((1-mn)/rng)*(h-6)-3}" x2="${w}" y2="${h-((1-mn)/rng)*(h-6)-3}" stroke="#8884" stroke-dasharray="3 3"/>
    <polyline points="${pts}" fill="none" stroke="${up?'#3fb950':'#f85149'}" stroke-width="1.5"/></svg>`;
}

function renderAftershock(){
  const app = document.getElementById("app");
  app.innerHTML = `
    <section id="asStrip" class="strip"></section>
    <div class="evobanner" id="asBanner">${esc(state.aftershock && state.aftershock.framing || "")}</div>
    <div class="pagehd"><h2>Aftershock · rug-absorption survivor</h2>
      <span class="pill">buy only the absorbed survivor · leave before the exit closes</span></div>
    <div class="evoverdictbar" id="asVerdict"></div>
    <div class="pagehd"><h3 style="margin:0">Pot-growth equity curve (SCORE)</h3></div>
    <div class="tablewrap" style="padding:8px 4px" id="asSpark"></div>
    <div class="pagehd"><h3 style="margin:0">Trades</h3><span class="pill" id="asTradeTabs"></span></div>
    <div class="tablewrap"><table class="grid"><thead id="asHead"></thead><tbody id="asBody"></tbody></table></div>`;
  document.getElementById("asHead").innerHTML =
    "<tr><th class='l'>Token</th><th>State</th><th>Entry</th><th>Exit/Now</th><th>stressed R</th><th class='l'>Reason</th></tr>";
  renderAftershockView();
}

function renderAftershockView(){
  const e = state.aftershock;
  const strip = document.getElementById("asStrip");
  if(!strip) return;
  const banner = document.getElementById("asBanner");
  if(banner && e && e.framing) banner.textContent = e.framing;
  if(!e) return;
  if(e._error){
    strip.innerHTML = `<div class="cell"><div class="lbl">aftershock</div><div class="val neg">unavailable</div><div class="sub">${esc(e._error)}</div></div>`;
    return;
  }
  const d = e.dump || {}, cn = e.control_null || {}, cc = e.cluster_concentration || {};
  const G = e.log_growth_G, pt = e.per_trade_growth;
  const cells = [
    {lbl:"Pot growth · SCORE", val:(pt==null?"—":fmtR(pt)+"/trade"), sub:`G ${G==null?"—":G} · x${e.pot_multiple==null?"—":e.pot_multiple}`, cls:(pt!=null?(pt>0?"pos":"neg"):"muted")},
    {lbl:"Dump rate · kill-gate", val:pctFmt(d.dump_rate), sub:`${d.unexitable_dumps??0}/${d.pass_resolved??0} · constraint, not score`, cls:(d.dump_rate!=null?(d.dump_rate<0.13?"pos":"neg"):"muted")},
    {lbl:"Edge vs null", val:(cn.edge_per_trade==null?"—":fmtR(cn.edge_per_trade)), sub:`vs ${cn.n_control??0} un-absorbed shocks`, cls:(cn.edge_per_trade!=null?(cn.edge_per_trade>0?"pos":"neg"):"muted")},
    {lbl:"PASS resolved", val:(e.resolved_pass??0)+" / "+(e.minimum??30), sub:"toward first verdict"},
    {lbl:"Max drawdown", val:(e.max_drawdown==null?"—":pctFmt(e.max_drawdown)), sub:"of the pot equity"},
    {lbl:"Cluster top-1", val:(cc.top1_share==null?"—":pctFmt(cc.top1_share)), sub:"G concentration (fragile if high)"},
  ];
  strip.innerHTML = cells.map(c =>
    `<div class="cell"><div class="lbl">${esc(c.lbl)}</div><div class="val ${c.cls||""}">${esc(c.val)}</div><div class="sub">${esc(c.sub)}</div></div>`).join("");
  const vb = document.getElementById("asVerdict");
  if(vb){
    const kg = e.kill_switch || {};
    const dumpV = (kg.dump_gate||{}).verdict||"?", expV = (kg.expectancy_gate||{}).verdict||"?";
    vb.innerHTML = `<span class="vlbl">VERDICT</span>${esc(e.verdict||"—")} · <span class="muted">kill ${esc(expV.split(' ')[0])} · dump-gate ${esc(dumpV.split(' ')[0])}</span>`;
  }
  const sp = document.getElementById("asSpark");
  if(sp) sp.innerHTML = (e.equity_curve && e.equity_curve.length)
    ? sparkline(e.equity_curve) : `<div class="msg">no resolved trades yet</div>`;

  const body = document.getElementById("asBody");
  const open = (e.open_positions||[]), closed = (e.closed_positions||[]);
  const tabs = document.getElementById("asTradeTabs");
  if(tabs) tabs.textContent = `${open.length} open · ${closed.length} closed`;
  const orow = p => `<tr><td class="l">${esc(p.symbol||p.pool||"—")}</td><td><span class="badge b-alive">open</span></td>
    <td>${esc(p.entry_price_usd??"—")}</td><td>${esc(p.current_price_usd??"—")}</td><td class="muted">held ${esc(p.held_minutes??"—")}m</td><td class="l muted">watching</td></tr>`;
  const crow = p => {
    const sr = p.stressed_net_return;
    const unex = String(p.resolution_reason||"").includes("UNEXIT");
    return `<tr><td class="l">${esc(p.symbol||p.pool||"—")}</td><td class="muted">closed</td>
      <td>${esc(p.entry_price_usd??"—")}</td><td>${esc(p.exit_price_usd??"—")}</td>
      <td class="${sr!=null?(sr>0?'pos':'neg'):''}">${sr==null?"—":(sr>0?'+':'')+Number(sr).toFixed(3)}</td>
      <td class="l ${unex?'neg':''}">${esc(p.resolution_reason||"—")}</td></tr>`;
  };
  body.innerHTML = (open.map(orow).join("") + closed.map(crow).join(""))
    || `<tr><td class="empty l" colspan="6">no trades yet — waits for an absorbed rug-shock</td></tr>`;
}

/* ================= PAGE 5 — AFTERSHOCK V2 (3 arms) ================= */
const AF_FAMILY = {
  av2: {title:"Aftershock V2 · payable absorption", pill:"net reserve replacement · entry-veto · executable-quote trail"},
  av3: {title:"Aftershock V3 · quote-harvest", pill:"quote-trail · ratchet · rollover harvest"},
  av4: {title:"Aftershock V4 · profit-lock", pill:"quote-trail + one-way break-even profit floor"},
  av5: {title:"Aftershock V5 · scale-out", pill:"sell half at a green target, ride half on the trail"},
};
function renderAftershockV2(opts){
  const fam = (opts && opts.family) || (opts && opts.v3 ? "av3" : "av2");
  const meta = AF_FAMILY[fam] || AF_FAMILY.av2;
  const app = document.getElementById("app");
  const data = state[fam];
  app.innerHTML = `
    <div class="pagehd"><h2>${esc(meta.title)}</h2><span class="pill">${esc(meta.pill)}</span></div>
    <div class="evobanner" id="av2Banner">${esc(data && data.framing || "")}</div>
    <div class="armgrid" id="av2Grid" data-fam="${fam}"></div>`;
  renderAftershockV2View();
}

function renderAftershockV2View(){
  const grid = document.getElementById("av2Grid");
  if(!grid) return;
  const fam = grid.dataset.fam || "av2";
  const e = state[fam];
  const banner = document.getElementById("av2Banner");
  if(banner && e && e.framing) banner.textContent = e.framing;
  if(!e) return;
  if(e._error){ grid.innerHTML = `<div class="msg neg">unavailable — ${esc(e._error)}</div>`; return; }
  const arms = e.arms || [];
  grid.innerHTML = arms.map(a => {
    if(a._error) return `<div class="armcard"><div class="armhd"><span class="armletter">${esc(a.arm)}</span><span class="armlabel">${esc(a.label||"")}</span></div><div class="msg neg">${esc(a._error)}</div></div>`;
    const pt = a.per_trade_growth, dr = a.dump_rate, ed = a.edge_vs_null;
    const killPos = String(a.kill||"").toUpperCase() === "ALIVE";
    const rows = [
      ["Pot growth", pt==null?"—":fmtR(pt)+"/tr", pt!=null?(pt>0?"pos":"neg"):"muted", `× ${a.pot_multiple==null?"—":a.pot_multiple}`],
      ["Dump rate", dr==null?"—":(dr*100).toFixed(1)+"%", dr!=null?(dr<0.13?"pos":"neg"):"muted", "kill-gate <13%"],
      ["Edge vs null", ed==null?"—":fmtR(ed), ed!=null?(ed>0?"pos":"neg"):"muted", `${a.n_control??0} nulls`],
      ["PASS resolved", (a.resolved_pass??0)+" / "+(a.minimum??30), "", "toward verdict"],
      ["Open", String(a.open??0), "muted", "positions"],
    ];
    return `<div class="armcard">
      <div class="armhd"><span class="armletter">${esc(a.arm)}</span><span class="armlabel">${esc(a.label||"")}</span>
        <span class="grow"></span><span class="killtag ${killPos?'alive':'halt'}">kill ${esc(a.kill||"—")}</span></div>
      <div class="armverdict">${esc(a.verdict||"—")}</div>
      <div class="armspark">${(a.equity_curve&&a.equity_curve.length)?sparkline(a.equity_curve):`<span class="msg">no resolved PASS yet</span>`}</div>
      <div class="armstats">${rows.map(r=>`<div class="armstat"><span class="k">${esc(r[0])}<span class="s">${esc(r[3])}</span></span><span class="v ${r[2]}">${esc(r[1])}</span></div>`).join("")}</div>
    </div>`;
  }).join("");
}

/* ================= PAGE — PAC V1 (sole focused memecoin candidate) ================= */
function pacNum(v, places=2){
  if(v==null || v==="") return "—";
  const n=Number(v); return Number.isFinite(n)?n.toFixed(places):"—";
}
function pacPct(v){
  if(v==null || v==="") return "—";
  const n=Number(v); return Number.isFinite(n)?(n*100).toFixed(1)+"%":"—";
}
function pacEquityChart(raw, evidenceStatus){
  const vals=(raw||[]).map(Number).filter(Number.isFinite);
  const data=vals.length?vals:[100];
  const w=920,h=250,l=58,r=18,t=18,b=34, innerW=w-l-r, innerH=h-t-b;
  let mn=Math.min(100,...data), mx=Math.max(100,...data);
  const pad=Math.max(1,(mx-mn)*0.18); mn-=pad; mx+=pad;
  const y=v=>t+(mx-v)/(mx-mn)*innerH;
  const x=i=>l+(data.length<=1?0:i/(data.length-1)*innerW);
  const grid=[0,.25,.5,.75,1].map(f=>{
    const yy=t+f*innerH, value=mx-f*(mx-mn);
    return `<line x1="${l}" y1="${yy}" x2="${w-r}" y2="${yy}" class="pac-gridline"/>`+
      `<text x="${l-9}" y="${yy+4}" text-anchor="end" class="pac-axis">${value.toFixed(1)}</text>`;
  }).join("");
  const pts=data.length===1?`${l},${y(data[0])} ${w-r},${y(data[0])}`:
    data.map((v,i)=>`${x(i)},${y(v)}`).join(" ");
  const baseY=y(100), last=data[data.length-1], cls=last>=100?"up":"down";
  const area=`${l},${baseY} ${pts} ${w-r},${baseY}`;
  const waiting=data.length===1?`<text x="${l+innerW/2}" y="${t+innerH/2}" text-anchor="middle" class="pac-wait">${esc(evidenceStatus==="NO_FORWARD_EVIDENCE"?"WAITING FOR ANCHORED FORWARD TRADES":"PERFORMANCE REFUSED BY EVIDENCE GATE")}</text>`:"";
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="PAC normalized performance index">
    ${grid}<line x1="${l}" y1="${baseY}" x2="${w-r}" y2="${baseY}" class="pac-baseline"/>
    <polygon points="${area}" class="pac-area ${cls}"/><polyline points="${pts}" class="pac-line ${cls}"/>
    <circle cx="${data.length===1?w-r:x(data.length-1)}" cy="${y(last)}" r="4" class="pac-point ${cls}"/>
    <text x="${l}" y="${h-10}" class="pac-axis">start</text><text x="${w-r}" y="${h-10}" text-anchor="end" class="pac-axis">${Math.max(0,data.length-1)} resolved</text>${waiting}
  </svg>`;
}
function renderPAC(){
  const app=document.getElementById("app"), d=state.pac;
  app.innerHTML=`
    <div class="pagehd pac-head"><h2>Aftershock PAC V1 · focused candidate</h2><span class="pill">PAYABLE ABSORPTION COMPRESSION</span><span class="grow"></span><span id="pacStatusBadge" class="killtag halt">loading</span></div>
    <div id="pacBoundary" class="pac-boundary"></div>
    <section id="pacStrip" class="strip"></section>
    <div class="pac-layout">
      <section class="pac-chart-card"><div class="pac-card-head"><div><span class="pac-eyebrow">PERFORMANCE</span><h3>Normalized discovery capital</h3></div><div class="pac-last" id="pacLast">—</div></div><div class="pac-chart" id="pacChart"></div><div class="pac-chart-note" id="pacChartNote"></div></section>
      <aside class="pac-side">
        <section class="pac-panel"><div class="pac-panel-title">Formula</div><div class="pac-formula" id="pacFormula">—</div><div class="pac-note" id="pacFormulaNote"></div></section>
        <section class="pac-panel"><div class="pac-panel-title">Measurement gates</div><div id="pacGates" class="pac-gates"></div></section>
      </aside>
    </div>
    <div class="pagehd"><h3 style="margin:0">Scenario activity</h3><span class="pill" id="pacTradeCount">0 resolved</span></div>
    <div class="tablewrap pac-table"><table class="grid"><thead><tr><th class="l">Mint</th><th>State</th><th>All-cost R</th><th>Entry cost</th><th>Net exit</th><th class="l">Reason</th></tr></thead><tbody id="pacBody"></tbody></table></div>`;
  renderPACView();
}
function renderPACView(){
  const d=state.pac, strip=document.getElementById("pacStrip"); if(!strip||!d) return;
  const perf=d.performance||{}, op=d.operational||{}, errors=d.integrity_errors||[];
  const valid=d.evidence_status==="VALID_PAPER_SCENARIO", noData=d.evidence_status==="NO_FORWARD_EVIDENCE";
  const statusBadge=document.getElementById("pacStatusBadge");
  if(statusBadge){ statusBadge.className=`killtag ${valid?'alive':'halt'}`; statusBadge.textContent=esc(d.evidence_status||"REFUSED"); }
  const boundary=document.getElementById("pacBoundary");
  if(boundary) boundary.innerHTML=`<strong>${esc(d.boundary||"")}</strong><span>${esc(errors[0]||(!noData?"Only fully-costed anchored rows can move this chart.":"No forward rows exist yet; baseline is not a performance result."))}</span>`;
  const cells=[
    ["Capital index",pacNum(perf.normalized_capital_index,2),`start 100 · normalized, not USD`,valid?(Number(perf.normalized_capital_index)>=100?"pos":"neg"):"muted"],
    ["Mean all-cost R",perf.mean_return_r==null?"—":(Number(perf.mean_return_r)>=0?"+":"")+pacNum(perf.mean_return_r,3),`${perf.resolved||0} fully reconciled`,perf.mean_return_r==null?"muted":(Number(perf.mean_return_r)>0?"pos":"neg")],
    ["Win rate",pacPct(perf.win_rate),`${perf.wins||0} wins · ${perf.losses||0} losses`,""],
    ["Unexitable",pacPct(perf.unexitable_rate),`${perf.full_losses||0} full losses`,perf.unexitable_rate==null?"muted":(Number(perf.unexitable_rate)<.13?"pos":"neg")],
    ["Max drawdown",pacPct(perf.max_drawdown),"normalized 100-index",perf.max_drawdown==null?"muted":""],
    ["Discovery",`${perf.resolved||0} / ${perf.minimum_discovery||100}`,`${pacPct(perf.discovery_progress)} complete`,""],
    ["Open",String((d.open_positions||[]).length),"max one position",""],
    ["Seal",esc(op.seal||"?"),`activation ${op.activation||"?"} · ${op.dependency_count||"?"} deps`,op.seal==="ANCHORED"?"pos":"neg"],
  ];
  strip.innerHTML=cells.map(c=>`<div class="cell"><div class="lbl">${esc(c[0])}</div><div class="val ${c[3]||""}">${c[1]}</div><div class="sub">${esc(c[2])}</div></div>`).join("");
  const chart=document.getElementById("pacChart"); if(chart) chart.innerHTML=pacEquityChart(perf.equity_curve,d.evidence_status);
  const last=document.getElementById("pacLast"); if(last){last.textContent=pacNum(perf.normalized_capital_index,2);last.className=`pac-last ${Number(perf.normalized_capital_index)>=100?'pos':'neg'}`;}
  const note=document.getElementById("pacChartNote"); if(note) note.textContent=perf.numeraire_note||"Performance stays blank until evidence passes every gate.";
  const formula=document.getElementById("pacFormula"); if(formula) formula.textContent=d.formula||"—";
  const formulaNote=document.getElementById("pacFormulaNote"); if(formulaNote) formulaNote.textContent=d.formula_note||"";
  const gates=document.getElementById("pacGates"); if(gates){
    const feed=(op.solusd||{}).status==="FRESH";
    const rows=[
      [op.seal==="ANCHORED","seal",op.seal||"unknown"],
      [op.activation==="ANCHORED","activation",op.activation||"unknown"],
      [feed,"SOL/USD",feed?`fresh · $${op.solusd.price}`:(op.solusd||{}).reason||"refused"],
      [(op.tape_files_with_current_causal_schema||0)>0,"causal tape",`${op.tape_files_with_current_causal_schema||0} mint files`],
      [op.runner_audit==="PASS"||String(op.runner_audit||"").startsWith("GO_"),
        "runner audit",op.runner_audit||"not recorded"],
      [valid,"performance evidence",d.evidence_status||"unknown"],
    ];
    gates.innerHTML=rows.map(r=>`<div class="pac-gate"><span class="dot ${r[0]?'ok':'bad'}"></span><span>${esc(r[1])}</span><strong>${esc(r[2])}</strong></div>`).join("")+
      (op.open_gates||[]).map(g=>`<div class="pac-open-gate">OPEN · ${esc(g)}</div>`).join("");
  }
  const body=document.getElementById("pacBody"), opens=d.open_positions||[], activity=d.activity||[];
  const openRows=opens.map(p=>`<tr><td class="l mono">${esc(p.mint)}</td><td><span class="badge b-open">open</span></td><td>—</td><td>${(p.entry_all_in_lamports/1e9).toFixed(6)} SOL</td><td>—</td><td class="l muted">watching executable full-position quote</td></tr>`);
  const closedRows=activity.filter(a=>a.kind==="resolved").map(a=>`<tr><td class="l mono">${esc(a.mint)}</td><td><span class="badge ${a.unexitable_full_loss?'b-dead':'b-null'}">closed</span></td><td class="${Number(a.return_r)>0?'pos':(Number(a.return_r)<0?'neg':'')}">${Number(a.return_r)>=0?'+':''}${pacNum(a.return_r,3)}R</td><td>${(a.entry_all_in_lamports/1e9).toFixed(6)} SOL</td><td>${(a.exit_net_proceeds_lamports/1e9).toFixed(6)} SOL</td><td class="l ${a.unexitable_full_loss?'neg':''}">${esc(a.action)}</td></tr>`);
  const costRows=activity.filter(a=>a.kind==="attempt_cost").map(a=>`<tr><td class="l mono">${esc(a.mint)}</td><td><span class="badge b-dead">failed attempt</span></td><td class="neg">${pacNum(a.return_r,3)}R</td><td>${((a.attempt_cost_lamports||0)/1e9).toFixed(6)} SOL fee</td><td>0</td><td class="l neg">${esc(a.status||"attempt cost")}</td></tr>`);
  if(body) body.innerHTML=(openRows.join("")+closedRows.join("")+costRows.join(""))||`<tr><td class="empty l" colspan="6">No valid forward trades yet. The chart will move only after anchored, fully-costed scenario resolutions.</td></tr>`;
  const count=document.getElementById("pacTradeCount"); if(count) count.textContent=`${perf.resolved||0} resolved · ${perf.failed_attempt_cost_events||0} failed-cost · ${opens.length} open`;
}

/* ---------------- polling ---------------- */
async function poll(){
  // A render/chart exception must NOT masquerade as a network disconnect. We separate the two:
  // only a failed FETCH (network) can flip the badge to "reconnecting", and only after 2 in a row
  // (a single cancelled in-flight request during a redraw is normal and shouldn't flicker). A throw
  // inside updateTokenPage/loadChart is caught locally and logged -- the connection stays "live".
  try{
    if(state.route.name === "portfolio"){
      const [sum, pos] = await Promise.all([getJSON("/api/summary"), getJSON("/api/positions")]);
      state.summary = sum; state.positions = pos; state.failStreak = 0;
      try{
        if(document.getElementById("strip")){ renderStrip(); renderRows(); }
        else renderPortfolio();
      }catch(re){ console.error("portfolio render:", re); }
    } else if(state.route.name === "pac"){
      const pac = await getJSON("/api/pac");
      state.pac = pac; state.failStreak = 0;
      try{
        if(document.getElementById("pacChart")) renderPACView();
        else renderPAC();
      }catch(re){ console.error("pac render:", re); }
    } else if(state.route.name === "evo"){
      const ev = await getJSON("/api/evo");
      state.evo = ev; state.failStreak = 0;
      try{
        if(document.getElementById("evoBody")) renderEvoView();
        else renderEvo();
      }catch(re){ console.error("evo render:", re); }
    } else if(state.route.name === "exit"){
      const ex = await getJSON("/api/exit");
      state.exit = ex; state.failStreak = 0;
      try{
        if(document.getElementById("exitBody")) renderExitView();
        else renderExit();
      }catch(re){ console.error("exit render:", re); }
    } else if(state.route.name === "aftershock"){
      const as = await getJSON("/api/aftershock");
      state.aftershock = as; state.failStreak = 0;
      try{
        if(document.getElementById("asBody")) renderAftershockView();
        else renderAftershock();
      }catch(re){ console.error("aftershock render:", re); }
    } else if(state.route.name === "av2"){
      const a2 = await getJSON("/api/aftershock_v2");
      state.av2 = a2; state.failStreak = 0;
      try{
        if(document.getElementById("av2Grid")) renderAftershockV2View();
        else renderAftershockV2();
      }catch(re){ console.error("av2 render:", re); }
    } else if(state.route.name === "av3"){
      const a3 = await getJSON("/api/aftershock_v3");
      state.av3 = a3; state.failStreak = 0;
      try{
        if(document.getElementById("av2Grid")) renderAftershockV2View();
        else renderAftershockV2({family:"av3"});
      }catch(re){ console.error("av3 render:", re); }
    } else if(state.route.name === "av4"){
      const a4 = await getJSON("/api/aftershock_v4");
      state.av4 = a4; state.failStreak = 0;
      try{
        if(document.getElementById("av2Grid")) renderAftershockV2View();
        else renderAftershockV2({family:"av4"});
      }catch(re){ console.error("av4 render:", re); }
    } else if(state.route.name === "av5"){
      const a5 = await getJSON("/api/aftershock_v5");
      state.av5 = a5; state.failStreak = 0;
      try{
        if(document.getElementById("av2Grid")) renderAftershockV2View();
        else renderAftershockV2({family:"av5"});
      }catch(re){ console.error("av5 render:", re); }
    } else if(state.route.name === "token"){
      const d = await getJSON("/api/coin/" + encodeURIComponent(state.route.pool));
      state.failStreak = 0;
      if(!d._error){
        try{
          // The static shell is built ONCE (renderTokenPage on navigation). A poll for the SAME token
          // must NOT rebuild #app or #chart — it updates the header/stat TEXT in place and pushes fresh
          // candle DATA into the EXISTING chart (via updateTokenPage). Only when the shell isn't up for
          // this pool — and no build is already in flight — does the poll build it (crash recovery).
          if(state.tokenMounted === state.route.pool){
            updateTokenPage(d);
          } else if(!state.tokenBuilding){
            buildTokenPage(d);
          }
        }catch(re){ console.error("token render:", re); }
      }
    }
    setLive(true, state.route.name==="pac" ? "PAC ledger · 2s" : "live · 6s"); stampUpdated();
  }catch(e){
    state.failStreak = (state.failStreak||0) + 1;
    if(state.failStreak >= 2) setLive(false, "reconnecting");
  }
}

/* ---------------- chart lib load ---------------- */
function loadChartLib(){
  const sc = document.createElement("script");
  sc.src = "https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js";
  sc.onload = () => { state.chartLib = window.LightweightCharts;
    if(state.route && state.route.name==="token" && state.coin){
      loadChart(state.coin, state.tf || "1m");
    }};
  sc.onerror = () => { state.chartLib = null; };  // canvas fallback stays
  document.head.appendChild(sc);
}

/* ---------------- boot ---------------- */
async function boot(){
  setLive(false, "connecting");
  loadChartLib();
  window.addEventListener("hashchange", onRoute);
  // Don't poll a backgrounded tab (each poll rebuilds a live payload server-side); refresh on refocus.
  document.addEventListener("visibilitychange", () => { if(!document.hidden) poll(); });
  state.route = parseRoute();
  onRoute();
  await poll();
  let slowTick=0;
  setInterval(() => {
    if(document.hidden) return;
    slowTick += 1;
    if((state.route&&state.route.name==="pac") || slowTick%3===0) poll();
  }, 2000);
}
boot();
