import copy
from decimal import Decimal as D
import unittest
from scripts.cohort_evidence import owner_delta, exchange_shape, causal_gate, chart_sensitivity, balanced_rosters, Refused


def balance(index, mint, amount, owner='owner', decimals=6):
    return {'accountIndex':index,'mint':mint,'owner':owner,'programId':'token-program',
            'uiTokenAmount':{'amount':str(amount),'decimals':decimals,'uiAmount':None}}


def tx():
    return {'slot':100,'blockTime':1234,'transaction':{'signatures':['signature'],
            'message':{'accountKeys':[{'pubkey':v,'signer':i==0} for i,v in enumerate(['payer','owner','ata1','ata2','quote'])]}},
            'meta':{'err':None,'fee':5000,'preBalances':[10000,9000000,0,0,0],
                    'postBalances':[5000,9000000,0,0,0],
                    'preTokenBalances':[balance(2,'meme',10),balance(3,'meme',20),balance(4,'quote',100)],
                    'postTokenBalances':[balance(2,'meme',40),balance(3,'meme',50),balance(4,'quote',80)]}}


def decode(t=None, owner='owner'):
    return owner_delta(t or tx(),owner,'signature')


class Tests(unittest.TestCase):
    def test_all_accounts_summed_no_ui_amount_needed(self):
        d=decode(); m=next(v for v in d['tokens'] if v['mint']=='meme')
        self.assertEqual((m['pre_raw'],m['post_raw'],m['delta_raw']),('30','90','60'))
    def test_nonpayer_not_credited_fee(self):
        d=decode();self.assertEqual(d['fee_paid_lamports'],0);self.assertEqual(d['native_ex_fee_lamports'],0)
    def test_actual_fee_payer_separate(self):
        d=decode(owner='payer');self.assertEqual(d['native_delta_lamports'],-5000);self.assertEqual(d['native_ex_fee_lamports'],0)
    def test_large_raw_units_exact(self):
        t=tx();t['meta']['postTokenBalances'][0]['uiTokenAmount']['amount']=str(2**63+1)
        d=decode(t);self.assertEqual(int(d['tokens'][0]['delta_raw']),2**63+21)
    def test_internal_transfer_is_not_buy(self):
        t=tx();t['meta']['postTokenBalances']=[balance(2,'meme',0),balance(3,'meme',30),balance(4,'quote',100)]
        self.assertEqual(exchange_shape(decode(t),{('token-program','quote')})['status'],'UNRESOLVED_FLOW_NOT_BUY')
    def test_exchange_shape_not_authenticated_trade(self):
        r=exchange_shape(decode(),{('token-program','quote')})
        self.assertEqual(r['status'],'QUOTE_EXCHANGE_CANDIDATE');self.assertFalse(r['buy_proven'])
    def test_airdrop_is_not_buy(self):
        t=tx();t['meta']['postTokenBalances'][2]=balance(4,'quote',100)
        self.assertEqual(exchange_shape(decode(t),{('token-program','quote')})['status'],'UNRESOLVED_FLOW_NOT_BUY')
    def test_missing_metadata_is_not_zero(self):
        t=tx();del t['meta']['preTokenBalances']
        with self.assertRaises(Refused):decode(t)
    def test_unknown_owner_not_assumed(self):
        t=tx();del t['meta']['postTokenBalances'][0]['owner']
        with self.assertRaises(Refused):decode(t)
    def test_duplicate_account_refused(self):
        t=tx();t['meta']['preTokenBalances'].append(copy.deepcopy(t['meta']['preTokenBalances'][0]))
        with self.assertRaises(Refused):decode(t)
    def test_decimal_mismatch_refused(self):
        t=tx();t['meta']['postTokenBalances'][0]['uiTokenAmount']['decimals']=9
        with self.assertRaises(Refused):decode(t)
    def test_wrong_signature_refused(self):
        with self.assertRaises(Refused):owner_delta(tx(),'owner','other')
    def test_failure_token_mutation_refused(self):
        t=tx();t['meta']['err']={'InstructionError':[0,'error']}
        with self.assertRaises(Refused):decode(t)
    def test_failure_preserves_fee(self):
        t=tx();t['meta']['err']='error';t['meta']['postTokenBalances']=t['meta']['preTokenBalances']
        d=decode(t,owner='payer');self.assertEqual(d['execution'],'FAILED');self.assertEqual(d['fee_paid_lamports'],5000)
    def test_raw_versioned_keys_refused(self):
        t=tx();t['transaction']['message']['accountKeys']=['payer']
        with self.assertRaises(Refused):decode(t)
    def test_causal_roster_required(self):
        causal_gate(10,11,12,13)
        for args in [(13,11,12,14),(10,13,12,14),(10,11,12,12)]:
            with self.assertRaises(Refused):causal_gate(*args)
    def test_missing_entries_retained_all_stresses(self):
        rows=[{'chain':'s','mint':'a','entry_open':None,'exit_open':None},
              {'chain':'s','mint':'b','entry_open':D(1),'exit_open':None},
              {'chain':'s','mint':'c','entry_open':D(1),'exit_open':D(0),'roundtrip_fraction':D('.0114')}]
        for loss in [D('-.3'),D('-.5'),D('-1')]:
            r=chart_sensitivity(rows,loss)
            self.assertEqual((r['signals'],r['resolved'],r['missing_entry'],r['missing_exit']),(3,1,1,1))
            self.assertEqual(r['mean'],(2*loss-1)/3)
    def test_roundtrip_not_charged_twice(self):
        row={'chain':'s','mint':'a','entry_open':D(1),'exit_open':D(1),'roundtrip_fraction':D('.0114')}
        r=chart_sensitivity([row],D('-1'));self.assertEqual(r['mean'],D('-.0114'))
    def test_even_median_and_mint_equal(self):
        rows=[{'chain':'s','mint':str(i),'entry_open':D(1),'exit_open':D(i),'roundtrip_fraction':D(0)} for i in [0,2]]
        self.assertEqual(chart_sensitivity(rows,D('-1'))['median'],D(0))
    def test_duplicate_mint_refused(self):
        row={'chain':'s','mint':'a','entry_open':None,'exit_open':None}
        with self.assertRaises(Refused):chart_sensitivity([row,row],D('-1'))
    def test_equal_arm_size_and_order_invariant(self):
        first=balanced_rosters(['a','b','c'],['d','e'],'fixed')
        self.assertEqual(first,balanced_rosters(['c','b','a'],['e','d'],'fixed'))
        self.assertEqual(len(first['board']),len(first['controls']))
    def test_no_overlapping_or_duplicate_wallets(self):
        for b,c in [(['a','b'],['b']),(['a','a'],['c']),(['a'],['b','b'])]:
            with self.assertRaises(Refused):balanced_rosters(b,c,'fixed')
    def test_no_empty_control(self):
        with self.assertRaises(Refused):balanced_rosters(['a'],[],'fixed')


if __name__=='__main__':unittest.main()
