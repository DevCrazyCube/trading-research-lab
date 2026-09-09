"""Bounded public Pons contract/ABI discovery. No orders, price analysis or keys."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time

import requests
from Crypto.Hash import keccak

ROOT=Path('research/midcap/rh_curve_private')
RPC='https://rpc.mainnet.chain.robinhood.com'
EXPLORER='https://robinhoodchain.blockscout.com/api/v2/smart-contracts/'
GITHUB='https://api.github.com/repos/ponsdotdev/ponsfamily/commits/main'
RAW='https://raw.githubusercontent.com/ponsdotdev/ponsfamily/'
OLD='0x7e1eabd52ae29598e6483f72dcf1a70b14284db8'
ADDRESS=re.compile('0x[0-9a-fA-F]{40}')


def digest(raw):return hashlib.sha256(raw).hexdigest()
def selector(sig):return '0x'+keccak.new(digest_bits=256,data=sig.encode()).hexdigest()[:8]
def topic(sig):return '0x'+keccak.new(digest_bits=256,data=sig.encode()).hexdigest()
def signature(abi):return abi['name']+'('+','.join(x['type'] for x in abi['inputs'])+')'


def source_event(source,name):
    """Static event shape from pinned source, explicitly NOT deployment attestation."""
    source=re.sub(r'/\*.*?\*/|//[^\n]*','',source,flags=re.S)
    match=re.search(r'event\s+'+re.escape(name)+r'\s*\((.*?)\)\s*;',source,re.S)
    if not match:raise ValueError('source event missing: '+name)
    fields=[]
    for part in match.group(1).split(','):
        words=part.split()
        if len(words) not in (2,3) or not re.fullmatch(r'address|u?int(?:[0-9]+)?|bytes32|bool',words[0]):
            raise ValueError('unsupported source event type')
        if len(words)==3 and words[1]!='indexed':raise ValueError('unsupported source event field')
        fields.append({'name':words[-1],'type':words[0],'indexed':len(words)==3})
    return {'name':name,'type':'event','inputs':fields,'anonymous':False}


def saved_source(folder,num):
    m=json.loads((folder/f'{num:03d}.json').read_text());raw=(folder/f'{num:03d}.body').read_bytes()
    if m.get('http_status')!=200 or digest(raw)!=m.get('sha256'):raise ValueError('saved source integrity')
    return raw.decode()


def inspect_saved_launches(source,out):
    """Inspect two predetermined curve identities from saved factory launches."""
    if source.resolve().parent!=ROOT.resolve():raise ValueError('private source required')
    prior=json.loads((source/'result.json').read_text());events=prior.get('launches',[])
    if not events:raise ValueError('no saved launches')
    c=Capture(out,budget=32);r={'status':'DEVELOPMENT_CURVE_IDENTITY_ONLY_NO_TRADE','curves':[],
        'source_capture':str(source),'source_result_sha256':digest((source/'result.json').read_bytes()),
        'economic_result':'NOT_COMPUTED'}
    try:
        if int(c.rpc('eth_chainId',[]),16)!=4663:raise ValueError('wrong chain')
        head=c.rpc('eth_blockNumber',[]);r['head']=int(head,16)
        events=sorted(events,key=lambda x:tuple(int(x['raw'][k],16) for k in ['blockNumber','transactionIndex','logIndex']))
        e=next(x for x in prior['abi_shapes'] if x['name']=='TokenLaunched')
        names=[x['name'] for x in e['inputs'] if x['indexed']]
        for event in [events[0],events[-1]]:
            g=event['raw'];addr='0x'+g['topics'][names.index('curve')+1][-40:]
            token='0x'+g['topics'][names.index('token')+1][-40:]
            ob={'address':addr,'token':token,'factory':event['factory'],'getters':{},'runtime_attested':False};r['curves'].append(ob)
            ob['code_sha256']=digest(bytes.fromhex(c.rpc('eth_getCode',[addr,head])[2:]))
            for name in ['factory','token','pairToken','feeBps','creatorTaxBps']:
                ob['getters'][name]=c.rpc('eth_call',[{'to':addr,'data':selector(name+'()')},head])
            ob['factory_binding_matches']=ob['getters']['factory'].lower()=='0x'+event['factory'][2:].rjust(64,'0')
            ob['token_binding_matches']=ob['getters']['token'].lower()=='0x'+token[2:].rjust(64,'0')
            logs=c.rpc('eth_getLogs',[{'address':addr,'fromBlock':g['blockNumber'],'toBlock':head}])
            ob['raw_log_count']=len(logs)
            ob['topics']=sorted({x['topics'][0] for x in logs if x.get('topics')})
    except Exception as e:
        r['failure_type']=type(e).__name__
        if isinstance(e,ValueError):r['refusal']=str(e)
    r['requests']=c.n;r['ended_ns']=time.time_ns();(out/'result.json').write_text(json.dumps(r,sort_keys=True))
    return r


def rpc_discovery(source,out):
    """Public RPC continuation. Explorer refusal stays unresolved; never bypassed."""
    if source.resolve().parent!=ROOT.resolve():raise ValueError('private source required')
    c=Capture(out,budget=40);r={'status':'SOURCE_SHAPE_ONLY_NOT_BYTECODE_ATTESTED_NO_TRADE',
        'economic_result':'NOT_COMPUTED','explorer_verification':'UNAVAILABLE_HTTP403',
        'factories':[],'curves':[],'source_capture':str(source)}
    try:
        prior=json.loads((source/'result.json').read_text());factory=prior['current_readme_factory']
        r['github_commit']=prior['github_commit'];facsrc=saved_source(source,3);curvesrc=saved_source(source,4)
        launch=source_event(facsrc,'TokenLaunched');buy=source_event(curvesrc,'CurveBuy');sell=source_event(curvesrc,'CurveSell')
        r['abi_shapes']=[launch,buy,sell,source_event(curvesrc,'CurveCompleted')]
        if int(c.rpc('eth_chainId',[]),16)!=4663:raise ValueError('wrong chain')
        head=c.rpc('eth_blockNumber',[]);r['head']=int(head,16)
        for addr in dict.fromkeys([factory,OLD]):
            code=c.rpc('eth_getCode',[addr,head]);ob={'address':addr,'code_bytes':len(code[2:])//2,
                'code_sha256':digest(bytes.fromhex(code[2:])),'getters':{}};r['factories'].append(ob)
            for name in ['launchEnabled','snipeTaxStartBps','snipeTaxSeconds','memeHook','poolManager']:
                # Declared public getters in retained factory source; ABI values remain raw.
                if not re.search(r'public(?:\s+immutable)?\s+'+name+r'\b',facsrc):
                    ob['getters'][name]='SOURCE_ABSENT';continue
                ob['getters'][name]=c.rpc('eth_call',[{'to':addr,'data':selector(name+'()')},head])
            logs=c.rpc('eth_getLogs',[{'address':addr,'fromBlock':hex(max(0,int(head,16)-20000)),
                 'toBlock':head,'topics':[topic(signature(launch))]}])
            ob['launch_logs_last_20001_blocks']=len(logs)
            for g in logs:
                r.setdefault('launches',[]).append({'factory':addr,'raw':g})
        trades=c.rpc('eth_getLogs',[{'fromBlock':hex(max(0,int(head,16)-2000)),'toBlock':head,
            'topics':[[topic(signature(buy)),topic(signature(sell))]]}])
        r['curve_shaped_logs_last_2001_blocks']=len(trades)
        emitters=sorted({g['address'].lower() for g in trades})[:2]
        # If no trades, use last available factory-emitted launch instead.
        for x in reversed(r.get('launches',[])):
            names=[f['name'] for f in launch['inputs'] if f['indexed']]
            address='0x'+x['raw']['topics'][1+names.index('curve')][-40:]
            if address not in emitters and len(emitters)<2:emitters.append(address)
        for addr in emitters:
            ob={'address':addr,'getters':{},'runtime_attested':False};r['curves'].append(ob)
            for name in ['factory','token','pairToken','feeBps','creatorTaxBps']:
                ob['getters'][name]=c.rpc('eth_call',[{'to':addr,'data':selector(name+'()')},head])
            owner='0x'+ob['getters']['factory'][-40:];ob['factory_matches_source_candidates']=owner in [factory,OLD]
            # Snipe methods absent in this pinned curve source: do not fabricate ABI or infer zero tax.
            ob['tax_decay_semantics']='UNRESOLVED_SOURCE_FACTORY_CURVE_INCONSISTENCY'
    except Exception as e:
        r['failure_type']=type(e).__name__
        if isinstance(e,ValueError):r['refusal']=str(e)
    r['requests']=c.n;r['ended_ns']=time.time_ns();(out/'result.json').write_text(json.dumps(r,sort_keys=True))
    return {k:v for k,v in r.items() if k not in {'launches','abi_shapes','source_capture'}}


class Capture:
    def __init__(self,out,budget=40):
        if out.resolve().parent!=ROOT.resolve() or out.exists():raise ValueError('fresh private output required')
        os.umask(0o077);out.mkdir();self.out=out;self.n=0;self.budget=budget;self.last=0
        raw=Path(__file__).read_bytes();(out/'probe_source.py').write_bytes(raw)
        (out/'manifest.json').write_text(json.dumps({'source_sha256':digest(raw),'start_wall_ns':time.time_ns(),
            'budget':budget,'purpose':'DEVELOPMENT_CONTRACT_DISCOVERY_NO_RETURNS_NO_TRADE'}))
    def request(self,url,body=None):
        if not (url in (RPC,GITHUB) or re.fullmatch(re.escape(EXPLORER)+ADDRESS.pattern,url) or
                re.fullmatch(re.escape(RAW)+r'[0-9a-f]{40}/(README.md|contractsV2/src/v2/[A-Za-z0-9]+.sol)',url)):
            raise ValueError('URL refused')
        if self.n>=self.budget:raise ValueError('request budget')
        time.sleep(max(0,1.2-(time.monotonic()-self.last)));self.last=time.monotonic();self.n+=1
        prefix=self.out/f'{self.n:03d}';m={'url':url,'request':body,'sent_ns':time.time_ns()}
        try:
            with requests.request('POST' if body else 'GET',url,json=body,timeout=20,stream=True,allow_redirects=False) as r:
                data=[];size=0
                for part in r.iter_content(65536):
                    size+=len(part)
                    if size>8*1024**2:raise ValueError('response size')
                    data.append(part)
                raw=b''.join(data);m.update(http_status=r.status_code,received_ns=time.time_ns(),sha256=digest(raw),bytes=len(raw))
            with prefix.with_suffix('.body').open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            if m['http_status']!=200:raise ValueError('HTTP_'+str(m['http_status']))
            return raw
        except Exception as e:
            m['error_type']=type(e).__name__
            if isinstance(e,ValueError):m['refusal']=str(e)
            raise
        finally:prefix.with_suffix('.json').write_text(json.dumps(m,sort_keys=True))
    def rpc(self,method,params):
        if method not in {'eth_chainId','eth_blockNumber','eth_getCode','eth_call','eth_getLogs','eth_getBlockByNumber'}:
            raise ValueError('read-only RPC allowlist')
        ident=self.n+1
        j=json.loads(self.request(RPC,{'jsonrpc':'2.0','id':ident,'method':method,'params':params}))
        if j.get('id')!=ident or j.get('error') or 'result' not in j:raise ValueError('RPC_ERROR_OR_IDENTITY')
        return j['result']


def run(out):
    c=Capture(out);r={'status':'DEVELOPMENT_ONLY_NO_TRADE','factory_observations':[],'contracts':[],
                      'economic_result':'NOT_COMPUTED'}
    try:
        commit=json.loads(c.request(GITHUB));sha=commit['sha']
        if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('commit format')
        r['github_commit']=sha
        readme=c.request(RAW+sha+'/README.md').decode()
        match=re.search(r'\|\s*V2\s*\|[^\n]*?(0x[0-9a-fA-F]{40})',readme)
        if not match:raise ValueError('README V2 factory absent')
        factory=match.group(1).lower();r['current_readme_factory']=factory
        for path in ['PonsV2LaunchFactory.sol','PonsV2BondingCurve.sol']:
            c.request(RAW+sha+'/contractsV2/src/v2/'+path)
        if int(c.rpc('eth_chainId',[]),16)!=4663:raise ValueError('wrong chain')
        head=c.rpc('eth_blockNumber',[]);r['block']=int(head,16)
        for addr in dict.fromkeys([factory,OLD]):
            code=c.rpc('eth_getCode',[addr,head]);sc=json.loads(c.request(EXPLORER+addr))
            (out/('abi_'+addr+'.json')).write_text(json.dumps(sc.get('abi')))
            ob={'address':addr,'rpc_code_sha256':digest(bytes.fromhex(code[2:])),
                'name':sc.get('name'),'verified':sc.get('is_verified'),
                'explorer_runtime_matches_rpc':str(sc.get('deployed_bytecode','')).lower()==code.lower(),
                'getters':{}}
            abi=sc.get('abi')
            if not isinstance(abi,list):raise ValueError('explorer ABI unavailable')
            for name in ['launchEnabled','snipeTaxStartBps','snipeTaxSeconds','memeHook','poolManager']:
                entries=[x for x in abi if x.get('type')=='function' and x.get('name')==name and not x['inputs']]
                if len(entries)!=1:ob['getters'][name]='ABSENT';continue
                if entries[0].get('stateMutability') not in ('view','pure'):raise ValueError('non-view getter')
                ob['getters'][name]=c.rpc('eth_call',[{'to':addr,'data':selector(signature(entries[0]))},head])
            r['factory_observations'].append(ob)
            events=[x for x in abi if x.get('type')=='event' and x.get('name')=='TokenLaunched']
            if len(events)!=1:raise ValueError('TokenLaunched ABI unresolved')
            e=events[0];r.setdefault('launch_abis',{})[addr]=e
            logs=c.rpc('eth_getLogs',[{'address':addr,'fromBlock':hex(max(0,int(head,16)-2000)),
                'toBlock':head,'topics':[topic(signature(e))]}])
            ob['launch_logs_in_development_slice']=len(logs)
            # One mechanically last emitted launch per factory, not selected by price/volume.
            if logs:
                g=max(logs,key=lambda x:(int(x['blockNumber'],16),int(x['transactionIndex'],16),int(x['logIndex'],16)))
                indexed=[x['name'] for x in e['inputs'] if x['indexed']]
                if 'curve' not in indexed:raise ValueError('curve field absent')
                curve='0x'+g['topics'][1+indexed.index('curve')][-40:]
                code=c.rpc('eth_getCode',[curve,head]);sc=json.loads(c.request(EXPLORER+curve))
                (out/('abi_'+curve+'.json')).write_text(json.dumps(sc.get('abi')))
                r['contracts'].append({'address':curve,'factory':addr,'name':sc.get('name'),
                    'block':int(g['blockNumber'],16),'rpc_code_sha256':digest(bytes.fromhex(code[2:])),
                    'explorer_runtime_matches_rpc':str(sc.get('deployed_bytecode','')).lower()==code.lower(),
                    'event_abi':[x for x in sc.get('abi',[]) if x.get('type')=='event']})
    except Exception as e:
        r['failure_type']=type(e).__name__
        if isinstance(e,ValueError):r['refusal']=str(e)
    r['requests']=c.n;r['ended_ns']=time.time_ns()
    (out/'result.json').write_text(json.dumps(r,sort_keys=True))
    return {k:v for k,v in r.items() if k not in {'launch_abis','contracts'}} | {'curves_identified':len(r['contracts'])}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--rpc-from-source',type=Path)
    p.add_argument('--inspect-launches',type=Path)
    a=p.parse_args()
    result=(inspect_saved_launches(a.inspect_launches,a.out) if a.inspect_launches else
            rpc_discovery(a.rpc_from_source,a.out) if a.rpc_from_source else run(a.out))
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(2 if result.get('failure_type') else 0)
