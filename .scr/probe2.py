import sqlite3,pickle,hashlib,collections,statistics as st
D='/home/anont/meme/research/'
db=pickle.load(open('/home/anont/meme/.scr/db.pkl','rb'))
DB=db['DB']
mf=list(zip(*[v['MF'] for v in DB.values()]))
for n,col in zip(db['MFEATN'],mf):
    s=sorted(col)
    print(n, 'min',round(s[0],2),'p25',round(s[len(s)//4],2),'med',round(s[len(s)//2],2),'p75',round(s[3*len(s)//4],2),'max',round(s[-1],2))
c=sqlite3.connect('file:'+D+'b11a/b11a_bodies.sqlite?mode=ro',uri=True)
print([r[0] for r in c.execute("select name from sqlite_master where type='table'")])
for t in ('instruction','reserve_observation'):
    try:
        print(t, c.execute("select sql from sqlite_master where name=?",(t,)).fetchone()[0][:900])
    except Exception as e: print(t,e)
