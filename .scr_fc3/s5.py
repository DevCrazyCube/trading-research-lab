import sqlite3, os, json, hashlib, collections, time

def hh(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3

t0 = time.time()
w = sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro', uri=True)
rows = [r for r in w.execute('select bonding_curve,mint,creator,create_slot,block_time,complete from window_label')
        if hh(r[1]) in (1, 2)]
w.close()
curves = {r[0]: r for r in rows}
mint2curve = {r[1]: r[0] for r in rows}

c = sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
orows = [r for r in c.execute("select mint,pool,n_bars,first_ts,last_ts,status from ohlcv")
         if hh(r[0]) in (1, 2) and r[5] == 'ok' and r[2]]
c.close()
trade_curves = set(mint2curve[r[0]] for r in orows if r[0] in mint2curve)
print('tradeable curves', len(trade_curves))

b = sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro', uri=True)
cnt = collections.Counter()
first = collections.defaultdict(list)
for r in b.execute('select slot,transaction_index,outer_index,inner_index,bonding_curve,virtual_quote_before,virtual_quote_after from reserve_observation'):
    bc = r[4]
    if bc in curves:
        cnt[bc] += 1
        if len(first[bc]) < 40:
            first[bc].append(r)
print('h12 curves with obs', len(cnt), 'tradeable curves with obs', len(trade_curves & set(cnt)))
print('elapsed', time.time() - t0)

# slot coverage of reserve_observation vs create_slot
obs_slots = [r[0] for v in first.values() for r in v]
print('obs slot range', min(obs_slots), max(obs_slots))
cs = [r[3] for r in rows]
print('create_slot range', min(cs), max(cs))

covered = sorted(curves[bc][4] for bc in cnt)
print('block_time range of covered curves', covered[0], covered[-1])

# instruction inspect
nam = collections.Counter()
shown = 0
for bc, rs in list(first.items()):
    for r in rs[:2]:
        ins = b.execute('select idl_name,accounts_json,program_id from instruction where slot=? and transaction_index=? and outer_index=? and inner_index=?',
                        (r[0], r[1], r[2], r[3])).fetchone()
        if not ins:
            nam['MISSING'] += 1
            continue
        nam[ins[0]] += 1
        if shown < 6:
            acc = json.loads(ins[1]) if ins[1] else []
            print(bc[:8], 'idl', ins[0], 'naccts', len(acc), 'vqb', r[5], 'vqa', r[6])
            print('   ', acc)
            shown += 1
    if len(nam) > 0 and sum(nam.values()) > 400:
        break
print('idl names', nam.most_common(20))
print('done', time.time() - t0)
b.close()
