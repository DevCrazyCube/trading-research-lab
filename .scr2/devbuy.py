import sqlite3, pickle, collections, json, time, hashlib
SCR='/home/anont/meme/.scr2'
D=pickle.load(open(SCR+'/data.pkl','rb'))
META=D['meta']; BARS=D['bars']
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))

wl=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
rows=wl.execute("select bonding_curve,mint,creator,create_slot,block_time from window_label").fetchall()
wl.close()
bc2=dict((r[0],(r[1],r[2],r[3],r[4])) for r in rows)
ourcre=set(META[m]['creator'] for m in BARS if m in META)
p("creators of our mints:",len(ourcre))

c=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro',uri=True)
c.execute("pragma cache_size=-200000")
t=time.time()
obs=collections.defaultdict(list)
for slot,ti,oi,ii,bc,vqb,vqa in c.execute(
  "select slot,transaction_index,outer_index,inner_index,bonding_curve,virtual_quote_before,virtual_quote_after from reserve_observation"):
    info=bc2.get(bc)
    if not info: continue
    if info[1] not in ourcre: continue
    obs[bc].append((slot,ti,oi,ii,vqb,vqa))
p("target curves:",len(obs),"rows:",sum(len(v) for v in obs.values()),"scan %.0fs"%(time.time()-t))

t=time.time()
TR_IDX={'buy':6,'sell':6,'buy_exact_sol_in':6,'buy_exact_quote_in':6,
        'buy_v2':13,'sell_v2':13,'buy_exact_quote_in_v2':13}
devinfo={}
nlook=0
for bc,lst in obs.items():
    mint,cre,cslot,cbt=bc2[bc]
    lst.sort()
    devsol=0.0; devbuys=0; firstbuyer_dev=None; ntr=0
    for (slot,ti,oi,ii,vqb,vqa) in lst:
        if vqb is None or vqa is None: continue
        d=(vqa-vqb)/1e9
        r=c.execute("select idl_name,accounts_json from instruction where slot=? and transaction_index=? and outer_index=? and inner_index=?",(slot,ti,oi,ii)).fetchone()
        nlook+=1
        if not r: continue
        nm,aj=r
        idx=TR_IDX.get(nm)
        if idx is None: continue
        try: acc=json.loads(aj)
        except Exception: continue
        if idx>=len(acc): continue
        w=acc[idx]
        ntr+=1
        if firstbuyer_dev is None and d>0:
            firstbuyer_dev=(w==cre)
        if w==cre and d>0:
            devbuys+=1; devsol+=d
    devinfo[bc]=dict(mint=mint,creator=cre,bt=cbt,slot=cslot,devsol=devsol,
                     devbuys=devbuys,firstdev=firstbuyer_dev,ntr=ntr)
p("lookups:",nlook,"%.0fs"%(time.time()-t))
c.close()
withdev=sum(1 for v in devinfo.values() if v['devbuys']>0)
p("curves with a creator buy:",withdev,"of",len(devinfo))
p("devsol quantiles:",sorted(round(v['devsol'],3) for v in devinfo.values() if v['devbuys']>0)[:20])
# per-creator prior dev-buy history availability for our mints
bycre=collections.defaultdict(list)
for bc,v in devinfo.items(): bycre[v['creator']].append(v)
navail=0
for m in BARS:
    if m not in META: continue
    cre=META[m]['creator']; t0=META[m]['bt']
    pri=[v for v in bycre.get(cre,[]) if v['bt']<t0]
    if pri: navail+=1
p("our mints with >=1 b11a-covered PRIOR coin by same creator:",navail,"of",len(BARS))
selfcov=sum(1 for m in BARS if m in META and META[m]['bc'] in devinfo)
p("our mints with own-curve b11a coverage:",selfcov)
pickle.dump(devinfo,open(SCR+'/devinfo.pkl','wb'))
open(SCR+'/devbuy.out','w').write("\n".join(o))
