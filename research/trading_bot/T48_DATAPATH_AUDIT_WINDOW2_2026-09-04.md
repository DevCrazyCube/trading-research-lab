# T48 tranche 5 — DATA-PATH AUDIT: window-2 (b11m) collection chain

**Date:** 2026-09-04 00:00 CEST · STRATEGIST tick (CHUNK A) · instrument **9 of the T48 series**
**Method:** read-only SQL over the sealed artifacts + source read of the frozen collector.
**Verdict: CLEAN on all three T48 dimensions. No fault. No fix. Nothing touched.**

**Blindness discipline, stated first.** Window-2 feeds B19L, the programme's only *data-blind*
out-of-sample test. This audit therefore touched **only structural and provenance columns** —
slot, signature, `time_class`, `err_json` presence, row counts, membership keys, schema. It read
**no path, price, reserve or outcome value**, and it computed **no statistic that appears in
either pinned evaluation**. `results_unlocked` is still `false` and was not written to.
U4 remains absent (`DECISIONS.md` unchanged since 09-02 15:50) → **T38 stays blocked-attended**.

---

## (a) RECENCY / BOUNDARY — OK

The analogue of "recency" for a sealed historical window is **boundary integrity**: the window
must contain what it declares and *nothing past its cutoff*, because past-the-cutoff data here is
lookahead, not staleness.

| assertion | result |
|---|---|
| declared launch window (cohort + subsample metadata agree) | `437211660 .. 437415261` (exclusive), both artifacts identical |
| cohort launch slots inside it | 35,267 rows, `min 437211661 / max 437415256` — **0 outside** |
| subsample launch slots inside it | 5,000 rows, `min 437211673 / max 437415254` — **0 outside** |
| declared observation cutoff | `438854169` (matches `supervisor_state.json` and bodies `metadata.cutoff_slot`) |
| `transaction_coordinate` slots > cutoff | **0** (`max 438846716`) |
| out-of-window signature rows | present but **explicitly labelled**: 844 `after_cutoff`, 43 `before_launch`, 5,484,107 `in_window` |
| slot agreement between block lookup and tx body | enforced in code — `b9d_transaction_bodies.py:1298 reconcile_slot()` **raises** on disagreement |

The 844 after-cutoff rows are the sharp case and they pass: they exist (they are the evidence that
the scan reached past the boundary and therefore did not truncate early) and they are **carried
under a label rather than silently mixed in**. The consumer's population query filters on
`time_class = 'in_window'` (`:250`, `:304`). This is the correct shape — the opposite of the
newsdesk "absence looked like data" fault, where an unlabelled silence entered a judgement.

## (b) REPRESENTATION — OK, and reconciles exactly

The fault class here would be a curve whose history was cut short by a page cap, or a body-fetch
that stopped early, leaving a subset that *looks* complete.

- **Signature scan: no truncation anywhere.** `curve_scan` = 5,000 rows, **all `status='complete'`,
  `capped = 0` for every curve, `boundary_proven = 1` for every curve, zero `terminal_error`.**
  Max 23 pages, mean 2.86 — nowhere near a cap. (Compare the predmarket puller, which was read one
  page deep of a paged feed.)
- **Body fetch reconciles to the frozen rule, exactly.** The declared population is
  `time_class='in_window' AND err_json='null' AND is_mayhem_mode=0` (`:250–258`). Independently
  recomputed: **366,688 signatures over 4,049 curves**. `raw_transaction` holds **366,688**.
  Non-mayhem curves in the subsample: **4,049**. Exact match on both axes.
- **Every curve is represented — no zero-body curves.** Per-curve fetched-signature counts:
  `1–4: 1,773 · 5–19: 961 · 20–99: 781 · 100+: 534` — **bucket `0` is empty**. No curve entered the
  path dataset as a silent blank.
- **No time-of-window concentration.** Launch slots across 20 equal buckets run 1,028–2,577 with a
  mild monotone decline (front ≈ 2.3k, back ≈ 1.6k). That is a real launch-rate drift over ~23
  hours of chain time, not a collector that stalled; every bucket is populated at the same order of
  magnitude, and slot coverage is 203,342 / 203,601 = **99.87 %** (259 skipped, recorded in
  `provenance`).

**One scope statement, recorded so it is never mistaken for a gap:** bodies are fetched for
*successful* transactions only (`err_json='null'`). Failed transactions are therefore absent from
the path dataset by design, and the pipeline covers that with a separate stage —
`failure_coverage_gate` (`b9f_failure_coverage.py`), completed. Worth naming because B20B is a
*deadness* screen and "failing swaps" is a plausible deadness signature; the declared answer is
that failures are handled by their own gate, not by the path corpus. Not a fault; a boundary of
what the path corpus means.

## (c) ATTRIBUTION — OK, and structurally immune to the fault that killed the newsdesk

Fault #4 of this series was the newsdesk treating *the query that fetched a row* as the row's
identity (per-ticker RSS provenance → 53 % wrong tickers). Window-2 fetches signatures per
`bonding_curve` address, so the same trap is available. It is closed three separate ways:

1. **Bodies carry no inherited key.** `raw_transaction` is keyed by `signature` alone — there is no
   `bonding_curve` column for the fetch context to leak into.
2. **Curve identity is re-derived from each instruction's own account roles**, not from the
   subscription: `curve = roles.get("bonding_curve")` (`:2082`), and a parent event without that
   role **raises** rather than falling back to the queried address (`:2084`). The reserve path does
   the same (`:2682–2690`).
3. **Cross-row identity disagreement is fatal, not reconciled.** A mint mapping to two curves raises
   (`:2674–2678`); a signature appearing under two slots raises (`frozen_population_by_slot`);
   membership must agree bidirectionally between the signature inventory and the cohort or the fetch
   set is refused outright (`:252–256`).

Both cohort artifacts additionally declare `contains_outcomes=0` with an explicit
`outcome_view_columns` contract, and the `outcome` view is a strict projection of
`cohort_identity` — the provenance column `create_signature` is deliberately excluded from the
view so that the view provably *is* a projection rather than the table renamed.

---

## What this tranche adds to the T48 thesis

Nine instruments, nine faults: **7 in 6 reader/discretionary surfaces, 1 in 5 archival collectors —
and that one (T31) was a schedule fault, not a content fault.**

Window-2 is the **most adversarially-built collector in the programme** and it audits clean on the
first pass, which sharpens the thesis rather than weakening it. The difference is not care or
effort; it is **structure**: window-2 raises `FreezeViolation` at every point where a reader would
have silently coerced — missing key, disagreeing slot, ambiguous mint, absent role, one-sided
membership. Every one of the nine faults found in this series was a place where code chose a
plausible value over an exception. **The generalisable rule: an input surface is honest in
proportion to the number of places it is willing to refuse.** Readers refuse nowhere, which is why
they hold seven of the nine faults.

**Remaining before the stated kill-condition: MEME ARENA only.** If it audits clean, T48 closes
`done` and no further auditing is authorised.
