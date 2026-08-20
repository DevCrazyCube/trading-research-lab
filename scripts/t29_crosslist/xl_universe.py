#!/usr/bin/env python3
"""Cross-listing / multi-ticker identical-claim universe.

MAPPING PROVENANCE: hand-curated. There is no free machine-readable ADR<->ordinary map
reachable from this host (no DTCC/BNYM/Citi ADR directory API, no Stooq -- Stooq serves a
JS proof-of-work challenge and then 'Access denied' to this IP even after the PoW is solved).
So the map below is written by hand from public knowledge of large, liquid ADR programmes.
It is therefore a CONVENIENCE-SAMPLE universe with a survivorship tilt toward programmes that
still exist today. Both facts are recorded in the result file rather than left implicit.

ADR RATIOS ARE NOT ENCODED. Every formula in this sweep works on a ROLLING-DEMEANED log
spread, so the ratio constant (and the pence/GBP factor, and any constant FX quoting error)
drops out of the z-score exactly. A wrong ratio cannot manufacture a signal; it can only
shift a constant that is subtracted back off.
"""

# region -> (yahoo suffix handled per-symbol, fx yahoo symbol converting LOCAL -> USD,
#            home close time in ET, notes)
REGIONS = {
    "CA":  {"fx": "CADUSD=X", "home_close_et": "16:00", "overlap": "full"},
    "BR":  {"fx": "BRLUSD=X", "home_close_et": "16:00", "overlap": "full"},
    "MX":  {"fx": "MXNUSD=X", "home_close_et": "15:00", "overlap": "full"},
    "AR":  {"fx": "ARSUSD=X", "home_close_et": "16:00", "overlap": "full"},
    "UK":  {"fx": "GBPUSD=X", "home_close_et": "11:30", "overlap": "partial"},
    "EU":  {"fx": "EURUSD=X", "home_close_et": "11:30", "overlap": "partial"},
    "CH":  {"fx": "CHFUSD=X", "home_close_et": "11:30", "overlap": "partial"},
    "DK":  {"fx": "DKKUSD=X", "home_close_et": "11:00", "overlap": "partial"},
    "IL":  {"fx": "ILSUSD=X", "home_close_et": "10:25", "overlap": "partial"},
    "JP":  {"fx": "JPYUSD=X", "home_close_et": "02:00", "overlap": "none"},
    "KR":  {"fx": "KRWUSD=X", "home_close_et": "02:30", "overlap": "none"},
    "TW":  {"fx": "TWDUSD=X", "home_close_et": "01:30", "overlap": "none"},
    "HK":  {"fx": "HKDUSD=X", "home_close_et": "04:00", "overlap": "none"},
    "IN":  {"fx": "INRUSD=X", "home_close_et": "06:00", "overlap": "none"},
    "AU":  {"fx": "AUDUSD=X", "home_close_et": "02:00", "overlap": "none"},
}

# us_ticker -> (yahoo home ticker, region)
ADR_MAP = {
    # ---- Canada: TSX and NYSE/NASDAQ sessions are IDENTICAL (09:30-16:00 ET).
    # This is the only bloc where the daily-close spread is a genuinely CONTEMPORANEOUS
    # identical-claim mispricing rather than a stale-price gap.
    "SHOP": ("SHOP.TO", "CA"), "CNQ": ("CNQ.TO", "CA"), "SU": ("SU.TO", "CA"),
    "ENB": ("ENB.TO", "CA"), "TRP": ("TRP.TO", "CA"), "BCE": ("BCE.TO", "CA"),
    "RY": ("RY.TO", "CA"), "TD": ("TD.TO", "CA"), "BNS": ("BNS.TO", "CA"),
    "BMO": ("BMO.TO", "CA"), "CM": ("CM.TO", "CA"), "MFC": ("MFC.TO", "CA"),
    "SLF": ("SLF.TO", "CA"), "GOLD": ("ABX.TO", "CA"), "AEM": ("AEM.TO", "CA"),
    "WPM": ("WPM.TO", "CA"), "FNV": ("FNV.TO", "CA"), "CP": ("CP.TO", "CA"),
    "CNI": ("CNR.TO", "CA"), "TRI": ("TRI.TO", "CA"), "NTR": ("NTR.TO", "CA"),
    "CVE": ("CVE.TO", "CA"), "IMO": ("IMO.TO", "CA"), "PBA": ("PPL.TO", "CA"),
    "QSR": ("QSR.TO", "CA"), "WCN": ("WCN.TO", "CA"), "TECK": ("TECK-B.TO", "CA"),
    "OTEX": ("OTEX.TO", "CA"), "CCJ": ("CCO.TO", "CA"), "AGI": ("AGI.TO", "CA"),
    "PAAS": ("PAAS.TO", "CA"), "KGC": ("K.TO", "CA"), "IAG": ("IMG.TO", "CA"),
    "EQX": ("EQX.TO", "CA"), "HBM": ("HBM.TO", "CA"), "NGD": ("NGD.TO", "CA"),
    "SSRM": ("SSRM.TO", "CA"), "MAG": ("MAG.TO", "CA"), "DNN": ("DML.TO", "CA"),
    "NXE": ("NXE.TO", "CA"), "ERF": ("ERF.TO", "CA"), "VET": ("VET.TO", "CA"),
    "CPG": ("CPG.TO", "CA"), "BTE": ("BTE.TO", "CA"), "LAC": ("LAC.TO", "CA"),
    "TFPM": ("TFPM.TO", "CA"), "BAM": ("BAM.TO", "CA"), "BN": ("BN.TO", "CA"),
    "GIB": ("GIB-A.TO", "CA"), "DOOO": ("DOO.TO", "CA"), "MGA": ("MG.TO", "CA"),
    "STN": ("STN.TO", "CA"), "CIGI": ("CIGI.TO", "CA"), "FSV": ("FSV.TO", "CA"),
    "RBA": ("RBA.TO", "CA"), "WFG": ("WFG.TO", "CA"), "CLS": ("CLS.TO", "CA"),
    "BLDP": ("BLDP.TO", "CA"), "NVEI": ("NVEI.TO", "CA"), "TIXT": ("TIXT.TO", "CA"),
    "ATHR": ("ATH.TO", "CA"), "SAND": ("SSL.TO", "CA"), "OR": ("OR.TO", "CA"),
    "FSM": ("FVI.TO", "CA"), "GATO": ("GTO.TO", "CA"), "ELD": ("ELD.TO", "CA"),
    "SVM": ("SVM.TO", "CA"), "AUY": ("YRI.TO", "CA"), "BTG": ("BTO.TO", "CA"),
    "TRQ": ("TRQ.TO", "CA"), "SW": ("SW.TO", "CA"),
    # ---- Brazil: B3 09:00-16:00 ET -- effectively simultaneous with the US session.
    "VALE": ("VALE3.SA", "BR"), "ITUB": ("ITUB4.SA", "BR"), "BBD": ("BBDC4.SA", "BR"),
    "ABEV": ("ABEV3.SA", "BR"), "GGB": ("GGBR4.SA", "BR"), "BSBR": ("SANB11.SA", "BR"),
    "ERJ": ("EMBR3.SA", "BR"), "SBS": ("SBSP3.SA", "BR"), "BRFS": ("BRFS3.SA", "BR"),
    "CSAN": ("CSAN3.SA", "BR"), "SUZ": ("SUZB3.SA", "BR"), "PBR": ("PETR3.SA", "BR"),
    "PBR.A": ("PETR4.SA", "BR"), "CIG": ("CMIG4.SA", "BR"), "ELP": ("CPLE6.SA", "BR"),
    "UGP": ("UGPA3.SA", "BR"), "VIV": ("VIVT3.SA", "BR"), "BBDO": ("BBDC3.SA", "BR"),
    "ITUP": ("ITUB3.SA", "BR"),
    # ---- Mexico: BMV 08:30-15:00 ET.
    "AMX": ("AMXB.MX", "MX"), "FMX": ("FEMSAUBD.MX", "MX"), "KOF": ("KOFUBL.MX", "MX"),
    "TV": ("TLEVISACPO.MX", "MX"), "CX": ("CEMEXCPO.MX", "MX"),
    # ---- UK (prices in GBp; the rolling demean absorbs the 100x).
    "BP": ("BP.L", "UK"), "SHEL": ("SHEL.L", "UK"), "HSBC": ("HSBA.L", "UK"),
    "GSK": ("GSK.L", "UK"), "AZN": ("AZN.L", "UK"), "UL": ("ULVR.L", "UK"),
    "RIO": ("RIO.L", "UK"), "BTI": ("BATS.L", "UK"), "DEO": ("DGE.L", "UK"),
    "NGG": ("NG.L", "UK"), "VOD": ("VOD.L", "UK"), "LYG": ("LLOY.L", "UK"),
    "BCS": ("BARC.L", "UK"), "PUK": ("PRU.L", "UK"), "RELX": ("REL.L", "UK"),
    "IHG": ("IHG.L", "UK"), "AMCR": ("AMC.AX", "AU"),
    # ---- Continental Europe.
    "ING": ("INGA.AS", "EU"), "ASML": ("ASML.AS", "EU"), "PHG": ("PHIA.AS", "EU"),
    "STLA": ("STLAM.MI", "EU"), "TTE": ("TTE.PA", "EU"), "SNY": ("SAN.PA", "EU"),
    "SAP": ("SAP.DE", "EU"), "DB": ("DBK.DE", "EU"), "SAN": ("SAN.MC", "EU"),
    "BBVA": ("BBVA.MC", "EU"), "TEF": ("TEF.MC", "EU"), "E": ("ENI.MI", "EU"),
    "NVS": ("NOVN.SW", "CH"), "UBS": ("UBSG.SW", "CH"), "NVO": ("NOVO-B.CO", "DK"),
    # ---- Japan / Korea / Taiwan / HK / India / Australia: home close PRECEDES the US
    # session, so the close-to-close spread is a STALE-PRICE gap, not a simultaneous one.
    "TM": ("7203.T", "JP"), "SONY": ("6758.T", "JP"), "MUFG": ("8306.T", "JP"),
    "SMFG": ("8316.T", "JP"), "MFG": ("8411.T", "JP"), "HMC": ("7267.T", "JP"),
    "NMR": ("8604.T", "JP"),
    "KB": ("105560.KS", "KR"), "SKM": ("017670.KS", "KR"), "LPL": ("034220.KS", "KR"),
    "PKX": ("005490.KS", "KR"), "KEP": ("015760.KS", "KR"),
    "TSM": ("2330.TW", "TW"), "UMC": ("2303.TW", "TW"), "CHT": ("2412.TW", "TW"),
    "ASX": ("3711.TW", "TW"),
    "BABA": ("9988.HK", "HK"), "JD": ("9618.HK", "HK"), "NTES": ("9999.HK", "HK"),
    "BIDU": ("9888.HK", "HK"), "LI": ("2015.HK", "HK"), "XPEV": ("9868.HK", "HK"),
    "NIO": ("9866.HK", "HK"), "TCOM": ("9961.HK", "HK"), "BILI": ("9626.HK", "HK"),
    "ZTO": ("2057.HK", "HK"), "YUMC": ("9987.HK", "HK"), "HTHT": ("1179.HK", "HK"),
    "BEKE": ("2423.HK", "HK"),
    "INFY": ("INFY.NS", "IN"), "HDB": ("HDFCBANK.NS", "IN"), "IBN": ("ICICIBANK.NS", "IN"),
    "WIT": ("WIPRO.NS", "IN"), "RDY": ("DRREDDY.NS", "IN"),
    "BHP": ("BHP.AX", "AU"), "WDS": ("WDS.AX", "AU"),
    # ---- Israel (TASE closes 10:25 ET).
    "TEVA": ("TEVA.TA", "IL"), "NICE": ("NICE.TA", "IL"), "ICL": ("ICL.TA", "IL"),
    "ESLT": ("ESLT.TA", "IL"), "CAMT": ("CAMT.TA", "IL"),
    # ---- Argentina: the ADR premium here is the 'contado con liqui' FX-control channel,
    # not a convergence trade. Carried, but tagged AR and excluded from the headline blocs.
    "GGAL": ("GGAL.BA", "AR"), "YPF": ("YPFD.BA", "AR"), "BMA": ("BMA.BA", "AR"),
    "PAM": ("PAMP.BA", "AR"), "TEO": ("TECO2.BA", "AR"), "CRESY": ("CRES.BA", "AR"),
    "EDN": ("EDN.BA", "AR"), "SUPV": ("SUPV.BA", "AR"), "LOMA": ("LOMA.BA", "AR"),
    "BBAR": ("BBAR.BA", "AR"), "TGS": ("TGSU2.BA", "AR"), "IRS": ("IRSA.BA", "AR"),
}

# Pairs where BOTH legs are US-listed and carry the SAME economic claim.
# These are the only fully-tradable RV pairs in this sub-family: a dual-listed-company
# (DLC) structure, or two ADR lines on the same foreign issuer's two share classes.
# Deliberately EXCLUDES the domestic dual-class-voting pairs already tested in T28.
US_US_PAIRS = [
    ("CCL",   "CUK",    "DLC Carnival Corp & plc"),
    ("BBL",   "BHP",    "DLC BHP Billiton plc/Ltd (unified Jan 2022)"),
    ("RDS.A", "RDS.B",  "DLC Royal Dutch Shell A/B (unified Jan 2022)"),
    ("UN",    "UL",     "DLC Unilever NV/plc (unified Nov 2020)"),
    ("RENX",  "RELX",   "DLC RELX NV/plc (unified 2018)"),
    ("ENL",   "RUK",    "DLC Reed Elsevier NV/plc"),
    ("AMX",   "AMOV",   "America Movil L vs A ADR"),
    ("PBR",   "PBR.A",  "Petrobras ON vs PN ADR"),
    ("CIG",   "CIG.C",  "Cemig ON vs PN ADR"),
    ("ELP",   "ELPC",   "Copel ON vs PNB ADR"),
    ("SID",   "SIDD",   "CSN (probe)"),
    ("TV",    "TVAA",   "Televisa (probe)"),
]

US_SYMBOLS = sorted(set(ADR_MAP) | {s for p in US_US_PAIRS for s in p[:2]})
HOME_SYMBOLS = sorted({v[0] for v in ADR_MAP.values()})
FX_SYMBOLS = sorted({v["fx"] for v in REGIONS.values()})
COUNTRY_ETF = {"CA": "EWC", "BR": "EWZ", "MX": "EWW", "UK": "EWU", "EU": "VGK",
               "CH": "EWL", "DK": "EDEN", "IL": "EIS", "JP": "EWJ", "KR": "EWY",
               "TW": "EWT", "HK": "MCHI", "IN": "INDA", "AU": "EWA", "AR": "ARGT"}

if __name__ == "__main__":
    print("US symbols", len(US_SYMBOLS), "home", len(HOME_SYMBOLS), "fx", len(FX_SYMBOLS))
