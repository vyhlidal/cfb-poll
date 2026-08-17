# The accuracy scoreboard

> This page replaces the gate. The gate was a pass/fail ceremony against a threshold, and its verdict was a boolean. This is the scoreboard: what the model said in August, what happened, and how often it was right, beside the same figure for the sportswriters and for doing nothing at all.

`projection-3.0.0` · generated 2026-08-17T18:52:49+00:00 · `9f52506cac`

## The protocol, which is the whole of the honesty

Walk-forward. For target season Y every system reads results from seasons <= Y-1, the offseason table for Y and the calendar of Y, and nothing from Y itself. Straight-up accuracy, with the home-field constant taken from season Y-1's fitted L3 home field rather than fitted on the games being scored. Ties count as misses.

A system with no legal way to exist for a season is reported as absent rather than given a shortcut. `projection_v2` and `projection_v3` have no 2022 row because the archive starts in 2021 and there is no completed transition to fit a recipe on before 2022; fitting one on 2022 itself and then scoring 2022 would be a description wearing a projection's clothes.

## Every game with an FBS team in it

This is what a reader means by week 1. Half of week 1 is an FBS team playing an FCS team, and a model that quietly drops those is scoring itself on the half of the slate it finds interesting.

| system | week 1 | weeks 1-4 |
|---|---:|---:|
| last season's ratings, unchanged | 81.0% (384) | 77.0% (1251) |
| the old model (projection-2.0.0) | 82.4% (290) | 77.4% (937) |
| this model (projection-3.0.0) | 86.9% (290) | 80.4% (937) |
| the AP writers' August ballot | 82.3% (384) | 76.7% (1251) |

Season by season, week 1:

| season | last season's ratings, unchanged | the old model (projection-2.0.0) | this model (projection-3.0.0) | the AP writers' August ballot |
|---|---|---|---|---|
| 2022 | 76.6% (94) | — | — | 80.9% (94) |
| 2023 | 85.1% (94) | 86.2% (94) | 89.4% (94) | 86.2% (94) |
| 2024 | 81.0% (100) | 80.0% (100) | 87.0% (100) | 82.0% (100) |
| 2025 | 81.2% (96) | 81.2% (96) | 84.4% (96) | 80.2% (96) |

## FBS against FBS only

The hard subset, where nobody is picking on anybody. Smaller samples, and the honest headline for anyone comparing this with another rating system.

| system | week 1 | weeks 1-4 |
|---|---:|---:|
| last season's ratings, unchanged | 74.0% (192) | 71.3% (815) |
| the old model (projection-2.0.0) | 73.4% (139) | 71.7% (605) |
| this model (projection-3.0.0) | 74.1% (139) | 71.6% (605) |
| the AP writers' August ballot | 68.2% (192) | 67.4% (815) |

Season by season, week 1:

| season | last season's ratings, unchanged | the old model (projection-2.0.0) | this model (projection-3.0.0) | the AP writers' August ballot |
|---|---|---|---|---|
| 2022 | 71.7% (53) | — | — | 69.8% (53) |
| 2023 | 78.8% (52) | 78.8% (52) | 80.8% (52) | 76.9% (52) |
| 2024 | 71.8% (39) | 66.7% (39) | 66.7% (39) | 59.0% (39) |
| 2025 | 72.9% (48) | 72.9% (48) | 72.9% (48) | 64.6% (48) |

## What moved, and what measured it

Three changes separate this model from the one it replaces, and each was measured before it was adopted rather than after.

1. **A rating earned outside FBS no longer transplants at face value.** 602 crossover games price the move at 13.4 points; 68 games from six promoted programs give 9.8 of it back; and no promoted team is projected above the best first FBS season a promoted program has actually had. This is the single largest source of the gain above, and it is almost entirely in the crossover games — which is exactly where it should be.
2. **A second season of memory.** The year before last counts at 0.2. Worth about half a point of week-one accuracy, which is inside the noise band on this many games and is reported as a peak rather than a discovery.
3. **The freeze is gone.** The recipe refits whenever a season closes, so the 2024-to-2025 transition is now in the design. What replaces the freeze is the vintage record: every board ever published stays up with the coefficients it ran under, so "what did you say in August" is answered by the archive rather than by refusing to learn.

## The levers

Every number below is a choice the model is genuinely uncertain about, and every default was measured rather than picked. The two things that are not levers, and never will be, are at the bottom.

| lever | what it does | range | default |
|---|---|---|---:|
| **How much the year before last still counts** | Programs are not rebuilt every August. At 0 the projection only looks at last season. Turn it up and the season before last gets a say too, which steadies a team whose one bad year looks like an accident. | 0 to 0.6 | 0.2 |
| **How far an FCS rating falls when it meets FBS** | A team that earned its rating against FCS opponents does not carry it intact into an FBS game. At 1 the projection applies the full gap the crossover games measured. At 0 it takes the FCS rating at face value, which is what this poll did until the 2026 board put North Dakota State tenth. | 0 to 1.5 | 1 |
| **Credit for being the kind of program that moves up** | A program that is promoted to FBS is not a random FCS team. It spent years buying its way to FBS rosters and staff, and the six programs that have made the jump won back most of the gap in their first season. At 0 a promoted team is treated like any other FCS team. | 0 to 1.5 | 1 |
| **Cap a promoted team at the best any promoted team has done** | On, no promoted team is projected above the best first FBS season a promoted program has actually had. Off, a program rated far above every previous promotion gets the full credit anyway. | 0 to 1 | 1 |
| **How much a returning offence is worth** | The share of last season's offensive snaps, carries and targets that is back on the roster. It is offence only, because nobody publishes the defensive half. | 0 to 2 | 1 |
| **The cost of a new head coach** | One number for every school that changed head coach. It does not know whether the new man is any good, and there is no term for how long anyone has been in the job. | 0 to 2 | 1 |
| **How much the transfer portal moves a team** | Bodies out minus bodies in, counted rather than rated. Departures are recorded well and arrivals are not, so this term is the weakest thing on the board. | 0 to 2 | 1 |
| **How much home field is worth in August** | A multiplier on the home-field advantage the projection uses to turn ratings into game calls. At 1 it believes last season's fitted value exactly. Above 1 it leans on home field harder, which is the right direction when the ratings themselves are carried over from a season that is finished and are therefore spread wider than this season's truth. | 0 to 2 | 1.5 |
| **Where a blowout stops counting extra** | Winning by 40 is better than winning by 20. Winning by 60 is barely better than winning by 40. This is where the curve flattens; set it as high as you like and margin counts all the way up, or drop it to 1 and beating somebody by 70 is worth about what beating them by 1 is worth. | 1 to no limit | 32 |
| **How much a win is worth on its own** | Points added to the winner for the simple fact of winning, before any margin counts. At 0 this is a scoring-margin ranking. Turn it up and a one-point win starts to look like a comfortable one. | 0 to 12 | 7 |
| **Whether September still counts in December** | At 1 every game counts the same all season, which is what a poll about what you earned should do. Below 1 the season decays and recent form takes over. | 0.5 to 1 | 1 |
| **What sorts the table** | Three different questions, and you pick which one the table answers. Schedule odds asks how hard that season was to survive, and it is what the published poll sorts on. The wins-based resume asks what your record earned against that schedule, which puts every unbeaten team above every team with a loss. The margin-aware resume asks how good the results say you are, which will rank a good team with losses above an unbeaten one. | `schedule_odds`, `L4_resume`, `L4_resume_margin` | `schedule_odds` |
| **Let the model know which conference a team is in** | Off. Nothing in the base model knows what a conference is, and that is the point: conference strength has to be earned on the field and read off the results, never assumed from the letters on the jersey. The switch is published so the refusal is checkable rather than claimed. | 0 to 1 | 0 |

**No human polls, ever.** No AP, coaches or committee ranking may reach any design matrix of either product. They are comparison targets and never fitting targets. There is no lever for this and there will not be one.

**No future data, ever.** Every published number for a given week is computable from games played before it. Walk-forward honesty is not a ceremony here, it is what makes an accuracy figure mean anything.
