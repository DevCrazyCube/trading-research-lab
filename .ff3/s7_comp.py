import pickle,json,collections
o=open('/home/anont/meme/.ff3/step7.txt','w')
tapes=pickle.load(open('/home/anont/meme/.ff3/tapes.pkl','rb'))
allowed=json.load(open('/home/anont/meme/.ff3/allowed.json'))
c=collections.Counter()
for bc in tapes:
    v=allowed[bc]; c[('complete',v[4])]+=1
o.write("taped curves by complete: %s\n"%dict(c))
o.write("all allowed by complete: %s\n"%dict(collections.Counter(v[4] for v in allowed.values())))
# create slot distribution of taped vs all
ts=sorted(allowed[bc][2] for bc in tapes)
al=sorted(v[2] for v in allowed.values())
o.write("taped create_slot p0 %d p50 %d p100 %d\n"%(ts[0],ts[len(ts)//2],ts[-1]))
o.write("all   create_slot p0 %d p50 %d p100 %d\n"%(al[0],al[len(al)//2],al[-1]))
# how many allowed curves created in the taped-create window
lo,hi=ts[0],ts[-1]
inwin=[v for v in allowed.values() if lo<=v[2]<=hi]
o.write("allowed created in taped window: %d ; taped %d ; frac %.3f\n"%(len(inwin),len(tapes),len(tapes)/len(inwin)))
o.write("complete among inwin: %s\n"%dict(collections.Counter(v[4] for v in inwin)))
# trades count vs complete
tn=collections.defaultdict(list)
for bc,tr in tapes.items(): tn[allowed[bc][4]].append(len(tr))
for k,v in tn.items():
    v=sorted(v); o.write("complete=%s n=%d median trades %d\n"%(k,len(v),v[len(v)//2]))
o.close()
