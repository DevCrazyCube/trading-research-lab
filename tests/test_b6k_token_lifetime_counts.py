import base64
import importlib.util
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "b6k_token_lifetime_counts.py"
SPEC = importlib.util.spec_from_file_location("b6k", SCRIPT)
B6K = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B6K)


class CreateEventDecodeTests(unittest.TestCase):
    def test_create_event_mint_uses_idl_field_order(self):
        mint = bytes(range(32))
        strings = b"".join(len(value).to_bytes(4, "little") + value
                           for value in (b"name", b"SYM", b"https://example.invalid"))
        payload = B6K.CREATE_DISC + strings + mint + bytes(128)
        tx = {"meta": {"logMessages": [
            "Program data: " + base64.b64encode(payload).decode()
        ]}}
        self.assertEqual(B6K.create_mints(tx), {B6K.base58(mint)})

    def test_trade_event_is_not_a_launch(self):
        trade_disc = B6K.hashlib.sha256(b"event:TradeEvent").digest()[:8]
        tx = {"meta": {"logMessages": [
            "Program data: " + base64.b64encode(trade_disc + bytes(200)).decode()
        ]}}
        self.assertEqual(B6K.create_mints(tx), set())


if __name__ == "__main__":
    unittest.main()
