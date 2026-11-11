#!/usr/bin/env python3
"""FACTORY v2 runner (conductor-owned). Implements research/factory/PREREGISTRATION_v2.md — nothing else.

Stages, in the only order the pre-registration allows:

    pin        write PREREG_PIN_v2.json (prereg + data manifests + rule grid + library code + venues.json)
    tier2      design-window screen of every enabled formula of one lane (sealed panel: no row after
               design_end ever reaches a rule); every formula is ledgered, winners and losers alike
    mtest      Benjamini-Hochberg (pooled), Romano-Wolf StepM / SPA / PBO per block
    freeze     SURVIVORS_FROZEN.json — one shot; tier1 and holdout refuse to run before it exists
    tier1      the 16 primary ensembles (speed limit -> ensemble -> transforms -> drift-aware account)
    holdout    the frozen Tier-2 survivors on the sealed holdout, once
    report     markdown reports under research/factory/reports/v2/

Every stage first re-checks the pins and refuses on any mismatch. `--synthetic` swaps the real panels
for the strategy library's seeded synthetic panels and writes to a scratch directory: it is how the
whole pipeline was smoke-tested BEFORE the freeze, without a single real-data result.

    cd /home/anont/meme && research/factory/.venv/bin/python -m scripts.factory.v2 tier2 --lane FX
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sys
import time
import traceback
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.factory import audit, engine, mtest, portfolio, realism, stats  # noqa: E402
from scripts.factory.panel import PanelBundle  # noqa: E402
from scripts.factory.strategies import registry  # noqa: E402
from scripts.factory.strategies.common import size_positions  # noqa: E402

FACT = ROOT / "research" / "factory"
PREREG = FACT / "PREREGISTRATION_v2.md"
DESIGN = FACT / "DESIGN_v2.md"
PIN = FACT / "PREREG_PIN_v2.json"
VENUES = FACT / "landscape" / "venues.json"
SEED = 20261110
SPEED_LIMIT_SR = 0.13
BUFFER = 0.10


class Refused(RuntimeError):
    """A pre-registered precondition is not met; the stage does not run."""


# ==================================================================================================
# Configuration — a transcription of PREREGISTRATION_v2 §2/§3. Nothing here is tuned.
# ==================================================================================================
MAJORS = ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]
SCANDI = ["SEK", "NOK"]
EMS = ["MXN", "ZAR", "PLN", "HUF", "CZK", "ILS"]


@dataclass(frozen=True)
class LaneCfg:
    ppy: int
    sigma: float
    design: Tuple[str, Optional[str]]
    holdout: Tuple[str, Optional[str]]
    full: Tuple[str, Optional[str]]
    postpub: Tuple[str, Optional[str]]
    exec_prints: bool
    missing: str
    long_only: bool
    max_gross: float


LANES: Dict[str, LaneCfg] = {
    "FX": LaneCfg(252, 0.10, ("2000-01-03", "2016-12-30"), ("2017-01-02", None), ("2000-01-03", None),
                  ("2013-01-01", None), False, "refuse", False, 10.0),
    "MACRO": LaneCfg(252, 0.10, ("2017-01-03", "2021-12-31"), ("2022-01-03", None), ("2017-01-03", None),
                     ("2017-01-03", None), False, "refuse", False, 4.0),
    "CRYPTO-PERP": LaneCfg(365, 0.20, ("2020-07-01", "2023-12-31"), ("2024-01-01", None), ("2020-07-01", None),
                           ("2021-01-01", None), True, "zero", False, 2.0),
    "CRYPTO-SPOT": LaneCfg(365, 0.20, ("2018-08-01", "2023-12-31"), ("2024-01-01", None), ("2018-08-01", None),
                           ("2021-01-01", None), True, "zero", True, 1.0),
}
TIER2_FAMILIES = {"CRYPTO-SPOT": ("TREND", "XSMOM")}          # prereg §5
ML_ONLY_ON = ("FX", "G10")                                     # prereg §5

# (cost bp per side, holding cost bp per year on long AND short notional); FX values are per group.
_FX = lambda maj, sca, em: {"MAJ": maj, "SCA": sca, "EM": em}  # noqa: E731
COSTS = {
    # Tier-1 scenarios (prereg §3 table)
    ("FX", "t1"): {"base": (_FX(0.6, 2.5, 6.0), _FX(100, 100, 250)),
                   "stress": (_FX(1.5, 5.0, 15.0), _FX(200, 200, 400)),
                   "ref": (_FX(0.75, 2.5, 6.0), _FX(0, 0, 0))},
    ("MACRO", "t1"): {"base": (1.0, 250.0), "stress": (2.5, 300.0), "ref": (1.0, 0.0)},
    ("MACRO", "t1_lo"): {"base": (5.0, 0.0), "stress": (15.0, 0.0), "ref": (5.0, 0.0)},
    ("CRYPTO-PERP", "t1"): {"base": (7.0, 0.0), "stress": (15.0, 0.0), "ref": (4.0, 0.0)},
    ("CRYPTO-SPOT", "t1"): {"base": (27.0, 0.0), "stress": (50.0, 0.0), "ref": (17.0, 0.0)},
    # Tier-2 screen (prereg §5): FX and MACRO are screened at the reference (futures-like) cost so a
    # wrapper's financing does not hide a signal; "retail" tags whether a formula also survives the wrapper.
    ("FX", "t2"): {"base": (_FX(0.75, 2.5, 6.0), _FX(0, 0, 0)), "stress": (_FX(1.5, 5.0, 15.0), _FX(0, 0, 0)),
                   "retail": (_FX(0.6, 2.5, 6.0), _FX(100, 100, 250))},
    ("MACRO", "t2"): {"base": (1.0, 0.0), "stress": (2.5, 0.0), "retail": (1.0, 250.0)},
    ("CRYPTO-PERP", "t2"): {"base": (7.0, 0.0), "stress": (15.0, 0.0), "retail": (7.0, 0.0)},
    ("CRYPTO-SPOT", "t2"): {"base": (27.0, 0.0), "stress": (50.0, 0.0), "retail": (27.0, 0.0)},
}


_SYNTHETIC_FX_FALLBACK = False


def _fx_group(ccy: str) -> str:
    if ccy in MAJORS:
        return "MAJ"
    if ccy in SCANDI:
        return "SCA"
    if ccy in EMS:
        return "EM"
    if _SYNTHETIC_FX_FALLBACK:        # the synthetic smoke-test panel carries SGD; real panels never reach this
        return "EM"
    raise Refused(f"no FX cost group for {ccy!r} (prereg §3 lists G10 and six EM currencies)")


def cost_series(spec, columns) -> Tuple[pd.Series, pd.Series]:
    """(cost bp per side, hold cost bp per year) as per-instrument Series."""
    c, h = spec
    cols = list(columns)
    if isinstance(c, dict):
        return (pd.Series({k: float(c[_fx_group(k)]) for k in cols}),
                pd.Series({k: float(h[_fx_group(k)]) for k in cols}))
    return pd.Series(float(c), index=cols), pd.Series(float(h), index=cols)


# ==================================================================================================
# Context: real panels or the synthetic smoke-test panels
# ==================================================================================================
class Ctx:
    def __init__(self, synthetic: bool, out: Optional[str] = None):
        self.synthetic = synthetic
        if synthetic:
            global _SYNTHETIC_FX_FALLBACK
            _SYNTHETIC_FX_FALLBACK = True
        self.run = pathlib.Path(out) if out else FACT / "runs" / "v2"
        self.rep = (pathlib.Path(out) / "reports") if out else FACT / "reports" / "v2"
        self.run.mkdir(parents=True, exist_ok=True)
        self.rep.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, PanelBundle] = {}
        self._cfg: Dict[str, LaneCfg] = {}

    def panel(self, lane: str) -> PanelBundle:
        if lane not in self._cache:
            if self.synthetic:
                from scripts.factory.tests import test_strategies_synth as synth
                pb = synth.lane_panel(lane, seed=7)
                if LANES.get(lane) and LANES[lane].exec_prints and "exec_prices" not in pb.aux:
                    # the synthetic crypto panels have no execution prints: fabricate two noisy later prints
                    g = np.random.default_rng(11)
                    aux = dict(pb.aux)
                    aux["exec_prices"] = pb.prices * (1.0 + 0.002 * g.standard_normal(pb.prices.shape))
                    aux["exec_prices_alt"] = pb.prices * (1.0 + 0.003 * g.standard_normal(pb.prices.shape))
                    meta = dict(pb.meta, exec_prices_strictly_after_decision=True)
                    pb = PanelBundle(lane=pb.lane, prices=pb.prices, carry=pb.carry, aux=aux, tbill=pb.tbill, meta=meta)
                self._cache[lane] = pb
            else:
                from scripts.factory.data import load_lane
                self._cache[lane] = load_lane(lane)
        return self._cache[lane]

    def cfg(self, lane: str) -> LaneCfg:
        if lane in self._cfg:
            return self._cfg[lane]
        base = LANES[lane]
        if not self.synthetic:
            self._cfg[lane] = base
            return base
        idx = self.panel(lane).prices.index          # synthetic panels have their own dates
        n = len(idx)
        d = lambda i: str(idx[min(max(i, 0), n - 1)].date())  # noqa: E731
        a, b, c = int(0.20 * n), int(0.62 * n), int(0.62 * n) + 1
        self._cfg[lane] = LaneCfg(base.ppy, base.sigma, (d(a), d(b)), (d(c), None), (d(a), None),
                                  (d(int(0.45 * n)), None), base.exec_prints, "zero", base.long_only,
                                  base.max_gross)          # synthetic panels carry deliberate price gaps
        return self._cfg[lane]

    def universes(self, lane: str, panel: PanelBundle) -> Dict[str, List[str]]:
        if lane.startswith("FX"):
            u = registry.fx_universes(panel)
            return {k: v for k, v in u.items() if k in registry.LANE_UNIVERSES.get(lane, ("G10",))}
        return {"ALL": list(panel.prices.columns)}


def sha256_file(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


LIB_FILES = ["panel.py", "engine.py", "stats.py", "mtest.py", "audit.py", "portfolio.py", "realism.py"]


def current_pins() -> dict:
    from scripts.factory.data import LANES as DATA_LANES
    data = {}
    for lane in DATA_LANES:
        m = FACT / "data" / lane / "manifest.json"
        data[lane] = sha256_file(m) if m.exists() else None
    return {
        "preregistration_sha256": sha256_file(PREREG),
        "design_sha256": sha256_file(DESIGN),
        "venues_sha256": sha256_file(VENUES),
        "grid_sha256_with_sources": registry.grid_sha256(),
        "grid_sha256_declaration": registry.grid_sha256(include_sources=False),
        "data_manifest_sha256": data,
        "library_sha256": {f: sha256_file(ROOT / "scripts" / "factory" / f) for f in LIB_FILES},
    }


def check_pins(ctx: Ctx) -> str:
    if ctx.synthetic:
        return "SYNTHETIC"
    if not PIN.exists():
        raise Refused("PREREG_PIN_v2.json does not exist — run `pin` (the freeze) before any real-data stage")
    pin = json.loads(PIN.read_text())
    cur = current_pins()
    bad = [k for k in ("preregistration_sha256", "venues_sha256", "grid_sha256_with_sources",
                       "data_manifest_sha256", "library_sha256") if pin.get(k) != cur[k]]
    if bad:
        raise Refused(f"pinned objects changed since the freeze: {bad}. A frozen run does not continue on "
                      f"edited rules, data or code; record the change in DECISIONS.md and re-freeze as v3.")
    return pin["preregistration_sha256"]


# ==================================================================================================
# Shared helpers
# ==================================================================================================
def eng_kwargs(panel: PanelBundle, cfg: LaneCfg, later: bool = False) -> dict:
    if cfg.exec_prints:
        key = "exec_prices_alt" if later else "exec_prices"
        if key not in panel.aux:
            raise Refused(f"lane needs aux[{key!r}]")
        return dict(exec_prices=panel.aux[key], extra_lag=0, missing_return=cfg.missing)
    return dict(lag=2 if later else 1, missing_return=cfg.missing)


def jsonable(v):
    if v is None:
        return None
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def read_jsonl(p: pathlib.Path) -> List[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def append_jsonl(p: pathlib.Path, row: dict) -> None:
    with p.open("a") as f:
        f.write(json.dumps(jsonable(row), default=str) + "\n")


def basket_weights(panel: PanelBundle, sigma: float) -> pd.DataFrame:
    """The lane's equal-weight long basket in the factory's own sizing (inverse vol, eligible only)."""
    ones = pd.DataFrame(1.0, index=panel.prices.index, columns=panel.prices.columns)
    return size_positions(ones, panel, sigma)


def active_subset(panel: PanelBundle, w: pd.DataFrame) -> Tuple[PanelBundle, pd.DataFrame]:
    """Drop instruments the book never holds (crypto panels carry ~700 columns, most never eligible)."""
    keep = [c for c in w.columns if bool((w[c].fillna(0.0) != 0.0).any())]
    if not keep:
        keep = list(w.columns[:1])
    return panel.subset(keep), w[keep]


def probe_rows(panel: PanelBundle, start: str, qs=(0.4, 0.6, 0.9)) -> List[int]:
    idx = panel.prices.index
    i0 = int(np.searchsorted(idx.values, pd.Timestamp(start, tz="UTC").to_datetime64()))
    n = len(idx)
    return sorted({min(max(i0 + int((n - 1 - i0) * q), 1), n - 2) for q in qs})


# ==================================================================================================
# TIER 2 — the design-window screen
# ==================================================================================================
def tier2_lane(ctx: Ctx, lane: str, ml: bool, n_null: int) -> None:
    sha = check_pins(ctx)
    cfg = ctx.cfg(lane)
    full = ctx.panel(lane)
    sealed = full.window(None, cfg.design[1])                # SEAL: no row after design_end reaches a rule
    ledger = ctx.run / "tier2_design_ledger.jsonl"
    done = {r["formula_id"] for r in read_jsonl(ledger) if r.get("prereg_sha256") == sha}
    netdir = ctx.run / "tier2_net"
    netdir.mkdir(exist_ok=True)
    rng = np.random.default_rng(SEED)
    spec = COSTS[(lane, "t2")]
    print(f"[tier2 {lane}] sealed panel {sealed.prices.shape}, last row {sealed.prices.index[-1]}", flush=True)

    for uname, cols in ctx.universes(lane, sealed).items():
        sub = sealed.subset(cols)
        fams = TIER2_FAMILIES.get(lane)
        rules = registry.rules(lane, sub, families=fams)
        if ml:
            rules = [r for r in rules if r.family == "ML"] if (lane, uname) == ML_ONLY_ON else []
        else:
            rules = [r for r in rules if r.family != "ML"]
        if not rules:
            continue
        c_b, h_b = cost_series(spec["base"], sub.prices.columns)
        c_s, h_s = cost_series(spec["stress"], sub.prices.columns)
        c_r, h_r = cost_series(spec["retail"], sub.prices.columns)
        kw, kw_later = eng_kwargs(sub, cfg), eng_kwargs(sub, cfg, later=True)
        wb = basket_weights(sub, cfg.sigma)
        bench = engine.backtest(sub, wb, cost_bp_side=c_b, hold_cost_long_bp_year=h_b, hold_cost_short_bp_year=h_b, **kw).net
        nets: Dict[str, pd.Series] = {}
        w_by_id: Dict[str, pd.DataFrame] = {}
        probes = probe_rows(sub, cfg.design[0])
        for rule in rules:
            fid = f"{lane}|{uname}|{rule.id}"
            if fid in done:
                print(f"  skip (ledgered) {fid}", flush=True)
                continue
            t0 = time.time()
            row = {"formula_id": fid, "lane": lane, "universe": uname, "rule_id": rule.id, "family": rule.family,
                   "kind": rule.kind, "tier": rule.tier, "params": rule.params, "prereg_sha256": sha}
            try:
                w = size_positions(rule.signal(sub), sub, cfg.sigma)
                if cfg.long_only:
                    w = w.clip(lower=0.0)
                if rule.family == "ML":                       # prereg §3: one probe for ML (slow fits)
                    ar = audit.future_scramble_audit(rule.fn, sub, rule.params, probes[1:2], rng,
                                                     truncation_probe=False, antithetic=False, determinism_check=False)
                else:
                    ar = audit.future_scramble_audit(rule.fn, sub, rule.params, probes, rng)
                rb = engine.backtest(sub, w, cost_bp_side=c_b, hold_cost_long_bp_year=h_b, hold_cost_short_bp_year=h_b, **kw)
                rs = engine.backtest(sub, w, cost_bp_side=c_s, hold_cost_long_bp_year=h_s, hold_cost_short_bp_year=h_s, **kw)
                rr = engine.backtest(sub, w, cost_bp_side=c_r, hold_cost_long_bp_year=h_r, hold_cost_short_bp_year=h_r, **kw)
                rl = engine.backtest(sub, w, cost_bp_side=c_b, hold_cost_long_bp_year=h_b, hold_cost_short_bp_year=h_b, **kw_later)
                st = stats.summarize(rb.net, periods_per_year=cfg.ppy, window=cfg.design, gross=rb.gross,
                                     turnover=rb.turnover, gross_leverage=rb.gross_leverage, benchmark=bench)
                ss = stats.summarize(rs.net, periods_per_year=cfg.ppy, window=cfg.design)
                sr = stats.summarize(rr.net, periods_per_year=cfg.ppy, window=cfg.design)
                ls = audit.lag_sensitivity(rb.net, rl.net, cfg.ppy, window=cfg.design)
                row.update({f"d_{k}": v for k, v in st.items()})
                row.update({"stress_sharpe": ss["sharpe"], "retail_sharpe": sr["sharpe"],
                            "later_sharpe": ls["sharpe_b"], "print_proximity": bool(ls["flag"]),
                            "audit_pass": bool(ar.passed), "audit_detail": str(ar.detail)[:240],
                            "turnover_model": rb.meta.get("turnover_model"),
                            "n_missing_zeroed": rb.meta.get("n_missing_return_held")})
                m = stats.window_mask(rb.net.index, cfg.design)
                nets[fid] = rb.net[m]
                if n_null > 0:
                    w_by_id[fid] = w
            except Exception as e:                            # a failing formula is a ledger row, never a skip
                row.update({"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-1200:]})
            row["seconds"] = round(time.time() - t0, 2)
            append_jsonl(ledger, row)
            print(f"  {fid:<52} sharpe {row.get('d_sharpe') if 'error' not in row else float('nan'):>7.2f} "
                  f"t {row.get('d_hac_t') if 'error' not in row else float('nan'):>6.2f} "
                  f"{'ok' if row.get('audit_pass') else ('ERR ' + row.get('error', '')[:60] if 'error' in row else 'LEAK')}"
                  f" ({row['seconds']}s)", flush=True)
        if nets:
            tag = f"{lane}__{uname}{'__ML' if ml else ''}"
            pd.DataFrame(nets).to_parquet(netdir / f"{tag}.parquet")
        if n_null > 0 and len(w_by_id) >= 2:
            try:
                keep = sorted({c for w in w_by_id.values() for c in w.columns[(w.fillna(0) != 0).any()]})
                subn = sub.subset([c for c in sub.prices.columns if c in keep])
                wn = {k: v[subn.prices.columns] for k, v in w_by_id.items()}
                kn = eng_kwargs(subn, cfg)
                kn.pop("missing_return", None)
                nres = mtest.circular_shift_null(subn, wn, window=cfg.design, cost_bp_side=c_b[subn.prices.columns],
                                                 seed=SEED, n_rep=n_null, **kn)
                out = {k: jsonable(v) for k, v in nres.items() if not isinstance(v, (np.ndarray, pd.Series, pd.DataFrame, list))}
                (ctx.run / f"tier2_circnull_{lane}__{uname}.json").write_text(json.dumps(out, indent=1, default=str))
            except Exception as e:
                (ctx.run / f"tier2_circnull_{lane}__{uname}.json").write_text(
                    json.dumps({"error": f"{type(e).__name__}: {e}"}))
                print(f"  circular-shift null failed (report-only): {type(e).__name__}: {e}", flush=True)


def tier2_blocks(ctx: Ctx) -> Dict[str, pd.DataFrame]:
    blocks: Dict[str, pd.DataFrame] = {}
    for p in sorted((ctx.run / "tier2_net").glob("*.parquet")):
        key = p.stem.replace("__ML", "")
        df = pd.read_parquet(p)
        blocks[key] = df if key not in blocks else blocks[key].join(df, how="outer")
    return blocks


def tier2_mtest(ctx: Ctx, reps: int) -> dict:
    sha = check_pins(ctx)
    rows = [r for r in read_jsonl(ctx.run / "tier2_design_ledger.jsonl") if r.get("prereg_sha256") == sha]
    ok = [r for r in rows if "error" not in r]
    p = pd.Series({r["formula_id"]: (r.get("d_p_one_sided") if r.get("d_p_one_sided") is not None else np.nan) for r in ok})
    bh = mtest.bh_fdr(p, q=0.10)
    bh_set = sorted(p.index[np.asarray(bh["reject"], dtype=bool)])
    blocks = tier2_blocks(ctx)
    alpha_block = 0.05 / max(len(blocks), 1)
    out = {"prereg_sha256": sha, "n_formulas": len(rows), "n_errors": len(rows) - len(ok), "bh_q": 0.10,
           "bh_reject": bh_set, "alpha_block": alpha_block, "blocks": {}}
    stepm_set: List[str] = []
    for key, df in blocks.items():
        x = df.fillna(0.0)
        b: dict = {"n_formulas": int(x.shape[1]), "n_rows": int(x.shape[0])}
        try:
            sm = mtest.stepm(x, alpha=alpha_block, reps=reps, seed=SEED)
            b["stepm_superior"] = list(sm["superior"])
            b["stepm_block"] = sm.get("block")
            b["stepm_first_critical_value"] = jsonable(sm["steps"][0]["critical_value"]) if sm.get("steps") else None
            stepm_set += list(sm["superior"])
        except Exception as e:
            b["stepm_error"] = f"{type(e).__name__}: {e}"
        try:
            sp = mtest.spa(x, reps=reps, seed=SEED)
            b["spa_p"] = {k: jsonable(sp[k]) for k in ("p_lower", "p_consistent", "p_upper")}
            b["spa_best"] = str(sp.get("best"))
        except Exception as e:
            b["spa_error"] = f"{type(e).__name__}: {e}"
        try:
            pb = mtest.pbo_cscv(x, S=16)
            b["pbo"] = jsonable(pb["pbo"])
            b["pbo_slope"] = jsonable(pb.get("slope"))
        except Exception as e:
            b["pbo_error"] = f"{type(e).__name__}: {e}"
        out["blocks"][key] = b
    out["stepm_superior_all"] = sorted(set(stepm_set))
    (ctx.run / "tier2_mtest.json").write_text(json.dumps(jsonable(out), indent=1, default=str))
    print(f"[mtest] {len(ok)} formulas; BH(q=10%) rejects {len(bh_set)}; StepM superior {len(set(stepm_set))}", flush=True)
    return out


def tier2_freeze(ctx: Ctx) -> dict:
    sha = check_pins(ctx)
    out_p = ctx.run / "SURVIVORS_FROZEN.json"
    if out_p.exists():
        raise Refused("SURVIVORS_FROZEN.json exists — the freeze is one-shot")
    mt = json.loads((ctx.run / "tier2_mtest.json").read_text())
    rows = {r["formula_id"]: r for r in read_jsonl(ctx.run / "tier2_design_ledger.jsonl") if r.get("prereg_sha256") == sha}
    cand = sorted(set(mt["bh_reject"]) | set(mt["stepm_superior_all"]))
    verdicts, survivors = [], []
    for fid in cand:
        r = rows[fid]
        why = []
        if (r.get("stress_sharpe") or -1.0) <= 0:
            why.append("stress<=0")
        if not r.get("audit_pass"):
            why.append("LEAKY")
        if r.get("print_proximity"):
            why.append("PRINT-PROXIMITY")
        verdicts.append({"formula_id": fid, "bh": fid in mt["bh_reject"], "stepm": fid in mt["stepm_superior_all"],
                         "d_sharpe": r.get("d_sharpe"), "d_hac_t": r.get("d_hac_t"), "stress_sharpe": r.get("stress_sharpe"),
                         "retail_sharpe": r.get("retail_sharpe"), "survives": not why, "excluded_for": why})
        if not why:
            survivors.append(fid)
    payload = {"frozen_utc": pd.Timestamp.now(tz="UTC").isoformat(), "prereg_sha256": sha,
               "design_ledger_sha256": sha256_file(ctx.run / "tier2_design_ledger.jsonl"),
               "mtest_sha256": sha256_file(ctx.run / "tier2_mtest.json"),
               "n_formulas": len(rows), "candidates": verdicts, "survivors": survivors,
               "survivors_sha256": hashlib.sha256(json.dumps(survivors).encode()).hexdigest()}
    out_p.write_text(json.dumps(jsonable(payload), indent=1, default=str))
    print(f"[freeze] {len(survivors)} survivors of {len(rows)} formulas (candidates {len(cand)}) -> {out_p}", flush=True)
    return payload


# ==================================================================================================
# TIER 1 — the 16 primaries
# ==================================================================================================
def _t1_cost_key(spec) -> Tuple[str, str]:
    if spec.lane == "MACRO" and spec.transforms.get("long_only"):
        return ("MACRO", "t1_lo")
    return (spec.lane, "t1")


def build_primary(ctx: Ctx, spec) -> dict:
    """Members -> speed limit -> ensemble -> book transforms. Returns the panel subset and the target frame."""
    cfg = ctx.cfg(spec.lane)
    panel = ctx.panel(spec.lane)
    cols = ctx.universes(spec.lane, panel)[spec.universe] if spec.lane.startswith("FX") else list(panel.prices.columns)
    sub = panel.subset(cols)
    lo = bool(spec.transforms.get("long_only"))
    c_b, _ = cost_series(COSTS[_t1_cost_key(spec)]["base"], sub.prices.columns)
    kw = eng_kwargs(sub, cfg)
    books, fam, members = {}, {}, []
    for rule in registry.primary_members(spec, sub):
        w = size_positions(rule.signal(sub), sub, cfg.sigma)
        if lo:
            w = w.clip(lower=0.0)
        r0 = engine.backtest(sub, w, cost_bp_side=c_b, **kw)                  # trading cost only: the speed limit
        m = stats.window_mask(r0.net.index, cfg.design)
        vol = float(r0.gross[m].std(ddof=1) * math.sqrt(cfg.ppy)) if m.sum() > 2 else float("nan")
        cost_yr = float(r0.cost[m].mean() * cfg.ppy) if m.sum() > 0 else float("nan")
        cost_sr = cost_yr / vol if vol and vol > 0 else float("inf")
        kept = bool(cost_sr <= SPEED_LIMIT_SR)
        members.append({"rule_id": rule.id, "family": rule.family, "cost_sr": cost_sr, "kept": kept,
                        "turnover_sides_per_year": float(r0.turnover[m].mean() * cfg.ppy) if m.sum() else None})
        if kept:
            books[rule.id], fam[rule.id] = w, rule.family
    if not books:
        return {"sub": sub, "w": None, "members": members, "lo": lo}
    w_ens = portfolio.ensemble(books, fam, sub, target=cfg.sigma)
    if lo:
        w_t = portfolio.vol_target(w_ens.clip(lower=0.0), sub, float(spec.transforms["vol_target"]),
                                   max_gross=float(spec.transforms.get("max_gross", 1.0)))
        w_t = portfolio.long_only_cap(w_t, float(spec.transforms.get("max_gross", 1.0)))
    else:
        w_t = portfolio.vol_target(w_ens, sub, float(spec.transforms["vol_target"]), max_gross=cfg.max_gross)
    return {"sub": sub, "w": w_t, "members": members, "lo": lo}


def account_run(sub: PanelBundle, w: pd.DataFrame, cfg: LaneCfg, cspec, lo: bool, freq: Optional[str]):
    """Official Tier-1 scoring: units drift; trades only by the band (L/S) or the schedule (long-only)."""
    c, h = cost_series(cspec, sub.prices.columns)
    venue = {k: realism.VenueSpec.ideal().with_overrides(fee_bp=float(c[k]), financing_long_bp_year=float(h[k]),
                                                         financing_short_bp_year=float(h[k])) for k in sub.prices.columns}
    delay = 0 if cfg.exec_prints else 1
    mask = portfolio.rebalance_rows(sub.prices.index, freq, offset=delay) if lo else None
    return realism.simulate_account(sub, w, equity0=1e7, venue=venue, rebalance_mask=mask,
                                    no_trade_band=0.0 if lo else BUFFER, window=cfg.full, **eng_kwargs(sub, cfg))


def weight_engine_run(sub, w, cfg, cspec, lo, freq, later=False):
    c, h = cost_series(cspec, sub.prices.columns)
    wx = portfolio.rebalance_on(w, freq) if lo else portfolio.apply_buffer(w, BUFFER)
    return engine.backtest(sub, wx, cost_bp_side=c, hold_cost_long_bp_year=h, hold_cost_short_bp_year=h,
                           turnover_model="target", **eng_kwargs(sub, cfg, later=later))


def windows_for(cfg: LaneCfg, index: pd.DatetimeIndex) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    last5 = str((index[-1] - pd.DateOffset(years=5)).date())
    w = {"FULL": cfg.full, "POST_PUB": cfg.postpub, "LAST_5Y": (max(last5, cfg.full[0]), None)}
    if cfg.postpub[0] > cfg.full[0]:
        w["PRE_PUB"] = (cfg.full[0], str((pd.Timestamp(cfg.postpub[0]) - pd.Timedelta(days=1)).date()))
    return w


def yearly_returns(net: pd.Series, window) -> Dict[str, float]:
    m = stats.window_mask(net.index, window)
    s = net[m]
    return {str(y): float((1.0 + g).prod() - 1.0) for y, g in s.groupby(s.index.year)}


def vol_matched_basket(sub, cfg, target_vol: float, cspec, lo: bool, freq: Optional[str]):
    """The 'just hold less' benchmark: the lane's equal-weight long basket at constant exposure, run through
    the SAME drift-aware account and costs as the book, scaled so its FULL-window realised vol equals the
    book's (capped at gross 1 for long-only wrappers). Ex-post scaling is deliberate — it is a yardstick,
    not a strategy."""
    wb = basket_weights(sub, cfg.sigma)
    gross = wb.abs().sum(axis=1).replace(0, np.nan)
    wn = wb.div(gross, axis=0).fillna(0.0)                       # constant 1.0 gross where the basket exists
    r1 = account_run(sub, wn, cfg, cspec, lo, freq)
    m = stats.window_mask(r1.net.index, cfg.full)
    v1 = float(r1.net[m].std(ddof=1) * math.sqrt(cfg.ppy))
    k = target_vol / v1 if v1 > 0 else 0.0
    if lo:
        k = min(k, 1.0)
    if abs(k - 1.0) < 1e-12:
        return r1.net, k
    return account_run(sub, wn * k, cfg, cspec, lo, freq).net, k


def label_primary(res: dict) -> Tuple[str, List[str]]:
    """PREREGISTRATION_v2 §4, verbatim."""
    f = []
    if not (res["full"]["sharpe"] is not None and res["full"]["sharpe"] >= 0.30):
        f.append("(a) FULL net Sharpe < 0.30")
    if not (res["stress_full_sharpe"] is not None and res["stress_full_sharpe"] >= 0.15):
        f.append("(b) stress Sharpe < 0.15")
    if not (res["p_sharpe_gt0"] is not None and res["p_sharpe_gt0"] >= 0.80):
        f.append("(c) bootstrap P(Sharpe>0) < 0.80")
    if not (res["postpub"]["sharpe"] is not None and res["postpub"]["sharpe"] >= 0.0):
        f.append("(d) POST-PUB Sharpe < 0")
    if not (res["max_abs_share"] is not None and res["max_abs_share"] <= 0.50 and res["share_years_positive"] >= 0.50):
        f.append("(e) concentration or < half of years positive")
    if not (res["members_audit_clean"] and not res["print_proximity"]):
        f.append("(f) audit / print-proximity")
    if res["long_only"]:
        g = (res["full"]["sharpe"] is not None and res["bench_sharpe"] is not None
             and res["full"]["sharpe"] >= res["bench_sharpe"] - 0.10
             and res["full"]["max_drawdown"] >= 0.80 * res["bench_max_drawdown"])   # drawdowns are negative
        if not g and not f:
            return "NO VALUE-ADD OVER HOLDING", ["(g) not better than the vol-matched basket"]
        if not g:
            f.append("(g) not better than the vol-matched basket")
    else:
        if not (res["alpha_ann"] is not None and res["alpha_ann"] >= 0.0):
            f.append("(g) alpha vs the lane basket < 0")
    return ("PAPER-CANDIDATE" if not f else "NOT A CANDIDATE"), f


def tier1(ctx: Ctx, only: Optional[List[str]] = None) -> None:
    sha = check_pins(ctx)
    if not (ctx.run / "SURVIVORS_FROZEN.json").exists():
        raise Refused("Tier 1 is displayed only after the Tier-2 survivor freeze (prereg §5 sequencing)")
    rng = np.random.default_rng(SEED + 1)
    netdir = ctx.run / "tier1_net"
    netdir.mkdir(exist_ok=True)
    results: Dict[str, dict] = {}
    base_streams: Dict[str, Tuple[pd.Series, int]] = {}
    for spec in registry.primaries():
        if only and spec.id not in only:
            continue
        if spec.lane == "GLOBAL":
            continue
        t0 = time.time()
        cfg = ctx.cfg(spec.lane)
        b = build_primary(ctx, spec)
        res: dict = {"id": spec.id, "lane": spec.lane, "universe": spec.universe, "families": list(spec.families),
                     "transforms": spec.transforms, "members": b["members"], "long_only": b["lo"],
                     "prereg_sha256": sha}
        print(f"[tier1] {spec.id}: {sum(m['kept'] for m in b['members'])}/{len(b['members'])} members kept by the speed limit", flush=True)
        if b["w"] is None:
            res["label"], res["fails"] = "NOT IMPLEMENTABLE AT THIS COST", ["every member exceeds the speed limit"]
            results[spec.id] = res
            continue
        sub, w = active_subset(b["sub"], b["w"])
        lo = b["lo"]
        freq = spec.transforms.get("rebalance")
        cset = COSTS[_t1_cost_key(spec)]
        acct = {name: account_run(sub, w, cfg, cset[name], lo, freq) for name in ("base", "stress", "ref")}
        weng = weight_engine_run(sub, w, cfg, cset["base"], lo, freq)
        weng_later = weight_engine_run(sub, w, cfg, cset["base"], lo, freq, later=True)
        net = acct["base"].net
        wins = windows_for(cfg, net.index)
        bench_net, bench_k = vol_matched_basket(sub, cfg, float(net[stats.window_mask(net.index, cfg.full)].std(ddof=1)
                                                                * math.sqrt(cfg.ppy)), cset["base"], lo, freq)
        ev = stats.evidence_table(net, wins, cfg.ppy, gross=acct["base"].gross, turnover=acct["base"].turnover,
                                  gross_leverage=acct["base"].gross_leverage, benchmark=bench_net, hac_lags=21)
        ev_ref = stats.evidence_table(acct["ref"].net, wins, cfg.ppy, hac_lags=21)
        ev_stress = stats.evidence_table(acct["stress"].net, wins, cfg.ppy, hac_lags=21)
        boot = stats.sharpe_ci_bootstrap(net, periods_per_year=cfg.ppy, reps=2000, seed=SEED, window=cfg.full)
        contrib = stats.contribution_by_instrument(weng, window=cfg.full)
        yrs = yearly_returns(net, cfg.full)
        bst = stats.summarize(bench_net, periods_per_year=cfg.ppy, window=cfg.full)
        ls = audit.lag_sensitivity(weng.net, weng_later.net, cfg.ppy, window=cfg.full)
        clean = True
        for m in b["members"]:
            if not m["kept"]:
                continue
            rule = registry.get(m["rule_id"])
            ar = audit.future_scramble_audit(rule.fn, b["sub"], rule.params, probe_rows(b["sub"], cfg.full[0], (0.5,)), rng,
                                             antithetic=False, determinism_check=False)
            m["audit_pass"] = bool(ar.passed)
            clean = clean and bool(ar.passed)
        row = lambda t, k: jsonable(dict(t.loc[k])) if k in t.index else None  # noqa: E731
        res.update({
            "full": row(ev, "FULL"), "postpub": row(ev, "POST_PUB"), "prepub": row(ev, "PRE_PUB"), "last5": row(ev, "LAST_5Y"),
            "ref_full": row(ev_ref, "FULL"), "ref_postpub": row(ev_ref, "POST_PUB"),
            "stress_full_sharpe": jsonable(ev_stress.loc["FULL", "sharpe"]),
            "p_sharpe_gt0": 1.0 - float(boot["frac_le_zero"]), "sharpe_ci90": [jsonable(boot["lo"]), jsonable(boot["hi"])],
            "max_abs_share": jsonable(contrib["abs_share"].max()) if len(contrib) else None,
            "top_contributors": {str(k): jsonable(v) for k, v in contrib["abs_share"].head(5).items()},
            "yearly": yrs, "share_years_positive": float(np.mean([v > 0 for v in yrs.values()])) if yrs else 0.0,
            "weight_engine_full_sharpe": jsonable(stats.summarize(weng.net, periods_per_year=cfg.ppy, window=cfg.full)["sharpe"]),
            "later_timing_sharpe": jsonable(ls["sharpe_b"]), "print_proximity": bool(ls["flag"]),
            "members_audit_clean": clean,
            "bench_sharpe": jsonable(bst["sharpe"]), "bench_max_drawdown": jsonable(bst["max_drawdown"]),
            "bench_ann_return": jsonable(bst["ann_return"]), "bench_exposure": bench_k,
            "alpha_ann": jsonable(ev.loc["FULL", "alpha_ann"]), "alpha_t": jsonable(ev.loc["FULL", "alpha_t"]),
            "beta": jsonable(ev.loc["FULL", "beta"]),
            "avg_gross_leverage": jsonable(ev.loc["FULL", "avg_gross_leverage"]),
            "cost_bp_year": jsonable(acct["base"].cost_breakdown),
            "postpub_p_one_sided": jsonable(ev.loc["POST_PUB", "p_one_sided"]),
            "seconds": round(time.time() - t0, 1),
        })
        res["label"], res["fails"] = label_primary(res)
        results[spec.id] = res
        pd.DataFrame({"base": acct["base"].net, "stress": acct["stress"].net, "ref": acct["ref"].net,
                      "weight_engine": weng.net, "bench": bench_net}).to_parquet(netdir / f"{spec.id}.parquet")
        wdir = ctx.run / "tier1_w"
        wdir.mkdir(exist_ok=True)
        w.to_parquet(wdir / f"{spec.id}.parquet")              # the target frame, for realism / the leverage ladder
        base_streams[spec.id] = (net, cfg.ppy)
        print(f"   FULL sharpe {res['full']['sharpe']:.2f} (ref {res['ref_full']['sharpe']:.2f}, stress {res['stress_full_sharpe']:.2f}) "
              f"POST-PUB {res['postpub']['sharpe']:.2f} maxDD {res['full']['max_drawdown']:.1%} -> {res['label']} ({res['seconds']}s)", flush=True)

    g = next((s for s in registry.primaries() if s.lane == "GLOBAL"), None)
    if g is not None and (not only or g.id in only):
        specs_by_id = {s.id: s for s in registry.primaries()}
        for pid in g.transforms["equal_risk_of"]:              # books scored in an earlier process
            f = netdir / f"{pid}.parquet"
            if pid not in base_streams and f.exists():
                base_streams[pid] = (pd.read_parquet(f)["base"], ctx.cfg(specs_by_id[pid].lane).ppy)
        parts = [p for p in g.transforms["equal_risk_of"] if p in base_streams]
        if len(parts) == len(g.transforms["equal_risk_of"]):
            results[g.id] = global_book(ctx, g, {p: base_streams[p] for p in parts}, sha)
        else:
            print(f"[tier1] {g.id}: waiting for {sorted(set(g.transforms['equal_risk_of']) - set(parts))}", flush=True)
    # merge with books scored by earlier processes, then Holm across ALL primaries (POST-PUB one-sided p, HAC 21)
    merged = json.loads((ctx.run / "tier1_results.json").read_text()) if (ctx.run / "tier1_results.json").exists() else {}
    merged.update(results)
    ids = [k for k, v in merged.items() if v.get("postpub_p_one_sided") is not None]
    if ids:
        hp = mtest.holm(pd.Series({k: merged[k]["postpub_p_one_sided"] for k in ids}), alpha=0.05)
        for k, rej, padj in zip(ids, np.asarray(hp["reject"], dtype=bool), np.asarray(hp["p_adjusted"], dtype=float)):
            merged[k]["confirmed"] = bool(rej)
            merged[k]["postpub_p_holm"] = float(padj)
            merged[k]["holm_m"] = len(ids)
    (ctx.run / "tier1_results.json").write_text(json.dumps(jsonable(merged), indent=1, default=str))


def global_book(ctx: Ctx, spec, streams: Dict[str, Tuple[pd.Series, int]], sha: str) -> dict:
    """Equal-risk mix of the lane books' base-cost net streams on calendar days, re-targeted to 10 % vol.
    Every scale uses returns up to the previous day only. Limit: the cost of re-scaling between books is
    not charged (the streams are already net of their own costs)."""
    daily, ppys = {}, {}
    for k, (s, ppy_k) in streams.items():
        d = s.copy()
        d.index = d.index.tz_convert("UTC").normalize()
        daily[k] = d.groupby(level=0).sum()
        ppys[k] = ppy_k
    df = pd.DataFrame(daily).sort_index()
    df = df.reindex(pd.date_range(df.index[0], df.index[-1], freq="D", tz="UTC"))
    scaled, started = {}, {}
    for k in df.columns:
        x = df[k].dropna()                                    # the stream's own prints
        vol = x.rolling(60, min_periods=40).std(ddof=1).shift(1) * math.sqrt(ppys[k])
        sx = (x * (0.10 / vol)).where(vol > 0)
        scaled[k] = sx.reindex(df.index)                      # NaN on days the stream has no print
        first = sx.first_valid_index()
        started[k] = pd.Series(df.index >= first, index=df.index) if first is not None else pd.Series(False, index=df.index)
    sc = pd.DataFrame(scaled)
    k_active = pd.DataFrame(started).sum(axis=1)              # streams that EXIST by this date
    mix = (sc.fillna(0.0).sum(axis=1) / k_active.where(k_active > 0)).fillna(0.0)   # no print today = 0 return
    live = mix[k_active > 0]
    v = (live.rolling(90, min_periods=60).std(ddof=1).shift(1) * math.sqrt(365.25)).reindex(mix.index)
    lev = (0.10 / v).clip(upper=3.0).fillna(0.0)
    net = (mix * lev).rename("net")
    ppy = 365
    start = str(net.index[(lev > 0).values][0].date()) if (lev > 0).any() else str(net.index[0].date())
    all_live = k_active[k_active == len(streams)]
    wins = {"FULL": (start, None), "POST_PUB": (max("2013-01-01", start), None),
            "COMMON": (max(str(all_live.index[0].date()), start) if len(all_live) else start, None),
            "LAST_5Y": (max(str((net.index[-1] - pd.DateOffset(years=5)).date()), start), None)}
    ev = stats.evidence_table(net, wins, ppy, hac_lags=21)
    boot = stats.sharpe_ci_bootstrap(net, periods_per_year=ppy, reps=2000, seed=SEED, window=wins["FULL"])
    yrs = yearly_returns(net, wins["FULL"])
    row = lambda k: jsonable(dict(ev.loc[k])) if k in ev.index else None  # noqa: E731
    res = {"id": spec.id, "lane": "GLOBAL", "universe": None, "families": [], "transforms": spec.transforms,
           "members": [{"rule_id": k, "family": "BOOK", "kept": True} for k in streams], "long_only": False,
           "prereg_sha256": sha, "full": row("FULL"), "postpub": row("POST_PUB"), "prepub": None, "last5": row("LAST_5Y"),
           "common": row("COMMON"), "ref_full": None, "ref_postpub": None, "stress_full_sharpe": None,
           "p_sharpe_gt0": 1.0 - float(boot["frac_le_zero"]), "sharpe_ci90": [jsonable(boot["lo"]), jsonable(boot["hi"])],
           "yearly": yrs, "share_years_positive": float(np.mean([v > 0 for v in yrs.values()])) if yrs else 0.0,
           "postpub_p_one_sided": jsonable(ev.loc["POST_PUB", "p_one_sided"]),
           "label": "COMPOSITE (see its three books)", "fails": []}
    net.to_frame("base").to_parquet(ctx.run / "tier1_net" / f"{spec.id}.parquet")
    print(f"[tier1] {spec.id}: FULL sharpe {res['full']['sharpe']:.2f} from {wins['FULL'][0]}", flush=True)
    return res


# ==================================================================================================
# FX robustness (prereg §2/§3): the pre-euro record on FX-FRED, and the same-day NY-noon execution check
# ==================================================================================================
def _fx_book(panel: PanelBundle, spec, kept: List[str], cfg: LaneCfg) -> Optional[pd.DataFrame]:
    """The primary's ensemble rebuilt on another FX panel with the SAME kept members (no new speed limit)."""
    cols = registry.fx_universes(panel)["G10"]
    sub = panel.subset(cols)
    books, fam = {}, {}
    for rid in kept:
        rule = registry.get(rid)
        if registry.missing_requirements(rule, sub):
            continue
        books[rid], fam[rid] = size_positions(rule.signal(sub), sub, cfg.sigma), rule.family
    if not books:
        return None
    w = portfolio.vol_target(portfolio.ensemble(books, fam, sub, target=cfg.sigma), sub,
                             float(spec.transforms["vol_target"]), max_gross=cfg.max_gross)
    return sub, portfolio.apply_buffer(w, BUFFER)


def fx_robustness(ctx: Ctx) -> None:
    sha = check_pins(ctx)
    t1p = ctx.run / "tier1_results.json"
    if not t1p.exists():
        raise Refused("run tier1 first: the robustness books reuse each primary's kept member list")
    t1 = json.loads(t1p.read_text())
    cfg = ctx.cfg("FX")
    out: dict = {"prereg_sha256": sha, "fx_fred": {}, "fx_exec": {}}
    specs = {s.id: s for s in registry.primaries()}
    # (1) FX-FRED: 1976-01-02 -> 1998-12-31 (pre-euro) and 1999 -> last (overlap with the ECB lane)
    try:
        fred = ctx.panel("FX-FRED")
        for pid in ("P.FX.G10.TREND", "P.FX.G10.CARRY", "P.FX.G10.VALUE", "P.FX.G10.XSMOM", "P.FX.G10.ALL"):
            if pid not in t1 or not t1[pid].get("members"):
                continue
            kept = [m["rule_id"] for m in t1[pid]["members"] if m.get("kept")]
            b = _fx_book(fred, specs[pid], kept, cfg)
            if b is None:
                continue
            sub, w = b
            res = {}
            for name in ("base", "ref"):
                c, h = cost_series(COSTS[("FX", "t1")][name], sub.prices.columns)
                r = engine.backtest(sub, w, cost_bp_side=c, hold_cost_long_bp_year=h, hold_cost_short_bp_year=h,
                                    lag=1, missing_return="zero")
                for wn, win in (("pre_euro_1976_1998", ("1976-01-02", "1998-12-31")), ("since_1999", ("1999-01-04", None))):
                    st = stats.summarize(r.net, periods_per_year=cfg.ppy, window=win)
                    res[f"{name}_{wn}"] = {k: jsonable(st[k]) for k in ("sharpe", "hac_t", "ann_return", "max_drawdown", "n_obs")}
            out["fx_fred"][pid] = res
            print(f"[fx-robust] {pid} on FX-FRED: pre-euro ref Sharpe {res['ref_pre_euro_1976_1998']['sharpe']}, "
                  f"base {res['base_pre_euro_1976_1998']['sharpe']}", flush=True)
    except Exception as e:
        out["fx_fred"]["error"] = f"{type(e).__name__}: {e}"
    # (2) FX-EXEC: same-day NY-noon execution vs next-fix execution, same calendar, reference cost
    try:
        ex = ctx.panel("FX-EXEC")
        pid = "P.FX.G10.ALL"
        kept = [m["rule_id"] for m in t1[pid]["members"] if m.get("kept")]
        sub, w = _fx_book(ex, specs[pid], kept, cfg)
        c, h = cost_series(COSTS[("FX", "t1")]["ref"], sub.prices.columns)
        r_exec = engine.backtest(sub, w, cost_bp_side=c, hold_cost_long_bp_year=h, hold_cost_short_bp_year=h,
                                 exec_prices=sub.aux["exec_prices"], extra_lag=0, missing_return="refuse")
        r_lag1 = engine.backtest(sub, w, cost_bp_side=c, hold_cost_long_bp_year=h, hold_cost_short_bp_year=h,
                                 lag=1, missing_return="refuse")
        s_exec = stats.summarize(r_exec.net, periods_per_year=cfg.ppy, window=cfg.full)["sharpe"]
        s_lag1 = stats.summarize(r_lag1.net, periods_per_year=cfg.ppy, window=cfg.full)["sharpe"]
        out["fx_exec"] = {"primary": pid, "sharpe_same_day_ny_noon": jsonable(s_exec), "sharpe_next_fix": jsonable(s_lag1),
                          "gap": jsonable(s_exec - s_lag1), "timing_artifact_warning": bool(abs(s_exec - s_lag1) > 0.2)}
        print(f"[fx-robust] {pid}: same-day NY-noon exec Sharpe {s_exec:.2f} vs next-fix {s_lag1:.2f}", flush=True)
    except Exception as e:
        out["fx_exec"] = {"error": f"{type(e).__name__}: {e}"}
    (ctx.run / "fx_robustness.json").write_text(json.dumps(jsonable(out), indent=1, default=str))



# ==================================================================================================
# HOLDOUT — the frozen survivors, once
# ==================================================================================================
def holdout(ctx: Ctx, descriptive: bool) -> None:
    sha = check_pins(ctx)
    fz = ctx.run / "SURVIVORS_FROZEN.json"
    if not fz.exists():
        raise Refused("no SURVIVORS_FROZEN.json — the holdout is read only after the freeze")
    frozen = json.loads(fz.read_text())
    design_rows = {r["formula_id"]: r for r in read_jsonl(ctx.run / "tier2_design_ledger.jsonl")
                   if r.get("prereg_sha256") == sha and "error" not in r}
    targets = list(design_rows) if descriptive else list(frozen["survivors"])
    out_p = ctx.run / ("holdout_descriptive.jsonl" if descriptive else "holdout_survivors.jsonl")
    done = {r["formula_id"] for r in read_jsonl(out_p)}
    for fid in targets:
        if fid in done:
            continue
        lane, uname, rid = fid.split("|")
        cfg = ctx.cfg(lane)
        panel = ctx.panel(lane)
        sub = panel.subset(ctx.universes(lane, panel)[uname])
        rule = registry.get(rid)
        spec = COSTS[(lane, "t2")]
        c_b, h_b = cost_series(spec["base"], sub.prices.columns)
        c_s, h_s = cost_series(spec["stress"], sub.prices.columns)
        c_r, h_r = cost_series(spec["retail"], sub.prices.columns)
        kw = eng_kwargs(sub, cfg)
        row = {"formula_id": fid, "prereg_sha256": sha, "is_survivor": fid in frozen["survivors"]}
        try:
            w = size_positions(rule.signal(sub), sub, cfg.sigma)
            if cfg.long_only:
                w = w.clip(lower=0.0)
            rb = engine.backtest(sub, w, cost_bp_side=c_b, hold_cost_long_bp_year=h_b, hold_cost_short_bp_year=h_b, **kw)
            rs = engine.backtest(sub, w, cost_bp_side=c_s, hold_cost_long_bp_year=h_s, hold_cost_short_bp_year=h_s, **kw)
            rr = engine.backtest(sub, w, cost_bp_side=c_r, hold_cost_long_bp_year=h_r, hold_cost_short_bp_year=h_r, **kw)
            st = stats.summarize(rb.net, periods_per_year=cfg.ppy, window=cfg.holdout, gross=rb.gross, turnover=rb.turnover)
            ss = stats.summarize(rs.net, periods_per_year=cfg.ppy, window=cfg.holdout)
            sr = stats.summarize(rr.net, periods_per_year=cfg.ppy, window=cfg.holdout)
            t = st["hac_t"]
            row.update({"h_sharpe": st["sharpe"], "h_hac_t": t, "h_ann_return": st["ann_return"],
                        "h_max_drawdown": st["max_drawdown"], "h_n_obs": st["n_obs"], "h_stress_sharpe": ss["sharpe"],
                        "h_retail_sharpe": sr["sharpe"], "d_sharpe": design_rows[fid].get("d_sharpe"),
                        "d_hac_t": design_rows[fid].get("d_hac_t")})
            if t is not None and t >= 2.0 and (ss["sharpe"] or -1) > 0:
                row["verdict"] = "PASS"
            elif t is not None and 1.0 <= t < 2.0:
                row["verdict"] = "ALIVE-UNPROVEN"
            else:
                row["verdict"] = "DEAD"
        except Exception as e:
            row.update({"error": f"{type(e).__name__}: {e}"})
        append_jsonl(out_p, row)
        if not descriptive:
            print(f"[holdout] {fid}: design t {row.get('d_hac_t')} -> holdout t {row.get('h_hac_t')} {row.get('verdict', row.get('error'))}", flush=True)
    print(f"[holdout] wrote {out_p}", flush=True)


# ==================================================================================================
# REPORTS
# ==================================================================================================
def _f(v, nd=2, pct=False):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    return f"{v:.1%}" if pct else f"{v:.{nd}f}"


def report(ctx: Ctx) -> None:
    sha = check_pins(ctx)
    L: List[str] = [f"# FACTORY v2 — results ({'SYNTHETIC SMOKE TEST — not market data' if ctx.synthetic else 'real data'})", "",
                    f"Pre-registration sha256 `{sha[:16]}…`. Generated {pd.Timestamp.now(tz='UTC').isoformat()}.", ""]
    t1p = ctx.run / "tier1_results.json"
    if t1p.exists():
        t1 = json.loads(t1p.read_text())
        L += ["## Tier 1 — the 16 primary ensembles", "",
              "Net of the base (retail-wrapper) cost unless stated; `ref` = futures-like financing; Sharpe is of excess returns.", "",
              "| primary | label | FULL Sharpe | ref | stress | POST-PUB | P(SR>0) | ann. ret | max DD | basket Sharpe / DD | alpha/yr | gross | kept |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|"]
        for s in registry.primaries():
            r = t1.get(s.id)
            if not r:
                continue
            if r.get("full") is None:
                L.append(f"| {s.id} | {r.get('label')} | – | – | – | – | – | – | – | – | – | – | {sum(m['kept'] for m in r['members'])}/{len(r['members'])} |")
                continue
            L.append("| {id} | **{lab}**{conf} | {fs} | {rf} | {st} | {pp} | {pb} | {ar} | {dd} | {bs} / {bd} | {al} | {gl} | {kept}/{tot} |".format(
                id=s.id, lab=r["label"], conf=" · CONFIRMED" if r.get("confirmed") else "",
                fs=_f(r["full"]["sharpe"]), rf=_f((r.get("ref_full") or {}).get("sharpe")), st=_f(r.get("stress_full_sharpe")),
                pp=_f(r["postpub"]["sharpe"]) if r.get("postpub") else "–", pb=_f(r.get("p_sharpe_gt0")),
                ar=_f(r["full"]["ann_return"], pct=True), dd=_f(r["full"]["max_drawdown"], pct=True),
                bs=_f(r.get("bench_sharpe")), bd=_f(r.get("bench_max_drawdown"), pct=True), al=_f(r.get("alpha_ann"), pct=True),
                gl=_f(r.get("avg_gross_leverage")), kept=sum(m["kept"] for m in r["members"]), tot=len(r["members"])))
        L += ["", "### Why each label", ""]
        for s in registry.primaries():
            r = t1.get(s.id)
            if r:
                L.append(f"- **{s.id}** — {r['label']}" + (": " + "; ".join(r["fails"]) if r.get("fails") else ""))
        L += ["", "### Calendar years (base cost, net)", ""]
        for s in registry.primaries():
            r = t1.get(s.id)
            if r and r.get("yearly"):
                L.append(f"- **{s.id}**: " + ", ".join(f"{y} {v:+.1%}" for y, v in r["yearly"].items()))
        L.append("")
    fxr = ctx.run / "fx_robustness.json"
    if fxr.exists():
        fx = json.loads(fxr.read_text())
        L += ["## FX robustness", ""]
        for pid, r in (fx.get("fx_fred") or {}).items():
            if isinstance(r, dict) and "ref_pre_euro_1976_1998" in r:
                L.append(f"- **{pid}** on FRED noon rates — pre-euro 1976–1998: Sharpe {_f(r['ref_pre_euro_1976_1998']['sharpe'])} at futures-like cost, "
                         f"{_f(r['base_pre_euro_1976_1998']['sharpe'])} at retail cost; since 1999: {_f(r['ref_since_1999']['sharpe'])} / {_f(r['base_since_1999']['sharpe'])}")
        e = fx.get("fx_exec") or {}
        if "gap" in e:
            L.append(f"- Timing check on `{e['primary']}`: same-day NY-noon execution Sharpe {_f(e['sharpe_same_day_ny_noon'])} vs next-fix {_f(e['sharpe_next_fix'])} "
                     f"(gap {_f(e['gap'])}{' — TIMING-ARTIFACT WARNING' if e.get('timing_artifact_warning') else ''}).")
        L.append("")
    led = [r for r in read_jsonl(ctx.run / "tier2_design_ledger.jsonl") if r.get("prereg_sha256") == sha]
    if led:
        mt = json.loads((ctx.run / "tier2_mtest.json").read_text()) if (ctx.run / "tier2_mtest.json").exists() else {}
        L += ["## Tier 2 — the design-window screen", "",
              f"{len(led)} formulas ledgered ({sum('error' in r for r in led)} errors). "
              f"Benjamini–Hochberg (q = 10 %) rejects {len(mt.get('bh_reject', []))}; StepM superior {len(mt.get('stepm_superior_all', []))}.", ""]
        for key, b in (mt.get("blocks") or {}).items():
            L.append(f"- `{key}`: {b.get('n_formulas')} formulas × {b.get('n_rows')} prints; StepM {b.get('stepm_superior', b.get('stepm_error'))}; "
                     f"SPA p (consistent) {_f((b.get('spa_p') or {}).get('p_consistent'), 3)}; PBO {_f(b.get('pbo'))}")
        L += ["", "Top 25 by design HAC t (screen cost):", "",
              "| formula | Sharpe | HAC t | stress | retail | later timing | turnover/yr | audit | flags |", "|---|---:|---:|---:|---:|---:|---:|---|---|"]
        okr = sorted([r for r in led if "error" not in r and r.get("d_hac_t") is not None], key=lambda r: -r["d_hac_t"])
        for r in okr[:25]:
            L.append(f"| {r['formula_id']} | {_f(r.get('d_sharpe'))} | {_f(r.get('d_hac_t'))} | {_f(r.get('stress_sharpe'))} | {_f(r.get('retail_sharpe'))} | "
                     f"{_f(r.get('later_sharpe'))} | {_f(r.get('d_turnover_sides_per_year'), 1)} | {'ok' if r.get('audit_pass') else 'LEAKY'} | "
                     f"{'PRINT-PROX' if r.get('print_proximity') else ''} |")
        ts = np.array([r["d_hac_t"] for r in okr], dtype=float)
        if len(ts):
            L += ["", f"Distribution of design HAC t over {len(ts)} formulas: min {ts.min():.2f}, p25 {np.percentile(ts, 25):.2f}, "
                      f"median {np.median(ts):.2f}, p75 {np.percentile(ts, 75):.2f}, max {ts.max():.2f}; share positive {np.mean(ts > 0):.0%}.", ""]
    fz = ctx.run / "SURVIVORS_FROZEN.json"
    if fz.exists():
        frozen = json.loads(fz.read_text())
        L += ["## Frozen survivors and the holdout", "", f"Frozen {frozen['frozen_utc']}: {len(frozen['survivors'])} survivors "
              f"of {frozen['n_formulas']} formulas (candidates before exclusions: {len(frozen['candidates'])}).", ""]
        for c in frozen["candidates"]:
            L.append(f"- {c['formula_id']}: design Sharpe {_f(c['d_sharpe'])}, t {_f(c['d_hac_t'])}, stress {_f(c['stress_sharpe'])}, "
                     f"retail {_f(c.get('retail_sharpe'))} — {'SURVIVES' if c['survives'] else 'excluded: ' + ', '.join(c['excluded_for'])}")
        hs = read_jsonl(ctx.run / "holdout_survivors.jsonl")
        if hs:
            L += ["", "| survivor | design t | holdout Sharpe | holdout t | stress | retail | verdict |", "|---|---:|---:|---:|---:|---:|---|"]
            for r in hs:
                L.append(f"| {r['formula_id']} | {_f(r.get('d_hac_t'))} | {_f(r.get('h_sharpe'))} | {_f(r.get('h_hac_t'))} | "
                         f"{_f(r.get('h_stress_sharpe'))} | {_f(r.get('h_retail_sharpe'))} | **{r.get('verdict', r.get('error'))}** |")
        hd = [r for r in read_jsonl(ctx.run / "holdout_descriptive.jsonl") if "error" not in r and r.get("h_hac_t") is not None]
        if hd:
            d = np.array([r["d_hac_t"] for r in hd], dtype=float)
            h = np.array([r["h_hac_t"] for r in hd], dtype=float)
            top = h[d >= np.percentile(d, 90)]
            L += ["", f"Descriptive only (all {len(hd)} formulas): correlation of design t with holdout t = {np.corrcoef(d, h)[0, 1]:.2f}; "
                      f"holdout t > 0 for {np.mean(h > 0):.0%}; median holdout t {np.median(h):.2f}; "
                      f"of the design top decile, {(np.mean(top > 0) if len(top) else float('nan')):.0%} are positive on holdout.", ""]
    out = ctx.rep / "RESULTS.md"
    out.write_text("\n".join(L) + "\n")
    print(f"[report] {out}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["pin", "tier2", "mtest", "freeze", "tier1", "fxrobust", "holdout", "report"])
    ap.add_argument("--lane")
    ap.add_argument("--ml", action="store_true")
    ap.add_argument("--null-reps", type=int, default=0)
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--descriptive", action="store_true")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.synthetic and not a.out:
        raise SystemExit("--synthetic needs --out <scratch dir>: a smoke test never writes into runs/v2")
    ctx = Ctx(a.synthetic, a.out)
    if a.stage == "pin":
        if PIN.exists():
            raise Refused("PREREG_PIN_v2.json exists — the freeze is one-shot")
        pins = current_pins()
        pins.update({"frozen_utc": pd.Timestamp.now(tz="UTC").isoformat(), "runner_sha256": sha256_file(pathlib.Path(__file__)),
                     "tier2_formula_count": registry.declared_counts(
                         families_by_lane={"CRYPTO-SPOT": ("TREND", "XSMOM")}, lanes=registry.TIER2_LANES,
                         universes_by_lane_family={"FX": {"ML": ("G10",)}})["formulas_total"],
                     "primaries": len(registry.primaries())})
        PIN.write_text(json.dumps(pins, indent=1))
        print(json.dumps(pins, indent=1))
    elif a.stage == "tier2":
        tier2_lane(ctx, a.lane, a.ml, a.null_reps)
    elif a.stage == "mtest":
        tier2_mtest(ctx, a.reps)
    elif a.stage == "freeze":
        tier2_freeze(ctx)
    elif a.stage == "tier1":
        tier1(ctx, a.only)
    elif a.stage == "fxrobust":
        fx_robustness(ctx)
    elif a.stage == "holdout":
        holdout(ctx, a.descriptive)
    elif a.stage == "report":
        report(ctx)


if __name__ == "__main__":
    main()
