#!/usr/bin/env python3
"""T32 — SPX box-spread implied lending rate measured DURING regular trading hours.

Third and FINAL probe of the box (T21 §6.8 candidate; T25_BOX_PROBE.json measured it
with the market closed: mid +0.37 pp over 3m T-bills, four-leg executable 3.65 pp
BELOW). This script is fully self-contained and detached: it waits for the capture
start (default 13:30 UTC = 09:30 ET), takes a quote snapshot every INTERVAL minutes
for DURATION minutes, then computes the rates and writes
research/trading_bot/T32_BOX_RTH.json and .md itself. No agent turn waits on it.

Quotes only: Alpaca options chain snapshots (data.alpaca.markets, paper keys from
.env, default feed). NO orders of any kind, paper or otherwise.

PRE-REGISTERED PROTOCOL (frozen before any RTH quote is read):
  * Primary expiry = 2027-08-20 (~1.0 y). Secondary: 2027-06-17, 2027-12-17 (rate
    curve shape) and 2026-12-18 (direct comparison with T25's closed-market read).
  * Box(K1<K2) = +C(K1) -C(K2) -P(K1) +P(K2); pays K2-K1 at expiry (European, cash).
    Lender BUYS the box: mid cost uses four mids; EXECUTABLE cost = ask C1 - bid C2
    - bid P1 + ask P2 (crossing all four spreads, no leg legged).
  * Rate = simple annualised: ((K2-K1)/cost - 1) / T * 100, T in ACT/365 years.
  * Pair filter: all four legs two-sided (bid>0, ask>0) with quote timestamp on the
    capture day; both strikes within [0.70, 1.30] x parity-implied forward; width
    500 <= K2-K1 <= 2000 index points.
  * Per snapshot per expiry: n_pairs, p25 / median / p75 / p90 of mid and executable.
    Session number = MEDIAN across snapshots of the per-snapshot MEDIAN (same estimand
    T25 reported). p90 is reported as context ("a lender cherry-picking the best
    decile of pairs") but the verdict is on the median.
  * Benchmark: latest FRED DTB3 (3-month T-bill, %), fetched live, cache fallback.
  * KILL-CONDITION (frozen in agenda T32): primary-expiry session-median EXECUTABLE
    four-leg rate below the T-bill => the box is PERMANENTLY DEAD, no fourth probe.
    Only if it clears T-bills does a next step exist (and it would be a design, not
    a trade).
"""
import argparse
import datetime as dt
import json
import os
import statistics as st
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT_JSON = os.path.join(REPO, "research", "trading_bot", "T32_BOX_RTH.json")
OUT_MD = os.path.join(REPO, "research", "trading_bot", "T32_BOX_RTH.md")
RAW_DIR = os.path.join(REPO, "research", "data", "t32_box_rth")
CASH_CSV = os.path.join(REPO, "research", "data", "t13_cache", "cash.csv")
PRIMARY = "2027-08-20"
EXPIRIES = ["2027-08-20", "2027-06-17", "2027-12-17", "2026-12-18"]
BAND = (0.70, 1.30)
WIDTH = (500.0, 2000.0)
DATA = "https://data.alpaca.markets/v1beta1/options/snapshots/SPX"
CLOCK = "https://paper-api.alpaca.markets/v2/clock"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"


def creds():
    env = {}
    try:
        with open(os.path.join(REPO, ".env")) as fh:
            for line in fh:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except IOError:
        pass
    k = os.environ.get("ALPACA_API_KEY_ID") or env.get("ALPACA_API_KEY_ID")
    s = os.environ.get("ALPACA_API_SECRET_KEY") or env.get("ALPACA_API_SECRET_KEY")
    if not k or not s:
        raise SystemExit("no Alpaca paper keys in env/.env")
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}


def get(url, headers, tries=5):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40) as fh:
                return json.load(fh)
        except urllib.error.HTTPError as exc:
            last = "HTTP %d %s" % (exc.code, exc.read().decode(errors="replace")[:120])
            if exc.code == 429:
                time.sleep(3.0 * (i + 1))
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
        time.sleep(1.0 * (i + 1))
    raise RuntimeError("%s -> %s" % (url[:80], last))


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S %Z"), msg)
    print(line, flush=True)
    with open(os.path.join(RAW_DIR, "capture.log"), "a") as fh:
        fh.write(line + "\n")


def tbill():
    try:
        body = urllib.request.urlopen(FRED, timeout=30).read().decode()
        rows = [l.split(",") for l in body.strip().splitlines()[1:]]
        rows = [r for r in rows if len(r) == 2 and r[1] not in (".", "")]
        d, v = rows[-1]
        return float(v), "FRED DTB3 %s (live)" % d
    except Exception as exc:  # noqa: BLE001
        with open(CASH_CSV) as fh:
            last = fh.read().strip().splitlines()[-1].split(",")
        return float(last[1]), "%s %s (cache fallback; live fetch failed: %s)" % (last[2], last[0], exc)


def fetch_chain(expiry, headers):
    out, token = {}, None
    while True:
        params = {"expiration_date": expiry, "limit": 1000}
        if token:
            params["page_token"] = token
        body = get(DATA + "?" + urllib.parse.urlencode(params), headers)
        for sym, snap in (body.get("snapshots") or {}).items():
            q = snap.get("latestQuote") or {}
            # SPX270820C03100000: root SPX, yymmdd, C/P, strike*1000
            core = sym[3:]
            cp = core[6]
            strike = int(core[7:]) / 1000.0
            out[(strike, cp)] = {"bp": q.get("bp"), "ap": q.get("ap"), "bs": q.get("bs"),
                                 "as": q.get("as"), "t": q.get("t"), "sym": sym}
        token = body.get("next_page_token")
        if not token:
            break
    return out


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 3)


def summarise(xs):
    return {"n": len(xs), "p25": pct(xs, 0.25), "median": pct(xs, 0.5),
            "p75": pct(xs, 0.75), "p90": pct(xs, 0.9), "max": (round(max(xs), 3) if xs else None)}


ALLOW_STALE = False  # preflight-only math check against T25's closed-market read


def analyse(chain, expiry, capture_day, asof):
    T = (dt.date.fromisoformat(expiry) - asof.date()).days / 365.0
    strikes = sorted({k for (k, cp) in chain})
    good = {}
    stale = 0
    for k in strikes:
        c, p = chain.get((k, "C")), chain.get((k, "P"))
        if not c or not p:
            continue
        legs = [c, p]
        if any((l["bp"] or 0) <= 0 or (l["ap"] or 0) <= 0 for l in legs):
            continue
        if any(not (l["t"] or "").startswith(capture_day) for l in legs):
            stale += 1
            if not ALLOW_STALE:
                continue
        good[k] = (c, p)
    # parity-implied forward: strike minimising |C_mid - P_mid|
    fwd = None
    if good:
        fwd = min(good, key=lambda k: abs((good[k][0]["bp"] + good[k][0]["ap"]) / 2
                                          - (good[k][1]["bp"] + good[k][1]["ap"]) / 2))
    mids, execs, pairs = [], [], 0
    ks = [k for k in sorted(good) if fwd and BAND[0] * fwd <= k <= BAND[1] * fwd]
    for i, k1 in enumerate(ks):
        c1, p1 = good[k1]
        for k2 in ks[i + 1:]:
            w = k2 - k1
            if w < WIDTH[0]:
                continue
            if w > WIDTH[1]:
                break
            c2, p2 = good[k2]
            mid_cost = ((c1["bp"] + c1["ap"]) / 2 - (c2["bp"] + c2["ap"]) / 2
                        - (p1["bp"] + p1["ap"]) / 2 + (p2["bp"] + p2["ap"]) / 2)
            ex_cost = c1["ap"] - c2["bp"] - p1["bp"] + p2["ap"]
            if mid_cost <= 0 or ex_cost <= 0:
                continue
            pairs += 1
            mids.append((w / mid_cost - 1.0) / T * 100.0)
            execs.append((w / ex_cost - 1.0) / T * 100.0)
    return {"years_to_expiry": round(T, 3), "strikes_quoted": len(strikes),
            "strikes_two_sided_fresh": len(good), "strikes_stale_quote": stale,
            "parity_forward": fwd, "strikes_in_band": len(ks), "n_pairs": pairs,
            "mid": summarise(mids), "executable": summarise(execs)}


def snapshot(label, headers, asof):
    day = asof.strftime("%Y-%m-%d")
    res = {"label": label, "taken_utc": asof.strftime("%Y-%m-%dT%H:%M:%SZ"), "expiries": {}}
    try:
        res["clock"] = get(CLOCK, headers)
    except RuntimeError as exc:
        res["clock"] = {"error": str(exc)}
    for e in EXPIRIES:
        try:
            chain = fetch_chain(e, headers)
            with open(os.path.join(RAW_DIR, "chain_%s_%s.json" % (e, label)), "w") as fh:
                json.dump({k[1] + str(k[0]): v for k, v in chain.items()}, fh)
            res["expiries"][e] = analyse(chain, e, day, asof)
        except Exception as exc:  # noqa: BLE001
            res["expiries"][e] = {"error": repr(exc)}
    return res


def aggregate(snaps, tb):
    per = {}
    for e in EXPIRIES:
        rows = [s["expiries"][e] for s in snaps if "error" not in s["expiries"].get(e, {"error": 1})
                and s["expiries"][e]["n_pairs"] > 0]
        if not rows:
            per[e] = {"n_snapshots": 0}
            continue
        med_mid = [r["mid"]["median"] for r in rows]
        med_ex = [r["executable"]["median"] for r in rows]
        p90_ex = [r["executable"]["p90"] for r in rows]
        per[e] = {
            "n_snapshots": len(rows),
            "years_to_expiry": rows[0]["years_to_expiry"],
            "median_pairs_per_snapshot": pct([r["n_pairs"] for r in rows], 0.5),
            "session_median_mid_pct": pct(med_mid, 0.5),
            "session_median_executable_pct": pct(med_ex, 0.5),
            "best_snapshot_median_executable_pct": round(max(med_ex), 3),
            "session_median_p90_executable_pct": pct(p90_ex, 0.5),
            "session_median_p25_mid_pct": pct([r["mid"]["p25"] for r in rows], 0.5),
            "session_median_p75_mid_pct": pct([r["mid"]["p75"] for r in rows], 0.5),
            "spread_vs_tbill_pp": {
                "mid": round(pct(med_mid, 0.5) - tb, 3),
                "executable": round(pct(med_ex, 0.5) - tb, 3),
                "executable_p90": round(pct(p90_ex, 0.5) - tb, 3),
            },
        }
    return per


def write_md(status, pre, result=None):
    lines = ["# T32 — SPX box-spread lending rate, REGULAR TRADING HOURS (final probe)", "",
             "**Status:** %s  " % status,
             "**Script:** `scripts/trading_bot/t32_box_rth.py` (detached; capture + analysis in one process)  ",
             "**Task:** `T32_spx_box_rth_probe` — third and FINAL probe of the box.", "",
             "## Pre-registered protocol (frozen at launch, before any RTH quote was read)", "",
             "```", __doc__.split("PRE-REGISTERED PROTOCOL")[1].strip(), "```", "",
             "Launch record: " + json.dumps(pre), ""]
    if result:
        tb = result["tbill_3m_pct"]
        lines += ["## Result", "",
                  "T-bill benchmark: **%.2f %%** (%s). Snapshots: %d clean of %d taken, %s -> %s UTC. "
                  "Market open at first snapshot: %s." % (
                      tb, result["tbill_source"], result["n_snapshots_clean"], result["n_snapshots"],
                      result["first_snapshot_utc"], result["last_snapshot_utc"], result["market_open_at_start"]),
                  "", "| expiry | T (y) | snaps | pairs/snap | mid median % | exec median % | exec p90 % | best-snap exec median % | exec − T-bill (pp) | p90 exec − T-bill (pp) |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for e, r in result["per_expiry"].items():
            if r.get("n_snapshots", 0) == 0:
                lines.append("| %s | – | 0 | – | – | – | – | – | – | – |" % e)
                continue
            lines.append("| %s%s | %.3f | %d | %s | %s | %s | %s | %s | %s | %s |" % (
                e, " (primary)" if e == PRIMARY else "", r["years_to_expiry"], r["n_snapshots"],
                r["median_pairs_per_snapshot"], r["session_median_mid_pct"],
                r["session_median_executable_pct"], r["session_median_p90_executable_pct"],
                r["best_snapshot_median_executable_pct"], r["spread_vs_tbill_pp"]["executable"],
                r["spread_vs_tbill_pp"]["executable_p90"]))
        lines += ["", "## Verdict (mechanical, from the frozen rule)", "", "**%s**" % result["verdict"], "",
                  result["verdict_note"], "",
                  "Comparison with T25 (market closed, 2026-08-19): 1y executable +0.06 %% = −3.65 pp vs T-bills; "
                  "mid +0.37 pp over. RTH read on the primary expiry: executable %s pp, mid %s pp." % (
                      result["per_expiry"].get(PRIMARY, {}).get("spread_vs_tbill_pp", {}).get("executable"),
                      result["per_expiry"].get(PRIMARY, {}).get("spread_vs_tbill_pp", {}).get("mid")), ""]
    with open(OUT_MD, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None, help="capture start, ISO UTC e.g. 2026-08-24T13:30:00Z (default: now)")
    ap.add_argument("--duration-min", type=int, default=60)
    ap.add_argument("--interval-min", type=int, default=5)
    ap.add_argument("--preflight-only", action="store_true", help="one snapshot now, no verdict, no md/json overwrite")
    ap.add_argument("--allow-stale", action="store_true", help="preflight only: accept off-day quotes (math check vs T25)")
    args = ap.parse_args()
    os.makedirs(RAW_DIR, exist_ok=True)
    headers = creds()

    if args.preflight_only:
        global ALLOW_STALE
        ALLOW_STALE = bool(args.allow_stale)
        asof = dt.datetime.now(dt.timezone.utc)
        s = snapshot("preflight", headers, asof)
        with open(os.path.join(RAW_DIR, "preflight.json"), "w") as fh:
            json.dump(s, fh, indent=1)
        print(json.dumps({e: {k: v for k, v in r.items() if k in ("strikes_quoted", "strikes_two_sided_fresh",
                          "strikes_stale_quote", "parity_forward", "n_pairs", "mid", "executable")}
                          for e, r in s["expiries"].items()}, indent=1))
        print("clock:", s.get("clock"))
        return 0

    start = (dt.datetime.fromisoformat(args.start.replace("Z", "+00:00")) if args.start
             else dt.datetime.now(dt.timezone.utc))
    pre = {"launched_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "capture_start_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "duration_min": args.duration_min, "interval_min": args.interval_min,
           "expiries": EXPIRIES, "primary": PRIMARY, "band": BAND, "width": WIDTH}
    write_md("CAPTURE PENDING / IN PROGRESS", pre)
    log("launched; waiting for %s" % pre["capture_start_utc"])
    while dt.datetime.now(dt.timezone.utc) < start:
        time.sleep(15)

    snaps = []
    n = args.duration_min // args.interval_min + 1
    for i in range(n):
        asof = dt.datetime.now(dt.timezone.utc)
        s = snapshot("s%02d" % i, headers, asof)
        snaps.append(s)
        p = s["expiries"].get(PRIMARY, {})
        log("snapshot %d/%d: primary pairs=%s exec median=%s mid median=%s open=%s" % (
            i + 1, n, p.get("n_pairs"), (p.get("executable") or {}).get("median"),
            (p.get("mid") or {}).get("median"), (s.get("clock") or {}).get("is_open")))
        with open(os.path.join(RAW_DIR, "snapshots.json"), "w") as fh:
            json.dump(snaps, fh, indent=1)
        if i < n - 1:
            nxt = start + dt.timedelta(minutes=args.interval_min * (i + 1))
            while dt.datetime.now(dt.timezone.utc) < nxt:
                time.sleep(5)

    tb, tb_src = tbill()
    per = aggregate(snaps, tb)
    prim = per.get(PRIMARY, {})
    clean = sum(1 for s in snaps if s["expiries"].get(PRIMARY, {}).get("n_pairs", 0) > 0)
    if prim.get("n_snapshots", 0) == 0:
        verdict = "INCONCLUSIVE — no clean primary-expiry snapshot (capture failure, not a market read)"
        note = "Collector fault; the frozen rule is not triggered by a broken capture. Re-run once; a second capture failure closes the task as blocked."
    elif prim["session_median_executable_pct"] < tb:
        verdict = "BOX PERMANENTLY DEAD — executable four-leg rate below T-bills during RTH (third probe; no fourth)"
        note = ("Primary expiry session-median executable %.3f %% vs T-bill %.2f %% (%.2f pp). "
                "Even the p90 executable pair sits at %.3f %% (%.2f pp vs T-bill). "
                "Mid %.3f %% (%.2f pp). The estimand is a rate level, so power is not the issue." % (
                    prim["session_median_executable_pct"], tb, prim["spread_vs_tbill_pp"]["executable"],
                    prim["session_median_p90_executable_pct"], prim["spread_vs_tbill_pp"]["executable_p90"],
                    prim["session_median_mid_pct"], prim["spread_vs_tbill_pp"]["mid"]))
    else:
        verdict = "BOX CLEARS T-BILLS AT EXECUTABLE — survives the kill-condition (rate level, not a Sharpe)"
        note = ("Primary expiry session-median executable %.3f %% vs T-bill %.2f %% (+%.2f pp). "
                "Next step is a pre-registered DESIGN (size, fill assumption at the touch, margin), not a trade." % (
                    prim["session_median_executable_pct"], tb, prim["spread_vs_tbill_pp"]["executable"]))
    result = {
        "probe": "SPX box spread implied financing rate, REGULAR TRADING HOURS (T32, final)",
        "pre_registration": pre, "tbill_3m_pct": tb, "tbill_source": tb_src,
        "n_snapshots": len(snaps), "n_snapshots_clean": clean,
        "first_snapshot_utc": snaps[0]["taken_utc"], "last_snapshot_utc": snaps[-1]["taken_utc"],
        "market_open_at_start": (snaps[0].get("clock") or {}).get("is_open"),
        "per_expiry": per, "verdict": verdict, "verdict_note": note,
        "raw_dir": os.path.relpath(RAW_DIR, REPO),
        "source": "Alpaca /v1beta1/options/snapshots/SPX latestQuote (default feed), quotes only",
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(result, fh, indent=1)
    write_md("COMPLETE", pre, result)
    log("DONE: %s" % verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
