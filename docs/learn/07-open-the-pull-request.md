# 07. Open the pull request

*Reading: about 20 minutes. Doing: about 20 minutes.*

---

## Why a football fan cares

Your result exists on one laptop.

That is the difference between having an opinion and making a claim. Right now
you know your best-win rating lost on seven metrics, and nobody else can check
that, argue with it, or build on it. The whole reason this project publishes its
own failing gate is that a number nobody can check is barely a number.

This module puts your work somewhere a stranger can run it. You do not have to
submit anything, and the module tells you how to finish either way. But you should
know exactly what would happen if you did, because the answer is unusually clean:
a machine would score you on the identical harness and post the result, and no
human would get a vote.

## What you will be able to do

- Save your work as a commit on a branch, and explain what both of those are.
- Describe what happens mechanically when a pull request lands here.
- Explain why a stranger's code can run in this project's CI safely.
- Read a losing scorecard as a result rather than a verdict on you.
- Decide, on your own terms, whether your entry is worth submitting.

## What you already have

Two challenger files from module 05 and one from module 06, sitting in
`configs/challengers/` in your clone. Everything below happens in the same
terminal.

Segments 1 through 4 need no account. Segment 5 onward describes what a GitHub
account would add, and you can read it without having one.

---

## The walkthrough

### Segment 1. See what you changed

```bash
git status --short
```

```text
?? configs/challengers/best-win.py
?? configs/challengers/my-first-idea.toml
?? configs/challengers/my-second-idea.toml
```

`git` has been watching the folder the whole time. `??` means "this file is new
and I am not tracking it yet."

What to notice: `out/` is not in that list, even though you wrote a dozen files
into it. Neither is `archive/`. Both are deliberately ignored, because they are
regenerable from the code and the data, and a repository that carries its own
output gets unreadable fast.

Why that matters: the thing you are about to submit is the *recipe* rather than
the result. Anyone can rerun the recipe. That is the property that makes the whole
challenge idea work.

### Segment 2. Tell git who you are

Once per clone. If you have a GitHub account, use its email.

<!-- verify: run timeout=300 -->
```bash
git config user.name "Your Name"
git config user.email "you@example.com"
```

These are local to this folder, so nothing else on your machine changes.

### Segment 3. Make a branch

<!-- verify: run timeout=300 -->
```bash
git checkout -b my-challenger
```

```text
Switched to a new branch 'my-challenger'
```

A **branch** is a named line of work. `main` is the project's official line.
Yours is now a separate line that starts from the same place and cannot disturb
it.

What to notice: nothing was copied and nothing takes up space. A branch is a
label.

Why that matters: this is the convention that makes it safe for strangers to
propose changes to software that other people depend on. Your work is real, it is
saved, and it is not in anybody's way.

### Segment 4. Commit

<!-- verify: run timeout=300 -->
```bash
git add configs/challengers/
git commit -m "Add a best-win challenger, and the two parameter variants behind it"
```

```text
[my-challenger 6a4bf8a] Add a best-win challenger, and the two parameter variants behind it
 3 files changed, 74 insertions(+)
```

A **commit** is a saved snapshot with a message explaining why. `git add` chooses
what goes in it and `git commit` writes it down.

<!-- verify: run timeout=300 -->
```bash
git log --oneline -1
```

```text
6a4bf8a Add a best-win challenger, and the two parameter variants behind it
```

The short string in front is the commit's own name, computed from its contents,
so yours will be different from that one and from everybody else's.

**Take a screenshot.** Your work is now a permanent, named, recoverable thing
rather than a file that a bad afternoon could delete.

What to notice: the message says what changed and why, not "update" or "stuff."
This repository asks for one idea per pull request for the same reason.

Why that matters: you can stop here and have finished the track. Everything from
here needs a free GitHub account, and it is worth understanding whether or not
you make one.

### Segment 5. What a fork is

You do not have permission to write to somebody else's repository, and you should
not want it. A **fork** is your own copy of the project on GitHub, under your
account, that remembers where it came from.

The flow, if you choose to do it:

<!-- verify: skip reason="requires a GitHub account and a browser" -->
```bash
# 1. Click "Fork" at https://github.com/vyhlidal/cfb-poll
# 2. Point your clone at your fork and push the branch to it
git remote add fork https://github.com/YOUR-USERNAME/cfb-poll
git push fork my-challenger
# 3. GitHub prints a link. Open it and fill in the description.
```

That is the whole mechanism. Your branch lands in your copy, and a **pull
request** is a formal note saying "here is a change, in my copy, that I think
belongs in yours."

What to notice: nothing here asks you for a password on the command line. GitHub
will walk you through signing in the first time you push, in a browser.

### Segment 6. What actually happens when you submit

This is the part worth reading even if you never open a pull request, because it
is the thing that makes this project a classroom instead of a leaderboard.

A file lands in `configs/challengers/`. A workflow notices, and it:

1. Installs the same pinned tools you installed in module 02.
2. Downloads the same archive and checks the same fingerprints.
3. Runs `cfbpoll audit-features`, which rebuilds every model's inputs from a
   published allow-list and fails the build if anything banned reached a fit.
4. Runs `cfbpoll challenge run` on your entry, over the same seasons, against the
   same baselines, with the same gate.
5. Posts your scorecard to the run summary and uploads it as a downloadable file.

No human decides your number. The same code that produced every other row in the
table produces yours.

What to notice: step 3 runs *before* your entry is scored. A challenger cannot be
graded past the constraint everybody is competing under, so a leak is a refusal
rather than a scorecard nobody should trust.

Why that matters: this is what "the same harness" means as an engineering claim
rather than a slogan. Nothing in the challenge path recomputes a metric its own
way. If it did, your number would come from code that only challengers run, and
it would settle nothing.

### Segment 7. Why it is safe to invite strangers

This is a small point with a large lesson in it.

Your pull request runs your code in somebody else's CI. That is normally a
frightening thing to allow. It is safe here because of three deliberate choices:

- The workflow triggers on `pull_request` rather than the variant that would run
  your code with the project's own permissions.
- It grants read-only access and no secrets at all.
- The harness needs no secrets, because the archive is MIT-licensed and public.

What to notice: the third one is what makes the first two affordable. The project
could not safely accept challengers if scoring one required an API key.

Why that matters: the licence decision from module 02, the one that let you run
`make rankings` without an account, is the same decision that lets a few hundred
strangers submit code. Openness at the data layer paid off twice, and neither
payoff was obvious in advance.

### Segment 8. How to read your result

Your scorecard will almost certainly say you lost. Three readings, and only one of
them is correct.

**Wrong: "my idea was stupid."** The idea was a real theory of ranking that a lot
of people hold. You are the only person in that argument who has ever measured it.

**Wrong: "the test is rigged against new ideas."** The test is the one the
incumbent fails, publicly, on five of five criteria. It was made stricter during
development and the change cost the maintainers a passing grade, and they kept it.

**Right: "here is what my idea cost, and here is which property caused it."** From
module 06 you can already say it: the rule ignores margin, so margin error blew
up, and it uses one game per team, so it throws away most of the evidence.

That third sentence is a result. It is publishable, it is checkable, and it is
worth more than a win you could not explain.

What to notice: the scorecard's own closing line keeps two things apart. Beating
the incumbent on a metric is a finding. Clearing the gate is what the gate exists
to decide. A leaderboard that merges those two stops being a measurement.

Why that matters: you now have a working example of a field where "I was wrong,
here is by how much" is the normal, respectable output. That is rarer than it
should be, and recognizing it is most of what people mean by scientific literacy.

---

## When it does not work

**`Please tell me who you are`.** You skipped Segment 2. Run those two `git
config` lines.

**`nothing to commit, working tree clean`.** Your files were already committed, or
`git add` did not match them. Run `git status --short` and check the paths.

**`fatal: a branch named 'my-challenger' already exists`.** You already made it.
Run `git checkout my-challenger` without the `-b`.

**`Permission denied` or `403` when pushing.** You pushed to the original
repository instead of your fork. Check that the URL in your `git remote add fork`
line has *your* username in it.

**Your pull request's check is red.** Open the run and read the log. If it failed
in the audit step, your entry consumed something the constraints ban. If it failed
in the challenge step, your code raised an error on data your local run did not
reach. Both are ordinary and both are fixable by pushing another commit to the
same branch.

**You would rather not submit.** Then do not. The commit on your machine is the
outcome the track promised, and every module worked without an account except this
one.

---

## Try it

Twenty minutes. This is the last exercise in the track.

**Step 1.** Write the pull request description you would submit, in a file, so it
exists whether or not you post it.

<!-- verify: run timeout=300 -->
```bash
cat > MY-CHALLENGER.md <<'MD'
## What I claim

You are as good as your best win. A team's rating is the rating of the best team
it beat, minus 4 points per loss.

## What the harness said

0 of 7 metrics beat the incumbent. It does not clear the gate. Neither does the
incumbent.

## Why it lost

It never reads a score, so margin error rose by 1.7 points. It uses one game per
team, so it discards most of the evidence and straight-up accuracy fell more than
5 points. The loss penalty drags teams below opponents they beat, so retrodictive
violations rose rather than falling, which is the opposite of what I expected.

## What I would try next

Replace "best win" with "average of the top three wins" so the rule keeps more
evidence while staying true to the argument.
MD
cat MY-CHALLENGER.md
```

**Step 2.** Read it back and check three things: your claim is stated before your
result, your diagnosis names a property of the rule rather than a mood, and your
next step is something the harness could actually score.

**Step 3.** Delete it from the commit if you are not submitting, or keep it. It is
your repository now.

<!-- verify: run timeout=300 -->
```bash
rm MY-CHALLENGER.md
git status --short
```

A good result looks like: a description a stranger could read in ninety seconds
and know exactly what you claimed, what happened, and why. That format is the same
one every analysis document in this repository uses, and it is the one that
survives contact with somebody who disagrees with you.

## Check yourself

1. What is the difference between a branch and a fork?
2. Why is `out/` not in your commit?
3. A stranger's code runs in this project's CI. Why is that safe here?
4. The feature audit runs before your entry is scored. Why that order?
5. Your entry lost on all seven metrics. Write the one-sentence version of what
   you learned.

**Answers.**

1. A branch is a named line of work inside a repository. A fork is your own copy
   of the whole repository on GitHub. You use a branch to organize your work and a
   fork to have somewhere you are allowed to push it.
2. It is regenerable from the code and the data, and a repository that carries its
   own output becomes unreadable. You submit the recipe.
3. The workflow gives a fork's code read-only access and no secrets, and it can
   afford to because the archive is public and the harness needs no key.
4. So that a challenger which consumed a banned input is refused rather than
   scored. A scorecard produced under a violated constraint is worse than no
   scorecard.
5. Something like: a rating that uses only who you beat throws away the margin and
   most of the schedule, and both losses show up in the metrics you would expect.

## In the field

**Someone asks whether you are a programmer now.** No, and that is not the useful
claim. You ran a real system, changed it deliberately, measured whether the change
helped, and published the result with its failures attached. That loop is the job.
The syntax is the part that gets easier.

**A friend wants to try it.** Send them to
[module 01](01-what-you-are-about-to-build.md). The whole track takes an afternoon
if you push, or a season if you take one module a week, which is the better way to
do it because the poll is live and your entry gets more interesting as the season
gets weirder.

**You want to keep going.** Three directions, all real. Read
[`docs/methodology.md`](../methodology.md) and find out what the model is actually
doing. Read
[`docs/analysis/fresh-eyes-review.md`](../analysis/fresh-eyes-review.md), an
independent review this project commissioned and published verbatim, including the
section on how somebody would attack it. Or go back to module 06 with a better
idea, because that is the one that still has an open question in it.

---

## Quick reference

| Command | What it does |
|---|---|
| `git status --short` | What changed |
| `git config user.name "..."` | Tell git who you are, in this clone |
| `git checkout -b NAME` | Start a new branch |
| `git add PATH` | Choose what goes in the next commit |
| `git commit -m "..."` | Save a snapshot with a reason |
| `git log --oneline -1` | Show the last commit |
| `git push fork BRANCH` | Send your branch to your own copy on GitHub |

| Idea | Plain version |
|---|---|
| Fork | Your own copy of the project on GitHub |
| Branch | A named line of work |
| Commit | A saved snapshot with a message |
| Pull request | A note saying "this change in my copy belongs in yours" |
| CI | A machine that runs the same tests on every submission |

---

**That is the track.** You started having never opened a terminal. You have a
scored scorecard with your own idea in it, a diagnosis of why it lost, and a
commit with your name on it.

The gate is still failing. Nobody has cleared it. That is an open problem sitting
in a public repository with a mechanical way to settle it, and you now know how to
take a swing at it.
