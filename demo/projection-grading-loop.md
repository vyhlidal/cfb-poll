# The grading loop, worked on 2024

This is what the published surface reads like. The projection below was made from 2023's final ratings by a recipe fitted on 2021→2022, 2022→2023, 2024→2025 — so 2024 is genuinely out of sample — and it is then graded, week by week, against the poll it is not allowed to influence.

2024 rather than 2025 because grading is scoring, and 2025 is the sealed holdout. ADR 0010.

## Week 5 — the first graded week

*2024-regu-w05*

### We thought this, and here is what we now know

- The projection had Indiana at #110. The poll now has them at #13. The projection under-rated them by 97 places, and they are +19.0 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -5.04 points of Power.
- The projection had Florida State at #13. The poll now has them at #105. The projection over-rated them by 92 places, and they are -18.1 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +10.24 points of Power.
- The projection had Kansas at #22. The poll now has them at #111. The projection over-rated them by 89 places, and they are +1.0 points of Power off the projected figure. The projection's largest term pointing the wrong way was net portal flow, worth -0.29 points of Power.
- The projection had Navy at #104. The poll now has them at #23. The projection under-rated them by 81 places, and they are +13.3 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -6.10 points of Power.
- The projection had BYU at #80. The poll now has them at #1. The projection under-rated them by 79 places, and they are +10.5 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -2.36 points of Power.

### Which offseason assumption was wrong

| term | coefficient | z | verdict |
|---|---:|---:|---|
| prior_power | -0.136 | -1.5 | priced about right |
| returning_production | -0.514 | -1.0 | priced about right |
| coaching_change | +3.701 | +1.9 | priced about right |
| net_portal | -1.503 | -1.1 | priced about right |

- The model priced last season's rating about right: over the 134 teams it moved, the data cannot tell its effect from zero (1.5 standard errors).
- The model priced returning production about right: over the 133 teams it moved, the data cannot tell its effect from zero (1.0 standard errors).
- The model priced the coaching-change penalty about right: over the 33 teams it moved, the data cannot tell its effect from zero (1.9 standard errors).
- The model priced net portal flow about right: over the 134 teams it moved, the data cannot tell its effect from zero (1.1 standard errors).

> One season is one data point about the recipe, and the terms are correlated with each other - a team that changed coach also tends to lose production - so a single season's coefficient is suggestive and not a verdict. The loop's value is cumulative.

## The end of the season

*2024-post-w01*

### We thought this, and here is what we now know

- The projection had Florida State at #13. The poll now has them at #115. The projection over-rated them by 102 places, and they are -18.1 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +10.24 points of Power.
- The projection had Indiana at #110. The poll now has them at #10. The projection under-rated them by 100 places, and they are +19.0 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -5.04 points of Power.
- The projection had Arizona State at #99. The poll now has them at #9. The projection under-rated them by 90 places, and they are +15.7 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -4.83 points of Power.
- The projection had Arizona at #17. The poll now has them at #96. The projection over-rated them by 79 places, and they are -12.6 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +8.42 points of Power.
- The projection had Oregon State at #25. The poll now has them at #101. The projection over-rated them by 76 places, and they are -14.0 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +8.33 points of Power.

### Which offseason assumption was wrong

| term | coefficient | z | verdict |
|---|---:|---:|---|
| prior_power | -0.136 | -1.5 | priced about right |
| returning_production | -0.514 | -1.0 | priced about right |
| coaching_change | +3.701 | +1.9 | priced about right |
| net_portal | -1.503 | -1.1 | priced about right |

- The model priced last season's rating about right: over the 134 teams it moved, the data cannot tell its effect from zero (1.5 standard errors).
- The model priced returning production about right: over the 133 teams it moved, the data cannot tell its effect from zero (1.0 standard errors).
- The model priced the coaching-change penalty about right: over the 33 teams it moved, the data cannot tell its effect from zero (1.9 standard errors).
- The model priced net portal flow about right: over the 134 teams it moved, the data cannot tell its effect from zero (1.1 standard errors).

> One season is one data point about the recipe, and the terms are correlated with each other - a team that changed coach also tends to lose production - so a single season's coefficient is suggestive and not a verdict. The loop's value is cumulative.

## How to read the attribution

The per-team lines are **accounting, not causation**. Each term handed each team a signed number of points relative to a league-average team; when a team lands below its projection, the largest credit that did not pay off is the one named. It says which term was carrying the error, not which term caused it.

The league table underneath is a regression of every team's projection error on each term's contribution. A negative coefficient means the teams that term credited systematically underperformed — we over-credited it that season — and that is the number the next version of the recipe should move toward. It is a statement about the recipe rather than about a team, which is what makes it worth accumulating for a decade.

