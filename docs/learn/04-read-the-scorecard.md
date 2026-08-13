# 04. Read the scorecard

*Reading: about 20 minutes. Doing: about 10 minutes.*

---

## Why a football fan cares

Ask anyone who publishes a ranking a simple question: how often are you wrong?

Almost nobody answers. The polls do not answer. The committee does not answer.
Most of the computer systems that get quoted on broadcasts do not publish a
number you could check either. The ranking arrives every Tuesday with the same
confidence whether it was right last week or not.

This module is about the part of the project that answers the question. You are
going to run the test yourself, watch the model fail it, and understand why the
failure is on the front page instead of in a footnote.

## What you will be able to do

- Run the walk-forward backtest and read its table.
- Explain what "walk-forward" prevents and why it is the whole ballgame.
- Say what each of the five gate criteria measures, in football terms.
- Name the system that beats this model on one criterion, and explain why.
- Explain what a sealed holdout is and why 2025 is one.

## What you already have

A working clone with the data downloaded, from module 02. You do not need
`out/poll.csv` for this module, and this module will overwrite parts of `out/`,
which is fine.

From module 01 you know the gate exists and that nothing clears it. Now you get
to reproduce that.

---

## The walkthrough

### Segment 1. Run the test

<!-- verify: run timeout=1800 -->
```bash
make backtest
```

It takes about thirty seconds.

```text
walk-forward [2021, 2022, 2023] - FBS-vs-FBS, weeks >= 5 (the published window)
system             n     SU%     MAE    RMSE   Brier  logloss   viol%   churn
schedule_odds   1585   68.71  13.038  16.531  0.1971   0.5772   20.15    9.67
resume          1585   68.71  13.038  16.531  0.1971   0.5772   19.97    9.29
l3              1585   68.71  13.038  16.531  0.1971   0.5772   22.32    8.29
l2              1585   69.53  13.227  16.740  0.1975   0.5794   21.21    8.06
l1              1585   69.15  13.165  16.684  0.1995   0.5826   23.96    7.97
colley          1585   67.95  13.562  17.237  0.2063   0.5989   19.62    9.58
srs             1585   69.09  13.196  16.695  0.1995   0.5821   21.83    8.21
elo             1585   68.77  13.559  17.098  0.2014   0.5885   22.50    9.60
random_walker   1585   65.05  14.015  17.984  0.2178   0.6244   19.97   12.26
winpct          1585   66.12  13.824  17.660  0.2118   0.6118   17.80   10.12
home_team       1585   56.34  15.458  19.863  0.2475   0.6885     nan     nan
```

**Take a screenshot.** That is eleven rating systems graded on 1,585 real games,
computed on your machine in half a minute.

What to notice: the bottom row, `home_team`, is a system that always picks the
home team and always says the margin is the average home-field advantage. It gets
56.34 percent of games right.

Why that matters: that is the floor. Any rating system has to beat "pick the home
team" before it has demonstrated anything at all, and having the floor printed in
the same table is how you keep a good-looking number honest. Some public systems
are closer to that row than their marketing suggests.

### Segment 2. Walk-forward, which is the whole ballgame

The word at the top of that output is `walk-forward`, and it is the reason the
numbers mean anything.

To predict a week 9 game, the model is refit using only data through week 8 of
that same season. It has never seen the game it is being graded on. It has never
seen any game after it. It does not get to use prior seasons either, because
prior-season ratings are a banned input in this project.

What to notice: this is harder than it sounds to enforce. The model here is a
batch refit, which means it recomputes everything from scratch every week, and
that makes it very easy to accidentally hand it a column that came from the
future.

Why that matters: a ranking system that scores itself on games it was fit on will
look outstanding and predict nothing. This is the single most common way a sports
model fools its own author, and it is why the guard lives in the harness rather
than in each system's own code. In module 06 you will write a rating function and
you will be physically unable to cheat at this, because the games are already
truncated before your code ever sees them.

### Segment 3. What the columns are asking

| Column | The question | Better is |
|---|---|---|
| `SU%` | How often did it pick the winner? | Higher |
| `MAE` | On average, by how many points did it miss the final margin? | Lower |
| `RMSE` | The same, but a 30-point miss hurts much more than three 10-point misses | Lower |
| `Brier`, `logloss` | When it said 70 percent, did that happen 70 percent of the time? | Lower |
| `viol%` | How often does the ranking put a team below somebody it beat? | Lower |
| `churn` | How many places does the average team move week to week? | Context rather than a score |

What to notice: `MAE` at 13.038 means that on an average game, this model's
predicted margin was about thirteen points off the real one.

Why that matters: thirteen points is a lot. It is two scores. That number is not
a scandal, it is what college football is: a sport where a 20-point favorite
loses often enough to keep the sport worth watching. Every system in that table
is between 13 and 15. Anybody quoting a rating system that claims to be much
better than 13 is either measuring something else or has seen the answers.

`viol%` is the one that is specific to rankings rather than predictions. If your
poll has Alabama above Texas and Texas beat Alabama, that is a violation. It is
not automatically a mistake, because Texas might have lost to five other teams,
but a ranking that racks them up is arguing with results it can see.

### Segment 4. The gate

<!-- verify: run timeout=600 -->
```bash
uv run python - <<'PY'
import json

metrics = json.load(open("out/backtest_metrics.json"))
gate = metrics["systems"]["schedule_odds"]["gate"]
seen, want = gate["observed"], gate["thresholds"]

rows = [
    ("Straight-up accuracy", f'{seen["su_accuracy"]:.2%}',
     f'>= {want["su_accuracy_min"]:.0%}', gate["su_accuracy"]),
    ("Margin MAE", f'{seen["mae"]:.3f}',
     f'<= {want["mae_max"]}', gate["mae"]),
    ("Margin RMSE", f'{seen["rmse"]:.3f}',
     f'<= {want["rmse_max"]}', gate["rmse"]),
    ("Calibration deviation", f'{seen["max_calibration_deviation_pp"]:.2f} pp',
     f'<= {want["calibration_max_decile_deviation_pp"]} pp', gate["calibration"]),
    ("Retrodictive violations", f'{seen["retrodictive_violation_rate"]:.4f}',
     "at or below every system", gate["violations_vs_baselines"]),
]

print(f'{"criterion":24} {"observed":>12}  {"threshold":<26} verdict')
for name, observed, threshold, ok in rows:
    print(f"{name:24} {observed:>12}  {threshold:<26} {'PASS' if ok else 'FAIL'}")

print()
print("gate cleared:", gate["passed"])
print("still undecided:", ", ".join(gate["undecided"]))
PY
```

```text
criterion                    observed  threshold                  verdict
Straight-up accuracy           68.71%  >= 70%                     FAIL
Margin MAE                     13.038  <= 12.8                    FAIL
Margin RMSE                    16.531  <= 15.8                    FAIL
Calibration deviation         7.37 pp  <= 5.0 pp                  FAIL
Retrodictive violations        0.2015  at or below every system   FAIL

gate cleared: False
still undecided: brier_beats_all_baselines, retro_vs_live_monotone
```

**Take a screenshot.** Five criteria, five failures, printed by the project's own
code on your machine.

What to notice: go back to the table in Segment 1 and look for any system with
`MAE` at or below 12.8. There is not one. The gate is set above where the entire
field currently sits.

Why that matters: this is a gate the authors set high enough that they fail it,
rather than a bar drawn under wherever they happened to land. A gate you always
clear tells a reader nothing.

### Segment 5. The row that beats us

Find `winpct` in the first table. Its `viol%` is **17.80**, and ours is **20.15**.

`winpct` is a ranking by win percentage. It does not know who you played. It does
not know where you played. It does not adjust for anything. And it beats this
model on the criterion that measures how often a ranking contradicts a
head-to-head result.

What to notice: that is not a bug, it is arithmetic. A ranking that is purely a
function of record can hardly ever put a team below somebody it beat, because
beating them usually improved your record. A ranking that cares who you played
will sometimes say the win did not count for much, and every one of those is a
violation.

Why that matters: this is the price of the project's whole idea, printed in its
own scorecard. The criterion used to be measured against a hand-picked pair of
rivals that happened to exclude win percentage. An outside reviewer pointed that
out, the list was widened to every scored system, and the criterion flipped from
pass to fail as a direct result. The stricter version is the one that shipped.

### Segment 6. The sealed season

Look at the last thing `make backtest` printed.

```text
2024 (validate) and 2025 (holdout) are NOT scored here. 2025 is a
single-shot test and the harness refuses it without --unlock-holdout.
```

Constants get tuned on 2021 to 2023. A tuned choice gets checked once against
2024. 2025 has never been scored by anything in this project, and the code
refuses to score it.

What to notice: this is not a technical restriction. It is a promise with a lock
on it.

Why that matters: if you try enough variations against the same seasons, one of
them wins by luck, and you will not be able to tell which. A **holdout** is a
season you agree not to look at, so that when you finally do look, the number
means what you think it means. You get one. If you spend it, you have to say so
publicly. Module 05 is where this becomes your problem rather than a policy you
read about.

---

## When it does not work

**`make backtest` says it cannot find the archive.** You skipped module 02 or you
are in the wrong folder. Run `pwd` and then `make rankings` once.

**Your numbers differ in the fourth decimal from the ones printed above.** For
2023 they should match exactly. For 2021 and 2022 they can differ slightly,
because the published version includes 80 postseason games from a private source
that cannot be republished. This is documented rather than mysterious, and
`out/_run.json` records which archives your run actually read.

**It takes much longer than thirty seconds.** The first run reads about 0.3 GB of
play-by-play off disk. On a slow drive, two or three minutes is normal. If it is
still going after ten, stop it with Control-C and run `make rankings` first to
confirm the data is intact.

**The gate command prints `KeyError`.** `make backtest` did not finish, so
`out/backtest_metrics.json` is missing or truncated. Run it again.

---

## Try it

Ten minutes.

**Step 1.** Print every system's five gate numbers, not just ours, and see how
the field looks against the same bar.

<!-- verify: run timeout=600 -->
```bash
uv run python - <<'PY'
import json

metrics = json.load(open("out/backtest_metrics.json"))

print(f'{"system":16} {"SU%":>7} {"MAE":>8} {"RMSE":>8} {"viol%":>7}  gate')
for name, block in sorted(metrics["systems"].items()):
    gate = block.get("gate") or {}
    seen = gate.get("observed") or {}
    if not seen:
        continue
    violations = seen.get("retrodictive_violation_rate")
    shown = f"{violations:.4f}" if violations is not None else "-"
    print(
        f"{name:16} {seen['su_accuracy']:>6.2%} {seen['mae']:>8.3f} "
        f"{seen['rmse']:>8.3f} {shown:>7}  "
        f"{'PASS' if gate.get('passed') else 'fail'}"
    )
PY
```

```text
system               SU%      MAE     RMSE   viol%  gate
colley           67.95%   13.562   17.237  0.1962  fail
elo              68.77%   13.559   17.098  0.2250  fail
home_team        56.34%   15.458   19.863       -  fail
l1               69.15%   13.165   16.684  0.2396  fail
l2               69.53%   13.227   16.740  0.2121  fail
l3               68.71%   13.038   16.531  0.2232  fail
random_walker    65.05%   14.015   17.984  0.1997  fail
resume           68.71%   13.038   16.531  0.1997  fail
schedule_odds    68.71%   13.038   16.531  0.2015  fail
srs              69.09%   13.196   16.695  0.2183  fail
winpct           66.12%   13.824   17.660  0.1780  fail
```

`home_team` shows a dash in the violations column because it has no ratings, so
there is no ordering that could contradict a result. A system with nothing to say
cannot be wrong in that particular way, which is worth remembering the next time
somebody's model looks unusually clean on one metric.

**Step 2.** Answer these two questions from what printed:

- Which system has the best MAE, and is it ours?
- Does any system clear the gate?

**Step 3.** Open [`demo/backtest-2021-2023.md`](../../demo/backtest-2021-2023.md)
and find the protocol section. Read the bullet about blend weights being fitted
on out-of-sample games only. You do not need to understand the mechanism. Notice
that the project measured what the strict version cost and published the cost.

A good result looks like: you can say out loud that no system clears the gate,
that ours has the best MAE in the comparison and that this is still a failure,
and that those two facts are not in tension.

## Check yourself

1. What does walk-forward prevent, and why is a batch refit especially at risk?
2. MAE is about 13 for every serious system in the table. Is that good?
3. Win percentage beats this model on violations. Why, and is it a defect?
4. What is a holdout season, and what does spending it cost you?
5. The gate has two criteria marked "undecided." Why is that better than calling
   them passed?

**Answers.**

1. It prevents a model from being graded on games it was fit on. A batch refit
   recomputes the whole season each week, so it is unusually easy to hand it a
   column containing information from after the game being predicted.
2. It is what the sport is. Every system in the comparison is between 13 and 15
   points of average error, and a claim of much better than that deserves a hard
   look at what got measured.
3. Because a rating built only from record almost never contradicts a head-to-head
   result, while a rating that discounts a win over a weak opponent sometimes
   will. It is the price of adjusting for schedule, and it is printed rather than
   hidden.
4. A season the project agrees not to score until one decisive test. Spending it
   means you no longer have an unseen season, so any later result on it is worth
   much less.
5. Because a criterion that has not been decided is not evidence for anything.
   Calling it passed would inflate the score with something nobody measured.

## In the field

**Someone quotes a rating system that claims 75 percent accuracy.** Ask which
games, which weeks, and whether the model had seen them. Straight-up accuracy
over all games including week 1 blowouts against overmatched opponents is a very
different number from accuracy over conference games in November. This project
publishes both cuts for exactly that reason.

**A friend says the model is bad because it fails its own test.** It is the only
one in the comparison that has a test. The five failing rows are the reason to
take it more seriously rather than less, and the fastest way to make that point
is to ask what the AP poll's MAE is.

**You want to know whether a change you made actually helped.** That is module 05,
and the answer is not "it feels better." It is a delta table.

---

## Quick reference

| Term | Plain version |
|---|---|
| Backtest | Run the model over past seasons and grade every prediction |
| Walk-forward | To predict week N, fit only on data through week N minus 1 |
| Out-of-sample | A game the model had not seen when it predicted it |
| Baseline | A simple system you have to beat before you have shown anything |
| MAE | Average points you miss the final margin by |
| Straight-up % | How often you pick the winner |
| Calibration | Whether your 70 percent claims happen 70 percent of the time |
| Retrodictive violation | Your ranking puts a team below somebody it beat |
| Publication gate | Five thresholds. Nothing clears it, including this project |
| Holdout | A season nobody is allowed to score yet. Here, 2025 |

**Next:** [05. Change one number](05-change-one-number.md). You have read two
people's homework. Now you turn something in.
