import pickle, collections, bisect, gc
gc.disable()
SP='/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/'
ev=pickle.load(open(SP+'h33_all.pkl','rb'))   # (mint,i,t,p_after,c_L2,d60)
tape=pickle.load(open(SP+'tape.pkl','rb'))
bt=pickle.load(open(SP+'blocktime.pkl','rb'))
first={}
for (slot,ti,oi,ii,mint,bc,user,vqb,vtb,vqa,vta,name,e,ok) in tape:
    t=bt.get(slot)
    if t is None: continue
    if mint not in first or t<first[mint]: first[mint]=t
del tape
def mean(v): return sum(v)/len(v)
def q(s,p): return s[min(len(s)-1,max(0,int(p*len(s))))]
buckets=[(0,60),(60,300),(300,900),(900,3600),(3600,21600),(21600,10**9)]
print('AGE-STRATIFIED latency haircut c at L=2 slots (0.84s), ALL BUYS')
print('%-16s %8s %7s %9s %9s %9s %9s %9s'%('age_bucket','n','mints','mean','median','p75','p90','frac>1.14%'))
for lo,hi in buckets:
    v=[];ms=set();d=0
    for (m,i,t,p,c,d60) in ev:
        a=t-first[m]
        if lo<=a<hi: v.append(c); ms.add(m); d+=d60
    if not v: continue
    s=sorted(v)
    print('%-16s %8d %7d %+8.3f%% %+8.4f%% %+8.3f%% %+8.3f%% %9.4f  dead60=%.4f'%(
      '%d-%ds'%(lo,hi if hi<10**9 else 999999),len(v),len(ms),100*mean(v),100*q(s,.5),100*q(s,.75),100*q(s,.90),
      1-bisect.bisect_right(s,0.0114)/len(s), d/len(v)))
