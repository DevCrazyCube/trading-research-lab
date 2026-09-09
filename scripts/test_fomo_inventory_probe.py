import unittest
from scripts.fomo_inventory_probe import bracket,selector


class Tests(unittest.TestCase):
    def test_repeated_seconds_bracket(self):
        def fetch(n):return {'number':hex(n),'timestamp':hex(n//4)}
        lo,hi=bracket(fetch,100,10)
        self.assertEqual(int(lo['number'],16),39);self.assertEqual(int(hi['number'],16),40)
    def test_target_outside_refused(self):
        with self.assertRaises(ValueError):bracket(lambda n:{'number':hex(n),'timestamp':hex(n)},100,200)
    def test_wrong_block_refused(self):
        def fetch(n):return {'number':hex(n if n in [0,100] else n+1),'timestamp':hex(n)}
        with self.assertRaises(ValueError):bracket(fetch,100,40)
    def test_erc20_selectors(self):
        self.assertEqual(selector('balanceOf(address)'),'70a08231')
        self.assertEqual(selector('decimals()'),'313ce567')


if __name__=='__main__':unittest.main()
