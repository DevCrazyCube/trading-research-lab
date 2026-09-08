import sys, os, sqlite3, json
OUT = '/home/anont/meme/.scr2/probe.out'
out = []
def p(*a): out.append(" ".join(str(x) for x in a))
p("python", sys.version.split()[0])
try:
    import numpy; p("numpy", numpy.__version__)
except Exception as e: p("numpy missing", e)

paths = ['/home/anont/meme/research/midcap/grad_ohlcv.sqlite',
         '/home/anont/meme/research/b11a/window_labels.sqlite',
         '/home/anont/meme/research/b11a/b11a_bodies.sqlite']
for path in paths:
    p("==", path, os.path.exists(path), os.path.getsize(path) if os.path.exists(path) else -1)
    try:
        c = sqlite3.connect('file:'+path+'?mode=ro', uri=True)
        for name, sql in c.execute("select name,sql from sqlite_master where type='table'"):
            p("TABLE", name)
            p("   ", (sql or "")[:600].replace("\n"," "))
            try:
                n = c.execute("select count(*) from [%s]" % name).fetchone()[0]
                p("    rows=", n)
            except Exception as e:
                p("    cnt err", e)
        c.close()
    except Exception as e:
        p("ERR", repr(e))

# sample ohlcv row
c = sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
r = c.execute("select mint,pool,n_bars,first_ts,last_ts,status,substr(bars_json,1,300) from ohlcv limit 3").fetchall()
for x in r: p("SAMPLE", x)
p("status counts:", c.execute("select status,count(*),sum(n_bars) from ohlcv group by status").fetchall())
c.close()

c = sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro', uri=True)
p("wl sample", c.execute("select * from window_label limit 3").fetchall())
p("wl count", c.execute("select count(*), sum(complete) from window_label").fetchone())
p("wl block_time range", c.execute("select min(block_time),max(block_time),min(create_slot),max(create_slot) from window_label").fetchone())
p("distinct creators", c.execute("select count(distinct creator) from window_label").fetchone())
c.close()
open(OUT,'w').write("\n".join(out))
