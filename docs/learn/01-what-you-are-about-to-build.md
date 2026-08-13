# 01. Start at the end

*Reading: about 15 minutes. Nothing to install yet.*

---

## Why a football fan cares

December 2023. Florida State finishes 13-0, wins the ACC championship game, and
the College Football Playoff committee leaves them out. First undefeated Power
Five champion ever excluded. Your group chat had opinions. Everyone's did.

Here is the thing nobody in that argument could do: check. The committee's
ranking is thirteen people in a room, and the room does not publish a formula, a
number, or a test you could run against it. When they said Florida State was
worse than a one-loss Alabama, there was no way to be wrong about that, which
also means there was no way to be right.

This project is what the argument looks like when somebody writes it down. Before
you install anything, you are going to read the answer it gives, and the report
card it gives itself.

## What you will be able to do

- Explain the difference between a ranking that asks *how good are you* and one
  that asks *how hard was what you did*.
- Point at the three numbers this project publishes on every team, every week.
- Describe what a scorecard is and why this repository publishes one that fails.
- Say, in your own words, what "beat the model" means here as a mechanical claim.

## What you already have

You already run a ranking system in your head. You watch games, you weigh who
somebody played, you discount a blowout against a bad team, you argue that a
close loss on the road is better than a comfortable win at home. All of that is a
model. It is just written in a language nobody else can execute.

Nothing in this module needs code, math, or a terminal. You need a browser and
about fifteen minutes.

---

## The walkthrough

### Segment 1. The poll, and the argument it settles

Open [**the 2023 final poll**](../../demo/2023-final-poll.md).

Scroll to the main table and find Florida State. The model has them **3rd**.
Georgia, at 12-1, is **7th**. Liberty, undefeated at 13-0 in Conference USA, is
**10th**.

What to notice: Liberty is undefeated and is still behind a one-loss Georgia. The
committee had Liberty 23rd, so this model is closer to the human answer than a
"just rank the unbeatens first" system would be. It got there without knowing
what a conference is. Nothing in the computation has ever heard of the SEC.

Why that matters: the usual complaint about computer rankings is that they are
either naive about strength of schedule or they smuggle in reputation. This one
does neither, and the poll page shows its work for both claims.

### Segment 2. Why there are three numbers

Stay on the same page and look at the columns beside each team.

| Column | The question it answers |
|---|---|
| **Schedule odds** | How hard was it to do what you did? |
| **Résumé** | What have you earned? |
| **Power** | How good are you? |

Florida State's row is the reason all three get published. Their **poll** rank is
3rd. Their **power** rank is 11th. That is an eight-place disagreement inside one
team's row, and it is not an error. The poll says a reference-quality team goes
13-0 against that exact schedule about four times in a thousand. The power rating
says their play was worth about 22 points against an average team, which is
eleventh best, because they won a lot of close games.

What to notice: both statements are true and neither is hidden. A ranking that
published one number would have to pick a side and would look confident about a
question it had not actually settled.

Why that matters: this is the whole product. The disagreement between the two
numbers *is* the information. When you hear "best three-loss team in the
country," that is somebody noticing a gap between résumé and power without having
a column for it.

### Segment 3. The 90 percent interval, which is the honest part

Look at the interval printed next to each rank. Washington is ranked 1st with an
interval of **2nd to 40th**.

That looks embarrassing. It is the most honest thing on the page.

What to notice: the model ran the season a thousand times, redrawing every game's
result from its own fitted uncertainty, and in the middle 90 percent of those
seasons Washington landed somewhere between 2nd and 40th. Thirteen games is a
very small amount of evidence about 133 teams. Everybody's ranking has this
problem. This one prints it.

Why that matters: when you get to module 04 and see the model fail its own
accuracy test, you will already know that the failure is being reported rather
than discovered. The interval is the first sign that this project would rather
look bad than look certain.

### Segment 4. The scorecard, which is where you are headed

Open [**the challenger scorecard**](../../demo/challenge-iterative-margin/scorecard.md).

This is the artifact you produce in module 06. Somebody had a ranking idea, wrote
it down as about forty lines of code, and ran it through the same test as the
model in this repository.

The result, at the top of the page: **1 of 7 metrics beat the incumbent.** It
does not clear the publication gate. Neither does the incumbent.

What to notice: that entry ships with this repository as a worked example, and
the maintainers chose a losing one deliberately. A worked example that wins
teaches you nothing about what happens when your idea does not work, which is
what happens to most ideas.

Why that matters: your module 06 entry will probably lose too. Knowing that in
module 01 is the difference between "I failed" and "I measured."

### Segment 5. The report card the model gives itself

Open [**the walk-forward backtest**](../../demo/backtest-2021-2023.md) and scroll
to the publication gate table.

Five criteria. The model fails all five.

**Take a screenshot of that table.** It is the strangest thing in the project and
the reason to trust the rest of it. You will reproduce it yourself in module 04.

What to notice: one row says a plain win-percentage ranking beats this model on
one of the five criteria, 0.1831 to 0.2019. That is a system with no schedule
adjustment at all, beating the sophisticated one, and it is printed on the
project's own page rather than left out.

Why that matters: a gate you always pass is a decoration. This one was made
stricter during development and the change flipped a criterion from pass to fail,
and the maintainers kept the stricter version. That is the standard this track
holds you to in module 06, and it is the standard you get to hold this project to
starting now.

### Segment 6. What "beat the model" means here

It means one specific mechanical thing.

Your idea is scored by the **same** code, on the **same** games, over the **same**
seasons, against the **same** other systems, with the **same** gate. Nothing in
the challenge path recomputes a metric its own way. If it did, your number would
come from code that only challengers run, and it would settle nothing.

So "did it beat the model" has an answer, and the answer is not a person's
opinion of your idea. That is unusual, and it is the reason this project makes a
decent classroom.

---

## When it does not work

**The demo pages look like a lot.** They are written for people who already build
rating systems, and they are dense on purpose. In module 01 you are only asked to
find the five things named above. Skip everything else. You will come back to
these pages in module 03 and module 04 and they will read differently once your
own copy is running.

**You disagree with the poll.** Good, that is the correct reaction and it is
survivable. Write down the team and the reason. In module 03 you will be able to
check whether your disagreement is about the model's inputs, its method, or its
honest uncertainty, and those are three different arguments.

---

## Try it

No terminal. Five minutes, on the poll page.

1. Pick your team. Find it on the [2023 final poll](../../demo/2023-final-poll.md).
   If they are outside the top 25, pick a team you have a strong opinion about.
2. Write down its poll rank, its résumé rank, and its power rank.
3. Write one sentence naming which of the three you think is most wrong, and why.
4. Write down its 90 percent rank interval.

A good result looks like: *"Missouri is 11th in the poll and 21st in power. I
think the poll is too high on them because their schedule got easier late. Their
interval is 3rd to 49th."* One team, three numbers, one opinion you can test
later.

Keep that sentence. Module 03 comes back to it.

## Check yourself

1. A team is ranked 3rd in the poll and 11th in power. What is the model saying?
2. Why does this repository ship a worked example that loses?
3. The 90 percent rank interval on the top team is 2nd to 40th. Is that a bug?
4. What makes "did your idea beat the model" a mechanical question here rather
   than an argument?

**Answers.**

1. That their results were unlikely against that particular schedule, and their
   underlying play was merely good. Usually it means close wins. Both statements
   are published because both are true.
2. Because most ideas lose, and a worked example that wins would not show you what
   the harness does in the case you are actually going to be in.
3. No. It is the model reporting how little thirteen games tell you about 133
   teams. Every ranking has that uncertainty. This one prints it.
4. Because your entry is scored by the same code, the same games, the same
   seasons, the same rivals and the same gate as everything else on the page.

## In the field

**Your friend says computer polls are garbage because they do not watch the
games.** The honest answer is that this one does not watch the games and says so,
and that the committee also has a formula it just will not write down. Then point
at the gate table. A system that publishes when it is wrong is a different kind of
object from one that does not.

**Somebody says the model is obviously broken because it has your team too low.**
Ask which number they mean. If they mean power, that is a claim about how the team
plays. If they mean the poll, that is a claim about how hard the schedule was.
Those are separate arguments and this project keeps them in separate columns.

**Someone asks what you are actually learning by doing this.** You are learning
the loop that every technical project runs on: get it working, read the output,
change one thing, measure whether it helped, publish so somebody can check you.
Football is just the subject that makes the loop worth finishing.

---

## Quick reference

| | |
|---|---|
| **Schedule odds** | How improbable your record was against your exact schedule. This is the poll. |
| **Résumé** | The team quality your results would be expected from. |
| **Power** | Expected margin against an average team on a neutral field. This is the engine. |
| **Gap** | Résumé minus power. Positive means you have out-performed your play. |
| **Rank interval** | Where the rank landed in the middle 90 percent of a thousand resimulated seasons. |
| **Scorecard** | Seven metrics, your entry against the incumbent and every baseline. |
| **Publication gate** | Five thresholds. Nothing currently clears it, including this project. |

**Next:** [02. Get it running](02-get-it-running.md). You install two things and
your laptop computes a top 25.
