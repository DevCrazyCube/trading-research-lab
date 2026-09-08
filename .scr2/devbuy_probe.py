import sqlite3, pickle, collections, json, time
SCR='/home/anont/meme/.scr2'
D=pickle.load(open(SCR+'/data.pkl','rb'))
META=D['meta']; BARS=D['bars']
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))
bcs={META[m]['bc']:m for m in BARS if m in META}
p("our bonding curves:",len(bcs))
c=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro',uri=True)
t=time.time()
cnt=collections.Counter()
seen=collections.Counter()
for bc,slot,vqb,vqa in c.execute("select bonding_curve,slot,virtual_quote_before,virtual_quote_after from reserve_observation"):
    seen[bc]+=1
p("distinct bonding_curves in reserve_observation:",len(seen),"scan %.0fs"%(time.time()-t))
hit=[b for b in bcs if b in seen]
p("our curves present:",len(hit),"of",len(bcs))
p("obs per our curve (hist):",sorted(collections.Counter(min(seen[b],50) for b in hit).items())[:30])
# how many creates in window_labels are covered at all
wl=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
allbc=[r[0] for r in wl.execute("select bonding_curve from window_label")]
wl.close()
p("window creates covered by reserve_observation:",sum(1 for b in allbc if b in seen),"of",len(allbc))
c.close()
open(SCR+'/devbuy_probe.out','w').write("\n".join(o))
