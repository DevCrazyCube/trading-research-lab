import sys,json,base64,urllib.request
url=[l.split('=',1)[1].strip().strip("'").strip('"') for l in open('/home/anont/meme/.env') if l.startswith('HELIUS_RPC_URL')][0]
def rpc(m,p):
    r=urllib.request.Request(url,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(r,timeout=120).read())
prog,idlf,acct,out=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
sl=json.loads(sys.argv[5]) if len(sys.argv)>5 else None
idl=json.load(open(idlf))
d=[a for a in idl['accounts'] if a['name']==acct][0]['discriminator']
import base64 as b64
memcmp={"offset":0,"bytes":b64.b64encode(bytes(d)).decode()}
cfg={"encoding":"base64","filters":[{"memcmp":{"offset":0,"bytes":memcmp['bytes'],"encoding":"base64"}}]}
if sl: cfg["dataSlice"]={"offset":sl[0],"length":sl[1]}
r=rpc("getProgramAccounts",[prog,cfg])
if 'error' in r: print('ERR',json.dumps(r['error'])[:400]); sys.exit(1)
res=r['result']
print(acct,'count',len(res))
json.dump([(x['pubkey'],base64.b64decode(x['account']['data'][0]).hex()) for x in res],open(out,'w'))
