import json,urllib.request,time,datetime,sys
RPC='https://api.mainnet-beta.solana.com'
def rpc(method,params,tries=8):
    body=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
    for t in range(tries):
        try:
            r=urllib.request.Request(RPC,data=body,headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0'})
            d=json.load(urllib.request.urlopen(r,timeout=30))
            if 'error' in d: time.sleep(2*(t+1)); continue
            return d['result']
        except Exception as e:
            time.sleep(2*(t+1))
    return None
S=json.load(open('h69_sample.json'))['sample']
ds=json.load(open('ds_pairs.json'))
# 4 mints WITH a dexscreener pair (known pairCreatedAt) + 6 without
have=[x for x in S if x['mint'] in ds][:4]
dont=[x for x in S if x['mint'] not in ds][:6]
for x in have+dont:
    r=rpc('getSignaturesForAddress',[x['curve'],{'limit':1}])
    bt=r[0]['blockTime'] if r else None
    ref=None
    if x['mint'] in ds:
        p=max(ds[x['mint']],key=lambda p:(p.get('liquidity') or {}).get('usd') or 0)
        ref=p.get('pairCreatedAt')
    print('%s last_curve_sig=%s  ds_pairCreatedAt=%s  nsig=%s'%(
        x['mint'][:12],
        datetime.datetime.fromtimestamp(bt,datetime.UTC).strftime('%Y-%m-%d %H:%M') if bt else None,
        datetime.datetime.fromtimestamp(ref/1000,datetime.UTC).strftime('%Y-%m-%d %H:%M') if ref else '-',
        len(r) if r else 0), flush=True)
    time.sleep(0.4)
