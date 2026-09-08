import pickle, json, hashlib, statistics as st, os
from collections import defaultdict, Counter
S='/home/anont/meme/.scratch_fc/'
D=pickle.load(open(S+'data1.pkl','rb')); FEAT=pickle.load(open(S+'feat.pkl','rb'))
OUT=open(S+'confound.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()
def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3
bars=D['bars']; WL=D['WL']
T0=min(r[4] for r in WL); T1=max(r[4] for r in WL)
P('window_label block_time span hours', round((T1-T0)/3600,2))
# 1) left-censoring: np==0 vs creation time within window
mints=sorted(bars)
buck=defaultdict(lambda:[0,0])
for m in mints:
    q=int((FEAT[m]['bt']-T0)/(T1-T0)*6)
    q=min(q,5)
    buck[q][0]+=1
    if FEAT[m]['n_prior']==0: buck[q][1]+=1
P('CONFOUND 1  frac np==0 by sixth-of-window (creation time):')
for q in sorted(buck): P('   sixth %d  n=%3d  frac np==0 = %.3f'%(q,buck[q][0],buck[q][1]/buck[q][0]))

# 2) graduation look-ahead: how many of the OHLCV universe are complete=1?
comp=Counter(FEAT[m].get('bt') is not None for m in mints)
c2=Counter(D['mint2comp'][m] for m in mints)
P('CONFOUND 2  window_label complete flag among tradeable mints:', dict(c2))

# 3) graduation timestamp from fresh_snapshots (h12 mints only)
first_complete={}; first_seen={}; last_incomplete={}
n=0
with open('/home/anont/meme/research/midcap/fresh_snapshots.jsonl') as f:
    for line in f:
        n+=1
        try: r=json.loads(line)
        except Exception: continue
        m=r.get('mint')
        if not m or h3(m)==0: continue
        ts=r.get('ts_ms')
        if ts is None: continue
        ts=ts/1000.0
        if m not in first_seen or ts<first_seen[m]: first_seen[m]=ts
        if r.get('complete'):
            if m not in first_complete or ts<first_complete[m]: first_complete[m]=ts
        else:
            if m not in last_incomplete or ts>last_incomplete[m]: last_incomplete[m]=ts
P('snapshot lines',n,'h12 mints seen',len(first_seen),'with complete=1',len(first_complete))
cov=[m for m in mints if m in first_complete]
P('tradeable mints with a complete=1 snapshot:',len(cov),'of',len(mints))
if cov:
    lags=[(first_complete[m]-FEAT[m]['bt'])/60.0 for m in cov]
    lags.sort()
    P('  minutes from create to first complete=1 snapshot: p10/p50/p90 = %.1f / %.1f / %.1f'%(
        lags[len(lags)//10],lags[len(lags)//2],lags[9*len(lags)//10]))
    P('  frac graduating within 20min: %.3f  within 60min: %.3f'%(
        sum(1 for x in lags if x<=20)/len(lags), sum(1 for x in lags if x<=60)/len(lags)))
pickle.dump(dict(first_complete=first_complete,last_incomplete=last_incomplete,first_seen=first_seen),
            open(S+'grad.pkl','wb'))
OUT.close()
