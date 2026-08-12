# Methodology

> **PLACEHOLDER.** This page will carry the published math — every equation,
> every constant, every week — because constraint 5 requires it. Until then, this
> is a map to the research that specifies it.
>
> **Built so far:** all four layers — L1 efficiency, L2 results, the L3 blend and
> the L4 résumé rating — plus the **schedule-odds ordering, which is the headline
> poll** (`model/schedule_odds.py`, adopted 2026-08-12, see
> [ADR 0005](adr/0005-headline-ordering.md)), our own expected-points model
> (`model/ep.py`) and the R(N, K) retroactive surface. Opponent quality inside
> both desert layers is L3 (`power_source = "L3"`, `power_version = "v1"`), with
> L2 kept available and stamped on the artifact whenever it is what actually ran.
> Every published rank carries a **90% interval** from a parametric bootstrap on
> the fixed schedule, and every Power rating carries a **standard error** from the
> ridge sandwich. Real output, with the reasoning written out, is under
> [`demo/`](../demo/).

## Where the real specification lives

Three research reports, dated August 2026, are the specification for this
repository. They are not summarised faithfully here; read them.

| Report | Covers | What to read it for |
|---|---|---|
| `01-data-sources.md` | Sources, terms, durability | The two-source split (CFBD weekly, SportsDataverse backfill), the 22-call Sunday job (§3.7), the terms analysis (§4.1), the append-only archive design (§5.4), the validation gates (§5.5) |
| `02-modeling-approaches.md` | The math | Survey of every major system (§2), the four-layer design (§3), the early-season problem (§4), the backtest plan (§5), and the build order (Appendix B) |
| `03-architecture.md` | Stack, compute, storage, repo | Python + uv (§3), why the clock is not GitHub's `schedule:` (§4), files-are-truth storage (§5), repo layout (§6.2), the challenge harness (§7.3), reproducibility engineering (§9) |

The five hard constraints and the banned-input table are in
[constraints.md](./constraints.md). The decisions already taken are in
[adr/](./adr/).

## The model in one screen

Four layers, all batch refits, all regularized (report 02 §1):

| Layer | What it is | Output |
|---|---|---|
| **L1 — Efficiency core** | Ridge on garbage-time-filtered play value from **our own** expected-points model (`model/ep.py`, never the archive's banned `EPA` column), one offense and one defense coefficient per team, plus home field | Opponent-adjusted offensive and defensive ratings in EPA/play |
| **L2 — Results core** | Ridge on game-level compressed scoring margin (`tanh` cap plus explicit win premium) | Opponent-adjusted team rating in points |
| **L3 — Power rating** | Walk-forward stacked blend of L1 (rescaled to points) and L2 | Predictive: expected margin vs an average team on a neutral field |
| **L4 — Résumé rating** | Root-solve for the quality `q` whose *expected* results against this exact schedule equal the *actual* results, using L3 for opponent quality | Retrodictive: "these results are what a +18.4 team would produce against this schedule" |
| **Schedule odds** | The exact Poisson-binomial tail `P(W ≥ W_t)` for a team of published reference quality `q_ref` against this exact schedule, using the same L3 opponent quality | Retrodictive: "a top-25-calibre team would have gone this well about 9 times in 100" |

**The headline poll is ordered by schedule odds, on `−log10 P(W ≥ W_t)`.** The
promise is *the harder it was to do what you did, the higher you go — measured,
never assumed*. **L4 (Résumé) and L3 (Power) are published beside it on every row,
always, with the résumé-minus-power gap shown.**

The résumé was the headline from commit `50f4058` until 2026-08-12 and the change
is recorded, with the evidence and the price, in
[ADR 0005](adr/0005-headline-ordering.md) and
[the headline-ordering study](analysis/headline-ordering-study.md). The one-line
reason: an undefeated team's résumé saturates at the published bracket, which is
not a function of the schedule and therefore not a function of the data window, so
the retroactive re-ranking of constraint 4 could not move an unbeaten team at all.
`[publication].headline_ordering` still accepts `"L4_resume"`, and switching it
regenerates the whole pipeline under the old ordering.

Schedule odds is the poll; Power is the engine; the résumé is the same accomplishment
stated on the points scale.

The schedule-odds key, which is where the poll's order comes from:

```
p_g   = Φ( (q_ref − Power_{o_g} + h·s_g) / σ )          per game
P_t   = P(W ≥ W_t),  W ~ PoissonBinomial(p_1 … p_n)     exact convolution, O(n²)
key_t = −log10(P_t)                                     higher is better
```

`q_ref` is the one free constant: the Power rating of the 25th-ranked Power team
that week, published every week together with **the name of the team it came from**,
so a reader can check it against the same week's table. Margin never enters this key
— not as a tie-break, not anywhere — and the module carries no margin column to leak
from.

The response transform, which is where the two most contested numbers live:

```
s = C · tanh(m / C) + β_w · sign(m)
```

`C = 32` bounds the value of running up the score without discarding margin.
`β_w = 7.0` is the win premium — the discontinuity at zero that makes this a
football ranking rather than a scoring-margin ranking. Both values and both grids
are in [`configs/default.toml`](../configs/default.toml) with their citations.

**Both are fitted rather than cited.** They were the research report's 24 and 3.0
until 2026-08-12, when the full C × β_w × garbage-time × prediction-compression
factorial was searched on 2021-2023 under a protocol committed before any number
was read, and the winner validated once on 2024
([ADR 0007](adr/0007-tuned-constants.md)). One caveat travels with them: the entire
416-cell search spans 0.135 points of MAE against a gate gap of 0.219, so these
constants are not what stands between the system and its thresholds.

**`C = 32` used to sit on the top of its own grid, and it no longer does.**
Campaign 2 widened `c_grid` under pre-registration all the way to `inf` — the
identity response, the limit of the family, so the grid cannot produce another
corner — and searched `β_w` to 12. The optimum of that widened grid is `c = inf`,
`β_w = 12`, which improves MAE on both the tune seasons and 2024 and **is not
adopted**: combined with the same campaign's accumulation-window change it makes
MAE worse than either alone, and a clause fixed before any number was read blocks
it. It also makes calibration substantially worse and moves the poll far enough to
be a *dial* rather than a convention. The full result, and the argument for
re-opening it in a campaign of its own, are in
[`campaign-2.md`](analysis/campaign-2.md) and [ADR 0009](adr/0009-accumulation-window.md).

The résumé root-solve, which is where retroactive re-ranking comes from:

```
μ_g(q) = q − Power_{o_g} + h·s_g
P_g(q) = Φ( μ_g(q) / σ )                σ = ESTIMATED, see below
Résumé_t = the unique q* with Σ_g P_g(q*) = actual wins
```

`σ` is **not the constant 15.3**. Since 2026-08-12 it is the root-mean-square
walk-forward residual of this system's own margin predictions, over the
out-of-sample games of **the last three weeks** — `[resume].sigma_trailing_buckets`
— published every week beside the number of games it came from
(`[resume].sigma_estimator`). 15.3 — the Prediction Tracker band for good public
models — survives as the thin-window fallback and as a floor, which is what it is
actually good for. The reason is the independent review's S6: 15.3 is the residual
SD around a *good public model's* prediction, and using it as the denominator of
every probability this poll publishes asserts a precision this system has not
demonstrated.

**The window is trailing rather than cumulative, and that is the fix that closed
the calibration diagnosis.** Estimating σ on every game of the season so far made
the calibration criterion *worse*, and the reason turned out to be the shape of the
window rather than the estimator: the ratings feeding σ and feeding the affine
points calibration improve as the season goes on, so a σ fitted on weeks 2-9
over-covers week 10 and a slope fitted on weeks 2-9 under-scales it. Campaign 1
diagnosed that and deliberately did not act on it; campaign 2 pre-registered the
trailing window and it worked. The slope of actual margin on predicted goes from
1.1492 ± 0.0437 to 1.0329 ± 0.0398 on the tune seasons — indistinguishable from
one — and from 1.2428 to 1.0222 on 2024, with the maximum decile deviation falling
11.28 pp → 7.37 pp and 15.82 pp → 8.12 pp. **The gate threshold is 5.0 pp and it
still fails.** The diagnosis is
[`tuning-campaign.md`](analysis/tuning-campaign.md) §5; the fix, its cost of 0.028
points of MAE, and the C grid that won on MAE and was blocked by the same campaign's
interaction clause are in [`campaign-2.md`](analysis/campaign-2.md) and
[ADR 0009](adr/0009-accumulation-window.md).

**A trailing window is not a relaxation of the out-of-sample rule.** Every game in
it was predicted before it was scored, by a fit that had not seen it. Fitting either
estimator on the *training* window is a different thing entirely, costs L2 0.44
points of MAE, and is not done.

Both desert layers depend on opponent quality **only** through `Power_{o_g}` (and,
for schedule odds, through `q_ref`, which is itself read off Power). Substitute
through-week-N Power ratings for the live ranking `R(N,N)`; substitute
end-of-season Power ratings for the hindsight ranking `R(N,final)`. Nothing else
changes. That is constraint 4 in one substitution.

**With one exception, and it is the exception that moved the headline.** `Σ_g P_g(q)`
approaches `n` from below, so an undefeated team has no finite root and lands on the
published bracket `q_bounds = [−60, +60]`. `+60` is not a function of the schedule,
so the substitution above has nothing to act on and an unbeaten team's résumé rank
cannot move between the two surfaces. A tail probability has no such degeneracy:
`P(W ≥ n) = Π_g p_g` is finite, strictly positive and strictly ordered by schedule
difficulty. Measured on 2023, over the last five published weeks: the résumé ordering
moved 0 of 26 unbeaten-team rows; schedule odds moved 7.

## Why the estimator is what it is

The largest published head-to-head comparison — eight ranking methods, 56 NCAAF
seasons, 20-fold cross-validation — found that "the least squares and random
walker methods have significantly better predictive accuracy at the 95%
confidence level than the other methods considered," and that for college football
score-differential implementations beat win-loss-only ones (report 02 §2.15).
Least squares on margin is L2; L1 generalises it to the play level. The random
walker is in our baseline set precisely because it is the one that might beat us.

## What this page will contain when the model exists

- Every equation above, with the fitted values for the current week
- λ, C, β_w, h, k, w₁, w₂, σ — published every week, from `model_params.json`
- The self-classification the field already uses: this system is roughly
  `Adv/Hom/Mix/264` in David Wilson's taxonomy (advanced mathematics; home field
  and score information; mixed predictive/retrodictive intention; 264 teams)
- The honest reproducibility claims table from report 03 §9.5 — including the
  ones we cannot make, such as byte-identical replay on arbitrary hardware
- What we deliberately do not do, and what that costs us: no individual player
  availability modelling, no matchup interaction terms in v1, no recency weighting
  by default

## Status

Nothing above is running. See the [README](../README.md) status section for what
exists versus what is coming, and report 03 §10 for the build order.
