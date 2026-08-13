# 06. Write a rating of your own

*Reading: about 25 minutes. Doing: about 40 minutes.*

---

## Why a football fan cares

Here is the oldest argument in the sport, in one line:

> **You are as good as your best win.**

Somebody says it every year about a two-loss team that beat the eventual champion
in September. It is a real theory of ranking. It says margin is noise, that
piling up wins over bad teams proves nothing, and that the only thing worth
knowing about a team is the best thing it did.

Nobody has ever made that person show their work, because there was no way to.
You are about to write it down as a rule a computer can execute, run it against
three seasons of actual football, and find out what it is worth.

## What you will be able to do

- Explain what a `rate()` function has to do and what the harness does for you.
- Describe a football idea precisely enough that code could implement it.
- Use an AI coding assistant as a pair programmer, and name what it will not do.
- Score a structural challenger and read a scorecard where you lost everything.
- Diagnose a loss: say which property of your idea cost you which metric.

## What you already have

From module 05: a working harness, and one experiment already run. From module 04:
the seven metrics and what they measure. You need nothing else installed.

This module reads about forty lines of Python. You are not expected to be able to
write Python. You are expected to be able to read a rule and check that the code
says the same thing the rule says, which is a different and more useful skill.

---

## The walkthrough

### Segment 1. Turn the argument into a rule

"You are as good as your best win" is not yet a rule. Three questions have to be
answered before code can run it:

1. **How good is the team you beat?** Their rating. But their rating depends on
   who *they* beat. So the rule has to be applied over and over until the numbers
   settle down.
2. **What do losses cost?** The bar version says nothing. That cannot be right,
   or a 4-8 team with one great win outranks a 12-1 team. Pick a number: four
   points per loss.
3. **What about a team with no wins at all?** They need a starting value. Twenty
   points below average.

That is the whole rule:

> A team's rating is the rating of the best team it beat, minus four points per
> loss. Teams with no wins start at minus twenty. Repeat fifteen times.

What to notice: two of those three answers were invented by you rather than
derived from anything. Four points per loss is a guess. Fifteen rounds is a guess.

Why that matters: every rating system in the world is made of decisions like
those. The difference between the good ones and the rest is whether the numbers
were guessed once and forgotten, or written down where somebody can change them
and measure what happens. Yours are going to be constants at the top of the file
with their own names, so the person who disagrees with you knows exactly which
line to argue with.

### Segment 2. The contract

A structural challenger is a Python file containing one function with this exact
shape:

```text
def rate(games, plays, through_week, config=None, state=None) -> dict[str, float]
```

You get a table of `games` and you return a dictionary: one number per team.
Higher is better. That is the entire interface.

Three things the harness does for you, which are worth understanding because they
are what makes the result trustworthy:

- **`games` is already cut off at `through_week`.** You physically cannot see a
  game you are about to be graded on. The walk-forward guard from module 04 lives
  in the harness rather than in your code, so no challenger can get it wrong.
- **The scale does not matter.** Return numbers from 0 to 1 or from -400 to 400.
  The harness fits a conversion to points for every system every week, so you are
  never penalized for using different units than somebody else.
- **You are registered as one more system in a single run.** There is nothing to
  merge and no remembered number to compare against.

What to notice: `plays` will be `None` for you, because you are not going to
declare that you need play-by-play data. You are rating teams from the scoreboard,
which is what the bar argument does too.

Why that matters: the smallest interface that can express your idea is the one to
use. Every extra thing you ask for is a thing that can be wrong.

### Segment 3. Meet your pair programmer

This is the point in the track where an AI coding assistant earns its keep, and it
is worth being precise about why.

You have a rule in English. You need it in Python, matching a specific function
signature, in a file with a specific shape, in a repository whose conventions you
have not read. That translation is exactly the job these tools are good at.

**What it does well.**

- Turns a described rule into working code faster than you could look up the
  syntax.
- Reads the repository around it, so it can match the conventions in
  `configs/challengers/iterative_margin.py` without being told what they are.
- Explains an error message in plain language when something breaks.
- Never gets bored of a small mechanical change you want to try for the fourth
  time.

**What it does not do, and this is the part that matters.**

- It has no idea whether your football idea is any good. It will write clean,
  confident code for a bad idea at exactly the speed it writes it for a good one.
- It will sometimes produce code that runs and does not do what you asked. Not
  often, and not obviously. This is the failure mode to actually watch for.
- It cannot tell you that you beat the model. Only the harness can, and that is
  the entire reason this project is a decent place to learn.

That last point is the shape of the whole thing. You are not being asked to trust
the assistant. You are being handed a measurement that settles the question
independently of anything it or you believe.

**You do not need it to finish this module.** The finished file is in Segment 5,
and pasting it teaches you the same lesson. Installing an assistant means an
account and, depending on how much you use it, a subscription or metered credits.
That is the first thing in this track that costs money, and it is optional. Skip
to Segment 5 if you would rather not.

If you do want one, [Claude Code](https://docs.claude.com/en/docs/claude-code)
runs in the same terminal you have been using:

<!-- verify: skip reason="installs a third-party tool globally and requires an account" -->
```bash
npm install -g @anthropic-ai/claude-code
```

Then run `claude` from inside the `cfb-poll` folder. Other assistants exist and
several are good. This track uses one and does not rank them, because tool
comparisons go stale in weeks.

### Segment 4. What to actually say to it

The quality of what you get back is mostly the quality of what you ask for.
Beginners under-specify and then get frustrated at the result. Here is a prompt
that works, verbatim, and it is long on purpose:

```text
I want to add a structural challenger to this repository. Read
configs/challengers/README.md and configs/challengers/iterative_margin.py first
so you match the conventions.

My rating rule, in football terms:
  - A team's rating is the rating of the best team it beat.
  - Subtract 4 points for every loss.
  - A team with no wins starts at -20.
  - Apply the rule 15 times so the ratings settle, and re-center on zero
    after each round.

Write it to configs/challengers/best-win.py. Put ROUNDS, LOSS_PENALTY and the
no-wins starting value at the top of the file as named constants with comments,
so somebody can argue with my guesses. Do not use plays. Sort team names before
iterating so the result is deterministic. Keep it under 50 lines and readable by
someone who does not know Python.
```

Three things that prompt does, which are the transferable part:

- **It points at examples in the repository** rather than describing conventions
  in the abstract.
- **It states the rule in the domain's own terms** rather than in code terms. You are the
  one who knows football. Let it do the translation.
- **It names the constraints that matter to you**: named constants, determinism,
  length, readability. Unstated preferences do not happen.

What to notice: it also says "do not use plays" and "sort team names." Those are
correctness requirements, and you know them because you read Segment 2.

Why that matters: the assistant is faster than you at writing code and worse than
you at knowing what the code has to be true about. Every requirement you can state
is one you do not have to catch later.

**Then read what it wrote.** Not to check the Python. To check that the code says
the same thing your rule says. If your rule says four points per loss, find the
four. If it says fifteen rounds, find the fifteen. That is a review you are
qualified to do today.

### Segment 5. The file

This is what came back, cleaned up. Paste it whether or not you used an assistant.

<!-- verify: run timeout=600 -->
```bash
cat > configs/challengers/best-win.py <<'PY'
"""You are as good as your best win.

The bar argument, written down. A team is worth the rating of the best team it
beat, minus a penalty for every loss. Margin does not count. A 45-point win over
a bad team is worth exactly what a 1-point win over that same team is worth.
"""

CHALLENGER = {
    "name": "best-win",
    "kind": "structural",
    "author": "learn track, module 06",
    "needs_plays": False,
    "notes": "A team is worth its best win, minus 4 points per loss.",
}

ROUNDS = 15          # how many times to re-rate everyone
LOSS_PENALTY = 4.0   # points off per loss
NO_WINS = -20.0      # where a winless team starts


def rate(games, plays=None, through_week=None, config=None, state=None):
    if games.is_empty():
        return {}

    home = games["home_team"].to_list()
    away = games["away_team"].to_list()
    home_points = games["home_points"].to_list()
    away_points = games["away_points"].to_list()

    teams = sorted(set(home) | set(away))
    beaten = {team: [] for team in teams}
    losses = dict.fromkeys(teams, 0)

    for h, a, hp, ap in zip(home, away, home_points, away_points, strict=True):
        if hp is None or ap is None or hp == ap:
            continue
        winner, loser = (h, a) if hp > ap else (a, h)
        beaten[winner].append(loser)
        losses[loser] += 1

    rating = dict.fromkeys(teams, 0.0)
    for _ in range(ROUNDS):
        updated = {}
        for team in teams:
            best_win = max((rating[o] for o in sorted(beaten[team])), default=NO_WINS)
            updated[team] = best_win - LOSS_PENALTY * losses[team]
        average = sum(updated.values()) / len(updated)
        rating = {team: value - average for team, value in updated.items()}

    return rating
PY
```

Read it against the rule. `LOSS_PENALTY = 4.0` is the four points. `ROUNDS = 15`
is the fifteen. The `max(...)` line is "the best team it beat." The last line of
the loop is the re-centering.

What to notice: `sorted(set(home) | set(away))` and `sorted(beaten[team])`. Those
sorts do not change the answer mathematically. They make the order the computer
adds things up in depend on the data rather than on the order things happened to
land in memory, so the same input always produces the identical output.

Why that matters: a rating that moves slightly between two runs of the same code
settles nothing, and it is a genuinely nasty bug to find later. This repository
treats determinism as a feature and asks contributors to as well.

### Segment 6. Score it

<!-- verify: run timeout=2400 -->
```bash
uv run cfbpoll challenge run --entry configs/challengers/best-win.py --out out/challenge/best-win
```

About twenty seconds, because a structural challenger runs once rather than twice.

```text
challenger 'best-win' (structural) from configs/challengers/best-win.py
  worse   Straight-up %            incumbent     0.6871  challenger     0.6347  (-0.0524)
  worse   Margin MAE               incumbent    13.0378  challenger    14.7374  (+1.6995)
  worse   Margin RMSE              incumbent    16.5312  challenger    18.8321  (+2.3009)
  worse   Brier                    incumbent     0.1971  challenger     0.2281  (+0.0309)
  worse   Log loss                 incumbent     0.5772  challenger     0.6492  (+0.0719)
  worse   Max calib. dev. (pp)     incumbent     7.3699  challenger    15.6406  (+8.2707)
  worse   Retrodictive violations  incumbent     0.2015  challenger     0.2462  (+0.0447)
0 of 7 metrics beat the incumbent; clears the gate: False (incumbent: False)
wrote: out/challenge/best-win/scorecard.md and out/challenge/best-win/scorecard.json
```

**Take a screenshot.** You wrote a rating system and it lost on all seven.

That is the expected result and it is the honest one. The worked example this
repository ships loses on six of seven, and it was written by the person who built
the model. Yours is a bar argument you turned into code in an afternoon.

### Segment 7. Diagnose the loss

A score you cannot explain is worth almost nothing. This one is explainable, and
working out why is the actual exercise.

Print the whole scorecard. The delta table you already saw is at the top, the same
board for every baseline is under it, and the publication gate is at the bottom.

<!-- verify: run timeout=600 -->
```bash
cat out/challenge/best-win/scorecard.md
```

Three readings, in order of how much they teach.

**Margin error blew up by 1.7 points.** Of course it did. Your rule never looks at
a single score. It knows who won and nothing else, so when the harness asks it to
predict a margin, it is guessing from a rating built out of win-loss information
only. Compare that with `winpct` in module 04, which also ignores margin and also
sits high on MAE. You have independently rediscovered why margin is in almost
every serious rating system.

**Straight-up accuracy fell more than five points.** This is the surprising one. A
best-win rule throws away every game except one per team. A 12-1 team's entire
season collapses to "beat somebody good," and the eleven other wins do nothing.
Rating systems work by pooling evidence, and you built one that discards almost
all of it on purpose.

**Retrodictive violations got worse, not better.** This is the one you should have
predicted would improve, and it is the most interesting failure in the module.
Your rule is built entirely out of who beat whom, so it ought to contradict
head-to-head results less often. It contradicts them more. The reason is the loss
penalty: a team that beat a great opponent and then lost four times gets dragged
below teams it beat, and a chain of those produces contradictions that a
schedule-adjusted rating avoids.

The biggest single number on the board is the calibration deviation, which more
than doubled to 15.64. That one follows from the first reading rather than telling
you anything new. A rating with no margin information cannot produce a sensible
predicted margin, and the probabilities are computed from the margin, so a broken
margin makes broken probabilities. One cause, two failing columns.

What to notice: you can name a property of your idea behind each of the three
results. That is what a diagnosis is.

Why that matters: this is what "beat the model" actually costs, and the number is
now concrete rather than rhetorical. The gap between a good bar argument and a
working rating system is not effort or cleverness. It is that a rating system has
to use all of the evidence, and almost every intuitive shortcut throws most of it
away.

---

## When it does not work

**`SyntaxError` or `IndentationError`.** The paste got mangled. Python cares
about leading spaces. Delete the file with
`rm configs/challengers/best-win.py` and paste the entire block from Segment 5
again in one go, including the last line that says only `PY`.

**`KeyError: 'home_team'`.** Your code asked `games` for a column that is not
there. Column names are fixed by the harness. Copy them out of Segment 5.

**`TypeError: rate() takes N positional arguments`.** Your function signature does
not match the contract. It needs `games`, then `plays`, `through_week`, `config`
and `state` with defaults.

**Every team gets the same rating, or the run produces `nan`.** Your loop is not
converging or something divided by zero. Lower `ROUNDS` to 3 and print the first
few ratings to see what is happening.

**The assistant wrote something you cannot follow.** Ask it to explain the file
line by line, or ask it to rewrite the file so that somebody who does not know
Python can read it. Both work, and the second one usually produces better code.

**The assistant's version scores differently from ours.** That is expected and it
is fine. Your rule and our rule are not identical unless the constants are. Read
its file, find where it disagrees with your rule, and decide which one you meant.

---

## Try it

Thirty minutes. Two experiments and a decision.

**Step 1.** Your loss penalty was a guess. Test it. Four points per loss was
arbitrary, so try twelve.

<!-- verify: run timeout=600 -->
```bash
sed -i.bak 's/^LOSS_PENALTY = 4.0/LOSS_PENALTY = 12.0/' configs/challengers/best-win.py
grep -n "LOSS_PENALTY = " configs/challengers/best-win.py
```

`sed -i.bak` edits the file in place and keeps a copy of the original as
`best-win.py.bak`. Editing it by hand in a text editor works just as well.

**Step 2.** Score the change.

<!-- verify: run timeout=2400 -->
```bash
uv run cfbpoll challenge run --entry configs/challengers/best-win.py --out out/challenge/best-win-12
```

**Step 3.** Compare the two runs and write one sentence about what a heavier loss
penalty did. Then put it back to something you can defend, because module 07
submits this file.

<!-- verify: run timeout=600 -->
```bash
mv configs/challengers/best-win.py.bak configs/challengers/best-win.py
grep -n "LOSS_PENALTY = " configs/challengers/best-win.py
```

A good result looks like: you know which direction the loss penalty pushes each
metric, and you can say why in football terms. If you also went back and changed
the rule itself rather than just a constant, better. The point of the module is
the loop, and the loop is now yours.

## Check yourself

1. Why is it impossible for your `rate()` function to cheat by looking ahead?
2. Why does the harness not care what scale your numbers are on?
3. Your entry lost on margin error by 1.7 points. What property of your rule
   caused that, specifically?
4. What is the AI assistant good for here, and what can it not settle?
5. Why do the two `sorted(...)` calls matter if they do not change the answer?

**Answers.**

1. Because `games` is truncated to `through_week` before your function is called.
   The guard lives in the harness, so it is enforced for every entry identically.
2. It fits a conversion to points for every system every week, so ratings on
   different scales are compared fairly.
3. It never reads a score. It only knows who won, so it has no information from
   which to predict how much anybody wins by.
4. It is good at turning a stated rule into working code that matches the
   repository's conventions, and at explaining errors. It cannot tell you whether
   the idea is good. The harness does that, which is why the harness is the
   trustworthy part.
5. Because they fix the order the computer adds numbers in, so the same input
   always gives a bit-identical answer. A rating that drifts between runs of the
   same code settles nothing.

## In the field

**Someone says AI writes all the code now and there is nothing left to learn.**
You just watched it write forty correct lines for an idea that lost on all seven
metrics. The code was never the hard part. Knowing what to measure, and being
willing to publish the answer when it goes against you, is the part that does not
automate.

**A friend has a ranking idea and wants to argue about it.** Ask them for the rule
in three sentences, the way Segment 1 does. Most ranking arguments dissolve at
that step, because the person has not decided what losses cost. If they get
through it, they have a challenger and this repository will score it.

**You are asked in an interview what you have built.** You wrote a rating system,
scored it on a public harness against seven baselines with a strict walk-forward
protocol, and diagnosed why it lost. That is a more honest description of
technical work than most portfolio projects, precisely because it did not win.

---

## Quick reference

| | |
|---|---|
| Structural challenger | A `.py` file with a `CHALLENGER` dict and a `rate()` function |
| `rate(games, plays, through_week, config, state)` | The fixed signature |
| Returns | `{team_name: rating}`, higher is better, any scale |
| `games` | Already truncated to `through_week`. You cannot see ahead |
| `needs_plays` | Leave it `False` unless you use play-by-play |
| Determinism | Sort before iterating, always |
| `--out DIR` | Keep each run's scorecard separate |
| Expected outcome | A loss. Ours loses too |

**Next:** [07. Open the pull request](07-open-the-pull-request.md). Right now your
result exists on one laptop.
