"""The walk-forward harness and its metrics.

The load-bearing test in this file is the planted-future-game one. Everything
else in the project is downstream of "the fit never saw the answer", and that is
the single easiest thing to get wrong when the estimator is a batch refit
(report 02 §5.1).
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from cfbpoll.backtest import metrics, walkforward
from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games

CONFIG = load_config()

needs_archive = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(), reason="local archive not materialised"
)


# ---------------------------------------------------------------------- metrics


def test_straight_up_accuracy_scores_a_zero_prediction_as_a_coin_flip() -> None:
    assert metrics.straight_up_accuracy(np.array([3.0, -3.0]), np.array([7.0, -1.0])) == 1.0
    assert metrics.straight_up_accuracy(np.array([0.0]), np.array([7.0])) == 0.5


def test_margin_errors_are_the_textbook_definitions() -> None:
    e = metrics.margin_errors(np.array([0.0, 0.0]), np.array([3.0, -5.0]))
    assert e["mae"] == pytest.approx(4.0)
    assert e["rmse"] == pytest.approx(np.sqrt((9 + 25) / 2))


def test_win_probability_uses_sigma_from_the_config() -> None:
    sigma = CONFIG["resume"]["sigma"]
    assert metrics.win_probability(np.array([0.0]), sigma)[0] == pytest.approx(0.5)
    assert metrics.win_probability(np.array([sigma]), sigma)[0] == pytest.approx(0.8413, abs=1e-4)


def test_brier_and_log_loss_reward_a_confident_correct_call() -> None:
    good = np.array([0.9, 0.1])
    bad = np.array([0.5, 0.5])
    won = np.array([1.0, 0.0])
    assert metrics.brier(good, won) < metrics.brier(bad, won)
    assert metrics.log_loss(good, won) < metrics.log_loss(bad, won)


def test_log_loss_is_finite_even_on_a_certain_and_wrong_prediction() -> None:
    assert np.isfinite(metrics.log_loss(np.array([1.0]), np.array([0.0])))


def test_calibration_table_recovers_a_perfectly_calibrated_series() -> None:
    rng = np.random.Generator(np.random.PCG64(20260812))
    p = rng.uniform(0.05, 0.95, 20000)
    won = (rng.uniform(size=p.size) < p).astype(float)
    table = metrics.calibration_table(p, won)
    assert metrics.max_calibration_deviation_pp(table) < 3.0


def test_violations_counts_the_loser_ranked_above_the_winner() -> None:
    v = metrics.violations({"A": 10.0, "B": 1.0}, ["A", "B"], ["B", "A"])
    assert v["violations"] == 1.0
    assert v["violation_rate"] == pytest.approx(0.5)


def test_rank_churn_ignores_teams_that_only_appear_once() -> None:
    churn = metrics.rank_churn({"A": 1, "B": 2}, {"A": 2, "B": 1, "C": 3})
    assert churn["churn_all"] == pytest.approx(1.0)
    assert churn["n"] == 2.0
    assert np.isnan(metrics.rank_churn(None, {"A": 1})["churn_all"])


def test_gate_reports_per_criterion_and_never_guesses() -> None:
    verdict = metrics.check_gate(
        {"su_accuracy": 0.72, "mae": 12.4, "rmse": 15.4, "max_calibration_deviation_pp": 2.0},
        CONFIG["gate"],
    )
    assert verdict["su_accuracy"] and verdict["mae"] and verdict["passed"]
    assert "brier_beats_all_baselines" in verdict["undecided"]
    failing = metrics.check_gate({"su_accuracy": 0.5}, CONFIG["gate"])
    assert failing["su_accuracy"] is False and failing["passed"] is False


# ------------------------------------------------------------------- calibration


def test_calibration_recovers_a_planted_linear_relationship() -> None:
    ratings = {"A": 10.0, "B": 0.0, "C": -10.0}
    rows = [("A", "B", 10.0), ("B", "C", 10.0), ("A", "C", 20.0), ("C", "A", -20.0)]
    frame = pl.DataFrame(
        {
            "home_team": [r[0] for r in rows],
            "away_team": [r[1] for r in rows],
            "neutral_site": [True] * len(rows),
            "home_points": pl.Series([int(21 + r[2]) for r in rows], dtype=pl.Int32),
            "away_points": pl.Series([21] * len(rows), dtype=pl.Int32),
        }
    )
    a, b, h = walkforward.calibrate(ratings, frame)
    assert b == pytest.approx(1.0, abs=1e-9)
    assert a == pytest.approx(0.0, abs=1e-9)


def test_a_system_with_no_rating_spread_degrades_instead_of_raising() -> None:
    """The home-team floor has an identically-zero delta column."""
    frame = pl.DataFrame(
        {
            "home_team": ["A", "B"],
            "away_team": ["B", "A"],
            "neutral_site": [False, False],
            "home_points": pl.Series([24, 20], dtype=pl.Int32),
            "away_points": pl.Series([20, 17], dtype=pl.Int32),
        }
    )
    a, b, h = walkforward.calibrate({}, frame)
    assert b == 0.0
    assert a + h == pytest.approx(3.5)


# --------------------------------------------------------------------- the lock


@needs_archive
def test_the_holdout_season_is_refused() -> None:
    with pytest.raises(walkforward.HoldoutLocked) as err:
        walkforward.run_backtest([2024, 2025], ["l2"])
    assert "2025" in str(err.value)


@needs_archive
def test_the_holdout_can_only_be_opened_deliberately() -> None:
    """The flag works - it has to, or the single shot could never be taken -
    but nothing in this repository passes it."""
    result = walkforward.run_backtest([2025], ["winpct"], unlock_holdout=True, first_eval_week=13)
    assert result["protocol"]["holdout_touched"] is True


# ------------------------------------------------------- the leakage guarantee


@needs_archive
def test_walk_forward_never_sees_a_planted_future_game() -> None:
    """Plant an absurd result far in the future and prove no fit can see it.

    2023 Kent State beat Georgia 99-0 in December. If any week-N fit ingested it,
    Kent State's rating would be unmistakable. It is not, because the slicing is
    owned by ingest/windows and every rater is handed an already-truncated frame.
    """
    games = load_games([2023], universe="model")
    planted = games.head(1).with_columns(
        game_id=pl.Series([999_999_999], dtype=pl.Int64),
        week=pl.Series([15], dtype=pl.Int32),
        season_type=pl.Series(["regular"]),
        start_date=pl.Series(["2023-12-09T00:00:00.000Z"]).str.to_datetime(
            "%Y-%m-%dT%H:%M:%S%.3fZ", time_zone="UTC"
        ),
        home_team=pl.Series(["Kent State"]),
        away_team=pl.Series(["Georgia"]),
        home_points=pl.Series([99], dtype=pl.Int32),
        away_points=pl.Series([0], dtype=pl.Int32),
        game_type=pl.Series(["regular"]),
    )
    poisoned = pl.concat([games, planted]).sort("game_id")

    buckets = windows.season_buckets(poisoned, 2023)
    week15 = next(b for b in buckets if b.season_type == "regular" and b.week == 15)
    for bucket in buckets:
        if bucket.order > week15.order:
            continue
        train = windows.games_before(poisoned, bucket, buckets)
        assert 999_999_999 not in set(train["game_id"].to_list()), bucket.label

    clean = windows.games_through(poisoned, season=2023, week=10, season_type="regular")
    assert 999_999_999 not in set(clean["game_id"].to_list())


@needs_archive
def test_the_planted_game_does_change_the_answer_once_it_is_in_the_window() -> None:
    """The mirror of the test above: if the guard were absent the effect would be
    obvious, so the guard is doing real work rather than testing nothing."""
    from cfbpoll.model import l2_results

    games = load_games([2023], universe="model")
    honest = l2_results.fit(games, CONFIG, through=(2023, "regular", 15))
    planted = games.head(1).with_columns(
        game_id=pl.Series([999_999_999], dtype=pl.Int64),
        week=pl.Series([9], dtype=pl.Int32),
        season_type=pl.Series(["regular"]),
        start_date=pl.Series(["2023-10-28T00:00:00.000Z"]).str.to_datetime(
            "%Y-%m-%dT%H:%M:%S%.3fZ", time_zone="UTC"
        ),
        home_team=pl.Series(["Kent State"]),
        away_team=pl.Series(["Georgia"]),
        home_points=pl.Series([99], dtype=pl.Int32),
        away_points=pl.Series([0], dtype=pl.Int32),
        game_type=pl.Series(["regular"]),
    )
    poisoned = l2_results.fit(
        pl.concat([games, planted]).sort("game_id"), CONFIG, through=(2023, "regular", 15)
    )
    assert poisoned.ratings["Kent State"] > honest.ratings["Kent State"] + 3.0


# ------------------------------------------------------------------- end to end


@needs_archive
def test_backtest_runs_and_l2_beats_the_naive_baselines() -> None:
    result = walkforward.run_backtest(
        [2022, 2023], ["l2", "colley", "srs", "elo", "walker", "winpct", "home_team"]
    )
    headline = {
        name: block["segments_from_headline_week"]["fbs_vs_fbs"]
        for name, block in result["systems"].items()
    }
    assert 0.66 <= headline["l2"]["su_accuracy"] <= 0.76
    assert headline["l2"]["mae"] < headline["winpct"]["mae"]
    assert headline["l2"]["mae"] < headline["colley"]["mae"]
    assert headline["l2"]["su_accuracy"] > headline["home_team"]["su_accuracy"] + 0.08
    assert result["protocol"]["prior_seasons_used"] is False
    assert result["protocol"]["holdout_touched"] is False


@needs_archive
def test_segments_are_reported_separately() -> None:
    result = walkforward.run_backtest([2023], ["l2"])
    segments = result["systems"]["l2"]["segments"]
    assert {"fbs_vs_fbs", "fbs_vs_fcs", "bowl", "cfp"} <= set(segments)
    # FBS-vs-FCS games are easy and would inflate the headline if pooled in.
    assert segments["fbs_vs_fcs"]["su_accuracy"] > segments["fbs_vs_fbs"]["su_accuracy"]


@needs_archive
def test_backtest_is_deterministic() -> None:
    import json

    a = walkforward.run_backtest([2022], ["l2", "colley"])
    b = walkforward.run_backtest([2022], ["l2", "colley"])
    # Compared as serialised JSON because the tree legitimately contains NaN
    # (a week with no shared teams has no churn), and NaN != NaN.
    assert json.dumps(a, sort_keys=True, default=float) == json.dumps(
        b, sort_keys=True, default=float
    )


@needs_archive
def test_segment_labels_cover_every_game() -> None:
    games = walkforward.segment_games(load_games([2023], universe="model"))
    counts = games.group_by("segment").len().to_dict(as_series=False)
    got = dict(zip(counts["segment"], counts["len"], strict=True))
    assert got["fbs_vs_fbs"] + got["cfp"] + got["bowl"] == 792
    assert sum(got.values()) == games.height
