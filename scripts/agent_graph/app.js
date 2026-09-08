"use strict";
const $ = s => document.querySelector(s);
const esc = s => (s == null ? "" : String(s)).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num = (x, d = 2) => (x == null || x === "" || isNaN(+x)) ? "—" : (+x).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const money = x => (x == null || isNaN(+x)) ? "—" : "$" + num(x, 2);
const pct = x => (x == null || isNaN(+x)) ? "—" : (100 * +x).toFixed(2) + "%";
const signClass = x => +x > 0 ? "pos" : (+x < 0 ? "neg" : "");
async function getJSON(u) { const r = await fetch(u, { cache: "no-store" }); return r.json(); }
async function postJSON(u, b) { const r = await fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }); return r.json(); }

const ICON = {
  think: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#8b94a1" stroke-width="2"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.6.6 1 1.4 1 2.5h6c0-1.1.4-1.9 1-2.5A6 6 0 0 0 12 3z"/></svg>',
  tool: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#d59a2c" stroke-width="2"><path d="M14.7 6.3a4 4 0 0 1-5 5L4 17v3h3l5.7-5.7a4 4 0 0 0 5-5l-2.6 2.6-2-2 2.6-2.6z"/></svg>',
  result: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#26a869" stroke-width="2"><path d="M20 6 9 17l-5-5"/></svg>',
  text: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#8b94a1" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
};
const SICON = {
  agenda: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="3" width="16" height="18" rx="1"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
  select: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h10M4 12h16M4 18h7"/><circle cx="18" cy="6" r="2"/></svg>',
  execute: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2 2M16.4 16.4l2 2M18.4 5.6l-2 2M7.6 16.4l-2 2"/></svg>',
  verify: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l7 3v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6z"/><path d="M9 12l2 2 4-4"/></svg>',
  merge: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="12" r="2"/><path d="M8 6c0 4 2 6 8 6M8 18c0-4 2-6 8-6"/></svg>'
};

/* ---------- routing ---------- */
const ROUTES = {
  control: { title: "Control", sub: "the agent loop & graph", render: renderControl, live: true },
  agenda: { title: "Agenda", sub: "research & build tasks", render: renderAgenda },
  portfolio: { title: "Portfolio", sub: "Alpaca paper account", render: renderPortfolio },
  profits: { title: "Profits & P/L", sub: "equity, realized & unrealized", render: renderProfits },
  accounts: { title: "Accounts & Wallets", sub: "connected trading accounts", render: renderAccounts }
};
let pollTimer = null, currentRoute = null;
function go(route) {
  if (!ROUTES[route]) route = "control";
  currentRoute = route;
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("active", a.dataset.route === route));
  $("#pageTitle").innerHTML = ROUTES[route].title + ' <span class="sub">' + ROUTES[route].sub + "</span>";
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  ROUTES[route].render(false);
  if (ROUTES[route].live) pollTimer = setInterval(() => { if (currentRoute === route) ROUTES[route].render(true); }, 1500);
}
window.addEventListener("hashchange", () => go(location.hash.slice(1)));

/* ---------- shared bits ---------- */
function countBy(tasks) { const c = { running: 0, verified: 0, pending: 0, blocked: 0, killed: 0 }; (tasks || []).forEach(t => c[t.status] = (c[t.status] || 0) + 1); return c; }
function newestRun(st) { const rs = st.runs || []; return rs.find(r => r.agents && r.agents.some(a => a.state === "running")) || rs.find(r => r.agents && r.agents.length) || { agents: [] }; }
function runningAgents(st) { const o = []; (st.runs || []).forEach(r => r.agents.forEach(a => { if (a.state === "running") o.push(a); })); return o; }
function updateNav(st) {
  const c = countBy(st.agenda.tasks);
  const na = runningAgents(st).length;
  $("#navAgenda .cnt").textContent = st.agenda.tasks.length;
  $("#sfLoop").innerHTML = st.control && st.control.paused ? '<span class="d paused"></span>paused' : (st.any_running ? '<span class="d active"></span>running' : '<span class="d active"></span>idle');
  $("#sfAgents").textContent = na;
}

/* ---------- CONTROL ---------- */
async function renderControl(isPoll) {
  const st = await getJSON("/api/state").catch(() => null);
  if (!st || st._error) { $("#view").innerHTML = '<div class="empty">backend unreachable — is server.py running?</div>'; return; }
  updateNav(st);
  const c = countBy(st.agenda.tasks), ctrl = st.control || {}, nAg = runningAgents(st).length, nf = st.notify || {};
  const live = st.any_running;
  $("#liveDot").className = "ld" + (live ? " on" : "");
  $("#liveText").textContent = live ? "agents working" : "idle";

  const ctlbar = `
    <div class="ctl"><div class="t">Loop state</div><div class="b">
      <span class="state-tag"><span class="d ${ctrl.paused ? "paused" : "active"}"></span>${ctrl.paused ? "Paused" : "Active"}</span>
      <div class="toggle" style="margin-left:auto">
        <button class="${!ctrl.paused ? "on" : ""}" onclick="act('/api/loop/resume')">Run</button>
        <button class="${ctrl.paused ? "on" : ""}" onclick="act('/api/loop/pause')">Pause</button>
      </div></div></div>
    <div class="ctl"><div class="t">Batch size (tasks per iteration)</div><div class="b">
      <div class="stepper"><button onclick="setBatch(${(ctrl.batch||3)-1})">−</button><span class="val">${ctrl.batch||3}</span><button onclick="setBatch(${(ctrl.batch||3)+1})">+</button></div>
      <span style="color:var(--faint);font-size:11.5px">dep-gated &amp; priority-ordered</span></div></div>
    <div class="ctl"><div class="t">Actions</div><div class="b">
      <button class="btn sm" onclick="act('/api/loop/reclaim')" title="After a crash, reset any task stuck in 'running' (no agent actually on it) back to pending so the loop re-picks it.">Reset stuck tasks</button>
      <button class="btn sm primary" onclick="act('/api/loop/request-run')" title="Flag an iteration to run at the next tick.">Queue iteration</button>
      </div><div class="foot">runs Opus 5.0 · hourly at :19${ctrl.run_requested ? ' · <span style="color:var(--warn)">run queued</span>' : ""}</div></div>
    <div class="ctl"><div class="t">Telegram notifications</div><div class="b">
      <span class="state-tag"><span class="dot ${nf.configured ? "active" : "paused"}"></span>${nf.configured ? "Connected" : "Not configured"}</span>
      <button class="btn sm" onclick="notifyTest()" ${nf.configured ? "" : "disabled"}>Send test</button>
      </div><div class="foot" id="ntMsg">${nf.configured ? "pushes a summary after every iteration" : "set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env"}</div></div>`;

  const stats = [["verified", c.verified], ["running", c.running], ["pending", c.pending], ["blocked", c.blocked], ["agents", nAg]]
    .map(([k, n]) => `<div class="stat ${k}"><div class="n">${n}</div><div class="l"><span class="d ${k}"></span>${k === "agents" ? "Agents live" : k[0].toUpperCase() + k.slice(1)}</div></div>`).join("");

  // pipeline — aggregate agents across ALL live runs (multiple workflows run concurrently)
  const run = newestRun(st);
  const allAg = (st.runs || []).flatMap(r => r.agents || []);
  const nE = allAg.filter(a => a.role === "execute" && a.state === "running").length;
  const nV = allAg.filter(a => a.role === "verify" && a.state === "running").length;
  const sdef = [
    { k: "agenda", nm: "Agenda", sub: st.agenda.tasks.length + " tasks", on: true },
    { k: "select", nm: "Select", sub: "loop.py next", on: live },
    { k: "execute", nm: "Execute", sub: nE ? nE + " running" : "idle", busy: nE > 0, on: live },
    { k: "verify", nm: "Verify", sub: nV ? nV + " running" : "idle", busy: nV > 0, on: live },
    { k: "merge", nm: "Merge", sub: "loop.py merge", on: live }
  ];
  let pipe = "";
  sdef.forEach((s, i) => {
    pipe += `<div class="stage ${s.busy ? "busy" : (s.on ? "on" : "")}"><div class="disc">${SICON[s.k]}</div><div class="nm">${s.nm}</div><div class="sub">${esc(s.sub)}</div></div>`;
    if (i < sdef.length - 1) pipe += `<div class="conn ${live ? "live" : ""}"></div>`;
  });

  // jobs
  const runningTasks = st.agenda.tasks.filter(t => t.status === "running");
  const byTask = {};
  (st.runs || []).forEach(r => (r.agents || []).forEach(a => {
    const slot = (byTask[a.task] = byTask[a.task] || {});
    if (!slot[a.role] || a.state === "running") slot[a.role] = a;   // prefer a live agent across runs
  }));
  const snip = a => { const e = (a.activity || []).slice(-1)[0]; if (!e) return '<span style="color:var(--faint)">booting…</span>'; if (e.kind === "tool") return `<span class="tag">${esc(e.name)}</span> ${esc(e.text)}`; if (e.kind === "think") return `<em>${esc(e.text)}</em>`; return esc(e.text); };
  const jobs = runningTasks.length ? runningTasks.map(t => {
    const ex = (byTask[t.id] || {}).execute, vf = (byTask[t.id] || {}).verify;
    const live2 = (vf && vf.state === "running") ? vf : (ex || vf);
    return `<div class="job"><div class="jh"><span class="tid">${esc(t.id)}</span><span class="ti">${esc(t.title)}</span></div>
      <div class="subnodes"><div class="sn ${ex ? ex.state : "pending"}"><span class="d2"></span>execute</div><span style="color:var(--border2)">→</span><div class="sn ${vf ? vf.state : "pending"}"><span class="d2"></span>verify</div></div>
      <div class="snip">${live2 ? snip(live2) : '<span style="color:var(--faint)">queued…</span>'}</div></div>`;
  }).join("") : "";

  // feed
  let rows = [];
  runningAgents(st).forEach(a => a.activity.slice(-7).forEach(ev => rows.push({ who: a.task + " · " + a.role, ev })));
  if (!rows.length) { const r = (st.runs || []).find(r => r.agents.length); if (r) r.agents.forEach(a => a.activity.slice(-3).forEach(ev => rows.push({ who: a.task + " · " + a.role, ev }))); }
  const feed = rows.length ? rows.slice(-24).map(r => { const k = r.ev.kind, lead = k === "tool" ? `<b>${esc(r.ev.name)}</b> ` : ""; return `<div class="frow k-${k}"><span class="who">${esc(r.who)}</span><span class="ic">${ICON[k] || ""}</span><span class="tx">${lead}${esc(r.ev.text)}</span></div>`; }).join("")
    : '<div class="empty">No agent activity yet — the graph lights up on the next iteration.</div>';

  const fwd = st.forward_test ? `<div class="panel pad" style="margin-bottom:14px;border-left:3px solid var(--accent)">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--text3);margin-bottom:6px">Paper bot · forward test</div>
      <div class="mono" style="font-size:12.5px;color:var(--text)">${esc(st.forward_test)}</div></div>` : "";
  $("#view").innerHTML = `
    ${fwd}
    <div class="ctlbar">${ctlbar}</div>
    <div class="hd"><h2>Overview</h2></div><div class="stats">${stats}</div>
    <div class="hd"><h2>Loop &amp; graph</h2><span class="note">agenda → select → execute → verify → merge, repeating</span></div>
    <div class="pipe"><div class="stages">${pipe}</div><div class="loopnote">↻ repeats hourly · verified tasks settle · refuted tasks re-queue · dep-gated</div></div>
    ${jobs ? `<div class="hd"><h2>Jobs in flight</h2></div><div class="jobs">${jobs}</div>` : ""}
    <div class="hd"><h2>Live activity</h2><span class="note">what the agents are thinking &amp; doing</span></div>
    <div class="feed">${feed}</div>`;
}
async function act(url) { await postJSON(url, {}); if (currentRoute === "control") renderControl(true); }
async function setBatch(v) { if (v < 1) v = 1; await postJSON("/api/loop/batch", { batch: v }); renderControl(true); }
async function notifyTest() { const el = $("#ntMsg"); if (el) el.textContent = "sending…"; const r = await postJSON("/api/notify/test", {}); if (el) el.textContent = r.ok ? "test message sent ✓" : ("failed: " + (r.error || "Telegram rejected the message")); }

/* ---------- AGENDA ---------- */
let showAddForm = false;
async function renderAgenda() {
  const st = await getJSON("/api/state").catch(() => null);
  if (!st) { $("#view").innerHTML = '<div class="empty">backend unreachable</div>'; return; }
  updateNav(st);
  const tasks = (st.agenda.tasks || []).slice().sort((a, b) => a.priority - b.priority);
  const rows = tasks.map(t => {
    const v = (t.verdict || {}).verdict || "";
    const deps = (t.deps || []).length ? (t.deps || []).map(d => `<span class="tid" style="font-size:11px">${esc(d.replace(/_.*/, ""))}</span>`).join(" ") : '<span style="color:var(--faint)">—</span>';
    const r = t.result || {};
    const hasResult = !!(r.headline);
    const needsSignoff = hasResult && (t.status === "blocked" || v === "NEEDS_OWNER");   // a finished finding awaiting accept
    const notRun = !hasResult && ["pending", "blocked"].includes(t.status);              // never executed -> can be launched
    const canRequeue = hasResult && ["blocked", "killed"].includes(t.status);            // done but rejected -> re-run
    const open = expandedTasks.has(t.id);
    const vbadge = v ? `<span class="badge ${v === "CONFIRMED" ? "verified" : (v === "REFUTED" || v === "NEEDS_OWNER" ? (v === "NEEDS_OWNER" ? "running" : "blocked") : "running")}">${esc(v)}</span>` : '<span style="color:var(--faint)">—</span>';
    const detail = open ? `<tr class="detailrow"><td colspan="8"><div class="dpanel">
        ${r.headline ? `<div class="dh">${esc(r.headline)}</div>` : '<div class="dh" style="color:var(--text3)">No result recorded yet.</div>'}
        ${(t.verdict || {}).reason ? `<div class="dl"><b>Verifier (${esc(v)}):</b> ${esc((t.verdict || {}).reason)}</div>` : ""}
        ${r.detail ? `<div class="dl"><b>What the agent did:</b>\n${esc(r.detail)}</div>` : ""}
        ${r.guardrail_note ? `<div class="dl"><b>Guardrails:</b> ${esc(r.guardrail_note)}</div>` : ""}
        ${needsSignoff ? `<div class="owner"><span style="color:var(--text2);font-size:12px">Owner decision:</span>
          <button class="btn sm approve" onclick="taskApprove('${t.id}')">Approve &amp; unblock</button>
          <button class="btn sm" onclick="taskReq('${t.id}')">Re-run instead</button>
          <span id="ownerMsg_${t.id}" style="color:var(--text3);font-size:11.5px">Approving accepts this finished result and lets dependent tasks proceed.</span></div>` : ""}
        ${notRun ? `<div class="owner"><span style="color:var(--text2);font-size:12px">This task has not run:</span>
          <button class="btn sm approve" onclick="taskRun('${t.id}')">Run it</button>
          <span id="ownerMsg_${t.id}" style="color:var(--text3);font-size:11.5px">Launches the task — the loop dispatches it on the next tick. (Approve only accepts finished work; it can't start a task.)</span></div>` : ""}
      </div></td></tr>` : "";
    return `<tr class="${open ? "open" : ""}">
      <td class="r">${t.priority}</td>
      <td class="tid">${esc(t.id)}</td>
      <td>${esc(t.title)}</td>
      <td><span class="badge">${esc(t.kind)}</span></td>
      <td>${deps}</td>
      <td><span class="badge ${t.status}">${t.status}</span></td>
      <td>${vbadge}</td>
      <td><div class="act">
        <button class="btn sm" onclick="toggleDetail('${t.id}')" title="show details / finding">${open ? "▾ Hide" : "⋯ Details"}</button>
        ${needsSignoff ? `<button class="btn sm approve" onclick="taskApprove('${t.id}')" title="Accept this finished result and unblock dependents">✓ Approve</button>` : ""}
        ${notRun ? `<button class="btn sm approve" onclick="taskRun('${t.id}')" title="Launch this task — it dispatches on the next loop tick">▶ Run</button>` : ""}
        <button class="btn sm" onclick="taskPrio('${t.id}',${t.priority - 1})" title="raise priority">▲</button>
        <button class="btn sm" onclick="taskPrio('${t.id}',${t.priority + 1})" title="lower priority">▼</button>
        ${canRequeue ? `<button class="btn sm" onclick="taskReq('${t.id}')" title="send back to pending to re-run">Re-queue</button>` : ""}
        <button class="btn sm danger" onclick="taskDel('${t.id}')" title="delete">✕</button>
      </div></td></tr>${detail}`;
  }).join("");

  const form = showAddForm ? `
    <div class="panel pad" style="margin-top:12px">
      <div class="formgrid">
        <label class="fld"><span class="lb">ID (optional)</span><input id="f_id" placeholder="auto"></label>
        <label class="fld"><span class="lb">Kind</span><select id="f_kind"><option>research</option><option>build</option><option>meta</option></select></label>
        <label class="fld" style="grid-column:1/3"><span class="lb">Title</span><input id="f_title" placeholder="What should the agent do?"></label>
        <label class="fld"><span class="lb">Priority</span><input id="f_prio" type="number" value="10"></label>
        <label class="fld"><span class="lb">Deps (comma-separated task IDs)</span><input id="f_deps" placeholder="T1_edge_shortlist, T2_backtest_harness"></label>
        <label class="fld" style="grid-column:1/3"><span class="lb">Why it matters</span><textarea id="f_why" rows="2"></textarea></label>
        <label class="fld" style="grid-column:1/3"><span class="lb">Acceptance (what "done" means)</span><textarea id="f_acc" rows="2"></textarea></label>
        <label class="fld" style="grid-column:1/3"><span class="lb">Guardrails (one per line)</span><textarea id="f_guard" rows="2"></textarea></label>
      </div>
      <div class="row"><button class="btn primary" onclick="taskAdd()">Add task</button><button class="btn" onclick="toggleAdd()">Cancel</button></div>
      <div id="addMsg"></div>
    </div>` : "";

  $("#view").innerHTML = `
    <div class="hd"><h2>Tasks</h2><span class="note">${tasks.length} total</span><span class="grow"></span>
      <button class="btn primary" onclick="toggleAdd()">${showAddForm ? "Close" : "+ Add task"}</button></div>
    ${form}
    <div class="tbl" style="margin-top:12px"><table><thead><tr>
      <th class="r">P</th><th>ID</th><th>Title</th><th>Kind</th><th>Deps</th><th>Status</th><th>Verdict</th><th>Actions</th>
    </tr></thead><tbody>${rows}</tbody></table></div>`;
}
let expandedTasks = new Set();
function toggleDetail(id) { if (expandedTasks.has(id)) expandedTasks.delete(id); else expandedTasks.add(id); renderAgenda(); }
async function taskApprove(id) {
  const r = await postJSON("/api/task/approve", { id });
  const msg = (r.unblocked && r.unblocked.length) ? ("approved — unblocked " + r.unblocked.join(", ") + " (queued for next tick)") : "approved — nothing was waiting on this task";
  const el = document.getElementById("ownerMsg_" + id); if (el) el.textContent = msg;
  setTimeout(renderAgenda, 900);
}
async function taskRun(id) {
  const r = await postJSON("/api/task/run", { id });
  const el = document.getElementById("ownerMsg_" + id); if (el) el.textContent = r.queued ? "queued — the loop will dispatch it on the next tick" : "could not queue";
  setTimeout(renderAgenda, 900);
}
function toggleAdd() { showAddForm = !showAddForm; renderAgenda(); }
async function taskPrio(id, p) { await postJSON("/api/task/update", { id, priority: Math.max(1, p) }); renderAgenda(); }
async function taskReq(id) { await postJSON("/api/task/update", { id, status: "pending" }); renderAgenda(); }
async function taskDel(id) { if (!confirm("Delete " + id + "?")) return; await postJSON("/api/task/delete", { id }); renderAgenda(); }
async function taskAdd() {
  const g = $("#f_guard").value.split("\n").map(s => s.trim()).filter(Boolean);
  const deps = $("#f_deps").value.split(",").map(s => s.trim()).filter(Boolean);
  const body = { id: $("#f_id").value.trim() || undefined, title: $("#f_title").value.trim(), kind: $("#f_kind").value, priority: +$("#f_prio").value, why: $("#f_why").value.trim(), acceptance: $("#f_acc").value.trim(), guardrails: g, deps };
  if (!body.title) { $("#addMsg").innerHTML = '<div class="msg err">Title is required.</div>'; return; }
  const r = await postJSON("/api/task/add", body);
  $("#addMsg").innerHTML = `<div class="msg ok">Added ${esc(r.added || "")}.</div>`;
  showAddForm = false; setTimeout(renderAgenda, 400);
}

/* ---------- PORTFOLIO ---------- */
async function renderPortfolio() {
  $("#view").innerHTML = '<div class="empty">loading paper account…</div>';
  const p = await getJSON("/api/portfolio").catch(() => null);
  if (!p) { $("#view").innerHTML = '<div class="empty">backend unreachable</div>'; return; }
  if (!p.connected) {
    $("#view").innerHTML = `<div class="notice">Alpaca paper account not connected: ${esc(p.error || "unknown")}. Check keys on the Accounts page.</div>`;
    return;
  }
  const a = p.account;
  const dayPL = (+a.equity) - (+a.last_equity);
  const tiles = [
    ["Equity", money(a.equity), ""], ["Cash", money(a.cash), ""],
    ["Buying power", money(a.buying_power), ""],
    ["Today's P/L", (dayPL >= 0 ? "+" : "") + money(dayPL), signClass(dayPL)],
    ["Long / Short", money(a.long_market_value) + " / " + money(a.short_market_value), ""]
  ].map(([l, v, c]) => `<div class="stat"><div class="n ${c}" style="font-size:20px">${v}</div><div class="l">${l}</div></div>`).join("");
  const pos = (p.positions || []);
  const posRows = pos.length ? pos.map(x => {
    const plc = signClass(x.unrealized_pl);
    return `<tr><td class="tid">${esc(x.symbol)}</td>
      <td><span class="badge side-${x.side}">${esc(x.side)}</span></td>
      <td class="r">${num(x.qty, 0)}</td><td class="r">${money(x.avg_entry_price)}</td>
      <td class="r">${money(x.current_price)}</td><td class="r">${money(x.market_value)}</td>
      <td class="r ${plc}">${(+x.unrealized_pl >= 0 ? "+" : "") + money(x.unrealized_pl)}</td>
      <td class="r ${plc}">${pct(x.unrealized_plpc)}</td></tr>`;
  }).join("") : `<tr><td colspan="8" class="empty">No open positions — the paper account is flat. Positions appear here once the bot (T4) trades.</td></tr>`;
  $("#view").innerHTML = `
    <div class="hd"><h2>Account</h2><span class="note mono">paper · #${esc((a.account_number || "").slice(-6))}</span><span class="grow"></span>
      <button class="btn sm" onclick="renderPortfolio()">↻ Refresh</button></div>
    <div class="stats">${tiles}</div>
    <div class="hd"><h2>Positions</h2><span class="note">${pos.length} open</span></div>
    <div class="tbl"><table><thead><tr><th>Symbol</th><th>Side</th><th class="r">Qty</th><th class="r">Avg entry</th><th class="r">Last</th><th class="r">Mkt value</th><th class="r">Unreal P/L</th><th class="r">%</th></tr></thead><tbody>${posRows}</tbody></table></div>`;
}

/* ---------- PROFITS ---------- */
function sparkline(vals) {
  const v = (vals || []).filter(x => x != null);
  if (v.length < 2) return '<div class="empty">no history yet</div>';
  const mn = Math.min(...v), mx = Math.max(...v), W = 900, Hh = 200, pad = 6;
  const pts = v.map((y, i) => [pad + i * (W - 2 * pad) / (v.length - 1), Hh - pad - (mx === mn ? Hh / 2 : (y - mn) / (mx - mn) * (Hh - 2 * pad))]);
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const up = v[v.length - 1] >= v[0], col = up ? "#26a869" : "#d24b43";
  const area = d + ` L${pts[pts.length - 1][0].toFixed(1)} ${Hh} L${pts[0][0].toFixed(1)} ${Hh} Z`;
  return `<svg viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none"><path d="${area}" fill="${col}22"/><path d="${d}" fill="none" stroke="${col}" stroke-width="2"/></svg>`;
}
async function renderProfits() {
  $("#view").innerHTML = '<div class="empty">loading…</div>';
  const [h, o, p] = await Promise.all([getJSON("/api/history").catch(() => ({})), getJSON("/api/orders").catch(() => ({})), getJSON("/api/portfolio").catch(() => ({}))]);
  const a = (p && p.account) || {};
  const eq = (h && h.equity) || [];
  const startV = (h && h.base_value) || (eq[0] || 0);
  const totalPL = eq.length ? eq[eq.length - 1] - startV : 0;
  const dayPL = a.equity ? (+a.equity - +a.last_equity) : 0;
  const tiles = [
    ["Current equity", money(a.equity || (eq.length ? eq[eq.length - 1] : null)), ""],
    ["Total P/L (1M)", (totalPL >= 0 ? "+" : "") + money(totalPL), signClass(totalPL)],
    ["Today's P/L", (dayPL >= 0 ? "+" : "") + money(dayPL), signClass(dayPL)]
  ].map(([l, v, c]) => `<div class="stat"><div class="n ${c}" style="font-size:20px">${v}</div><div class="l">${l}</div></div>`).join("");
  const orders = (o && o.orders) || [];
  const orows = Array.isArray(orders) && orders.length ? orders.slice(0, 25).map(x => `<tr>
      <td class="mono" style="font-size:11px">${esc((x.submitted_at || "").slice(0, 16).replace("T", " "))}</td>
      <td class="tid">${esc(x.symbol)}</td><td><span class="badge side-${x.side}">${esc(x.side)}</span></td>
      <td class="r">${num(x.qty, 0)}</td><td>${esc(x.type)}</td>
      <td><span class="badge ${x.status === "filled" ? "verified" : "pending"}">${esc(x.status)}</span></td>
      <td class="r">${x.filled_avg_price ? money(x.filled_avg_price) : "—"}</td></tr>`).join("")
    : `<tr><td colspan="7" class="empty">No orders yet — the paper account has no trade history.</td></tr>`;
  $("#view").innerHTML = `
    <div class="hd"><h2>Equity (last month)</h2><span class="grow"></span><button class="btn sm" onclick="renderProfits()">↻ Refresh</button></div>
    <div class="stats" style="margin-bottom:12px">${tiles}</div>
    <div class="chart">${sparkline(eq)}</div>
    <div class="hd"><h2>Recent orders</h2><span class="note">${Array.isArray(orders) ? orders.length : 0}</span></div>
    <div class="tbl"><table><thead><tr><th>Submitted</th><th>Symbol</th><th>Side</th><th class="r">Qty</th><th>Type</th><th>Status</th><th class="r">Fill</th></tr></thead><tbody>${orows}</tbody></table></div>`;
}

/* ---------- ACCOUNTS ---------- */
async function renderAccounts() {
  $("#view").innerHTML = '<div class="empty">loading…</div>';
  const d = await getJSON("/api/accounts").catch(() => null);
  if (!d) { $("#view").innerHTML = '<div class="empty">backend unreachable</div>'; return; }
  const rows = (d.accounts || []).map(a => `<tr>
    <td><b>${esc(a.name)}</b></td><td>${esc(a.kind)}</td>
    <td><span class="badge ${a.mode === "paper" ? "verified" : "pending"}">${esc(a.mode)}</span></td>
    <td class="mono" style="font-size:11px">${esc(a.id || "—")}</td>
    <td><span class="badge ${a.status === "connected" ? "verified" : (a.status === "error" ? "blocked" : "pending")}">${esc(a.status)}</span></td>
    <td style="color:var(--dim);font-size:12px">${esc(a.detail || "")}</td></tr>`).join("");
  $("#view").innerHTML = `
    <div class="hd"><h2>Connected accounts</h2><span class="grow"></span><button class="btn sm" onclick="renderAccounts()">↻ Refresh</button></div>
    <div class="tbl"><table><thead><tr><th>Account</th><th>Universe</th><th>Mode</th><th>Key</th><th>Status</th><th>Detail</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="hd"><h2>Add an account / wallet</h2></div>
    <div class="notice">Adding a <b>real-money</b> account or crypto wallet (API keys, seed phrases, signing keys) is an <b>owner-gated</b> action and is intentionally not doable through this web form for security. To connect one, add the credentials to <span class="mono">.env</span> yourself and they appear here automatically. Live trading stays disabled until you explicitly enable it — the bot trades the <b>paper</b> account only.</div>
    <div class="panel pad" style="margin-top:12px;opacity:.7">
      <div class="formgrid">
        <label class="fld"><span class="lb">Broker / chain</span><select disabled><option>Alpaca (live)</option><option>Solana wallet</option><option>Coinbase</option></select></label>
        <label class="fld"><span class="lb">Mode</span><select disabled><option>paper</option><option>live (owner-gated)</option></select></label>
        <label class="fld" style="grid-column:1/3"><span class="lb">API key / address</span><input disabled placeholder="set in .env — not accepted here"></label>
      </div>
      <button class="btn" disabled>Connect (owner-gated)</button>
    </div>`;
}

/* ---------- theme ---------- */
const SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/></svg>';
const MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
function currentTheme() { return document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); }
function paintThemeBtn() { const b = $("#themeBtn"); if (b) b.innerHTML = currentTheme() === "dark" ? SUN : MOON; }
function initTheme() { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; paintThemeBtn(); }
function toggleTheme() { const next = currentTheme() === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = next; localStorage.setItem("theme", next); paintThemeBtn(); }

/* ---------- boot ---------- */
initTheme();
getJSON("/api/state").then(updateNav).catch(() => {});
go(location.hash.slice(1) || "control");
