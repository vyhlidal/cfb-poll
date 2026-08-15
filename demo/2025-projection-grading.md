# We projected 2025. Here is what the season said.

> The recipe below is the one this project publishes. It was fitted on 2021→2022, 2022→2023, 2023→2024 and **2024→2025 is not among those transitions**, so nothing here was fitted on the season it is being graded against. Nothing was excluded to make that true either: that transition has never been in the list.

Recipe `projection-1.0.0` · source season 2024 · config sha256 `68896b5aab42351f...` · code `46572be4fd`

The coefficients below are the ones on the published 2026 card, to 1e-9. Nothing was refitted, dropped or excluded to make 2025 out of sample: 2024->2025 was never in design_transitions.

## The projection against the season, at the end of it

`Projected` is the guess. `Live` is the poll as it was published in the final week. `Hindsight` is that same week re-scored with the whole season's answers, which is the column that says what a team turned out to be. A negative delta means we had them too high.

**At the final bucket the two surfaces are the same ranking, and that is arithmetic rather than agreement.** R(N, N) and R(N, final) coincide when N *is* final, because there is no rest-of-season left to substitute in. The two columns separate earlier in the year, and the week-by-week table below is where that separation is worth reading.

| Projected | Team | Live | Hindsight | vs live | vs hindsight | Power projected → actual |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Ohio State | 5 | 5 | -4 | -4 | 34.44 → 29.45 |
| 2 | Notre Dame | 12 | 12 | -10 | -10 | 33.24 → 28.57 |
| 3 | Oregon | 2 | 2 | +1 | +1 | 31.56 → 28.16 |
| 4 | Penn State | 48 | 48 | -44 | -44 | 31.41 → 17.14 |
| 5 | Texas | 11 | 11 | -6 | -6 | 31.01 → 17.6 |
| 6 | Alabama | 10 | 10 | -4 | -4 | 30.27 → 20.33 |
| 7 | Georgia | 7 | 7 | +0 | +0 | 29.33 → 22.22 |
| 8 | South Carolina | 81 | 81 | -73 | -73 | 29.12 → 8.48 |
| 9 | Iowa State | 35 | 35 | -26 | -26 | 28.94 → 12.29 |
| 10 | Arizona State | 36 | 36 | -26 | -26 | 28.15 → 11.79 |
| 11 | BYU | 4 | 4 | +7 | +7 | 27.41 → 19.63 |
| 12 | Kansas State | 56 | 56 | -44 | -44 | 27.41 → 12.4 |
| 13 | SMU | 31 | 31 | -18 | -18 | 27.26 → 15.47 |
| 14 | Indiana | 1 | 1 | +13 | +13 | 27.23 → 34.43 |
| 15 | Baylor | 75 | 75 | -60 | -60 | 27.18 → 4.65 |
| 16 | Clemson | 64 | 64 | -48 | -48 | 26.95 → 10.57 |
| 17 | Miami | 3 | 3 | +14 | +14 | 26.19 → 27.23 |
| 18 | Texas A&M | 8 | 8 | +10 | +10 | 26.11 → 22.02 |
| 19 | LSU | 42 | 42 | -23 | -23 | 26.04 → 12.53 |
| 20 | Boise State | 45 | 45 | -25 | -25 | 26.03 → 11.67 |
| 21 | Colorado | 102 | 102 | -81 | -81 | 25.78 → 1.25 |
| 22 | Louisville | 30 | 30 | -8 | -8 | 25.74 → 15.57 |
| 23 | Ole Miss | 6 | 6 | +17 | +17 | 25.73 → 19.76 |
| 24 | Illinois | 21 | 21 | +3 | +3 | 25.26 → 13.47 |
| 25 | Iowa | 20 | 20 | +5 | +5 | 25.13 → 17.73 |

## What was wrong, in the projection's own words

- The projection had Colorado at #21. The poll now has them at #102. The projection over-rated them by 81 places, and they are -24.5 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +12.50 points of Power.
- The projection had North Texas at #92. The poll now has them at #17. The projection under-rated them by 75 places, and they are +9.8 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -4.63 points of Power.
- The projection had South Carolina at #8. The poll now has them at #81. The projection over-rated them by 73 places, and they are -20.6 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +12.47 points of Power.
- The projection had Baylor at #15. The poll now has them at #75. The projection over-rated them by 60 places, and they are -22.5 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +10.12 points of Power.
- The projection had Virginia at #77. The poll now has them at #22. The projection under-rated them by 55 places, and they are +3.7 points of Power off the projected figure. The projection's largest term pointing the wrong way was returning production, worth -1.39 points of Power.

## Convergence, week by week

Mean absolute rank error of the frozen projection against each surface. The `hindsight` column is the fairer early reading: in week 5 the live poll is itself provisional, and grading an August guess against a provisional answer double-counts the noise.

| week | published | vs live | vs hindsight | vs hindsight, projected top 25 | top-25 hits |
|---|:---:|---:|---:|---:|---:|
| `2025-regu-w01` | no | 43.78 | 38.94 | 49.36 | 7 |
| `2025-regu-w02` | no | 38.25 | 34.90 | 41.40 | 11 |
| `2025-regu-w03` | no | 36.88 | 33.72 | 38.52 | 11 |
| `2025-regu-w04` | no | 34.07 | 32.18 | 34.08 | 12 |
| `2025-regu-w05` | yes | 32.56 | 30.93 | 31.00 | 13 |
| `2025-regu-w06` | yes | 31.63 | 29.71 | 30.24 | 13 |
| `2025-regu-w07` | yes | 29.91 | 28.37 | 26.28 | 11 |
| `2025-regu-w08` | yes | 29.18 | 27.63 | 24.44 | 14 |
| `2025-regu-w09` | yes | 28.75 | 27.91 | 25.60 | 13 |
| `2025-regu-w10` | yes | 28.88 | 27.44 | 25.12 | 13 |
| `2025-regu-w11` | yes | 28.01 | 26.96 | 23.96 | 13 |
| `2025-regu-w12` | yes | 27.79 | 27.19 | 24.12 | 13 |
| `2025-regu-w13` | yes | 27.90 | 27.18 | 23.24 | 12 |
| `2025-regu-w14` | yes | 26.59 | 26.28 | 22.40 | 12 |
| `2025-regu-w15` | yes | 26.46 | 26.25 | 22.32 | 12 |
| `2025-regu-w16` | yes | 26.57 | 26.32 | 22.32 | 12 |
| `2025-post-w01` | yes | 26.13 | 26.13 | 22.80 | 13 |

## Which term was carrying the error, across the league

Regress every team's projection error on each term's contribution. A negative coefficient means teams we credited on that term systematically underperformed, which is to say we over-credited it this season.

```json
{
 "prior_power": {
  "coefficient": -0.344457263344027,
  "standard_error": 0.07815658790920799,
  "z": -4.407270999908184,
  "n_teams_moved": 136,
  "implied_multiplier": 0.655542736655973,
  "verdict": "TOO STRONG",
  "sentence": "The model weighted last season's rating TOO STRONG. For every point of Power it moved a team's projection, that team finished 0.34 points the other way (4.4 standard errors over 136 teams). This season wanted about 0.66x the model's coefficient."
 },
 "returning_production": {
  "coefficient": -0.8087077338721921,
  "standard_error": 0.4344869580478018,
  "z": -1.8612934609264358,
  "n_teams_moved": 134,
  "implied_multiplier": 0.19129226612780792,
  "verdict": "priced about right",
  "sentence": "The model priced returning production about right: over the 134 teams it moved, the data cannot tell its effect from zero (1.9 standard errors)."
 },
 "coaching_change": {
  "coefficient": 0.466829698126052,
  "standard_error": 0.7156498747205599,
  "z": 0.6523157686687715,
  "n_teams_moved": 37,
  "implied_multiplier": 1.466829698126052,
  "verdict": "priced about right",
  "sentence": "The model priced the coaching-change penalty about right: over the 37 teams it moved, the data cannot tell its effect from zero (0.7 standard errors)."
 },
 "net_portal": {
  "coefficient": 0.13590682225032263,
  "standard_error": 1.6037498420219451,
  "z": 0.08474315550296586,
  "n_teams_moved": 136,
  "implied_multiplier": 1.1359068222503226,
  "verdict": "priced about right",
  "sentence": "The model priced net portal flow about right: over the 136 teams it moved, the data cannot tell its effect from zero (0.1 standard errors)."
 }
}
```

The league-wide attribution is a regression of projection error on each term's contribution, over about 134 teams and four correlated terms. One season is one data point about the recipe. It is suggestive and it is not a verdict.

Generated by `scripts/make_projection_2025.py` at 2026-08-15T19:32:24+00:00. The machine-readable form is `2025/projection-grading.json` in the site's data tree.
