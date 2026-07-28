#!/usr/bin/env python3
"""Fill the census placeholders from the census JSON — mechanically, not by hand.

`research/B8B_COHORT_CENSUS.md` carries 19 `«placeholder»` tokens. Typing 19 numbers out of a JSON
report into a markdown document by hand is precisely where a silent transcription error lives: a
transposed digit in a leakage share or an `n` looks exactly like a correct one, nothing fails, and
the document is what a reader quotes. This script substitutes each token from the report, so **every
number in the census is provably the number the artifact produced.**

It writes prose nowhere. It only replaces tokens, so the document stays human-written and the
argument stays reviewable; the numbers stop being retyped.

Two refusals, both deliberate:

* **It will not fill a census whose verdict is not COMPLETE.** A partial run must not be dressed as
  a result (freeze §5), and a half-filled document is the most quotable thing there is.
* **It will not leave a placeholder behind.** An unfilled `«…»` in a document with the draft banner
  removed would read as an editing slip rather than a missing measurement, so any leftover token is
  an error, not a warning.

Read-only with respect to the artifact. Usage:

    python3 scripts/b8b_census.py --json out.json      # produce the report (exits 1 unless COMPLETE)
    python3 scripts/b8b_fill_census.py --json out.json # fill the document from it
"""
import argparse
import hashlib
import json
import math
import pathlib
import re
import sqlite3

Z = 1.96
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_SENTINEL = "11111111111111111111111111111111"


def wilson(n, p=0.01, z=Z):
    """The interval a reader should quote. See census §'Cohort size' and Seq 145/146 for why the
    frozen Wald bar is reported alongside it rather than replaced by it."""
    if n <= 0:
        return 0.0, 0.0
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (centre - half) * 100, (centre + half) * 100


def assert_artifact_matches_report(artifact, report):
    """The hashed file must be the one the report describes. C1 (Seq 152).

    Removing `--artifact-sha` in favour of a computed digest was right — a hash typed by hand is
    the transcription error this script exists to prevent. But it moved the problem up one level:
    `--json` and `--database` are independent inputs and nothing related them, so the census could
    carry a provenance line that is internally false — *"these numbers came from the artifact with
    sha X"* naming a file that produced none of them. Demonstrated with a real b8b artifact built
    for window `111,111,111 → 111,211,111` filling a census reported from `433,894,233 →
    434,097,833`: accepted, exit 0.

    The report copies the artifact's own `metadata` table, so the comparison is exact and needs no
    tolerance. Same shape as `assert_schedule_anchor` in the scanner — tie the artifact to what the
    run declares — applied to the write-up instead of the scan.
    """
    declared = report.get("metadata")
    if not declared:
        raise SystemExit(
            f"REFUSING: the census report carries no `metadata`, so the artifact it came from "
            f"cannot be identified. Filling would put an unverifiable provenance line into the "
            f"document. Regenerate the report with scripts/b8b_census.py --json.")
    connection = sqlite3.connect(f"file:{artifact}?mode=ro", uri=True)
    try:
        stored = dict(connection.execute("SELECT key, value FROM metadata"))
    except sqlite3.DatabaseError as error:
        raise SystemExit(
            f"REFUSING: cannot read the metadata table of {artifact} ({error}). Its identity "
            f"cannot be confirmed against the report.") from None
    finally:
        connection.close()
    mismatched = {key: (stored.get(key), value) for key, value in declared.items()
                  if stored.get(key) != value}
    if mismatched:
        summary = ", ".join(f"{key}: artifact={found!r} report={expected!r}"
                            for key, (found, expected) in sorted(mismatched.items()))
        raise SystemExit(
            f"REFUSING: {artifact} is not the artifact this report describes — {summary}. The "
            f"census would name the sha256 of a file that produced none of its numbers.")


def markdown_table(header, rows):
    """A markdown table. Generated rather than retyped, for the same reason as the scalars."""
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def per_hour_table(report):
    return markdown_table(
        ["hour", "offset (min)", "retrieved", "skipped", "members"],
        [[r["hour"], r["offset"], f"{r['retrieved_slots']:,}", r["skipped_slots"], r["creates"]]
         for r in report["per_hour"]])


def regime_table(report):
    total = report["cohort"]["create_events"] or 1
    names = {SOL_SENTINEL: "SOL (native sentinel)", USDC: "USDC"}
    rows = sorted(report["quote_regimes"].items(), key=lambda kv: -kv[1])
    return markdown_table(
        ["quote mint", "regime", "members", "share"],
        [[f"`{mint}`", names.get(mint, "**OTHER — investigate**"), f"{count:,}",
          f"{count / total:.2%}"] for mint, count in rows])


def covariate_table(report):
    rows = []
    for column in ("is_mayhem_mode", "is_cashback_enabled"):
        counts = report.get(column, {})
        total = sum(counts.values()) or 1
        for value in sorted(counts):
            rows.append([f"`{column}`", value, f"{counts[value]:,}",
                         f"{counts[value] / total:.1%}"])
    return markdown_table(["covariate", "value", "members", "share"], rows)


def leakage_table(report):
    return markdown_table(
        ["population", "n", "actor groups", "repeat actors",
         "members from a repeat actor", "surplus beyond one-each", "largest group"],
        [[r["population"], f"{r['n']:,}", r["distinct_actor_groups"], r["repeat_actor_groups"],
          f"{r['members_from_a_repeat_actor']:,} ({r['share_from_repeat_actor']:.1%})",
          f"{r['surplus_beyond_one_each']:,} ({r['share_surplus']:.1%})",
          r["largest_actor_group"]] for r in report["leakage"]])


def require(section, key, name):
    """Read a reported value or refuse. Never default: a defaulted number in a published document
    is indistinguishable from a measured one, and reads as evidence either way."""
    if key not in section:
        raise SystemExit(
            f"REFUSING: report section {name!r} has no {key!r}. Substituting a default would put "
            f"an unmeasured number into the census as though it had been measured.")
    return section[key]


def values(report, artifact_sha):
    completeness = report["completeness"]
    precision = report["precision"]
    n = report["cohort"]["create_events"]
    low, high = wilson(n)
    status = completeness["status"]
    return {
        "artifact": artifact_sha,
        "24": str(completeness["blocks"]),
        "n_sampled": f"{completeness['sampled']:,}",
        "retrieved": f"{status.get('retrieved', 0):,}",
        "skipped": f"{status.get('skipped', 0):,}",
        "verified": f"{status.get('skipped', 0) - completeness['skips_unverified']:,}",
        "missing": f"{completeness['missing']:,}",
        "decode_errors": str(completeness["decode_errors"]),
        # No default. The value lives in `cohort`, and the previous `completeness.get(..., 0)`
        # silently substituted a fallback: the document read "0 members outside every sampled
        # block" as a *default*, not a measurement. It happened to be the true value, which is
        # exactly why it would never have been noticed. Same class as C1 - a provenance claim with
        # nothing behind it - so a missing key must refuse.
        "outside": str(require(report["cohort"], "members_outside_blocks", "cohort")),
        "n": f"{n:,}",
        "wilson_lo": f"{low:.3f}",
        "wilson_hi": f"{high:.3f}",
        "max_p": f"{precision['max_p_meeting_bar'] * 100:.2f}%",
        "met/missed": "met" if precision["meets_bar_at_1pct"] else "missed",
        "n_required": f"{precision['n_required']:,}",
        "hw_wald": f"{precision['half_widths']['0.01'] * 100:.3f}",
        "per-hour table": per_hour_table(report),
        "regime table": regime_table(report),
        "mayhem / cashback table": covariate_table(report),
        "leakage table: all vs tradable": leakage_table(report),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="output of scripts/b8b_census.py --json")
    parser.add_argument("--census", default="research/B8B_COHORT_CENSUS.md")
    parser.add_argument("--database", default="research/b8b_cohort_433894233_434097833.sqlite",
                        help="artifact whose sha256 is COMPUTED and written into the census. "
                             "There is deliberately no --artifact-sha: a hash typed by hand is "
                             "exactly the transcription error this script exists to remove (B1).")
    arguments = parser.parse_args()

    report = json.loads(pathlib.Path(arguments.json).read_text())
    if report.get("verdict") != "COMPLETE":
        raise SystemExit(
            f"REFUSING: census verdict is {report.get('verdict')!r}, not COMPLETE. A partial run "
            f"must not be written up as a result (freeze §5), and a half-filled document is the "
            f"most quotable thing there is. Finish or resume the scan first.")

    # The census script already gates on block count, but the filler must not trust its input:
    # a report claiming COMPLETE with fewer per-hour rows renders a short table into a document
    # whose prose says 24 strata, and the mismatch is invisible in the rendered output.
    declared = report["completeness"]["blocks"]
    reported = len(report.get("per_hour", []))
    if declared != reported:
        raise SystemExit(
            f"REFUSING: report declares {declared} sampled blocks but carries {reported} per-hour "
            f"rows. Rendering that would put a {reported}-row table under prose describing "
            f"{declared} strata.")

    artifact = pathlib.Path(arguments.database)
    if not artifact.is_file():
        raise SystemExit(f"REFUSING: artifact {artifact} not found; its sha256 is computed, not "
                         f"supplied, so the census cannot name the bytes it describes.")
    assert_artifact_matches_report(artifact, report)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

    document = pathlib.Path(arguments.census)
    text = document.read_text()
    filled = values(report, digest)

    def substitute(match):
        key = match.group(1)
        if key not in filled:
            raise SystemExit(f"REFUSING: no value for placeholder «{key}». Every token must map to "
                             f"a measured quantity; inventing one is how a number enters a document "
                             f"without provenance.")
        return filled[key]

    text, replacements = re.subn(r"«([^»]+)»", substitute, text)
    # B2: a second run finds no placeholders, substitutes nothing, sees an empty `leftover`, and
    # writes the unchanged file while printing success. That bites in the one case where re-running
    # matters most - you fill, notice the report was wrong, re-run with corrected input, get
    # "filled 20 values", and publish the stale numbers. Report replacements MADE, not values
    # available, and refuse when none were.
    if replacements == 0:
        raise SystemExit(
            f"REFUSING: {document} contains no placeholders, so nothing was substituted. It has "
            f"already been filled. Re-running would print success and silently leave the previous "
            f"numbers in place. Restore the template from git before filling again:\n"
            f"    git checkout -- {document}")
    leftover = re.findall(r"«([^»]+)»", text)
    if leftover:
        raise SystemExit(f"REFUSING: placeholders remain after substitution: {leftover}")

    document.write_text(text)
    print(f"substituted {replacements} placeholders in {document}")
    print(f"artifact sha256 {digest} (computed from {artifact}, not supplied)")
    print("NOTE: the draft banner is NOT removed automatically — removing it is the act of "
          "publishing, and that stays a human decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
