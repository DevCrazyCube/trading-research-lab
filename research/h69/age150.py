import json,urllib.request,time,datetime
RPC='https://api.mainnet-beta.solana.com'
def rpc(method,params,tries=6):
    body=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
    for t in range(tries):
        try:
            r=urllib.request.Request(RPC,data=body,headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0'})
            d=json.load(urllib.request.urlopen(r,timeout=30))
            if 'error' in d: time.sleep(1.5*(t+1)); continue
            return d['result']
        except Exception: time.sleep(1.5*(t+1))
    return None
S=json.load(open('h69_sample.json'))['sample']
out={}
for i,x in enumerate(S):
    r=rpc('getSignaturesForAddress',[x['curve'],{'limit':1}])
    out[x['mint']]=r[0]['blockTime'] if r else None
    if i%25==0: print('..',i,flush=True)
    time.sleep(0.35)
json.dump(out,open('last_sig.json','w'))
NOW=int(time.time())
ages=sorted((NOW-v)/86400 for v in out.values() if v)
print('resolved',len(ages),'of',len(S))
def q(p): return ages[int((len(ages)-1)*p)]
print('LAST-ACTIVITY age days (UPPER bound is migration<=this): p10=%.0f p25=%.0f MED=%.0f p75=%.0f p90=%.0f max=%.0f'%(q(.1),q(.25),q(.5),q(.75),q(.9),ages[-1]))
for d in (14,30,60,90,180):
    print('  share with last activity within %3dd: %.1f%% (n=%d)'%(d,100*sum(1 for a in ages if a<=d)/len(ages),sum(1 for a in ages if a<=d)))
