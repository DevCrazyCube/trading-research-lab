"""Bounded paired Robinhood log/FOMO-alert observation; no trading or performance.

Three source identities fixed from the earlier schema pilot, before this new window.
At most three FOMO resolutions and three alert connections; no paid upgrade.
Public RPC is read-only. Transfer/alert associations are NOT authenticated trade IDs.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from urllib.parse import quote
import zlib

import requests
import websocket
from Crypto.Hash import keccak
from scripts.fomo_probe import PRIVATE, get_key

RPC='https://rpc.mainnet.chain.robinhood.com'
FOMO='https://api.fomoapi.io'
TRANSFER='0x'+keccak.new(digest_bits=256,data=b'Transfer(address,address,uint256)').hexdigest()
ADDRESS=re.compile(r'0x[0-9a-fA-F]{40}')
HASH=re.compile(r'0x[0-9a-fA-F]{64}')
MAX_HTTP=16*1024**2


def decode_http(raw,encoding):
    if encoding in ('','identity',None):
        if len(raw)>MAX_HTTP:raise ValueError('HTTP decoded byte bound exceeded')
        return raw
    if encoding not in ('gzip','deflate'):raise ValueError('unsupported HTTP encoding')
    decoder=zlib.decompressobj(16+zlib.MAX_WBITS if encoding=='gzip' else zlib.MAX_WBITS)
    decoded=decoder.decompress(raw,MAX_HTTP+1)
    if len(decoded)>MAX_HTTP or not decoder.eof or decoder.unused_data:
        raise ValueError('oversized/incomplete HTTP compression')
    return decoded


def address(value):
    if not isinstance(value,str) or not ADDRESS.fullmatch(value):
        raise ValueError('invalid EVM address')
    return value.lower()


def transfer(log):
    """Strict ERC20-shaped event, not proof of token behavior or an executed swap."""
    topics=log.get('topics',[])
    if not topics or topics[0].lower()!=TRANSFER:
        return None
    if len(topics)!=3 or any(not isinstance(t,str) or not HASH.fullmatch(t) for t in topics):
        return None  # e.g. ERC721 shares the signature but has four indexed topics
    if any(t[2:26]!='0'*24 for t in topics[1:]) or not HASH.fullmatch(log.get('data','')):
        raise ValueError('malformed ERC20-shaped transfer')
    if log.get('removed') is not False:
        raise ValueError('removed or uncertain log')
    return {'token':address(log['address']),'from':address('0x'+topics[1][-40:]),
            'to':address('0x'+topics[2][-40:]),'amount':int(log['data'],16)}


def select_handles(pilot):
    db=sqlite3.connect(pilot.resolve().as_uri()+'?mode=ro',uri=True)
    selected=[]
    try:
        for (raw,) in db.execute('SELECT raw FROM raw_frame ORDER BY sequence'):
            row=json.loads(raw)
            handle=row.get('trader')
            if (row.get('type')=='alert' and row.get('chainId')==4663
                    and row.get('alertType') in {'buy','sell'} and isinstance(handle,str)
                    and re.fullmatch(r'@?[A-Za-z0-9_.-]{1,80}',handle)):
                handle=handle.lstrip('@').lower()
                if handle not in selected:selected.append(handle)
                if len(selected)==3:break
    finally:db.close()
    if len(selected)!=3:raise ValueError('three fixed source identities unavailable')
    return selected


class Evidence:
    def __init__(self,out,key):
        if out.resolve().parent!=PRIVATE.resolve() or out.exists():
            raise ValueError('new directory directly under fomo_private required')
        os.umask(0o077);out.mkdir()
        self.out,self.key,self.lock=out,key,threading.RLock()
        self.db=sqlite3.connect(out/'raw.sqlite',check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE raw(sequence INTEGER PRIMARY KEY,kind TEXT,wall_ns INTEGER,mono_ns INTEGER,meta TEXT,payload BLOB,sha256 TEXT)')
        self.seq,self.total,self.previous=0,0,'0'*64

    def save(self,kind,payload,meta=None,clocks=None):
        wall,mono=clocks or (time.time_ns(),time.monotonic_ns())
        raw=payload if isinstance(payload,bytes) else json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
        metadata=json.dumps(meta or {},sort_keys=True,separators=(',',':'))
        if self.key.encode() in raw or self.key in metadata:raise ValueError('secret echo refused')
        with self.lock:
            if self.total+len(raw)>128*1024**2:raise ValueError('capture byte bound exceeded')
            seq=self.seq+1
            h=hashlib.sha256(json.dumps([self.previous,seq,kind,wall,mono,metadata,
                                         hashlib.sha256(raw).hexdigest()],separators=(',',':')).encode()).hexdigest()
            self.db.execute('INSERT INTO raw VALUES (?,?,?,?,?,?,?)',(seq,kind,wall,mono,metadata,raw,h))
            self.db.commit();self.seq=seq;self.previous=h;self.total+=len(raw)
            return self.seq

    def request(self,url,method='GET',body=None,headers=None,kind='http'):
        before=(time.time_ns(),time.monotonic_ns())
        # Fixed callers only. Never follow redirects with an API credential.
        if url!=RPC and not url.startswith(FOMO+'/v2/users/'):
            raise ValueError('HTTP target outside probe allowlist')
        try:
            r=requests.request(method,url,json=body,headers={'Accept-Encoding':'identity',**(headers or {})},
                               timeout=8,allow_redirects=False,stream=True)
            raw=r.raw.read(MAX_HTTP+1);clocks=(time.time_ns(),time.monotonic_ns())
            meta={'url':url,'request':body,'sent_wall_ns':before[0],'sent_mono_ns':before[1],
                  'http_status':r.status_code,'credits_cost':r.headers.get('x-credits-cost'),
                  'credits_remaining':r.headers.get('x-credits-remaining'),
                  'content_encoding':r.headers.get('Content-Encoding','identity').lower()}
            clear=decode_http(raw,meta['content_encoding'])
            if self.key.encode() in clear:raise ValueError('compressed secret echo refused')
            self.save(kind,raw,meta,clocks);r.close()
            if len(raw)>MAX_HTTP or meta['http_status']!=200:raise ValueError('HTTP response refused')
            return json.loads(clear),clocks
        except Exception as error:
            self.save('request_error',{'error_type':type(error).__name__},{'kind':kind})
            raise


def validate_logs(logs,first,last):
    if not isinstance(logs,list):raise ValueError('logs unavailable')
    seen=set()
    for log in logs:
        number=int(log['blockNumber'],16)
        coordinate=(log['blockHash'],log['transactionHash'],int(log['logIndex'],16))
        if not first<=number<=last or coordinate in seen:raise ValueError('duplicate/out-of-range log')
        if not HASH.fullmatch(log['blockHash']) or not HASH.fullmatch(log['transactionHash']):
            raise ValueError('invalid transaction/block identity')
        if log.get('removed') is not False:raise ValueError('removed/uncertain log')
        int(log['transactionIndex'],16);address(log['address']);seen.add(coordinate)
    return logs


def run(pilot,out,seconds,roster=None,poll_seconds=5):
    if not math.isfinite(seconds) or not 30<=seconds<=600:raise ValueError('duration 30..600 required')
    if not math.isfinite(poll_seconds) or not 5<=poll_seconds<=30:raise ValueError('poll interval 5..30 required')
    handles=select_handles(pilot);key=get_key();e=Evidence(out,key)
    e.save('manifest',{'schema':'fomo-chain-feasibility-v1','selected_handles':handles,
        'selection':'first three distinct eligible Robinhood handles by prior pilot receipt order; not PnL',
        'pilot':str(pilot),'seconds':seconds,'max_fomo_resolutions':3,'max_fomo_connections':3,
        'roster_reuse':str(roster) if roster else None,'poll_seconds':poll_seconds,
        'max_rpc_calls':1200,'max_catchup_blocks':128,'source_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'chain_id':4663,'status':'NO_TRADE','canonical_status':'UNFINALIZED_RPC_OBSERVATIONS',
        'join_policy':'all plausible associations retained; never authenticated trade identity or PnL'})
    rpc_calls=0
    def rpc(method,params):
        nonlocal rpc_calls
        if method not in {'eth_chainId','eth_getBlockByNumber','eth_getLogs'}:raise ValueError('RPC method refused')
        rpc_calls+=1
        if rpc_calls>1200:raise ValueError('RPC budget exhausted')
        result,clocks=e.request(RPC,'POST',{'jsonrpc':'2.0','id':rpc_calls,'method':method,'params':params},kind='rpc')
        if result.get('id')!=rpc_calls or result.get('error') or result.get('result') is None:
            raise ValueError('RPC response refused')
        return result['result'],clocks
    mapping={};stop=threading.Event();ws_thread=None
    try:
        chain,_=rpc('eth_chainId',[])
        if int(chain,16)!=4663:raise ValueError('wrong chain')
        if roster:
            old_summary=summarize(roster)
            if not old_summary['ended']:raise ValueError('roster source must be closed')
            source_db=sqlite3.connect((roster/'raw.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
            try:
                saved=source_db.execute("SELECT wall_ns,payload FROM raw WHERE kind='roster_ready'").fetchall()
            finally:source_db.close()
            if len(saved)!=1 or not 0<=time.time_ns()-saved[0][0]<=2*3600*10**9:
                raise ValueError('roster absent, future or older than two hours')
            mapping={h:address(w) for h,w in json.loads(saved[0][1])['mapping'].items()}
            if set(mapping)!=set(handles):raise ValueError('roster selection changed')
            e.save('identity_reused',{'source':str(roster),'source_raw_tail':old_summary['raw_tail_sha256'],
                                     'identity_observed_wall_ns':saved[0][0]})
        else:
            for handle in handles:
                user,clocks=e.request(FOMO+'/v2/users/'+quote(handle,safe=''),
                    headers={'Authorization':'Bearer '+key},kind='identity')
                returned=(user.get('handle') or user.get('userHandle') or '').lstrip('@').lower()
                if returned!=handle:raise ValueError('resolver returned another identity')
                mapping[handle]=address((user.get('wallets') or {}).get('evm'))
        start_wall=time.time_ns();deadline=time.monotonic()+seconds
        e.save('roster_ready',{'mapping':mapping,'identity_status':'VENDOR_CLAIM','start_wall_ns':start_wall})
        def alerts():
            for epoch in range(1,4):
                if stop.is_set() or time.monotonic()>=deadline:return
                ws=None
                try:
                    e.save('ws_epoch',{'epoch':epoch})
                    ws=websocket.create_connection('wss://api.fomoapi.io/ws/alerts?key='+quote(key,safe=''),
                                                    timeout=min(8,max(.01,deadline-time.monotonic())),redirect_limit=0)
                    last_ping=time.monotonic()
                    while not stop.is_set() and time.monotonic()<deadline:
                        if time.monotonic()-last_ping>10:ws.ping();last_ping=time.monotonic()
                        ws.settimeout(min(2,max(.01,deadline-time.monotonic())))
                        try:
                            raw=ws.recv();clocks=(time.time_ns(),time.monotonic_ns())
                        except websocket.WebSocketTimeoutException:continue
                        if raw in ('',b''):raise ConnectionError('remote close')
                        raw=raw.encode() if isinstance(raw,str) else raw
                        e.save('alert_frame',raw,{'epoch':epoch},clocks)
                except Exception as error:
                    e.save('ws_gap',{'epoch':epoch,'error_type':type(error).__name__,'coverage':'UNKNOWN_UNREPAIRED'})
                finally:
                    if ws:
                        try:ws.close(timeout=1)
                        except Exception:pass
                if stop.wait(min(1,max(0,deadline-time.monotonic()))):return
            e.save('ws_exhausted',{'max_connections':3});stop.set()
        ws_thread=threading.Thread(target=alerts);ws_thread.start()
        last=None;polls=0
        while not stop.is_set() and time.monotonic()<deadline:
            before=time.monotonic()
            head,_=rpc('eth_getBlockByNumber',['latest',False]);number=int(head['number'],16)
            if last is None:last=number-1
            if number<last:raise ValueError('chain head regressed')
            if number-last>128:raise ValueError('chain catchup bound exceeded')
            if number>last:
                logs,_=rpc('eth_getLogs',[{'fromBlock':hex(last+1),'toBlock':hex(number)}])
                validate_logs(logs,last+1,number)
                e.save('range_validated',{'first':last+1,'last':number,'logs':len(logs),
                                         'status':'SINGLE_SOURCE_NOT_CENSUS'})
                last=number
            polls+=1
            if polls%15==0:print(json.dumps({'status':'PAIRED_CAPTURE_NO_TRADE','polls':polls,'rpc_calls':rpc_calls}),flush=True)
            stop.wait(max(0,min(poll_seconds-(time.monotonic()-before),deadline-time.monotonic())))
        e.save('end',{'reason':'DURATION_COMPLETE' if time.monotonic()>=deadline else 'STREAM_LIMIT',
                      'rpc_calls':rpc_calls})
    except BaseException as error:
        e.save('failure',{'error_type':type(error).__name__,'rpc_calls':rpc_calls})
        raise
    finally:
        stop.set()
        if ws_thread:ws_thread.join(timeout=12)
        if ws_thread and ws_thread.is_alive():raise ValueError('websocket thread did not finish')
        e.save('closed',{'status':'NO_TRADE'});e.db.close()
    return summarize(out)


def summarize(out):
    db=sqlite3.connect((out/'raw.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    raw=db.execute('SELECT * FROM raw ORDER BY sequence').fetchall();db.close()
    previous='0'*64;counts=Counter();transfers=[];alerts=[];mapping={};start=0;welcome=[];credits=[];last_clocks={}
    for seq,kind,wall,mono,meta,payload,h in raw:
        expected=hashlib.sha256(json.dumps([previous,seq,kind,wall,mono,meta,
                                            hashlib.sha256(payload).hexdigest()],separators=(',',':')).encode()).hexdigest()
        if h!=expected or seq!=sum(counts.values())+1:raise ValueError('raw hash chain mismatch')
        previous=h;counts[kind]+=1;metadata=json.loads(meta)
        if kind in last_clocks:
            w,m=last_clocks[kind]
            if mono<=m or wall<w or abs((wall-w)-(mono-m))>10**9:raise ValueError('clock discontinuity')
        last_clocks[kind]=(wall,mono)
        row=json.loads(decode_http(payload,metadata.get('content_encoding','gzip' if payload[:2]==b'\x1f\x8b' else 'identity')))
        if kind=='identity':credits.append(metadata.get('credits_cost'))
        if kind=='roster_ready':mapping=row['mapping'];start=row['start_wall_ns']
        if kind=='alert_frame':
            if row.get('type')=='welcome':welcome.append({'realtime':row.get('realtime'),'delaySeconds':row.get('delaySeconds')})
            if row.get('type')=='alert':alerts.append((wall,mono,row))
        if kind=='rpc' and (metadata.get('request') or {}).get('method')=='eth_getLogs' and isinstance(row.get('result'),list):
            by_tx={}
            for log in row['result']:
                t=transfer(log)
                if t:
                    identity=(log['blockHash'],log['transactionHash'])
                    values=by_tx.setdefault(identity,defaultdict(int))
                    values[(t['to'],t['token'])]+=t['amount'];values[(t['from'],t['token'])]-=t['amount']
            for (block,tx),values in by_tx.items():
                for (wallet,token),amount in values.items():
                    if wallet in mapping.values() and amount:
                        transfers.append({'wallet':wallet,'token':token,'amount':amount,'block':block,'tx':tx,'wall':wall,'mono':mono})
    eligible=[];replays=0
    for wall,mono,a in alerts:
        if a.get('replay') is True:replays+=1;continue
        handle=(a.get('trader') or '').lstrip('@').lower()
        if a.get('chainId')!=4663 or handle not in mapping or a.get('alertType') not in {'buy','sell'}:continue
        # Provider time is only a replay/staleness screen, never the lead clock.
        ts=a.get('ts')
        if type(ts) not in (int,float) or not start/1e6<=ts<=wall/1e6:continue
        token=address(a.get('tokenAddress'));sign=1 if a['alertType']=='buy' else -1
        candidates=[t for t in transfers if t['wallet']==mapping[handle] and t['token']==token and t['amount']*sign>0
                    and -30e9 <= mono-t['mono'] <= 60e9]
        eligible.append({'candidate_count':len(candidates),
            'candidate_observed_leads_seconds':[(mono-t['mono'])/1e9 for t in candidates],
            'status':'UNAUTHENTICATED_ASSOCIATION_NOT_TRADE_ID'})
    result={'status':'FEASIBILITY_NO_TRADE','records':dict(counts),'frames':len(alerts),'explicit_replays':replays,
            'welcomes':welcome,'roster_size':len(mapping),'roster_transfer_observations':len(transfers),
            'prospective_roster_alerts':len(eligible),'candidate_associations':eligible,'resolution_credit_headers':credits,
            'raw_chain':'EXACT_INTERNAL','raw_tail_sha256':previous,'ended':bool(counts['closed']),'capture_failed':bool(counts['failure']),
            'edge':'UNMEASURED','pnl':'NOT_COMPUTED','identity':'VENDOR_MAPPING_NOT_INDEPENDENTLY_AUTHENTICATED'}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--pilot',type=Path,default=PRIVATE/'probe_network_20260908.sqlite')
    parser.add_argument('--seconds',type=float,default=300)
    parser.add_argument('--report',action='store_true')
    parser.add_argument('--roster',type=Path)
    parser.add_argument('--poll-seconds',type=float,default=5)
    args=parser.parse_args()
    try:
        result=summarize(args.out) if args.report else run(args.pilot,args.out,args.seconds,args.roster,args.poll_seconds)
        print(json.dumps(result,sort_keys=True),flush=True)
        if not args.report:
            with (args.out/'summary.json').open('x') as stream:json.dump(result,stream,sort_keys=True)
    except Exception as error:
        print(json.dumps({'status':'REFUSED_NO_TRADE','error_type':type(error).__name__}),flush=True)
        raise SystemExit(2)
