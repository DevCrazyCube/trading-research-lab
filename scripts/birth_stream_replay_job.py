"""Observable offline job around the existing full birth-stream verifier.

Same verification gates; cache the pinned IDL event map and emit durable progress.
No RPC, sampling, strategy evaluation, source writes, or implicit restart.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from scripts import birth_stream_verify as V
from scripts import b9d_transaction_bodies as B
from scripts.birth_origin import Refused, write_new


def run(source, out):
    if out.exists():
        raise Refused('new job directory required')
    out.mkdir(parents=True)
    started=time.time_ns()
    write_new(out/'job.json', {'status':'FULL_REPLAY_STARTED_NO_TRADE','source':str(source),
        'started_unix_nanos':started,'pid':os.getpid(),
        'verifier_sha256':hashlib.sha256(Path(V.__file__).read_bytes()).hexdigest(),
        'wrapper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'network':'DISABLED','sampling':'NONE','source_access':'READ_ONLY'})
    original=V.decode_notification
    cached=None
    calls=0
    with (out/'progress.jsonl').open('x') as progress:
        def emit(item):
            progress.write(json.dumps(item,sort_keys=True)+'\n')
            progress.flush()
            os.fsync(progress.fileno())
            print(json.dumps(item,sort_keys=True),flush=True)
        def decode(message, idl, subscription):
            nonlocal cached,calls
            if cached is None:
                cached=B.event_entries(idl)
            calls+=1
            if calls % 100000 == 0:
                emit({'status':'REPLAYING_NOT_ATTESTED','decoder_calls':calls,
                      'elapsed_seconds':(time.time_ns()-started)/1e9})
            return original(message,idl,subscription,cached)
        V.decode_notification=decode
        try:
            report,observations=V.verify(source)
            report['job_provenance']={'wrapper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                     'elapsed_seconds':(time.time_ns()-started)/1e9}
            write_new(out/'raw_replay.json',report)
            write_new(out/'result.json',report)
            emit({'status':'FULL_REPLAY_COMPLETE_NO_TRADE','frames':report['frames'],
                  'creates':report['creates'],'raw_replay':report['raw_replay'],
                  'elapsed_seconds':(time.time_ns()-started)/1e9})
        except BaseException as error:
            failure={'status':'REPLAY_FAILED_NOT_ATTESTED','error_type':type(error).__name__,
                     'decoder_calls':calls,'elapsed_seconds':(time.time_ns()-started)/1e9}
            write_new(out/'failure.json',failure)
            emit(failure)
            raise
        finally:
            V.decode_notification=original


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    run(args.source,args.out)
