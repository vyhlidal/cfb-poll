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
> degeneracy: in the window below, **56 of 97** unbeaten-team rows move, against
> **46 of 97** under the ordering it replaced.
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
| `2023-regu-w05` | Mississippi State | 91 | 66 | ▲25 | 0.008 → 0.036 | -0.49 → 7.06 | -4.39 → 2.87 |
| `2023-regu-w05` | Miami (OH) | 35 | 54 | ▼19 | 0.199 → 0.088 | 21.14 → 14.10 | 13.76 → 8.82 |
| `2023-regu-w06` | Mississippi State | 78 | 61 | ▲17 | 0.025 → 0.048 | 3.55 → 9.00 | -1.89 → 2.87 |
| `2023-regu-w05` | Temple | 95 | 112 | ▼17 | 0.006 → 0.001 | -0.81 → -6.68 | -6.39 → -9.73 |
| `2023-regu-w07` | Tulsa | 68 | 85 | ▼17 | 0.044 → 0.012 | 6.10 → 2.54 | 3.31 → -4.75 |
| `2023-regu-w05` | Texas A&M | 21 | 38 | ▼17 | 0.327 → 0.190 | 24.76 → 19.29 | 18.36 → 17.02 |
| `2023-regu-w05` | Oklahoma State | 87 | 71 | ▲16 | 0.009 → 0.032 | -0.12 → 6.46 | -1.07 → 11.25 |
| `2023-regu-w06` | Memphis | 44 | 29 | ▲15 | 0.153 → 0.248 | 15.45 → 21.85 | 7.64 → 10.52 |
| `2023-regu-w05` | Toledo | 64 | 49 | ▲15 | 0.037 → 0.102 | 8.35 → 14.65 | 5.29 → 11.78 |
| `2023-regu-w05` | UL Monroe | 65 | 80 | ▼15 | 0.036 → 0.019 | 6.79 → 4.06 | -2.37 → -7.98 |
| `2023-regu-w06` | Kansas State | 56 | 42 | ▲14 | 0.077 → 0.160 | 9.40 → 16.39 | 12.54 → 20.83 |
| `2023-regu-w06` | UCF | 73 | 59 | ▲14 | 0.028 → 0.055 | 4.04 → 9.55 | 5.19 → 12.10 |
| `2023-regu-w07` | Auburn | 66 | 52 | ▲14 | 0.047 → 0.070 | 6.41 → 11.02 | 5.54 → 10.01 |
| `2023-regu-w07` | UCF | 73 | 59 | ▲14 | 0.036 → 0.055 | 5.20 → 9.55 | 6.26 → 12.10 |
| `2023-regu-w05` | South Alabama | 106 | 92 | ▲14 | 0.002 → 0.007 | -5.47 → 0.46 | 4.39 → 9.38 |

## The unbeaten teams, which is what changed

Both columns below are read off the same grid, so the difference between them is the
ordering rule and nothing else.

| Unbeaten-team rows that move live → hindsight | Schedule odds | Résumé (the ordering it replaced) |
|---|---:|---:|
| Published window, weeks 5+ | **56** of 97 | 46 of 97 |
| Last five published weeks (`2023-regu-w11`–`2023-regu-w15`) | **7** of 26 | 2 of 26 |

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
| `2023-regu-w05` | 4-0 | 26 | 24 | ▲2 | 0.5288 → 0.4624 |
| `2023-regu-w06` | 5-0 | 18 | 22 | ▼4 | 0.3942 → 0.4202 |
| `2023-regu-w07` | 6-0 | 16 | 14 | ▲2 | 0.2687 → 0.2768 |
| `2023-regu-w08` | 7-0 | 14 | 12 | ▲2 | 0.2160 → 0.2389 |
| `2023-regu-w09` | 8-0 | 8 | 11 | ▼3 | 0.1240 → 0.1586 |
| `2023-regu-w10` | 9-0 | 12 | 11 | ▲1 | 0.1239 → 0.1470 |
| `2023-regu-w11` | 10-0 | 10 | 10 | — | 0.1071 → 0.1232 |
| `2023-regu-w12` | 11-0 | 9 | 10 | ▼1 | 0.0798 → 0.1157 |
| `2023-regu-w13` | 12-0 | 11 | 9 | ▲2 | 0.0903 → 0.0982 |
| `2023-regu-w14` | 13-0 | 8 | 8 | — | 0.0731 → 0.0745 |
| `2023-regu-w15` | 13-0 | 8 | 8 | — | 0.0691 → 0.0745 |

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
| `2023-regu-w05` | 5.64 | 25 |
| `2023-regu-w06` | 4.54 | 17 |
| `2023-regu-w07` | 3.40 | 17 |
| `2023-regu-w08` | 2.50 | 13 |
| `2023-regu-w09` | 2.42 | 14 |
| `2023-regu-w10` | 1.70 | 12 |
| `2023-regu-w11` | 1.22 | 7 |
| `2023-regu-w12` | 0.77 | 5 |
| `2023-regu-w13` | 0.51 | 3 |
| `2023-regu-w14` | 0.50 | 3 |
| `2023-regu-w15` | 0.39 | 2 |

Mean divergence falls from **5.64 places** at `2023-regu-w05` to **0.39** at `2023-regu-w15`, monotonically.

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
Code `d706a06` - config `configs/default.toml` sha256 `bd6a19c152f0222c...`
