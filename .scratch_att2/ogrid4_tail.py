EXITS=[('hold',None,None,None,False),('tp5',0.05,None,None,False),('tp300',3.00,None,None,False),('tp1000',10.00,None,None,False),('sl15',None,0.15,None,False),('sl80',None,0.80,None,False),('tp5_sl15',0.05,0.15,None,False),('tp1000_sl80',10.00,0.80,None,False),('tp300_sl50',3.00,0.50,None,False),('trail25',None,None,0.25,False),('trail50',None,None,0.50,False),('gapexit',None,None,None,True),('tp300_gap',3.00,None,None,True),('tp10',0.10,None,None,False)]

def evaluate3(cname,H,ex,pos,dc,halves,toll=None):
    global TOLL
    old=TOLL
    if toll is not None: TOLL=toll
    tp,sl,tr,gx = ex[1],ex[2],ex[3],ex[4]
    per_mint={}; ndrop=0; ntr=0
    for mint,idx in SIG[cname].items():
        if hh(mint) not in halves: continue
        rs=[]; blocked=-1
        for i in idx:
            j=i+1
            if j<=blocked: continue
            o=trade_ret(mint,j,H,tp,sl,tr,gx,pos,dc)
            if o is None: continue
            rs.append(o[0]); ntr+=1
            if o[1] is None:
                ndrop+=1; blocked=j
            else:
                blocked=o[1]
        if rs: per_mint[mint]=sum(rs)/len(rs)
    TOLL=old
    if not per_mint: return None
    return per_mint

def trim_mean(v,f=0.10):
    s=sorted(v); n=len(s); k=int(n*f)
    s2=s[k:n-k] if n-2*k>=3 else s
    return sum(s2)/len(s2)

def boot(v,stat,B=1500,seed=17):
    if len(v)<5: return None
    rnd=random.Random(seed); n=len(v); ms=[]
    for _ in range(B):
        ms.append(stat([v[rnd.randrange(n)] for _ in range(n)]))
    ms.sort(); return ms[int(0.05*B)]

def stats(pm):
    v=list(pm.values())
    return dict(mean=st.mean(v),med=st.median(v),trim=trim_mean(v),k=len(v),vals=v)

P('=== ROBUST RE-GATE (mint-equal; mean is outlier-dominated here) ===')
# diagnose the control blowup
pm=evaluate3('all',15,('hold',None,None,None,False),'flat',-0.30,{2})
top=sorted(pm.items(),key=lambda kv:-kv[1])[:5]
P('random-bar 15m VALIDATE: top 5 per-mint averages: %s'%[(m[:8],round(x*100,0)) for m,x in top])
P('  mean=%.1f%% median=%.1f%% trimmed10=%.1f%% k=%d'%(st.mean(list(pm.values()))*100,
   st.median(list(pm.values()))*100, trim_mean(list(pm.values()))*100, len(pm)))
pm1=evaluate3('all',15,('hold',None,None,None,False),'flat',-0.30,{1})
P('random-bar 15m TRAIN   : mean=%.1f%% median=%.1f%% trimmed10=%.1f%% k=%d'%(st.mean(list(pm1.values()))*100,
   st.median(list(pm1.values()))*100, trim_mean(list(pm1.values()))*100, len(pm1)))

CTRL={}
for H in HG:
    for ex in EXITS:
        for pos in POS:
            a=evaluate3('all',H,ex,pos,-0.30,{1}); b=evaluate3('all',H,ex,pos,-0.30,{2})
            CTRL[(H,ex[0],pos)]=(stats(a) if a else None, stats(b) if b else None)
P('controls built t=%.0fs'%(time.time()-T0))

rows=[]; combos=0; g1=0; g2=0; g3=0; g4=0; g5=0
for cname,_ in CONDS:
    if cname=='all': continue
    for H in HG:
        for ex in EXITS:
            for pos in POS:
                combos+=1
                A=evaluate3(cname,H,ex,pos,-0.30,{1})
                if A is None or len(A)<10: continue
                a=stats(A)
                ct,cv=CTRL[(H,ex[0],pos)]
                if ct is None or cv is None: continue
                if a['trim']<=ct['trim']: continue
                g1+=1
                B=evaluate3(cname,H,ex,pos,-0.30,{2})
                if B is None or len(B)<10: continue
                b=stats(B)
                if b['trim']<=cv['trim']: continue
                g2+=1
                if b['trim']<=0: continue
                g3+=1
                if a['trim']<=0: continue
                g4+=1
                lo=boot(b['vals'],trim_mean)
                if lo is None or lo<=0: continue
                g5+=1
                rows.append(dict(cond=cname,H=H,exit=ex[0],pos=pos,
                  ttrim=a['trim'],tmed=a['med'],tmean=a['mean'],tk=a['k'],
                  vtrim=b['trim'],vmed=b['med'],vmean=b['mean'],vk=b['k'],vlo=lo,
                  ct=ct['trim'],cv=cv['trim'],edge=b['trim']-cv['trim']))
P('combos (excl all): %d'%combos)
P('R1 train trimmed > control trimmed          : %d'%g1)
P('R2 + validate trimmed > control trimmed     : %d'%g2)
P('R3 + validate trimmed > 0                   : %d'%g3)
P('R4 + train trimmed > 0                      : %d'%g4)
P('R5 + validate bootstrap lo(trimmed) > 0     : %d'%g5)
rows.sort(key=lambda r:-r['edge'])
P('--- robust survivors (%d) ---'%len(rows))
for r in rows[:50]:
    P('  %-14s H=%4d %-12s %-9s tr_trim=%+7.2f%%(med%+7.2f%%,k%d) va_trim=%+7.2f%%(med%+7.2f%%,mean%+9.2f%%,k%d,lo%+7.2f%%) ctrl_v=%+7.2f%% edge=%+7.2f%%'%(
      r['cond'],r['H'],r['exit'],r['pos'],r['ttrim']*100,r['tmed']*100,r['tk'],
      r['vtrim']*100,r['vmed']*100,r['vmean']*100,r['vk'],r['vlo']*100,r['cv']*100,r['edge']*100))
json.dump(rows,open('/home/anont/meme/.scratch_att2/ogrid3_survivors.json','w'))
P('done t=%.0fs'%(time.time()-T0))
OUT.close()
