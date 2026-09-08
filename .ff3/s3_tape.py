import sqlite3,json,collections,pickle,sys
o=open('/home/anont/meme/.ff3/step3.txt','w')
allowed=json.load(open('/home/anont/meme/.ff3/allowed.json'))
con=sqlite3.connect('file::memory:',uri=True)
con.execute("ATTACH DATABASE 'file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro' AS b")
con.execute("CREATE TABLE al(bc TEXT PRIMARY KEY)")
con.executemany("INSERT INTO al VALUES(?)",[(k,) for k in allowed])
con.commit()
q="""select ro.bonding_curve, ro.slot, ro.transaction_index, ro.outer_index, ro.inner_index,
 ro.virtual_quote_before, ro.virtual_token_before, ro.virtual_quote_after, ro.virtual_token_after,
 ro.real_quote_after, ro.real_token_after, i.idl_name, i.accounts_json
 from b.reserve_observation ro join al on al.bc=ro.bonding_curve
 left join b.instruction i on i.slot=ro.slot and i.transaction_index=ro.transaction_index
   and i.outer_index=ro.outer_index and i.inner_index=ro.inner_index"""
tapes=collections.defaultdict(list)
namecnt=collections.Counter()
noacct=0; n=0
for row in con.execute(q):
    bc,slot,ti,oi,ii,vqb,vtb,vqa,vta,rqa,rta,name,acc=row
    n+=1
    namecnt[name]+=1
    if vqb is None or vqa is None or vtb is None or vta is None: continue
    tr=None
    if acc:
        try:
            a=json.loads(acc)
        except Exception:
            a=None
        if a:
            if name in ('buy','sell','buy_exact_sol_in','buy_exact_quote_in'):
                if len(a)>6: tr=a[6]
            elif name and name.endswith('_v2'):
                if len(a)>13: tr=a[13]
            else:
                if len(a)>13: tr=a[13]
                elif len(a)>6: tr=a[6]
    if tr is None: noacct+=1
    tapes[bc].append((slot,ti,oi,ii,vqb,vtb,vqa,vta,rqa,rta,name,tr))
o.write("rows %d curves %d noacct %d\n"%(n,len(tapes),noacct))
o.write("idl_name on reserve rows: %s\n"%namecnt.most_common(20))
for bc in tapes: tapes[bc].sort(key=lambda r:(r[0],r[1],r[2],r[3]))
lens=sorted(len(v) for v in tapes.values())
o.write("trades/curve pct: min %d p25 %d p50 %d p75 %d p90 %d max %d\n"%(lens[0],lens[len(lens)//4],lens[len(lens)//2],lens[3*len(lens)//4],lens[int(len(lens)*0.9)],lens[-1]))
pickle.dump(dict(tapes),open('/home/anont/meme/.ff3/tapes.pkl','wb'),protocol=4)
# sample tape
k=[bc for bc in tapes if len(tapes[bc])>50][0]
for r in tapes[k][:6]: o.write(str(r)+"\n")
o.close()
