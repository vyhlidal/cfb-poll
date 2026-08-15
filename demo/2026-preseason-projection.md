# The 2026 Preseason Projection

> **THIS IS A PROJECTION. IT IS NOT THE POLL.**
>
> The poll ranks what a team has done, from on-field results only, and it does not begin until week 5. This page is the model's August projection, built from last season's fitted ratings plus every offseason change we can measure. Its whole job is to be graded in public by the poll it is not allowed to influence.
>
> It is frozen. It will not be edited, quietly improved, or re-run when it starts to look bad. That is the deal.

Recipe `projection-2.0.0` · source season 2025 · generated 2026-08-15T23:25:29+00:00 · `5b35533d83`

## The recipe, in full

```
P_hat(team) = intercept
            + +0.6053 * prior_power_centered
            + +5.0016 * returning_usage_centered
            + -1.3010 * coach_change
            + -0.1805 * portal_net_z
```

| term | coefficient | standard error | reads as |
|---|---:|---:|---|
| intercept | +6.232 | 0.381 | projected Power of a league-average team that kept its coach |
| prior_power | +0.605 | 0.035 | share of last season's deviation from the FBS mean that survives |
| returning_production | +5.002 | 1.551 | points of Power per unit of returning offensive usage share |
| coaching_change | -1.301 | 0.833 | points of Power associated with a new head coach |
| net_portal | -0.180 | 0.340 | points of Power per standard deviation of net portal flow |

Fitted on 3 season transitions 2021→2022, 2022→2023, 2023→2024 · 398 team-seasons · R² = 0.463 · residual SD = 6.65 points.

**Read the standard errors before the ranking.** `prior_power`, `returning_production` are more than two standard errors from zero on this fit. `coaching_change`, `net_portal` are NOT: the data does not distinguish that coefficient from zero, and it is published at its fitted value rather than dropped, so that the grading loop can report season by season whether it ever earns its place. A term kept at a value the data cannot support is a term on probation, and saying which ones those are is cheaper than letting a reader assume all four are load-bearing.

## The top 25

`Power` is the projected rating in points. The four `Δ` columns are each term's signed contribution to it, in points, measured against a league-average team — they sum to `Power` with the intercept (+6.23) included.

| # | team | Power | proj W-L | SoS | SoS rk | W on median | Δ last season | Δ returning | Δ coach | Δ portal |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | Ohio State | 21.46 | 8.7-3.3 | 9.8 | 6 | 9.7 | +13.45 | +1.34 | +0.00 | +0.44 |
| 2 | Indiana | 20.99 | 9.1-2.9 | 8.8 | 18 | 9.6 | +16.46 | -1.61 | +0.00 | -0.09 |
| 3 | Oregon | 20.44 | 9.0-3.0 | 7.4 | 41 | 9.5 | +12.67 | +1.15 | +0.00 | +0.39 |
| 4 | Texas Tech | 20.21 | 9.8-2.2 | 3.9 | 91 | 9.5 | +13.44 | +0.63 | +0.00 | -0.09 |
| 5 | Notre Dame | 19.39 | 9.4-2.6 | 5.1 | 70 | 9.4 | +12.92 | +0.10 | +0.00 | +0.14 |
| 6 | Miami | 18.68 | 9.2-2.8 | 4.9 | 75 | 9.2 | +12.11 | +0.25 | +0.00 | +0.09 |
| 7 | Utah | 16.97 | 8.6-3.4 | 6.8 | 51 | 8.9 | +10.66 | +1.37 | -1.30 | +0.01 |
| 8 | Georgia | 16.93 | 8.2-3.8 | 8.4 | 24 | 8.9 | +9.07 | +1.51 | +0.00 | +0.11 |
| 9 | Texas A&M | 16.48 | 8.2-3.8 | 7.9 | 33 | 8.8 | +8.96 | +1.31 | +0.00 | -0.01 |
| 10 | North Dakota State | 16.42 | 9.5-2.5 | 0.7 | 137 | 8.8 | +10.47 | +0.00 | -0.32 | +0.04 |
| 11 | USC | 16.37 | 7.9-4.1 | 8.9 | 17 | 8.8 | +8.79 | +1.08 | +0.00 | +0.26 |
| 12 | BYU | 15.98 | 8.3-3.7 | 6.9 | 47 | 8.7 | +7.51 | +2.21 | +0.00 | +0.04 |
| 13 | Oklahoma | 15.53 | 7.5-4.5 | 9.5 | 8 | 8.6 | +7.50 | +1.53 | +0.00 | +0.26 |
| 14 | Vanderbilt | 15.19 | 7.8-4.2 | 8.7 | 19 | 8.5 | +9.57 | -0.57 | +0.00 | -0.04 |
| 15 | Washington | 14.49 | 7.4-4.6 | 9.3 | 10 | 8.4 | +7.44 | +0.65 | +0.00 | +0.16 |
| 16 | Alabama | 13.58 | 7.3-4.7 | 9.1 | 13 | 8.2 | +7.93 | -0.70 | +0.00 | +0.11 |
| 17 | Ole Miss | 13.57 | 7.3-4.7 | 9.0 | 14 | 8.2 | +7.58 | +1.19 | -1.30 | -0.14 |
| 18 | Texas | 13.29 | 6.8-5.2 | 11.1 | 1 | 8.1 | +6.28 | +0.70 | +0.00 | +0.09 |
| 19 | Michigan | 12.86 | 6.9-5.1 | 10.1 | 5 | 8.0 | +6.24 | +1.35 | -1.30 | +0.34 |
| 20 | San Diego State | 12.74 | 7.4-3.6 | 4.4 | 82 | 8.0 | +3.78 | +2.79 | +0.00 | -0.06 |
| 21 | Arizona | 12.54 | 7.1-4.9 | 8.4 | 25 | 8.0 | +5.19 | +1.23 | +0.00 | -0.11 |
| 22 | Iowa | 12.17 | 7.3-4.7 | 7.1 | 45 | 7.9 | +6.36 | -0.18 | +0.00 | -0.24 |
| 23 | SMU | 12.09 | 7.8-4.2 | 5.4 | 66 | 7.9 | +4.99 | +0.69 | +0.00 | +0.19 |
| 24 | Tennessee | 11.97 | 7.1-4.9 | 8.2 | 28 | 7.8 | +5.97 | -0.37 | +0.00 | +0.14 |
| 25 | Missouri | 11.23 | 6.8-5.2 | 8.5 | 21 | 7.7 | +4.83 | +0.31 | +0.00 | -0.14 |

**`SoS` is mean opponent projected power at a neutral field**, with venue kept out of it deliberately; `SoS rk` is that figure's rank among the 138 teams with a full schedule, 1 being hardest. **`W on median` is the load-bearing column**: every team scored against Notre Dame's 12-game calendar, which sits at the middle of that field. It is the column that makes this ordering checkable, because it is the only one where all 25 teams face the same opposition.

The sharpest case: **Ohio State projects 8.7 wins and Texas Tech projects 9.8, and Ohio State still ranks higher.** Swap their calendars and the reason is arithmetic rather than opinion: Ohio State would win 10.0 games on Texas Tech's schedule, and Texas Tech would win 8.4 on Ohio State's.

Projected records use sd(margin | projection) = sqrt(15.30^2 + 2 * 6.65^2) = 17.96 points, with the first term from [resume].sigma, the documented floor, which the source season's own walk-forward estimate came in under. The second term is the recipe's own residual error, carried by both teams independently. In-season the poll works with the first term alone; in August it does not have that luxury, and every win probability here is correspondingly closer to a coin flip.

## What this projection does not know

- **Returning production is offence only.** CFBD serves no defensive returning production of any kind, so the term covers half the roster. A team that returns its whole offence and none of its defence and a team that does the reverse are, to this recipe, the same team.
- **The portal term is a body count, and half of it is undercounted.** `origin` is populated on every row; `destination` on 78% of them, so players who had not landed anywhere when CFBD last wrote the file are counted out of their old school and never counted in to their new one. Departures are measured well; arrivals are not.
- **Stars were available and were not used.** CFBD publishes a recruiting rating on most portal rows. A star-weighted net flow would almost certainly predict better. It is also a recruiting composite, which is the first input the poll's constraint 2 bans, and using one here would make the poll's refusal look like a technicality.
- **The coaching term is a binary, not a judgement.** It says the head coach is new. It does not say whether he is good, it knows nothing about coordinators, and one coefficient applies to every school that changed.
- **Coverage.** 136 of 138 FBS teams have a returning-production row; the 2 missing (North Dakota State, Sacramento State) are new to FBS and have no prior FBS production to return, which is a correct absence rather than a gap.
- **The win totals are timid on purpose.** sd(margin | projection) = sqrt(15.30^2 + 2 * 6.65^2) = 17.96 points, with the first term from [resume].sigma, the documented floor, which the source season's own walk-forward estimate came in under. The second term is the recipe's own residual error, carried by both teams independently. In-season the poll works with the first term alone; in August it does not have that luxury, and every win probability here is correspondingly closer to a coin flip.
- **The 2026 schedule is 888 games as CFBD had it when this ran.** Schedules change; the projection does not get re-run when they do.
- **North Dakota State, Sacramento State moved up from FCS for 2026, and their prior-season rating was earned against FCS opposition.** The Power fit is all-divisions, so they carry a real rating. Ridge still shrinks thin schedules toward the mean of a universe that includes every FCS team, which is a softer standard than the one they are about to be held to, and the recipe has no term for promotion. It is not hypothetical here: North Dakota State lands #10. Treat that as the single least trustworthy row on this page, and watch what the grading loop does to it.
- **No AP preseason poll for 2026 was in the archive when this ran**, so the head-to-head comparison on this page is the historical one. The AP's 2026 preseason ballot will be scored against this page's when it appears.

## The holdout

This season was the project's sealed holdout. It was scored exactly once, on 2026-08-15, with every constant already frozen, and the result is published at demo/2025-holdout-scorecard.md whatever it says. The recipe's coefficients were fitted on transitions that exclude it and were not touched when it opened. See docs/adr/0012-2025-opens.md.

## The separation, measured

`cfbpoll audit-features` was run on the frames this page was built from, with the projection design matrix handed in: **10 layers, passed**. Every poll layer was rebuilt from its allow-list and came out bit-identical, and the projection layer was judged against its own deny-list — which still bans human polls and third-party fitted models, so the AP preseason poll this page is measured against is mechanically unable to be an input to it.

