import json,urllib.request,time,datetime,sys
def get(u,tries=10):
    for t in range(tries):
        try:
            r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
            return json.load(urllib.request.urlopen(r,timeout=45))
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(20); continue
            if e.code==404: return {'_404':True}
            return {'_http':e.code}
        except Exception as ex: time.sleep(8)
    return {'_fail':True}
S=json.load(open('h69_sample.json'))['sample']
ds=json.load(open('ds_pairs.json'))
un=[x for x in S if x['mint'] not in ds][:6]
hv=[x for x in S if x['mint'] in ds][:2]
print('--- mints DexScreener has NO pair for ---',flush=True)
for x in un+hv:
    tag='NO-DS' if x['mint'] not in ds else 'HAS-DS'
    d=get('https://api.geckoterminal.com/api/v2/networks/solana/tokens/%s/pools'%x['mint'])
    if '_404' in d or '_fail' in d or '_http' in d:
        print('%-7s %s -> %s'%(tag,x['mint'][:14],list(d)),flush=True); time.sleep(4); continue
    ps=d.get('data',[])
    print('%-7s %s gt_pools=%d'%(tag,x['mint'][:14],len(ps)),flush=True)
    for p in ps[:2]:
        a=p['attributes']
        print('        pool=%s created=%s resUSD=%s'%(p['id'].split('_')[-1][:12],a.get('pool_created_at'),a.get('reserve_in_usd')),flush=True)
    time.sleep(4)
