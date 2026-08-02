# Operator snapshot schema — v1.0.0

Produced by `scripts/b12b_operator_snapshot.py`, rendered by `ui/operator_console.html`.
Read-only: consumers must treat every snapshot as immutable and must pin `snapshot_schema_version`.

Status: **offline. Nothing here is operationally ready.** The console is an interface for research
output; no data pipeline feeds it automatically, the only fixture that ships is synthetic, and
nothing in the project has ever been executable.

## Why an adapter exists between the pipeline and the page

Because the alternative is a browser recomputing research figures. Every number a console shows
should have been derived, checked and hashed by the code that owns it. A UI that divides two
integers to show a percentage has quietly become a second implementation of the metric, and the two
will disagree on the day it matters.

So the adapter assembles, validates and hashes; the console only formats. **There is no arithmetic
on data in the page at all** — exact integers and exact `[numerator, denominator]` pairs are
displayed as they arrive, and a test asserts the script contains no `toFixed`, `Math.round`,
`parseFloat`, `* 100` or `/ 100`.

## Sections

| field | contents |
| --- | --- |
| `status_banner` | `level` (`RESEARCH` or `SIMULATED`), `executable` (always `false`), headline, detail |
| `overview` | opportunity counts, open positions, pending orders, results-locked, kill switch, emergency |
| `pipeline` | each stage: kind, runnable, blocked reason, whether its counts are withheld |
| `windows` | burned-range count, the frozen fresh window and whether it has been queried, warnings |
| `strategy` | model family, learned parameters, primary policy/horizon/metric, label semantics, unmet unlock requirements |
| `opportunities` | per candidate: the exact proposed order, decision, every reason with code and label |
| `simulated_positions` | per path: outcome status and label, liquidity state, exact net return and drawdown pairs, censoring reason |
| `portfolio` | aggregates, positions, configured limits with exact utilisation, and the risk block |
| `evidence` | both clocks, both maxima, staleness, completeness, conflict, version support, halts |
| `config` | version, ratification, config hash |
| `provenance` | source → identifier, echoed |
| `snapshot_sha256` | hash over everything else |

## What the adapter refuses to assemble

1. **An executable claim.** `level` must be `RESEARCH` or `SIMULATED`; `executable` must be exactly
   `False`; every `outcome_status` must be a known simulated outcome. `EXECUTABLE` is not a value
   this schema has.
2. **An approval that contradicts the system's own state.** If the kill switch is engaged, the
   emergency state is set, or the evidence is stale, an approved opportunity is a contradiction and
   the snapshot is refused rather than rendered.
3. **A stale snapshot that calls itself fresh.** `is_stale` is recomputed from the clocks and the
   configured maxima; a flag that disagrees with its own numbers is refused. That is the snapshot an
   operator would trust and should not.
4. **A float**, anywhere, at any depth.
5. **An undeclared field**, because a console cannot render what it has no contract for, and a field
   nobody declared is a field nobody reviewed.
6. **Anything credential-shaped** — `api-key`, `private_key`, `secret`, `Bearer `, a URL with
   embedded credentials. A snapshot is the artifact most likely to be pasted into a chat window.
7. **Internal disagreement**: an approved opportunity carrying reasons, a rejected one carrying
   none, an overview count that disagrees with its list, results shown unlocked while requirements
   are unmet, or a named model with no frozen artifact hash.

## Display strings: derived here, by integer arithmetic, and hashed

The console must not divide. But an operator reading `306788560` and `[3834857, 12500000]` is doing
the arithmetic in their head instead — the same computation, performed by the person least able to
check it and most likely to be tired. So the adapter publishes the human-readable form too.

| kind | rule | exact? |
| --- | --- | --- |
| `*_sol_display` | `lamports // 1_000_000_000` and the remainder as **9 fixed decimals** | **exact** — every lamport is shown, nothing is rounded, digits are never trimmed |
| `*_percent_display` | magnitude truncated toward zero to **2 decimals** by integer division, prefixed `≈` | **not exact** — `|displayed| ≤ |exact| < |displayed| + 0.01` |

`display_format` carries the version and both rules in the snapshot itself, so the rule travels
with the values it governs.

**Every display string sits beside the raw value it came from, and the raw value is authoritative.**
`assert_display_consistent` re-derives every one and is **total in both directions**: a display
string with no raw sibling is an unsourced number on an operator's screen, and a raw field with no
display string is a silent gap where the console would show nothing. Display strings are inside the
snapshot hash, so tampering with one changes it.

## Unknown is never zero

Every optional numeric field is present and explicitly `null` when unknown — never omitted, never
substituted with zero. The console renders `null` as a visibly italic *unknown*, and that only works
because the adapter never quietly supplies a number it does not have. A real zero still prints as
`0`; a test pins both halves of that.

## Labels

Plain-language labels are a **deterministic mapping from stable codes**, held in the adapter so they
are versioned and testable. Every risk reason code has one, asserted total against
`b12a.REASON_PRECEDENCE`, and the **raw code always travels with the label** and is displayed beside
it.

A code the build does not recognise renders as `Unrecognised code (X)` and is **never dropped**. A
console that silently omits an unknown code shows an operator a shorter list than the truth, which
is the one failure worse than showing them a code they cannot read yet.

## The console

`ui/operator_console.html` is a single self-contained file. **No stylesheet, script, font, image or
analytics is loaded from anywhere, and there is no `fetch`, `XMLHttpRequest`, `WebSocket`,
`EventSource`, form, or beacon in it.** It can be opened from disk with the network unplugged and
behave identically — the property that makes "this page cannot leak a snapshot and cannot touch a
wallet" checkable by reading it rather than by trusting it.

It loads either a snapshot JSON the user picks from their own machine (`FileReader`, local, no
upload) or the embedded synthetic demo. The embedded demo is rewritten from
`build_demo_snapshot()` by `--embed`, so the fixture cannot drift from the page, and a test asserts
they are equal.

**It cannot act.** No form, no submit control, and a test scans every interactive element for
`submit`, `approve`, `sign`, `execute`, `connect wallet`, `send`, `place order` and friends. Data
reaches the page only through `textContent`; `innerHTML`, `insertAdjacentHTML`, `document.write` and
`eval` appear nowhere, because a mint or a censoring reason is data from a file and data from a file
is never markup.

**Layout defects found by rendering, not by reading.** Three were fixed after inspecting the page
in headless Firefox at 1440px and 390px: 44-character identifiers were being squeezed into four
ragged lines (the identifier cell now has a width floor as well as a ceiling); stacked-card labels
sat beside multi-line values instead of above them; and stat values broke mid-token because of
`word-break: break-all` (now `overflow-wrap: anywhere`). A fourth was a mislabelled column header
reading "Utilisation (exact)" above a deliberately approximate percentage.

**Accessibility and layout:** skip link, semantic landmarks, every section labelled by its heading,
every table with a `<caption>`, column scopes and row headers, a `role="status"` live region for the
banner, visible focus styling, `prefers-reduced-motion` honoured, `prefers-color-scheme` for both
themes, and a narrow-screen layout where tables stack into labelled cards via `data-label`.

## Local preview

```
python scripts/b12b_preview_server.py          # http://127.0.0.1:8765/operator_console.html
```

Standard library only; **no dependency is added by it and none may be.** It binds loopback,
serves `GET`/`HEAD` from `ui/` and nothing else, answers every other method `405`, refuses paths
resolving outside that directory, and sends a restrictive Content-Security-Policy. **There is no
route that writes, mutates, approves, signs or submits**, and there is no code path that could grow
one without deleting the check that forbids it.

The console does not need the server — it works from `file://`. The server exists because some
browser tooling is awkward with `file://`, not because the page needs a network.

## Not covered

- Any live or automatic data feed. The only shipped fixture is synthetic and says so in its own
  provenance block.
- Any B11a composition. That window has never been queried and the console cannot query anything.
- Operational readiness of any kind. This is an interface for research output.

No profitability claim is made and nothing here is a trading recommendation.
