# Contributing

The point of this project is that strangers can check it, run it, and try to beat
it. Contributions are welcome in that spirit.

**Current state: scaffold.** There is no working model yet, so the most useful
contributions right now are corrections to the design, the constants, or the
reasoning in `docs/` — not code against an API that does not exist.

## Setup

```bash
git clone https://github.com/vyhlidal/cfb-poll && cd cfb-poll
make .venv          # uv sync --locked; installs Python 3.12 and every pinned wheel
make test           # pytest
make lint           # ruff
```

You need [uv](https://docs.astral.sh/uv/) and nothing else. `uv` fetches the
interpreter itself; there is no system Python requirement, no compiler, and no
Docker.

**Never hand-edit `uv.lock`.** Change `pyproject.toml` and let `uv` resolve. CI
runs `uv sync --locked`, which fails rather than silently updating a stale lock.

## The rules that are not negotiable

Before proposing anything that touches the model, read
[`docs/constraints.md`](docs/constraints.md). A change that introduces a human
poll, a recruiting prior, a prior-season rating, conference identity, a third-party
rating, or a Vegas line as a **feature** will be rejected regardless of how much it
improves accuracy. That is the entire point of the project, and
`cfbpoll audit-features --fail-on-banned` runs in CI to enforce it mechanically.

Three more, from the research:

- **Walk-forward is strict.** To predict week N, fit on data through week N−1
  only. Any accidental use of future data invalidates the whole exercise, and it
  is the easiest mistake to make when the estimator is a batch refit.
- **2025 is held out.** Single shot. If you tune against it and say nothing, your
  result is meaningless. If we tune against it, we say so publicly and re-designate.
- **Determinism is a feature.** Never `np.random.seed`; use an explicit
  `Generator(PCG64(seed))` with `SeedSequence.spawn`. Sort before writing. Do not
  let dict or groupby iteration order reach a file. See report 03 §9.3.

## Challenging the model

This is the contribution we most want, and it has its own front door:
[`configs/challengers/README.md`](configs/challengers/README.md).

Short version — a challenger is either a parameter override TOML, or a module
implementing:

```python
def rate(games, plays, through_week) -> dict[int, float]: ...
```

Open a PR and CI runs it through the identical harness against the identical
baselines and posts a scorecard: SU%, MAE, RMSE, Brier, calibration, violations,
retro-vs-live divergence, side by side with the incumbent.

*(The harness does not exist yet. It is step 14 of the build order and depends on
the backtest harness, step 5.)*

## Pull requests

- One idea per PR. If a change alters a published number, say so in the
  description and regenerate the affected golden fixture **in the same PR**, so the
  change is reviewed rather than absorbed.
- New constants go in `configs/default.toml` with a comment citing the source, not
  hard-coded in a module.
- If you are making a decision that future contributors will wonder about, add an
  ADR in `docs/adr/`.
- Never commit a secret, a raw CFBD response body, or anything from `archive/` or
  `out/`. All three are gitignored; if you find a path around that, that is a bug
  worth reporting.

## Reporting a data problem

Upstream data has bugs, and finding them is genuinely useful. The known example:
game_id `401778314`, a December 2025 bowl mislabelled `week = 1` upstream, which
`validate/data_quality.py` guards against by name. If you find another, open an
issue with the game id and what is wrong — the validation gate should learn it.
