"""Per-mint bonding-curve metadata for MY mints only (h in 1,2). Never reads h==0 mints."""
import sqlite3, json, hashlib, collections, math, os
ROOT='/home/anont/meme'; OUT=ROOT+'/.combo2way_scratch'
def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3
oc=sqlite3.connect('file:%s/research/midcap/grad_ohlcv.sqlite?mode=ro'%ROOT,uri=True)
rows=oc.execute("select mint,first_ts from ohlcv where n_bars>0").fetchall()
mine={m:ft for m,ft in rows if h3(m)!=0}
print('my mints',len(mine))
wl=sqlite3.connect('file:%s/research/b11a/window_labels.sqlite?mode=ro'%ROOT,uri=True)
ml=list(mine)
q='select mint,bonding_curve,block_time,create_slot,data_len from window_label where mint in (%s)'%(','.join('?'*len(ml)))
wlrows=wl.execute(q,ml).fetchall()
print('window_label rows',len(wlrows))
curve2mint={}; base={}
for m,bc,bt,cs,dl in wlrows:
    curve2mint[bc]=m
    base[m]=dict(bc=bc,block_time=bt,create_slot=cs,data_len=dl)
bo=sqlite3.connect('file:%s/research/b11a/b11a_bodies.sqlite?mode=ro'%ROOT,uri=True)
print('idl_name counts:')
for nm,c in bo.execute("select idl_name,count(*) from instruction where idl_name is not null group by 1 order by 2 desc limit 30"):
    print('   ',nm,c)
CURVES=set(curve2mint)
agg=collections.defaultdict(lambda: dict(n=0,buys=0,sells=0,bsol=[],ssol=0.0,fslot=None,lslot=None,keys=[]))
n=0
for slot,ti,oi,ii,bc,vqb,vqa in bo.execute(
        "select slot,transaction_index,outer_index,inner_index,bonding_curve,virtual_quote_before,virtual_quote_after from reserve_observation"):
    n+=1
    if bc not in CURVES: continue
    a=agg[bc]; a['n']+=1
    if a['fslot'] is None or slot<a['fslot']: a['fslot']=slot
    if a['lslot'] is None or slot>a['lslot']: a['lslot']=slot
    if vqb is not None and vqa is not None:
        dq=(vqa-vqb)/1e9
        if dq>0: a['buys']+=1; a['bsol'].append(dq)
        elif dq<0: a['sells']+=1; a['ssol']+=-dq
    a['keys'].append((slot,ti,oi,ii))
print('reserve_observation scanned',n,'curves hit',len(agg))
# unique wallets via instruction join
want={}
for bc,a in agg.items():
    for k in a['keys']: want[k]=bc
print('keys wanted',len(want))
wallets=collections.defaultdict(set)
seen=0
for slot,ti,oi,ii,aj,idl in bo.execute("select slot,transaction_index,outer_index,inner_index,accounts_json,idl_name from instruction where accounts_json is not null"):
    k=(slot,ti,oi,ii)
    bc=want.get(k)
    if bc is None: continue
    seen+=1
    try: acc=json.loads(aj)
    except Exception: continue
    if idl and idl.endswith('_v2'):
        w=acc[13] if len(acc)>13 else None
    else:
        w=acc[6] if len(acc)>6 else None
    if w: wallets[bc].add(w)
print('instruction rows matched',seen)
out={}
for m,b in base.items():
    bc=b['bc']; a=agg.get(bc)
    ft=mine[m]
    r=dict(gradspeed=math.log1p(max(0.0,(ft-b['block_time'])/60.0)) if b['block_time'] else None,
           data_len=b['data_len'], create_hour=(b['block_time']//3600)%24 if b['block_time'] else None)
    if a and a['n']>0:
        bsol=sorted(a['bsol'],reverse=True); tot=sum(bsol)
        r.update(bc_n=math.log1p(a['n']),
                 bc_buyfrac=a['buys']/max(1,a['buys']+a['sells']),
                 bc_maxbuy=math.log1p(bsol[0]) if bsol else None,
                 bc_top1=(bsol[0]/tot) if tot>0 else None,
                 bc_top5=(sum(bsol[:5])/tot) if tot>0 else None,
                 bc_totbuy=math.log1p(tot),
                 bc_sellratio=(a['ssol']/tot) if tot>0 else None,
                 bc_slots=math.log1p(max(0,a['lslot']-a['fslot'])),
                 bc_wallets=math.log1p(len(wallets.get(bc,()))),
                 bc_tpw=a['n']/max(1,len(wallets.get(bc,())) or 1))
    out[m]=r
json.dump(out,open(OUT+'/meta.json','w'))
cov=collections.Counter()
for m,r in out.items():
    for k,v in r.items():
        if v is not None: cov[k]+=1
print('coverage',dict(cov),'of',len(out))
