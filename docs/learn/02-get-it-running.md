# 02. Get it running

*Reading: about 10 minutes. Doing: about 20 minutes, most of it a download.*

---

## Why a football fan cares

Every Sunday in the fall, somebody publishes a top 25 and you get to be annoyed
about it. You have never once been able to open the thing up and look inside.

By the end of this page, your own laptop will have computed a top 25 for the 2023
season, from the actual game results, and printed it. Not downloaded it. Computed
it. Every number on the screen will have come out of arithmetic that ran on your
machine, from data you can inspect, with no account and no permission from
anybody.

That is a strange feeling the first time. It is also the entire premise of the
rest of this track.

## What you will be able to do

- Open a terminal and run a command in a directory you chose.
- Copy this project onto your machine with `git`.
- Install its tools into a private folder that cannot break the rest of your
  computer.
- Produce a 2023 top 25 and a file called `out/poll.csv`.
- Recognize the six ways this step actually fails, and fix each one.

## What you already have

Nothing from module 01 is required to have been installed. You need a computer, a
browser you have already been using, and about 2 GB of free disk.

**Windows users, do this first.** Open PowerShell as administrator, run
`wsl --install`, and restart. You get an Ubuntu window. Everything below happens
in that window and works unchanged. Trying to follow these steps in PowerShell or
Command Prompt will fail on the third command, and that is a tooling difference
rather than anything you did wrong.

---

## The walkthrough

### Segment 1. Open a terminal

On a Mac, press Cmd and Space, type `Terminal`, press Return. On Ubuntu or WSL,
open the Terminal application. A window appears with a line of text and a cursor.

That line is the **prompt**. It is the computer telling you where you are and
waiting. You type a **command**, press Return, and it does the thing and prints
what happened.

What to notice: nothing on that screen can hurt you by being looked at. The
commands in this track are all either "make a copy of something", "install
something into this folder", or "compute something and write a file."

Why that matters: most people who bounce off a terminal bounce off it in the
first four minutes, because it looks like a place where mistakes are permanent.
It mostly is not, and everything in this track happens inside one folder you can
delete.

### Segment 2. Install `uv`, the only tool you have to install

This project runs on Python, and you are about to *not* install Python. A tool
called `uv` does that for you, into a folder inside the project, at the exact
version this project was tested with.

<!-- verify: skip reason="writes a tool into the reader's home directory; CI provisions uv with astral-sh/setup-uv" -->
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On a Mac with Homebrew already installed, `brew install uv` does the same thing.

Then **close the terminal window and open a new one**, so it picks up the newly
installed tool. Check that it worked:

```bash
uv --version
```

```text
uv 0.9.22
```

What to notice: your version number will be higher than that one and that is
fine. What matters is that a version printed instead of `command not found`.

Why that matters: this is the only thing you install globally in the entire
track. Everything else lands inside the project folder. If you decide in module
07 that you hated all of this, deleting one folder undoes it.

### Segment 3. Copy the project onto your machine

```bash
git clone https://github.com/vyhlidal/cfb-poll
cd cfb-poll
```

The first command copies the whole project, including its history, from GitHub to
a new folder called `cfb-poll`. That is what **clone** means. The second command
moves you into that folder, so every command after this one runs in the right
place.

```text
Cloning into 'cfb-poll'...
remote: Enumerating objects: ..., done.
Receiving objects: 100% (...), done.
Resolving deltas: 100% (...), done.
```

What to notice: `cd` changed where you are, and nothing printed. Silence is
success. If you ever lose track, `pwd` prints the folder you are standing in and
`ls` prints what is in it.

Why that matters: the single most common beginner failure in this module is
running the next command from the wrong folder. Everything from here on assumes
you are inside `cfb-poll`.

### Segment 4. Install the tools

```bash
make .venv
```

`make` is a very old program that runs recipes somebody wrote down in a file
called `Makefile`. This recipe asks `uv` to build a **virtual environment**: a
private folder holding this project's own copy of Python and every library it
needs, at exactly the versions it was tested against.

```text
Resolved 61 packages in 12ms
Installed 41 packages in 289ms
 + numpy==2.3.4
 + polars==1.43.2
 + scikit-learn==1.9.0
 ...
```

What to notice: the versions are pinned. Not "the newest numpy", a specific
numpy. The recipe uses `uv sync --locked`, which fails rather than quietly
upgrading anything.

Why that matters: this is why the numbers you produce in five minutes will match
the numbers on the published pages. A project that installs "whatever is newest"
gives a different answer next month and cannot tell you why.

### Segment 5. Compute a poll

This is the long one. It downloads about 0.55 GB of historical play-by-play and
schedule data, checks every file against a fingerprint committed in the
repository, then fits the model and writes the poll.

<!-- verify: run timeout=2400 -->
```bash
make rankings
```

```text
fetch pbp/play_by_play_2023.parquet (110,666,583 bytes)
archive archive/sportsdataverse @ archive-v1: 28 checked, 28 downloaded (549,177,654 bytes), 28 verified
feature audit: PASS - 9 layers rebuilt from their allow-lists
C schedule odds v0 - the headline ordering (Power = L3 v1) - 2023 through 2023-regu-w15:
1557 games, 302 teams, 133 ranked, lambda_l2=0.5 h=2.444
  #   90% int  team                      -log10P         P   resume   power   +/-    gap   rec   retro
  1    2-40    Washington                  3.567  2.71e-04   60.00*   23.71  1.86  36.29  13-0  +0
  2    1-20    Michigan                    2.545  2.85e-03   60.00*   31.92  1.84  28.08  13-0  +0
  3    2-36    Florida State               2.392  4.06e-03   60.00*   23.35  1.82  36.65  13-0  +0
  4    2-36    Alabama                     2.149  7.10e-03   36.85    24.23  1.82  12.62  12-1  +0
  5    1-32    Texas                       2.032  9.30e-03   36.50    25.46  1.84  11.04  12-1  +0
```

**Take a screenshot of that.** You just computed a college football ranking.

What to notice: the Washington row reads **3.567**, and so does the Washington row
on the [published 2023 poll](../../demo/2023-final-poll.md) you read in module 01.
Not close to it. The same number.

Why that matters: you did not verify a claim by trusting a page. You reproduced a
published result on hardware you own. That is the difference between a system
somebody says is open and one that is.

One line in there deserves a second look: `28 checked, 28 downloaded, 28
verified`. Every downloaded file was checked against a fingerprint stored in the
repository before anything read it, and a mismatch stops the run instead of
warning you. You did not have to trust the download either.

### Segment 6. Find what it wrote

```bash
ls out
```

```text
_run.json               poll.json               ratings_hindsight.parquet
model_params.json       rank_intervals.csv      ratings_live.csv
poll.csv                rank_intervals.parquet  ratings_live.parquet
                        ratings_hindsight.csv
```

The exact layout depends on how wide your window is. Ten files is the number that
matters.

`poll.csv` is the poll. `_run.json` is the receipt: which data files this run
actually read, which commit produced it, and every constant it used.

What to notice: `cfbpoll site build` is still a stub in this project, so the poll
arrives as files rather than as a web page. That is a real gap and the project
says so on its own front page rather than pretending.

Why that matters: module 03 is about reading `poll.csv`, and you now have your
own copy of it with a timestamp on it.

---

## When it does not work

**`command not found: uv`.** The installer put `uv` somewhere your current
terminal window does not know about yet. Close the window, open a new one, try
again. If it still fails, run `export PATH="$HOME/.local/bin:$PATH"` and try once
more in that same window.

**`xcrun: error: invalid active developer path`, or a popup asking to install
developer tools.** That is macOS noticing you used `git` for the first time. Click
Install, wait, then run the `git clone` command again. Nothing is broken.

**`command not found: git`, on Ubuntu or WSL.** A fresh Ubuntu does not ship it.
Run `sudo apt update && sudo apt install git make` and enter your own password
when it asks. That is the one place in this track where anything needs
administrator rights, and it is your operating system asking rather than this
project.

**`fatal: destination path 'cfb-poll' already exists`.** You already cloned it.
Run `cd cfb-poll` and carry on from Segment 4.

**`make: *** No rule to make target`, or `command not found: make`.** You are
either in the wrong folder or on Windows outside WSL. Run `pwd`. The answer should
end in `/cfb-poll`. If it does not, `cd` into the folder you cloned.

**The download stalls or dies partway.** Run `make rankings` again. Downloads land
under a temporary name and are only renamed once their fingerprint checks out, so
an interrupted sync resumes rather than restarting, and any file that is there is
a file that was verified.

**It finished but the numbers are not identical to ours.** Check the season and
week: the default is 2023 through week 15. If you overrode either, you computed a
different poll, correctly. For 2021 and 2022 postseason games your numbers will
differ slightly from the published ones on purpose, and
[the project explains exactly why](../../README.md#the-fork-promise).

---

## Try it

Ten minutes, in the same terminal.

**Step 1.** Confirm where you are. The answer should end in `cfb-poll`.

```bash
pwd
```

**Step 2.** Rank a different season. This reuses the data you already downloaded,
so it takes well under a minute.

<!-- verify: run timeout=900 -->
```bash
make rankings RANK_SEASON=2022 RANK_WEEK=15
```

**Step 3.** Look at the top five and write down who is first. It is not
Washington.

**Step 4.** Put 2023 back, because module 03 assumes it.

<!-- verify: run timeout=900 -->
```bash
make rankings
```

A good result looks like: 2022 produces a different top five, in well under a
minute, with no new download. You have now driven the thing rather than run it
once.

## Check yourself

1. What is a virtual environment, in one sentence, and why does this project use
   one?
2. Why does `make rankings` default to 2023 instead of this week?
3. You closed your laptop and came back. What do you type to get back to work?
4. The archive step printed `28 checked, 28 downloaded, 28 verified`. What was
   verified, and against what?

**Answers.**

1. A private folder holding this project's own Python and libraries at pinned
   versions, so the project cannot break other software on your machine and other
   software cannot change this project's answers.
2. Ranking the current week means knowing which week it is, and that needs an API
   key. The default is a completed historical season so the first command a
   stranger types works without an account.
3. Open a terminal, `cd cfb-poll`. The virtual environment stays where it is; you
   do not reinstall anything.
4. The sha256 fingerprint of every downloaded file, against a lockfile committed
   in the repository, before any code read the data.

## In the field

**A friend asks you to prove the poll is not rigged.** Hand them these six
commands. Ten minutes later they have their own copy producing the same numbers.
An open project is one where that sentence is true, and most projects that call
themselves open fail it at the data step.

**Someone says "I could never do that, I do not code."** You did not code. You
copied six lines and pressed Return. The distance between a person who has never
opened a terminal and a person who has run a real model is one afternoon, and
almost all of it is nerve rather than skill.

**Your download is on hotel wifi and the 0.55 GB is a problem.** Every module
after this one reuses what you already have. The download happens once.

---

## Quick reference

| Command | What it does |
|---|---|
| `pwd` | Print where you are |
| `ls` | List what is here |
| `cd cfb-poll` | Move into the project |
| `uv --version` | Check the one tool you installed |
| `make .venv` | Install this project's pinned tools |
| `make rankings` | Download the data, fit the model, write `out/poll.csv` |
| `make rankings RANK_SEASON=2022 RANK_WEEK=15` | The same, for a different week |

**Next:** [03. Read the poll you just made](03-read-the-poll.md).
