#!/usr/bin/env python3
"""INVENT 0824 flow formulas.  Every sign is declared a priori from the mechanism.

Each entry: name -> dict(obj, sig, why, sign_rationale)
  obj  "XS"  -> (S,T) coin-space signal, LONG the high end.
  obj  "ROT" -> (T,)  aggregate signal, POSITIVE = long alt-index / short BTC.
All signals are shifted by one day inside build(), so column t uses only information
through the CLOSE of day t-1 and is executed at the VWAP of day t.
"""
from __future__ import annotations
import numpy as np
from inv0824_flow_lib import (roll_mean, roll_std, roll_sum_ok, shift, zs, zs1, rm1, sh1,
                              roll_corr)


def build(P, F, G, U, A, CBC, CBQ):
    r = F["r_v"]; qv = F["qv"]
    netf = G["netf"]; netd = G["netd"]
    Q = {}

    # ================= FAMILY A -- NETFLOW ABSORPTION (exchange-netflow proxy) ==========
    # Mechanism: on-chain exchange netflow is invisible in free data, but its MARKET
    # FOOTPRINT is not.  Coins deposited to an exchange to be sold sit as passive asks;
    # taker BUY dollars then arrive and the price does NOT move.  So "much net taker
    # buying, little price response" = hidden supply = bearish; "price moved on little
    # net taker buying" = thin ask side / coins withdrawn = bullish.
    for w in (5, 20):
        zf = zs(roll_mean(netf, w), 120)
        zr = zs(roll_mean(r, w), 120)
        Q[f"A_ABSORB{w}"] = dict(
            obj="XS", sig=zr - zf,
            why=f"{w}d return z minus {w}d net-taker-flow z: price response per unit of "
                "taker flow; low = buying absorbed by hidden exchange-deposited supply.",
            sign_rationale="LONG high (price moved without needing flow = thin supply).")

    lam = roll_mean(np.abs(r), 20) / np.maximum(
        roll_mean(np.abs(netd) / np.maximum(G["adv20"], 1.0), 20), 1e-9)
    Q["A_LAMBDA20"] = dict(
        obj="XS", sig=np.log(np.where(lam > 0, lam, np.nan)),
        why="Kyle-lambda proxy: 20d mean |vwap return| per unit of |net taker $|/ADV.",
        sign_rationale="LONG high lambda (flow moves it = no deposited supply wall).")

    Q["A_FLOWCORR20"] = dict(
        obj="XS", sig=roll_corr(netf, r, 20),
        why="20d correlation between the daily net-taker imbalance and the daily vwap "
            "return: does flow actually price the coin, or is it being absorbed?",
        sign_rationale="LONG high correlation (clean demand, no absorption).")

    nadv = roll_sum_ok(netd, 5) / np.maximum(G["adv20"] * 5.0, 1.0)
    Q["A_NETADV5"] = dict(
        obj="XS", sig=-nadv,
        why="5d net taker dollars over 5x ADV -- pure retail taker pressure (control, the "
            "family D0821-B already reported as no-consistent-sign).",
        sign_rationale="SHORT recent net taker buying (taker pressure is contrarian).")

    Q["A_FLOWACCEL"] = dict(
        obj="XS", sig=-(roll_mean(netf, 5) - roll_mean(netf, 60)),
        why="flow acceleration: 5d net-taker imbalance minus its 60d level.",
        sign_rationale="SHORT accelerating taker buying (exhaustion).")

    zf5 = zs(roll_mean(netf, 5), 120)
    Q["A_ABSORB_X_ILLIQ"] = dict(
        obj="XS", sig=(zs(roll_mean(r, 5), 120) - zf5) * np.sign(
            np.nan_to_num(zs(G["lamihud"], 120))),
        why="absorption signed by whether illiquidity is above or below its own trend "
            "(supply walls should bite hardest where the book is thin).",
        sign_rationale="LONG high (same absorption direction, amplified where thin).")

    # ================= FAMILY B -- STABLECOIN DOMINANCE / DRY POWDER ===================
    # Mechanism: stablecoin pair turnover on the same venue is the observable footprint of
    # capital sitting OUT of risk.  A rising stablecoin share of exchange dollar volume is
    # money leaving alts; the rotation book (long alts / short BTC) should be off.
    Q["B_STABSHARE_D20"] = dict(
        obj="ROT", sig=-(A["stab_share"] - sh1(A["stab_share"], 20)),
        why="20d change in the stablecoin share of total Binance USDT-pair dollar volume.",
        sign_rationale="Rising stable share = risk-off -> SHORT alts vs BTC.")
    Q["B_STABSHARE_LVL"] = dict(
        obj="ROT", sig=-zs1(A["stab_share"], 250),
        why="250d z of the stablecoin volume share level.",
        sign_rationale="High stable share = defensive tape -> SHORT alts vs BTC.")
    Q["B_STABVOL_Z"] = dict(
        obj="ROT", sig=-zs1(A["stab_lqv"], 120),
        why="120d z of log total stablecoin-pair dollar volume (flight-to-stables burst).",
        sign_rationale="Stablecoin turnover burst = de-risking -> SHORT alts vs BTC.")
    Q["B_STABFLOW5"] = dict(
        obj="ROT", sig=-rm1(A["stab_netf"], 5),
        why="5d mean net TAKER buying of stablecoins (buying USDC/FDUSD/TUSD with USDT).",
        sign_rationale="Net taker buying of stables = dry-powder build -> SHORT alts.")

    # ================= FAMILY C -- BTC-DOMINANCE ROTATION ==============================
    Q["C_VDOM_D20"] = dict(
        obj="ROT", sig=-(A["btc_vdom"] - sh1(A["btc_vdom"], 20)),
        why="20d change in BTC's share of total USDT-pair dollar volume.",
        sign_rationale="Rising BTC volume dominance persists -> SHORT alts vs BTC.")
    Q["C_RS60"] = dict(
        obj="ROT", sig=rm1(A["alt_r"], 60) - rm1(A["btc_r"], 60),
        why="60d alt-EW minus BTC mean daily vwap return (rotation momentum).",
        sign_rationale="Rotation regimes are persistent -> LONG the recent winner side.")
    Q["C_RS5"] = dict(
        obj="ROT", sig=-(rm1(A["alt_r"], 5) - rm1(A["btc_r"], 5)),
        why="5d alt-EW minus BTC relative strength (short-horizon rotation reversal).",
        sign_rationale="Fast relative moves overshoot -> FADE.")
    Q["C_BREADTH20"] = dict(
        obj="ROT", sig=zs1(rm1(A["breadth"], 20), 250),
        why="20d fraction of universe alts out-returning BTC, z-scored over 250d.",
        sign_rationale="Broadening participation persists -> LONG alts vs BTC.")
    Q["C_DOMFLOW10"] = dict(
        obj="ROT", sig=rm1(A["alt_netf"], 10) - rm1(A["btc_netf"], 10),
        why="10d net taker imbalance of the alt aggregate minus BTC's -- where is the "
            "marginal taker dollar going?",
        sign_rationale="Taker flow rotation persists -> LONG the side being bought.")

    # ================= FAMILY D -- CROSS-VENUE (US vs OFFSHORE) FLOW SHARE =============
    # Mechanism: Coinbase = US onshore demand, Binance = offshore.  The published
    # "Coinbase premium" is a PRICE spread (family D3/D4 -- expected to be bounce, rho1
    # gate applied).  The VOLUME SHARE (D1/D2) is not a price spread at all and therefore
    # cannot be bid-ask bounce; it is the fresh object of this round.
    with np.errstate(invalid="ignore", divide="ignore"):
        ushare = CBQ / (CBQ + qv)
        prem_raw = np.log(CBC / F["c"])
    ok = np.isfinite(prem_raw)
    med = np.full(prem_raw.shape[1], np.nan)
    for t in range(prem_raw.shape[1]):
        m = ok[:, t]
        if m.sum() >= 8:
            med[t] = np.median(prem_raw[m, t])
    prem = prem_raw - med[None, :]          # de-mean the USD/USDT leg out

    Q["D_USSHARE_D20"] = dict(
        obj="XS", sig=ushare - shift(ushare, 20),
        why="20d change in Coinbase's share of (Coinbase + Binance) dollar volume.",
        sign_rationale="Rising US venue share = onshore accumulation -> LONG.")
    Q["D_USSHARE_LVL"] = dict(
        obj="XS", sig=zs(ushare, 250),
        why="250d z of the Coinbase volume-share level.",
        sign_rationale="LONG names with an unusually US-heavy tape.")
    Q["D_CBPREM5"] = dict(
        obj="XS", sig=roll_mean(prem, 5),
        why="5d mean cross-sectionally de-medianed Coinbase-minus-Binance log price "
            "(the published Coinbase Premium Index).",
        sign_rationale="LONG a positive premium (US bid leads).")
    Q["D_CBPREM_D5"] = dict(
        obj="XS", sig=prem - shift(prem, 5),
        why="5d change in the de-medianed Coinbase premium.",
        sign_rationale="LONG a widening US premium.")
    agg_us = np.full(qv.shape[1], np.nan)
    for t in range(qv.shape[1]):
        m = U[:, t] & np.isfinite(CBQ[:, t]) & np.isfinite(qv[:, t])
        if m.sum() >= 8:
            agg_us[t] = CBQ[m, t].sum() / (CBQ[m, t].sum() + qv[m, t].sum())
    Q["D_USAGG_D20"] = dict(
        obj="ROT", sig=-(agg_us - sh1(agg_us, 20)),
        why="20d change in the aggregate Coinbase share of matched dollar volume.",
        sign_rationale="US onshore money buys BTC first -> SHORT alts vs BTC.")

    # ================= FAMILY E -- ACTIVITY-SHOCK SHAPE (fresh variants) ===============
    Q["E_TICKET_SHOCK"] = dict(
        obj="XS", sig=zs(G["ticket"], 60),
        why="60d z of log mean ticket size (quote volume per trade): large tickets are "
            "desk/whale prints rather than retail clicks.",
        sign_rationale="LONG rising ticket size (institutional accumulation).")
    Q["E_COUNTNET"] = dict(
        obj="XS", sig=-(zs(roll_mean(G["ln"], 5), 120) - zs(roll_mean(G["lqv"], 5), 120)),
        why="5d trade-COUNT shock net of the 5d dollar-VOLUME shock: many small trades "
            "per dollar = retail crowd.",
        sign_rationale="SHORT retail-crowded names.")
    Q["E_VSHOCK_X_FLOW"] = dict(
        obj="XS", sig=-zs(roll_mean(G["lqv"], 5), 120) * np.sign(
            np.nan_to_num(roll_mean(netf, 5))),
        why="5d dollar-volume shock signed by the direction of the 5d taker imbalance.",
        sign_rationale="SHORT a volume+buying blow-off, LONG a volume+selling capitulation.")
    Q["E_AMIHUD_D20"] = dict(
        obj="XS", sig=G["lamihud"] - shift(G["lamihud"], 20),
        why="20d change in log Amihud illiquidity (|return| per dollar traded): a thinning "
            "book is the footprint of coins leaving the exchange.",
        sign_rationale="LONG rising illiquidity (net exchange OUTflow).")

    # single-day lag discipline
    for k, d in Q.items():
        s = d["sig"]
        d["sig"] = shift(s, 1) if s.ndim == 2 else sh1(s, 1)
    return Q
