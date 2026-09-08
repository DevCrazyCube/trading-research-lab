import sqlite3,pickle
D='/home/anont/meme/research/'
c=sqlite3.connect('file:'+D+'b11a/b11a_bodies.sqlite?mode=ro',uri=True)
for t in ('transaction_coordinate','raw_transaction'):
    print(t, c.execute("select sql from sqlite_master where name=?",(t,)).fetchone()[0][:600]);print()
print('ro count', c.execute("select count(*) from reserve_observation").fetchone())
print('tc count', c.execute("select count(*) from transaction_coordinate").fetchone())
db=pickle.load(open('/home/anont/meme/.scr/db.pkl','rb'))
DB=db['DB']
c2=sqlite3.connect('file:'+D+'b11a/window_labels.sqlite?mode=ro',uri=True)
bc={}
for m,b in c2.execute("select mint,bonding_curve from window_label"):
    bc[m]=b
hits=sum(1 for m in DB if m in bc)
print('bc map',hits,'/',len(DB))
# how many reserve obs for our mints
ours=[bc[m] for m in DB if m in bc]
q=','.join('?'*len(ours))
print('ro rows for our mints', c.execute(f"select count(*),count(distinct bonding_curve) from reserve_observation where bonding_curve in ({q})",ours).fetchone())
print('instr sample', c.execute("select slot,idl_name,discriminator from instruction limit 5").fetchall())
print('idl names', c.execute("select idl_name,count(*) from instruction group by 1 order by 2 desc limit 15").fetchall())
