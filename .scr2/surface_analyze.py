import pickle, statistics, collections, sys, random, math, json
sys.path.insert(0,'/home/anont/meme/.scr2')
SCR='/home/anont/meme/.scr2'
S=pickle.load(open(SCR+'/surface.pkl','rb'))
structs=S['structs']; base=S['base']; mat=S['mat']; FIL=S['filters']; fs=S['fsizes']
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))
NS=len(structs); NF=len(FIL)
p("structures=%d filters=%d cells=%d"%(NS,NF,NS*NF))

MIN_K=20; MIN_KC=8

# ---------- unconditional response surface ----------
p("")
p("=== A. UNCONDITIONAL SURFACE (no deployer filter) ===")
byg=collections.defaultdict(list)
for i,(tn,pn,h,mn) in enumerate(structs):
    btr,bva,bmed,bres,ktr,kva=base[i]
    byg[('timing',tn)].append(bva); byg[('pos',pn)].append(bva)
    byg[('hold',h)].append(bva); byg[('mod',mn)].append(bva)
for g in ('timing','pos','hold','mod'):
    p(" -- %s (validate-split mint-equal mean net, toll 1.14%%, dropout -30%%, cap +300%%)"%g)
    for k,v in sorted(((k,v) for k,v in byg.items() if k[0]==g), key=lambda x:str(x[0][1])):
        p("    %-14s cells=%3d  mean=%+.4f  best=%+.4f  worst=%+.4f  fracPos=%.2f"%(
            str(k[1]),len(v),statistics.mean(v),max(v),min(v),sum(1 for x in v if x>0)/len(v)))
allb=[b[1] for b in base]
p("  overall unconditional validate cells: mean=%+.4f  fracPos=%.3f  best=%+.4f"%(
    statistics.mean(allb),sum(1 for x in allb if x>0)/len(allb),max(allb)))
bi=max(range(NS),key=lambda i:base[i][1])
p("  best unconditional structure:",structs[bi],"tr=%+.4f va=%+.4f"%(base[bi][0],base[bi][1]))

# ---------- filter-level robustness ----------
p("")
p("=== B. DEPLOYER-FILTER EDGE ACROSS THE WHOLE STRUCTURE GRID ===")
p("edge = filtered mint-equal mean - same-structure UNCONDITIONAL mean (this is the")
p("       random-entry / random-mint control demanded by the contract).")
rowsum=[]
for j,f in enumerate(FIL):
    tre=[]; vae=[]
    for i in range(NS):
        c=mat[i][j]
        if c is None: continue
        trm,trk,vam,vamed,vak,vakc,van,vares,vm50,vm25,vraw,trkc=c
        if trk<MIN_K or vak<MIN_K or vakc<MIN_KC: continue
        tre.append(trm-base[i][0]); vae.append(vam-base[i][1])
    if len(vae)<50:
        rowsum.append((f,None)); continue
    rowsum.append((f,dict(n=len(vae),
        tr_mean=statistics.mean(tre), tr_pos=sum(1 for x in tre if x>0)/len(tre),
        va_mean=statistics.mean(vae), va_pos=sum(1 for x in vae if x>0)/len(vae),
        va_med=statistics.median(vae))))
ok=[(f,d) for f,d in rowsum if d]
ok.sort(key=lambda x:-x[1]['va_mean'])
p("%-26s %6s %8s %6s %8s %6s %8s   (ktr,kva)"%("filter","cells","TRedge","TR+%","VAedge","VA+%","VAedgeMed"))
for f,d in ok:
    p("%-26s %6d %+8.4f %6.2f %+8.4f %6.2f %+8.4f   %s"%(
        f,d['n'],d['tr_mean'],d['tr_pos'],d['va_mean'],d['va_pos'],d['va_med'],fs[f]))
p("")
p("filters with BOTH train and validate mean edge > 0 and both frac-positive > 0.60:")
dual=[(f,d) for f,d in ok if d['tr_mean']>0 and d['va_mean']>0 and d['tr_pos']>0.6 and d['va_pos']>0.6]
for f,d in dual:
    p("   %-26s TRedge=%+.4f (%.2f)  VAedge=%+.4f (%.2f)  cells=%d  k=%s"%(
        f,d['tr_mean'],d['tr_pos'],d['va_mean'],d['va_pos'],d['n'],fs[f]))
if not dual: p("   NONE")
pickle.dump(dict(ok=ok,dual=dual),open(SCR+'/filtsum.pkl','wb'))
open(SCR+'/surface_analyze.out','w').write("\n".join(o))
