"""Bounded read-only fee-rights feasibility, not a strategy or order builder.

Pin Raydium SDK source, inspect six recent LP-Lock transactions, identify Fee Keys
from successful collectCpFee instructions, and ask a public marketplace for asks.
No env/key access, subscriptions, signing, transaction construction or submission.
Responses are retained before parsing. Not a census, valuation or profit test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time

import requests

ROOT=Path('research/midcap/fee_rights_private')
SDK_COMMIT='28411d09ad17e598f83885f65c4b6d25a172ced0'
SDK='https://raw.githubusercontent.com/raydium-io/raydium-sdk-V2/'+SDK_COMMIT+'/'
RPC='https://api.mainnet-beta.solana.com'
ME='https://api-mainnet.magiceden.dev/v2/tokens/'
FEE_INFO='https://dynamic-ipfs.raydium.io/lock/cpmm/position?id='
ALPHABET='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
COLLECT=bytes([8,30,51,199,209,184,247,133])
LOCK=bytes([216,157,29,78,38,51,31,26])


def unbase58(s):
    if not isinstance(s,str) or len(s)>4096:raise ValueError('base58 input bound')
    n=0
    for c in s:
        if c not in ALPHABET:raise ValueError('invalid base58')
        n=n*58+ALPHABET.index(c)
    return b'\0'*(len(s)-len(s.lstrip('1')))+(n.to_bytes((n.bit_length()+7)//8,'big') if n else b'')


def claims(tx,signature,program):
    if tx is None:return [],['TRANSACTION_UNAVAILABLE']
    if tx['transaction']['signatures'][0]!=signature:raise ValueError('signature mismatch')
    if not isinstance(tx.get('meta'),dict):return [],['META_UNAVAILABLE']
    meta=tx['meta']
    if 'err' not in meta:raise ValueError('execution status unavailable')
    if meta['err'] is not None:return [],['FAILED_TRANSACTION']
    msg=tx['transaction']['message'];keys=[k['pubkey'] for k in msg['accountKeys']]
    instructions=[(i,None,x) for i,x in enumerate(msg['instructions'])]
    for group in meta.get('innerInstructions') or []:
        instructions.extend((group['index'],i,x) for i,x in enumerate(group['instructions']))
    found=[];issues=[]
    for outer,inner,ins in instructions:
        if ins.get('programId')!=program:continue
        if 'data' not in ins:issues.append('LOCK_INSTRUCTION_UNPARSED');continue
        data=unbase58(ins['data'])
        if data[:8]!=COLLECT:issues.append('OTHER_LOCK_INSTRUCTION:'+data[:8].hex());continue
        ac=ins.get('accounts',[])
        if len(data)!=16 or len(ac)!=18:raise ValueError('collect layout mismatch')
        nft_index=keys.index(ac[2]);nfts=set()
        for side in ['preTokenBalances','postTokenBalances']:
            if not isinstance(meta.get(side),list):raise ValueError('missing balance metadata')
            for b in meta[side]:
                u=b['uiTokenAmount']
                if b['accountIndex']==nft_index:
                    if b.get('owner')!=ac[1] or u.get('decimals')!=0 or u.get('amount')!='1':
                        raise ValueError('Fee Key owner/amount mismatch')
                    nfts.add(b['mint'])
        if len(nfts)!=1:raise ValueError('Fee Key mint unresolved')
        found.append({'signature':signature,'slot':tx['slot'],'outer_index':outer,'inner_index':inner,
                      'transaction_index':None,'nft_mint':nfts.pop(),'lock_pda':ac[3],'pool':ac[6],
                      'requested_lp_fee_units':str(int.from_bytes(data[8:],'little')),
                      'mint_a':ac[12],'mint_b':ac[13],
                      'evidence':'SUCCESSFUL_RPC_INSTRUCTION_MATCH; not pending fee valuation'})
    return found,issues


def issued_keys(tx,signature,program):
    """Identify only the SDK-pinned CPMM lock shape; never infer accrued cash."""
    if tx is None:return [],['TRANSACTION_UNAVAILABLE']
    if tx['transaction']['signatures'][0]!=signature:raise ValueError('signature mismatch')
    meta=tx.get('meta')
    if not isinstance(meta,dict) or 'err' not in meta:raise ValueError('execution status unavailable')
    if meta['err'] is not None:return [],['FAILED_TRANSACTION']
    msg=tx['transaction']['message'];keys=[k['pubkey'] for k in msg['accountKeys']]
    instructions=[(i,None,x) for i,x in enumerate(msg['instructions'])]
    for group in meta.get('innerInstructions') or []:
        instructions.extend((group['index'],i,x) for i,x in enumerate(group['instructions']))
    found=[];issues=[]
    for outer,inner,ins in instructions:
        if ins.get('programId')!=program:continue
        if 'data' not in ins:issues.append('LOCK_INSTRUCTION_UNPARSED');continue
        data=unbase58(ins['data'])
        if data[:8]!=LOCK:issues.append('OTHER_LOCK_INSTRUCTION:'+data[:8].hex());continue
        ac=ins.get('accounts',[])
        if len(data)!=17 or data[-1] not in (0,1) or len(ac)!=19:
            raise ValueError('lock layout mismatch')
        if not isinstance(meta.get('postTokenBalances'),list):raise ValueError('missing balance metadata')
        balances=[b for b in meta['postTokenBalances'] if b['accountIndex']==keys.index(ac[5])]
        if len(balances)!=1:raise ValueError('Fee Key account unresolved')
        b=balances[0];u=b['uiTokenAmount']
        if b.get('owner')!=ac[3] or b['mint']!=ac[4] or u.get('decimals')!=0 or u.get('amount')!='1':
            raise ValueError('Fee Key owner/amount mismatch')
        found.append({'signature':signature,'slot':tx['slot'],'outer_index':outer,'inner_index':inner,
                      'transaction_index':None,'nft_mint':ac[4],'lock_pda':ac[7],'pool':ac[6],
                      'evidence':'SUCCESSFUL_RPC_LOCK_SHAPE; not current ownership or fee valuation'})
    return found,issues


class Capture:
    def __init__(self,out):
        if out.resolve().parent!=ROOT.resolve() or out.exists():raise ValueError('fresh private directory required')
        os.umask(0o077);out.mkdir();self.out=out;self.count=0;self.last=0
    def request(self,url,body=None):
        if not (url.startswith(SDK) or url==RPC or
                re.fullmatch(re.escape(ME)+r'[1-9A-HJ-NP-Za-km-z]{32,44}/listings\?listingAggMode=true',url) or
                re.fullmatch(re.escape(FEE_INFO)+r'[1-9A-HJ-NP-Za-km-z]{32,44}',url)):
            raise ValueError('request target refused')
        if self.count>=32:raise ValueError('request budget exhausted')
        time.sleep(max(0,2-(time.monotonic()-self.last)))
        self.last=time.monotonic();self.count+=1
        sent=(time.time_ns(),time.monotonic_ns());meta={'url':url,'request':body,'sent_wall_ns':sent[0],'sent_mono_ns':sent[1]}
        prefix=self.out/f'{self.count:03d}'
        try:
            with requests.request('POST' if body else 'GET',url,json=body,timeout=15,stream=True,allow_redirects=False) as r:
                chunks=[];size=0
                for chunk in r.iter_content(65536):
                    size+=len(chunk)
                    if size>8*1024**2:raise ValueError('response byte bound')
                    chunks.append(chunk)
                raw=b''.join(chunks);meta.update({'received_wall_ns':time.time_ns(),'received_mono_ns':time.monotonic_ns(),
                    'http_status':r.status_code,'representation':'HTTP decoded response bytes',
                    'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
            with prefix.with_suffix('.body').open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            if meta['http_status']!=200:raise ValueError('HTTP_'+str(meta['http_status']))
            return raw
        except Exception as e:
            meta['failure_type']=type(e).__name__
            if isinstance(e,ValueError):meta['refusal']=str(e)
            raise
        finally:
            with prefix.with_suffix('.json').open('x') as f:json.dump(meta,f,sort_keys=True)
    def rpc(self,method,params):
        if method not in {'getAccountInfo','getSignaturesForAddress','getTransaction'}:raise ValueError('RPC method refused')
        ident=self.count+1
        j=json.loads(self.request(RPC,{'jsonrpc':'2.0','id':ident,'method':method,'params':params}))
        if j.get('id')!=ident or j.get('error') or 'result' not in j:raise ValueError('RPC refused')
        return j['result']


def checked_body(prefix):
    meta=json.loads(prefix.with_suffix('.json').read_text())
    raw=prefix.with_suffix('.body').read_bytes()
    if meta.get('http_status')!=200 or hashlib.sha256(raw).hexdigest()!=meta.get('sha256'):
        raise ValueError('saved response hash/status mismatch')
    return meta,raw


def market_from_saved(source,out):
    """Development-only market feasibility using prior successful RPC bodies, no RPC."""
    if source.resolve().parent!=ROOT.resolve():raise ValueError('private capture source required')
    c=Capture(out);result={'status':'NO_TRADE_FEASIBILITY','economic_result':'UNMEASURED',
        'source':str(source),'sdk_commit':SDK_COMMIT,'inputs':{},'keys':[], 'issues':[],
        'listing_checks':[], 'fee_info_checks':[], 'sampling':'available saved transactions, not a census'}
    source_raw=Path(__file__).read_bytes()
    (out/'probe_source.py').write_bytes(source_raw)
    (out/'manifest.json').write_text(json.dumps({'started_wall_ns':time.time_ns(),
        'source_sha256':hashlib.sha256(source_raw).hexdigest(),'spec':result},sort_keys=True))
    try:
        m,raw=checked_body(source/'001')
        if m['url']!=SDK+'src/common/programId.ts':raise ValueError('pinned SDK source mismatch')
        program=re.search(r'export const LOCK_CPMM_PROGRAM = new PublicKey\("([^"]+)"\)',raw.decode()).group(1)
        m,raw=checked_body(source/'002')
        if m['url']!=SDK+'src/raydium/cpmm/instruction.ts':raise ValueError('pinned SDK source mismatch')
        match=re.search(r'lockCpLiquidity: \[([^]]+)\]',raw.decode())
        if not match or bytes(int(x.strip()) for x in match.group(1).split(','))!=LOCK:
            raise ValueError('SDK discriminator mismatch')
        for path in sorted(source.glob('[0-9][0-9][0-9].json')):
            m=json.loads(path.read_text());req=m.get('request') or {}
            if req.get('method')!='getTransaction' or m.get('http_status')!=200:continue
            m,raw=checked_body(path.with_suffix(''));j=json.loads(raw)
            if j.get('id')!=req.get('id') or j.get('error') or 'result' not in j:raise ValueError('RPC identity/error')
            result['inputs'][path.name]=m['sha256']
            entries,issues=issued_keys(j['result'],req['params'][0],program)
            result['keys']+=entries;result['issues']+=issues
        # Retain the exact primary API routing source too. No inferred endpoint paths.
        url_source=c.request(SDK+'src/api/url.ts').decode()
        if 'CPMM_LOCK: "'+FEE_INFO.split('?')[0]+'"' not in url_source:
            raise ValueError('fee info endpoint differs from pinned SDK')
        for k in sorted({x['nft_mint']:x for x in result['keys']}.values(),key=lambda x:x['nft_mint'])[:6]:
            for kind,url in [('listing',ME+k['nft_mint']+'/listings?listingAggMode=true'),
                             ('fee_info',FEE_INFO+k['lock_pda'])]:
                try:
                    j=json.loads(c.request(url))
                    if kind=='listing' and not isinstance(j,list):raise ValueError('unknown listing schema')
                    result[kind+'_checks'].append({'nft_mint':k['nft_mint'],
                        'status':'RESPONSE_NOT_EXECUTION', 'rows':len(j) if isinstance(j,list) else None,
                        'top_level_keys':sorted(j) if isinstance(j,dict) else None})
                except Exception as e:
                    result[kind+'_checks'].append({'nft_mint':k['nft_mint'],'status':'UNAVAILABLE',
                        'failure_type':type(e).__name__,'refusal':str(e) if isinstance(e,ValueError) else None})
                    break
    except Exception as e:
        result['failure_type']=type(e).__name__
        if isinstance(e,ValueError):result['refusal']=str(e)
    result['request_count']=c.count;result['ended_wall_ns']=time.time_ns()
    (out/'result.json').write_text(json.dumps(result,sort_keys=True))
    return {k:v for k,v in result.items() if k not in {'keys','inputs','source'}} | {
        'saved_transactions':len(result['inputs']),'identified_keys':len(result['keys']),
        'listing_checks':[{k:v for k,v in x.items() if k!='nft_mint'} for x in result['listing_checks']],
        'fee_info_checks':[{k:v for k,v in x.items() if k!='nft_mint'} for x in result['fee_info_checks']]}


def run(out):
    c=Capture(out);result={'status':'NO_TRADE_FEASIBILITY','sdk_commit':SDK_COMMIT,
        'sampling':'first six returned LP-Lock signature rows; not a census or outcome-selected',
        'max_requests':32,'sources':{},'transactions_requested':0,'claims':[],'issues':[],
        'listing_checks':[],'economic_result':'UNMEASURED','offers_executable':'UNVERIFIED'}
    with (out/'manifest.json').open('x') as f:json.dump({'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'started_wall_ns':time.time_ns(),'spec':result},f,sort_keys=True)
    try:
        for name in ['src/common/programId.ts','src/raydium/cpmm/instruction.ts']:
            raw=c.request(SDK+name);result['sources'][name]=hashlib.sha256(raw).hexdigest()
            source=raw.decode()
            if name.endswith('programId.ts'):
                match=re.search(r'export const LOCK_CPMM_PROGRAM = new PublicKey\("([^"]+)"\)',source)
                if not match:raise ValueError('SDK lock program absent')
                program=match.group(1)
            else:
                match=re.search(r'collectCpFee: \[([^]]+)\]',source)
                if not match or bytes(int(x.strip()) for x in match.group(1).split(','))!=COLLECT:
                    raise ValueError('SDK discriminator mismatch')
        account=c.rpc('getAccountInfo',[program,{'encoding':'base64','commitment':'finalized'}])
        if not account.get('value',{}).get('executable'):raise ValueError('lock program not executable')
        result['program_observation_slot']=account['context']['slot'];result['program']=program
        sigs=c.rpc('getSignaturesForAddress',[program,{'limit':6,'commitment':'finalized'}])
        if not isinstance(sigs,list) or len(sigs)>6:raise ValueError('signature response bound')
        for s in sigs:
            result['transactions_requested']+=1
            tx=c.rpc('getTransaction',[s['signature'],{'encoding':'jsonParsed','maxSupportedTransactionVersion':0,'commitment':'finalized'}])
            entries,issues=claims(tx,s['signature'],program);result['claims']+=entries;result['issues']+=issues
        for mint in sorted({x['nft_mint'] for x in result['claims']}):
            try:
                listing=json.loads(c.request(ME+mint+'/listings?listingAggMode=true'))
                if not isinstance(listing,list):raise ValueError('unknown listing schema')
                result['listing_checks'].append({'nft_mint':mint,'response_rows':len(listing),
                    'status':'MARKETPLACE_RESPONSE_NOT_EXECUTION'})
            except Exception as e:
                result['listing_checks'].append({'nft_mint':mint,'status':'UNAVAILABLE','error_type':type(e).__name__})
                break  # no repeated requests on auth/rate failures
    except Exception as e:
        result['failure_type']=type(e).__name__
        if isinstance(e,ValueError):result['refusal']=str(e)
    finally:
        result['request_count']=c.count;result['ended_wall_ns']=time.time_ns()
        with (out/'result.json').open('x') as f:json.dump(result,f,sort_keys=True)
    return {'status':result['status'],'requests':c.count,'transactions':result['transactions_requested'],
        'successful_collect_instructions':len(result['claims']),
        'distinct_fee_keys':len({x['nft_mint'] for x in result['claims']}),
        'listing_checks':[{k:v for k,v in x.items() if k!='nft_mint'} for x in result['listing_checks']],
        'failure_type':result.get('failure_type'),'refusal':result.get('refusal'),
        'economic_result':'UNMEASURED'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--from-capture',type=Path)
    a=p.parse_args()
    result=market_from_saved(a.from_capture,a.out) if a.from_capture else run(a.out)
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(2 if result.get('failure_type') else 0)
