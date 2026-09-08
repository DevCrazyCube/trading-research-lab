import json, hashlib, sqlite3, collections, os
ROOT='/home/anont/meme'
def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3
con=sqlite3.connect('file:%s/research/midcap/grad_ohlcv.sqlite?mode=ro'%ROOT,uri=True)
mints=[m for (m,) in con.execute("select mint from ohlcv where n_bars>0") if h3(m)!=0]
MY=set(mints); print('my mints',len(MY))
n=0; hit=0; keys=None; sample=None
with open(ROOT+'/research/midcap/fresh_snapshots.jsonl') as f:
    for line in f:
        n+=1
        try: d=json.loads(line)
        except Exception: continue
        if keys is None and 'mint' in d: keys=sorted(d.keys()); sample=d
        m=d.get('mint')
        if m in MY: hit+=1
print('lines',n,'hits',hit)
print('keys',keys)
print('sample',json.dumps(sample)[:600] if sample else None)
# window_labels join for MY mints only
wl=sqlite3.connect('file:%s/research/b11a/window_labels.sqlite?mode=ro'%ROOT,uri=True)
q='select mint,block_time,create_slot,complete,virtual_token_reserves,real_token_reserves,data_len from window_label where mint in (%s)'%(','.join('?'*len(mints)))
rows=wl.execute(q,mints).fetchall()
print('window_label matches',len(rows))
print(rows[:3])
# attention
ap=ROOT+'/research/midcap/attention.jsonl'
na=0; ah=0; ak=None
with open(ap) as f:
    for line in f:
        na+=1
        try: d=json.loads(line)
        except Exception: continue
        if ak is None: ak=sorted(d.keys())
        for k in ('mint','address','tokenAddress'):
            if d.get(k) in MY: ah+=1; break
print('attention lines',na,'hits',ah,'keys',ak)
