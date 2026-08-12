# `fit_universe`: the sensitivity nobody published, and the decision

Computed by `scripts/fit_universe_study.py`; every number below is in
`fit-universe-sensitivity.json`.

> **PROVENANCE.** Every number below was computed against `configs/default.toml`
> as of the run recorded in the sibling `.json` (`provenance.config_sha256`). The
> constants moved on 2026-08-12 when the hyperparameter campaign fitted C, beta_w
> and both mode switches ([ADR 0007](../adr/0007-tuned-constants.md)), so these
> numbers reproduce under *that* config and not under today's. They are left exactly
> as they were: evidence quietly edited to agree with a later decision is not
> evidence.

`[model].fit_universe` decides which games enter the design matrix at all. Until
2026-08-12 it was argued from report 02 §3.7 and never measured, and the
[independent review](./fresh-eyes-review.md) (S4) put the objection precisely:

> `q_ref` moves JMU by one place. `fit_universe` moves it three. Neither has a
> published sensitivity table, and neither is presented to the reader as a choice
> at all.

The review's standard is the one applied here: run §9's exact machinery — mean rank
delta, max delta, Kendall's tau, top-25 membership changes — and **any parameter
whose tau against the default falls below the 0.985 that `q_ref`
achieves is a dial, not a convention, and must be labelled as one.**

---

## 1. What each universe actually fits (2023 through week 10)

| Universe | Games in the window | Teams in the fit | Non-FBS teams | λ | σ | Median rating SE |
|---|---:|---:|---:|---:|---:|---:|
| `all` — every completed game, all divisions | 3,083 | 704 | 571 | 0.5 | 16.97 | 2.34 |
| `model` — at least one FBS or FCS participant **(incumbent)** | 1,205 | 301 | 168 | 0.5 | 17.44 | 1.88 |
| `fbs_vs_fbs` — both participants FBS | 546 | 133 | 0 | 2 | 17.14 | 1.22 |

The incumbent fits **168 non-FBS teams** alongside the 133 FBS
ones, which is the number the review's mechanism argument turns on. Widening to
`all` adds 403 more; narrowing to
`fbs_vs_fbs` removes every one of them.

## 2. Does it move the ranking? Yes, and by more than `q_ref` does

| Alternative | Kendall's τ vs incumbent | Mean \|Δrank\| | Max \|Δrank\| | Top-25 changes | Verdict |
|---|---:|---:|---:|---:|---|
| `all` — every completed game, all divisions | 0.9863 | 0.80 | 5 | 1 | a convention |
| `fbs_vs_fbs` — both participants FBS | 0.9344 | 3.32 | 17 | 2 | **A DIAL** |

**The review's own example does not reproduce, and the reason is worth stating.**
It reported James Madison moving #7 → #4 under `fbs_vs_fbs`. On this build JMU is
#4 (all) / #4 (model) / #4 (fbs_vs_fbs) — it does not move at all. The review measured against a baseline this
repository no longer has: σ was the 15.3 constant rather than an estimate, and the
review's own §S4 baseline used in-sample blend weights. The SENSITIVITY is real and
larger than `q_ref`'s, which is the finding; the particular team it landed on was a
property of the configuration it was measured under. The movers below are where it
shows up now.

Dropping FCS from the fit gives τ = **0.9344**, against the
0.985 floor the `q_ref` sweep never dipped below. By the
project's own published standard that makes `fit_universe` **a dial**, and it is now
labelled as one in `configs/default.toml`.

Biggest movers under `fbs_vs_fbs`:

| Team | Incumbent | FBS-only |
|---|---:|---:|
| UCF | #66 | #83 |
| Northern Illinois | #97 | #80 |
| Buffalo | #113 | #97 |
| Stanford | #80 | #65 |
| Nevada | #124 | #110 |
| California | #78 | #91 |

## 3. The mechanism the review named, measured

The review's account: ridge shrinks every coefficient toward the mean of the fit
universe; thinly-connected FCS teams are shrunk hardest and are pulled *up* toward a
mean far above their level; the FBS teams that beat them are pulled *down*; the net
effect compresses the FBS-over-FCS gap, and the compression lands hardest on the
teams whose schedules hold the most near-FCS opponents — which is to say on G5
teams. **Ridge-toward-zero on a mixed-division universe is not neutral with respect
to the G5-versus-P4 question.**

Rating differences are invariant to the zero point of a fit, so the table below is
in gaps rather than levels. Conference labels are an audit lens and never a feature.

| Universe | Mean FBS − mean FCS | Mean P4 sample − mean G5 sample |
|---|---:|---:|
| `all` — every completed game, all divisions | 11.14 | 11.23 |
| `model` — at least one FBS or FCS participant **(incumbent)** | 10.34 | 10.83 |
| `fbs_vs_fbs` — both participants FBS | — | 9.64 |

**The direction is the review's, and the size is smaller than its framing suggests.**
Dropping the non-FBS teams narrows the P4-minus-G5 gap from 10.83 to 9.64 points
(-1.19). The mixed-division universe is therefore
mildly favourable to G5 teams, exactly as the review says — and the caveat is now a
published number rather than an unstated property.

## 4. Which universe is actually better? The backtest decides

Decision rule, fixed before the numbers were read: **lowest walk-forward MAE on the tune seasons over the published window, retrodictive violations as the tie-break; fixed before the numbers were read**. The
evaluation universe is FBS-vs-FBS in every row, so the same games are being predicted
in all three columns; what changes is what the fit was allowed to see.

| Universe | n | SU % | MAE | RMSE | Brier | Calib. dev. | Violations (headline) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `all` — every completed game, all divisions | 1585 | 69.15 | **13.028** | 16.549 | 0.1976 | 13.94 pp | 0.2019 |
| `model` — at least one FBS or FCS participant **(incumbent)** ✅ | 1585 | 69.21 | **13.019** | 16.549 | 0.1980 | 13.67 pp | 0.2015 |
| `fbs_vs_fbs` — both participants FBS | 1585 | 69.65 | **13.074** | 16.567 | 0.1989 | 11.11 pp | 0.2006 |

**Winner: `model`.**

**AND THE RESULT IS MIXED, WHICH IS THE HONEST HEADLINE.** The decision rule was
fixed before the numbers were read and the incumbent wins it — by 0.055 points of MAE over
`fbs_vs_fbs`, which is well inside the ~0.3-point noise floor for three seasons.
On straight-up accuracy, calibration deviation, retrodictive violations the narrower universe is AHEAD:
69.65% vs 69.21%, 11.11pp vs 13.67pp, 0.2006 vs 0.2015. A pre-registered rule that picks one
column while three others point the other way is a rule doing its job — the
alternative is choosing the criterion after seeing the numbers — but a reader
is entitled to know it was close and which way the other criteria fell.

The interesting one is calibration. Dropping the 168 non-FBS teams improves
the deviation the gate misses by the widest margin (11.11pp against 13.67pp) and it is still
nowhere near the 5.0pp threshold, which is consistent with the finding in
demo/backtest-2021-2023.md that the calibration miss is an asymmetry nobody
has diagnosed rather than anything the fit universe controls.

Report 02 §3.7 argued
for it from first principles — FBS-vs-FCS games are ~10% of the FBS schedule and
cluster in the weeks the model is most data-starved, and FCS-vs-FCS games are
what identify individual FCS coefficients rather than the pooled node that cost
ESPN 31 spots of Iowa State in 2013 — and the walk-forward numbers agree.

**That does not make it a convention.** It is a dial that happens to be set
correctly, which is a different claim and a weaker one, and the difference is
why this table exists. Narrowing to FBS-vs-FBS costs +0.055 points of MAE and
moves the ranking by a mean of 3.32 places.

## 5. What this does not settle

1. **Three seasons is a small sample.** Differences in MAE below roughly 0.3 points
   are not distinguishable within a single season, and these are pooled over three.
   The MAE spread across universes here is small enough that the honest statement is
   "no universe is clearly worse on prediction", and the ranking movement is the
   bigger effect.
2. **2024 and 2025 are untouched.** The validation season is not scored here and the
   holdout is locked. If this decision is ever revisited against them, that has to
   be said publicly (report 02 §5.1).
3. **The mechanism is measured at one week of one season.** §3's gap numbers are
   2023 through week 10. The direction is stable but the magnitude is not claimed
   to be.

```
uv run python scripts/fit_universe_study.py
```

Generated by `scripts/fit_universe_study.py` at 2026-08-12 - code `28bc665` - config sha256 `ab906806951a114b...`
