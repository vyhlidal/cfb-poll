# ADR 0005 — The headline poll is ordered by schedule odds

- **Status:** Accepted
- **Date:** 2026-08-12
- **Decided by:** the project owner, on the evidence of
  [`docs/analysis/headline-ordering-study.md`](../analysis/headline-ordering-study.md)
  (committed at `784ab50`)
- **Supersedes:** the ordering adopted in commit `50f4058` ("Flip the poll: L4
  résumé is the headline, Power beside every team")
- **Full reasoning:** the study, in full. Research report 02 §2.4, §2.10, §3.4,
  §3.5, §3.6, §5.2

## Decision

> **The headline poll is ordered by SCHEDULE ODDS: `−log10 P(W ≥ W_t)`, the
> probability that a team of published reference quality `q_ref` would have gone at
> least this well against this exact schedule. The promise is "the harder it was to
> do what you did, the higher you go" — measured, never assumed.**

`[publication].headline_ordering = "schedule_odds"`. The estimator is
[`src/cfbpoll/model/schedule_odds.py`](../../src/cfbpoll/model/schedule_odds.py),
built for the study as candidate C. Per-game win probabilities are
`p_g = Φ((q_ref − Power_o + h·s_g)/σ)` and the tail is the **exact**
Poisson-binomial convolution — no Monte Carlo, reproducible bit for bit.

**Nothing was removed from the page.** The L4 résumé on the points scale, its
margin-aware variant, its saturation flag, and the L3 Power rating with the
résumé-minus-power gap are columns on every published row, in every artifact, on
both surfaces. What changed is which column sorts the table.

## The owner's rationale, preserved

> An unbeaten Group of Five team probably would not survive a Big Ten schedule —
> but that must be a **scientific answer derived from on-field data, not an
> assumption**. Assuming it is how you get AP-poll-style conference bias.

That sentence is the whole decision, and it cuts in both directions at once. It
rules out the ordering that made an unbeaten team untouchable regardless of what it
played, and it rules out any ordering that reaches the same conclusion by knowing
which league a team is in.

Schedule odds satisfies it exactly. Nothing in the computation knows what a
conference is; opponent quality arrives only as a Power rating fitted from results,
and the answer is an *output*. In 2023 that output is a 13-0 Liberty at **#10**,
below a 12-1 Georgia at **#7** — the same direction as the intuition, arrived at
from Liberty's actual opponents rather than from the letters "C-USA". And the model
publishes the head-to-head beside it: Georgia by about 8 on a neutral field,
Liberty wins that game roughly 3 times in 10.

## The evidence, condensed

Three orderings, computed off the **identical** Power source, fits and windows in
every cell, so every difference below is a difference between ordering *rules*.
Seasons 2021-2024, tune on 2021-2023, validate on 2024; 2025 never loaded.

| | ordering | rank key |
|---|---|---|
| **A** | wins-based résumé, margin variant breaking ties among saturated teams | `(−resume, −resume_margin, team)` |
| **B** | margin-aware résumé for everyone | `(−resume_margin, team)` |
| **C** | **schedule odds — adopted** | `(tail, mid_p, team)`, `tail = P(W ≥ W_t)` |
| *P* | *L3 Power itself — not a candidate; the calibration mark for the prediction axis* | `(−power, team)` |

| Axis | Winner | Margin | n |
|---|---|---|---|
| Retrodictive violations, final ranking | **A ≈ C** | tune 0.1997 / 0.2139 / 0.2011; validate 0.1930 / 0.2105 / 0.1942 | ~3,056 games |
| Retrodictive violations, all weeks, both surfaces | **A ≈ C** | **B worse in 16 of 16 cells** | 8 season×surface cells |
| Forward ordering accuracy | **B** | 0.6822 vs A 0.6624 and C 0.6626 pooled | 9,433 games |
| Retro-convergence, all teams | tie | all three decline monotonically in N | 4 seasons |
| **Retro-convergence, unbeaten teams** | **C ≳ B ≫ A** | **C 1.343, B 1.269, A 0.395 places** | pooled, weeks ≥ 5 |
| Case plausibility, 2023 board | **C** | B ranks 8-4 Kansas State #12, 7-5 Texas A&M #23 | qualitative |
| Week-over-week stability | **B** | 5.03 vs A 6.22 and C 6.25 | pooled |
| Postseason (CFP / NY6 / bowls) | **none** | n = 14 / 4 / 74 | **unusable; do not quote** |
| `q_ref` sensitivity (C only) | **safe** | τ ≥ 0.985, ≤ 1 top-25 change across a 16-point q_ref swing | 4 seasons × 3 alternatives |

**The axes disagree in exactly one direction and it is not subtle.** B wins the two
axes that reward being a good *predictor* and loses the axis that rewards being a
good *résumé*, moving toward the pure Power reference on both counts. That is not a
mixed result. It is a coherent one: margin makes a rating better at what Power is
already for, and Power is already published beside every team.

A and C are statistically tied on the résumé axis, tied on league-wide convergence,
and tied on stability. **They differ on exactly one thing: what can happen to an
unbeaten team.**

## What was rejected, and why

### A — the wins-based résumé. Rejected: retro-inert for unbeaten teams.

`E[W|q]` approaches `n` from below, so an undefeated team has **no finite root** and
the published bracket `q_bounds = [−60, 60]` is where the estimate is truncated.
Every unbeaten team therefore lands on **exactly +60**, whatever it played. +60 is
not a function of the schedule, so it is not a function of the Power window either,
so substituting end-of-season Power for through-week-N Power **cannot change it**.

The retroactive re-ranking of constraint 4 is one substitution into `Power_{o_g}`.
For a saturated team there is nothing downstream of `Power_{o_g}` left to move.

That is a structural fact, not a tuning outcome, and it has two consequences the
study verified rather than argued:

1. **Under A no team with a loss can ever be ranked above an unbeaten team**, on
   either surface, in any season. Observed count of such inversions across all
   eight season×surface cells: **zero**. Not "rare" — zero, forever, because the
   ordering makes it impossible.
2. From **week 11 of 2023 onward, A moved no unbeaten team at all** between the
   live and hindsight surfaces. C is the only candidate still moving them in week
   15.

So the owner's own self-correction — *"if by week 13 it's clear that Liberty's
schedule is actually quite tough in weeks 1-5, maybe things change?"* — **cannot
fire under A**. If September turns out to have been hard, A cannot say so; if it
turns out to have been soft, A cannot say that either. The feature described as the
project's most differentiated product does not function for precisely the teams
whose ranking is most argued about.

A also produced **Cincinnati #1 in 2021** — ahead of Alabama, Georgia and Michigan,
purely because it was the only unbeaten team in the country, and *forced*, not
chosen. B, C and the committee all said #4. The committee agreement is a
coincidence worth noticing and explicitly **not** a target (report 02 §5.5: fitting
toward committee agreement reintroduces human-poll bias through the back door).
What it does show is that A's #1 was a position no independent judge reached.

A remains fully implemented, fully published on every row, and reachable by setting
`headline_ordering = "L4_resume"`. A choice that cannot be switched back is not a
choice.

### B — the margin-aware résumé for everyone. Rejected: loses the résumé axis, 16/16.

B is worse than both A and C on retrodictive violations in **all sixteen** season ×
surface cells. It genuinely wins forward ordering accuracy by about 2 points and
genuinely wins week-over-week stability, and both of those are real and were not
waved away — but look at where B sits relative to the pure Power rating on each
axis it wins (forward: 0.6624 → 0.6822 → 0.6918; violations: 0.1997 → 0.2139 →
0.2281). **B is not a better résumé. B is a worse résumé that has partially turned
into a power rating**, and the project already publishes a power rating that does
that job better, beside every team, every week.

The 2023 board settles it without any statistics. B ranks an **8-4 Kansas State
twelfth** and a **7-5 Texas A&M twenty-third**, above an 11-1 James Madison and a
13-0 Liberty. That is not a marginal defect; it is what the ordering is *for*.
`resume_margin` rewards winning big and losing close, so a team that got blown out
by nobody and blew out several people outranks a team that simply kept winning. A
poll whose promise is "who earned it" cannot put a 7-5 team ahead of an 11-1 team
and survive contact with a reader.

B stays exactly where it was: **published in the same table**, as the second
résumé variant and as A's tie-break among saturated teams — the one job for which
its smoothness is useful and its desert defects are invisible.

## The price of C, stated plainly

1. **An unbeaten team can finish behind a one-loss team, and that will require
   explaining every year.** It is the direct consequence of the promise. The
   explanation is on the page: the tail probability, the reference team it was
   measured against by name, and the Power column.
2. **One published constant that A did not have.** `q_ref` is the Power rating of
   the 25th-ranked Power team that week, the least flattering defensible reading of
   ESPN's "average Top-25 team", and a single team that can be *named* each week.
   Study §9 measured the ordering's sensitivity to it rather than asserting it was
   fine: across a 16-point swing in reference quality, Kendall's τ never fell below
   0.985, the mean rank change never reached one place, and at most one team
   entered or left the top 25. 2023 Liberty spans #8 to #12 across that whole swing
   and never reaches Georgia at #7 under any choice. The probability *values* move
   by orders of magnitude, which is exactly why the value is published rather than
   the rank alone.
3. **C loses forward ordering accuracy to B by about 2 points.** Accepted, and for
   a stated reason: forward accuracy is a prediction metric, and the headline poll
   is not the instrument this project ships for prediction. L3 Power is, and it
   beats all three orderings on that axis.

C also inherits the invariance that makes the résumé's zero point harmless: shift
every Power rating by a constant and every rank-derived `q_ref` shifts with it, so
no probability moves at all. Only the `fixed` method breaks that, which is why it
is not the default.

## What this changes in the code

Small, and of a known shape — the study predicted it in §11 and it held:

- `retro.cell` computes `schedule_odds.fit` beside `l4_resume.fit`, off the same
  Power source and the same windows.
- The published row gains `odds_key`, `tail_p`, `mid_p`, `expected_wins`,
  `surprise`, `q_ref` and `q_ref_team`. It loses nothing.
- The one sort rule moves to `publish/poll.ORDER_KEYS` and is keyed on
  `headline_ordering`.
- `schedule_odds` joins the permanently-scored backtest systems, beside `resume`.

Nothing in the résumé, the Power blend, the L1/L2/L3 stack, or the retroactive
substitution changed, because schedule odds depends on opponent quality through
exactly the same single channel the résumé does.

**Provisional labelling and `headline_start_week = 5` were not revisited and are
unchanged.** Weeks 1-4 still publish clearly-labelled provisional output.

## Where this decision is weak

Stated so it is not read as stronger than it is, and reproduced from study §10.4:

- **Four seasons.** The forward-accuracy gap between B and the other two (2 pp on
  9,433 games) is comfortably significant. **The gap between A and C on violations
  (0.1 to 0.5 pp) is not, and nothing here claims it is.** A and C are tied on
  that axis, and what decided between them was the structural finding.
- The postseason axis is unusable at current sample sizes (14 CFP games, 4 non-CFP
  NY6 games) and 2021-2022 cannot contribute to it at all, because the archive
  carries no postseason rows for those seasons.
- 2024 is the validation season. Every conclusion holds on it with the same sign,
  but it was consulted once, in one pass, and must not be consulted again for a
  re-tune.
- 2025 is untouched and stays locked.
- **No bootstrap intervals anywhere.** `model/bootstrap.py` is still a stub, so the
  study reports point estimates and sample sizes and leaves the reader to judge.

## How to revisit it

The evidence regenerates in about 25 seconds:

```
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run python scripts/headline_ordering_study.py --out out/ordering-study
```

Both orderings are scored side by side in every backtest run, permanently, so the
comparison stays live rather than frozen in this document:

```
uv run cfbpoll backtest --systems schedule_odds,resume,l3,l2,l1,colley,srs,elo,walker,winpct
```

If schedule odds ever loses the violations axis to the résumé by more than noise,
this ADR should be reopened, and the rule is that it gets reopened on numbers.
