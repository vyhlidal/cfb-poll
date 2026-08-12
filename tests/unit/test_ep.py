"""Our expected-points model: the shape of the curve, and the constraint.

The EP table is the one place in this project where a published third-party
number was available and was refused (report 01 §5.6). These tests are what make
that refusal checkable rather than merely stated: the football facts the curve
must reproduce, the leakage scope, and the fact that no fit path touches the
shipped column.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from cfbpoll.config import load_config
from cfbpoll.ingest.plays import DEFAULT_ARCHIVE, attach_games, load_plays
from cfbpoll.ingest.sportsdataverse import load_games
from cfbpoll.model import ep

CONFIG = load_config()
SEASONS = (2021, 2022, 2023)

pytestmark = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "pbp").exists(),
    reason="local archive not materialised; run `cfbpoll archive sync`",
)


@pytest.fixture(scope="module")
def joined() -> pl.DataFrame:
    return attach_games(load_plays(SEASONS), load_games(SEASONS, universe="model"))


@pytest.fixture(scope="module")
def model(joined: pl.DataFrame) -> ep.EPModel:
    return ep.fit(joined, CONFIG)


@pytest.fixture(scope="module")
def valued(joined: pl.DataFrame, model: ep.EPModel) -> pl.DataFrame:
    return ep.play_values(joined, model, CONFIG)


def test_canonical_points_snaps_to_published_values() -> None:
    d = np.array([0.0, 2.0, -2.0, 3.0, -3.0, 6.0, 7.0, 8.0, -7.0, 14.0, 1.0])
    got = ep.canonical_points(d, 7.0, 3.0, 2.0)
    assert got.tolist() == [0.0, 2.0, -2.0, 3.0, -3.0, 7.0, 7.0, 7.0, -7.0, 7.0, 2.0]


def test_the_first_and_ten_curve_rises_monotonically_toward_the_goal_line(
    model: ep.EPModel,
) -> None:
    """The single most basic fact about football field position. If this is not
    monotone the model is not an expected-points model."""
    curve = np.array([model.value(1, 3, y) for y in range(1, 100)])
    # curve[0] is 1st-and-10 from the opponent's 1; curve[98] is from our own 1.
    assert np.all(np.diff(curve) < 0)
    assert model.value(1, 3, 99) < 0.5  # backed up on your own goal line
    assert model.value(1, 3, 2) > 4.0  # first-and-goal is worth most of a TD


def test_expected_points_fall_with_the_down(model: ep.EPModel) -> None:
    for ytg in (80, 60, 40, 20):
        values = [model.value(d, 3, ytg) for d in (1, 2, 3, 4)]
        assert values == sorted(values, reverse=True)


def test_expected_points_fall_with_the_distance_to_go(model: ep.EPModel) -> None:
    for ytg in (70, 50, 30):
        short, medium, long_, very_long = (model.value(3, b, ytg) for b in (1, 2, 3, 4))
        assert short > medium > long_ > very_long


def test_next_score_target_is_signed_to_the_team_with_the_ball(
    joined: pl.DataFrame,
) -> None:
    frame = ep.next_score_targets(joined.filter(pl.col("season") == 2023), CONFIG)
    assert set(frame["next_score"].unique().to_list()) <= {0.0, 2.0, -2.0, 3.0, -3.0, 7.0, -7.0}
    # A play that scores is its own next score.
    scorers = frame.filter(pl.col("points_scored") >= 6)
    assert (scorers["next_score"] == 7.0).all()


def test_next_score_never_crosses_a_scoring_segment(joined: pl.DataFrame) -> None:
    """A fourth-quarter play's target must not be an overtime score, and a
    first-half play's must not be a third-quarter score. The feed's own `half`
    column folds overtime into the second half, which is why this module keys on
    `score_segment` instead."""
    frame = ep.next_score_targets(joined.filter(pl.col("season") == 2023), CONFIG)
    last_of_segment = (
        frame.group_by(["game_id", "score_segment"])
        .agg(pl.all().sort_by("play_index").last())
        .filter(pl.col("points_scored") == 0)
    )
    assert (last_of_segment["next_score"] == 0.0).all()


def test_play_value_is_centred_and_scaled_like_expected_points(valued: pl.DataFrame) -> None:
    values = valued["play_value"].to_numpy()
    assert abs(float(np.mean(values))) < 0.05  # a zero-sum quantity by construction
    assert 1.2 < float(np.std(values)) < 2.0


def test_turnovers_are_the_most_costly_plays(valued: pl.DataFrame) -> None:
    by_class = dict(
        valued.group_by("play_class")
        .agg(mean=pl.col("play_value").mean())
        .iter_rows()  # type: ignore[arg-type]
    )
    assert by_class["scrimmage_other"] < -1.5  # fumbles and safeties
    assert abs(by_class["rush"]) < 0.1
    assert abs(by_class["pass"]) < 0.1


def test_only_snaps_are_valued(valued: pl.DataFrame) -> None:
    assert valued["is_snap"].all()
    assert not valued["play_class"].is_in(["kickoff", "two_point", "non_play"]).any()


def test_our_play_value_tracks_the_banned_column_closely(valued: pl.DataFrame) -> None:
    """THE VALIDATION DIAGNOSTIC, AND ONLY THAT (report 02 §3.10).

    If our published-from-scratch model and the shipped black box agree, the
    constraint has cost us nothing measurable and we can put a number on it. The
    number is reported; it is never fitted to and never fed in.
    """
    stats = ep.shipped_epa_correlation(valued, 2023)
    assert stats["n"] > 200_000
    assert stats["pearson_r"] > 0.80
    assert 0.8 < stats["sd_ours"] / stats["sd_theirs"] < 1.25


def test_no_fit_path_reads_the_shipped_column(
    joined: pl.DataFrame, model: ep.EPModel, valued: pl.DataFrame
) -> None:
    banned = {"EPA", "ep_before", "ep_after", "ppa", "wpa", "shipped_epa"}
    assert banned.isdisjoint(set(joined.columns))
    assert banned.isdisjoint(set(valued.columns))
    assert banned.isdisjoint(set(model.as_params()))
    # ours are named so that no reader can confuse the two
    assert {"our_ep_before", "our_ep_after", "play_value"} <= set(valued.columns)


def test_fit_is_a_pure_function_of_the_plays_it_is_given(joined: pl.DataFrame) -> None:
    """Walk-forward safety at the EP layer: a table fitted through week 5 cannot
    depend on week 6, because `fit` does no slicing and sees only what it is
    handed (report 02 §5.1)."""
    early = joined.filter(pl.col("week") <= 5)
    a = ep.fit(early, CONFIG)
    b = ep.fit(early, CONFIG)
    assert np.array_equal(a.table, b.table)
    full = ep.fit(joined, CONFIG)
    assert not np.array_equal(a.table, full.table)
    assert a.n_plays < full.n_plays


def test_default_scope_is_the_leak_free_one() -> None:
    assert CONFIG["ep"]["fit_scope"] == "training_window"
