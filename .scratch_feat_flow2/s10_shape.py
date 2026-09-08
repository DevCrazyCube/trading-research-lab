import pickle, numpy as np
from collections import defaultdict
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/shape.txt','w')
def p(*a): print(*a,file=out); out.flush()
A=pickle.load(open(W+'/stageA.pkl','rb'))
O=np.load(W+'/outcomes.npz',allow_pickle=True); names=list(O['names'])
# A rows: (cell,s,mean,med,mean25,fz50,n,k,ctrl,edge,frozen)
p('stage-A rows',len(A))
def parts(s):
    nm=names[s]; a=nm.split('|'); return a[0],a[1],a[2]
agg=defaultdict(list)
for z in A:
    H,ex,po=parts(z[1]); agg[('pos',po)].append(z[2]); agg[('exit',ex)].append(z[2]); agg[('H',H)].append(z[2])
    agg[('feat',z[0].split('<=')[0].split('>=')[0])].append(z[2])
p('--- TRAIN mean net by axis level (mint-equal), n rows ---')
for k in sorted(agg,key=lambda k:(k[0],-np.mean(agg[k]))):
    v=np.array(agg[k]); p('%-6s %-22s n=%5d  mean=%7.4f  med=%7.4f  frac>0=%.3f'%(k[0],k[1],len(v),v.mean(),np.median(v),(v>0).mean()))
V=pickle.load(open(W+'/validated.pkl','rb'))
p('')
p('--- validated rows by position ---')
byp=defaultdict(list)
for r in V:
    po=r['struct'].split('|')[2]; byp[po].append(r)
for po,rs in byp.items():
    vm=np.array([r['v_mean'] for r in rs])
    surv=[r for r in rs if r['v_mean']>0 and r['v_lo']>0 and r['edge']>0 and r['v_m50']>0]
    p('%-12s validated=%4d  vmean_avg=%7.4f  survivors=%d'%(po,len(rs),vm.mean(),len(surv)))
p('')
p('--- survivors that use position P0 (no averaging-in) ---')
s0=[r for r in V if r['struct'].split('|')[2]=='P0' and r['v_mean']>0 and r['v_lo']>0 and r['edge']>0 and r['v_m50']>0]
s0=sorted(s0,key=lambda r:-r['v_mean'])
p('count',len(s0))
p('%-26s %-30s %8s %8s %8s %8s %6s %5s %8s %8s'%('cell','struct','trmean','vmean','vmed','vCIlo','n','k','ctrl','edge'))
for r in s0[:40]:
    p('%-26s %-30s %8.4f %8.4f %8.4f %8.4f %6d %5d %8.4f %8.4f'%(r['cell'],r['struct'],r['train_mean'],r['v_mean'],r['v_med'],r['v_lo'],r['v_n'],r['v_k'],r['ctrl'],r['edge']))
p('')
p('--- survivors with a PURE TIME exit (no truncation at all) ---')
st=[r for r in V if r['struct'].split('|')[1]=='time' and r['v_mean']>0 and r['v_lo']>0 and r['edge']>0]
p('count',len(st))
for r in sorted(st,key=lambda r:-r['v_mean'])[:30]:
    p('%-26s %-30s %8.4f %8.4f %8.4f %8.4f %6d %5d %8.4f %8.4f'%(r['cell'],r['struct'],r['train_mean'],r['v_mean'],r['v_med'],r['v_lo'],r['v_n'],r['v_k'],r['ctrl'],r['edge']))
p('')
p('--- how many stage-A TIME-exit rows were even train-positive? ---')
tt=[z for z in A if names[z[1]].split('|')[1]=='time']
tt=np.array([z[2] for z in tt]); p('time-exit rows',len(tt),'frac train mean>0',float((tt>0).mean()),'mean',float(tt.mean()))
out.close()
