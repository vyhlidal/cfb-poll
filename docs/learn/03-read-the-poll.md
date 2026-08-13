# 03. Read the poll you just made

*Reading: about 20 minutes. Doing: about 15 minutes.*

---

## Why a football fan cares

Your friend says the poll is broken because their team is too low. You now have
the poll on your own laptop, so you can do the thing nobody in that argument can
usually do: look up the row and find out which part of the ranking they actually
disagree with.

Almost every top 25 argument is really three different arguments wearing the same
jacket. Is the team good? Did they earn it? Was it hard? This poll keeps those in
separate columns, and after this module you will be able to tell which one your
friend means, sometimes before they can.

## What you will be able to do

- Open `out/poll.csv` and find any team's row.
- Explain what each of the three published numbers claims about a team.
- Read a 90 percent rank interval and say what it does and does not mean.
- Compare a team's live rank with its hindsight rank and explain why they differ.
- Name one thing this poll cannot see.

## What you already have

`out/poll.csv` from module 02, holding 133 ranked teams and 33 columns for the
2023 season through week 15. If you overwrote it while playing with 2022, run
`make rankings` once more before you start.

From module 01 you have a sentence you wrote about one team. Get it out. This
module checks it.

---

## The walkthrough

### Segment 1. What a CSV is, in one paragraph

`poll.csv` is a **CSV**: a plain text file where each line is one team and the
values on that line are separated by commas. The first line names the columns.
Nothing is hidden inside it and nothing is compiled. You can open it in a
spreadsheet by double clicking it, and on a Mac this command does that for you:

<!-- verify: skip reason="opens a GUI spreadsheet application" -->
```bash
open out/poll.csv
```

That is a legitimate way to work and plenty of professionals do it. The terminal
commands below are here because they are exact, repeatable, and paste into a
message when you want somebody else to see what you saw.

### Segment 2. What is actually in there

```bash
uv run python - <<'PY'
import polars as pl
poll = pl.read_csv("out/poll.csv")
print(f"{poll.height} teams, {poll.width} columns")
print(", ".join(poll.columns))
PY
```

```text
133 teams, 33 columns
rank, rank_lo, rank_hi, rank_median, team, wins, losses, odds_key, tail_p,
mid_p, expected_wins, surprise, q_ref, q_ref_team, resume, resume_margin, ...
```

What to notice: 133 teams, and every one of them carries the same 33 columns.
There is no top 25 and a shrug for everybody else. Rank 130 gets an interval and
a power rating just like rank 1 does.

Why that matters: rankings that only publish 25 rows are hiding the part where
they are least sure. You are going to use rows 100 and up in module 06, because
that is where a bad model gives itself away.

### Segment 3. The top 25, readably

<!-- verify: run timeout=600 -->
```bash
uv run python - <<'PY'
import polars as pl

pl.Config(tbl_rows=25, tbl_cols=-1, tbl_width_chars=200,
          tbl_hide_dataframe_shape=True, tbl_hide_column_data_types=True)

poll = pl.read_csv("out/poll.csv")
print(poll.select(
    "rank", "rank_lo", "rank_hi", "team", "wins", "losses",
    pl.col("odds_key").round(3),
    pl.col("resume").round(1),
    pl.col("power").round(1),
    pl.col("gap").round(1),
).head(25))
PY
```

```text
┌──────┬─────────┬─────────┬────────────────┬──────┬────────┬──────────┬────────┬───────┬──────┐
│ rank ┆ rank_lo ┆ rank_hi ┆ team           ┆ wins ┆ losses ┆ odds_key ┆ resume ┆ power ┆ gap  │
╞══════╪═════════╪═════════╪════════════════╪══════╪════════╪══════════╪════════╪═══════╪══════╡
│ 1    ┆ 2       ┆ 40      ┆ Washington     ┆ 13   ┆ 0      ┆ 3.567    ┆ 60.0   ┆ 23.7  ┆ 36.3 │
│ 2    ┆ 1       ┆ 20      ┆ Michigan       ┆ 13   ┆ 0      ┆ 2.545    ┆ 60.0   ┆ 31.9  ┆ 28.1 │
│ 3    ┆ 2       ┆ 36      ┆ Florida State  ┆ 13   ┆ 0      ┆ 2.392    ┆ 60.0   ┆ 23.3  ┆ 36.7 │
│ 4    ┆ 2       ┆ 36      ┆ Alabama        ┆ 12   ┆ 1      ┆ 2.149    ┆ 36.9   ┆ 24.2  ┆ 12.6 │
│ 5    ┆ 1       ┆ 32      ┆ Texas          ┆ 12   ┆ 1      ┆ 2.032    ┆ 36.5   ┆ 25.5  ┆ 11.0 │
│ ...  ┆ ...     ┆ ...     ┆ ...            ┆ ...  ┆ ...    ┆ ...      ┆ ...    ┆ ...   ┆ ...  │
│ 25   ┆ 12      ┆ 88      ┆ Utah           ┆ 8    ┆ 4      ┆ 0.34     ┆ 19.1   ┆ 13.4  ┆ 5.7  │
└──────┴─────────┴─────────┴────────────────┴──────┴────────┴──────────┴────────┴───────┴──────┘
```

That is the top five and the bottom row of the twenty-five your terminal printed.

**Take a screenshot.** This is the poll, as a table you can hand to somebody.

What to notice: `odds_key` falls as you go down, and it falls fast. Washington is
3.567 and Alabama at 4th is 2.149.

Why that matters: `odds_key` is on a **log scale**, which sounds mathematical and
is not. It just means every whole point is a factor of ten. A 3.567 season is
roughly ten times less likely than a 2.5 season and a hundred times less likely
than a 1.5 season. Three whole points of separation between the top team and the
tenth is not a small gap dressed up. It is a thousandfold gap.

### Segment 4. The three numbers, on one row

Look at Washington. `odds_key` 3.567, `resume` 60.0, `power` 23.7.

- **`odds_key`, schedule odds.** How improbable a 13-0 record was against exactly
  that schedule, for a team of published reference quality. Higher is more
  improbable, and more improbable ranks higher. This column is the poll.
- **`resume`.** The team quality that would be expected to produce those exact
  results against that exact schedule. It answers "what have you earned."
- **`power`.** Expected margin against an average team on a neutral field, in
  points. It answers "how good are you."
- **`gap`.** Résumé minus power. Washington is +36.3.

What to notice: `resume` reads exactly 60.0 for Washington, Michigan, Florida
State and Liberty. That is not a coincidence and it is not four teams being
identical. 60 is a ceiling. An undefeated team's résumé has no upper bound the
data can pin down, because "what quality of team wins all of them" has no answer
once you have won all of them. The model stops at 60 and flags it rather than
inventing a number.

Why that matters: this is the clearest example in the whole project of a system
saying "I cannot tell" instead of guessing. When you build your own rating in
module 06, you will find out how easy it is to write code that always produces a
confident number and how rarely that is the same as producing a good one.

### Segment 5. Your team's row

Change `Liberty` to whatever team you want.

<!-- verify: run timeout=600 -->
```bash
uv run python - "Liberty" <<'PY'
import sys

import polars as pl

pl.Config(tbl_cols=-1, tbl_width_chars=200, tbl_hide_dataframe_shape=True,
          tbl_hide_column_data_types=True)

team = sys.argv[1]
poll = pl.read_csv("out/poll.csv")
row = poll.filter(pl.col("team") == team)

if row.is_empty():
    print(f"no team called {team!r}. Check the spelling against out/poll.csv.")
else:
    print(row.select(
        "rank", "rank_lo", "rank_hi", "team", "wins", "losses",
        pl.col("odds_key").round(3),
        pl.col("tail_p").round(4),
        pl.col("resume").round(1),
        pl.col("power").round(1),
        pl.col("gap").round(1),
        "rank_hindsight", "rank_delta",
    ))
PY
```

```text
┌──────┬─────────┬─────────┬─────────┬──────┬────────┬──────────┬────────┬────────┬───────┬──────┬────────────────┬────────────┐
│ rank ┆ rank_lo ┆ rank_hi ┆ team    ┆ wins ┆ losses ┆ odds_key ┆ tail_p ┆ resume ┆ power ┆ gap  ┆ rank_hindsight ┆ rank_delta │
╞══════╪═════════╪═════════╪═════════╪══════╪════════╪══════════╪════════╪════════╪═══════╪══════╪════════════════╪════════════╡
│ 10   ┆ 5       ┆ 56      ┆ Liberty ┆ 13   ┆ 0      ┆ 1.006    ┆ 0.0987 ┆ 60.0   ┆ 18.6  ┆ 41.4 ┆ 8              ┆ 2          │
└──────┴─────────┴─────────┴─────────┴──────┴────────┴──────────┴────────┴────────┴───────┴──────┴────────────────┴────────────┘
```

What to notice: `tail_p` is 0.0987, which is the plain-English version of
`odds_key`. A reference-quality team goes 13-0 against Liberty's schedule about
ten times in a hundred. Washington's `tail_p` is 0.00027, which is about three
times in ten thousand.

Why that matters: both teams went undefeated. One of them did something a good
team would do one season in ten, and the other did something a good team would do
three seasons in ten thousand. "Undefeated" is one word covering an enormous
range, and the reason this poll does not simply rank the unbeaten teams first is
that doing so would throw away that entire distinction.

### Segment 6. The interval, and what it is admitting

Liberty is ranked 10th with an interval of **5th to 56th**.

The model reran the 2023 season a thousand times. Each time it redrew every
game's margin from its own fitted uncertainty, refit everything, and re-ranked.
In the middle 90 percent of those thousand seasons, Liberty finished somewhere
between 5th and 56th.

What to notice: the interval is not "the model is unsure whether Liberty is
good." It is "thirteen games is not very much evidence, and a season is partly
weather."

Why that matters: the median interval width across all 133 teams in this poll is
**73 places**, and the project prints that on
[the poll page itself](../../demo/2023-final-poll.md). No system in its comparison
set publishes anything like it, and the honest reason is that the number does not
make anybody look good.

### Segment 7. Live and hindsight, which is the trick nobody else does

Liberty's `rank_delta` is `+2`. Live, on championship Saturday, they were 10th.
With the whole season's results in hand, they are 8th.

Nothing about Liberty changed. What changed is what the model knows about the
teams Liberty played. Some of those opponents turned out better than they looked
in October, which makes beating them in October worth more than it was worth at
the time.

What to notice: this is the answer to "now that we know that opponent was
overrated, how good was week 5 really?" Most ranking systems cannot answer it,
because they update forward and never go back. This one refits the entire season
from scratch every time, which is slow and is the whole reason retroactive
re-ranking is possible at all.

Why that matters: it is the clearest case in the project of a design decision
made for a reason and paid for in compute. When you meet the same tradeoff in
module 06, you will recognize it.

---

## When it does not work

**`FileNotFoundError: out/poll.csv`.** You are in the wrong folder, or module 02
did not finish. Run `pwd` (it should end in `cfb-poll`) and then `ls out`.

**`no team called 'Ohio st'`.** Team names are spelled the way the data spells
them, capital letters and all. `Ohio State`, `Ole Miss`, `Texas A&M`. Run the
top 25 command from Segment 3 and copy a name out of it exactly.

**Your team is not in the file at all.** The poll ranks 133 teams and there are
more college football teams than that. Teams that played too few games against
the ranked universe are computed but not ranked. That is a real limitation, and
it is the honest kind: the model does not have enough connections to place them.

**The table is squashed and full of `…`.** Your terminal window is narrower than
the table. Make the window wider, or drop a column or two from the list inside
the command.

---

## Try it

Fifteen minutes. Get out the sentence you wrote in module 01.

**Step 1.** Look up the team you picked.

<!-- verify: run timeout=600 -->
```bash
uv run python - "Missouri" <<'PY'
import sys

import polars as pl

pl.Config(tbl_cols=-1, tbl_width_chars=200, tbl_hide_dataframe_shape=True,
          tbl_hide_column_data_types=True)

team = sys.argv[1]
poll = pl.read_csv("out/poll.csv")
row = poll.filter(pl.col("team") == team)
print(row.select("rank", "team", "wins", "losses",
                 pl.col("resume").round(1), pl.col("power").round(1),
                 pl.col("gap").round(1), "rank_hindsight"))
PY
```

**Step 2.** Find the ten teams whose résumé most exceeds their power. These are
the teams that have out-performed how they actually play.

<!-- verify: run timeout=600 -->
```bash
uv run python - <<'PY'
import polars as pl

pl.Config(tbl_rows=10, tbl_hide_dataframe_shape=True,
          tbl_hide_column_data_types=True)

poll = pl.read_csv("out/poll.csv")
print(poll.filter(pl.col("saturated") == 0)
          .sort("gap", descending=True)
          .select("rank", "team", "wins", "losses",
                  pl.col("resume").round(1),
                  pl.col("power").round(1),
                  pl.col("gap").round(1))
          .head(10))
PY
```

The team at the top of that list is **2023 Iowa**, 10-3, with a power rating of
7.6 and a résumé of 20.8. If you watched any college football that year you
already know why, and the model got there without anyone telling it that Iowa's
offense was the story of the season. It found it in the margins.

**Step 3.** Rewrite your module 01 sentence using the actual numbers, naming
which of the three columns you disagree with.

A good result looks like: *"I said Missouri was too high. Their power rank is
worse than their poll rank by ten places, so I was really saying their schedule
odds are overrating close wins. That is a claim about the model's rank key, and
module 05 is where I get to test it."* You have converted an opinion into
something checkable.

## Check yourself

1. A team has `resume` 34.0 and `power` 22.0. What kind of season did they have?
2. Why do four teams all read exactly `60.0` in the résumé column?
3. `odds_key` for the top team is 3.567 and for the tenth team is 1.006. Roughly
   how much more improbable was the top team's season?
4. A team's `rank_delta` is `-4`. What happened?
5. Someone says the 90 percent interval proves the poll is worthless. What is the
   better reading?

**Answers.**

1. They won more than their play suggests, usually by winning close games. The
   gap is +12.
2. It is a ceiling flag. An undefeated team's résumé has no upper bound the data
   can identify, so the model stops at 60 and marks it rather than inventing a
   number.
3. About 360 times, because the column is a log scale and the difference is about
   2.56 whole points.
4. Their opponents turned out worse than they looked at the time, so the same
   wins were worth less once the season finished.
5. Every ranking has that much uncertainty after thirteen games. This one measured
   it and printed it. The interval is a fact about college football rather than a
   defect of this particular poll.

## In the field

**Your roommate is furious that a Group of Five team is ranked ahead of a
two-loss power conference team.** Pull up both rows. If the argument is about
power, the model already agrees with them and the power column shows it. If it is
about the poll, the model is saying the schedule odds were more improbable, and
that is a claim you can both go check against the actual opponents.

**Someone asks why this is better than just watching games.** It is not better. It
is different, and it is checkable. The committee watches games and cannot show
you its arithmetic. This can show you its arithmetic and has never seen a snap.
Both facts are true and the interesting work is in knowing which question you are
asking.

**A friend who does data work asks what the intervals are from.** A thousand
parametric draws on the fixed schedule, refitting and re-ranking each time. The
project publishes that it is a lower bound, because plays are not resimulated.
[`docs/analysis/uncertainty.md`](../analysis/uncertainty.md) has the method and
the disqualified alternative.

---

## Quick reference

| Column | Read it as |
|---|---|
| `rank` | The poll |
| `rank_lo`, `rank_hi` | The 90 percent interval on that rank |
| `odds_key` | How improbable the record was, log scale, higher ranks higher |
| `tail_p` | The same thing as a plain probability |
| `resume` | The team quality those results would be expected from. 60.0 means "off the top of the scale" |
| `power` | Expected margin against an average team, in points |
| `gap` | Résumé minus power. Positive means out-performing your play |
| `rank_hindsight` | Where they land once the whole season is known |
| `rank_delta` | Hindsight minus live. Positive means their opponents got better |

**Next:** [04. Read the scorecard](04-read-the-scorecard.md). The poll grades the
teams. Now something has to grade the poll.
