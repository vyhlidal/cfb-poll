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

Nothing else may enter a design matrix (report 02 §3.10):

- **L1:** play EPA, offense team ID, defense team ID, home/away/neutral, quarter,
  score margin, clock *(the last three only for garbage-time filtering)*
- **L2:** final score, team IDs, home/away/neutral, game type
- **L3:** L1 and L2 outputs
- **L4:** L3 outputs, win/loss, schedule

## The trap this is really guarding

The banned list is easy to honour when the data arrives labelled. It is hard when
the banned values are sitting in the same file as the facts.

The SportsDataverse play-by-play parquet ships precomputed `EPA` and `wpa`
columns; the schedule files ship `home_pregame_elo`, `home_postgame_elo` and
`excitement_index` (report 01 §5.6). CFBD documents PPA, win probability, WEPA,
Elo, SRS and CORE as **proprietary models** whose "exact formulas, fitted
coefficients, training artifacts, and every implementation detail are not part of
the public documentation."

> Do not let these leak into the model just because they are conveniently present
> in the same file.

Every third-party rating is a **benchmark, never an input**. The audit is an
allow-list check, not a deny-list check, so an input nobody thought of fails
closed.

There is a second, practical reason beyond principle: CFBD warns that "model
changes can affect the comparability of values across periods." A backtest resting
on someone else's derived ratings can silently drift when they retrain. A backtest
resting on raw game facts cannot.
