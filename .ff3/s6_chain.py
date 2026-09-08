import pickle,collections,statistics,json
o=open('/home/anont/meme/.ff3/step6.txt','w')
tapes=pickle.load(open('/home/anont/meme/.ff3/tapes.pkl','rb'))
allowed=json.load(open('/home/anont/meme/.ff3/allowed.json'))
perfect=0; broken=0
firstbreak={}
nb=collections.Counter()
lastslot_perfect=[]
for bc,tr in tapes.items():
    tr=[r for r in tr if not (r[10] or '').startswith('create')]
    if len(tr)<2: continue
    breaks=0; fb=None
    for i in range(1,len(tr)):
        if tr[i][4]!=tr[i-1][6]:
            breaks+=1
            if fb is None: fb=i
    nb[min(breaks,10)]+=1
    if breaks==0: perfect+=1; lastslot_perfect.append(tr[-1][0])
    else:
        broken+=1; firstbreak[bc]=(fb,len(tr),tr[fb][0])
o.write("curves>=2 trades: perfect chain %d broken %d\n"%(perfect,broken))
o.write("breaks hist %s\n"%sorted(nb.items()))
# prefix length distribution for broken
pl=sorted(v[0] for v in firstbreak.values())
if pl: o.write("broken: prefix len p25 %d p50 %d p75 %d\n"%(pl[len(pl)//4],pl[len(pl)//2],pl[3*len(pl)//4]))
fbslots=sorted(v[2] for v in firstbreak.values())
if fbslots: o.write("first-break slot p10 %d p50 %d p90 %d\n"%(fbslots[len(fbslots)//10],fbslots[len(fbslots)//2],fbslots[int(len(fbslots)*0.9)]))
if lastslot_perfect:
    ls=sorted(lastslot_perfect); o.write("perfect-chain last slot p10 %d p50 %d p90 %d max %d\n"%(ls[len(ls)//10],ls[len(ls)//2],ls[int(len(ls)*0.9)],ls[-1]))
# total trades in perfect-prefixes
tot=0
for bc,tr in tapes.items():
    tr=[r for r in tr if not (r[10] or '').startswith('create')]
    if len(tr)<2: continue
    if bc in firstbreak: tot+=firstbreak[bc][0]
    else: tot+=len(tr)
o.write("trades usable in perfect prefixes: %d\n"%tot)
o.close()
