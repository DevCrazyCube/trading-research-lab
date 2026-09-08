"""Attention event-study sweep engine.
Harness contract A-G enforced. Only mints with md5%3 in (1,2)."""
import json, hashlib, collections, statistics as st, math, random

ATT='/home/anont/meme/research/midcap/attention.jsonl'
def hh(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

def load():
    ev={}; tk=[]
    for line in open(ATT):
        line=line.strip()
        if not line: continue
        try: d=json.loads(line)
        except Exception: continue
        if d.get('ev')=='EVENT': ev.setdefault((d['mint'],d['ts_ms']),d)
        elif d.get('ev')=='TICK': tk.append(d)
    g=collections.defaultdict(list)
    for t in tk: g[(t['mint'],t['t0'])].append(t)
    for v in g.values(): v.sort(key=lambda x:x['ts_ms'])
    FEND=max(t['ts_ms'] for t in tk)
    return ev,g,FEND

class Series:
    """t: minutes since anchor; p: price path; c: control price path; q: liquidity."""
    __slots__=('mint','t0','t','p','c','q','meta','half','avail')
    def __init__(s,mint,t0,t,p,c,q,meta,half,avail):
        s.mint=mint;s.t0=t0;s.t=t;s.p=p;s.c=c;s.q=q;s.meta=meta;s.half=half;s.avail=avail

def build(ev,g,FEND,use_control=False):
    """use_control=True -> the series price path IS the matched control's path (placebo arm)."""
    out=[]
    for (m,t0),v in g.items():
        if hh(m) not in (1,2): continue
        ctrl=v[0].get('ctrl')
        if use_control:
            if not ctrl or hh(ctrl) not in (1,2): continue   # never touch h==0 mints
            pxs=[x.get('ctrl_px') for x in v]
            if any(x is None for x in pxs): continue
            p=pxs; c=[x['px'] for x in v]; ident=ctrl
        else:
            p=[x['px'] for x in v]; c=[x.get('ctrl_px') for x in v]; ident=m
        t=[(x['ts_ms']-t0)/60000.0 for x in v]
        q=[x.get('liq') for x in v]
        e=ev.get((m,t0),{})
        meta=dict(feed=e.get('feed'),total=e.get('total'),amount=e.get('amount'),
                  mcap=e.get('mcap'),liq=e.get('liq'),age_h=e.get('age_h'),sym=e.get('sym'))
        out.append(Series(ident,t0,t,p,c,q,meta,hh(m),(FEND-t0)/60000.0))
    return out

# ---------------- simulation ----------------
NOFILL=object(); DROP=object()

def entry_index(s,S,fillcap=30.0):
    """Contract A: signal at first tick with t>=S; enter at the NEXT tick that actually traded
       (price differs from prior tick). Returns index or None."""
    n=len(s.t); i=None
    for k in range(n):
        if s.t[k]>=S: i=k; break
    if i is None: return None
    for j in range(i+1,n):
        if s.p[j]!=s.p[j-1] and s.t[j]-s.t[i]<=fillcap:
            return j
        if s.t[j]-s.t[i]>fillcap: return None
    return None

def sim(s,ei,H,exit_kind,pos_kind,params):
    """Returns (gross_return_on_full_capital, n_legs_traded, resolved_bool)."""
    pe=s.p[ei]; te=s.t[ei]
    if pe<=0: return None
    target=te+H
    tp=params.get('tp'); sl=params.get('sl'); tr=params.get('tr')
    add_d=params.get('add_d'); add_u=params.get('add_u'); halfout=params.get('halfout')
    runmax=pe
    w_entry = 0.5 if pos_kind in ('dip_add','brk_add') else 1.0
    added=False; add_px=None
    sold_half=False; half_px=None
    exit_px=None
    n=len(s.p)
    ce=s.c[ei] if s.c[ei] else None
    reached=False
    for k in range(ei+1,n):
        if s.t[k]>target: break
        reached=True
        px=s.p[k]
        if px>runmax: runmax=px
        # position adds
        if pos_kind=='dip_add' and not added and px<=pe*(1-add_d): added=True; add_px=px
        if pos_kind=='brk_add' and not added and px>=pe*(1+add_u): added=True; add_px=px
        if pos_kind=='half_out' and not sold_half and halfout and px>=pe*(1+halfout):
            sold_half=True; half_px=px
        # exits
        if sl is not None and px<=pe*(1-sl): exit_px=px; break
        if tp is not None and px>=pe*(1+tp): exit_px=px; break
        if tr is not None and px<=runmax*(1-tr) and runmax>pe: exit_px=px; break
        if exit_kind=='ctrlcross' and ce and s.c[k]:
            if (px/pe-1) < (s.c[k]/ce-1): exit_px=px; break
        if exit_kind=='liqdrop' and s.q[ei] and s.q[k] is not None:
            if s.q[k] < params.get('liqf',0.5)*s.q[ei]: exit_px=px; break
    resolved=True
    if exit_px is None:
        # need a mark at/inside the horizon
        last=None
        for k in range(ei,n):
            if s.t[k]<=target: last=k
        if last is None or s.t[-1]<target-1.6:
            resolved=False; exit_px=None
        else:
            exit_px=s.p[last]
    if not resolved: return ('DROP',None,False)
    r_entry=(exit_px/pe-1.0)
    if pos_kind=='half_out' and sold_half:
        r_entry=0.5*(half_px/pe-1.0)+0.5*(exit_px/pe-1.0)
    legs=1.0*w_entry
    r=w_entry*r_entry
    if pos_kind in ('dip_add','brk_add'):
        if added:
            r+=0.5*(exit_px/add_px-1.0); legs+=0.5
    return (r,legs,True)

def net(r,legs,toll):
    return r - legs*toll

# ---------------- conditions ----------------
def cond_mask(s, ei, name):
    m=s.meta
    if name=='all': return True
    if name.startswith('feed='): return m.get('feed')==name[5:]
    if name=='paid': return m.get('total') is not None
    if name=='unpaid': return m.get('total') is None
    if name=='paid_ge50': return (m.get('total') or 0)>=50
    if name=='mcap_lt20k': return (m.get('mcap') or 0)<20000
    if name=='mcap_ge20k': return (m.get('mcap') or 0)>=20000
    if name=='mcap_ge100k': return (m.get('mcap') or 0)>=100000
    if name=='liq0': return (m.get('liq') or 0)<=0
    if name=='liq_gt0': return (m.get('liq') or 0)>0
    if name=='liq_ge20k': return (m.get('liq') or 0)>=20000
    if name=='age_lt30m': return (m.get('age_h') or 0)<0.5
    if name=='age_30m_6h': return 0.5<=(m.get('age_h') or 0)<6
    if name=='age_ge6h': return (m.get('age_h') or 0)>=6
    # entry-time path conditions (strictly <= signal tick)
    d = s.p[ei]/s.p[0]-1.0 if s.p[0] else 0.0
    if name=='drift_le_-10': return d<=-0.10
    if name=='drift_-10_0': return -0.10<d<=0.0
    if name=='drift_0_10': return 0.0<d<=0.10
    if name=='drift_gt10': return d>0.10
    if name=='drift_le0': return d<=0.0
    if name=='drift_gt0': return d>0.0
    cc = (s.c[ei]/s.c[0]-1.0) if (s.c[ei] and s.c[0]) else None
    if name=='rs_pos': return cc is not None and d>cc
    if name=='rs_neg': return cc is not None and d<=cc
    if name=='ctrl_dead': return cc is not None and cc<=-0.50
    if name=='ctrl_alive': return cc is not None and cc>-0.50
    if name=='liq_rising':
        return s.q[ei] is not None and s.q[0] is not None and s.q[ei]>s.q[0]
    if name=='liq_falling':
        return s.q[ei] is not None and s.q[0] is not None and s.q[ei]<=s.q[0]
    return False

CONDS=['all','feed=token-profiles/latest/v1','feed=token-boosts/latest/v1','feed=token-boosts/top/v1',
       'paid','unpaid','paid_ge50','mcap_lt20k','mcap_ge20k','mcap_ge100k','liq0','liq_gt0','liq_ge20k',
       'age_lt30m','age_30m_6h','age_ge6h','drift_le_-10','drift_-10_0','drift_0_10','drift_gt10',
       'drift_le0','drift_gt0','rs_pos','rs_neg','ctrl_dead','ctrl_alive','liq_rising','liq_falling']

# ---------------- grid ----------------
S_GRID=[0.0,1.5,3.0,5.0,7.5,15.0,30.0,45.0,60.0,90.0]
H_GRID=[3.0,7.5,15.0,30.0,60.0,120.0,180.0]
EXITS=[('hold',{}),
       ('tp25',{'tp':0.25}),('tp50',{'tp':0.50}),('tp100',{'tp':1.00}),('tp10',{'tp':0.10}),
       ('sl25',{'sl':0.25}),('sl50',{'sl':0.50}),
       ('tp25_sl25',{'tp':0.25,'sl':0.25}),('tp50_sl25',{'tp':0.50,'sl':0.25}),
       ('tp100_sl50',{'tp':1.00,'sl':0.50}),('tp25_sl50',{'tp':0.25,'sl':0.50}),
       ('trail25',{'tr':0.25}),('trail50',{'tr':0.50}),
       ('tp100_trail25',{'tp':1.00,'tr':0.25}),
       ('ctrlcross',{}),('liqdrop50',{'liqf':0.5})]
POS=[('flat',{}),('dip_add',{'add_d':0.25}),('brk_add',{'add_u':0.25}),('half_out',{'halfout':0.50})]
