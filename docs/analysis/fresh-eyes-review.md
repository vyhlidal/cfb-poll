# Fresh Eyes, Phase 3: Independent Review

**Reviewer:** brought in cold, no prior exposure to this project or its research corpus.
**Method:** an independent design was written first and committed to
[`fresh-eyes-phase1-independent-design.md`](./fresh-eyes-phase1-independent-design.md)
**before any source file was opened**, so that agreement between the two can be read as
convergence rather than absorption. Only then was the implementation examined, run, and
measured.

**What I ran:** the full test suite; `cfbpoll rank --season 2023 --through-week 10`; a
conference-bridge inventory over 2021-2024; a matched-units standard-error calculation on
the 2023 schedule graph; and a 300-draw parametric bootstrap of the headline ordering.
Every number below that is not attributed to a repo document was computed during this
review.

**Repo state note.** HEAD is `784ab50`. A concurrent session is switching the headline from
the wins-based résumé to schedule odds; `configs/default.toml`, `model/retro.py`,
`model/schedule_odds.py` and `publish/poll.py` were mid-edit during this audit. At HEAD the
suite is green. In the working tree four tests fail and `retro._finalize` is called with one
argument against a two-argument definition — both are in-flight artifacts of that switch,
not findings about the design, and they are listed once at the end rather than mixed into
the substantive findings.

---

## Verdict

**Publishable with fixes. Not publishable this week.**

The modelling core is real, careful, and in several specific respects better than the public
systems it benchmarks against. The *publication apparatus* around it is not ready, and two
of its gaps are the kind that a hostile reader converts into a headline within an hour.

The single sentence version: **this project has built a good rating system and has not yet
built the honesty machinery it promises on the tin.** The constraint auditor that guarantees
the constitution raises `NotImplementedError`. The rank intervals that the config turns on
and the docstrings call "the single most honest thing a computer poll can do" are a stub.
And the demo announces that the publication gate passes when the harness object it was
generated from records `"passed": false`.

None of those is a modelling error. All three are shipping-readiness errors, and all three
are fixable in days rather than months.

---

## 1. Phase 1 versus the build: divergence table

| # | Question | My Phase 1 design | What is built | Who is right |
|---|---|---|---|---|
| 1 | Week windows | Predicted week-numbering traps; said a bare `week <= N` filter is a bug | `ingest/windows.py`: buckets = (season_type, week) ordered by **first kickoff**, with the 2023 postseason week-1-and-11-15 collision documented | **Them, decisively.** Better than my sketch and better than most public systems |
| 2 | FCS handling | Model FCS teams individually, hierarchically shrunk; pooling is unacceptable | Individual coefficients under the same ridge penalty; pooling explicitly rejected; FCS-vs-FCS coverage verified (635 games in 2023) | **Agreement.** I predicted they would pool. They did not |
| 3 | Margin saturation | Robust (Student-t) likelihood; hard caps are an avoidable attack surface | `s = C·tanh(m/C) + β_w·sign(m)`, C = 24 | **Them on the cap question** (tanh beats a cap), **me on the estimand** — compressing the response changes what is being estimated and forces a linearisation back to points |
| 4 | Garbage time | Continuous win-probability taper, not a step function | Hard Connelly thresholds (43/37/29/22). The continuous `leverage` mode is in the config and raises `NotImplementedError` | **Me**, and they agree in the docstring; it is deferred because a WP model of their own does not exist yet |
| 5 | Pace / tempo | Heteroskedastic σ as a function of possessions; neutral-state tempo | Per-play efficiency (L1) handles the level; **σ is a single global constant** | **Me.** Nothing in the system varies game variance with pace or total |
| 6 | Opponent adjustment | Ridge / mixed model, simultaneous offense and defense, unpenalised intercept and HFA | Exactly that, at two levels (play and game), Cholesky on formed normal equations, deterministic folds | **Agreement**, and their implementation is cleaner than my sketch |
| 7 | CV grouping | Group on game, never on play | `cv_group = "game_id"`, deterministic round-robin, emphatic docstring | **Agreement.** I predicted they would get this wrong. They did not |
| 8 | Connectivity | Effective resistance; expected G5-vs-P4 contrasts to carry **2-2.5×** the uncertainty of P4-vs-P4 | Connected-component count only | **Them on the substance, me on the diagnostic.** See §4 — my 2-2.5× prediction was wrong, and their implicit assumption was right. But the diagnostic they ship saturates at "1 component" from week 5 and answers nothing |
| 9 | Deserve estimand | Binary W/L primary; opponent quality from a **separate W/L-only** fit so the two surfaces are genuinely independent | Schedule odds is W/L for the ranked team, but opponent quality is L3 (margin-derived) and q_ref is read off L3 | **Me.** The two published surfaces share their entire difficulty scale |
| 10 | `q_ref` | Name it as the biggest hidden assumption; publish a weekly sweep | Named, published on every row **with the team it came from**, four methods implemented, sensitivity measured across a 16-point swing | **Them, emphatically.** This is better than anything public. It is also, per §5-S4, sensitivity analysis pointed at the wrong parameter |
| 11 | Bowls / opt-outs | Down-weight or exclude from power; never let a bowl revalue September | `bowl_non_cfp = 0.25`; final poll excludes non-CFP bowls | **Agreement on the rule**, **me on the gap**: the exclusion is not applied to the hindsight Power window, so it does revalue September (S8) |
| 12 | Injuries / FSU | Power must be *capable of disagreeing* — recency, or break detection, or a state space | `recency_gamma = 1.0` (off by default), no break detection, variant B deferred | **Me.** Power is a season-constant estimate. See §6 |
| 13 | Retroactivity | R(N,K) with K ≥ N; hindsight must never score prediction accuracy; hyperparameters walked forward | Exactly that, K ≥ N enforced in code, one Power fit per column, **blend weights walked forward inside the grid** | **Agreement**, and their §3.6 construction is cleaner than mine |
| 14 | Uncertainty | Credible intervals on both surfaces; rank intervals; leave-one-game-out influence | `publish_rank_intervals = true` in config; `model/bootstrap.py` is a stub | **Me.** Nothing published carries an error bar |
| 15 | Bootstrap validity | Naive resampling of games is **invalid** on a network; use parametric-on-fixed-schedule or block-by-week | The stub's docstring specifies "resample games with replacement, refit" | **Me**, and this matters because it is not yet built — cheap to fix now, expensive later |
| 16 | Baselines | SRS/Colley/Elo are a low bar; report against the closing spread | SRS, Colley, Elo, win %, home-team, **and the random walker** — including a docstring saying it might beat them | **Split.** Their baseline set is better than mine except for the market, which is absent |
| 17 | EP model | Instruments may be pre-fit on prior seasons; team states may not | Own EP model fitted on the **training window** (zero leakage), shipped `EPA` column used only as a named diagnostic (r = 0.847) | **Them.** Stricter than I asked for, and the discipline is real |

**Scorecard on my five advance predictions:** two landed (deserve is fed margin-derived
opponent quality; σ is a single unfitted constant). Three missed (FCS pooling, hard margin
cap, play-level CV grouping). A build that beats three of five cold predictions from a
hostile reviewer is not a naive build.

---

## 2. What is genuinely better than the public systems

Stated first, because the findings list is long and it would otherwise mislead.

1. **`ingest/windows.py`.** Ordering week buckets by first kickoff instead of trusting the
   feed's week integer. The 2023 postseason genuinely contains both week 1 (42 bowls) and
   weeks 11-15 (the FCS bracket); 48-54 games per season carry a December date under
   `week = 1`. A `week <= N` filter leaks January into November. This is a real leakage
   vector that most public systems either do not hit or do not talk about, and it is closed
   here by construction rather than by a guard.
2. **`docs/data-findings.md`.** 4,810 byte-identical duplicate play rows in 2021; 15,353
   orphan plays across 86 game IDs; `score_pts = -8` on a kickoff-return touchdown;
   summing the shipped score column reconciles to the official final in only 429 of 792
   games. This is forensic work that essentially nobody does in public, and every item is
   pinned by a test.
3. **Own expected-points model rather than the shipped `EPA` column**, with the shipped
   column surviving only inside a function that names it in its own signature. The
   temptation was one column away and it was refused. That is the single clearest signal in
   the repository that the constitution is meant seriously.
4. **Individual FCS coefficients**, justified from measured FCS-vs-FCS coverage rather than
   asserted. Correct on the merits and it buys ~120 extra graph edges a year.
5. **Out-of-sample calibration for every system including the baselines**, with the cost of
   the alternative measured (0.44 MAE for L2, and it inverts the ordering against Elo).
   Public head-to-head comparisons almost never do this, and it is the difference between a
   baseline table and theatre.
6. **The R(N, K) grid as a first-class object**, with `movers` and the divergence curve
   falling out of it for free. The published divergence curve declining monotonically from
   5.31 to 0.41 mean absolute rank change across 2023 is a genuinely novel public artifact
   and it is a self-critique instrument, which is rarer still.
7. **Determinism engineering** — `math.fsum`, sorted keys everywhere, no RNG on the model
   path, `SeedSequence.spawn` specified so results do not depend on core count, fixed-length
   bisection. Reproducibility is designed in, not retrofitted.
8. **Holdout locking** with an explicit flag that no code path passes, and a docstring that
   says what must be announced publicly if it is ever unlocked.
9. **Publishing the evidence against your own choice.** The headline-ordering study reports
   that the adopted ordering C is *worse* on forward accuracy than the Power rating printed
   beside it (0.6626 vs 0.6918) and worse than the rejected candidate B, and says so. §10.4
   ("where this study is weak") explicitly declines to claim significance for the A-vs-C
   gap. That is unusual and it should be preserved under pressure.
10. **`q_ref` published with the name of the team it came from.** A reader can check the
    constant against the same week's poll. I asked for a sweep in Phase 1; they built the
    sweep *and* made the constant auditable against a nameable team.

---

## 3. Findings by severity

Each carries a falsifiable test the existing harness could run.

### S1 — BLOCKING. The demo says the publication gate passes. The harness says it does not.

`demo/backtest-2021-2023.md` states: "**The résumé clears the gate the L2-only build
missed.**" The gate object in `demo/backtest-2021-2023.json`, generated by the same run,
records for every system including the résumé:

```
"passed": false,  "mae": false,  "rmse": false,
"su_accuracy": false,  "calibration": false,
"violations_vs_baselines": true      (résumé, Colley and win% only)
```

Against the config's own thresholds, on the tune seasons, weeks 5+: SU accuracy 69.21% vs
`su_accuracy_min = 0.70`; MAE 13.019 vs `mae_max = 12.8`; RMSE 16.549 vs `rmse_max = 15.8`;
max calibration deviation 9.17 pp vs `calibration_max_decile_deviation_pp = 5.0`. **Four of
the five decidable criteria fail.** The one that passes is the retrodictive-violations
comparison — and `violations_must_beat = ["colley", "srs"]` omits **win percentage**, which
at 0.1769 beats the résumé's 0.1936 and every other system in the table.

The demo does disclose the win-percentage result and calls it "the price of caring who you
played," which is the correct defence. But the summary sentence a reader carries away is
"clears the gate," and that sentence is not what the harness computed.

> **Test.** Add an assertion to the demo generator that the narrative claim equals
> `systems[headline].gate.passed`, and fail the build when they disagree. Separately, add
> `winpct` to `[gate].violations_must_beat` and re-run; if the intent is that a resume
> metric need not beat win percentage on retrodiction, say so in the gate's own definition
> rather than by omission from a list.

### S2 — BLOCKING. Constraint enforcement is unimplemented while the config asserts it is enforced.

`configs/default.toml` sets `[constraints].fail_build_on_banned_feature = true`.
`docs/constraints.md` states the banned-input table is "enforced by
`cfbpoll audit-features --fail-on-banned` in both the weekly and reproducibility workflows."
Both workflows do call it. And:

- `validate/leakage.py::audit` → `raise NotImplementedError(...)`
- `cli.py::audit_features` → `_stub(...)` → raises

So the mechanism that guarantees no banned feature ever reaches a design matrix does not
exist, and `weekly.yml` would abort at step "audit features" before it ever ranked anything.
By inspection the model path is clean — the allow-listed columns are the only ones that
reach `design.py` — but "by inspection" is exactly what the allow-list was built to replace,
and the project's central promise is that a reader does not have to take inspection on
trust.

`validate/data_quality.py`, `publish/release.py`, `publish/site.py`, `publish/postgres.py`,
`publish/files.py::write_run` and `ingest/archive.py` are stubs on the same footing. The
weekly pipeline as written cannot run end to end.

> **Test.** Run the `weekly.yml` step sequence locally against 2023 and assert exit 0. Then
> plant a `home_pregame_elo` column into the L2 frame and assert `audit-features` exits
> non-zero.

### S3 — BLOCKING for the stated product. Nothing published carries uncertainty, and the bootstrap that is specified is the wrong one.

`publish_rank_intervals = true  # every week, forever`. `model/bootstrap.py` is a stub. The
headline-ordering study says so itself: "No bootstrap intervals anywhere ... this study
reports point estimates and sample sizes and leaves the reader to judge."

I computed what those intervals look like. **Parametric bootstrap, 300 draws, 2023 through
week 10, schedule held fixed, the fitted L2 Power ratings treated as truth, margins redrawn
from N(μ_g, 15.3²), refit and re-ranked each draw:**

| Team | Published rank | Bootstrap median | 90% rank interval |
|---|---|---|---|
| Ohio State | 1 | 4 | **#1 – #18** |
| Washington | 2 | 13 | **#2 – #49** |
| Florida State | 3 | 9 | **#2 – #31** |
| Alabama | 4 | 13 | **#1 – #41** |
| **James Madison** | **6** | **20** | **#4 – #52** |
| Georgia | 8 | 13 | #3 – #39 |
| Michigan | 11 | 9 | #4 – #24 |
| Liberty | 17 | 24 | #6 – #56 |
| Tulane | 22 | 33 | #7 – #74 |

P(James Madison in the top 10) = **0.22**. P(top 25) = 0.63.

Two things follow. First, the ordering's published ranks are far more precise-looking than
they are. Second — and this is the sharper point — **the bootstrap median is worse than the
published rank for nearly every undefeated team**, because under the model's own estimate of
these teams' quality, going 9-0 is an unlikely outcome. The headline ordering is, by
construction, a ranking of *how improbable your record was*, which means it systematically
promotes teams whose record was improbable **including for reasons of luck**. That is
defensible as a definition of desert and it is indefensible if published without an interval.

Separately: the stub's docstring specifies "Resample games with replacement, refit." That is
invalid here. Games are edges in the schedule graph, not exchangeable observations;
resampling them with replacement can disconnect the graph and can leave a team with zero
games, destroying exactly the connectivity structure whose uncertainty is being measured.
The schedule was fixed years in advance and is not random. The correct object is a
parametric bootstrap on the fixed schedule (what I ran above) or a block bootstrap by week.

> **Test.** Implement the parametric bootstrap and publish the interval. Then implement the
> naive game-resampling version as a comparison and report, over 1000 draws, the fraction of
> draws in which the graph has more than one component or some FBS team has zero games. If
> that fraction is materially above zero, the naive scheme is disqualified on its own output.

### S4 — MAJOR. The sensitivity analysis measures the one constant that does not move the ranking, and omits the ones that do.

The study's §9 is excellent work: four `q_ref` methods, a 16-point swing in reference
quality, Kendall's tau never below 0.985, mean rank change never one full place. The
conclusion — "the constant is a convention, not a dial" — is correct.

It is also, for that reason, the least interesting sensitivity in the system. Measured on
2023 through week 10, James Madison's headline rank under variations that are **not**
published as sensitivities:

| Variation | JMU rank | Tail probability |
|---|---|---|
| baseline (q_ref = power_rank_25, σ = 15.3, L3 power, in-sample blend) | #7 | 0.1124 |
| q_ref = mean_top_25 | #6 | 0.3019 |
| q_ref = power_rank_10 | #6 | 0.3777 |
| q_ref = mean_fbs | #7 | 0.0023 |
| σ = 17.0 | #6 | 0.0955 |
| σ = 19.0 | #6 | 0.0792 |
| `power_source = "L2"` (no play feed) | #6 | 0.1007 |
| **`fit_universe = "fbs_vs_fbs"` (drop FCS from the fit)** | **#4** | **0.0475** |
| **walk-forward blend weights (the live `rank` path)** | **#4** | — |

So `q_ref` moves JMU by one place, exactly as advertised. `fit_universe` moves it three.
The blend-weight fitting protocol moves it three. Neither has a published sensitivity table,
and neither is presented to the reader as a choice at all.

The `fit_universe` result has a mechanism worth naming. The fit universe holds 301 teams at
week 10, of which **168 are non-FBS**. Ridge shrinks every coefficient toward the mean of
that universe. FCS teams are thinly connected and are shrunk hardest, which pulls them *up*
toward a mean that sits far above their true level; the FBS teams that beat them are pulled
*down*. The net effect compresses the FBS-over-FCS gap, and the compression lands hardest on
teams whose schedules contain the most near-FCS-quality opponents — which is to say, on G5
teams. **Ridge-toward-zero on a mixed-division universe is not neutral with respect to the
G5-versus-P4 question; it is directionally favourable to G5 teams.** That is a real,
quantified, publishable caveat and it is currently unstated.

> **Test.** Run §9's exact sensitivity machinery — mean rank delta, max delta, Kendall's
> tau, top-25 membership changes — over `fit_universe`, `power_source`, `σ`,
> `garbage_time.mode`, `C` and `β_w`, and publish the same table. Any parameter whose tau
> against the default falls below the 0.985 that `q_ref` achieves is a dial, not a
> convention, and must be labelled as one.

### S5 — MAJOR. "Margin never enters" is true of one term and false of the sentence.

`schedule_odds.py` states: "MARGIN NEVER ENTERS. Not as a tie-break, not as a secondary key,
nowhere ... there is no margin column in this module to leak from, which makes the claim
checkable by reading the code rather than by trusting this paragraph."

The flattener genuinely carries no margin. But every value it consumes does:

- `opponent_power` is L3 = `w1·k·(α−β) + w2·ρ`, where ρ is the ridge fit on
  `C·tanh(m/C) + β_w·sign(m)` — margin — and α, β are fitted on expected-points value per
  play, which is margin's differential form.
- `q_ref` is read off the same L3 ratings.
- `h` is the L3 blend regression's site coefficient, fitted with **actual game margin** as
  the response.

So the ranked team's own margin does not enter, and everything that determines what its wins
are worth is margin all the way down. The honest sentence is: *your own margin never enters;
your opponents' margins set the price of every game you played.* That is still a meaningful
and defensible property — it is what makes a one-point win worth the same as a blowout — but
the current wording is the kind of overclaim that a hostile reader quotes back with the L3
equation underneath it.

The substantive cost is visible in the case the poll will be attacked over. James Madison's
nine wins through week 10 of 2023, by margin: **1, 2, 3, 7, 8, 11, 28, 28, 35.** Five of
nine by one score. The headline ordering cannot see any of that. Its own Power rating can,
and puts JMU at #20.

> **Test.** Refit opponent quality from a **W/L-only** ridge Bradley-Terry (venue-adjusted,
> same penalty) and recompute the headline. Report Kendall's tau against the current
> ordering and the rank delta for every G5 team in the top 25. If tau is high, the claim of
> margin-independence is nearly true and can be stated precisely; if it is low, the headline
> is margin-driven and the docstring must be rewritten.

### S6 — MAJOR. σ = 15.3 is the denominator of every probability the poll publishes, and it is smaller than the system's own error.

σ enters `p_g = Φ((q_ref − Power_o + h·s)/σ)` for every game of every team, and the headline
key is `−log10 ∏ p_g` for an undefeated team. It is:

- **not fitted** — `configs/default.toml` says of itself "Nothing in this file has been
  fitted yet; grids are unsearched," and σ has no grid at all;
- **not walk-forward** — a single constant for all weeks and all seasons;
- **not heteroskedastic** — identical for a 90-play rock fight and a 160-play track meet;
- **and inconsistent with the system's own measured error.** The published walk-forward RMSE
  for the L3 blend, weeks 5+, is **16.55**. My plain opponent-adjusted ridge on the same
  window returns a residual SD of **16.96**. σ = 15.3 is roughly 8-10% below both.

Too small a σ makes every `p_g` too extreme, which makes every tail too small, which
inflates every `−log10` key — and because the key is a *product* over 9 to 13 games, the
distortion compounds multiplicatively rather than cancelling. A uniform 0.03 shift in each
`p_g` across 13 games moves the key by roughly 0.2-0.5 log units, which in the 2023 week-10
table is several ranking places.

The provenance is better than I first assumed — report 02 §5.4 confirms 15.3 twice, from the
Prediction Tracker RMSE band and from an independent conditional-SD estimate of 15.35 for
2021 (arXiv 2212.08116). So the number is a sound estimate of *the residual SD of margin
around a good prediction*. The problem is the antecedent: **this system's predictions are
not yet that good.** Using 15.3 as the denominator asserts a forecasting precision the model
has not demonstrated, and does so inside the probability that becomes the headline rank.

The tension is visible in the project's own gate, which sets the **stretch** RMSE target at
**15.3** — the system would have to become exactly as accurate as the σ it already assumes
in order to earn that assumption. Until then σ should be the model's measured error, not the
error of the class of models it aspires to join.

> **Test.** Refit σ per season as the walk-forward residual SD of the model's own
> predictions, re-run the headline for 2021-2024, and report rank deltas and the calibration
> curve under both. Then fit σ as a linear function of the two teams' combined plays per
> game and report whether decile calibration improves — `calibration` is currently the
> gate criterion missed by the widest relative margin (9.17 pp against a 5.0 pp threshold).

### S7 — MODERATE. The headline key rewards having played more games, and propagates no error.

`P(W ≥ W_t)` over a Poisson-binomial has two properties that are not documented on the poll
page:

1. **It is monotone in games played.** Two teams with identical average opponent quality,
   one 9-0 and one 10-0, are separated by a factor of one `p_g` — the 10-0 team ranks higher
   partly for having played one more game against anybody. Across a week where teams have
   played 8 to 10 games because of byes, this is a live effect on the ordering, and it is
   not the same thing as "the harder it was to do what you did."
2. **Independence is assumed and is not true.** The Poisson-binomial requires independent
   Bernoullis. Conditional on a fixed `q_ref` the games are independent, but the `p_g` are
   built from *estimated* opponent Power whose errors are correlated across a team's
   schedule — conference-mates share a fit and share their estimation error. The tail is
   therefore stated with more precision than it has, and no error is propagated.

> **Test.** Construct two synthetic teams with identical opponent Power vectors, one with
> 9 games and one with 10, both undefeated, and report the rank gap. Separately, perturb
> every `p_g` by ±0.03 and report the induced change in the top-25 ordering; if it exceeds
> the `q_ref` sensitivity (§9's tau ≥ 0.985), then estimation error in Power matters more
> than the constant the project publishes weekly.

### S8 — MODERATE. Retroactive re-ranking lets opt-out-contaminated bowls revalue September.

`retro.hindsight_surface` takes `final` to be the last bucket by kickoff order, which for
2023 includes the postseason. `[weights].bowl_non_cfp = 0.25` discounts those games but does
not remove them. So Florida State's 63-3 Orange Bowl loss — played without 33 players, a
game the config's own comment cites as the canonical example of a result that "measures
something other than team quality" — enters the hindsight Power fit and therefore changes
what every 2023 FSU opponent's September win was worth.

The project already knows the rule: `final_poll_excludes_non_cfp_bowls = true`. That
exclusion is applied to the choice of evaluation window N and not to the hindsight Power
window K. The asymmetry looks unintentional.

Note this is a *mechanism* finding, not a claim of large effect: the demo shows hindsight
does not move FSU itself (its résumé window is frozen at week N). The question is what it
does to the teams FSU played.

> **Test.** Compute the 2023 hindsight surface with `bowl_non_cfp = 0.25` and with `0.0`.
> Report the max and mean absolute rank delta across all evaluation weeks. If any team moves
> more than a place or two on the strength of December roster attrition, the hindsight Power
> window should exclude non-CFP bowls by the same rule the final poll already uses.

### S9 — MODERATE. The config asserts model behaviour that does not exist.

Constraint 5's framing is that "the config IS the methodology" and "if a number appears in
the model and not in this file, that is a bug." The converse is not currently enforced, and
four keys assert behaviour that no code path implements:

| Key | Config says | Reality |
|---|---|---|
| `[margin.prediction_compression].enabled` | `true`, with threshold and α | Referenced **nowhere in `src/`** — only in `scripts/headline_ordering_study.py`, which computes it as a side column |
| `[homefield].method` | `"home_and_home"` | Selects nothing. The live `h` is always the regression coefficient; the home-and-home estimate is computed and published as a diagnostic |
| `[homefield].h_pasteur`, `h_recent_estimate` | `3.70`, `2.8` | Unused constants |
| `[garbage_time].mode = "leverage"` | "Backtest all three, then choose, and publish which is live" | Raises `NotImplementedError`; one of the three cannot be backtested |

Each is individually minor. Collectively they undermine the specific promise that makes this
project different, which is that the config is a complete and truthful description of the
model.

> **Test.** A config-coverage test: walk every key in `default.toml`, assert each is read by
> some code path, and fail on any key that is not. Keys that are deliberately inert should
> be moved to a clearly-labelled `[reference]` block.

### S10 — MODERATE. The connectivity diagnostic saturates before it becomes interesting.

`schedule_connectivity` returns team count, component count, and largest-component share.
The published table shows 2023 going from 125 components before week 2, to 8 before week 3,
to **1 component / 100% before week 10** — and it stays there. From roughly week 5 onward
the diagnostic returns the same three numbers every week forever.

That is the wrong question. "Is the graph connected?" is answered yes by early October.
"How much does the data actually pin down a specific cross-conference comparison?" is never
asked. See §4 for what the right diagnostic returns and why it matters.

> **Test.** Add per-pair standard errors from the ridge normal matrix (five lines; see §4)
> and assert the reported value changes materially between week 5 and week 12 after the
> component count has flatlined. A diagnostic that stops varying has stopped diagnosing.

### S11 — MINOR. Internal inconsistencies in the published analysis documents.

- `demo/backtest-2021-2023.md` prose: "the résumé and Colley are exactly tied (429 each, of
  2,216 games)." The table two lines above lists Colley at **435 / 0.1963**.
- Headline-ordering study §3a, 2021 row: **A is bolded at 0.1872 while C is numerically
  lower at 0.1858** in the same row.

Small, but these are exactly the documents whose whole authority rests on "every number
below comes out of `study.json` and nothing below was typed by hand."

> **Test.** Generate every number in the analysis prose from the JSON by template, or add a
> checker that greps numeric literals out of the markdown and asserts each appears in the
> corresponding JSON.

### S12 — MINOR. λ is selected against the wrong objective, and the garbage-time flag rests on a reconstructed scoreboard.

- **λ selection.** `cv_select_lambda` minimises weighted held-out squared error on the
  *response* — play-level expected-points value at L1. The quantity the poll cares about is
  team-rating accuracy, and the λ that best predicts a held-out play is not in general the λ
  that best estimates a team coefficient. Grouping on `game_id` is right and important; the
  objective is a separate question and it is not discussed.
- **Garbage time.** `docs/data-findings.md` §12 records that the shipped score columns are
  unusable, and that the repaired reconstruction reaches the official final in **763 of 792**
  games in 2023. `score_margin` is precisely the input to the garbage-time threshold. So in
  roughly 4% of games the filter is deciding what is garbage time from a scoreboard known
  not to reconcile. The finding is documented; the consequence for L1 weights is not.

> **Test.** Re-run 2021-2023 selecting λ by held-out **game margin** error rather than
> play-level MSE and compare MAE. Separately, restrict L1 to the 763 reconciling games and
> report the rank delta against the full fit.

### S13 — IN-FLIGHT, not a design finding.

Recorded for the log only. Midway through this audit the working tree was mid-edit from the
concurrent headline switch: `model/retro.py` called `_finalize(frame)` at three sites against
a `_finalize(frame, ordering)` definition — a `TypeError` on any call to `live_surface`,
`hindsight_surface` or `grid` — and four tests failed
(`test_config.py::test_headline_is_resume_with_power_beside_it` plus three in
`test_rank_command.py`) because they asserted the résumé ordering the config no longer
selects. **Both were resolved by that session before this review was filed; the suite is
green at 250 passed.** Nothing here is a finding about the design, and **no code was modified
by this review.**

One durable lesson does survive it: the three failing `test_rank_command` assertions encoded
the *headline choice* rather than the *headline mechanism* ("undefeated teams lead the
wins-based résumé"). Tests that assert a configurable policy will break every time the policy
is exercised, which trains readers to expect red. Assert the invariant — that the published
order matches `ORDER_KEYS[headline_ordering]` — and let the choice move freely.

---

## 4. The owner's question: would 2023 James Madison survive the Big Ten?

This is the question the whole system exists to answer scientifically rather than by
assumption. Here is the trace, and then the answer.

### 4a. How the talent gap actually enters — which games, what connectivity

Conference identity is nowhere in the model; that constraint is genuinely honoured. So
everything the system believes about G5-versus-P4 level arrives through non-conference
games. I counted them (conference labels used only as an audit lens, never as a feature):

| Season | FBS-vs-FBS regular-season games | **G5 ↔ P4 bridge games** | share of all games | at the P4 site | per G5 team |
|---|---|---|---|---|---|
| 2021 | 732 | **77** | 10.5% | 82% | 1.31 |
| 2022 | 734 | **81** | 11.0% | 79% | 1.35 |
| 2023 | 750 | **90** | 12.0% | 80% | 1.48 |
| 2024 | 752 | **101** | 13.4% | 74% | 1.63 |

So the entire cross-conference structure rests on roughly **one game in eight**, and four in
five of those are played at the Power-4 stadium. The venue confound I flagged in Phase 1 is
real and it is large: the estimated G5-versus-P4 offset is close to collinear with the
home-field constant across this subsample.

Narrowing to the actual case, **James Madison's 2023 schedule contains exactly one Power-4
opponent: Virginia, on the road, won 36-35.** Virginia finished 3-9. That single one-point
road win over a bottom-third ACC team is the whole of JMU's *direct* evidence about Power-4
competition. Everything else is transitive, and the second hop is not much thicker: the Sun
Belt played **18** games against Power-4 opposition in all of 2023, across a 14-team league.

### 4b. Is that enough? The surprising answer

In Phase 1 I predicted the sparsity would show up as inflated variance — that a G5-versus-P4
contrast would carry 2 to 2.5 times the standard error of a P4-versus-P4 contrast. **I was
wrong, and measurably so.**

Ridge on game margin, 2023 through week 10, λ = 8, standard error of an estimated rating
*difference* computed from the sandwich `s²·e'A⁻¹(Z'Z)A⁻¹e`:

| Pair type | SE of the rating difference |
|---|---|
| within the Big Ten | 4.19 pts |
| SEC vs Big Ten (P4 cross-conference) | 4.15 pts |
| Sun Belt vs Big Ten (G5 vs P4) | 4.16 pts |
| **James Madison vs a Big Ten team** | **4.16 pts** |

The ratio is **1.00×**, not 2.5×. The reason is that the schedule graph is a good enough
expander: every team plays about nine games, and in a graph like that the effective
resistance between two nodes is dominated by the local degree terms rather than by the
global cut. Conference clustering does not create the bottleneck I assumed. Ridge on a
connected schedule graph really is sufficient for the *variance* of this comparison, and
the implementation's implicit bet on that is correct.

**What the sparsity does threaten is bias, not variance, and bias is measured nowhere.** The
three channels are: the venue confound above (80% of bridges at the P4 site, so any error in
`h` maps almost directly onto the conference offset); the September problem (all bridges are
played in the first month, so a December ranking splices a September estimate of league
level onto a November estimate of within-league order, and `recency_gamma = 1.0` means the
model treats them as contemporaneous); and the mixed-division shrinkage effect quantified in
S4, which is directionally favourable to G5 teams. A uniform standard error across pair
types says nothing about any of these.

### 4c. What the system can actually know — and it is a real answer

Taking the same fit and reading off the gaps against their matched standard errors:

**2023 through week 10, opponent-adjusted rating, James Madison = 8.09**

| Big Ten team | rating | gap vs JMU | SE | z |
|---|---|---|---|---|
| Michigan | 16.65 | **+8.56** | 4.16 | **2.1** |
| Penn State | 15.66 | +7.57 | 4.16 | 1.8 |
| Ohio State | 14.44 | +6.35 | 4.16 | 1.5 |
| Rutgers | 4.04 | −4.05 | 4.16 | −1.0 |
| Iowa | 2.41 | −5.69 | 4.17 | −1.4 |
| Minnesota | −1.01 | −9.10 | 4.16 | −2.2 |
| Purdue | −3.43 | −11.53 | 4.16 | −2.8 |
| Michigan State | −3.70 | −11.79 | 4.16 | −2.8 |

**So: the system can say, from on-field data alone and at about two standard errors, that
2023 James Madison was worse than the top of the Big Ten and better than the bottom of it.**
It places JMU above eleven of the fourteen Big Ten teams and below three. The honest verdict
the model supports is "JMU would have been a middle-of-the-league Big Ten team, clearly not
a contender, comfortably not a doormat" — and it is statistically unable to separate JMU
from Iowa, Rutgers, Wisconsin or Nebraska at all.

That is a genuine scientific answer to a question that is normally settled by assertion, and
the project deserves credit for making it computable. The repo's own study reaches a
compatible conclusion by a different route (JMU vs Michigan on a neutral field: −16.13
points, JMU wins 14.6% of the time).

### 4d. What it cannot know, and must say so

1. **Attrition under sustained load.** Twelve weeks against Power-4 lines is a different
   physical regime, and depth is what survives it. Nothing in a box score against Sun Belt
   opposition measures a third defensive tackle. This is not a precision problem; it is data
   that does not exist.
2. **The truncated ceiling.** JMU's rating is estimated from a distribution of performances
   whose upper region was never tested. "Does this team have a top-five performance in it?"
   is a question about a tail its schedule never sampled.
3. **The counterfactual is not the estimand.** The system estimates *level*. "Survive the
   Big Ten" is a question about a season-long workload, not a single neutral-field game.
   Those are different questions and only the second is answerable.
4. **Bias, per 4b.** Venue confound, September staleness, and mixed-division shrinkage all
   push in estimable directions and none is currently quantified.

### 4e. And the honest caveat about the headline number

At 2023 week 10 the schedule-odds headline places James Madison **#4** on the live surface
while its own Power rating is **#20**. My bootstrap puts the 90% rank interval on that #4 at
**#4 to #52**, with a median of #20 and P(top ten) = 0.22. JMU's nine wins came by margins
of 1, 2, 3, 7, 8, 11, 28, 28, 35.

The system's answer to "how good is JMU" (§4c) is defensible and well-founded. Its answer to
"where does JMU rank" is far softer than the published integer suggests, and the gap between
those two statements is the thing the poll most needs to communicate and currently does not.

---

## 5. Football-realism assessment

**Pace and tempo.** Handled at the level (per-play efficiency, opponent-adjusted) and not at
the variance (§S6). Two teams equal in efficiency but 20 possessions apart do not have the
same margin distribution, and a constant σ treats the fast team's results as more
informative than they are. Tempo is also not measured in neutral game states, so observed
pace is partly a record of having trailed. Neither is fatal; both are unaddressed.

**The 2023 Florida State case — is publishing Power beside deserve honest enough?**
Partly, and not yet fully. The final poll shows FSU at résumé #2 / Power #11 with a stated
gap of +36.79, and the demo says "the two numbers disagree by 9 places, and that disagreement
is the entire product." That framing is right, and the architecture supporting it is right:
the résumé target is raw wins, and `[weights]` shapes the Power fit rather than the
accomplishment, so the two can genuinely diverge.

But the Power rating printed beside FSU is a **season-constant estimate over thirteen games,
eleven of which Jordan Travis played.** `recency_gamma = 1.0` by default, with the stated
rationale that "a poll that says 'who earned it' should not decide that September didn't
count." That rationale is exactly correct **for the résumé** and exactly wrong **for Power**,
whose entire job is to answer "who'd win next week." As built, both published numbers are
statements about a team that no longer existed, and the honesty of showing two numbers is
undercut by both of them being blind to the same thing.

The good news is that the architecture already separates the two, so the fix is small: run
the backtest with `recency_gamma < 1`, and if it improves out-of-sample MAE, turn it on —
it will move Power and leave the résumé target untouched, which is precisely the asymmetry
the design already supports. A structural-break flag on per-game offensive efficiency (an
on-field observable; you can detect that FSU's EPA/play collapsed without knowing why) would
be better still, with the honest caveat that it has almost no statistical power with one or
two post-break games.

**December opt-outs.** The rule is right (`bowl_non_cfp = 0.25`, final poll computed before
non-CFP bowls). The leak is §S8: the hindsight Power window does not honour it.

**Rivalry and situational noise.** Not modelled, correctly — the effects are real, small,
and not predictable ex ante. Worth one sentence in the published methodology so it reads as
a decision rather than an oversight.

**Week numbering and data traps.** Best-in-class. See §2 items 1 and 2.

---

## 6. Statistical assessment: leakage, and what I could not break

I went looking for leakage in five places and found none of the kind that invalidates
results:

- **Walk-forward.** One module owns the slicing; every rater receives an already-truncated
  frame; `tests/property` plants a future game and asserts it never arrives. `plays_for`
  inner-joins on the truncated game frame. Clean.
- **The EP layer.** `fit_scope = "training_window"` fits the expected-points table on exactly
  the plays already truncated. The `frozen` alternative is offered *and labelled as leakage*
  in its own comment. This is stricter than my Phase 1 design asked for.
- **Blend weights.** The out-of-sample accumulator is updated **after** a bucket is
  predicted, with the features of the fit that predicted it — and the code says so at the
  exact line where moving it up would break the guarantee. Pooled per season, never across
  seasons, with the cost of that strictness measured (0.046 MAE). Clean.
- **Points calibration.** Fitted on accumulated out-of-sample predictions, with the
  in-sample alternative measured and rejected (0.44 MAE for L2, and it inverts the ordering
  against Elo). This is better than standard practice.
- **CV grouping.** On `game_id`, deterministic, never on plays.

**Where leakage-adjacent risk remains:** the constants themselves. `configs/default.toml`
says of itself that nothing in it has been fitted and the grids are unsearched — so the live
values (σ = 15.3, C = 24, β_w = 3.0, λ grid bounds, Connelly's thresholds, k ≈ 68) are
inherited from public sources rather than tuned, which is leakage-free but is also the
"derivative without justification" problem in §7. The moment those grids *are* searched, the
protocol must ensure the search is walk-forward or cross-season; the harness supports it and
nothing enforces it.

**Bootstrap validity:** see S3. The specified scheme is wrong and it is not yet built, which
is the best possible time to say so.

**Saturation:** handled honestly for the résumé — the bracket is published, saturated teams
are flagged in every artifact, and the docstring correctly identifies it as Bradley-Terry's
separation problem. The schedule-odds ordering removes the degeneracy entirely, which is the
strongest argument in its favour and the study makes it well.

---

## 7. Derivative without independent justification

Flagged in the spirit of the commission — not as accusation, since every one is cited
openly, but because "cited" and "justified on our own data" are different standards and the
project's own constitution asks for the second.

| Constant / choice | Inherited from | What is missing |
|---|---|---|
| **σ = 15.3** | "The Prediction Tracker RMSE band for good public models" | The system's own walk-forward RMSE is 16.55. Never re-estimated on this data (S6) |
| **Garbage-time thresholds 43/37/29/22** | Connelly / SP+ convention | Taken verbatim. Never re-estimated; the continuous alternative that would test them raises `NotImplementedError` |
| **C = 24, β_w = 3.0** | "Pasteur capped at 21, the CFBD SRS walkthrough uses ±28"; "Sports-Reference floors at ±7 ≈ β_w 3.0" | Grids exist and are unsearched. β_w is described as "the single most contested value in the system" and is set by analogy |
| **λ grid [75 … 325]** | "The published CFBD ridge implementation searched alphas = [75, 100, …, 325]" | The grid bounds are someone else's dataset's answer |
| **k ≈ 65-72** | Report's expectation | Fitted, but the sanity band is inherited |
| **`q_ref` = "an average Top-25 team"** | ESPN Strength-of-Record | Honestly attributed. The implementation (exact Poisson-binomial vs 20,000-run Monte Carlo, nameable reference team) is a genuine improvement on it |
| **The headline estimand itself** | ESPN's SOR sentence "taken at its literal word" | Attributed openly, which is the right behaviour. But "a BCS if it were invented today" and "ESPN's SOR computed exactly" are different products, and the marketing should not blur them |

The pattern: **the machinery is independent and the constants are borrowed.** For a system
whose pitch is "every constant published weekly, fork it and reproduce it," that is a
survivable position only if the publication says plainly which constants were measured here
and which were inherited. Right now the config's citations point at the *source*, not at the
*status*, and a reader cannot tell the two apart.

---

## 8. What I would attack first if I were paid to discredit this poll

In the order a hostile writer would actually use them.

1. **"Your own poll disagrees with your own poll by sixteen places, and you can't tell me
   which one is right."** James Madison #4 on the headline, #20 on Power, in the same table,
   with no interval on either. Then the schedule: a one-point win at 3-9 Virginia is the
   entire Power-4 résumé. Then the margins: five one-score wins in nine games. This is the
   attack, and it lands because the honest defence — "here is the uncertainty" — does not
   exist yet.
2. **"Your headline is the worst predictor on your own page."** The study reports the adopted
   ordering at 0.6626 forward accuracy against the Power rating printed beside it at 0.6918
   and the rejected candidate B at 0.6822. This is defensible — a desert measure is not
   supposed to be a predictor — but the defence must be pre-written and prominent, because
   the number is already published and the framing is one sentence away from "their poll is
   worse than the number they hid at the end of the row."
3. **"You said you passed your own gate. Your own file says `passed: false`."** S1. This is
   the credibility kill-shot for a project whose entire brand is transparency, and it is a
   documentation fix, not a modelling one.
4. **"Win percentage beats you."** On the single gate criterion the system passes,
   retrodictive violations, the dumbest baseline in the table — ignore who you played,
   count wins — scores 0.1769 against the résumé's 0.1936. The demo has the right answer
   ("the price of caring who you played") buried in the middle of a section. It needs to be
   on the front page as an owned result.
5. **"Margin never enters, you say."** Then the L3 equation, with tanh-compressed margin
   inside it, and the observation that `q_ref` is read off it too. S5.

Everything on this list is either already true and disclosed somewhere in the repo, or is a
wording problem. That is a good position to be in — it means the fixes are cheap — but the
current publication order buries every one of the honest disclosures beneath a claim that
overstates.

---

## 9. Where my Phase 1 was wrong

Recorded because the commission was for independent judgement, not for a document that only
finds fault.

1. **Connectivity.** I predicted G5-versus-P4 contrasts would carry 2-2.5× the standard error
   of P4-versus-P4 contrasts. Measured: 1.00×. The schedule graph is enough of an expander
   that pairwise variance is essentially uniform. My whole §4 framing in Phase 1 — that
   sparse bridges make the comparison imprecise — was the wrong worry. The right worry is
   bias, and I under-weighted it relative to variance.
2. **FCS pooling.** I predicted they would pool FCS into one node. They model individually,
   and verified the FCS-vs-FCS coverage that makes it identifiable.
3. **Margin cap.** I predicted a hard cap. They use tanh, which is the smoother thing I said
   I would prefer.
4. **CV grouping.** I predicted play-level grouping. They group on `game_id` and are
   emphatic about it.
5. **Effective resistance as the headline diagnostic.** Still worth publishing, but I
   oversold it: given (1), it will report a nearly constant number across pair types and its
   real value is as a *level* statement ("every rating difference in this poll carries about
   ±4 points of standard error") rather than as a G5-versus-P4 discriminator.

What survived contact: the deserve/predict entanglement through opponent quality (S5), the
single-σ problem (S6), the missing uncertainty (S3), the bowl-revalues-September mechanism
(S8), and the observation that q_ref is a smuggled prior — which the project handles better
than I expected but points at the wrong parameter (S4).

---

## 10. Fix list

**Before publishing anything (blocking):**

1. Correct the gate narrative, or fix the gate. If the intent is that the résumé need not
   clear the predictive thresholds, encode that intent in `[gate]` and report per-criterion
   status; do not let a summary sentence contradict `gate.passed`. **(S1)**
2. Implement `validate/leakage.py::audit` and `cfbpoll audit-features`, or remove the claim
   that the constitution is enforced. Currently the weekly workflow cannot run past that
   step. **(S2)**
3. Ship rank intervals, using a parametric bootstrap on the **fixed** schedule — not
   resampling of games with replacement. Publish the interval beside every rank from the
   first week. **(S3)**

**Before the first season (high):**

4. Publish the sensitivity table for `fit_universe`, `power_source`, σ, `garbage_time.mode`,
   C and β_w using §9's existing machinery, and state the mixed-division shrinkage caveat.
   **(S4)**
5. Rewrite the margin-independence claim to what is true: *your own margin never enters; your
   opponents' margins price your wins.* Optionally, build the W/L-only opponent-quality fit
   so the claim can be made in full. **(S5)**
6. Re-estimate σ on this system's own walk-forward residuals, and test a
   possessions-dependent σ against the decile-calibration criterion the gate currently
   misses by the widest margin. **(S6)**
7. Exclude non-CFP bowls from the hindsight Power window, matching the rule the final poll
   already applies. **(S8)**
8. Run the backtest with `recency_gamma < 1` and adopt it for Power if it improves
   out-of-sample error. The architecture already keeps the résumé target untouched, so this
   is the cheap version of making Power capable of disagreeing about post-injury Florida
   State. **(§5)**

**Housekeeping (do it anyway):**

9. Config-coverage test; move inert keys to a `[reference]` block. **(S9)**
10. Replace the connectivity diagnostic with per-pair standard errors, or add them beside it.
    **(S10)**
11. Generate analysis-document numbers from JSON rather than by hand; fix the Colley 429/435
    and the 2021 bolding. **(S11)**
12. Mark every constant in `default.toml` as `measured-here` or `inherited`, and say which in
    the published methodology. **(§7)**

---

## 11. Closing assessment

The thing I did not expect to find was how much of the hard, unglamorous work is already
done and done well: the week-bucket ordering, the duplicate-play forensics, the refusal to
touch a shipped EPA column that was one join away, the out-of-sample calibration applied to
the *baselines* as well as to the model, the holdout that no code path can unlock, and a
study that publishes the evidence against the choice its own owner made. That is a level of
discipline I have not seen in a public rating system.

What is missing is not modelling ability. It is the last mile: the machinery that turns a
good estimator into a claim a stranger can check, and the editorial discipline to make the
published sentence match the computed object. Three fixes get this to publishable. The
fourth through eighth make it defensible for a season.

The poll should not go out this week. It should go out.

---

## Appendix: was it already considered?

Per the commission, the prior research corpus was left unread until the findings above were
written, then checked only to see whether a specific concern had already been raised, and
where. Results:

| Finding | Already in the research? | Where, and what it says |
|---|---|---|
| **S3, bootstrap validity** | **Yes and no — this is the origin of the defect.** | Report 02 §3.3 says "**block bootstrap over games** (resample games with replacement, refit, 500-1000 draws)". Those are two different procedures and the parenthetical specifies the wrong one. `model/bootstrap.py` copied the parenthetical faithfully. The report also gives the *correct* tool in the same sentence — the ridge sandwich `σ̂²(XᵀWX+λD)⁻¹(XᵀW²X)(XᵀWX+λD)⁻¹` — and sets it aside as less "robust for publication." That sandwich is exactly the formula used to compute every standard error in §4 of this review. The right instrument was in hand and was put down. |
| **S6, σ = 15.3** | **Provenance yes, the objection no.** | Report 02 §5.4 documents both independent confirmations. Nothing anywhere asks whether the constant is appropriate given *this* system's error, and nothing notes that the gate's stretch RMSE target equals σ. |
| **S3/S10, uncertainty and rank intervals** | **Yes, as an aspiration.** | Report 02 §3.3: "Publishing 'Team X is ranked 7th, 90% interval 4th-13th' is the single most honest thing a computer poll can do and no major system does it." The intent is the project's own; only the delivery is missing. |
| **Bridge-game inventory, cross-conference counts** | **No.** | "cross-conference" and "bridge game" appear nowhere in the corpus. The counts in §4a are new. |
| **Effective resistance / per-pair precision** | **No.** | The term appears nowhere. §4b's finding — that pairwise SE is uniform across pair types, so connectivity is *not* the binding constraint — is new, and it contradicts my own Phase 1 prediction rather than the project's. |
| **Heteroskedastic σ / pace-dependent variance** | **No.** | No hit anywhere in the corpus. |
| **S1, win percentage beating the résumé on violations** | **Partly.** | Win percentage is specified as a baseline in report 02 §5.3 and the demo reports the result honestly. What is absent is the recognition that `violations_must_beat` was drawn around Colley and SRS while the baseline that actually wins is excluded from it. |

So of the twelve substantive findings, three (S3, S6, and the interval gap) are refinements
of positions the research already held, and the cross-conference and heteroskedasticity work
is new to the project.

---

*Reviewed cold. No code was modified — `git status` shows this review and its Phase 1
companion as the only files added. Phase 1 was written to disk before any source file in
this repository was opened, and the prior research corpus was not read until after the
findings above were complete.*
