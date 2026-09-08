import sqlite3, json, hashlib, os, collections
OUT='/home/anont/meme/.scr2/step1.out'
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))

def h(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

wl=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
rows=wl.execute("select mint,creator,creator_onchain,create_slot,block_time,complete,bonding_curve,status from window_label").fetchall()
wl.close()
p("creates",len(rows))
# creator vs creator_onchain agreement
agree=sum(1 for r in rows if r[1]==r[2])
p("creator==creator_onchain", agree, "null creator", sum(1 for r in rows if not r[1]))

bycre=collections.defaultdict(list)
for m,cr,cro,slot,bt,comp,bc,st in rows:
    bycre[cr].append((bt,slot,m,comp,bc))
cnt=collections.Counter(len(v) for v in bycre.values())
p("launches-per-creator hist (n:creators)", sorted(cnt.items())[:30])
p("max launches", max(len(v) for v in bycre.values()))
multi=sum(1 for v in bycre.values() if len(v)>1)
p("creators with >1 launch", multi, "of", len(bycre))
p("coins by multi-launch creators", sum(len(v) for v in bycre.values() if len(v)>1))

oh=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
ohm=[r[0] for r in oh.execute("select mint from ohlcv where status='ok' and n_bars>0")]
oh.close()
p("ohlcv ok mints", len(ohm))
ohs=set(ohm)
hs=collections.Counter(h(m) for m in ohm)
p("ohlcv by h", dict(hs))

# for ohlcv mints in h1/h2: how many have >=1 prior launch by same creator
mintinfo={r[0]:(r[1],r[4]) for r in rows}  # mint -> creator, block_time
nprior=collections.Counter()
usable=0
for m in ohm:
    if h(m)==0: continue
    usable+=1
    ci=mintinfo.get(m)
    if not ci: nprior['NOLABEL']+=1; continue
    cr,bt=ci
    k=sum(1 for (bt2,s2,m2,c2,b2) in bycre[cr] if bt2<bt or (bt2==bt and m2<m))
    nprior[min(k,10)]+=1
p("usable(h1,2) ohlcv mints",usable)
p("n_prior_launch hist for those:", sorted((str(k),v) for k,v in nprior.items()))

# graduation rate overall
p("complete rate", sum(r[5] for r in rows)/len(rows))
open(OUT,'w').write("\n".join(o))
