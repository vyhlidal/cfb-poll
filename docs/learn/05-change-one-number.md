# 05. Change one number

*Reading: about 20 minutes. Doing: about 15 minutes.*

---

## Why a football fan cares

"A win is a win."

You have said it. Somebody in your group chat says it every October. It means
that beating a good team by one point should count for a lot more than the
scoreboard makes it look, and that running up 45 on a bad team should not buy you
much.

This model already has an opinion about that, and the opinion is a number:
**7.0**. Seven points of credit for winning, on top of whatever the margin was.
It is the single most argued-over constant in the whole project.

In this module you tell the model that 7.0 is wrong, and then the harness tells
you whether you were right. That whole loop takes about ninety seconds.

## What you will be able to do

- Find a model constant in the config file and explain what it controls.
- Write a challenger entry that changes exactly one number.
- Run your entry through the same harness that scores everything else.
- Read a delta table and say which metrics moved and by how much.
- Explain why beating the model on a metric is not the same as clearing the gate.

## What you already have

Everything from module 02, and the backtest numbers from module 04 in your head.
You do not need `make backtest` to have been run recently; the challenge command
runs its own.

---

## The walkthrough

### Segment 1. Find the number

```bash
grep -n "beta_w = " configs/default.toml
```

```text
232:beta_w = 7.0                                # FITTED 2026-08-12, ADR 0007 (was 3.0)
```

`grep` finds lines in files. `-n` prints the line number. The constant lives on
line 232 of `configs/default.toml`, and every model constant in this project
lives in that one file with a comment saying where it came from.

What to notice: it says `FITTED`, and it says it used to be 3.0. Somebody
searched a grid of candidate values, froze a choice in writing before looking at
the validation season, and then checked it once.

Why that matters: this is what separates a tuned constant from a guess. It also
tells you the honest ceiling on your own idea. The comment a few lines up says
the entire 416-cell search was worth 0.135 points of MAE, best cell to worst, and
the gate needs about 0.22. Changing this number is a real experiment. It is not
going to fix the model, and the project says so in its own config file rather
than letting you discover it.

### Segment 2. Understand what you are changing

The results core scores each game with this:

```text
s = C * tanh(m / C) + beta_w * sign(m)
```

Ignore the shape of it. Two plain sentences cover what you need:

- **`C = 32`** squashes big margins. A 40-point win and a 60-point win end up
  worth nearly the same. This is the answer to "so should teams run up the score?"
- **`beta_w = 7.0`** is a flat bonus for winning, regardless of margin. This is
  the answer to "a win is a win."

What to notice: with `beta_w` at 7.0, winning by 1 is worth roughly what losing by
6 is worth in the other direction, plus the win. Turn it to 0 and this becomes a
scoring-margin ranking. Turn it very high and it becomes close to a win-loss
ranking.

Why that matters: you are not fiddling with an arbitrary dial. You are picking a
point on the line between "football is about margins" and "football is about
winning," which is the actual argument people have every Saturday night.

### Segment 3. Write your entry

A **challenger** is a file that says what you want to change. A parameter
challenger is a `.toml` file with a `[challenger]` block describing your claim,
plus only the constants you are overriding.

Put your own name in the `author` line, then paste the whole block:

<!-- verify: run timeout=600 -->
```bash
cat > configs/challengers/my-first-idea.toml <<'TOML'
[challenger]
name = "beta-w-10"
kind = "parameter"
author = "your name here"
notes = """
A win is a win. The model gives a 7.0-point bonus for winning, on top of the
margin. I think that is too small: beating a good team by one point should count
for a lot more than the scoreboard says. This entry raises the bonus to 10.
"""

[margin]
beta_w = 10.0
TOML
```

`cat > file <<'TOML' ... TOML` writes everything between the markers into a new
file. If you would rather use a text editor, open
`configs/challengers/my-first-idea.toml` and type it in. Either way works.

What to notice: the file contains `beta_w` and nothing else from the model. Not a
copy of the default config with one line changed. Only the difference.

Why that matters: if you copied the whole config and edited one line, nobody
reading your entry could tell what you actually claimed. The `notes` field is
there for the same reason. An experiment whose hypothesis is not written down
before the result is not an experiment.

### Segment 4. The refusal you should meet on purpose

Before running the real one, watch what happens when you get a name wrong.

<!-- verify: run timeout=600 -->
```bash
cat > configs/challengers/typo-demo.toml <<'TOML'
[challenger]
name = "typo-demo"
kind = "parameter"
author = "learn track"

[margin]
beta_win = 10.0
TOML
uv run cfbpoll challenge run --entry configs/challengers/typo-demo.toml || echo "REFUSED, which is the point"
rm configs/challengers/typo-demo.toml
```

The `||` at the end means "if that command fails, run this instead." You expect
this one to fail.

```text
KeyError: "config override sets 'beta_win', which `configs/default.toml` does
not define. An override that names nothing changes nothing, silently."
REFUSED, which is the point
```

You will also see a wall of red with a stack of file names in it. That is normal
and it is not your fault. The useful line is the last one before your own message.

What to notice: `beta_win` is not a real constant. A more forgiving program would
have shrugged, ignored it, and run the default model. You would then have written
up a finding about a model nobody ran.

Why that matters: this is the same habit as everything else in the project.
Failing loudly beats succeeding quietly with the wrong thing, and it is worth
recognizing when you see the pattern somewhere else.

### Segment 5. Run it

<!-- verify: run timeout=2400 -->
```bash
uv run cfbpoll challenge run --entry configs/challengers/my-first-idea.toml
```

This takes about a minute. A parameter challenger is a claim about a constant, so
the harness walks the seasons twice: once under the default config for the
incumbent and every baseline, once under yours.

```text
challenger 'beta-w-10' (parameter) from configs/challengers/my-first-idea.toml
  better  Straight-up %            incumbent     0.6871  challenger     0.6896  (+0.0025)
  worse   Margin MAE               incumbent    13.0378  challenger    13.0522  (+0.0144)
  worse   Margin RMSE              incumbent    16.5312  challenger    16.5534  (+0.0222)
  worse   Brier                    incumbent     0.1971  challenger     0.1972  (+0.0000)
  worse   Log loss                 incumbent     0.5772  challenger     0.5773  (+0.0001)
  worse   Max calib. dev. (pp)     incumbent     7.3699  challenger     7.9721  (+0.6023)
  better  Retrodictive violations  incumbent     0.2015  challenger     0.2006  (-0.0009)
2 of 7 metrics beat the incumbent; clears the gate: False (incumbent: False)
wrote: out/challenge/scorecard.md and out/challenge/scorecard.json
```

**Take a screenshot.** That is your first result.

What to notice: **2 of 7.** You picked more winners and you contradicted fewer
head-to-head results. You also made the margin predictions slightly worse and the
probability calibration meaningfully worse.

Why that matters: that is a completely coherent football finding, and you should
be able to say it in a sentence. Giving more credit for winning makes the ranking
better at ordering teams by who beat whom, and worse at guessing scores. Those are
different jobs, and this model does both, so a change that helps one can cost the
other. Nobody told you that. The delta table did.

### Segment 6. The number that will not match

Look at the incumbent's retrodictive violations: **0.2015**. Now open
[the published scorecard](../../demo/challenge-iterative-margin/scorecard.md) from
module 01. It says **0.2019**.

That difference is real and it is documented. The published run includes 80
postseason games from 2021 and 2022 that came from a private source whose terms
forbid republishing them, so your copy's history for those two seasons stops at
conference championship weekend.

What to notice: both rows in your scorecard came from the same run on the same
games, so your comparison is valid. Only the comparison to a number copied off a
web page is affected.

Why that matters: most projects would let you find this yourself and conclude
something was broken. This one prints which archives your run actually read into
`out/challenge/backtest_metrics_reference.json` under `game_sources`. A difference
you can explain is a different thing from a difference you noticed.

### Segment 7. What you are not allowed to do

Your entry ran on 2021 to 2023. It did not touch 2024 and it cannot touch 2025.

If you try enough values of `beta_w` against the same three seasons, one of them
wins. That does not mean it is better. It means you searched. The only defense is
to fix your claim before you look, and then check it once on a season you have
not used.

What to notice: `cfbpoll challenge run` never passes `--unlock-holdout`, so the
2025 lock is enforced by code rather than by your good intentions.

Why that matters: this is the single most transferable idea in the whole track,
and it has nothing to do with football. Tuning against your test set is how
confident wrong answers get produced in every field that uses data. You now have
a concrete memory of a program refusing to let you do it.

---

## When it does not work

**`No such file or directory: configs/challengers/my-first-idea.toml`.** The
`cat > ... TOML` block did not complete. Paste the entire block including the
final line that says only `TOML`, and press Return after it.

**`KeyError: config override sets 'x'`.** You named a constant that does not
exist. Check your spelling against `grep -n "beta_w" configs/default.toml`.

**`HoldoutLocked`.** You passed `--seasons` including 2025. Drop it and use the
default.

**Nothing prints for a long time.** A parameter challenger runs the walk twice
over three seasons. A minute is normal, three is not alarming.

**Your deltas differ slightly from the ones above.** For 2021 and 2022 that is the
documented archive difference from Segment 6. Your own incumbent-versus-challenger
comparison is still exact, because both rows came out of one run.

---

## Try it

Fifteen minutes. Now make it your own claim.

**Step 1.** Pick a different value and say why before you run it. Lower means
margins matter more. Higher means winning matters more.

<!-- verify: run timeout=600 -->
```bash
cat > configs/challengers/my-second-idea.toml <<'TOML'
[challenger]
name = "beta-w-3"
kind = "parameter"
author = "your name here"
notes = """
The opposite claim. If the model is going to predict scores, margin should carry
more of the weight and the flat win bonus should be small. Three points, about a
field goal.
"""

[margin]
beta_w = 3.0
TOML
```

**Step 2.** Run it, keeping the result in its own folder so your first one
survives.

<!-- verify: run timeout=2400 -->
```bash
uv run cfbpoll challenge run --entry configs/challengers/my-second-idea.toml --out out/challenge/beta-w-3
```

**Step 3.** Write two sentences. Which direction helped straight-up accuracy?
Which direction helped MAE? Do those two answers point the same way?

A good result looks like: you can state a rule you discovered rather than a number
you got. Something like *"raising the win bonus helps the ranking and hurts the
score prediction, and lowering it does the reverse, so the 7.0 they shipped is a
compromise rather than a winner."* That is a real finding about the model, and you
produced it in two runs.

## Check yourself

1. What does `beta_w` control, in football terms?
2. Why does a parameter challenger contain only the keys you are changing?
3. Your entry beat the incumbent on 2 of 7 metrics. Did you beat the model?
4. Why does the harness refuse an override naming a constant that does not exist?
5. You try twelve values of `beta_w` and report the best one. What is wrong with
   that?

**Answers.**

1. A flat bonus for winning, added on top of the compressed margin. It is the dial
   between a scoring-margin ranking and a win-loss ranking.
2. So that a reader can see the claim. A copied config with one edit hides which
   line is the experiment.
3. You beat it on two metrics, which is a finding. Clearing the gate is the
   decision, and neither of you cleared it. The scorecard keeps those apart on
   purpose.
4. Because an override that names nothing changes nothing, silently, and you would
   then publish a result about the default model believing it was yours.
5. You searched rather than predicted. The best of twelve tries wins partly by
   luck, and you have no unseen season left to check it against unless you
   declared the search first.

## In the field

**Someone claims their rating system is better because it weights wins more.** Ask
them better at what. You now know that "more credit for winning" moves ranking
metrics and score-prediction metrics in opposite directions, and that a system
which does not separate those two jobs is hiding the tradeoff rather than
resolving it.

**A friend in a stats class asks what you did.** You ran a controlled experiment.
One variable changed, everything else held identical, evaluated on data neither
version had seen, against the same rivals. That description is worth more in a job
interview than the football is.

**You want to try twenty more values right now.** Do it. Just write down what you
predict before each run, and remember that the only clean check left is 2024, and
that you get 2025 exactly once.

---

## Quick reference

| | |
|---|---|
| `configs/default.toml` | Every model constant, with a comment saying where it came from |
| `beta_w` | The win premium. 7.0 by default |
| `C` | The compression scale. 32.0 by default. Squashes blowouts |
| Parameter challenger | A `.toml` with a `[challenger]` block plus only the keys you change |
| `cfbpoll challenge run --entry FILE` | Score it on the identical harness |
| `--out DIR` | Keep this result in its own folder |
| Delta table | Your seven metrics against the incumbent's |
| Beating a metric | A finding |
| Clearing the gate | The decision. Nothing clears it |

**Next:** [06. Write a rating of your own](06-write-your-own-rating.md). Changing
their number was the warm-up.
