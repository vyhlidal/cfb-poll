"""Invariants the research reports state as facts. If one of these breaks, a
claim on the methodology page has become false.

No hypothesis dependency: the "property" here is quantified over a deterministic
sweep of inputs generated from an explicit PCG64 seed, which keeps the test suite
reproducible bit-for-bit (report 03 §9.3 item 2) and the dependency set fixed.
"""

from __future__ import annotations

import numpy as np
import pytest

from cfbpoll.config import load_config
from cfbpoll.model import design, ridge

SEED = 20260812  # configs/default.toml [bootstrap].seed
CONFIG = load_config()


def _rng() -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(SEED))


def test_compressed_response_is_bounded_by_c_plus_beta_w() -> None:
    """report 02 §3.2: tanh asymptotes at +/-C, and the win premium adds beta_w.

    THE GRID NOW CONTAINS `inf`, AND THE INVARIANT IS STATED FOR WHAT IT IS. Campaign
    2 widened `c_grid` under pre-registration to end at the LIMIT of the family - the
    identity response, which does not compress and is therefore not bounded. That is
    not a hole in the invariant; it is the invariant's own boundary case, and the
    reason the widened grid cannot produce another corner solution in C. The bound is
    a property of finite C and is asserted for every finite C in the grid.
    """
    rng = _rng()
    for c in CONFIG["margin"]["c_grid"]:
        for beta_w in CONFIG["margin"]["beta_w_grid"]:
            margins = np.concatenate(
                [
                    rng.integers(-120, 121, size=400).astype(float),
                    np.array([0.0, 1.0, -1.0, 1e6, -1e6]),
                ]
            )
            s = design.compress_margin_array(margins, float(c), float(beta_w))
            if not np.isfinite(c):
                # the uncompressed limit: s = m + beta_w*sign(m), unbounded by design
                assert np.allclose(s, margins + beta_w * np.sign(margins))
                continue
            assert np.all(np.abs(s) <= c + beta_w + 1e-12)
            # and the bound is tight: a big enough margin approaches it
            assert design.compress_margin(1e6, float(c), float(beta_w)) == pytest.approx(
                c + beta_w, abs=1e-9
            )


def test_compressed_response_is_monotone_and_odd() -> None:
    c, beta_w = CONFIG["margin"]["c"], CONFIG["margin"]["beta_w"]
    m = np.arange(1, 90, dtype=float)
    s = design.compress_margin_array(m, c, beta_w)
    assert np.all(np.diff(s) > 0)
    assert np.allclose(design.compress_margin_array(-m, c, beta_w), -s)


def test_ridge_shrinks_every_team_to_the_same_rating_as_lambda_grows() -> None:
    """report 02 §4: the penalty shrinks toward LEAGUE AVERAGE, identically for
    every team. That is a statement about our ignorance, not about any team, and
    it is the whole reason regularization is not a reputation prior."""
    rng = _rng()
    n_teams, n_games = 24, 160
    teams = tuple(f"T{i:02d}" for i in range(n_teams))
    home = rng.integers(0, n_teams, n_games)
    away = (home + 1 + rng.integers(0, n_teams - 1, n_games)) % n_teams
    strength = rng.normal(0, 12, n_teams)
    margin = strength[home] - strength[away] + 3.0 + rng.normal(0, 15, n_games)

    import polars as pl

    frame = pl.DataFrame(
        {
            "game_id": pl.Series(np.arange(n_games), dtype=pl.Int64),
            "game_type": ["regular"] * n_games,
            "neutral_site": [False] * n_games,
            "home_team": [teams[i] for i in home],
            "away_team": [teams[i] for i in away],
            "home_points": pl.Series(np.round(21 + margin).astype(np.int32)),
            "away_points": pl.Series(np.full(n_games, 21, dtype=np.int32)),
        }
    )
    d = design.build_game_design(frame, CONFIG)

    spreads = []
    for lam in (1.0, 10.0, 100.0, 10_000.0, 1e8):
        theta = ridge.solve(d.Z, d.s, d.v, d.penalty, lam)
        spreads.append(float(np.ptp(theta[: d.n_teams])))
    assert spreads == sorted(spreads, reverse=True)
    assert spreads[-1] < 1e-5  # all teams equal, and equal to zero
    assert abs(ridge.solve(d.Z, d.s, d.v, d.penalty, 1e8)[d.site_index]) > 0.5


def test_lambda_zero_reproduces_ordinary_least_squares() -> None:
    """Colley = Massey + 2I (report 02 §2.1): our estimator with the penalty
    switched off must BE the least-squares estimator, or the identity is wrong."""
    rng = _rng()
    import polars as pl

    n_teams, n_games = 8, 60
    teams = tuple(f"T{i}" for i in range(n_teams))
    home = rng.integers(0, n_teams, n_games)
    away = (home + 1 + rng.integers(0, n_teams - 1, n_games)) % n_teams
    frame = pl.DataFrame(
        {
            "game_id": pl.Series(np.arange(n_games), dtype=pl.Int64),
            "game_type": ["regular"] * n_games,
            "neutral_site": rng.random(n_games) < 0.2,
            "home_team": [teams[i] for i in home],
            "away_team": [teams[i] for i in away],
            "home_points": pl.Series(rng.integers(0, 60, n_games).astype(np.int32)),
            "away_points": pl.Series(rng.integers(0, 60, n_games).astype(np.int32)),
        }
    )
    d = design.build_game_design(frame, CONFIG)
    dense = np.asarray(d.Z.todense())
    ridge_theta = ridge.solve(d.Z, d.s, d.v, d.penalty, lam=1e-9)
    ols_theta, *_ = np.linalg.lstsq(dense * np.sqrt(d.v)[:, None], d.s * np.sqrt(d.v), rcond=None)
    # OLS is only identified up to a constant shift of the team block; compare
    # the differences, which is what a ranking actually uses.
    a = ridge_theta[: d.n_teams] - ridge_theta[: d.n_teams].mean()
    b = ols_theta[: d.n_teams] - ols_theta[: d.n_teams].mean()
    assert np.allclose(a, b, atol=1e-4)


def test_the_penalty_makes_a_disconnected_schedule_solvable() -> None:
    """report 02 §3.2: L + lambda*I is positive definite for any lambda > 0, so
    the 2020-style disconnected-graph failure of SRS cannot happen here."""
    import polars as pl

    # Two islands that never play each other. Plain least squares is singular.
    rows = [("A", "B"), ("B", "A"), ("C", "D"), ("D", "C")]
    frame = pl.DataFrame(
        {
            "game_id": pl.Series(np.arange(len(rows)), dtype=pl.Int64),
            "game_type": ["regular"] * len(rows),
            "neutral_site": [False] * len(rows),
            "home_team": [r[0] for r in rows],
            "away_team": [r[1] for r in rows],
            "home_points": pl.Series(np.array([31, 10, 24, 17], dtype=np.int32)),
            "away_points": pl.Series(np.array([7, 14, 21, 13], dtype=np.int32)),
        }
    )
    d = design.build_game_design(frame, CONFIG)
    theta = ridge.solve(d.Z, d.s, d.v, d.penalty, lam=2.0)
    assert np.all(np.isfinite(theta))
