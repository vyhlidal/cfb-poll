"""L2 results core: the design, the solver, and the fit.

Most of these run on a hand-built toy league so they assert exact arithmetic
rather than "it did not crash". The archive-backed ones are marked and skip
cleanly on a machine without the archive.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from cfbpoll.config import load_config
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games
from cfbpoll.model import design, l2_results, ridge

CONFIG = load_config()

needs_archive = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised",
)


def toy_games(rows: list[tuple[str, str, int, int]], neutral: bool = False) -> pl.DataFrame:
    """A minimal frame with exactly the columns the L2 path is allowed to see."""
    return pl.DataFrame(
        {
            "game_id": pl.Series(list(range(1, len(rows) + 1)), dtype=pl.Int64),
            "season": pl.Series([2023] * len(rows), dtype=pl.Int32),
            "week": pl.Series([1] * len(rows), dtype=pl.Int32),
            "season_type": ["regular"] * len(rows),
            "game_type": ["regular"] * len(rows),
            "start_date": pl.Series(["2023-09-02T00:00:00.000Z"] * len(rows)).str.to_datetime(
                "%Y-%m-%dT%H:%M:%S%.3fZ", time_zone="UTC"
            ),
            "completed": [True] * len(rows),
            "neutral_site": [neutral] * len(rows),
            "conference_game": [False] * len(rows),
            "home_team": [r[0] for r in rows],
            "away_team": [r[1] for r in rows],
            "home_points": pl.Series([r[2] for r in rows], dtype=pl.Int32),
            "away_points": pl.Series([r[3] for r in rows], dtype=pl.Int32),
            "home_class": ["fbs"] * len(rows),
            "away_class": ["fbs"] * len(rows),
        }
    )


# ------------------------------------------------------------------ the response


def test_compress_margin_matches_the_published_formula() -> None:
    c, beta = 24.0, 3.0
    assert design.compress_margin(0, c, beta) == 0.0
    assert design.compress_margin(1, c, beta) == pytest.approx(
        24 * np.tanh(1 / 24) + 3.0, abs=1e-12
    )
    assert design.compress_margin(-1, c, beta) == pytest.approx(-design.compress_margin(1, c, beta))


def test_a_one_point_win_beats_a_one_point_loss_by_two_times_one_plus_beta() -> None:
    """The win premium, stated the way report 02 §3.2 states it."""
    c, beta = 24.0, 3.0
    gap = design.compress_margin(1, c, beta) - design.compress_margin(-1, c, beta)
    plain = 2 * design.compress_margin(1, c, 0.0)
    assert gap == pytest.approx(plain + 2 * beta, abs=1e-12)


def test_forty_and_sixty_point_wins_are_nearly_the_same() -> None:
    """The sportsmanship property, without discarding margin (report 02 §2.6)."""
    c, beta = 24.0, 3.0
    assert design.compress_margin(60, c, beta) - design.compress_margin(40, c, beta) < 1.5
    assert design.compress_margin(24, c, beta) - design.compress_margin(3, c, beta) > 8.0


# ------------------------------------------------------------------ the design


def test_game_design_shape_and_nonzeros() -> None:
    g = toy_games([("A", "B", 21, 14), ("B", "C", 10, 3)])
    d = design.build_game_design(g, CONFIG)
    assert d.teams == ("A", "B", "C")
    assert d.Z.shape == (2, 4)  # 3 teams + site (no intercept - report 02 §3.2)
    row = d.Z.getrow(0).toarray().ravel()
    assert list(row) == [1.0, -1.0, 0.0, 1.0]
    assert list(d.penalty) == [1.0, 1.0, 1.0, 0.0]


def test_neutral_site_zeroes_the_site_term() -> None:
    d = design.build_game_design(toy_games([("A", "B", 21, 14)], neutral=True), CONFIG)
    assert d.Z.getrow(0).toarray().ravel()[d.site_index] == 0.0


def test_bowl_weight_comes_from_the_config() -> None:
    g = toy_games([("A", "B", 21, 14), ("C", "D", 10, 3)]).with_columns(
        game_type=pl.Series(["bowl_non_cfp", "regular"])
    )
    v = design.game_weights(g, CONFIG)
    assert list(v) == [CONFIG["weights"]["bowl_non_cfp"], CONFIG["weights"]["regular_season"]]


# ------------------------------------------------------------------ the solver


def test_unpenalized_columns_survive_an_enormous_lambda() -> None:
    """Home field must NOT be shrunk (report 02 §3.1, config [ridge] unpenalized)."""
    g = toy_games([("A", "B", 30, 0), ("B", "A", 3, 0), ("A", "C", 20, 10), ("C", "B", 7, 6)])
    d = design.build_game_design(g, CONFIG)
    theta = ridge.solve(d.Z, d.s, d.v, d.penalty, lam=1e9)
    teams = theta[: d.n_teams]
    assert np.allclose(teams, 0.0, atol=1e-6)
    assert abs(theta[d.site_index]) > 1.0


def test_group_folds_are_balanced_and_deterministic() -> None:
    groups = np.arange(100)[::-1]
    a = ridge.group_folds(groups, 5)
    b = ridge.group_folds(groups, 5)
    assert np.array_equal(a, b)
    assert sorted(np.bincount(a).tolist()) == [20, 20, 20, 20, 20]


def test_cv_falls_back_to_maximum_shrinkage_on_a_tiny_frame() -> None:
    d = design.build_game_design(toy_games([("A", "B", 21, 14)]), CONFIG)
    cv = ridge.cv_select_lambda(
        d.Z, d.s, d.v, d.penalty, d.game_ids, CONFIG["ridge"]["l2_grid"], n_folds=5
    )
    assert cv.lam == max(CONFIG["ridge"]["l2_grid"])
    assert cv.n_folds == 0


# ------------------------------------------------------------------ the fit


def test_fit_ranks_a_transitive_toy_league_correctly() -> None:
    games = toy_games(
        [
            ("A", "B", 28, 7),
            ("B", "C", 24, 10),
            ("A", "C", 35, 3),
            ("C", "A", 7, 21),
            ("B", "A", 10, 17),
            ("C", "B", 14, 20),
        ]
    )
    f = l2_results.fit(games, CONFIG)
    order = sorted(f.ratings, key=lambda t: -f.ratings[t])
    assert order == ["A", "B", "C"]


def test_every_team_gets_its_own_coefficient_including_the_thin_ones() -> None:
    """No pooled FCS node - report 02 §3.7 and configs/default.toml [fcs]."""
    games = toy_games([("A", "B", 21, 14), ("A", "Z", 63, 0)]).with_columns(
        away_class=pl.Series(["fbs", "fcs"])
    )
    f = l2_results.fit(games, CONFIG)
    assert set(f.ratings) == {"A", "B", "Z"}
    assert f.n_teams == 3


def test_unseen_team_defaults_to_the_league_average_prior() -> None:
    f = l2_results.fit(toy_games([("A", "B", 21, 14)]), CONFIG)
    assert f.rating("Nobody State") == 0.0


def test_fit_is_pure_and_deterministic() -> None:
    games = toy_games([("A", "B", 28, 7), ("B", "C", 24, 10), ("C", "A", 3, 30)])
    first = l2_results.fit(games, CONFIG)
    shuffled = games.sort("home_team", descending=True)
    second = l2_results.fit(shuffled, CONFIG)
    assert first.ratings == second.ratings
    assert first.home_field == second.home_field
    assert games.equals(games.sort("game_id"))  # the input was not mutated


def test_empty_frame_returns_an_empty_but_valid_fit() -> None:
    f = l2_results.fit(toy_games([("A", "B", 21, 14)]).head(0), CONFIG)
    assert f.ratings == {}
    assert f.n_games == 0
    assert f.lam == max(CONFIG["ridge"]["l2_grid"])


def test_home_and_home_estimator_recovers_a_planted_home_edge() -> None:
    """Report 02 §3.2, after Pasteur: sum margins over reciprocal pairs only."""
    games = toy_games(
        [
            ("A", "B", 24, 20),  # A by 4 at home
            ("B", "A", 21, 17),  # B by 4 at home  -> h = 4
            ("A", "C", 50, 0),  # bought home game, no return trip: excluded
        ]
    )
    assert l2_results.estimate_home_field(games) == pytest.approx(4.0)


def test_home_and_home_estimator_returns_none_without_a_return_trip() -> None:
    assert l2_results.estimate_home_field(toy_games([("A", "B", 24, 20)])) is None


def test_params_publish_beta_w_and_lambda() -> None:
    """Constraint 5: every constant, every week (report 03 §5.3)."""
    p = l2_results.fit(toy_games([("A", "B", 21, 14)]), CONFIG).as_params()
    assert p["beta_w"] == CONFIG["margin"]["beta_w"]
    assert p["C"] == CONFIG["margin"]["c"]
    assert "lambda" in p and "home_field" in p and p["version"] == "v0"


# ------------------------------------------------------------------ real data


@needs_archive
def test_lambda_declines_as_the_season_accumulates_data() -> None:
    """Report 02 §4: 'smaller datasets require higher values'. The early-season
    stabiliser is the penalty itself, not a reputation prior."""
    games = load_games([2023], universe="model")
    lambdas = [
        l2_results.fit(games, CONFIG, through=(2023, "regular", w)).lam for w in (2, 4, 6, 10)
    ]
    assert lambdas == sorted(lambdas, reverse=True)
    assert lambdas[0] > lambdas[-1]


@needs_archive
def test_2023_week_10_top_of_the_table_is_football_reality() -> None:
    games = load_games([2023], universe="model")
    f = l2_results.fit(games, CONFIG, through=(2023, "regular", 10))
    fbs = set(load_games([2023], universe="fbs_vs_fbs")["home_team"].to_list())
    top = [t for t in sorted(f.ratings, key=lambda t: -f.ratings[t]) if t in fbs][:10]
    assert "Ohio State" in top and "Michigan" in top
    assert {"Georgia", "Florida State", "Washington", "Texas"} <= set(top)
