import sqlite3, json, hashlib, math, os, pickle, statistics as st
D='/home/anont/meme/research/'
OUT='/home/anont/meme/.scr/'

def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

# ---------- metadata ----------
meta={}   # mint -> dict
snap_first={}
nline=0
with open(D+'midcap/fresh_snapshots.jsonl') as f:
    for ln in f:
        nline+=1
        try: r=json.loads(ln)
        except: continue
        m=r.get('mint')
        if not m: continue
        if h3(m)==0: continue           # NEVER touch holdout
        d=meta.setdefault(m,{'replies':0,'has_x':0,'has_tg':0,'has_web':0,'creator':None,
                             'created_ms':None,'first_mcap':None,'first_ts':None,'max_mcap':0,
                             'nsnap':0,'first_complete':None,'sym':'','name':''})
        d['nsnap']+=1
        for k in ('has_x','has_tg','has_web'):
            if r.get(k): d[k]=1
        try: d['replies']=max(d['replies'], int(r.get('replies') or 0))
        except: pass
        if r.get('creator'): d['creator']=r['creator']
        if r.get('created_ms'): d['created_ms']=r['created_ms']
        mc=r.get('mcap')
        if mc:
            d['max_mcap']=max(d['max_mcap'],mc)
        ts=r.get('ts_ms')
        if ts is not None and (d['first_ts'] is None or ts<d['first_ts']):
            d['first_ts']=ts; d['first_mcap']=mc; d['first_complete']=r.get('complete')
            d['sym']=r.get('sym') or ''; d['name']=r.get('name') or ''
print('snapshot lines',nline,'meta mints (h12)',len(meta))

# ---------- creator features from window_labels (h12 only) ----------
c2=sqlite3.connect('file:'+D+'b11a/window_labels.sqlite?mode=ro',uri=True)
creates=[]
for mint,creator,slot,bt,comp in c2.execute("select mint,creator,create_slot,block_time,complete from window_label"):
    if not mint or h3(mint)==0: continue
    creates.append((creator,slot,bt,comp,mint))
creates.sort(key=lambda x:(x[1] or 0))
prior_n={}; prior_g={}
seen_n={}; seen_g={}
mint_create={}
for creator,slot,bt,comp,mint in creates:
    prior_n[mint]=seen_n.get(creator,0)
    prior_g[mint]=seen_g.get(creator,0)
    mint_create[mint]=(creator,slot,bt,comp)
    if creator:
        seen_n[creator]=seen_n.get(creator,0)+1
        if comp: seen_g[creator]=seen_g.get(creator,0)+1
print('creates h12',len(creates))

# ---------- bars ----------
c=sqlite3.connect('file:'+D+'midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
MINTS={}
gmax=0
for mint,bj,nb in c.execute("select mint,bars_json,n_bars from ohlcv"):
    if h3(mint)==0: continue
    if not bj: continue
    b=json.loads(bj)
    if len(b)<6: continue
    b.sort(key=lambda x:x[0])
    MINTS[mint]=b
    gmax=max(gmax,b[-1][0])
print('mints with bars h12',len(MINTS),'global last ts',gmax)
print('total bars', sum(len(v) for v in MINTS.values()))

FEATN=['age','gap','r1','r5','r15','r60','dd','rv15','volz','nb15','body','wickup','wickdn',
       'pxrel','lvol','lmcap','upfrac','hi60','vol15','rng']
MFEATN=['has_x','has_tg','has_web','replies','pcreate','pgrad','age_at_first','lmc0','nsnap','symlen']

def build(mint,b):
    n=len(b)
    ts=[x[0] for x in b]; op=[x[1] for x in b]; hi=[x[2] for x in b]; lo=[x[3] for x in b]
    cl=[x[4] for x in b]; vo=[x[5] for x in b]
    F=[[0.0]*len(FEATN) for _ in range(n)]
    runmax=cl[0]; vols_seen=[]
    j5=0;j15=0;j60=0
    for i in range(n):
        t=ts[i]
        while ts[j5] < t-300: j5+=1
        while ts[j15] < t-900: j15+=1
        while ts[j60] < t-3600: j60+=1
        runmax=max(runmax,hi[i])
        f=F[i]
        f[0]=(t-ts[0])/60.0
        f[1]=(t-ts[i-1])/60.0 if i>0 else 0.0
        f[2]=cl[i]/cl[i-1]-1 if i>0 else 0.0
        f[3]=cl[i]/cl[j5]-1 if j5<i else 0.0
        f[4]=cl[i]/cl[j15]-1 if j15<i else 0.0
        f[5]=cl[i]/cl[j60]-1 if j60<i else 0.0
        f[6]=cl[i]/runmax-1
        seg=[cl[k]/cl[k-1]-1 for k in range(max(1,j15),i+1)]
        f[7]=st.pstdev(seg) if len(seg)>1 else 0.0
        v15=sum(vo[j15:i+1]); f[18]=v15
        vols_seen.append(v15)
        med=sorted(vols_seen)[len(vols_seen)//2]
        f[8]=math.log10((v15+1)/(med+1))
        f[9]=float(i-j15+1)
        f[10]=cl[i]/op[i]-1
        f[11]=hi[i]/cl[i]-1
        f[12]=cl[i]/lo[i]-1 if lo[i]>0 else 0.0
        f[13]=cl[i]/cl[0]-1
        f[14]=math.log10(vo[i]+1)
        f[15]=math.log10(cl[i]*1e9+1)
        up=sum(1 for k in range(max(1,j15),i+1) if cl[k]>cl[k-1])
        f[16]=up/max(1,(i-max(1,j15)+1))
        h60=max(hi[j60:i+1]); f[17]=cl[i]/h60-1
        f[19]=(hi[i]-lo[i])/cl[i] if cl[i]>0 else 0.0
    return ts,op,hi,lo,cl,vo,F

DB={}
for mint,b in MINTS.items():
    ts,op,hi,lo,cl,vo,F=build(mint,b)
    md=meta.get(mint,{})
    cr=mint_create.get(mint)
    mf=[float(md.get('has_x',0)),float(md.get('has_tg',0)),float(md.get('has_web',0)),
        float(md.get('replies',0)),float(prior_n.get(mint,0)),float(prior_g.get(mint,0)),0.0,
        math.log10((md.get('first_mcap') or 0)+1),float(md.get('nsnap',0)),float(len(md.get('sym') or ''))]
    cms=md.get('created_ms')
    if cms: mf[6]=(ts[0]-cms/1000.0)/3600.0
    elif cr and cr[2]: mf[6]=(ts[0]-cr[2])/3600.0
    else: mf[6]=-1.0
    DB[mint]={'ts':ts,'op':op,'hi':hi,'lo':lo,'cl':cl,'vo':vo,'F':F,'MF':mf,'h':h3(mint)}

with open(OUT+'db.pkl','wb') as f: pickle.dump({'DB':DB,'FEATN':FEATN,'MFEATN':MFEATN,'gmax':gmax},f)
print('saved', len(DB))
import collections
print('h split', collections.Counter(v['h'] for v in DB.values()))
print('meta coverage', sum(1 for m in DB if m in meta), '/', len(DB))
print('create coverage', sum(1 for m in DB if m in mint_create), '/', len(DB))
