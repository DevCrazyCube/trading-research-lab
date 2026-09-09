"""One bounded FOMO alerts connection, raw evidence only; no trades or retries.

Reads only FOMO_API_KEY from the environment or .env. Never prints the URL/key,
wallets, handles, alert text, or exception bodies. Raw output stays git-ignored.
This is a transport/schema feasibility probe, NOT a canonical event/feature feed.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import sqlite3
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'research/midcap/fomo_private'
ENDPOINT = 'wss://api.fomoapi.io/ws/alerts'
MAX_FRAME = 1024 * 1024
MAX_RAW = 8 * 1024 * 1024


def get_key():
    key = os.environ.get('FOMO_API_KEY')
    if not key:
        matches = []
        with (ROOT / '.env').open() as stream:
            for line in stream:
                name, sep, value = line.partition('=')
                if sep and name.strip().removeprefix('export ') == 'FOMO_API_KEY':
                    parts = shlex.split(value, comments=True)
                    if len(parts) != 1:
                        raise ValueError('invalid API key configuration')
                    matches.append(parts[0])
        if len(matches) != 1:
            raise ValueError('one FOMO_API_KEY required')
        key = matches[0]
    if len(key) < 8 or any(c.isspace() for c in key):
        raise ValueError('invalid API key configuration')
    return key


def digest(previous, seq, wall, mono, raw):
    metadata = json.dumps([previous, seq, wall, mono,
                           hashlib.sha256(raw).hexdigest()], separators=(',', ':'))
    return hashlib.sha256(metadata.encode()).hexdigest()


def inspect_frames(frames):
    kinds, chains, fields, replay, hash_fields = Counter(), Counter(), Counter(), Counter(), Counter()
    welcomes, invalid, clocks, previous_clocks = [], 0, 0, None
    alerts, lag_ms = 0, []
    for wall, mono, raw in frames:
        if previous_clocks:
            w, m = previous_clocks
            if mono <= m or wall < w or abs((wall - w) - (mono - m)) > 10**9:
                clocks += 1
        previous_clocks = (wall, mono)
        try:
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise ValueError('not an object')
        except (ValueError, UnicodeError):
            invalid += 1
            continue
        kind = message.get('type')
        kind = kind if isinstance(kind, str) else 'UNKNOWN'
        kinds[kind if kind in {'welcome', 'alert', 'trade', 'retract', 'error', 'ping', 'pong', 'subscribed'} else 'UNKNOWN'] += 1
        if kind == 'welcome':
            welcomes.append({key: message.get(key) if type(message.get(key)) in (bool, int, float) else None
                             for key in ['realtime', 'delaySeconds']})
        if kind != 'alert':
            continue
        alerts += 1
        # Field names are schema information. No payload values are printed.
        fields.update(message.keys())
        chain = message.get('chainId')
        chains[str(chain) if type(chain) is int else 'UNKNOWN'] += 1
        replay['EXPLICIT_REPLAY' if message.get('replay') is True else
               'EXPLICIT_NOT_REPLAY' if message.get('replay') is False else 'UNKNOWN'] += 1
        for key in ['txHash', 'transactionHash', 'signature']:
            if isinstance(message.get(key), str) and message[key]:
                hash_fields[key] += 1  # presence only; not validated identity
        ts = message.get('ts')
        if type(ts) in (int, float) and math.isfinite(ts):
            lag_ms.append(wall / 10**6 - ts)
    return {'status': 'FEASIBILITY_ONLY_NO_TRADE', 'message_types': dict(kinds), 'alerts': alerts,
            'alert_chain_ids': dict(chains), 'alert_fields': dict(fields), 'welcome_claims': welcomes,
            'replay_status': dict(replay), 'transaction_identifier_fields_present': dict(hash_fields),
            'malformed_frames': invalid, 'clock_discontinuities': clocks,
            'provider_ts_to_receipt_ms': {'n': len(lag_ms), 'min': min(lag_ms) if lag_ms else None,
                                         'max': max(lag_ms) if lag_ms else None},
            'latency_interpretation': 'provider timestamp semantics/replay unknown; NOT chain-to-app latency',
            'chain_join': 'NOT_PERFORMED', 'executable_returns': 'NOT_MEASURED'}


def report(path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        manifest_raw, end_raw = db.execute('SELECT manifest_json,end_json FROM session').fetchone()
        previous, count = '0' * 64, 0
        def frames():
            nonlocal previous, count
            for seq, wall, mono, raw, prior, hashed in db.execute('SELECT * FROM raw_frame ORDER BY sequence'):
                count += 1
                if seq != count or prior != previous or digest(previous, seq, wall, mono, raw) != hashed:
                    raise ValueError('raw chain verification failed')
                previous = hashed
                yield wall, mono, raw
        result = inspect_frames(frames())
        end = json.loads(end_raw) if end_raw else None
        if end and (end['frames'] != count or end['tail_sha256'] != previous):
            raise ValueError('closed capture tail mismatch')
        result.update(frames=count, raw_chain='EXACT_INTERNAL_REPLAY', end=end,
                      started_unix_nanos=json.loads(manifest_raw)['started_unix_nanos'])
        return result
    finally:
        db.close()


def run(path, seconds):
    if not math.isfinite(seconds) or not 1 <= seconds <= 180:
        raise ValueError('duration must be 1..180 seconds')
    if path.resolve().parent != PRIVATE.resolve() or path.exists():
        raise ValueError('new file directly under fomo_private required')
    key = get_key()
    import websocket
    # No dotenv execution, signing, subscriptions to paid endpoints, or reconnects.
    os.umask(0o077)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    with path.open('xb'):
        pass
    db = sqlite3.connect(path)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    db.executescript('''CREATE TABLE session(manifest_json TEXT,end_json TEXT);
        CREATE TABLE raw_frame(sequence INTEGER PRIMARY KEY,received_unix_nanos INTEGER,
            received_monotonic_nanos INTEGER,raw BLOB,previous_sha256 TEXT,record_sha256 TEXT);''')
    start, start_mono = time.time_ns(), time.monotonic_ns()
    db.execute('INSERT INTO session VALUES (?,NULL)', (json.dumps({
        'schema': 'fomo-alert-probe-v1', 'endpoint': ENDPOINT, 'started_unix_nanos': start,
        'started_monotonic_nanos': start_mono, 'duration_seconds': seconds,
        'max_connections': 1, 'max_raw_bytes': MAX_RAW, 'max_frame_bytes': MAX_FRAME,
        'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'purpose': 'raw schema/entitlement probe only; all chains; no outcome selection',
        'replay_policy': 'preserve all; absent replay flag means UNKNOWN',
        'coverage': 'UNKNOWN_SINGLE_VENDOR', 'orders': 'DISABLED'}),))
    db.commit()
    deadline = time.monotonic() + seconds
    ws, count, total, previous = None, 0, 0, '0' * 64
    reason, error_type = 'DURATION_COMPLETE', None
    try:
        ws = websocket.create_connection(ENDPOINT + '?key=' + quote(key, safe=''),
                                         timeout=min(10, seconds), redirect_limit=0)
        while time.monotonic() < deadline:
            ws.settimeout(min(2, max(0.001, deadline - time.monotonic())))
            try:
                raw = ws.recv()
                wall, mono = time.time_ns(), time.monotonic_ns()
            except websocket.WebSocketTimeoutException:
                continue
            if raw in ('', b''):
                reason = 'REMOTE_CLOSE'
                break
            raw = raw.encode() if isinstance(raw, str) else raw
            if key.encode() in raw or quote(key, safe='').encode() in raw:
                reason = 'SECRET_ECHO_REFUSED_UNSAVED_FRAME'
                break
            if len(raw) > MAX_FRAME or total + len(raw) > MAX_RAW:
                reason = 'CAPACITY_UNSAVED_FRAME'
                break
            hashed = digest(previous, count + 1, wall, mono, raw)
            db.execute('INSERT INTO raw_frame VALUES (?,?,?,?,?,?)',
                       (count + 1, wall, mono, raw, previous, hashed))
            db.commit()  # no decoding before raw durability
            count, total, previous = count + 1, total + len(raw), hashed
    except KeyboardInterrupt:
        reason = 'INTERRUPTED'
    except Exception as error:
        reason, error_type = 'FAILED', type(error).__name__  # URL may be in exception body
    finally:
        if ws:
            try:
                ws.close(timeout=1)
            except Exception:
                pass
        db.execute('UPDATE session SET end_json=?', (json.dumps({
            'reason': reason, 'error_type': error_type, 'frames': count, 'raw_bytes': total,
            'tail_sha256': previous, 'ended_unix_nanos': time.time_ns()}),))
        db.commit()
        db.close()
    return report(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--out', type=Path)
    choice.add_argument('--report', type=Path)
    parser.add_argument('--seconds', type=float, default=90)
    args = parser.parse_args()
    try:
        result = report(args.report) if args.report else run(args.out, args.seconds)
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(0 if not result['end'] or result['end']['reason'] == 'DURATION_COMPLETE' else 2)
    except Exception as error:
        print(json.dumps({'status': 'REFUSED_NO_TRADE', 'error_type': type(error).__name__}))
        raise SystemExit(2)
