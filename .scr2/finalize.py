"""Finalist validation: cluster(creator) bootstrap + equal-size random-subset
null + explicit same-structure random-entry control, on the VALIDATE split."""
import sys, json, pickle, statistics, random, collections
sys.path.insert(0,'/home/anont/meme/.scr2')
import engine as E, sweep as SW
SCR='/home/anont/meme/.scr2'
random.seed(20260904)

TIM=dict(E.TIMINGS); POS=dict(E.POSITIONS); MOD=dict(E.MODS)

def stats_for(per, mints):
    return SW.cell(per, mints)

def boot_ci(per, mints, reps=4000):
    bycre=collections.defaultdict(list)
    for m in mints:
        if m in per: bycre[SW.CREATOR.get(m,m)].append(m)
    cres=list(bycre)
    if not cres: return None
    vals={m:SW.mint_stat(per[m],E.TOLL_A,-0.30,SW.CAP) for m in mints if m in per}
    out=[]
    for _ in range(reps):
        pick=[cres[random.randrange(len(cres))] for _ in cres]
        v=[vals[m] for c in pick for m in bycre[c]]
        out.append(sum(v)/len(v))
    out.sort()
    return out[int(0.025*reps)], out[int(0.5*reps)], out[int(0.975*reps)]

def subset_null(per, pool, k, reps=4000):
    vals=[SW.mint_stat(per[m],E.TOLL_A,-0.30,SW.CAP) for m in pool if m in per]
    if len(vals)<k: return None
    out=[]
    for _ in range(reps):
        s=random.sample(vals,k)
        out.append(sum(s)/k)
    out.sort()
    return out

def run(cands):
    res=[]
    for c in cands:
        timing=TIM[c['timing']]; position=POS[c['pos']]; mod=MOD[c['mod']]
        per={}
        for m in E.MINTS:
            r=E.sim_mint(m,timing,position,c['hold'],mod)
            if r is not None: per[m]=r
        F=SW.FSET[c['filt']]
        tr=[m for m in SW.TRAIN if m in F]; va=[m for m in SW.VALID if m in F]
        ct=stats_for(per,tr); cv=stats_for(per,va)
        btr=stats_for(per,SW.TRAIN); bva=stats_for(per,SW.VALID)
        ci=boot_ci(per,va)
        null=subset_null(per,SW.VALID,cv['k']) if cv else None
        pval=None
        if null: pval=sum(1 for x in null if x>=cv['mean'])/len(null)
        pooled=stats_for(per,[m for m in E.MINTS if m in F])
        res.append(dict(spec=c,
            tr={k2:ct[k2] for k2 in ct if k2!='vals'} if ct else None,
            va={k2:cv[k2] for k2 in cv if k2!='vals'} if cv else None,
            base_tr=btr['mean'] if btr else None, base_va=bva['mean'] if bva else None,
            base_va_med=bva['med'] if bva else None,
            ci=ci, p_subset=pval,
            pooled_mean=pooled['mean'] if pooled else None,
            pooled_k=pooled['k'] if pooled else None))
    return res

if __name__=='__main__':
    cands=json.load(open(SCR+'/cands.json'))
    r=run(cands)
    o=[]
    for x in r:
        s=x['spec']
        o.append("### %s | %s/%s/h%d/%s"%(s['filt'],s['timing'],s['pos'],s['hold'],s['mod']))
        o.append("  TRAIN   mean=%+.4f med=%+.4f k=%d kc=%d n=%d res=%.3f   (uncond %+.4f)"%(
            x['tr']['mean'],x['tr']['med'],x['tr']['k'],x['tr']['kc'],x['tr']['n'],x['tr']['res'],x['base_tr']))
        v=x['va']
        o.append("  VALID   mean=%+.4f med=%+.4f k=%d kc=%d n=%d res=%.3f   (uncond %+.4f med %+.4f)"%(
            v['mean'],v['med'],v['k'],v['kc'],v['n'],v['res'],x['base_va'],x['base_va_med']))
        o.append("  VALID   edge_vs_random_control=%+.4f  m50=%+.4f m100=%+.4f toll2.5=%+.4f uncapped=%+.4f"%(
            v['mean']-x['base_va'],v['mean50'],v['mean100'],v['mean25'],v['mean_raw']))
        o.append("  VALID   creator-cluster bootstrap 95%% CI = [%+.4f, %+.4f] median %+.4f"%(x['ci'][0],x['ci'][2],x['ci'][1]) if x['ci'] else "  no ci")
        o.append("  VALID   equal-size random-subset null p = %.4f"%x['p_subset'])
        o.append("  POOLED(h1+h2) mean=%+.4f k=%d"%(x['pooled_mean'],x['pooled_k']))
        o.append("")
    open(SCR+'/finalize.out','w').write("\n".join(o))
    pickle.dump(r,open(SCR+'/finalize.pkl','wb'))
