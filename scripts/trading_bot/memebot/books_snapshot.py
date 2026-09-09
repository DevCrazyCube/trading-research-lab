"""Snapshot the SPL holdings of a wallet roster (free Solana RPC) and price them (free DexScreener).
Prospective 'leaderboard books' test: run daily; the analysis compares forward returns of tokens held by
7d-leaderboard winners vs random active wallets, mint-equal, dropouts charged. Read-only, no key, no orders."""
import json,time,urllib.request,sys,os,datetime
RPC="https://api.mainnet-beta.solana.com"; ROSTER="research/midcap/books_roster_20260909.json"; OUT="research/midcap/books_forward"
def rpc(m,p):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for i in range(6):
        try:
            r=urllib.request.Request(RPC,data=b,headers={"content-type":"application/json","User-Agent":"Mozilla/5.0"})
            j=json.loads(urllib.request.urlopen(r,timeout=40).read())
            if "error" in j: raise RuntimeError(j["error"])
            return j["result"]
        except Exception as e:
            time.sleep(2*(i+1))
    return None
def holdings(w):
    r=rpc("getTokenAccountsByOwner",[w,{"programId":"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},{"encoding":"jsonParsed"}])
    if r is None: return None
    out=[]
    for x in r.get("value",[]):
        info=x["account"]["data"]["parsed"]["info"]; amt=float(info["tokenAmount"]["uiAmount"] or 0)
        if amt>0: out.append((info["mint"],amt))
    return out
def prices(mints):
    px={}
    for i in range(0,len(mints),30):
        chunk=mints[i:i+30]
        try:
            r=urllib.request.Request("https://api.dexscreener.com/tokens/v1/solana/"+",".join(chunk),headers={"User-Agent":"Mozilla/5.0"})
            for p in json.loads(urllib.request.urlopen(r,timeout=30).read()) or []:
                a=p["baseToken"]["address"]; 
                if a not in px or float(p.get("liquidity",{}).get("usd") or 0)>px[a]["liq"]:
                    px[a]={"px":float(p.get("priceUsd") or 0),"liq":float(p.get("liquidity",{}).get("usd") or 0),"mcap":float(p.get("marketCap") or 0),"created":p.get("pairCreatedAt")}
        except Exception: pass
        time.sleep(0.4)
    return px
def main():
    os.makedirs(OUT,exist_ok=True); ro=json.load(open(ROSTER)); snap={"ts":time.time(),"wallets":{}}
    allm=set()
    for grp in ("winners","controls"):
        for w in ro[grp]:
            h=holdings(w["sol"]); snap["wallets"][w["sol"]]={"group":grp,"rank":w["rank"],"holdings":h}
            if h: allm.update(m for m,_ in h)
            time.sleep(0.45)
    snap["prices"]=prices(sorted(allm))
    fn=f"{OUT}/snapshot_{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M')}.json"; json.dump(snap,open(fn,"w"))
    nw=sum(1 for v in snap["wallets"].values() if v["holdings"] is not None); print("wrote",fn,"wallets read",nw,"mints",len(allm),"priced",len(snap["prices"]))
if __name__=="__main__": main()
