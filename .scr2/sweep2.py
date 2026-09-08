"""Second pass: record the FULL (structure x filter) surface, not just the
train-passing cells, so filter-level robustness can be judged as a plateau
rather than a spike.  Stores train/validate mint-equal means and the
same-structure unconditional control for every cell.
"""
import sys, time, pickle, statistics, json
sys.path.insert(0,'/home/anont/meme/.scr2')
import engine as E
import sweep as SW

SCR='/home/anont/meme/.scr2'
FILTERS=SW.FILTERS; FSET=SW.FSET
TRAIN=SW.TRAIN; VALID=SW.VALID
TRSET={f:[m for m in TRAIN if m in FSET[f]] for f,_ in FILTERS}
VASET={f:[m for m in VALID if m in FSET[f]] for f,_ in FILTERS}

def main():
    t0=time.time()
    structs=[]
    mat=[]   # per struct: list over filters of (tr_mean,tr_k,va_mean,va_med,va_k,va_kc,va_n,va_res,va_m50,va_m25)
    base=[]  # per struct: (tr_mean, va_mean, va_med, va_res)
    done=0
    total=len(E.TIMINGS)*len(E.POSITIONS)*len(E.HOLDS)*len(E.MODS)
    for tname,timing in E.TIMINGS:
        for pname,position in E.POSITIONS:
            for hold in E.HOLDS:
                for mname,mod in E.MODS:
                    per={}
                    for m in E.MINTS:
                        r=E.sim_mint(m,timing,position,hold,mod)
                        if r is not None: per[m]=r
                    btr=SW.cell(per,TRAIN); bva=SW.cell(per,VALID)
                    if btr is None or bva is None:
                        done+=1; continue
                    structs.append((tname,pname,hold,mname))
                    base.append((btr['mean'],bva['mean'],bva['med'],bva['res'],btr['k'],bva['k']))
                    row=[]
                    for f,_ in FILTERS:
                        ct=SW.cell(per,TRSET[f]); cv=SW.cell(per,VASET[f])
                        if ct is None or cv is None:
                            row.append(None); continue
                        row.append((ct['mean'],ct['k'],cv['mean'],cv['med'],cv['k'],cv['kc'],
                                    cv['n'],cv['res'],cv['mean50'],cv['mean25'],cv['mean_raw'],ct['kc']))
                    mat.append(row)
                    done+=1
                    if done%200==0:
                        open(SCR+'/sweep2.progress','w').write("%d/%d %.0fs\n"%(done,total,time.time()-t0))
    pickle.dump(dict(structs=structs,base=base,mat=mat,
                     filters=[f for f,_ in FILTERS],
                     fsizes={f:(len(TRSET[f]),len(VASET[f])) for f,_ in FILTERS}),
                open(SCR+'/surface.pkl','wb'),protocol=4)
    open(SCR+'/sweep2.out','w').write("structs=%d filters=%d elapsed=%.0fs\n"%(len(structs),len(FILTERS),time.time()-t0))

if __name__=='__main__':
    main()
