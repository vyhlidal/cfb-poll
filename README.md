# cfb-poll

**An open, bias-free college football ranking. The BCS, if it were invented
today — with every equation, every constant, and every input published.**

No human polls. No recruiting rankings. No reputation. No black boxes. Every
number on every page recomputable by a stranger with no API key, no account, and
no permission from anyone.

> ## ⚠️ Status: the poll exists. Two of its four layers do not.
>
> **What runs today:** the games loader over the MIT archive, the L2 results core
> (ridge on compressed scoring margin), the **L4 résumé rating — the headline
> poll**, the full R(N, K) retroactive grid (`cfbpoll grid`), `cfbpoll rank`, and
> the walk-forward backtest against every baseline (`cfbpoll backtest`). Real
> output is committed under [`demo/`](demo/):
>
> - [**The 2023 final poll**](demo/2023-final-poll.md) — résumé and power, live and
>   hindsight, and what a transparent system says about undefeated Florida State
> - [2023 retroactive movers](demo/2023-retro-movers.md) — who the model was wrong
>   about, in its own words, plus the divergence curve
> - [2021: Cincinnati](demo/2021-cincinnati.md) — the first Group of Five playoff team
> - [The poll at week 10, 2023](demo/2023-w10-top25.md) · [walk-forward backtest](demo/backtest-2021-2023.md)
>
> **What does not:** L1 efficiency and the L3 blend. Report 02 §3.4 reads
> opponent quality off L3; L3 does not exist, so **Power is L2 rescaled to
> points**, and every artifact stamps `power_source = "L2"`, `power_version =
> "v0"` rather than letting a reader assume otherwise. The bootstrap rank
> intervals, publishing and the site are also still stubs, and they raise
> `NotImplementedError` rather than pretending.
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

## Two ratings, published side by side

Most systems publish one number and leave you to argue about what it means. We
publish two, always, with the gap between them shown.

| | **Résumé rating (L4)** | **Power rating (L3)** |
|---|---|---|
| Question it answers | *What have you earned?* | *How good are you?* |
| In one sentence | "Given who they played and where, these results are what a +18.4 team would be expected to produce" | "Expected margin against an average team on a neutral field" |
| Kind | Retrodictive — a selection instrument | Predictive |
| Role | **This is the poll.** The headline ranking | **This is the engine.** Never hidden, published beside the poll every week |

**Résumé is the poll. Power is the engine.** Retroactively re-scoring week 5
because we now know an opponent was overrated is inherently a *résumé* operation —
you are re-evaluating an accomplishment in light of better information about its
difficulty. So the résumé number is the ranking, and the power number stays
visible so the system can be scored honestly against Vegas and against FPI.

The gap between them is itself the interesting column: teams whose résumé exceeds
their power rating have out-performed their underlying play; the reverse is the
"best three-loss team in the country" case.

**Every published row carries a 90% rank interval**, every week, forever — "ranked
7th, 90% interval 4th–13th." No major system does this, and it is the single most
honest thing a computer poll can do.

**The headline poll begins in week 5.** Weeks 1–4 are published as clearly-labelled
provisional output alongside a connectivity report — schedule-graph diagnostics,
the fitted λ, interval widths — because in September the honest answer is that
nobody knows yet, and we would rather show the math for why than pretend.

---

## The fork promise

```bash
git clone https://github.com/vyhlidal/cfb-poll && cd cfb-poll
make rankings
```

No API key. No account. No Docker. No `sudo`. Not ours, not anyone's.

That works because of the license split: the historical archive is MIT-licensed
and republishable, so a fork gets everything through last Sunday without touching
a paid API. `make rankings` fetches the archive (~0.55 GB, sha256-verified against
a committed manifest), fits, and writes a static site you can open with
`python -m http.server`.

> **Honestly: this does not work yet.** `make rankings` currently prints what it
> will do and exits. The command above is the contract this repository is being
> built to satisfy — it is in the README because it is the design target, and the
> day it stops being aspirational this paragraph goes away.

**Beat the model.** When the challenge harness lands, add a parameter variant to
[`configs/challengers/`](configs/challengers/) or a module implementing
`rate(games, plays, through_week) -> dict[team_id, float]`, open a PR, and CI runs
it through the identical walk-forward harness against the identical baselines and
posts a scorecard. "Did it beat the model" gets a mechanical answer instead of an
argument.

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

The two most contested numbers are published prominently rather than buried:
**C = 24** (the compression scale — a 40-point win and a 60-point win are worth
nearly the same, which answers the BCS sportsmanship objection without discarding
margin) and **β_w = 3.0** (the win premium — what makes this a football ranking
rather than a scoring-margin ranking). Both live in
[`configs/default.toml`](configs/default.toml) with their citations, both are
grid-searched in the backtest, and both ship in `model_params.json` every week.

Full math: [`docs/methodology.md`](docs/methodology.md).
Data sources and terms: [`docs/data-sources.md`](docs/data-sources.md).
Decisions and why: [`docs/adr/`](docs/adr/).

---

## Commands

Every `make` target maps to `cfbpoll` CLI verbs.

| Target | What it does |
|---|---|
| `make .venv` | **Works now.** `uv sync --locked` — installs Python 3.12 and every pinned wheel |
| `make backtest` | **Works now.** Walk-forward 2021–2023 against every baseline; 2025 stays locked |
| `make demos` | **Works now.** Regenerate everything under `demo/` from the archive |
| `make grid` | **Works now.** The R(N, K) retroactive triangle for one season (`GRID_SEASON=2023`) |
| `make rankings` | Sync the archive, fit L1–L4, bootstrap intervals, build the static site |
| `make replay` | Recompute a known historical week offline and assert a byte-match |
| `make site` | Build the static site into `site/_build` |
| `make test` / `make lint` | pytest / ruff |

```
cfbpoll ingest {cfbd,sportsdataverse}   pull a week or a season into the archive
cfbpoll archive {sync,push}             materialise or push the raw archive
cfbpoll validate                        data-quality gate; halt and publish nothing on failure
cfbpoll audit-features                  fail the build if a banned input reached a model matrix
cfbpoll rank                            fit the model, write the poll and both surfaces
cfbpoll grid                            the full R(N,K) retroactive triangle for a season
cfbpoll bootstrap                       rank + rating intervals
cfbpoll guard                           has this week already been published?
cfbpoll canonicalize                    emit the sorted CSV that golden fixtures hash
cfbpoll publish {release,postgres}      publish out/ to its destinations
cfbpoll site build                      build the static site
```

---

## Status

**What exists**

- The canonical games loader over the local MIT archive (2021–2025), with the
  binding week-bucket rules of `docs/data-findings.md`
- **L2 results core** — ridge on compressed scoring margin, every FBS *and* FCS
  team with its own coefficient under the same penalty
- **L4 résumé rating — the headline poll.** Root-solve for the quality `q` whose
  expected results against that exact schedule equal the actual ones, in both the
  wins-based and margin-aware variants, with Power and the résumé-minus-power gap
  beside every team
- **R(N, K) and retroactive re-ranking** — `cfbpoll grid` writes the full
  upper-triangular surface, the live and hindsight surfaces, and the biggest
  retroactive movers
- The strict walk-forward backtest and all five computed baselines
- `configs/default.toml` — every model constant with its starting value, its
  backtest grid, and a citation to the research section that fixed it
- Licenses: MIT for code, CC BY 4.0 for published ratings, upstream notices
- The five constraints and the banned-input table (`docs/constraints.md`)
- Four architecture decision records (`docs/adr/`)
- `weekly.yml` and `reproducibility.yml`, committed as the specification. Both are
  `workflow_dispatch` only — no schedule, so nothing fires accidentally

**What is coming, in build order** (research report 03 §10, report 02 Appendix B)

1. The MIT backfill onto disk, checksummed into `data/manifests/` — the step most
   likely to be lost forever if delayed
2. `cfbpoll archive sync --verify` and the archive published as `archive-v1`
3. ~~**L2 alone**~~ — done
4. ~~**The backtest harness and the computed baselines**~~ — done, built second
   rather than last because every subsequent decision depends on it
5. ~~**L4 résumé and the R(N, K) grid**~~ — done; this is the headline poll and
   the retroactive product
6. `reproducibility.yml` with the first golden fixture
7. `weekly.yml` end to end, run manually before any clock is attached
8. **L1 efficiency → L3 blend** — which is what replaces `power_source = "L2"`
   with the real thing — then bootstrap rank intervals
9. The static site, the sandbox web app, and the challenge harness

**Known gaps, recorded rather than glossed**

- Cloudflare R2 is not provisioned; the private-archive push target is a stub
- No CFBD key is configured, and the terms snapshot in
  `docs/terms-snapshots/` has not been taken (it requires a browser render)
- FCS-vs-FCS play-by-play coverage is unconfirmed, and it changes the FCS design
  (`configs/default.toml` records this as an open dependency)
- The clock (n8n on the VPS) does not exist yet, deliberately

---

## License

Code: [MIT](LICENSE). Published ratings and rankings:
[CC BY 4.0](LICENSE-DATA.md). Upstream data: MIT (SportsDataverse), with CFBD raw
data deliberately not republished.
