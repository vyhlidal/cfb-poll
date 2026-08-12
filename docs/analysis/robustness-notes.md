# Robustness notes: the venue confound, and the September splice

Computed by `scripts/robustness_notes.py`; every number is in
`robustness-notes.json`. **No default changes on the strength of anything below.**
Both sections answer questions the
[independent review](./fresh-eyes-review.md) raised about *bias* rather than
variance - the thing its §4b concluded was the real threat once it had measured
that connectivity was not.

Conference membership appears here as an **audit lens and never as a feature**.
`conference` is on the banned-pattern list in `validate/leakage.py`, the schedule
frame's `conference_game` column is proved unconsumed by every design matrix on
every run, and the 2023 Power-4 list in this script is asserted against the
archive's own team names so a typo fails loudly. Nothing in this file touches a fit.

---

## 1. The bridge-game venue confound

### 1a. The inventory, reproduced

2023, FBS-vs-FBS regular season and conference championships, with 70 Power-4 teams
(the ACC, Big Ten, Big 12, SEC and Pac-12 as they stood, plus Notre Dame) and 63 others:

| | Full season | Through week 10 |
|---|---:|---:|
| FBS-vs-FBS games | 750 | 546 |
| **G5 ↔ P4 bridge games** | **109** | **100** |
| Share of all FBS-vs-FBS games | 14.5% | 18.3% |
| At the P4 site | 82 | 75 |
| At the G5 site | 25 | 23 |
| At a neutral site | 2 | 2 |
| **Share of hosted bridges at the P4 site** | **77%** | **77%** |
| Bridges per G5 team | 1.73 | 1.59 |

**The review's structural claim reproduces.** It reported 90 bridges in 2023 at 80%
P4-hosted; this counts 109 at 77% — the
difference is a membership question (this list puts Notre Dame and the four 2023
AAC-to-Big-12 arrivals on the P4 side) rather than a disagreement about structure.
The whole cross-conference structure of the poll rests on about
15% of its games, and 77%
of those are played in the Power-4 stadium.

### 1b. Does that confound the conference offset? Two tests, and the answer is no

The worry, stated exactly: if the estimated G5-versus-P4 offset is nearly collinear
with the home-field constant across this subsample, then any error in `h` maps
almost directly onto the offset, and a poll that got `h` wrong by half a point would
be wrong about every G5 team in the same direction.

The design matrix carries an **unpenalised site column** (`model/design.py`), so `h`
is estimated rather than assumed and whatever it absorbs, it absorbs for every game.
That is the in-principle answer. Here is the measurement.

**Test (a) — exact, from the ridge sandwich.** The correlation between the estimated
site coefficient and the estimated `mean(P4) − mean(G5)` contrast, read straight out
of the covariance matrix (`ridge.sandwich`, report 02 §3.3). Collinearity would show
up as a correlation near ±1.

| Quantity | Value |
|---|---:|
| Site coefficient (compressed-response units, λ = 8) | 4.6879 ± 0.3948 |
| P4 − G5 contrast | 3.2158 ± 0.3754 |
| **Correlation between them** | **-0.0328** |

**0.0328.** The two estimates are very nearly
orthogonal. The venue asymmetry in the bridge set is real and it does *not* propagate
into the conference offset, because every other game in the fit - a thousand of them -
identifies `h` independently of the bridges. The bridges are 12% of the games; they
are not 12% of the information about home field.

**Test (b) — assume `h` instead of estimating it, and assume it wrong.** Offsetting
the response while *keeping* the site column would be a no-op by construction, so
this is the counterfactual that bites: the site column is **removed from the**
**design**, `h` is imposed, and the team coefficients absorb whatever the imposed
value gets wrong. A team picks up that error in proportion to its home/away
imbalance, and the question is whether G5 teams' imbalance is systematically
different. The estimated value is 4.688.

| Imposed `h`, error vs the estimate | P4 − G5 gap | Shift |
|---|---:|---:|
| -2.0 points | 3.4579 | +0.2421 |
| -1.0 points | 3.3368 | +0.1211 |
| +0.0 points | 3.2158 | +0.0000 |
| +1.0 points | 3.0947 | -0.1211 |
| +2.0 points | 2.9737 | -0.2421 |

A full point of error in an ASSUMED `h` moves the P4-minus-G5 gap by
**0.1211** compressed-response units — against a gap of 3.22 and a
standard error on that gap of 0.38.

The review's Phase 1 called this "the single most underappreciated sensitivity in
the whole system" and expected an error in `h` to map almost one-for-one onto the
conference offset. **It does not**, and the reason is the one the review itself gave
for why its variance prediction failed: the schedule graph is a good enough expander
that no single subsample dominates any single coefficient. The venue asymmetry in
the bridge set is real, and the leverage it was assumed to carry is
**0.32 standard errors per
point** of error rather than one-for-one — a real effect, an order of magnitude
smaller than the framing. And in the live model `h` is not assumed at all: it is an
unpenalised column, which is why test (a) is the one that matters and test (b) is
the counterfactual it is measured against.

**What this does NOT clear.** Test (b) says the offset is insensitive to a *global*
error in `h`. Home-field advantage genuinely varies by venue by several points, and a
single global constant cannot represent that. A systematic difference between P4 and
G5 home-field advantage would land on the bridge set and would not be caught by
either test here, because both hold the single-`h` model fixed. Estimating per-venue
home field is a real piece of work with weak identification (about six home games a
year per team) and it is not attempted.

---

## 2. `recency_gamma` and the September splice

Every cross-conference game is played in the first month; conference play consumes
October and November. So a December ranking splices a **September** estimate of
league level onto a **November** estimate of within-league order, and
`recency_gamma = 1.0` treats the two as contemporaneous (review §4b, channel 2).

The review's other reason for wanting γ < 1 is the 2023 Florida State case: Power's
job is "who'd win next week", and a season-constant estimate over thirteen games,
eleven of them with Jordan Travis, cannot disagree with the résumé about a team that
no longer exists. Publishing two numbers is only honest if the second one is
*capable* of disagreeing.

Walk-forward, [2021, 2022, 2023], weeks 5+, FBS-vs-FBS. L3 is the Power rating
and the violations column is the headline ordering's:

| γ | n | SU % | MAE | RMSE | Brier | Calib. dev. | Violations (headline) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.0 *(default)* | 1585 | 69.21 | 13.019 | 16.549 | 0.1980 | 13.67 pp | 0.2015 |
| 0.98 | 1585 | 69.02 | 13.023 | 16.551 | 0.1981 | 13.59 pp | 0.2024 |
| 0.95 | 1585 | 69.09 | 13.042 | 16.556 | 0.1985 | 11.88 pp | 0.2042 |

**No value of γ improves out-of-sample margin error.** The default is already the best of the three on MAE, on RMSE, on Brier and on retrodictive violations; decaying at 0.95 costs +0.024 points of MAE and +0.0027 on violations.

The one column that moves in γ's favour is **calibration**: γ = 0.95 gives 11.88pp against the default's 13.67pp, and it is still nowhere near the 5.0pp gate. Worth recording next to the finding in demo/backtest-2021-2023.md that the calibration miss is an asymmetry nobody has diagnosed: two unrelated knobs both nudge it and neither closes it, which is what you would expect if the cause is neither of them.

**THE DEFAULT DOES NOT CHANGE, and the reason is not that the number is small.**
`recency_gamma` is a fairness knob before it is an accuracy knob. The config states
the position it encodes - *"a poll that says who earned it should not decide that
September didn't count"* - and that is a judgement about what the poll is for, not a
hypothesis the backtest can settle. The owner decides it. This table exists so the
decision is made against a measured cost rather than an assumed one.

Two things a reader should hold onto if it is ever revisited:

1. **The architecture already supports the asymmetry the review asked for.** Game
   weights shape the *Power* fit; the résumé's target is raw wins and raw compressed
   margin. Turning recency on would move Power and leave the accomplishment
   untouched, which is precisely the split that would let the two published numbers
   disagree about post-injury Florida State.
2. **γ is a blunt instrument for the thing it is aimed at.** Exponential decay
   downweights September uniformly, and September is *where the cross-conference
   information lives*. It treats the splice by discarding one end of it. A
   structural-break flag on per-game offensive efficiency - an on-field observable -
   would target the FSU case without touching the bridge games, and the review says
   the same. That is a different piece of work and it is not attempted here.

```
uv run python scripts/robustness_notes.py
```

Generated by `scripts/robustness_notes.py` at 2026-08-12 - code `959bbe1` - config sha256 `a197e7f5dbab6aa0...`
