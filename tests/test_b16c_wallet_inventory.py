"""B16c guards. Synthetic `meta` payloads; no burned artifact, no network.

The guard that matters most is the one that already caught a real defect: `accountIndex` is an index
into ONE transaction's account keys, not a stable identifier for a token account. Treating it as an
identity split a single account into three and inverted the holding verdict for 101 positions.
"""
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B16C = load("b16c_wallet_inventory", "b16c_wallet_inventory.py")

OWNER = "Owner11111111111111111111111111111111111111"
OTHER = "Owner22222222222222222222222222222222222222"
MINT = "Mint111111111111111111111111111111111111111"


def balance(index, owner=OWNER, mint=MINT, amount="100", decimals=6,
            program="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"):
    return {"accountIndex": index, "owner": owner, "mint": mint, "programId": program,
            "uiTokenAmount": {"amount": amount, "decimals": decimals,
                              "uiAmount": None, "uiAmountString": amount}}


def meta(pre, post, err=None):
    return {"err": err, "preTokenBalances": pre, "postTokenBalances": post}


def observation(owner, mint, slot, transaction_index, before, after, account_index=0):
    return {"owner": owner, "mint": mint, "slot": slot, "transaction_index": transaction_index,
            "amount_before": before, "amount_after": after, "account_index": account_index,
            "account_created": before == 0, "account_closed": after == 0,
            "decimals": 6, "program_id": B16C.TOKEN_PROGRAMS[0], "signature": "sig"}


class TestBalanceChanges(unittest.TestCase):
    def test_a_created_account_has_a_zero_before(self):
        changes = B16C.transaction_balance_changes(meta([], [balance(4, amount="500")]))
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["amount_before"], 0)
        self.assertEqual(changes[0]["amount_after"], 500)
        self.assertTrue(changes[0]["account_created"])

    def test_a_closed_account_has_a_zero_after(self):
        changes = B16C.transaction_balance_changes(meta([balance(4, amount="500")], []))
        self.assertEqual(changes[0]["amount_before"], 500)
        self.assertEqual(changes[0]["amount_after"], 0)
        self.assertTrue(changes[0]["account_closed"])

    def test_pre_and_post_are_paired_by_account_index_not_by_owner(self):
        """One owner, two accounts of one mint: they must not be netted into each other."""
        changes = B16C.transaction_balance_changes(meta(
            [balance(2, amount="100"), balance(5, amount="300")],
            [balance(2, amount="0"), balance(5, amount="400")]))
        by_index = {c["account_index"]: c for c in changes}
        self.assertEqual((by_index[2]["amount_before"], by_index[2]["amount_after"]), (100, 0))
        self.assertEqual((by_index[5]["amount_before"], by_index[5]["amount_after"]), (300, 400))

    def test_an_account_that_changes_owner_within_a_transaction_is_refused(self):
        with self.assertRaisesRegex(B16C.InventoryRefused, "changed owner"):
            B16C.transaction_balance_changes(meta(
                [balance(3, owner=OWNER)], [balance(3, owner=OTHER)]))

    def test_an_account_that_changes_mint_is_refused(self):
        with self.assertRaisesRegex(B16C.InventoryRefused, "changed mint"):
            B16C.transaction_balance_changes(meta(
                [balance(3, mint=MINT)], [balance(3, mint="OtherMint")]))

    def test_an_entry_missing_a_required_field_is_refused_not_defaulted(self):
        for field in ("owner", "mint", "accountIndex"):
            with self.subTest(field=field):
                entry = balance(1)
                del entry[field]
                with self.assertRaisesRegex(B16C.InventoryRefused, field):
                    B16C.transaction_balance_changes(meta([entry], []))

    def test_a_missing_amount_or_decimals_is_refused(self):
        for field in ("amount", "decimals"):
            with self.subTest(field=field):
                entry = balance(1)
                del entry["uiTokenAmount"][field]
                with self.assertRaisesRegex(B16C.InventoryRefused, field):
                    B16C.transaction_balance_changes(meta([entry], []))

    def test_the_exact_integer_amount_is_used_not_the_ui_amount(self):
        """uiAmount is a float and would lose precision on large balances."""
        changes = B16C.transaction_balance_changes(
            meta([], [balance(0, amount="903550561855907")]))
        self.assertEqual(changes[0]["amount_after"], 903550561855907)
        self.assertIsInstance(changes[0]["amount_after"], int)


class TestReconciliation(unittest.TestCase):
    """The defect this suite exists for: accountIndex is not an account identity."""

    def test_one_account_seen_at_three_different_indexes_is_one_account(self):
        rows = [observation(OWNER, MINT, 100, 1, 0, 35, account_index=4),
                observation(OWNER, MINT, 200, 2, 35, 70, account_index=2),
                observation(OWNER, MINT, 300, 3, 70, 0, account_index=3)]
        summary = B16C.reconcile(rows)[(OWNER, MINT)]
        self.assertEqual(summary["final_amount"], 0,
                         "the wallet ended flat; indexes 4, 2 and 3 are the same account")
        self.assertEqual(summary["observations"], 3)
        self.assertEqual(summary["uncollected_gaps"], 0)

    def test_the_final_amount_is_the_last_observation_not_a_sum(self):
        rows = [observation(OWNER, MINT, 100, 1, 0, 500),
                observation(OWNER, MINT, 200, 1, 500, 900)]
        self.assertEqual(B16C.reconcile(rows)[(OWNER, MINT)]["final_amount"], 900)

    def test_two_accounts_in_one_transaction_are_summed_for_that_transaction(self):
        rows = [observation(OWNER, MINT, 100, 1, 0, 500, account_index=1),
                observation(OWNER, MINT, 100, 1, 0, 300, account_index=2)]
        summary = B16C.reconcile(rows)[(OWNER, MINT)]
        self.assertEqual(summary["final_amount"], 800)
        self.assertEqual(summary["max_accounts_in_one_transaction"], 2)

    def test_a_break_in_the_chain_is_counted_as_an_uncollected_gap(self):
        """Where the earlier `after` is not the later `before`, something moved unseen."""
        rows = [observation(OWNER, MINT, 100, 1, 0, 500),
                observation(OWNER, MINT, 200, 1, 320, 0)]
        summary = B16C.reconcile(rows)[(OWNER, MINT)]
        self.assertEqual(summary["uncollected_gaps"], 1)
        self.assertEqual(summary["uncollected_gap_amount"], 180)

    def test_a_chaining_series_reports_no_gap(self):
        rows = [observation(OWNER, MINT, 100, 1, 0, 500),
                observation(OWNER, MINT, 200, 1, 500, 250),
                observation(OWNER, MINT, 300, 1, 250, 0)]
        self.assertEqual(B16C.reconcile(rows)[(OWNER, MINT)]["uncollected_gaps"], 0)

    def test_observations_are_ordered_canonically_not_by_insertion(self):
        rows = [observation(OWNER, MINT, 300, 1, 250, 0),
                observation(OWNER, MINT, 100, 1, 0, 500),
                observation(OWNER, MINT, 200, 1, 500, 250)]
        summary = B16C.reconcile(rows)[(OWNER, MINT)]
        self.assertEqual(summary["final_amount"], 0)
        self.assertEqual(summary["uncollected_gaps"], 0)

    def test_transaction_index_breaks_ties_within_a_slot(self):
        rows = [observation(OWNER, MINT, 100, 9, 500, 0),
                observation(OWNER, MINT, 100, 2, 0, 500)]
        summary = B16C.reconcile(rows)[(OWNER, MINT)]
        self.assertEqual(summary["final_amount"], 0)
        self.assertEqual(summary["uncollected_gaps"], 0)

    def test_different_owners_are_never_merged(self):
        rows = [observation(OWNER, MINT, 100, 1, 0, 500),
                observation(OTHER, MINT, 200, 1, 0, 700)]
        summary = B16C.reconcile(rows)
        self.assertEqual(summary[(OWNER, MINT)]["final_amount"], 500)
        self.assertEqual(summary[(OTHER, MINT)]["final_amount"], 700)

    def test_different_mints_for_one_owner_are_never_merged(self):
        rows = [observation(OWNER, MINT, 100, 1, 0, 500),
                observation(OWNER, "OtherMint", 200, 1, 0, 700)]
        summary = B16C.reconcile(rows)
        self.assertEqual(summary[(OWNER, MINT)]["final_amount"], 500)
        self.assertEqual(summary[(OWNER, "OtherMint")]["final_amount"], 700)


class TestPositionReassessment(unittest.TestCase):
    def position(self, wallet=OWNER, curve="Curve", unresolved=True):
        return {"wallet": wallet, "bonding_curve": curve, "archetype": "immediate_launch_sniper",
                "inventory_unresolved": unresolved, "observed_quote_flow_lamports": 1_000,
                "quote_in_lamports": 10_000, "quote_out_lamports": 11_000}

    def test_a_zero_final_balance_reads_as_flat(self):
        result = B16C.reassess_positions(
            [self.position()], {"Curve": {"mint": MINT}},
            {(OWNER, MINT): {"final_amount": 0, "uncollected_gaps": 0, "observations": 2}})
        self.assertEqual(result[0]["inventory_status"], "flat_at_last_observation")

    def test_a_positive_final_balance_reads_as_still_holding(self):
        result = B16C.reassess_positions(
            [self.position()], {"Curve": {"mint": MINT}},
            {(OWNER, MINT): {"final_amount": 42, "uncollected_gaps": 0, "observations": 2}})
        self.assertEqual(result[0]["inventory_status"], "still_holding_at_last_observation")

    def test_absent_balance_evidence_is_not_treated_as_zero(self):
        """The failure this avoids: reporting a wallet flat because nothing was seen."""
        result = B16C.reassess_positions(
            [self.position()], {"Curve": {"mint": MINT}}, {})
        self.assertEqual(result[0]["inventory_status"], "no_balance_evidence")
        self.assertIsNone(result[0]["final_amount"])

    def test_a_curve_with_no_recorded_mint_is_reported_as_such(self):
        result = B16C.reassess_positions(
            [self.position()], {"Curve": {"mint": None}}, {})
        self.assertEqual(result[0]["inventory_status"], "no_mint_recorded")

    def test_the_trade_derived_verdict_is_preserved_for_comparison(self):
        result = B16C.reassess_positions(
            [self.position(unresolved=True)], {"Curve": {"mint": MINT}},
            {(OWNER, MINT): {"final_amount": 0, "uncollected_gaps": 0, "observations": 1}})
        self.assertTrue(result[0]["trade_derived_unresolved"])
        self.assertEqual(result[0]["inventory_status"], "flat_at_last_observation")


class TestObservationIntake(unittest.TestCase):
    """Drives the reader itself, which the pure-function tests above never reach."""

    def setUp(self):
        import shutil
        import sqlite3
        import tempfile
        import zlib
        self.zlib = zlib
        self.sqlite3 = sqlite3
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b16c-io-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.path = self.directory / "b9d.sqlite"
        con = sqlite3.connect(self.path)
        con.executescript("""
            CREATE TABLE raw_transaction (signature TEXT, method TEXT, params_json TEXT,
                received_at_unix REAL, response_sha256 TEXT, raw_zlib BLOB);
            CREATE TABLE transaction_coordinate (signature TEXT, slot INTEGER,
                transaction_index INTEGER);
        """)
        con.commit()
        con.close()

    def add(self, signature, body, slot=100, transaction_index=0, with_coordinate=True):
        con = self.sqlite3.connect(self.path)
        con.execute("INSERT INTO raw_transaction VALUES (?,?,?,?,?,?)",
                    (signature, "getTransaction", "[]", 0.0, "x",
                     self.zlib.compress(json.dumps(body).encode())))
        if with_coordinate:
            con.execute("INSERT INTO transaction_coordinate VALUES (?,?,?)",
                        (signature, slot, transaction_index))
        con.commit()
        con.close()

    def test_a_successful_transaction_yields_observations(self):
        self.add("ok", {"result": {"meta": meta([], [balance(0, amount="500")])}})
        rows, census = B16C.observations(self.path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(census["transactions_used"], 1)
        self.assertEqual(rows[0]["amount_after"], 500)

    def test_a_failed_transaction_is_excluded_and_counted(self):
        """A failed transaction moved no tokens; including it would add phantom observations."""
        self.add("bad", {"result": {"meta": meta([], [balance(0, amount="500")],
                                                 err={"InstructionError": [0, "X"]})}})
        rows, census = B16C.observations(self.path)
        self.assertEqual(rows, [])
        self.assertEqual(census["failed_transaction_excluded"], 1)
        self.assertNotIn("transactions_used", census)

    def test_a_transaction_without_balance_arrays_is_excluded_and_counted(self):
        self.add("nb", {"result": {"meta": {"err": None}}})
        rows, census = B16C.observations(self.path)
        self.assertEqual(rows, [])
        self.assertEqual(census["no_token_balance_arrays"], 1)

    def test_a_transaction_without_a_canonical_coordinate_is_excluded(self):
        self.add("nc", {"result": {"meta": meta([], [balance(0)])}}, with_coordinate=False)
        rows, census = B16C.observations(self.path)
        self.assertEqual(rows, [])
        self.assertEqual(census["no_canonical_coordinate"], 1)

    def test_an_ambiguous_owner_change_is_refused_and_counted(self):
        self.add("amb", {"result": {"meta": meta([balance(1, owner=OWNER)],
                                                 [balance(1, owner=OTHER)])}})
        rows, census = B16C.observations(self.path)
        self.assertEqual(rows, [])
        self.assertEqual(census["refused_ambiguous_account"], 1)

    def test_rows_come_back_in_canonical_order(self):
        self.add("b", {"result": {"meta": meta([], [balance(0, amount="2")])}},
                 slot=200, transaction_index=1)
        self.add("a", {"result": {"meta": meta([], [balance(0, amount="1")])}},
                 slot=100, transaction_index=9)
        rows, _census = B16C.observations(self.path)
        self.assertEqual([(r["slot"], r["transaction_index"]) for r in rows],
                         [(100, 9), (200, 1)])


class TestClaimsNotMade(unittest.TestCase):
    def test_the_module_decodes_no_token_instruction_layout(self):
        source = (ROOT / "scripts" / "b16c_wallet_inventory.py").read_text()
        for banned in ("discriminator", "struct.unpack", "borsh", "instruction_layout"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)

    def test_the_module_states_that_flat_means_at_the_last_observation(self):
        source = (ROOT / "scripts" / "b16c_wallet_inventory.py").read_text()
        self.assertIn("not for all time", source)

    def test_no_reported_quantity_is_labelled_profit(self):
        source = (ROOT / "scripts" / "b16c_wallet_inventory.py").read_text()
        for banned in ('"profit_', "def profit", "pnl", "roi"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)

    def test_shared_ownership_is_never_inferred(self):
        """The word may appear in the disclaimer -- that is where it belongs. What must not exist
        is code that DOES it, so this reads the AST rather than the text."""
        import ast
        source = (ROOT / "scripts" / "b16c_wallet_inventory.py").read_text()
        self.assertIn("never inferred", source)
        tree = ast.parse(source)
        defined = {node.name for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in defined:
            with self.subTest(name=name):
                lowered = name.lower()
                for banned in ("cluster", "same_owner", "link"):
                    self.assertNotIn(banned, lowered)
        assigned = {target.id for node in ast.walk(tree)
                    if isinstance(node, ast.Assign)
                    for target in node.targets if isinstance(target, ast.Name)}
        for name in assigned:
            with self.subTest(name=name):
                self.assertNotIn("cluster", name.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
