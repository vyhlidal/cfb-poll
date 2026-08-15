# Audit: the 2025 Projection had Colorado 21st and the season had them 102nd

**Date:** 2026-08-15
**Scope:** read-only. No model code, no fixture and no published artifact was changed by this
audit. Every number below was recomputed from the archive at the repository state named in
`demo/2025-projection-grading.md` (`projection-1.0.0`, code `1fade96666`).
**Prompted by:** the owner's challenge, that a model claiming to be free of media bias should
not have had Colorado 21st going into 2025, and that either the projection or the poll is
broken.

---

## The verdict in four sentences

**Colorado at #21 is a defensible, data-driven output of the published recipe.** Every one of
the four terms fired with the correct sign, none was imputed, and the offseason terms moved
Colorado *down* nine places from where last season's rating alone would have put them. The
sportswriters had Colorado unranked in their August 2025 top 25 and the model had them 21st,
so on this team the model was *higher* than the press, which is the opposite of the failure
mode the challenge assumed.

**Two things are genuinely broken, and both are in the measurement layer rather than the
ranking.** First, the grading page compares `projected_power` and `actual_power` across two
different definitions of Power, which manufactures a uniform seven-point over-projection and
almost the whole of the published "last season's rating was TOO STRONG, this season wanted
0.66x" verdict. Second, the coaching term reads a CFBD file pulled after the season, so five
teams in the 2025 projection were docked 2.33 points for a firing that had not happened in
August. Neither defect changes Colorado's rank. Both change what the grading page is entitled
to say.

---

## Part 1. Forensics on Colorado 2025

### 1.1 The row, term by term

The recipe is `P_hat = a + phi*(Power_{Y-1} - mean) + b_rp*(usage - mean) + b_hc*coach + b_pf*z(portal_net)`,
with the coefficients published on the 2026 card and byte-identical here.

| term | input | centred value | coefficient | contribution |
|---|---:|---:|---:|---:|
| intercept | | | | **+14.979230** |
| `prior_power` | 33.065348 (2024 final Power) | +18.307096 | 0.68264463 | **+12.497241** |
| `returning_production` | 0.196 usage | −0.202709 | 7.08291777 | **−1.435771** |
| `coaching_change` | 0 (Deion Sanders stayed) | 0 | −2.33456789 | **0.000000** |
| `net_portal` | −1 (34 out, 33 in) | z = +0.627634 | −0.41060136 | **−0.257707** |
| | | | **projected Power** | **25.782992** |

Ranked 21st of 136. The centring constants for 2025 are `prior_power_center = 14.758252`,
`returning_usage_center = 0.398709`, `coach_change_rate = 0.261194`,
`portal_net_center = −5.852941`, `portal_net_sd = 7.732116`. All four imputation flags on
Colorado's row are 0: nothing about this team was filled in.

### 1.2 Did returning production catch the exodus? Yes, and it was not enough

This is the crux of the challenge, and the answer is not the one either side expected.

The offence-only limitation did **not** mask the departure of Shedeur Sanders and Travis
Hunter. Colorado's 2025 returning usage was 0.196, the 33rd lowest of 134 FBS teams, and the
split makes the QB loss unmistakable in the data: **returning passing usage 0.010**, receiving
usage 0.231, rushing usage 0.488. The term saw the exodus, priced it, and debited Colorado
1.44 points.

The reason 1.44 points did not matter is arithmetic, not coverage. Across the 136 projected
teams:

| term | min | max | span | sd |
|---|---:|---:|---:|---:|
| `prior_power` | −21.552 | +21.000 | **42.552** | 8.998 |
| `returning_production` | −2.760 | +3.721 | **6.481** | 1.587 |
| `coaching_change` | −2.335 | 0.000 | **2.335** | 1.022 |
| `net_portal` | −0.842 | +1.601 | **2.443** | 0.411 |
| projected Power | −9.399 | +34.438 | 43.837 | 9.784 |

The three offseason terms together command about 11 points of range against `prior_power`'s
42.6. A team that arrives with the 12th-best rating in the country cannot be argued out of the
top 25 by terms whose entire dynamic range is a quarter of the prior's. Colorado needed 16.3
points of correction, measured like for like on the recipe's own response scale per §2.1. The
returning-production term's whole span, end to end, is 6.5.

Walking the recipe up in layers makes the mechanism explicit:

| team | naive carryover | mean reversion only | full recipe | 2025 actual |
|---|---:|---:|---:|---:|
| Colorado | 12 | 12 | **21** | 90 |
| Penn State | 5 | 5 | 4 | 25 |
| South Carolina | 13 | 13 | 8 | 58 |
| Baylor | 20 | 20 | 15 | 72 |
| Indiana | 8 | 8 | 14 | 1 |
| North Texas | 95 | 95 | 92 | 18 |
| Virginia | 69 | 69 | 77 | 27 |

(Actual is the ordering of the 2025 final Power over the same 136 teams. The poll's own
hindsight ranking has Colorado 102nd; the two differ because the poll ranks schedule odds and
Power ranks points. That distinction is already stated on every projection artifact.)

Mean reversion cannot reorder anything, because `a + phi*(x - mean)` is a positive affine map.
Everything the offseason data bought on Colorado is the nine places between #12 and #21, and
all nine came from a returning-production term that fired exactly as designed.

### 1.3 What the model inherited was its own Power, not the media's opinion

Colorado went 9-4 in 2024. The poll ranked them **25th** at the end of that season. The Power
rating underneath the poll had them **12th**. The projection regresses Power, not the poll's
rank, so it inherited the 12th-place number.

That gap is not a bug and it is worth understanding, because it is where the intuition
"we had them too high" actually comes from. The poll ranks by schedule odds, which asks how
hard it was to go 9-4 against that schedule. Power asks how many points a team is worth. A
2024 Colorado team that lost four close games scores worse on the first question than on the
second. The projection reads the second.

And the AP preseason top 25 for 2025, archived and used only as a baseline, does **not contain
Colorado**. The writers had moved on. The model had not, because the model does not read the
writers. Whatever went wrong here, media bias did not cause it.

### 1.4 The controls, which are the most informative part of the file

| team | proj | actual | `prior_power` | `returning_production` | `coaching_change` | `net_portal` | returning usage |
|---|---:|---:|---:|---:|---:|---:|---:|
| Colorado | 21 | 102 | +12.497 | −1.436 | 0.000 | −0.258 | 0.196 (33rd lowest) |
| South Carolina | 8 | 81 | +12.468 | **+1.667** | 0.000 | +0.008 | 0.634 (105th) |
| Penn State | 4 | 48 | +16.046 | **+2.609** | −2.335 | +0.114 | 0.767 (131st) |
| Baylor | 15 | 75 | +10.115 | **+2.715** | 0.000 | −0.629 | 0.782 (132nd) |
| Indiana | 14 | 1 | +14.129 | **−1.776** | 0.000 | −0.098 | 0.148 (20th lowest) |
| North Texas | 92 | 17 | −4.628 | −0.982 | 0.000 | +0.486 | 0.260 (46th) |

**South Carolina is the cleanest control and it destroys the "returning production would have
saved us" hypothesis.** South Carolina arrived with essentially the same prior as Colorado
(33.02 against 33.07), kept its coach, and returned *well above average* production. Every
offseason signal pointed up. They finished 81st. The recipe missed them by 73 places while
holding the opposite offseason evidence from Colorado.

**Indiana is the same point from the other side.** Indiana returned the second-least production
of any projected top-25 team, was debited 1.78 points for it, and went 16-0 to finish first.

**Penn State and Baylor returned the most production in the entire country** (131st and 132nd
of 134 by ascending usage) and finished 48th and 75th.

Across all 136 teams, `corr(returning usage, 2025 final Power) = +0.134`, against
`corr(prior Power, 2025 final Power) = +0.687`. In 2025, returning production carried almost
no information about the season, and what little it carried pointed the wrong way at the top
of the table. That is a real fact about the portal era: the teams that return their production
are increasingly the teams nobody wanted to poach.

The counterfactual confirms it. Scaling `b_rp` up to force Colorado down monotonically
*degrades* the whole ranking:

| `b_rp` | Colorado | Indiana | Penn St | Baylor | Spearman vs actual |
|---:|---:|---:|---:|---:|---:|
| 7.08 (shipped) | 21 | 14 | 4 | 15 | **0.6973** |
| 14.17 (2x) | 28 | 24 | 1 | 9 | 0.6817 |
| 21.25 (3x) | 36 | 33 | 1 | 4 | 0.6549 |
| 35.41 (5x) | 52 | 51 | 1 | 3 | 0.5947 |
| 85.00 (12x) | 73 | 78 | 3 | 4 | 0.4277 |

Every setting that fixes Colorado breaks Indiana and promotes Penn State to first. "Weight
returning production harder" is a demonstrably wrong fix and the file should say so.

### 1.5 The portal term did nothing, and the undercounting did not hide anything

Colorado had 34 departures and 33 arrivals, net −1, z = +0.63, worth −0.26 points. The
destination field is populated on 83.8% of 2025 portal rows, so arrivals are undercounted;
correcting that would push Colorado's net *up*, and since the fitted `net_portal` coefficient
is *negative* (−0.411, standard error 0.474, not distinguishable from zero) the correction
would have moved Colorado down by tenths of a point. The term is noise and the undercounting is
noise on top of noise.

Colorado's departures ranked 28th of 136 by raw count, which is high but unremarkable. Against
the projection residual: `corr(portal_out) = +0.120`, `corr(portal_in) = +0.107`,
`corr(portal_net) = −0.023`. The complete half of the portal data is no more informative than
the incomplete half.

### 1.6 Colorado forensics: conclusion

No term misfired on Colorado. No data gap masked anything. No sign is wrong. The row is exactly
what the published recipe produces from correctly-loaded inputs, and a reader reproducing it by
hand from the five published numbers gets 25.782992.

The honest finding is a **magnitude asymmetry**: the recipe's one strong term is last season's
rating, and its three weak terms cannot overturn it. That is a property of the design, it is
visible in the coefficient table the project already publishes, and 2025 is the first season
that made it cost something.

---

## Part 2. Two defects the audit did find, both in the measurement layer

### 2.1 The grading page compares two different Powers

`scripts/make_projection_2025.py` produces a "Power projected → actual" column. The two halves
of that arrow are different quantities.

- `projected_power` is on the **fit-response** scale. The recipe's input is
  `seasons.final_power(2024)` and its response is `seasons.final_power(2025)`, both of which
  call `l4_resume.power_source` over the whole season at once.
- `actual_power` is on the **published-poll** scale. `grade.grade_season` takes it from
  `retro.season_power(...)[final]`, which is the walk-forward L3 blend, the same surface the
  poll publishes every week.

The project already knows these are different constructions and already names them. From
`scripts/make_demos.py`: the walk-forward version is "the definition the gate uses, and it is
the one that matches how the poll is actually produced", and the full-season refit is a
"diagnostic" whose blend weights are in-sample, "exactly what report 02 §3.3 legislates
against". The projection is fitted on the diagnostic and graded against the published one.

Measured over the 136 teams in 2025:

```
graded_actual = -3.6541 + 0.7006 * fit_response      r = 0.977
means:  response 15.398 -> graded  7.134
sds:    response 14.003 -> graded 10.041
```

The same relation holds in 2024 (`graded = −3.3719 + 0.6274 * response`, r = 0.965), so this is
a standing property of the two constructions and not a 2025 artifact.

**Consequence one: every team looks over-projected.** Mean `power_error` as shipped is
**−7.236**. Recomputed with `actual_power` on the recipe's own response definition it is
**+1.029**. Colorado's headline "−24.5 points of Power off the projected figure" is
**−16.35** on a like-for-like scale.

**Consequence two: the league-wide attribution's headline verdict is mostly the slope.** The
0.7006 scale factor sits almost exactly where the published `implied_multiplier` of 0.6555
sits, and `prior_power` carries most of the design's variance, so the regression reads the
scale change as a coefficient error.

| term | as shipped | | | recomputed on the response scale | | |
|---|---:|---:|---|---:|---:|---|
| | coef | z | verdict | coef | z | verdict |
| `prior_power` | −0.3445 | −4.41 | **TOO STRONG** | **+0.0093** | **+0.09** | **priced about right** |
| `returning_production` | −0.8087 | −1.86 | priced about right | −0.8125 | −1.40 | priced about right |
| `coaching_change` | +0.4669 | +0.65 | priced about right | +0.3940 | +0.41 | priced about right |
| `net_portal` | +0.1359 | +0.08 | priced about right | +0.3918 | +0.18 | priced about right |

The published sentence "The model weighted last season's rating TOO STRONG ... This season
wanted about 0.66x the model's coefficient" is, on the recipe's own definition of the quantity
it predicts, **not supported**. On the like-for-like comparison the multiplier is 1.009 and the
z is 0.09. All four terms come back "priced about right", which is a much less interesting
result and the correct one.

**Consequence three, forward-looking:** the published 2026 card leads with a projected Power of
37.9 while the published 2025 poll's #1 finished at 30.0. Same word on both pages, two scales.
A reader who compares them will conclude the projection is systematically optimistic.

**The fix is a choice, not a calculation, and it needs the owner.** Either grade against
`seasons.final_power` (keeps the recipe internally consistent, but scores against a surface the
project never publishes), or refit the recipe's input and response on
`retro.season_power[final]` (grades against the published poll, at the cost of a new
`PROJECTION_VERSION` and a refit of all three transitions). What cannot stand is the current
state, where one column is one thing and the next column is the other.

### 2.2 The coaching term reads the season it is projecting

`offseason.coaching(Y)` calls `/coaches?year=Y` and `_primary_coach` picks the coach with the
most games. That file is pulled after the season has been played, so when a school fires its
head coach in October and the interim works more games than he did, the interim becomes the
school's "primary coach" for Y, and `coach_change` flips to 1 for a change that had not
happened in August.

Counting mid-season changes where the August head coach lost the games tiebreak:

| target season | `coach_change == 1` | mid-season situations | **false flags** |
|---|---:|---:|---:|
| 2022 (fitted) | 35 | 15 | **5** |
| 2023 (fitted) | 25 | 9 | **1** |
| 2024 (fitted) | 32 | 13 | 0 |
| 2025 (graded) | 35 | 21 | **5** |
| 2026 (published) | 33 | 0 | **0** |

The 2025 false flags are **Penn State** (Terry Smith 7 games over James Franklin 6),
**Arkansas** (Petrino over Pittman), **Oklahoma State** (Meacham over Gundy), **UCLA** (Skipper
over Foster) and **Virginia Tech** (Montgomery over Pry). Each was docked 2.335 points for a
firing the projection had no right to know about. Sixteen other 2025 schools also changed coach
mid-season and were flagged correctly, purely because the firing fell on the other side of the
halfway point. The term is a coin flip on exactly the teams where it matters most.

The leak flatters the model, which is why it has to be said out loud. Coaches get fired for
losing, so a false "new coach" flag lands on teams that are about to underperform. Penn State
is the worked example: without the leak its projected Power is 33.748 and its projected rank is
**2** rather than 4. The published grading page reports Penn State as a 44-place miss. The
honest number is a 46-place miss.

`validate/leakage.py` does not catch this. It audits column *names* against banned patterns
and it has no temporal guard, so an offseason input that is simply not knowable in August
passes cleanly. That is a gap in the audit, not a failure of it.

The published 2026 card is unaffected: the 2026 coaches file has zero multi-coach schools,
because the season has not been played.

---

## Part 3. The structural question, and the Campaign 3 specification

### 3.1 What the owner described, and what the recipe actually does

The challenge describes a chained walk: evaluate 2021, use 2021 plus the model to forecast
2022, run that through the poll, use that for 2023, and so on to 2026.

That is **not** what the recipe does, and the difference is worth stating precisely.

| | the owner's chain | the shipped recipe |
|---|---|---|
| input to season Y | the model's own forecast of Y−1 | the **actual** final Power of Y−1 |
| coefficients | one set, or refitted each step | one pooled set, fitted once on three transitions |
| out-of-sample claim | the whole chain after step 1 | leave-one-transition-out, plus 2025 as a true holdout |
| what it measures | multi-year error accumulation | one-year-ahead skill |

**The chain would be worse for this product, and the arithmetic says why.** With phi = 0.683,
feeding the model its own output five times decays every team toward the league mean by
0.683^5 = 0.148. By 2026 the chained ranking would be 85% league average and would order
almost nothing. It also answers a question the product does not ask: the Projection's promise
is "given what actually happened last year, what happens next year", and a chain replaces the
one input the model is entitled to have with a simulation of it.

**The instinct underneath the challenge is right, though, and it points at a real gap.** The
recipe's honest out-of-sample scoring is `fit.leave_one_out`, which holds out one transition
and fits on the other two. On 2023 that means fitting on 2022 and 2024, so a *later* season
informs an *earlier* projection. That is acceptable for a coefficient-stability check and it is
not the walk a reader assumes when they read "out of sample". The thing the challenge is
actually reaching for is an **expanding-window walk-forward re-fit**, which the project does not
have and should.

The per-transition fits are what make this urgent:

| transition | phi | `b_rp` | `b_hc` | `b_pf` | R² |
|---|---:|---:|---:|---:|---:|
| 2021→2022 | +0.6511 | +4.98 | +0.33 | −1.42 | 0.466 |
| 2022→2023 | +0.7457 | +10.88 | −1.81 | −0.36 | 0.616 |
| 2023→2024 | +0.6667 | +4.63 | −5.27 | +0.31 | 0.479 |
| 2024→2025 (never fitted, shown for reference) | +0.6890 | +1.33 | −3.25 | −0.57 | 0.484 |
| **pooled (shipped)** | **+0.6826** | **+7.08** | **−2.33** | **−0.41** | 0.507 |

**phi is the stable part of this recipe.** Four independent seasons put it between 0.651 and
0.746, and 2025, which had never been fitted on, wanted 0.689 against the shipped 0.683. The
"prior_power was TOO STRONG" verdict is contradicted by the season's own fit once the scale
defect of §2.1 is removed. `b_rp` meanwhile ranges over 4.98, 10.88, 4.63 and 1.33, and 2025
alone puts a standard error of 4.12 on a point estimate of 1.33. The offseason terms are where
the instability lives.

### 3.2 Campaign 3, pre-registered. SPECIFICATION ONLY. Nothing below was run.

Written in the shape of `docs/analysis/_campaign-2-protocol.md`, whose discipline is that the
protocol is committed with the results section empty.

#### 3.2.0 Prerequisite, and it blocks everything else

**Lead 0 is not a search and must land before any lead below is scored.** Resolve §2.1: pick
one definition of Power for the projection's input, its response and its grading, and make the
three the same. Until that is done, every objective below is measured on a scale that drifts by
a factor of 0.70 between the thing predicted and the thing scored, and any coefficient the
campaign adopts will be absorbing that drift. Lead 0 also fixes §2.2 by taking `coach_change`
from a coaches file pulled before week 1 of the target season, or by restricting
`_primary_coach` to the coach of record in the season's first game.

Recommendation, for the owner to accept or reject: adopt the **published-poll**
(`retro.season_power[final]`) definition on both sides. It is the surface the product ships, it
is the one the gate already uses, and its blend weights are out of sample. The cost is a refit
and a `PROJECTION_VERSION` bump to `projection-2.0.0`, which the grading loop's whole premise
requires be done loudly.

#### 3.2.1 Objective, fixed before any number is read

**Primary:** mean out-of-sample **Spearman correlation over all FBS teams**, projection against
the target season's settled ranking, averaged over the walk-forward folds in 3.2.2. Higher is
better.

**Tie-break, in order:** (1) top-25 overlap against the settled top 25, treatment-free; (2)
censored rank MAE at 26, the AP-comparable metric `fit.rank_metrics` already computes.

Spearman is primary rather than top-25 overlap because Campaign 3's candidates are shape
changes to a full-league rating and overlap counts only 25 teams, which over four folds is too
coarse to separate them. Both are reported for every candidate regardless.

#### 3.2.2 Evaluation protocol: the expanding-window walk, which is what the challenge asked for

For each target season Y in **2023, 2024, 2025** and, when it settles, **2026**:

1. Fit the candidate recipe on **every transition whose target season is strictly before Y**.
   Y = 2023 fits on 2021→2022 alone. Y = 2024 fits on two. Y = 2025 fits on three. Y = 2026
   fits on four.
2. Apply it to Y using the **actual** final Power of Y−1 and Y's offseason data. Never the
   model's own forecast. §3.1 is the argument.
3. Score against Y's settled ranking on the metrics in 3.2.1.

This is chained in the sense that matters, which is that no fold may see a season that had not
finished when the projection would have been published, and it drops the leave-one-out
protocol's use of later seasons to inform earlier ones. It gives three folds today and four
after 2026 settles, against the one true holdout the project has now.

**The 2021→2022 transition is the floor and is reported as such.** A single-transition fit of
four coefficients on 131 teams is thin, and the Y = 2023 fold exists to show how thin rather
than to be quoted on its own.

**Guard, checked before any candidate is scored:** re-run the shipped recipe through this exact
protocol first and publish its numbers. If the walk-forward protocol moves the shipped recipe's
score materially against `demo/projection-backtest.md`, the protocol is the finding and the
campaign stops there.

#### 3.2.3 The candidates, one bounded question each

**Lead 1, a defensive returning-production proxy.** CFBD serves no defensive returning
production of any kind; the 2025 `/player/returning` rows carry `usage`, three offensive usage
splits, and five PPA fields, and PPA is banned by `PROJECTION_BANNED_PATTERNS`. There is no
proxy inside the current pull. The bounded question is therefore an **acquisition** question,
not a search: can a defensive returning-snap share be built from the play archive this project
already holds, at coverage comparable to the offensive term's 133 of 134? Scope: build it,
measure coverage, publish the coverage number, and only then admit it as a fifth term. **If
coverage lands below 95% of FBS in any of the four fit seasons, the term is not admitted**, and
that rule is fixed now so it cannot be relaxed after the coverage number is known.

**Lead 2, portal weighting.** Three variants, scored identically: (a) `portal_out` alone,
standardised, on the argument that departures are the complete half of the data; (b) net flow
with arrivals inflated by the season's populated-destination rate, which is the smallest
possible correction for the known undercount; (c) the shipped `z(portal_net)`, as control.
**Prior, stated in advance:** this audit measured all three against the 2025 residual and found
correlations of +0.120, +0.107 and −0.023, so no variant is expected to win. The lead is run
because "we measured it and it bought nothing" is a publishable sentence and "we never checked"
is not.

**Lead 3, mean reversion.** Grid phi over a multiplier of the fitted value in
{0.50, 0.66, 0.80, 1.00, 1.20} applied as a **fixed override**, not refitted. This is the lead
the published attribution appears to demand, and 3.2.0 is why it must be re-asked after the
scale defect is fixed: on the corrected comparison the 2025 implied multiplier is 1.009, and
the four independent per-transition fits put phi in [0.651, 0.746]. **Prior, stated in
advance:** the grid is expected to select 1.00 and the lead is expected to close the question
rather than move the recipe. Note that phi cannot reorder anything on its own, so this lead can
only move the metrics through its interaction with the other three terms.

**Lead 4, shrinkage on the offseason terms.** Ridge-penalise the three offseason coefficients
toward zero, leaving phi and the intercept unpenalised, with the penalty chosen inside each
fold. This is the lead this audit's evidence actually supports: `b_rp` ranges over 4.98, 10.88,
4.63 and 1.33 across four seasons while phi ranges over 0.651 to 0.746, and pooled OLS on three
transitions has no mechanism for saying "this coefficient is less certain than that one".

**Not attempted, and named so the omission is visible:** per-season coefficients, a coaching
term that knows anything about the coach, and any recruiting composite. The first is fitting
noise on three seasons, the second is FPI's reputation prior wearing a different hat, and the
third is the one input constraint 2 names first.

#### 3.2.4 The adoption rule, fixed before any number is read

A candidate replaces `projection-1.0.0` only if **all four** hold:

1. It beats the shipped recipe on mean out-of-sample Spearman across every fold in 3.2.2.
2. It does not lose on either tie-break metric, averaged across folds.
3. It wins on **at least three of the four** folds individually. A candidate carried by one
   season is a candidate fitted to one season.
4. Its coefficient signs are stable across all folds. A term that changes sign between folds
   is not adopted at any effect size.

If more than one candidate clears the bar, the **simplest** wins, where simplest means fewest
terms and then fewest fitted constants. If none clears it, the recipe does not move and the
campaign publishes that, which is the outcome this audit expects for Leads 2 and 3.

**Every candidate's full result table is published whether or not it is adopted**, and the
protocol is committed before the results section is filled, so the commit history is the
evidence that the rule came first.

---

## Part 4. What the grading page should say about Colorado

One paragraph, to replace the current Colorado story line. It uses the corrected Power error
from §2.1 rather than the mismatched one.

> We had Colorado 21st and the season put them 102nd. That is the biggest miss on this page and
> it is worth being precise about why, because the easy explanation is wrong. The model does not
> read the press, and on this team the press was closer than we were: the AP left Colorado out
> of its preseason top 25 entirely and we ranked them. What we read was Colorado's own 2024,
> where they were the 12th-best team in the country by our Power rating, and that one number was
> worth 12.5 points to their projection. The model also saw the exodus and priced it. Colorado
> returned 19.6% of its offensive usage, the 33rd lowest figure in the country, and 1% of its
> passing usage, which is what losing your quarterback looks like in the data. That cost them
> 1.4 points and moved them from 12th to 21st. The problem is the ratio. Last season's rating
> can swing a team 42 points and returning production can swing one 6, so a team that shows up
> 12th cannot be argued out of the top 25 by the offseason. The grading loop is what found that,
> one season after we published the recipe, and finding it is the reason the loop exists. What
> we are not going to do is turn the returning-production dial up until Colorado looks right.
> We checked: every setting that moves Colorado down also moves Indiana down, and Indiana
> returned even less than Colorado did and went 16-0. Penn State and Baylor returned more
> production than anyone in the country and finished 48th and 75th. In 2025 returning production
> told you almost nothing, and the fix for Colorado is not a bigger version of a term that did
> not work.

Notes on the copy, for whoever wires it in:

- No em dashes. No hedging. The word `guess` does not appear, which is a change from the rest
  of the page: `render_grading` currently writes "`Projected` is the guess" in the table preamble
  and the module docstrings use it in several places. That should be swept separately.
- "1% of its passing usage" is `returning_passing_usage = 0.010`, published on the offseason
  frame.
- The 42-point and 6-point figures are the `prior_power` and `returning_production` spans from
  §1.2 and should be regenerated per season rather than hard-coded.
- The paragraph deliberately does not claim the recipe will change. Leads 3 and 4 in §3.2.3 are
  where that is decided, and promising a fix before the campaign runs is the thing the
  pre-registration exists to prevent.

---

## What this audit did not do

It changed no model code, no fixture and no published artifact. It ran no tuning and selected
no constant. The Campaign 3 protocol above is a specification and none of its leads was
executed. Every number was recomputed from the archive and the shipped recipe, and the
reconstruction reproduces the published `demo/2025-projection-grading.md` row for Colorado
exactly.
