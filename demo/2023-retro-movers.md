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
> **31 of 97** under the ordering it replaced.
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
| `2023-regu-w05` | Mississippi State | 90 | 66 | ▲24 | 0.009 → 0.037 | -0.65 → 6.94 | -4.66 → 2.70 |
| `2023-regu-w05` | Miami (OH) | 35 | 54 | ▼19 | 0.208 → 0.091 | 21.01 → 14.13 | 13.67 → 8.90 |
| `2023-regu-w06` | Mississippi State | 79 | 61 | ▲18 | 0.027 → 0.048 | 3.32 → 8.88 | -2.17 → 2.70 |
| `2023-regu-w05` | Temple | 94 | 112 | ▼18 | 0.007 → 0.001 | -0.82 → -6.65 | -6.65 → -9.84 |
| `2023-regu-w07` | Tulsa | 68 | 85 | ▼17 | 0.042 → 0.013 | 6.01 → 2.48 | 3.40 → -4.65 |
| `2023-regu-w05` | Oklahoma State | 87 | 71 | ▲16 | 0.010 → 0.033 | -0.19 → 6.45 | -1.03 → 11.17 |
| `2023-regu-w05` | Texas A&M | 22 | 38 | ▼16 | 0.337 → 0.194 | 24.54 → 19.29 | 17.97 → 17.05 |
| `2023-regu-w06` | Memphis | 44 | 29 | ▲15 | 0.162 → 0.254 | 15.32 → 21.86 | 7.24 → 10.36 |
| `2023-regu-w05` | Toledo | 64 | 49 | ▲15 | 0.040 → 0.103 | 8.25 → 14.59 | 4.92 → 11.64 |
| `2023-regu-w06` | Kansas State | 56 | 42 | ▲14 | 0.082 → 0.165 | 9.20 → 16.42 | 12.37 → 20.99 |
| `2023-regu-w05` | UCF | 61 | 47 | ▲14 | 0.052 → 0.107 | 8.88 → 13.63 | 10.49 → 12.10 |
| `2023-regu-w06` | UCF | 73 | 59 | ▲14 | 0.030 → 0.058 | 3.90 → 9.63 | 4.93 → 12.10 |
| `2023-regu-w07` | Auburn | 66 | 52 | ▲14 | 0.045 → 0.071 | 6.34 → 10.97 | 5.33 → 9.92 |
| `2023-regu-w07` | UCF | 72 | 58 | ▲14 | 0.036 → 0.058 | 5.25 → 9.63 | 6.20 → 12.10 |
| `2023-regu-w05` | Boston College | 95 | 81 | ▲14 | 0.007 → 0.016 | -0.81 → 3.49 | -6.27 → 2.10 |

## The unbeaten teams, which is what changed

Both columns below are read off the same grid, so the difference between them is the
ordering rule and nothing else.

| Unbeaten-team rows that move live → hindsight | Schedule odds | Résumé (the ordering it replaced) |
|---|---:|---:|
| Published window, weeks 5+ | **56** of 97 | 31 of 97 |
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
| `2023-regu-w05` | 4-0 | 26 | 24 | ▲2 | 0.5139 → 0.4583 |
| `2023-regu-w06` | 5-0 | 18 | 22 | ▼4 | 0.3778 → 0.4154 |
| `2023-regu-w07` | 6-0 | 16 | 14 | ▲2 | 0.2748 → 0.2731 |
| `2023-regu-w08` | 7-0 | 14 | 12 | ▲2 | 0.2099 → 0.2348 |
| `2023-regu-w09` | 8-0 | 8 | 11 | ▼3 | 0.1168 → 0.1541 |
| `2023-regu-w10` | 9-0 | 12 | 11 | ▲1 | 0.1171 → 0.1426 |
| `2023-regu-w11` | 10-0 | 10 | 10 | — | 0.1034 → 0.1195 |
| `2023-regu-w12` | 11-0 | 9 | 10 | ▼1 | 0.0795 → 0.1121 |
| `2023-regu-w13` | 12-0 | 10 | 9 | ▲1 | 0.0941 → 0.0949 |
| `2023-regu-w14` | 13-0 | 8 | 8 | — | 0.0702 → 0.0718 |
| `2023-regu-w15` | 13-0 | 8 | 8 | — | 0.0663 → 0.0718 |

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
| `2023-regu-w05` | 5.68 | 24 |
| `2023-regu-w06` | 4.57 | 18 |
| `2023-regu-w07` | 3.35 | 17 |
| `2023-regu-w08` | 2.50 | 13 |
| `2023-regu-w09` | 2.35 | 14 |
| `2023-regu-w10` | 1.70 | 13 |
| `2023-regu-w11` | 1.19 | 6 |
| `2023-regu-w12` | 0.86 | 5 |
| `2023-regu-w13` | 0.44 | 3 |
| `2023-regu-w14` | 0.44 | 2 |
| `2023-regu-w15` | 0.41 | 2 |

Mean divergence falls from **5.68 places** at `2023-regu-w05` to **0.41** at `2023-regu-w15`, monotonically.

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
Code `c3132c9` - config `configs/default.toml` sha256 `ab906806951a114b...`
