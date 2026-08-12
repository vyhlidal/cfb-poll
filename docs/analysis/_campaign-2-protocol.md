# Campaign 2 — bracketing C, the shape of the accumulation window, and the h question

**Date opened:** 2026-08-12
**Status:** PROTOCOL PRE-REGISTERED. No number below the protocol had been read when
the protocol was written; this file was committed with the results sections empty
and filled in afterwards, so the commit history is the evidence that the rule came
first (`git log --follow docs/analysis/campaign-2.md`).

Campaign 1 closed with three sentences that set this one up, and it named its own
successor items before it had any of the answers
([ADR 0007](../adr/0007-tuned-constants.md), "The next campaign's pre-registered
items"):

> widen `c_grid` above 32; a trailing-window σ and a trailing-window points
> calibration; a win-probability model so `garbage_time.mode = "leverage"` becomes
> measurable; and an identification strategy for `h` that does not depend on 37
> neutral-site games.

This campaign takes the first, the second and the fourth. The third is not
attempted: a win-probability model is a build, not a search, and pretending
otherwise would be a way of appearing to close a hole rather than closing it.

The gate, as it stands, on the config that ADR 0007 froze
([`demo/backtest-2021-2023.md`](../../demo/backtest-2021-2023.md)):

| Criterion | Threshold | Observed | Verdict |
|---|---|---:|---|
| Straight-up accuracy | >= 70.00% | 69.27% | FAIL |
| Margin MAE | <= 12.8 | 13.010 | FAIL |
| Margin RMSE | <= 15.8 | 16.547 | FAIL |
| Max decile calibration deviation | <= 5.0 pp | 11.28 pp | FAIL |
| Retrodictive violations vs every scored system | at or below all | 0.2015 | FAIL |

**Campaign 1's central finding is the reason this campaign is scoped the way it
is.** The entire 416-cell space it searched spans 0.135 points of MAE and the gate
needs 0.219, so the gap is structural. Nothing below is expected to close it, and
a lead that improves the gate's verdict would be a surprise rather than the plan.
What is on the table is one bounded question per lead: is the optimum bracketed
now that the grid has been widened, is the *shape* of the accumulation window
worth anything, and is `h` identifiable at all under this project's rules.

---

## PART 0 — THE PROTOCOL, fixed before any number was read

### 0.1 Objective, tie-break, and the two different adoption metrics

**Leads 1 and 3 are scored on** walk-forward MAE on the tune seasons **2021-2023**,
headline window (`weeks >= [publication].headline_start_week`, i.e. weeks 5+),
segment `fbs_vs_fbs`. Lower is better. **Tie-break, in order:** Brier, then
retrodictive violation rate.

**Lead 2 is scored on the maximum decile calibration deviation** over the same
games, because that is the criterion it is aimed at and because campaign 1 already
established that MAE is not what this instrument moves. Its MAE and Brier are
*guards*, not objectives — see 0.4.

This is the same rule ADR 0006 used to choose the fit universe and the same rule
campaign 1 used to choose C and β_w, reused for the same reason: a project that
changes its selection rule between studies is choosing the rule to fit the answer.
Where lead 2 departs from it, it says so here, in advance, with the reason.

The headline ordering `schedule_odds` predicts through its Power source
(`[resume].power_source = "L3"`), so its predictive row **is** L3's row by
construction. The grids are therefore scored on `l3` and the numbers transfer
without an assumption. Violations, which are about the ordering rather than about
Power, are recomputed with the full system list for the frozen winners only.

**The incumbent is the config as ADR 0007 left it** — C = 32, β_w = 7, garbage
time connelly, prediction compression off, σ and the points calibration both
cumulative — and every delta below is against that, not against the pre-ADR-0007
starting values. Campaign 1's baseline is spent.

### 0.2 Search space — LEAD 1, bracketing C

C's optimum sat on the top of its own published grid. The grid is widened once,
here, and the widening is declared before it is searched:

| Parameter | Values | Cells |
|---|---|---:|
| `[margin].c` | 32, 36, 40, 48, 64, 96, **uncapped** | 7 |
| `[margin].beta_w` | 5, 6, 7, 8, 10, 12 | 6 |

42 cells. `[garbage_time].mode` is held at `connelly` and
`[margin.prediction_compression].enabled` at `false`, the values campaign 1's
416-cell factorial chose in 208 of 208 paired cells each. Re-searching them would
be re-litigating a settled result with a smaller sample.

**"Uncapped" is the point of the exercise and it is the honest top of the grid.**
C is the scale of `s = C·tanh(m/C) + β_w·sign(m)`, so C → ∞ is the identity
response `s = m + β_w·sign(m)`: margin enters uncompressed. It is written
`c = inf` in the config, it is a real value of the parameter rather than a missing
one, and it means the grid **cannot** produce another corner solution in C — the
top of this grid is the limit of the family. If the optimum lands there, the
finding is that this dataset does not want the tanh at all, which is a substantive
claim about the model and not a request for a wider grid.

β_w's grid is widened upward only. Campaign 1 searched 0 to 8 at full resolution
and the whole low half lost; re-running it would spend the budget on a question
already answered. The upper end goes to 12, which is beyond every precedent on
record (Sports-Reference's ±7 floor is β_w ≈ 3), so an optimum at 12 would be
reported as an edge exactly as C = 32 was.

### 0.3 Search space — LEAD 2, the shape of the accumulation window

Campaign 1 named the mechanism and refused to act on it, because acting on a fix
discovered while looking is the failure a protocol exists to prevent
(tuning-campaign.md §5.6). This is that fix, pre-registered.

Both the affine points calibration and σ are fitted on the games **accumulated so
far** in the season, and the ratings that feed them improve as the season goes on,
so a slope fitted on weeks 2-9 under-scales week 10 and a σ fitted on weeks 2-9
(mean 18.46) over-covers week 10 (realised RMSE 16.55). A **trailing** window is
the same estimator with a different shape.

| Parameter | Values | Cells |
|---|---|---:|
| `K_σ` — trailing buckets for σ | 3, 4, 5, 6, all | 5 |
| `K_calib` — trailing buckets for the affine calibration | 3, 4, 5, 6, all | 5 |

25 cells, searched as a **product** and not in two stages, because the two
estimators enter the same probability and campaign 1 established that a two-stage
search on interacting switches locates the first stage under a value the second
stage then moves. `(all, all)` is the incumbent and is a cell of the grid rather
than a separate baseline.

**A bucket is a week.** The unit is `ingest/windows.py`'s bucket, whose order is
by first kickoff, because deriving "the last K weeks" from the week number
reintroduces the 2023 postseason's week-1-and-11-15 collision. `K = all` is the
cumulative estimator that runs today.

**THIS IS NOT A RELAXATION OF THE OUT-OF-SAMPLE RULE, AND THE DISTINCTION IS THE
WHOLE LEAD.** ADR 0007 states the boundary in its own words: *"fitting either of
them on the training window costs L2 0.44 points of MAE and inverts the ordering
against Elo. The defect is the SHAPE of the accumulation window, not the fact that
it is out of sample. A trailing window is out of sample too."* Every game in a
trailing window is still a game that was predicted before it was scored, by a fit
that had not seen it. Nothing here reads a future game and nothing here reads a
prior season.

**The thin-window fallback, declared in advance so it is not chosen later.** If a
trailing slice holds fewer than `[backtest].calibration_min_out_of_sample_games`
(40) games for the calibration, or fewer than
`[resume].sigma_min_out_of_sample_games` (40) for σ, the estimator falls back to
the **full accumulation** — the incumbent behaviour — and not to the training
window. That is the more conservative of the two available fallbacks and it keeps
the trailing arms strictly nested inside the incumbent's own information set.

If lead 2 is adopted, the trailing rule applies to σ in **both** places it is
estimated — the harness (`backtest/walkforward.py`) and the live pipeline
(`model/l3_power.py`) — because a poll whose published σ differs from the σ its
own gate was computed under is publishing two models.

### 0.4 Cost, and how the grids are walked

Measured before the search, on this machine, with the archive already loaded: one
three-season backtest scoring `l3` alone takes **13.4 s**. Lead 1's 42 cells and
lead 2's 25 cells are therefore about 15 minutes of single-process compute
between them, and much less with the frames loaded once per worker. **Both grids
are affordable in full, so both are run in full** — no subsampling, no
coarse-then-refine, no opportunity to stop early on a number one likes.

### 0.5 Adoption rules, fixed before any number was computed

**LEAD 1 — C and β_w.** Adopted only if the winner **improves tune MAE against
the incumbent AND the 2024 MAE also improves against the incumbent.** Direction,
not magnitude, on 2024.

This is **stricter than campaign 1's rule**, which adopted on a 2024 result that
merely did not worsen beyond 0.055 points. The bar is raised deliberately and the
reason is stated before the answer is known: campaign 1's search stayed inside the
interval other people's published work justifies, and this one leaves it. A value
of C above every precedent on record, chosen because it won a search on 1,585
games, has to clear a higher bar than a value inside the precedents did, or the
project is treating "the grid was widened" as if it were evidence.

If the tune improvement is smaller than the 0.055-point noise floor, that is
published as a measurement of smallness — as ADR 0007 published 0.0086 — and does
not by itself block adoption. The noise floor decides the 2024 question and only
the 2024 question, which is what it was declared for.

**LEAD 2 — the trailing windows.** Adopted only if the winner:

1. cuts the maximum decile calibration deviation by **≥ 2.0 pp on the tune
   seasons** (campaign 1's own calibration bar, reused rather than reinvented),
   **AND**
2. **holds direction on 2024** — the deviation moves the same way there, and
3. **does not degrade the guards**: tune MAE no worse than the incumbent's by more
   than **0.055 points** (ADR 0006's noise floor), and tune Brier no worse than the
   incumbent's by more than **one standard error of the paired per-game
   difference**, computed on the identical 1,585 games. The paired standard error
   is the right instrument and it is not an invented constant: both cells score the
   same games, so pairing removes the game-to-game variance that dominates an
   unpaired comparison, and the number is computed from the runs themselves.

**LEAD 3 — league-structural home field. THE CONFIG DEFAULT DOES NOT CHANGE,
WHATEVER THE RESULT.** There is no adoption rule for lead 3 because lead 3 is not
up for adoption in this campaign. It is run, measured, and reported, and
[ADR 0008](../adr/0008-league-structural-home-field.md) puts the question it
raises to the owner. See PART 0.5 below, which is the part of this protocol that
matters most.

**If a lead's tune and validation numbers disagree, the config KEEPS the incumbent
value for that lead and the campaign reports that lead as a failure.** Leads are
independent: one failing does not block another.

**INTERACTION, pre-registered.** Leads 1 and 2 are each searched against the
**current config**, so that neither result is conditional on the other. If both
clear their rules, the **joint cell** (lead 1's winner × lead 2's winner) is
evaluated on tune and on 2024 and must clear **both** rules again before both are
adopted together. If the joint cell fails, only the lead with the larger
pre-declared claim on its own objective is adopted — lead 1 on MAE, lead 2 on
calibration — and the other is reported as blocked by the interaction.

**2024 IS READ AGAIN IN THIS CAMPAIGN.** ADR 0007 required that every future
decision reading it say so publicly and re-designate the split. This paragraph is
that statement: 2024 has now been read twice, once by campaign 1 and once here,
and each lead's 2024 evaluation happens ONCE, after that lead's tune winner is
frozen in writing in the results document.

**2025 stays locked.** Nothing in this campaign reads it. The harness refuses it
without `unlock_holdout=True`, no code path here passes it, and lead 3's
prior-season pooling explicitly excludes it.

---

## PART 0.5 — THE CONSTRAINT QUESTION, STATED BOTH WAYS BEFORE THE NUMBER

Campaign 1 convicted `h` of being barely identified: the site coefficient the
harness actually uses averages **6.39 points with a standard deviation of 4.34**
across published weeks, against **1.88 ± 0.34** from 1,113 home-and-home pairs.
Only 37 of 1,585 scored games are at neutral sites, so the intercept and the site
term are very nearly collinear. Every honest estimate of the home-field advantage
in college football is between 2 and 3 points. The number this poll runs on is
6.39, it swings by more than 4 points week to week, and that is a defect on the
record with nothing yet done about it.

The identification strategy that would fix it uses **prior-season home-and-home
pairs**, and that is where the campaign stops and asks.

### An earlier framing of this was wrong, and correcting it is the first thing owed

It has been said in the course of setting this campaign up that anchoring `h` on
prior-season data would be an extension of an existing precedent — that the EP
layer already fits across seasons. **That is not true and the record should say so
plainly.** `[ep].fit_scope = "training_window"`: the EP model is fitted inside the
walk-forward window like everything else. `frozen_seasons` exists as an
alternative the config names and no code path selects. **Every fitted quantity in
this project is currently within-season and walk-forward.** Cross-season fitting
was raised earlier in the project's life and rejected as leakage.

So this would be **the first cross-season fitted quantity in the system.** Not an
extension. A first. Arguing it as a precedent extension would be arguing it on a
false premise, and a project whose entire pitch is that its constraints are
audited rather than asserted cannot afford that even once.

### The case FOR ratifying it

- **`h` is not a team rating and carries no team identity.** Constraint 2's banned
  list says "prior-season ratings of any kind", and the reason it says that is
  spelled out at length in `docs/constraints.md`: a reputation prior "shrinks a
  team toward what we think of its brand". A single league-wide venue constant
  shrinks nobody toward anything. It is one scalar, identical for all 133 teams,
  and it cannot advantage a brand because it does not know which team it is
  attached to. The line the constraints document draws so it can be audited is
  *"priors may encode ignorance, never reputation"*, and a league-average
  home-field advantage is closer to a physical constant of the sport than to an
  opinion about anybody.
- **The thing it replaces is worse.** A coefficient with a standard deviation of
  4.34 points, driven by 37 games, is not a measurement of home-field advantage;
  it is noise wearing home-field advantage's name. Refusing a well-identified
  1.88 ± 0.34 in favour of a badly identified 6.39 ± 4.34 protects the letter of
  the constraint at the cost of the thing the constraint is for.
- **It is auditable in the way constraint 5 demands.** One number, published
  weekly on `model_params.json`, computed by a function anyone can run on the
  public archive, with a standard error beside it.

### The case AGAINST ratifying it

- **The bright line is the asset.** The reason this project can say "we do not use
  conference identity" as a *result* rather than a claim is that
  `audit-features` rebuilds every design matrix from an allow-list and requires
  bit-identity. A bright line survives because it is bright. "No prior-season data
  except this one scalar, which we judged to be different in kind" is a line that
  requires a judgement call at every future crossing, and the second crossing is
  always easier to argue than the first.
- **The slope is real, not rhetorical.** Every subsequent cross-season quantity
  will cite this one. A per-conference home-field term is "just a few more
  scalars". A venue-altitude term is "a physical constant of the sport". The
  argument that admits `h` admits those, and the project has no principle written
  down today that separates them.
- **There is a within-season alternative that has not been exhausted.** 21
  within-season pairs is a thin sample, but it is not the only within-season
  instrument: constraining `h` toward a published reference with a penalty,
  pooling neutral-site games across the season, or simply reporting the
  identification failure and refusing to act are all available and none of them
  crosses the line.
- **The gain may be nil.** Campaign 1 measured the residual mean at home sites as
  −1.13 points against −0.19 at neutral, an order of magnitude too small to
  explain the calibration miss. If anchoring `h` does not move MAE, calibration or
  violations beyond the noise floors declared in 0.5, then the constraint question
  is being asked for nothing, and the honest answer is to say so.

### What the experiment will and will not do

**Arm A — the live-runnable form, if it were ratified.** For each season S, `h` is
the pooled home-and-home estimate over every archived season **strictly before**
S, walk-forward across seasons exactly as everything else is walk-forward within
one. 2021 has no prior season in the archive and is documented as the boundary
case; 2022's only prior is 2021, which campaign 1 measured at 17 within-season
pairs, so it is expected to be a second boundary case and will be reported as one
whatever it turns out to be. The anchored `h` is held fixed in the harness's
affine calibration and only the intercept and slope are fitted, on the
residualised response `margin − h·site`.

**Arm B — the bound, which is NOT a live estimator.** `h` pooled over 2021-2023
applied to 2021-2023. It reads seasons it is scoring, exactly as campaign 1's
oracle σ row did, and it exists for the same reason: to bound what a
well-identified `h` could be worth before anyone argues about whether to allow
one. It is labelled NOT RUNNABLE at every appearance.

**The default config does not move.** `[constraints].allow_prior_season_data`
stays `false`, the anchor stays off, and the harness **refuses** to apply a
prior-season anchor unless that constraint key is explicitly flipped in an
override. The experiment flips it in its own override and nowhere else. ADR 0008
is written as a question awaiting the owner's decision and is labelled as such in
its status line.

**The result cannot change the argument above.** The case for and the case against
are written here, before the number, so that neither can be quietly re-weighted
once the number is known. What the number decides is whether the question is worth
the owner's time — not which side of it is right.

---

## PART 0.6 — WHAT COUNTS AS THIS CAMPAIGN HAVING FAILED

Stated in advance, because a campaign that can only succeed is not an experiment:

- Lead 1 fails if the widened grid's winner does not improve tune MAE, or improves
  it and reverses on 2024. **The most likely single outcome is that C = 32 remains
  the optimum**, in which case campaign 1's corner was a corner in the grid and not
  in the data, and this campaign's contribution is to have closed that question.
- Lead 2 fails if no trailing window cuts the tune deviation by 2 pp, or if the
  one that does reverses on 2024, or if it buys calibration by spending MAE or
  Brier past the guards.
- Lead 3 cannot fail, because it is not being adopted. It can be **uninteresting**,
  which is a real outcome and would be reported as one: if the anchored `h` moves
  nothing beyond the noise floors, ADR 0008 records that the constraint question is
  not worth crossing a bright line for.
- **All three can land and the gate can still fail all five criteria.** On campaign
  1's evidence that is the expected outcome, and it is written here so that a
  reader meeting the results does not have to take the campaign's word for what it
  expected.
