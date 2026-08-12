# 2021: Cincinnati, the first Group of Five playoff team

> **Data caveat, stated up front.** The `cfb_schedules_*` archive carries **no postseason rows at all** for 2021 and 2022: `season_type` has one value, `regular`. So "final" in this document means **through conference championship weekend** — no bowls, no playoff. Every number below is computed on that window and none of it should be read as though it included the postseason.

Cincinnati went 13-0, won the American, and became the first team from outside the
Power Five to make the College Football Playoff — at **#4**, behind three one-loss
Power Five teams. The argument at the time was entirely about schedule: had
Cincinnati actually *done* more than Alabama, Michigan and Georgia, or had it only
avoided losing to anybody good? That is precisely the question the résumé rating is
constructed to answer, so it is the natural first test of it.

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

## The final poll (through conference championships)

| # | Team | Rec | Résumé | Margin résumé | Power | Gap | Power # | Hindsight # |
|---:|---|:---:|---:|---:|---:|---:|---:|---:|
| 1 | Cincinnati | 13-0 | 60.00\* | 32.86 | 27.27 | +32.73 | 5 | 1 (—) |
| 2 | Alabama | 12-1 | 39.49 | 35.09 | 31.23 | +8.26 | 2 | 2 (—) |
| 3 | Michigan | 12-1 | 37.65 | 34.10 | 29.37 | +8.28 | 4 | 3 (—) |
| 4 | Georgia | 12-1 | 37.13 | 39.58 | 34.35 | +2.78 | 1 | 4 (—) |
| 5 | Notre Dame | 11-1 | 33.79 | 27.60 | 24.98 | +8.81 | 6 | 5 (—) |
| 6 | Michigan State | 10-2 | 30.37 | 22.95 | 20.37 | +10.01 | 14 | 6 (—) |
| 7 | Ole Miss | 10-2 | 29.96 | 24.47 | 21.82 | +8.14 | 10 | 7 (—) |
| 8 | Ohio State | 10-2 | 29.57 | 32.58 | 29.61 | -0.04 | 3 | 8 (—) |
| 9 | Oklahoma State | 11-2 | 29.05 | 25.18 | 24.60 | +4.45 | 7 | 9 (—) |
| 10 | Baylor | 11-2 | 28.77 | 23.13 | 20.37 | +8.40 | 13 | 10 (—) |
| 11 | UTSA | 12-1 | 28.65 | 18.17 | 15.78 | +12.87 | 36 | 11 (—) |
| 12 | Louisiana | 12-1 | 28.09 | 16.18 | 14.25 | +13.84 | 41 | 12 (—) |

For this season the live and hindsight columns are **identical**, and that is not a
bug: with no postseason in the archive, the final evaluation week *is* the final
data window, so R(N, N) and R(N, final) are the same fit. The retroactive view of
2021 lives in the earlier weeks, below.

## The two numbers, side by side

| Team | Rec | Résumé | Résumé # | Power | Power # | Gap |
|---|:---:|---:|---:|---:|---:|---:|
| Cincinnati | 13-0 | 60.00\* | 1 | 27.27 | 5 | +32.73 |
| Alabama | 12-1 | 39.49 | 2 | 31.23 | 2 | +8.26 |
| Michigan | 12-1 | 37.65 | 3 | 29.37 | 4 | +8.28 |
| Georgia | 12-1 | 37.13 | 4 | 34.35 | 1 | +2.78 |

**Cincinnati is résumé #1 and power #5.** The committee put it at #4, which is
almost exactly between the two numbers — and, read charitably, is what a committee
trying to blend "what did you do" with "how good are you" would land on if it did
the blending in its head instead of on paper.

The résumé number is not saying Cincinnati was the best team in the country. It is
saying that **13-0 against this schedule has no finite quality that explains it** —
the saturation property, which puts every unbeaten team on the bracket. The power
rating, 27.27 points, is the model's actual estimate of how good Cincinnati was, and it
is 5th. Publishing both, with the gap (+32.73) printed between them, is the
whole of report 02 §3.5's argument in one row.

The win that carried the résumé is on the schedule: at Notre Dame, 24-13, on
2 October 2021. Notre Dame finished the regular season 11-1 and is power #6 here,
so it is a genuinely load-bearing road win against a top-ten team — which is
exactly the kind of thing a résumé rating is supposed to notice and a margin-based
power rating is supposed to under-weight.

## The retroactive view: Cincinnati week by week

Cincinnati was undefeated all season, so its wins-based résumé is pinned at the
bracket in every week and the rank movement below comes entirely from the
margin-aware tie-break and from what the rest of the country learned about
Cincinnati's opponents. The Power column is where the substitution shows.

| Week | Live # | Hindsight # | Move | Power live | Power hindsight |
|---|---:|---:|---:|---:|---:|
| `2021-regu-w01` | 26 | 7 | ▲19 | 10.87 | 27.27 |
| `2021-regu-w02` | 3 | 5 | ▼2 | 6.60 | 27.27 |
| `2021-regu-w03` | 4 | 9 | ▼5 | 8.28 | 27.27 |
| `2021-regu-w04` | 3 | 6 | ▼3 | 13.35 | 27.27 |
| `2021-regu-w05` | 4 | 3 | ▲1 | 16.52 | 27.27 |
| `2021-regu-w06` | 2 | 2 | — | 17.17 | 27.27 |
| `2021-regu-w07` | 2 | 2 | — | 22.99 | 27.27 |
| `2021-regu-w08` | 3 | 2 | ▲1 | 19.95 | 27.27 |
| `2021-regu-w09` | 2 | 2 | — | 21.83 | 27.27 |
| `2021-regu-w10` | 2 | 2 | — | 22.06 | 27.27 |
| `2021-regu-w11` | 2 | 2 | — | 22.71 | 27.27 |
| `2021-regu-w12` | 2 | 2 | — | 25.63 | 27.27 |
| `2021-regu-w13` | 2 | 2 | — | 26.56 | 27.27 |
| `2021-regu-w14` | 1 | 1 | — | 27.13 | 27.27 |
| `2021-regu-w15` | 1 | 1 | — | 27.27 | 27.27 |

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

**What this document cannot tell you.** Cincinnati lost the Cotton Bowl semifinal to
Alabama 27-6. That game is not in the archive for this season, so it is not in any
number above. A reader who wants to argue that the playoff settled the question is
arguing from evidence this poll has not seen — which is worth saying plainly rather
than letting the omission pass as a result.

## Reproduce it

```
uv run cfbpoll rank --season 2021 --through-week 15 --out out/
uv run cfbpoll grid --season 2021 --out out/
```

Generated by `scripts/make_demos.py` at 2026-08-12 from the local SportsDataverse MIT archive (2021-2025 `cfb_schedules_*`).
Code `0fc0735` - config `configs/default.toml` sha256 `9cbd0331ca1732a0...`
