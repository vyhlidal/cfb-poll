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

**3. We run your version.** Against the same archive, the same schedule, the same
walk-forward window and the same scoreboard the published poll ran against. No
API key and no account, ever. It is not one command though, and do not tell them
it is: it is `make .venv`, then a one-time archive download, then a rank. See
[The commands](#the-commands) for what that actually costs.

**4. We score it against the original.** Same harness, same baselines, same
metrics, and the answer is mechanical:

```bash
uv run cfbpoll challenge run --entry configs/challengers/<name>.toml   # constants
uv run cfbpoll challenge run --entry configs/challengers/<name>.py     # a method
```

`--entry` takes either form. The scorecard gives straight-up win percentage, MAE,
RMSE, Brier, log loss, calibration and ordering violations, side by side with the
published poll and with five computed baselines, plus the publication gate applied
to all of it.

**Know this seam before you promise a score.** The harness scores *orderings and
rating methods*, not recipes. A recipe is a `[recipe]` block; a challenger is a
`[challenger]` block. They take the same constants, so scoring a recipe means
writing its constants out a second time as a challenger TOML, and you should do
that rather than skip step 4. The project says so about itself: no recipe has been
backtested end to end as a system, and `configs/recipes/README.md` lists that under
"where this is weak". If someone's idea is a pure value judgement, be straight that
the scorecard measures prediction, which is not the same question as whether their
poll is *right*.

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

**Two habits about numbers.** This document quotes specific figures, and the ones
in the recipe table came off a published board at a moment in time. Before you
repeat any number to the person as a current fact, regenerate it or read it out of
`out/_run.json`, because a briefing file cannot know what has moved since it was
written. And when you are unsure whether something is still true, check `git log`
and the ADRs rather than trusting this page.

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

  It matters for anything that fits a model: `rank`, `backtest`, `grid`,
  `challenge run`. It does not matter for `recipes`, `publish` or `audit-features`,
  which fit nothing.

Regularization is **not** a reputation prior, and this distinction matters when
someone objects. Ridge shrinks an unknown team toward *league average*, which is a
statement about our ignorance. A recruiting prior shrinks a team toward *what we
think of its brand*, which is the bias this project exists to delete.

Full text and the banned-input table: [`docs/constraints.md`](docs/constraints.md).
`cfbpoll audit-features --fail-on-banned` enforces it mechanically on every run, so
a violation fails the build rather than shipping quietly.

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
  projection/         THE PROJECTION: a labelled preseason prediction, never the
                      poll. Kept separate on purpose (ADR 0010)

configs/
  default.toml        EVERY model constant, with citations. The methodology
  recipes/            the three published value systems
  challengers/        outside entries. This is where a new idea goes
docs/
  constraints.md      the five rules, with the banned-input table
  methodology.md      the math
  adr/                thirteen decision records. Read these before arguing with one
  analysis/           the studies, including the independent review that took an
                      earlier version of the README apart
demo/                 committed real output. Boards, backtests, scorecards
tests/                unit, property and golden
```

---

## The levers, cheapest first

Climb this ladder in order. Tell the person which rung you are on.

### Rung 1: a recipe

A ranking is a value system, and three are already published and named. This costs
one flag.

```bash
uv run cfbpoll recipes                      # the roster, with each one's costs
uv run cfbpoll rank --season 2023 --through-week 15 --recipe full-merit
```

| recipe | what it believes | 2023: where does 13-0 Liberty land? |
|---|---|---:|
| **full-merit** | margin at face value, uncompressed | **#20** |
| **house** | margin in the engine, out of the headline. **The published poll** | **#10** |
| **just-win** | winning is what counts, running it up buys nothing | **#2** |

If what they told you in step 1 is "running up the score should count for
nothing", you are done in one command. Show them `just-win` and the 21 rows that
move ([`demo/2023-recipes.md`](demo/2023-recipes.md)).

### Rung 2: their own recipe

A recipe file is a `[recipe]` block plus **only** the constants it changes. Copy
[`configs/recipes/just-win.toml`](configs/recipes/just-win.toml) and edit.

**How it gets picked up:** drop it in `configs/recipes/`, set `slug` to match the
filename (`recipes.load` enforces that), and it is immediately available as
`--recipe <slug>`. There is no registry to edit. `config.merge_overlay` refuses a
key that `configs/default.toml` does not define, so a typo like `beta-w` fails
loudly instead of quietly publishing a poll under constants nobody set.

The two constants people actually want are in `[margin]`:

- **`c`** (default `32.0`), the compression scale. Lower means a blowout counts
  for less. `just-win` uses `1.0`. Uncapped means margin at face value.
- **`beta_w`** (default `7.0`), the win premium. This is the constant that makes
  it a football ranking instead of a scoring-margin ranking. Set it to `0` and
  winning stops mattering on its own.

And `[publication] headline_ordering` picks what the board is sorted on:
schedule odds, the wins-based résumé, or the margin-aware résumé.

**`tradeoffs` is required and must be non-empty.** `recipes.load` refuses a recipe
that will not state its own cost. Do not write a throwaway line to get past the
check. Ask the person what their poll gets wrong and write down what they say,
because that answer is usually the most interesting thing in the file.

**A recipe changes values. It never changes evidence.** `recipes.EVIDENCE_KEYS`
lists the keys a recipe may never touch (the fit universe, the walk-forward flags,
the holdout, the FCS policy, `[constraints]`, `[weights]`), and
`assert_values_only` refuses the file at load time if it names one. If their idea
needs to change what data the model sees, it is not a recipe. Go to rung 4.

### Rung 3: a one-knob variant

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
Either a parameter override TOML or a module implementing one function:

```python
def rate(games, plays, through_week) -> dict[int, float]: ...
```

Drop it in [`configs/challengers/`](configs/challengers/) and run it:

```bash
uv run cfbpoll challenge run --entry configs/challengers/iterative_margin.py
```

CI runs the identical harness against the identical baselines and posts a
scorecard. Two worked examples ship, including one that loses on 6 of 7 metrics,
which is the more useful example.

### Rung 5: change the model

Editing `src/cfbpoll/model/` is fair game and sometimes it is the only honest way
to express what they believe. Before you do:

- New constants go in `configs/default.toml` with a comment citing why, never
  hard-coded in a module.
- If the change alters a published number, regenerate the affected golden fixture
  in the same change, so it gets reviewed instead of absorbed.
- If a future reader will wonder why, write an ADR in `docs/adr/`.
- Run `uv run cfbpoll audit-features --fail-on-banned` before you believe anything.

Working on a branch, opening a PR, and what CI will do to it are all in
[`CONTRIBUTING.md`](CONTRIBUTING.md). The short version: one idea per PR, and if a
change alters a published number, say so and regenerate the affected fixture in
the same PR so the change gets reviewed instead of absorbed.

---

## The commands

**The one prerequisite is [uv](https://docs.astral.sh/uv/).** Not Python, not a
compiler, not Docker, not `sudo`. `uv` fetches the interpreter itself. If it is
missing, install it first, because `make .venv` is the first thing that breaks
without it.

Every `make` target maps to a `cfbpoll` verb. These all work on a fresh clone with
no account and no API key.

```bash
make .venv        # uv sync --locked. Installs Python 3.12 and every pinned wheel
make archive      # fetch the MIT archive (~0.55 GB) and sha256-check every file
make rankings     # archive -> fit -> out/poll.csv, out/poll.json, out/_run.json
make backtest     # walk-forward 2021-2023 against every baseline
make grid         # the R(N,K) retroactive triangle for one season
make fixtures     # rank a whole season -> the published JSON tree (see below)
make demos        # regenerate the committed demo/ boards from the archive
make cards        # the share cards, SVG and PNG
make variants     # the eight one-knob variants
make test         # pytest
make lint         # ruff
```

Run the CLI through `uv run cfbpoll ...`. That is what the make targets do and it
works without activating anything.

Narrow the archive while iterating: `make archive SEASONS=2023` or
`ONLY=schedules,crosswalk` for a scores-only run that skips the 0.52 GB of
play-by-play. Override the season with
`make rankings RANK_SEASON=2022 RANK_WEEK=12`.

Things to know before you run anything:

- **`make archive` is a real 0.55 GB download** from a public GitHub release of
  MIT-licensed data. Tell the person it is happening before it happens, and offer
  the narrow form first. It is resumable, downloads land on `<name>.part` and are
  renamed only once the digest matches, so an interrupted sync costs nothing and
  any file that is there is a file that was checked. A checksum mismatch is a hard
  failure by design, not a warning: re-run rather than working around it.
- **`make fixtures` writes to `../sandbox/cfb-poll-data` by default**, which is
  the poll owner's layout and does not exist in your fork. Point it somewhere
  real: `make fixtures FIXTURES=out/data`. It also depends on `backtest`, so it is
  the slow one.
- **`make backtest` and `make fixtures` take minutes, not seconds**, because they
  read the play archive and refit every week. `make rankings` for a single week is
  quick. Background the long ones rather than leaving somebody watching a cursor.

The run record, `out/_run.json`, says which archives the run read and every
constant it used. When a number surprises someone, open that file first.

**The archive is historical, so "what does this week's poll look like" has no
keyless answer.** Ranking *now* means resolving which week it is, which needs
CFBD's `/calendar`, which needs an API key. That is why the default is a complete
past season. If they ask for the current week, say that plainly rather than
producing a stale board and calling it live.

---

## Ship it

A ranking nobody can see is not a poll. When their version is producing a board
they believe in, give it a surface.

```bash
# 1. produce their board into a run directory
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run cfbpoll rank --season 2023 --through-week 15 --recipe <their-slug> --out out

# 2. the share cards: SVG and PNG, carrying THEIR constants in the footer
uv run cfbpoll publish cards --from out --variant top5     # the hero card
uv run cfbpoll publish cards --from out --variant top25_x
uv run cfbpoll publish cards --from out --variant top25_instagram

# 3. the JSON tree a site reads
make fixtures FIXTURES=out/data
```

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
something they asked. "Liberty goes from #10 to #2 under just-win" is the
sentence. The TOML is the footnote.

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
