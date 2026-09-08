"""v2 matrix: adds bonding-curve/mint metadata, a CAUSAL bad-feed guard, and a capped-gross column.
HOLDOUT: only md5(mint)%3 in (1,2)."""
import sqlite3, json, hashlib, math, os
import numpy as np

ROOT='/home/anont/meme'; OUT=ROOT+'/.combo2way_scratch'
def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

con=sqlite3.connect('file:%s/research/midcap/grad_ohlcv.sqlite?mode=ro'%ROOT,uri=True)
rows=con.execute("select mint,bars_json from ohlcv where n_bars>0").fetchall()
bars={}
for m,bj in rows:
    hv=h3(m)
    if hv==0: continue
    b=sorted(json.loads(bj),key=lambda z:z[0])
    if len(b)>=8: bars[m]=(hv,b)

META=json.load(open(OUT+'/meta.json')) if os.path.exists(OUT+'/meta.json') else {}
MKEYS=['gradspeed','data_len','create_hour','bc_n','bc_buyfrac','bc_maxbuy','bc_top1','bc_top5',
       'bc_totbuy','bc_sellratio','bc_slots','bc_wallets','bc_tpw']
PKEYS=['ret1','ret5','ret15','ret30','dd_max','up_min','tot_ret','rvol15','barrange','bodypos',
       'volratio','logvol5','density15','age_min','cumvol','hour','accel','vwapdev','revcount']
FEATS=PKEYS+['m_'+k for k in MKEYS]
NF=len(FEATS); NP=len(PKEYS)

TOL_EXIT=3600; HOLD=900; CAP=3.0   # fill-realism cap on gross (+300%)
JUMP=math.log(5.0)

rm=[];rh=[];rp=[];rf=[];rg=[];rx=[];rq=[]   # rq = feed-clean flag (causal)
mint_ids=[]
for mi,(m,(hv,b)) in enumerate(sorted(bars.items())):
    mint_ids.append(m)
    ts=np.array([x[0] for x in b],dtype=np.int64)
    op=np.array([x[1] for x in b],dtype=np.float64); hi=np.array([x[2] for x in b],dtype=np.float64)
    lo=np.array([x[3] for x in b],dtype=np.float64); cl=np.array([x[4] for x in b],dtype=np.float64)
    vo=np.array([x[5] for x in b],dtype=np.float64)
    good=(cl>0)&(op>0)&(hi>0)&(lo>0)
    if good.sum()<8: continue
    ts,op,hi,lo,cl,vo=ts[good],op[good],hi[good],lo[good],cl[good],vo[good]
    n=len(ts)
    runmax=np.maximum.accumulate(hi); runmin=np.minimum.accumulate(lo); cumv=np.cumsum(vo)
    lr=np.zeros(n); lr[1:]=np.log(cl[1:]/cl[:-1]); pv=cl*vo
    # causal bad-feed detector: a >5x move immediately reversed by a >5x move the other way
    rev=np.zeros(n,dtype=np.int32)
    c=0
    for j in range(2,n):
        if lr[j-1]>JUMP and lr[j]<-JUMP: c+=1
        elif lr[j-1]<-JUMP and lr[j]>JUMP: c+=1
        rev[j]=c
    md=META.get(m,{})
    mfeat=[]
    for k in MKEYS:
        v=md.get(k)
        mfeat.append(float(v) if isinstance(v,(int,float)) else np.nan)
    i5=np.searchsorted(ts,ts-300,side='right')-1
    i15=np.searchsorted(ts,ts-900,side='right')-1
    i30=np.searchsorted(ts,ts-1800,side='right')-1
    j5=np.searchsorted(ts,ts-300,side='left'); j15=np.searchsorted(ts,ts-900,side='left')
    j30=np.searchsorted(ts,ts-1800,side='left')
    tgt=ts+HOLD; ex=np.searchsorted(ts,tgt,side='left'); ok=(ex<n)
    exi=np.where(ok,np.minimum(ex,n-1),0); within=ok&((ts[exi]-tgt)<=TOL_EXIT)
    for i in range(3,n-1):
        if ts[i]-ts[0]<300: continue
        if i5[i]<0 or i15[i]<0: continue
        k=i+1
        f=[0.0]*NF
        f[0]=cl[i]/cl[i-1]-1.0
        f[1]=cl[i]/cl[i5[i]]-1.0
        f[2]=cl[i]/cl[i15[i]]-1.0
        f[3]=cl[i]/cl[i30[i]]-1.0 if i30[i]>=0 else np.nan
        f[4]=cl[i]/runmax[i]-1.0
        f[5]=cl[i]/runmin[i]-1.0
        f[6]=cl[i]/op[0]-1.0
        seg=lr[max(1,j15[i]):i+1]; f[7]=float(seg.std()) if len(seg)>=3 else np.nan
        f[8]=(hi[i]-lo[i])/cl[i]
        f[9]=(cl[i]-lo[i])/(hi[i]-lo[i]) if hi[i]>lo[i] else 0.5
        v5=float(vo[j5[i]:i+1].sum()); v30=float(vo[j30[i]:i+1].sum()); nb30=(i+1-j30[i])
        f[10]=v5/(v30/max(1.0,nb30/5.0)) if v30>0 else np.nan
        f[11]=math.log1p(v5)
        f[12]=float(i+1-j15[i])
        f[13]=(ts[i]-ts[0])/60.0
        f[14]=math.log1p(cumv[i])
        f[15]=float((ts[i]//3600)%24)
        f[16]=f[1]-(f[2]-f[1])/2.0
        pvs=float(pv[j30[i]:i+1].sum()); vvs=float(vo[j30[i]:i+1].sum())
        f[17]=cl[i]/(pvs/vvs)-1.0 if vvs>0 else np.nan
        f[18]=float(rev[i])
        f[NP:]=mfeat
        if within[k]:
            g=op[exi[k]]/op[k]-1.0; xp=int(exi[k])
        else:
            g=np.nan; xp=-1
        rm.append(mi);rh.append(hv);rp.append(k);rf.append(f);rg.append(g);rx.append(xp)
        rq.append(1 if rev[i]==0 else 0)

F=np.array(rf,dtype=np.float64); G=np.array(rg,dtype=np.float64)
np.savez_compressed(OUT+'/matrix2.npz',F=F,mint=np.array(rm,dtype=np.int32),
    hv=np.array(rh,dtype=np.int8),pos=np.array(rp,dtype=np.int32),gross=G,
    exitpos=np.array(rx,dtype=np.int32),clean=np.array(rq,dtype=np.int8),
    feats=np.array(FEATS))
json.dump(mint_ids,open(OUT+'/mints2.json','w'))
print('rows',F.shape,'mints',len(set(rm)))
print('feed-clean rows',float(np.mean(rq)))
fin=np.isfinite(G); print('resolution',float(fin.mean()))
cln=np.array(rq)==1
print('mean all %.4f  mean clean %.4f  capped-clean %.4f'%(np.nanmean(G),np.nanmean(G[cln]),
      np.nanmean(np.clip(G[cln],-1,CAP))))
for i,nme in enumerate(FEATS):
    col=F[:,i]; ok=np.isfinite(col)
    print('%-14s valid=%.3f q=%s'%(nme,ok.mean(),np.round(np.nanpercentile(col[ok],[1,25,50,75,99]),4).tolist() if ok.sum()>10 else 'NA'))
