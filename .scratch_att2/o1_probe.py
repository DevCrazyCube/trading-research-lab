import sqlite3, json, hashlib, collections, statistics as st
OUT=open('/home/anont/meme/.scratch_att2/o1.txt','w')
def P(*a): print(*a,file=OUT)
def hh(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
rows=[r for r in c.execute('select mint,pool,n_bars,first_ts,last_ts,status from ohlcv where n_bars>0')]
h12=[r for r in rows if hh(r[0]) in (1,2)]
P('h12 ohlcv mints with bars:',len(h12))
P('status',collections.Counter(r[5] for r in h12))
nb=sorted(r[2] for r in h12)
P('n_bars min/p25/med/p75/max',[nb[i] for i in (0,len(nb)//4,len(nb)//2,3*len(nb)//4,-1)],'sum',sum(nb))
P('first_ts range',min(r[3] for r in h12),max(r[3] for r in h12))
P('last_ts range',min(r[4] for r in h12),max(r[4] for r in h12))
m0=h12[0][0]
bj=c.execute('select bars_json from ohlcv where mint=?',(m0,)).fetchone()[0]
b=json.loads(bj)
P('sample bars type',type(b),'len',len(b))
P('first 3 rows (as stored, newest first):',b[:3])
P('last 3:',b[-3:])

# window_labels join
w=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
P('window_label cols',[r[1] for r in w.execute('pragma table_info(window_label)')])
S12=set(r[0] for r in h12)
n=0; creators={}
cre=collections.Counter()
allrows=[]
for mint,creator,cs,bt,comp in w.execute('select mint,creator,create_slot,block_time,complete from window_label'):
    allrows.append((mint,creator,cs,bt,comp))
    cre[creator]+=1
P('window_label rows',len(allrows),'unique creators',len(cre))
inw=set(r[0] for r in allrows)
P('h12 ohlcv mints found in window_labels:',len(S12 & inw),'of',len(S12))

# fresh snapshots
snap=collections.defaultdict(list)
for line in open('/home/anont/meme/research/midcap/fresh_snapshots.jsonl'):
    line=line.strip()
    if not line: continue
    try: d=json.loads(line)
    except Exception: continue
    if 'mint' not in d: continue
    if hh(d['mint']) not in (1,2): continue
    snap[d['mint']].append(d)
P('h12 mints in fresh_snapshots:',len(snap))
P('h12 ohlcv mints WITH snapshots:',len(S12 & set(snap)))
k=list(snap)[0]
P('snapshot keys',sorted(snap[k][0].keys()))
OUT.close()
