# The grading loop, worked on 2024

This is what the published surface reads like. The projection below was made from 2023's final ratings by a recipe fitted on 2021→2022, 2022→2023 — so 2024 is genuinely out of sample — and it is then graded, week by week, against the poll it is not allowed to influence.

2024 rather than 2025 because grading is scoring, and 2025 is the sealed holdout. ADR 0010.

## Week 5 — the first graded week

*2024-regu-w05*

### We thought this, and here is what we now know

- The projection had Indiana at #109. The poll now has them at #13. The projection under-rated them by 96 places, and they are +18.8 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -4.91 points of Power.
- The projection had Florida State at #17. The poll now has them at #105. The projection over-rated them by 88 places, and they are -17.0 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +9.99 points of Power.
- The projection had Kansas at #23. The poll now has them at #111. The projection over-rated them by 88 places, and they are +1.5 points of Power off the projected figure. The projection's largest term pointing the wrong way was net portal flow, worth -0.30 points of Power.
- The projection had Navy at #106. The poll now has them at #23. The projection under-rated them by 83 places, and they are +13.6 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -5.95 points of Power.
- The projection had BYU at #82. The poll now has them at #1. The projection under-rated them by 81 places, and they are +10.9 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -2.30 points of Power.

### Which offseason assumption was wrong

| term | coefficient | z | verdict |
|---|---:|---:|---|
| prior_power | -0.114 | -1.2 | priced about right |
| returning_production | -0.603 | -1.5 | priced about right |
| coaching_change | -23.338 | -2.5 | TOO STRONG |
| net_portal | -1.476 | -1.1 | priced about right |

- The model priced last season's rating about right: over the 134 teams it moved, the data cannot tell its effect from zero (1.2 standard errors).
- The model priced returning production about right: over the 133 teams it moved, the data cannot tell its effect from zero (1.5 standard errors).
- The model weighted the coaching-change penalty TOO STRONG. For every point of Power it moved a team's projection, that team finished 23.34 points the other way (2.5 standard errors over 33 teams). This season wanted about -22.34x the model's coefficient.
- The model priced net portal flow about right: over the 134 teams it moved, the data cannot tell its effect from zero (1.1 standard errors).

> One season is one data point about the recipe, and the terms are correlated with each other - a team that changed coach also tends to lose production - so a single season's coefficient is suggestive and not a verdict. The loop's value is cumulative.

## The end of the season

*2024-post-w01*

### We thought this, and here is what we now know

- The projection had Indiana at #109. The poll now has them at #10. The projection under-rated them by 99 places, and they are +18.8 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -4.91 points of Power.
- The projection had Florida State at #17. The poll now has them at #115. The projection over-rated them by 98 places, and they are -17.0 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +9.99 points of Power.
- The projection had Arizona State at #98. The poll now has them at #9. The projection under-rated them by 89 places, and they are +16.0 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -4.70 points of Power.
- The projection had Arizona at #14. The poll now has them at #96. The projection over-rated them by 82 places, and they are -12.7 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +8.21 points of Power.
- The projection had Oregon State at #24. The poll now has them at #101. The projection over-rated them by 77 places, and they are -13.6 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +8.12 points of Power.

### Which offseason assumption was wrong

| term | coefficient | z | verdict |
|---|---:|---:|---|
| prior_power | -0.114 | -1.2 | priced about right |
| returning_production | -0.603 | -1.5 | priced about right |
| coaching_change | -23.338 | -2.5 | TOO STRONG |
| net_portal | -1.476 | -1.1 | priced about right |

- The model priced last season's rating about right: over the 134 teams it moved, the data cannot tell its effect from zero (1.2 standard errors).
- The model priced returning production about right: over the 133 teams it moved, the data cannot tell its effect from zero (1.5 standard errors).
- The model weighted the coaching-change penalty TOO STRONG. For every point of Power it moved a team's projection, that team finished 23.34 points the other way (2.5 standard errors over 33 teams). This season wanted about -22.34x the model's coefficient.
- The model priced net portal flow about right: over the 134 teams it moved, the data cannot tell its effect from zero (1.1 standard errors).

> One season is one data point about the recipe, and the terms are correlated with each other - a team that changed coach also tends to lose production - so a single season's coefficient is suggestive and not a verdict. The loop's value is cumulative.

## How to read the attribution

The per-team lines are **accounting, not causation**. Each term handed each team a signed number of points relative to a league-average team; when a team lands below its projection, the largest credit that did not pay off is the one named. It says which term was carrying the error, not which term caused it.

The league table underneath is a regression of every team's projection error on each term's contribution. A negative coefficient means the teams that term credited systematically underperformed — we over-credited it that season — and that is the number the next version of the recipe should move toward. It is a statement about the recipe rather than about a team, which is what makes it worth accumulating for a decade.

