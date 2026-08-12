# configs/challengers/

**Fork this and beat the model.** This directory is where community entries live.

Empty right now — the challenge harness does not exist yet. It is step 14 of the
build order (report 03 §10) and it needs the backtest harness (step 5) first.

## The two kinds of challenger (report 03 §7.3)

**1. Parameter variant.** Drop a `<name>.toml` here containing only the keys you
want to change from `configs/default.toml`. Example: a challenger arguing the win
premium is too high would ship a file overriding `[margin].beta_w`.

**2. Structural variant.** Add a module exposing this exact protocol:

```python
def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    through_week: int,
) -> dict[int, float]:
    ...
```

The signature is fixed in `src/cfbpoll/model/__init__.py` as `Rater`. `games` and
`plays` are sliced for you so a challenger cannot see past `through_week` — the
walk-forward guard lives in the harness, not in your code.

## What happens then

Open a PR. `challenge.yml` runs your entry through the **identical** walk-forward
harness, on the **identical** MIT archive, against the **identical** baselines
(report 02 §5.3), and posts a scorecard comment: SU%, MAE, RMSE, Brier,
calibration deviation, violations, and retro-vs-live divergence, side by side with
the incumbent. The publication gate from report 02 §5.4 is encoded in the harness,
so "did it beat the model" has a mechanical answer rather than an argument.

## Two things to know before you start

- **You need no API key and no accounts.** The harness runs entirely on the
  MIT-licensed SportsDataverse archive. Fork PRs receive no repository secrets,
  which is why this is safe for us and frictionless for you.
- **2025 is held out and the harness will refuse to score you on it by default.**
  It is a single-shot test season (report 02 §5.1). Tune on 2021-2023, validate on
  2024. If you tune against 2025 and say nothing, the result is meaningless — and
  if we tune against it, we will say so publicly and re-designate.
