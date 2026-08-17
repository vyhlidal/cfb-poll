# AGENTS.md

**Somebody cloned this repository and pointed you at it. Here is what they have
and what you are going to do with them.**

This is The Poll: an open, bias-free college football ranking that lives at
[thepoll.ai](https://thepoll.ai). It ranks teams on how hard their season actually
was, measured from results and never assumed from reputation. No AP voters. No
coaches' ballots. No recruiting rankings. Nothing in the math knows what a
conference is. Every equation and every constant that produces the published board
is in this repository, and that is the entire point: an argument about a ranking
gets settled by running one, not by talking. The person you are working with
disagrees with something about how football teams get ranked. Everybody does. Your
job is to find out exactly what, turn it into a working poll, run it, and score it
against the original on the same harness that scores the original.

You do not need them to write any Python. That is what you are for.

## If you read nothing else

Ten facts that stop the failures a fresh assistant actually hits. Everything below
this block is the long version.

1. **`uv` is the only prerequisite.** Not Python, not Docker, not `sudo`.
   `make .venv` first.
2. **`make archive` is a large download** (see [the targets](#the-targets) for the
   current size). Say so before you start it. `make archive SEASONS=2023` while
   iterating.
3. **Prefer the `make` targets over the bare CLI.** Targets that fit a model pin
   single-threaded BLAS; the bare CLI does not, and multi-threaded reductions sum
   in a nondeterministic order. `recipes` and `publish` fit nothing and are safe
   bare.
4. **Give every run its own `OUT`.** `out/` is the default and output files are
   overwritten in place with no prompt. `OUT=out/<slug>` keeps two boards apart.
5. **`ONLY=schedules,crosswalk` changes the model.** No plays means L1 cannot fit
   and the blend degrades to L2. **A normal rank does this silently, with no
   error**, so check `power_source` in `model_params.json` before comparing
   anything. (A play-level *challenger* is the exception: it raises
   `FileNotFoundError` instead.)
6. **`make fixtures` defaults to a path outside the repo** that does not exist in
   your fork. Always pass `FIXTURES=out/data` or it breaks.
7. **Uncapped margin is spelled `c = inf`**, a bare TOML float. It is the one
   value with a required spelling; a misspelled key is refused loudly, but do not
   improvise here.
8. **2025 is a sealed holdout.** Single shot. Do not tune against it.
9. **Numbers: quote the ones pinned in `configs/default.toml` or in source;
   regenerate anything a run produced.** Details under
   [the vocabulary](#the-vocabulary-so-you-can-answer-without-opening-a-file).
10. **Their team's ranking is the point.** Get to a board they can look at before
    you get to a scorecard.

---

## The flow you are offering

Say this to them early, in your own words, and then run it. It is five steps and
they own every one of them.

**1. I ask you what you actually believe about football.** Not about code. About
football. Does a 49-point win say more than a 3-point win, or is running the score
up on a bad team worth nothing? Should an undefeated team from a weak league
finish ahead of a one-loss team from a brutal one? When a team you beat in
September turns out to be terrible, should that September win be worth less in
December? Is a road win worth more than a home win, and how much more? There are
no wrong answers here and you should not steer them toward one. Their answers are
the specification.

**2. We turn your answers into settings, or into code.** Most convictions are
already a lever in this repo and cost one line to pull. Some are not, and those
become a real change to the model. The ladder is in
[The levers](#the-levers-cheapest-first) below. Always try the cheapest rung that
honestly expresses what they said, and tell them when you are climbing past it and
why.

**3. We run your version, and you see your board.** It produces a ranked table
from the same archive the published poll reads. This is the step where they find
out where their own team landed, and it is worth reaching quickly.

It is **not** one command, and do not tell them it is: it is `make .venv`, then a
one-time archive download, then a rank. See [First run, end to end](#first-run-end-to-end).

**4. We score it against the original.** Same harness, same baselines, same
metrics, same walk-forward window, and the same scoreboard the published poll was
scored against:

```bash
make challenge CHALLENGE_ENTRY=configs/challengers/<name>.toml   # constants
make challenge CHALLENGE_ENTRY=configs/challengers/<name>.py     # a method
```

Either entry form works, and it **computes its own baselines, so `make backtest`
is not a prerequisite.** The scorecard gives straight-up win percentage, MAE,
RMSE, Brier, log loss, calibration and ordering violations, side by side with the
published poll and with five computed baselines, plus the publication gate applied
to all of it. It lands in `out/challenge/`.

**The one thing that will bite you: seasons.** Scoring defaults to `2021-2023`,
but the fast iteration loop tells people to fetch one season. If the archive only
holds 2023, match them or the run asks for data that is not on disk:

```bash
make challenge CHALLENGE_ENTRY=... CHALLENGE_SEASONS=2023
```

Say which seasons a score covers when you report it. A number from one season is
not the same claim as a number from three.

**The number is reproducible. It is not the last word, so do not call it
"mechanical" and walk away.** Three seams decide how much it is worth, and you
should say all three out loud:

- **`make challenge` cannot score an ordering.** It scores rating *methods* and
  constants. A parameter entry is filed under the `schedule_odds` row whatever its
  config says the headline should be, so if their conviction is about **what sorts
  the board**, this command will hand back a number that did not test it. That has
  its own command and its own metric:
  [Scoring an ordering conviction](#scoring-an-ordering-conviction). Route them
  there instead of reporting a score that answers a different question.
- **A recipe is not directly scorable.** Scoring one means transcribing its
  constants into a challenger TOML, and part of a recipe does not survive that
  trip. See
  [Recipe to challenger](#recipe-to-challenger-the-transcription-that-matters).
- **The scorecard measures prediction, not desert.** It asks "does this forecast
  games better", which is a different question from "is this the right way to rank
  a season". Somebody whose conviction is about fairness can lose every metric and
  still be making a coherent argument. Say so rather than letting a table settle a
  question it was not asked.

The project already says this about itself: no recipe has been backtested end to
end as a system, and `configs/recipes/README.md` lists that under "where this is
weak".

If their idea loses, say so plainly and show them where. A losing example is
already committed here on purpose, because that is what happens to most ideas and
pretending otherwise would make the harness useless.

**5. We prepare your presentation surface.** A ranking nobody can see is not a
poll. Their version gets the same share cards, the same board documents and the
same published-fixture tree the real one gets, carrying their name and their
constants. See [Ship it](#ship-it).

Do not run all five and hand them a report at the end. Stop after step 1 and read
their answers back as a plan. Stop after step 3 and show them their top 25 before
you score anything, because the first thing anyone wants to know is where their
own team landed.

---

## What the poll actually says

You need to be able to explain this without opening a file, because it is the
first thing they will ask.

Teams are ranked on **schedule odds**: `−log10 P(W ≥ W_t)`, the probability that a
team of published reference quality would have gone at least this well against that
exact schedule. The tail is exact, a Poisson-binomial convolution, not a
simulation.

The load-bearing consequence, and the thing that surprises people: **your own
margin never enters the rank key.** Beat a team by one and you get exactly what
you get for beating them by forty. What beating *them* is worth was fitted from
margins, theirs and everyone else's. Margin is in the engine and out of the
headline.

Three numbers ship on every row, always:

| | what it answers | role |
|---|---|---|
| **Schedule odds** | How hard was that to do? | **This is the poll.** |
| **Résumé (L4)** | What have you earned? | Published beside it |
| **Power (L3)** | How good are you? | **This is the engine.** Never hidden |

Every row also carries a **90% rank interval**. The headline poll begins in
**week 5**; weeks 1 through 4 publish a connectivity report and clearly-labelled
provisional output, because in September nobody knows yet and the honest move is
to show the math for why.

Read [`README.md`](README.md) for the full version and
[`docs/methodology.md`](docs/methodology.md) for the math.

### The vocabulary, so you can answer without opening a file

You will meet these in the source tree and in conversation. Learn them now.

- **L1, efficiency.** Ridge on garbage-time-filtered play value. One offence and
  one defence coefficient per team, plus home field.
- **L2, results.** Ridge on *compressed* scoring margin, `s = C·tanh(m/C) + β_w·sign(m)`.
  "Compressed" is the whole point: `tanh` means a 40-point win and a 60-point win
  are worth nearly the same, which answers the run-up-the-score objection without
  throwing margin away.
- **L3, power.** The walk-forward blend of L1 and L2, weights fitted out of
  sample. This is the engine, and the answer to "how good are you".
- **L4, résumé.** Root-solve for the team quality whose expected results against
  that exact schedule equal the actual ones. The answer to "what have you earned".
- **Schedule odds.** The headline. Described above.
- **R(N, K).** The retroactive grid: the ranking for evaluation week `N` computed
  with data through week `K`, for every `K ≥ N`. `R(5, 5)` is what we said in
  week 5. `R(5, final)` is what week 5 was actually worth once the season told us
  who those opponents were. The gap between them is the retroactive product, and
  constraint 4 exists to make it principled.
- **The publication gate.** Five criteria in `[gate]` in `configs/default.toml`
  that a system must clear to be published: straight-up accuracy ≥ 0.70, MAE
  ≤ 12.8, RMSE ≤ 15.8, calibration deviation ≤ 5.0 points, and Brier beating every
  baseline. The project publishes its own gate verdict rather than hiding it.
- **The tau line.** Kendall's tau of 0.985 between two orderings, the threshold
  from ADR 0006 for calling a constant a real `dial` versus a mere `convention`.
- **Connectivity.** How well the schedule graph ties the league together. In weeks
  1 through 4 teams have barely played each other, so opponent adjustment has
  little to work with, and the poll publishes that diagnostic instead of a
  ranking.
- **The holdout.** 2025. Sealed, single shot.

**"Variant" means three unrelated things here.** Keep them straight or you will
send somebody to the wrong command:

| phrase | what it is | where |
|---|---|---|
| **playground variant** | a one-knob perturbation of the published poll, as a thin ordering document | `publish/variants.py`, `make variants`, rung 3 |
| **card variant** | which canvas a share card is drawn on (`top5`, `top25_x`, `connectivity`, …) | `publish cards --variant` |
| **challenger variant** | an outside entry, `kind = "parameter"` or `"structural"` | `configs/challengers/`, rung 4 |

`--variant` on a command line is always the card sense.

**Which numbers in this file you may repeat.** There are two kinds here and they
have opposite rules:

- **Pinned by a file, safe to quote.** Constants and thresholds that live in
  `configs/default.toml` or in source: `c = 32`, `beta_w = 7`, the gate's five
  criteria, the 0.985 tau line, and the three ordering strings. These can still go
  out of date, since this file is a copy of them rather than the source. If one
  matters to a decision, open the config and confirm it.
- **Produced by a run, never quote from here.** Anything about where a team
  landed, what a metric came out at, or how many rows moved. The recipe table's
  Liberty placements are this kind. **Regenerate them or read them out of the run
  before you say them to anybody**, because a briefing file cannot know what has
  changed since it was written.

When you are unsure which kind you are holding, check `git log` and the ADRs
rather than trusting this page.

---

## The rules that do not bend

Bring these up before the person spends an hour on an idea the harness will
reject. They are not style preferences, they are why the project exists.

1. **No human polls as inputs.** AP, Coaches and CFP are comparison targets only,
   and never fitting targets either.
2. **No reputation priors.** No recruiting rankings, no talent composites, no
   returning production, no coaching tenure, no conference identity, no
   prior-season ratings. This is the one that catches people, because it
   disqualifies the obvious features.
3. **Opponent adjustment is mandatory**, simultaneously, in one linear system.
4. **Retroactive re-ranking has to work.** "Now that we know that opponent was
   overrated, how good was week 5 really?" needs a principled answer, which is why
   the estimator is a batch refit rather than an Elo.
5. **Full transparency.** Every constant published, every poll traceable to the
   commit, config and data that made it.

Plus three from the research that will bite you specifically:

- **Walk-forward is strict.** To predict week N you fit on data through week N−1.
  This is the easiest mistake to make when the estimator is a batch refit, and it
  invalidates everything downstream.
- **2025 is a sealed holdout.** Single shot. The harness refuses it without
  `--unlock-holdout`. Do not tune against it, and if you somehow do, say so.
- **Determinism is a feature.** Never `np.random.seed`. Use an explicit
  `Generator(PCG64(seed))` with `SeedSequence.spawn`. Sort before writing. Never
  let dict or groupby iteration order reach a file.

  **This one has a trap in it that will catch you.** Fits must run with
  single-threaded BLAS, because multi-threaded reductions sum in a
  nondeterministic order. Every `make` target sets that for you. A bare
  `uv run cfbpoll rank` does not, so prefer the make target, and when you do need
  the CLI directly, carry the prefix yourself:

  ```bash
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    uv run cfbpoll rank --season 2023 --through-week 15 --recipe just-win
  ```

  **It matters for anything that fits a model**, and the list is longer than it
  looks: `rank`, `backtest`, `grid`, `bootstrap`, `challenge run`, and
  **`audit-features`**, which is easy to assume is a read-only check but rebuilds
  the design matrices through `ep.fit` and `schedule_odds.fit` to prove no banned
  input reached them.

  It genuinely does not matter for `recipes` (which prints a roster) or
  `publish` (which reads a finished run directory and writes files). Those two
  are safe bare.

  **The reliable rule: if a command produces a number, use a make target.** Only
  reach for the bare CLI when there is no target, and then carry the prefix.

Regularization is **not** a reputation prior, and this distinction matters when
someone objects. Ridge shrinks an unknown team toward *league average*, which is a
statement about our ignorance. A recruiting prior shrinks a team toward *what we
think of its brand*, which is the bias this project exists to delete.

Full text and the banned-input table: [`docs/constraints.md`](docs/constraints.md).

**The leakage audit is automatic, so you do not have to remember it.**
`cfbpoll rank` runs it *before* it fits anything, which means no poll is ever
published from an unaudited fit, and `make rankings` therefore audits every run
you do. The standalone `cfbpoll audit-features` verb exists to audit a season or
window **without** ranking, and to get the full report as JSON. You need it for
inspection, not for safety.

### Which ADR answers which argument

Most objections a person raises have already been argued out and written down.
Find the record before you re-litigate it from scratch, and read it *with* them
rather than using it to shut them down. A decision that was made on evidence can
be changed by better evidence, and several of these say so themselves.

| If they say... | Read |
|---|---|
| "Why is the poll sorted by odds and not by résumé?" / "unbeatens should be first" | [ADR 0005](docs/adr/0005-headline-ordering.md) + [the study](docs/analysis/headline-ordering-study.md) |
| "Where did C = 32 and beta_w = 7 come from? They look arbitrary" | [ADR 0007](docs/adr/0007-tuned-constants.md), [campaign 1](docs/analysis/tuning-campaign.md), [campaign 2](docs/analysis/campaign-2.md) |
| "Why fit on that set of teams? Why are FCS teams in there?" | [ADR 0006](docs/adr/0006-fit-universe.md) |
| "Recent games should count more" / "why this accumulation window?" | [ADR 0009](docs/adr/0009-accumulation-window.md) |
| "Just add home field from last season, everyone knows it" | [ADR 0008](docs/adr/0008-league-structural-home-field.md). **Open**: it puts the question to the owner rather than answering it |
| "A ranking is subjective, so this whole thing is fake" | [ADR 0011](docs/adr/0011-recipes.md). The project agrees, and ships three value systems |
| "Can it predict next season?" | [ADR 0010](docs/adr/0010-projection-and-poll.md). Yes, as a separate product that may never touch the poll. [ADR 0013](docs/adr/0013-projection-measurement-defects.md) is its repaired measurement |
| "Why is 2025 special?" | [ADR 0012](docs/adr/0012-2025-opens.md) |
| "Why Python?" / "why is the data in a GitHub release?" / "why files not a database?" | [ADR 0001](docs/adr/0001-python-not-rails.md), [0003](docs/adr/0003-storage.md), [0004](docs/adr/0004-files-are-truth.md) |

If their argument is genuinely not in there and it holds up, that is an ADR worth
writing, and rung 5 says so.

---

## The map

```
src/cfbpoll/
  cli.py              every command. Start here when you need to know what exists
  config.py           config load + merge_overlay (refuses unknown keys)
  recipes.py          the named value systems, and EVIDENCE_KEYS (see below)
  ingest/             archive sync, the MIT parquet loaders, CFBD client, teams
  model/
    ep.py             our own expected-points model. NOT the archive's EPA column
    l1_efficiency.py  ridge on play value
    l2_results.py     ridge on compressed scoring margin
    l3_power.py       the walk-forward stacked blend. The engine
    l4_resume.py      root-solve for the quality that explains the results
    schedule_odds.py  THE HEADLINE. The exact Poisson-binomial tail
    retro.py          R(N,K), the retroactive re-ranking surface
    bootstrap.py      the 90% rank intervals
  backtest/
    walkforward.py    the harness
    challenge.py      how an outside idea gets scored
    baselines/        colley, elo, srs, random_walker, winpct
  publish/
    serving.py        a run directory -> the document the site and cards read
    fixtures.py       the published JSON tree
    cards.py          the share cards. SITE_DOMAIN lives here
    variants.py       the eight one-knob variants
  validate/
    leakage.py        rebuilds every design matrix and proves no banned input got in
    data_quality.py   the gate that halts publication
  ops/
    guard.py          may this clock run, and is this week already published
    preflight.py      which verbs the Sunday job calls are still stubs
  projection/         THE PROJECTION: a labelled preseason prediction, never the
                      poll. Kept separate on purpose (ADR 0010)

configs/
  default.toml        EVERY model constant, with citations. The methodology
  recipes/            the three published value systems
  challengers/        outside entries. This is where a new idea goes
ops/                  THE SUNDAY AUTOMATION, delivered and armed nowhere
  arming.toml         the safety catch. Three clocks and one step, all `false`
  bin/weekly.sh       THE job. GitHub Actions and the VPS timer both run this file
  bin/deliver-fixtures.sh   pushes the week to the site repo. ARMING THIS DEPLOYS
                      thepoll.ai, which is why it has its own switch
  bin/pull-cfbd-archive.sh  the Mac's copy of the private archive (ADR 0015)
  n8n/                the clock and the dead-man's switch, ready to import
  systemd/            the VPS fallback unit and timer, ready to install
docs/
  constraints.md      the five rules, with the banned-input table
  methodology.md      the math
  adr/                fifteen decision records. Read these before arguing with one
  runbooks/           procedures a human runs: the Sunday automation, the VPS
                      install, the archive sync
  analysis/           the studies, including the independent review that took an
                      earlier version of the README apart
demo/                 committed real output. Boards, backtests, scorecards
tests/                unit, property and golden
```

---

## The levers, cheapest first

Climb this ladder in order. Tell the person which rung you are on.

**First, check what shape their conviction is, because the ladder only fits one of
them.** Rungs 1 to 4 move *continuous constants and orderings*. A belief like
"margin should count for less" is a knob and the ladder is built for it. A belief
like **"an unbeaten team must always finish above a team with a loss"** is a hard
rule, and no constant delivers "always". Say that difference out loud rather than
handing someone a recipe that mostly does what they asked:

- **Get as close as a lever gets, and name the gap.** `just-win` orders on the
  wins-based résumé, where every unbeaten team saturates at the same published
  bracket. That is very close to "unbeatens first" and it is not a guarantee.
- **Then show them the price, because this one is written down.** That same
  saturation is why the retroactive re-ranking cannot move an unbeaten team by a
  single place, in any week, in any direction. `just-win`'s own `tradeoffs` list
  says so, and so does [ADR 0005](docs/adr/0005-headline-ordering.md). A hard rule
  usually costs something specific, and finding that cost together is more useful
  than either granting the rule or refusing it.
- **A real guarantee is rung 5**, a change to the ordering itself, and it needs an
  ADR because it is a constraint rather than a value.

### Rung 1: a recipe

A ranking is a value system, and three are already published and named. This costs
one flag.

```bash
uv run cfbpoll recipes                      # the roster, with costs. Fits nothing
make rankings RANK_SEASON=2023 RANK_WEEK=15 RANK_RECIPE=full-merit OUT=out/full-merit
```

**Name the season and week even though they have defaults.** The defaults are
`RANK_SEASON=2023 RANK_WEEK=15`, which happen to match the season this doc's
examples fetch. Spell them out anyway, because the moment somebody's archive holds
a different season the silent default becomes a missing-data error on their very
first command, and an explicit flag is the difference between a confusing failure
and an obvious one.

| recipe | what it believes | 2023: where does 13-0 Liberty land? |
|---|---|---:|
| **full-merit** | margin at face value, uncompressed | **#20** |
| **house** | margin in the engine, out of the headline. **The published poll** | **#10** |
| **just-win** | winning is what counts, running it up buys nothing | **#2** |

*(That last column is a run-produced number. It is here to show the spread, not to
be quoted. Regenerate it before you tell anyone where their team lands.)*

If what they told you in step 1 is "running up the score should count for
nothing", you are done in one command. Show them `just-win` and the rows that
move: the side-by-side board is [`demo/2023-recipes.md`](demo/2023-recipes.md),
and the count of movers is a run-produced number, so read it off that document
rather than from here.

### Rung 2: their own recipe

A recipe file is a `[recipe]` block plus **only** the constants it changes. Copy
[`configs/recipes/just-win.toml`](configs/recipes/just-win.toml) and edit.

**How it gets picked up:** drop it in `configs/recipes/`, set `slug` to match the
filename (`recipes.load` enforces that), and it is immediately available as
`--recipe <slug>`. There is no registry to edit. `config.merge_overlay` refuses a
key that `configs/default.toml` does not define, so a typo like `beta-w` fails
loudly instead of quietly publishing a poll under constants nobody set.

The two constants people actually want are in `[margin]`. The response curve is
`s = c·tanh(m/c) + beta_w·sign(m)`, so both are in points:

- **`c`** (default `32.0`), the compression scale. Lower means a blowout counts
  for less. `just-win` uses `1.0`.

  **"Uncapped" is written `c = inf`**, a bare TOML float, exactly as
  [`full-merit.toml`](configs/recipes/full-merit.toml) writes it. It is the limit
  of the tanh family, not a missing value or a sentinel string: at `inf` the
  response becomes `s = m + beta_w·sign(m)` and margin enters at face value.
  `design.tanh_term` takes that limit explicitly, because numpy would evaluate
  `inf * tanh(m/inf)` as `nan` and take the poll down quietly. Do not write
  `"uncapped"`, `0`, or `-1` and expect it to work. (The string `uncapped` does
  appear in the codebase, but only as the *label* of the `margin-c-uncapped`
  playground variant, never as a config value.)

- **`beta_w`** (default `7.0`), the win premium. This is the constant that makes
  it a football ranking instead of a scoring-margin ranking. Set it to `0` and
  winning stops mattering on its own. `full-merit` uses `12.0`, the top of
  campaign 2's grid.

**`[publication] headline_ordering` picks what sorts the board, and it accepts
exactly three strings.** Anything else raises `unknown [publication].headline_ordering`:

| value | what sorts the table | used by |
|---|---|---|
| `schedule_odds` | how hard the season was | the published poll (default) |
| `L4_resume` | the wins-based résumé | `just-win` |
| `L4_resume_margin` | the margin-aware résumé | `full-merit` |

**Set `headline_ordering` and nothing else. Do not set `headline_layer`.** That is
the whole rule, and both shipped recipes follow it. The reason, for when you meet
it: `[publication] headline_layer` is the human-readable name stamped on
artifacts, and `poll.headline_ordering` raises if the two disagree, because two
names for one fact is a drift hazard. Omitted, it is derived for you
(`schedule_odds -> C_schedule_odds`, `L4_resume -> L4_resume`,
`L4_resume_margin -> L4_resume_margin`). Setting it by hand buys nothing and can
only cost you a raise.

**Numbers may be written as ints.** `beta_w = 10` is accepted exactly like
`beta_w = 10.0`. The shipped files use the float form for readability, and `inf`
is the one value with a required spelling.

**`tradeoffs` is required and must be non-empty.** `recipes.load` refuses a recipe
that will not state its own cost. Do not write a throwaway line to get past the
check. Ask the person what their poll gets wrong and write down what they say,
because that answer is usually the most interesting thing in the file.

**A recipe changes values. It never changes evidence.** `recipes.EVIDENCE_KEYS`
lists the keys a recipe may never touch (the fit universe, the walk-forward flags,
the holdout, the FCS policy, `[constraints]`, `[weights]`), and
`assert_values_only` refuses the file at load time if it names one. If their idea
needs to change what data the model sees, it is not a recipe. Go to rung 4.

### Rung 3: a one-knob playground variant

This is the **playground** sense of "variant" (see the vocabulary above; the word
means three different things in this repo).

Eight perturbations of the published poll already exist as thin ordering
documents, for showing someone how much a single constant is actually worth:
`margin-beta-w-0`, `margin-beta-w-3`, `margin-beta-w-12`, `margin-c-1`,
`margin-c-18`, `margin-c-uncapped`, `ordering-l4-resume`,
`ordering-l4-resume-margin`. Each carries a verdict of `dial` or `convention`
computed against a 0.985 tau line. `make variants` regenerates them.

This is the rung that answers "does this constant even matter?" before anyone
spends real time on it. Often the answer is no, and that is worth knowing early.

### Rung 4: a challenger

This is a new rating method, and it is the contribution the project most wants.
There are two forms, and **the file extension and the declared `kind` must agree**
or the loader refuses the entry.

#### Form A: a parameter variant (`.toml`, `kind = "parameter"`)

Copy [`configs/challengers/beta-w-4.toml`](configs/challengers/beta-w-4.toml).
The whole schema is a `[challenger]` block plus the constants you change:

```toml
[challenger]
name   = "beta-w-4"        # REQUIRED. Any string. Not tied to the filename
kind   = "parameter"       # REQUIRED. "parameter" for .toml
author = "your name"       # optional
notes  = """Optional. Why you think this is right."""

[margin]                   # then ONLY the constants you change
beta_w = 4.0
```

**A challenger block is not a recipe block.** There is no `slug`, no `stance`, no
`one_liner`, no `manifesto`, and **`tradeoffs` is not required** and is not read.
Only `name` and `kind` are required; `kind` must be exactly `parameter` or
`structural`. Two more rules the loader enforces: a `.toml` that overrides no
constant is refused (an override that changes nothing would publish a finding
about a model nobody ran), and every key must exist in `configs/default.toml`,
since `merge_overlay` rejects unknown keys rather than absorbing a typo.

#### Form B: a structural variant (`.py`, `kind = "structural"`)

A module with a module-level `CHALLENGER` dict (not a TOML block) and one
function. See [`iterative_margin.py`](configs/challengers/iterative_margin.py),
about forty lines:

```python
CHALLENGER = {
    "name": "iterative-margin",
    "kind": "structural",
    "author": "you",
    "needs_plays": False,   # True if rate() reads the play archive
    "notes": "...",
}

def rate(games, plays, through_week, state=None) -> dict[str, float]: ...
```

**The `rate()` contract, precisely.** Guessing at any of this wastes a run:

- **Key on the team NAME, a string.** `games["home_team"]` is a polars `String`
  holding `"Jacksonville State"`, not an id number. Return
  `{"Georgia": 18.4, ...}`.

  **Do not trust the type hint in `src/cfbpoll/model/__init__.py` on this one
  point.** The `Rater` protocol there declares `TeamId = int` and
  `Ratings = dict[TeamId, float]`, and the running code disagrees with it: the
  canonical games frame carries string team names, the harness's internal caches
  are `dict[str, float]`, and the shipped example
  [`iterative_margin.py`](configs/challengers/iterative_margin.py) is annotated
  `-> dict[str, float]`. **Follow the shipped example, not the protocol
  annotation.** (`game_id` really is an `Int64`. It is the team columns that are
  strings.)

- **The value is a rating on the points scale, higher is better.** It is not a
  rank, and lower is not better.

- **A team you omit is treated as league average**, which is also what returning
  `{}` means. That is a defined answer, not an error.

- **`games`**: one polars frame, one row per game, already sliced to
  `through_week`. It never contains a banned column, because
  `cfbpoll audit-features` enforces that upstream. Columns:
  `game_id` (`Int64`), `season`, `week`, `season_type`, `game_type`,
  `start_date`, `completed`, `neutral_site`, `conference_game`,
  `home_team` / `away_team` (`String`), `home_points` / `away_points` (`Int32`),
  `home_class` / `away_class`, `source`.

- **`plays`**: a polars frame **or `None`**, and `needs_plays` decides which.
  Declare `needs_plays = True` and the harness loads the play archive and hands it
  over. Declare `False` (or omit it) and **you are handed `None` deliberately**, so
  a rater that reads plays anyway fails loudly rather than quietly consuming a
  frame it disclaimed.

  Columns are a 17-field allow-list out of a 362-column feed: `game_id`,
  `game_row_number`, `pos_team`, `def_pos_team`, `home`, `away`, `period`,
  `clock_minutes`, `clock_seconds`, `down`, `distance`, `yards_to_goal`,
  `yards_gained`, `play_type` and the scoring fields. **There is no `week` or
  `season_type` column, by design**: the games table is the only authority on
  those, and `attach_games` is the only supported way to get them onto a play.

  **`needs_plays = True` against a scores-only archive raises `FileNotFoundError`**
  naming the missing `pbp/play_by_play_<season>.parquet` and telling you to run
  `cfbpoll archive sync --verify`. That is a loud, useful failure rather than a
  silent degradation, so a play-level challenger and `ONLY=schedules,crosswalk`
  simply do not go together.

- **`through_week`**: the data window `K`. **You must never look past it**, and
  that is the entire walk-forward protocol. In practice the harness has already
  truncated the frames for you, so the rule reduces to: do not go find data
  yourself.

- **`state`**: an `l3_power.SeasonState` or `None`. It is a per-season fit cache
  plus an out-of-sample accumulator whose `add` the harness calls only *after* a
  bucket has been predicted and scored, which is what makes the blend weights
  out-of-sample. **Passing `None` is always correct and only slower.** A rater that
  does not use it must still accept and ignore it, and almost every challenger
  should just ignore it.

- **Call cadence:** **once per system per week bucket**, walking each season
  forward, memoised so a system that predicts through another does not refit it.
  It is not called once per game. Assume many calls and keep it deterministic:
  same inputs, same output, every time.

#### Running either one

```bash
make challenge CHALLENGE_ENTRY=configs/challengers/iterative_margin.py
```

Three knobs, all on the target: `CHALLENGE_ENTRY`, `CHALLENGE_SEASONS`, and
**`OUT`, which puts the scorecard in `$(OUT)/challenge`** exactly as it redirects
a rank. Scoring overwrites, so two entries need two of them:

```bash
make challenge CHALLENGE_ENTRY=configs/challengers/theirs.toml OUT=out/theirs
```

Underneath is `cfbpoll challenge run`; its `--systems` option you simply **omit**
to get the published comparison set. CI runs the identical harness against the
identical baselines and posts a scorecard. Two worked examples ship, including one
that LOSES, which is the more useful example. Its exact record is on its
committed scorecard ([`demo/challenge-iterative-margin/scorecard.md`](demo/challenge-iterative-margin/scorecard.md));
quote it from there, not from here.

### Scoring an ordering conviction

**This is the path `make challenge` cannot take, and it comes up constantly**,
because "what should sort the board" is the most common strong opinion in the
sport. Use it whenever the conviction is about the *headline ordering* rather than
about the constants.

The two published orderings are systems in the backtest harness, so you compare
them there:

```bash
make backtest SYSTEMS=schedule_odds,resume
```

**Read `retrodictive_violation_rate` in `out/backtest_metrics.json`.** That is the
metric these rows exist for: how often the ordering put a team above another team
that beat it. Both orderings predict margins through the same Power source, so
their MAE and Brier columns are identical by construction and tell you nothing
about the ordering. Comparing them on MAE is the classic misread here.

`SYSTEMS` is comma-separated with no spaces. Valid names: `schedule_odds`,
`resume`, `l3`, `l2`, `l1`, `home_team`, `winpct`, `colley`, `srs`, `elo`,
`random_walker` (alias `walker`), `closing_line`, `cfp`. The home-team floor is
always included whether or not you name it, because a table without its floor is
not a table.

#### Worked example

> **They say:** "Ranking on odds is backwards. What you *earned* should sort the
> board, not how unlikely your record was."

That is `L4_resume` versus `schedule_odds`, which is exactly the argument
[ADR 0005](docs/adr/0005-headline-ordering.md) decided. Do this:

```bash
# 1. score the two orderings head to head
make backtest SYSTEMS=schedule_odds,resume

# 2. build their board so they can see it, not just read a metric
make rankings RANK_SEASON=2023 RANK_WEEK=15 RANK_RECIPE=just-win OUT=out/theirs
```

`just-win` is the shipped recipe whose `[publication] headline_ordering` is
`L4_resume`, so it is their ordering with a value system attached. If they want
that ordering with the *house* constants, write a one-key recipe (rung 2) setting
only `headline_ordering = "L4_resume"` and rank with it.

Then tell them three things, in this order:

1. **What the violation rate says.** Which ordering more often ranked a team above
   somebody who beat it, on real seasons.
2. **What their board actually looks like**, by name, off the run you just did.
3. **What the decision already cost.** ADR 0005 and
   [the headline-ordering study](docs/analysis/headline-ordering-study.md) record
   the axes the rejected orderings *won*, which is the honest half of the answer
   and the half most people never get told.

The third ordering, `L4_resume_margin` (`full-merit`'s), has no separate backtest
system row. To compare it, rank under `full-merit` and read the boards side by
side rather than claiming a scored result you do not have.

### Recipe to challenger: the transcription that matters

Step 4 of the flow depends on this, so get it right rather than improvising.

**What carries over unchanged:** every constant block. `[margin]`, and any other
`configs/default.toml` key the recipe overrides, are copied across **verbatim**.
That is the whole point: the same numbers, scored.

**What you replace:** the `[recipe]` block becomes a `[challenger]` block, which
needs only two keys. `stance`, `one_liner`, `manifesto` and `tradeoffs` have no
equivalent and are dropped. Put the manifesto's argument in `notes` if you want it
to reach the scorecard's context.

**Which string becomes `name`: use the recipe's `slug`, not its `name`.** Both
would load, since challenger `name` is free-form and tied to nothing. The slug is
the better choice because it is already the identifier the person types and sees
on their runs, so the recipe and its scorecard carry one label instead of two.

```toml
# configs/recipes/theirs.toml        ->   # configs/challengers/theirs.toml
[recipe]                                  [challenger]
slug = "theirs"            ---------->    name = "theirs"     # from slug
name = "Theirs"                           kind = "parameter"  # always, for .toml
stance = 1                                author = "them"     # optional
one_liner = "..."                         notes = """..."""   # optional
manifesto = """..."""
tradeoffs = ["..."]                       # everything below copies UNCHANGED
[margin]                                  [margin]
c = 12.0                                  c = 12.0
beta_w = 9.0                              beta_w = 9.0
```

**What does not survive the trip, and you must say so out loud:
`[publication] headline_ordering`.** A parameter challenger is scored under the
`schedule_odds` system row regardless of what its config says the headline should
be, so transcribing a recipe whose whole idea is "sort by the wins-based résumé"
produces a scorecard that did not test that idea. If their conviction is about the
*ordering* rather than about the constants, the honest report is that the
scorecard measured the constants only, and the ordering question belongs to
[the headline-ordering study](docs/analysis/headline-ordering-study.md) and
[ADR 0005](docs/adr/0005-headline-ordering.md) instead. Comparing orderings
directly is what `cfbpoll backtest --systems ...` does.

### Rung 5: change the model

Editing `src/cfbpoll/model/` is fair game and sometimes it is the only honest way
to express what they believe. Before you do:

- New constants go in `configs/default.toml` with a comment citing why, never
  hard-coded in a module.
- If a future reader will wonder why, write an ADR in `docs/adr/`.
- **Check the leakage audit, do not skip re-ranking to run it separately.**
  `make rankings` runs the audit before it fits, so the run you were going to do
  anyway is the check. Read its verdict rather than trusting the change. Only
  reach for the standalone verb when you want the JSON report or want to audit a
  window without ranking, and then carry the prefix, since it fits models too:

  ```bash
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    uv run cfbpoll audit-features --fail-on-banned --out out/audit.json
  ```

Branches, PRs and what CI will do to them are in
[`CONTRIBUTING.md`](CONTRIBUTING.md). The one rule worth repeating here: **one
idea per PR, and if a change alters a published number, say so and regenerate the
affected fixture in the same PR**, so the change gets reviewed instead of
absorbed.

---

## The commands

**The one prerequisite is [uv](https://docs.astral.sh/uv/).** Not Python, not a
compiler, not Docker, not `sudo`. `uv` fetches the interpreter itself. If it is
missing, install it first, because `make .venv` is the first thing that breaks
without it.

### First run, end to end

This is the whole path from a fresh clone to their own board. Say what each step
costs before you start it.

```bash
# A. toolchain. Seconds to a couple of minutes. Needs `uv` on PATH.
make .venv

# B. the data. A real, large download (size in `make archive` below). Say so
#    first, and narrow it while iterating.
make archive SEASONS=2023

# C. the published poll, so there is a baseline to compare against
make rankings RANK_SEASON=2023 RANK_WEEK=15

# D. their version, into its own directory so both survive
make rankings RANK_SEASON=2023 RANK_WEEK=15 RANK_RECIPE=just-win OUT=out/just-win

# E. show them the two boards
head -30 out/poll.csv out/just-win/poll.csv
```

(Lettered so they do not collide with the five numbered steps of
[the flow](#the-flow-you-are-offering). This whole block is flow step 3.)

C and D each write four files into their `OUT`: `poll.csv`, `poll.json`,
`model_params.json` and `_run.json`. Scoring comes next and is
`make challenge`, which computes its own baselines and needs nothing run before
it.

### The targets

Every `make` target maps to a `cfbpoll` verb. **Everything in this list runs with
no account and no API key** on a fresh clone. The one thing anywhere in the
project that needs a key is resolving the *live current week*, and nothing shipped
does that.

```bash
make .venv        # uv sync --locked. Installs Python 3.12 and every pinned wheel
make archive      # fetch the MIT archive (~0.55 GB) and sha256-check every file
make rankings     # archive -> fit -> the four files in OUT (see --out below)
make backtest     # walk-forward against every baseline
make challenge    # score ONE community entry on that same harness
make grid         # the R(N,K) retroactive triangle for one season
make fixtures     # rank a whole season -> the published JSON tree
make demos        # regenerate the committed demo/ boards from the archive
make cards        # the share cards, SVG and PNG
make variants     # the one-knob playground variants
make test         # pytest
make lint         # ruff

# The Sunday automation (ADR 0002). NOTHING HERE FIRES ON ITS OWN: every
# trigger in ops/arming.toml is committed `false` and the guard refuses them.
make guard          # would the Sunday job run right now, and why not
make preflight      # which verbs the Sunday job needs are still stubs
make weekly-dry-run # the whole job, printed, executing nothing
```

**If somebody asks "does the poll publish itself yet?", the answer is no and
`make guard` proves it.** The clock, the fallback, the dead-man's switch and the
delivery to the website are all built and none is armed: the n8n workflows in
`ops/n8n/` are not imported, the systemd units in `ops/systemd/` are not
installed, and [`ops/arming.toml`](ops/arming.toml) says `false` four times.
`make preflight` names any verb that still has to be real before a publication
can complete at all.

**`[steps] delivery` is the one to be careful with.** The other three switches
decide whether a board gets computed. That one pushes the published tree into the
site repository, which auto-deploys, so arming it is arming a live website with
no staging step in between. It is a separate table from the clocks for that
reason, and unlike them it has no human exemption: a person clicking "Run
workflow" does not deploy the site either.

The whole procedure, including the two credentials a human has to create, is
[`docs/runbooks/sunday-automation.md`](docs/runbooks/sunday-automation.md).

Run the CLI through `uv run cfbpoll ...`. That is what the make targets do and it
works without activating anything.

**Every variable, with its default.** These are silent unless you set them, which
is why they are listed rather than described: a default you did not know about is
the most common way a first command fails.

| target | variable | default |
|---|---|---|
| all | `OUT` | `out` |
| all | `CONFIG` | `configs/default.toml` |
| `archive` | `SEASONS` | *(all)* |
| `archive` | `ONLY` | *(everything, including play-by-play)* |
| `rankings` | `RANK_SEASON` | `2023` |
| `rankings` | `RANK_WEEK` | `15` |
| `rankings` | `RANK_RECIPE` | `house` |
| `backtest` | `SYSTEMS` | `schedule_odds,resume,l3,l2,l1,colley,srs,elo,walker,winpct` |
| `backtest` | `BACKTEST_SEASONS` | `2021-2023` |
| `challenge` | `CHALLENGE_ENTRY` | `configs/challengers/iterative_margin.py` |
| `challenge` | `CHALLENGE_SEASONS` | `2021-2023` |
| `grid` | `GRID_SEASON` | `2023` |
| `fixtures` | `FIXTURES` | `../sandbox/cfb-poll-data` **(outside your fork; always override)** |
| `fixtures` | `FIXTURE_SEASON` | `2023` |
| `variants` | `VARIANT_SEASON` | `2025` |

**Two of these defaults are traps in a fork**, and they are the ones to say out
loud: `FIXTURES` points somewhere that does not exist, and every seasoned default
assumes an archive that holds that season. Name the season explicitly on any
command you run for somebody, and `make help` prints the current list if you
suspect this table has drifted.

**`--out` / `OUT`, because two boards side by side is the normal case.** The
default is `out/`. The directory is created if it does not exist, and the four
filenames are **overwritten in place** with no prompt and no backup, so a second
run into the same directory silently replaces the first. Nothing is cleaned, so a
stale unrelated file left in there survives and can mislead you later. Give every
recipe its own directory (`OUT=out/<slug>`) and they coexist.

Things to know before you run anything:

- **`make archive` is a real 0.55 GB download** from a public GitHub release of
  MIT-licensed data. Tell the person it is happening before it happens, and offer
  the narrow form first. It is resumable, downloads land on `<name>.part` and are
  renamed only once the digest matches, so an interrupted sync costs nothing and
  any file that is there is a file that was checked. A checksum mismatch is a hard
  failure by design, not a warning: re-run rather than working around it.

- **`ONLY=schedules,crosswalk` is cheap but it changes the model, and it does not
  warn you in a way anyone notices.** With no play archive there is nothing for
  **L1 efficiency** to regress on. It does **not** error: `l3_power.fit` sees
  `plays is None`, substitutes an empty L1 fit, and the L3 blend **degrades to the
  L2 results core**. You get a real ranking built on scoring margin alone, with no
  play-level efficiency in it at all.

  The run stamps `power_source` as `L2` rather than `L3` on `model_params.json`,
  `poll.json` and every artifact, which is how you tell after the fact. **Check
  that field before you compare a scores-only run against anything**, because
  comparing an L2-powered board to an L3-powered one and calling the difference a
  result of their recipe is the exact mistake this flag sets up. Use it to iterate
  fast, then re-run with the full archive before anybody draws a conclusion.

- **`make fixtures` writes to `../sandbox/cfb-poll-data` by default**, which is
  the poll owner's layout and does not exist in your fork. Point it somewhere
  real: `make fixtures FIXTURES=out/data`.

- **`make backtest` and `make fixtures` take minutes, not seconds**, because they
  read the play archive and refit every week. `make rankings` for a single week is
  quick. Background the long ones rather than leaving somebody watching a cursor.

The run record, `out/_run.json`, says which archives the run read and every
constant it used. When a number surprises someone, open that file first.

### Two questions people ask that have awkward answers

**"Show me this week's poll."** There is no keyless answer. The archive is
historical, and ranking *now* means resolving which week it is, which needs CFBD's
`/calendar`, which needs an API key. That is why the default is a complete past
season. Say that plainly rather than producing a stale board and calling it live.

**"What about weeks 1 to 4?"** The headline poll deliberately does not start until
week 5, so ranking an early week gives you provisional output plus the
connectivity report, not a poll. That is a feature and the card set has a variant
for exactly this:

```bash
make rankings RANK_SEASON=2023 RANK_WEEK=3
uv run cfbpoll publish cards --from out --variant connectivity
```

The `connectivity` card draws the schedule graph the fit is standing on, with its
diagnostics. It is the honest artifact for September, and it is worth showing
somebody who wants to know why the poll will not commit yet.

---

## Ship it

When their version is producing a board they believe in, give it a surface.

```bash
# 1. produce their board into its own run directory
make rankings RANK_SEASON=2023 RANK_WEEK=15 RANK_RECIPE=<their-slug> OUT=out/theirs

# 2. the share cards: SVG and PNG, carrying THEIR constants in the footer.
#    `publish` fits nothing, so these need no BLAS prefix.
uv run cfbpoll publish cards --from out/theirs --variant top5     # the hero card
uv run cfbpoll publish cards --from out/theirs --variant top25_x
uv run cfbpoll publish cards --from out/theirs --variant top25_instagram

# 3. the JSON tree a site reads. SLOW: it runs a full backtest first and will
#    look stuck for minutes. Tell them before you start it.
make fixtures FIXTURES=out/data
```

**Warn them before you start `make fixtures`, because it looks like it has
hung.** It depends on `backtest`, so it silently runs a full walk-forward over
2021-2023 first, and only then ranks every week of the season one at a time. That
is minutes of no useful output. The dependency is deliberate rather than
belt-and-braces: the gate table and baseline comparison in the published documents
are read out of `backtest_metrics.json`, so publishing against a stale one puts
numbers on a page that no longer describe the model. Say "this takes a few minutes
and will look stuck partway through" first, and background it.

**Do not reach for `make demos` here.** It regenerates the *committed house*
boards under `demo/` from the archive. It does not know about their recipe and it
will not produce their ranking. Their board comes out of their own run directory,
which is what step 1 above is for.

The cards carry the schools' real marks from a pinned local cache, embedded as
`data:` URIs so a card never renders as a blank square when someone reposts it.
The constants footer is on every card and is never dropped for space. That footer
is the signature: no other poll's share image publishes the numbers that produced
it, and if this fork is going to argue with the published poll in public, it
should argue with its own constants visible.

`cards.SITE_DOMAIN` is the address drawn in the footer, and in this fork it still
says `thepoll.ai`. If they are publishing their own board somewhere else, change
it, because a card outlives the post it was attached to and the host on it has to
be the host that answers.

---

## How to talk to them

Read [`README.md`](README.md) and a couple of the ADRs before you write anything
in this repo's voice, then match it. The short version:

**Football first, code second.** They came for the sport. Lead with teams, weeks
and results, and reach for the implementation only when it is the answer to
something they asked. The shape of the sentence you want is:

> *"&lt;team&gt; goes from #&lt;n&gt; to #&lt;m&gt; under &lt;recipe&gt;."*

Fill it from the run you just did, never from memory and never from this file. The
TOML is the footnote.

**Plain and confident.** Contractions. Active voice. Direct address. Cut the
consultant vocabulary. Skip em dashes; a period or a comma does the job. Authority
here comes from having run the thing, so lead with the specific number that proves
you ran it.

**Say what is wrong with your own work.** This is the house style and it is
load-bearing. Every recipe ships a required list of its own costs. The README
publishes that a tuned constant sits on the edge of its own search grid and that
the whole campaign was worth less than the publication gate needs. The committed
challenger example loses. When their idea underperforms, tell them straight, show
them the metric, and treat it as a result rather than a setback. A poll that will
not state its own weaknesses is a marketing page, and this one is not that.

**Never quietly change a published number.** If something moves, say it moved,
say why, and regenerate the artifact in the same breath.

---

## Attribution, which is not optional here

Two upstream efforts make this possible and both get named at the top rather than
in a footnote.

- **[CollegeFootballData.com](https://collegefootballdata.com)**, run by Rad Sports
  Analytics LLC and effectively by one person. Their terms say attribution is not
  required. This project gives it anyway, on every published poll and every post.
  If a fork publishes, it should too. Raw CFBD responses are never republished.
- **[SportsDataverse](https://github.com/sportsdataverse)** (`cfbfastR`,
  `sportsdataverse-data`), MIT licensed, which is the fact that makes the whole
  no-API-key fork promise possible.

Code is MIT. Published ratings are CC BY 4.0. Details in
[`LICENSE-DATA.md`](LICENSE-DATA.md).

*No affiliation with the NCAA, its conferences, or any member institution. All
data is unofficial. Not betting advice.*
