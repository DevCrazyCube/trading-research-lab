"""B19 strategy-preregistration register — slice D of the B17c gap map (G5).

Holds the canonical hash of every strategy preregistration in the B19 group and refuses if one
has changed. A preregistration whose text can be edited after the fact is not a preregistration,
so the pin lives in code and the check is mechanical rather than a promise in prose.

WHY THE HASH IS OVER A CANONICAL SERIALIZATION AND NOT THE FILE BYTES: reformatting a JSON
document — reindenting, reordering keys — must not read as tampering, and changing a frozen VALUE
must. `json.dumps(..., sort_keys=True, separators=(",", ":"))` is exactly that distinction. It is
the same rule B16d used and the same one `b18a` uses for the frozen measurement contract. A reader
re-checking with `sha256sum` on the raw file will get a different digest; that is expected.

BOTH DIGESTS ARE RECORDED BELOW, AND THE EXPLANATION LIVES HERE RATHER THAN IN THE DOCUMENTS.
That placement is load-bearing, not stylistic: a note added to a pinned document would add a key,
which changes its canonical hash, which breaks the pin the note was meant to explain. The same
suggestion was made against the frozen B17b contract in handoff 197 and would have made every
B17b record unwritable; it is recorded here so the next person to have the idea sees why not.
`file_sha256` is the raw-bytes digest, checked by a test rather than by `verify`, so that
reformatting a document fails loudly instead of silently invalidating the reference value while
`verify` keeps tolerating it.

WHY A STRUCTURAL CHECK SITS BESIDE THE HASH: a pin proves a document did not change. It says
nothing about whether the document ever contained the disciplines this project depends on. A new
preregistration added to the register with no disclosure block, no prohibitions or a permissive
status lock would be pinned just as firmly as a good one. `assert_conforms` is what makes the
register a standard rather than a filing cabinet.

Nothing here runs a study, reads an artifact, opens a socket or evaluates anything.
"""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"

# Every strategy preregistration in the B19 group, with the canonical hash frozen at commit time.
# Adding an entry here without its document conforming is refused by assert_conforms.
REGISTER = {
    "B19B_EXIT_TIMING_POLICY_V1": {
        "filename": "B19B_EXIT_TIMING_POLICY_PREREGISTRATION.json",
        "canonical_sha256": "80017c689b69d986263920cfad20fdbf61fb1b29cf33f876c0fd917525bac6e7",
        "file_sha256": "1046b61ce7f93c31e481d4c403b40bda6b0cf5a9204969b106bd3f3a1659b2aa",
        "question": "does the choice of exit coordinate change the executable outcome at all",
    },
    "B19C_CAPACITY_WALL_SIZE_DEPENDENCE_V1": {
        "filename": "B19C_CAPACITY_WALL_SIZE_DEPENDENCE_PREREGISTRATION.json",
        "canonical_sha256": "519102ba451da9c8556ce321c992312ddbeb5f9b7ab99d3dd9bfa10f976b76fe",
        "file_sha256": "9a5e1d7f112aec810bb09b9e9ad7e8ba8e0a08fe3245dfd6f8d4fd0bb3d15ae3",
        "question": "above the frozen ceiling, is external-liquidity capacity a cliff or a slope",
    },
    "B19D_NON_ISSUANCE_SIGNAL_V1": {
        "filename": "B19D_NON_ISSUANCE_SIGNAL_PREREGISTRATION.json",
        "canonical_sha256": "768524effaaf4a013deb80ee5879e98b31729fef39bccbbe16270cdfd05b4b59",
        "file_sha256": "621e27a0a5b8cd241ad02b4b483141d0379b875d6d3fcc687f1714b69b251fdd",
        "question": "does any non-issuance signal survive complete costs and the capacity gate",
    },
}

# Required of every document in the group. Each exists because its absence would let a document
# read as disciplined while being permissive.
REQUIRED_BLOCKS = ("question", "known_at_authorship_time", "prohibitions", "refusal_codes",
                   "status_locks")

REQUIRED_STATUS_LOCKS = {
    "executable": False,
    "performance_status": "not_evaluated",
    "execution_status": "never_executed",
}


class PreregistrationRefused(RuntimeError):
    """The register cannot vouch for this document, so it vouches for nothing.

    Deliberately not a warning and not a boolean. A caller that wanted to proceed anyway would
    have to catch this and say so in its own code, which is visible in review.
    """


def canonical_sha256(document):
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _float_paths(value, path="$"):
    """Every location holding a float. The house rule is exact integers; JSON hides the violation.

    Returned as paths rather than a count because "there is a float somewhere in a 200-line
    document" is not an actionable message.
    """
    found = []
    if isinstance(value, float):
        found.append(path)
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(_float_paths(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_float_paths(item, f"{path}[{index}]"))
    return found


def assert_conforms(document, prereg_id):
    """The disciplines every B19 preregistration must carry, checked rather than assumed."""
    if not isinstance(document, dict):
        raise PreregistrationRefused(
            f"{prereg_id}: a preregistration must be a JSON object, got "
            f"{type(document).__name__}")

    stated = document.get("preregistration_id")
    if stated != prereg_id:
        raise PreregistrationRefused(
            f"the register calls this {prereg_id} but the document calls itself {stated!r}; a "
            "document that does not know its own identity cannot be cited by it")

    missing = [block for block in REQUIRED_BLOCKS if block not in document]
    if missing:
        raise PreregistrationRefused(
            f"{prereg_id} does not state {missing}. An absent discipline is not a satisfied one")

    status = document.get("status")
    if not isinstance(status, str) or not status.startswith("FROZEN"):
        raise PreregistrationRefused(
            f"{prereg_id} status is {status!r}; a preregistration that is not frozen is a draft, "
            "and a draft may not be cited as a commitment made in advance")

    locks = document["status_locks"]
    if not isinstance(locks, dict):
        raise PreregistrationRefused(f"{prereg_id} status_locks must be an object")
    for field, required in REQUIRED_STATUS_LOCKS.items():
        if field not in locks:
            raise PreregistrationRefused(
                f"{prereg_id} status_locks does not state {field}; an unstated lock is not an "
                "engaged one")
        if locks[field] != required:
            raise PreregistrationRefused(
                f"{prereg_id} status_locks {field} is {locks[field]!r}, must be {required!r}. "
                "Nothing in this group has been executed or evaluated")

    # The disclosure block is what lets a later reader audit the fit instead of trusting an
    # assurance, and the B11 line is the one that matters: these were written before it landed.
    disclosure = document["known_at_authorship_time"]
    if not isinstance(disclosure, dict) or "b11" not in disclosure:
        raise PreregistrationRefused(
            f"{prereg_id} known_at_authorship_time must state what was known about b11 at "
            "authorship; without it the document cannot be distinguished from a postregistration")

    for block, label in (("prohibitions", "prohibition"), ("refusal_codes", "refusal code")):
        entries = document[block]
        if not isinstance(entries, list) or not entries:
            raise PreregistrationRefused(
                f"{prereg_id} states no {label}. An empty {block} list is not a permissive "
                "default, it is a document that forgot to say what it refuses")

    for entry in document["refusal_codes"]:
        if not isinstance(entry, dict) or "code" not in entry or "meaning" not in entry:
            raise PreregistrationRefused(
                f"{prereg_id} has a refusal code without both a code and a meaning: {entry!r}")

    floats = _float_paths(document)
    if floats:
        raise PreregistrationRefused(
            f"{prereg_id} carries a float at {floats}; every quantity in this project is an exact "
            "integer or an exact rational pair")

    return document


def verify(prereg_id, path=None):
    """Load one preregistration, refusing unless it is both pinned and conforming."""
    entry = REGISTER.get(prereg_id)
    if entry is None:
        raise PreregistrationRefused(
            f"{prereg_id!r} is not in the B19 register. An unregistered preregistration is not "
            "vouched for by absence")

    document_path = pathlib.Path(path) if path is not None else RESEARCH / entry["filename"]
    if not document_path.is_file():
        raise PreregistrationRefused(
            f"{prereg_id} is registered but {document_path} is absent; a missing preregistration "
            "refuses rather than defaulting to unpinned")

    document = json.loads(document_path.read_bytes())
    actual = canonical_sha256(document)
    if actual != entry["canonical_sha256"]:
        raise PreregistrationRefused(
            f"{prereg_id} hashes {actual}, pinned {entry['canonical_sha256']}. The document has "
            "changed since it was frozen")

    return assert_conforms(document, prereg_id)


def verify_all():
    """Every registered preregistration, in register order. Returns id -> document."""
    return {prereg_id: verify(prereg_id) for prereg_id in REGISTER}


if __name__ == "__main__":
    for prereg_id, document in verify_all().items():
        print(f"{prereg_id}: verified — {document['question'][:72]}")
