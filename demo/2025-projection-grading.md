# We projected 2025. Here is what the season said.

> The recipe below is the one this project publishes. It was fitted on 2021→2022, 2022→2023, 2023→2024, 2024→2025 and **2024→2025 is not among those transitions**, so nothing here was fitted on the season it is being graded against. Nothing was excluded to make that true either: that transition has never been in the list.

Recipe `projection-3.0.0` · source season 2024 · config sha256 `37d52aa3d0ccca4a...` · code `e648927a76`

The coefficients below were fitted without 2025 in any response, so this projection is an out-of-sample application of the model to a season it never saw. They are NOT the coefficients on the 2026 card: that recipe has one more completed season to learn from, which is the point of dropping the freeze, and each vintage keeps the numbers it ran under.

**Which Power.** retro.season_power(...)[final]: the WALK-FORWARD Power at the season's last bucket, whose blend weights are estimated out of sample week by week. This is the surface the poll publishes, the surface the gate uses, and the surface the grading page scores against. It is the projection's input, its response and its grading target, and they are the same object.

## The one row this page is most often asked about

> The projection had South Carolina 14th and they finished 81st. Of the 30 teams the projection put highest, that is the furthest any of them fell, and it is worth being precise about why, because the easy explanation is wrong. The model does not read the press, and here that cuts against the easy story rather than for it: the AP had South Carolina 13th in its own preseason top 25, so the writers made the same mistake from a completely different direction. What the model read was South Carolina's own 2024, where they were the 16th best team in the country by its power rating, and that one number was worth 5.9 points to their projection. The model also read what left the roster. South Carolina returned 63.4% of its offensive usage, the 105th lowest figure among the 134 teams with a row, and 88% of its passing usage, which is what a quarterback room turning over looks like in the data. That cost them 1.4 points, the portal took another 0.0, and between them they moved South Carolina from 16th to 14th. The problem is the ratio. Last season's rating can swing a team 28 points and returning production can swing one 5, so a team that arrives 16th cannot be argued down to 81st by the offseason. The grading loop is what settles what to do about that, and this season it settled it the dull way: across the 136 teams the poll ranked, all four terms come back priced about right, the furthest of them 1.4 standard errors from the published value. No coefficient here was wrong. The ratio is a property of the design, and 2025 is the first season that made it cost something. What I am not going to do is turn the returning-production dial up until South Carolina looks right. I checked: every setting that moves South Carolina down also moves Indiana down, and Indiana returned even less than South Carolina did and went 16-0. Penn State and Baylor returned more production than almost anyone in the country, 4th and 3rd of 134, and finished 48th and 75th. In 2025 returning production told you almost nothing, and the fix for South Carolina is not a bigger version of a term that did not work.

## The projection against the season, at the end of it

`Projected` is the projection. `Live` is the poll as it was published in the final week. `Hindsight` is that same week re-scored with the whole season's answers, which is the column that says what a team turned out to be. A negative delta means we had them too high. Both Power columns are on the definition named above, which is the one the poll publishes.

**At the final bucket the two surfaces are the same ranking, and that is arithmetic rather than agreement.** R(N, N) and R(N, final) coincide when N *is* final, because there is no rest-of-season left to substitute in. The two columns separate earlier in the year, and the week-by-week table below is where that separation is worth reading.

| Projected | Team | Live | Hindsight | vs live | vs hindsight | Power projected → actual |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Ohio State | 5 | 5 | -4 | -4 | 18.59 → 29.45 |
| 2 | Penn State | 48 | 48 | -46 | -46 | 18.52 → 17.14 |
| 3 | Notre Dame | 12 | 12 | -9 | -9 | 18.31 → 28.57 |
| 4 | Texas | 11 | 11 | -7 | -7 | 16.61 → 17.6 |
| 5 | Oregon | 2 | 2 | +3 | +3 | 16.02 → 28.16 |
| 6 | Clemson | 64 | 64 | -58 | -58 | 15.58 → 10.57 |
| 7 | Alabama | 10 | 10 | -3 | -3 | 15.17 → 20.33 |
| 8 | SMU | 31 | 31 | -23 | -23 | 14.79 → 15.47 |
| 9 | Georgia | 7 | 7 | +2 | +2 | 14.56 → 22.22 |
| 10 | Kansas State | 56 | 56 | -46 | -46 | 14.5 → 12.4 |
| 11 | Boise State | 45 | 45 | -34 | -34 | 13.73 → 11.67 |
| 12 | LSU | 42 | 42 | -30 | -30 | 13.6 → 12.53 |
| 13 | Texas A&M | 8 | 8 | +5 | +5 | 13.55 → 22.02 |
| 14 | South Carolina | 81 | 81 | -67 | -67 | 13.5 → 8.48 |
| 15 | Ole Miss | 6 | 6 | +9 | +9 | 13.27 → 19.76 |
| 16 | Louisville | 30 | 30 | -14 | -14 | 13.04 → 15.57 |
| 17 | Tennessee | 41 | 41 | -24 | -24 | 12.63 → 17.08 |
| 18 | Miami | 3 | 3 | +15 | +15 | 12.43 → 27.23 |
| 19 | Iowa State | 35 | 35 | -16 | -16 | 12.4 → 12.29 |
| 20 | Arizona State | 36 | 36 | -16 | -16 | 12.36 → 11.79 |
| 21 | Navy | 15 | 15 | +6 | +6 | 12.22 → 11.67 |
| 22 | Georgia Tech | 34 | 34 | -12 | -12 | 11.77 → 11.85 |
| 23 | Kansas | 80 | 80 | -57 | -57 | 11.6 → 8.08 |
| 24 | James Madison | 16 | 16 | +8 | +8 | 11.34 → 18.05 |
| 25 | Oklahoma | 13 | 13 | +12 | +12 | 11.08 → 19.62 |

## What was wrong, in the projection's own words

- The projection had Virginia at #106. The poll now has them at #22. The projection under-rated them by 84 places, and they are +14.2 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -2.74 points of Power.
- The projection had North Texas at #100. The poll now has them at #17. The projection under-rated them by 83 places, and they are +17.1 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -2.89 points of Power.
- The projection had South Carolina at #14. The poll now has them at #81. The projection over-rated them by 67 places, and they are -5.0 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +5.90 points of Power.
- The projection had Clemson at #6. The poll now has them at #64. The projection over-rated them by 58 places, and they are -5.0 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +7.31 points of Power.
- The projection had Kansas at #23. The poll now has them at #80. The projection over-rated them by 57 places, and they are -3.5 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +4.94 points of Power.

## Convergence, week by week

Mean absolute rank error of the frozen projection against each surface. The `hindsight` column is the fairer early reading: in week 5 the live poll is itself provisional, and grading an August projection against a provisional answer double-counts the noise.

| week | published | vs live | vs hindsight | vs hindsight, projected top 25 | top-25 hits |
|---|:---:|---:|---:|---:|---:|
| `2025-regu-w01` | no | 42.81 | 37.72 | 41.16 | 8 |
| `2025-regu-w02` | no | 38.04 | 34.40 | 40.12 | 10 |
| `2025-regu-w03` | no | 36.47 | 33.82 | 36.40 | 11 |
| `2025-regu-w04` | no | 33.12 | 31.59 | 33.20 | 11 |
| `2025-regu-w05` | yes | 31.90 | 30.29 | 28.96 | 12 |
| `2025-regu-w06` | yes | 31.04 | 29.40 | 27.72 | 12 |
| `2025-regu-w07` | yes | 30.10 | 28.15 | 23.36 | 11 |
| `2025-regu-w08` | yes | 29.62 | 27.72 | 22.24 | 13 |
| `2025-regu-w09` | yes | 28.59 | 27.72 | 23.16 | 13 |
| `2025-regu-w10` | yes | 28.62 | 27.43 | 23.04 | 13 |
| `2025-regu-w11` | yes | 27.93 | 26.97 | 21.96 | 13 |
| `2025-regu-w12` | yes | 27.87 | 27.26 | 21.84 | 14 |
| `2025-regu-w13` | yes | 27.59 | 27.31 | 20.64 | 14 |
| `2025-regu-w14` | yes | 26.97 | 26.69 | 20.32 | 12 |
| `2025-regu-w15` | yes | 26.81 | 26.68 | 20.44 | 12 |
| `2025-regu-w16` | yes | 26.96 | 26.76 | 20.44 | 12 |
| `2025-post-w01` | yes | 26.35 | 26.35 | 21.04 | 12 |

## Which term was carrying the error, across the league

Regress every team's projection error on each term's contribution. A negative coefficient means teams we credited on that term systematically underperformed, which is to say we over-credited it this season.

**Across the 136 teams the poll ranked, every one of the four terms came back priced about right. The furthest from zero was last season's rating, at 1.4 standard errors, and the data cannot tell that apart from the value the recipe already uses. The season did not ask for a different coefficient.**

| term | coefficient | z | implied multiplier | verdict |
|---|---:|---:|---:|---|
| `prior_power` | +0.1950 | +1.38 | 1.195 | priced about right |
| `returning_production` | -0.4495 | -0.84 | 0.550 | priced about right |
| `coaching_change` | +0.5427 | +0.36 | 1.543 | priced about right |
| `net_portal` | +2.1847 | +0.34 | 3.185 | priced about right |

```json
{
 "prior_power": {
  "coefficient": 0.19504284884863665,
  "standard_error": 0.14136761596810843,
  "z": 1.379685492416007,
  "n_teams_moved": 136,
  "implied_multiplier": 1.1950428488486367,
  "verdict": "priced about right",
  "sentence": "The model priced last season's rating about right: over the 136 teams it moved, the data cannot tell its effect from zero (1.4 standard errors)."
 },
 "returning_production": {
  "coefficient": -0.44953889780699263,
  "standard_error": 0.5344457217213565,
  "z": -0.8411310625878081,
  "n_teams_moved": 134,
  "implied_multiplier": 0.5504611021930074,
  "verdict": "priced about right",
  "sentence": "The model priced returning production about right: over the 134 teams it moved, the data cannot tell its effect from zero (0.8 standard errors)."
 },
 "coaching_change": {
  "coefficient": 0.5427403919567839,
  "standard_error": 1.505888373721031,
  "z": 0.3604121005434681,
  "n_teams_moved": 32,
  "implied_multiplier": 1.542740391956784,
  "verdict": "priced about right",
  "sentence": "The model priced the coaching-change penalty about right: over the 32 teams it moved, the data cannot tell its effect from zero (0.4 standard errors)."
 },
 "net_portal": {
  "coefficient": 2.184721299844459,
  "standard_error": 6.435102902387907,
  "z": 0.33950060053177444,
  "n_teams_moved": 136,
  "implied_multiplier": 3.184721299844459,
  "verdict": "priced about right",
  "sentence": "The model priced net portal flow about right: over the 136 teams it moved, the data cannot tell its effect from zero (0.3 standard errors)."
 }
}
```

The league-wide attribution is a regression of projection error on each term's contribution, over about 134 teams and four correlated terms. One season is one data point about the recipe. It is suggestive and it is not a verdict.

Generated by `scripts/make_projection_2025.py` at 2026-08-18T21:03:25+00:00. The machine-readable form is `2025/projection-grading.json` in the site's data tree.
