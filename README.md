# cfb-poll

**The poll is at [thepoll.ai](https://thepoll.ai). This repository is the machine
that prints it, and it is yours to take apart.**

An open, bias-free college football ranking. The BCS, if it were invented today,
with every equation, every constant, and every input published. No human polls. No
recruiting rankings. No reputation. No black boxes. Every number on every page
recomputable by a stranger with no API key, no account, and no permission from
anyone.

**Read the poll first. Then come back and argue with it.** Everybody who watches
this sport already has a ranking in their head, and the usual answer to a bad one
is to complain about it. Here the answer is to fork this, change what you think a
poll should reward, and run your version against the same schedule, the same
archive and the same scoreboard the published poll ran against. You do not have to
write Python to do it. Point any AI coding assistant at
[`AGENTS.md`](AGENTS.md) and it will take you from a football opinion to a ranked
board and a scorecard that says whether you beat the original.

> ## ⚠️ Status: all four layers exist. The bootstrap does not.
>
> **What runs today:** the games and play loaders over the MIT archive, **our own
> expected-points model**, the L1 efficiency core (ridge on play value), the L2
> results core (ridge on compressed scoring margin), the L3 blend that stacks
> them out-of-sample, the L4 résumé rating, the **schedule-odds ordering — the
> headline poll**, the full R(N, K) retroactive grid (`cfbpoll grid`),
> `cfbpoll rank`, and the walk-forward backtest against every baseline
> (`cfbpoll backtest`). Real output is committed under [`demo/`](demo/):
>
> - [**The 2023 final poll**](demo/2023-final-poll.md) — schedule odds, résumé and
>   power, live and hindsight, and what a transparent system says about undefeated
>   Florida State
> - [2023 retroactive movers](demo/2023-retro-movers.md) — who the model was wrong
>   about, in its own words, plus the divergence curve
> - [2021: Cincinnati](demo/2021-cincinnati.md) — the first Group of Five playoff team
> - [The poll at week 10, 2023](demo/2023-w10-top25.md) · [walk-forward backtest](demo/backtest-2021-2023.md)
>
> **The expected-points model is ours.** The archive ships an `EPA` column and it
> is a third party's fitted model, which report 01 §5.6 bans as an input, so
> `model/ep.py` fits a next-score model from the scoreboard instead — about a
> hundred lines, every constant in the config. It correlates with the shipped
> column at **r = 0.847** over 221,945 plays, reported as a validation diagnostic
> and never fed in.
>
> **What does not run:** publishing and the site. They are stubs and they raise
> `NotImplementedError` rather than pretending. A season with no play archive falls back to `power_source = "L2"`
> and stamps that on every artifact rather than letting a reader assume otherwise.
>
> See [Status](#status) for what exists versus what is coming.

---

## The five hard constraints

These are the reason the project exists. Full text, with the reasoning and the
banned-input table, in [`docs/constraints.md`](docs/constraints.md).

| # | Constraint | What it rules out |
|---|---|---|
| **1** | **No human polls** | AP, Coaches and CFP rankings are comparison targets, never inputs — and never fitting targets either, which is the subtle version of the violation |
| **2** | **No reputation priors** | No recruiting rankings, no talent composites, no returning production, no coaching tenure, no conference identity, no prior-season ratings. This disqualifies SP+ and FPI as templates *and* as features |
| **3** | **Mandatory opponent adjustment** | Every rating is adjusted for who you played and where — simultaneously, in one linear system, not by iterative averaging |
| **4** | **Retroactive re-ranking** | "Now that we know that opponent was overrated, how good was week 5 really?" must have a principled answer. This is why the estimator is a batch refit and not an Elo |
| **5** | **Full transparency** | Every equation, every constant, every input published; every poll traceable to the exact commit, config and data that produced it |

**Regularization is not a reputation prior.** Ridge shrinks an unknown team toward
*league average* — a statement about our ignorance. A recruiting prior shrinks a
team toward *what we think of its brand* — a statement about reputation. The first
is allowed; the second is the bias we exist to eliminate. Colley's famously
"bias free" BCS matrix used exactly the same device, and without it his matrix is
singular and the method does not work at all.

---

## The promise

> ### The harder it was to do what you did, the higher you go — measured, never assumed.

Teams are ranked by **schedule odds**: `−log10 P(W ≥ W_t)`, the probability that a
team of published reference quality would have gone at least this well against that
exact schedule. Both halves of the sentence are load-bearing.

**"The harder it was"** means schedule difficulty and nothing else. **Your own
margin never enters the rank key — not as a tie-break, not anywhere. Your
opponents' margins price your wins.** Beat a team by one and you get exactly what
you get for beating them by forty; what beating *them* is worth was fitted from
margins, theirs and everyone else's.

That is enforced rather than promised, and in both directions. Hold opponent
quality fixed, scramble every final score in a season while preserving every
winner, and every number this ordering publishes is bit-identical. Refit opponent
quality from those same scrambled scores — which is what the pipeline actually
does — and the ranking moves. Both are tests in
[`tests/unit/test_schedule_odds.py`](tests/unit/test_schedule_odds.py), and the
second one exists because this README used to make the wider claim and an
independent reviewer we commissioned took it apart
([`docs/analysis/fresh-eyes-review.md`](docs/analysis/fresh-eyes-review.md), S5).
The narrow claim is the one that is true, and it is still the property nobody else
in this category offers.

**"Measured, never assumed"** is the part that matters. An unbeaten Group of Five
team probably would not survive a Big Ten schedule — and a poll may only say so if
it *derived* it from results. Assuming it is how you get AP-poll-style conference
bias. Nothing in the computation knows what a conference is. In 2023 the poll puts
a 13-0 Liberty at **#10**, below a 12-1 Georgia at **#7**: the same direction as
the intuition, reached from Liberty's actual opponents rather than from the letters
"C-USA".

**Unbeatens-first was considered and rejected**, and it was this project's own
published ordering until 2026-08-12. Under the wins-based résumé an undefeated team
saturates at a published bracket, which made "win them all and finish ahead of
everyone who didn't" a theorem rather than a tendency — but that bracket is not a
function of the schedule, so the retroactive re-ranking below could not move an
unbeaten team **at all**. From week 11 of 2023 it moved none of them by a single
place. The full evidence, including the axes the rejected orderings *won*, is in
[the headline-ordering study](docs/analysis/headline-ordering-study.md); the
decision and its price are in
[ADR 0005](docs/adr/0005-headline-ordering.md).

## Three numbers, published side by side

Most systems publish one number and leave you to argue about what it means. We
publish three, always, on every row, with the gap between the last two shown.

| | **Schedule odds** | **Résumé rating (L4)** | **Power rating (L3)** |
|---|---|---|---|
| Question it answers | *How hard was that to do?* | *What have you earned?* | *How good are you?* |
| In one sentence | "A top-25-calibre team would have gone this well against this schedule about 9 times in 100" | "Given who they played and where, these results are what a +18.4 team would be expected to produce" | "Expected margin against an average team on a neutral field" |
| Kind | Retrodictive — a selection instrument | Retrodictive — a selection instrument | Predictive |
| Role | **This is the poll.** The headline ranking | Published beside it, both variants, with the saturation flag | **This is the engine.** Never hidden |

**Odds are the poll. Power is the engine.** Retroactively re-scoring week 5 because
we now know an opponent was overrated is inherently a *desert* operation — you are
re-evaluating an accomplishment in light of better information about its difficulty
— so a desert number is the ranking, and the power number stays visible so the
system can be scored honestly against Vegas and against FPI.

The résumé-minus-power gap is still the interesting column: teams whose résumé
exceeds their power rating have out-performed their underlying play; the reverse is
the "best three-loss team in the country" case. And the one free constant in the
headline ordering — the reference team's rating — is published every week **with
the name of the team it came from**, so anyone can check it against the same week's
table.

**Every published row carries a 90% rank interval**, every week, forever — "ranked
7th, 90% interval 4th–13th." No major system does this, and it is the single most
honest thing a computer poll can do.

**The headline poll begins in week 5.** Weeks 1–4 are published as clearly-labelled
provisional output alongside a connectivity report — schedule-graph diagnostics,
the fitted λ, interval widths — because in September the honest answer is that
nobody knows yet, and we would rather show the math for why than pretend.

---

## A ranking is a value system, so we ship three of them

Where margin should count is not a modelling question with an answer. It is a
disagreement about what a poll is *for*: if point differential pays, teams **will**
run up the score on an overmatched opponent, and everyone has seen it — but
ignoring margin entirely throws away the real information in a 70-point win against
a 1-point win. The poll's compromise is a defensible position, and it is *a
position*. So the positions are named ([ADR 0011](docs/adr/0011-recipes.md),
[`configs/recipes/`](configs/recipes/)):

| recipe | what it believes | 2023: where does 13-0 Liberty land? |
|---|---|---:|
| **Full Merit** | margin at face value, no compression, ranked on the margin-aware résumé | **#20** |
| **The House Poll** | margin in the engine, out of the headline. **This is the published poll.** | **#10** |
| **Just Win** | winning is what counts; running the score up buys nothing | **#2** |

```bash
uv run cfbpoll recipes                                        # the roster, with costs
uv run cfbpoll rank --season 2023 --through-week 15 --recipe full-merit
```

Every recipe carries a one-paragraph manifesto **and a list of what it gets wrong**,
which is required and non-empty: a value system that will not state its own cost is
a marketing page. Only the house recipe is published as *the poll*; the others are
labelled alternate lenses everywhere they appear.

**A recipe changes values. It never changes evidence.** Every recipe reads the same
archive, through the same walk-forward window, under the same constraints, and
passes the same leakage audit — enforced at load time by `recipes.EVIDENCE_KEYS`,
and measured directly by digesting the frames each one actually fits on. The three
digests are published on every week document so a reader can check it rather than
believe it.

The whole board, side by side, with the 21 rows that move and why:
[`demo/2023-recipes.md`](demo/2023-recipes.md).

---

## The fork promise

```bash
git clone https://github.com/vyhlidal/cfb-poll && cd cfb-poll
make .venv         # uv sync --locked; installs Python 3.12 and every pinned wheel
make rankings      # archive sync -> rank -> out/poll.csv
```

No API key. No account. No Docker. No `sudo`. Not ours, not anyone's.

That works because of the licence split: the historical archive is MIT-licensed
and republishable, so a fork gets everything without touching a paid API.
`make rankings` fetches the archive from
[our `archive-v1` release](https://github.com/vyhlidal/cfb-poll/releases/tag/archive-v1)
— 28 assets, ~0.55 GB, every one of them checked against the sha256 in
[`data/manifests/sportsdataverse.lock.json`](data/manifests/sportsdataverse.lock.json)
**before any consumer reads it** — then fits and writes the poll to `out/`.
A mismatch is a hard failure, not a warning. Downloads land on `<name>.part` and
are renamed only once the digest matches, so an interrupted sync is resumable and
any file that is there is a file that was checked.

This paragraph used to say *"honestly, this does not work yet."* It works now.
What is still missing is the last hop: `cfbpoll site build` is a stub, so the poll
arrives as `out/poll.csv`, `out/poll.json` and a run record rather than as a page
you can open. Two smaller honesties, both of which the run record will tell you
itself:

- The default is `RANK_SEASON=2023 RANK_WEEK=15`, a complete historical season.
  Ranking *this* week means resolving which week it is, which needs CFBD's
  `/calendar`, which needs a key — so the keyless default is a season the archive
  already holds. 2025 is a complete season too and is the site's example season
  since [ADR 0012](docs/adr/0012-2025-opens.md); it is not the keyless default
  only because the default has never moved.
- **Your 2021 and 2022 postseason will differ from ours, legitimately.** Those 80
  games come from a private CFBD backfill that its terms forbid us to republish,
  so a fork's hindsight surface for those two seasons stops at conference
  championship weekend. `_run.json` records which archives a run actually read,
  which is the difference between a documented difference and a mysterious one.

**Beat the model.** Add a parameter variant to
[`configs/challengers/`](configs/challengers/) or a module implementing
`rate(games, plays, through_week) -> dict[team_id, float]`, open a PR, and CI runs
it through the identical walk-forward harness against the identical baselines and
posts a scorecard. "Did it beat the model" gets a mechanical answer instead of an
argument. Two worked examples ship with it, and so does the scorecard one of them
actually produced:

```bash
make challenge CHALLENGE_ENTRY=configs/challengers/iterative_margin.py
```

That entry beats the incumbent on **1 of 7** metrics and clears **0 of 5** gate
criteria ([the scorecard](demo/challenge-iterative-margin/scorecard.md)). Shipping
a losing example is deliberate: it shows what the harness does when an idea does
not work, which is what happens to most ideas.

---

## Attribution

This project would not exist without two upstream efforts, and both deserve to be
named at the top rather than in a footnote.

### [CollegeFootballData.com](https://collegefootballdata.com)

Run by Rad Sports Analytics LLC, and effectively by one person. It is the
authoritative open college football API and the backbone of an entire field of
public analytics. **Their terms say attribution is not required. We give it
anyway** — here, on every published poll, on the site, and in every social post.
If you use this project, consider [supporting them](https://www.patreon.com/collegefootballdata).

Raw CFBD API responses are never republished here; their terms ask that they not
be, and we respect that. Only our derived ratings are published.

### [SportsDataverse](https://github.com/sportsdataverse) — `cfbfastR` and `sportsdataverse-data`

MIT licensed, which is the fact that makes the fork promise above possible at all.
Their bulk play-by-play archive is what a fork downloads and what every backtest
runs against. Republished copies carry their MIT notice unmodified.

Details and the full licensing position: [`LICENSE-DATA.md`](LICENSE-DATA.md).

*No affiliation with the NCAA, its conferences, or any member institution. All
data is unofficial. Not betting advice.*

---

## How it works

Four layers, all batch refits, all regularized:

| Layer | What it is |
|---|---|
| **L1 — Efficiency** | Ridge on garbage-time-filtered play-level EPA: one offense and one defense coefficient per team, plus home field |
| **L2 — Results** | Ridge on compressed scoring margin, `s = C·tanh(m/C) + β_w·sign(m)` |
| **L3 — Power** | Walk-forward stacked blend of L1 and L2, weights fitted out-of-sample |
| **L4 — Résumé** | Root-solve for the team quality `q` whose expected results against this exact schedule equal the actual results |
| **Schedule odds — the headline** | The exact Poisson-binomial tail `P(W ≥ W_t)` for a reference-quality team against that exact schedule. Ranked on `−log10 P` |

The tail is **exact**, not simulated. ESPN's Strength-of-Record is reportedly a
~20,000-run Monte Carlo; a Poisson-binomial over `n ≤ 15` independent games has an
exact `O(n²)` convolution, so the whole league costs microseconds and reproduces
bit for bit forever. It is property-tested against brute-force enumeration of all
`2ⁿ` outcomes for every `n ≤ 12`, to `1e-14`.

The two most contested numbers are published prominently rather than buried:
**C = 32** (the compression scale — a 40-point win and a 60-point win are worth
nearly the same, which answers the BCS sportsmanship objection without discarding
margin) and **β_w = 7.0** (the win premium — what makes this a football ranking
rather than a scoring-margin ranking). Both live in
[`configs/default.toml`](configs/default.toml) with their citations, and both ship
in `model_params.json` every week.

**Both are fitted, and the search is published with its failures.** They started at
the research report's 24 and 3.0; the 416-cell factorial of 2026-08-12
([ADR 0007](docs/adr/0007-tuned-constants.md),
[the campaign](docs/analysis/tuning-campaign.md)) searched them on 2021-2023 under
a protocol committed before any number was read, froze one choice in writing, and
evaluated it once on 2024. Two results a reader should have up front: **C = 32 sits
on the edge of its own published grid**, so the search did not bracket the optimum;
and **the whole factorial is worth 0.135 points of MAE while the publication gate
needs 0.219**, so tuning these constants is not what closes the gate.

Full math: [`docs/methodology.md`](docs/methodology.md).
Data sources and terms: [`docs/data-sources.md`](docs/data-sources.md).
Decisions and why: [`docs/adr/`](docs/adr/).

---

## Commands

Every `make` target maps to `cfbpoll` CLI verbs.

| Target | What it does |
|---|---|
| `make .venv` | **Works now.** `uv sync --locked` — installs Python 3.12 and every pinned wheel |
| `make archive` | **Works now.** Fetch the MIT archive from our release and sha256-check every file. `SEASONS=2023` or `ONLY=schedules,crosswalk` narrows it |
| `make rankings` | **Works now.** `archive` → fit → `out/poll.csv`, `out/poll.json`, `out/_run.json`. `RANK_SEASON=2023 RANK_WEEK=15 RANK_RECIPE=house` by default; pair `RANK_RECIPE` with `OUT` to keep two boards side by side |
| `make backtest` | **Works now.** Walk-forward 2021–2023 against every baseline; 2025 stays locked. `SYSTEMS=schedule_odds,resume` narrows it to the two orderings, which is how an ordering argument gets settled; `BACKTEST_SEASONS=` moves the window |
| `make challenge` | **Works now.** Score one community entry through that same harness. `CHALLENGE_ENTRY=<path>`, `CHALLENGE_SEASONS=2021-2023` |
| `make demos` | **Works now.** Regenerate everything under `demo/` from the archive |
| `make projection` | **Works now.** Regenerate the 2026 Projection, its backtest and the grading-loop demo. A labelled prediction, never the poll — [ADR 0010](docs/adr/0010-projection-and-poll.md) |
| `make projection-audit` | **Works now.** The separation proof: both products, both deny-lists, one report. Non-zero if a projection input is anywhere near a poll layer |
| `make grid` | **Works now.** The R(N, K) retroactive triangle for one season (`GRID_SEASON=2023`) |
| `make recipe-fixtures` | **Works now.** Weeks 5–15 under each **alternate lens** ([ADR 0011](docs/adr/0011-recipes.md)). Does not touch the published poll's tree |
| `make variants` | **Works now.** Eight one-knob **variants** of the published poll — `margin.beta_w`, `margin.c`, `publication.headline_ordering` — as thin ordering documents carrying the top 40 and a `dial`/`convention` verdict computed against the 0.985 τ line. Does not touch the published poll's tree |
| `make archive-lock` | Regenerate the committed lockfile from a backfill manifest. Only after a backfill or a new release tag |
| `make replay` | Recompute a known historical week offline and assert a byte-match |
| `make site` | Build the static site into `site/_build` |
| `make test` / `make lint` | pytest / ruff |

```
cfbpoll ingest {cfbd,sportsdataverse}   pull a week or a season into the archive
cfbpoll archive {sync,push}             materialise or push the raw archive
cfbpoll validate                        data-quality gate; halt and publish nothing on failure
cfbpoll audit-features                  fail the build if a banned input reached a model matrix
cfbpoll recipes                         the named value systems, with their costs
cfbpoll rank [--recipe <slug>]          fit the model, write the poll and both surfaces
cfbpoll grid                            the full R(N,K) retroactive triangle for a season
cfbpoll bootstrap                       rank + rating intervals (parametric, fixed schedule)
cfbpoll guard                           has this week already been published?
cfbpoll canonicalize                    emit the sorted CSV that golden fixtures hash
cfbpoll publish {release,postgres,fixtures,cards}
                                        publish out/ to its destinations. `fixtures`
                                        takes one run OR a directory of them, so
                                        `make fixtures` republishes a whole season;
                                        `cards` renders the share card (SVG + PNG);
                                        `--variant top5|top10|top25_x|top25_instagram`
                                        picks the board, `top5` being the hero card;
                                        `--variant projection_top5|projection_top10
                                        |projection_top25 --projection
                                        <season>/projection.json` renders the
                                        Projection's cards instead
cfbpoll site build                      build the static site
cfbpoll projection {ingest,build,audit,fixture}
                                        THE PROJECTION - a preseason ranking from
                                        last season's fitted ratings plus the
                                        offseason, published to be graded in
                                        public by the poll it may not touch.
                                        `audit` proves the separation both ways
```

---

## Status

**What exists**

- The canonical games loader over the local MIT archive (2021–2025), with the
  binding week-bucket rules of `docs/data-findings.md`, plus the **CFBD postseason
  backfill** that closes the 2021–2022 hole: those two seasons carry no postseason
  rows in the parquet at all, so they were missing 80 games including both
  playoffs (`docs/data-findings.md` §13)
- The **real CFBD client** (`ingest/cfbd.py`) — bearer auth, a `GET /info` quota
  guard, the 22-call weekly sequence of report 01 §3.7, and an append-only raw
  archive that never overwrites a body and refuses to record a URL carrying a key
- **Team colours and the generated mark** (`data/team-colors.csv`,
  `ingest/teams.py`) — 138 schools, a WCAG contrast repair on the 23 whose own
  two colours are illegible together, published on every poll row
- The **weekly share card** (`publish/cards.py`, `cfbpoll publish cards`) — SVG
  and PNG, seven variants, carrying the schools' real marks from a pinned,
  gitignored cache (`publish/logos.py`, `data/logo-cache-manifest.json`) with a
  luminance guard that plates the marks too dark to sit on the card's ground, and
  a CI guard that fails the build if a card ever hotlinks instead of embedding
- The canonical **play loader** (`ingest/plays.py`), a 17-column allow-list out of
  a 362-column feed, with four new binding data findings recorded in
  `docs/data-findings.md` §8–§12
- **Our own expected-points model** (`model/ep.py`) — the Carter/Romer/Burke
  next-score construction, fitted from the scoreboard, because the archive's
  `EPA` column is someone else's model and is banned as an input
- **L1 efficiency core** — ridge on garbage-time-filtered play value, one offence
  and one defence coefficient per team plus home field, λ by grouped CV on
  `game_id`; rush/pass unit splits for explanation only
- **L2 results core** — ridge on compressed scoring margin, every FBS *and* FCS
  team with its own coefficient under the same penalty
- **L3 power rating** — the blend of L1 and L2, with `w1` and `w2` fitted on
  out-of-sample games only and published every week
- **L4 résumé rating.** Root-solve for the quality `q` whose expected results
  against that exact schedule equal the actual ones, in both the wins-based and
  margin-aware variants, with Power and the résumé-minus-power gap beside every
  team. It was the headline poll from commit `50f4058` until 2026-08-12 and is now
  published beside the headline on every row
- **Schedule odds — the headline poll** (`model/schedule_odds.py`). The exact
  Poisson-binomial tail `P(W ≥ W_t)` for a reference-quality team against that
  exact schedule, ranked on `−log10 P`, with the reference team named every week.
  Adopted on the evidence of
  [the headline-ordering study](docs/analysis/headline-ordering-study.md);
  see [ADR 0005](docs/adr/0005-headline-ordering.md)
- **R(N, K) and retroactive re-ranking** — `cfbpoll grid` writes the full
  upper-triangular surface, the live and hindsight surfaces, and the biggest
  retroactive movers
- **Published uncertainty.** A **90% rank interval beside every rank**, from a
  parametric bootstrap on the *fixed* schedule, and a **standard error beside
  every Power rating**, from the ridge sandwich. The scheme report 02 §3.3
  specified — resample games with replacement — is invalid on a schedule graph
  and is disqualified by its own output (it breaks the graph in 100% of draws);
  `cfbpoll bootstrap --naive-diagnostic` recomputes that. Method and the
  replication of the independent review's own bootstrap:
  [docs/analysis/uncertainty.md](docs/analysis/uncertainty.md)
- **The feature audit** (`validate/leakage.py`, `cfbpoll audit-features
  --fail-on-banned`). Not a docstring: every design matrix is rebuilt from the
  frame *restricted to that layer's allow-list* and required to be bit-identical,
  so "no banned input reached a fit" is a measurement recomputed before every
  poll rather than a promise. `conference_game` is in the schedule frame on every
  run and is proved unconsumed on every run. `cfbpoll rank` runs it pre-fit
- The strict walk-forward backtest and all five computed baselines
- `configs/default.toml` — every model constant with its starting value, its
  backtest grid, and a citation to the research section that fixed it
- Licenses: MIT for code, CC BY 4.0 for published ratings, upstream notices
- The five constraints, the headline promise and the banned-input table
  (`docs/constraints.md`)
- **The analysis set** (`docs/analysis/`), all of it generated by a script and
  reproducible from the archive:
  [`uncertainty.md`](docs/analysis/uncertainty.md) (the sandwich, the bootstrap,
  and the replication of the independent review's own intervals),
  [`fit-universe-sensitivity.md`](docs/analysis/fit-universe-sensitivity.md),
  [`robustness-notes.md`](docs/analysis/robustness-notes.md) (the bridge-game
  venue confound and the `recency_gamma` sweep),
  [`headline-ordering-study.md`](docs/analysis/headline-ordering-study.md),
  [`tuning-campaign.md`](docs/analysis/tuning-campaign.md) and
  [`campaign-2.md`](docs/analysis/campaign-2.md) (two pre-registered hyperparameter
  campaigns, protocol committed before any number was read), and the
  [independent review](docs/analysis/fresh-eyes-review.md) that asked for most of it
- Eight architecture decision records (`docs/adr/`), including
  [ADR 0006](docs/adr/0006-fit-universe.md): the fit universe stays `model`, on a
  rule fixed before the numbers were read, and stops being called a convention —
  and [ADR 0008](docs/adr/0008-league-structural-home-field.md), which is **open**:
  it puts a constraint question to the owner rather than answering it
- `weekly.yml` and `reproducibility.yml`, committed as the specification. Both are
  `workflow_dispatch` only — no schedule, so nothing fires accidentally

**What is coming, in build order** (research report 03 §10, report 02 Appendix B)

1. ~~**The MIT backfill onto disk, checksummed into `data/manifests/`**~~ — done
2. ~~**`cfbpoll archive sync --verify` and the archive published as `archive-v1`**~~
   — done, 2026-08-13. 28 assets, 549,177,654 bytes, every one sha256-checked
   against a committed lockfile before any consumer reads it. This was the whole
   fork promise and it was a stub for the first day of this repository's life
3. ~~**L2 alone**~~ — done
4. ~~**The backtest harness and the computed baselines**~~ — done, built second
   rather than last because every subsequent decision depends on it
5. ~~**L4 résumé and the R(N, K) grid**~~ — done; this is the headline poll and
   the retroactive product
6. `reproducibility.yml` with the first golden fixture
7. `weekly.yml` end to end, run manually before any clock is attached
8. ~~**L1 efficiency → L3 blend**~~ — done; `power_source` is now `"L3"`
8b. ~~**Rank intervals and rating standard errors**~~ — done; published on every
   row, every week
9. The static site and the sandbox web app. ~~**The challenge harness**~~ — done,
   with two worked examples and a committed scorecard
   (`configs/challengers/`, `.github/workflows/challenge.yml`)

**Known gaps, recorded rather than glossed**

- Cloudflare R2 is not provisioned; the private-archive push target is a stub
- `cfbpoll site build` is a stub, so `make rankings` produces the poll as files
  rather than as a page
- The terms snapshot in `docs/terms-snapshots/` has not been taken (it requires a
  browser render)
- **A fork's 2021 and 2022 postseason differs from ours, legitimately.** Those 80
  games come from a private CFBD backfill its terms forbid us to republish, so a
  fork's hindsight surface for those two seasons stops at conference championship
  weekend. `_run.json` records which archives every run actually read
- FCS-vs-FCS play-by-play coverage is real but incomplete (1,492 of 1,603
  model-universe games in 2023 have a play feed; FBS-vs-FBS is complete). A team
  with no plays gets an L1 coefficient of zero — league average — which is what
  ridge would shrink it to anyway, and its L2 coefficient is unaffected
- The clock (n8n on the VPS) does not exist yet, deliberately

---

## License

Code: [MIT](LICENSE). Published ratings and rankings:
[CC BY 4.0](LICENSE-DATA.md). Upstream data: MIT (SportsDataverse), with CFBD raw
data deliberately not republished.
