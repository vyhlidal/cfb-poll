# 2023 retroactive movers — who the model was wrong about, in its own words

Report 02 §3.6 calls this view *"the most differentiated thing this project can
ship"*, and it costs nothing extra once the R(N, K) grid exists. Every row is one
team in one week, ranked twice by the same estimator: once with the data available
that week (`R(N, N)`, the poll as published) and once with the whole season's
answers substituted in for opponent quality (`R(N, final)`, hindsight variant A).

**Nothing about the team's own results changes between the two columns.** The
record window is frozen at week N; only the *opponents' Power ratings* are
replaced. That is the whole retroactive mechanism, and it is one substitution
(report 02 §3.4).

> **This page is the reason the headline ordering changed on 2026-08-12.** Until
> then the poll was ordered by the wins-based résumé, under which an undefeated
> team's rating is the published bracket `+60`. `+60` is not a function of the
> schedule, so it is not a function of the data window either — which means the one
> substitution above had **nothing left to move** for an unbeaten team. Every
> undefeated team's row on this page read `—`, forever, and from week 11 onward that
> was true of every unbeaten team in the country. A tail probability has no such
> degeneracy: in the window below, **60 of 97** unbeaten-team rows move, against
> **43 of 97** under the ordering it replaced.
> See [ADR 0005](../docs/adr/0005-headline-ordering.md).

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

## Biggest moves, weeks 5+ (the published window)

▲ means the live poll **under**-rated the team: the opponents it had beaten turned
out to be better than they looked at the time. `−log10 P` is the rank key; the
résumé is carried beside it as the comparison column.

| Week | Team | Live # | Hindsight # | Move | −log10 P live → hindsight | Résumé live → hindsight | Power live → hindsight |
|---|---|---:|---:|---:|---:|---:|---:|
| `2023-regu-w05` | Toledo | 67 | 46 | ▲21 | 0.027 → 0.129 | 7.29 → 16.22 | 5.29 → 11.78 |
| `2023-regu-w05` | Mississippi State | 90 | 69 | ▲21 | 0.007 → 0.039 | -0.09 → 6.48 | -4.39 → 2.87 |
| `2023-regu-w05` | Oklahoma State | 89 | 70 | ▲19 | 0.007 → 0.039 | -0.11 → 6.47 | -1.07 → 11.25 |
| `2023-regu-w05` | Miami (OH) | 35 | 53 | ▼18 | 0.184 → 0.109 | 20.42 → 15.39 | 13.76 → 8.82 |
| `2023-regu-w05` | Temple | 95 | 112 | ▼17 | 0.005 → 0.002 | -0.58 → -7.09 | -6.39 → -9.73 |
| `2023-regu-w07` | Tulsa | 68 | 85 | ▼17 | 0.040 → 0.016 | 6.16 → 2.46 | 3.31 → -4.75 |
| `2023-regu-w05` | Texas A&M | 21 | 38 | ▼17 | 0.307 → 0.218 | 23.84 → 20.77 | 18.36 → 17.02 |
| `2023-regu-w06` | UCF | 75 | 59 | ▲16 | 0.021 → 0.060 | 4.11 → 9.32 | 5.19 → 12.10 |
| `2023-regu-w06` | South Alabama | 96 | 80 | ▲16 | 0.005 → 0.019 | -0.34 → 3.75 | 9.34 → 9.38 |
| `2023-regu-w06` | Mississippi State | 77 | 62 | ▲15 | 0.019 → 0.054 | 3.67 → 8.89 | -1.89 → 2.87 |
| `2023-regu-w05` | South Alabama | 107 | 92 | ▲15 | 0.001 → 0.010 | -5.15 → 0.03 | 4.39 → 9.38 |
| `2023-regu-w05` | San Diego State | 83 | 98 | ▼15 | 0.008 → 0.008 | 1.54 → -0.63 | -7.28 → -3.20 |
| `2023-regu-w05` | Arkansas | 78 | 93 | ▼15 | 0.012 → 0.010 | 2.73 → -0.60 | 9.39 → 5.28 |
| `2023-regu-w05` | UL Monroe | 63 | 78 | ▼15 | 0.031 → 0.025 | 6.76 → 4.11 | -2.37 → -7.98 |
| `2023-regu-w05` | Clemson | 46 | 61 | ▼15 | 0.100 → 0.079 | 13.34 → 11.36 | 16.05 → 17.11 |

## The unbeaten teams, which is what changed

Both columns below are read off the same grid, so the difference between them is the
ordering rule and nothing else.

| Unbeaten-team rows that move live → hindsight | Schedule odds | Résumé (the ordering it replaced) |
|---|---:|---:|
| Published window, weeks 5+ | **60** of 97 | 43 of 97 |
| Last five published weeks (`2023-regu-w11`–`2023-regu-w15`) | **11** of 26 | 2 of 26 |

The second row is the finding. Late in a season the résumé ordering has nothing left
to say about an undefeated team — every one of them is on the bracket, the bracket
does not depend on the data window, and the retroactive substitution has no surface
to act on. The teams whose ranking is argued about hardest are exactly the teams it
went silent about.

Liberty, week by week, is the case the study was built around. It was 13-0 in
Conference USA, and the question was whether a poll could revise its September
*without being told* that Conference USA is Conference USA:

| Week | Rec | Live # | Hindsight # | Move | P(W ≥ W_t) live → hindsight |
|---|:---:|---:|---:|---:|---:|
| `2023-regu-w05` | 4-0 | 27 | 23 | ▲4 | 0.5753 → 0.4092 |
| `2023-regu-w06` | 5-0 | 22 | 18 | ▲4 | 0.4761 → 0.3616 |
| `2023-regu-w07` | 6-0 | 16 | 14 | ▲2 | 0.3003 → 0.2325 |
| `2023-regu-w08` | 7-0 | 14 | 12 | ▲2 | 0.2213 → 0.1945 |
| `2023-regu-w09` | 8-0 | 8 | 10 | ▼2 | 0.1297 → 0.1259 |
| `2023-regu-w10` | 9-0 | 12 | 10 | ▲2 | 0.1426 → 0.1138 |
| `2023-regu-w11` | 10-0 | 10 | 9 | ▲1 | 0.1196 → 0.0923 |
| `2023-regu-w12` | 11-0 | 11 | 10 | ▲1 | 0.0934 → 0.0847 |
| `2023-regu-w13` | 12-0 | 11 | 9 | ▲2 | 0.1042 → 0.0696 |
| `2023-regu-w14` | 13-0 | 10 | 8 | ▲2 | 0.1047 → 0.0512 |
| `2023-regu-w15` | 13-0 | 10 | 8 | ▲2 | 0.0987 → 0.0512 |

Note the direction in the last two weeks. The hindsight probability is **higher**
than the live one, meaning end-of-season Power judged Liberty's schedule slightly
*easier* than the live ratings did — and Liberty still rises, because the teams
around it were re-judged more harshly still. That is the retroactive product doing
exactly what it was built to do, and it is only visible on an ordering that has
somewhere to move.

## The divergence curve, which is a falsifiable claim

Report 02 §5.2 lists retro-vs-live divergence as a **stability** metric and says it
must decline in N, or the retroactive product itself is unstable. The later the
week, the less the rest of the season can teach us about it. Here is the curve, for
all 133 ranked teams:

| Evaluation week | Mean \|Δrank\| | Max \|Δrank\| |
|---|---:|---:|
| `2023-regu-w05` | 5.83 | 21 |
| `2023-regu-w06` | 4.78 | 16 |
| `2023-regu-w07` | 3.43 | 17 |
| `2023-regu-w08` | 2.38 | 13 |
| `2023-regu-w09` | 2.27 | 12 |
| `2023-regu-w10` | 1.83 | 9 |
| `2023-regu-w11` | 1.34 | 8 |
| `2023-regu-w12` | 1.41 | 6 |
| `2023-regu-w13` | 1.44 | 7 |
| `2023-regu-w14` | 1.92 | 7 |
| `2023-regu-w15` | 1.71 | 6 |

Mean divergence falls from **5.83 places** at `2023-regu-w05` to **1.71** at `2023-regu-w15`, and the decline is monotone except at the very end of the season, where the final data window adds the postseason and moves a handful of teams that the previous window had already settled.

That shape is the thing to check, not the individual rows. A retroactive poll whose
week-12 ranking still moved 6 places in hindsight would be telling you its week-12
ranking was never worth reading.

## What the big movers have in common

They are almost all outside the top 25, and that is the honest finding. In the
published window the top of the table barely moves: by week 10 the mean move across
the whole FBS is under two places, and the teams whose opponents' quality is still
genuinely unknown are the ones with thin, unconnected schedules. The retroactive
product is most valuable exactly where the poll is least confident, which is the
opposite of how retroactive re-ranking usually gets sold.

The change of 2026-08-12 does not alter that finding and was not expected to. What
it altered is a different thing: that a specific, identifiable class of team — the
undefeated ones, who are exactly the teams the ranking gets argued about — was
excluded from this page **by construction** rather than by having a settled
ranking. Study §5a shows the league-wide convergence curves for the three candidate
orderings are within noise of each other; §5b shows the unbeaten teams were not.

## Reproduce it

```
uv run cfbpoll grid --season 2023 --out out/
```

`out/retro_movers.csv` carries the top 25 movers for every evaluation week;
`out/ratings_grid.parquet` carries the whole triangle, so any other view of it is a
group-by away.

Generated by `scripts/make_demos.py` at 2026-08-13 from the local SportsDataverse MIT archive (2021-2025 `cfb_schedules_*`), plus the private CFBD archive for the 2021-2022 postseason (80 games).
Code `efdd6ab` - config `configs/default.toml` sha256 `c836cec36f7d49d3...`
