import numpy as np, pickle
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/summary.txt','w')
def p(*a): print(*a,file=out); out.flush()
Z=np.load(W+'/feats.npz',allow_pickle=True)
DM=Z['DM'].astype(np.int64); hv=Z['hv']; mints=list(Z['mints'])
O=np.load(W+'/outcomes_pess.npz',allow_pickle=True)
RET=O['RET']; EOFF=O['EOFF']; FROZEN=O['FROZEN']; CENS=O['CENS']; names=list(O['names']); TE=O['TE']
HOR=list(O['HORIZ']); NM=len(mints); NDP=len(DM)
hdp=hv[DM]; VA=(hdp==2); TR=(hdp==1)
TEl=TE.tolist(); DMl=DM.tolist()
def run(s,split,fc=None,toll=0.0114):
    hidx=HOR.index(int(names[s].split('|')[0][1:]))
    sel=np.flatnonzero(split&(~CENS[hidx])); eo=EOFF[s].tolist()
    keep=[]; curm=-1; free=-1
    for i in sel:
        m=DMl[i]
        if m!=curm: curm=m; free=-1
        if TEl[i]>=free: keep.append(i); free=TEl[i]+eo[i]
    ki=np.asarray(keep); g=RET[s][ki].astype(np.float64); fz=FROZEN[hidx][ki]
    if fc is not None: g=np.where(fz,fc,g)
    net=(1+g)*(1-toll)-1
    cnt=np.bincount(DM[ki],minlength=NM); sm=np.bincount(DM[ki],weights=net,minlength=NM)
    nz=cnt>0; mu=sm[nz]/cnt[nz]
    return mu.mean(),np.median(mu),len(keep),int(nz.sum()),float(fz.mean())
p('=== UNCONDITIONAL on-curve baseline, every decision point, no entry filter ===')
p('   mint-equal weighted, no-overlap, pessimistic fills, toll 1.14%')
p('%-30s %8s %8s %7s %5s %7s'%('structure','mean','median','n','k','frozen'))
for nm in ['H60|time|P0','H180|time|P0','H600|time|P0','H1800|time|P0','H5400|time|P0',
           'H180|flowrev|P0','H180|sl0.15|P0','H180|tp0.25|P0']:
    s=names.index(nm)
    a=run(s,TR); b=run(s,VA)
    p('%-30s %8.4f %8.4f %7d %5d %7.3f   (train)'%(nm,a[0],a[1],a[2],a[3],a[4]))
    p('%-30s %8.4f %8.4f %7d %5d %7.3f   (valid)'%('',b[0],b[1],b[2],b[3],b[4]))
p('')
p('=== dropout-charge sensitivity of the unconditional H1800 time hold (validate) ===')
s=names.index('H1800|time|P0')
for fc,tag in [(None,'frozen=0'),(-0.30,'frozen=-30%'),(-0.50,'frozen=-50%'),(-1.00,'frozen=-100%')]:
    a=run(s,VA,fc); p('  %-14s mean=%7.4f med=%7.4f'%(tag,a[0],a[1]))
p('')
p('=== decision-point universe ===')
p('mints with tapes (h in 1,2): 2371 ; with >=7 trades and a decision point: %d'%len(set(DM.tolist())))
p('decision points: %d  (train h=1: %d, validate h=2: %d)'%(NDP,int(TR.sum()),int(VA.sum())))
p('holdout h==0 mints: never loaded, never counted')
out.close()
