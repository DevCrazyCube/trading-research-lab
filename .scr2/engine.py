"""Exhaustive sweep engine: TIMING x POSITION x EXIT simulated per mint,
creator ENTRY FILTERS applied post-hoc (they are static per mint, so the
within-mint simulation is independent of them).

Harness contract:
 A. signal on bar i -> enter at OPEN of bar i+1 (next REAL bar).
 B. one open position per mint at a time (no overlap).
 C. mint-equal weighting for every headline number.
 D. dropouts charged at -30 / -50 / -100 %.
 E. toll 1.14% round trip, also 2.5%.
 F. simple returns.
 G. no conditioning on bar count / trade count / continued listing.
"""
import pickle, bisect, math, sys, os, time, json

SCR = '/home/anont/meme/.scr2'
D = pickle.load(open(SCR + '/data.pkl', 'rb'))
BARS = D['bars']; FEAT = D['feat']; META = D['meta']
MINTS = sorted(BARS)

# ---- pack bars ----
PK = {}
for m in MINTS:
    b = BARS[m]
    PK[m] = (
        [r[0] for r in b], [r[1] for r in b], [r[2] for r in b],
        [r[3] for r in b], [r[4] for r in b], len(b))

TOLL_A = 0.0114
TOLL_B = 0.025

# ---------------- grids ----------------
TIMINGS = [
    ('first',        ('first', 0)),
    ('age15',        ('age', 900)),
    ('age60',        ('age', 3600)),
    ('age240',       ('age', 14400)),
    ('allbars',      ('all', 0)),
    ('allbars_a60',  ('all', 3600)),
]
POSITIONS = [
    ('p_single',   ((1.0, 0),)),
    ('p_50_50_5',  ((0.5, 0), (0.5, 5))),
    ('p_50_50_15', ((0.5, 0), (0.5, 15))),
    ('p_25_75_10', ((0.25, 0), (0.75, 10))),
    ('p_3x_0_5_15',((1/3., 0), (1/3., 5), (1/3., 15))),
]
HOLDS = [2, 5, 15, 30, 60, 180, 480, 1440]
MODS = [
    ('m_plain',   dict()),
    ('m_tp30',    dict(tp=0.30)),
    ('m_tp50',    dict(tp=0.50)),
    ('m_tp100',   dict(tp=1.00)),
    ('m_tp200',   dict(tp=2.00)),
    ('m_tp400',   dict(tp=4.00)),
    ('m_sl20',    dict(sl=-0.20)),
    ('m_sl35',    dict(sl=-0.35)),
    ('m_sl60',    dict(sl=-0.60)),
    ('m_tr25',    dict(trail=0.25)),
    ('m_tr40',    dict(trail=0.40)),
    ('m_tp100sl50', dict(tp=1.00, sl=-0.50)),
    ('m_half50',  dict(ptp=0.50, pfrac=0.5)),
]

# ---------------- per-mint simulator ----------------
def sim_mint(m, timing, position, hold, mod):
    ts, op, hi, lo, cl, n = PK[m]
    t0 = ts[0]
    tk, targ = timing
    if tk == 'first':
        sig = [0]
    elif tk == 'age':
        i = bisect.bisect_left(ts, t0 + targ)
        if i >= n: return None
        sig = [i]
    else:
        if targ:
            i0 = bisect.bisect_left(ts, t0 + targ)
        else:
            i0 = 0
        sig = range(i0, n)

    tp = mod.get('tp'); sl = mod.get('sl'); trail = mod.get('trail')
    ptp = mod.get('ptp'); pfrac = mod.get('pfrac', 0.0)
    hs = hold * 60

    rets = []           # gross returns of resolved trades
    ndrop = 0
    busy = -1
    for i in sig:
        j = i + 1
        if j >= n: break
        te = ts[j]
        if te < busy: continue
        # ---- tranches ----
        tot_w = 0.0; tot_tok = 0.0; klast = j
        for w, d in position:
            if d == 0:
                k = j
            else:
                k = bisect.bisect_left(ts, te + d * 60, j)
                if k >= n: break
            tot_w += w; tot_tok += w / op[k]
            if k > klast: klast = k
        if tot_tok <= 0: continue
        epx = tot_w / tot_tok
        # ---- exit scan ----
        eidx = bisect.bisect_left(ts, te + hs, klast)
        last = (eidx if eidx < n else n - 1)
        tp_px = epx * (1 + tp) if tp else None
        sl_px = epx * (1 + sl) if sl else None
        ptp_px = epx * (1 + ptp) if ptp else None
        rh = 0.0
        exit_px = None
        exit_b = None
        part = 0.0          # realised partial pnl contribution
        pdone = False
        for b in range(klast, last + 1):
            exit_b = b
            # trailing uses the high BEFORE this bar (no same-bar lookahead)
            if trail and rh > 0:
                tl = rh * (1 - trail)
                if lo[b] <= tl:
                    exit_px = min(tl, op[b]); break
            if sl_px is not None and lo[b] <= sl_px:
                exit_px = min(sl_px, op[b]); break
            if tp_px is not None and hi[b] >= tp_px:
                exit_px = max(tp_px, op[b]); break
            if ptp_px is not None and not pdone and hi[b] >= ptp_px:
                px = max(ptp_px, op[b])
                part = pfrac * (px / epx - 1.0); pdone = True
            if hi[b] > rh: rh = hi[b]
        if exit_px is None:
            if eidx < n:
                exit_px = op[eidx]; exit_b = eidx
            else:
                ndrop += 1
                busy = float('inf')
                break
        rem = (1.0 - pfrac) if pdone else 1.0
        g = part + rem * (exit_px / epx - 1.0)
        rets.append(g)
        busy = ts[exit_b]
    nt = len(rets) + ndrop
    if nt == 0: return None
    return (rets, ndrop)


def agg(res, toll, dropcharge):
    rets, ndrop = res
    s = 0.0
    for g in rets:
        s += (1.0 + g) * (1.0 - toll) - 1.0
    s += ndrop * dropcharge
    return s / (len(rets) + ndrop)


def main():
    t_start = time.time()
    out = {}
    combos = 0
    total = len(TIMINGS) * len(POSITIONS) * len(HOLDS) * len(MODS)
    done = 0
    for tname, timing in TIMINGS:
        for pname, position in POSITIONS:
            for hold in HOLDS:
                for mname, mod in MODS:
                    key = (tname, pname, hold, mname)
                    per = {}
                    for m in MINTS:
                        r = sim_mint(m, timing, position, hold, mod)
                        if r is None: continue
                        rets, ndrop = r
                        per[m] = (
                            agg(r, TOLL_A, -0.30),
                            agg(r, TOLL_A, -0.50),
                            agg(r, TOLL_A, -1.00),
                            agg(r, TOLL_B, -0.30),
                            len(rets) + ndrop,
                            len(rets),
                        )
                    out[key] = per
                    done += 1
                    if done % 100 == 0:
                        open(SCR + '/engine.progress', 'w').write(
                            "%d/%d  %.1fs\n" % (done, total, time.time() - t_start))
    with open(SCR + '/sims.pkl', 'wb') as fh:
        pickle.dump(out, fh, protocol=4)
    open(SCR + '/engine.out', 'w').write(
        "sims=%d mints=%d elapsed=%.1fs\n" % (len(out), len(MINTS), time.time() - t_start))

if __name__ == '__main__':
    main()
