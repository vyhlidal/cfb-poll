# 2021: Cincinnati, the first Group of Five playoff team

> **Data caveat, stated up front.** The `cfb_schedules_*` archive carries **no postseason rows at all** for 2021 and 2022: `season_type` has one value, `regular`. So "final" in this document means **through conference championship weekend** — no bowls, no playoff. Every number below is computed on that window and none of it should be read as though it included the postseason.

Cincinnati went 13-0, won the American, and became the first team from outside the
Power Five to make the College Football Playoff — at **#4**, behind three one-loss
Power Five teams. The argument at the time was entirely about schedule: had
Cincinnati actually *done* more than Alabama, Michigan and Georgia, or had it only
avoided losing to anybody good? That is precisely the question the résumé rating is
constructed to answer, so it is the natural first test of it.

> **Power is L2, version v0.** Report 02 §3.4 reads opponent quality off the L3
> blend of efficiency and results. L1 and L3 are not built (report 02 Appendix B
> puts them fourth and fifth), so the Power rating here is the L2 results core
> rescaled to points by one no-intercept OLS per fit. Every artifact stamps
> `power_source = "L2"`, `power_version = "v0"`. When L3 lands, this number
> changes and the résumé equation does not.

## The final poll (through conference championships)

| # | Team | Rec | Résumé | Margin résumé | Power | Gap | Power # | Hindsight # |
|---:|---|:---:|---:|---:|---:|---:|---:|---:|
| 1 | Cincinnati | 13-0 | 60.00\* | 36.18 | 33.28 | +26.72 | 5 | 1 (—) |
| 2 | Alabama | 12-1 | 44.06 | 39.27 | 37.05 | +7.01 | 3 | 2 (—) |
| 3 | Michigan | 12-1 | 43.30 | 39.06 | 37.32 | +5.98 | 2 | 3 (—) |
| 4 | Georgia | 12-1 | 41.61 | 43.66 | 40.12 | +1.49 | 1 | 4 (—) |
| 5 | Notre Dame | 11-1 | 38.26 | 31.53 | 31.78 | +6.48 | 6 | 5 (—) |
| 6 | Michigan State | 10-2 | 35.74 | 27.57 | 27.61 | +8.13 | 11 | 6 (—) |
| 7 | Ohio State | 10-2 | 34.99 | 37.63 | 35.85 | -0.86 | 4 | 7 (—) |
| 8 | Ole Miss | 10-2 | 34.08 | 28.31 | 27.94 | +6.14 | 10 | 8 (—) |
| 9 | Oklahoma State | 11-2 | 33.98 | 29.83 | 30.13 | +3.85 | 7 | 9 (—) |
| 10 | Baylor | 11-2 | 33.57 | 27.32 | 26.29 | +7.28 | 14 | 10 (—) |
| 11 | UTSA | 12-1 | 31.44 | 20.16 | 20.14 | +11.30 | 35 | 11 (—) |
| 12 | Oklahoma | 10-2 | 31.14 | 24.55 | 24.39 | +6.75 | 17 | 12 (—) |

For this season the live and hindsight columns are **identical**, and that is not a
bug: with no postseason in the archive, the final evaluation week *is* the final
data window, so R(N, N) and R(N, final) are the same fit. The retroactive view of
2021 lives in the earlier weeks, below.

## The two numbers, side by side

| Team | Rec | Résumé | Résumé # | Power | Power # | Gap |
|---|:---:|---:|---:|---:|---:|---:|
| Cincinnati | 13-0 | 60.00\* | 1 | 33.28 | 5 | +26.72 |
| Alabama | 12-1 | 44.06 | 2 | 37.05 | 3 | +7.01 |
| Michigan | 12-1 | 43.30 | 3 | 37.32 | 2 | +5.98 |
| Georgia | 12-1 | 41.61 | 4 | 40.12 | 1 | +1.49 |

**Cincinnati is résumé #1 and power #5.** The committee put it at #4, which is
almost exactly between the two numbers — and, read charitably, is what a committee
trying to blend "what did you do" with "how good are you" would land on if it did
the blending in its head instead of on paper.

The résumé number is not saying Cincinnati was the best team in the country. It is
saying that **13-0 against this schedule has no finite quality that explains it** —
the saturation property, which puts every unbeaten team on the bracket. The power
rating, 33.28 points, is the model's actual estimate of how good Cincinnati was, and it
is 5th. Publishing both, with the gap (+26.72) printed between them, is the
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
| `2021-regu-w01` | 21 | 7 | ▲14 | 9.59 | 33.28 |
| `2021-regu-w02` | 7 | 6 | ▲1 | 15.45 | 33.28 |
| `2021-regu-w03` | 7 | 10 | ▼3 | 21.78 | 33.28 |
| `2021-regu-w04` | 5 | 9 | ▼4 | 23.50 | 33.28 |
| `2021-regu-w05` | 4 | 3 | ▲1 | 28.06 | 33.28 |
| `2021-regu-w06` | 2 | 2 | — | 28.72 | 33.28 |
| `2021-regu-w07` | 2 | 2 | — | 32.46 | 33.28 |
| `2021-regu-w08` | 3 | 2 | ▲1 | 28.89 | 33.28 |
| `2021-regu-w09` | 2 | 2 | — | 29.64 | 33.28 |
| `2021-regu-w10` | 2 | 2 | — | 29.55 | 33.28 |
| `2021-regu-w11` | 2 | 2 | — | 29.62 | 33.28 |
| `2021-regu-w12` | 2 | 2 | — | 31.79 | 33.28 |
| `2021-regu-w13` | 2 | 2 | — | 32.35 | 33.28 |
| `2021-regu-w14` | 1 | 1 | — | 32.90 | 33.28 |
| `2021-regu-w15` | 1 | 1 | — | 33.28 | 33.28 |

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
Code `dfd6342` - config `configs/default.toml` sha256 `d51df72ef70172b6...`
