# Two untouchables, and a registry of everything else

Until 2026-08-17 this page was called *The Five Hard Constraints* and it read as
five equals. That was wrong in a way that cost accuracy: it put "no human polls",
which is the reason the product exists, on the same footing as modelling choices
that were never anything but choices, and it made every one of them equally
frightening to touch. [ADR 0014](adr/0014-the-liberation.md) separates them. The
old text is not deleted — it is in the git history and in ADRs 0010 and 0012,
which say what this project believed and why.

**The base model has one job: predict as well as the data allows.** Two things it
may never do, and one promise about the record. Everything else is a lever, and
every lever is on this page with the measurement that set its default.

---

## Untouchable 1 — No human polls. Ever.

No AP poll, no coaches poll, no CFP committee ranking may be an input to
anything, in either product. They are **comparison targets, never fitting
targets**.

The subtle version is the dangerous one: fitting toward agreement with the
committee would reintroduce human poll bias through the back door. We report
Kendall's tau against the final committee top-25 and then **let the disagreements
be the product**.

The AP's August ballot is the Projection's headline baseline — the thing it is
trying to beat, and it does, 86.9% to 82.3% on week-one games over 2022-2025.
A baseline that is also an input measures nothing. **There is no lever for this
and there will not be one.**

## Untouchable 2 — No future data. Ever.

Every published number for a given week is computable from games played before
it. This one got *stronger* when the freezes came off, and the reason is worth
stating: once the objective is predictive accuracy, walk-forward honesty stops
being an ethic and becomes the definition of the measurement. An accuracy figure
computed with any knowledge of the games being scored is not a smaller result. It
is not a result.

Concretely, in `projection/chain.py`: for target season Y a system may read game
results from seasons ≤ Y−1, the offseason table for Y and the calendar of Y — all
three of which exist in August — and nothing else. Every constant is re-measured
per link from the seasons behind it. A system that cannot be built that way for a
season is reported **absent** for that season rather than given a shortcut, which
is why the model has no 2022 row: the archive starts in 2021 and fitting a recipe
on 2022 in order to score 2022 would be a description wearing a projection's
clothes.

This is also the one place we corrected ourselves rather than the world.
`fit.early_season_metrics` fitted its own intercept and home-field term by least
squares **on the very games it then scored**. Straight-up accuracy is invariant to
the slope but not to those two, so every early-season accuracy figure this project
published before 2026-08-17 was flattered by a home-field advantage tuned on the
answers. The chain takes its home-field constant from the prior season's fit.

## The promise about the record — every vintage is preserved

Nothing published is edited in place. Every board stays up with the coefficients
it ran under, the `git_sha` that produced it and the `config_hash` that
parameterised it. `projection-3.0.0` **supersedes** `projection-2.0.0`; it does
not correct it.

This is the mechanism that let the freezes go. The freeze bought one sentence —
*the coefficients did not move after we saw that season* — and cost a season of
data on every future refit, forever. The vintage record buys the same sentence
and costs nothing: "what did you say in August" is answered by the archive rather
than by refusing to learn.

---

# The levers

`src/cfbpoll/levers.py` is the machine-readable half of this page and
`cfbpoll levers` prints it. Every lever carries a plain-football name, a
published range, a default, **what measured that default**, and — where it has
been swept — what moving it costs. No lever ships with blank evidence; a test
asserts it.

| lever | what it does | default | what set it |
|---|---|---:|---|
| **How far an FCS rating falls when it meets FBS** | a rating earned outside FBS does not carry intact into an FBS game | 1.0 | 13.4 points, se 0.6, from 602 crossover games |
| **Credit for being the kind of program that moves up** | a promoted program is not a randomly drawn FCS team | 1.0 | 9.8 points, se 1.9, from 68 games by six promoted programs |
| **Cap a promoted team at the best any promoted team has done** | the guard that stops the credit above being extrapolated | on | James Madison, 2022, 32nd in FBS |
| **How much the year before last still counts** | programs are not rebuilt every August | 0.2 | a 216-cell walk-forward grid, 2022-2025 |
| **How much home field is worth in August** | carried ratings are spread wider than this season's truth | 1.5 | the same grid |
| **Where a blowout stops counting extra** | winning by 60 is barely better than winning by 40 | 32.0 | ADR 0007, a 416-cell factorial |
| **How much a win is worth on its own** | the discontinuity that makes this football and not scoring margin | 7.0 | ADR 0007 |
| **Whether September still counts in December** | at 1 the season does not decay | 1.0 | available and off, report 02 §3.1 |
| **What sorts the table** | schedule odds, or the win-loss résumé | schedule odds | ADR 0005 |
| **Let the model know which conference a team is in** | **off, and it is the one that stays off** | 0.0 | see below |

Also levered, and fitted rather than swept: how much a returning offence is
worth, the cost of a new head coach, and how much the portal moves a team. Their
standard errors ship beside them and two of the three have never cleared two of
their own.

## Conference identity, which is out of the base and stays out

A conference is a **label, not a measurement**. Conference strength has to emerge
from results or the poll is a brand ranking with arithmetic on top, and
*nothing in it knows what a conference is* is the fairness spine of the whole
product.

**This is not a claim in this repository. It is a result, recomputed before every
fit.** `conference_game` is in the schedule frame on every run — the 2021
structural conference-championship fallback needs it — and `cfbpoll
audit-features` rebuilds all seven design matrices without it and requires the
same bytes. It is published on `model_params.json` under `feature_audit`.

It ships as a lever, defaulted to zero, because a refusal a reader cannot see the
switch for is not a refusal they can check. **The default does not move without a
measured accuracy number the owner has seen.** No such number is offered here,
and if conference-as-feature is ever found to help materially, that finding gets
published before anything is adopted.

---

# What the Poll additionally promises

The two untouchables govern both products. The Poll — the thing that ranks what a
team has *done* — makes three further promises that are properties of what it is
for rather than constraints on what may be measured.

## It adjusts for who you played, always

Every rating is adjusted for opponent and venue, **simultaneously, not
iteratively**: offence and defence are solved jointly in one linear system, which
makes the "10 sacks against an FCS team" problem vanish by construction. FCS
teams get their own coefficients under the same penalty rather than being pooled
into one node, which is exactly ESPN's pre-2015 FPI failure.

The all-divisions fit has a known cost, and since 2026-08-17 it has a treatment
rather than a caveat: ridge under-separates two blocks connected by only ~120
games a season, and `projection/crossdivision.py` measures the residual gap from
the crossover games themselves and corrects it. See ADR 0014 §3.1.

## It can be re-run with hindsight

Every rating is a pure function `R(evaluation_week N, data_window K)`: live
ranking for week N is `R(N, N)`, hindsight ranking is `R(N, final)`. This is why
the estimator is a batch refit and not an Elo — Elo is path-dependent and has no
principled "week 5 with hindsight."

This promise **chose the headline ordering**, and it is worth recording that it
did real work rather than sitting on a page: under the wins-based résumé an
unbeaten team's rating saturates at the published bracket `+60`, which is not a
function of the schedule, therefore not a function of `K`. Measured: from week 11
of 2023 onward, the résumé ordering moved **no unbeaten team by a single place**
between the live and hindsight surfaces. See [ADR 0005](adr/0005-headline-ordering.md).

## Everything is published, and a stranger can reproduce it

Every equation, every constant, every input — and every published poll
reproducible by someone with no API key, no account and no permission from
anyone. `model_params.json` ships every constant every week; `_run.json` ties
every poll to the exact `git_sha`, `config_hash` and `archive_hash` that produced
it; a CI job recomputes a historical week offline and asserts a byte-match on
every push.

Since ADR 0014 this clause carries the lever registry too. Publishing a number is
not transparency if the reader cannot tell which of the numbers were choices.

## Reputation priors, and where they are now allowed

The old constraint 2 banned recruiting rankings, talent composites, returning
production, prior-season ratings and coaching tenure outright. That ban **still
holds for the Poll, mechanically**, and the banned-input table below is
unchanged. What ADR 0010 established and ADR 0014 keeps is that the ban is on the
Poll's published rankings, not on this repository: the Projection is a second
product that uses last season's ratings, returning production and coaching
changes, and the audit is hostile in one direction only.

**The Projection reads the Poll. The Poll may never read the Projection.**

Recruiting stars remain refused in both, and that refusal is the one place the
project spends accuracy on principle. They are on the portal feed, they are not
banned by the audit, a star-weighted net flow would very likely predict better,
and they are refused anyway — because using one where it is legal would make the
Poll's refusal look like a technicality. That is a choice, it is not a
measurement, and it is written here as a choice.

---

# The headline promise

Everything above says what the poll may not do, or what a reader may change. This
says what the poll claims to DO, in the one sentence it can be held to:

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

**"Measured, never assumed"** is the no-reputation rule applied to the thing everyone
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
not a function of the data window, and therefore retroactive re-ranking — the
project's most differentiated promise — could not move an unbeaten team at all. From week 11 of 2023 onward it moved none of them by a single place.
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
weekly workflow and the reproducibility workflow. Nothing on it moved when the
freezes came off.

| Banned input | Why |
|---|---|
| AP / Coaches / CFP rankings | Untouchable 1, directly |
| Recruiting rankings, talent composites | Reputation prior. Refused in the Projection too, on the record |
| Returning production / returning starters | Reputation prior in the Poll. The Projection uses it, and the audit is hostile in one direction only |
| Prior-season ratings of any kind | Reputation prior in the Poll. The Projection is built on them |
| **SP+ or FPI as features** | **Indirect violation** — both embed recruiting-based priors, so importing them imports the prior |
| **CORE, or any CFBD-served rating, as a feature** | Third-party fitted models. Banned by the same rule and enforced by the same allow-list rebuild, which fails closed whether or not a rating was ever banned by name. The roster of what we compare against is `cfbpoll benchmarks` and [data-sources.md](./data-sources.md) |
| **Vegas lines as features** | Market opinion is partly poll-driven; also destroys independence from the baseline we're measuring against |
| Conference identity as a feature | A label, not a measurement. Conference strength must *emerge* from results. Shipped as a lever, defaulted off, and the default does not move without a measured number the owner has seen |
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

## The Projection, and why it does not appear in this document

Since 2026-08-15 this repository publishes a **second product**: the
[Projection](adr/0010-projection-and-poll.md), a preseason ranking built from
last season's fitted ratings plus returning production, the transfer portal and
coaching changes — three of the things the table above bans by name.

**None of this changed when the Projection arrived.** This document is the *Poll's* charter. It says
what the Poll may not do, and the Poll does not do any of it: every design matrix
above is still rebuilt from its allow-list before every fit and still comes out
bit-identical.

What changed is that the audit now knows there are two products, and it is
**hostile in one direction only**:

- every column the projection package produces — `returning_*`, `portal_*`,
  `coach_*`, `prior_power*`, `projected_*` — is in `PROJECTION_INPUT_PATTERNS`,
  spliced into the banned table above;
- for a **poll layer**, one of them being merely **present in the frame is a
  violation**, with no consumption test required. That is the one asymmetry in
  the audit and it is earned by provenance: `excitement_index` is in the games
  frame on every run because ESPN shipped it beside the facts, but a projection
  input can only be in a poll frame because somebody in this repository put it
  there.

**The Projection reads the Poll. The Poll may never read the Projection.**
`tests/unit/test_projection_separation.py` plants one in a poll design matrix and
requires the audit to name it; `cfbpoll projection audit` prints both halves in
one report, with the product each layer was judged by beside it.

The Projection has a banned list of its own, and the two entries on it are the
ones that show the separation is a design rather than an excuse: **human polls**
(the AP preseason top 25 is the Projection's headline baseline, and a baseline
that is also an input measures nothing) and **third-party fitted models** (SP+,
FPI, Elo, CORE and CFBD's PPA, refused here for exactly the reasons this page
already gives). Recruiting stars are available on the portal feed, are not banned
by the audit, and are refused anyway — because using one where it is legal would
make the refusal above look like a technicality.

The set is enumerable rather than folklore: `cfbpoll benchmarks` prints it, with
two columns that carry the whole argument — whether the implementation is open,
and whether its author publishes error metrics. As of 2026-08-13, of the five
series CFBD serves, **none is open source and only SP+ publishes error metrics**.
That includes CFBD's own **CORE** (Bill Radjewski, published 2026-08-08), which
is archived here for comparison and named in the deny list as `cfbd_core` and
friends rather than as the bare substring `core` — which would fire on `score`,
`score_margin` and half the allow-list, and a report that cries wolf on the
scoreboard is a report nobody reads on the day it matters.

There is a second, practical reason beyond principle: CFBD warns that "model
changes can affect the comparability of values across periods." A backtest resting
on someone else's derived ratings can silently drift when they retrain. A backtest
resting on raw game facts cannot.
