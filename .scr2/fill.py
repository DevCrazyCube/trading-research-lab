"""How fragile is the +200% fill?  If most winners are stamped inside the
entry bar itself, the result rests on an intrabar-path assumption in the most
chaotic minute of the coin's life."""
import sys, bisect, statistics, collections
sys.path.insert(0,'/home/anont/meme/.scr2')
import engine as E, sweep as SW
SCR='/home/anont/meme/.scr2'
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))
S=SW.FSET['rate>=5/h']
for hold in (30,180,480):
    for sp,nm in ((SW.TRAIN,'TRAIN'),(SW.VALID,'VALID')):
        sel=[m for m in sp if m in S]
        bars_to_tp=[]; onbar0=0; gap=0; ntp=0; other=0
        # conservative variant: TP can only fill from the bar AFTER the entry bar
        cons=[]
        for m in sel:
            ts,op,hi,lo,cl,n=E.PK[m]
            if n<2: continue
            j=1; te=ts[j]; epx=op[j]; tp=epx*3.0
            eidx=bisect.bisect_left(ts,te+hold*60,j)
            last=eidx if eidx<n else n-1
            hit=None
            for b in range(j,last+1):
                if hi[b]>=tp: hit=b; break
            if hit is not None:
                ntp+=1
                bars_to_tp.append(hit-j)
                if hit==j: onbar0+=1
                if op[hit]>=tp: gap+=1
            else: other+=1
            # conservative: skip the entry bar for TP detection
            hit2=None
            for b in range(j+1,last+1):
                if hi[b]>=tp: hit2=b; break
            if hit2 is not None:
                px=max(tp,op[hit2]); g=px/epx-1.0
            elif eidx<n:
                g=op[eidx]/epx-1.0
            else:
                cons.append(-0.30); continue
            if g>SW.CAP: g=SW.CAP
            cons.append((1+g)*(1-E.TOLL_A)-1.0)
        p("h%-5d %-6s k=%d  TPhit=%d (%.2f)  of those: onEntryBar=%d (%.2f)  gappedThrough=%d"%(
            hold,nm,len(sel),ntp,ntp/len(sel),onbar0,onbar0/max(ntp,1),gap))
        p("        bars-from-entry to TP: median=%s  p90=%s"%(
            statistics.median(bars_to_tp) if bars_to_tp else None,
            sorted(bars_to_tp)[int(.9*len(bars_to_tp))] if bars_to_tp else None))
        p("        CONSERVATIVE (TP cannot fill on the entry bar): mean=%+.4f median=%+.4f k=%d"%(
            statistics.mean(cons),statistics.median(cons),len(cons)))
        # same conservative variant on ALL mints in the split (the control)
        allc=[]
        for m in sp:
            ts,op,hi,lo,cl,n=E.PK[m]
            if n<2: continue
            j=1; te=ts[j]; epx=op[j]; tp=epx*3.0
            eidx=bisect.bisect_left(ts,te+hold*60,j)
            last=eidx if eidx<n else n-1
            hit2=None
            for b in range(j+1,last+1):
                if hi[b]>=tp: hit2=b; break
            if hit2 is not None: g=max(tp,op[hit2])/epx-1.0
            elif eidx<n: g=op[eidx]/epx-1.0
            else: allc.append(-0.30); continue
            if g>SW.CAP: g=SW.CAP
            allc.append((1+g)*(1-E.TOLL_A)-1.0)
        p("        CONSERVATIVE unconditional control: mean=%+.4f k=%d  -> edge=%+.4f"%(
            statistics.mean(allc),len(allc),statistics.mean(cons)-statistics.mean(allc)))
    p("")
open(SCR+'/fill.out','w').write("\n".join(o))
