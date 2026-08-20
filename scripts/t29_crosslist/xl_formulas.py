#!/usr/bin/env python3
"""The 30 PRE-REGISTERED formulas. Frozen before the design run.

Blocs (defined by the home venue's overlap with the US session, because that is what decides
whether a close-to-close spread is a CONTEMPORANEOUS mispricing or a stale-price gap):
  FULL   -- CA, BR, MX. Home close is within an hour of the US close.
  PART   -- UK, EU, CH, DK, IL. Home closes mid-US-session.
  NONE   -- JP, KR, TW, HK, IN, AU. Home closed hours before the US session opened.
  AR     -- Argentina. The 'contado con liqui' FX-control channel, not a convergence trade.
"""
FULL = ("CA", "BR", "MX")
PART = ("UK", "EU", "CH", "DK", "IL")
NONE = ("JP", "KR", "TW", "HK", "IN", "AU")
AR = ("AR",)

FORMULAS = [
    # ---- Family A: both legs US-listed. A genuine two-legged RV trade.
    dict(id="A1", fam="pair", note="all US/US same-claim pairs, L250 K2.0 exit0.5 mh20",
         L=250, K=2.0, EXIT=0.5, MAXHOLD=20, subset="all"),
    dict(id="A2", fam="pair", note="all pairs, faster book L120 K1.5 mh40",
         L=120, K=1.5, EXIT=0.5, MAXHOLD=40, subset="all"),
    dict(id="A3", fam="pair", note="DLC structures only", L=250, K=2.0, EXIT=0.5,
         MAXHOLD=20, subset="dlc"),
    dict(id="A4", fam="pair", note="foreign-issuer ADR share-class pairs only", L=250,
         K=2.0, EXIT=0.5, MAXHOLD=20, subset="adrclass"),
    # ---- Family B: ADR-vs-home spread, traded as a US-only cross-sectional book.
    dict(id="B1",  fam="xsec", regions=("CA",), mode="z", L=60,  frac=0.1, h=1),
    dict(id="B2",  fam="xsec", regions=("CA",), mode="z", L=60,  frac=0.1, h=5),
    dict(id="B3",  fam="xsec", regions=("CA",), mode="z", L=250, frac=0.1, h=5),
    dict(id="B4",  fam="xsec", regions=("CA",), mode="z", L=20,  frac=0.1, h=1),
    dict(id="B5",  fam="xsec", regions=("CA",), mode="d1",       frac=0.1, h=1),
    dict(id="B6",  fam="xsec", regions=("CA",), mode="dev", L=60, frac=0.1, h=5),
    dict(id="B7",  fam="xsec", regions=("CA",), mode="z", L=60,  frac=0.5, h=5, zgate=1.5),
    dict(id="B8",  fam="xsec", regions=("CA",), mode="z", L=60,  frac=0.2, h=5,
         weighting="invvol"),
    dict(id="B9",  fam="xsec", regions=("CA",), mode="z", L=60,  frac=0.1, h=1, entry_lag=1,
         note="conservative fill: signal at close t, enter at close t+1"),
    dict(id="B10", fam="xsec", regions=("CA",), mode="ewma", hl=30, L=60, frac=0.1, h=5),
    dict(id="B11", fam="xsec", regions=("BR", "MX"), mode="z", L=60, frac=0.2, h=5),
    dict(id="B12", fam="xsec", regions=("BR", "MX"), mode="z", L=60, frac=0.2, h=1),
    dict(id="B13", fam="xsec", regions=FULL, mode="z", L=60, frac=0.1, h=5,
         region_neutral=True),
    dict(id="B14", fam="xsec", regions=FULL, mode="z", L=250, frac=0.1, h=10,
         region_neutral=True),
    dict(id="B15", fam="xsec", regions=PART, mode="z", L=60, frac=0.2, h=5),
    dict(id="B16", fam="xsec", regions=PART, mode="z", L=60, frac=0.2, h=1),
    dict(id="B17", fam="xsec", regions=PART, mode="d1", frac=0.2, h=1),
    dict(id="B18", fam="xsec", regions=NONE, mode="z", L=60, frac=0.2, h=5),
    dict(id="B19", fam="xsec", regions=NONE, mode="z", L=60, frac=0.2, h=1),
    dict(id="B20", fam="xsec", regions=NONE, mode="d1", frac=0.2, h=1),
    dict(id="B21", fam="xsec", regions=FULL + PART + NONE, mode="z", L=60, frac=0.1, h=5,
         region_neutral=True),
    dict(id="B22", fam="xsec", regions=FULL + PART + NONE, mode="z", L=60, frac=0.1, h=1,
         region_neutral=True),
    dict(id="B23", fam="xsec", regions=FULL + PART + NONE, mode="twoscale", L=60, L2=250,
         frac=0.1, h=5, region_neutral=True),
    dict(id="B24", fam="xsec", regions=AR, mode="z", L=60, frac=0.2, h=5,
         note="Argentine CCL channel, tagged separately"),
    dict(id="B25", fam="xsec", regions=("CA",), mode="z", L=60, frac=0.5, h=20, zgate=2.0,
         note="wide-gate slow fade"),
    dict(id="B26", fam="xsec", regions=("CA",), mode="z", L=60, frac=0.1, h=5,
         etb_only=False, note="ETB screen OFF -- measures what the screen costs"),
]
assert len({f["id"] for f in FORMULAS}) == len(FORMULAS) == 30, len(FORMULAS)
