# configs/challengers/

**Fork this and beat the model.** This directory is where community entries live,
and as of 2026-08-13 the harness behind it is real: two worked examples are here,
one of them has a scored scorecard committed at
[`demo/challenge-iterative-margin/`](../../demo/challenge-iterative-margin/), and
`.github/workflows/challenge.yml` runs any entry a pull request adds.

```bash
uv run cfbpoll challenge run --entry configs/challengers/iterative_margin.py
```

## The one rule that makes any of this mean anything

Your entry is scored by the **same** `run_backtest`, on the **same** frames, over
the **same** seasons, against the **same** baselines, with the **same**
publication gate as [`demo/backtest-2021-2023.md`](../../demo/backtest-2021-2023.md).
Nothing in the challenge path re-implements a metric. If it did, the answer would
be a number produced by code that only challengers run, and it would settle
nothing.

## The two kinds of challenger

**1. Parameter variant** — a `<name>.toml` here containing a `[challenger]` block
and *only* the keys you want to change from `configs/default.toml`. Worked
example: [`beta-w-4.toml`](beta-w-4.toml), which argues the 7.0-point win premium
is too high.

A parameter variant is a claim about a constant, so the harness runs twice over
the same seasons and the same systems — once under the default config for the
incumbent and every baseline, once under the merged config for your row. Every
key you name must exist in `configs/default.toml`: an unknown key is **refused**,
not ignored, because an override that names nothing changes nothing silently and
you would then publish a finding about a model nobody ran.

**2. Structural variant** — a module exposing this exact protocol. Worked
example: [`iterative_margin.py`](iterative_margin.py), about forty lines.

```python
CHALLENGER = {"name": "your-name", "kind": "structural", "needs_plays": False}

def rate(games, plays, through_week, config=None, state=None) -> dict[str, float]:
    ...
```

The signature is fixed in `src/cfbpoll/model/__init__.py` as `Rater`. `games` and
`plays` are **already sliced** for you, so a challenger cannot see past
`through_week` — the walk-forward guard lives in the harness, not in your code.
`plays` is `None` unless you declare `needs_plays = true`. A structural variant is
registered as one more system in a **single** run alongside the incumbent and
every baseline, so there is nothing to merge and nothing to argue about.

## What comes back

A scorecard: SU%, MAE, RMSE, Brier, log loss, calibration deviation and
retrodictive violations, side by side with the incumbent, plus the same board for
every baseline and the publication gate applied to all of it. `scorecard.md` is
the summary; `scorecard.json` is the same thing machine-readable; the full metrics
trees land beside them as `backtest_metrics_*.json` so nothing in the summary is
unfalsifiable.

The committed sample entry loses. `iterative-margin` beats the incumbent on
**1 of 7** metrics and clears the gate on 0 of 5 criteria, which is a more useful
worked example than a manufactured win: it shows you what the harness does when an
idea does not work, which is the outcome most ideas have.

**Beating the incumbent on a metric is a finding. Clearing the gate is what the
gate exists to decide.** The scorecard keeps those apart on purpose. A leaderboard
that conflates them stops being a measurement and becomes a marketing surface.

## Two things to know before you start

- **You need no API key and no accounts.** The harness runs entirely on the
  MIT-licensed SportsDataverse archive, published as
  [`archive-v1`](https://github.com/vyhlidal/cfb-poll/releases/tag/archive-v1).
  Fork pull requests receive no repository secrets and the workflow asks for
  none, which is why this is safe for us and frictionless for you.
- **Your incumbent numbers will differ slightly from ours, and that is expected.**
  Our 2021 and 2022 postseason includes 80 games from a private CFBD backfill
  whose terms forbid us to republish it, so your comparison runs on the MIT
  archive alone. Measured on the committed example: the incumbent's retrodictive
  violation rate is 0.2019 here and 0.2015 on a fresh clone. This does not
  compromise a scorecard — both rows in it come from the same run on the same
  frames — but it does mean a number copied from
  [the published backtest](../../demo/backtest-2021-2023.md) will not always match
  yours to the fourth decimal. `out/.../backtest_metrics_reference.json` records
  `game_sources`, which says which archives produced your numbers.
- **2025 is held out and the harness refuses to score it.** It is a single-shot
  test season (report 02 §5.1) and `cfbpoll challenge run` never passes
  `--unlock-holdout`. Tune on 2021–2023, validate on 2024. If you tune against
  2025 and say nothing, the result is meaningless — and if we tune against it, we
  will say so publicly and re-designate.
