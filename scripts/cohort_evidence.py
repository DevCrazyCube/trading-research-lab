"""Exact owner balance evidence and causal gates for a future cohort experiment.

Offline only: no RPC, signer, orders, prices or inference of profit. A two-asset
exchange shape is NOT authenticated DEX execution. Source receipts must be kept.
See Solana RPC JSON structures and fees docs, accessed 2026-09-09.
"""
from collections import defaultdict
from decimal import Decimal
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time


class Refused(ValueError):
    pass


def integer(value, label, maximum=2**64-1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise Refused(label)
    return value


def text(value, label):
    if not isinstance(value, str) or not value:
        raise Refused(label)
    return value


def owner_delta(tx, owner, expected_signature):
    """Net raw units across ALL owner token accounts, with native fees separate.

    Consumes a jsonParsed getTransaction result. Unknown owners/omitted balance
    metadata refuse, not zero. Missing counterpart rows mean created/closed token
    accounts only inside this returned transaction, NOT an account-history claim.
    Ownership changes are retained as attributed inventory changes, not trades.
    """
    text(owner, 'owner'); text(expected_signature, 'signature')
    if not isinstance(tx, dict) or not isinstance(tx.get('meta'), dict):
        raise Refused('transaction/meta unavailable')
    transaction = tx['transaction']; signatures = transaction['signatures']
    if not signatures or signatures[0] != expected_signature:
        raise Refused('transaction identity mismatch')
    slot = integer(tx['slot'], 'slot')
    keys = transaction['message']['accountKeys']
    if not keys or any(not isinstance(k, dict) for k in keys):
        raise Refused('jsonParsed expanded account keys required')
    addresses = [text(k.get('pubkey'), 'account key') for k in keys]
    if len(set(addresses)) != len(addresses) or keys[0].get('signer') is not True:
        raise Refused('duplicate accounts or unsigned fee payer')
    meta = tx['meta']
    if 'err' not in meta:
        raise Refused('execution status unavailable')
    before, after = meta.get('preBalances'), meta.get('postBalances')
    if not isinstance(before, list) or not isinstance(after, list) or len(before) != len(keys) or len(after) != len(keys):
        raise Refused('native balance/account mismatch')
    for amount in before + after:
        integer(amount, 'native amount')
    fee = integer(meta.get('fee'), 'fee')
    units = {}; identities = {}; sums = []
    for field in ('preTokenBalances', 'postTokenBalances'):
        rows = meta.get(field)
        if not isinstance(rows, list):
            raise Refused('token balance metadata unavailable')
        accounts = set(); total = defaultdict(int)
        for row in rows:
            index = integer(row.get('accountIndex'), 'token account index', len(keys)-1)
            if index in accounts:
                raise Refused('duplicate token account balance')
            accounts.add(index)
            holder = text(row.get('owner'), 'token owner unavailable')
            mint = text(row.get('mint'), 'mint')
            program = text(row.get('programId'), 'token program unavailable')
            value = row.get('uiTokenAmount') or {}
            decimals = integer(value.get('decimals'), 'decimals', 255)
            amount = value.get('amount')
            if not isinstance(amount, str) or not amount.isascii() or not amount.isdecimal():
                raise Refused('raw token amount required')
            raw = integer(int(amount), 'raw token amount')
            asset = (program, mint)
            if asset in units and units[asset] != decimals:
                raise Refused('inconsistent mint decimals')
            if index in identities and identities[index] != asset:
                raise Refused('account reused for different asset; instruction reconciliation required')
            identities[index] = asset; units[asset] = decimals
            if holder == owner:
                total[asset] += raw
        sums.append(total)
    pre, post = sums
    changes = [{'program_id': p, 'mint': m, 'decimals': units[(p,m)],
                'pre_raw': str(pre[(p,m)]), 'post_raw': str(post[(p,m)]),
                'delta_raw': str(post[(p,m)] - pre[(p,m)])}
               for p,m in sorted(set(pre) | set(post))]
    failed = meta['err'] is not None
    if failed and any(int(c['delta_raw']) for c in changes):
        raise Refused('failed transaction has token mutation')
    index = addresses.index(owner) if owner in addresses else None
    native = after[index] - before[index] if index is not None else None
    paid = fee if addresses[0] == owner else 0
    return {'schema': 'owner-delta-v1', 'signature': expected_signature, 'owner': owner,
            'slot': slot, 'transaction_index': None, 'instruction_index': None,
            'block_time': tx.get('blockTime'), 'execution': 'FAILED' if failed else 'SUCCESS',
            'native_delta_lamports': native, 'fee_paid_lamports': paid,
            'native_ex_fee_lamports': native + paid if native is not None else None,
            'tokens': changes, 'trade_identity': 'UNVERIFIED', 'pnl': 'NOT_COMPUTED',
            'native_caveat': 'includes rent, transfers and wrapping; not swap consideration',
            'canonical_order': 'slot known; transaction and instruction order unresolved'}


def exchange_shape(delta, quote_assets):
    """Quotes are explicit (program,mint) pairs supplied from pinned sources.

    No minimum size/transaction-count filter. Transfer + unrelated payment can
    have this same shape; require venue/instruction reconciliation before buying.
    Native SOL is deliberately not classified from a rent-confounded delta.
    """
    if delta['execution'] != 'SUCCESS':
        return {'status': 'FAILED_TRANSACTION', 'buy_proven': False}
    changed = [v for v in delta['tokens'] if int(v['delta_raw']) != 0]
    spent = [v for v in changed if int(v['delta_raw']) < 0]
    gained = [v for v in changed if int(v['delta_raw']) > 0]
    if (len(changed) == 2 and len(spent) == len(gained) == 1
            and (spent[0]['program_id'], spent[0]['mint']) in quote_assets
            and (gained[0]['program_id'], gained[0]['mint']) not in quote_assets):
        return {'status': 'QUOTE_EXCHANGE_CANDIDATE', 'buy_proven': False,
                'received': gained[0], 'spent': spent[0]}
    return {'status': 'UNRESOLVED_FLOW_NOT_BUY', 'buy_proven': False}


def causal_gate(roster_available_ns, rule_frozen_ns, feature_available_ns, entry_open_ns):
    for v in (roster_available_ns, rule_frozen_ns, feature_available_ns, entry_open_ns):
        integer(v, 'time')
    if not max(roster_available_ns, rule_frozen_ns) <= feature_available_ns < entry_open_ns:
        raise Refused('roster/rule/feature not available before entry')


def balanced_rosters(board, controls, seed):
    """Fixed equal-sized sampling, never ranked/filtered by later returns.

    Equal size fixes opportunity-count bias only. It is NOT proof of matched
    activity, funding independence, or representative random-wallet controls.
    """
    if len(set(board)) != len(board) or len(set(controls)) != len(controls):
        raise Refused('duplicate roster wallet')
    if set(board) & set(controls):
        raise Refused('control overlaps leaderboard')
    if not controls or len(board) < len(controls):
        raise Refused('empty control or undersized board')
    for wallet in board + controls:
        text(wallet, 'wallet')
    text(seed, 'sampling seed')
    sample = sorted(board,key=lambda w:(hashlib.sha256((seed+'\0'+w).encode()).hexdigest(),w))[:len(controls)]
    return {'board': sorted(sample), 'controls': sorted(controls)}


def freeze_roster(root, out):
    """Save a fresh NO_TRADE identity manifest, not a financial preregistration."""
    private = (root/'fomo_private').resolve()
    if out.resolve().parent != private or out.exists():
        raise Refused('new output directly under private evidence required')
    paths = {'board':root/'leaderboard_7d_20260909.json','controls':root/'cohort_controls_20260909.json'}
    data = {k:p.read_bytes() for k,p in paths.items()}
    decoded = {k:json.loads(raw) for k,raw in data.items()}
    wallets = {k:[r['wallets']['solana'] for r in j['traders'] if r.get('wallets',{}).get('solana')]
               for k,j in decoded.items()}
    pins = {k:hashlib.sha256(raw).hexdigest() for k,raw in data.items()}
    seed = 'cohort-forward-roster-v1:'+pins['board']+':'+pins['controls']
    sample = balanced_rosters(wallets['board'],wallets['controls'],seed)
    now = time.time_ns()
    result = {'schema':'cohort-forward-roster-v1','status':'NO_TRADE_ROSTER_ONLY',
              'local_freeze_wall_ns':now,'local_freeze_mono_ns':time.monotonic_ns(),
              'source_hashes':pins,'source_paths':{k:str(p) for k,p in paths.items()},
              'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'rosters':sample,'seed':seed,'selection':'SHA256 sample of current board; equal arm counts',
              'earlier_outcomes':'DEVELOPMENT_ONLY_NOT_HOLDOUT',
              'control_activity_matching':'UNPROVEN','funding_independence':'UNPROVEN',
              'rule_freeze':'NOT_DONE; no entry/exit rule authorized',
              'identity':'VENDOR_MAPPING; not independent ownership authentication'}
    os.umask(0o077);out.mkdir()
    encoded=json.dumps(result,sort_keys=True,separators=(',',':')).encode()
    with (out/'roster.json').open('xb') as stream:
        stream.write(encoded);stream.flush();os.fsync(stream.fileno())
    return {'status':result['status'],'path':str(out),'board_wallets':len(sample['board']),
            'control_wallets':len(sample['controls']),'local_freeze_wall_ns':now,
            'roster_sha256':hashlib.sha256(encoded).hexdigest()}


def chart_sensitivity(events, dropout):
    """All-signal-denominator diagnostic; NOT executable PnL or a promotion test.

    Input one row per chain/mint per horizon. Missing entries and exits stay in
    denominator under each owner's dropout stress. Zero really is a resolved
    full loss; it must never be mistaken for missing. No implicit fee defaults.
    """
    if dropout not in (Decimal('-.30'), Decimal('-.50'), Decimal('-1')):
        raise Refused('owner dropout scenario required')
    seen = set(); returns = []; resolved = 0; missing_entry = 0; missing_exit = 0
    for e in events:
        identity = (e['chain'], e['mint'])
        if identity in seen:
            raise Refused('duplicate mint/overlap')
        seen.add(identity)
        p0, p1 = e['entry_open'], e['exit_open']
        if p0 is None:
            missing_entry += 1; returns.append(dropout); continue
        if not isinstance(p0, Decimal) or not p0.is_finite() or p0 <= 0:
            raise Refused('invalid entry')
        if p1 is None:
            missing_exit += 1; returns.append(dropout); continue
        if not isinstance(p1, Decimal) or not p1.is_finite() or p1 < 0:
            raise Refused('invalid exit')
        cost = e['roundtrip_fraction']
        if not isinstance(cost, Decimal) or not cost.is_finite() or not 0 <= cost < 1:
            raise Refused('explicit cost scenario required')
        returns.append((p1/p0)*(1-cost)-1); resolved += 1
    n = len(returns); ordered = sorted(returns)
    median = ((ordered[(n-1)//2] + ordered[n//2])/2) if n else None
    return {'status': 'CHART_SENSITIVITY_NOT_EXECUTABLE_PNL', 'signals': n,
            'resolved': resolved, 'missing_entry': missing_entry, 'missing_exit': missing_exit,
            'resolution_rate': Decimal(resolved)/n if n else None,
            'mean': sum(returns)/n if n else None, 'median': median, 'dropout': dropout}


def audit_history(path, roster, roster_time):
    db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)
    try:
        columns = [r[1] for r in db.execute('PRAGMA table_info(row)')]
        n, wallets, signatures, mints, start, end = db.execute(
            'SELECT count(*),count(distinct wallet),count(distinct sig),count(distinct mint),min(ts),max(ts) FROM row').fetchone()
        done = db.execute('SELECT count(*) FROM done').fetchone()[0]
        historical = db.execute('SELECT count(*) FROM row WHERE ts<?', (roster_time,)).fetchone()[0]
        quote_conflicts = db.execute('SELECT count(*) FROM (SELECT wallet,sig FROM row GROUP BY wallet,sig HAVING min(sol)!=max(sol))').fetchone()[0]
    finally:
        db.close()
    return {'path': str(path), 'rows': n, 'wallets_with_rows': wallets, 'signature_count': signatures,
            'mint_count': mints, 'roster_size': len(roster), 'marked_done': done,
            'earliest_row': start, 'latest_row': end, 'rows_before_roster_snapshot': historical,
            'per_transaction_sol_conflicts': quote_conflicts, 'columns': columns,
            'raw_rpc_preserved_in_this_database': False,
            'verdict': 'DEVELOPMENT_ONLY_NO_CAUSAL_PROFIT_TEST',
            'completeness': 'UNPROVEN; done table does not track failures, pages or cap stops'}


if __name__ == '__main__':
    from datetime import datetime
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('research/midcap'))
    parser.add_argument('--freeze-roster', type=Path)
    args = parser.parse_args(); root = args.root
    if args.freeze_roster:
        print(json.dumps(freeze_roster(root,args.freeze_roster),sort_keys=True))
        raise SystemExit(0)
    board_path = root/'leaderboard_7d_20260909.json'
    board = json.loads(board_path.read_bytes())
    stamp = datetime.fromisoformat(board['capturedAt'].replace('Z','+00:00')).timestamp()
    control = json.loads((root/'cohort_controls_20260909.json').read_bytes())
    result = {'status': 'NO_TRADE', 'leaderboard_reported_capture': board['capturedAt'],
              'leaderboard_sha256': hashlib.sha256(board_path.read_bytes()).hexdigest(), 'arms': {}}
    for name, members in [('cohort_history',board['traders']), ('cohort_history_controls',control['traders'])]:
        roster = {r['wallets']['solana'] for r in members if r.get('wallets',{}).get('solana')}
        result['arms'][name] = audit_history(root/(name+'.sqlite'),roster,stamp)
    print(json.dumps(result, sort_keys=True))
