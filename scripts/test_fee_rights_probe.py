"""Engineering fixtures only: no economic evidence, requests, or wallet identities."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import fee_rights_probe as p


def b58(raw):
    n=int.from_bytes(raw,'big');s=''
    while n:n,r=divmod(n,58);s=p.ALPHABET[r]+s
    return '1'*(len(raw)-len(raw.lstrip(b'\0')))+s


def fixture(lock=False,inner=False):
    ac=['fixture-account-'+str(i) for i in range(19 if lock else 18)]
    data=(p.LOCK if lock else p.COLLECT)+(2**63+1).to_bytes(8,'little')+(b'\1' if lock else b'')
    ins={'programId':'fixture-program','accounts':ac,'data':b58(data)}
    b={'accountIndex':5 if lock else 2,'mint':ac[4] if lock else 'fixture-nft',
       'owner':ac[3] if lock else ac[1],'uiTokenAmount':{'decimals':0,'amount':'1'}}
    return {'slot':100,'transaction':{'signatures':['fixture-signature'],'message':{
        'accountKeys':[{'pubkey':x} for x in ac],
        'instructions':[{'programId':'other'}] if inner else [ins]}},'meta':{
        'err':None,'preTokenBalances':[] if lock else [copy.deepcopy(b)],'postTokenBalances':[b],
        'innerInstructions':[{'index':0,'instructions':[ins]}] if inner else []}}


class DecodeTests(unittest.TestCase):
    def test_base58(self):
        for raw in [b'',b'\0',b'\0\0',bytes(range(256))]:self.assertEqual(p.unbase58(b58(raw)),raw)
        for bad in ['0','O',None,'x'*4097]:
            with self.assertRaises(ValueError):p.unbase58(bad)

    def test_collect_exact_u64(self):
        rows,issues=p.claims(fixture(),'fixture-signature','fixture-program')
        self.assertFalse(issues);self.assertEqual(rows[0]['requested_lp_fee_units'],str(2**63+1))
        self.assertIsNone(rows[0]['transaction_index']);self.assertIsNone(rows[0]['inner_index'])

    def test_inner_order_coordinate(self):
        rows,_=p.claims(fixture(inner=True),'fixture-signature','fixture-program')
        self.assertEqual((rows[0]['outer_index'],rows[0]['inner_index']),(0,0))

    def test_collect_not_creator_or_unknown_claim(self):
        tx=fixture();tx['transaction']['message']['instructions'][0]['data']=b58(b'unknown!'+b'\0'*8)
        rows,issues=p.claims(tx,'fixture-signature','fixture-program')
        self.assertFalse(rows);self.assertTrue(issues[0].startswith('OTHER_LOCK_INSTRUCTION:'))

    def test_layout_refused(self):
        tx=fixture();tx['transaction']['message']['instructions'][0]['accounts'].pop()
        with self.assertRaisesRegex(ValueError,'layout'):p.claims(tx,'fixture-signature','fixture-program')

    def test_owner_refused(self):
        tx=fixture();tx['meta']['postTokenBalances'][0]['owner']='not-owner'
        with self.assertRaisesRegex(ValueError,'owner'):p.claims(tx,'fixture-signature','fixture-program')

    def test_missing_and_failed_not_claims(self):
        self.assertEqual(p.claims(None,'s','p'),([],['TRANSACTION_UNAVAILABLE']))
        tx=fixture();tx['meta']['err']={'InstructionError':[0,'test']}
        self.assertEqual(p.claims(tx,'fixture-signature','fixture-program'),([],['FAILED_TRANSACTION']))

    def test_signature_binding(self):
        for fn in [p.claims,p.issued_keys]:
            with self.assertRaisesRegex(ValueError,'signature'):fn(fixture(),'different','fixture-program')

    def test_lock_mint_and_pool(self):
        for inner in [True,False]:
            rows,issues=p.issued_keys(fixture(lock=True,inner=inner),'fixture-signature','fixture-program')
            self.assertFalse(issues);self.assertEqual(rows[0]['nft_mint'],'fixture-account-4')
            self.assertEqual(rows[0]['lock_pda'],'fixture-account-7')
            self.assertNotIn('claimable',rows[0])

    def test_lock_requires_unique_nft_account(self):
        tx=fixture(lock=True);tx['meta']['postTokenBalances']*=2
        with self.assertRaisesRegex(ValueError,'unresolved'):p.issued_keys(tx,'fixture-signature','fixture-program')

    def test_lock_amount_and_mint(self):
        for field,value in [('mint','wrong'),('owner','wrong')]:
            tx=fixture(lock=True);tx['meta']['postTokenBalances'][0][field]=value
            with self.assertRaises(ValueError):p.issued_keys(tx,'fixture-signature','fixture-program')
        tx=fixture(lock=True);tx['meta']['postTokenBalances'][0]['uiTokenAmount']['amount']='2'
        with self.assertRaises(ValueError):p.issued_keys(tx,'fixture-signature','fixture-program')

    def test_saved_hash_and_http_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix=Path(tmp)/'001';raw=b'{"result":null}'
            prefix.with_suffix('.body').write_bytes(raw)
            m={'sha256':hashlib.sha256(raw).hexdigest(),'http_status':200}
            prefix.with_suffix('.json').write_text(json.dumps(m))
            self.assertEqual(p.checked_body(prefix)[1],raw)
            prefix.with_suffix('.body').write_bytes(raw+b' ')
            with self.assertRaisesRegex(ValueError,'hash/status'):p.checked_body(prefix)

    def test_requests_cannot_submit_or_escape_allowlist(self):
        c=object.__new__(p.Capture);c.count=0
        with patch.object(p.requests,'request') as request:
            for url in ['https://evil.test',p.ME+'x/listings',p.FEE_INFO+'../../x']:
                with self.assertRaisesRegex(ValueError,'target'):c.request(url)
            for method in ['sendTransaction','simulateTransaction','requestAirdrop']:
                with self.assertRaisesRegex(ValueError,'method'):c.rpc(method,[])
            request.assert_not_called()

    def test_budget_stops_before_request(self):
        c=object.__new__(p.Capture);c.count=32
        with patch.object(p.requests,'request') as request:
            with self.assertRaisesRegex(ValueError,'budget'):c.request(p.RPC)
            request.assert_not_called()


if __name__=='__main__':unittest.main()
