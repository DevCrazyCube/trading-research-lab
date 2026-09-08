import os, sys, sqlite3, json
S = "/home/anont/meme/research/scratch_combo2"
out = []
out.append("python " + sys.version)
try:
    out.append("midcap: " + repr(sorted(os.listdir("/home/anont/meme/research/midcap"))))
except Exception as e:
    out.append("midcap ERR " + repr(e))
try:
    c = sqlite3.connect("file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro", uri=True)
    out.append("tables: " + repr(c.execute("select name,sql from sqlite_master").fetchall()))
    out.append("counts: " + repr(c.execute("select count(*), sum(n_bars) from ohlcv").fetchone()))
    r = c.execute("select mint,pool,n_bars,first_ts,last_ts,status from ohlcv limit 3").fetchall()
    out.append("sample: " + repr(r))
    b = c.execute("select bars_json from ohlcv where n_bars>5 limit 1").fetchone()[0]
    bb = json.loads(b)
    out.append("bars head: " + repr(bb[:3]))
except Exception as e:
    out.append("ohlcv ERR " + repr(e))
open(os.path.join(S, "probe_out.txt"), "w").write("\n".join(out))
