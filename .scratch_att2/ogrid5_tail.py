EXITS=[('hold',None,None,None,False),('tp5',0.05,None,None,False),('tp10',0.10,None,None,False),
 ('tp25',0.25,None,None,False),('tp50',0.50,None,None,False),('tp100',1.00,None,None,False),
 ('tp300',3.00,None,None,False),('tp1000',10.00,None,None,False),
 ('sl15',None,0.15,None,False),('sl25',None,0.25,None,False),('sl50',None,0.50,None,False),('sl80',None,0.80,None,False),
 ('tp5_sl15',0.05,0.15,None,False),('tp25_sl25',0.25,0.25,None,False),('tp50_sl25',0.50,0.25,None,False),
 ('tp100_sl50',1.00,0.50,None,False),('tp1000_sl80',10.00,0.80,None,False),('tp300_sl50',3.00,0.50,None,False),
 ('trail25',None,None,0.25,False),('trail50',None,None,0.50,False),
 ('gapexit',None,None,None,True),('tp300_gap',3.00,None,None,True),('tp50_gap',0.50,None,None,True)]

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
    return (per_mint, ntr, ndrop)

def trim_mean(v,f=0.10):
    s=sorted(v); n=len(s); k=int(n*f)
    s2=s[k:n-k] if n-2*k>=3 else s
    return sum(s2)/len(s2)
def boot(v,stat,B=1500,seed=17):
    if len(v)<5: return None
    rnd=random.Random(seed); n=len(v); ms=[]
    for _ in range(B): ms.append(stat([v[rnd.randrange(n)] for _ in range(n)]))
    ms.sort(); return ms[int(0.05*B)]
def stats(t):
    pm,ntr,nd=t; v=list(pm.values())
    return dict(mean=st.mean(v),med=st.median(v),trim=trim_mean(v),k=len(v),n=ntr,
                res=((ntr-nd)/ntr if ntr else 0),vals=v)

P('=== COMBINED FULL-RANGE PASS ===')
P('%5s %10s %10s %10s %6s %8s %7s'%('H','ctrl_mean','ctrl_med','ctrl_trim','k','trades','res%'))
CTRL={}
for H in HG:
    for ex in EXITS:
        for pos in POS:
            a=evaluate3('all',H,ex,pos,-0.30,{1}); b=evaluate3('all',H,ex,pos,-0.30,{2})
            CTRL[(H,ex[0],pos)]=(stats(a) if a else None, stats(b) if b else None)
for H in HG:
    c=CTRL[(H,'hold','flat')][1]
    P('%5d %+9.2f%% %+9.2f%% %+9.2f%% %6d %8d %6.1f'%(H,c['mean']*100,c['med']*100,c['trim']*100,c['k'],c['n'],c['res']*100))
P('controls built t=%.0fs'%(time.time()-T0))

near=[]; rows=[]; combos=0; g1=g2=g3=g4=g5=0
for cname,_ in CONDS:
    if cname=='all': continue
    for H in HG:
        for ex in EXITS:
            for pos in POS:
                combos+=1
                A=evaluate3(cname,H,ex,pos,-0.30,{1})
                if A is None or len(A[0])<10: continue
                a=stats(A); ct,cv=CTRL[(H,ex[0],pos)]
                if ct is None or cv is None: continue
                if a['trim']<=ct['trim']: continue
                g1+=1
                B=evaluate3(cname,H,ex,pos,-0.30,{2})
                if B is None or len(B[0])<10: continue
                b=stats(B)
                if b['trim']<=cv['trim']: continue
                g2+=1
                if b['trim']<=0: continue
                g3+=1
                if a['trim']<=0: continue
                g4+=1
                lo=boot(b['vals'],trim_mean)
                rec=dict(cond=cname,H=H,exit=ex[0],pos=pos,ttrim=a['trim'],tmed=a['med'],tk=a['k'],tn=a['n'],
                         vtrim=b['trim'],vmed=b['med'],vmean=b['mean'],vk=b['k'],vn=b['n'],vres=b['res'],
                         vlo=(lo if lo is not None else -9),cv=cv['trim'],edge=b['trim']-cv['trim'])
                near.append(rec)
                if lo is not None and lo>0: g5+=1; rows.append(rec)
P('combos (excl all): %d'%combos)
P('R1 train trimmed > control trimmed      : %d'%g1)
P('R2 + validate trimmed > control trimmed : %d'%g2)
P('R3 + validate trimmed > 0               : %d'%g3)
P('R4 + train trimmed > 0 (BOTH halves +)  : %d'%g4)
P('R5 + validate bootstrap lo(trim) > 0    : %d'%g5)
near.sort(key=lambda r:-r['vlo'])
P('--- the %d cells positive on BOTH halves, ranked by validate bootstrap lower bound ---'%len(near))
for r in near[:45]:
    P('  %-14s H=%4d %-12s %-9s tr=%+7.2f%%(med%+7.2f%%,k%d,n%d) va=%+7.2f%%(med%+7.2f%%,mean%+9.2f%%,k%d,n%d) lo=%+7.2f%% ctrl=%+7.2f%% res=%.0f%%'%(
      r['cond'],r['H'],r['exit'],r['pos'],r['ttrim']*100,r['tmed']*100,r['tk'],r['tn'],
      r['vtrim']*100,r['vmed']*100,r['vmean']*100,r['vk'],r['vn'],r['vlo']*100,r['cv']*100,r['vres']*100))
json.dump(near,open('/home/anont/meme/.scratch_att2/ogrid5_near.json','w'))
P('FINAL survivors: %d'%len(rows))
P('done t=%.0fs'%(time.time()-T0))
OUT.close()
