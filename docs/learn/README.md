# Build a college football ranking, and learn how AI actually gets used

**Seven modules. You start having never opened a terminal. You finish holding a
scored report card on a ranking idea that is yours.**

This is not a Python course. It is not a statistics course. It is a football
project that happens to teach you the working shape of modern technical work:
get a real system running, read what it produces, change something, measure
whether the change helped, and publish the result so a stranger can check it.

The football is the point, and it is also the reason the lesson sticks. You have
argued about the top 25. You already know the questions. The only new thing here
is that you get to settle one of them with a number instead of a voice.

---

## What you will have at the end

A file with your own ranking idea in it, and a scorecard that says, mechanically,
whether it was better than the model in this repository. Seven metrics, side by
side with the incumbent and with every other system in the comparison, produced by
the same code that scores everything else here.

You do not have to trust the scorecard, and you do not have to trust us. You run
it yourself, on your own machine, from data anyone can download.

Most ideas lose. Ours loses. The worked example this repository ships loses on
six of seven metrics, [on purpose](../../demo/challenge-iterative-margin/scorecard.md).
Learning to read a loss correctly is most of the skill.

---

## The modules

| # | Module | What you end up looking at | Reading | Doing |
|---|---|---|---|---|
| 01 | [Start at the end](01-what-you-are-about-to-build.md) | A real scorecard, before you install anything | 15 min | 0 |
| 02 | [Get it running](02-get-it-running.md) | A top 25 your own laptop computed | 10 min | 20 min |
| 03 | [Read the poll you just made](03-read-the-poll.md) | Your team's row, and why it sits there | 20 min | 15 min |
| 04 | [Read the scorecard](04-read-the-scorecard.md) | Every system's accuracy, including ours failing | 20 min | 10 min |
| 05 | [Change one number](05-change-one-number.md) | Your first delta table | 20 min | 15 min |
| 06 | [Write a rating of your own](06-write-your-own-rating.md) | Your idea, scored on seven metrics | 25 min | 40 min |
| 07 | [Open the pull request](07-open-the-pull-request.md) | Your commit, and what CI would do with it | 20 min | 20 min |

**About four hours end to end: a little over two hours of reading, about two hours
at the keyboard, plus one download.** Spread it over a season and it is one module
a week with time left over to watch games.

Do them in order. Each module assumes the one before it ran.

There is a [glossary](GLOSSARY.md). Every term the modules introduce is in it,
one plain line each. Nothing in the modules requires you to have read it first.

---

## What you need

- A Mac or a Linux machine. **On Windows, install WSL first**: open PowerShell as
  administrator, run `wsl --install`, restart, and then follow every module inside
  the Ubuntu window that appears. Everything here works in there unchanged.
- About 2 GB of free disk. The historical data is 0.55 GB and the tools are
  another few hundred megabytes.
- An internet connection for the download in module 02.
- No accounts. No API keys. No credit card. Not for this repository, not for
  anyone else's. That is a deliberate property of the project and module 02
  explains why it was possible.

Two modules mention something optional. Module 06 introduces an AI coding
assistant, which needs an account and may cost money, and that module is written
so that skipping it changes nothing about what you produce. Module 07 wants a free
GitHub account if you decide to submit, and it tells you how to finish without
one.

---

## What this deliberately does not teach

Naming the edges is part of being useful. Each of these is a real subject and
this track is the wrong place for it.

- **Python as a language.** You will edit one function and read about forty lines
  of code. You will not learn Python here. If you want that afterward, the
  official [Python tutorial](https://docs.python.org/3/tutorial/) is free and
  better at it than we would be.
- **The mathematics.** Ridge regression, Poisson binomial tails, and the rest of
  the machinery are written up in [`docs/methodology.md`](../methodology.md). This
  track teaches you to use the model and check it. Understanding why the estimator
  is shaped the way it is is a different journey, and a good one.
- **Building websites or deploying anything.** `cfbpoll site build` is still a
  stub in this repository, and a module that deployed a page which does not build
  would be the one dishonest thing in the track.
- **Automation tools and cloud infrastructure.** Scheduling the weekly run is a
  problem for whoever operates a poll. It is not a thing you need in order to beat
  a model, so it is not here.
- **Which AI coding tool is best.** Module 06 uses one and mentions that others
  exist. Tool comparisons go stale in weeks and they teach nothing durable.

---

## The one thing you should know about this manual

Every command in these seven modules is extracted by a script and run, in order,
in a clone with nothing set up, before the manual is allowed to change:

<!-- verify: skip reason="running the verifier inside its own verification run would recurse" -->
```bash
uv run python scripts/verify_learn_track.py
```

If a command in front of you has stopped working, that script fails and this file
is wrong until somebody fixes it. You are not being asked to guess whether a step
still applies. That is the same discipline the model itself runs under, and it is
the reason to trust anything on this page.

When a command still fails on your machine, every module has a section called
**When it does not work** with the three or four ways it actually breaks. Start
there before you start doubting yourself.

---

*Code is MIT licensed. Published ratings are CC BY 4.0. The data comes from
[SportsDataverse](https://github.com/sportsdataverse) and
[CollegeFootballData.com](https://collegefootballdata.com), and both of them
deserve your support more than we deserve your attention.*
