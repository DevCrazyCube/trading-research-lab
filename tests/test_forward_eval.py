"""T19 — the forward-test evaluator, with every guardrail shown to be able to refuse.

The dangerous failures for an evaluator are not arithmetic slips. They are:

  * writing to the thing it is supposed to be reading (a ledger an evaluator can touch is a
    ledger that can be rewritten to agree with the evaluation),
  * scoring a strategy whose pre-registration has moved, i.e. against a moved goalpost,
  * reporting the EASY benchmark comparison and calling it the result,
  * emitting `certifiable: true`, or a claim, at any sample size,
  * counting a re-run session twice,
  * quietly substituting a different null when the real one is not computable.

Every test below breaks one of those. The suite is hermetic: nothing here opens a socket and
nothing writes into `research/`.
"""
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.trading_bot import forward_eval as FE          # noqa: E402
from scripts.trading_bot.frozen import Refused              # noqa: E402


def synthetic_records(n=400):
    """A deterministic ledger containing one >=20% benchmark crash. No RNG anywhere."""
    sessions = FE._synthetic_sessions(n)
    recs = []
    for i, s in enumerate(sessions):
        recs.append({
            "kind": "session", "session_date": s["date"],
            "rule": {"target": 0.10, "wmax": 1.0, "L": 60,
                     "rule_id": "T13-VOL-L60-T0.1-WMAX1.0"},
            "decision": {"realised_vol_annual": 0.10 / s["weight_in_force"],
                         "target_weight": s["weight_in_force"],
                         "cross_check": "frozen == local recomputation"},
            "account": {"equity": 100_000.0},
            "fill_reconciliation": {"reconciled": True, "status": "filled",
                                    "filled_qty": 10, "qty_ordered": 10,
                                    "shortfall_bp_adverse_positive": 0.2},
            "settled_sessions": [s] if i > 0 else [],
        })
    return recs, sessions


class TheWriteGuard(unittest.TestCase):
    """The guardrail. An evaluator that can write a ledger is not read-only."""

    def test_a_ledger_path_is_refused(self):
        with self.assertRaises(Refused):
            FE._refuse_if_protected(FE.RESEARCH / "T4_FORWARD_LOG.jsonl")

    def test_a_state_path_is_refused(self):
        with self.assertRaises(Refused):
            FE._refuse_if_protected(FE.RESEARCH / "T4_FORWARD_STATE.json")

    def test_a_preregistration_is_refused(self):
        with self.assertRaises(Refused):
            FE._refuse_if_protected(FE.RESEARCH / "T4_FORWARD_PREREGISTRATION.md")

    def test_the_authorisation_file_is_refused(self):
        with self.assertRaises(Refused):
            FE._refuse_if_protected(FE.RESEARCH / "T4_OWNER_AUTHORISATION.json")

    def test_the_register_itself_is_refused(self):
        with self.assertRaises(Refused):
            FE._refuse_if_protected(FE.RESEARCH / "FORWARD_REGISTER.json")

    def test_a_future_strategys_ledger_is_protected_before_it_exists(self):
        """Protection is by suffix, so nobody has to remember to add T20's ledger here."""
        with self.assertRaises(Refused):
            FE._refuse_if_protected(FE.RESEARCH / "T99_SOMETHING_LOG.jsonl")

    def test_an_ordinary_report_path_is_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            p = FE._write(pathlib.Path(d) / "report.json", "{}")
            self.assertTrue(p.exists())


class TheRegisterAndIntegrity(unittest.TestCase):

    def test_a_moved_preregistration_refuses_rather_than_being_scored(self):
        with tempfile.TemporaryDirectory() as d:
            prereg = pathlib.Path(d) / "P.md"
            prereg.write_text("frozen")
            entry = {"id": "X", "preregistration": str(prereg.relative_to(prereg.anchor)),
                     "preregistration_sha256": "0" * 64}
            # point at an absolute path via ROOT-joining semantics
            entry["preregistration"] = str(prereg)
            with self.assertRaises(Refused) as cm:
                FE.verify_integrity({**entry, "preregistration": str(prereg)})
            self.assertIn("not a pre-registration", str(cm.exception))

    def test_a_matching_hash_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            prereg = pathlib.Path(d) / "P.md"
            prereg.write_text("frozen")
            out = FE.verify_integrity({"id": "X", "preregistration": str(prereg),
                                       "preregistration_sha256": FE._sha256(prereg)})
            self.assertTrue(out["frozen"])

    def test_the_shipped_register_is_readable_and_its_hash_holds(self):
        reg = FE.load_register()
        entry = FE.resolve_strategy("T4", reg)
        self.assertTrue(FE.verify_integrity(entry)["frozen"])

    def test_an_unknown_strategy_refuses_rather_than_guessing(self):
        with self.assertRaises(Refused):
            FE.resolve_strategy("NOPE", FE.load_register())


class SettledSessions(unittest.TestCase):

    def test_a_re_run_session_is_counted_once(self):
        recs, sessions = synthetic_records(60)
        duplicated = recs + [{"kind": "session", "session_date": recs[-1]["session_date"],
                              "settled_sessions": recs[-1]["settled_sessions"]}]
        self.assertEqual(len(FE.settled_sessions(recs)),
                         len(FE.settled_sessions(duplicated)))

    def test_a_partial_session_record_refuses_rather_than_being_scored(self):
        bad = [{"kind": "session", "session_date": "2026-01-05",
                "settled_sessions": [{"date": "2026-01-05", "weight_in_force": 0.7}]}]
        with self.assertRaises(Refused):
            FE.settled_sessions(bad)

    def test_sessions_come_back_in_calendar_order(self):
        recs, _ = synthetic_records(40)
        out = FE.settled_sessions(list(reversed(recs)))
        self.assertEqual(out, sorted(out, key=lambda s: s["date"]))


class TheVolMatchedNull(unittest.TestCase):
    """N1 is the gate that killed both T13 families. It must actually be vol-matched."""

    @classmethod
    def setUpClass(cls):
        _, cls.sessions = synthetic_records(300)
        cls.dd = FE.drawdown_block(cls.sessions)

    def test_the_null_realises_the_strategys_own_volatility(self):
        r_f = [s["r_model_withcash"] for s in self.sessions]
        w1 = FE.match_weight(self.sessions, FE._annual_vol(r_f))
        self.assertAlmostEqual(FE._annual_vol(FE.constant_weight_curve(self.sessions, w1)),
                               FE._annual_vol(r_f), places=6)

    def test_a_ledger_without_r_index_refuses_instead_of_substituting_the_benchmark(self):
        stripped = [{k: v for k, v in s.items() if k != "r_index"} for s in self.sessions]
        with self.assertRaises(Refused):
            FE.constant_weight_curve(stripped, 0.7)

    def test_a_zero_volatility_strategy_refuses_rather_than_matching_nothing(self):
        flat = [dict(s, r_model_withcash=0.0, r_index=0.0, r_cash_accrual=0.0)
                for s in self.sessions]
        with self.assertRaises(Refused):
            FE.match_weight(flat, 0.0)

    def test_the_easy_benchmark_comparison_is_the_flattering_one(self):
        """The whole reason N1 exists. If these two ever agree, the test has lost its point."""
        easy = self.dd["vs_benchmark_DIAGNOSTIC_ONLY"]["delta_maxdd_pp"]
        honest = self.dd["vs_vol_matched_null_N1"]["delta_maxdd_pp"]
        self.assertGreater(easy, honest)

    def test_the_benchmark_comparison_is_labelled_as_not_the_answer(self):
        self.assertIn(
            "diagnostic",
            self.dd["vs_benchmark_DIAGNOSTIC_ONLY"]["why_this_is_not_the_answer"].lower())


class CrashEpisodes(unittest.TestCase):

    def test_a_twenty_percent_benchmark_decline_is_one_episode(self):
        _, sessions = synthetic_records(400)
        self.assertEqual(len(FE.crash_episodes(sessions)), 1)

    def test_a_calm_series_has_no_episodes_however_long_it_runs(self):
        sessions = [s for s in FE._synthetic_sessions(400, crash_at=10_000)]
        self.assertEqual(FE.crash_episodes(sessions), [])

    def test_no_sessions_means_no_episodes_rather_than_an_error(self):
        self.assertEqual(FE.crash_episodes([]), [])


class Certifiability(unittest.TestCase):

    def test_certifiable_is_false_at_every_sample_size(self):
        for n in (0, 60, 400):
            recs, sessions = synthetic_records(n) if n else ([], [])
            self.assertFalse(FE.certifiability_block(sessions, recs)["certifiable"])

    def test_the_binding_axis_is_crashes_not_sessions(self):
        recs, sessions = synthetic_records(400)
        self.assertEqual(FE.certifiability_block(sessions, recs)["binding_axis"],
                         "completed crash episodes")

    def test_the_power_table_reproduces_T13s_published_arithmetic(self):
        """6.00 pp / sd 6.84 / n=3 -> 5.0, 10.2, 13.7 crashes. T4 prereg §6."""
        self.assertAlmostEqual(FE._crashes_for_power(0.50), 5.0, places=1)
        self.assertAlmostEqual(FE._crashes_for_power(0.80), 10.2, places=1)
        self.assertAlmostEqual(FE._crashes_for_power(0.90), 13.7, places=1)

    def test_the_remaining_crash_count_falls_as_episodes_complete(self):
        recs, sessions = synthetic_records(400)
        block = FE.certifiability_block(sessions, recs)
        self.assertEqual(block["crash_axis"]["completed"], 1)
        self.assertEqual(block["crash_axis"]["remaining_before_any_verdict"],
                         FE.CRASHES_FOR_VERDICT - 1)

    def test_power_inputs_carry_their_own_disclaimer(self):
        recs, sessions = synthetic_records(400)
        block = FE.certifiability_block(sessions, recs)
        disc = block["power_arithmetic"]["inputs_that_are_not_results"]["DISCLAIMER"]
        self.assertIn("NOT A RESULT", disc)

    def test_a_short_sample_declines_to_estimate_moments_rather_than_guessing(self):
        recs, sessions = synthetic_records(20)
        inputs = (FE.certifiability_block(sessions, recs)
                  ["power_arithmetic"]["inputs_that_are_not_results"]["paired_excess_vs_N1"])
        self.assertFalse(inputs["computable"])


class GatesAndWithholding(unittest.TestCase):

    def test_a_p_value_is_withheld_below_a_year_of_sessions(self):
        _, sessions = synthetic_records(120)
        sig = (FE.drawdown_block(sessions)["vs_vol_matched_null_N1"]
               ["significance_half_of_FG1"])
        self.assertFalse(sig["computed"])
        self.assertIn("forbids", sig["reason"])

    def test_a_computed_p_value_still_carries_its_restriction(self):
        _, sessions = synthetic_records(400)
        sig = (FE.drawdown_block(sessions)["vs_vol_matched_null_N1"]
               ["significance_half_of_FG1"])
        self.assertTrue(sig["computed"])
        self.assertIn("NOT_LICENSED", sig)

    def test_size_alone_never_reads_as_a_pass(self):
        _, sessions = synthetic_records(400)
        n1 = FE.drawdown_block(sessions)["vs_vol_matched_null_N1"]
        self.assertIn("size_half_of_FG1_met", n1)
        self.assertIn("not the gate", n1["reminder"])

    def test_zero_fills_is_not_a_hundred_percent_fill_rate(self):
        out = FE.execution_block([])
        self.assertIsNone(out["fill_rate"])
        self.assertFalse(out["power_on_this_axis"]["computable"])

    def test_the_rule_of_three_bounds_the_non_fill_rate(self):
        out = FE._rule_of_three(300, 300)
        self.assertAlmostEqual(out["upper_95pct_bound_on_non_fill_rate"], 0.01, places=6)

    def test_a_fidelity_mismatch_invalidates_the_window(self):
        recs, sessions = synthetic_records(60)
        broken = [dict(s) for s in sessions]
        broken[-1]["weight_in_force"] = 0.123456
        out = FE.fidelity_block(recs, broken)
        self.assertTrue(out["mismatches"])
        self.assertIn("INVALIDATED", out["gate_FG3"])


class WhatTheReportMayClaim(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        recs, _ = synthetic_records(400)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ledger = pathlib.Path(cls.tmp.name) / "L.jsonl"
        cls.ledger.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        cls.rep = FE.evaluate("T4", ledger_path=cls.ledger)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_claim_is_ever_licensed(self):
        self.assertEqual(self.rep["claims_licensed"], [])

    def test_the_forbidden_claims_are_named_explicitly(self):
        joined = " ".join(self.rep["claims_explicitly_not_licensed"]).lower()
        for phrase in ("makes money", "beats buy-and-hold", "live account"):
            self.assertIn(phrase, joined)

    def test_the_status_line_leads_with_the_denominator_not_the_pnl(self):
        line = self.rep["status_line"]
        self.assertIn("settled sessions", line)
        self.assertIn("NOT CERTIFIABLE", line)
        self.assertLess(line.index("settled sessions"), line.index("realised"))

    def test_the_status_line_fits_on_one_line(self):
        self.assertLess(len(self.rep["status_line"]), 220)
        self.assertNotIn("\n", self.rep["status_line"])

    def test_no_gate_reads_as_a_pass_before_the_minimum_sample(self):
        g = self.rep["gates"]
        self.assertFalse(g["minimum_sample_met"])
        for key in ("FG1_drawdown_vs_N1", "FG2_delta_cagr_vs_N1", "FG5_dsr"):
            self.assertIn("NOT READABLE", g[key]["state"])

    def test_the_gates_that_accrue_daily_are_readable_now(self):
        g = self.rep["gates"]
        self.assertTrue(g["FG3_fidelity"]["readable_now"])
        self.assertTrue(g["FG4_execution_rail"]["readable_now"])

    def test_FG2_is_withheld_because_a_cagr_is_forbidden_not_because_it_is_hard(self):
        self.assertIn("forbids", self.rep["gates"]["FG2_delta_cagr_vs_N1"]["state"])

    def test_the_report_points_at_the_iteration_protocol(self):
        self.assertIn("ITERATION_PROTOCOL.md", self.rep["iteration_protocol"])

    def test_the_text_rendering_never_prints_a_licensed_claim(self):
        text = FE.render_text(self.rep)
        self.assertIn("NOT CERTIFIABLE", text)
        self.assertIn("DIAGNOSTIC ONLY", text)

    def test_realised_pnl_is_reported_but_never_annualised(self):
        """Annualising a short forward sample is how a log becomes a forecast.

        `cagr` DOES appear once in the rendered page -- inside the not-licensed list, where it
        belongs. This asserts on the PnL block itself, and on the machine-readable record that
        a downstream reader would actually parse.
        """
        text = FE.render_text(self.rep)
        block = text.split("-- REALISED PnL")[1].split("-- EXPOSURE PATH")[0].lower()
        for banned in ("cagr", "annualis", "per year", "/yr"):
            self.assertNotIn(banned, block)
        self.assertNotIn("cagr", json.dumps(self.rep["realised_pnl"]).lower())

    def test_the_evaluation_is_a_pure_function_of_the_ledger(self):
        again = FE.evaluate("T4", ledger_path=self.ledger)
        for key in ("elapsed", "drawdown", "hit_rate", "certifiability"):
            self.assertEqual(json.dumps(self.rep[key], sort_keys=True, default=str),
                             json.dumps(again[key], sort_keys=True, default=str))


class TheSelftest(unittest.TestCase):

    def test_the_selftest_passes_and_prints_its_own_checks(self):
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = FE._selftest()
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["problems"], [])
        self.assertTrue(out["ledger_write_refused"])
        self.assertFalse(out["certifiable"])


class TheProtocolDocument(unittest.TestCase):
    """The doc is a deliverable; a broken link in it is a broken deliverable."""

    def test_the_protocol_exists_and_names_the_one_rule(self):
        text = FE.PROTOCOL_PATH.read_text()
        self.assertIn("immutable", text)
        self.assertIn("NEW pre-registered forward test", text)

    def test_every_path_the_protocol_cites_exists(self):
        text = FE.PROTOCOL_PATH.read_text()
        for token in ("scripts/trading_bot/forward_eval.py",
                      "scripts/trading_bot/t4_eval_entrypoint.sh",
                      "research/trading_bot/FORWARD_REGISTER.json",
                      "tests/test_forward_eval.py"):
            self.assertIn(token, text)
            self.assertTrue((ROOT / token).exists(), token)

    def test_the_register_lists_T4_as_running_with_its_prior_verdict(self):
        entry = FE.resolve_strategy("T4", FE.load_register())
        self.assertEqual(entry["status"], "RUNNING")
        self.assertIn("DEAD", entry["prior_verdict"])


if __name__ == "__main__":
    unittest.main()
