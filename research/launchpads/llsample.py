import sys,json,base64,urllib.request,collections
sys.path.insert(0,'.')
from sol import b58e
url=[l.split('=',1)[1].strip().strip("'").strip('"') for l in open('/home/anont/meme/.env') if l.startswith('HELIUS_RPC_URL')][0]
def rpc(m,p):
    r=urllib.request.Request(url,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(r,timeout=300).read())
PROG='LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj'
disc=base64.b64encode(bytes([247,237,227,245,215,195,222,70])).decode()
cfg=sys.argv[1]
r=rpc("getProgramAccounts",[PROG,{"encoding":"base64","dataSlice":{"offset":0,"length":210},
  "filters":[{"memcmp":{"offset":0,"bytes":disc,"encoding":"base64"}},{"memcmp":{"offset":173,"bytes":cfg,"encoding":"base58"}},
             {"memcmp":{"offset":17,"bytes":"Ag==","encoding":"base64"}}]}])
res=r['result']; print('graduated pools',len(res))
def u(b,o): return int.from_bytes(b[o:o+8],'little')
c=collections.Counter()
gc=collections.Counter()
for x in res[:5000]:
    b=base64.b64decode(x['account']['data'][0])
    c[(u(b,21),u(b,29),u(b,37),u(b,45),u(b,69))]+=1
    gc[b58e(b[141:173])]+=1
for k,n in c.most_common(6):
    supply,tbs,vb,vq,tq=k
    X=((vq+tq)/vq)**2
    print(f"  n={n} supply={supply} base_sell={tbs} vbase={vb} vquote={vq/1e9:.6f} SOL raise={tq/1e9:.3f} SOL -> X={X:.4f}x")
print('global_configs',gc.most_common(5))
