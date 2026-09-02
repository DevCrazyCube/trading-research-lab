import sys,json,base64,urllib.request,hashlib,collections
sys.path.insert(0,'.')
from sol import b58e,b58d
url=[l.split('=',1)[1].strip().strip("'").strip('"') for l in open('/home/anont/meme/.env') if l.startswith('HELIUS_RPC_URL')][0]
def rpc(m,p):
    r=urllib.request.Request(url,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(r,timeout=90).read())
PROG='LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj'
idl=json.load(open('idl_raydium launchlab.json'))
ev={bytes(e['discriminator']).hex():e['name'] for e in idl['events']}
sigs=[s['signature'] for s in rpc("getSignaturesForAddress",[PROG,{"limit":60}]).get("result",[])]
def u(b,o): return int.from_bytes(b[o:o+8],'little')
seen=0
for s in sigs:
    tx=rpc("getTransaction",[s,{"encoding":"json","maxSupportedTransactionVersion":0}]).get("result")
    if not tx: continue
    for l in tx['meta'].get('logMessages',[]):
        if not l.startswith('Program data: '): continue
        raw=base64.b64decode(l[14:])
        nm=ev.get(raw[:8].hex())
        if nm!='TradeEvent': continue
        b=raw[8:]
        pool=b58e(b[0:32]); o=32
        f={}
        for name in ['total_base_sell','virtual_base','virtual_quote','real_base_before','real_quote_before','real_base_after','real_quote_after','amount_in','amount_out','protocol_fee','platform_fee','creator_fee','share_fee']:
            f[name]=u(b,o); o+=8
        td=b[o]; o+=1; st=b[o]; o+=1; ei=b[o]
        tot=f['protocol_fee']+f['platform_fee']+f['creator_fee']+f['share_fee']
        base=f['amount_in'] if td==0 else f['amount_out']
        quote_gross = f['amount_in'] if td==0 else f['amount_out']
        print(f"{s[:12]} dir={'buy' if td==0 else 'sell'} in={f['amount_in']} out={f['amount_out']} prot={f['protocol_fee']} plat={f['platform_fee']} creat={f['creator_fee']} share={f['share_fee']} total_fee/quote={tot/max(1,quote_gross)*100:.4f}% pool={pool}")
        seen+=1
    if seen>=8: break
