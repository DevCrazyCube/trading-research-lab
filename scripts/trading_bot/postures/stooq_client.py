"""Stooq free daily CSV client with SHA-256 proof-of-work challenge solver.

Stooq gates bulk CSV behind a JS PoW: the page embeds a challenge token `c` and a
difficulty `d` (leading zero hex nibbles). The browser finds n such that
sha256(c+str(n)) starts with '0'*d, POSTs c & n to /__verify, receives a cookie,
then re-requests. This reimplements the same public flow in Python.
Read-only, keyless, free.
"""
import hashlib
import http.cookiejar
import re
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0 Safari/537.36")
_JAR = http.cookiejar.CookieJar()
_OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_JAR))
_OP.addheaders = [("User-Agent", UA), ("Accept", "text/csv,text/html,*/*")]

_CHAL = re.compile(r'const c="([A-Za-z0-9_\-]+)",d=(\d+)')


def _solve(c, d):
    tgt = "0" * d
    n = 0
    while True:
        if hashlib.sha256((c + str(n)).encode()).hexdigest().startswith(tgt):
            return n
        n += 1


def _verify(body, base):
    m = _CHAL.search(body)
    if not m:
        return False
    c, d = m.group(1), int(m.group(2))
    n = _solve(c, d)
    data = urllib.parse.urlencode({"c": c, "n": n}).encode()
    req = urllib.request.Request(
        urllib.parse.urljoin(base, "/__verify"), data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": UA},
    )
    with _OP.open(req, timeout=30) as r:
        return r.status == 200


def fetch(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with _OP.open(req, timeout=45) as r:
                body = r.read().decode("utf-8", "replace")
        except Exception:
            time.sleep(2 + 2 * i)
            continue
        head = body[:200]
        if head.lstrip().lower().startswith("date,"):
            return body
        if "crypto.subtle.digest" in body:
            try:
                _verify(body, url)
            except Exception:
                time.sleep(2)
            continue
        time.sleep(3 + 3 * i)
    return ""


def daily(sym):
    return fetch("https://stooq.com/q/d/l/?s=%s&i=d" % urllib.parse.quote(sym))
