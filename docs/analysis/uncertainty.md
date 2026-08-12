# Published uncertainty: the sandwich, the bootstrap, and the scheme that was wrong

Everything below is computed by `scripts/uncertainty_study.py` and written to
`uncertainty.json` in the same directory. Nothing here is typed by hand.

This answers S3 and S10 of [the independent review](./fresh-eyes-review.md), whose
verdict was blunt and correct: *nothing published carries uncertainty, and the
bootstrap that is specified is the wrong one.*

---

## 1. The scheme report 02 §3.3 specified is invalid, and here is the measurement

The parenthetical was **"resample games with replacement, refit"**, and
`model/bootstrap.py` copied it faithfully into a docstring for months without
anyone noticing that it cannot work. Games are **edges in the schedule graph**, not
exchangeable observations. The graph's connectivity is what identifies a
cross-conference comparison at all, and resampling edges destroys it.

`bootstrap.naive_resample_diagnostic` runs that scheme and counts the damage over
1,000 draws on the 2023 schedule through week 10 (1,205 games, 301 teams):

| Outcome of a naive draw | Fraction of draws |
|---|---:|
| Schedule graph has more than one component | 0.6% |
| Some team is left with zero games | 100.0% |
| **Broken either way** | **100.0%** |
| Mean largest-component share | 95.7% of teams |

The review asked for exactly this test and said: *if that fraction is materially
above zero, the naive scheme is disqualified on its own output.* It is
**100.0%**. Nothing in this package uses it, and
the function exists only so the disqualification is a number rather than an
argument.

**What is used instead:** a parametric bootstrap on the **fixed** schedule. The
calendar was set years in advance by human beings with television contracts and is
not a random variable; the outcomes are. Each draw redraws every game's margin from
`Normal(Power_home − Power_away + h·site, σ²)`, refits the results core, rebuilds
Power, and re-ranks with the same `l4_resume.fit` and `schedule_odds.fit` the poll
itself calls. Each draw is a complete alternative season played on the real
calendar.

---

## 2. Reproducing the review's bootstrap, and comparing two independent builds

The review ran its own parametric bootstrap: 300 draws, 2023 through week 10, the
schedule held fixed, a plain opponent-adjusted ridge on game margin treated as
truth, margins redrawn from N(μ, 15.3²). The nearest configuration this repository
can run is `power_source = "L2"` at 300 draws, σ = 15.3,
λ = 0.5 — a compressed-margin response rather than a raw one, and a
cross-validated penalty rather than a fixed λ = 8. Both tables below are the
**schedule-odds** ordering.

| Team | Published (theirs) | Published (ours) | Median (theirs) | Median (ours) | 90% (theirs) | 90% (ours) |
|---|---:|---:|---:|---:|---|---|
| Ohio State | 1 | 1 | 4 | 3 | #1 – #18 | #1 – #19 |
| Washington | 2 | 2 | 13 | 13 | #2 – #49 | #2 – #42 |
| Florida State | 3 | 3 | 9 | 8 | #2 – #31 | #1 – #30 |
| Alabama | 4 | 4 | 13 | 12 | #1 – #41 | #1 – #42 |
| James Madison | 6 | 6 | 20 | 24 | #4 – #52 | #3 – #56 |
| Georgia | 8 | 8 | 13 | 14 | #3 – #39 | #3 – #39 |
| Michigan | 11 | 11 | 9 | 10 | #4 – #24 | #4 – #27 |
| Liberty | 17 | 17 | 24 | 25 | #6 – #56 | #6 – #59 |
| Tulane | 22 | 22 | 33 | 38 | #7 – #74 | #9 – #84 |

**Every published rank matches**, which is the part that matters: two people who
never saw each other's code produced the same ordering from the same archive. The
medians agree to a place or two everywhere and the intervals overlap heavily.

On the review's own headline example — 2023 James Madison, published #6
under this configuration — their interval was **#4 – #52** with a median of #20 and
P(top ten) = 0.22. Ours is **#3 – #56** with a median of #24 and
P(top ten) = 0.18, P(top 25) = 0.55 (theirs: 0.63).

The residual differences are attributable and small: our response is the compressed
margin rather than raw margin, our λ is cross-validated (0.5) rather
than fixed at 8, and 300 draws carry their own Monte Carlo noise. Nothing here
needed to be reconciled; two builds landed in the same place.

### The property that will surprise a reader, and it is not a bug

**The bootstrap median is worse than the published rank for nearly every undefeated
team.** Under the model's own estimate of these teams' quality, going 9-0 is an
unlikely outcome, so most simulated seasons do not repeat it. The headline ordering
ranks teams by how improbable their record was; a record that is improbable is one
that usually does not happen again. That is defensible as a definition of desert and
it is indefensible published without an interval, which is precisely the review's
point and the reason this is now on every row.

---

## 3. What the live poll publishes

The live configuration is `power_source = "L3"` with 1,000 draws,
σ = 17.44 (estimated from this system's own walk-forward residuals,
review S6 - not the 15.3 constant), seed 20260812, λ = 0.5.
These are the numbers that
reach `poll.csv`, `poll.json`, `rank_intervals.parquet` and the console table.

| Team | Published | Bootstrap median | 90% rank interval | P(top 10) | P(top 25) |
|---|---:|---:|---|---:|---:|
| Ohio State | 1 | 5 | **#1 – #26** | 0.72 | 0.95 |
| Washington | 2 | 16 | **#2 – #58** | 0.33 | 0.66 |
| Florida State | 3 | 14 | **#1 – #52** | 0.42 | 0.75 |
| Alabama | 6 | 20 | **#2 – #64** | 0.28 | 0.65 |
| James Madison | 4 | 27 | **#3 – #70** | 0.20 | 0.48 |
| Georgia | 5 | 14 | **#2 – #54** | 0.33 | 0.68 |
| Michigan | 9 | 7 | **#3 – #31** | 0.60 | 0.93 |
| Liberty | 12 | 31 | **#5 – #79** | 0.16 | 0.47 |
| Tulane | 16 | 41 | **#8 – #94** | 0.07 | 0.29 |

The median 90% interval width across all 133 ranked teams is **87 places**.

**The L1 efficiency half of Power is held at its point estimate** in the live
configuration, because plays are not resimulated: a generative model of 170,000
correlated snaps is a different project. The results core, the record, every win
probability, q_ref and both orderings are all redrawn. **These intervals are
therefore a lower bound on total uncertainty**, and every artifact says so in
`bootstrap_note`.

---

## 4. The ridge sandwich, and the diagnostic that replaces component-counting

Report 02 §3.3 wrote down the sandwich covariance

```
Cov(θ̂) = σ̂² (ZᵀWZ + λD)⁻¹ (ZᵀW²Z) (ZᵀWZ + λD)⁻¹
```

and then set it aside as less "robust for publication" than a bootstrap — while
specifying the wrong bootstrap in the same sentence. The review computed every
standard error in its §4 from exactly this expression. It is now
`model/ridge.py::sandwich`, it runs on every L2 fit, and `power_se` is a column on
every published row of every surface.

Median per-team standard error, live configuration: **1.88 points**
(review's configuration: 5.24 points, because a cross-validated λ shrinks
less than the review's fixed λ = 8 and the compressed response is rescaled by b).

### S10: the connectivity diagnostic saturates; per-pair standard errors do not

`schedule_connectivity` answers "is the graph connected?" — yes, from early
October, forever. The question worth asking is **how much does the data actually pin
down a specific cross-conference comparison**, and the answer is the standard error
of a rating *difference*, which is not the two individual errors added in
quadrature: two teams that share opponents share estimation error.

Conference labels are used here as an **audit lens only**. No model in this
repository knows a conference exists; these groups are a way to slice a table, and
the finding is that the slices are indistinguishable.

| Pair type | SE of the rating difference (ours, L2 cfg) | SE (ours, live L3 cfg) | SE (review) |
|---|---:|---:|---:|
| within the Big Ten | 7.08 | 2.53 | 4.19 |
| SEC vs Big Ten (P4 cross-conference) | 7.46 | 2.67 | 4.15 |
| Sun Belt vs Big Ten (G5 vs P4) | 7.44 | 2.66 | 4.16 |
| James Madison vs a Big Ten team | 7.44 | 2.66 | 4.16 |

**The ratio of a G5-versus-P4 contrast to a within-P4 one is 1.05×.** The
review's Phase 1 predicted 2 to 2.5×; the review measured 1.00× and recorded its
own prediction as wrong. We measure 1.05× on a different fit, with a different penalty,
on a different response, and reach the same conclusion: the ratio is one, not two
and a half.

The mechanism the review names is right: every team plays about nine games, and in a
graph like that the effective resistance between two nodes is dominated by local
degree rather than by the global cut. **Conference clustering does not create the
bottleneck.** Ridge on a connected schedule graph really is sufficient for the
*variance* of this comparison.

**What the sparsity threatens is bias, and a uniform standard error says nothing
about it.** The three channels — the venue confound on bridge games, the September
staleness of every cross-conference edge, and mixed-division ridge shrinkage — are
measured in [robustness-notes.md](./robustness-notes.md) and
[fit-universe-sensitivity.md](./fit-universe-sensitivity.md), not here.

---

## What this does not do

1. **It does not propagate play-level uncertainty.** See §3.
2. **It conditions on λ.** The penalty is held at the value the real data's
   cross-validation selected. The bootstrap propagates sampling uncertainty at a
   fixed hyperparameter, which is the standard construction; folding in the CV's own
   variance would be a different and much less interesting quantity.
3. **It conditions on the model being right.** A parametric bootstrap redraws from
   the fitted model, so it cannot tell you that the model is wrong — only how much
   the ranking would move if the model were right and the season were replayed. The
   normal margin distribution, the homoskedastic σ and the single latent
   strength dimension are all assumptions inside the interval rather than things
   it tests. σ itself is now estimated from this system's own walk-forward
   residuals rather than assumed at 15.3 (review S6), but it is still ONE number
   for every game, and the review's §5 objection to that - a 90-play rock fight
   and a 160-play track meet do not have the same margin variance - stands
   unmeasured.
4. **It says nothing about the counterfactual.** "Would James Madison survive the
   Big Ten" is a question about a season-long workload, and no interval on a rank
   answers it (review §4d).

```
uv run python scripts/uncertainty_study.py
uv run cfbpoll bootstrap --season 2023 --through-week 10 --naive-diagnostic
```

Generated by `scripts/uncertainty_study.py` at 2026-08-12 - code `c3132c9` - config sha256 `ab906806951a114b...`
