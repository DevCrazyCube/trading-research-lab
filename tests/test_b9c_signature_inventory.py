import hashlib
import importlib.util
import json
import sqlite3
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9c", ROOT / "scripts" / "b9c_signature_inventory.py")
B9C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9C)


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B11D = _load("b11d", "b11d_cohort_adapter.py")
B11E = _load("b11e", "b11e_pipeline_dryrun.py")


def fresh_cohort(directory):
    """A real fresh cohort artifact, built by the real adapter from a real B7d enumeration.

    Deliberately not a hand-written fixture: the whole failure being regressed here is that a
    cohort produced by this exact path was measured against a pin describing a different study,
    so the artifact under test has to be one the adapter actually produces.
    """
    creates = B11E.make_enumeration(directory / "creates.sqlite")
    cohort = directory / "cohort.sqlite"
    B11D.build(creates, cohort)
    members = sqlite3.connect(f"file:{cohort}?mode=ro", uri=True)
    rows = members.execute(
        "SELECT mint,bonding_curve,launch_slot FROM outcome ORDER BY launch_slot,mint").fetchall()
    members.close()
    return Path(creates), cohort, rows


def test_classify_slot_envelope():
    assert B9C.classify({"slot": 9}, 10, 20) == "before_launch"
    assert B9C.classify({"slot": 10}, 10, 20) == "in_window"
    assert B9C.classify({"slot": 20}, 10, 20) == "in_window"
    assert B9C.classify({"slot": 21}, 10, 20) == "after_cutoff"
    assert B9C.classify({"slot": None}, 10, 20) == "unknown"


def test_normalize_preserves_error_and_coordinates():
    page = [{"signature": "sig", "slot": 15, "blockTime": 123, "err": {"x": 1},
             "memo": "m", "confirmationStatus": "finalized"}]
    row = B9C.normalize_page("curve", 2, page, 10, 20)[0]
    assert row == ("curve", "sig", 15, 123, '{"x":1}', "m", "finalized", 2, 0,
                   "in_window")


def test_normalize_missing_signature_fails_visible():
    with pytest.raises(RuntimeError, match="missing signature"):
        B9C.normalize_page("curve", 0, [{"slot": 1}], 1, 2)


def test_request_key_is_canonical():
    left = B9C.request_key("m", [{"b": 2, "a": 1}])
    right = B9C.request_key("m", [{"a": 1, "b": 2}])
    assert left == right


def test_store_raw_preserves_exact_bytes(tmp_path):
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.schema(db)
    raw = b'{"jsonrpc":"2.0","result":[ ] ,"id":1}'
    B9C.store_raw(db, "key", "method", [1], raw, "curve", 0)
    compressed, digest = db.execute(
        "SELECT raw_zlib,response_sha256 FROM raw_rpc_response").fetchone()
    assert zlib.decompress(compressed) == raw
    assert digest == hashlib.sha256(raw).hexdigest()
    db.close()


def test_schema_indexes_raw_page_coordinates(tmp_path):
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.schema(db)
    indexes = {row[1] for row in db.execute("PRAGMA index_list(signature_observation)")}
    assert "signature_observation_page_coordinate" in indexes
    db.close()


BURNED_CUTOFF = {"cutoff_time": str(B9C.CUTOFF_TIME)}


def test_initialize_matching_metadata_is_idempotent(tmp_path):
    path = tmp_path / "x.sqlite"
    members = [("mint", "curve", 10)]
    db = B9C.connect(path)
    B9C.initialize(db, "source", "hash", members, 40, BURNED_CUTOFF)
    assert dict(db.execute("SELECT key,value FROM metadata"))["cutoff_time"] == str(B9C.CUTOFF_TIME)
    before = list(db.iterdump())
    B9C.initialize(db, "source", "hash", members, 40, BURNED_CUTOFF)
    assert list(db.iterdump()) == before
    db.close()


def test_initialize_refuses_source_hash_change(tmp_path):
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.initialize(db, "source", "one", [("mint", "curve", 10)], 40, BURNED_CUTOFF)
    with pytest.raises(RuntimeError, match="source_sha256"):
        B9C.initialize(db, "source", "two", [("mint", "curve", 10)], 40, BURNED_CUTOFF)
    db.close()


def test_initialize_refuses_a_changed_horizon_on_resume(tmp_path):
    """The mismatch guard must cover the cutoff too, not only the source.

    A partial inventory resumed under a different horizon would hold pages collected under two
    different bounds with nothing in the artifact saying so. `cutoff_metadata` goes through
    `expected` precisely so this refuses, and the burned build could not have tested it because
    there was only ever one horizon to resume under.
    """
    db = B9C.connect(tmp_path / "x.sqlite")
    members = [("mint", "curve", 10)]
    B9C.initialize(db, "source", "hash", members, 40, {"cutoff_slot": "500"})
    with pytest.raises(RuntimeError, match="cutoff_slot"):
        B9C.initialize(db, "source", "hash", members, 40, {"cutoff_slot": "501"})
    db.close()


def test_initialize_in_fresh_mode_does_not_stamp_the_burned_timestamp(tmp_path):
    """The artifact must record the bound it was collected under, not the B9 one.

    Before this, `initialize` wrote `cutoff_time = CUTOFF_TIME` unconditionally, so a fresh
    collection would have carried the July B9 horizon in its metadata while actually being bounded
    by something else entirely — a provenance claim contradicted by the run that made it.
    """
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.initialize(db, "source", "hash", [("mint", "curve", 10)], 40,
                   {"cutoff_slot": "437211659", "cutoff_source": "explicit-fresh-window"})
    metadata = dict(db.execute("SELECT key,value FROM metadata"))
    assert metadata["cutoff_slot"] == "437211659"
    assert "cutoff_time" not in metadata
    db.close()


def test_resolve_cutoff_slot_returns_a_stored_horizon_without_any_call(tmp_path):
    """Fresh mode's horizon must travel by the route the module already had.

    `resolve_cutoff_slot` short-circuits on a stored `cutoff_slot`. This asserts it does so with a
    url of None and no retries budget: if it ever reached the network the arguments would raise,
    so passing proves the bisect — and with it CUTOFF_TIME — is genuinely unreachable in fresh mode
    rather than merely unlikely.
    """
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.initialize(db, "source", "hash", [("mint", "curve", 10)], 40,
                   {"cutoff_slot": "437211659", "cutoff_source": "explicit-fresh-window"})
    assert B9C.resolve_cutoff_slot(db, None, 435569160, 0) == 437211659
    db.close()


def test_preserved_request_replays_and_verifies_hash(tmp_path):
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.schema(db)
    params = [1]
    raw = json.dumps({"jsonrpc": "2.0", "id": 1, "result": 99}).encode()
    key = B9C.request_key("getBlockTime", params)
    B9C.store_raw(db, key, "getBlockTime", params, raw)
    got_key, got_raw, result, stored = B9C.preserved_request(
        db, "unused", "getBlockTime", params, 1)
    assert (got_key, got_raw, result, stored) == (key, raw, 99, True)
    db.execute("UPDATE raw_rpc_response SET response_sha256='bad'")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        B9C.preserved_request(db, "unused", "getBlockTime", params, 1)
    db.close()


def test_verify_raw_replay_detects_normalized_mismatch(tmp_path):
    db = B9C.connect(tmp_path / "x.sqlite")
    B9C.schema(db)
    db.executemany("INSERT INTO metadata VALUES (?,?)", [
        ("cutoff_slot", "20"), ("cutoff_time", str(B9C.CUTOFF_TIME))])
    db.execute("INSERT INTO curve_scan(mint,bonding_curve,launch_slot) VALUES ('m','c',10)")
    page = [{"signature": "s", "slot": 15, "blockTime": 1, "err": None,
             "memo": None, "confirmationStatus": "finalized"}]
    raw = json.dumps({"jsonrpc": "2.0", "id": 1, "result": page}).encode()
    B9C.store_raw(db, "key", "getSignaturesForAddress", ["c", {}], raw, "c", 0)
    db.executemany("INSERT INTO signature_observation VALUES (?,?,?,?,?,?,?,?,?,?)",
                   B9C.normalize_page("c", 0, page, 10, 20))
    assert B9C.verify_raw_replay(db) == (1, 1)
    db.execute("UPDATE signature_observation SET time_class='after_cutoff'")
    with pytest.raises(RuntimeError, match="normalized replay mismatch"):
        B9C.verify_raw_replay(db)
    db.close()


# ------------------------------------------------------------------------------------------------
# The burned/fresh split. B11a collected 203,601 slots over three days, built a clean 33,866-member
# cohort, and stage 4 refused it in one second against a pin describing the 1,601-curve B9 study.
# ------------------------------------------------------------------------------------------------

def test_source_mode_splits_the_burned_artifact_from_everything_else():
    assert B9C.source_mode(B9C.BURNED_SOURCE) == B9C.SOURCE_MODE_BURNED
    assert B9C.source_mode("research/b11a/b11a_cohort.sqlite") == B9C.SOURCE_MODE_FRESH


def test_a_fresh_cohort_is_not_measured_against_the_burned_pin(tmp_path):
    """The regression. This is B11a's failure, reproduced at three members instead of 33,866.

    The fixture size is asserted first and deliberately: if it ever became EXPECTED_MEMBERS this
    test would pass while proving nothing, which is the shape of vacuous pass this module's own
    history is full of.
    """
    creates, cohort, members = fresh_cohort(tmp_path)
    assert len(members) != B9C.EXPECTED_MEMBERS, "the fixture must not accidentally be the pin"
    B9C.assert_cohort(members, B9C.SOURCE_MODE_FRESH, cohort, creates)


def test_the_pin_still_refuses_a_burned_source_of_the_wrong_size():
    """Fresh mode must not have loosened burned mode. The pin is still the pin."""
    members = [("mint", "curve", 10)]
    assert len(members) != B9C.EXPECTED_MEMBERS
    with pytest.raises(SystemExit, match="pinned at"):
        B9C.assert_cohort(members, B9C.SOURCE_MODE_BURNED, B9C.BURNED_SOURCE)


@pytest.mark.parametrize("mode", [B9C.SOURCE_MODE_BURNED, B9C.SOURCE_MODE_FRESH])
def test_duplicate_bonding_curves_refuse_in_every_mode(mode):
    """Structural corruption is not a property of which study produced the artifact.

    Parametrized over both modes because this half of the original one-line guard was the half that
    had to survive, and a fresh-mode path that dropped it would look correct against B11a's data --
    which happens to be clean -- and be wrong for the next window.
    """
    members = [("mintA", "shared", 10), ("mintB", "shared", 11)]
    with pytest.raises(SystemExit, match="distinct bonding curves"):
        B9C.assert_cohort(members, mode, "any/path")


@pytest.mark.parametrize("mode", [B9C.SOURCE_MODE_BURNED, B9C.SOURCE_MODE_FRESH])
def test_an_empty_cohort_refuses_before_anything_can_pass_it_vacuously(mode):
    """Absence is refusal, and it must be checked FIRST.

    An empty population satisfies distinctness and every agreement check trivially, so if this ran
    later it would be a guard standing behind guards that had already waved the artifact through.
    """
    with pytest.raises(SystemExit, match="no members"):
        B9C.assert_cohort([], mode, "any/path")


def test_the_two_conditions_no_longer_share_one_message(tmp_path):
    """Diagnosing B11a meant opening the artifact and re-running both comparisons by hand.

    The old line raised the same text for a wrong count and for duplicate curves, so the refusal
    named neither. These assert the messages are actually different, which is the property that
    was missing rather than the fact that both refuse.
    """
    with pytest.raises(SystemExit) as wrong_count:
        B9C.assert_cohort([("m", "c", 1)], B9C.SOURCE_MODE_BURNED, B9C.BURNED_SOURCE)
    with pytest.raises(SystemExit) as duplicate:
        B9C.assert_cohort([("a", "s", 1), ("b", "s", 2)], B9C.SOURCE_MODE_BURNED, B9C.BURNED_SOURCE)
    assert str(wrong_count.value) != str(duplicate.value)
    assert "pinned at" in str(wrong_count.value)
    assert "distinct bonding curves" in str(duplicate.value)


def test_fresh_mode_refuses_when_the_create_enumeration_is_not_named(tmp_path):
    """Dropping the pin must not leave the population unchecked."""
    creates, cohort, members = fresh_cohort(tmp_path)
    with pytest.raises(SystemExit, match="--creates was not given"):
        B9C.assert_cohort(members, B9C.SOURCE_MODE_FRESH, cohort, None)


def test_fresh_mode_refuses_a_creates_artifact_the_cohort_did_not_come_from(tmp_path):
    """The binding that makes the agreement mean anything.

    Without it `--creates` could name any enumeration at all and the comparison would be between
    two unrelated windows.
    """
    creates, cohort, members = fresh_cohort(tmp_path)
    other = B11E.make_enumeration(tmp_path / "other.sqlite", start=500, end_exclusive=505)
    assert Path(other).read_bytes() != creates.read_bytes(), "the decoy must actually differ"
    with pytest.raises(SystemExit, match="records that it was built from"):
        B9C.assert_cohort(members, B9C.SOURCE_MODE_FRESH, cohort, other)


def test_fresh_mode_refuses_when_the_adapter_filtered(tmp_path):
    """What the count comparison is actually for, and the reason it survives the hash check.

    With the digest binding in place a truncated or swapped enumeration is already refused, so the
    count cannot disagree on DATA -- it can only disagree if the adapter stopped being exhaustive.
    That is reachable by a future edit rather than by a bad artifact, and it is the only thing here
    the digest does not already say, so it is tested against exactly that: a cohort that is
    internally consistent and honestly bound to its enumeration, carrying one member fewer.

    The precondition assertions matter more than the refusal. Without them a doctored artifact that
    simply failed `assert_fresh_cohort` would raise from the wrong guard and the test would pass
    for a reason that has nothing to do with filtering.
    """
    creates, cohort, members = fresh_cohort(tmp_path)
    dropped = members[-1][0]
    connection = sqlite3.connect(cohort)
    with connection:
        connection.execute("DELETE FROM cohort_identity WHERE mint=?", (dropped,))
        rows = [{"mint": m, "bonding_curve": c, "launch_slot": s, "is_mayhem_mode": g}
                for m, c, s, g in connection.execute(
                    "SELECT mint, bonding_curve, launch_slot, is_mayhem_mode FROM cohort_identity")]
        connection.execute("UPDATE metadata SET value=? WHERE key='cohort_sha256'",
                           (B11D.cohort_digest(rows),))
    connection.close()

    filtered = B11D.assert_fresh_cohort(cohort)
    assert filtered["members"] == len(members) - 1, "the doctored cohort must be one member short"
    assert filtered["source_sha256"] == hashlib.sha256(creates.read_bytes()).hexdigest(), \
        "it must still be honestly bound to its enumeration, or the digest guard fires instead"

    remaining = [row for row in members if row[0] != dropped]
    with pytest.raises(SystemExit, match="adapter never filters"):
        B9C.assert_cohort(remaining, B9C.SOURCE_MODE_FRESH, cohort, creates)


def test_fresh_mode_refuses_a_source_that_cannot_say_what_it_is(tmp_path):
    """The adapter's verification must be load-bearing, not decorative.

    Without this, every fresh-mode check downstream could be satisfied by values read straight out
    of an unverified file: the member count would agree because it came from the same rows, and the
    digest would agree because it was recomputed rather than compared. A cohort that never declares
    itself has to be refused before any of that.
    """
    creates = Path(B11E.make_enumeration(tmp_path / "creates.sqlite"))
    impostor = tmp_path / "impostor.sqlite"
    connection = sqlite3.connect(impostor)
    with connection:
        connection.executescript(
            "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            "CREATE TABLE outcome (mint TEXT, bonding_curve TEXT, launch_slot INTEGER,"
            " is_mayhem_mode INTEGER);")
        connection.execute("INSERT INTO outcome VALUES ('m','c',10,0)")
    connection.close()
    with pytest.raises(SystemExit, match="not a verified fresh cohort"):
        B9C.assert_cohort([("m", "c", 10)], B9C.SOURCE_MODE_FRESH, impostor, creates)


# ------------------------------------------------------------------------------------------------
# The four guards a mutation sweep found alive after the first round of tests above. Three of them
# sat in `main`, which no test can enter without a network, and one of those three was the fail-open
# fix itself -- the whole reason for this change, with nothing able to provoke it.
# ------------------------------------------------------------------------------------------------

def test_fresh_mode_refuses_rather_than_falling_back_to_the_burned_horizon():
    """The centrepiece. A fresh cohort with no stated horizon must stop, not inherit B9's.

    Falling back is not a harmless default: `resolve_cutoff_slot` brackets on
    `low_time <= CUTOFF_TIME < high_time`, the tip is always later than a July timestamp, so the
    only thing between a fresh window and the burned horizon is whether the window happens to start
    after it. B11a did and refused. A window starting earlier would have bracketed, bisected, and
    truncated its own collection at another study's clock silently.
    """
    with pytest.raises(SystemExit, match="--cutoff-slot was not given"):
        B9C.assert_mode_arguments(B9C.SOURCE_MODE_FRESH, "fresh/cohort.sqlite", None, "creates")


def test_a_stated_horizon_satisfies_fresh_mode():
    """The refusal above must be about the missing horizon and not about fresh mode itself."""
    assert B9C.assert_mode_arguments(
        B9C.SOURCE_MODE_FRESH, "fresh/cohort.sqlite", 437211659, "creates") is None


@pytest.mark.parametrize("cutoff_slot, creates", [(437211659, None), (None, "creates.sqlite")])
def test_the_burned_source_refuses_an_argv_override(cutoff_slot, creates):
    """The freeze may not be re-pointed from the command line.

    Parametrized over both overrides because one of them passing is enough to reopen the hole, and
    a single-argument test would have covered whichever one I happened to write.
    """
    with pytest.raises(SystemExit, match="fresh-mode only"):
        B9C.assert_mode_arguments(
            B9C.SOURCE_MODE_BURNED, B9C.BURNED_SOURCE, cutoff_slot, creates)


def test_the_burned_source_accepts_its_own_defaults():
    assert B9C.assert_mode_arguments(
        B9C.SOURCE_MODE_BURNED, B9C.BURNED_SOURCE, None, None) is None


def test_the_recorded_horizon_follows_the_mode():
    """Burned records a time, fresh records the slot it was given, and neither borrows the other."""
    burned = B9C.cutoff_metadata_for(B9C.SOURCE_MODE_BURNED, None)
    fresh = B9C.cutoff_metadata_for(B9C.SOURCE_MODE_FRESH, 437211659)
    assert burned == {"cutoff_time": str(B9C.CUTOFF_TIME)}
    assert fresh["cutoff_slot"] == "437211659"
    assert "cutoff_time" not in fresh, "a fresh artifact must not carry the B9 timestamp"
    assert str(B9C.CUTOFF_TIME) not in fresh.values()


def test_the_view_may_not_disagree_with_the_table_it_projects(tmp_path):
    """`outcome` is the consumers' contract; the count they read must be the population.

    Reachable by redefining the view, which is how it would happen for real: the adapter's digest
    and member count are both taken from `cohort_identity`, so a view that returns a subset leaves
    the artifact internally verifiable while handing every consumer a short population.
    """
    creates, cohort, members = fresh_cohort(tmp_path)
    connection = sqlite3.connect(cohort)
    with connection:
        connection.execute("DROP VIEW outcome")
        connection.execute(
            "CREATE VIEW outcome AS SELECT mint, bonding_curve, launch_slot, is_mayhem_mode "
            "FROM cohort_identity LIMIT 1")
    connection.close()

    verified = B11D.assert_fresh_cohort(cohort)
    assert verified["members"] == len(members), \
        "the table must still verify, or the adapter refuses first and this proves nothing"
    short = sqlite3.connect(f"file:{cohort}?mode=ro", uri=True)
    through_the_view = short.execute(
        "SELECT mint,bonding_curve,launch_slot FROM outcome ORDER BY launch_slot,mint").fetchall()
    short.close()
    assert len(through_the_view) < len(members), "the view must actually be short"

    with pytest.raises(SystemExit, match="no longer projects the table"):
        B9C.assert_cohort(through_the_view, B9C.SOURCE_MODE_FRESH, cohort, creates)


def test_main_actually_reaches_the_mode_gate(monkeypatch, tmp_path):
    """Extracting the gate is worth nothing if `main` does not call it.

    A sweep proved this was needed: with every guard inside `assert_mode_arguments` tested and
    killing its mutant, deleting the CALL from `main` changed no test at all -- the same defect as
    a floor that every test invoked directly and nothing wired in.

    Runnable end-to-end because the refusal lands before any filesystem or network access. The
    source path is asserted NOT to exist, which is what proves that: if the gate had moved below
    the source hashing, this would fail with FileNotFoundError instead.
    """
    source = tmp_path / "fresh_cohort.sqlite"
    assert not source.exists(), "the refusal must come before anything opens the source"
    monkeypatch.setenv("SOLANA_RPC_URL", "http://never-contacted.invalid")
    monkeypatch.setattr(sys, "argv", ["b9c", "--source", str(source),
                                      "--database", str(tmp_path / "out.sqlite")])
    with pytest.raises(SystemExit, match="--cutoff-slot was not given"):
        B9C.main()


def test_main_reaches_the_mode_gate_for_the_burned_source_too(monkeypatch, tmp_path):
    """The other half of the gate, through the real entry point.

    Deliberately does NOT assert the burned artifact is absent. The ordering claim is carried by
    the fresh test above, which owns its tmp_path and controls existence; asserting it here would
    make this fail on any checkout that legitimately has the burned corpus, reporting an
    environment as a defect.
    """
    monkeypatch.setenv("SOLANA_RPC_URL", "http://never-contacted.invalid")
    monkeypatch.setattr(sys, "argv", ["b9c", "--cutoff-slot", "437211659",
                                      "--database", str(tmp_path / "out.sqlite")])
    with pytest.raises(SystemExit, match="fresh-mode only"):
        B9C.main()
