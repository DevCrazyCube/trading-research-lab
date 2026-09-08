import pickle, json, hashlib, statistics as st, time
from collections import defaultdict, Counter
S='/home/anont/meme/.scratch_fc/'
D=pickle.load(open(S+'data1.pkl','rb'))
OUT=open(S+'build2.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()
def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

WL=D['WL']; bars=D['bars']; launch=D['launch']
mint2cre=D['mint2cre']; mint2bt=D['mint2bt']; mint2comp=D['mint2comp']

trad=sorted(bars)
P('tradeable', len(trad))
P('covered by bodies (dev features)', sum(1 for m in trad if m in launch))
# creator launch timeline (h12 only)
bycre=defaultdict(list)
for bc,m,cr,slot,bt,comp in WL:
    bycre[cr].append((bt,m,comp))
for v in bycre.values(): v.sort()

feat={}
for m in trad:
    cr=mint2cre[m]; bt=mint2bt[m]
    prior=[(b,mm,cp) for (b,mm,cp) in bycre[cr] if b<bt]
    npri=len(prior)
    gradn=sum(1 for (b,mm,cp) in prior if cp==1)
    # prior coins covered by bodies -> dev buy sizes
    pd=[launch[mm]['dev_buy_sol'] for (b,mm,cp) in prior if mm in launch]
    pdsell=[launch[mm]['dev_sell_sol']/max(launch[mm]['dev_buy_sol'],1e-9) for (b,mm,cp) in prior if mm in launch and launch[mm]['dev_buy_sol']>0]
    L=launch.get(m)
    feat[m]=dict(
        cre=cr, bt=bt, h=h3(m),
        n_prior=npri,
        grad_n=gradn,
        grad_frac=(gradn/npri) if npri else -1.0,
        gap_prev=((bt-prior[-1][0])/60.0) if npri else -1.0,
        n_prior_1h=sum(1 for (b,mm,cp) in prior if b>=bt-3600),
        prior_devbuy_med=(st.median(pd) if pd else -1.0),
        prior_devsell_frac_med=(st.median(pdsell) if pdsell else -1.0),
        n_prior_cov=len(pd),
        dev_buy_sol=(L['dev_buy_sol'] if L else -1.0),
        dev_first=(L['dev_first'] if L else -1),
        n_trades=(L['n_trades'] if L else -1),
        covered=1 if L else 0,
        nbars=len(bars[m]),
        first_ts=bars[m][0][0], last_ts=bars[m][-1][0],
    )
P('h==1 (train)', sum(1 for m in trad if feat[m]['h']==1), 'h==2 (validate)', sum(1 for m in trad if feat[m]['h']==2))
for k in ['n_prior','grad_n','gap_prev','dev_buy_sol','prior_devbuy_med','n_prior_cov','covered','dev_first']:
    vals=[feat[m][k] for m in trad]
    P(k,'nonneg n=',sum(1 for v in vals if v>=0),
      'dist', Counter(min(int(v),50) if isinstance(v,(int,float)) and v>=0 else -1 for v in vals).most_common(12))
P('grad_frac dist (npri>0)', Counter(round(feat[m]['grad_frac'],1) for m in trad if feat[m]['n_prior']>0).most_common(15))
P('creators among tradeable', len(set(feat[m]['cre'] for m in trad)))
cc=Counter(feat[m]['cre'] for m in trad)
P('mints per creator (tradeable)', Counter(cc.values()).most_common())
# bar timing: age at first bar
ages=[(bars[m][0][0]-feat[m]['bt'])/60.0 for m in trad]
ages.sort()
P('age(min) at first bar: p10/p50/p90', round(ages[len(ages)//10],1), round(ages[len(ages)//2],1), round(ages[9*len(ages)//10],1))
spans=[(bars[m][-1][0]-bars[m][0][0])/60.0 for m in trad]
spans.sort()
P('bar span(min): p10/p50/p90', round(spans[len(spans)//10],1), round(spans[len(spans)//2],1), round(spans[9*len(spans)//10],1))
pickle.dump(feat, open(S+'feat.pkl','wb'))
OUT.close()
