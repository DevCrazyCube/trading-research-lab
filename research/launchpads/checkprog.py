import sys,json,urllib.request,base64
url=[l.split('=',1)[1].strip().strip("'").strip('"') for l in open('/home/anont/meme/.env') if l.startswith('HELIUS_RPC_URL')][0]
def rpc(method,params):
    req=urllib.request.Request(url,data=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode(),headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(req,timeout=40).read())
cands=json.load(open(sys.argv[1]))
for name,pk in cands:
    try:
        r=rpc("getAccountInfo",[pk,{"encoding":"base64"}])
        v=r.get("result",{}).get("value")
        if v is None:
            print(f"{name:28s} {pk:46s} NOT_FOUND"); continue
        ex=v.get("executable"); ow=v.get("owner"); ln=len(base64.b64decode(v['data'][0])) if v.get('data') else 0
        # recent activity
        s=rpc("getSignaturesForAddress",[pk,{"limit":1}]).get("result",[])
        bt=s[0].get("blockTime") if s else None
        import datetime
        ts=datetime.datetime.utcfromtimestamp(bt).isoformat()+"Z" if bt else "none"
        print(f"{name:28s} {pk:46s} exec={ex} owner={ow[:12]}.. len={ln} last_sig={ts}")
    except Exception as e:
        print(f"{name:28s} {pk:46s} ERR {e}")
