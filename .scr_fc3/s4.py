import sqlite3, os, json, hashlib, collections, time

def hh(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3

t0 = time.time()
w = sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro', uri=True)
rows = [r for r in w.execute('select bonding_curve,mint,creator,create_slot,block_time,complete from window_label')
        if hh(r[1]) in (1, 2)]
w.close()
curves = {r[0]: r for r in rows}
print('h12 curves', len(curves), time.time() - t0)

b = sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro', uri=True)
b.execute('pragma mmap_size=0')
n = b.execute('select count(*) from reserve_observation').fetchone()[0]
print('reserve_observation rows', n, time.time() - t0)

# scan all reserve_observation, keep those on h12 curves
cnt = collections.Counter()
first = collections.defaultdict(list)
q = b.execute('select slot,transaction_index,outer_index,inner_index,bonding_curve,virtual_quote_before,virtual_quote_after from reserve_observation')
kept = 0
for r in q:
    bc = r[4]
    if bc in curves:
        kept += 1
        cnt[bc] += 1
        if len(first[bc]) < 25:
            first[bc].append(r)
print('rows on h12 curves', kept, 'curves touched', len(cnt), time.time() - t0)
tr = sorted(cnt.values())
print('trades per curve: n=%d min=%d med=%d max=%d' % (len(tr), tr[0], tr[len(tr)//2], tr[-1]))

# sample instruction lookup
sample = list(first.items())[:3]
for bc, rs in sample:
    for r in rs[:3]:
        ins = b.execute('select idl_name,accounts_json,program_id from instruction where slot=? and transaction_index=? and outer_index=? and inner_index=?',
                        (r[0], r[1], r[2], r[3])).fetchone()
        if ins:
            acc = json.loads(ins[1]) if ins[1] else []
            print(bc[:8], r[0], ins[0], 'naccts', len(acc), 'dq', r[6] - r[5])
            print('   accts', acc[:16])
        else:
            print(bc[:8], r[0], 'NO INSTRUCTION ROW')
print('done', time.time() - t0)
b.close()
