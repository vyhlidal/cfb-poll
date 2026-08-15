# ADR 0013 — Two measurement defects in the Projection, repaired; `projection-2.0.0`

- **Status:** Accepted
- **Date:** 2026-08-15
- **Prompted by:** [`docs/analysis/projection-audit-colorado.md`](../analysis/projection-audit-colorado.md),
  which was opened to answer "why did a model claiming to be free of media bias
  have Colorado 21st", found that Colorado's row was correct, and found two other
  things that were not.
- **Evidence:** [`demo/2025-projection-grading.md`](../../demo/2025-projection-grading.md),
  [`demo/2026-preseason-projection.md`](../../demo/2026-preseason-projection.md),
  [`demo/projection-backtest.md`](../../demo/projection-backtest.md), all
  regenerated from the archive at the branch head this ADR was committed on.
- **Amends:** [ADR 0010](./0010-projection-and-poll.md), which built the
  separation audit. Neither defect below is a separation breach and the audit was
  never going to catch either one, which is the third thing this ADR is about.
- **Scope:** repair only. **No search ran, no constant was selected, and no
  candidate was scored.** The recipe has the same four terms fitted on the same
  three transitions by the same OLS; its coefficients moved because two of its
  inputs were wrong. Campaign 3, specified in §3.2 of the audit, remains
  specified and not run.

---

## Context

The audit reproduced the published `demo/2025-projection-grading.md` exactly and
then took the two halves of its headline table apart.

### Defect 1. The grading page compared two different Powers

`scripts/make_projection_2025.py` printed a column headed "Power projected →
actual". The two ends were different quantities.

- `projected_power` was on the **fit-response** scale. `seasons.final_power`
  returned `l4_resume.power_source` over a whole season at once, and the recipe
  both regressed toward it and predicted it.
- `actual_power` was on the **published-poll** scale. `grade.grade_season` read it
  from `retro.season_power(...)[final]`, the walk-forward L3 blend, which is the
  surface the poll publishes every week and the one the gate uses.

The project already knew these were two constructions and already named them.
`scripts/make_demos.py` calls the walk-forward version "the definition the gate
uses, and it is the one that matches how the poll is actually produced", and calls
the full-season refit a "diagnostic" whose blend weights are in-sample, "exactly
what report 02 §3.3 legislates against". The projection was fitted on the
diagnostic and graded against the published one.

Over 2025's 136 teams the two are related by

```
graded_actual = -3.6541 + 0.7006 * fit_response      r = 0.977
```

and the same relation holds in 2024 (`-3.3719 + 0.6274 * response`, r = 0.965), so
it is a standing property of the two constructions rather than a 2025 artifact.

Three consequences, all of them published:

1. **Every team looked over-projected.** Mean `power_error` on the shipped page
   was **-7.236**.
2. **The league-wide attribution read the scale change as a coefficient error.**
   The 0.7006 slope sat almost exactly where the published `implied_multiplier` of
   0.6555 sat, `prior_power` carries most of the design's variance, and the
   regression duly returned `prior_power` **TOO STRONG at -4.41 standard errors**.
   That sentence was the loudest claim on the page.
3. **The 2026 card led with a projected Power of 37.9 while the published 2025
   poll's number one finished at 30.0.** Same word, two scales, adjacent pages.

### Defect 2. The coaching term read the season it was projecting

`offseason.coaching(Y)` called `/coaches?year=Y` and `_primary_coach` picked each
school's coach by games worked. That file is pulled after season Y has been
played. A school that fired its head coach in October, whose interim then worked
more games than he did, arrived in the design matrix as an **August coaching
change**, and was docked 2.33 points of projected Power for a hire it had not yet
made.

| target season | `coach_change == 1` | mid-season situations | false flags |
|---|---:|---:|---:|
| 2022 (fitted) | 35 | 15 | **5** |
| 2023 (fitted) | 25 | 9 | **1** |
| 2024 (fitted) | 32 | 13 | 0 |
| 2025 (graded) | 35 | 21 | **5** |
| 2026 (published) | 33 | 0 | 0 |

The 2025 five were Penn State, Arkansas, Oklahoma State, UCLA and Virginia Tech.
Sixteen other 2025 schools also changed coach mid-season and came out right,
purely because the firing fell on the other side of the halfway point. The term
was a coin flip on exactly the teams where it mattered.

**The leak flattered the model**, which is why it had to be said out loud rather
than filed as a data-quality note. Coaches get fired for losing, so a false "new
coach" flag lands on teams that are about to underperform.

`validate/leakage.py` could not see it. Every check in that module asks WHICH
columns reach a fit. `coach_change` is on the projection's allow-list for good
reasons, the restricted rebuild was bit-identical every run, and the column name
was innocent. Only the clock was wrong.

## Decision

### 1. One Power, the published one, on all three sides of the arrow

`seasons.final_power` returns `retro.season_power(...)[final]` — the walk-forward
Power at the season's last bucket. That is now the recipe's input, the recipe's
response, and the grading page's answer key, and they are the same object rather
than three things that happen to agree.

The audit offered two ways out and recommended this one. Grading against
`l4_resume.power_source` instead would have kept the recipe internally consistent
at the cost of scoring it against a surface the project never publishes. The
published poll is the product; the projection's job is to be graded by it; a
projection graded against something nobody can read is not being graded in public.

`seasons.POWER_DEFINITION` states it in one sentence and every projection artifact
now stamps it beside `SETTLED_DEFINITION`.

The whole walk is memoised and `grade.grade_season` reads the same memo, so the
two halves cannot drift into two copies. The cost is arithmetic: the walk is one
L3 fit per bucket instead of one per season, about six seconds a season against
one, which the backtest pays five times over and nobody notices.

### 2. The August head coach, decided from what August has

`offseason._august_coach` answers "who opened this season" from three rules, in
order:

1. **A coach with zero games did not open it**, and is dropped from the candidate
   pool whenever anybody at that school worked one. This is what separates
   Buffalo's 2024 phantom row — Maurice Linguist at zero games beside Pete Lembo's
   thirteen, because Linguist left in January and the row stayed — from a real
   mid-season change. In a season nobody has played every row is zero, so the pool
   is every row and the step is a no-op, which is the correct behaviour for the
   file the live projection actually reads.
2. **One candidate is one head coach.** Somebody coached game one.
3. **More than one candidate means a mid-season change**, and the August man is
   the one who was already at that school the season before. Prior-season
   continuity decides it and no within-season quantity is consulted.

**When continuity finds nobody**, the school both hired over the offseason and
changed again during the season, so `coach_change` is 1 whichever candidate opened
it and the games count cannot reach the number the recipe consumes. It fills in
the display NAME and is stamped `inferred_from_games`, and
`tests/unit/test_projection_offseason.py` asserts the implication
(`inferred_from_games` implies `coach_change != 0`) on every season rather than
trusting it.

**`coach_change` is now August-versus-August**: the head coach who opens season Y
against the head coach who opened Y-1. Both sides run through the same function,
so the column answers "did this program replace its head coach over the
offseason" and not "did anything happen to its head coach at any point in either
year".

**What the archive cannot do, stated rather than papered over.** The audit's other
suggested fix was a coaches file pulled before week 1 of the target season. There
is no such pull in the archive for any past season and this work made no network
call, so it was not available. The rule above is the best archive-derivable
substitute, and its one gap is that the earliest archived coaches file is 2021, so
2021 itself has no continuity anchor and three of its schools fall back to the
games count. Those sit on the PRIOR side of the first fitted transition, in the
past relative to the projection that reads them, so it is an accuracy limit rather
than a leak. It is published per team in `coach_of_record_source_prior`.

### 3. A TEMPORAL guard, because the audit that existed could not have caught this

`validate/leakage.TemporalGuard` runs on projection layers only. A poll layer is
fitted on games that have been played and has no August to be honest about; a
guard that passes vacuously on every run is a guard nobody reads.

Same two halves as everything else in that module:

- **`TEMPORAL_BANNED_PATTERNS`**, the deny half and the courtesy: a column whose
  name announces a within-season quantity is named as one on sight.
- **`PROJECTION_KNOWABLE_IN_AUGUST`**, the allow half and the gate: every column
  present on the projection design frame must be declared with the sentence that
  says what settles its value and by when. Undeclared is a violation, so a column
  added to the offseason frame has to be reasoned about before it can ride along.
  This fails closed, which is the only property that matters.

`TemporalLeak` subclasses `BannedFeature`, so every existing caller keeps catching
it and a caller that wants to know the clock was the problem can now ask.
`tests/unit/test_projection_separation.py` plants two leaks: one that matches a
pattern and one that matches nothing and is caught by the declaration alone.

The near miss is recorded in the patterns themselves. A rule on the bare word
`record` would have fired on `coach_of_record_source` on every healthy run, and a
guard that cries wolf every run is a guard that gets ignored.

### 4. `PROJECTION_VERSION` goes to `projection-2.0.0`

A major bump, loudly. The coefficients moved, so every artifact published under
`projection-1.0.0` is **superseded rather than corrected in place**. The grading
loop is season over season and a record whose response definition changed silently
would be worthless.

## What moved

### The recipe

Same four terms, same three transitions, same pooled OLS. The response changed
surface and six false coaching flags and one false negative left the design.

| | `projection-1.0.0` | `projection-2.0.0` |
|---|---:|---:|
| intercept | +14.979 | **+6.232** |
| `prior_power` (phi) | +0.6826 (se 0.037) | **+0.6053** (se 0.035) |
| `returning_production` | +7.083 (se 2.151) | **+5.002** (se 1.551) |
| `coaching_change` | -2.335 (se 1.132) | **-1.301** (se 0.833) |
| `net_portal` | -0.411 (se 0.474) | **-0.180** (se 0.340) |
| R² | 0.507 | 0.463 |
| residual SD | 9.217 | **6.649** |

Most of the shrinkage is scale: the walk-forward response has a standard deviation
of about 10 points against the refit's 14, and the three offseason coefficients
are in response units. `phi` is the one that is not a scale artifact, because both
sides of it changed together, and it fell from 0.683 to 0.605. That is the honest
reading of a noisier response: blend weights estimated week by week out of sample
carry more error than blend weights fitted on the whole season at once, and a
noisier target attenuates the slope. The per-transition fits agree it is real:

| transition | phi | `b_rp` | `b_hc` | `b_pf` | R² |
|---|---:|---:|---:|---:|---:|
| 2021→2022 | +0.5523 | +4.32 | +1.54 | -0.28 | 0.455 |
| 2022→2023 | +0.7618 | +7.33 | -1.41 | -0.65 | 0.565 |
| 2023→2024 | +0.5647 | +2.48 | -3.36 | +0.21 | 0.429 |
| 2024→2025 (never fitted, for reference) | +0.6805 | +2.53 | -2.51 | -0.43 | 0.410 |
| **pooled (shipped)** | **+0.6053** | **+5.00** | **-1.30** | **-0.18** | 0.463 |

`b_hc` still changes sign across transitions and `b_rp` still ranges over a factor
of three. The instability the audit found in the offseason terms is not an
artifact of either defect and it survives both repairs, which is what Campaign 3's
Lead 4 was written for.

### The 2025 grading page

| | `projection-1.0.0` | `projection-2.0.0` |
|---|---:|---:|
| mean `power_error`, final week | **-7.236** | **+1.193** |
| Colorado | 21st → 102nd, -24.53 points | **28th → 102nd, -9.79 points** |
| Penn State | 4th → 48th | **3rd → 48th** |
| projected top 25 that finished top 25 | 13 | 12 |
| mean abs rank error vs hindsight, final | 26.13 | 27.31 |
| `prior_power` attribution | **-0.3445, z -4.41, TOO STRONG** | **+0.1242, z +0.88, priced about right** |
| `returning_production` | -0.8087, z -1.86, about right | -0.4949, z -0.78, about right |
| `coaching_change` | +0.4669, z +0.65, about right | +0.9291, z +0.65, about right |
| `net_portal` | +0.1359, z +0.08, about right | +1.3711, z +0.37, about right |

**The published sentence "The model weighted last season's rating TOO STRONG ...
This season wanted about 0.66x the model's coefficient" is withdrawn.** On the
corrected surfaces all four terms come back priced about right, the furthest of
them 0.9 standard errors from the value the recipe uses. That is a much less
interesting result and it is the correct one.

The audit predicted the verdict and predicted the magnitude too optimistically. It
recomputed §2.1 in isolation — the shipped coefficients, with `actual_power`
transformed onto the fit-response scale — and got `prior_power` +0.0093 at z 0.09.
The repair does more than transform: it refits on the published surface and also
removes six false coaching flags, so the landing point is +0.1242 at z 0.88. Same
verdict, four times the magnitude, still comfortably inside the threshold. The
difference between a simulation of a fix and the fix is worth recording.

The templated attribution machinery printed the corrected verdicts without a line
changing, in both directions, which is what it was built for. The 2024 grading
demo moved the same way: three terms that read TOO STRONG under 1.0.0 now read
priced about right.

### The 2026 board

Ohio State stays first. The top ten moves as follows, against the shipped card:

| # | team | was | move |
|---:|---|---:|---:|
| 1 | Ohio State | 1 | 0 |
| 2 | Indiana | 3 | +1 |
| 3 | Oregon | 2 | -1 |
| 4 | Texas Tech | 7 | +3 |
| 5 | Notre Dame | 5 | 0 |
| 6 | Miami | 6 | 0 |
| 7 | Utah | 10 | +3 |
| 8 | Georgia | 4 | -4 |
| 9 | Texas A&M | 12 | +3 |
| 10 | North Dakota State | 23 | **+13** |

**North Dakota State at tenth is the row to watch and the card already says so.**
They moved up from FCS for 2026, their prior rating was earned against FCS
opposition, and the promoted-team caveat names them and their rank in the
generated text. Nothing about the promotion changed here; the walk-forward Power
simply rates their 2025 higher relative to FBS than the full-season refit did.

Penn State's 2026 rank is essentially unmoved, 42nd to 43rd, because the coaching
fix does not touch 2026: that file has no multi-coach schools, since the season
has not been played. Penn State's movement from the coaching fix is in the 2025
grading, 4th to 3rd.

Three teams left the published top 25 (Illinois 22, Pittsburgh 24, Boise State 25)
and three entered (San Diego State 20, Tennessee 24, Missouri 25).

### The backtest

`top25_overlap` falls from 14.33 to 13.00 and the AP's from 14.67 to 13.67, so the
comparison against the writers still splits and still splits the same way. Against
the naive floor the result got worse and is now published as such: **the offseason
terms buy zero extra top-25 teams over three seasons**, against one under 1.0.0.
They still buy 0.28 places of censored rank error and 0.007 of Spearman. The
verdict template gained a branch for this, because its only ending was "that is a
small edge and it is a real one" and it would have printed that over a difference
of 0.0.

## Consequences

1. **Every `projection-1.0.0` artifact is superseded.** `demo/` is regenerated in
   the same commit series. The site fixtures for 2025 and 2026 are regenerated and
   handed over uncommitted, because the sandbox is a separate repository and this
   work does not push.
2. **The Colorado paragraph ships as a published field**, `feature_story` on
   `<season>/projection-grading.json`, with every number read off the live frames
   and every claim asserted before the sentence carrying it is allowed out,
   including its superlative. It is there because `grade.story_lines` correctly
   drops the row: Colorado is 28th and 102nd, outside 25 on both sides, and the
   filter is right and the row still needs explaining.
3. **`attribution_verdict` ships beside it**, because a page built to print a
   mispriced term prints silence when nothing is mispriced. The field is templated
   in both directions.
4. **Campaign 3's prerequisite is discharged.** The audit's §3.2.0 said Lead 0
   blocks every lead below it, because until the projection's input, response and
   grading are one definition, any coefficient a campaign adopts is absorbing a
   0.70 scale drift. They are now one definition and the coaching term is no
   longer answered from the future. **The campaign itself is still specified and
   not run**, and nothing in this ADR selects a constant.
5. **Lead 3's prior is now testable and points where the audit said it would.**
   The corrected implied multiplier on `prior_power` is 1.124 with z 0.88, and
   four independent per-transition fits put phi between 0.552 and 0.762. The grid
   over phi should select 1.00 and close the question. That is a prediction
   recorded before the lead runs, not a result.
6. **A pre-existing wart got louder and is flagged rather than fixed here.**
   `implied_multiplier` is `1 + gamma`, and when the term being attributed was
   itself fitted near zero the contribution column has almost no spread, gamma
   explodes, and the published sentence becomes arithmetically correct nonsense.
   `demo/projection-grading-loop.md` now reads "-22.34x the model's coefficient"
   for `coaching_change`, on a leave-one-out fit whose `b_hc` is +0.150. The
   shipped 1.0.0 file already printed "+7.19x" and "-0.55x" for the same reason.
   Deciding what that sentence is entitled to say is a design question and does
   not belong in a defect repair.
7. **The separation audit's shape is now three questions, not two.** Which columns
   reach a fit, whose deny-list applies, and when each value became knowable. The
   third was added after it was answered wrong for three seasons, which is the
   ordinary way audits acquire checks and is worth saying rather than presenting
   the finished set as though it had been foreseen.

## Alternatives rejected

- **Grade against `l4_resume.power_source` instead.** Keeps the recipe internally
  consistent and scores it against a surface the project never publishes. The
  product is the published poll and the projection's job is to be graded by it.
- **Transform one scale onto the other and publish the mapping.** Cheaper, and it
  would have left two definitions in the code with a constant between them,
  fitted on 136 teams of one season, that somebody would eventually forget to
  refit. Two definitions joined by a fudge factor is the defect with a coat on.
- **Keep `projection-1.0.0` and call this a bug-fix release.** The coefficients
  moved and the headline verdict reversed. A grading loop that quietly changed its
  response definition would make its own record meaningless, which is the exact
  argument `PROJECTION_VERSION` exists for.
- **Fix the coaching term by dropping mid-season-change schools from the fit.**
  Throws away the teams the term is most about, and leaves the live 2026 column
  computed by a rule that would still be wrong the moment a 2026 file with games
  in it exists.
- **Refit the offseason coefficients with a shrinkage penalty while we were in
  here, given `b_hc` changes sign across transitions.** That is Campaign 3's Lead
  4. Choosing it now, having just read the corrected numbers, is selecting a
  method against a result, which is the failure the pre-registration exists to
  prevent.
- **Re-run the audit's Colorado paragraph unchanged and fix only the arithmetic.**
  Two of its claims stop being true on the corrected surfaces: Colorado is no
  longer inside our top 25, and the grading loop did not find `prior_power` too
  strong. A paragraph whose numbers were patched and whose story was not would be
  worse than the one it replaced.
