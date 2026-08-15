# We projected 2025. Here is what the season said.

> The recipe below is the one this project publishes. It was fitted on 2021→2022, 2022→2023, 2023→2024 and **2024→2025 is not among those transitions**, so nothing here was fitted on the season it is being graded against. Nothing was excluded to make that true either: that transition has never been in the list.

Recipe `projection-2.0.0` · source season 2024 · config sha256 `956301f2331d8e19...` · code `5b35533d83`

The coefficients below are the ones on the published 2026 card, to 1e-9. Nothing was refitted, dropped or excluded to make 2025 out of sample: 2024->2025 was never in design_transitions.

**Which Power.** retro.season_power(...)[final]: the WALK-FORWARD Power at the season's last bucket, whose blend weights are estimated out of sample week by week. This is the surface the poll publishes, the surface the gate uses, and the surface the grading page scores against. It is the projection's input, its response and its grading target, and they are the same object.

## The one row this page is most often asked about

> We had Colorado 28th and the season put them 102nd. Of the 30 teams we projected highest, that is the furthest any of them fell, and it is worth being precise about why, because the easy explanation is wrong. The model does not read the press: the AP left Colorado out of its preseason top 25 and so did we, so nobody's hype got inherited here. What we read was Colorado's own 2024, where they were the 18th best team in the country by our Power rating, and that one number was worth 5.9 points to their projection. The model also saw the exodus and priced it. Colorado returned 19.6% of its offensive usage, the 33rd lowest figure among the 134 teams with a row, and 1% of its passing usage, which is what losing your quarterback looks like in the data. That cost them 1.0 point, the portal took another 0.1, and between them they moved Colorado from 18th to 28th. The problem is the ratio. Last season's rating can swing a team 28 points and returning production can swing one 5, so a team that arrives 18th cannot be argued down to 102nd by the offseason. The grading loop is what settles what to do about that, and this season it settled it the dull way: across the 136 teams the poll ranked, all four terms come back priced about right, the furthest of them 0.9 standard errors from the value we published. No coefficient here was wrong. The ratio is a property of the design, and 2025 is the first season that made it cost something. What we are not going to do is turn the returning-production dial up until Colorado looks right. We checked: every setting that moves Colorado down also moves Indiana down, and Indiana returned even less than Colorado did and went 16-0. Penn State and Baylor returned more production than almost anyone in the country, 4th and 3rd of 134, and finished 48th and 75th. In 2025 returning production told you almost nothing, and the fix for Colorado is not a bigger version of a term that did not work.

## The projection against the season, at the end of it

`Projected` is the projection. `Live` is the poll as it was published in the final week. `Hindsight` is that same week re-scored with the whole season's answers, which is the column that says what a team turned out to be. A negative delta means we had them too high. Both Power columns are on the definition named above, which is the one the poll publishes.

**At the final bucket the two surfaces are the same ranking, and that is arithmetic rather than agreement.** R(N, N) and R(N, final) coincide when N *is* final, because there is no rest-of-season left to substitute in. The two columns separate earlier in the year, and the week-by-week table below is where that separation is worth reading.

| Projected | Team | Live | Hindsight | vs live | vs hindsight | Power projected → actual |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Notre Dame | 12 | 12 | -11 | -11 | 18.29 → 28.57 |
| 2 | Ohio State | 5 | 5 | -3 | -3 | 18.29 → 29.45 |
| 3 | Penn State | 48 | 48 | -45 | -45 | 17.48 → 17.14 |
| 4 | Texas | 11 | 11 | -7 | -7 | 16.15 → 17.6 |
| 5 | Clemson | 64 | 64 | -59 | -59 | 15.21 → 10.57 |
| 6 | Oregon | 2 | 2 | +4 | +4 | 14.79 → 28.16 |
| 7 | SMU | 31 | 31 | -24 | -24 | 14.6 → 15.47 |
| 8 | Alabama | 10 | 10 | -2 | -2 | 14.57 → 20.33 |
| 9 | Arizona State | 36 | 36 | -27 | -27 | 14.32 → 11.79 |
| 10 | South Carolina | 81 | 81 | -71 | -71 | 14.27 → 8.48 |
| 11 | Boise State | 45 | 45 | -34 | -34 | 13.85 → 11.67 |
| 12 | Navy | 15 | 15 | -3 | -3 | 13.83 → 11.67 |
| 13 | Ole Miss | 6 | 6 | +7 | +7 | 13.5 → 19.76 |
| 14 | Kansas State | 56 | 56 | -42 | -42 | 13.5 → 12.4 |
| 15 | Georgia | 7 | 7 | +8 | +8 | 13.47 → 22.22 |
| 16 | Miami | 3 | 3 | +13 | +13 | 13.1 → 27.23 |
| 17 | Texas A&M | 8 | 8 | +9 | +9 | 12.97 → 22.02 |
| 18 | Indiana | 1 | 1 | +17 | +17 | 12.94 → 34.43 |
| 19 | Tennessee | 41 | 41 | -22 | -22 | 12.93 → 17.08 |
| 20 | Louisville | 30 | 30 | -10 | -10 | 12.79 → 15.57 |
| 21 | LSU | 42 | 42 | -21 | -21 | 12.41 → 12.53 |
| 22 | Georgia Tech | 34 | 34 | -12 | -12 | 12.11 → 11.85 |
| 23 | Baylor | 75 | 75 | -52 | -52 | 11.97 → 4.65 |
| 24 | Iowa State | 35 | 35 | -11 | -11 | 11.96 → 12.29 |
| 25 | BYU | 4 | 4 | +21 | +21 | 11.47 → 19.63 |

## What was wrong, in the projection's own words

- The projection had Virginia at #102. The poll now has them at #22. The projection under-rated them by 80 places, and they are +14.0 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -2.65 points of Power.
- The projection had North Texas at #90. The poll now has them at #17. The projection under-rated them by 73 places, and they are +16.2 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -2.22 points of Power.
- The projection had South Carolina at #10. The poll now has them at #81. The projection over-rated them by 71 places, and they are -5.8 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +6.86 points of Power.
- The projection had Clemson at #5. The poll now has them at #64. The projection over-rated them by 59 places, and they are -4.6 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +7.23 points of Power.
- The projection had Baylor at #23. The poll now has them at #75. The projection over-rated them by 52 places, and they are -7.3 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +4.10 points of Power.

## Convergence, week by week

Mean absolute rank error of the frozen projection against each surface. The `hindsight` column is the fairer early reading: in week 5 the live poll is itself provisional, and grading an August projection against a provisional answer double-counts the noise.

| week | published | vs live | vs hindsight | vs hindsight, projected top 25 | top-25 hits |
|---|:---:|---:|---:|---:|---:|
| `2025-regu-w01` | no | 43.37 | 39.04 | 46.08 | 8 |
| `2025-regu-w02` | no | 38.22 | 34.82 | 38.28 | 10 |
| `2025-regu-w03` | no | 36.96 | 34.24 | 34.96 | 11 |
| `2025-regu-w04` | no | 33.78 | 32.32 | 33.80 | 12 |
| `2025-regu-w05` | yes | 32.16 | 31.12 | 28.84 | 13 |
| `2025-regu-w06` | yes | 31.59 | 30.16 | 27.56 | 13 |
| `2025-regu-w07` | yes | 30.12 | 28.81 | 24.28 | 12 |
| `2025-regu-w08` | yes | 29.44 | 27.97 | 23.56 | 14 |
| `2025-regu-w09` | yes | 28.69 | 28.25 | 24.76 | 14 |
| `2025-regu-w10` | yes | 29.59 | 28.49 | 24.40 | 13 |
| `2025-regu-w11` | yes | 28.87 | 27.99 | 22.64 | 13 |
| `2025-regu-w12` | yes | 28.72 | 28.13 | 22.28 | 14 |
| `2025-regu-w13` | yes | 28.54 | 28.18 | 20.96 | 14 |
| `2025-regu-w14` | yes | 27.62 | 27.43 | 20.80 | 12 |
| `2025-regu-w15` | yes | 27.53 | 27.47 | 20.68 | 12 |
| `2025-regu-w16` | yes | 27.59 | 27.54 | 20.68 | 12 |
| `2025-post-w01` | yes | 27.31 | 27.31 | 21.40 | 12 |

## Which term was carrying the error, across the league

Regress every team's projection error on each term's contribution. A negative coefficient means teams we credited on that term systematically underperformed, which is to say we over-credited it this season.

**Across the 136 teams the poll ranked, every one of the four terms came back priced about right. The furthest from zero was last season's rating, at 0.9 standard errors, and the data cannot tell that apart from the value the recipe already uses. The season did not ask for a different coefficient.**

| term | coefficient | z | implied multiplier | verdict |
|---|---:|---:|---:|---|
| `prior_power` | +0.1242 | +0.88 | 1.124 | priced about right |
| `returning_production` | -0.4949 | -0.78 | 0.505 | priced about right |
| `coaching_change` | +0.9291 | +0.65 | 1.929 | priced about right |
| `net_portal` | +1.3711 | +0.37 | 2.371 | priced about right |

```json
{
 "prior_power": {
  "coefficient": 0.12422304295521329,
  "standard_error": 0.14175862113142665,
  "z": 0.8762997408111366,
  "n_teams_moved": 136,
  "implied_multiplier": 1.1242230429552134,
  "verdict": "priced about right",
  "sentence": "The model priced last season's rating about right: over the 136 teams it moved, the data cannot tell its effect from zero (0.9 standard errors)."
 },
 "returning_production": {
  "coefficient": -0.4949333158103332,
  "standard_error": 0.6382894540454439,
  "z": -0.7754057546673734,
  "n_teams_moved": 134,
  "implied_multiplier": 0.5050666841896668,
  "verdict": "priced about right",
  "sentence": "The model priced returning production about right: over the 134 teams it moved, the data cannot tell its effect from zero (0.8 standard errors)."
 },
 "coaching_change": {
  "coefficient": 0.9290665724993549,
  "standard_error": 1.432414056820111,
  "z": 0.6486019653855095,
  "n_teams_moved": 32,
  "implied_multiplier": 1.9290665724993548,
  "verdict": "priced about right",
  "sentence": "The model priced the coaching-change penalty about right: over the 32 teams it moved, the data cannot tell its effect from zero (0.6 standard errors)."
 },
 "net_portal": {
  "coefficient": 1.3710659729826071,
  "standard_error": 3.7384768166673905,
  "z": 0.36674454335785434,
  "n_teams_moved": 136,
  "implied_multiplier": 2.371065972982607,
  "verdict": "priced about right",
  "sentence": "The model priced net portal flow about right: over the 136 teams it moved, the data cannot tell its effect from zero (0.4 standard errors)."
 }
}
```

The league-wide attribution is a regression of projection error on each term's contribution, over about 134 teams and four correlated terms. One season is one data point about the recipe. It is suggestive and it is not a verdict.

Generated by `scripts/make_projection_2025.py` at 2026-08-15T23:25:58+00:00. The machine-readable form is `2025/projection-grading.json` in the site's data tree.
