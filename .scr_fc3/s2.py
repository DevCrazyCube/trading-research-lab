import sqlite3, os, json, hashlib, collections

def h(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3

p = '/home/anont/meme/research/b11a/b11a_bodies.sqlite'
print('bodies size', os.path.getsize(p))
c = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
for (n, s) in c.execute("select name,sql from sqlite_master where type in ('table','index')"):
    print(' OBJ', n)
    print('  ', s)
c.close()
