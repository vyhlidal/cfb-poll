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
> **16.16 points**. It is the one free constant in the ordering, so it is
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
| `q_ref` (power_rank_25) | 16.16 points — Tennessee |
| sigma | 15.3 points |
| Compression C / win premium beta_w | 32 / 7 |

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

| # | 90% interval | Team | Rec | −log10 P | P(W ≥ W_t) | Résumé | Margin résumé | Power | ± | Gap | Résumé # | Power # | Hindsight # |
|---:|:---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2–42 | Washington | 13-0 | 3.515 | 0.0003 | 60.00\* | 30.90 | 23.71 | 1.86 | +36.29 | 3 | 9 | 1 (—) |
| 2 | 1–21 | Michigan | 13-0 | 2.587 | 0.0026 | 60.00\* | 39.44 | 31.92 | 1.84 | +28.08 | 1 | 1 | 2 (—) |
| 3 | 2–40 | Florida State | 13-0 | 2.479 | 0.0033 | 60.00\* | 32.62 | 23.35 | 1.82 | +36.65 | 2 | 11 | 3 (—) |
| 4 | 2–38 | Alabama | 12-1 | 2.171 | 0.0067 | 39.07 | 30.15 | 24.23 | 1.82 | +14.84 | 6 | 8 | 4 (—) |
| 5 | 1–34 | Texas | 12-1 | 2.064 | 0.0086 | 38.67 | 32.40 | 25.46 | 1.84 | +13.22 | 7 | 7 | 5 (—) |
| 6 | 1–26 | Ohio State | 11-1 | 1.890 | 0.0129 | 39.45 | 35.03 | 29.17 | 1.90 | +10.27 | 5 | 3 | 6 (—) |
| 7 | 1–33 | Georgia | 12-1 | 1.652 | 0.0223 | 36.10 | 32.77 | 26.03 | 1.82 | +10.08 | 8 | 5 | 7 (—) |
| 8 | 4–60 | Liberty | 13-0 | 1.161 | 0.0691 | 60.00\* | 22.97 | 18.57 | 1.85 | +41.43 | 4 | 18 | 8 (—) |
| 9 | 1–25 | Oregon | 11-2 | 1.066 | 0.0858 | 29.02 | 33.43 | 30.57 | 1.87 | -1.55 | 11 | 2 | 9 (—) |
| 10 | 4–64 | Ole Miss | 10-2 | 1.053 | 0.0885 | 29.49 | 23.11 | 18.28 | 1.88 | +11.21 | 9 | 19 | 10 (—) |
| 11 | 3–54 | Missouri | 10-2 | 1.022 | 0.0951 | 28.70 | 24.23 | 20.95 | 1.88 | +7.74 | 12 | 13 | 11 (—) |
| 12 | 2–40 | Oklahoma | 10-2 | 0.974 | 0.1062 | 28.06 | 28.43 | 25.80 | 1.90 | +2.25 | 14 | 6 | 12 (—) |
| 13 | 1–35 | Penn State | 10-2 | 0.891 | 0.1284 | 28.33 | 32.25 | 26.37 | 1.90 | +1.95 | 13 | 4 | 13 (—) |
| 14 | 6–63 | James Madison | 11-1 | 0.827 | 0.1489 | 29.29 | 22.06 | 17.58 | 1.88 | +11.71 | 10 | 22 | 14 (—) |
| 15 | 3–56 | LSU | 9-3 | 0.629 | 0.2349 | 23.93 | 25.17 | 20.89 | 1.88 | +3.04 | 15 | 14 | 15 (—) |
| 16 | 5–65 | Troy | 11-2 | 0.555 | 0.2785 | 23.57 | 21.02 | 17.27 | 1.81 | +6.30 | 16 | 24 | 16 (—) |
| 17 | 5–61 | Louisville | 10-3 | 0.503 | 0.3137 | 21.98 | 19.05 | 18.27 | 1.82 | +3.71 | 19 | 20 | 17 (—) |
| 18 | 13–91 | Tulane | 11-2 | 0.489 | 0.3242 | 22.60 | 14.79 | 10.91 | 1.81 | +11.69 | 18 | 43 | 18 (—) |
| 19 | 4–61 | SMU | 11-2 | 0.471 | 0.3383 | 22.99 | 21.82 | 18.88 | 1.82 | +4.11 | 17 | 17 | 20 (▼1) |
| 20 | 24–112 | Iowa | 10-3 | 0.470 | 0.3392 | 21.94 | 13.81 | 7.65 | 1.84 | +14.30 | 20 | 60 | 19 (▲1) |
| 21 | 2–45 | Notre Dame | 9-3 | 0.441 | 0.3621 | 21.47 | 27.19 | 23.61 | 1.86 | -2.14 | 21 | 10 | 21 (—) |
| 22 | 13–90 | NC State | 9-3 | 0.431 | 0.3708 | 21.00 | 16.70 | 12.40 | 1.89 | +8.60 | 22 | 36 | 22 (—) |
| 23 | 14–100 | Oklahoma State | 9-4 | 0.429 | 0.3725 | 20.42 | 14.68 | 11.39 | 1.84 | +9.03 | 24 | 41 | 23 (—) |
| 24 | 4–60 | Arizona | 9-3 | 0.400 | 0.3981 | 20.52 | 21.08 | 19.52 | 1.91 | +1.00 | 23 | 16 | 24 (—) |
| 25 | 11–91 | Utah | 8-4 | 0.361 | 0.4357 | 19.71 | 16.18 | 13.41 | 1.91 | +6.30 | 26 | 30 | 25 (—) |

> **The interval is the honest part of this table.** Every rank carries a 90%
> interval from 1,000 parametric draws on the FIXED schedule: each draw redraws
> every game's margin from the fitted model, refits, and re-ranks with the same
> code the poll uses. The median interval width across all 133 ranked
> teams is **77 places**. A poll that prints an integer for a quantity
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
| **Live** R(N, N) | 3 | 2.479 | 0.0033 | 2 | 60.00\* | 11 | 23.35 | +36.65 |
| **Hindsight** R(N, final) | 3 | 2.395 | 0.0040 | 2 | 60.00\* | 11 | 22.19 | +37.81 |

**The poll and the power rating disagree by 8 places, and that disagreement is the
entire product.** The poll says a reference-quality team would have gone 13-0 against
Florida State's schedule about 0.3 times in 100 — the 3rd-least likely
record in the country. The power rating says its *play* was worth about
22.2 points against an average team, 11th, because it won a lot of close
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
and lands at **#8** live, **#8** in hindsight, on power #18.

**An undefeated team is ranked below a one-loss team, and that is the decision of
2026-08-12 doing exactly what it was chosen to do.** Under the ordering this project
published until then, Liberty was **#4** and Georgia was **#8** — the `Résumé #` column
above — and it could not have been otherwise: an unbeaten team's wins-based résumé
saturates at the published bracket, so no team with a loss can outrank it, however
soft the schedule. That was a theorem, not a finding.

The poll now makes a different claim, and it is a claim that can be checked:
13-0 against Liberty's schedule is a 6.9-in-100 event for a reference-quality team, and 12-1
against Georgia's is a 2.2-in-100 event. Georgia's was harder. Nothing in that
computation knows what a conference is — no conference identity may enter any design
matrix (constraint 2) — so the ordering is derived from Liberty's actual opponents
rather than assumed from the letters "C-USA". That distinction is the whole point:
assuming it is how you get AP-poll-style conference bias.

The model publishes the head-to-head beside it, so the reader does not have to take
the ranking's word for anything: Georgia by about 8 points on a neutral field,
which Liberty wins roughly 3 times in 10. And the retroactive column moves Liberty
down 0 places between the two surfaces — under the résumé ordering it moved
**zero**, in this week and every week from week 11 onward, because there was nothing
downstream of opponent quality left to move.

Alabama, whom the committee took over Florida State, is poll #4 and power #8
here (live). On the power number the committee and this model broadly agree about
Alabama; on the ranking they do not agree about what a 13-0 season is worth, and the
difference between them is now a probability rather than a preference.

The margin-aware résumé is in the same table and disagrees with both, putting
Liberty at 22.97 against Michigan's 39.44. It is published because report 02 §3.4 says to
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
Code `d706a06` - config `configs/default.toml` sha256 `bd6a19c152f0222c...`
