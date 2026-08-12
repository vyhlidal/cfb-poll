# tests/unit/

Unit tests for individual functions. **Empty — there are no functions to test yet.**

Real tests that do run today live one directory up: `tests/test_cli.py` (the CLI
surface matches the workflows, and every stub fails loudly) and
`tests/test_config.py` (`configs/default.toml` parses and carries the constants the
research fixed).

## What belongs here once the model exists

- `compress_margin` — monotone, odd-symmetric, asymptotes at ±C, and discontinuous
  at zero by exactly `2·β_w`
- `garbage_time_weight` — the Connelly thresholds applied at the right quarter
  boundaries, and the strict alternative
- the ridge solver against a small hand-checkable system, including that the
  intercept and home-field terms are genuinely unpenalized
- `expected_wins` / `solve_quality` — strictly increasing in q, and the bisection
  recovering a known q to machine precision
- the walk-forward slicer — the leakage guard deserves the sharpest test in the
  repository, because a bug there silently invalidates every number downstream
