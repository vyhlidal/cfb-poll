# The 2026 Preseason Projection

> **THIS IS A PROJECTION. IT IS NOT THE POLL.**
>
> The poll ranks what a team has done, from on-field results only, and it does not begin until week 5. This page is a guess made in August, before anybody has played a snap. It is built from last season's fitted ratings plus every offseason change we can measure, and its whole job is to be graded in public by the poll it is not allowed to influence.
>
> It is frozen. It will not be edited, quietly improved, or re-run when it starts to look bad. That is the deal.

Recipe `projection-1.0.0` · source season 2025 · generated 2026-08-15T19:32:54+00:00 · `46572be4fd`

## The recipe, in full

```
P_hat(team) = intercept
            + +0.6826 * prior_power_centered
            + +7.0829 * returning_usage_centered
            + -2.3346 * coach_change
            + -0.4106 * portal_net_z
```

| term | coefficient | standard error | reads as |
|---|---:|---:|---|
| intercept | +14.979 | 0.532 | projected Power of a league-average team that kept its coach |
| prior_power | +0.683 | 0.037 | share of last season's deviation from the FBS mean that survives |
| returning_production | +7.083 | 2.151 | points of Power per unit of returning offensive usage share |
| coaching_change | -2.335 | 1.132 | points of Power associated with a new head coach |
| net_portal | -0.411 | 0.474 | points of Power per standard deviation of net portal flow |

Fitted on 3 season transitions 2021→2022, 2022→2023, 2023→2024 · 398 team-seasons · R² = 0.507 · residual SD = 9.22 points.

**Read the standard errors before the ranking.** `prior_power`, `returning_production`, `coaching_change` are more than two standard errors from zero on this fit. `net_portal` is NOT: the data does not distinguish that coefficient from zero, and it is published at its fitted value rather than dropped, so that the grading loop can report season by season whether it ever earns its place. A term kept at a value the data cannot support is a term on probation, and saying which ones those are is cheaper than letting a reader assume all four are load-bearing.

## The top 25

`Power` is the projected rating in points. The four `Δ` columns are each term's signed contribution to it, in points, measured against a league-average team — they sum to `Power` with the intercept (+14.98) included.

| # | team | Power | proj W-L | SoS | SoS rk | W on median | Δ last season | Δ returning | Δ coach | Δ portal |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | Ohio State | 37.91 | 9.1-2.9 | 21.5 | 2 | 10.4 | +20.03 | +1.90 | +0.00 | +1.00 |
| 2 | Oregon | 37.57 | 9.5-2.5 | 18.2 | 28 | 10.4 | +20.08 | +1.63 | +0.00 | +0.88 |
| 3 | Indiana | 37.20 | 9.6-2.4 | 18.9 | 17 | 10.3 | +24.71 | -2.28 | +0.00 | -0.20 |
| 4 | Georgia | 33.57 | 9.1-2.9 | 18.2 | 29 | 9.9 | +16.20 | +2.14 | +0.00 | +0.25 |
| 5 | Notre Dame | 33.55 | 9.7-2.3 | 14.8 | 59 | 9.9 | +18.12 | +0.15 | +0.00 | +0.31 |
| 6 | Miami | 33.21 | 9.8-2.2 | 12.9 | 71 | 9.8 | +17.68 | +0.36 | +0.00 | +0.20 |
| 7 | Texas Tech | 32.61 | 10.0-2.0 | 12.5 | 74 | 9.7 | +16.94 | +0.90 | +0.00 | -0.20 |
| 8 | BYU | 32.34 | 9.2-2.8 | 16.1 | 47 | 9.7 | +14.15 | +3.13 | +0.00 | +0.08 |
| 9 | Oklahoma | 30.90 | 8.1-3.9 | 20.4 | 8 | 9.5 | +13.16 | +2.17 | +0.00 | +0.60 |
| 10 | Utah | 30.33 | 8.9-3.1 | 16.2 | 44 | 9.4 | +15.72 | +1.95 | -2.33 | +0.02 |
| 11 | Ole Miss | 29.84 | 8.3-3.7 | 19.0 | 16 | 9.3 | +15.82 | +1.69 | -2.33 | -0.32 |
| 12 | Texas A&M | 29.68 | 8.5-3.5 | 17.4 | 36 | 9.3 | +12.88 | +1.85 | +0.00 | -0.03 |
| 13 | USC | 29.66 | 8.1-3.9 | 19.5 | 13 | 9.3 | +12.55 | +1.53 | +0.00 | +0.60 |
| 14 | Washington | 27.09 | 7.6-4.4 | 20.1 | 10 | 8.8 | +10.82 | +0.93 | +0.00 | +0.37 |
| 15 | Vanderbilt | 26.69 | 7.9-4.1 | 18.4 | 23 | 8.8 | +12.61 | -0.81 | +0.00 | -0.09 |
| 16 | Alabama | 26.66 | 7.8-4.2 | 18.7 | 19 | 8.8 | +12.42 | -0.99 | +0.00 | +0.25 |
| 17 | Arizona | 26.63 | 7.7-4.3 | 18.8 | 18 | 8.8 | +10.18 | +1.74 | +0.00 | -0.26 |
| 18 | Texas | 26.39 | 7.1-4.9 | 22.1 | 1 | 8.7 | +10.23 | +0.99 | +0.00 | +0.20 |
| 19 | Michigan | 25.27 | 7.0-5.0 | 21.2 | 4 | 8.5 | +9.94 | +1.92 | -2.33 | +0.77 |
| 20 | SMU | 25.05 | 8.5-3.5 | 13.8 | 68 | 8.5 | +8.67 | +0.98 | +0.00 | +0.42 |
| 21 | Iowa | 24.68 | 7.4-4.6 | 17.7 | 32 | 8.4 | +10.51 | -0.26 | +0.00 | -0.55 |
| 22 | Illinois | 24.60 | 7.5-4.5 | 18.4 | 22 | 8.4 | +9.40 | -0.04 | +0.00 | +0.25 |
| 23 | North Dakota State | 24.41 | 9.5-2.5 | 5.6 | 134 | 8.4 | +9.92 | +0.00 | -0.57 | +0.08 |
| 24 | Pittsburgh | 23.05 | 8.4-3.6 | 11.7 | 80 | 8.1 | +7.47 | +0.46 | +0.00 | +0.14 |
| 25 | Boise State | 22.60 | 7.0-4.0 | 15.2 | 54 | 8.0 | +5.23 | +2.08 | +0.00 | +0.31 |

**`SoS` is mean opponent projected power at a neutral field**, with venue kept out of it deliberately; `SoS rk` is that figure's rank among the 138 teams with a full schedule, 1 being hardest. **`W on median` is the load-bearing column**: every team scored against NC State's 12-game calendar, which sits at the middle of that field. It is the column that makes this ordering checkable, because it is the only one where all 25 teams face the same opposition.

The sharpest case: **Ohio State projects 9.1 wins and Texas Tech projects 10.0, and Ohio State still ranks higher.** Swap their calendars and the reason is arithmetic rather than opinion: Ohio State would win 10.6 games on Texas Tech's schedule, and Texas Tech would win 8.2 on Ohio State's.

Projected records use sd(margin | projection) = sqrt(15.30^2 + 2 * 9.22^2) = 20.10 points, with the first term from [resume].sigma, the documented fallback and floor. The second term is the recipe's own residual error, carried by both teams independently. In-season the poll works with the first term alone; in August it does not have that luxury, and every win probability here is correspondingly closer to a coin flip.

## What this projection does not know

- **Returning production is offence only.** CFBD serves no defensive returning production of any kind, so the term covers half the roster. A team that returns its whole offence and none of its defence and a team that does the reverse are, to this recipe, the same team.
- **The portal term is a body count, and half of it is undercounted.** `origin` is populated on every row; `destination` on 78% of them, so players who had not landed anywhere when CFBD last wrote the file are counted out of their old school and never counted in to their new one. Departures are measured well; arrivals are not.
- **Stars were available and were not used.** CFBD publishes a recruiting rating on most portal rows. A star-weighted net flow would almost certainly predict better. It is also a recruiting composite, which is the first input the poll's constraint 2 bans, and using one here would make the poll's refusal look like a technicality.
- **The coaching term is a binary, not a judgement.** It says the head coach is new. It does not say whether he is good, it knows nothing about coordinators, and one coefficient applies to every school that changed.
- **Coverage.** 136 of 138 FBS teams have a returning-production row; the 2 missing (North Dakota State, Sacramento State) are new to FBS and have no prior FBS production to return, which is a correct absence rather than a gap.
- **The win totals are timid on purpose.** sd(margin | projection) = sqrt(15.30^2 + 2 * 9.22^2) = 20.10 points, with the first term from [resume].sigma, the documented fallback and floor. The second term is the recipe's own residual error, carried by both teams independently. In-season the poll works with the first term alone; in August it does not have that luxury, and every win probability here is correspondingly closer to a coin flip.
- **The 2026 schedule is 888 games as CFBD had it when this ran.** Schedules change; the projection does not get re-run when they do.
- **North Dakota State, Sacramento State moved up from FCS for 2026, and their prior-season rating was earned against FCS opposition.** The Power fit is all-divisions, so they have a real rating rather than a guess — but ridge shrinks thin schedules toward the mean of a universe that includes every FCS team, which is a softer standard than the one they are about to be held to, and the recipe has no term for promotion. It is not hypothetical here: North Dakota State lands #23. Treat that as the single least trustworthy row on this page, and watch what the grading loop does to it.
- **No AP preseason poll for 2026 was in the archive when this ran**, so the head-to-head comparison on this page is the historical one. The AP's 2026 guess will be scored against this page's when it appears.

## The holdout

This season was the project's sealed holdout. It was scored exactly once, on 2026-08-15, with every constant already frozen, and the result is published at demo/2025-holdout-scorecard.md whatever it says. The recipe's coefficients were fitted on transitions that exclude it and were not touched when it opened. See docs/adr/0012-2025-opens.md.

## The separation, measured

`cfbpoll audit-features` was run on the frames this page was built from, with the projection design matrix handed in: **10 layers, passed**. Every poll layer was rebuilt from its allow-list and came out bit-identical, and the projection layer was judged against its own deny-list — which still bans human polls and third-party fitted models, so the AP preseason poll this page is measured against is mechanically unable to be an input to it.

