import sqlite3, json, hashlib, os
from collections import Counter, defaultdict
OUT = open('/home/anont/meme/.scratch_fc/p2.txt','w')
def P(*a): print(*a, file=OUT)
def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16) % 3
def conn(p): return sqlite3.connect('file:%s?mode=ro'%p, uri=True)

# window_label restricted to h in (1,2)
c = conn('/home/anont/meme/research/b11a/window_labels.sqlite')
rows = c.execute("select mint,creator,block_time,complete,create_slot from window_label").fetchall()
c.close()
wl = [r for r in rows if r[0] and h3(r[0]) != 0]
P('window_label total rows', len(rows), 'h12 rows', len(wl))
del rows

bycre = defaultdict(list)
for m,cr,bt,comp,slot in wl:
    bycre[cr].append((bt,slot,m,comp))
P('creators (h12)', len(bycre))
cnt = Counter(len(v) for v in bycre.values())
P('launches-per-creator dist (h12):', sorted(cnt.items())[:25])
P('  creators with >=2:', sum(v for k,v in cnt.items() if k>=2), 'coins in them:', sum(k*v for k,v in cnt.items() if k>=2))
P('  creators with >=3:', sum(v for k,v in cnt.items() if k>=3))
P('  max launches', max(cnt))

# ohlcv universe
c = conn('/home/anont/meme/research/midcap/grad_ohlcv.sqlite')
oh = c.execute("select mint,n_bars,status from ohlcv").fetchall()
c.close()
ok = [r for r in oh if r[2]=='ok' and r[1] and r[1]>0]
P('ohlcv ok mints', len(ok))
ok12 = [r for r in ok if h3(r[0])!=0]
P('ohlcv ok h12', len(ok12))
P('  h==1', sum(1 for r in ok12 if h3(r[0])==1), 'h==2', sum(1 for r in ok12 if h3(r[0])==2))
wlmints = set(m for m,cr,bt,comp,slot in wl)
inwl = [r for r in ok12 if r[0] in wlmints]
P('ohlcv h12 present in window_label', len(inwl))
P('  bars total for those', sum(r[1] for r in inwl))
# how many of those have a creator with prior launches
cr_of = {m:cr for m,cr,bt,comp,slot in wl}
bt_of = {m:bt for m,cr,bt,comp,slot in wl}
npri = Counter()
for m,nb,st in inwl:
    cr = cr_of[m]; bt = bt_of[m]
    k = sum(1 for (b,s,mm,cp) in bycre[cr] if b < bt)
    npri[k]+=1
P('prior-launch count dist among tradeable h12 mints:', sorted(npri.items()))
OUT.close()
