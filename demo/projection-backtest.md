# Did the Projection beat the sportswriters?

The headline question this product has to answer, scored honestly and reported whatever it says. Four systems, one target, one code path.

## The four systems

| system | what it is |
|---|---|
| `projection` | the four-term recipe |
| `regress_only` | the same recipe with ONLY the prior-Power term — the control that says whether the offseason data bought anything |
| `naive_carryover` | last season's final Power, unchanged. The floor |
| `ap_preseason` | the AP writers' August top 25. A baseline, never an input |

Every number below is **out of sample**: each season is scored by a recipe fitted on the other two transitions only. Scoring the recipe on the transitions it was fitted on would be reporting a training error.

## Ranking the season that followed

Target: `R(final, final)`, the poll evaluated on the whole season — the most complete statement the poll ever makes about a year.

`top-25 hits` is treatment-free: both systems name 25 teams and we count how many finished there. `rank MAE` censors **every** system's rank at 26, so each is answering the AP's own question, which is the only way to compare a 25-team poll with a 134-team rating without flattering one of them.

| system | top-25 hits /25 | rank MAE (censored) | Spearman, all FBS |
|---|---:|---:|---:|
| `projection` | 12.8 | 8.25 | 0.594 |
| `regress_only` | 13.0 | 8.18 | 0.583 |
| `naive_carryover` | 13.0 | 8.18 | 0.583 |
| `ap_preseason` | 13.8 | 8.35 | — |

### Season by season

| target | system | top-25 hits | rank MAE (censored) |
|---:|---|---:|---:|
| 2022 | `projection` | 10 | 9.20 |
| 2022 | `regress_only` | 9 | 10.04 |
| 2022 | `naive_carryover` | 9 | 10.04 |
| 2022 | `ap_preseason` | 10 | 9.96 |
| 2023 | `projection` | 14 | 7.56 |
| 2023 | `regress_only` | 15 | 7.72 |
| 2023 | `naive_carryover` | 15 | 7.72 |
| 2023 | `ap_preseason` | 17 | 6.44 |
| 2024 | `projection` | 15 | 8.16 |
| 2024 | `regress_only` | 15 | 7.88 |
| 2024 | `naive_carryover` | 15 | 7.88 |
| 2024 | `ap_preseason` | 14 | 8.68 |
| 2025 | `projection` | 12 | 8.08 |
| 2025 | `regress_only` | 13 | 7.08 |
| 2025 | `naive_carryover` | 13 | 7.08 |
| 2025 | `ap_preseason` | 14 | 8.32 |

## Predicting the first four weeks

FBS-vs-FBS, weeks 1–4 of the target season. Straight-up accuracy is the honest number here because it is invariant to any positive affine map of the ratings, so it measures the ordering and nothing else. MAE needs a scale and every system gets one from the same in-sample affine fit on exactly these games — a fair comparison between systems, and not an out-of-sample error estimate.

| system | SU accuracy | MAE (points) |
|---|---:|---:|
| `projection` | 0.7157 | 14.469 |
| `regress_only` | 0.7153 | 14.453 |
| `naive_carryover` | 0.7153 | 14.453 |
| `ap_preseason` | 0.6816 | 15.683 |

## The verdict

**The comparison against the AP splits.** We win one of the two rank metrics and lose the other: top-25 hits 12.8 against 13.8, censored rank error 8.25 against 8.35.

**We do not beat the naive floor.** Carrying last season's final rating forward unchanged hits 13.0 of the final top 25; the recipe hits 12.8. The offseason terms are worth about -0.2 teams a season, and about -0.07 places of censored rank error. Over these three seasons the offseason terms bought nothing measurable, and that is the result, reported by the party it is worst for.

**`regress_only` and `naive_carryover` are identical on every rank metric, and that is arithmetic rather than coincidence.** Regressing toward the mean is `a + phi * (x - mean)`, a positive affine map, which cannot reorder anything. The mean-reversion coefficient changes what we predict a team's rating will BE; it cannot change who we think is better than whom. Only the three offseason terms can move a rank — which is precisely why the gap between `projection` and `naive_carryover` is the whole measured value of the offseason data.

**We beat the AP at predicting games, and by more than we lose to them at ranking.** Over the first four weeks the recipe is right on 71.6% of straight-up results against the AP's 68.2%, and its margin MAE is 1.21 points lower. That is not a contradiction of the paragraph above: the AP ranks 25 teams well and expresses no opinion at all about the other 109, and most games in September involve at least one of those 109.

**Three transitions is not many.** Every number here rests on three season pairs, and the honest reading of a 1.0-team difference in top-25 hits over three seasons is that it is inside the noise. The grading loop exists because this table only becomes an argument after several more seasons have been added to it, in public, without the recipe being quietly re-tuned in between.

