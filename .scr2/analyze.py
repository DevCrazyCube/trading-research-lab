import pickle, json, statistics, collections, random, sys, math
sys.path.insert(0,'/home/anont/meme/.scr2')
SCR='/home/anont/meme/.scr2'
S=pickle.load(open(SCR+'/sweep.pkl','rb'))
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))
p("combos swept:",S['ncomb'],"structures:",S['n_struct'],"filters:",S['n_filters'],
  "train mints:",S['ntrain'],"valid mints:",S['nvalid'],"elapsed %.0fs"%S['elapsed'])
p("rows passing TRAIN gate:",len(S['rows']))

# ---------- response surface (unconditional, same structures) ----------
surf=S['surface']
p("")
p("=== UNCONDITIONAL SURFACE (no creator filter), validate-split mint-equal mean, toll1.14 drop-30, cap+300% ===")
by=collections.defaultdict(list)
for tname,pname,hold,mname,mtr,mva,ktr,kva,res in surf:
    by[('timing',tname)].append(mva); by[('pos',pname)].append(mva)
    by[('hold',hold)].append(mva); by[('mod',mname)].append(mva)
for grp in ('timing','pos','hold','mod'):
    p(" -- %s"%grp)
    for k,v in sorted((k,v) for k,v in by.items() if k[0]==grp):
        p("    %-14s n=%3d meanOfCells=%+.4f  best=%+.4f  worst=%+.4f"%(str(k[1]),len(v),statistics.mean(v),max(v),min(v)))
best=sorted(surf,key=lambda r:-r[5])[:15]
p(" -- best 15 unconditional structures (validate)")
for r in best: p("    %s/%s/h%d/%s  train=%+.4f valid=%+.4f k=%d res=%.3f"%(r[0],r[1],r[2],r[3],r[4],r[5],r[7],r[8]))
worst=sorted(surf,key=lambda r:r[5])[:8]
p(" -- worst 8 unconditional structures (validate)")
for r in worst: p("    %s/%s/h%d/%s  train=%+.4f valid=%+.4f"%(r[0],r[1],r[2],r[3],r[4],r[5]))

p("")
p("=== filter sizes (train,valid mints) ===")
for f,(a,b) in sorted(S['fsizes'].items(), key=lambda x:-x[1][0]):
    p("   %-24s %3d %3d"%(f,a,b))

# ---------- validate gate ----------
MIN_K=20; MIN_KC=8
surv=[]
for r in S['rows']:
    va=r['va']; bva=r['bva']; tr=r['tr']
    if va['k']<MIN_K or va['kc']<MIN_KC: continue
    if va['mean']<=0: continue
    edge=va['mean']-bva['mean']
    if edge<=0: continue
    if va['mean50']<=0 or va['mean25']<=0: continue   # robust to toll + dropout charge
    r['edge']=edge
    surv.append(r)
p("")
p("=== rows surviving VALIDATE gate (mean>0, beats same-structure unconditional, robust to toll 2.5%% and -50%% dropout) ===")
p("survivors:",len(surv))
surv.sort(key=lambda r:-(r['edge']))
for r in surv[:60]:
    p("  %-12s %-12s h%-5d %-12s %-26s | TR m=%+.4f k=%d | VA m=%+.4f med=%+.4f k=%d kc=%d n=%d res=%.2f | base VA m=%+.4f edge=%+.4f | m50=%+.4f m100=%+.4f m25=%+.4f raw=%+.4f"%(
        r['timing'],r['pos'],r['hold'],r['mod'],r['filt'],
        r['tr']['mean'],r['tr']['k'],
        r['va']['mean'],r['va']['med'],r['va']['k'],r['va']['kc'],r['va']['n'],r['va']['res'],
        r['bva']['mean'],r['edge'],r['va']['mean50'],r['va']['mean100'],r['va']['mean25'],r['va']['mean_raw']))

# which filters appear most among survivors
cf=collections.Counter(r['filt'] for r in surv)
p("")
p("survivor filters (count):",cf.most_common(30))
cm=collections.Counter(r['mod'] for r in surv); p("survivor mods:",cm.most_common())
ct=collections.Counter(r['timing'] for r in surv); p("survivor timings:",ct.most_common())
ch=collections.Counter(r['hold'] for r in surv); p("survivor holds:",ch.most_common())
cp=collections.Counter(r['pos'] for r in surv); p("survivor positions:",cp.most_common())

pickle.dump(surv,open(SCR+'/surv.pkl','wb'))
open(SCR+'/analyze.out','w').write("\n".join(o))
