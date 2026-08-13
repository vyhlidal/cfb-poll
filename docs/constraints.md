# The Five Hard Constraints

These are not preferences. They are the reason the project exists, and any change
to a number in this document is a change to what the project *is*.

Stated verbatim, from the scope line of research report 02
(`02-modeling-approaches.md`), which is the canonical wording:

> **the project's five hard constraints (no human polls; no reputation priors;
> mandatory opponent adjustment; retroactive re-ranking; full transparency)**

---

## 1. No human polls

No AP poll, no Coaches poll, no CFP committee ranking may be an input to anything.
They are **comparison targets, never fitting targets**.

The subtle version of this violation is the dangerous one: fitting toward
agreement with the committee would reintroduce human poll bias through the back
door — "a subtle but complete violation of constraint 1" (report 02 §5.5). We
report Kendall's tau against the final committee top-25 and then **let the
disagreements be the product**.

## 2. No reputation priors

No recruiting rankings, no talent composites, no returning production, no
returning starters, no coaching tenure, no conference identity, no prior-season
ratings. The constraint text bans "last season's reputation in the published
rankings" (quoted in report 02 §4).

This is what disqualifies every commercial system as a template. SP+ uses
returning production and recruiting rankings. FPI uses prior performance,
returning starters, recruiting and coaching tenure, and its priors "never
completely disappear." Pasteur carries the prior season as "two fully-weighted
games." All three would fail this constraint.

**Regularization is not a reputation prior**, and the distinction is the project's
central public argument (report 02 §4):

> Ridge shrinks an unknown team toward *the league average*, which is a statement
> about our ignorance, not a statement about the team. A recruiting prior shrinks a
> team toward *what we think of its brand*, which is exactly the bias we are trying
> to eliminate.

Three pieces of evidence make that more than rhetoric:

1. λ in ridge is literally a ratio of variances — noise variance over prior
   variance. It contains no team-specific information whatsoever, and every team
   gets the identical penalty.
2. The most rigorously bias-free method in the BCS used exactly this device.
   Colley's `+2` **is** a ridge penalty; without it his matrix is singular and the
   method does not work at all. He marketed the system as "bias free" *with* that
   term in it.
3. Bradley-Terry's phantom-player fix is provably a MAP estimate under a prior
   (Glickman 2026). Pseudo-games, phantom opponents, Laplace's rule of succession
   and the ridge penalty are the same mathematical object under four names, in
   four literatures, always solving identifiability on sparse schedules — never
   encoding an opinion.

The line, stated so it can be audited: **priors may encode ignorance, never
reputation.** The audit is to inspect the code for team-specific constants, of
which there are none.

## 3. Mandatory opponent adjustment

Every rating is adjusted for who a team played and where. The adjustment is
**simultaneous, not iterative** — offense and defense are solved jointly in one
linear system, which is both more correct and cheaper than iterative averaging,
and which makes the "10 sacks against an FCS team" problem vanish by construction
(report 02 §1, commitment 3).

FCS teams get their own coefficients under the same penalty. Pooling them into one
node is exactly ESPN's pre-2015 FPI failure (report 02 §3.7).

## 4. Retroactive re-ranking

Ratings must be re-computable with hindsight: "given what we now know about how
good those opponents actually were, how good were the first N weeks of results?"

This is why the estimator is a **batch refit and not an Elo**. Every rating is a
pure function `R(evaluation_week N, data_window K)`:

- live ranking for week N = `R(N, N)`
- hindsight ranking for week N = `R(N, final)`

Change the set of games, re-solve, done. Elo cannot do this cleanly because it is
path-dependent: there is no principled "week 5 with hindsight," and its week-5
rating cannot use week-13 information without breaking its own update recursion
(report 02 §2.7, §3.6).

**This constraint chose the headline ordering**, and it is worth recording that a
constraint did real work rather than sitting on a page. The wins-based résumé that
was the headline until 2026-08-12 satisfied constraint 4 for every team *that had
lost a game*, and could not satisfy it for any team that had not: an undefeated
team's résumé saturates at the published bracket `[−60, +60]`, +60 is not a
function of the schedule, therefore it is not a function of `K`, therefore
substituting end-of-season opponent quality could not move it at all. Measured:
from week 11 of 2023 onward, the résumé ordering moved **no unbeaten team by a
single place** between the live and hindsight surfaces. See
[ADR 0005](adr/0005-headline-ordering.md).

## 5. Full transparency

Every equation, every constant, every input published — and every published poll
reproducible by a stranger with no API key, no account, and no permission from
anyone.

Concretely this means: `model_params.json` ships every constant every week;
`_run.json` ties every poll to the exact `git_sha`, `config_hash` and
`archive_hash` that produced it; the win premium `β_w` appears in a permanent
footer rather than a buried methodology page; and a CI job recomputes a historical
week offline and asserts a byte-match on every push.

---

# The headline promise

The five constraints say what the poll may not do. This says what it claims to do,
in the one sentence a reader is entitled to hold it to:

> **The harder it was to do what you did, the higher you go — measured, never
> assumed.**

Teams are ranked by `−log10 P(W ≥ W_t)`: the probability that a team of published
reference quality would have gone at least this well against that exact schedule.
Both halves of the sentence are load-bearing.

**"The harder it was"** means schedule difficulty, and only schedule difficulty.
**Your own margin never enters the rank key — not as a tie-break, not as a
secondary sort, nowhere. Your opponents' margins price your wins.**

That is enforced rather than promised, and the enforcement has two halves because
the claim has two halves. The narrow half: the module's schedule flattener carries
no margin column at all, and with opponent quality held fixed a test scrambles
every final score in a season while preserving every winner and asserts the
ranking is bit-identical
(`tests/unit/test_schedule_odds.py::test_scores_may_change_freely_if_winners_do_not`).
The half that keeps the sentence honest: opponent quality is the L3 Power rating,
which is fitted on compressed scoring margin, so a second test refits Power from
the same scrambled scores the way the pipeline does and asserts the published
ranking **moves**
(`::test_refitting_opponent_quality_from_scrambled_scores_does_move_the_ranking`).

This wording is narrower than what this project published until 2026-08-13. The
wider version — "margin never enters, scramble the scores and the ranking is
bit-identical" — was true of the module and false of the poll, and the
independent review said so before anyone outside did
(`docs/analysis/fresh-eyes-review.md`, S5). The second test exists so that the
sentence cannot quietly widen again.

**"Measured, never assumed"** is constraint 2 applied to the thing everyone
actually argues about. An unbeaten Group of Five team probably would not survive a
Big Ten schedule — and a poll may only say so if it *derived* it. Nothing in the
computation knows what a conference is; opponent quality arrives only as a rating
fitted from results. In 2023 the poll puts a 13-0 Liberty at #10, below a 12-1
Georgia at #7. That is the same direction as the intuition, reached from Liberty's
actual opponents rather than from the letters "C-USA", and it is falsifiable in a
way the intuition is not.

## Unbeatens-first was considered, and rejected

The obvious alternative promise — *win them all and you finish ahead of every team
that did not* — is the oldest promise in the sport, and it was the published
ordering of this project from commit `50f4058` until 2026-08-12. It was the
wins-based L4 résumé, under which an undefeated team's rating has no finite root
and lands on the published bracket `+60`. That delivers unbeatens-first as a
theorem rather than a tendency: across four seasons and both surfaces, the number
of teams with a loss ever ranked above an unbeaten team was **exactly zero**, in
all eight cells.

It was rejected because **+60 is not a function of the schedule**, and therefore
not a function of the data window, and therefore constraint 4 — retroactive
re-ranking, the project's most differentiated product — could not move an unbeaten
team at all. From week 11 of 2023 onward it moved none of them by a single place.
A poll that cannot say "September turned out to be harder than we thought" about
the teams whose ranking is most argued about is not delivering the feature it
advertises.

The evidence, in full, with the axes on which the rejected orderings *won*:
[`docs/analysis/headline-ordering-study.md`](analysis/headline-ordering-study.md).
The decision, the owner's rationale and the price:
[`docs/adr/0005-headline-ordering.md`](adr/0005-headline-ordering.md).

**The résumé did not go away.** It is on every published row, with its saturation
flag, its margin-aware variant, and the Power rating with the gap between them.
Anyone who prefers unbeatens-first can sort by that column, or set
`[publication].headline_ordering = "L4_resume"` and regenerate the whole pipeline
under it. What changed is which column sorts the table by default.

---

# Banned inputs

Reproduced from research report 02 §3.10. `cfbpoll audit-features --fail-on-banned`
fails the build if any of these reaches a model matrix, and it runs in both the
weekly workflow and the reproducibility workflow.

| Banned input | Why |
|---|---|
| AP / Coaches / CFP rankings | Constraint 1, directly |
| Recruiting rankings, talent composites | Constraint 2 — reputation prior |
| Returning production / returning starters | Constraint 2 |
| Prior-season ratings of any kind | Constraint 2 |
| **SP+ or FPI as features** | **Indirect violation** — both embed recruiting-based priors, so importing them imports the prior |
| **Vegas lines as features** | Market opinion is partly poll-driven; also destroys independence from the baseline we're measuring against |
| Conference identity as a feature | A reputation prior in disguise. Conference strength must *emerge* from results, never be assumed |
| Home-team "brand," stadium prestige, TV rating | Obviously |

## The complete allowed feature list

Nothing else may enter a design matrix (report 02 §3.10). The live table is
`LAYERS` in `src/cfbpoll/validate/leakage.py`, with a stated reason for every
single column, and `tests/unit/test_leakage.py` asserts this prose and that table
agree:

- **Games loader:** the canonical schedule projection — ids, the window triple,
  kickoff, site, teams, the scoreboard, and the division classes.
- **Plays loader:** the canonical play projection. Never the shipped
  `EPA`/`ppa`/`wpa`/`ep_*`/`wp_*` block.
- **EP (our expected-points model):** down, distance, yards to goal, points
  scored on a play, and the scoring segment — plus the two possession labels,
  which sign the next score to the side with the ball. Not the clock, not the
  score, and no team dimension in the fitted table, which the audit asserts
  separately. (Report 02 §3.10's summary sentence says "not the teams"; the
  implementation reads the labels and the report's sentence is the loose one.
  The distinction that matters is that `EPModel.table` is indexed
  `(down, distance bucket, yards to goal)` and by nothing else.)
- **L1:** **our** play value from that model, offense team ID, defense team ID,
  home/away/neutral, quarter, score margin, clock *(the last three only for
  garbage-time filtering)*
- **L2:** final score, team IDs, home/away/neutral, game type, kickoff date
  *(the last only for the recency weight, and inert while `recency_gamma = 1.0`)*
- **L3:** L1 and L2 outputs, team IDs, home/away/neutral, final score *(the blend
  regression's response is actual margin)*
- **L4:** L3 outputs, win/loss, schedule
- **Schedule odds (the headline):** L3 outputs, win/loss, schedule, and the
  division class, which selects the FBS-only q_ref pool. The scoreboard enters
  only through `sign(home_points − away_points)`.

## How the audit knows, rather than assumes

`cfbpoll audit-features` does not read the code and take its word for it. For
every layer it **rebuilds that layer's design matrix from the frame restricted to
the allow-list above, and requires the result to be bit-identical** to the one the
unrestricted frame produced. If a layer consumes anything else, the restricted
rebuild either raises (the column is required) or disagrees (the column is used),
and the audit names the culprit by adding each non-allow-listed column back on its
own until the unrestricted answer returns.

The consequence is worth stating plainly, because it is the difference between a
promise and a measurement. `conference_game` **is in the schedule frame on every
run** — the 2021 structural conference-championship fallback needs it — and every
run of the audit rebuilds all seven design matrices without it and gets the same
bytes. "We do not use conference identity" is therefore not a claim in this
repository. It is a result, recomputed before every poll is fitted, and published
on `model_params.json` under `feature_audit`.

## The trap this is really guarding

The banned list is easy to honour when the data arrives labelled. It is hard when
the banned values are sitting in the same file as the facts.

The SportsDataverse play-by-play parquet ships precomputed `EPA`, `ppa` and `wpa`
columns plus a six-column next-score probability block; the schedule files ship
`home_pregame_elo`, `home_postgame_elo` and `excitement_index` (report 01 §5.6).
CFBD documents PPA, win probability, WEPA, Elo, SRS and CORE as **proprietary
models** whose "exact formulas, fitted coefficients, training artifacts, and every
implementation detail are not part of the public documentation."

> Do not let these leak into the model just because they are conveniently present
> in the same file.

**This is not hypothetical, and it is the one place the constraint cost real
work.** Report 02 §3.1 specifies L1 as a ridge on play-level EPA, and the `EPA`
column is right there in the file the loader already opens. Honouring the ban
meant writing our own expected-points model — `src/cfbpoll/model/ep.py`, the
Carter/Romer/Burke next-score construction, about a hundred lines, every constant
in `configs/default.toml` under `[ep]`. It correlates with the shipped column at
**r = 0.847** over 221,945 plays in 2023, with matching standard deviations (1.516
ours, 1.514 theirs). That number is reported as a validation diagnostic and is
never fitted to; the function that computes it names the banned column in its own
signature so nobody can reach it by accident.

Every third-party rating is a **benchmark, never an input**. The audit is an
allow-list check, not a deny-list check, so an input nobody thought of fails
closed.

There is a second, practical reason beyond principle: CFBD warns that "model
changes can affect the comparability of values across periods." A backtest resting
on someone else's derived ratings can silently drift when they retrain. A backtest
resting on raw game facts cannot.
