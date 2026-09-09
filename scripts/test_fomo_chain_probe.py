import unittest
import gzip
from unittest.mock import patch
from scripts.fomo_chain_probe import TRANSFER,transfer,validate_logs,address,decode_http


def event():
    return {'address':'0x'+'1'*40,'topics':[TRANSFER,'0x'+'0'*24+'2'*40,'0x'+'0'*24+'3'*40],
            'data':'0x'+f'{7:064x}','removed':False,'blockNumber':'0xa',
            'blockHash':'0x'+'4'*64,'transactionHash':'0x'+'5'*64,'transactionIndex':'0x0','logIndex':'0x1'}


class Tests(unittest.TestCase):
    def test_transfer_exact_integer_roles(self):
        r=transfer(event());self.assertEqual(r['amount'],7);self.assertEqual(r['from'],'0x'+'2'*40)
    def test_wrong_signature_not_transfer(self):
        e=event();e['topics'][0]='0x'+'f'*64;self.assertIsNone(transfer(e))
    def test_nft_not_erc20(self):
        e=event();e['topics'].append('0x'+'6'*64);self.assertIsNone(transfer(e))
    def test_address_padding_refused(self):
        e=event();e['topics'][1]='0x'+'f'*64
        with self.assertRaises(ValueError):transfer(e)
    def test_removed_or_missing_state_refused(self):
        for value in [None,True]:
            e=event();e['removed']=value
            with self.assertRaises(ValueError):transfer(e)
    def test_duplicate_or_out_of_range_refused(self):
        e=event()
        with self.assertRaises(ValueError):validate_logs([e,e],10,10)
        with self.assertRaises(ValueError):validate_logs([e],11,12)
    def test_valid_range(self):self.assertEqual(len(validate_logs([event()],9,11)),1)
    def test_no_display_symbol_as_address(self):
        with self.assertRaises(ValueError):address('ANON')
    def test_gzip_rpc_response(self):
        raw=b'{"jsonrpc":"2.0","id":1,"result":"0x1237"}'
        self.assertEqual(decode_http(gzip.compress(raw),'gzip'),raw)
    def test_compression_bomb_refused(self):
        with patch('scripts.fomo_chain_probe.MAX_HTTP',10):
            with self.assertRaises(ValueError):decode_http(gzip.compress(b'a'*100),'gzip')
    def test_incomplete_compression_refused(self):
        with self.assertRaises(ValueError):decode_http(gzip.compress(b'{}')[:-2],'gzip')
    def test_unknown_encoding_refused(self):
        with self.assertRaises(ValueError):decode_http(b'{}','mystery')


if __name__=='__main__':unittest.main()
