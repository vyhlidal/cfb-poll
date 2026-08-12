# Which ordering should be the headline poll?

> **DECIDED, 2026-08-12: candidate C, schedule odds, is the headline ordering.**
> See [`docs/adr/0005-headline-ordering.md`](../adr/0005-headline-ordering.md) for
> the decision, the rationale and what was rejected.
> `[publication].headline_ordering = "schedule_odds"`.
>
> **Not one number in this document changed when that happened, and none may.**
> This file is the evidence as it stood at commit `784ab50`, when nothing on the
> live path read `[schedule_odds]` and the recommendation below was still a
> recommendation. It is deliberately left in that voice: a decision record whose
> evidence has been quietly edited afterwards to agree with the decision is not
> evidence. Everything below still reproduces from the command in the next
> section, and the demos under `demo/` are regenerated from the live pipeline and
> must agree with §5c, §7 and §7a — if they ever stop agreeing, this file is
> right and the pipeline has a bug.
>
> Two statements below are now history rather than fact, and are left standing for
> the same reason: `[publication].headline_layer` was `L4_resume` at the time (it
> is now `C_schedule_odds`), and §11's "nothing in the model package imports it"
> described the state before adoption. `[resume].saturation_tiebreak` is still
> `margin` and still governs the résumé column.

**Status when written: evidence, not a decision.** Nothing in
`configs/default.toml` changed except the addition of a `[schedule_odds]` block
that no live path read. The owner decides after reading this; the study exists so
that the decision is made on numbers.

**Reproduce every table in this document:**

```
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run python scripts/headline_ordering_study.py --out out/ordering-study
```

Runtime is about 25 seconds on a laptop. The script writes `study.json`; every
number below comes out of that file and nothing below was typed by hand.

---

## 0. The question, verbatim

> "It shouldn't matter. If we simulated Liberty vs Georgia as accurately as
> possible who would win? Depending on the year it would likely be Georgia. Does
> schedule odds or margin variant create the most realistic picture? And,
> remember, the new feature to our model is a retroactive reranking that affects
> subsequent polls. If, by week 13 it's clear that Liberty's schedule is actually
> quite tough in weeks 1-5 maybe things change? The problem is, I don't want to
> guess. I want analysis and data to rule our decisions."

Three separable questions live in that paragraph and this document answers them
in order:

1. **Who actually wins Liberty vs Georgia?** That is a prediction question, and
   the model already has a prediction layer. §2.
2. **Schedule odds or margin variant?** Neither existed as a full ordering when
   the question was asked. The margin variant existed as a tie-break; schedule
   odds did not exist at all and was built for this study
   (`src/cfbpoll/model/schedule_odds.py`). §3 through §9 compare them.
3. **Does the retroactive re-ranking rescue the unbeaten case by week 13?** This
   turns out to have a hard structural answer that is not a matter of taste, and
   it is the single most decision-relevant finding in the document. §5.

---

## 1. Methods

### 1.1 The three candidate orderings

All three read their numbers off the **same** objects. For each evaluation cell
the script computes one Power source, one `l4_resume.L4Fit` and one
`schedule_odds.OddsFit`, then derives three rank vectors from them. Any
difference in any table below is a difference between ordering *rules* and cannot
be a difference in data, fit, window, or seed.

| | ordering | rank key | what it claims |
|---|---|---|---|
| **A** | wins-based résumé, margin variant breaks ties among saturated teams only | `(-resume, -resume_margin, team)` | "these results are what a +18.4 team would be expected to produce" |
| **B** | margin-aware résumé for everyone | `(-resume_margin, team)` | the same, scored on compressed margin instead of on wins |
| **C** | schedule odds (new) | `(tail, mid_p, team)` where `tail = P(W >= W_t)` | "a reference-quality team would have gone this well against this schedule with probability P" |

**A is the current behaviour.** It is what `configs/default.toml` produces today.

**C is new.** `model/schedule_odds.py` implements ESPN's Strength-of-Record
sentence literally (report 02 §2.4): fix quality at a published reference `q_ref`,
compute per-game win probabilities `p_g = Φ((q_ref − Power_o + h·s_g)/σ)`, and
take the exact Poisson-binomial upper tail `P(W ≥ W_t)`. Rank key is `−log10(P)`.
The tail is computed by the exact O(n²) convolution, not by Monte Carlo:
`tests/unit/test_schedule_odds.py` property-tests it against brute-force
enumeration of all 2ⁿ outcomes for every n ≤ 12, to 1e-14. **Margin never enters
C**, and that is enforced rather than promised: the module's schedule flattener
carries no margin column at all, and
`test_scores_may_change_freely_if_winners_do_not` scrambles every final score
while preserving every winner and asserts that C is bit-identical while B moves.

### 1.2 One non-candidate reference ordering

Every table also carries **P**, the L3 Power rating itself, ranked directly.
Power is the companion layer and report 02 §3.5 rules it out as the headline on
purpose: a poll ordered by Power answers "who would win", not "who earned it".
It is here because **forward ordering accuracy is a prediction metric**, and
without a pure-prediction reference there is no way to tell whether a résumé
ordering scoring well on that axis is evidence of desert or evidence of having
quietly become a power rating. P is the calibration mark for that axis. It is not
a candidate and must not be read as one.

### 1.3 Data, protocol, surfaces

- Seasons 2021-2024. Tune on 2021-2023, validate on 2024, per report 02 §5.1.
  **2025 is locked and this script never loads it.**
- Opponent quality is L3 (`[resume].power_source = "L3"`), with walk-forward
  blend weights, one Power fit per bucket via `retro.season_power`. No ordering
  ever sees a game the others do not.
- Windows are `(season_type, week)` **buckets ordered by first kickoff**, never
  bare week numbers (docs/data-findings.md §1, binding).
- Two surfaces, produced by the one substitution of report 02 §3.6: **live**
  `R(N, N)` uses through-week-N Power; **hindsight** `R(N, final)` uses
  end-of-season Power with the record still truncated at N.
- Ranks cover FBS teams only, as the published poll does.

### 1.4 Limits that constrain what can be concluded

1. **2021 and 2022 carry no postseason rows at all** in `cfb_schedules_*`
   (docs/data-findings.md, and the derivation block in
   `ingest/sportsdataverse.py`). "Final" for those two seasons means through
   conference championships. Consequences that recur below: those seasons cannot
   appear in the postseason test (§6), and the 2021 Cincinnati case has no
   subsequent result in our data even though Cincinnati played Alabama in the
   Cotton Bowl.
2. **The archive carries no CFP committee poll.**
   `archive/sportsdataverse/ratings/cfb_ratings_weekly_*.csv` is EPA/FEI
   ratings, not committee rankings. Committee ranks in the case table therefore
   come from report 02 §5.5's verified lists, which record the top 5 or 6 for
   2021-2023 and the full top 12 for 2024, and are labelled as such. A blank in
   that column means "not in §5.5's recorded list", never "unranked".
3. **The postseason samples are tiny.** 14 CFP games and 4 non-CFP New Year's Six
   games across both available seasons. Non-CFP bowls have the systematic
   roster-availability problem report 02 §3.8 documents (78+ opt-outs and 431
   portal entries in the 2021-22 postseason; Florida State lost 33 players before
   the 2023 Orange Bowl), which is exactly why `[weights].bowl_non_cfp = 0.25`
   exists. Nothing in §6 should move a decision on its own.
4. **`[margin.prediction_compression]` is configured but not implemented** on any
   model path. §2 therefore computes it explicitly and reports raw and compressed
   predicted margins side by side. On these pairs no margin exceeds the 21-point
   threshold, so the two columns are identical and the gap is currently harmless.

---

## 2. The direct answer to the simulation question

L3 predicted margin on a **neutral field** is `Power_a − Power_b`; win
probability is `Φ(margin / σ)` with `σ = 15.3` (report 02 §3.4, §5.4).
"live final" is the final pre-postseason Power window; "hindsight final" is the
end-of-season Power window.

| season | matchup | surface | Power | Power (opp) | predicted margin | compressed | P(first team wins) |
|---|---|---|---:|---:|---:|---:|---:|
| 2023 | Liberty vs Georgia | live final | 18.72 | 25.95 | −7.23 | −7.23 | **0.318** |
| 2023 | Liberty vs Georgia | hindsight final | 17.89 | 26.05 | −8.16 | −8.16 | **0.297** |
| 2021 | Cincinnati vs Alabama | live final | 27.27 | 31.23 | −3.96 | −3.96 | **0.398** |
| 2021 | Cincinnati vs Alabama | hindsight final | 27.27 | 31.23 | −3.96 | −3.96 | **0.398** |
| 2023 | James Madison vs Michigan | hindsight final | 16.62 | 32.75 | −16.13 | −16.13 | 0.146 |
| 2023 | James Madison vs Georgia | hindsight final | 16.62 | 26.05 | −9.43 | −9.43 | 0.269 |
| 2023 | Liberty vs Oregon | hindsight final | 17.89 | 30.18 | −12.29 | −12.29 | 0.211 |

2021's two rows are identical because 2021 has no postseason bucket, so the live
final and the hindsight final windows are the same window (limit 1 above).

James Madison against each of the 2023 top-10 Power teams, on a neutral field,
end-of-season Power:

| opponent | predicted margin | P(JMU wins) |
|---|---:|---:|
| Michigan | −16.13 | 0.146 |
| Oregon | −13.55 | 0.188 |
| Ohio State | −11.88 | 0.219 |
| Georgia | −9.43 | 0.269 |
| Penn State | −8.91 | 0.280 |
| Oklahoma | −8.13 | 0.298 |
| Texas | −7.26 | 0.318 |
| Notre Dame | −6.97 | 0.324 |
| Alabama | −6.63 | 0.332 |
| Washington | −5.93 | 0.349 |

**The answer.** Georgia by about 8 points on a neutral field, and Liberty wins
that game roughly 3 times in 10. The owner's instinct was right on direction and
right on magnitude. Note also that the model was, if anything, generous to
Liberty: it predicted Oregon by 12.3 in the Fiesta Bowl and Oregon won by 39.

**And the answer settles less than it looks like it does.** The model already
publishes exactly this number. `[publication].companion_layer = "L3_power"` puts
Power beside every team in every poll, with the gap shown, precisely so that "who
would win" always has an on-page answer (report 02 §3.5). If the headline poll is
also ordered by who would win, the project has two power ratings and no résumé,
and the thing that makes it a BCS successor rather than another predictive rating
is gone. The rest of this study is about what the *headline* should be given that
the prediction is already published beside it.

---

## 3. Retrodictive violations

Games in which the ranking places the loser above the winner (report 02 §2.12,
§5.2). Universe is FBS-vs-FBS, which is the evaluation universe of report 02
§5.1.

### 3a. Final ranking against every game of the season

At `N = final` the live and hindsight surfaces are the same cell by construction,
so there is one number per season per ordering.

| season | poll bucket | n games | A | B | C | P (ref) |
|---|---|---:|---:|---:|---:|---:|
| 2021 | 2021-regu-w15 | 732 | **137 (0.1872)** | 154 (0.2104) | 136 (0.1858) | 163 (0.2227) |
| 2022 | 2022-regu-w15 | 734 | **163 (0.2221)** | 165 (0.2248) | 168 (0.2289) | 173 (0.2357) |
| 2023 | 2023-post-w01 | 792 | 151 (0.1907) | 164 (0.2071) | **150 (0.1894)** | 179 (0.2260) |
| 2024 | 2024-post-w01 | 798 | 154 (0.1930) | 168 (0.2105) | **155 (0.1942)** | 189 (0.2368) |

Pooled: tune seasons 2021-2023, A 0.1997 / B 0.2139 / C 0.2011 / P 0.2281.
Validation season 2024, A 0.1930 / B 0.2105 / C 0.1942 / P 0.2368.

### 3b. Pooled over every evaluation week, both surfaces

Each row scores that week's ranking against the games in that week's résumé
window.

| season | surface | A | B | C | P (ref) |
|---|---|---:|---:|---:|---:|
| 2021 | live | 0.1701 | 0.1893 | **0.1674** | 0.2026 |
| 2021 | hindsight | **0.1652** | 0.1863 | 0.1654 | 0.2245 |
| 2022 | live | **0.1884** | 0.1962 | 0.1909 | 0.2319 |
| 2022 | hindsight | **0.1895** | 0.1956 | 0.1912 | 0.2340 |
| 2023 | live | **0.1581** | 0.1777 | 0.1608 | 0.1962 |
| 2023 | hindsight | **0.1580** | 0.1791 | 0.1612 | 0.2095 |
| 2024 | live | **0.1713** | 0.1899 | 0.1727 | 0.2293 |
| 2024 | hindsight | 0.1714 | 0.1867 | **0.1697** | 0.2335 |

**Reading.** A and C are indistinguishable on this axis: they trade the lead
season by season and never differ by more than 0.4 percentage points. **B is
worse than both in all sixteen cells.** P is worst everywhere, by a lot, which is
the expected result and a good sanity check: a pure prediction is not trying to
be consistent with what happened.

This is the axis a "most deserving" poll exists to win, and it says A ≈ C > B.

---

## 4. Forward ordering accuracy

At each live week N from `headline_start_week = 5`, take the ranking R(N,N), then
look at every **future** FBS-vs-FBS regular-season or conference-championship
game between two ranked teams and ask how often the better-ranked team won. All
FBS teams carry a rank under all four orderings, so the game set is identical
across orderings and this is a clean paired comparison.

| season | n future games | A | B | C | P (ref) |
|---|---:|---:|---:|---:|---:|
| 2021 | 2242 | 0.6838 | 0.6918 | 0.6847 | **0.6994** |
| 2022 | 2227 | 0.6655 | 0.6807 | 0.6605 | **0.6911** |
| 2023 | 2299 | 0.6699 | 0.6973 | 0.6681 | **0.7147** |
| 2024 | 2665 | 0.6353 | 0.6623 | 0.6409 | **0.6664** |
| **pooled** | **9433** | 0.6624 | **0.6822** | 0.6626 | **0.6918** |

Tune 2021-2023 (n = 6768): A 0.6730, B 0.6900, C 0.6711, P 0.7018.
Validate 2024 (n = 2665): A 0.6353, B 0.6623, C 0.6409, P 0.6664.
The ordering of the three candidates is the same on tune and on validation.

By evaluation week, pooled across seasons:

| week | n future games | A | B | C | P (ref) |
|---:|---:|---:|---:|---:|---:|
| 5 | 1917 | 0.6307 | 0.6588 | 0.6333 | 0.6672 |
| 6 | 1711 | 0.6523 | 0.6710 | 0.6517 | 0.6809 |
| 7 | 1502 | 0.6698 | 0.6811 | 0.6718 | 0.6911 |
| 8 | 1284 | 0.6651 | 0.6830 | 0.6667 | 0.7033 |
| 9 | 1074 | 0.6741 | 0.7020 | 0.6723 | 0.7086 |
| 10 | 845 | 0.6781 | 0.7101 | 0.6769 | 0.7089 |
| 11 | 607 | 0.7018 | 0.7068 | 0.6936 | 0.7183 |
| 12 | 367 | 0.7057 | 0.7084 | 0.7057 | 0.7112 |
| 13 | 112 | 0.6696 | 0.6696 | 0.6696 | 0.6964 |

Restricting to games where **both** teams are in the ordering's own top 25 makes
the game set differ per ordering, so it is reported for completeness rather than
as a paired test: pooled, A 0.5843 (n=522), B 0.6432 (n=583), C 0.5659 (n=539),
P 0.6557 (n=575).

**Reading, and the caveat that matters more than the numbers.** B wins this axis
by about 2 percentage points over both A and C, consistently, in every season, on
tune and on validation. That is real and it should not be waved away.

But look at where B sits relative to P. On forward accuracy B captures roughly
two thirds of the distance from A to the pure power rating (0.6624 → 0.6822 →
0.6918). On retrodictive violations B moves *away* from A in the direction of P
as well (0.1997 → 0.2139 → 0.2281 on tune). **B is not a better résumé. B is a
worse résumé that has partially turned into a power rating.** That is what
margin does: it is information about quality, and quality is what predicts. The
project already publishes a number that does that job better than B does, beside
every team, every week.

Forward accuracy is a legitimate axis and B genuinely wins it. It is also the one
axis on which the headline poll is not the instrument the project ships for the
purpose.

---

## 5. Retroactive convergence, and the structural finding

### 5a. Mean |rank_live − rank_hindsight| over all ranked FBS teams

Report 02 §5.2 requires this to decline in N, or the retroactive product is
unstable. It declines for all four orderings in all four seasons. A representative
season (2023):

| week | A | B | C | P (ref) |
|---|---:|---:|---:|---:|
| 2023-regu-w05 | 5.31 | 6.26 | 6.15 | 16.12 |
| 2023-regu-w06 | 4.38 | 4.81 | 4.96 | 14.41 |
| 2023-regu-w07 | 3.14 | 3.79 | 3.73 | 11.11 |
| 2023-regu-w08 | 2.56 | 2.75 | 2.80 | 9.68 |
| 2023-regu-w09 | 2.23 | 2.84 | 2.63 | 8.65 |
| 2023-regu-w10 | 1.73 | 1.80 | 1.71 | 7.44 |
| 2023-regu-w11 | 1.23 | 1.43 | 1.22 | 5.50 |
| 2023-regu-w12 | 0.80 | 1.08 | 0.96 | 3.79 |
| 2023-regu-w13 | 0.45 | 0.57 | 0.54 | 1.50 |
| 2023-regu-w14 | 0.44 | 0.56 | 0.57 | 1.19 |
| 2023-regu-w15 | 0.41 | 0.42 | 0.36 | 1.07 |
| 2023-post-w01 | 0.00 | 0.00 | 0.00 | 0.00 |

The full four-season table is in `study.json` under
`study_5_retro_convergence.rows`. The three candidates are within noise of each
other everywhere; P moves three to sixteen times as much, which is the honest
statement that a power rating is a much less stable thing to publish retroactively
than a résumé is.

### 5b. THE STRUCTURAL POINT: what A can and cannot do for an unbeaten team

The owner's self-correction was: *"If, by week 13 it's clear that Liberty's
schedule is actually quite tough in weeks 1-5 maybe things change?"*

**Under A, for an unbeaten team, that mechanism is switched off at the level of
the number, and it is switched off by construction rather than by tuning.**

`E[W|q]` approaches n from below, so an undefeated team has no finite root and the
published bracket `q_bounds = [-60, 60]` is where the estimate is truncated
(`l4_resume.py`, SATURATION; report 02 §2.10). Every unbeaten team therefore lands
on **exactly** +60, whatever it played. +60 is not a function of the schedule, so
it is not a function of the Power window either, so **substituting end-of-season
Power for through-week-N Power cannot change it**. The retroactive mechanism of
report 02 §3.6 is one substitution into `Power_{o_g}`; for a saturated team there
is nothing downstream of `Power_{o_g}` left to move.

Two consequences, both verified in `study_9_boards.unbeaten_floor`:

**(i) Under A no team with a loss can ever be ranked above an unbeaten team, on
either surface, in any season.** Observed count of such inversions under A:

| season | surface | n unbeaten | A: worst unbeaten rank / teams with a loss above it | B | C | P (ref) |
|---|---|---:|---|---|---|---|
| 2021 | live | 1 | #1 / **0** | #4 / 3 | #4 / 3 | #5 / 4 |
| 2021 | hindsight | 1 | #1 / **0** | #4 / 3 | #4 / 3 | #5 / 4 |
| 2022 | live | 2 | #2 / **0** | #2 / 0 | #2 / 0 | #3 / 1 |
| 2022 | hindsight | 2 | #2 / **0** | #2 / 0 | #2 / 0 | #3 / 1 |
| 2023 | live | 4 | #4 / **0** | #15 / 11 | #10 / 6 | #17 / 13 |
| 2023 | hindsight | 4 | #4 / **0** | #15 / 11 | #8 / 4 | #18 / 14 |
| 2024 | live | 1 | #1 / **0** | #2 / 1 | #1 / 0 | #4 / 3 |
| 2024 | hindsight | 1 | #1 / **0** | #2 / 1 | #1 / 0 | #5 / 4 |

Zero, in all eight cells. Not "rare". Zero, and it will be zero forever, because
the ordering makes it impossible.

**(ii) An unbeaten team's rank under A can still move, but only against other
unbeaten teams, and only through the margin tie-break.** Because
`saturation_tiebreak = "margin"`, the second element of A's key is
`resume_margin`, which does depend on Power. So A's unbeaten teams do shuffle
among themselves in hindsight. They cannot cross the boundary. Setting
`saturation_tiebreak = "none"` would remove even that and leave unbeaten teams
ordered alphabetically.

Quantified, restricted to unbeaten teams, weeks ≥ 5, mean live→hindsight rank
movement:

| season | A | B | C | P (ref) |
|---|---:|---:|---:|---:|
| 2021 | 0.431 | 1.837 | 1.565 | 6.445 |
| 2022 | 0.398 | 0.547 | 0.730 | 2.873 |
| 2023 | 0.377 | 0.982 | 1.168 | 3.771 |
| 2024 | 0.375 | 1.674 | 1.861 | 5.431 |
| **pooled** | **0.395** | **1.269** | **1.343** | **4.648** |

B and C move unbeaten teams roughly **3.2x** as far as A does, and the pure
Power reference moves them 12x as far. And in the late
weeks of 2023 the difference is not 3x, it is total:

| week | n unbeaten | A mean/max | B mean/max | C mean/max |
|---|---:|---:|---:|---:|
| 2023-regu-w11 | 7 | 0.00 / 0 | 0.29 / 2 | 0.29 / 1 |
| 2023-regu-w12 | 6 | 0.00 / 0 | 0.17 / 1 | 0.67 / 2 |
| 2023-regu-w13 | 5 | 0.00 / 0 | 0.20 / 1 | 0.20 / 1 |
| 2023-regu-w14 | 4 | 0.00 / 0 | 0.00 / 0 | 0.50 / 2 |
| 2023-regu-w15 | 4 | 0.00 / 0 | 0.00 / 0 | 0.50 / 2 |

From week 11 onward in 2023, **A moves no unbeaten team at all** between the live
and hindsight surfaces. C is the only ordering still moving them in week 15.

### 5c. Liberty 2023, live to hindsight, every week

| week | record | A live→hind | B live→hind | C live→hind | C tail P(W≥W_t) live→hind |
|---|---|---|---|---|---|
| 2023-regu-w01 | 1-0 | 74→55 | 93→55 | 32→22 | 0.9668→0.8028 |
| 2023-regu-w02 | 2-0 | 45→35 | 48→35 | 35→20 | 0.7316→0.6293 |
| 2023-regu-w03 | 3-0 | 29→23 | 30→24 | 29→22 | 0.5934→0.5573 |
| 2023-regu-w04 | 4-0 | 17→16 | 24→19 | 30→25 | 0.7019→0.5230 |
| 2023-regu-w05 | 4-0 | 14→14 | 20→18 | 27→26 | 0.6142→0.5230 |
| 2023-regu-w06 | 5-0 | 13→13 | 25→24 | 21→22 | 0.4723→0.4875 |
| 2023-regu-w07 | 6-0 | 10→10 | 19→19 | 18→16 | 0.3560→0.3299 |
| 2023-regu-w08 | 7-0 | 9→8 | 23→20 | 15→14 | 0.2824→0.2932 |
| 2023-regu-w09 | 8-0 | 7→7 | 17→18 | 10→11 | 0.1564→0.1981 |
| 2023-regu-w10 | 9-0 | 7→6 | 17→17 | 12→12 | 0.1570→0.1878 |
| 2023-regu-w11 | 10-0 | 6→6 | 15→15 | 11→11 | 0.1469→0.1630 |
| 2023-regu-w12 | 11-0 | 6→6 | 14→15 | 12→12 | 0.1113→0.1563 |
| 2023-regu-w13 | 12-0 | 5→5 | 16→15 | 12→11 | 0.1317→0.1370 |
| 2023-regu-w14 | 13-0 | **4→4** | 15→15 | **10→8** | 0.1004→0.1074 |
| 2023-regu-w15 | 13-0 | **4→4** | 15→15 | **10→8** | 0.0946→0.1074 |
| 2023-post-w01 | 13-1 | 10→10 | 17→17 | 11→11 | 0.1566→0.1566 |

Liberty finishes the regular season at **#4 under A** (the study reproduces the
figure in the brief), **#15 under B**, **#10 live / #8 hindsight under C**.

The week-13 self-correction the owner described **does fire under C**: Liberty
gains two spots when the season's answers about its opponents are substituted in.
It fires zero times under A from week 11 onward. And note the direction: the
hindsight tail is *higher* than the live tail (0.0946 → 0.1074), meaning
end-of-season Power judged Liberty's schedule slightly **easier** than the live
ratings did. Liberty still rises two places because the teams around it were
re-judged more harshly still. That is the retroactive product doing exactly what
it was built to do, and it is only visible on an ordering that has somewhere to
move.

---

## 6. The postseason test

Final pre-postseason **live** ranking, scored on games that were never in any fit.
2023 and 2024 only (limit 1).

| season | segment | n | A | B | C | P (ref) |
|---|---|---:|---:|---:|---:|---:|
| 2023 | CFP | 3 | 3 (1.000) | 2 (0.667) | 2 (0.667) | 2 (0.667) |
| 2023 | NY6 non-CFP | 4 | 1 (0.250) | 2 (0.500) | 2 (0.500) | 2 (0.500) |
| 2023 | bowls non-CFP | 39 | 17 (0.436) | 17 (0.436) | 18 (0.462) | 17 (0.436) |
| 2023 | all postseason | 42 | 20 (0.476) | 19 (0.452) | 20 (0.476) | 19 (0.452) |
| 2024 | CFP | 11 | 6 (0.545) | 7 (0.636) | 5 (0.455) | 8 (0.727) |
| 2024 | NY6 non-CFP | 0 | — | — | — | — |
| 2024 | bowls non-CFP | 35 | 22 (0.629) | 19 (0.543) | 21 (0.600) | 19 (0.543) |
| 2024 | all postseason | 46 | 28 (0.609) | 26 (0.565) | 26 (0.565) | 27 (0.587) |
| **pooled** | CFP | 14 | 0.643 | 0.643 | 0.500 | 0.714 |
| **pooled** | NY6 non-CFP | 4 | 0.250 | 0.500 | 0.500 | 0.500 |
| **pooled** | bowls non-CFP | 74 | 0.527 | 0.486 | 0.527 | 0.486 |
| **pooled** | all postseason | 88 | 0.545 | 0.511 | 0.523 | 0.523 |

2024 has zero non-CFP New Year's Six games because in the 12-team era all six NY6
bowls were CFP quarterfinals or semifinals.

**This axis decides nothing and should not be quoted as if it did.** Fourteen CFP
games and four NY6 games cannot separate orderings whose true rates differ by a
few points. One extra correct CFP pick moves a season's rate by 7 to 33 points.
Non-CFP bowls (n = 74, the only segment with a usable count) are near a coin flip
for every ordering including the pure power rating, which is what
`[weights].bowl_non_cfp = 0.25` and report 02 §3.8 already predicted: those games
measure something other than team quality. The honest summary of §6 is **no
signal**, and it will stay that way until several more seasons accumulate.

---

## 7. Case table

Ranks at each season's final pre-postseason poll bucket, live / hindsight.
Committee column is report 02 §5.5's verified CFP releases; a dash means "not in
§5.5's recorded list" (limit 2), not "unranked".

| season | team | record | A | B | C | P (ref) | committee | what happened next |
|---|---|---|---|---|---|---|---|---|
| 2023 | Liberty | 13-0 | **4 / 4** | 15 / 15 | **10 / 8** | 17 / 18 | — | L 6-45 vs Oregon (Fiesta) |
| 2023 | James Madison | 11-1 | 12 / 13 | 19 / 19 | 14 / 14 | 23 / 24 | — | L 21-31 vs Air Force |
| 2021 | Cincinnati | 13-0 | **1 / 1** | 4 / 4 | 4 / 4 | 5 / 5 | **4** | no data (limit 1) |
| 2022 | Tulane | 11-2 | 11 / 11 | 16 / 16 | 12 / 12 | 19 / 19 | — | no data (limit 1) |
| 2024 | Army | 11-2 | 15 / 15 | 19 / 19 | 17 / 18 | 27 / 27 | — | W 27-6 vs Louisiana Tech |
| 2024 | Boise State | 12-1 | 4 / 4 | 9 / 10 | 4 / 4 | 14 / 15 | **9** | L 14-31 vs Penn State |

Two cases carry real information.

**Cincinnati 2021.** A puts a 13-0 Cincinnati at **#1**, ahead of Alabama,
Georgia and Michigan, purely because it is the only unbeaten team in the country.
B and C both put it at **#4**, behind exactly those three. The committee also put
it at #4. That is a coincidence worth noticing and not a target: report 02 §5.5 is
explicit that fitting toward committee agreement would reintroduce human poll bias
through the back door. What it does show is that A's #1 is a position no
independent judge reached, and it is a position A was *forced* into.

**Boise State 2024.** A and C agree at #4, the committee said #9, and Boise State
then lost by 17 to Penn State. Here A and C are both more generous than the
committee was, and both look wrong after the fact. Neither ordering has an
advantage in this case, and it is a useful reminder that "our number and the
committee's disagree" does not tell you which one was right.

### 7a. The 2023 board, which is the argument in one picture

Final pre-postseason live ranking. `*` marks an unbeaten team.

| # | A (current) | B (margin) | C (schedule odds) |
|---:|---|---|---|
| 1 | Michigan (13-0)* | Michigan (13-0)* | Washington (13-0)* |
| 2 | Florida State (13-0)* | Ohio State (11-1) | Michigan (13-0)* |
| 3 | Washington (13-0)* | Oregon (11-2) | Florida State (13-0)* |
| 4 | **Liberty (13-0)*** | Georgia (12-1) | Alabama (12-1) |
| 5 | Ohio State (11-1) | Texas (12-1) | Texas (12-1) |
| 6 | Alabama (12-1) | Penn State (10-2) | Ohio State (11-1) |
| 7 | Texas (12-1) | Florida State (13-0)* | **Georgia (12-1)** |
| 8 | **Georgia (12-1)** | Washington (13-0)* | Ole Miss (10-2) |
| 9 | Ole Miss (10-2) | Alabama (12-1) | Oregon (11-2) |
| 10 | Oregon (11-2) | Oklahoma (10-2) | **Liberty (13-0)*** |
| 11 | Missouri (10-2) | Notre Dame (9-3) | Missouri (10-2) |
| 12 | James Madison (11-1) | **Kansas State (8-4)** | Oklahoma (10-2) |
| 13 | Penn State (10-2) | LSU (9-3) | Penn State (10-2) |
| 14 | Oklahoma (10-2) | Missouri (10-2) | James Madison (11-1) |
| 15 | LSU (9-3) | **Liberty (13-0)*** | LSU (9-3) |
| … | | | |
| 23 | Oklahoma State (9-4) | **Texas A&M (7-5)** | NC State (9-3) |

B's board contains **Kansas State at 8-4 ranked twelfth** and **Texas A&M at 7-5
ranked twenty-third**, above an 11-1 James Madison and a 13-0 Liberty. That is not
a marginal defect, it is what the ordering is for: `resume_margin` rewards winning
big and losing close, so a team that got blown out by nobody and blew out several
people outranks a team that simply kept winning. A poll whose promise is "who
earned it" cannot put a 7-5 team at #23 ahead of an 11-1 team and expect to
survive contact with a reader.

C's board keeps all four unbeaten teams in the top ten, puts Georgia at #7 ahead
of Liberty at #10, and has no record on it that requires an explanation.

---

## 8. Stability

Week-over-week rank churn on the live surface, mean |rank_N − rank_{N−1}|, weeks
≥ 5, over all ranked FBS teams and over the top 25.

| season | A all / top25 | B all / top25 | C all / top25 | P (ref) all / top25 |
|---|---:|---:|---:|---:|
| 2021 | 6.16 / 4.27 | 5.21 / 4.60 | 6.20 / 4.36 | 5.36 / 4.60 |
| 2022 | 6.45 / 3.83 | 4.97 / 3.48 | 6.47 / 4.04 | 5.07 / 4.46 |
| 2023 | 5.96 / 4.00 | 4.83 / 2.89 | 5.94 / 4.07 | 4.90 / 2.87 |
| 2024 | 6.31 / 4.90 | 5.11 / 3.72 | 6.37 / 4.90 | 5.05 / 3.42 |
| **pooled** | **6.22 / 4.26** | **5.03 / 3.67** | **6.25 / 4.36** | 5.09 / 3.83 |

B is the calmest ordering, by about 1.2 places overall and 0.6 in the top 25. A
and C are indistinguishable and both churn more.

This is a real advantage for B and it has a real cause: margin is a smoother
signal than a win, so a rating built on it moves less when a single game flips.
It is also, again, the thing that makes B behave like a power rating: P churns
almost exactly as little as B does (5.09 vs 5.03). Low churn is a virtue in a
predictive rating and an ambiguous one in a poll whose whole subject matter is
what changed last Saturday.

---

## 9. Practicality: does C's `q_ref` choice matter?

`q_ref` is the one free constant in C. Default is `power_rank_25`, the Power
rating of the 25th-ranked Power team that week, which is the least flattering
defensible reading of ESPN's "average Top-25 team" and is a single team that can
be named in the artifact each week (`schedule_odds.QRef` publishes the name).

| season | `power_rank_25` (team) | `mean_top_25` | `power_rank_10` (team) | `mean_fbs` |
|---|---|---:|---|---:|
| 2021 | 17.54 (Houston) | 22.29 | 21.82 (Ole Miss) | 8.34 |
| 2022 | 11.98 (South Alabama) | 17.79 | 18.45 (Texas) | 5.51 |
| 2023 | 15.99 (Tennessee) | 22.06 | 23.38 (Washington) | 6.79 |
| 2024 | 13.49 (Kansas) | 18.08 | 18.69 (Tennessee) | 5.69 |

The alternatives span roughly 16 points of reference quality, from a
league-average team to a top-10 team. Against the default ordering:

| season | alternative | mean rank delta | max | Kendall tau | top-25 membership changes |
|---|---|---:|---:|---:|---:|
| 2021 | mean_top_25 | 0.60 | 3 | 0.9897 | 0 |
| 2021 | power_rank_10 | 0.52 | 3 | 0.9909 | 0 |
| 2021 | mean_fbs | 0.86 | 6 | 0.9850 | 1 |
| 2022 | mean_top_25 | 0.58 | 4 | 0.9901 | 0 |
| 2022 | power_rank_10 | 0.63 | 4 | 0.9894 | 0 |
| 2022 | mean_fbs | 0.75 | 3 | 0.9873 | 1 |
| 2023 | mean_top_25 | 0.63 | 3 | 0.9904 | 1 |
| 2023 | power_rank_10 | 0.74 | 3 | 0.9884 | 1 |
| 2023 | mean_fbs | 0.78 | 4 | 0.9870 | 0 |
| 2024 | mean_top_25 | 0.54 | 4 | 0.9915 | 1 |
| 2024 | power_rank_10 | 0.67 | 4 | 0.9888 | 1 |
| 2024 | mean_fbs | 0.79 | 4 | 0.9863 | 0 |

Kendall tau never drops below 0.985, the mean rank change never reaches one
place, and at most one team enters or leaves the top 25. The cases:

| season | team | `power_rank_25` | `mean_top_25` | `power_rank_10` | `mean_fbs` |
|---|---|---:|---:|---:|---:|
| 2021 | Cincinnati | #4 (P=0.0139) | #2 (P=0.0601) | #2 (P=0.0531) | #4 (P=1.6e-04) |
| 2022 | Tulane | #12 (P=0.139) | #12 (P=0.446) | #11 (P=0.488) | #12 (P=0.0143) |
| 2023 | James Madison | #14 (P=0.180) | #14 (P=0.486) | #14 (P=0.558) | #14 (P=0.00919) |
| 2023 | **Liberty** | **#10** (P=0.0946) | **#8** (P=0.297) | **#8** (P=0.354) | **#12** (P=0.00399) |
| 2024 | Army | #17 (P=0.256) | #16 (P=0.523) | #16 (P=0.561) | #19 (P=0.0264) |
| 2024 | Boise State | #4 (P=0.0528) | #4 (P=0.175) | #4 (P=0.199) | #4 (P=0.00209) |

**Verdict on practicality: the constant is safe.** The probability *values* move
by orders of magnitude, which is expected and is why the value is published rather
than the rank alone. The *ordering* barely notices. Liberty spans #8 to #12 across
a 16-point swing in the reference, and never reaches Georgia at #7 under any
choice. C also inherits the invariance that makes the résumé's zero point
harmless: shift every Power rating by a constant and every rank-derived `q_ref`
shifts with it, so no probability moves at all
(`test_ordering_is_invariant_to_a_constant_shift_of_power`). Only the `fixed`
method breaks that, which is why it is not the default.

---

## 10. Recommendation

### 10.1 Axis by axis, what the data says

| axis | winner | margin | confidence |
|---|---|---|---|
| Retrodictive violations, final ranking | **A ≈ C** | A and C trade the lead by season; both beat B by 1.3-1.8 pp | high, n ≈ 3,056 games |
| Retrodictive violations, all weeks, both surfaces | **A ≈ C** | B worse in 16 of 16 cells | high |
| Forward ordering accuracy | **B** | +2.0 pp over A and C, every season, tune and validate | high, n = 9,433 |
| Postseason (CFP / NY6 / bowls) | **none** | n = 14 / 4 / 74 | none. Do not use this axis |
| Retro-convergence, all teams | **tie** | all three decline monotonically, within noise of each other | high |
| Retro-convergence, unbeaten teams | **C ≳ B ≫ A** | C 1.34, B 1.27, A 0.395 places; A is exactly 0.00 from wk 11 in 2023 | structural, not statistical |
| Case plausibility (2023 board) | **C** | B ranks 8-4 Kansas State #12 and 7-5 Texas A&M #23 | qualitative but stark |
| Week-over-week stability | **B** | 5.03 vs 6.22 (A) and 6.25 (C) overall | high |
| `q_ref` practicality (C only) | **safe** | tau ≥ 0.985, ≤ 1 top-25 change across a 16-point q_ref swing | high |

### 10.2 Where the axes disagree, and what that disagreement means

They disagree in exactly one direction and it is not subtle. **B wins the two
axes that reward being a good predictor (forward accuracy, stability) and loses
the axis that rewards being a good résumé (retrodictive violations), and on both
counts it moves toward the pure Power reference.** A and C win the résumé axis,
lose the prediction axes, and stay far from Power.

That is not a mixed result. It is a coherent result that says: margin makes a
rating better at what Power is already for.

The genuine disagreement is between **A and C**, and it is narrower than it looks.
They are statistically tied on retrodictive violations, statistically tied on
convergence for the league as a whole, and tied on stability. **They differ on
exactly one thing: what happens to an unbeaten team.** Under A the answer is
"nothing can happen, ever". Under C the answer is a finite, ordered, movable
number.

### 10.3 What the owner is actually choosing between

Not "which ordering is more accurate". The three are close enough on every
measurable axis that accuracy is not the deciding input. The choice is:

**Choose A** if the poll's promise is *"win them all and you are ahead of every
team that did not"*. That is a legitimate and defensible promise, it is the
oldest promise in the sport, and A delivers it as a theorem rather than as a
tendency. The price is stated plainly: the retroactive re-ranking feature, which
is described as the project's most differentiated product, **does not function for
unbeaten teams** and cannot be made to. If by week 13 it becomes clear that
Liberty's September schedule was tough, A cannot say so, and if it becomes clear
that it was soft, A cannot say that either. In 2023 that means a 13-0 Liberty is
#4, ahead of a 12-1 Georgia that the model itself says would beat Liberty 70% of
the time, and no amount of subsequent evidence can move it. A also produced the
only ranking in this study that no independent judge reached: Cincinnati #1 in
2021.

**Choose C** if the poll's promise is *"the harder it was to do what you did, the
higher you go"*. C is tied with A on the one axis a résumé exists to win, keeps
every unbeaten team in the top ten in every season examined, and is the only
candidate under which the owner's own week-13 self-correction actually fires
(Liberty +2 in hindsight, 2023, weeks 14-15, where A moves nothing). It answers
the simulation question the same way the simulation does, using only who you
played, where, and whether you won. Margin never touches it, so the "you're
ignoring that they got blown out" complaint keeps the same answer it has today:
look at the Power column. The price: an unbeaten team can finish behind a one-loss
team, which will require explaining, and there is one published constant (`q_ref`)
that A does not have, though §9 shows it barely matters.

**Do not choose B as the headline.** It loses the résumé axis outright, its
advantages are advantages of a power rating that the project already publishes
beside every team, and its 2023 board ranks a 7-5 team 23rd and an 8-4 team 12th
above an 11-1 and a 13-0. B should stay exactly where it is: published in the
same table as the second variant, and used as A's tie-break among saturated
teams, which is the one job for which its smoothness is useful and its
"deserve" defects are invisible.

### 10.4 Where this study is weak

Stated so the recommendation is not read as stronger than it is.

- Four seasons. The forward-accuracy gap between B and the other two (2 pp on
  9,433 games) is comfortably significant; the gap between A and C on violations
  (0.1 to 0.5 pp) is not, and this document does not claim it is.
- The postseason axis is unusable at current sample sizes and 2021-2022 cannot
  contribute to it at all.
- 2024 is the validation season and every conclusion above holds on it with the
  same sign, but 2024 was consulted once, in the same pass, and should not be
  consulted again for a re-tune.
- 2025 is untouched.
- No bootstrap intervals anywhere: `model/bootstrap.py` is still a stub, so this
  study reports point estimates and sample sizes and leaves the reader to judge.

---

## 11. What was built, and what it does not do

`src/cfbpoll/model/schedule_odds.py` is a pure, deterministic, standalone module.
It imports `PowerSource` from `l4_resume` and nothing else from the model
package; nothing in the model package imports it. `configs/default.toml` gained a
`[schedule_odds]` block that no live path reads. `cfbpoll rank`, `cfbpoll
backtest` and the retroactive grid are byte-for-byte unaffected, and the 195
pre-existing tests still pass alongside the 41 new ones.

Adopting C later is a small change with a known shape: `retro.cell` would call
`schedule_odds.fit` beside `l4_resume.fit`, `publish/poll.py` would gain the
`odds_key`, `tail_p` and `q_ref` columns, and `[publication].headline_layer`
would name it. Nothing in the résumé, the Power blend, or the retroactive
substitution would change, because C depends on opponent quality through exactly
the same single channel the résumé does.
