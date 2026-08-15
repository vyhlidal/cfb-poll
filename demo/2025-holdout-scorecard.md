# The 2025 holdout scorecard

> **THE GATE DOES NOT CLEAR.** 1 of 5 decidable criteria pass. The gate does not clear on 2025.
>
> This is the one scoring pass 2025 was reserved for. The constants were fitted on 2021-2023, validated once on 2024 and frozen on 2026-08-12, **before this season was ever scored**. It was scored on 2026-08-15T17:08:07Z, once, and the result is published exactly as it came out.

Season 2025 · system `schedule_odds` · config `0.2.0` sha256 `dfc23153e49a101b...` · code `b61a958ea6`

```
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run cfbpoll backtest --config configs/default.toml --systems schedule_odds,resume,l3,l2,l1,colley,srs,elo,walker,winpct --seasons 2025 --out out/holdout-2025 --unlock-holdout
```

Everything below is the published window: fbs_vs_fbs, weeks >= 5, 567 games, strict walk-forward (fit through bucket N-1 of the same season, predict bucket N).

## The gate, criterion by criterion

| criterion | threshold | observed | verdict |
|---|---|---:|:---:|
| Straight-up accuracy at or above the floor | 70.00% | 69.49% | **FAIL** |
| Mean absolute error at or below the ceiling | 12.8 | 12.635 | pass |
| Root mean squared error at or below the ceiling | 15.8 | 15.997 | **FAIL** |
| Worst decile calibration deviation within tolerance | 5.0 pp | 9.52 pp | **FAIL** |
| Retrodictive violations at or below every scored system | `all_scored_systems` | 17.20% | **FAIL** |
| Brier score beats every baseline | — | — | **undecided** |
| Retro-vs-live divergence declines monotonically | — | — | **undecided** |

**1 of 5 decidable criteria pass.** Two more are reported as undecided and are not converted into passes anywhere in this document.

### The one that passes, and it is worth saying plainly

Mean absolute error is **12.635 points** against a ceiling of 12.8. **No tune season ever cleared it**: the same ordering on 2021-2023 reads 13.038. A fully held-out season is where the margin ceiling was met for the first time, and it was met by a model that had never been shown the season. That is the one line in this document that reads better than the tune seasons did.

### The four that fail

- **Straight-up accuracy** 69.49% against a 70.00% floor. Short by 0.51 percentage points, which is 3 games in 567.
- **RMSE** 15.997 against a 15.8 ceiling. MAE clears and RMSE does not, which is what a season with fat tails looks like: the typical miss is inside the target and the large misses are larger than the target allows.
- **Calibration** 9.52 pp worst-decile deviation against a 5.0 pp tolerance. This is the criterion two tuning campaigns have now attacked directly; ADR 0009 took it from 11.28 pp to 7.37 pp on the tune seasons and said in the same breath that it still failed. On a season nobody fitted, it is worse than the tuned figure, not better.
- **Retrodictive violations** 17.20%, which loses to winpct 16.71%. It is the same rival that has beaten this criterion since the fresh-eyes review widened it: win percentage does not lose to anything on a metric that ignores schedule entirely, and the gate was rewritten to stop curating its rivals rather than to be easier to pass.

### The two that stay undecided, and why they are not decided here

**Brier beats every baseline.** The house scores 0.1916. It loses to `elo` (0.1900), `l1` (0.1906), `l2` (0.1874), `srs` (0.1914), ties `l3`, `resume` (which share its prediction source by construction), and beats `colley`, `random_walker`, `winpct`. The home-team floor is excluded, as it is from the violations criterion, because beating a system with no ratings measures nothing.

`[gate].brier_must_beat_all_baselines` has never been wired into `metrics.check_gate` either, and 'baseline' is not defined anywhere in the config: the competition systems and this project's own lower layers are both in the table. Under either reading the house loses, and the losers are named above, so nothing is being hidden by leaving the boolean where the harness leaves it.

**Retro-vs-live divergence declines monotonically.** Over the published window the curve falls from 7.18 places at `2025-regu-w05` to 0.00 at `2025-post-w01`. It is **not strictly monotone**: `2025-regu-w06` → `2025-regu-w07` rises by 0.16 places.

`[gate].retro_vs_live_divergence_monotone` has never been wired into `metrics.check_gate`, which has reported it as undecided since before the constants were frozen. The criterion does not say whether 'monotone' means strictly, or in the published window, or up to some tolerance, and picking one of those readings after seeing this curve would be choosing a rule against a result. The evidence is published in full; the rule is a successor campaign's to pre-register.

## The whole table, 2025, every system scored

| system | n | SU% | MAE | RMSE | Brier | log loss | viol% | churn |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `schedule_odds` | 567 | 69.49% | 12.635 | 15.997 | 0.1916 | 0.5609 | 17.20% | 9.09 |
| `resume` | 567 | 69.49% | 12.635 | 15.997 | 0.1916 | 0.5609 | 17.33% | 8.68 |
| `l3` | 567 | 69.49% | 12.635 | 15.997 | 0.1916 | 0.5609 | 20.92% | 10.32 |
| `l2` | 567 | 70.90% | 12.752 | 16.131 | 0.1874 | 0.5513 | 19.06% | 7.39 |
| `l1` | 567 | 69.49% | 12.671 | 16.010 | 0.1906 | 0.5588 | 22.65% | 7.01 |
| `colley` | 567 | 67.55% | 13.385 | 16.843 | 0.1983 | 0.5800 | 17.70% | 9.11 |
| `srs` | 567 | 70.02% | 12.736 | 15.964 | 0.1914 | 0.5608 | 18.32% | 7.11 |
| `elo` | 567 | 69.66% | 13.184 | 16.573 | 0.1900 | 0.5585 | 20.17% | 9.09 |
| `random_walker` | 567 | 65.26% | 14.049 | 17.723 | 0.2147 | 0.6196 | 18.44% | 11.78 |
| `winpct` | 567 | 67.37% | 13.710 | 17.274 | 0.2058 | 0.5981 | 16.71% | 9.81 |
| `home_team` | 567 | 57.14% | 15.685 | 19.760 | 0.2476 | 0.6917 | n/a | n/a |

`home_team` is the floor and is always in the table whether or not it is asked for. `resume` is the ordering the headline replaced and stays scored forever, so the 2026-08-12 decision remains checkable rather than archived.

## The same table on the tune seasons, for contrast

2021-2023, the seasons the constants were fitted on.

| system | n | SU% | MAE | RMSE | Brier | viol% |
|---|---:|---:|---:|---:|---:|---:|
| `schedule_odds` | 1585 | 68.71% | 13.038 | 16.531 | 0.1971 | 20.19% |
| `resume` | 1585 | 68.71% | 13.038 | 16.531 | 0.1971 | 20.15% |
| `l3` | 1585 | 68.71% | 13.038 | 16.531 | 0.1971 | 22.80% |
| `l2` | 1585 | 69.53% | 13.227 | 16.740 | 0.1975 | 21.86% |
| `l1` | 1585 | 69.15% | 13.165 | 16.684 | 0.1995 | 24.34% |
| `colley` | 1585 | 67.95% | 13.562 | 17.237 | 0.2063 | 19.76% |
| `srs` | 1585 | 69.09% | 13.196 | 16.695 | 0.1995 | 22.11% |
| `elo` | 1585 | 68.77% | 13.559 | 17.098 | 0.2014 | 22.03% |
| `random_walker` | 1585 | 65.05% | 14.015 | 17.984 | 0.2178 | 20.23% |
| `winpct` | 1585 | 66.12% | 13.824 | 17.660 | 0.2118 | 18.31% |
| `home_team` | 1585 | 56.34% | 15.458 | 19.863 | 0.2475 | n/a |

### The house ordering, tune against holdout

| metric | tune 2021-2023 | holdout 2025 | direction |
|---|---:|---:|:---:|
| su_accuracy | 68.71% | 69.49% | better |
| mae | 13.0378 | 12.6346 | better |
| rmse | 16.5312 | 15.9968 | better |
| brier | 0.1971 | 0.1916 | better |
| log_loss | 0.5772 | 0.5609 | better |
| violations | 20.19% | 17.20% | better |

Read this table for its shape and not for a win anywhere: one season is one season, and 567 games is a small number to hang an inference on.

## The divergence curve on 2025

Mean and maximum absolute rank change between R(N, N), the poll as it was published in week N, and R(N, final), the same week re-scored with the season's answers. Every ranked team, every evaluation bucket.

| evaluation bucket | teams | mean \|Δrank\| | max \|Δrank\| |
|---|---:|---:|---:|
| `2025-regu-w01` | 136 | 16.84 | 73 |
| `2025-regu-w02` | 136 | 18.26 | 67 |
| `2025-regu-w03` | 136 | 11.46 | 43 |
| `2025-regu-w04` | 136 | 10.59 | 37 |
| `2025-regu-w05` | 136 | 7.18 | 28 |
| `2025-regu-w06` | 136 | 5.79 | 25 |
| `2025-regu-w07` | 136 | 5.96 | 23 |
| `2025-regu-w08` | 136 | 5.40 | 24 |
| `2025-regu-w09` | 136 | 4.03 | 18 |
| `2025-regu-w10` | 136 | 3.78 | 17 |
| `2025-regu-w11` | 136 | 3.15 | 13 |
| `2025-regu-w12` | 136 | 2.34 | 13 |
| `2025-regu-w13` | 136 | 1.72 | 8 |
| `2025-regu-w14` | 136 | 0.97 | 5 |
| `2025-regu-w15` | 136 | 0.91 | 5 |
| `2025-regu-w16` | 136 | 0.91 | 5 |
| `2025-post-w01` | 136 | 0.00 | 0 |

## Segments, because they measure different things

| segment | n | SU% | MAE | RMSE | Brier |
|---|---:|---:|---:|---:|---:|
| `bowl` | 35 | 54.29% | 12.302 | 14.954 | 0.2470 |
| `cfp` | 11 | 63.64% | 14.354 | 17.056 | 0.2115 |
| `fbs_vs_fbs` | 714 | 68.63% | 13.571 | 17.330 | 0.1981 |
| `fbs_vs_fcs` | 78 | 92.31% | 24.015 | 29.152 | 0.0954 |

The gate reads `fbs_vs_fbs` and nothing else. FBS-vs-FCS is a different question with a 92% straight-up rate and a 24-point mean error, bowls are 35 games played by teams with opt-outs, and the CFP is 11. None of the three is a sample anybody should quote a verdict off.

## What this scorecard licenses, and what it does not

- **It licenses publishing 2025 as an example season.** The number that was protected was the integrity of the tuning, and the tuning is over: nothing here selected a constant, because every constant was frozen three days before this season was read.
- **It does not license a re-tune.** Any constant moved after today has been moved by somebody who has seen this page, and the honest way to do that is a pre-registered campaign on a re-designated split, announced in public, exactly as ADR 0007 required of 2024.
- **It does not make the poll publishable by the project's own standard.** The gate exists to be failed in public. It fails here for the fourth consecutive published evaluation, on the same four criteria, and the site should say so with this page linked.
- **It does not decide the two undecided criteria.** The evidence for both is above. The rule for either is a successor campaign's to pre-register.

Generated by `scripts/make_holdout_scorecard.py` at 2026-08-15T17:30:12+00:00 from `out/holdout-2025/backtest_metrics.json`, which was written by the single scoring pass logged in `.cache/holdout-2025.log`.
