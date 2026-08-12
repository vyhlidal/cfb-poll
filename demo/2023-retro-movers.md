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
> degeneracy: in the window below, **57 of 97** unbeaten-team rows move, against
> **35 of 97** under the ordering it replaced.
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
| `2023-regu-w05` | Mississippi State | 87 | 66 | ▲21 | 0.006 → 0.034 | 0.18 → 7.55 | -4.66 → 2.70 |
| `2023-regu-w05` | Oklahoma State | 90 | 70 | ▲20 | 0.005 → 0.025 | -0.17 → 6.42 | -1.03 → 11.17 |
| `2023-regu-w05` | Miami (OH) | 33 | 53 | ▼20 | 0.177 → 0.070 | 19.59 → 12.93 | 13.67 → 8.90 |
| `2023-regu-w06` | Kansas State | 56 | 37 | ▲19 | 0.063 → 0.155 | 8.58 → 16.04 | 12.37 → 20.99 |
| `2023-regu-w05` | Temple | 95 | 114 | ▼19 | 0.004 → 0.000 | -0.35 → -6.28 | -6.65 → -9.84 |
| `2023-regu-w07` | Tulsa | 67 | 86 | ▼19 | 0.034 → 0.009 | 6.15 → 2.57 | 3.40 → -4.65 |
| `2023-regu-w05` | Toledo | 69 | 51 | ▲18 | 0.019 → 0.077 | 6.05 → 13.06 | 4.92 → 11.64 |
| `2023-regu-w07` | UCF | 70 | 52 | ▲18 | 0.027 → 0.054 | 5.34 → 9.95 | 6.20 → 12.10 |
| `2023-regu-w06` | Mississippi State | 77 | 60 | ▲17 | 0.019 → 0.042 | 3.45 → 9.03 | -2.17 → 2.70 |
| `2023-regu-w05` | UL Monroe | 63 | 80 | ▼17 | 0.028 → 0.014 | 6.55 → 3.99 | -2.34 → -7.83 |
| `2023-regu-w05` | Texas A&M | 21 | 38 | ▼17 | 0.297 → 0.164 | 22.67 → 17.87 | 17.97 → 17.05 |
| `2023-regu-w06` | Memphis | 45 | 29 | ▲16 | 0.121 → 0.229 | 13.28 → 20.60 | 7.24 → 10.36 |
| `2023-regu-w06` | UCF | 73 | 57 | ▲16 | 0.022 → 0.054 | 3.98 → 9.95 | 4.93 → 12.10 |
| `2023-regu-w05` | South Alabama | 109 | 93 | ▲16 | 0.001 → 0.005 | -5.04 → 0.76 | 4.52 → 9.36 |
| `2023-regu-w05` | Air Force | 35 | 21 | ▲14 | 0.168 → 0.357 | 60.00 → 60.00 | 19.13 → 10.83 |

## The unbeaten teams, which is what changed

Both columns below are read off the same grid, so the difference between them is the
ordering rule and nothing else.

| Unbeaten-team rows that move live → hindsight | Schedule odds | Résumé (the ordering it replaced) |
|---|---:|---:|
| Published window, weeks 5+ | **57** of 97 | 35 of 97 |
| Last five published weeks (`2023-regu-w11`–`2023-regu-w15`) | **7** of 26 | 0 of 26 |

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
| `2023-regu-w05` | 4-0 | 27 | 26 | ▲1 | 0.6142 → 0.5230 |
| `2023-regu-w06` | 5-0 | 21 | 22 | ▼1 | 0.4723 → 0.4875 |
| `2023-regu-w07` | 6-0 | 18 | 16 | ▲2 | 0.3560 → 0.3299 |
| `2023-regu-w08` | 7-0 | 15 | 14 | ▲1 | 0.2824 → 0.2932 |
| `2023-regu-w09` | 8-0 | 10 | 11 | ▼1 | 0.1564 → 0.1981 |
| `2023-regu-w10` | 9-0 | 12 | 12 | — | 0.1570 → 0.1878 |
| `2023-regu-w11` | 10-0 | 11 | 11 | — | 0.1469 → 0.1630 |
| `2023-regu-w12` | 11-0 | 12 | 12 | — | 0.1113 → 0.1563 |
| `2023-regu-w13` | 12-0 | 12 | 11 | ▲1 | 0.1317 → 0.1370 |
| `2023-regu-w14` | 13-0 | 10 | 8 | ▲2 | 0.1004 → 0.1074 |
| `2023-regu-w15` | 13-0 | 10 | 8 | ▲2 | 0.0946 → 0.1074 |

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
| `2023-regu-w05` | 6.15 | 21 |
| `2023-regu-w06` | 4.96 | 19 |
| `2023-regu-w07` | 3.73 | 19 |
| `2023-regu-w08` | 2.80 | 14 |
| `2023-regu-w09` | 2.63 | 12 |
| `2023-regu-w10` | 1.71 | 9 |
| `2023-regu-w11` | 1.22 | 10 |
| `2023-regu-w12` | 0.96 | 5 |
| `2023-regu-w13` | 0.54 | 2 |
| `2023-regu-w14` | 0.57 | 3 |
| `2023-regu-w15` | 0.36 | 2 |

Mean divergence falls from **6.15 places** at `2023-regu-w05` to **0.36** at `2023-regu-w15`, and the decline is monotone except at the very end of the season, where the final data window adds the postseason and moves a handful of teams that the previous window had already settled.

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

Generated by `scripts/make_demos.py` at 2026-08-12 from the local SportsDataverse MIT archive (2021-2025 `cfb_schedules_*`).
Code `f1c76c4` - config `configs/default.toml` sha256 `0f7999e5d90bcb94...`
