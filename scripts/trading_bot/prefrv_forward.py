#!/usr/bin/env python3
"""PREFRV forward paper runner -- amendment A1 (task T40) of PREFRV_FORWARD_PREREGISTRATION.md.

Built and sha256-pinned 2026-08-31 03:00 CEST (durable supervisor, CHUNK B), BEFORE the T30
day-30 verdict exists and WITHOUT reading any research/data/borrow_forward/extract file, any
pair-level fee/availability figure, or any price bar after 2026-08-14.  The self-test runs on
SYNTHETIC panels in a tempdir only.  Research / paper only.  No orders, no broker
authentication, no spend.  Standalone PREFRV_FORWARD_* ledger -- NOT a BASKET1 leg.  Never
touches the t4 path.

Modes
  --start    refuses unless the s1 preconditions ALL hold (T30_BORROW_VERDICT.json says
             BORROW_WALL_PASSED with clean_days >= 30, every pin in
             PREFRV_FORWARD_PREREGISTRATION.sha256 verifies, PREFRV_FORWARD_STATE.json does
             not exist, DECISIONS.md does not contain T39_VETO); then writes the state file
             with the alive set taken VERBATIM (file order, alive == true) from the verdict.
  --week     inert (exit 0) while no state file exists, so the cron line can be installed
             before the verdict.  Otherwise processes every COMPLETED grid interval not yet
             logged: fetches bars/quotes (append-only under research/data/prefrv_forward/
             with a manifest), applies the s3 state machine and s4 cost model, appends
             PREFRV_FORWARD_LOG.jsonl pair rows + one book row per grid week, updates state.
  --verdict  applies s6/s7 verbatim; refuses to run on an existing terminal verdict
             (DEAD / ALIVE / PROMOTABLE / RETIRED); UNDECIDED may be rewritten weekly.
  --selftest synthetic panels only; never reads a real extract, real cache, real bar or the
             real state/ledger; asserts refusal gates, state-machine transitions, cost and
             fee arithmetic, recall/retirement, and the verdict rules.

Frozen constants are copied from the pre-registration and MUST NOT be edited (a change =
a new frozen test = forbidden).  Mechanical resolutions declared by this amendment (rule
content unchanged):
  * NYSE sessions are enumerated from SPY daily bars (feed sip, raw): every NYSE session
    prints an SPY bar, so forward grid session g = the 5g-th SPY bar date strictly after
    2026-08-14 (g=1 -> 2026-08-21).
  * s4.1 says both legs pay the worse leg's half-spread "on entry and on exit"; the design
    code's book() aggregation dropped the exit week's turnover cost (an exiting pair has
    nw == 0 and fell out of the active mask).  The English rule wins because it is the
    STRICTLY MORE CONSERVATIVE side: a pair-week is included in the book mean iff it holds
    (nw != 0) OR trades (|dw| > 0), so exit costs are charged in the exit week (with zero
    P&L that week).  This can only lower the forward net vs the design convention.
  * s4.4 "closed at the close of the next grid session": the recall flag raised during the
    interval forces an exit in the decision step AT that next grid session (position earns
    through that close, then is flat), with the normal exit cost plus one extra hs_pair.
  * D1 (diagnostic sign witness) uses the same weights, the same cost_spread and the SAME
    fee amount as series P (its fill window is one session later; the <= 1-day fee
    difference is noise and D1 is never promoted, only its sign is a s7 gate).
  * s7 "no single pair contributes > 40% of cumulative net gains": share = the pair's
    positive cumulative net divided by the sum of all positive cumulative pair nets.
  * A called/redeemed series prints its redemption in the adjusted series and then stops
    printing; the exit return therefore carries the redemption cash and the pair retires
    via the 5-session no-print rule (retire_no_print covers retire_called mechanically).
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
import os
import pathlib
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np

np.seterr(all="ignore")

# ------------------------------------------------------------------ frozen constants (s3-s7)
DESIGN_GRID_END = "2026-08-14"   # last design grid session; forward sessions are strictly after
Z_L, Z_K, Z_X, MAXHOLD = 52, 2.0, 0.5, 26
Z_MINPTS = 26                    # >= 26 finite points in the trailing window, sd > 0
SEC31_BP = 0.278                 # per unit turnover, s4.1
NO_PRINT_SESSIONS = 5            # s4.5 retirement
FEE_MISSING_DAYS = 5             # s4.2 -> treat as recall
RECALL_ZERO_EXTRACTS = 2         # s4.4 consecutive clean extracts with AVAILABLE == 0
DROP_MIN_WEEKS = 26              # s6 per-pair drop eligibility
Z95_ONE_SIDED = 1.645
N_MIN = 40                       # s6 pooled gates
N_ALIVE = 52                     # s7 first ALIVE eligibility
N_MAX = 156                      # s7 -> RETIRED "unproven"
ALIVE_T = 2.0
ALIVE_MEAN_BP = 9.6              # the design's own held-out net; distance from zero
PAIR_SHARE_MAX = 0.40
MIN_ISSUERS = 3
PROMO_MIN_PAIRS = 30             # s7 INVENT_0822 s3.1 guard
PROMO_HS_BP = 9.0
TERMINAL = ("DEAD", "ALIVE", "PROMOTABLE", "RETIRED")

CAL_SYM = "SPY"                  # session calendar witness (every NYSE session prints SPY)
ALPACA = "https://data.alpaca.markets"


# ------------------------------------------------------------------------------ environment
class Env:
    """All paths + data providers.  --selftest swaps root and the two fetchers; every other
    mode uses the real repo layout and the Alpaca data endpoint (data host only)."""

    def __init__(self, root: pathlib.Path):
        self.root = pathlib.Path(root)
        rt = self.root / "research" / "trading_bot"
        self.rt = rt
        self.data = self.root / "research" / "data" / "prefrv_forward"
        self.borrow = self.root / "research" / "data" / "borrow_forward"
        self.cache = self.root / "research" / "data" / "inv0822_tether"
        self.decisions = self.root / "DECISIONS.md"
        self.pinfile = rt / "PREFRV_FORWARD_PREREGISTRATION.sha256"
        self.t30_verdict = rt / "T30_BORROW_VERDICT.json"
        self.state_path = rt / "PREFRV_FORWARD_STATE.json"
        self.log_path = rt / "PREFRV_FORWARD_LOG.jsonl"
        self.verdict_path = rt / "PREFRV_FORWARD_VERDICT.json"
        self.fetch_bars = self._alpaca_bars      # (syms, start, end, adjustment)->{sym:{d:c}}
        self.fetch_quotes = self._alpaca_quotes  # (syms)->{sym: half_bp}
        self.today = lambda: dt.date.today().isoformat()

    # -- Alpaca (data endpoint only; keys from .env exactly as the frozen cache was built) --
    def _headers(self):
        env = {}
        for line in (self.root / ".env").read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
        return {"APCA-API-KEY-ID": env["ALPACA_API_KEY_ID"],
                "APCA-API-SECRET-KEY": env["ALPACA_API_SECRET_KEY"],
                "Accept": "application/json"}

    def _get(self, path, params):
        url = f"{ALPACA}{path}?{urllib.parse.urlencode(params)}"
        for attempt in range(6):
            try:
                req = urllib.request.Request(url, headers=self._headers())
                with urllib.request.urlopen(req, timeout=120) as fh:
                    return json.load(fh)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503):
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        raise RuntimeError("give up " + url)

    def _alpaca_bars(self, syms, start, end, adjustment):
        out = {}
        B = 100
        for k in range(0, len(syms), B):
            chunk, page = syms[k:k + B], None
            while True:
                p = dict(symbols=",".join(chunk), timeframe="1Day", start=start, end=end,
                         adjustment=adjustment, limit=10000, feed="sip")
                if page:
                    p["page_token"] = page
                js = self._get("/v2/stocks/bars", p)
                for s, bars in (js.get("bars") or {}).items():
                    out.setdefault(s, {}).update({b["t"][:10]: b["c"] for b in bars})
                page = js.get("next_page_token")
                if not page:
                    break
        return out

    def _alpaca_quotes(self, syms):
        q = {}
        B = 100
        for k in range(0, len(syms), B):
            js = self._get("/v2/stocks/quotes/latest",
                           dict(symbols=",".join(syms[k:k + B]), feed="sip"))
            for s, v in (js.get("quotes") or {}).items():
                bid, ask = v.get("bp") or 0, v.get("ap") or 0
                if bid > 0 and ask > bid:
                    q[s] = (ask - bid) / (ask + bid) * 1e4
        return q


# ------------------------------------------------------------------------------ small utils
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ibkr_sym(alpaca_sym):
    return alpaca_sym.replace(".PR", " PR")


def parse_avail(v):
    try:
        return int(str(v).strip().lstrip(">").replace(",", "") or 0)
    except ValueError:
        return 0


def parse_fee(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def nw_t(x, lags=4):
    """Newey-West (Bartlett) t of the mean, reported alongside the plain t; never a gate."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 2:
        return float("nan")
    e = x - x.mean()
    s = float(e @ e) / n
    for L in range(1, min(lags, n - 1) + 1):
        g = float(e[L:] @ e[:-L]) / n
        s += 2.0 * (1.0 - L / (lags + 1.0)) * g
    if s <= 0:
        return float("nan")
    return float(x.mean() / math.sqrt(s / n))


def cal_days(d0, d1):
    """Calendar dates in (d0, d1]."""
    a = dt.date.fromisoformat(d0)
    b = dt.date.fromisoformat(d1)
    out = []
    while a < b:
        a += dt.timedelta(days=1)
        out.append(a.isoformat())
    return out


# --------------------------------------------------------------------------- borrow extracts
class Borrow:
    """Clean T30 extracts, read lazily.  Fee/gate values are only ever requested for dates
    >= the forward start; on a day without a clean extract the last clean value carries
    forward (s4.2)."""

    def __init__(self, env: Env):
        self.env = env
        with open(env.borrow / "ledger.json") as fh:
            ledger = json.load(fh)
        self.clean = sorted(d for d, v in ledger["days"].items()
                            if v.get("status") == "clean")
        self._cache = {}

    def _rows(self, day):
        if day not in self._cache:
            with open(self.env.borrow / "extract" / f"extract_{day}.json") as fh:
                e = json.load(fh)
            self._cache[day] = {r["SYM"]: r for r in e["rows"]}
        return self._cache[day]

    def last_clean_leq(self, d):
        c = [x for x in self.clean if x <= d]
        return c[-1] if c else None

    def clean_in(self, d0, d1):
        """Clean extract dates in (d0, d1]."""
        return [x for x in self.clean if d0 < x <= d1]

    def fee_pct(self, ibkr, day):
        """FEERATE (%/yr) for `ibkr` effective on calendar day `day` (carry-forward), or nan."""
        src = self.last_clean_leq(day)
        if src is None:
            return float("nan")
        r = self._rows(src).get(ibkr)
        return parse_fee(r["FEERATE"]) if r else float("nan")

    def avail(self, ibkr, day):
        """AVAILABLE effective on `day` (carry-forward), or None if no extract/row."""
        src = self.last_clean_leq(day)
        if src is None:
            return None
        r = self._rows(src).get(ibkr)
        return parse_avail(r["AVAILABLE"]) if r else None

    def avail_on_clean(self, ibkr, clean_day):
        r = self._rows(clean_day).get(ibkr)
        return parse_avail(r["AVAILABLE"]) if r else None


# ------------------------------------------------------------------------------ pins / gates
def verify_pins(env: Env):
    """Every non-comment line of the pin file must verify.  Returns list of mismatches."""
    bad = []
    for line in env.pinfile.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        h, rel = line.split(None, 1)
        p = env.root / rel.strip()
        if not p.exists():
            bad.append((rel.strip(), h, "MISSING"))
        elif sha256(p) != h:
            bad.append((rel.strip(), h, sha256(p)))
    return bad


def load_state(env: Env):
    with open(env.state_path) as fh:
        return json.load(fh)


def save_state(env: Env, st):
    tmp = str(env.state_path) + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(st, fh, indent=1, sort_keys=True)
    os.replace(tmp, env.state_path)


def append_log(env: Env, rows):
    with open(env.log_path, "a") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, default=float) + "\n")


# ----------------------------------------------------------------------------------- --start
def cmd_start(env: Env):
    if env.state_path.exists():
        print("REFUSED: PREFRV_FORWARD_STATE.json already exists -- a forward book is "
              "started once (s1.3).")
        return 3
    if not env.t30_verdict.exists():
        print("REFUSED: T30_BORROW_VERDICT.json does not exist (s1.1).")
        return 3
    with open(env.t30_verdict) as fh:
        v = json.load(fh)
    if v.get("verdict") != "BORROW_WALL_PASSED":
        print("REFUSED: T30 verdict is %r, not BORROW_WALL_PASSED (s1.1). Branch not taken."
              % v.get("verdict"))
        return 3
    if int(v.get("clean_days", 0)) < 30:
        print("REFUSED: T30 verdict clean_days %s < 30 (s1.1)." % v.get("clean_days"))
        return 3
    bad = verify_pins(env)
    if bad:
        for rel, want, have in bad:
            print("PIN MISMATCH %s: pinned %s, on disk %s" % (rel, want, have))
        print("REFUSED: pre-registration pin set drifted (s1.2).")
        return 4
    if env.decisions.exists() and "T39_VETO" in env.decisions.read_text():
        print("REFUSED: DECISIONS.md contains T39_VETO (s1.4). Owner designs attended.")
        return 3

    alive = [p for p in v["pairs"] if p.get("alive")]  # verbatim, file order (s2)
    if not alive:
        print("REFUSED: verdict says BORROW_WALL_PASSED but has zero alive pairs "
              "(inconsistent verdict file; not starting).")
        return 3
    q = json.load(gzip.open(env.cache / "pref_halfspread.json.gz"))
    med = float(np.nanmedian([x.get("median_half_bp", np.nan) for x in q.values()]))
    pairs = []
    for p in alive:
        hs = [q.get(p["a"], {}).get("median_half_bp"), q.get(p["b"], {}).get("median_half_bp")]
        hs = [x if (x is not None and np.isfinite(x)) else med for x in hs]
        pairs.append(dict(a=p["a"], b=p["b"], root=p["a"].split(".")[0],
                          ibkr_a=ibkr_sym(p["a"]), ibkr_b=ibkr_sym(p["b"]),
                          hs_bp=float(max(hs))))
    ev_date = str(v.get("evaluated_at", ""))[:10]
    st = dict(
        started_at=time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        t30_evaluated_at=ev_date,
        prereg="PREFRV_FORWARD_PREREGISTRATION.md",
        pairs=pairs,
        status={str(k): "active" for k in range(len(pairs))},
        positions={},            # idx -> {w, age, entered}
        recall_zero_run={}, recall_pending={}, fee_missing_run={}, noprint_run={},
        pair_stats={str(k): dict(n=0, s=0.0, ss=0.0, cum=0.0) for k in range(len(pairs))},
        issuers_held=[],
        grid_done=[], n_book_weeks=0,
        skip_no_borrow={},
        fwd_raw={},
    )
    env.data.mkdir(parents=True, exist_ok=True)
    save_state(env, st)
    append_log(env, [dict(type="start", at=st["started_at"], t30_evaluated_at=ev_date,
                          n_pairs=len(pairs),
                          pairs=[f'{p["a"]}/{p["b"]}' for p in pairs])])
    print("STARTED: %d alive pairs (verbatim from T30 verdict, evaluated %s). First grid "
          "session = first 5g-th NYSE session strictly after %s and strictly after the "
          "evaluation date; --week takes it from here." % (len(pairs), ev_date, DESIGN_GRID_END))
    return 0


# ------------------------------------------------------------------------------------ --week
def design_grid_raw(env: Env, legs):
    """Design grid dates + per-leg raw closes on them, from the frozen (pinned) cache."""
    raw = json.load(gzip.open(env.cache / "pref_bars_raw.json.gz"))
    days = sorted({d for s in raw.values() for d in s})
    grid = [d for d in days[::5] if d <= DESIGN_GRID_END]
    return grid, {s: {d: raw[s].get(d) for d in grid} for s in legs if s in raw}


def forward_sessions(env: Env):
    spy = env.fetch_bars([CAL_SYM], "2026-08-15", env.today(), "raw").get(CAL_SYM, {})
    return sorted(d for d in spy if d > DESIGN_GRID_END)


def zscore(series_vals):
    """z of the last element vs the trailing Z_L values (excluding it), s3 validity rule."""
    *hist, cur = series_vals
    w = np.array(hist[-Z_L:], float)
    f = np.isfinite(w)
    if cur is None or not np.isfinite(cur) or f.sum() < Z_MINPTS:
        return float("nan")
    sd = float(np.nanstd(w, ddof=1))
    if not (sd > 0):
        return float("nan")
    return float((cur - np.nanmean(w)) / sd)


def cmd_week(env: Env):
    if not env.state_path.exists():
        print("inert: no PREFRV_FORWARD_STATE.json (book not started; --start gates on the "
              "T30 verdict). Nothing read, nothing written.")
        return 0
    st = load_state(env)
    pairs = st["pairs"]
    borrow = Borrow(env)
    env.data.mkdir(parents=True, exist_ok=True)

    sessions = forward_sessions(env)
    grid = [sessions[i] for i in range(4, len(sessions), 5)]     # 5g-th session
    start_after = max(DESIGN_GRID_END, st["t30_evaluated_at"])
    grid = [g for g in grid if g > start_after]
    done = set(st["grid_done"])
    sidx = {d: i for i, d in enumerate(sessions)}

    # legs still in play
    def live_idx():
        return [k for k in range(len(pairs)) if st["status"][str(k)] == "active"]

    legs = sorted({pairs[k][leg] for k in range(len(pairs)) for leg in ("a", "b")})
    if not live_idx():
        print("no active pairs remain; nothing to process.")
        return 0

    # fetch bars once, covering everything pending (append-only weekly snapshot + manifest)
    pending = [i for i in range(len(grid) - 1)
               if grid[i] not in done and sidx[grid[i + 1]] + 1 <= len(sessions) - 1]
    if not pending:
        print("no completed grid interval pending (grid so far: %s; done %d)."
              % (grid[-3:], len(done)))
        return 0
    fetch_from = (dt.date.fromisoformat(min(grid[i] for i in pending))
                  - dt.timedelta(days=10)).isoformat()
    bars_raw = env.fetch_bars(legs, fetch_from, env.today(), "raw")
    bars_adj = env.fetch_bars(legs, fetch_from, env.today(), "all")
    quotes = env.fetch_quotes(legs)
    hs_real = float(np.median(list(quotes.values()))) if quotes else float("nan")

    stamp = env.today()
    snap = env.data / f"bars_{stamp}.json.gz"
    with gzip.open(snap, "wt") as fh:
        json.dump(dict(fetched=stamp, from_=fetch_from, raw=bars_raw, adj=bars_adj,
                       quotes=quotes), fh)
    man_path = env.data / "manifest.json"
    man = json.load(open(man_path)) if man_path.exists() else {"files": []}
    man["files"].append(dict(file=snap.name, sha256=sha256(snap),
                             n_syms=len(bars_raw),
                             n_rows=sum(len(v) for v in bars_raw.values())))
    with open(man_path, "w") as fh:
        json.dump(man, fh, indent=1)

    dgrid, draw = design_grid_raw(env, legs)

    def raw_close(sym, d):
        if d <= DESIGN_GRID_END:
            return draw.get(sym, {}).get(d)
        v = st["fwd_raw"].get(sym, {}).get(d)
        return v if v is not None else bars_raw.get(sym, {}).get(d)

    def adj_close(sym, d):
        return bars_adj.get(sym, {}).get(d)

    n_new = 0
    for i in pending:
        t, t1 = grid[i], grid[i + 1]
        d1_fill_t = sessions[sidx[t] + 1]
        d1_fill_t1 = sessions[sidx[t1] + 1]

        # persist forward raw grid closes (z history for later weeks)
        for s in legs:
            v = bars_raw.get(s, {}).get(t)
            if v is not None:
                st["fwd_raw"].setdefault(s, {})[t] = v
            v1 = bars_raw.get(s, {}).get(t1)
            if v1 is not None:
                st["fwd_raw"].setdefault(s, {})[t1] = v1

        # ---- s4.5 no-print retirement, counted over sessions in (t, t1] -----------------
        # capture the iteration set BEFORE retiring, so a just-retired pair still gets its
        # closing row this week (it leaves the set from the next interval on)
        live_at_start = live_idx()
        span = [d for d in sessions if t < d <= t1]
        for k in live_at_start:
            p = pairs[k]
            retire = False
            for leg in ("a", "b"):
                key = f"{k}:{leg}"
                run = st["noprint_run"].get(key, 0)
                for d in span:
                    run = 0 if bars_raw.get(p[leg], {}).get(d) is not None else run + 1
                    if run >= NO_PRINT_SESSIONS:
                        retire = True
                st["noprint_run"][key] = run
            if retire:
                st["status"][str(k)] = "retired_no_print"

        # ---- decision at grid session t (s3 order; recall force-exit first, s4.4) -------
        rows = []
        p_net, p_gross, d1_net = [], [], []
        zgrid_hist = [d for d in (dgrid + [g for g in grid if g <= t]) if d <= t]
        zwin = zgrid_hist[-(Z_L + 1):]
        for k in live_at_start:
            p = pairs[k]
            ks = str(k)
            pos = st["positions"].get(ks)
            w = pos["w"] if pos else 0
            age = pos["age"] if pos else 0
            flags = []

            vals = []
            for d in zwin:
                ra_, rb_ = raw_close(p["a"], d), raw_close(p["b"], d)
                vals.append(math.log(ra_ / rb_) if ra_ and rb_ else float("nan"))
            z = zscore(vals) if zwin and zwin[-1] == t else float("nan")

            aa0, aa1 = adj_close(p["a"], t), adj_close(p["a"], t1)
            bb0, bb1 = adj_close(p["b"], t), adj_close(p["b"], t1)
            r_a = aa1 / aa0 - 1.0 if aa0 and aa1 else float("nan")
            r_b = bb1 / bb0 - 1.0 if bb0 and bb1 else float("nan")
            dead = not (np.isfinite(r_a) and np.isfinite(r_b))
            if st["status"][ks] == "retired_no_print" and w != 0:
                # close at last available closes (s4.5): use last finite adjusted close in span
                la = [adj_close(p["a"], d) for d in [t] + span]
                lb = [adj_close(p["b"], d) for d in [t] + span]
                la = [x for x in la if x]
                lb = [x for x in lb if x]
                r_a = la[-1] / la[0] - 1.0 if len(la) > 1 else 0.0
                r_b = lb[-1] / lb[0] - 1.0 if len(lb) > 1 else 0.0
                dead = False

            nw = w
            extra_hs = 0.0
            if w != 0 and st["recall_pending"].get(ks):
                nw = 0
                extra_hs = p["hs_bp"]
                flags.append("exit_recall")
                st["recall_pending"].pop(ks, None)
                st["recall_zero_run"].pop(ks, None)
            elif st["status"][ks] == "retired_no_print":
                if w != 0:
                    nw = 0
                    flags.append("retire_no_print")
            elif w != 0 and np.isfinite(z) and abs(z) <= Z_X:
                nw = 0
                flags.append("exit_band")
            elif w != 0 and age >= MAXHOLD:
                nw = 0
                flags.append("exit_maxhold")
            elif w != 0 and dead:
                nw = 0
                flags.append("exit_no_print_return")
            elif w == 0 and np.isfinite(z) and abs(z) >= Z_K and not dead \
                    and st["status"][ks] == "active":
                want = -1 if z > 0 else 1
                short_leg = p["ibkr_a"] if want == -1 else p["ibkr_b"]
                av = borrow.avail(short_leg, t)
                if av is not None and av > 0:
                    nw = want
                    flags.append("enter")
                else:
                    st["skip_no_borrow"][ks] = st["skip_no_borrow"].get(ks, 0) + 1
                    flags.append("skip_no_borrow")

            dw = abs(nw - w)
            held = nw != 0
            traded = dw > 0
            if not held and not traded:
                if "skip_no_borrow" in flags:
                    rows.append(dict(type="pair", grid=t, pair=f'{p["a"]}/{p["b"]}',
                                     w=0, z=z, flags=flags))
                continue

            # ---- s4.2 realised borrow fee over calendar days in (t, t1] ----------------
            fee_bp = 0.0
            if held:
                short_alp = p["a"] if nw == -1 else p["b"]
                short_ib = p["ibkr_a"] if nw == -1 else p["ibkr_b"]
                run = st["fee_missing_run"].get(ks, 0)
                for d in cal_days(t, t1):
                    f = borrow.fee_pct(short_ib, d)
                    if np.isfinite(f):
                        fee_bp += f / 100.0 / 365.0 * 1e4
                        run = 0
                    else:
                        run += 1
                        if run >= FEE_MISSING_DAYS:
                            st["recall_pending"][ks] = True
                            flags.append("fee_missing_recall")
                st["fee_missing_run"][ks] = run
                # ---- s4.4 recall watch: consecutive clean extracts with AVAILABLE == 0 -
                zrun = st["recall_zero_run"].get(ks, 0)
                for cd in borrow.clean_in(t, t1):
                    av = borrow.avail_on_clean(short_ib, cd)
                    zrun = zrun + 1 if av == 0 else 0
                    if zrun >= RECALL_ZERO_EXTRACTS:
                        st["recall_pending"][ks] = True
                st["recall_zero_run"][ks] = zrun
                # capacity note (report-only, s4.6)
                capacity = None
                av_now = borrow.avail(short_ib, t1)
                px = bars_raw.get(short_alp, {}).get(t1)
                if av_now is not None and px:
                    capacity = av_now * px
            else:
                capacity = None

            gross_bp = (nw * (r_a - r_b)) * 1e4 if held else 0.0
            if held and not np.isfinite(gross_bp):
                gross_bp = 0.0
            cost_bp = dw * (2.0 * p["hs_bp"] + SEC31_BP) + extra_hs
            net_bp = gross_bp - cost_bp - fee_bp
            p_gross.append(gross_bp)
            p_net.append(net_bp)

            # ---- D1 diagnostic (same weights/costs/fee; one-session-later fills) -------
            da0, da1 = adj_close(p["a"], d1_fill_t), adj_close(p["a"], d1_fill_t1)
            db0, db1 = adj_close(p["b"], d1_fill_t), adj_close(p["b"], d1_fill_t1)
            if held and da0 and da1 and db0 and db1:
                d1g = nw * ((da1 / da0 - 1.0) - (db1 / db0 - 1.0)) * 1e4
                d1_net.append(d1g - cost_bp - fee_bp)
            elif traded and not held:
                d1_net.append(-cost_bp)

            if held:
                st["positions"][ks] = dict(w=nw, age=(age + 1 if w == nw else 1), entered=(
                    pos["entered"] if (pos and w == nw) else t))
                roots = set(st["issuers_held"])
                roots.add(p["root"])
                st["issuers_held"] = sorted(roots)
            else:
                st["positions"].pop(ks, None)
                st["fee_missing_run"].pop(ks, None)
                st["recall_zero_run"].pop(ks, None)

            ps = st["pair_stats"][ks]
            ps["n"] += 1
            ps["s"] += net_bp
            ps["ss"] += net_bp * net_bp
            ps["cum"] += net_bp
            # ---- s6 per-pair drop --------------------------------------------------------
            if ps["n"] >= DROP_MIN_WEEKS and st["status"][ks] == "active":
                m = ps["s"] / ps["n"]
                var = max(ps["ss"] / ps["n"] - m * m, 0.0) * ps["n"] / max(ps["n"] - 1, 1)
                ub = m + Z95_ONE_SIDED * math.sqrt(var / ps["n"])
                if ub < 0:
                    st["status"][ks] = "dropped_neg"
                    if ks in st["positions"]:
                        flags.append("drop_neg_flat_next")

            rows.append(dict(type="pair", grid=t, pair=f'{p["a"]}/{p["b"]}', w=nw, z=z,
                             r_a=r_a, r_b=r_b, gross_bp=gross_bp, cost_bp=cost_bp,
                             fee_bp=fee_bp, net_bp=net_bp, capacity=capacity, flags=flags))

        n_active = len(p_net)
        counted = n_active > 0        # a zero-active week is not an observation (s4.6)
        book = dict(type="book", grid=t, next_grid=t1, n_active=n_active,
                    counted=counted,
                    p_gross_bp=float(np.mean(p_gross)) if counted else None,
                    p_net_bp=float(np.mean(p_net)) if counted else None,
                    d1_net_bp=float(np.mean(d1_net)) if d1_net else None,
                    n_d1=len(d1_net), realised_hs_median_bp=hs_real,
                    n_pairs_alive=len(live_idx()))
        append_log(env, rows + [book])
        if counted:
            st["n_book_weeks"] += 1
        st["grid_done"].append(t)
        save_state(env, st)
        n_new += 1
        print("week %s -> %s: n_active %d, P net %s bp, D1 net %s bp (N=%d)"
              % (t, t1, n_active,
                 "%.1f" % book["p_net_bp"] if counted else "--",
                 "%.1f" % book["d1_net_bp"] if book["d1_net_bp"] is not None else "--",
                 st["n_book_weeks"]))

    print("processed %d interval(s); book-weeks N=%d; active pairs %d/%d."
          % (n_new, st["n_book_weeks"], len(live_idx()), len(pairs)))
    return 0


# --------------------------------------------------------------------------------- --verdict
def cmd_verdict(env: Env):
    if env.verdict_path.exists():
        with open(env.verdict_path) as fh:
            old = json.load(fh)
        if old.get("verdict") in TERMINAL:
            print("REFUSED: terminal verdict %s already written %s; never re-read (s7)."
                  % (old["verdict"], old.get("at")))
            return 3
    if not env.state_path.exists() or not env.log_path.exists():
        print("no forward book (state/log missing); nothing to judge.")
        return 0
    st = load_state(env)
    books, pair_rows = [], []
    with open(env.log_path) as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("type") == "book" and r.get("counted"):
                books.append(r)
            elif r.get("type") == "pair":
                pair_rows.append(r)
    N = len(books)
    net = np.array([b["p_net_bp"] for b in books], float)
    gross = np.array([b["p_gross_bp"] for b in books], float)
    d1 = np.array([b["d1_net_bp"] for b in books if b.get("d1_net_bp") is not None], float)
    m = float(net.mean()) if N else float("nan")
    sd = float(net.std(ddof=1)) if N > 1 else float("nan")
    t_net = m / (sd / math.sqrt(N)) if N > 1 and sd > 0 else float("nan")
    mg = float(gross.mean()) if N else float("nan")
    sdg = float(gross.std(ddof=1)) if N > 1 else float("nan")
    t_gross = mg / (sdg / math.sqrt(N)) if N > 1 and sdg > 0 else float("nan")
    ub95 = m + Z95_ONE_SIDED * sd / math.sqrt(N) if N > 1 else float("nan")
    issuers_held = st["issuers_held"]

    cum = {ks: v["cum"] for ks, v in st["pair_stats"].items() if v["n"] > 0}
    pos_cum = {ks: c for ks, c in cum.items() if c > 0}
    share_max = (max(pos_cum.values()) / sum(pos_cum.values())) if pos_cum else 0.0
    issuers_pos = sorted({st["pairs"][int(ks)]["root"] for ks in pos_cum})
    hs_real = [b["realised_hs_median_bp"] for b in books
               if b.get("realised_hs_median_bp") is not None
               and np.isfinite(b["realised_hs_median_bp"])]
    hs_med = float(np.median(hs_real)) if hs_real else float("nan")
    n_alive_set = sum(1 for v in st["status"].values() if v == "active")

    verdict, why = "UNDECIDED", []
    if N >= N_MIN and len(issuers_held) < MIN_ISSUERS:
        verdict, why = "DEAD", ["not executable: <3 distinct issuers ever held by N=40"]
    elif N >= N_MIN and np.isfinite(ub95) and ub95 < 0:
        verdict, why = "DEAD", ["pooled net upper-95 %.2f bp < 0 at N=%d" % (ub95, N)]
    elif N >= N_MIN and np.isfinite(mg) and mg <= 0:
        verdict, why = "DEAD", ["tether failed forward: mean gross %.2f bp <= 0" % mg]
    elif N >= N_ALIVE:
        gates = dict(
            t_net=bool(np.isfinite(t_net) and t_net >= ALIVE_T),
            mean=bool(np.isfinite(m) and m >= ALIVE_MEAN_BP),
            t_gross=bool(np.isfinite(t_gross) and t_gross >= ALIVE_T),
            d1_sign=bool(len(d1) > 0 and float(d1.mean()) > 0),
            share=bool(share_max <= PAIR_SHARE_MAX),
            issuers=bool(len(issuers_pos) >= MIN_ISSUERS),
        )
        if all(gates.values()):
            verdict = "ALIVE"
            why = ["all s7 gates pass"]
            if n_alive_set >= PROMO_MIN_PAIRS and np.isfinite(hs_med) and hs_med <= PROMO_HS_BP:
                verdict = "PROMOTABLE"
                why = ["ALIVE + s3.1 guard (%d pairs, realised hs %.1f bp)"
                       % (n_alive_set, hs_med)]
        elif N >= N_MAX:
            verdict, why = "RETIRED", ["unproven at N_max=%d" % N_MAX]
        else:
            why = ["gates: " + json.dumps(gates)]
    elif N >= N_MAX:
        verdict, why = "RETIRED", ["unproven at N_max=%d" % N_MAX]

    out = dict(at=time.strftime("%Y-%m-%d %H:%M:%S %Z"), N_book_weeks=N,
               mean_net_bp=m, sd_net_bp=sd, t_net=t_net, t_net_nw4=nw_t(net),
               mean_gross_bp=mg, t_gross=t_gross, upper95_net_bp=ub95,
               d1_mean_net_bp=float(d1.mean()) if len(d1) else None,
               max_pair_share=share_max, issuers_positive=issuers_pos,
               issuers_held=issuers_held, n_pairs_alive_now=n_alive_set,
               realised_hs_median_bp=hs_med, verdict=verdict, why=why,
               rules="PREFRV_FORWARD_PREREGISTRATION.md s6-s7 verbatim")
    with open(env.verdict_path, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print("verdict at N=%d: %s (%s)  net %.2f bp t %.2f | gross %.2f bp t %.2f | ub95 %.2f"
          % (N, verdict, "; ".join(why), m if N else float("nan"), t_net, mg, t_gross,
             ub95 if N > 1 else float("nan")))
    if verdict in TERMINAL:
        print("TERMINAL: nothing below this file is ever re-read (s7); the runner now "
              "refuses --verdict and the book is closed.")
    return 0


# -------------------------------------------------------------------------------- --selftest
def _weekdays(end, n):
    """n weekdays ending at `end` (inclusive), ascending."""
    d = dt.date.fromisoformat(end)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= dt.timedelta(days=1)
    return out[::-1]


def _weekdays_after(start, n):
    d = dt.date.fromisoformat(start)
    out = []
    while len(out) < n:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d.isoformat())
    return out


def cmd_selftest():
    """Synthetic panels only.  Builds a fake repo in a tempdir; never touches real data."""
    failures = []

    def check(name, cond):
        print(("  ok  " if cond else "  FAIL") + " " + name)
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        env = Env(root)
        for p in (env.rt, env.data, env.borrow / "extract", env.cache):
            p.mkdir(parents=True, exist_ok=True)

        # --- synthetic design history: 271 weekdays ending 2026-08-14 -> 55 grid sessions
        hist_days = _weekdays(DESIGN_GRID_END, 271)
        legs = ["RA.PRA", "RA.PRB", "RB.PRA", "RB.PRB", "RC.PRA", "RC.PRB",
                "RD.PRA", "RD.PRB"]
        pairs_syn = [("RA.PRA", "RA.PRB"), ("RB.PRA", "RB.PRB"),
                     ("RC.PRA", "RC.PRB"), ("RD.PRA", "RD.PRB")]
        rng = np.random.default_rng(20260831)
        raw_hist = {}
        for s in legs:
            base = 25.0
            eps = rng.normal(0, 0.004, len(hist_days)) if s.endswith("A") else 0.0
            raw_hist[s] = {d: float(base * math.exp(eps[i] if s.endswith("A") else 0.0))
                           for i, d in enumerate(hist_days)}
        with gzip.open(env.cache / "pref_bars_raw.json.gz", "wt") as fh:
            json.dump(raw_hist, fh)
        with gzip.open(env.cache / "pref_halfspread.json.gz", "wt") as fh:
            json.dump({s: dict(median_half_bp=10.0) for s in legs}, fh)

        # --- forward calendar + price paths (raw == adj; no dividends in the synth panel)
        fwd = _weekdays_after(DESIGN_GRID_END, 25)   # through 5 grid sessions
        grid_fwd = fwd[4::5]
        JUMP = 0.05

        def px(sym, d):
            if d <= DESIGN_GRID_END:
                return raw_hist.get(sym, {}).get(d)
            # RA.PRA jumps +5% on grid1, reverts after grid1 (entry then band exit)
            if sym == "RA.PRA":
                return 25.0 * math.exp(JUMP) if d <= grid_fwd[0] else 25.0
            # RB.PRA same shape (tests skip_no_borrow: its short leg has AVAILABLE=0 at t)
            if sym == "RB.PRA":
                return 25.0 * math.exp(JUMP) if d <= grid_fwd[0] else 25.0
            # RC.PRA jumps and STAYS (position held over several weeks; recall test)
            if sym == "RC.PRA":
                return 25.0 * math.exp(JUMP)
            # RD.PRA jumps, then the leg stops printing after grid2 (retirement test)
            if sym == "RD.PRA":
                if d > grid_fwd[1]:
                    return None
                return 25.0 * math.exp(JUMP)
            return 25.0

        def fetch_bars(syms, start, end, adjustment):
            out = {}
            days = [d for d in (hist_days + fwd) if start <= d <= end]
            for s in syms:
                if s == CAL_SYM:
                    out[s] = {d: 500.0 for d in fwd if start <= d <= end}
                    continue
                vals = {d: px(s, d) for d in days}
                out[s] = {d: v for d, v in vals.items() if v is not None}
            return out

        env.fetch_bars = fetch_bars
        env.fetch_quotes = lambda syms: {s: 8.0 for s in syms}
        env.today = lambda: fwd[-1]

        # --- synthetic borrow feed: clean every weekday; FEERATE 3.65 %/yr -> 1 bp/day
        ledger = dict(days={d: dict(status="clean") for d in fwd},
                      summary=dict(days_clean=len(fwd), days_attempted=len(fwd)))
        with open(env.borrow / "ledger.json", "w") as fh:
            json.dump(ledger, fh)
        # RC recall: short leg (RC.PRA, since z>0 -> w=-1 -> short a) AVAILABLE=0 on the two
        # weekdays right after grid2 -> close at grid3 with extra hs.
        recall_days = set(_weekdays_after(grid_fwd[1], 2))
        for d in fwd:
            rows = []
            for s in legs:
                avail = 1000
                if s == "RB.PRB" or (s == "RB.PRA"):
                    avail = 0 if s == "RB.PRA" else 1000   # RB short leg unborrowable
                if s == "RC.PRA" and d in recall_days:
                    avail = 0
                rows.append(dict(SYM=ibkr_sym(s), FEERATE="3.65", AVAILABLE=str(avail)))
            with open(env.borrow / "extract" / f"extract_{d}.json", "w") as fh:
                json.dump(dict(bof="syn", date=d, n_matched=len(rows),
                               n_universe=len(rows), rows=rows), fh)

        # --- synthetic T30 verdict + pins + decisions ------------------------------------
        vpairs = [dict(a=a, b=b, alive=True) for a, b in pairs_syn]
        vpairs.append(dict(a="RA.PRA", b="RB.PRB", alive=False))   # must be excluded
        verdict = dict(verdict="BORROW_WALL_PASSED", clean_days=30,
                       evaluated_at="2026-08-18 22:00:00 UTC", pairs=vpairs)
        with open(env.t30_verdict, "w") as fh:
            json.dump(verdict, fh)
        env.decisions.write_text("owner log; no veto here\n")
        pin_targets = ["research/data/inv0822_tether/pref_bars_raw.json.gz",
                       "research/data/inv0822_tether/pref_halfspread.json.gz"]
        env.pinfile.write_text("".join(
            "%s  %s\n" % (sha256(root / rel), rel) for rel in pin_targets))

        print("[1] --start refusal gates")
        with open(env.t30_verdict, "w") as fh:
            json.dump(dict(verdict, verdict="PERMANENTLY_DEAD"), fh)
        check("refuses on PERMANENTLY_DEAD", cmd_start(env) == 3)
        with open(env.t30_verdict, "w") as fh:
            json.dump(dict(verdict, clean_days=20), fh)
        check("refuses on clean_days<30", cmd_start(env) == 3)
        env.decisions.write_text("2026-09-01 owner: T39_VETO, designing attended\n")
        with open(env.t30_verdict, "w") as fh:
            json.dump(verdict, fh)
        check("refuses on T39_VETO", cmd_start(env) == 3)
        env.decisions.write_text("no veto\n")
        env.pinfile.write_text("0" * 64 + "  " + pin_targets[0] + "\n")
        check("refuses on pin mismatch", cmd_start(env) == 4)
        env.pinfile.write_text("".join(
            "%s  %s\n" % (sha256(root / rel), rel) for rel in pin_targets))
        check("starts when all gates hold", cmd_start(env) == 0)
        check("refuses on existing state", cmd_start(env) == 3)
        st = load_state(env)
        check("alive set verbatim (4 pairs, non-alive excluded)",
              len(st["pairs"]) == 4 and all(
                  (p["a"], p["b"]) == pairs_syn[i] for i, p in enumerate(st["pairs"])))
        check("hs_bp = max leg half-spread", all(p["hs_bp"] == 10.0 for p in st["pairs"]))

        print("[2] --week state machine + cost/fee arithmetic")
        check("week runs", cmd_week(env) == 0)
        st = load_state(env)
        logs = [json.loads(x) for x in open(env.log_path)]
        pair_rows = [r for r in logs if r.get("type") == "pair"]
        books = [r for r in logs if r.get("type") == "book"]

        g1 = grid_fwd[0]
        ra_rows = {r["grid"]: r for r in pair_rows if r["pair"] == "RA.PRA/RA.PRB"}
        rb_rows = {r["grid"]: r for r in pair_rows if r["pair"] == "RB.PRA/RB.PRB"}
        rc_rows = {r["grid"]: r for r in pair_rows if r["pair"] == "RC.PRA/RC.PRB"}
        rd_rows = {r["grid"]: r for r in pair_rows if r["pair"] == "RD.PRA/RD.PRB"}
        r1 = ra_rows.get(g1)
        check("RA enters short at grid1 (z>2 -> w=-1)",
              r1 is not None and r1["w"] == -1 and "enter" in r1["flags"])
        # hand-check the entry week: gross = -(e^{-J}-1)*1e4; cost = 2*10+0.278;
        # fee = days_in_(g1,g2] * 1bp/day
        exp_gross = -(math.exp(-JUMP) - 1.0) * 1e4
        ndays = len(cal_days(g1, grid_fwd[1]))
        check("RA gross arithmetic", abs(r1["gross_bp"] - exp_gross) < 1e-6)
        check("RA entry cost = 2hs+SEC31", abs(r1["cost_bp"] - (20.0 + SEC31_BP)) < 1e-9)
        check("RA fee = 1bp/calendar-day held", abs(r1["fee_bp"] - ndays * 1.0) < 1e-9)
        r2 = ra_rows.get(grid_fwd[1])
        check("RA band-exits at grid2 with exit cost charged",
              r2 is not None and r2["w"] == 0 and "exit_band" in r2["flags"]
              and abs(r2["cost_bp"] - (20.0 + SEC31_BP)) < 1e-9 and r2["gross_bp"] == 0.0)
        rb1 = rb_rows.get(g1)
        check("RB blocked by borrow gate (skip_no_borrow)",
              rb1 is not None and rb1["w"] == 0 and "skip_no_borrow" in rb1["flags"])
        check("skip_no_borrow counted in state", st["skip_no_borrow"].get("1", 0) >= 1)
        rc3 = rc_rows.get(grid_fwd[2])
        check("RC recall-exits at grid3 with extra hs",
              rc3 is not None and "exit_recall" in rc3["flags"]
              and abs(rc3["cost_bp"] - (20.0 + SEC31_BP + 10.0)) < 1e-9)
        check("RD retired after 5 no-print sessions",
              st["status"]["3"] == "retired_no_print"
              and any("retire_no_print" in r.get("flags", []) for r in rd_rows.values()))
        check("issuers_held tracked", set(st["issuers_held"]) >= {"RA", "RC", "RD"})
        check("book rows counted only when active",
              all(b["counted"] == (b["n_active"] > 0) for b in books)
              and st["n_book_weeks"] == sum(1 for b in books if b["counted"]))
        check("D1 recorded", any(b.get("d1_net_bp") is not None for b in books))
        check("idempotent (no re-processing)", cmd_week(env) == 0
              and len([json.loads(x) for x in open(env.log_path)]) == len(logs))
        check("append-only manifest written",
              json.load(open(env.data / "manifest.json"))["files"])

        print("[3] --verdict rules on crafted books")
        def crafted(books_rows, st_extra=None):
            e2 = Env(root / "v")
            e2.rt.mkdir(parents=True, exist_ok=True)
            s2 = dict(st)
            s2.update(st_extra or {})
            with open(e2.state_path, "w") as fh:
                json.dump(s2, fh, default=float)
            with open(e2.log_path, "w") as fh:
                for r in books_rows:
                    fh.write(json.dumps(r, default=float) + "\n")
            cmd_verdict(e2)
            with open(e2.verdict_path) as fh:
                out = json.load(fh)
            code = cmd_verdict(e2) if out["verdict"] in TERMINAL else None
            for p in (e2.state_path, e2.log_path, e2.verdict_path):
                p.unlink(missing_ok=True)
            return out, code

        def mk(n, net, gross, d1=5.0, hs=8.0):
            return [dict(type="book", grid="g%d" % i, counted=True, n_active=3,
                         p_net_bp=net, p_gross_bp=gross, d1_net_bp=d1, n_d1=3,
                         realised_hs_median_bp=hs) for i in range(n)]

        many_iss = dict(issuers_held=["RA", "RB", "RC"],
                        pair_stats={"0": dict(n=40, s=400.0, ss=99999.0, cum=400.0),
                                    "1": dict(n=40, s=390.0, ss=99999.0, cum=390.0),
                                    "2": dict(n=40, s=380.0, ss=99999.0, cum=380.0),
                                    "3": dict(n=0, s=0.0, ss=0.0, cum=0.0)})
        out, _ = crafted(mk(45, -50.0, -10.0), many_iss)
        check("DEAD on gross<=0 / negative net at N>=40", out["verdict"] == "DEAD")
        rows = mk(45, 5.0, 20.0)
        for i, r in enumerate(rows):   # tiny wiggle so sd>0, mean stays ~5
            r["p_net_bp"] = 5.0 + (0.1 if i % 2 else -0.1)
        out, _ = crafted(rows, many_iss)
        check("UNDECIDED on small positive at N=45", out["verdict"] == "UNDECIDED")
        rows = mk(60, 30.0, 40.0)
        for i, r in enumerate(rows):
            r["p_net_bp"] = 30.0 + (3.0 if i % 2 else -3.0)
            r["p_gross_bp"] = 40.0 + (3.0 if i % 2 else -3.0)
        out, code = crafted(rows, many_iss)
        check("ALIVE when every s7 gate passes", out["verdict"] == "ALIVE")
        check("terminal verdict refuses re-run", code == 3)
        out, _ = crafted([dict(r, d1_net_bp=-1.0) for r in rows], many_iss)
        check("D1 sign witness blocks ALIVE", out["verdict"] == "UNDECIDED")
        one_iss = dict(many_iss, issuers_held=["RA"])
        out, _ = crafted(rows, one_iss)
        check("DEAD not-executable on <3 issuers held", out["verdict"] == "DEAD"
              and "not executable" in out["why"][0])
        conc = dict(many_iss, pair_stats={"0": dict(n=60, s=900.0, ss=9e9, cum=900.0),
                                          "1": dict(n=60, s=50.0, ss=9e9, cum=50.0),
                                          "2": dict(n=60, s=50.0, ss=9e9, cum=50.0),
                                          "3": dict(n=0, s=0.0, ss=0.0, cum=0.0)})
        out, _ = crafted(rows, conc)
        check("40% pair-share gate blocks ALIVE", out["verdict"] == "UNDECIDED")
        rows156 = mk(156, 2.0, 10.0)
        for i, r in enumerate(rows156):
            r["p_net_bp"] = 2.0 + (5.0 if i % 2 else -5.0)
        out, _ = crafted(rows156, many_iss)
        check("RETIRED unproven at N_max", out["verdict"] == "RETIRED")

        print("[4] inert without state")
        e3 = Env(root / "inert")
        e3.rt.mkdir(parents=True, exist_ok=True)
        check("--week inert with no state file", cmd_week(e3) == 0)

    if failures:
        print("\nSELFTEST FAIL: %d assertion(s): %s" % (len(failures), failures))
        return 1
    print("\nSELFTEST OK: all assertions passed on synthetic panels; no real data read.")
    return 0


# --------------------------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--start", action="store_true")
    g.add_argument("--week", action="store_true")
    g.add_argument("--verdict", action="store_true")
    g.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return cmd_selftest()
    env = Env(pathlib.Path(__file__).resolve().parents[2])
    if a.start:
        return cmd_start(env)
    if a.week:
        return cmd_week(env)
    return cmd_verdict(env)


if __name__ == "__main__":
    sys.exit(main())
