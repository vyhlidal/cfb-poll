# The 2026 Preseason Projection

> **THIS IS A PROJECTION. IT IS NOT THE POLL.**
>
> The poll ranks what a team has done, from on-field results only, and it does not begin until week 5. This page is the model's August projection, built from last season's fitted ratings plus every offseason change we can measure. Its whole job is to be graded in public by the poll it is not allowed to influence.
>
> It is frozen. It will not be edited, quietly improved, or re-run when it starts to look bad. That is the deal.

Recipe `projection-3.0.0` · source season 2025 · generated 2026-08-17T08:30:47+00:00 · `55c9729da4`

## The recipe, in full

```
P_hat(team) = intercept
            + +0.6486 * prior_power_centered
            + +5.2116 * returning_usage_centered
            + -1.5098 * coach_change
            + -0.1381 * portal_net_z
```

| term | coefficient | standard error | reads as |
|---|---:|---:|---|
| intercept | +6.582 | 0.344 | projected Power of a league-average team that kept its coach |
| prior_power | +0.649 | 0.034 | share of last season's deviation from the FBS mean that survives |
| returning_production | +5.212 | 1.399 | points of Power per unit of returning offensive usage share |
| coaching_change | -1.510 | 0.761 | points of Power associated with a new head coach |
| net_portal | -0.138 | 0.304 | points of Power per standard deviation of net portal flow |

Fitted on 4 season transitions 2021→2022, 2022→2023, 2023→2024, 2024→2025 · 534 team-seasons · R² = 0.451 · residual SD = 6.92 points.

**Read the standard errors before the ranking.** `prior_power`, `returning_production` are more than two standard errors from zero on this fit. `coaching_change`, `net_portal` are NOT: the data does not distinguish that coefficient from zero, and it is published at its fitted value rather than dropped, so that the grading loop can report season by season whether it ever earns its place. A term kept at a value the data cannot support is a term on probation, and saying which ones those are is cheaper than letting a reader assume all four are load-bearing.

## The top 25

`Power` is the projected rating in points. The four `Δ` columns are each term's signed contribution to it, in points, measured against a league-average team — they sum to `Power` with the intercept (+6.58) included.

| # | team | Power | proj W-L | SoS | SoS rk | W on median | Δ last season | Δ returning | Δ coach | Δ portal |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | Ohio State | 22.73 | 8.8-3.2 | 10.0 | 5 | 9.8 | +14.41 | +1.40 | +0.00 | +0.34 |
| 2 | Oregon | 21.02 | 9.0-3.0 | 7.2 | 37 | 9.6 | +12.94 | +1.20 | +0.00 | +0.30 |
| 3 | Indiana | 20.73 | 9.0-3.0 | 8.2 | 23 | 9.5 | +15.89 | -1.68 | +0.00 | -0.07 |
| 4 | Notre Dame | 20.54 | 9.4-2.6 | 5.8 | 62 | 9.5 | +13.75 | +0.11 | +0.00 | +0.10 |
| 5 | Texas Tech | 19.14 | 9.6-2.4 | 3.9 | 83 | 9.2 | +11.97 | +0.66 | +0.00 | -0.07 |
| 6 | Miami | 19.07 | 9.2-2.8 | 4.6 | 74 | 9.2 | +12.16 | +0.26 | +0.00 | +0.07 |
| 7 | Georgia | 17.67 | 8.3-3.7 | 8.4 | 19 | 9.0 | +9.43 | +1.57 | +0.00 | +0.09 |
| 8 | Texas A&M | 16.75 | 8.1-3.9 | 7.9 | 29 | 8.8 | +8.81 | +1.36 | +0.00 | -0.01 |
| 9 | BYU | 16.61 | 8.4-3.6 | 6.8 | 45 | 8.7 | +7.70 | +2.30 | +0.00 | +0.03 |
| 10 | USC | 16.38 | 7.8-4.2 | 9.6 | 9 | 8.7 | +8.47 | +1.13 | +0.00 | +0.20 |
| 11 | Utah | 16.03 | 8.3-3.7 | 6.6 | 49 | 8.6 | +9.52 | +1.43 | -1.51 | +0.01 |
| 12 | Oklahoma | 15.37 | 7.3-4.7 | 9.9 | 6 | 8.5 | +7.00 | +1.59 | +0.00 | +0.20 |
| 13 | Texas | 14.97 | 7.1-4.9 | 11.6 | 1 | 8.4 | +7.60 | +0.73 | +0.00 | +0.07 |
| 14 | Ole Miss | 14.62 | 7.6-4.4 | 8.7 | 15 | 8.3 | +8.41 | +1.24 | -1.51 | -0.11 |
| 15 | Alabama | 14.55 | 7.5-4.5 | 8.6 | 17 | 8.3 | +8.61 | -0.73 | +0.00 | +0.09 |
| 16 | Vanderbilt | 14.40 | 7.6-4.4 | 8.4 | 20 | 8.3 | +8.44 | -0.60 | +0.00 | -0.03 |
| 17 | Washington | 14.38 | 7.4-4.6 | 9.0 | 13 | 8.3 | +6.99 | +0.68 | +0.00 | +0.12 |
| 18 | SMU | 13.51 | 8.1-3.9 | 5.2 | 66 | 8.1 | +6.07 | +0.72 | +0.00 | +0.14 |
| 19 | Tennessee | 13.05 | 7.3-4.7 | 7.8 | 31 | 8.0 | +6.75 | -0.38 | +0.00 | +0.10 |
| 20 | Iowa | 12.59 | 7.4-4.6 | 6.9 | 42 | 7.9 | +6.38 | -0.19 | +0.00 | -0.18 |
| 21 | Michigan | 12.57 | 6.9-5.1 | 10.6 | 2 | 7.9 | +5.83 | +1.41 | -1.51 | +0.26 |
| 22 | Boise State | 12.06 | 6.8-4.2 | 6.7 | 46 | 7.8 | +3.84 | +1.53 | +0.00 | +0.10 |
| 23 | Missouri | 11.86 | 6.9-5.1 | 8.2 | 22 | 7.7 | +5.06 | +0.32 | +0.00 | -0.11 |
| 24 | Arizona | 11.78 | 7.0-5.0 | 8.1 | 25 | 7.7 | +4.01 | +1.28 | +0.00 | -0.09 |
| 25 | Louisville | 11.60 | 7.4-4.6 | 6.4 | 53 | 7.7 | +5.85 | -0.90 | +0.00 | +0.07 |

**`SoS` is mean opponent projected power at a neutral field**, with venue kept out of it deliberately; `SoS rk` is that figure's rank among the 138 teams with a full schedule, 1 being hardest. **`W on median` is the load-bearing column**: every team scored against Clemson's 12-game calendar, which sits at the middle of that field. It is the column that makes this ordering checkable, because it is the only one where all 25 teams face the same opposition.

The sharpest case: **Ohio State projects 8.8 wins and Texas Tech projects 9.6, and Ohio State still ranks higher.** Swap their calendars and the reason is arithmetic rather than opinion: Ohio State would win 10.1 games on Texas Tech's schedule, and Texas Tech would win 8.1 on Ohio State's.

Projected records use sd(margin | projection) = sqrt(15.30^2 + 2 * 6.92^2) = 18.16 points, with the first term from [resume].sigma, the documented floor, which the source season's own walk-forward estimate came in under. The second term is the recipe's own residual error, carried by both teams independently. In-season the poll works with the first term alone; in August it does not have that luxury, and every win probability here is correspondingly closer to a coin flip.

## How a rating crosses divisions

A team that earned its rating against FCS opponents does not carry it intact into an FBS game, and until this version that is exactly what happened. The size of the mistake is measurable, because the archive holds every game where the two divisions met.

Run the model's own prediction over those **602 crossover games** and the FBS side beats it by **+17.3 points** on average. Most of that is not about divisions: this model under-predicts every mismatch, and the same regression says a game it calls by 10 points is actually won by about 13. Carrying the predicted margin as a regressor and asking what is left for the division boundary gives the number this page uses:

| what | value | standard error | measured on |
|---|---:|---:|---|
| an FCS rating, against FBS opposition | **-13.4** | 0.61 | 602 crossover games |
| credit for being a program that got promoted | **+9.8** | 2.00 | 68 games, 6 programs |
| net, for a team moving up | **-3.6** | | both |

**The two numbers are not in conflict and they are not the same question.** The first is what an FCS roster is worth on a Saturday against FBS opposition. The second is what a program gains by being the kind of program that gets promoted at all, which is a program that spent years buying its way to FBS rosters and FBS staff. A promoted team carries both.

**And then the guard, which is the part that decides the top of this board.** The promotion credit is fitted on 6 programs whose ratings topped out at +6.0 against the FBS average. Any team rated well above that is outside the evidence, so the rule is a maximum rather than an extrapolation: **no promoted team is projected above the best first FBS season a promoted program has actually had.** That is James Madison in 2022, at +5.7 against the FBS average.

Every one of these is a lever with a published range. Turn the first to zero and you get the board this project published in August 2026, with North Dakota State tenth.

## The rows people will argue about

**North Dakota State, projected #33.** North Dakota State moved up from FCS, so the rating they bring with them was earned against teams they will not play any more.

Their 2025 rating was +24.52. The 602 games between an FBS team and an FCS team in this archive say a rating earned outside FBS is worth 13.4 points less against FBS opposition. The 68 games 6 promoted programs have actually played in their first FBS season give 9.8 of that back. That still left them above anything a promoted program has ever done, so the ceiling applies: no promoted team is projected above James Madison's first FBS season in 2022, which is the best on record. North Dakota State lands 33rd.

*North Dakota State has played 2 games against an FBS opponent in this archive and won 0: 2022 lost to Arizona by 3; 2024 lost to Colorado by 5.*

**Sacramento State, projected #116.** Sacramento State moved up from FCS, so the rating they bring with them was earned against teams they will not play any more.

Their 2025 rating was +2.99. The 602 games between an FBS team and an FCS team in this archive say a rating earned outside FBS is worth 13.4 points less against FBS opposition. The 68 games 6 promoted programs have actually played in their first FBS season give 9.8 of that back. Sacramento State lands 116th.

*Sacramento State has played 6 games against an FBS opponent in this archive and won 2: 2021 lost to California by 12; 2022 beat Colorado State by 31; 2023 beat Stanford by 7; 2024 lost to San José State by 18; 2024 lost to Fresno State by 16; 2025 lost to Nevada by 3.*

**Texas, projected #13.** Texas projects 13th, and the argument is not about this August. It is about last season, which the model scored 21st.

They finished 2025 on +17.60 Power, +10.47 against the FBS average, which was 21st in the league. That is the number to argue with, because everything after it is arithmetic. The projection does not use it alone: it blends in 2024, when Texas rated +22.48, at the published weight, and the carried rating that comes out is +18.58, which is 15th. Returning production then adds +0.73 points and the portal +0.07, and mean reversion pulls every team toward the middle at once, which is how a carried +18.58 becomes a projected 14.97 and 15th becomes 13th. Their 2026 schedule is the 1st hardest of 138, which costs them projected wins and costs them nothing in the ranking: this board is sorted by how good the model thinks a team is, not by how many games it expects them to win.

*The three 2025 games that cost Texas the most, each measured against what the model expected of them that day: lost to Georgia by 25 on the road, where the model expected them to lose by 8; lost to Florida by 8 on the road, where the model expected them to win by 5; beat UTEP by 17 at home, where the model expected them to win by 27. Their best day ran the other way: they beat Sam Houston by 55 at home, where the model expected them to win by 34.*

## What this projection does not know

- **Returning production is offence only.** CFBD serves no defensive returning production of any kind, so the term covers half the roster. A team that returns its whole offence and none of its defence and a team that does the reverse are, to this recipe, the same team.
- **The portal term is a body count, and half of it is undercounted.** `origin` is populated on every row; `destination` on 78% of them, so players who had not landed anywhere when CFBD last wrote the file are counted out of their old school and never counted in to their new one. Departures are measured well; arrivals are not.
- **Stars were available and were not used.** CFBD publishes a recruiting rating on most portal rows. A star-weighted net flow would almost certainly predict better. It is also a recruiting composite, which is the first input the poll's constraint 2 bans, and using one here would make the poll's refusal look like a technicality.
- **The coaching term is a binary, not a judgement.** It says the head coach is new. It does not say whether he is good, it knows nothing about coordinators, and one coefficient applies to every school that changed.
- **Coverage.** 136 of 138 FBS teams have a returning-production row; the 2 missing (North Dakota State, Sacramento State) are new to FBS and have no prior FBS production to return, which is a correct absence rather than a gap.
- **The win totals are timid on purpose.** sd(margin | projection) = sqrt(15.30^2 + 2 * 6.92^2) = 18.16 points, with the first term from [resume].sigma, the documented floor, which the source season's own walk-forward estimate came in under. The second term is the recipe's own residual error, carried by both teams independently. In-season the poll works with the first term alone; in August it does not have that luxury, and every win probability here is correspondingly closer to a coin flip.
- **The 2026 schedule is 888 games as CFBD had it when this ran.** Schedules change; the projection does not get re-run when they do.
- **North Dakota State, Sacramento State moved up from FCS for 2026.** Their rating was earned against opponents they will not play any more, and this version corrects for that from the crossover games rather than warning about it in a footnote. The correction and the evidence behind it are in **How a rating crosses divisions** above. What is still thin: the promotion half of it rests on six programs, and the ceiling that stops it being extrapolated is a maximum over those same six.
- **No AP preseason poll for 2026 was in the archive when this ran**, so the head-to-head comparison on this page is the historical one. The AP's 2026 preseason ballot will be scored against this page's when it appears.

## The holdout

This season was the project's sealed holdout. It was scored exactly once, on 2026-08-15, with every constant already frozen, and the result is published at demo/2025-holdout-scorecard.md whatever it says. The recipe's coefficients were fitted on transitions that exclude it and were not touched when it opened. See docs/adr/0012-2025-opens.md.

## The separation, measured

`cfbpoll audit-features` was run on the frames this page was built from, with the projection design matrix handed in: **10 layers, passed**. Every poll layer was rebuilt from its allow-list and came out bit-identical, and the projection layer was judged against its own deny-list — which still bans human polls and third-party fitted models, so the AP preseason poll this page is measured against is mechanically unable to be an input to it.

