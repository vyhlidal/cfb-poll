# ADR 0014 — The base model has one job, and the ceremonies that were slowing it down are over

- **Status:** **ACCEPTED.** Decided by the project owner, whose charter is quoted
  below. Implemented in `src/cfbpoll/projection/{crossdivision,chain,systems}.py`
  and `src/cfbpoll/levers.py`.
- **Date:** 2026-08-17
- **Supersedes:** the freeze, holdout and pre-registration machinery of
  [ADR 0010](0010-projection-and-poll.md) §3, [ADR 0012](0012-2025-opens.md) and
  the protocol documents `docs/analysis/_tuning-campaign-protocol.md` and
  `docs/analysis/_campaign-2-protocol.md`. **Those ADRs remain as history and are
  not edited.** They record what this project believed and why, and a project
  whose argument is "we publish what we did" does not go back and tidy up the
  parts it has since changed its mind about.
- **Touches:** [`docs/constraints.md`](../constraints.md), rewritten into two
  untouchables plus a lever registry.
- **Evidence:** [`demo/projection-chain.md`](../../demo/projection-chain.md), and
  every number in the sibling `.json`.

---

## 1. The charter, distilled

> The base model has ONE constraint: maximum predictive accuracy. Two things are
> untouchable — no human polls, ever, and no future-data leakage, because
> walk-forward honesty IS accuracy. Everything else is free. Chain the seasons,
> measure week-one accuracy, and iterate until it is as high as the data allows.
> Document every change and its measured effect. The old pre-registration
> ceremony is replaced by: every result published, every change explained on the
> page.

Two things in that are worth separating, because only one of them is a loosening.

**The loosening.** Margin of victory belongs in the base without apology; a
40-point win is information about two football teams and "style points" is a
worry about incentives, not about measurement. Constants refit when new data
lands. The projection is a living forecast rather than a frozen August artifact.
Grid-search freely.

**The tightening, which is the half that gets missed.** Walk-forward honesty
stops being a nicety and becomes the definition of the objective. An accuracy
figure computed with any knowledge of the games being scored is not a smaller
result, it is not a result. Everything in `chain.py` follows from taking that
literally, including the parts that made our own numbers look worse.

## 2. What the freeze was for, and why it goes

The freeze bought exactly one sentence: *the coefficients did not move after we
saw 2025*. It cost a season of data on every future refit, forever.

That was a good trade when the alternative was a reader with no way to tell a
prediction from a retrofit. It is a bad trade now, because there is a better
mechanism for the same promise and this project already ships it: **the vintage
record**. Every board ever published stays up, with the coefficients it ran
under, the git sha that produced it and the config hash that parameterised it.
"What did you say in August" is answered by the archive rather than by refusing
to learn.

So `design_transitions` gains 2024→2025, and the discipline that replaces the
freeze is narrower and does more work:

> A recipe projecting season Y may fit on transitions whose **target** season is
> strictly before Y, and on nothing else.

`holdout.assert_no_target_is_locked` still enforces it and still bars 2026, the
season this recipe predicts. A recipe fitted on the outcomes it claims to project
is not a projection, it is a description, and that has not changed.

### The gate becomes a scoreboard

The gate was a pass/fail ceremony against a threshold chosen in advance, and its
verdict was a boolean. A boolean is the least informative possible answer to
"how good is this model". `demo/projection-chain.md` replaces it with the
scoreboard: what the model said in August, what happened, how often it was right,
and the identical figure for the AP's ballot and for doing nothing at all.
Published every time, whatever it says. The old scorecard stays where it is.

## 3. What was measured, and what was adopted

Walk-forward, 2022 through 2025, straight-up accuracy, home-field constant taken
from the prior season's fit rather than fitted on the games being scored.

| | week 1 | weeks 1-4 |
|---|---:|---:|
| **every game with an FBS team in it** | | |
| last season's ratings, unchanged | 81.0% | 77.0% |
| the old model, `projection-2.0.0` | 82.4% | 77.4% |
| **this model, `projection-3.0.0`** | **86.9%** | **80.4%** |
| the AP writers' August ballot | 82.3% | 76.7% |
| **FBS against FBS only** | | |
| last season's ratings, unchanged | 74.0% | 71.3% |
| the old model | 73.4% | 71.7% |
| **this model** | **74.1%** | **71.6%** |
| the AP writers' August ballot | 68.2% | 67.4% |

Three changes, each measured before adoption.

### 3.1 A rating earned outside FBS no longer transplants at face value

This is where nearly all of the gain is, and it is the sniff-test failure the
charter named: North Dakota State tenth on the 2026 board.

The archive holds 602 games where the two divisions met. Run the model's own
prediction over them and the FBS side beats it by **+17.3 points**. That number
is the wrong one to apply, and finding out why is the whole of the work: this
model under-predicts *every* mismatch, because ridge shrinks and the margin
response is compressed. Over FBS-vs-FBS games the same regression says
`actual = 1.30 × predicted`.

Carry the predicted margin as a regressor and ask what is left for the division
boundary:

```
actual_margin = a + b * predicted_margin + gap * bridge
```

**gap = −13.4 points, standard error 0.6**, over 4,546 games. On a matched window
— only games the model calls by 10 to 30 points — bridge games come out 13.5
points (se 0.87) above FBS-vs-FBS games with an identical prediction. It is
stable walk-forward, converging from −9.4 on one season of data to −13.4 on five.

**And then the measurement that cuts the other way**, which is why this ADR ships
two constants instead of one. A promoted program is not a randomly drawn FCS
team; it is one that spent years buying its way to FBS rosters and staff. Six
programs moved up between 2022 and 2025 and played 68 games against FBS opponents
in their first FBS season. Carry their FCS rating forward untouched and those 68
games come out at **−3.6 points, se 1.9**. Apply the full 13.4 and the error grows
instead of shrinking: mean absolute error rises from 12.4 to about 14 points and
straight-up accuracy falls from 69.1% to 63.2%.

Both are real. They answer different questions, they are published separately,
and a promoted team carries both, netting the −3.6 the 68 games actually measured.

**The guard is the part that decides the row.** The promotion credit is fitted on
six programs whose FCS-year ratings topped out at +6.0 against the FBS mean.
North Dakota State sits at **+17.4** — outside the evidence by eleven points, and
no amount of care makes six programs into evidence about a seventh that far
outside them. So the rule is a maximum rather than an extrapolation:

> **No promoted team is projected above the best first FBS season a promoted
> program has actually had.**

That is James Madison in 2022, at +5.75 against the FBS mean, which was 32nd.
North Dakota State lands **33rd**.

Honesty about which lever did the work: the accuracy chain **cannot arbitrate the
promotion credit**, because it touches one or two teams and moves pooled week-one
accuracy by less than a tenth of a point. It is a fairness question wearing a
coefficient's clothes. That is exactly why it, and the ceiling, are published
levers with their sample sizes attached rather than constants somebody has to go
and find.

### 3.2 A second season of memory

The year before last counts at 0.2. Swept over a 216-cell grid; worth about half
a point of week-one accuracy, which is inside the noise band on this many games
and is published as a peak rather than a discovery.

### 3.3 Conference identity: measured, and still out

Unchanged, and deliberately so. Nothing in either product knows what a conference
is, and `cfbpoll audit-features` rebuilds every design matrix without
`conference_game` before every fit and requires bit-identical output. That makes
the refusal a result rather than a promise. It ships as a lever defaulted to
zero, because a refusal a reader cannot see the switch for is not one they can
check. **The default does not move without the owner seeing a measured accuracy
number first**, and no such number is offered here.

## 4. What this does not change

- **No human poll is an input to anything.** The AP preseason ballot is the
  Projection's headline baseline, and a baseline that is also an input measures
  nothing. There is no lever for this and there will not be one.
- **No future data.** Strengthened rather than relaxed, and `chain.py` is where
  it is now enforced game by game.
- **The Poll's own charter.** The Poll still ranks what a team has done, from
  on-field results only, with nothing carried across a season boundary. Every
  design matrix is still rebuilt from its allow-list before every fit. The
  Projection still reads the Poll and the Poll still may never read the
  Projection.
- **The vintage record.** Nothing published is edited in place. `projection-3.0.0`
  supersedes `2.0.0`; it does not correct it.

## 5. What would reverse this

- If a future season's chain shows `projection-3.0.0` losing to
  `projection-2.0.0` on the same walk-forward protocol, the change is reverted
  and the reversal is published in the same place the adoption was.
- If the promotion ceiling is ever the reason a team is visibly mis-ranked in the
  other direction — a promoted program that turns out to be a top-15 team and was
  held at 33rd — the ceiling is the first thing to go, and the fact that it will
  have been wrong is the price of a guard that was right about the general case.
- If the cross-division gap ever stops being distinguishable from zero as the
  bridge sample grows, the correction goes and the artifact says so.
