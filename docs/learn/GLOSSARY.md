# Glossary

Every term the seven modules introduce, one plain line each. Football analogies
appear where they are honest and are left out where they would mislead.

You do not need to read this first. It is here for the moment a word shows up and
you would rather not stop.

---

## The football numbers

**Schedule odds.** How improbable your record was against your exact schedule, for
a team of published reference quality. This is the rank key: the harder it was,
the higher you go. Column name `odds_key`.

**Résumé rating.** The team quality your results would be expected to come from,
given who you played and where. It answers "what have you earned." A value of
exactly 60.0 is a ceiling flag rather than a measurement.

**Power rating.** Expected margin against an average team on a neutral field, in
points. It answers "how good are you." This is the engine, and it is never hidden.

**Gap.** Résumé minus power. Positive means the team has out-performed how it
actually plays, which usually means winning close games.

**Rank interval.** Where a team's rank landed in the middle 90 percent of a
thousand resimulated seasons. Printed beside every rank. Wide intervals are what
thirteen games actually support.

**Live and hindsight.** The same week ranked twice: as it read at the time, and as
it reads once the whole season is known. The difference is what the model learned
about your opponents after you played them.

**Retroactive re-ranking.** Recomputing an earlier week now that you know how good
its opponents turned out to be. Answers "now that we know that team was overrated,
how good was week 5 really?"

**Reference team.** The one free constant in the ranking: the quality level whose
odds everything is measured against. Published every week with the name of the
team it came from.

**Saturation.** An undefeated team's résumé has no upper limit the data can
identify, so the model stops at 60.0 and marks it rather than inventing a number.

---

## How a model gets graded

**Backtest.** Run the model over past seasons and grade every prediction it would
have made. The football version of grading a scout on the players they actually
ranked, years later.

**Walk-forward.** To predict week N, fit only on data through week N minus 1 of the
same season. The model never sees the game it is graded on, and never sees any
game after it.

**Out-of-sample.** A game the model had not seen when it predicted it. The only
kind of prediction worth counting.

**Baseline.** A simple system you have to beat before you have shown anything.
`home_team` always picks the home team and gets 56 percent right, which is the
floor everybody else in the table has to clear.

**MAE.** Mean absolute error. On an average game, how many points did you miss the
final margin by? Every serious system in this comparison sits between 13 and 15.

**RMSE.** The same idea, but one 30-point miss hurts far more than three 10-point
misses. It punishes being spectacularly wrong.

**Straight-up accuracy.** How often you picked the winner. Written `SU%`.

**Brier score and log loss.** Two ways of asking whether your probabilities mean
anything. Lower is better in both.

**Calibration.** Of the games where you said 70 percent, did 70 percent happen? A
model can pick winners well and still be badly calibrated, which matters the moment
anybody uses the probability for anything.

**Retrodictive violation.** Your ranking puts a team below somebody it beat. Not
automatically wrong, because the beaten team might have five other losses, but a
ranking that racks them up is arguing with results it can see.

**Churn.** How many places the average team moves week to week. Context rather than
a score. Very low churn can mean stability or can mean the model is not learning.

**Publication gate.** Five thresholds this project set for itself. It fails all
five, prints them on the front page, and made one of them stricter partway through
at its own cost.

**Holdout.** A season nobody is allowed to score until one decisive test. Here it
is 2025, and the code refuses to score it. You get one look, and spending it costs
you the ability to check anything cleanly afterward.

**Tune and validate seasons.** 2021 to 2023 are where constants get searched. 2024
is where a frozen choice gets checked once. Mixing those up is how confident wrong
answers get made.

**Pre-registration.** Writing down what you are going to test, and what would count
as a win, before you look at the answer. The defense against searching until
something wins by luck.

**Banned input.** Something the constraints forbid the model from using: human
polls, recruiting rankings, prior-season ratings, conference identity, betting
lines. Enforced by rebuilding every model's inputs from a published allow-list and
requiring an identical result.

**Allow-list.** A list of what is permitted, so anything nobody thought of fails
automatically. The opposite of a list of what is banned, which misses whatever
nobody anticipated.

---

## Challenging the model

**Incumbent.** The model currently in this repository, whatever your entry is
being compared against.

**Challenger.** Your entry. Either a parameter variant or a structural variant.

**Parameter variant.** A `.toml` file that changes one or more published constants
and nothing else. The claim is "this number should be different."

**Structural variant.** A `.py` file with a `rate()` function. The claim is "the
whole approach should be different."

**`rate(games, plays, through_week, config, state)`.** The fixed shape a structural
challenger has to have. You get the games, you return one number per team, higher
is better.

**Delta table.** Your seven metrics beside the incumbent's, with the difference.
The thing the harness prints when it finishes.

**Scorecard.** The full written result: the delta table, the same board for every
baseline, and the gate applied to all of it. Written as both `scorecard.md` and
`scorecard.json`.

**"Beating a metric is a finding. Clearing the gate is the decision."** The
scorecard keeps those separate on purpose, because a leaderboard that merges them
stops being a measurement.

**Constant.** A number in `configs/default.toml` that shapes the model. Every one
of them carries a comment saying where it came from.

**Win premium, `beta_w`.** The flat bonus for winning, on top of margin. 7.0
points. The dial between a scoring-margin ranking and a win-loss ranking.

**Compression scale, `C`.** 32.0. Squashes big margins so a 40-point win and a
60-point win are worth nearly the same. The answer to "should teams run up the
score."

---

## The tools

**Terminal.** The window where you type commands. Nothing in this track can damage
anything outside the project folder.

**Prompt.** The line the terminal shows while it waits for you.

**Command.** One instruction you type and run.

**Directory.** A folder. `pwd` prints where you are, `cd` moves, `ls` lists.

**Path.** The address of a file. `configs/challengers/best-win.py` is a path
relative to where you are standing.

**Repository, or repo.** A project folder that `git` is keeping the history of.

**`git`.** The program that records every version of every file and lets many
people propose changes without stepping on each other.

**Clone.** Your own complete copy of a repository on your machine, history and all.

**Branch.** A named line of work. `main` is the official one. Yours is separate and
cannot disturb it.

**Commit.** A saved snapshot with a message explaining why. Recoverable forever.

**Fork.** Your own copy of somebody else's repository on GitHub, under your
account, that remembers where it came from.

**Pull request, or PR.** A formal note saying "here is a change in my copy that I
think belongs in yours."

**CI, continuous integration.** A machine that runs the same checks on every
submission. Here it downloads the archive, audits for banned inputs, scores your
entry and posts the scorecard.

**Secrets.** Passwords and API keys a project stores for its own automation. A
fork's pull request gets none of them here, which is what makes it safe to invite
strangers to submit code.

**`uv`.** The one tool you install. It fetches Python itself and every library at
pinned versions, into a folder inside the project.

**Virtual environment.** That private folder. It means this project cannot break
other software on your machine and other software cannot change this project's
answers.

**Lockfile, and "pinned."** A committed list of exact versions. `uv sync --locked`
fails rather than quietly upgrading something, which is why your numbers match the
published ones.

**`make`, and the `Makefile`.** An old program that runs recipes somebody wrote
down. `make rankings` is a recipe. Every one of them maps to a `cfbpoll` command
you could type yourself.

**Archive.** The 0.55 GB of historical schedules and play-by-play the model runs
on. MIT licensed and republishable, which is the reason no account is needed.

**sha256, checksum, fingerprint.** A short string computed from a file's contents.
If one byte changes, it changes. Every archive file is checked against a
fingerprint committed in the repository before anything reads it.

**CSV.** A plain text table. One line per row, values separated by commas, first
line names the columns. Opens in any spreadsheet.

**JSON.** A plain text format for structured data. `out/_run.json` is the receipt
for a run: which data it read, which commit produced it, every constant it used.

**TOML.** A plain text format for settings. `configs/default.toml` is one.

**Log scale.** A column where each whole point is a factor of ten. `odds_key` is
one, which is why the gap between 3.5 and 1.0 is much larger than it looks.

**Deterministic.** The same input always produces a bit-identical answer. Achieved
by sorting before iterating and never letting the order things landed in memory
reach a result.

**Stub.** A piece of the project that exists as a name and raises an error instead
of pretending to work. `cfbpoll site build` is one.

**WSL.** Windows Subsystem for Linux. The Ubuntu window Windows users work in, so
that everything in this track runs unchanged.

**AI coding assistant.** A tool that turns a described rule into working code,
reads the repository for conventions, and explains errors. It cannot tell you
whether your idea is good. The harness does that.

---

*Missing a word? It belongs here. Open an issue or add it, and see
[module 07](07-open-the-pull-request.md) for how.*
