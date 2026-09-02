import sys,json,base64,urllib.request
sys.path.insert(0,'.')
from sol import b58e
url=[l.split('=',1)[1].strip().strip("'").strip('"') for l in open('/home/anont/meme/.env') if l.startswith('HELIUS_RPC_URL')][0]
def rpc(m,p):
    r=urllib.request.Request(url,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(r,timeout=90).read())
def u(b,o,n): return int.from_bytes(b[o:o+n],'little')
Q=2**64
for label,cfg in json.load(open(sys.argv[1])):
    v=rpc("getAccountInfo",[cfg,{"encoding":"base64"}]).get("result",{}).get("value")
    b=base64.b64decode(v['data'][0])
    ssp=u(b,392,16); msp=u(b,280,16)
    pts=[]
    for i in range(20):
        o=408+i*32; sp=u(b,o,16); liq=u(b,o+16,16)
        if sp==0 and liq==0: continue
        pts.append((sp,liq))
    base_tot=0.0; quote_tot=0.0; prev=ssp
    for sp,liq in pts:
        a=min(prev,msp); c=min(sp,msp)
        if c>a:
            L=liq/Q
            base_tot += L*(1/(a/Q)-1/(c/Q))
            quote_tot += L*((c/Q)-(a/Q))
        prev=sp
    td=b[235]
    print(f"{label} pts={len(pts)}")
    print(f"   integral base={base_tot:.1f} raw  vs swap_base_amount={u(b,256,8)}   ratio={base_tot/max(1,u(b,256,8)):.4f}")
    print(f"   integral quote={quote_tot:.1f} raw vs migration_quote_threshold={u(b,264,8)}  ratio={quote_tot/max(1,u(b,264,8)):.4f}")
    print(f"   X=(msp/ssp)^2={(msp/ssp)**2:.4f}  start_price_raw={(ssp/Q)**2:.6g}")
