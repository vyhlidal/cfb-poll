# The 2023 final poll — résumé and power, live and hindsight

This is the headline product: teams ranked by the **L4 résumé rating**, which is
the quality `q` whose *expected* results against that exact schedule equal the
*actual* ones, with the **Power rating** and the résumé-minus-power gap beside
every team (report 02 §3.4, §3.5). It is shown twice — as the poll would have read
on championship Saturday, and as it reads with the whole season's answers in hand.

> **Power is L2, version v0.** Report 02 §3.4 reads opponent quality off the L3
> blend of efficiency and results. L1 and L3 are not built (report 02 Appendix B
> puts them fourth and fifth), so the Power rating here is the L2 results core
> rescaled to points by one no-intercept OLS per fit. Every artifact stamps
> `power_source = "L2"`, `power_version = "v0"`. When L3 lands, this number
> changes and the résumé equation does not.

## The window, precisely

| | |
|---|---|
| Evaluation week **N** | `2023-regu-w15` — through conference championships |
| Live data window **K = N** | R(N, N), 2023-regu-w15 |
| Hindsight data window **K = final** | R(N, final), `2023-post-w01` — includes bowls and the playoff |
| Games in the season frame | 1,603 |
| ... of which FBS-vs-FBS | 792 |
| Ranked (FBS) teams | 133 |
| sigma | 15.3 points |
| Compression C / win premium beta_w | 24 / 3 |

The evaluation week is championship Saturday and **not** the post-bowl end of the
season, because `[weights].final_poll_excludes_non_cfp_bowls = true`: non-CFP bowls
have a systematic roster-availability problem (report 02 §3.8), so the final
published poll is the one computed before them. That also makes this poll directly
comparable to the committee's final ranking, which was released the same weekend.
The hindsight column *does* see the postseason — non-CFP bowls at weight
0.25, playoff games at full weight — because hindsight is
allowed to know things the live poll could not.

## The poll

Résumé is the rank. `Power #` is where the same team sits on the power rating, so
the disagreement between the two is readable on every row. `Hindsight #` is R(N,
final): the same week, re-scored with the season's answers.

| # | Team | Rec | Résumé | Margin résumé | Power | Gap | Power # | Hindsight # |
|---:|---|:---:|---:|---:|---:|---:|---:|---:|
| 1 | Michigan | 13-0 | 60.00\* | 45.54 | 39.47 | +20.53 | 1 | 1 (—) |
| 2 | Florida State | 13-0 | 60.00\* | 36.14 | 33.81 | +26.19 | 8 | 2 (—) |
| 3 | Washington | 13-0 | 60.00\* | 35.53 | 33.98 | +26.02 | 7 | 3 (—) |
| 4 | Liberty | 13-0 | 60.00\* | 24.92 | 24.01 | +35.99 | 20 | 4 (—) |
| 5 | Texas | 12-1 | 44.58 | 38.72 | 37.18 | +7.40 | 3 | 7 (▼2) |
| 6 | Alabama | 12-1 | 44.54 | 35.09 | 33.79 | +10.75 | 9 | 6 (—) |
| 7 | Ohio State | 11-1 | 44.40 | 40.52 | 37.54 | +6.86 | 2 | 5 (▲2) |
| 8 | Georgia | 12-1 | 40.89 | 38.00 | 35.01 | +5.88 | 5 | 8 (—) |
| 9 | Oregon | 11-2 | 35.35 | 39.93 | 36.81 | -1.46 | 4 | 9 (—) |
| 10 | Ole Miss | 10-2 | 35.11 | 27.87 | 26.49 | +8.62 | 16 | 10 (—) |
| 11 | Missouri | 10-2 | 33.78 | 29.21 | 28.75 | +5.04 | 13 | 12 (▼1) |
| 12 | Oklahoma | 10-2 | 33.62 | 33.85 | 33.19 | +0.43 | 10 | 13 (▼1) |
| 13 | Penn State | 10-2 | 33.56 | 37.76 | 34.62 | -1.07 | 6 | 11 (▲2) |
| 14 | James Madison | 11-1 | 31.50 | 24.26 | 24.12 | +7.38 | 19 | 14 (—) |
| 15 | LSU | 9-3 | 30.06 | 30.47 | 28.72 | +1.35 | 14 | 15 (—) |
| 16 | Louisville | 10-3 | 27.26 | 23.95 | 23.27 | +3.99 | 22 | 17 (▼1) |
| 17 | Iowa | 10-3 | 27.19 | 18.55 | 18.60 | +8.59 | 36 | 16 (▲1) |
| 18 | Troy | 11-2 | 26.67 | 24.74 | 24.59 | +2.08 | 18 | 18 (—) |
| 19 | Notre Dame | 9-3 | 26.62 | 32.06 | 29.42 | -2.80 | 12 | 19 (—) |
| 20 | Oklahoma State | 9-4 | 26.37 | 20.44 | 20.00 | +6.37 | 33 | 20 (—) |
| 21 | SMU | 11-2 | 26.34 | 23.65 | 21.86 | +4.48 | 26 | 22 (▼1) |
| 22 | Kansas State | 8-4 | 26.24 | 31.92 | 30.67 | -4.44 | 11 | 21 (▲1) |
| 23 | Arizona | 9-3 | 25.84 | 26.45 | 26.27 | -0.42 | 17 | 23 (—) |
| 24 | Utah | 8-4 | 25.70 | 21.70 | 21.06 | +4.64 | 29 | 24 (—) |
| 25 | NC State | 9-3 | 25.22 | 20.85 | 20.28 | +4.94 | 30 | 25 (—) |

**Why every undefeated team shows 60.00 and a `*`.** `E[W|q]` approaches the
number of games from below, so an undefeated team's résumé equation has **no
finite root** — the results are consistent with arbitrarily high quality. That is
Bradley-Terry's separation problem (report 02 §2.10) in deterministic clothes, and
the published bracket `q_bounds = [-60, +60]` is the regularization: it is where an
unbounded estimate gets truncated, at a number printed in the config. Two
consequences, both stated rather than hidden:

1. On the wins-based résumé **no one-loss team can outrank an undefeated team**,
   however soft the unbeaten schedule.
2. Saturated teams all land on the same value, so the order among them comes from
   the **margin-aware résumé**, which is finite for every team and is in the table.
   The rule is `[resume].saturation_tiebreak = "margin"`.

## The test this season exists for: Florida State

Florida State finished 13-0, won the ACC, and was left out of a four-team playoff
for the first time in the CFP era. Here is what a transparent system says, on both
numbers and both surfaces:

| | Résumé rank | Résumé | Margin résumé | Power rank | Power | Gap |
|---|---:|---:|---:|---:|---:|---:|
| **Live** R(N, N) | 2 | 60.00\* | 36.14 | 8 | 33.81 | +26.19 |
| **Hindsight** R(N, final) | 2 | 60.00\* | 36.12 | 9 | 33.16 | +26.84 |

**The two numbers disagree by 7 places, and
that disagreement is the entire product.** The résumé says Florida State did the
2nd-best job of beating the schedule in front of it — nobody with a loss can
outrank an unbeaten team on that number, by construction. The power rating says its
play was worth about 33.2 points against an average team, 9th
in the country, because it won a lot of close games. Both are true. The committee
was answering a third question — who would we most like to watch play for a title —
and it is the only one of the three that is not written down anywhere.

Note what hindsight does **not** do here: it does not move Florida State. The
Orange Bowl, in which a Florida State team missing 33 players lost 63-3, is in the
hindsight *Power* fit at weight 0.25 and is **not** in the résumé, because the
résumé window is frozen at week N (variant A, report 02 §3.6). A poll that let the
January consequences of the December decision retroactively justify the December
decision would be circular, and this construction cannot do it.

## Georgia, and the sanity check

Georgia was 12-1 with its only loss in the SEC championship game. Résumé 8 live,
8 in hindsight; power 5 live and 5 in hindsight. That gap runs the other way from Florida
State's — the model thinks Georgia *played* better than its résumé, which is what
losing one game to a good opponent looks like from the inside.

Alabama, whom the committee took over Florida State, is résumé 6 and power 9
here (live). On the power number the committee and this model broadly agree about
Alabama; on the résumé number they do not agree about what a 13-0 season is worth.

## The uncomfortable row

Liberty went 13-0 in Conference USA and lands at résumé 4 with a power rating of
24.01 — 20th. This is the saturation property doing exactly what it says it
does, and it is the single strongest argument against publishing the wins-based
résumé alone. The margin-aware résumé, in the same table, puts Liberty at
24.92 against Michigan's 45.54, which is a far more useful
sentence about the season. Report 02 §3.4 says to publish both because they answer
different questions; this row is why that instruction is load-bearing rather than
decorative.

## The committee's final ranking, for comparison — **not** a target

Fitting toward committee agreement would reintroduce human-poll bias through the
back door: a subtle but complete violation of constraint 1. This table is here so
the disagreements are visible, and the disagreements are the product (report 02
§5.5).

| CFP # | Team | Rec |
|---:|---|:---:|
| 1 | Michigan | 13-0 |
| 2 | Washington | 13-0 |
| 3 | Texas | 12-1 |
| 4 | Alabama | 12-1 |
| 5 | Florida State | 13-0 |

Sources: the official CFP release of 3 December 2023.

## Reproduce it

```
uv run cfbpoll rank --season 2023 --through-week 15 --out out/
uv run cfbpoll grid --season 2023 --out out/
```

`4` ranked teams are saturated in the live poll. The full 56,176-row R(N, K)
triangle, both surfaces and the movers table are written by the second command.

Generated by `scripts/make_demos.py` at 2026-08-12 from the local SportsDataverse MIT archive (2021-2025 `cfb_schedules_*`).
Code `dfd6342` - config `configs/default.toml` sha256 `d51df72ef70172b6...`
