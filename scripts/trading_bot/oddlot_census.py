#!/usr/bin/env python3
"""ODD-LOT TENDER-OFFER PRIORITY -- census / sizing step.

THESIS
------
In partial or Dutch-auction ISSUER tender offers (SC TO-I), the offeror is
contractually obligated to accept odd-lot holders (<100 shares) IN FULL, exempt
from proration.  When such a tender is oversubscribed at a PREMIUM, a large
holder is pro-rated (cannot fully exit at the tender price) but an odd-lot holder
gets full acceptance.  A retail trader who buys an odd lot in the market DURING
the offer window and tenders it captures (tender_price - market_price) in full.

This edge has a DETERMINISTIC CASH ANCHOR (the tender price is a contractual cash
amount), so it is immune to the async-mark / stale-quote artifact that killed most
of this repo's structural sweep.  The retail-only ceiling (<100 shares) is a
CAPACITY limit, not a validity problem -- so the census asks: is the POPULATION
large enough and PREMIUM-rich enough to bother with a full held-out event study,
or is it too rare / microcap (honest zero)?

WHAT THIS SCRIPT DOES
---------------------
Phase 1  Enumerate SC TO-I filings via EDGAR full-text search (efts.sec.gov) that
         mention odd-lot provisions AND (dutch auction | pro rata | proration).
         2015-01-01 .. today.  Dedupe by accession.  -> fts_hits.jsonl
Phase 2  Group hits by (CIK, tender file-number 005-xxxxx) = one unique OFFER.
         earliest file_date = announcement; latest = last amendment.
Phase 3  For each offer fetch the primary SC TO-I document + the LAST amendment.
         Parse: tender price / Dutch range, shares sought (partial?), expiry,
         odd-lot clause, and (from amendments) oversubscription / proration.
Phase 4  Resolve ticker (CIK->ticker map + display_names).  Look up the
         pre-announcement close and the during-window market price from the
         repo's cached equity daily panel.  Compute offer premium and the
         realized odd-lot capture net of two commissions.
Phase 5  Aggregate: N offers/yr, premium & capture distributions, %% oversubscribed,
         split by SIC (operating co vs closed-end fund), and by DATE into a
         DESIGN window (2015-2021) vs a HELD-OUT window (2022-2026).

Output   research/trading_bot/ODDLOT_CENSUS.json           (summary + per-event)
         research/trading_bot/oddlot_census.log            (progress)
         research/data/oddlot_cache/fts_hits.jsonl         (raw FTS hits)
         research/data/oddlot_cache/docs/<accession>.txt.gz (cached filing text)

RULES honored: free data only; EDGAR rate-limited to ~5 req/s with a contact UA;
memory-frugal (streamed JSONL, gz-cached filings); PAPER/RESEARCH only -- no
orders, no money, no wallet.  Designed to run DETACHED (setsid nohup) because the
crawl exceeds the synchronous request-timeout wall.
"""
import bisect
import gzip
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

import numpy as np

# ----------------------------------------------------------------------------- config
UA = "meme-research officialjoy04@gmail.com"
ROOT = "/home/anont/meme"
CACHE = os.path.join(ROOT, "research/data/oddlot_cache")
DOCS = os.path.join(CACHE, "docs")
OUT_JSON = os.path.join(ROOT, "research/trading_bot/ODDLOT_CENSUS.json")
LOG = os.path.join(ROOT, "research/trading_bot/oddlot_census.log")
PANEL = os.path.join(ROOT, "research/data/xll_cache/eq_daily_panel.npz")

START = "2015-01-01"
END = time.strftime("%Y-%m-%d")
HOLDOUT_FROM = "2022-01-01"          # design < this <= held-out
REQ_SLEEP = 0.20                      # ~5 req/s, well under the 10 req/s ceiling
FTS_PAGE = 100
FTS_MAX = 9000                        # efts hard-caps 'from' near 10000

# Each entry is AND-ed (multiple quoted phrases). We UNION the result sets.
QUERIES = [
    '"odd lot" "dutch auction"',
    '"odd lots" "dutch auction"',
    '"odd lot" "pro rata"',
    '"odd lot" "proration"',
    '"odd lots" "prorated"',
]
FORMS = "SC TO-I"                     # issuer self-tender; root_forms filter also nets /A

COMMISSION_FLAT = 1.00               # $ per side (2 sides = round trip)
COMMISSION_BPS = 5.0                 # bps per side
ODDLOT_SHARES = 99                   # max odd lot -> best-case flat-commission drag
REP_ODDLOT_NOTIONAL = 3000.0         # representative retail odd-lot $ position

# CEF/fund SIC codes -> tenders are NAV-discount plays, not premium-to-market; split out.
FUND_SICS = {"6726", "6221", "6199", "6770"}

os.makedirs(DOCS, exist_ok=True)


def log(msg):
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


# ----------------------------------------------------------------------------- http
_last = [0.0]


def _throttle():
    dt = time.time() - _last[0]
    if dt < REQ_SLEEP:
        time.sleep(REQ_SLEEP - dt)
    _last[0] = time.time()


def http_get(url, tries=5, raw=False):
    for i in range(tries):
        _throttle()
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
            with urllib.request.urlopen(req, timeout=45) as r:
                body = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                    body = gzip.decompress(body)
                return body if raw else body.decode("utf-8", "replace")
        except Exception as e:
            code = getattr(e, "code", None)
            if code == 404:
                return None
            if i == tries - 1:
                log("FAIL %s :: %s" % (url[:120], e))
                return None
            time.sleep(1.5 * (i + 1) + (2.0 if code in (429, 500, 503) else 0.0))
    return None


def fts(q, frm, start, end, page_from):
    params = urllib.parse.urlencode(
        {"q": q, "forms": frm, "startdt": start, "enddt": end, "from": page_from})
    url = "https://efts.sec.gov/LATEST/search-index?" + params
    txt = http_get(url)
    if txt is None:
        return None
    try:
        return json.loads(txt)
    except Exception:
        return None


# ----------------------------------------------------------------------------- phase 1
def phase1_enumerate():
    """Union all queries, dedupe by accession -> fts_hits.jsonl. Resumable-ish."""
    hits_path = os.path.join(CACHE, "fts_hits.jsonl")
    seen = set()
    n_written = 0
    with open(hits_path, "w") as out:
        for q in QUERIES:
            frm = 0
            total = None
            got = 0
            while True:
                d = fts(q, FORMS, START, END, frm)
                if d is None:
                    log("phase1 query=%r from=%d -> NULL, stop this query" % (q, frm))
                    break
                if total is None:
                    total = d.get("hits", {}).get("total", {}).get("value", 0)
                    log("phase1 query=%r total=%d" % (q, total))
                page = d.get("hits", {}).get("hits", [])
                if not page:
                    break
                for h in page:
                    adsh = (h.get("_source", {}).get("adsh")
                            or (h.get("_id", "").split(":")[0]))
                    key = (adsh, h.get("_id"))
                    if key in seen:
                        continue
                    seen.add(key)
                    s = h.get("_source", {})
                    rec = {
                        "id": h.get("_id"),
                        "adsh": adsh,
                        "ciks": s.get("ciks"),
                        "file_num": s.get("file_num"),
                        "file_date": s.get("file_date"),
                        "file_type": s.get("file_type"),
                        "root_forms": s.get("root_forms"),
                        "display_names": s.get("display_names"),
                        "sics": s.get("sics"),
                        "biz_states": s.get("biz_states"),
                        "matched_q": q,
                    }
                    out.write(json.dumps(rec) + "\n")
                    n_written += 1
                got += len(page)
                frm += FTS_PAGE
                if frm >= min(total or 0, FTS_MAX) or got >= (total or 0):
                    break
    log("phase1 DONE unique_docs=%d -> %s" % (n_written, hits_path))
    _snapshot({"phase": 1, "unique_fts_docs": n_written})
    return hits_path


# ----------------------------------------------------------------------------- phase 2
def phase2_group(hits_path):
    """Group docs into unique offers by (primary CIK, tender file-number)."""
    offers = {}
    with open(hits_path) as fh:
        for line in fh:
            r = json.loads(line)
            ciks = r.get("ciks") or []
            fnums = r.get("file_num") or []
            cik = ciks[0] if ciks else None
            # tender file numbers look like 005-XXXXX
            fnum = next((f for f in fnums if isinstance(f, str) and f.startswith("005-")),
                        (fnums[0] if fnums else None))
            if cik is None:
                continue
            key = "%s|%s" % (cik, fnum)
            o = offers.setdefault(key, {
                "cik": cik, "file_num": fnum, "display_names": r.get("display_names"),
                "sics": r.get("sics"), "biz_states": r.get("biz_states"),
                "docs": [], "matched_q": set()})
            o["docs"].append({"id": r["id"], "date": r["file_date"], "type": r["file_type"]})
            o["matched_q"].add(r.get("matched_q"))
    for o in offers.values():
        o["matched_q"] = sorted(x for x in o["matched_q"] if x)
        o["docs"].sort(key=lambda d: (d["date"] or "", d["id"]))
        o["announce_date"] = o["docs"][0]["date"]
        o["last_date"] = o["docs"][-1]["date"]
    log("phase2 DONE unique_offers=%d" % len(offers))
    _snapshot({"phase": 2, "unique_offers": len(offers)})
    return offers


# ----------------------------------------------------------------------------- filing text
def doc_url(doc_id, cik):
    adsh, _, fname = doc_id.partition(":")
    nodash = adsh.replace("-", "")
    cik_int = int(cik)
    if not fname:
        fname = adsh + ".txt"
    return "https://www.sec.gov/Archives/edgar/data/%d/%s/%s" % (cik_int, nodash, fname)


TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def fetch_text(doc_id, cik):
    adsh = doc_id.split(":")[0]
    safe = adsh + "__" + re.sub(r"[^A-Za-z0-9._-]", "_", doc_id.split(":", 1)[-1])[:60]
    cpath = os.path.join(DOCS, safe + ".txt.gz")
    if os.path.exists(cpath):
        with gzip.open(cpath, "rt", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    html = http_get(doc_url(doc_id, cik))
    if html is None:
        return None
    text = TAG.sub(" ", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&#146;", "'").replace("&#147;", '"').replace("&#148;", '"')
                .replace("&#151;", "-").replace("&rsquo;", "'").replace("&mdash;", "-"))
    text = WS.sub(" ", text)
    with gzip.open(cpath, "wt", encoding="utf-8") as fh:
        fh.write(text)
    return text


# ----------------------------------------------------------------------------- parsing
RANGE_RE = re.compile(
    r"(?:between|from)\s*\$?\s*(\d{1,3}(?:\.\d{1,2})?)\s*(?:and|to|-|through)\s*\$?\s*(\d{1,3}(?:\.\d{1,2})?)\s*(?:per\s+share|a\s+share|net)?",
    re.I)
NOTGREATER_RE = re.compile(
    r"not\s+(?:greater|more)\s+than\s*\$?\s*(\d{1,3}(?:\.\d{1,2})?)\D{0,80}?not\s+less\s+than\s*\$?\s*(\d{1,3}(?:\.\d{1,2})?)",
    re.I)
PRICE_RE = re.compile(
    r"(?:purchase\s+price\s+of|price\s+of|at\s+a\s+price\s+of|for)\s*\$\s*(\d{1,3}(?:\.\d{1,2})?)\s*(?:net\s+)?(?:in\s+cash\s+)?per\s+share",
    re.I)
SHARES_RE = re.compile(
    r"up\s+to\s*(?:an\s+aggregate\s+of\s*)?([\d,]{4,15})\s*(?:of\s+its\s+)?(?:issued\s+and\s+outstanding\s+)?shares",
    re.I)
MONTHS = ("January|February|March|April|May|June|July|August|September|October|"
          "November|December")
EXPIRE_RE = re.compile(
    r"expir\w+[^.]{0,120}?((?:%s)\s+\d{1,2},?\s+20\d\d)" % MONTHS, re.I)
OVERSUB_RE = re.compile(r"oversubscrib|over-subscrib|proration\s+factor|were\s+prorated"
                        r"|shares\s+were\s+prorated|preliminary\s+proration", re.I)
DUTCH_RE = re.compile(r"dutch\s+auction", re.I)
ODDLOT_RE = re.compile(r"odd\s+lot", re.I)


def _f(x):
    try:
        return float(x)
    except Exception:
        return None


def parse_primary(text):
    """Extract price / dutch range / shares sought / expiry / flags from primary doc."""
    out = {"dutch": bool(DUTCH_RE.search(text)),
           "odd_lot": bool(ODDLOT_RE.search(text)),
           "price": None, "range_lo": None, "range_hi": None,
           "shares_sought": None, "expiry": None}
    m = NOTGREATER_RE.search(text) or RANGE_RE.search(text)
    if m:
        lo, hi = sorted([_f(m.group(2)), _f(m.group(1))]
                        if NOTGREATER_RE.search(text) else [_f(m.group(1)), _f(m.group(2))])
        # sanity: plausible per-share range
        if lo and hi and 0.5 <= lo <= hi <= 999 and hi / lo <= 3.0:
            out["range_lo"], out["range_hi"] = lo, hi
    mp = PRICE_RE.search(text)
    if mp:
        p = _f(mp.group(1))
        if p and 0.5 <= p <= 999:
            out["price"] = p
    ms = SHARES_RE.search(text)
    if ms:
        try:
            out["shares_sought"] = int(ms.group(1).replace(",", ""))
        except Exception:
            pass
    me = EXPIRE_RE.search(text)
    if me:
        out["expiry"] = me.group(1)
    return out


# ----------------------------------------------------------------------------- price panel
class Panel:
    def __init__(self, path):
        d = np.load(path, allow_pickle=True)
        self.sym = {s: i for i, s in enumerate(d["symbols"])}
        self.dates = list(d["dates"])
        self.close = d["close"]
        self.first = self.dates[0]
        self.last = self.dates[-1]

    def idx_before(self, date):
        i = bisect.bisect_left(self.dates, date)  # first index >= date
        return i - 1  # last trading day strictly before `date`

    def pre_price(self, ticker, ann_date, back=1):
        j = self.sym.get(ticker)
        if j is None:
            return None
        i = self.idx_before(ann_date)
        i -= (back - 1)
        if i < 0 or i >= len(self.dates):
            return None
        v = float(self.close[j, i])
        return v if v == v and v > 0 else None

    def window(self, ticker, ann_date, fwd=5, span=40):
        """market price ~`fwd` trading days after announce; and min close over span."""
        j = self.sym.get(ticker)
        if j is None:
            return None, None
        i0 = self.idx_before(ann_date) + 1  # first trading day on/after announce
        k = i0 + fwd
        mkt = None
        if 0 <= k < len(self.dates):
            v = float(self.close[j, k])
            mkt = v if v == v and v > 0 else None
        lo = None
        a, b = max(0, i0), min(len(self.dates), i0 + span)
        seg = self.close[j, a:b]
        seg = seg[(seg == seg) & (seg > 0)]
        if seg.size:
            lo = float(seg.min())
        return mkt, lo


# ----------------------------------------------------------------------------- ticker map
def build_cik_ticker():
    ct = http_get("https://www.sec.gov/files/company_tickers.json")
    m = {}
    if ct:
        try:
            for v in json.loads(ct).values():
                m[int(v["cik_str"])] = v["ticker"].upper()
        except Exception:
            pass
    return m


NAME_TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)")


def resolve_ticker(display_names, cik, cik_map, panel):
    t = cik_map.get(int(cik))
    if t and t in panel.sym:
        return t
    for dn in (display_names or []):
        for cand in NAME_TICKER_RE.findall(dn):
            if cand in panel.sym and cand not in ("CIK",):
                return cand
    if t:
        return t  # known ticker but no panel coverage (delisted / no price)
    return None


# ----------------------------------------------------------------------------- phase 3+4
def phase34(offers, panel, cik_map):
    events = []
    keys = list(offers.keys())
    n = len(keys)
    for idx, key in enumerate(keys):
        o = offers[key]
        primary = next((d for d in o["docs"] if d["type"] == "SC TO-I"), o["docs"][0])
        last_amend = o["docs"][-1]
        ptext = fetch_text(primary["id"], o["cik"])
        parsed = parse_primary(ptext) if ptext else {}
        oversub = False
        if last_amend["id"] != primary["id"]:
            atext = fetch_text(last_amend["id"], o["cik"])
            if atext and OVERSUB_RE.search(atext):
                oversub = True
        if ptext and OVERSUB_RE.search(ptext):
            oversub = True

        tender_price = None
        if parsed.get("range_hi"):
            tender_price = parsed["range_hi"]          # Dutch: upper bound = max payable
        elif parsed.get("price"):
            tender_price = parsed["price"]

        ticker = resolve_ticker(o["display_names"], o["cik"], cik_map, panel)
        ann = o["announce_date"]
        pre = panel.pre_price(ticker, ann, back=1) if ticker else None
        pre5 = panel.pre_price(ticker, ann, back=5) if ticker else None
        mkt, wlo = panel.window(ticker, ann) if ticker else (None, None)
        pre_ref = pre or pre5

        premium = capture = capture_lo = None
        if tender_price and pre_ref:
            premium = tender_price / pre_ref - 1.0
        # realized odd-lot capture: buy in market during window, tender for full price
        entry = mkt or pre_ref
        if tender_price and entry:
            capture = tender_price / entry - 1.0
        if tender_price and wlo:
            capture_lo = tender_price / wlo - 1.0     # best-case entry at window low

        sic = (o["sics"] or [None])[0]
        events.append({
            "key": key, "cik": o["cik"], "file_num": o["file_num"],
            "ticker": ticker, "display": (o["display_names"] or [None])[0],
            "sic": sic, "is_fund": sic in FUND_SICS,
            "announce_date": ann, "last_date": o["last_date"],
            "matched_q": o["matched_q"], "n_docs": len(o["docs"]),
            "dutch": parsed.get("dutch"), "odd_lot": parsed.get("odd_lot"),
            "price": parsed.get("price"), "range_lo": parsed.get("range_lo"),
            "range_hi": parsed.get("range_hi"), "shares_sought": parsed.get("shares_sought"),
            "expiry": parsed.get("expiry"), "oversubscribed": oversub,
            "tender_price": tender_price,
            "pre_price": pre, "pre5_price": pre5, "mkt_window_price": mkt,
            "window_low": wlo,
            "premium_vs_pre": premium,
            "capture_vs_window": capture, "capture_vs_window_low": capture_lo,
            "primary_url": doc_url(primary["id"], o["cik"]),
        })
        if (idx + 1) % 20 == 0:
            log("phase3/4 %d/%d parsed (last ticker=%s price=%s)"
                % (idx + 1, n, ticker, tender_price))
            _snapshot({"phase": 3, "parsed": idx + 1, "total": n})
    log("phase3/4 DONE events=%d" % len(events))
    return events


# ----------------------------------------------------------------------------- aggregate
def _net(gross, entry_price):
    """net-of-2-commissions in fraction, two commission models."""
    if gross is None:
        return None, None
    flat = 2 * COMMISSION_FLAT / REP_ODDLOT_NOTIONAL          # $ model on rep notional
    bps = 2 * COMMISSION_BPS / 1e4
    return gross - flat, gross - bps


def _stats(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0}
    a = np.array(xs, float)
    return {"n": len(xs), "mean": float(a.mean()), "median": float(np.median(a)),
            "p25": float(np.percentile(a, 25)), "p75": float(np.percentile(a, 75)),
            "min": float(a.min()), "max": float(a.max()),
            "frac_positive": float((a > 0).mean())}


def phase5_aggregate(events):
    def bucket(evs, label):
        priced = [e for e in evs if e["tender_price"] and e["pre_price"] or
                  (e["tender_price"] and e["pre5_price"])]
        oversub = [e for e in priced if e["oversubscribed"]]
        prem_oversub = [e["premium_vs_pre"] for e in oversub]
        cap_oversub = [e["capture_vs_window"] for e in oversub]
        cap_lo_oversub = [e["capture_vs_window_low"] for e in oversub]
        # net-of-cost capture (bps model) for oversubscribed premium tenders
        net_bps = []
        net_flat = []
        for e in oversub:
            if e["capture_vs_window"] is not None:
                nf, nb = _net(e["capture_vs_window"], e["mkt_window_price"])
                net_flat.append(nf)
                net_bps.append(nb)
        return {
            "label": label,
            "n_offers": len(evs),
            "n_priced": len(priced),
            "n_dutch": sum(1 for e in evs if e["dutch"]),
            "n_oversubscribed": len(oversub),
            "n_oversub_premium_positive": sum(
                1 for e in oversub if (e["premium_vs_pre"] or -1) > 0),
            "premium_vs_pre_stats": _stats(prem_oversub),
            "capture_vs_window_stats": _stats(cap_oversub),
            "capture_vs_window_low_stats": _stats(cap_lo_oversub),
            "capture_net_bps_stats": _stats(net_bps),
            "capture_net_flat_stats": _stats(net_flat),
        }

    oper = [e for e in events if not e["is_fund"]]
    fund = [e for e in events if e["is_fund"]]
    design = [e for e in oper if (e["announce_date"] or "") < HOLDOUT_FROM]
    holdout = [e for e in oper if (e["announce_date"] or "") >= HOLDOUT_FROM]

    by_year = defaultdict(int)
    by_year_oversub = defaultdict(int)
    for e in oper:
        y = (e["announce_date"] or "?")[:4]
        by_year[y] += 1
        if e["oversubscribed"]:
            by_year_oversub[y] += 1

    summary = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "universe": {"start": START, "end": END, "forms": FORMS, "queries": QUERIES},
        "commissions": {"flat_per_side_usd": COMMISSION_FLAT,
                        "bps_per_side": COMMISSION_BPS,
                        "rep_oddlot_notional_usd": REP_ODDLOT_NOTIONAL,
                        "oddlot_shares": ODDLOT_SHARES},
        "counts": {
            "total_offers": len(events),
            "operating_company_offers": len(oper),
            "closedend_fund_offers": len(fund),
            "operating_dutch": sum(1 for e in oper if e["dutch"]),
            "operating_oversubscribed": sum(1 for e in oper if e["oversubscribed"]),
        },
        "operating_offers_per_year": dict(sorted(by_year.items())),
        "operating_oversub_per_year": dict(sorted(by_year_oversub.items())),
        "ALL_operating": bucket(oper, "all_operating_2015_2026"),
        "DESIGN_2015_2021": bucket(design, "design_2015_2021"),
        "HELDOUT_2022_2026": bucket(holdout, "heldout_2022_2026"),
        "FUNDS_reference": bucket(fund, "closedend_funds_reference"),
    }
    return summary


# ----------------------------------------------------------------------------- io
def _snapshot(progress):
    payload = {"status": "running", "progress": progress,
               "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    tmp = OUT_JSON + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, OUT_JSON)


def write_final(summary, events):
    payload = {"status": "complete", "summary": summary,
               "events": sorted(events, key=lambda e: (e["announce_date"] or ""))}
    tmp = OUT_JSON + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    os.replace(tmp, OUT_JSON)
    log("WROTE %s (events=%d)" % (OUT_JSON, len(events)))


# ----------------------------------------------------------------------------- main
def main():
    t0 = time.time()
    log("=== ODD-LOT TENDER CENSUS start (%s .. %s) ===" % (START, END))
    hits_path = phase1_enumerate()
    offers = phase2_group(hits_path)
    log("loading price panel + cik->ticker map ...")
    panel = Panel(PANEL)
    cik_map = build_cik_ticker()
    events = phase34(offers, panel, cik_map)
    summary = phase5_aggregate(events)
    write_final(summary, events)
    # human-readable tail in the log
    c = summary["counts"]
    log("SUMMARY operating=%d dutch=%d oversubscribed=%d funds=%d"
        % (c["operating_company_offers"], c["operating_dutch"],
           c["operating_oversubscribed"], c["closedend_fund_offers"]))
    ao = summary["ALL_operating"]
    log("SUMMARY oversub premium %s" % json.dumps(ao["premium_vs_pre_stats"]))
    log("SUMMARY oversub capture-vs-window net(bps) %s"
        % json.dumps(ao["capture_net_bps_stats"]))
    log("=== DONE in %.0fs ===" % (time.time() - t0))


if __name__ == "__main__":
    main()
