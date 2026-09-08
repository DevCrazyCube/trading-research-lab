import sys, statistics as st, math, random, json
sys.path.insert(0,'/home/anont/meme/.scratch_att2')
from engine import *
OUT=open('/home/anont/meme/.scratch_att2/power_out.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()

ev,g,FEND=load()
EVS=build(ev,g,FEND,False); CTL=build(ev,g,FEND,True)
P('h12 event series %d | h12-control placebo series %d'%(len(EVS),len(CTL)))

def table(series_list,label):
    P('--- %s ---'%label)
    P('%5s %6s %6s %9s %9s %9s %9s %6s'%('H','n','fill','mean1.14','med1.14','mean2.5','boot_lo','res%'))
    for H in [3.0,7.5,15.0,30.0,60.0,120.0,180.0]:
        vals=[];vals2=[];nd=0;nf=0;ntot=0
        for s in series_list:
            ei=entry_index(s,0.0)
            if ei is None: nf+=1; continue
            if s.avail < s.t[ei]+H: continue
            ntot+=1
            o=sim(s,ei,H,'hold','flat',{})
            if o is None or o[0]=='DROP':
                vals.append(-0.30); vals2.append(-0.30); nd+=1
            else:
                vals.append(o[0]-o[1]*0.0114); vals2.append(o[0]-o[1]*0.025)
        if not vals: continue
        rnd=random.Random(3); n=len(vals); ms=[]
        for _ in range(4000): ms.append(sum(vals[rnd.randrange(n)] for _ in range(n))/n)
        ms.sort()
        P('%5.1f %6d %6d %+8.2f%% %+8.2f%% %+8.2f%% %+8.2f%% %5.1f'%(
          H,len(vals),nf,st.mean(vals)*100,st.median(vals)*100,st.mean(vals2)*100,
          ms[int(0.05*4000)]*100,(len(vals)-nd)/len(vals)*100))
table(EVS,'ATTENTION EVENT MINTS (h12, n<=70) -- buy at next real trade after the boost appears, hold H, market exit')
table(CTL,'MATCHED CONTROL MINTS (h12, n<=49) -- identical structure, no boost')

# paired difference on the 49 series where BOTH mint and ctrl are h12
P('--- PAIRED DIFFERENCE (event minus its own matched control, same clock) ---')
P('%5s %5s %10s %10s %10s %10s'%('H','n','mean_diff','med_diff','sd','boot_lo'))
pairs={}
for s in CTL: pairs[(s.t0)]=s
POW={}
for H in [3.0,7.5,15.0,30.0,60.0,120.0]:
    ds=[]
    for s in EVS:
        cs=[x for x in CTL if x.t0==s.t0 and x.t is s.t or (x.t0==s.t0)]
        c=None
        for x in CTL:
            if x.t0==s.t0: c=x; break
        if c is None: continue
        ei=entry_index(s,0.0); ci=entry_index(c,0.0)
        if ei is None or ci is None: continue
        if s.avail < s.t[ei]+H or c.avail < c.t[ci]+H: continue
        a=sim(s,ei,H,'hold','flat',{}); b=sim(c,ci,H,'hold','flat',{})
        ra = -0.30 if (a is None or a[0]=='DROP') else a[0]-a[1]*0.0114
        rb = -0.30 if (b is None or b[0]=='DROP') else b[0]-b[1]*0.0114
        ds.append(ra-rb)
    if len(ds)<4: continue
    sd=st.pstdev(ds) if len(ds)>1 else 0
    rnd=random.Random(5); n=len(ds); ms=[]
    for _ in range(4000): ms.append(sum(ds[rnd.randrange(n)] for _ in range(n))/n)
    ms.sort()
    P('%5.1f %5d %+9.2f%% %+9.2f%% %9.2f%% %+9.2f%%'%(H,len(ds),st.mean(ds)*100,st.median(ds)*100,sd*100,ms[int(0.05*4000)]*100))
    POW[H]=(sd,len(ds))

P('--- POWER: n needed (one-sided alpha=0.05, power=0.80) on the PAIRED DIFFERENCE ---')
P('%5s %8s %s'%('H','sd','n needed to detect an effect of ...'))
za,zb=1.645,0.8416
for H,(sd,n) in sorted(POW.items()):
    line=[]
    for eff in (0.05,0.10,0.20,0.30,0.50):
        need=math.ceil(((za+zb)*sd/eff)**2)
        line.append('%+.0f%%:n=%d'%(eff*100,need))
    P('%5.1f %7.1f%%  %s   (have n=%d)'%(H,sd*100,'  '.join(line),n))

P('--- POWER on the UNPAIRED event-mint mean vs a 0%% bar ---')
for H in [15.0,60.0]:
    vals=[]
    for s in EVS:
        ei=entry_index(s,0.0)
        if ei is None or s.avail < s.t[ei]+H: continue
        o=sim(s,ei,H,'hold','flat',{})
        vals.append(-0.30 if (o is None or o[0]=='DROP') else o[0]-o[1]*0.0114)
    sd=st.pstdev(vals)
    P('H=%.0fm n=%d sd=%.1f%%  n needed: +5%%:%d  +10%%:%d  +20%%:%d  +30%%:%d'%(
      H,len(vals),sd*100,*[math.ceil(((za+zb)*sd/e)**2) for e in (0.05,0.10,0.20,0.30)]))
OUT.close()
