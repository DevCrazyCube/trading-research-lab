import sys,json,base64,urllib.request
sys.path.insert(0,'.')
from sol import b58e
url=[l.split('=',1)[1].strip().strip("'").strip('"') for l in open('/home/anont/meme/.env') if l.startswith('HELIUS_RPC_URL')][0]
def rpc(m,p):
    r=urllib.request.Request(url,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(r,timeout=300).read())
PROG='dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN'
idl=json.load(open('idl_meteora DBC.json'))
VPD=base64.b64encode(bytes([x for a in idl['accounts'] if a['name']=='VirtualPool' for x in a['discriminator']])).decode()
def u(b,o,n): return int.from_bytes(b[o:o+n],'little')
for label,cfg in json.load(open(sys.argv[1])):
    v=rpc("getAccountInfo",[cfg,{"encoding":"base64"}]).get("result",{}).get("value")
    if not v: print(label,cfg,'MISSING'); continue
    b=base64.b64decode(v['data'][0])
    ssp=u(b,392,16); msp=u(b,280,16); X=(msp/ssp)**2
    print(f"--- {label} cfg={cfg}")
    print(f"    quote={b58e(b[8:40])} token_decimal={b[235]} migration_option={b[233]} collect_fee_mode={b[232]}")
    print(f"    cliff_fee_num={u(b,104,8)} (={u(b,104,8)/1e9*100:.4f}%/side) periods={u(b,128,2)} base_fee_mode={b[130]} period_freq={u(b,112,8)} reduction={u(b,120,8)}")
    print(f"    creator_trading_fee_pct={b[245]} migration_fee_pct={b[247]} pool_creation_fee={u(b,368,8)}")
    print(f"    swap_base_amount={u(b,256,8)} migration_quote_threshold={u(b,264,8)} ({u(b,264,8)/1e9:.3f} SOL) migration_base_threshold={u(b,272,8)}")
    print(f"    sqrt_start={ssp} sqrt_migration={msp}  ==> X = {X:.4f}x  (+{(X-1)*100:.1f}%)")
    # count pools
    r=rpc("getProgramAccounts",[PROG,{"encoding":"base64","dataSlice":{"offset":305,"length":1},
        "filters":[{"memcmp":{"offset":0,"bytes":VPD,"encoding":"base64"}},{"memcmp":{"offset":72,"bytes":cfg,"encoding":"base58"}}]}])
    if 'error' in r: print('    pools: ERR',json.dumps(r['error'])[:150]); continue
    res=r['result']; mig=sum(1 for x in res if base64.b64decode(x['account']['data'][0])[0]==1)
    print(f"    pools={len(res)} migrated={mig} rate={100*mig/max(1,len(res)):.3f}%")
