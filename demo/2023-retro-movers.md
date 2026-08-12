# 2023 retroactive movers — who the model was wrong about, in its own words

Report 02 §3.6 calls this view *"the most differentiated thing this project can
ship"*, and it costs nothing extra once the R(N, K) grid exists. Every row is one
team in one week, ranked twice by the same estimator: once with the data available
that week (`R(N, N)`, the poll as published) and once with the whole season's
answers substituted in for opponent quality (`R(N, final)`, hindsight variant A).

**Nothing about the team's own results changes between the two columns.** The
résumé window is frozen at week N; only the *opponents' Power ratings* are
replaced. That is the whole retroactive mechanism, and it is one substitution
(report 02 §3.4).

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
out to be better than they looked at the time.

| Week | Team | Live # | Hindsight # | Move | Résumé live → hindsight | Power live → hindsight |
|---|---|---:|---:|---:|---:|---:|
| `2023-regu-w05` | Mississippi State | 89 | 66 | ▲23 | 0.18 → 7.55 | -4.66 → 2.70 |
| `2023-regu-w05` | Oklahoma State | 92 | 72 | ▲20 | -0.17 → 6.42 | -1.03 → 11.17 |
| `2023-regu-w07` | Tulsa | 68 | 87 | ▼19 | 6.15 → 2.57 | 3.40 → -4.65 |
| `2023-regu-w05` | Miami (OH) | 33 | 52 | ▼19 | 19.59 → 12.93 | 13.67 → 8.90 |
| `2023-regu-w05` | Toledo | 68 | 50 | ▲18 | 6.05 → 13.06 | 4.92 → 11.64 |
| `2023-regu-w06` | Mississippi State | 79 | 61 | ▲18 | 3.45 → 9.03 | -2.17 → 2.70 |
| `2023-regu-w07` | UCF | 72 | 54 | ▲18 | 5.34 → 9.95 | 6.20 → 12.10 |
| `2023-regu-w05` | Arkansas | 78 | 95 | ▼17 | 2.88 → 0.17 | 9.44 → 5.36 |
| `2023-regu-w05` | Temple | 95 | 112 | ▼17 | -0.35 → -6.28 | -6.65 → -9.84 |
| `2023-regu-w05` | South Alabama | 108 | 92 | ▲16 | -5.04 → 0.76 | 4.52 → 9.36 |
| `2023-regu-w06` | UCF | 74 | 59 | ▲15 | 3.98 → 9.95 | 4.93 → 12.10 |
| `2023-regu-w07` | Auburn | 66 | 51 | ▲15 | 6.57 → 11.14 | 5.33 → 9.92 |
| `2023-regu-w06` | Houston | 101 | 86 | ▲15 | -2.17 → 1.38 | 0.42 → 0.74 |
| `2023-regu-w06` | Memphis | 44 | 30 | ▲14 | 13.28 → 20.60 | 7.24 → 10.36 |
| `2023-regu-w05` | UCF | 61 | 47 | ▲14 | 8.29 → 13.57 | 10.49 → 12.10 |

## The divergence curve, which is a falsifiable claim

Report 02 §5.2 lists retro-vs-live divergence as a **stability** metric and says it
must decline in N, or the retroactive product itself is unstable. The later the
week, the less the rest of the season can teach us about it. Here is the curve, for
all 133 ranked teams:

| Evaluation week | Mean \|Δrank\| | Max \|Δrank\| |
|---|---:|---:|
| `2023-regu-w05` | 5.31 | 23 |
| `2023-regu-w06` | 4.38 | 18 |
| `2023-regu-w07` | 3.14 | 19 |
| `2023-regu-w08` | 2.56 | 12 |
| `2023-regu-w09` | 2.23 | 12 |
| `2023-regu-w10` | 1.73 | 8 |
| `2023-regu-w11` | 1.23 | 8 |
| `2023-regu-w12` | 0.80 | 4 |
| `2023-regu-w13` | 0.45 | 2 |
| `2023-regu-w14` | 0.44 | 4 |
| `2023-regu-w15` | 0.41 | 3 |

Mean divergence falls from **5.31 places** at `2023-regu-w05` to **0.41** at `2023-regu-w15`, monotonically.

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

## Reproduce it

```
uv run cfbpoll grid --season 2023 --out out/
```

`out/retro_movers.csv` carries the top 25 movers for every evaluation week;
`out/ratings_grid.parquet` carries the whole triangle, so any other view of it is a
group-by away.

Generated by `scripts/make_demos.py` at 2026-08-12 from the local SportsDataverse MIT archive (2021-2025 `cfb_schedules_*`).
Code `0fc0735` - config `configs/default.toml` sha256 `9cbd0331ca1732a0...`
