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


# ------------------------------------------------------------------------------------------------
# A subsample is a DRAW, not a smaller cohort. The full-cohort rule -- members == enumerated -- is
# false by construction for one, and relaxing it to members <= enumerated would check nothing.
# ------------------------------------------------------------------------------------------------

B11F = _load("b11f", "b11f_cohort_subsample.py")


def subsampled(directory, n=2):
    """A real subsample artifact, built by the real selector from a real enumeration."""
    creates = Path(B11E.make_enumeration(directory / "creates.sqlite"))
    parent = directory / "cohort.sqlite"
    B11D.build(creates, parent)
    child = directory / "subsample.sqlite"
    B11F.build_subsample(parent, child, n=n)
    connection = sqlite3.connect(f"file:{child}?mode=ro", uri=True)
    rows = connection.execute(
        "SELECT mint,bonding_curve,launch_slot FROM outcome ORDER BY launch_slot,mint").fetchall()
    connection.close()
    return creates, child, rows


def test_a_subsample_is_accepted_although_it_is_smaller_than_its_enumeration(tmp_path):
    """The regression for a defect I would have shipped into a five-day collection.

    The full-cohort check asserts the member count EQUALS the create count. A draw of N from a
    larger population fails that by construction, so my own guard would have refused the very
    subsample the preregistration exists to produce -- on the first run, after the supersede.
    """
    creates, child, members = subsampled(tmp_path, n=2)
    enumerated = sqlite3.connect(f"file:{creates}?mode=ro", uri=True)
    total = enumerated.execute("SELECT COUNT(*) FROM create_event").fetchone()[0]
    enumerated.close()
    assert len(members) < total, "the fixture must actually be a strict subset, or this proves nothing"
    B9C.assert_cohort(members, B9C.SOURCE_MODE_FRESH, child, creates)


def test_a_subsample_that_is_not_the_frozen_draw_is_refused(tmp_path):
    """The check that replaces the count, and the reason it is stronger than a bound.

    Swapping one selected curve for one the rule did not select keeps the size, the population and
    the declared N all correct -- every arithmetic property a bound would test still holds. Only
    re-running the selection catches it.
    """
    creates, child, members = subsampled(tmp_path, n=2)
    enumerated = sqlite3.connect(f"file:{creates}?mode=ro", uri=True)
    all_mints = [r[0] for r in enumerated.execute("SELECT mint FROM create_event")]
    enumerated.close()
    chosen = {m[0] for m in members}
    outsider = next(m for m in all_mints if m not in chosen)

    connection = sqlite3.connect(child)
    with connection:
        connection.execute("DELETE FROM cohort_identity WHERE mint=?", (members[-1][0],))
        connection.execute(
            "INSERT INTO cohort_identity(mint,bonding_curve,launch_slot,is_mayhem_mode,"
            "create_signature) VALUES (?,?,?,?,?)", (outsider, "curveX", 999, 0, "sigX"))
        # RESEAL. Without this the adapter's digest guard fires first and this test passes on a
        # refusal that has nothing to do with the draw -- proving the swap is detectable, which was
        # never in question, instead of proving the selection check detects it.
        rows = [{"mint": m, "bonding_curve": c, "launch_slot": s, "is_mayhem_mode": g}
                for m, c, s, g in connection.execute(
                    "SELECT mint, bonding_curve, launch_slot, is_mayhem_mode FROM cohort_identity")]
        connection.execute("UPDATE metadata SET value=? WHERE key='cohort_sha256'",
                           (B11D.cohort_digest(rows),))
    tampered = connection.execute(
        "SELECT mint,bonding_curve,launch_slot FROM outcome ORDER BY launch_slot,mint").fetchall()
    connection.close()
    assert len(tampered) == len(members), "the swap must preserve the count, or a bound would catch it"
    # The preconditions that make this test about the SELECTION and nothing else: the artifact still
    # verifies as a sealed fresh cohort, and still declares the right population and N.
    B11D.assert_fresh_cohort(child)
    declared = B9C.source_metadata(child)
    assert int(declared["subsample_n"]) == len(tampered)
    assert outsider in {row[0] for row in tampered}, "the outsider must actually be present"

    with pytest.raises(SystemExit, match="not the draw the frozen rule makes"):
        B9C.assert_cohort(tampered, B9C.SOURCE_MODE_FRESH, child, creates)


def test_a_subsample_drawn_under_a_different_seed_is_refused(tmp_path):
    """The seed is preregistered. A draw under another one is a different study."""
    creates = Path(B11E.make_enumeration(tmp_path / "creates.sqlite"))
    parent = tmp_path / "cohort.sqlite"
    B11D.build(creates, parent)
    child = tmp_path / "other_seed.sqlite"
    B11F.build_subsample(parent, child, seed="not-the-frozen-seed", n=2)
    connection = sqlite3.connect(f"file:{child}?mode=ro", uri=True)
    rows = connection.execute(
        "SELECT mint,bonding_curve,launch_slot FROM outcome ORDER BY launch_slot,mint").fetchall()
    connection.close()
    # It records the seed it used, so the recompute uses that seed too and AGREES -- the artifact is
    # internally honest. What must not happen is silence about which seed produced it.
    B9C.assert_cohort(rows, B9C.SOURCE_MODE_FRESH, child, creates)
    assert B9C.source_metadata(child)["subsample_seed"] == "not-the-frozen-seed", \
        "the artifact must record the seed it was actually drawn with"


def test_a_subsample_that_hides_its_parent_population_is_refused(tmp_path):
    """The never-filters guarantee has to survive the draw, on the number the artifact records."""
    creates, child, members = subsampled(tmp_path, n=2)
    connection = sqlite3.connect(child)
    with connection:
        connection.execute("UPDATE metadata SET value='999' WHERE key='subsample_population'")
    connection.close()
    with pytest.raises(SystemExit, match="drawn from a population of"):
        B9C.assert_cohort(members, B9C.SOURCE_MODE_FRESH, child, creates)


def test_a_subsample_that_misdeclares_its_size_is_refused(tmp_path):
    creates, child, members = subsampled(tmp_path, n=2)
    connection = sqlite3.connect(child)
    with connection:
        connection.execute("UPDATE metadata SET value='7' WHERE key='subsample_n'")
    connection.close()
    with pytest.raises(SystemExit, match="declares N=7"):
        B9C.assert_cohort(members, B9C.SOURCE_MODE_FRESH, child, creates)


def test_a_subsample_that_silently_drops_selected_curves_is_refused(tmp_path):
    """Why the check is equality and not a subset test, which is the weaker thing to write.

    A partial write, an interrupted build or a well-meaning filter leaves an artifact holding SOME
    of the drawn curves. With its N corrected to match, every arithmetic property still holds -- the
    population agrees, the size agrees, the digest reseals -- and only re-running the draw notices
    that the curves retained are not the ones the rule selects.

    Note what this test does NOT prove, because I first wrote it believing it did: it does not
    distinguish equality from a subset test. Correcting N forces |present| == n, and the n smallest
    keys are then the only set of that size the rule can produce, so subset and equality coincide
    for anything reaching that line. That equivalence is declared in the sweep, and it is coupled to
    the size check running FIRST.
    """
    creates, child, members = subsampled(tmp_path, n=3)
    dropped = members[-1][0]
    connection = sqlite3.connect(child)
    with connection:
        connection.execute("DELETE FROM cohort_identity WHERE mint=?", (dropped,))
        rows = [{"mint": m, "bonding_curve": c, "launch_slot": s, "is_mayhem_mode": g}
                for m, c, s, g in connection.execute(
                    "SELECT mint, bonding_curve, launch_slot, is_mayhem_mode FROM cohort_identity")]
        connection.execute("UPDATE metadata SET value=? WHERE key='cohort_sha256'",
                           (B11D.cohort_digest(rows),))
        connection.execute("UPDATE metadata SET value=? WHERE key='subsample_n'", (str(len(rows)),))
    remaining = connection.execute(
        "SELECT mint,bonding_curve,launch_slot FROM outcome ORDER BY launch_slot,mint").fetchall()
    connection.close()

    B11D.assert_fresh_cohort(child)
    present = {row[0] for row in remaining}
    original = {row[0] for row in members}
    assert present < original, "the fixture must be a STRICT subset, or it proves nothing"
    assert int(B9C.source_metadata(child)["subsample_n"]) == len(remaining), \
        "N must agree, so the size guard cannot be what refuses"

    with pytest.raises(SystemExit, match="not the draw the frozen rule makes"):
        B9C.assert_cohort(remaining, B9C.SOURCE_MODE_FRESH, child, creates)


def test_a_subsample_with_no_declared_population_is_refused(tmp_path):
    """Absence is refusal. A draw that cannot name what it drew from is not auditable."""
    creates, child, members = subsampled(tmp_path, n=2)
    connection = sqlite3.connect(child)
    with connection:
        connection.execute("DELETE FROM metadata WHERE key='subsample_population'")
    connection.close()
    with pytest.raises(SystemExit, match="records no parent population"):
        B9C.assert_cohort(members, B9C.SOURCE_MODE_FRESH, child, creates)


@pytest.mark.parametrize("key", ["subsample_seed", "subsample_n"])
def test_a_subsample_that_will_not_state_its_draw_is_refused(tmp_path, key):
    """Both halves, because a draw missing either one cannot be re-run and so cannot be checked."""
    creates, child, members = subsampled(tmp_path, n=2)
    connection = sqlite3.connect(child)
    with connection:
        connection.execute("DELETE FROM metadata WHERE key=?", (key,))
    connection.close()
    with pytest.raises(SystemExit, match="not the seed and N it was"):
        B9C.assert_cohort(members, B9C.SOURCE_MODE_FRESH, child, creates)


# ------------------------------------------------------------------------------------------------
# Sealing. A WAL checkpoint after a consumer records a byte hash is what refused a completed
# 12 GB collection at the decode gate, with every row cryptographically intact.
# ------------------------------------------------------------------------------------------------

def wal_database(path, rows=64):
    """A database with a GENUINELY un-checkpointed WAL, like an artifact mid-write.

    The returned connection is left OPEN on purpose. Closing the last connection checkpoints and
    removes the WAL, so a fixture that closes has nothing left to seal -- the seal test would then
    pass while exercising nothing. The precondition assertion below caught exactly that.
    """
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.execute("CREATE TABLE observation (id INTEGER PRIMARY KEY, payload TEXT)")
    with connection:
        connection.executemany("INSERT INTO observation(payload) VALUES (?)",
                               [(f"row-{i}" * 40,) for i in range(rows)])
    return path, connection


def test_sealing_leaves_no_sidecars_behind(tmp_path):
    """The -wal and -shm are what carried this failure; after sealing they must not exist."""
    path, holder = wal_database(tmp_path / "artifact.sqlite")
    assert Path(str(path) + "-wal").stat().st_size > 0, \
        "the fixture must carry an un-checkpointed WAL, or sealing it proves nothing"
    holder.close()
    B9C.seal_artifact(path)
    for sidecar in ("-wal", "-shm"):
        leftover = Path(str(path) + sidecar)
        assert not (leftover.exists() and leftover.stat().st_size), \
            f"{sidecar} still carries content after sealing"


def test_a_sealed_artifact_does_not_change_when_it_is_read(tmp_path):
    """The property the whole seal exists for.

    Before this, opening the database could fold the WAL into the main file and move its sha256 --
    identical content, different hash -- and a downstream consumer that pinned the byte hash then
    refused. This asserts the bytes survive repeated reading, including a read that does NOT
    promise immutability, which is the exact mistake the dashboard made.
    """
    path, holder = wal_database(tmp_path / "artifact.sqlite")
    holder.close()
    sealed = B9C.seal_artifact(path)
    for _ in range(3):
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.execute("SELECT COUNT(*) FROM observation").fetchone()
        connection.close()
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sealed, \
        "reading a sealed artifact must not move its bytes"


def test_the_returned_hash_is_the_hash_of_the_sealed_file(tmp_path):
    path, holder = wal_database(tmp_path / "artifact.sqlite")
    holder.close()
    sealed = B9C.seal_artifact(path)
    assert sealed == hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_sealing_is_idempotent(tmp_path):
    """A second seal must not move the bytes either, or re-sealing would defeat the point."""
    path, holder = wal_database(tmp_path / "artifact.sqlite")
    holder.close()
    first = B9C.seal_artifact(path)
    assert B9C.seal_artifact(path) == first


def test_the_content_survives_sealing(tmp_path):
    path, holder = wal_database(tmp_path / "artifact.sqlite", rows=128)
    holder.close()
    B9C.seal_artifact(path)
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT COUNT(*) FROM observation").fetchone()[0] == 128
    finally:
        connection.close()


def test_a_writer_still_holding_the_wal_is_refused_not_sealed(tmp_path):
    """A partial drain is the state nobody could reconcile afterwards; sealing it would preserve
    the ambiguity inside an artifact everything downstream trusts."""
    path, holder = wal_database(tmp_path / "artifact.sqlite")
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("INSERT INTO observation(payload) VALUES ('uncommitted')")
    try:
        with pytest.raises(Exception) as caught:
            B9C.seal_artifact(path)
        assert "REFUSING to seal" in str(caught.value)
    finally:
        holder.rollback()
        holder.close()


# ------------------------------------------------------------------------------------------------
# The content digest: the contract b9d verifies against. It answers "is this the same EVIDENCE",
# which is the question a byte hash of a live SQLite file cannot answer.
# ------------------------------------------------------------------------------------------------

def observation_db(path, rows):
    """rows: (curve, signature, slot, page_index, row_index). Minimal but real column set."""
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE signature_observation (
            bonding_curve TEXT, signature TEXT, slot INTEGER, block_time INTEGER,
            err_json TEXT, memo TEXT, confirmation_status TEXT,
            page_index INTEGER, row_index INTEGER, time_class TEXT);
    """)
    with connection:
        connection.executemany(
            "INSERT INTO signature_observation VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(c, s, sl, 1, "null", None, "finalized", p, r, "in_window")
             for c, s, sl, p, r in rows])
    return connection


def test_the_content_digest_is_stable_across_insertion_order(tmp_path):
    """Two builds of the same evidence must agree, whatever order the rows were written in."""
    rows = [("curveA", "sig1", 10, 0, 0), ("curveA", "sig2", 11, 0, 1),
            ("curveB", "sig3", 12, 0, 0)]
    first = observation_db(tmp_path / "a.sqlite", rows)
    second = observation_db(tmp_path / "b.sqlite", list(reversed(rows)))
    try:
        assert B9C.content_digest(first)[0] == B9C.content_digest(second)[0]
    finally:
        first.close(); second.close()


def test_the_content_digest_changes_when_a_value_changes(tmp_path):
    """Non-vacuous: a digest that never moves would verify nothing."""
    base = [("curveA", "sig1", 10, 0, 0)]
    first = observation_db(tmp_path / "a.sqlite", base)
    second = observation_db(tmp_path / "b.sqlite", [("curveA", "sig1", 11, 0, 0)])
    try:
        assert B9C.content_digest(first)[0] != B9C.content_digest(second)[0]
    finally:
        first.close(); second.close()


def test_a_null_and_an_empty_string_do_not_collide(tmp_path):
    """NULL is a distinct byte, not an absent field. Otherwise a missing memo and an empty memo
    hash identically and the digest cannot tell them apart."""
    connection = observation_db(tmp_path / "a.sqlite", [("c", "s", 1, 0, 0)])
    other = observation_db(tmp_path / "b.sqlite", [("c", "s", 1, 0, 0)])
    try:
        with other:
            other.execute("UPDATE signature_observation SET memo=''")
        assert B9C.content_digest(connection)[0] != B9C.content_digest(other)[0]
    finally:
        connection.close(); other.close()


def test_adjacent_fields_cannot_be_shifted_into_each_other(tmp_path):
    """Without a field separator, ('ab','c') and ('a','bc') hash the same."""
    first = observation_db(tmp_path / "a.sqlite", [("ab", "c", 1, 0, 0)])
    second = observation_db(tmp_path / "b.sqlite", [("a", "bc", 1, 0, 0)])
    try:
        assert B9C.content_digest(first)[0] != B9C.content_digest(second)[0]
    finally:
        first.close(); second.close()


def test_a_float_in_a_row_is_refused_not_hashed(tmp_path):
    """A float's rendering is a formatting decision; a digest must not depend on one."""
    connection = observation_db(tmp_path / "a.sqlite", [("c", "s", 1, 0, 0)])
    try:
        with connection:
            connection.execute("UPDATE signature_observation SET slot=1.5")
        with pytest.raises(Exception) as caught:
            B9C.content_digest(connection)
        assert "float" in str(caught.value)
    finally:
        connection.close()


def test_the_digest_reports_the_row_count_it_covered(tmp_path):
    connection = observation_db(tmp_path / "a.sqlite",
                                [("c", f"s{i}", i, 0, i) for i in range(7)])
    try:
        assert B9C.content_digest(connection)[1] == 7
    finally:
        connection.close()
