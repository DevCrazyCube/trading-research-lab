#!/usr/bin/env python3
"""Holdco / corporate-structure RV universe.

Four structurally distinct groups, all with an EXPLICIT identical-claim or known-ratio link:

  P  paired-entity / dual-listed-company / holdco-of-one-asset structures whose two listed
     lines are economically the SAME claim with a stated (usually 1:1) exchange right.
  H  holdco (or tracking stock) whose dominant asset is a LISTED stake in a named subsidiary.
     Ratio drifts with buybacks/issuance, so it is estimated, never asserted.
  S  post-spinoff parent/child pair.  NOT an identical claim -- the two are different
     businesses after separation.  Included because the brief asks for the PAIR-RV even
     though the DRIFT is dead; flagged as the weakest structural link of the four.
  M  stock-for-stock merger deal-ratio spread.  Target is contractually convertible into
     `ratio` acquirer shares (+ `cash` per share) on closing, so the identical-claim link is
     the strongest in the file -- conditional on the deal closing.

Dates are announcement / termination-or-close dates.  Ratios are the FINAL exchange ratios.
Every one of these is a fixed constant known on the announcement date except where noted.
"""

# ---------------------------------------------------------------- group P
# (a, b, stated_ratio a_per_b, note)   spread anchor = log(Pa/Pb) - log(ratio)
GROUP_P = [
    ("BIPC", "BIP", 1.0, "BIPC exchangeable 1:1 into BIP units at holder's option"),
    ("BEPC", "BEP", 1.0, "BEPC exchangeable 1:1 into BEP units at holder's option"),
    ("BAMR", "BAM", 1.0, "BAM Reinsurance 1:1 exchangeable into BAM (2021-06..2022-12)"),
    ("BBL", "BHP", 1.0, "BHP DLC: Plc vs Ltd ADR, both = 2 ordinary, same dividend"),
    ("RDS.A", "RDS.B", 1.0, "Shell DLC A/B ADR, same economics, different divi withholding"),
    ("UN", "UL", 1.0, "Unilever NV/PLC DLC ADRs, equalisation agreement (to 2020-11)"),
    ("PAGP", "PAA", 1.0, "PAGP's only asset is PAA units; ~1:1 look-through"),
]

# ---------------------------------------------------------------- group H
# (holdco, listed_stake, note)   ratio ESTIMATED, not asserted
GROUP_H = [
    ("LBRDA", "CHTR", "Liberty Broadband: ~0.6 CHTR/share, drifts with buybacks"),
    ("LBRDK", "CHTR", "same, non-voting line"),
    ("LSXMA", "SIRI", "Liberty SiriusXM tracker on ~83% of SIRI"),
    ("LSXMK", "SIRI", "same, non-voting line"),
    ("LTRPA", "TRIP", "Liberty TripAdvisor: ~2.2 TRIP/share"),
    ("DVMT", "VMW", "Dell Class V tracking stock ON VMware economics (2016-09..2018-12)"),
    ("DELL", "VMW", "Dell held ~81% of VMware (2018-12..2021-11 spin)"),
    ("IAC", "MTCH", "IAC held ~80% of Match to 2020-06"),
    ("IAC", "ANGI", "IAC held ~84% of ANGI to 2020"),
    ("L", "CNA", "Loews holds ~90% of CNA Financial"),
    ("IEP", "CVI", "Icahn Enterprises holds ~71% of CVR Energy"),
    ("FMX", "KOF", "FEMSA holds ~47% of Coca-Cola FEMSA, both NYSE ADR"),
    ("HRG", "SPB", "Harbinger held ~62% of Spectrum Brands (to 2018-07)"),
    ("BN", "BAM", "Brookfield Corp holds ~73% of Brookfield Asset Mgmt (2022-12+)"),
    ("NVST", "DHR", "Danaher retained ~80% of Envista Sep-Dec 2019 (short window)"),
]

# ---------------------------------------------------------------- group S
# (parent, child, spin_date)
GROUP_S = [
    ("EBAY", "PYPL", "2015-07-20"), ("HPQ", "HPE", "2015-11-02"),
    ("HPE", "DXC", "2017-04-03"), ("ASH", "VVV", "2017-05-15"),
    ("AA", "HWM", "2016-11-01"), ("CAG", "LW", "2016-11-10"),
    ("TNL", "WH", "2018-06-01"), ("DD", "DOW", "2019-04-02"),
    ("DD", "CTVA", "2019-06-03"), ("DOW", "CTVA", "2019-06-03"),
    ("RTX", "CARR", "2020-04-03"), ("RTX", "OTIS", "2020-04-03"),
    ("CARR", "OTIS", "2020-04-03"),
    ("DHR", "VNT", "2020-10-01"), ("DHR", "VLTO", "2023-10-02"),
    ("PFE", "VTRS", "2020-11-16"), ("MRK", "OGN", "2021-06-03"),
    ("IBM", "KD", "2021-11-04"), ("IP", "SLVM", "2021-10-01"),
    ("T", "WBD", "2022-04-11"), ("BDX", "EMBC", "2022-04-01"),
    ("GE", "GEHC", "2023-01-04"), ("GE", "GEV", "2024-04-02"),
    ("GEHC", "GEV", "2024-04-02"),
    ("JNJ", "KVUE", "2023-08-23"), ("MMM", "SOLV", "2024-04-01"),
    ("BWA", "PHIN", "2023-07-03"), ("CMI", "ATMU", "2023-05-19"),
    ("ENOV", "ESAB", "2022-04-05"), ("WDC", "SNDK", "2025-02-24"),
    ("XRX", "CNDT", "2017-01-03"), ("MET", "BHF", "2017-08-07"),
    ("XPO", "GXO", "2021-08-02"), ("XPO", "RXO", "2022-11-01"),
    ("DD", "CC", "2015-07-01"), ("APTV", "DLPH", "2017-12-05"),
    ("HON", "GTX", "2018-10-01"), ("HON", "REZI", "2018-10-29"),
    ("HLT", "HGV", "2017-01-04"), ("HLT", "PK", "2017-01-04"),
]

# ---------------------------------------------------------------- group M
# (target, acquirer, ratio_acq_per_tgt, cash_per_tgt, announce, end, closed?)
GROUP_M = [
    ("XLNX", "AMD",   1.7234, 0.0,   "2020-10-27", "2022-02-11", True),
    ("PXD",  "XOM",   2.3234, 0.0,   "2023-10-11", "2024-05-02", True),
    ("HES",  "CVX",   1.0250, 0.0,   "2023-10-23", "2025-07-17", True),
    ("PDCE", "CVX",   0.4638, 0.0,   "2023-05-22", "2023-08-07", True),
    ("MRO",  "COP",   0.2550, 0.0,   "2024-05-29", "2024-11-21", True),
    ("SWN",  "CHK",   0.0867, 0.0,   "2024-01-11", "2024-09-30", True),
    ("CXO",  "COP",   1.4500, 0.0,   "2020-10-19", "2021-01-15", True),
    ("PE",   "PXD",   0.1252, 0.0,   "2020-10-20", "2021-01-12", True),
    ("WPX",  "DVN",   0.5165, 0.0,   "2020-09-28", "2021-01-06", True),
    ("NBL",  "CVX",   0.1191, 0.0,   "2020-07-20", "2020-10-02", True),
    ("MXIM", "ADI",   0.6300, 0.0,   "2020-07-13", "2021-08-25", True),
    ("RTN",  "UTX",   2.3348, 0.0,   "2019-06-09", "2020-04-02", True),
    # ("STI","BBT",1.295,...) DROPPED: Alpaca's STI is Solidion Technology (2022+) and its
    # BBT is Beacon Financial, not SunTrust/BB&T.  Verified by price level, see census.
    # ("AMTD","SCHW",...) kept: AMTD price levels in 2019-20 DO match TD Ameritrade.
    ("AMTD", "SCHW",  1.0837, 0.0,   "2019-11-25", "2020-10-05", True),
    ("RSPP", "CXO",   1.9375, 0.0,   "2018-03-28", "2018-07-18", True),
    ("ANDV", "MPC",   1.8700, 0.0,   "2018-04-30", "2018-09-28", True),
    ("XEC",  "COG",   4.0146, 0.0,   "2021-05-24", "2021-09-30", True),
    ("CELG", "BMY",   1.0000, 50.0,  "2019-01-03", "2019-11-20", True),
    ("LLL",  "HRS",   1.3000, 0.0,   "2018-10-14", "2019-06-28", True),
    ("TSS",  "GPN",   0.8101, 0.0,   "2019-05-28", "2019-09-17", True),
    ("WCG",  "CNC",   3.3800, 120.0, "2019-03-27", "2020-01-23", True),
    ("ESRX", "CI",    0.2434, 48.75, "2018-03-08", "2018-12-20", True),
    ("AET",  "CVS",   0.8378, 145.0, "2017-12-03", "2018-11-28", True),
    ("VMW",  "AVGO",  0.2520, 0.0,   "2022-05-26", "2023-11-21", True),
    ("ALXN", "AZN",   2.1243, 60.0,  "2020-12-12", "2021-07-20", True),
    ("VIAB", "CBS",   0.59625, 0.0,  "2019-08-13", "2019-12-03", True),
    ("ATH",  "APO",   1.1490, 0.0,   "2021-03-08", "2021-12-31", True),
    ("ETFC", "MS",    1.0432, 0.0,   "2020-02-20", "2020-10-01", True),
    ("TCF",  "HBAN",  3.0028, 0.0,   "2020-12-13", "2021-06-08", True),
    ("PBCT", "MTB",   0.1180, 0.0,   "2021-02-22", "2022-03-31", True),
    ("CIT",  "FCNCA", 0.0620, 0.0,   "2020-10-16", "2022-01-03", True),
    ("UMPQ", "COLB",  0.5958, 0.0,   "2021-10-12", "2023-02-27", True),
    ("PACW", "BANC",  0.6569, 0.0,   "2023-07-25", "2023-11-29", True),
    ("CPE",  "APA",   1.0425, 0.0,   "2024-01-04", "2024-03-28", True),
    ("ANSS", "SNPS",  0.3450, 197.0, "2024-01-16", "2025-07-16", True),
    # ("DD","DOW",1.282,2015-12-11,2017-08-30) DROPPED: Alpaca's DOW carries Dow Chemical's
    # last price FLAT from 2017-08 to 2019-04-01 then becomes Dow Inc.  Unusable.
]


# Per-symbol validity windows.  Alpaca serves a series BY TICKER and stitches successive
# occupants of the same ticker together, sometimes carrying a stale price forward.  Verified
# against known price levels; see the census in the DEEPMINE writeup.
VALID = {
    "DOW":  ("2019-04-02", "2099-01-01"),   # flat-carried Dow Chemical price before this
    "LLL":  ("2000-01-01", "2019-06-28"),   # stitched to L3Harris after
    "AMTD": ("2000-01-01", "2020-10-05"),   # AMTD IDEA Group occupies the ticker after
    "UN":   ("2000-01-01", "2020-11-27"),   # "Corgi UNH 2x Daily ETF" occupies it in 2026
}
EXCLUDE = {"BBT", "STI"}                    # wrong issuer over the whole sample


def all_symbols():
    s = set()
    for a, b, _r, _n in GROUP_P:
        s |= {a, b}
    for a, b, _n in GROUP_H:
        s |= {a, b}
    for a, b, _d in GROUP_S:
        s |= {a, b}
    for t, q, _r, _c, _a, _e, _k in GROUP_M:
        s |= {t, q}
    return sorted(s)


if __name__ == "__main__":
    print(len(all_symbols()), "symbols")
    print(len(GROUP_P), "P /", len(GROUP_H), "H /", len(GROUP_S), "S /", len(GROUP_M), "M")
