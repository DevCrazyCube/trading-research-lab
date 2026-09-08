
def evaluate2(cname,H,ex,pos,dc,halves,toll=None):
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
    vals=list(per_mint.values())
    return dict(mean=st.mean(vals),med=st.median(vals),k=len(vals),n=ntr,
                res=((ntr-ndrop)/ntr if ntr else 0.0),vals=vals)

def boot_lo(vals,B=2000,seed=11):
    if len(vals)<4: return None
    rnd=random.Random(seed); n=len(vals); ms=[]
    for _ in range(B): ms.append(sum(vals[rnd.randrange(n)] for _ in range(n))/n)
    ms.sort(); return ms[int(0.05*B)]

P('=== FULL PASS: train(h=1) / validate(h=2) / random-entry control ===')
CTRL={}
for H in HG:
    for ex in EXITS:
        for pos in POS:
            CTRL[(H,ex[0],pos)]=dict(t=evaluate2('all',H,ex,pos,-0.30,{1}),
                                     v=evaluate2('all',H,ex,pos,-0.30,{2}))
P('random-entry control built t=%.0fs'%(time.time()-T0))
for HH_ in (5,15,60):
    cv=CTRL[(HH_,'hold','flat')]
    P('RANDOM-BAR %dm hold flat: train mean=%.2f%% med=%.2f%% k=%d n=%d res=%.1f%% | val mean=%.2f%% med=%.2f%% k=%d n=%d res=%.1f%%'%(
       HH_,cv['t']['mean']*100,cv['t']['med']*100,cv['t']['k'],cv['t']['n'],cv['t']['res']*100,
       cv['v']['mean']*100,cv['v']['med']*100,cv['v']['k'],cv['v']['n'],cv['v']['res']*100))
cv=CTRL[(15,'tp10','flat')]
P('RANDOM-BAR 15m tp10 flat (truncation control): val mean=%.2f%% med=%.2f%%'%(cv['v']['mean']*100,cv['v']['med']*100))
cv=CTRL[(15,'tp25','flat')]
P('RANDOM-BAR 15m tp25 flat (truncation control): val mean=%.2f%% med=%.2f%%'%(cv['v']['mean']*100,cv['v']['med']*100))

rows=[]; combos=0; g1=0; g2=0; g3=0; g4=0
for cname,_ in CONDS:
    for H in HG:
        for ex in EXITS:
            for pos in POS:
                combos+=1
                a=evaluate2(cname,H,ex,pos,-0.30,{1})
                if a is None or a['k']<8 or a['mean']<=0: continue
                g1+=1
                b=evaluate2(cname,H,ex,pos,-0.30,{2})
                if b is None or b['k']<8 or b['mean']<=0: continue
                g2+=1
                cc=CTRL[(H,ex[0],pos)]
                if cc['v'] is None or b['mean']<=cc['v']['mean']: continue
                if cc['t'] is None or a['mean']<=cc['t']['mean']: continue
                g3+=1
                lo=boot_lo(b['vals'])
                if lo is None or lo<=0: continue
                g4+=1
                sv=sorted(b['vals']); trimmed=(st.mean(sv[:-1]) if len(sv)>2 else None)
                rows.append(dict(cond=cname,H=H,exit=ex[0],pos=pos,
                    tmean=a['mean'],tmed=a['med'],tk=a['k'],tn=a['n'],tres=a['res'],
                    vmean=b['mean'],vmed=b['med'],vk=b['k'],vn=b['n'],vres=b['res'],vlo=lo,
                    vtrim=trimmed,ctrl_v=cc['v']['mean'],ctrl_t=cc['t']['mean'],
                    edge_v=b['mean']-cc['v']['mean']))
P('combos: %d'%combos)
P('gate1 train mean>0 & k>=8            : %d'%g1)
P('gate2 + validate mean>0 & k>=8       : %d'%g2)
P('gate3 + beats random control BOTH    : %d'%g3)
P('gate4 + validate bootstrap lo>0      : %d'%g4)
rows.sort(key=lambda r:-r['edge_v'])
P('--- survivors (%d) ---'%len(rows))
for r in rows[:60]:
    P('  %-14s H=%4d %-12s %-9s tr=%+7.2f%%(k%d,n%d) va=%+7.2f%%(med%+6.2f%%,k%d,n%d,lo%+6.2f%%,trim%+7.2f%%) ctrlv=%+6.2f%% edge=%+7.2f%% res=%.0f%%'%(
      r['cond'],r['H'],r['exit'],r['pos'],r['tmean']*100,r['tk'],r['tn'],
      r['vmean']*100,r['vmed']*100,r['vk'],r['vn'],r['vlo']*100,(r['vtrim'] or 0)*100,
      r['ctrl_v']*100,r['edge_v']*100,r['vres']*100))
json.dump(rows,open('/home/anont/meme/.scratch_att2/ogrid2_survivors.json','w'))
P('done t=%.0fs'%(time.time()-T0))
OUT.close()
