# Fresh Eyes, Phase 1: How I Would Build It

**Status: written BEFORE opening any source file, config, test, or output of this
repository, and before reading any of the prior research corpus.** The only inputs are
the stated brief (goals and hard constraints) and my own domain knowledge. Anything in
here that turns out to match the implementation is convergence, not influence; anything
that diverges is a genuine independent disagreement worth adjudicating in Phase 3.

Author role: senior sports data scientist, college football. Reviewer brought in cold.

---

## 0. Reading the brief adversarially before designing

Before the design, four observations about the brief itself, because two of its
constraints are in tension and a reviewer who does not say so up front is not being
useful.

**(a) "No priors ever" and "deserve" cannot both be fully satisfied.** A resume metric
must compare "13-0 against a weak schedule" to "11-1 against a brutal one." Nothing in
the observed data adjudicates that comparison. The data tells you the win probabilities;
it does not tell you how much credit an undefeated season against soft opposition should
receive. Every resume metric resolves this with a reference point — a hypothetical team
quality against which the schedule's difficulty is scored. That reference point is a
prior. It is not a prior *about a team* (which is what the constitution actually bans, and
correctly so), but it is a value judgment injected by the designer, and it moves the
ranking, not just its scale. **My position: this is acceptable and unavoidable, but it must
be named as the single most consequential free parameter in the system and published with a
sensitivity sweep, not buried as a constant.** A system that claims to be assumption-free
while hiding its most load-bearing assumption in a scalar is the easiest possible target
for a hostile critic.

**(b) "On-field observables only" should bind on team-specific inputs, not on measurement
instruments.** An expected-points model fit on many prior seasons of play-by-play carries
no team identity — it is a thermometer calibration, on the same footing as deciding that
a touchdown is worth 6 points. Banning it would be a category error and would force the
system into cruder measurement. But the instrument must be *frozen before the season* and
published, because fitting it on the current season and then using it to score Week 3 is
leakage into the retroactive surface. My rule: instruments may be pre-fit on prior seasons;
team states may not.

**(c) "Conference identity is never a feature" is right, and the corollary is that
conference strength is an output.** The important consequence is downstream: because
conference level is *estimated* rather than assumed, it comes with a standard error, and
that standard error is enormous for weakly-connected leagues. A system that bans conference
as an input but then reports conference-differentiating results as point estimates without
intervals has committed the worse sin. It has laundered an assumption into an apparent
measurement.

**(d) "Beat SRS/Colley/Elo before publishing" is too low a bar to be a real gate.** Those
systems are 1970s-to-1990s technology. Any competent opponent-adjusted efficiency model
beats them. The benchmark the public will actually apply on day one is the closing point
spread. I would report error against the market even though beating the market is not
required and probably not achievable, because refusing to report it looks like hiding.

---

## 1. Data granularity

**Primary store: play-by-play.** Minimum fields per play: game id, offense, defense,
period, clock, down, distance, yard line (offense-relative), play type, yards gained,
scoring result, turnover flag, penalty flag, home/away/neutral, and a stable game key.
Drive-level is derivable and I want drives too, because drive-level is the natural unit for
a few things (finishing drives, starting field position) that play-level EPA smears.

**Three derived layers, in order of robustness:**

1. **Game results** (W/L, margin, venue). Robust, low-information, never wrong.
2. **Drive/possession outcomes.** Points per drive, starting field position, drives ending
   in scores. Medium information, resistant to play-count and pace artifacts.
3. **Play-level EPA.** Highest information per game, fastest to stabilize, most exposed to
   modeling error and to garbage-time contamination.

**Why all three rather than picking one:** they have different bias profiles and different
convergence rates. EPA-based ratings stabilize in roughly 4-6 games; margin-based ratings
need 8-10. A blend that weights EPA more early and lets results assert themselves later is
strictly better than either alone, *provided the blend weight is chosen out-of-sample.* If
the blend weight is tuned on the same season it is evaluated on, the blend is the leak.

**Explicitly excluded by constitution and by my agreement:** recruiting composite, returning
production, prior-season rating carryover, brand, and anything a human voted on. I would
also exclude, on my own judgment, market lines as *inputs* (they encode human priors,
injury news, and last season) while using them as an *evaluation benchmark*. That split
matters: a benchmark you never train against is not contamination.

---

## 2. Opponent adjustment machinery

This is the core, and I would build it as a penalized regression on the game graph rather
than an iterative rating loop.

**Model form.** For each play p in game g between offense i and defense j:

```
EPA_p  =  O_i  −  D_j  +  h·(home indicator)  +  situational controls  +  ε_p
```

Solved as ridge-penalized least squares over the full design matrix of team-offense and
team-defense indicators. Equivalently a mixed model with team effects as random effects,
which is the same estimator with λ chosen by the variance-component ratio rather than by
cross-validation. I prefer the mixed-model framing because the shrinkage then has an
interpretation (signal-to-noise) rather than being a tuned knob, and because it gives
standard errors for free.

**Why not iterative SRS.** SRS on margin is a fixed point of "my rating = my average margin
+ average of opponents' ratings." It is fine, it is transparent, and it is 50 years old.
Its defects: it has no shrinkage (so early-season and weak-connectivity estimates blow up),
no uncertainty quantification, no way to express heteroskedasticity, and it inherits every
pathology of raw margin, including saturation and pace. Ridge/mixed on per-play efficiency
fixes all four. I would keep SRS as a published baseline, not as the engine.

**Separate offense and defense.** Not for display purposes — because it doubles the
effective sample per team and because unit-level effects are what actually transfer across
opponents. A team whose net rating is +5 from a great offense faces a very different
matchup distribution than one that is +5 from defense.

**Regularization target.** Toward zero (the global mean), because that is the only
prior-free target available. This must be flagged loudly as a *known directional bias*, not
a neutral choice — see §4.

**Situational controls I would include**, all on-field observable: venue (home/away/
neutral), rest days between games, and starting field position for drive-level work. I
would *not* include altitude, travel distance, or weather in v1 — each is defensible but
each adds an estimated coefficient with weak identification, and the marginal accuracy is
under a tenth of a point per game.

**Home field.** Estimate it, do not assume it. But recognize it is only weakly separable
from team strength in the first three weeks, and that a single global home-field constant
is a simplification: real home-field advantage varies by venue by several points, and the
G6-vs-P4 bridge games are almost entirely played at P4 venues, so **any error in the home
field constant maps almost directly onto the estimated conference offset.** If the true
home edge is 2.8 and the model uses 2.0, every G6 team's away-money-game performance is
credited 0.8 points too little, systematically, across the entire bridge set. This is, in
my judgment, the single most underappreciated sensitivity in the whole system, and it is
the first thing I would test.

**Solver requirements.** Deterministic, closed-form or convergent to fixed tolerance, no
random initialization, no stochastic optimizer. Reproducibility is a stated goal and a
model whose answer depends on a seed cannot be forked and reproduced.

---

## 3. The two surfaces: deserve and predict

**Predict (power rating).** The output of §2, converted to a points-per-game scale, plus
home field, used to generate a point spread and a win probability for any hypothetical
matchup. This is the "who'd win" number. Optimized purely for out-of-sample prediction
error. Nothing about it is philosophical.

**Deserve (resume / schedule odds).** My formalization:

For team *i* with observed games *g ∈ G_i*, each against opponent *o(g)* at venue *v(g)*,
define a hypothetical reference team of quality *q_ref*. For each game compute the
probability that the reference team wins that game at that venue:

```
P_g(q_ref)  =  Φ( (q_ref − R_o(g) + h·v(g)) / σ )
```

The reference team's win total across this schedule is Poisson-binomial. The deserve score
is the upper-tail probability that the reference team matches or exceeds the team's actual
win total:

```
Deserve_i  =  P( Binom-Poisson(P_g) ≥ W_i )      →  rank ascending (rarer = better)
```

**Design decisions inside that, and my positions:**

- **Binary W/L, not margin, for the primary deserve surface.** "Deserve" means judged on
  winning. The moment margin enters, deserve is a power rating with extra steps and the
  two published surfaces stop being independent. I would publish a margin-informed variant
  as a clearly-labeled secondary, never as the headline.

- **But: opponent strength `R_o` has to come from somewhere, and if it comes from the
  margin-based power rating, margin re-enters through the back door.** This is the
  structural leak in every resume metric I have ever seen, including the good ones. My fix
  is to run a *second, W/L-only* opponent-strength model — Bradley-Terry with ridge
  shrinkage, venue-adjusted — and feed the deserve layer from that. It is more work, it
  is slightly noisier, and it is the only way the two published surfaces are genuinely
  different objects rather than one object with two presentations. **If the implementation
  feeds deserve from the margin-based ratings, that is a real finding, not a nitpick.**

- **`q_ref` is the value judgment.** Set it at the FBS mean and undefeated-versus-cupcakes
  dominates, because beating 12 average teams is already rare. Set it high (top-10
  quality) and one-loss teams from brutal leagues rise, because the reference team also
  loses some of those games. There is no data-driven answer. **Publish a sweep:** the top
  25 under q_ref at the 50th, 75th, 90th, and 95th percentile of the FBS distribution, every
  week, as a standard artifact. Teams whose rank is stable across the sweep are genuinely
  ranked; teams that swing 10 spots are being ranked by the constant, and readers deserve
  to know which is which.

- **Why the tail-probability form rather than the cleaner MLE form.** The obvious
  alternative — "what team quality would most likely have produced this record against this
  schedule" — is degenerate for undefeated teams (the likelihood is monotone increasing,
  MLE runs to infinity). The `q_ref` tail construction exists precisely to regularize that
  degeneracy. This is worth stating explicitly because it reframes `q_ref` from "arbitrary
  convention" to "the specific device that makes undefeated teams rankable at all."

- **Uncertainty must propagate.** `R_o` for a weak schedule is poorly estimated, and that
  uncertainty flows straight into deserve. An undefeated G6 team's deserve score is a
  function of numbers that are themselves ±4 points. Publish deserve with a credible
  interval obtained by propagating opponent-rating uncertainty. Essentially no public
  resume metric does this, and it would be a genuine contribution.

- **Normalize for games played.** Improbability of a record mechanically grows with the
  number of games. Teams with byes, cancellations, or a 13th game must not be advantaged.

- **Losses must be scored, not just wins.** The Poisson-binomial on win *count* treats all
  11-1 teams identically regardless of *which* game they lost. Losing at Georgia and losing
  at home to a bottom-half team are not the same resume. I would use the full outcome
  vector likelihood rather than the win-count tail, or at minimum publish a "worst loss"
  companion column. The win-count formulation is a real information loss and I would expect
  it to be the most common public complaint.

---

## 4. Can the C-USA champion vs the mid-B1G team gap be measured from on-field data alone?

Honest answer: **partially, with wide and quantifiable uncertainty, and with one component
that is structurally unmeasurable.** Breaking it into three questions that get three
different answers.

### 4a. Is the level offset identified at all?

Yes, through non-conference games only. The FBS game graph is ~133 nodes. Conference play
creates dense near-cliques. Everything the model knows about cross-conference level comes
from the bridges — the non-conference games. Rough structure per G6 team per season: one
FCS game, one or two "money games" at P4 venues, one or two games against other G6 teams.
So the G6↔P4 bridge inventory is on the order of **100-140 games league-wide per season**,
against ~800-900 total FBS games. The entire conference-level structure of the poll rests
on roughly one game in seven.

That is not nothing. It is also not much, and it has properties that make it worse than its
count suggests.

### 4b. How bad is the bridge sample?

Five problems, in descending order of how much they worry me:

1. **Venue confound.** Money games are at the P4 site, nearly universally. The estimated
   level offset is therefore almost perfectly collinear with the home-field constant across
   this subsample. Get home field wrong by half a point and every conference offset moves.
   This is the highest-leverage single parameter in the system for the JMU question.

2. **All bridges are in September.** Conference play consumes October and November.
   So the cross-conference information used to rank teams in December was generated by
   teams that no longer exist in the same form — different QB reps, different injury state,
   different install. Meanwhile the *within*-conference information is fresh. The model is
   effectively splicing a September estimate of league level onto a November estimate of
   within-league order. Under a constant-strength assumption this is invisible and wrong.

3. **Effort and roster asymmetry.** The G6 team is playing its season. The P4 team is
   playing a tune-up, often with a 4th-quarter roster full of backups. This inflates
   observed G6 performance relative to a hypothetical neutral, full-effort meeting — in the
   direction of making G6 teams look *better* than they are. Not measurable from a box
   score. Garbage-time filtering removes some of it and I would expect the residual to be
   worth one to two points in the G6's favor.

4. **Selection in who schedules whom.** Money games are bought by P4 programs with budget,
   which skews toward the better half of P4. Meanwhile ambitious G6 programs seek these
   games and weak ones take whatever pays. The bridge set is not a random sample of
   G6×P4 pairs, though it is at least scheduled years in advance and therefore not selected
   on current-season form — which is the one genuinely reassuring property.

5. **Transitive dilution.** For a specific team, the number of *own* bridges is one or two.
   Everything else reaches P4 through conference-mates' bridges, two or three hops out,
   with the error compounding at each hop.

### 4c. The right way to quantify it, which I would insist on publishing

The variance of the estimated difference between two teams in a network model is governed
by the **effective resistance** between them in the game graph — formally, the appropriate
quadratic form of the Laplacian pseudo-inverse. This is exact, computable, and directly
answers "how much does the data actually pin down the JMU-vs-Michigan gap?"

My expectation, stated in advance so it is falsifiable: by week 10 of a season, the
standard error on (a specific G6 team − a specific P4 team) will be **roughly 2 to 2.5
times** the standard error on (a P4 team − a different-conference P4 team), because P4
teams are densely interconnected through many more paths. In absolute terms I would expect
something on the order of 3-6 points of standard error on the G6-vs-P4 contrast on a
points-margin scale, against a true gap that is probably 7-14 points for the case in
question. **That means a claimed gap of 7 points is roughly 1.5 standard errors — enough to
say "probably a gap exists," nowhere near enough to place the team precisely.**

I would publish, weekly: per-team connectivity diagnostic, the SE of each top-25 team's
rating, and a named inventory of the specific bridge games carrying the most leverage on
each conference offset — literally, "these four games are why we think the Sun Belt is
worth what we say it is worth." That last artifact does not exist anywhere publicly and it
would be the most intellectually honest thing on the site.

### 4d. What is structurally unmeasurable, no matter how good the model is

Level is estimable. **Robustness to a regime never experienced is not.** Specifically:

- **Attrition under sustained load.** Twelve weeks against P4 lines is a different physical
  regime. Two-deep quality is what survives it. Nothing in a box score against C-USA
  opposition measures your third defensive tackle.
- **Ceiling truncation.** A team that wins its league by 25 has a rating estimated from a
  distribution of performances whose upper region was never tested. The question "does this
  team have a top-10 performance in it" is a question about a tail the schedule never
  sampled.
- **Matchup-specific style stress.** Single-latent-dimension models assume transitivity.
  Elite defensive line play against a G6 offensive line is the canonical non-transitive
  stressor and it is not in the data.

So the honest formulation of what the system can deliver is: **"Given all observed results
and their transitive structure, here is the posterior distribution over this team's
strength, and here is the probability it exceeds a given B1G team's strength on a neutral
field in a single game."** It cannot deliver: "would this team survive a B1G season." Those
are different questions and the second one requires extrapolating to a workload regime that
generated none of the training data. I would say this in the published methodology, in
plain language, above the fold.

---

## 5. Early-season identifiability

**The counterintuitive fact:** early season has *proportionally more* cross-conference
information than late season, because September is when the bridges are played. What it
lacks is total volume and within-conference resolution. So the failure modes differ by
week:

- **Week 1:** most teams have one game. Team strength, home field, and opponent strength
  are jointly unidentified in any meaningful sense. Ridge shrinkage collapses nearly
  everything toward zero and the ordering is essentially "margin, lightly adjusted."
- **Weeks 2-4:** the graph connects but is sparse. Estimates are dominated by the penalty
  term. Rank volatility is extreme and mostly meaningless.
- **Weeks 5-8:** conference play densifies the local structure. Within-conference order
  becomes well identified. Cross-conference offset stops improving, because no new bridges
  are being played.
- **Weeks 9+:** within-conference precision keeps improving; cross-conference precision is
  frozen at its September value while the underlying teams drift.

**My design response, three parts:**

1. **Publish from week 1, but publish intervals, not just ranks.** The brief demands weekly
   publication. Fine. The intellectual honesty comes from an explicit resolution diagnostic:
   for each week, "the median 95% interval on a top-25 team's rating is ±X, which
   corresponds to ±Y ranking positions." In week 2 that number will be embarrassing, and
   printing it is the point.
2. **Flag unidentified teams explicitly** rather than silently ranking them: teams with
   zero games, teams whose component is not connected to the main graph, teams whose
   effective sample is below a threshold.
3. **Consider a slow time-varying strength component** (a random walk on team effects, i.e.
   a state-space formulation with small process variance, all teams initialized identically
   so it remains prior-free). This directly addresses the September/November splice in §4b,
   and it is what I would build if I had the engineering budget. The cost is that it makes
   the model much harder for an outsider to reproduce by hand, which fights the transparency
   goal. I would take the trade, but I would understand a decision to defer it — as long as
   the resulting bias is documented rather than ignored.

---

## 6. Garbage time

Two separate problems that are frequently conflated.

**(a) Efficiency contamination.** When a game is decided, both teams change objectives:
the leader runs clock and plays backups, the trailer throws into soft coverage and moves
the ball cheaply. Per-play efficiency in this state measures something other than team
quality.

- The crude fix is a score-differential-by-quarter rule. It is transparent and it is what
  most public systems use.
- The better fix is a **win-probability band**: drop or downweight plays where in-game WP is
  outside roughly [0.05, 0.95], using a WP model calibrated on prior seasons. This
  automatically handles pace, time remaining, and the difference between a 21-point lead in
  the second quarter and the same lead with four minutes left.
- **I would downweight continuously rather than hard-drop.** A step function creates a
  discontinuity that real games straddle, and it makes the result sensitive to a single
  meaningless play that pushes a game across the threshold. A smooth weight — something
  like a taper as WP approaches the bounds — is more robust and removes an easy line of
  attack.
- Note the pace interaction: fast teams accumulate more garbage-time plays, so any
  garbage-time rule differentially affects tempo teams. This must be checked.

**(b) Margin saturation.** A 63-0 win is barely more informative than a 42-0 win. Standard
public practice is a hard cap (28 or 35 points) or a concave transform.

**I would use neither.** I would model game margin with a **heavy-tailed likelihood
(Student-t)** rather than Gaussian. This achieves the same down-weighting of blowouts as a
cap, but smoothly, with the degree of down-weighting estimated from the data rather than
asserted, and without the arbitrary cliff that a cap creates. Hard caps are the single most
common "arbitrary constant" attack surface in public rating systems and they are avoidable.

---

## 7. Pace and tempo

Three distinct effects, and most public systems handle only the first.

1. **Per-play normalization.** Obvious and near-universal: rate stats, not counting stats.
2. **Heteroskedastic game variance.** Two teams identical in per-play efficiency but
   differing in tempo do *not* have the same distribution of game margins. More possessions
   means more realized variance in the margin. A model that assumes a single constant σ for
   every game systematically mis-weights fast-paced teams — their results are treated as
   more informative than they are, and their upset losses are penalized too heavily. **My
   design: σ as a function of the game's possession count** (or expected possession count
   from both teams' tempo). I regard the constant-σ assumption as a real, fixable defect,
   not a rounding error.
3. **Garbage-time interaction**, per §6.

There is a fourth, subtler one: **tempo is partially endogenous to game state.** Trailing
teams speed up. So observed pace is contaminated by whether you were behind, and a naive
tempo measure partly encodes "you were losing a lot." Pace should be measured in neutral
game states only.

---

## 8. FCS games

Roughly one per FBS team per season, so ~110-125 games — comparable in count to the entire
G6↔P4 bridge set, which is a good reason not to be lazy here.

**The options, ranked:**

1. **Best: model FCS teams individually**, with their ratings estimated from their own FCS
   games, hierarchically shrunk toward an FCS mean. This is correct on the merits — North
   Dakota State is not Kennesaw State, and pretending otherwise is a real error — and it
   has a valuable side effect: **FCS teams become additional bridges.** An FCS team that
   plays two different FBS teams links them in the graph. Given how starved the graph is
   for cross-conference edges (§4), throwing away 120 edges is expensive. Requires FCS
   results data, which is generally obtainable.
2. **Acceptable: a small number of FCS tiers**, with tier membership determined by on-field
   FCS results (not by subdivision label or playoff seeding history).
3. **Common but crude: a single pooled "FCS replacement" entity.** Makes beating a playoff
   FCS team identical to beating a bottom-tier one, and is mildly circular: the pooled FCS
   rating is estimated from exactly the games it is then used to evaluate.
4. **Unacceptable: dropping FCS games entirely.** This is not a wash — it means a team that
   *loses* to an FCS opponent escapes the consequence. For a poll whose headline is a
   "deserve" measure, that is a disqualifying bug. If FCS games are dropped from the power
   layer for measurement reasons, they must still be counted in the deserve layer.

Whatever is chosen, **FCS games must be excluded from the prediction-error evaluation set**,
or the reported MAE is flattered by ~120 easy games per season.

---

## 9. Injuries, opt-outs, and non-constant teams

The constitution says on-field observables only, and injuries are not on-field observable.
But their *consequences* are, and that is the opening.

**The 2023 Florida State case is the canonical test.** A 13-0 team whose starting QB is lost
in the twelfth game. The resume is elite and *was* legitimately earned. The team that would
take the field in January is not the team that earned it, as the Orange Bowl demonstrated
at 63-3 — a result additionally contaminated by mass opt-outs, and therefore a poor
measurement of anything.

**My positions:**

- **Deserve should rank FSU near the top and that is correct, not a bug.** They beat
  everyone they played. A resume metric that retroactively docks a team for an injury is
  not a resume metric.
- **Power must not rank them near the top, and this is where the design has to actually
  work.** If the power rating is a season-constant strength estimate, it will *also* rank
  FSU elite, and then publishing both numbers is honest-looking while being wrong twice.
  **Publishing power beside deserve is only meaningful if power is capable of disagreeing.**
  That requires one of: (a) a time-varying strength state that can move, (b) recency
  weighting, or (c) explicit structural-break detection on per-play efficiency by game — all
  three of which are on-field observable, since you can detect that offensive EPA per play
  collapsed without knowing why.
- **Statistical power for break detection is genuinely poor** with one or two post-break
  games. A break test will not fire confidently in real time. The honest response is to
  publish a *volatility/recent-form flag* with the rating rather than to pretend either
  certainty or ignorance.
- **December opt-outs: bowl games measure a different team.** My rule: bowl and postseason
  games are down-weighted or excluded from *power* estimation (they are not measurements of
  the team that played the season), while counting for deserve. And critically —
- **Retroactive re-ranking must not let opt-out-contaminated December results revalue
  September opponents.** This is a specific, concrete failure mode of the retroactivity
  feature: a team's September win gets retroactively devalued because the opponent lost a
  bowl game with 40% of its roster in the portal. That is not "later results revealing what
  the opponent was really worth." That is noise laundered as hindsight.

---

## 10. Retroactivity mechanics

Define `Poll(w, k)` = the ranking *for* week w computed *using data through* week k.

- **As-published** = `Poll(w, w)`.
- **Hindsight** = `Poll(w, K_final)`.

**Three traps, in descending severity:**

1. **The time machine.** In the hindsight surface, opponent quality should be estimated
   using all data through K, but the *games being credited to the ranked team* must still be
   only those through week w. If post-week-w games played by the ranked team enter as
   evidence about that team, you have not built a hindsight poll — you have built a
   full-season poll with a misleading label. These two objects are easy to conflate in code
   and the distinction is the entire intellectual content of the feature.
2. **Hindsight is not out-of-sample and must never be used to score accuracy.** Team A's
   hindsight week-3 rating depends on opponent B's strength, which depends on B's week-10
   game against A. That circularity is *intended* in the hindsight surface, and it is
   *disqualifying* for any prediction-accuracy claim. Only `Poll(w, w)` may be scored.
3. **Hyperparameter leakage.** If λ, blend weights, garbage-time thresholds, or σ are tuned
   on full-season data and then applied to produce `Poll(w, w)`, the walk-forward is
   cosmetic. Hyperparameters must be fit on entirely different seasons, or themselves
   walked forward. **This is the single most likely place for a sophisticated system to leak
   without anyone noticing**, and it is where I will look hardest in Phase 2.

**Reproducibility requirements:** content-address the input data (hash the game file), pin
the config, version the code, and make every published number a pure function of that
triple. A retroactive claim that cannot be re-derived from an archived snapshot is a claim,
not a record.

**One artifact I would add that nobody publishes: churn.** For each week, how far did the
hindsight poll move from the as-published poll — mean absolute rank change, and the
biggest individual movers. This is a self-critique instrument, it directly demonstrates the
system's own uncertainty, and it is the most interesting thing the retroactivity feature can
produce.

---

## 11. Validation and publication gates

**Baselines:** SRS/Massey, Colley, Elo (as specified), plus closing point spread as an
unbeatable-but-reportable reference.

**Metrics:**
- Margin: MAE and RMSE, out-of-sample, predicting week w+1 from data through week w.
- Win probability: log loss, Brier score, and a calibration curve. A ranking system that is
  never converted to probabilities has not been tested.
- Rank stability: week-over-week Kendall tau.
- Result consistency (fraction of games where the higher-ranked team won).

**A warning about that last one, which the brief names as a gate:** result consistency is
trivially maximized by a purely retrodictive system, and maximizing it produces *worse*
predictions. Colley- and Massey-class systems score well on retrodictive consistency
specifically because they fit the past rather than generalize. **If result consistency is a
publication gate, it must be a floor to clear, never an objective to optimize**, or the
gate actively selects for the wrong model.

**Statistical realism about the sample:** ~800-900 FBS games per season. Differences in MAE
below roughly 0.3 points are not distinguishable within a single season. Comparisons must
be **paired** (same games, paired differences), across **multiple seasons**, with standard
errors clustered appropriately. A headline claim of "we beat SRS" backed by one season and
an unpaired mean difference is not evidence.

**Bootstrap validity — and this is a real trap.** The naive bootstrap (resample games with
replacement, refit) is *invalid here* because games are not exchangeable: they are edges in
a network whose structure carries the identification. Resampling edges can disconnect the
graph or leave a team with zero games, and it destroys exactly the connectivity structure
whose uncertainty you were trying to characterize. **Correct approaches: a parametric
bootstrap (simulate outcomes from the fitted model on the fixed observed schedule, refit),
or a block bootstrap by week.** Fixing the schedule and resampling outcomes is the right
object, because the schedule is not random — it was set years in advance.

**On σ.** The residual standard deviation of college football game margin around a good
prediction is roughly 16 points (the NFL figure is ~13.5). Any value in 15.5-16.5 is
defensible as a point estimate. But my stronger position is that **a single constant σ is
the wrong object** — variance rises with expected total points and with possession count
(§7), and using one number mis-weights every fast, high-scoring team in the sport. I would
expect a constant-σ implementation to be defensible-but-improvable, and I would want to see
the number's provenance published, since it feeds directly into every win probability and
therefore into the entire deserve surface.

---

## 12. Data traps I expect to find

Written in advance as predictions, so Phase 2 can confirm or refute them:

- **Week numbering.** A "Week 0" exists in recent seasons. Conference championship week and
  postseason weeks are numbered inconsistently across sources. Any `through_week` filter
  that assumes contiguous 1..N integers will silently include or exclude games.
- **Season type.** Regular vs postseason is a separate field from week; filtering on week
  alone can leak bowl games into a week-13 poll.
- **Neutral-site flags.** Frequently wrong in public data — conference championship games,
  early-season kickoff games at neutral venues, and "home" games played at an NFL stadium.
  Every misflagged neutral game injects a full home-field constant of error.
- **FCS opponents with null or unstable identifiers**, and FCS teams sharing names with FBS
  teams.
- **Cancelled/postponed games** appearing with 0-0 scores or null scores.
- **Realignment and renames** breaking team identity joins across seasons — which matters
  for any multi-season hyperparameter fitting.
- **Duplicate or missing plays** in play-by-play, and drives with impossible field position.
- **Timezone/date boundaries** putting a Friday-night game in the wrong week.

---

## 13. Where this system will be wrong no matter what

Stated plainly, because a system that claims otherwise is the one I would attack.

1. **The counterfactual regime shift.** The G6-to-P4 question (§4d) is not answerable from
   data generated in a different regime. Depth, attrition, and the physical demands of a
   twelve-week P4 schedule are unobserved.
2. **Twelve games is a small sample.** Even with flawless methodology, a team's strength is
   estimated from ~12 noisy observations. The irreducible standard error is on the order of
   2-3 points. **The difference between rank 8 and rank 14 is, in most seasons, not
   statistically distinguishable.** Any poll presenting a strict 1-133 ordering without
   intervals is overclaiming, and this one will be too unless it publishes them.
3. **Turnover and special-teams luck.** Fumble recovery is close to a coin flip and swings
   games by several points. A resume metric *rewards* luck by construction — and that is
   arguably correct, since you did win — but it guarantees that deserve and predict diverge
   most exactly for the luckiest teams, which is precisely where the public will say the
   poll is broken.
4. **Latent roster state.** Injuries, suspensions, portal departures, and coaching changes
   are observable only through their delayed statistical consequences.
5. **Weather.** A 13-10 game in 30mph wind looks like two bad offenses.
6. **Non-transitivity.** Single-dimensional latent strength cannot represent style matchups.
   The effect is real but modest; the error is largest for extreme-style teams (triple
   option, extreme tempo, elite-DL-vs-weak-OL).
7. **The undefeated-versus-one-loss comparison is underdetermined.** It is a values question
   wearing a lab coat, and `q_ref` is where the values live.
8. **Motivation and situation.** Rivalry games, lookaheads, letdowns, and interim-coach
   bounces are real, roughly a point or two, and not predictable ex ante.

---

## 14. What I would build that public systems do not

Summarizing the genuinely differentiating pieces, since Phase 3 needs to judge whether this
build clears the bar of "worth existing alongside SP+/FPI/Massey":

1. Per-team **credible intervals** on both surfaces, and rank intervals derived from them.
2. **Connectivity diagnostics** via effective resistance — a defensible, quantitative answer
   to "how well does the data actually pin down this cross-conference comparison?"
3. A named, published **bridge-game leverage inventory**: which specific games are carrying
   the cross-conference information, with their influence weights.
4. A weekly **`q_ref` sensitivity sweep**, converting the system's biggest hidden assumption
   into a published, inspectable artifact.
5. **Hindsight churn reporting** as a self-critique instrument.
6. **Leave-one-game-out influence analysis**: which single result, if reversed, most changes
   the top 10.
7. Heteroskedastic σ and a heavy-tailed margin likelihood in place of hard caps and a global
   constant.

Items 2, 3, and 4 are the ones I would consider the actual reason for this system to exist.
Prediction accuracy is a crowded field; honest uncertainty accounting about cross-conference
comparison is empty ground.

---

## 15. My five advance predictions about the implementation

Recorded before opening the code so Phase 2 has something to score against.

1. The deserve layer will be fed opponent strength from the margin-based power model, making
   the two published surfaces less independent than they appear.
2. σ will be a single global constant rather than a function of pace or total, and its
   provenance will be thin.
3. Garbage time will be handled with a hard threshold rather than a smooth taper, and margin
   saturation with a cap rather than a robust likelihood.
4. FCS opponents will be pooled into one replacement-level entity rather than modeled
   individually, forfeiting ~120 graph edges.
5. Hyperparameters (λ, blend weights) will be selected with cross-validation whose grouping
   is at the game or play level rather than at the season level, producing optimistic
   walk-forward numbers.

If several of these land, the pattern would suggest conventions absorbed from public
systems rather than derived independently — which is precisely the contamination the owner
is worried about.

---

*End of Phase 1. Nothing beyond this line was written before reading the implementation.*
