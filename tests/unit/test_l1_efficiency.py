"""L1: the design matrix, the weights, the penalty, and the points scale.

The structural tests run on a tiny synthetic frame so the assertions are exact.
The calibration tests run on the archive, because "lambda lands where the
published ancestor implementation said it would" is only a claim if it is
checked against real data.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from cfbpoll.config import load_config
from cfbpoll.ingest.plays import DEFAULT_ARCHIVE, load_plays, plays_for
from cfbpoll.ingest.sportsdataverse import load_games
from cfbpoll.model import design, ep
from cfbpoll.model import l1_efficiency as l1

CONFIG = load_config()

pytestmark = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "pbp").exists(),
    reason="local archive not materialised; run `cfbpoll archive sync`",
)


@pytest.fixture(scope="module")
def games() -> pl.DataFrame:
    return load_games([2023], universe="model")


@pytest.fixture(scope="module")
def plays(games: pl.DataFrame) -> pl.DataFrame:
    return plays_for(load_plays([2023]), games)


@pytest.fixture(scope="module")
def fitted(plays: pl.DataFrame, games: pl.DataFrame) -> l1.L1Fit:
    return l1.fit(plays, games, CONFIG)


def _toy_plays() -> pl.DataFrame:
    """Four plays, two games, hand-checkable."""
    return pl.DataFrame(
        {
            "game_id": [1, 1, 2, 2],
            "play_index": [1, 2, 1, 2],
            "offense": ["A", "B", "A", "C"],
            "defense": ["B", "A", "C", "A"],
            "period": [1, 1, 4, 4],
            "clock_seconds": [800, 700, 300, 200],
            "yards_to_goal": [70, 60, 50, 40],
            "play_class": ["rush", "pass", "rush", "pass"],
            "score_margin": [0.0, 0.0, 0.0, 40.0],
            "is_kneel": [False, False, False, False],
            "is_spike": [False, False, False, False],
            "neutral_site": [False, False, True, True],
            "offense_is_home": [True, False, True, False],
            "play_value": [1.0, -1.0, 2.0, -2.0],
        }
    )


def test_design_has_four_non_zeros_per_row_and_the_documented_layout() -> None:
    d = design.build_play_design(_toy_plays(), CONFIG)
    assert d.teams == ("A", "B", "C")
    assert d.X.shape == (4, 2 * 3 + 2)
    assert (d.X.getnnz(axis=1) == 4).all()
    dense = d.X.toarray()
    # row 0: A on offence, B on defence, home, intercept
    assert dense[0, 0] == 1.0  # offence A
    assert dense[0, 3 + 1] == 1.0  # defence B
    assert dense[0, d.site_index] == 1.0  # offence is home
    assert dense[0, d.intercept_index] == 1.0
    # row 1: B on offence away
    assert dense[1, d.site_index] == -1.0
    # rows 2-3 are neutral site
    assert dense[2, d.site_index] == 0.0
    assert dense[3, d.site_index] == 0.0


def test_home_field_and_intercept_are_unpenalised() -> None:
    d = design.build_play_design(_toy_plays(), CONFIG)
    assert d.penalty[d.site_index] == 0.0
    assert d.penalty[d.intercept_index] == 0.0
    assert (d.penalty[: 2 * d.n_teams] == 1.0).all()


def test_garbage_time_zeroes_the_right_plays() -> None:
    thresholds = {"q1": 43, "q2": 37, "q3": 29, "q4": 22}
    assert design.garbage_time_weight(1, 42, thresholds) == 1.0
    assert design.garbage_time_weight(1, 43, thresholds) == 0.0
    assert design.garbage_time_weight(4, -22, thresholds) == 0.0  # both sides, symmetric
    assert design.garbage_time_weight(4, 21, thresholds) == 1.0
    # The toy frame's last play is 40 points up in the fourth quarter.
    w = design.play_weights(_toy_plays(), CONFIG)
    assert w.tolist() == [1.0, 1.0, 1.0, 0.0]


def test_kneels_and_spikes_are_zero_weighted() -> None:
    frame = _toy_plays().with_columns(is_kneel=pl.Series([True, False, False, False]))
    assert design.play_weights(frame, CONFIG)[0] == 0.0
    frame = _toy_plays().with_columns(is_spike=pl.Series([False, True, False, False]))
    assert design.play_weights(frame, CONFIG)[1] == 0.0


def test_leverage_weighting_refuses_rather_than_reaching_for_the_banned_column() -> None:
    """report 02 §3.1 lists `4*WP*(1-WP)` as a backtest alternative. Implementing
    it needs a win-probability model; the archive ships one and it is banned."""
    cfg = load_config()
    cfg["garbage_time"] = {**cfg["garbage_time"], "mode": "leverage"}
    with pytest.raises(NotImplementedError, match="win-probability"):
        design.play_weights(_toy_plays(), cfg)


def test_game_weights_multiply_through_to_the_plays() -> None:
    weights = {1: 1.0, 2: 0.25}
    w = design.play_weights(_toy_plays(), CONFIG, weights)
    assert w.tolist() == [1.0, 1.0, 0.25, 0.0]


def test_lambda_lands_where_the_published_ancestor_said_it_would(fitted: l1.L1Fit) -> None:
    """report 02 §2.8: the CFBD ridge implementation searched 75..325 and landed
    at 150-200 for a full FBS season at play level."""
    assert 125.0 <= fitted.lam <= 250.0
    assert fitted.cv.n_folds == CONFIG["ridge"]["cv_folds"]
    assert len(fitted.cv.cv_error) == len(CONFIG["ridge"]["l1_grid"])


def test_k_lands_near_offensive_plays_per_game(fitted: l1.L1Fit) -> None:
    """report 02 §3.1's sanity check: k should be roughly 65-72."""
    assert 60.0 <= fitted.k <= 80.0


def test_home_field_is_positive_and_small(fitted: l1.L1Fit) -> None:
    """The published CFBD estimate is 0.018 EPA/play on an FBS-vs-FBS universe;
    ours is larger because the fit universe includes FBS-vs-FCS and FCS-vs-FCS,
    where the home effect is bigger. What must hold is the sign and the order of
    magnitude - and, on the points scale, the literature's 2.8-3.7 band."""
    assert 0.0 < fitted.home_field < 0.1
    assert 2.0 < fitted.k_intercept + fitted.k_site < 5.0


def test_ratings_are_centred_by_the_penalty(fitted: l1.L1Fit) -> None:
    """Ridge picks the minimum-norm solution, which centres alpha and beta near
    zero and is what gives them their interpretation (report 02 §3.1)."""
    assert abs(float(np.mean(list(fitted.alpha.values())))) < 0.05
    assert abs(float(np.mean(list(fitted.beta.values())))) < 0.05


def test_every_team_in_the_window_gets_its_own_coefficient(
    fitted: l1.L1Fit, plays: pl.DataFrame
) -> None:
    """No pooled FCS node - report 02 §3.7, the pre-2015 FPI failure."""
    seen = set(plays["offense"].unique().to_list()) | set(plays["defense"].unique().to_list())
    valued = plays.filter(pl.col("play_class").is_in(CONFIG["efficiency"]["design_play_classes"]))
    seen = set(valued["offense"].unique().to_list()) | set(valued["defense"].unique().to_list())
    assert set(fitted.alpha) == seen
    assert set(fitted.beta) == seen


def test_unit_splits_exist_and_are_not_in_the_ranking(fitted: l1.L1Fit) -> None:
    assert set(fitted.units) == {"rush", "pass"}
    assert CONFIG["efficiency"]["unit_splits_in_ranking"] is False
    for unit in fitted.units.values():
        assert set(unit.alpha) == set(fitted.alpha)  # shared team index


def test_special_teams_never_reach_the_design(plays: pl.DataFrame, games: pl.DataFrame) -> None:
    """report 02 §3.1: special teams are excluded from L1 in v1 and left to the
    scoreboard, which L2 already reads."""
    model = ep.fit(plays, CONFIG)
    valued = ep.play_values(plays, model, CONFIG)
    keep = CONFIG["efficiency"]["design_play_classes"]
    assert "punt" not in keep
    assert "field_goal" not in keep
    assert "penalty" not in keep
    kept = valued.filter(pl.col("play_class").is_in(keep))
    assert not kept["play_class"].is_in(["punt", "field_goal", "kickoff", "penalty"]).any()


def test_fit_is_deterministic(plays: pl.DataFrame, games: pl.DataFrame) -> None:
    a = l1.fit(plays, games, CONFIG)
    b = l1.fit(plays, games, CONFIG)
    assert a.alpha == b.alpha
    assert a.beta == b.beta
    assert a.lam == b.lam
    assert a.k == b.k


def test_fit_sees_only_the_plays_it_is_handed(plays: pl.DataFrame, games: pl.DataFrame) -> None:
    """Walk-forward at the play level: a fit through week 5 must not move when
    week 6 exists in the archive, because it never receives it."""
    early_games = games.filter(pl.col("week") <= 5)
    early_plays = plays_for(plays, early_games)
    early = l1.fit(early_plays, early_games, CONFIG)
    full = l1.fit(plays, games, CONFIG)
    assert early.n_plays < full.n_plays
    assert early.alpha != full.alpha
    again = l1.fit(early_plays, early_games, CONFIG)
    assert again.alpha == early.alpha


def test_empty_window_returns_a_neutral_fit(games: pl.DataFrame) -> None:
    empty = games.head(0)
    model = ep.fit(plays_for(load_plays([2023]), games).head(0), CONFIG)
    fit = l1.fit(plays_for(load_plays([2023]), empty), empty, CONFIG, ep_model=model)
    assert fit.alpha == {}
    assert fit.net("anyone") == 0.0
