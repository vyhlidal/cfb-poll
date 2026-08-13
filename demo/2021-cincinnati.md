# 2021: Cincinnati, the first Group of Five playoff team

> **Where the postseason in this document comes from.** The MIT `cfb_schedules_*` parquet carries **no postseason rows at all** for 2021 and 2022 — `season_type` has one value, `regular` — so until 2026-08-12 this page stopped at conference championship weekend and said so. The 80 missing games (38 in 2021, 42 in 2022) were backfilled from the CFBD API, whose game ids turn out to be the same ESPN ids the parquet uses, and they are merged into the frame as `source = "cfbd"` rows. **A fork without the private CFBD archive sees the old, shorter window** and will reproduce every *live* number below but not the hindsight column. All 80 games are independently checkable against the MIT play-by-play, which has had them all along.

Cincinnati went 13-0, won the American, and became the first team from outside the
Power Five to make the College Football Playoff — at **#4**, behind three one-loss
Power Five teams. The argument at the time was entirely about schedule: had
Cincinnati actually *done* more than Alabama, Michigan and Georgia, or had it only
avoided losing to anybody good? That is precisely the question the headline ordering
is constructed to answer, so it is the natural first test of it.

**This page is also the sharpest illustration of what changed on 2026-08-12.** Under
the ordering this project published until then, Cincinnati was **#1** — ahead of
Alabama, Georgia and Michigan — and it was *forced* there rather than judged there:
an unbeaten team's wins-based résumé saturates at the published bracket, so no team
with a loss can outrank it, whatever either played. That was a position no
independent judge reached, and it was one of the two findings that decided
[ADR 0005](../docs/adr/0005-headline-ordering.md).

> **The rank key is schedule odds.** Teams are ordered by
> `−log10 P(W ≥ W_t)`: the probability that a team of reference quality `q_ref`
> would have gone **at least this well** against that exact schedule. The promise
> is *the harder it was to do what you did, the higher you go — measured, never
> assumed*. Adopted 2026-08-12 on the evidence of
> [`docs/analysis/headline-ordering-study.md`](../docs/analysis/headline-ordering-study.md);
> the decision and what was rejected are in
> [`docs/adr/0005-headline-ordering.md`](../docs/adr/0005-headline-ordering.md).
>
> ```
> p_g = Phi( (q_ref − Power_opponent + h · site) / sigma )      per game
> P   = P(W >= W_t),  W ~ PoissonBinomial(p_1 .. p_n)          exact, not simulated
> ```
>
> `q_ref` is the Power rating of the **25th-ranked Power team** — **Houston** this week, at
> **17.76 points**. It is the one free constant in the ordering, so it is
> published with the team it came from and you can check it against the `Power`
> column below. Study §9 measured how much it matters: across a 16-point swing in
> reference quality, Kendall's tau against this choice never fell below 0.985 and
> at most one team entered or left the top 25.
>
> **Margin never enters the key.** Not as a tie-break, not anywhere — the module
> carries no margin column to leak from. The margin-aware résumé is in the table
> beside it, because report 02 §3.4 says to publish both.

> **Power is L3, version v1 — the blend.** Report 02 §3.4 reads opponent quality
> off L3, and L3 now exists:
>
> ```
> Power_t = w1 · k · (alpha_t − beta_t)  +  w2 · rho_t
> ```
>
> `alpha` and `beta` are the L1 opponent-adjusted offence and defence ratings, in
> our own expected-points units per play; `k` converts them to points; `rho` is the
> L2 results core. `w1` and `w2` are fitted on **out-of-sample games only** — games
> already predicted by a fit that had not seen them — per report 02 §3.3, and they
> are published every week. There is no rescaling constant: the blend regression's
> response is actual game margin, so Power is already in points.
>
> The expected-points model is **ours**. The archive ships an `EPA` column and it is
> a third party's fitted model, which report 01 §5.6 bans as an input, so
> `model/ep.py` fits a next-score model from the scoreboard instead. It correlates
> with the shipped column at **r = 0.847** over 221,945 plays — reported as a
> validation diagnostic, never fed in.

## The window, precisely

| | |
|---|---|
| Evaluation week **N** | `2021-regu-w15` — through conference championships |
| Live data window **K = N** | R(N, N), `2021-regu-w15` |
| Hindsight data window **K = final** | R(N, final), `2021-post-w01` — includes the 38 backfilled postseason games |
| Games in the season frame | 1,564 |
| ... from the MIT parquet | 1,526 |
| ... backfilled from CFBD | 38 |
| Ranked (FBS) teams | 130 |

## The final poll (through conference championships)

| # | 90% interval | Team | Rec | −log10 P | P(W ≥ W_t) | Résumé | Margin résumé | Power | ± | Gap | Résumé # | Power # | Hindsight # |
|---:|:---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1–24 | Alabama | 12-1 | 2.289 | 0.0051 | 41.65 | 36.54 | 31.69 | 3.17 | +9.96 | 2 | 2 | 1 (—) |
| 2 | 1–37 | Cincinnati | 13-0 | 1.945 | 0.0113 | 60.00\* | 33.57 | 27.34 | 3.18 | +32.66 | 1 | 5 | 2 (—) |
| 3 | 1–31 | Michigan | 12-1 | 1.941 | 0.0115 | 39.70 | 35.15 | 29.65 | 3.21 | +10.05 | 3 | 4 | 4 (▼1) |
| 4 | 1–16 | Georgia | 12-1 | 1.895 | 0.0127 | 39.31 | 40.95 | 34.69 | 3.17 | +4.63 | 4 | 1 | 3 (▲1) |
| 5 | 2–48 | Notre Dame | 11-1 | 1.409 | 0.0390 | 35.89 | 28.95 | 25.32 | 3.25 | +10.57 | 5 | 6 | 5 (—) |
| 6 | 2–43 | Oklahoma State | 11-2 | 1.193 | 0.0642 | 30.96 | 26.66 | 25.26 | 3.27 | +5.70 | 9 | 7 | 6 (—) |
| 7 | 5–69 | Michigan State | 10-2 | 1.178 | 0.0664 | 31.81 | 23.67 | 20.62 | 3.31 | +11.19 | 6 | 14 | 8 (▼1) |
| 8 | 3–59 | Ole Miss | 10-2 | 1.139 | 0.0726 | 31.45 | 25.47 | 22.19 | 3.28 | +9.26 | 7 | 10 | 7 (▲1) |
| 9 | 1–33 | Ohio State | 10-2 | 1.101 | 0.0793 | 31.00 | 33.91 | 29.98 | 3.31 | +1.03 | 8 | 3 | 10 (▼1) |
| 10 | 4–63 | Baylor | 11-2 | 1.068 | 0.0856 | 30.60 | 24.58 | 21.12 | 3.27 | +9.48 | 10 | 12 | 9 (▲1) |
| 11 | 7–76 | UTSA | 12-1 | 0.810 | 0.1550 | 30.51 | 19.54 | 16.23 | 3.17 | +14.28 | 11 | 35 | 11 (—) |
| 12 | 5–74 | Oklahoma | 10-2 | 0.808 | 0.1555 | 28.42 | 22.31 | 19.40 | 3.36 | +9.02 | 13 | 18 | 12 (—) |

> **The interval is the honest part of this table.** Every rank carries a 90%
> interval from 1,000 parametric draws on the FIXED schedule: each draw redraws
> every game's margin from the fitted model, refits, and re-ranks with the same
> code the poll uses. The median interval width across all 130 ranked
> teams is **72 places**. A poll that prints an integer for a quantity
> that moves that far is claiming a precision it does not have.
>
> Two things follow that a reader should expect rather than discover. The
> bootstrap MEDIAN is worse than the published rank for nearly every undefeated
> team, because under the model's own estimate of their quality going unbeaten is
> an unlikely outcome and most simulated seasons do not repeat it - which is what
> ranking by improbability MEANS. And with `power_source = "L3"` the efficiency
> half of Power is held fixed across draws, because plays are not resimulated, so
> these intervals are a **lower bound** on total uncertainty.
>
> `±` is the ridge sandwich standard error of the Power rating, in points
> (report 02 §3.3). Full method and the replication of the independent review's
> own bootstrap: [docs/analysis/uncertainty.md](../docs/analysis/uncertainty.md).


**The hindsight column is new to this page.** It used to read `— (—)` on every row,
because with no postseason in the archive the final evaluation week *was* the final
data window, so R(N, N) and R(N, final) were literally the same fit. They are no
longer, and three adjacent pairs trade places: Georgia and Michigan, Ole Miss and
Michigan State, Baylor and Ohio State.

Read that column carefully, because the obvious reading of it is wrong. Hindsight
re-scores **the same games** — everything through championship Saturday — using
opponent quality estimated from the whole season. A team does not move here because
of how its own bowl went; it moves because the postseason revised what we think of
the teams it had already played. Michigan State won its bowl and still slips one
place, and Ole Miss lost its bowl and still gains one. That is the substitution
doing exactly its job, and it is a cleaner demonstration of what R(N, final) means
than a season where the movement happened to line up with the results.

## The three numbers, side by side

| Team | Rec | −log10 P | P(W ≥ W_t) | Poll # | Résumé | Résumé # | Power | Power # |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|
| Cincinnati | 13-0 | 1.945 | 0.0113 | 2 | 60.00\* | 1 | 27.34 | 5 |
| Alabama | 12-1 | 2.289 | 0.0051 | 1 | 41.65 | 2 | 31.69 | 2 |
| Michigan | 12-1 | 1.941 | 0.0115 | 3 | 39.70 | 3 | 29.65 | 4 |
| Georgia | 12-1 | 1.895 | 0.0127 | 4 | 39.31 | 4 | 34.69 | 1 |

**Cincinnati is poll #2, résumé #1, power #5. The committee put it at #4.**

The agreement with the committee is worth noticing and is emphatically **not** a
target: report 02 §5.5 is explicit that fitting toward committee agreement would
reintroduce human-poll bias through the back door, a subtle but complete violation of
constraint 1. What it shows is narrower and more useful. This poll says fourth, the
committee said fourth, and the margin-aware résumé says fourth too (study §7). The
ordering this project used to publish was the only one that said **first** — and it
said first because it could not say anything else.

The poll number says 13-0 against this schedule is a 1.13-in-100 event for a reference-quality
team: 0.514 in 100 for Alabama's 12-1, 1.146 for Michigan's and 1.274 for Georgia's,
against 1.135 for Cincinnati's. Three teams did something less likely than Cincinnati
did, and Georgia's 12-1 and Cincinnati's 13-0 are close enough that they separate in
the third decimal place — which is a far more honest description of that argument
than either #1 or #5.

That is a statement about schedules, derived from who those teams played. No
conference identity enters any design matrix (constraint 2), so the phrase
"American Athletic Conference" appears nowhere in the computation — and the ordering
would be identical if the conference labels were shuffled.

The power rating, 27.34 points, is the model's separate estimate of how good Cincinnati
was, and it is 5th. Publishing all three, with the résumé-minus-power gap
(+32.66) printed between the last two, is the whole of report 02 §3.5's argument in one row.

The win that carries the number is on the schedule: at Notre Dame, 24-13, on
2 October 2021. Notre Dame finished the regular season 11-1 and is power #7 here,
so it is a genuinely load-bearing road win against a top-ten team — which is
exactly the kind of thing a desert ordering is supposed to notice and a
margin-based power rating is supposed to under-weight.

## The retroactive view: Cincinnati week by week

Cincinnati was undefeated all season, which is precisely the case in which the
ordering this project published until 2026-08-12 could say nothing: its wins-based
résumé is pinned at the bracket in every week, and the bracket does not depend on
the data window, so the substitution had nothing to act on. The `Résumé #` column
below is that ordering's answer, carried for comparison. The poll's own column is
free to move, and does.

| Week | Live # | Hindsight # | Move | Résumé # live → hindsight | Power live | Power hindsight |
|---|---:|---:|---:|---:|---:|---:|
| `2021-regu-w01` | 63 | 28 | ▲35 | 27 → 9 | 10.77 | 25.89 |
| `2021-regu-w02` | 44 | 33 | ▲11 | 3 → 6 | 6.55 | 25.89 |
| `2021-regu-w03` | 16 | 25 | ▼9 | 5 → 8 | 8.21 | 25.89 |
| `2021-regu-w04` | 21 | 27 | ▼6 | 5 → 7 | 13.35 | 25.89 |
| `2021-regu-w05` | 12 | 9 | ▲3 | 4 → 4 | 16.70 | 25.89 |
| `2021-regu-w06` | 10 | 11 | ▼1 | 2 → 2 | 17.26 | 25.89 |
| `2021-regu-w07` | 6 | 6 | — | 2 → 2 | 23.48 | 25.89 |
| `2021-regu-w08` | 8 | 6 | ▲2 | 3 → 2 | 20.29 | 25.89 |
| `2021-regu-w09` | 5 | 4 | ▲1 | 2 → 2 | 22.03 | 25.89 |
| `2021-regu-w10` | 5 | 2 | ▲3 | 2 → 2 | 22.40 | 25.89 |
| `2021-regu-w11` | 5 | 2 | ▲3 | 2 → 2 | 22.78 | 25.89 |
| `2021-regu-w12` | 2 | 2 | — | 2 → 2 | 25.75 | 25.89 |
| `2021-regu-w13` | 4 | 2 | ▲2 | 2 → 2 | 26.63 | 25.89 |
| `2021-regu-w14` | 3 | 2 | ▲1 | 1 → 1 | 27.17 | 25.89 |
| `2021-regu-w15` | 2 | 2 | — | 1 → 1 | 27.34 | 25.89 |
| `2021-post-w01` | 4 | 4 | — | 3 → 3 | 25.89 | 25.89 |

Week 1 is the interesting row: live, Cincinnati is nowhere, because after one game
against nobody in particular a zero-prior ridge knows nothing. In hindsight it is
already a top-ten team's week 1. By week 6 the two columns have converged and stay
converged, which is the divergence curve of report 02 §5.2 behaving itself.

## The comparison — **not** a target

| CFP # | Team | Rec |
|---:|---|:---:|
| 1 | Alabama | 12-1 |
| 2 | Michigan | 12-1 |
| 3 | Georgia | 12-1 |
| 4 | Cincinnati | 13-0 |
| 5 | Notre Dame | 11-1 |
| 6 | Ohio State | 10-2 |

Source: the official CFP release of 5 December 2021. This is a human poll. It is a
comparison and never an input (constraint 1).

## What happened next — and what the poll does with it

This section used to be headed *what this document cannot tell you*, and it said that
Cincinnati lost the Cotton Bowl semifinal to Alabama 27-6, that the game was not in
the archive, and that a reader arguing the playoff settled the question was arguing
from evidence this poll had not seen. That was an honest caveat and it was also a
hole. It is closed. The game is in the frame:

| Date | Game | Result | `game_type` | Weight | Source |
|---|---|---|:---:|---:|---|
| 31 December 2021 | CFP Semifinal (Cotton Bowl) | Alabama 27, Cincinnati 6 | `cfp` | 1.0 | `cfbd` |

**And the answer is more interesting than either side of the old argument.**

Cincinnati is **#2 live and #2 in hindsight** — the
semifinal did not move its rank at all. That is the ordering behaving exactly as
specified rather than dodging the question: the rank key asks how improbable it was
to go 13-0 against *that schedule*, and losing a fourteenth game to Alabama does not
retroactively make the first thirteen easier. A poll that dropped Cincinnati here
would be scoring the semifinal twice — once as a loss and once as a reason to doubt
the season that earned the invitation.

What *does* move is the Power rating, the model's separate estimate of how good
Cincinnati was: **27.34 points live, 25.89 in hindsight**, a fall of 1.45.
That is the division of labour working, and it is the whole argument for publishing
both numbers. The résumé says what you did; the power rating says how good you
looked doing it. Alabama 27-6 is evidence about the second and not the first, and
the two columns say so independently rather than averaging into one number that
means neither.

## Reproduce it

```
uv run cfbpoll rank --season 2021 --through-week 15 --out out/
uv run cfbpoll grid --season 2021 --out out/
```

Generated by `scripts/make_demos.py` at 2026-08-13 from the local SportsDataverse MIT archive (2021-2025 `cfb_schedules_*`), plus the private CFBD archive for the 2021-2022 postseason (80 games).
Code `05c7578` - config `configs/default.toml` sha256 `c836cec36f7d49d3...`
