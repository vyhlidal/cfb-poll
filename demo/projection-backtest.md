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
| `projection` | 14.3 | 8.33 | 0.638 |
| `regress_only` | 13.3 | 8.81 | 0.632 |
| `naive_carryover` | 13.3 | 8.81 | 0.632 |
| `ap_preseason` | 14.7 | 8.07 | — |

### Season by season

| target | system | top-25 hits | rank MAE (censored) |
|---:|---|---:|---:|
| 2022 | `projection` | 10 | 8.80 |
| 2022 | `regress_only` | 9 | 9.80 |
| 2022 | `naive_carryover` | 9 | 9.80 |
| 2022 | `ap_preseason` | 10 | 9.72 |
| 2023 | `projection` | 18 | 7.44 |
| 2023 | `regress_only` | 18 | 8.08 |
| 2023 | `naive_carryover` | 18 | 8.08 |
| 2023 | `ap_preseason` | 19 | 6.72 |
| 2024 | `projection` | 15 | 8.76 |
| 2024 | `regress_only` | 13 | 8.56 |
| 2024 | `naive_carryover` | 13 | 8.56 |
| 2024 | `ap_preseason` | 15 | 7.76 |

## Predicting the first four weeks

FBS-vs-FBS, weeks 1–4 of the target season. Straight-up accuracy is the honest number here because it is invariant to any positive affine map of the ratings, so it measures the ordering and nothing else. MAE needs a scale and every system gets one from the same in-sample affine fit on exactly these games — a fair comparison between systems, and not an out-of-sample error estimate.

| system | SU accuracy | MAE (points) |
|---|---:|---:|
| `projection` | 0.7134 | 14.112 |
| `regress_only` | 0.7171 | 14.195 |
| `naive_carryover` | 0.7171 | 14.195 |
| `ap_preseason` | 0.6899 | 15.444 |

## The verdict

**We do not beat the AP preseason poll at ranking the season that followed.** The writers hit 14.7 of the final top 25 on average against our 14.3, and their censored rank error is 8.07 against our 8.33. It is close, and it is a loss, and a loss reported by the party that lost is worth more than a win reported by the party that won.

**We beat the naive floor.** Carrying last season's final rating forward unchanged hits 13.3 of the final top 25; the recipe hits 14.3. The offseason terms are worth about 1.0 teams a season, and about 0.48 places of censored rank error. That is a small edge and it is a real one.

**`regress_only` and `naive_carryover` are identical on every rank metric, and that is arithmetic rather than coincidence.** Regressing toward the mean is `a + phi * (x - mean)`, a positive affine map, which cannot reorder anything. The mean-reversion coefficient changes what we predict a team's rating will BE; it cannot change who we think is better than whom. Only the three offseason terms can move a rank — which is precisely why the gap between `projection` and `naive_carryover` is the whole measured value of the offseason data.

**We beat the AP at predicting games, and by more than we lose to them at ranking.** Over the first four weeks the recipe is right on 71.3% of straight-up results against the AP's 69.0%, and its margin MAE is 1.33 points lower. That is not a contradiction of the paragraph above: the AP ranks 25 teams well and expresses no opinion at all about the other 109, and most games in September involve at least one of those 109.

**Three transitions is not many.** Every number here rests on three season pairs, and the honest reading of a 0.3-team difference in top-25 hits over three seasons is that it is inside the noise. The grading loop exists because this table only becomes an argument after several more seasons have been added to it, in public, without the recipe being quietly re-tuned in between.

