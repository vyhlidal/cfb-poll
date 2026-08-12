# The 2023 final poll — résumé and power, live and hindsight

This is the headline product: teams ranked by the **L4 résumé rating**, which is
the quality `q` whose *expected* results against that exact schedule equal the
*actual* ones, with the **Power rating** and the résumé-minus-power gap beside
every team (report 02 §3.4, §3.5). It is shown twice — as the poll would have read
on championship Saturday, and as it reads with the whole season's answers in hand.

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
| 1 | Michigan | 13-0 | 60.00\* | 38.72 | 31.87 | +28.13 | 1 | 1 (—) |
| 2 | Florida State | 13-0 | 60.00\* | 31.24 | 23.21 | +36.79 | 11 | 2 (—) |
| 3 | Washington | 13-0 | 60.00\* | 29.18 | 23.38 | +36.62 | 10 | 3 (—) |
| 4 | Liberty | 13-0 | 60.00\* | 22.35 | 18.72 | +41.28 | 17 | 4 (—) |
| 5 | Ohio State | 11-1 | 37.58 | 34.39 | 29.22 | +8.36 | 3 | 5 (—) |
| 6 | Alabama | 12-1 | 36.76 | 28.65 | 23.98 | +12.79 | 8 | 6 (—) |
| 7 | Texas | 12-1 | 36.49 | 31.41 | 25.44 | +11.05 | 7 | 7 (—) |
| 8 | Georgia | 12-1 | 33.74 | 31.88 | 25.95 | +7.79 | 5 | 8 (—) |
| 9 | Ole Miss | 10-2 | 28.03 | 21.99 | 18.03 | +10.00 | 20 | 9 (—) |
| 10 | Oregon | 11-2 | 27.39 | 32.50 | 30.51 | -3.12 | 2 | 12 (▼2) |
| 11 | Missouri | 10-2 | 27.11 | 23.25 | 20.81 | +6.31 | 13 | 11 (—) |
| 12 | James Madison | 11-1 | 27.08 | 20.55 | 17.38 | +9.70 | 23 | 13 (▼1) |
| 13 | Penn State | 10-2 | 26.91 | 31.38 | 26.30 | +0.61 | 4 | 10 (▲3) |
| 14 | Oklahoma | 10-2 | 26.51 | 27.25 | 25.75 | +0.76 | 6 | 14 (—) |
| 15 | LSU | 9-3 | 22.90 | 23.98 | 20.67 | +2.23 | 14 | 15 (—) |
| 16 | Troy | 11-2 | 22.01 | 20.76 | 17.57 | +4.44 | 22 | 16 (—) |
| 17 | SMU | 11-2 | 21.58 | 20.24 | 18.60 | +2.97 | 18 | 17 (—) |
| 18 | Tulane | 11-2 | 20.89 | 13.74 | 10.72 | +10.18 | 44 | 19 (▼1) |
| 19 | Louisville | 10-3 | 20.83 | 18.05 | 18.06 | +2.77 | 19 | 20 (▼1) |
| 20 | Iowa | 10-3 | 20.77 | 12.84 | 7.39 | +13.38 | 63 | 18 (▲2) |
| 21 | Notre Dame | 9-3 | 20.49 | 26.43 | 23.53 | -3.03 | 9 | 21 (—) |
| 22 | NC State | 9-3 | 19.94 | 16.03 | 12.28 | +7.66 | 36 | 22 (—) |
| 23 | Oklahoma State | 9-4 | 19.66 | 14.29 | 11.32 | +8.34 | 41 | 23 (—) |
| 24 | Arizona | 9-3 | 19.40 | 20.31 | 19.47 | -0.06 | 16 | 24 (—) |
| 25 | Utah | 8-4 | 19.05 | 15.40 | 13.17 | +5.88 | 32 | 25 (—) |

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
| **Live** R(N, N) | 2 | 60.00\* | 31.24 | 11 | 23.21 | +36.79 |
| **Hindsight** R(N, final) | 2 | 60.00\* | 30.93 | 11 | 22.06 | +37.94 |

**The two numbers disagree by 9 places, and
that disagreement is the entire product.** The résumé says Florida State did the
2nd-best job of beating the schedule in front of it — nobody with a loss can
outrank an unbeaten team on that number, by construction. The power rating says its
play was worth about 22.1 points against an average team, 11th
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
8 in hindsight; power 5 live and 4 in hindsight. That gap runs the other way from Florida
State's — the model thinks Georgia *played* better than its résumé, which is what
losing one game to a good opponent looks like from the inside.

Alabama, whom the committee took over Florida State, is résumé 6 and power 8
here (live). On the power number the committee and this model broadly agree about
Alabama; on the résumé number they do not agree about what a 13-0 season is worth.

## The uncomfortable row

Liberty went 13-0 in Conference USA and lands at résumé 4 with a power rating of
18.72 — 17th. This is the saturation property doing exactly what it says it
does, and it is the single strongest argument against publishing the wins-based
résumé alone. The margin-aware résumé, in the same table, puts Liberty at
22.35 against Michigan's 38.72, which is a far more useful
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
Code `0fc0735` - config `configs/default.toml` sha256 `9cbd0331ca1732a0...`
