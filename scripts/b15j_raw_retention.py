"""B15j — sealed, compressed, replayable raw segments, and a disk reserve that protects B11a.

Implements `research/B15J_RAW_RETENTION_PREREGISTRATION.json`, committed alone before any file was
altered.

**Nothing is filtered.** The shadow feeds write about 51 GB/day and B11a's collection matures in
about 35 hours against 128 GB free. The temptation is to keep less; the answer is to store the same
bytes smaller. Every frame that was recorded is still recorded, and every derived table is still a
function of the raw log — the property that let B15a's contaminated census be rebuilt rather than
discarded.

**Sealed before compressed, verified before replaced.** A segment is sealed with its byte count,
record count, first and last identity and time, and the SHA-256 of its uncompressed bytes. Only
after the archive decompresses back to that exact hash, and only after a replay over the whole
segment set reproduces the census row for row, is the original removed. Until then the original is
the authority and the archive is a candidate.

**The active tail is never touched.** It is being appended to, so a partial final line is normal.
It is read as far as it is complete and never repaired.

**The guard protects B11a, not this pilot.** B11a's cohort matures once, at a slot fixed long ago.
A shadow feed can always be restarted. So when free space falls below the reserve the feed stops
and quarantines rather than degrading, because a feed that keeps writing a thinner record past the
guard produces a census whose coverage silently changed at an unmarked moment.
"""
import argparse
import fcntl
import gzip
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

PREREG_PATH = ROOT / "research" / "B15J_RAW_RETENTION_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "42172140823f35adf7aef4753aea3492f932809e51c23d7747672f5d655e670e"

PREREG_V2_PATH = ROOT / "research" / "B15J_RAW_RETENTION_V2_PREREGISTRATION.json"
PREREG_V2_CANONICAL_SHA256 = "913dd60479d7f725c040550a8a4ac2635d20efd16668af23458bcdf8b6ecdd01"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "sign_message", "PRIVATE_KEY", "WALLET",
                            "mnemonic", "seed_phrase", "requestAirdrop", "simulateTransaction")

SECRET_TOKENS = ("api-key", "api_key", "apikey", "authorization", "bearer ", "helius",
                 "secret", "private_key", "mnemonic")

R_DISK_RESERVE = "R_DISK_RESERVE"
R_SEAL_MISMATCH = "R_SEAL_MISMATCH"
R_DECOMPRESS_MISMATCH = "R_DECOMPRESS_MISMATCH"
R_REPLAY_DIVERGED = "R_REPLAY_DIVERGED"
R_SEGMENT_GAP = "R_SEGMENT_GAP"
R_PARTIAL_ARCHIVE = "R_PARTIAL_ARCHIVE"
R_INDEX_UNREADABLE = "R_INDEX_UNREADABLE"
R_SECRET_IN_ARCHIVE = "R_SECRET_IN_ARCHIVE"
R_ACTIVE_TAIL_COMPRESSED = "R_ACTIVE_TAIL_COMPRESSED"
R_PARKED_ORIGINAL = "R_PARKED_ORIGINAL"
R_CONCURRENT_COMPACTOR = "R_CONCURRENT_COMPACTOR"

READ_BLOCK = 1 << 20
COMPRESS_LEVEL = 6
GZIP_MTIME = 0          # pinned, so the same bytes always produce the same archive


class RetentionRefused(RuntimeError):
    """The retention path will not proceed, and says why rather than losing a byte quietly."""


def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise RetentionRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise RetentionRefused(f"the retention preregistration hashes {actual}, pinned {expected}")
    return document


def verify_preregistration_v2(path=PREREG_V2_PATH, expected_sha256=None):
    """The V2 freeze, and it must agree with V1 on everything V2 says it does not change.

    A superseding document is the usual way a frozen number gets quietly restated, so the reserve
    and the tail exclusion are compared against V1 rather than trusted because V2 says so.
    """
    expected = PREREG_V2_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise RetentionRefused(f"cannot read the V2 preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise RetentionRefused(f"the V2 retention preregistration hashes {actual}, pinned {expected}")
    v1 = verify_preregistration()
    if document["supersedes_canonical_sha256"] != PREREG_CANONICAL_SHA256:
        raise RetentionRefused(
            f"V2 says it supersedes {document['supersedes_canonical_sha256']}, but V1 hashes "
            f"{PREREG_CANONICAL_SHA256}. A superseding document must name the document it replaces.")
    unchanged = " ".join(document["what_changes_and_what_does_not"]["does_not_change"])
    reserve = v1["free_space_guard"]["reserve_bytes"]
    if str(reserve) not in unchanged:
        raise RetentionRefused(
            f"V2 does not carry V1's reserve of {reserve} bytes verbatim; a reserve restated in "
            f"different words is a reserve that can drift")
    return document


def assert_no_execution_surface(path=None):
    """The scan starts AFTER both token lists.

    This module declares two of them — one for execution surfaces, one for credential material —
    and they overlap. Scanning from the first list's end made the second list its own violation.
    """
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    text = path.read_text()
    marker = "SECRET_TOKENS = (" if "SECRET_TOKENS = (" in text else "EXECUTION_SURFACE_TOKENS = ("
    body = text.split(marker, 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise RetentionRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


# --------------------------------------------------------------------------------------------
# Free space
# --------------------------------------------------------------------------------------------

def free_bytes(path):
    usage = shutil.disk_usage(str(pathlib.Path(path).resolve()))
    return usage.free


def assert_free_space(path, reserve_bytes, measured=None):
    """Refuse before the disk is the problem, not after.

    The party protected here is B11a, whose cohort matures once at a slot fixed long ago and whose
    collection cannot be repeated. This pilot can always be restarted.
    """
    available = free_bytes(path) if measured is None else measured
    if available < reserve_bytes:
        raise RetentionRefused(
            f"{R_DISK_RESERVE}: {available} bytes free is below the {reserve_bytes}-byte reserve "
            f"held for the B11a collection. Capture stops rather than continuing in a reduced "
            f"form: a feed that writes a thinner record past this point changes its coverage at "
            f"an unmarked moment.")
    return available


# --------------------------------------------------------------------------------------------
# Hashing and records
# --------------------------------------------------------------------------------------------

def sha256_stream(handle):
    digest = hashlib.sha256()
    size = 0
    while True:
        block = handle.read(READ_BLOCK)
        if not block:
            break
        size += len(block)
        digest.update(block)
    return digest.hexdigest(), size


def sha256_path(path):
    with open(path, "rb") as handle:
        return sha256_stream(handle)


def sha256_gzip_member(path):
    """The hash of what the archive DECOMPRESSES to, streamed, never held whole in memory."""
    with gzip.open(path, "rb") as handle:
        return sha256_stream(handle)


def _identity_and_time(line):
    """(signature, received_wall_unix) for a raw line, or (None, None) when it carries neither.

    Null is recorded as null. An empty string would compare equal to another empty string and make
    two records with no identity look like the same record.
    """
    try:
        record = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None, None
    if not isinstance(record, dict):
        return None, None
    return record.get("signature"), record.get("received_wall_unix")


def scan_for_secrets(text, where):
    lowered = text.lower()
    found = sorted({token for token in SECRET_TOKENS if token in lowered})
    if found:
        raise RetentionRefused(f"{R_SECRET_IN_ARCHIVE}: {where} contains {found}")
    return True


# --------------------------------------------------------------------------------------------
# The segment index
# --------------------------------------------------------------------------------------------

def index_path(work_dir):
    return pathlib.Path(work_dir) / "segments" / "index.jsonl"


def read_index(work_dir):
    """Every seal record, in file order. Append-only, so file order is seal order."""
    path = index_path(work_dir)
    if not path.exists():
        return []
    records = []
    try:
        with path.open() as handle:
            for number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise RetentionRefused(
                        f"{R_INDEX_UNREADABLE}: {path} line {number}: {error}") from error
    except OSError as error:
        raise RetentionRefused(f"{R_INDEX_UNREADABLE}: {path}: {error}") from error
    return records


def assert_index_contiguous(records):
    """No gap, no duplicate. An incomplete segment set is never read as a complete one."""
    sequences = [record["sequence"] for record in records]
    if sequences != list(range(1, len(sequences) + 1)):
        duplicates = sorted({s for s in sequences if sequences.count(s) > 1})
        expected = set(range(1, (max(sequences) if sequences else 0) + 1))
        missing = sorted(expected - set(sequences))
        raise RetentionRefused(
            f"{R_SEGMENT_GAP}: the index is not 1..N. missing={missing} duplicated={duplicates}")
    return True


def append_index(work_dir, record):
    path = index_path(work_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":"))
    scan_for_secrets(line, f"index record {record.get('sequence')}")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return record


# --------------------------------------------------------------------------------------------
# Sealing and rotation
# --------------------------------------------------------------------------------------------

def seal_record_for(path, sequence, stem):
    """Everything needed to prove later that an archive is this file. Streamed, one pass."""
    path = pathlib.Path(path)
    digest = hashlib.sha256()
    size = record_count = 0
    first_line = last_line = None
    with path.open("rb") as handle:
        for raw_line in handle:
            size += len(raw_line)
            digest.update(raw_line)
            if not raw_line.strip():
                continue
            record_count += 1
            text = raw_line.decode("utf-8", errors="replace")
            if first_line is None:
                first_line = text
            last_line = text
    first_identity, first_time = _identity_and_time(first_line or "")
    last_identity, last_time = _identity_and_time(last_line or "")
    return {
        "sequence": sequence,
        "stem": stem,
        "uncompressed_bytes": size,
        "record_count": record_count,
        "first_record_sha256": hashlib.sha256((first_line or "").encode()).hexdigest(),
        "last_record_sha256": hashlib.sha256((last_line or "").encode()).hexdigest(),
        "first_received_wall_unix": first_time,
        "last_received_wall_unix": last_time,
        "first_identity": first_identity,
        "last_identity": last_identity,
        "sha256_uncompressed": digest.hexdigest(),
        "sealed_at_wall_unix": time.time(),
        "compressed": False,
        "verified": False,
    }


def segment_dir(work_dir):
    return pathlib.Path(work_dir) / "segments"


def sealed_path(work_dir, stem, sequence, compressed=False):
    name = f"{stem}-{sequence:06d}.jsonl" + (".gz" if compressed else "")
    return segment_dir(work_dir) / name


def rotate(active_path, work_dir, stem, document, sequence=None):
    """Seal the active tail into a new immutable segment. The bytes move; nothing is rewritten.

    Rotation happens at an append boundary, so the sealed segment ends on a complete line. The new
    active tail starts empty.
    """
    active_path = pathlib.Path(active_path)
    if not active_path.exists():
        raise RetentionRefused(f"there is no active tail at {active_path} to rotate")
    records = read_index(work_dir)
    assert_index_contiguous(records)
    sequence = (len(records) + 1) if sequence is None else sequence
    destination = sealed_path(work_dir, stem, sequence)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RetentionRefused(
            f"{R_SEGMENT_GAP}: {destination.name} already exists; a sequence is never reused")
    # os.replace is atomic within a filesystem: the tail is either the old file or the new segment,
    # never a half-copied third thing.
    os.replace(active_path, destination)
    active_path.touch()
    record = seal_record_for(destination, sequence, stem)
    append_index(work_dir, record)
    return record


def compress_segment(work_dir, record):
    """Write the archive beside the sealed original. The original is NOT removed here.

    A partial archive is written under .gz.partial and only renamed once it is complete, so a crash
    mid-write leaves something obviously unfinished rather than something that hashes to the wrong
    thing convincingly.
    """
    source = sealed_path(work_dir, record["stem"], record["sequence"])
    if not source.exists():
        raise RetentionRefused(
            f"{R_SEAL_MISMATCH}: the sealed original {source.name} is gone; nothing to compress")
    target = sealed_path(work_dir, record["stem"], record["sequence"], compressed=True)
    partial = target.with_suffix(target.suffix + ".partial")
    if partial.exists():
        # Never adopted. An adopted partial archive is a silent truncation that hashes to
        # something, and something is not the right thing.
        partial.unlink()
    with source.open("rb") as reader, partial.open("wb") as writer:
        with gzip.GzipFile(fileobj=writer, mode="wb", compresslevel=COMPRESS_LEVEL,
                           mtime=GZIP_MTIME) as archive:
            shutil.copyfileobj(reader, archive, READ_BLOCK)
    os.replace(partial, target)
    return target


def discard_partial_archives(work_dir):
    """Restart hygiene. A .gz.partial is discarded, never adopted."""
    directory = segment_dir(work_dir)
    if not directory.exists():
        return 0
    discarded = 0
    for path in sorted(directory.glob("*.gz.partial")):
        path.unlink()
        discarded += 1
    return discarded


def _descriptor_is_writable(pid, descriptor_name):
    """Whether this file descriptor can write. Read from /proc/PID/fdinfo, not guessed.

    Readers and writers matter differently here and the difference is not cosmetic. A READER
    holding the file keeps its own handle on the same inode across a rename, so it finishes reading
    exactly the bytes it started with — harmless. A WRITER keeps APPENDING to that inode, so the
    sealed segment grows after it was hashed. Treating both as blockers made a downstream reader
    look like a hazard and stopped a rotation that was safe.
    """
    info = pathlib.Path(f"/proc/{pid}/fdinfo/{descriptor_name}")
    try:
        for line in info.read_text().splitlines():
            if line.startswith("flags:"):
                flags = int(line.split()[1], 8)
                return (flags & os.O_ACCMODE) in (os.O_WRONLY, os.O_RDWR)
    except (OSError, ValueError, IndexError):
        # Unknown is not clean: a descriptor whose mode cannot be read counts as a writer.
        return True
    return True


def open_file_holders(path, writers_only=False):
    """PIDs holding this exact file open, read from /proc. Empty when nothing does.

    Rotating a file a live writer still holds is the quiet disaster in this design: `os.replace`
    moves the NAME, and the writer keeps appending to the same inode under its new name. The
    "sealed" segment then grows after it was hashed, and every later verification fails against a
    file that was correct when it was measured.
    """
    target = pathlib.Path(path).resolve()
    holders = set()
    proc = pathlib.Path("/proc")
    if not proc.exists():
        return holders
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            for descriptor in (entry / "fd").iterdir():
                try:
                    if descriptor.resolve() != target:
                        continue
                except (OSError, RuntimeError):
                    continue
                if writers_only and not _descriptor_is_writable(entry.name, descriptor.name):
                    continue
                holders.add(int(entry.name))
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            continue
    return holders


def assert_no_writer(path, allow=()):
    """Refuse if anything holds the file open FOR WRITING. Self is NOT excused automatically.

    An earlier version subtracted os.getpid() unconditionally, which meant the one caller most
    likely to hold the file — a writer rotating its own log — was the one caller the gate could
    never catch. A holder that is legitimately expected is named in `allow`, explicitly.
    """
    holders = open_file_holders(path, writers_only=True) - set(allow)
    if holders:
        raise RetentionRefused(
            f"{sorted(holders)} hold {pathlib.Path(path).name} open FOR WRITING. Rotating it now "
            f"would move the name while they keep appending to the same inode, so the sealed "
            f"segment would grow after it was hashed. Stop the writer first.")
    return True


# --------------------------------------------------------------------------------------------
# Reading, in canonical segment order
# --------------------------------------------------------------------------------------------

def open_segment(work_dir, record):
    """A sealed segment's bytes, compressed or not, whichever form currently exists."""
    plain = sealed_path(work_dir, record["stem"], record["sequence"])
    archive = sealed_path(work_dir, record["stem"], record["sequence"], compressed=True)
    if plain.exists():
        return plain.open("rb")
    if archive.exists():
        return gzip.open(archive, "rb")
    raise RetentionRefused(
        f"{R_SEGMENT_GAP}: segment {record['sequence']:06d} has neither a sealed original nor an "
        f"archive; the set is incomplete and is not read as though it were complete")


def iter_lines(work_dir, stem, active_path, include_tail=True, max_sequence=None):
    """Every raw line, sealed segments in ascending sequence and then the ACTIVE TAIL LAST.

    The tail comes last because it is still being appended to. Its final line may be partial; it is
    yielded only if it parses, and never repaired into something that looks whole.
    """
    records = [r for r in read_index(work_dir) if r["stem"] == stem]
    assert_index_contiguous(records)
    if max_sequence is not None:
        # A FIXED set. The live writer keeps sealing new segments, so "whatever the index holds
        # now" is a different set each time it is read, and the gate compared one set against
        # another and called the difference a divergence.
        records = [r for r in records if r["sequence"] <= max_sequence]
    for record in sorted(records, key=lambda r: r["sequence"]):
        handle = open_segment(work_dir, record)
        try:
            for line in handle:
                yield line.decode("utf-8", errors="replace")
        finally:
            handle.close()
    active = pathlib.Path(active_path)
    if include_tail and active is not None and active.exists():
        with active.open("rb") as handle:
            for line in handle:
                text = line.decode("utf-8", errors="replace")
                if not text.endswith("\n"):
                    # A partial final line in the tail is normal and is dropped, not completed.
                    try:
                        json.loads(text)
                    except (json.JSONDecodeError, ValueError):
                        continue
                yield text


def census_of(work_dir, stem, active_path, include_tail=True, max_sequence=None):
    """A cheap, total, order-sensitive fingerprint of the record stream.

    Not a summary of interesting fields — a hash chain over every line in canonical order, plus
    counts. A summary can agree while the underlying bytes differ; a chain cannot.

    `include_tail=False` covers the SEALED SEGMENTS only, and that is what the replace gate uses.
    The tail is being appended to by a live feed, so a census taken twice around a multi-minute
    verification never matches itself: the first live compaction refused both segments with
    R_REPLAY_DIVERGED because 400,000 frames had arrived in between. The tail is not a segment,
    is never replaced, and its bytes are never at risk — including it made the gate unpassable
    rather than stricter.
    """
    digest = hashlib.sha256()
    lines = identities = 0
    first_time = last_time = None
    for line in iter_lines(work_dir, stem, active_path, include_tail, max_sequence):
        lines += 1
        digest.update(line.encode())
        identity, moment = _identity_and_time(line)
        if identity is not None:
            identities += 1
        if moment is not None:
            first_time = moment if first_time is None else first_time
            last_time = moment
    return {"lines": lines, "identities": identities, "chain_sha256": digest.hexdigest(),
            "first_received_wall_unix": first_time, "last_received_wall_unix": last_time}


# --------------------------------------------------------------------------------------------
# The replace gate — three conditions, in order, or the original stays
# --------------------------------------------------------------------------------------------

def verify_segment(work_dir, record):
    """Conditions one and two: the archive exists, and it decompresses to the sealed hash."""
    archive = sealed_path(work_dir, record["stem"], record["sequence"], compressed=True)
    if not archive.exists():
        raise RetentionRefused(
            f"{R_PARTIAL_ARCHIVE}: no archive for segment {record['sequence']:06d}")
    archive_sha256, archive_bytes = sha256_path(archive)
    decompressed_sha256, decompressed_bytes = sha256_gzip_member(archive)
    if decompressed_sha256 != record["sha256_uncompressed"]:
        raise RetentionRefused(
            f"{R_DECOMPRESS_MISMATCH}: segment {record['sequence']:06d} decompresses to "
            f"{decompressed_sha256}, sealed as {record['sha256_uncompressed']}")
    # No separate byte-count check: the hash above is taken over exactly the bytes counted here,
    # so a matching digest with a differing length cannot occur. It read as an extra safeguard and
    # was one more branch that could never fire — worse than no check, because it looks like one.
    return {"archive_sha256": archive_sha256, "archive_bytes": archive_bytes,
            "decompressed_sha256": decompressed_sha256,
            "decompressed_bytes": decompressed_bytes}


def verify_and_replace(work_dir, record, stem, active_path, census=None):
    """The gate. Only all three passing removes a byte of raw evidence.

    The replay check is the one that matters and the one that is easy to skip: hashes prove the
    archive holds the same bytes, but only reading the whole set back in canonical order proves the
    READER still produces the same stream from it.
    """
    census = census_of if census is None else census
    # Pinned to the segments that exist NOW, so a segment sealed mid-verification cannot make the
    # two censuses differ. Excluding the tail was not enough: the writer rotates too.
    frontier = max((r["sequence"] for r in read_index(work_dir) if r["stem"] == stem), default=0)
    before = census(work_dir, stem, active_path, False, frontier)
    proof = verify_segment(work_dir, record)
    original = sealed_path(work_dir, record["stem"], record["sequence"])
    if not original.exists():
        return {"sequence": record["sequence"], "already_replaced": True, **proof}
    # Read the set with this segment served from its ARCHIVE, by hiding the original behind a
    # temporary name. If anything fails the original is put straight back.
    parked = original.with_suffix(original.suffix + ".parked")
    os.replace(original, parked)
    try:
        after = census(work_dir, stem, active_path, False, frontier)
        if after != before:
            raise RetentionRefused(
                f"{R_REPLAY_DIVERGED}: segment {record['sequence']:06d} read from its archive "
                f"produces {after}, not {before}")
    except Exception:
        os.replace(parked, original)                      # the original is the authority
        raise
    parked.unlink()
    return {"sequence": record["sequence"], "replaced": True, "before": before, "after": before,
            **proof}


# --------------------------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------------------------

TARGETS = {
    "b15a": {"work_dir": ROOT / "research" / "b15a", "active": "raw_frames.jsonl",
             "stem": "raw_frames"},
    "b15i": {"work_dir": ROOT / "research" / "b15i", "active": "raw_processed_frames.jsonl",
             "stem": "raw_processed_frames"},
}


def update_index_flags(work_dir, sequence, **flags):
    """Flags live in a side file. The index itself is append-only and is never rewritten."""
    path = segment_dir(work_dir) / "verified.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"sequence": sequence, "at_wall_unix": time.time(), **flags},
                                sort_keys=True, separators=(",", ":")) + "\n")
    return True


def verified_sequences(work_dir):
    path = segment_dir(work_dir) / "verified.jsonl"
    if not path.exists():
        return set()
    done = set()
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("replaced"):
                done.add(record["sequence"])
    return done


class CompactionLock:
    """One compactor per work directory, or none.

    Two concurrent runs raced: one replaced a segment while the other was mid-gate on it, and the
    second reported R_SEAL_MISMATCH for an original that had legitimately gone. Nothing was lost,
    but a second process deleting files another is verifying is not something to leave to luck.
    """

    def __init__(self, work_dir):
        self.path = pathlib.Path(work_dir) / "compaction.lock"
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.handle.close()
            self.handle = None
            raise RetentionRefused(
                f"another compactor holds {self.path}; refusing to verify files it may replace"
            ) from error
        return self

    def __exit__(self, *_):
        if self.handle is not None:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
        return False


def run(target="b15i", work_dir=None, rotate_first=True, max_segment_bytes=None, document=None,
        reserve_bytes=None, allow_writers=(), compress=True, active_name=None, stem=None):
    """Rotate if the tail is large, then compress, verify and replace every unverified segment."""
    assert_no_execution_surface()
    document = verify_preregistration() if document is None else document
    settings = TARGETS[target]
    work_dir = pathlib.Path(settings["work_dir"] if work_dir is None else work_dir)
    active = work_dir / (settings["active"] if active_name is None else active_name)
    stem = settings["stem"] if stem is None else stem
    limit = document["segment_format"]["max_segment_bytes"] if max_segment_bytes is None \
        else max_segment_bytes
    reserve = document["free_space_guard"]["reserve_bytes"] if reserve_bytes is None \
        else reserve_bytes
    v2_document = verify_preregistration_v2()
    lock = CompactionLock(work_dir)
    lock.__enter__()
    report = {"target": target, "gate_version": v2_document["preregistration_id"],
              "restored_parked": restore_parked_originals(work_dir),
              "discarded_partials": discard_partial_archives(work_dir),
              "free_bytes_before": free_bytes(work_dir), "reserve_bytes": reserve,
              "rotated": None, "verified": [], "refusals": []}
    if rotate_first and active.exists() and active.stat().st_size >= limit:
        assert_no_writer(active, allow=allow_writers)
        report["rotated"] = rotate(active, work_dir, stem, document)["sequence"]
    if compress:
        # V2: ONE pinned-frontier pass per run, not one per segment. V1 cost two full reads of the
        # whole retained set per segment replaced, which at 19 segments and 13 GB sealed took over
        # twenty minutes of a core and grew with everything retained. A gate too slow to finish is
        # a gate that stops running.
        gate = compact_once(work_dir, stem, v2_document)
        report["gate"] = gate
        report["frontier"] = gate.get("frontier")
        report["refusals"].extend(gate["refusals"])
        for sequence in gate["replaced"]:
            record = next(r for r in read_index(work_dir)
                          if r["stem"] == stem and r["sequence"] == sequence)
            archive = sealed_path(work_dir, stem, sequence, compressed=True)
            report["verified"].append(
                {"sequence": sequence, "uncompressed_bytes": record["uncompressed_bytes"],
                 "archive_bytes": archive.stat().st_size if archive.exists() else None})
    report["free_bytes_after"] = free_bytes(work_dir)
    report["reclaimed_bytes"] = report["free_bytes_after"] - report["free_bytes_before"]
    report["above_reserve"] = report["free_bytes_after"] >= reserve
    lock.__exit__()
    return report


def status(target="b15i", work_dir=None, document=None, active_name=None, stem=None):
    document = verify_preregistration() if document is None else document
    settings = TARGETS[target]
    work_dir = pathlib.Path(settings["work_dir"] if work_dir is None else work_dir)
    active = work_dir / (settings["active"] if active_name is None else active_name)
    records = [r for r in read_index(work_dir)
               if r["stem"] == (settings["stem"] if stem is None else stem)]
    replaced = verified_sequences(work_dir)
    uncompressed = sum(r["uncompressed_bytes"] for r in records)
    archives = sum(path.stat().st_size for path in segment_dir(work_dir).glob("*.gz")) \
        if segment_dir(work_dir).exists() else 0
    reserve = document["free_space_guard"]["reserve_bytes"]
    available = free_bytes(work_dir)
    return {"target": target, "segments": len(records), "replaced": len(replaced),
            "sealed_uncompressed_bytes": uncompressed, "archive_bytes": archives,
            "compression_ratio": (round(uncompressed / archives, 2) if archives else None),
            "active_tail_bytes": active.stat().st_size if active.exists() else 0,
            "free_bytes": available, "reserve_bytes": reserve,
            "margin_bytes": available - reserve, "above_reserve": available >= reserve,
            "label": document["status_locks"]["label"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="B15j raw retention (no frame is ever filtered)")
    parser.add_argument("--target", choices=sorted(TARGETS), default="b15i")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--rotate", action="store_true", help="seal the active tail now")
    parser.add_argument("--no-compress", action="store_true")
    parser.add_argument("--max-segment-bytes", type=int, default=None)
    arguments = parser.parse_args(argv)
    if arguments.status:
        print(json.dumps(status(arguments.target), indent=2, sort_keys=True))
        return 0
    report = run(arguments.target, rotate_first=True,
                 max_segment_bytes=(0 if arguments.rotate else arguments.max_segment_bytes),
                 compress=not arguments.no_compress)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["refusals"] else 0


if __name__ == "__main__":
    sys.exit(main())


# --------------------------------------------------------------------------------------------
# V2 — exactly one pinned-frontier pass per compaction run
# --------------------------------------------------------------------------------------------

def parked_path(work_dir, stem, sequence):
    return pathlib.Path(str(sealed_path(work_dir, stem, sequence)) + ".parked")


def restore_parked_originals(work_dir):
    """A parked original belongs to a run that never finished proving it. Restore it, always.

    Adopting the archive instead would accept an unverified replacement. Leaving the file parked
    would hide it from the reader, which is worse: the set would read as complete while missing a
    segment the index still lists.
    """
    directory = segment_dir(work_dir)
    if not directory.exists():
        return 0
    restored = 0
    for path in sorted(directory.glob("*.parked")):
        os.replace(path, path.with_suffix(""))
        restored += 1
    return restored


def expected_census(records):
    """The census the pinned set MUST produce, computed from the seal records alone.

    No file is read to obtain this. V1 compared one read against another read of the same bytes, so
    a reader defect that affected both identically would have passed both. Rotation-time evidence
    cannot be fooled that way.
    """
    ordered = sorted(records, key=lambda r: r["sequence"])
    chain = hashlib.sha256()
    for record in ordered:
        chain.update(record["sha256_uncompressed"].encode())
    return {"segments": len(ordered),
            "total_record_count": sum(r["record_count"] for r in ordered),
            "segment_chain_sha256": chain.hexdigest()}


def single_pass_verify(work_dir, stem, records):
    """ONE traversal of the pinned sealed set, verifying each segment as it streams.

    Every segment is read through the same code path a replay uses, in ascending sequence, in
    whatever form now exists. Each segment's bytes are hashed and its records counted during the
    traversal and checked against its own seal, so a failure names the segment rather than the run.
    """
    ordered = sorted(records, key=lambda r: r["sequence"])
    chain = hashlib.sha256()
    total = 0
    for record in ordered:
        digest = hashlib.sha256()
        count = 0
        handle = open_segment(work_dir, record)
        try:
            for line in handle:
                digest.update(line)
                if line.strip():
                    count += 1
        finally:
            handle.close()
        actual = digest.hexdigest()
        if actual != record["sha256_uncompressed"]:
            raise RetentionRefused(
                f"{R_SEAL_MISMATCH}: segment {record['sequence']:06d} streams to {actual}, sealed "
                f"as {record['sha256_uncompressed']}")
        if count != record["record_count"]:
            raise RetentionRefused(
                f"{R_SEAL_MISMATCH}: segment {record['sequence']:06d} streams {count} records, "
                f"sealed as {record['record_count']}")
        chain.update(actual.encode())
        total += count
    return {"segments": len(ordered), "total_record_count": total,
            "segment_chain_sha256": chain.hexdigest()}


def quarantine(work_dir, payload):
    path = segment_dir(work_dir) / "quarantine.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({**payload, "at_wall_unix": time.time()},
                      sort_keys=True, separators=(",", ":"))
    scan_for_secrets(line, "quarantine record")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return payload


def compact_once(work_dir, stem, document=None, verifier=None):
    """The V2 gate. Every candidate is replaced, or none is.

    A partial replacement would leave a set that was never verified as a set, and the next run
    would inherit it without knowing which half had been proven.
    """
    document = verify_preregistration_v2() if document is None else document
    work_dir = pathlib.Path(work_dir)
    verifier = single_pass_verify if verifier is None else verifier
    report = {"stem": stem, "restored_parked": restore_parked_originals(work_dir),
              "discarded_partials": discard_partial_archives(work_dir),
              "candidates": [], "replaced": [], "refusals": []}
    records = [r for r in read_index(work_dir) if r["stem"] == stem]
    assert_index_contiguous(records)
    if not records:
        report["frontier"] = 0
        return report
    # Pinned ONCE. The live writer keeps sealing segments, and a set read twice is two different
    # sets — comparing them reports a divergence that is only the feed doing its job.
    frontier = max(r["sequence"] for r in records)
    report["frontier"] = frontier
    pinned = [r for r in records if r["sequence"] <= frontier]
    already = verified_sequences(work_dir)
    candidates = [r for r in pinned if r["sequence"] not in already
                  and sealed_path(work_dir, stem, r["sequence"]).exists()]
    report["candidates"] = [r["sequence"] for r in candidates]

    # An archive whose original is already gone was replaced by a run whose flag write was lost.
    # It still has to prove itself before the flag is recorded.
    for record in pinned:
        sequence = record["sequence"]
        if sequence in already or sealed_path(work_dir, stem, sequence).exists():
            continue
        try:
            proof = verify_segment(work_dir, record)
            update_index_flags(work_dir, sequence, replaced=True, recovered_flag=True,
                               archive_sha256=proof["archive_sha256"],
                               archive_bytes=proof["archive_bytes"])
        except RetentionRefused as error:
            report["refusals"].append({"sequence": sequence, "reason": str(error)[:200]})

    if not candidates:
        report["expected_census"] = expected_census(pinned)
        return report

    for record in candidates:
        compress_segment(work_dir, record)
    for record in candidates:
        os.replace(sealed_path(work_dir, stem, record["sequence"]),
                   parked_path(work_dir, stem, record["sequence"]))
    try:
        expected = expected_census(pinned)
        observed = verifier(work_dir, stem, pinned)
        if observed != expected:
            raise RetentionRefused(
                f"{R_REPLAY_DIVERGED}: the pinned set streams {observed}, and the seal records say "
                f"{expected}")
    except Exception as error:                                            # noqa: BLE001
        # Every original back, none deleted. The failure is recorded rather than retried blindly,
        # and it carries its TYPE: a bare message like "unexpected end of stream" leaves an
        # operator unable to tell a refusal from a MemoryError.
        restored = restore_parked_originals(work_dir)
        reason = f"{type(error).__name__}: {error}"[:300]
        report["refusals"].append({"frontier": frontier, "restored": restored, "reason": reason})
        quarantine(work_dir, {"stem": stem, "frontier": frontier,
                              "candidates": report["candidates"],
                              "reason": reason, "restored": restored})
        return report
    for record in candidates:
        parked_path(work_dir, stem, record["sequence"]).unlink()
        archive = sealed_path(work_dir, stem, record["sequence"], compressed=True)
        update_index_flags(work_dir, record["sequence"], replaced=True,
                           archive_bytes=archive.stat().st_size,
                           uncompressed_bytes=record["uncompressed_bytes"])
        report["replaced"].append(record["sequence"])
    report["expected_census"] = expected
    report["observed_census"] = observed
    return report
