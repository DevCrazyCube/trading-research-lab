import sqlite3, pickle, random, collections
tape=pickle.load(open('/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/tape.pkl','rb'))
bycurve=collections.Counter(r[5] for r in tape)
s=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_signatures.sqlite?mode=ro',uri=True)
b=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro',uri=True)
b.execute('pragma mmap_size=8000000000')
sub=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_subsample.sqlite?mode=ro',uri=True)
print([r for r in sub.execute("select name from sqlite_master where type='table'")])
try:
    mh=dict(sub.execute('select bonding_curve,is_mayhem_mode from outcome'))
    print('curves',len(mh),'mayhem',sum(1 for v in mh.values() if v))
except Exception as e:
    print('outcome err',e); mh={}
rnd=random.Random(11)
curves=rnd.sample(sorted(bycurve),20)
tot_ok=0; tot_body=0; bad=0
for c in curves:
    rows=s.execute("select signature,slot,err_json from signature_observation where bonding_curve=? and time_class='in_window'",(c,)).fetchall()
    ok=[r for r in rows if r[2]=='null']
    have=sum(1 for r in ok if b.execute('select 1 from raw_transaction where signature=?',(r[0],)).fetchone())
    miss_fail=sum(1 for r in rows if r[2]!='null' and b.execute('select 1 from raw_transaction where signature=?',(r[0],)).fetchone())
    tot_ok+=len(ok); tot_body+=have
    if have!=len(ok): bad+=1
    print(c[:10],'mayhem',mh.get(c),'sigs',len(rows),'err_null',len(ok),'bodies_of_ok',have,'bodies_of_failed',miss_fail,'decoded_pump_trades',bycurve[c])
print('TOTAL err_null',tot_ok,'bodies',tot_body,'frac %.5f'%(tot_body/max(tot_ok,1)),'curves_incomplete',bad)
