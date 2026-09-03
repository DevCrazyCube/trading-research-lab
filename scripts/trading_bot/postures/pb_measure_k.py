#!/usr/bin/env python3
"""POSTURE B.1: MEASURE the concentration factor k on-chain.
   k = (CPMM-equivalent virtual value of ACTIVE liquidity) / (deposited TVL)
Both fee income and LVR scale with the liquidity you own, so the SIGN of an LP's
net return is  apyBase - k*sigma^2/8.  k is the whole ballgame; we measure it,
we do not assume it.  Two independent RPCs must agree or the pool is dropped.
"""
import json, subprocess, sys
RPCS = ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"]
FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
T = {"USDC":"0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
     "WETH":"0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
     "USDT":"0xdAC17F958D2ee523a2206206994597C13D831ec7",
     "WBTC":"0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"}
SEL = {"getPool":"0x1698ee82","slot0":"0x3850c7bd","liquidity":"0x1a686502",
       "token0":"0x0dfe1681","token1":"0xd21220a7","fee":"0xddca3f43","decimals":"0x313ce567"}

def call(to, data, rpc):
    p = json.dumps({"jsonrpc":"2.0","id":1,"method":"eth_call",
                    "params":[{"to":to,"data":data},"latest"]})
    r = subprocess.run(["curl","-s","--max-time","25","-X","POST",rpc,
                        "-H","Content-Type: application/json","-d",p],
                       capture_output=True, text=True)
    j = json.loads(r.stdout)
    if "error" in j: raise RuntimeError(f"{rpc}: {j['error']}")
    return j["result"]

def call2(to, data):
    """require two independent RPCs to agree"""
    a = call(to, data, RPCS[0]); b = call(to, data, RPCS[1])
    if a != b: raise RuntimeError(f"RPC DISAGREE on {to} {data}: {a} vs {b}")
    return a

def enc_addr(a): return a.lower().replace("0x","").rjust(64,"0")
def enc_u24(x):  return format(x,"x").rjust(64,"0")

# free price oracle (DefiLlama coins, no key)
def prices(addrs):
    q = ",".join("ethereum:"+a for a in addrs)
    r = subprocess.run(["curl","-s","--max-time","30",
                        f"https://coins.llama.fi/prices/current/{q}"],
                       capture_output=True, text=True)
    d = json.loads(r.stdout)["coins"]
    return {k.split(":")[1].lower(): v["price"] for k,v in d.items()}

PX = prices(list(T.values()))
print("measured spot prices (DefiLlama coins API):")
for n,a in T.items(): print(f"  {n:5s} ${PX[a.lower()]:,.4f}")

PAIRS = [("USDC","WETH",500,"ETHUSD"),("USDC","WETH",3000,"ETHUSD"),
         ("WETH","USDT",3000,"ETHUSD"),
         ("WBTC","WETH",500,"BTCETH"),("WBTC","WETH",3000,"BTCETH"),
         ("WBTC","USDT",3000,"BTCUSD"),("WBTC","USDC",3000,"BTCUSD")]

llama = json.load(open("/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/selected_pools.json"))
def tvl_of(sym, meta):
    for p in llama:
        if set(p["symbol"].split("-"))==set(sym) and p["meta"]==meta: return p["tvl"], p["vol1d"]
    return None, None

dec_cache = {}
def decimals(a):
    if a not in dec_cache: dec_cache[a] = int(call2(a, SEL["decimals"]), 16)
    return dec_cache[a]

print(f"\n{'pair':16s} {'fee':>6s} {'pool':44s} {'V_virtual':>16s} {'TVL_dep':>14s} {'k':>8s}")
out = []
for a, b, fee, volkey in PAIRS:
    pool = "0x" + call2(FACTORY, SEL["getPool"]+enc_addr(T[a])+enc_addr(T[b])+enc_u24(fee))[-40:]
    if int(pool,16)==0: print(f"{a}-{b} {fee}: NO POOL"); continue
    t0 = "0x" + call2(pool, SEL["token0"])[-40:]
    t1 = "0x" + call2(pool, SEL["token1"])[-40:]
    feeq = int(call2(pool, SEL["fee"]), 16)
    assert feeq == fee, (feeq, fee)
    L  = int(call2(pool, SEL["liquidity"]), 16)
    s0 = call2(pool, SEL["slot0"])[2:]
    sqrtPX96 = int(s0[0:64], 16)
    d0, d1 = decimals(t0), decimals(t1)
    sqrtP = sqrtPX96 / 2**96
    x_raw = L / sqrtP          # token0 virtual reserve
    y_raw = L * sqrtP          # token1 virtual reserve
    v0 = x_raw/10**d0 * PX[t0.lower()]
    v1 = y_raw/10**d1 * PX[t1.lower()]
    # CPMM: the two halves must be equal -- sanity check on all the decimal math
    assert abs(v0-v1)/max(v0,v1) < 0.02, f"halves disagree {v0:.0f} vs {v1:.0f}"
    Vv = v0 + v1
    meta = f"{fee/10000:g}%".replace("0.05%","0.05%")
    meta = {500:"0.05%",3000:"0.3%"}[fee]
    tvl, vol1d = tvl_of((a,b), meta)
    k = Vv/tvl if tvl else float("nan")
    print(f"{a+'-'+b:16s} {meta:>6s} {pool} {Vv:16,.0f} {tvl:14,.0f} {k:8.2f}")
    out.append(dict(pair=f"{a}-{b}", fee=fee, meta=meta, pool=pool, Vvirt=Vv,
                    tvl=tvl, vol1d=vol1d, k=k, volkey=volkey))
json.dump(out, open("/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/k_measured.json","w"), indent=1)
print("\n(both RPCs agreed on every call; halves-equal check passed on every pool)")
