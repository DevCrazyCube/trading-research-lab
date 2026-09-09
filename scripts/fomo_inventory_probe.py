"""Read-only, bounded historical ANON inventory check for the owner's saved profile.

No new FOMO calls. This audits opening token quantity, NOT cost basis or PnL.
Public historical RPC alone is not independent consensus or account-identity proof.
"""
import argparse
from datetime import datetime
from decimal import Decimal,localcontext
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from Crypto.Hash import keccak
from scripts.fomo_chain_probe import Evidence,RPC,address,decode_http
from scripts.fomo_probe import get_key

TOKEN='0x293eff1b996c56f6e0f6afdc9e955301eea86dc7'


def bracket(fetch,head,target):
    """Last block strictly earlier than target second; preserve timestamp ambiguity."""
    lo=fetch(0);hi=fetch(head)
    if not int(lo['timestamp'],16)<target<=int(hi['timestamp'],16):
        raise ValueError('target outside verified endpoint times')
    calls=2
    while int(hi['number'],16)-int(lo['number'],16)>1:
        if calls>=34:raise ValueError('binary-search bound exceeded')
        n=(int(lo['number'],16)+int(hi['number'],16))//2
        middle=fetch(n);calls+=1
        stamp=int(middle['timestamp'],16)
        if int(middle['number'],16)!=n or not int(lo['timestamp'],16)<=stamp<=int(hi['timestamp'],16):
            raise ValueError('nonmonotonic/mismatched block evidence')
        if stamp<target:lo=middle
        else:hi=middle
    return lo,hi


def selector(text):
    return keccak.new(digest_bits=256,data=text.encode()).hexdigest()[:8]


def run(profile,swaps,paired,out):
    user=json.loads(profile.read_bytes());fills=json.loads(swaps.read_bytes(),parse_float=Decimal)
    if (user.get('handle') or '').lstrip('@').lower()!='kankerhond':
        raise ValueError('profile is not the requested owner')
    wallet=address(user['wallets']['evm'])
    timestamp=min(r['at'] for r in fills['swaps'])
    target=int(datetime.fromisoformat(timestamp.replace('Z','+00:00')).timestamp())
    db=sqlite3.connect((paired/'raw.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    try:
        for meta,raw in db.execute("SELECT meta,payload FROM raw WHERE kind='rpc' ORDER BY sequence DESC"):
            m=json.loads(meta)
            if m['request']['method']=='eth_getBlockByNumber':
                reply=json.loads(decode_http(raw,m.get('content_encoding','identity')))
                if isinstance(reply.get('result'),dict):head=int(reply['result']['number'],16);break
        else:raise ValueError('no recorded head')
    finally:db.close()
    e=Evidence(out,get_key());calls=0;last=0
    e.save('manifest',{'schema':'owner-inventory-check-v1','profile_sha256':hashlib.sha256(profile.read_bytes()).hexdigest(),
        'swaps_sha256':hashlib.sha256(swaps.read_bytes()).hexdigest(),'source_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'wallet':wallet,'token':TOKEN,'chain_id':4663,'api_cutoff_timestamp':timestamp,
        'target_second':target,'max_rpc_calls':42,'minimum_request_spacing_seconds':5,
        'scope':'historical token quantity only; no cost basis, no PnL, no strategy validation'})
    def rpc(method,params):
        nonlocal calls,last
        if method not in {'eth_chainId','eth_getBlockByNumber','eth_call'} or calls>=42:
            raise ValueError('read-only RPC budget/method refused')
        time.sleep(max(0,5-(time.monotonic()-last)));last=time.monotonic();calls+=1
        reply,_=e.request(RPC,'POST',{'jsonrpc':'2.0','id':calls,'method':method,'params':params},kind='rpc')
        if reply.get('id')!=calls or reply.get('error') or reply.get('result') is None:
            raise ValueError('RPC refused')
        return reply['result']
    def fetch(n):return rpc('eth_getBlockByNumber',[hex(n),False])
    try:
        if int(rpc('eth_chainId',[]),16)!=4663:raise ValueError('wrong chain')
        lo,hi=bracket(fetch,head,target)
        def uint_call(data):
            value=rpc('eth_call',[{'to':TOKEN,'data':'0x'+data},lo['number']])
            if not isinstance(value,str) or len(value)!=66:raise ValueError('ABI result not one uint word')
            return int(value,16)
        decimals=uint_call(selector('decimals()'))
        if not 0<=decimals<=255:raise ValueError('invalid decimals')
        balance=uint_call(selector('balanceOf(address)')+'0'*24+wallet[2:])
        check=fetch(int(lo['number'],16))
        if check['hash']!=lo['hash']:raise ValueError('historical block changed')
        with localcontext() as context:
            context.prec=1000
            quantity=format(Decimal(balance).scaleb(-decimals),'f')
        result={'status':'HISTORICAL_INVENTORY_ONLY_NO_TRADE','balance_raw':str(balance),'decimals':decimals,
            'balance_tokens':quantity,'before_block':int(lo['number'],16),'before_block_timestamp':int(lo['timestamp'],16),
            'next_block':int(hi['number'],16),'next_block_timestamp':int(hi['timestamp'],16),
            'api_cutoff':timestamp,'rpc_calls':calls,'opening_cost_basis':'UNRESOLVED','pnl':'NOT_COMPUTED',
            'caveat':'API fill timestamps are not independently bound to chain execution; this is a historical balance checkpoint'}
        e.save('result',result)
        with (out/'summary.json').open('x') as stream:json.dump(result,stream,sort_keys=True)
        return result
    except Exception as error:
        e.save('failure',{'error_type':type(error).__name__,'rpc_calls':calls});raise
    finally:e.save('closed',{'status':'NO_TRADE'});e.db.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['profile','swaps','paired','out']:p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    try:print(json.dumps(run(args.profile,args.swaps,args.paired,args.out),sort_keys=True),flush=True)
    except Exception as error:
        print(json.dumps({'status':'REFUSED_NO_TRADE','error_type':type(error).__name__}),flush=True)
        raise SystemExit(2)
