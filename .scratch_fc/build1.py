"""Build cached feature/bar tables for the deployer-identity slice.
STRICT: only mints with md5(mint)%3 in (1,2) are ever touched.
"""
import sqlite3, json, hashlib, os, pickle, time
from collections import defaultdict, Counter
S='/home/anont/meme/.scratch_fc/'
OUT=open(S+'build1.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()
def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3
def conn(p): return sqlite3.connect('file:%s?mode=ro'%p,uri=True)

t0=time.time()
# ---------- window labels (h12 only) ----------
c=conn('/home/anont/meme/research/b11a/window_labels.sqlite')
raw=c.execute("select bonding_curve,mint,creator,create_slot,block_time,complete from window_label").fetchall()
c.close()
WL=[r for r in raw if r[1] and h3(r[1])!=0]
del raw
P('WL h12',len(WL))
curve2mint={r[0]:r[1] for r in WL}
mint2curve={r[1]:r[0] for r in WL}
mint2cre={r[1]:r[2] for r in WL}
mint2bt={r[1]:r[4] for r in WL}
mint2slot={r[1]:r[3] for r in WL}
mint2comp={r[1]:r[5] for r in WL}

# slot -> time linear fit
xs=[r[3] for r in WL]; ys=[r[4] for r in WL]
n=len(xs); mx=sum(xs)/n; my=sum(ys)/n
num=sum((x-mx)*(y-my) for x,y in zip(xs,ys)); den=sum((x-mx)**2 for x in xs)
slope=num/den; inter=my-slope*mx
P('slot->time slope(sec/slot)',round(slope,5),'inter',round(inter,1))
def slot2t(s): return inter+slope*s

# ---------- trades from bodies (h12 curves only) ----------
curves=set(curve2mint)
cb=conn('/home/anont/meme/research/b11a/b11a_bodies.sqlite')
q="""select r.bonding_curve, r.slot, r.transaction_index, r.outer_index, r.inner_index,
 r.virtual_quote_before, r.virtual_quote_after, i.idl_name, i.accounts_json
 from reserve_observation r join instruction i
  on i.slot=r.slot and i.transaction_index=r.transaction_index
  and i.outer_index=r.outer_index and i.inner_index=r.inner_index"""
trades=defaultdict(list)   # curve -> list of (slot,txi,oi,ii,delta_lamports,trader)
namecnt=Counter(); skipped=0; tot=0
for bc,slot,txi,oi,ii,vqb,vqa,idl,acc in cb.execute(q):
    tot+=1
    if bc not in curves: continue
    namecnt[idl]+=1
    if vqb is None or vqa is None:
        continue
    d=vqa-vqb
    if d==0: continue
    tr=None
    if acc:
        try:
            a=json.loads(acc)
            nm=idl or ''
            if nm.endswith('_v2'): idx=13
            else: idx=6
            if len(a)>idx: tr=a[idx]
        except Exception: pass
    trades[bc].append((slot,txi,oi,ii,d,tr,idl))
cb.close()
P('reserve_obs scanned',tot,'curves with trades',len(trades),'elapsed',round(time.time()-t0,1))
P('idl_name counts (h12 curves)',namecnt.most_common(20))

# ---------- per-launch dev features ----------
launch={}
for bc,lst in trades.items():
    m=curve2mint[bc]; cre=mint2cre.get(m)
    lst.sort()
    nb=0; ns=0; devbuy=0; devsell=0; devfirst=0; firsttrader=None
    devbuy_n=0; devsell_n=0; volbuy=0
    for k,(slot,txi,oi,ii,d,tr,idl) in enumerate(lst):
        if k==0: firsttrader=tr
        if d>0:
            nb+=1; volbuy+=d
            if tr and cre and tr==cre: devbuy+=d; devbuy_n+=1
        else:
            ns+=1
            if tr and cre and tr==cre: devsell+= -d; devsell_n+=1
    launch[m]=dict(
        n_trades=len(lst), n_buys=nb, n_sells=ns,
        dev_buy_sol=devbuy/1e9, dev_sell_sol=devsell/1e9,
        dev_buy_n=devbuy_n, dev_sell_n=devsell_n,
        dev_first=1 if (firsttrader and cre and firsttrader==cre) else 0,
        buy_vol_sol=volbuy/1e9,
        traders=len(set(t for (_,_,_,_,_,t,_) in lst if t)),
    )
P('launches with trade data',len(launch))
# quick stats
dvals=[v['dev_buy_sol'] for v in launch.values()]
P('dev_buy_sol: frac>0', round(sum(1 for x in dvals if x>0)/len(dvals),3))
import statistics as st
pos=[x for x in dvals if x>0]
P('dev_buy_sol pos: n',len(pos),'median',round(st.median(pos),4) if pos else None,
  'p90',round(sorted(pos)[int(.9*len(pos))],4) if pos else None)
P('dev_first frac', round(sum(v['dev_first'] for v in launch.values())/len(launch),3))
P('dev_sell frac', round(sum(1 for v in launch.values() if v['dev_sell_sol']>0)/len(launch),3))

# ---------- ohlcv ----------
c=conn('/home/anont/meme/research/midcap/grad_ohlcv.sqlite')
bars={}
for mint,bj,st_ in c.execute("select mint,bars_json,status from ohlcv where status='ok'"):
    if h3(mint)==0: continue
    try: b=json.loads(bj)
    except Exception: continue
    if not b: continue
    b.sort(key=lambda r:r[0])
    bars[mint]=b
c.close()
P('bars mints h12',len(bars),'total bars',sum(len(v) for v in bars.values()))

pickle.dump(dict(WL=WL,curve2mint=curve2mint,mint2curve=mint2curve,mint2cre=mint2cre,
                 mint2bt=mint2bt,mint2slot=mint2slot,mint2comp=mint2comp,
                 launch=launch,bars=bars,slope=slope,inter=inter),
            open(S+'data1.pkl','wb'))
P('done',round(time.time()-t0,1))
OUT.close()
