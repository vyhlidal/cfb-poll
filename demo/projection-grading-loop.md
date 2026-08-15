# The grading loop, worked on 2024

This is what the published surface reads like. The projection below was made from 2023's final ratings by a recipe fitted on 2021→2022, 2022→2023 — so 2024 is genuinely out of sample — and it is then graded, week by week, against the poll it is not allowed to influence.

2024 rather than 2025 because grading is scoring, and 2025 is the sealed holdout. ADR 0010.

## Week 5 — the first graded week

*2024-regu-w05*

### We thought this, and here is what we now know

- The projection had Florida State at #9. The poll now has them at #105 — we over-rated them by 96 places, and they are -32.1 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +17.43 points of Power.
- The projection had Kansas at #18. The poll now has them at #111 — we over-rated them by 93 places, and they are -11.4 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +9.58 points of Power.
- The projection had Indiana at #100. The poll now has them at #13 — we under-rated them by 87 places, and they are +10.8 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -4.72 points of Power.
- The projection had Navy at #109. The poll now has them at #23 — we under-rated them by 86 places, and they are +8.4 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -9.39 points of Power.
- The projection had Pittsburgh at #101. The poll now has them at #15 — we under-rated them by 86 places, and they are -2.7 points of Power off the projected figure. The projection's largest term pointing the wrong way was net portal flow, worth +0.18 points of Power.

### Which offseason assumption was wrong

| term | coefficient | z | verdict |
|---|---:|---:|---|
| prior_power | -0.392 | -6.4 | TOO STRONG |
| returning_production | -0.758 | -2.5 | TOO STRONG |
| coaching_change | +6.189 | +2.0 | TOO WEAK |
| net_portal | -1.549 | -2.4 | TOO STRONG |

- Last season's rating was TOO STRONG. For every point of Power it moved a team's projection, that team finished 0.39 points the other way (6.4 standard errors over 134 teams). This season wanted about 0.61x the coefficient we used.
- Returning production was TOO STRONG. For every point of Power it moved a team's projection, that team finished 0.76 points the other way (2.5 standard errors over 133 teams). This season wanted about 0.24x the coefficient we used.
- The coaching-change penalty was TOO WEAK. For every point of Power it moved a team's projection, that team finished 6.19 points further in the same direction (2.0 standard errors over 33 teams). This season wanted about 7.19x the coefficient we used.
- Net portal flow was TOO STRONG. For every point of Power it moved a team's projection, that team finished 1.55 points the other way (2.4 standard errors over 134 teams). This season wanted about -0.55x the coefficient we used.

> One season is one data point about the recipe, and the terms are correlated with each other - a team that changed coach also tends to lose production - so a single season's coefficient is suggestive and not a verdict. The loop's value is cumulative.

## The end of the season

*2024-post-w01*

### We thought this, and here is what we now know

- The projection had Florida State at #9. The poll now has them at #115 — we over-rated them by 106 places, and they are -32.1 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +17.43 points of Power.
- The projection had Indiana at #100. The poll now has them at #10 — we under-rated them by 90 places, and they are +10.8 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -4.72 points of Power.
- The projection had Arizona State at #91. The poll now has them at #9 — we under-rated them by 82 places, and they are +7.7 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth -4.61 points of Power.
- The projection had Arizona at #16. The poll now has them at #96 — we over-rated them by 80 places, and they are -24.1 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +11.59 points of Power.
- The projection had Oklahoma State at #22. The poll now has them at #102 — we over-rated them by 80 places, and they are -22.8 points of Power off the projected figure. The projection's largest term pointing the wrong way was last season's rating, worth +7.55 points of Power.

### Which offseason assumption was wrong

| term | coefficient | z | verdict |
|---|---:|---:|---|
| prior_power | -0.392 | -6.4 | TOO STRONG |
| returning_production | -0.758 | -2.5 | TOO STRONG |
| coaching_change | +6.189 | +2.0 | TOO WEAK |
| net_portal | -1.549 | -2.4 | TOO STRONG |

- Last season's rating was TOO STRONG. For every point of Power it moved a team's projection, that team finished 0.39 points the other way (6.4 standard errors over 134 teams). This season wanted about 0.61x the coefficient we used.
- Returning production was TOO STRONG. For every point of Power it moved a team's projection, that team finished 0.76 points the other way (2.5 standard errors over 133 teams). This season wanted about 0.24x the coefficient we used.
- The coaching-change penalty was TOO WEAK. For every point of Power it moved a team's projection, that team finished 6.19 points further in the same direction (2.0 standard errors over 33 teams). This season wanted about 7.19x the coefficient we used.
- Net portal flow was TOO STRONG. For every point of Power it moved a team's projection, that team finished 1.55 points the other way (2.4 standard errors over 134 teams). This season wanted about -0.55x the coefficient we used.

> One season is one data point about the recipe, and the terms are correlated with each other - a team that changed coach also tends to lose production - so a single season's coefficient is suggestive and not a verdict. The loop's value is cumulative.

## How to read the attribution

The per-team lines are **accounting, not causation**. Each term handed each team a signed number of points relative to a league-average team; when a team lands below its projection, the largest credit that did not pay off is the one named. It says which term was carrying the error, not which term caused it.

The league table underneath is a regression of every team's projection error on each term's contribution. A negative coefficient means the teams that term credited systematically underperformed — we over-credited it that season — and that is the number the next version of the recipe should move toward. It is a statement about the recipe rather than about a team, which is what makes it worth accumulating for a decade.

