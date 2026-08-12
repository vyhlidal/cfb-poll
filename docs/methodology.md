# Methodology

> **PLACEHOLDER.** This page will carry the published math — every equation,
> every constant, every week — because constraint 5 requires it. Until then, this
> is a map to the research that specifies it.
>
> **Built so far:** the L2 results core, the **L4 résumé rating (the headline
> poll)**, and the R(N, K) retroactive surface. **Not built:** L1 efficiency and
> the L3 blend, so opponent quality inside the résumé is L2 rescaled to points and
> every artifact says so (`power_source = "L2"`, `power_version = "v0"`). Real
> output, with the reasoning written out, is under [`demo/`](../demo/).

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
| **L1 — Efficiency core** | Ridge on garbage-time-filtered play-level EPA, one offense and one defense coefficient per team, plus home field | Opponent-adjusted offensive and defensive ratings in EPA/play |
| **L2 — Results core** | Ridge on game-level compressed scoring margin (`tanh` cap plus explicit win premium) | Opponent-adjusted team rating in points |
| **L3 — Power rating** | Walk-forward stacked blend of L1 (rescaled to points) and L2 | Predictive: expected margin vs an average team on a neutral field |
| **L4 — Résumé rating** | Root-solve for the quality `q` whose *expected* results against this exact schedule equal the *actual* results, using L3 for opponent quality | Retrodictive: "these results are what a +18.4 team would produce against this schedule" |

**The headline poll is L4 (Résumé). L3 (Power) is published beside it, always,
with the gap shown.** Résumé is the poll; Power is the engine.

The response transform, which is where the two most contested numbers live:

```
s = C · tanh(m / C) + β_w · sign(m)
```

`C = 24` bounds the value of running up the score without discarding margin.
`β_w = 3.0` is the win premium — the discontinuity at zero that makes this a
football ranking rather than a scoring-margin ranking. Both start values and both
grids are in [`configs/default.toml`](../configs/default.toml) with their
citations.

The résumé root-solve, which is where retroactive re-ranking comes from:

```
μ_g(q) = q − Power_{o_g} + h·s_g
P_g(q) = Φ( μ_g(q) / σ )                σ = 15.3
Résumé_t = the unique q* with Σ_g P_g(q*) = actual wins
```

Résumé depends on opponent quality **only** through `Power_{o_g}`. Substitute
through-week-N Power ratings for the live ranking `R(N,N)`; substitute
end-of-season Power ratings for the hindsight ranking `R(N,final)`. Nothing else
changes. That is constraint 4 in one substitution.

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
