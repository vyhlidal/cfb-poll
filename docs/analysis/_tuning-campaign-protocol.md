# The hyperparameter campaign, and the calibration diagnosis

**Date opened:** 2026-08-12
**Status:** PROTOCOL PRE-REGISTERED. No number below the protocol had been read when
the protocol was written; this file was committed with the results sections empty
and filled in afterwards, so the commit history is the evidence that the rule came
first (`git log --follow docs/analysis/tuning-campaign.md`).

Every constant in `configs/default.toml` is still at its unfitted starting value.
The file says so of itself: *"Nothing in this file has been fitted yet — the model
is not implemented."* The grids have never been searched. The publication gate
honestly fails all five decidable criteria
([`demo/backtest-2021-2023.md`](../../demo/backtest-2021-2023.md)):

| Criterion | Threshold | Observed | Verdict |
|---|---|---:|---|
| Straight-up accuracy | >= 70.00% | 69.21% | FAIL |
| Margin MAE | <= 12.8 | 13.019 | FAIL |
| Margin RMSE | <= 15.8 | 16.549 | FAIL |
| Max decile calibration deviation | <= 5.0 pp | 13.67 pp | FAIL |
| Retrodictive violations vs every scored system | at or below all | 0.2015 | FAIL |

This campaign has two jobs and they are separable. Close as much of that gap as the
data honestly allows, and diagnose why the calibration miss is *asymmetric* — a
stated 25% chance wins about 16% of the time, which is why raising σ made it worse
rather than better.

---

## PART 0 — THE PROTOCOL, fixed before any number was read

### 0.1 Objective and tie-break

**Objective:** walk-forward MAE on the tune seasons **2021-2023**, headline window
(`weeks >= [publication].headline_start_week`, i.e. weeks 5+), segment
`fbs_vs_fbs`. Lower is better.

**Tie-break, in order:** Brier, then retrodictive violation rate.

This is the same rule ADR 0006 used to choose the fit universe, and it is chosen
again here for exactly that reason: a project that changes its selection rule
between studies is choosing the rule to fit the answer. MAE is the metric every
game contributes to, so it is the one that moves for a reason rather than by three
games out of 1,585 (`demo/backtest-2021-2023.md` makes that argument about SU
accuracy and it holds here).

The headline ordering `schedule_odds` predicts through its Power source
(`[resume].power_source = "L3"`), so its predictive row **is** L3's row by
construction. The grid is therefore scored on `l3` and the numbers transfer
without an assumption. Violations, which are about the ordering rather than about
Power, are recomputed with the full system list for the frozen winner only.

### 0.2 Search space

Exactly the grids the config already publishes, plus the two mode switches the
config marks as unsearched:

| Parameter | Values | Cells |
|---|---|---:|
| `[margin].c` | `c_grid` = 18, 20, 22, 24, 26, 28, 30, 32 | 8 |
| `[margin].beta_w` | `beta_w_grid` = 0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8 | 13 |
| `[garbage_time].mode` | `connelly` \| `strict` | 2 |
| `[margin.prediction_compression].enabled` | `true` \| `false` | 2 |

`[ridge].l1_grid` and `l2_grid` are **not** searched here: λ is cross-validated
per fit, every week, grouped on `game_id`. Re-tuning a grid that is already
selected inside the fit would be selecting λ twice.

`[garbage_time].mode = "leverage"` cannot be searched: it raises
`NotImplementedError` because it needs a win-probability model this project does
not have. That is recorded as a hole in the search rather than a value that lost.

`[margin.prediction_compression]` is configured and, per the independent review
(S9), implemented **nowhere in `src/`**. Searching it "on/off" therefore requires
implementing it first. It is implemented as the config's own published formula and
nothing else: for a raw predicted margin `M` with `|M| > threshold`,
`M* = sign(M) * (21 + (1/α)·[(|M| − 20)^α − 1])`, continuous at the threshold.

### 0.3 Cost, and how the grid is walked

Measured before the search: one three-season backtest scoring `l3` alone takes
**14.4 s** with the archive already loaded. The full 8 × 13 = 104-cell C × β_w
grid is therefore roughly 25 minutes at one cell per process, and much less with
the games and plays frames loaded once and shared. **The full grid is affordable,
so the full grid is run** — no subsampling, no coarse-then-refine, no opportunity
to stop early on a number one likes.

The mode switches multiply it: 104 × 2 × 2 = 416 cells. The two modes are searched
as a **second stage on the C × β_w optimum plus its neighbourhood**, and the full
416 is run only if the second stage moves the optimum. Both stages are reported in
full whatever they show.

### 0.4 Validation, and the rule that can kill the campaign

The winner of the tune-season search is **frozen first, in writing, in this file**,
and only then evaluated on **2024**. That evaluation happens ONCE.

**Adoption rule, stated before the validation number was computed:** the tune-season
winner is adopted only if, on 2024, it improves MAE against the starting values **or
does not worsen it beyond noise**. The noise floor is fixed here at **0.055 points of
MAE**, which is not an invented number: it is the margin by which ADR 0006 chose the
fit universe and explicitly labelled "inside the noise floor for three seasons". The
same quantity cannot be noise when it decides one thing and signal when it decides
another.

**If tune and validation disagree, the config KEEPS the starting values and this
campaign reports failure.** That sentence is the whole point of writing the protocol
down first.

**2025 stays locked.** Nothing in this campaign reads it. The harness refuses it
without `unlock_holdout=True` and no code path here passes it.

---

## PART 0.5 — THE CALIBRATION DIAGNOSIS PROTOCOL

Four candidate fixes, **declared before any of them was run**, each tested
walk-forward on the tune seasons under the same harness:

1. **Student-t game margins instead of normal.** Fit ν on the tune-season
   walk-forward residuals; propagate to every win probability (L4 résumé,
   schedule odds, and the harness's own scoring).
2. **Heteroscedastic σ.** Does residual variance depend on the predicted absolute
   margin — i.e. on how big a mismatch the model thinks it is looking at? Fit
   σ(|m̂|) as a simple published function if and only if the data support one.
3. **Home field.** `[homefield].method = "home_and_home"` and
   `fit_both_and_publish = true` select nothing today; the live `h` is always the
   regression coefficient. Implement the Pasteur home-and-home estimator for real,
   compare the two estimates, and test whether per-venue or neutral-site handling
   closes any of the asymmetry.
4. **Favourite-longshot.** Is the asymmetry concentrated in the big-mismatch
   deciles? Slice the residuals by predicted margin and show it.

**Adoption rule, fixed in advance:** a fix is adopted only if it cuts the maximum
decile deviation by **>= 2.0 pp on the tune seasons AND holds direction on 2024**.
Anything that fails that rule is documented as **diagnosed-but-unfixed**, with the
evidence, and the config does not move.
