# B8a — Cohort enumeration census

**Run completed:** 2026-07-28
**Authorised by:** owner, recorded in `agent_discussion.md` Seq 77 against freeze SHA-256
`59da9f8d511605f1b8160233feeb14755b96472a2cd83f172b7fd71daff1d1cf`
**Artifact:** `research/b8a_cohort_433302364_433304364.sqlite`, SHA-256
`7564e8b1185757e02ffe9eeae8dc7b6e72fb8be19848603ca4dd85e799310f14`
**Scope:** enumeration only. No labels, no features, no member history reconstruction — the
authorisation in Seq 77 explicitly excludes those.

This is a census of what the authorised enumeration found. It states counts and nothing about
whether an edge exists.

## Completeness

The frozen window is `[433,302,364, 433,304,364)`, 2,000 slots. Every slot is accounted for:

| Status | Slots |
|---|---:|
| `retrieved` | 1,960 |
| `skipped`, **absence verified by `getBlocks`** | 40 |
| unverified, error, or pending | **0** |

The 40 skips are not assumed. `getBlock` returns `-32009` ambiguously for "skipped **or** missing",
so each was re-checked against `getBlocks`; all 40 carry `absence verified by getBlocks`, and none
carries the `getBlocks lists produced slot but getBlock unavailable` marker that would indicate a
slot we failed to read rather than one that never existed. **Decode errors: 0.**

This matters for the freeze's rule C4: membership is claimed **exhaustive** within the window, and
that claim is only as good as the slot accounting behind it.

## Cohort

**242 `CreateEvent`s, 242 distinct mints** (no mint appears twice), spanning slots 433,302,378 to
433,304,353 across 204 distinct slots. Membership was taken with **no attribute filtering**, as
frozen.

### Quote regime — reported split, as the freeze requires

| `quote_mint` | Members | Share |
|---|---:|---:|
| `11111111111111111111111111111111` (SOL sentinel) | 234 | 96.7% |
| `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` (USDC) | **8** | **3.3%** |

**This strengthens a finding that was previously thin.** B7k identified a single USDC-quoted
graduation and recorded explicitly that the inference rested on two observations and was **not
established**. Eight USDC launches in an exhaustive, preregistered window that was fixed before
anyone looked make USDC quoting a **recurring regime rather than an anomaly**. The frozen rule
stands and is now better supported: any feature or label reading `sol_amount` must branch on
`quote_mint` or fail closed, and no quote-denominated amount may be summed or averaged across
regimes.

B7l adds the second half of the trap: `quote_mint` has **two representations for SOL** depending on
where it is read — the event carries the sentinel `111…111`, the instruction account carries
wrapped SOL `So111…112`. The census above reads event-derived values. A filter written against the
account-derived form would return **zero** SOL members from this table, and an empty result reads
as "no SOL launches" rather than as a bug.

### Regime covariates — recorded, not filtered

| | `is_mayhem_mode=0` | `is_mayhem_mode=1` | Total |
|---|---:|---:|---:|
| SOL sentinel | 188 | 46 | 234 |
| USDC | 5 | 3 | 8 |
| **Total** | **193** | **49** | **242** |

`is_cashback_enabled` is true for 108 of 242.

**Tradable population at decision time: 193 (79.8%).** Mayhem members stay in the cohort for regime
accounting but are excluded from the tradable population by frozen policy, because B2a/B7a
established Mayhem curves are mutated outside trading by `set_mayhem_virtual_params` and are
therefore not reconstructible from the trade stream. That exclusion is a **policy applied after
selection**, never a sampling step.

## Finding not anticipated by the freeze: creator concentration

**157 distinct creators produced 242 launches; 37 launched more than once.**

**Corrected 2026-07-28** (audit, `agent_discussion.md` Seq 104; independently recomputed before
accepting). This section first said "roughly 35% of members come from a repeat creator". **That was
wrong.** 35.1% is 85/242 — the *surplus* beyond one launch each, which is not the exposed share.
**The share of members whose creator launched more than once in-window is 122/242 = 50.4%.** Half
the cohort, not a third. The conclusion below is unchanged and if anything stronger, but the figure
that will be quoted when a split is argued has to be the right one.

Broken out, because the modelling population is not the censused one:

| Population | n | creators | repeat creators | members from a repeat creator | max by one creator |
|---|---:|---:|---:|---:|---:|
| all, as censused | 242 | 157 | 37 | **122 (50.4%)** | 10 |
| **tradable, Mayhem excluded** | **193** | **142** | **26** | **77 (39.9%)** | **6** |
| Mayhem (excluded by policy) | 49 | 20 | 10 | 39 (79.6%) | 10 |

**All three are lower bounds.** First and last launch are **813 s ≈ 13.6 minutes** apart, so a
creator with a single launch inside the window can trivially have others just outside it. True
creator overlap is higher than any number here.

This is a **leakage hazard**, and it is the kind AGENTS.md names directly ("prevent temporal,
creator, wallet, token, and funding-cluster leakage"). Any later train/validation/test split made
naively by token or by time will place the *same creator* on both sides, and a model can then learn
creator identity rather than anything generalisable — scoring well for a reason that will not
survive contact with new creators.

**Stated as a constraint on future work, not resolved here:** whichever split is eventually frozen
must be **grouped by creator**, not by token. The alternative — discovering this after a model
scores well — is exactly the failure this project's preregistration discipline exists to prevent.

**The grouping key should be `creator ∪ user`, not `creator` alone.** They differ on 4 of 242 rows;
none of those 4 `user` values appears as a `creator` elsewhere, so the union actor space is **161,
not 157**. `creator` alone is very nearly complete *for this window* — but the bridge count happens
not to be zero, and the union is the safer default.

Funding-cluster leakage is a *superset* of all of this and is **not** measured: two distinct creator
pubkeys funded from one source are still one actor, and nothing here detects that.

### The Mayhem exclusion changes creator composition, not just row count

The 49 Mayhem launches come from only **20 creators, 79.6% of them repeat**, and the single largest
creator in the cohort — 10 launches, 4.1% of everything — is **entirely Mayhem**. That is why
tradable leakage (39.9%) is *lower* than raw (50.4%): excluding Mayhem removes the most
concentrated block. **Five creators launch both Mayhem and non-Mayhem**, so the exclusion cuts
across actors rather than removing them cleanly.

None of this challenges the frozen policy, which was applied after selection and correctly. But
"Mayhem excluded" is a **change in creator composition**, and should be described that way wherever
the 193 is used.

### USDC is not confounded with creator identity

The obvious way the USDC finding could have been an artefact is 8 launches from one or two bots.
It is not: **8 USDC launches, 8 distinct creators, exactly one each**, and seven of the eight come
from creators with ≤2 in-window launches. USDC quoting is spread across independent actors, so
B7k's inference is supported by a check that could have refuted it and did not.

## What this does not establish

- **No label, feature, or model.** None was computed, and `D_dead` binding at 7 days does not
  change that; labels remain unfrozen.
- **No member history.** The authorisation covers enumeration only; reconstructing each member's
  trade history is a separate cost needing its own scoped estimate, now that the member count is
  known to be 242.
- **No survival, graduation, or death rate.** Any such rate requires observation of the members
  over the tail, which has not been run.
- **Nothing about edge.** This is a substrate.

## Reproduction

Every number above is one query against the artifact; the raw decoded struct is retained per member
in `create_event.fields_json` and `event_payload_base64`, so the census is recomputable without
re-fetching. Read-only throughout: no signing, no spending, no deployment, no live or devnet
transactions.
