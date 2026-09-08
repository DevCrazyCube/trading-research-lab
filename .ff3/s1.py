import sqlite3,hashlib,json,collections
o=open('/home/anont/meme/.ff3/step1.txt','w')
wl=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
rows=wl.execute("select bonding_curve,mint,creator,create_slot,block_time,complete from window_label").fetchall()
o.write("window_label rows %d\n"%len(rows))
allowed={}
h0=0
for bc,mint,cr,cs,bt,comp in rows:
    h=int(hashlib.md5(mint.encode()).hexdigest(),16)%3
    if h==0:
        h0+=1; continue
    allowed[bc]=(mint,cr,cs,bt,comp,h)
o.write("allowed curves %d (h0 excluded %d)\n"%(len(allowed),h0))
o.write("complete=1 in allowed %d\n"%sum(1 for v in allowed.values() if v[4]==1))
bts=[v[3] for v in allowed.values() if v[3]]
o.write("block_time range %s..%s\n"%(min(bts),max(bts)))
cs=[v[2] for v in allowed.values()]
o.write("slot range %s..%s\n"%(min(cs),max(cs)))
g=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
gm=g.execute("select mint,n_bars,status from ohlcv").fetchall()
o.write("ohlcv rows %d\n"%len(gm))
cnt=collections.Counter(s for _,_,s in gm)
o.write(str(cnt)+"\n")
gh=collections.Counter(int(hashlib.md5(m.encode()).hexdigest(),16)%3 for m,_,_ in gm)
o.write("ohlcv by h "+str(gh)+"\n")
mints_allowed=set(v[0] for v in allowed.values())
o.write("ohlcv mints in allowed-curve set: %d\n"%sum(1 for m,_,_ in gm if m in mints_allowed))
json.dump({bc:list(v) for bc,v in allowed.items()},open('/home/anont/meme/.ff3/allowed.json','w'))
o.close()
