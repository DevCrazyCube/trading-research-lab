# B11F cost pilot — the measurement that sized N, versioned so it can be checked

`B11F_COHORT_SUBSAMPLE_PREREGISTRATION` sets N = 5,000 and discloses that the number was chosen
using a cost measurement taken **before** the document was finalised. These are those scripts and
their outputs. They are here rather than in a scratch directory because a preregistration that
cites artifacts nobody can open is citing nothing, and the whole point of the disclosure is that it
is checkable.

## What is here

| file | what it did |
|---|---|
| `rate_probe.py` | serial ramp 2.5→40 calls/s, then the concurrency arm; measured the endpoint, not the population |
| `rate_probe_result.json` | 5.85 / 4.95 / 5.80 / 5.76 / 5.66 calls/s achieved — the plateau that was the probe's own serialisation |
| `conc_probe_result.json` | 1/2/4/8 workers → 5.85 / 10.42 / 13.76 / 15.71 calls/s, zero 429 |
| `sample_sigs.py` + `.json` | seed 11, 40 curves, all-time signature counts |
| `sample_windowed.py` + `.json` | seed 23, 80 curves, counts bounded at the observation cutoff — the draw N was sized from |

Both sampling draws use a **fixed seed**, so a reviewer reruns them and gets the same curves.

## The property that matters, and it is machine-checkable

The disclosure's claim is that the pilot never brought two things together: each curve's *activity*,
and the *hash order* the selection rule uses. If both were known at once, N could be tuned to include
or exclude particular high-activity curves — N would silently become a selection knob rather than a
size knob, defeating the leakage prohibition through the one parameter left open.

That claim is not asserted here, it is checkable: **no executable module in this directory — no
`.py` file — imports a hash library, references the selection function, or carries the frozen seed
literal.** They compute quartiles, mean, standard deviation and a projected total, and nothing else.
The preregistration's pilot-isolation test makes that permanent, parsing each module's AST rather
than scanning text.

The scope is *executable code*, not text, and that distinction is not a loophole — it is forced by
this very file. An earlier draft of this paragraph claimed no file here contained the hash function
at all, which was **false the moment it was written**, because the sentence naming the property
contains the name of the property. A prose description of a guard is not the guard. This project has
now hit the same edge three times: a supervisor held to making no network call by a text scan that a
comment tripped, an orphan artifact exempted by a filename that lied about its format, and now a
README whose claim about text was falsified by its own text. Check code as code.

## What these numbers are NOT

They are a **cost model**, not a finding. The projected ~6.4M signatures for N = 5,000 carries about
±29% at 95%, and that width is the 80-curve pilot's own error, not the sampling draw — at N = 5,000
the draw itself contributes only a few percent. Nothing downstream may treat any figure here as an
observation about the cohort; the cohort has not been observed. Stage 4 has never run.

One number here is a corrected mistake, kept deliberately: the first serial probe reported clean
results at 40 calls/s requested and was measuring **itself**. Latency sat flat at ~171 ms and
1/0.171 = 5.85, exactly the plateau. The tell was in the latency column, not the throughput one.
