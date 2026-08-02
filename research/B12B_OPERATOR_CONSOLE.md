# B12b — operator snapshot and read-only console, verified

Date: 2026-08-02. Author: Claude (handoff 74). Offline only.
Code: `scripts/b12b_operator_snapshot.py`, `ui/operator_console.html`,
`scripts/b12b_preview_server.py`. Schema: `docs/OPERATOR_SNAPSHOT_SCHEMA.md`.
Tests: `tests/test_b12b_operator_console.py`.

```
python scripts/b12b_operator_snapshot.py --contract
python scripts/b12b_operator_snapshot.py --demo ui/demo_snapshot.json
python scripts/b12b_operator_snapshot.py --embed ui/operator_console.html
python scripts/b12b_preview_server.py     # http://127.0.0.1:8765/operator_console.html
```

## 0. Scope, and what was not touched

This is the trading system's own operator view, **not** the collaboration dashboard. No dependency
was added. **B11a was not read, queried or computed on**, B11b was not altered, and results remain
locked on `U3` — all asserted by tests in this suite. Nothing here is operationally ready: no
pipeline feeds it, and the only shipped fixture is synthetic and labelled so in its own provenance.

## 1. Why an adapter sits between the pipeline and the page

Because the alternative is a browser recomputing research figures. A UI that divides two integers to
show a percentage has become a second implementation of the metric, and the two will disagree on the
day it matters.

So the adapter assembles, validates and hashes; the page only formats. **There is no arithmetic on
data in the console at all** — exact integers and exact `[numerator, denominator]` pairs are shown as
they arrive. `1 / 4` rather than `25%`. A test asserts the script contains no `toFixed`,
`Math.round`, `parseFloat`, `* 100` or `/ 100`.

## 2. What the adapter refuses

An executable claim; an approval that contradicts the system's own halt or staleness state; a
snapshot whose `is_stale` flag disagrees with its own clocks; a float at any depth; an undeclared
field; anything credential-shaped including a URL with embedded credentials; and every form of
internal disagreement — an approved row carrying reasons, a rejected row carrying none, an overview
count that disagrees with its list, results shown unlocked while requirements are unmet, a named
model with no frozen artifact hash.

**Unknown is never zero.** Every optional numeric field is present and explicitly `null`, never
omitted and never substituted. The demo deliberately carries a position whose realisable value is
unknown so that state is exercised rather than assumed, and a render test asserts the word
*unknown* appears where a `0` would be wrong — while a real `0` still prints as `0`.

## 3. The console cannot do the things that would matter

| property | how it is established |
| --- | --- |
| no network of any kind | no `fetch`, `XMLHttpRequest`, `WebSocket`, `EventSource`, `sendBeacon`, worker or service worker; nothing loaded from `http`; no `<script src>`, no `@import` |
| cannot act | no `<form>`, no submit control, and every interactive element scanned for `submit`, `approve`, `sign`, `execute`, `connect wallet`, `send`, `place order` |
| no wallet surface | no `window.solana`, `phantom`, `walletconnect`, `keypair`, `signTransaction`, `sendTransaction` |
| no telemetry | no `gtag`, `analytics`, `dataLayer`, `posthog`, `sentry`, `mixpanel` |
| data is never markup | only `textContent`; no `innerHTML`, `insertAdjacentHTML`, `document.write` or `eval`, and no HTML built from strings |

**One thing that had to be fixed in the tests rather than the page:** the file's own prose names
every primitive it refuses to use, so the first scanners reported the strictest file in the
repository as the worst one. The scanners now strip HTML and JavaScript comments and read code only
— otherwise documenting a safety property would be indistinguishable from violating it.

## 4. Verified by running it, not only by reading it

`node` is present, so the console's pure helpers **and its whole render path** are executed against
a minimal DOM stub written inside the test file. No dependency is added: the tests skip if `node` is
absent rather than faking a pass.

That caught what source scanning cannot. The render tests assert that the console boots without
throwing, that **every element id the script addresses exists in the page** (a mistyped id silently
yields `null` and leaves a section blank), that all six table bodies receive rows, that the four
halt pills render, that a rejected opportunity shows both its plain-language reason and its raw
code, that a halted-and-stale snapshot lights three pills, and that a snapshot claiming to be
executable is refused at render time with a visible message rather than displayed.

## 5. Labels

Plain-language labels are a deterministic mapping from stable codes, held in the adapter so they are
versioned and testable. Every one of the 24 risk reason codes has a label, asserted **total** against
`b12a.REASON_PRECEDENCE`, and each label is checked to be a sentence rather than a prettified code.
The raw code always travels with the label and is displayed beside it.

An unrecognised code renders as `Unrecognised code (X)` and is never dropped: a console that omits a
code it does not know shows a shorter list than the truth, which is worse than showing a code
nobody can read yet.

## 6. The preview server is a preview, not an API

Standard library only. Loopback only. `GET` and `HEAD` only — every other method answers `405`
before reaching a handler. Paths resolving outside `ui/` are refused. A restrictive
Content-Security-Policy, `nosniff`, `no-referrer` and `no-store` on every response. A test asserts
the module imports nothing beyond `argparse`, `functools`, `http`, `pathlib` and `sys`, and contains
no `sqlite3`, `open(`, `write_text`, `subprocess` or `os.system`.

Live-checked: `200` for the console, `405` for `POST`, `404` for `/../DECISIONS.md`, and the CSP
header present.

The console does not need it — the page works from `file://`. It exists because some browser tooling
is awkward with `file://`, not because the page needs a network.

## 7. One source of truth for the demo

`--embed` rewrites the console's embedded JSON block from `build_demo_snapshot()`, and tests assert
that the embedded copy, the standalone `ui/demo_snapshot.json` and the adapter's output are all
equal, that embedding is idempotent, and that the payload contains no `</` that could close the
script element early and turn data into markup.

## 8. Also in this pass

`docs/RISK_DECISION_SCHEMA.md` now states, as Codex asked, that the drawdown control reads
**treasury net asset value** and that genesis must supply a positive current and peak NAV rather
than inferring zero from an empty positions list. Passing zero because the book is empty is a
category error that makes the governor reject every first trade and look broken; the behaviour is
correct, so the fix belongs in what the caller supplies. **No behaviour changed.**

## 9. Verification and limits

80 tests in this suite, 222 subtests; **1,192 passing repository-wide**. No mutation run was
performed on this area: the substance here is what the artifacts *cannot* do, and those properties
are asserted directly — by executing the page, by driving the server, and by scanning for absent
capabilities — rather than by perturbing a decision function. That is a deliberate difference from
B10a–B12a and is stated rather than glossed.

**Not claimed:** any operational readiness, any live feed, any real data in the interface, or any
review of visual design by a human. The layout has been verified structurally and by execution, not
by anybody looking at it.
