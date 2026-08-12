# The 2023 final poll — schedule odds, résumé and power, live and hindsight

This is the headline product: teams ranked by **schedule odds** — how improbable it
is that a reference-quality team would have gone at least this well against that
exact schedule — with the **L4 résumé rating**, the **Power rating** and the
résumé-minus-power gap beside every team (report 02 §3.4, §3.5). It is shown twice:
as the poll would have read on championship Saturday, and as it reads with the whole
season's answers in hand.

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
> `q_ref` is the Power rating of the **25th-ranked Power team** — **Tennessee** this week, at
> **15.99 points**. It is the one free constant in the ordering, so it is
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
| Evaluation week **N** | `2023-regu-w15` — through conference championships |
| Live data window **K = N** | R(N, N), 2023-regu-w15 |
| Hindsight data window **K = final** | R(N, final), `2023-post-w01` — includes bowls and the playoff |
| Games in the season frame | 1,603 |
| ... of which FBS-vs-FBS | 792 |
| Ranked (FBS) teams | 133 |
| Rank key | `−log10 P(W ≥ W_t)`, exact Poisson-binomial |
| `q_ref` (power_rank_25) | 15.99 points — Tennessee |
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

Schedule odds is the rank. `Résumé #` is where the same team sat under the ordering
this project published until 2026-08-12, and `Power #` is where it sits on the power
rating — both kept as labelled comparison columns so the disagreement between the
three is readable on every row rather than asserted. `Hindsight #` is R(N, final):
the same week, re-scored with the season's answers.

| # | Team | Rec | −log10 P | P(W ≥ W_t) | Résumé | Margin résumé | Power | Gap | Résumé # | Power # | Hindsight # |
|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | Washington | 13-0 | 3.601 | 0.0003 | 60.00\* | 29.18 | 23.38 | +36.62 | 3 | 10 | 1 (—) |
| 2 | Michigan | 13-0 | 2.574 | 0.0027 | 60.00\* | 38.72 | 31.87 | +28.13 | 1 | 1 | 2 (—) |
| 3 | Florida State | 13-0 | 2.406 | 0.0039 | 60.00\* | 31.24 | 23.21 | +36.79 | 2 | 11 | 3 (—) |
| 4 | Alabama | 12-1 | 2.167 | 0.0068 | 36.76 | 28.65 | 23.98 | +12.79 | 6 | 8 | 4 (—) |
| 5 | Texas | 12-1 | 2.064 | 0.0086 | 36.49 | 31.41 | 25.44 | +11.05 | 7 | 7 | 5 (—) |
| 6 | Ohio State | 11-1 | 1.905 | 0.0124 | 37.58 | 34.39 | 29.22 | +8.36 | 5 | 3 | 6 (—) |
| 7 | Georgia | 12-1 | 1.591 | 0.0256 | 33.74 | 31.88 | 25.95 | +7.79 | 8 | 5 | 7 (—) |
| 8 | Ole Miss | 10-2 | 1.034 | 0.0924 | 28.03 | 21.99 | 18.03 | +10.00 | 9 | 20 | 9 (▼1) |
| 9 | Oregon | 11-2 | 1.026 | 0.0941 | 27.39 | 32.50 | 30.51 | -3.12 | 10 | 2 | 11 (▼2) |
| 10 | Liberty | 13-0 | 1.024 | 0.0946 | 60.00\* | 22.35 | 18.72 | +41.28 | 4 | 17 | 8 (▲2) |
| 11 | Missouri | 10-2 | 0.986 | 0.1032 | 27.11 | 23.25 | 20.81 | +6.31 | 11 | 13 | 10 (▲1) |
| 12 | Oklahoma | 10-2 | 0.943 | 0.1140 | 26.51 | 27.25 | 25.75 | +0.76 | 14 | 6 | 12 (—) |
| 13 | Penn State | 10-2 | 0.852 | 0.1407 | 26.91 | 31.38 | 26.30 | +0.61 | 13 | 4 | 13 (—) |
| 14 | James Madison | 11-1 | 0.744 | 0.1804 | 27.08 | 20.55 | 17.38 | +9.70 | 12 | 23 | 14 (—) |
| 15 | LSU | 9-3 | 0.611 | 0.2447 | 22.90 | 23.98 | 20.67 | +2.23 | 15 | 14 | 15 (—) |
| 16 | Troy | 11-2 | 0.495 | 0.3201 | 22.01 | 20.76 | 17.57 | +4.44 | 16 | 22 | 16 (—) |
| 17 | Louisville | 10-3 | 0.467 | 0.3414 | 20.83 | 18.05 | 18.06 | +2.77 | 19 | 19 | 17 (—) |
| 18 | Iowa | 10-3 | 0.424 | 0.3768 | 20.77 | 12.84 | 7.39 | +13.38 | 20 | 63 | 18 (—) |
| 19 | Tulane | 11-2 | 0.420 | 0.3804 | 20.89 | 13.74 | 10.72 | +10.18 | 18 | 44 | 19 (—) |
| 20 | SMU | 11-2 | 0.419 | 0.3810 | 21.58 | 20.24 | 18.60 | +2.97 | 17 | 18 | 21 (▼1) |
| 21 | Notre Dame | 9-3 | 0.414 | 0.3854 | 20.49 | 26.43 | 23.53 | -3.03 | 21 | 9 | 20 (▲1) |
| 22 | Oklahoma State | 9-4 | 0.413 | 0.3865 | 19.66 | 14.29 | 11.32 | +8.34 | 23 | 41 | 23 (▼1) |
| 23 | NC State | 9-3 | 0.399 | 0.3986 | 19.94 | 16.03 | 12.28 | +7.66 | 22 | 36 | 22 (▲1) |
| 24 | Arizona | 9-3 | 0.363 | 0.4334 | 19.40 | 20.31 | 19.47 | -0.06 | 24 | 16 | 24 (—) |
| 25 | Kansas State | 8-4 | 0.349 | 0.4474 | 18.91 | 24.70 | 21.53 | -2.61 | 26 | 12 | 26 (▼1) |

**Why every undefeated team shows 60.00 and a `*` in the résumé column.** `E[W|q]`
approaches the number of games from below, so an undefeated team's résumé equation
has **no finite root** — the results are consistent with arbitrarily high quality.
That is Bradley-Terry's separation problem (report 02 §2.10) in deterministic
clothes, and the published bracket `q_bounds = [-60, +60]` is the regularization: it
is where an unbounded estimate gets truncated, at a number printed in the config.

**This is exactly why the résumé is no longer the rank key.** +60 is not a function
of the schedule, so it cannot say that one 13-0 was harder to achieve than another,
and — the part that decided it — it is not a function of the *data window* either,
so the retroactive re-ranking of constraint 4 **cannot move an unbeaten team at
all**. From week 11 of 2023 onward it moved none of them by a single place. The
column stays in the table with its flag precisely so that property is visible rather
than argued about, and the order *within* the column still comes from the
margin-aware variant (`[resume].saturation_tiebreak = "margin"`).

See [ADR 0005](../docs/adr/0005-headline-ordering.md) for the decision and its price:
an unbeaten team can now finish behind a one-loss team, and that will need explaining
every year.

## The test this season exists for: Florida State

Florida State finished 13-0, won the ACC, and was left out of a four-team playoff
for the first time in the CFP era. Here is what a transparent system says, on all
three numbers and both surfaces:

| | Poll # | −log10 P | P(W ≥ W_t) | Résumé # | Résumé | Power # | Power | Gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Live** R(N, N) | 3 | 2.406 | 0.0039 | 2 | 60.00\* | 11 | 23.21 | +36.79 |
| **Hindsight** R(N, final) | 3 | 2.301 | 0.0050 | 2 | 60.00\* | 11 | 22.06 | +37.94 |

**The poll and the power rating disagree by 8 places, and that disagreement is the
entire product.** The poll says a reference-quality team would have gone 13-0 against
Florida State's schedule about 0.4 times in 100 — the 3rd-least likely
record in the country. The power rating says its *play* was worth about
22.1 points against an average team, 11th, because it won a lot of close
games. Both are true, and neither is hidden. The committee was answering a third
question — who would we most like to watch play for a title — and it is the only one
of the three that is not written down anywhere.

Note what hindsight does **not** do here: it barely moves Florida State. The
Orange Bowl, in which a Florida State team missing 33 players lost 63-3, is in the
hindsight *Power* fit at weight 0.25 and is **not** in the record window, because that
window is frozen at week N (variant A, report 02 §3.6). A poll that let the January
consequences of the December decision retroactively justify the December decision
would be circular, and this construction cannot do it.

## Georgia, Liberty, and the sentence the poll now has to be able to say

Georgia was 12-1 with its only loss in the SEC championship game and lands at **#7**
live, **#7** in hindsight, on power #5 and #4. Liberty went 13-0 in Conference USA
and lands at **#10** live, **#8** in hindsight, on power #17.

**An undefeated team is ranked below a one-loss team, and that is the decision of
2026-08-12 doing exactly what it was chosen to do.** Under the ordering this project
published until then, Liberty was **#4** and Georgia was **#8** — the `Résumé #` column
above — and it could not have been otherwise: an unbeaten team's wins-based résumé
saturates at the published bracket, so no team with a loss can outrank it, however
soft the schedule. That was a theorem, not a finding.

The poll now makes a different claim, and it is a claim that can be checked:
13-0 against Liberty's schedule is a 9.5-in-100 event for a reference-quality team, and 12-1
against Georgia's is a 2.6-in-100 event. Georgia's was harder. Nothing in that
computation knows what a conference is — no conference identity may enter any design
matrix (constraint 2) — so the ordering is derived from Liberty's actual opponents
rather than assumed from the letters "C-USA". That distinction is the whole point:
assuming it is how you get AP-poll-style conference bias.

The model publishes the head-to-head beside it, so the reader does not have to take
the ranking's word for anything: Georgia by about 8 points on a neutral field,
which Liberty wins roughly 3 times in 10. And the retroactive column moves Liberty
up 2 places between the two surfaces — under the résumé ordering it moved
**zero**, in this week and every week from week 11 onward, because there was nothing
downstream of opponent quality left to move.

Alabama, whom the committee took over Florida State, is poll #4 and power #8
here (live). On the power number the committee and this model broadly agree about
Alabama; on the ranking they do not agree about what a 13-0 season is worth, and the
difference between them is now a probability rather than a preference.

The margin-aware résumé is in the same table and disagrees with both, putting
Liberty at 22.35 against Michigan's 38.72. It is published because report 02 §3.4 says to
publish both, and it is **not** the rank key: the study found it ranks an 8-4 Kansas
State 12th and a 7-5 Texas A&M 23rd, above an 11-1 James Madison and a 13-0 Liberty.

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
Code `6d68fc2` - config `configs/default.toml` sha256 `01c3ab291309b0be...`
