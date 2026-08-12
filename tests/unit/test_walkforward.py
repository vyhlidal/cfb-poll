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


# ------------------------------- the two retrodictive orderings as scored systems


@needs_archive
def test_schedule_odds_is_a_permanently_scored_system() -> None:
    """ADR 0005: the headline ordering and the ordering it replaced are BOTH in
    the scored set, forever.

    The decision between them was made on measured violations and measured forward
    ordering accuracy (docs/analysis/headline-ordering-study.md). Dropping the
    loser from the table afterwards would make that decision unfalsifiable from
    that week on, which is the opposite of what a backtest is for. They were
    within 0.4 percentage points of each other on violations across 2021-2024 and
    this is where anyone finds out if that stops being true."""
    from cfbpoll.backtest import baselines

    assert "schedule_odds" in baselines.SYSTEMS
    assert "schedule_odds" in baselines.RATERS
    assert baselines.RETRODICTIVE_SYSTEMS == {"schedule_odds", "resume"}
    for alias in ("odds", "sor", "schedule-odds", "headline"):
        assert baselines.resolve(alias) == "schedule_odds"

    result = walkforward.run_backtest([2023], ["schedule_odds", "resume", "l3"])
    for name in ("schedule_odds", "resume"):
        block = result["systems"][name]
        assert block["retrodictive_violation_rate"] is not None
        assert block["rank_churn"]["mean_all"] is not None
        assert block["retrodictive_violations"][0]["games"] > 700


@needs_archive
def test_schedule_odds_predicts_through_its_power_source_like_the_resume() -> None:
    """Both orderings are retrodictive by construction, so both borrow the Power
    rating they were built on for the margin columns and are scored on violations
    for the column that is about them (backtest/baselines/__init__.py)."""
    result = walkforward.run_backtest([2023], ["schedule_odds", "resume", "l3", "l2"])
    sources = result["protocol"]["prediction_sources"]
    expected = "l3" if result["protocol"]["power_source"].upper() == "L3" else "l2"
    assert sources["schedule_odds"] == expected == sources["resume"]

    odds = result["systems"]["schedule_odds"]["segments"]["fbs_vs_fbs"]
    proxy = result["systems"][expected]["segments"]["fbs_vs_fbs"]
    assert odds["su_accuracy"] == proxy["su_accuracy"]
    assert odds["mae"] == pytest.approx(proxy["mae"], abs=1e-12)

    # ...and the number that IS about the ordering is a different number
    assert (
        result["systems"]["schedule_odds"]["retrodictive_violation_rate"]
        != result["systems"][expected]["retrodictive_violation_rate"]
    )


@needs_archive
def test_schedule_odds_beats_its_own_power_rating_on_violations() -> None:
    """A desert ordering must respect results better than the margin-based power
    rating it is built on, or it is not doing its job (report 02 §5.4).

    AND THE PART THAT IS NOT FLATTERING, pinned here so it cannot quietly go away.
    Neither desert ordering clears `[gate].violations_must_beat`, on either
    protocol, and that is reported in demo/backtest-2021-2023.md rather than
    buried. Both lose to win percentage, which is close to the floor on a metric
    that ignores schedule entirely, and to Colley.

    ADAPTED 2026-08-12 (fresh-eyes review S1). Two things changed underneath it:

      * the PUBLISHED violations protocol is now walk-forward at the final
        bucket - the blend weights are the ones that were live, scored over every
        FBS-vs-FBS game including the postseason - which is how the poll is
        actually produced, and which is what the headline-ordering study used.
        The full-season refit is kept as `*_full_season_refit`;
      * `violations_must_beat` compares against every scored system rather than
        the two the old config named, so the résumé's `True` became a `False`.
        The résumé never beat win percentage; the rival list simply did not
        mention it.

    The two orderings swap places between the protocols by less than two
    thousandths, which is another way of saying the gap between them is not a
    fact about the orderings. Study §10.4 declines to claim significance for it
    and so does this test."""
    result = walkforward.run_backtest(
        [2021, 2022, 2023],
        ["schedule_odds", "resume", "l2", "l3", "colley", "srs", "winpct"],
    )
    systems = result["systems"]
    rate = {n: systems[n]["retrodictive_violation_rate"] for n in systems}
    refit = {n: systems[n]["retrodictive_violation_rate_full_season_refit"] for n in systems}
    assert rate["schedule_odds"] < rate["l2"]
    assert rate["schedule_odds"] < rate["l3"]
    assert rate["schedule_odds"] <= rate["srs"]
    # the two orderings are within a rounding difference of each other, and which
    # one is ahead depends on the protocol rather than on the ordering
    assert abs(rate["schedule_odds"] - rate["resume"]) < 0.01
    assert abs(refit["schedule_odds"] - refit["resume"]) < 0.01
    assert rate["schedule_odds"] > rate["colley"]
    # both lose the comparative criterion once the rival list is honest
    for name in ("schedule_odds", "resume"):
        gate = systems[name]["gate"]
        assert gate["violations_vs_baselines"] is False
        assert "winpct" in gate["violations_vs_baselines_detail"]["lost_to"]


@needs_archive
def test_resume_is_scored_and_predicts_through_its_power_source() -> None:
    """report 02 §3.5: the résumé is a DESERT measure, not a forecast. It is
    scored on violations and predicts margins through the Power rating it was
    built on, so its predictive columns are that source's by construction."""
    result = walkforward.run_backtest([2023], ["resume", "l3", "l2"])
    # ADAPTED when L3 landed: the résumé's Power source is [resume].power_source,
    # so its prediction proxy moved from l2 to l3 with it. The invariant under
    # test is unchanged - the résumé predicts through the layer it was built on -
    # and it is now checked against whichever layer that is.
    source = result["protocol"]["prediction_sources"]["resume"]
    assert source == ("l3" if result["protocol"]["power_source"].upper() == "L3" else "l2")
    assert result["protocol"]["prediction_sources"]["l2"] == "l2"

    resume = result["systems"]["resume"]["segments"]["fbs_vs_fbs"]
    proxy = result["systems"][source]["segments"]["fbs_vs_fbs"]
    assert resume["su_accuracy"] == proxy["su_accuracy"]
    assert resume["mae"] == pytest.approx(proxy["mae"], abs=1e-12)

    # ...and the number that IS about L4 is a different number
    assert (
        result["systems"]["resume"]["retrodictive_violation_rate"]
        != result["systems"][source]["retrodictive_violation_rate"]
    )


@needs_archive
def test_resume_beats_its_own_power_rating_on_violations() -> None:
    """The gate L2 rightly missed (report 02 §5.4). A margin-based power rating is
    not trying to respect results; the résumé is exactly the layer that does.

    ADAPTED 2026-08-12 (fresh-eyes review S1). The claim this test is about - a
    desert ordering respects results better than the margin-based power rating it
    is built on - is unchanged and still holds on both protocols. What changed is
    the two lines about Colley: on the PUBLISHED walk-forward protocol the résumé
    is at ~0.1997 and Colley at ~0.1962, so the résumé no longer clears the
    comparative criterion. It never beat win percentage either; the old rival list
    just did not name it."""
    result = walkforward.run_backtest(
        [2021, 2022, 2023], ["resume", "l2", "colley", "srs", "winpct"]
    )
    systems = result["systems"]
    rate = {n: systems[n]["retrodictive_violation_rate"] for n in systems}
    refit = {n: systems[n]["retrodictive_violation_rate_full_season_refit"] for n in systems}
    assert rate["resume"] < rate["l2"]
    assert rate["resume"] <= rate["srs"]
    assert refit["resume"] < refit["l2"]
    # the criterion returns a verdict rather than a shrug, and the verdict is that
    # a schedule-blind rating wins a schedule-blind metric
    assert systems["resume"]["gate"]["violations_vs_baselines"] is False
    assert systems["l2"]["gate"]["violations_vs_baselines"] is False
    assert rate["winpct"] < rate["resume"] < rate["l2"]


@needs_archive
def test_resume_violations_beat_power_violations_season_by_season() -> None:
    """Not just in aggregate: every season separately, on a direct full-season fit
    rather than through the harness, so the claim does not depend on pooling."""
    from cfbpoll.model import l4_resume

    for season in (2021, 2022, 2023):
        games = load_games([season], universe=str(CONFIG["model"]["fit_universe"]))
        fbs = walkforward.segment_games(games).filter(pl.col("segment") == "fbs_vs_fbs")
        winners, losers = [], []
        for home, away, hp, ap in zip(
            fbs["home_team"].to_list(),
            fbs["away_team"].to_list(),
            fbs["home_points"].to_list(),
            fbs["away_points"].to_list(),
            strict=True,
        ):
            winners.append(home if hp > ap else away)
            losers.append(away if hp > ap else home)

        fitted = l4_resume.fit(games, CONFIG)
        resume = metrics.violations(fitted.resume, winners, losers)
        power = metrics.violations(fitted.power.ratings, winners, losers)
        assert resume["violations"] <= power["violations"], season


def test_the_violations_gate_is_at_or_below_every_scored_system() -> None:
    """ADAPTED 2026-08-12, and the asserted truth genuinely changed.

    This used to be `..._every_named_baseline`, against a config that named
    `["colley", "srs"]`. The fresh-eyes review (S1) pointed out that the list
    omitted win percentage, which beats every other system in the table - so the
    gate's one comparative criterion was drawn around the rivals it happened to
    clear. `[gate].violations_must_beat` is now the sentinel
    `"all_scored_systems"` and the comparison runs against every system in the
    run. The shape of the assertion is unchanged: at or below all of them, or the
    criterion is False."""
    gate = dict(CONFIG["gate"])
    assert gate["violations_must_beat"] == metrics.ALL_SCORED_SYSTEMS
    rates = {"colley": 0.20, "srs": 0.22, "winpct": 0.20, "home_team": None}
    verdict = metrics.check_gate({}, gate, violation_rate=0.20, baseline_violation_rates=rates)
    assert verdict["violations_vs_baselines"] is True
    # the home-team floor has no ratings, so it is never a rival
    assert "home_team" not in verdict["violations_vs_baselines_detail"]["compared_against"]

    worse = metrics.check_gate({}, gate, violation_rate=0.21, baseline_violation_rates=rates)
    assert worse["violations_vs_baselines"] is False
    detail = worse["violations_vs_baselines_detail"]
    assert sorted(detail["lost_to"]) == ["colley", "winpct"]
    assert sorted(detail["beaten"]) == ["srs"]

    # a system is never its own rival
    itself = metrics.check_gate(
        {}, gate, violation_rate=0.20, baseline_violation_rates=rates, system="colley"
    )
    assert "colley" not in itself["violations_vs_baselines_detail"]["compared_against"]

    # AND THE ONE THIS REPLACED. An explicit list is still honoured, so a fork can
    # state a narrower intent in the gate's own definition rather than by leaving
    # a name off a list nobody reads - and a named rival that was not scored still
    # makes the criterion unknowable rather than trivially passed.
    named = {**gate, "violations_must_beat": ["colley", "srs"]}
    unknown = metrics.check_gate(
        {}, named, violation_rate=0.20, baseline_violation_rates={"colley": 0.20}
    )
    assert unknown["violations_vs_baselines"] is None
    assert "violations_vs_baselines" in unknown["undecided"]


def test_the_gate_publishes_its_thresholds_and_its_observations() -> None:
    """A bare per-criterion boolean is not auditable: a reader cannot tell what it
    was compared against. Since the fresh-eyes review the verdict carries the
    thresholds it used and the numbers it saw, and demo/backtest-2021-2023.md
    renders both rather than paraphrasing them."""
    verdict = metrics.check_gate(
        {"su_accuracy": 0.72, "mae": 12.4, "rmse": 15.4, "max_calibration_deviation_pp": 2.0},
        CONFIG["gate"],
    )
    assert verdict["thresholds"]["su_accuracy_min"] == CONFIG["gate"]["su_accuracy_min"]
    assert verdict["observed"]["mae"] == 12.4
    # evidence blocks are attached after the verdict is computed, so a dict can
    # never be mistaken for a criterion
    assert verdict["passed"] is True
    assert "thresholds" not in verdict["undecided"]
    assert "observed" not in verdict["undecided"]


@needs_archive
def test_both_violations_protocols_are_computed_and_named() -> None:
    """Fresh-eyes review S1: the harness and the headline-ordering study reported
    different violation rates, and the difference was PROTOCOL rather than
    arithmetic. Both are now computed for every system and both are in
    backtest_metrics.json, with the published one named as such.

    PUBLISHED  walk-forward at the final bucket - the hyperparameters that were
               live when the season ended - over every FBS-vs-FBS game including
               the postseason. This is how the poll is produced week by week.
    DIAGNOSTIC full-season refit, blend weights in-sample, fbs_vs_fbs segment
               only. What this harness computed before.

    The two differ most for the layers that HAVE a walked hyperparameter, which
    is the whole point: L3's blend weights. For Colley, which has none, the two
    protocols differ only by the postseason games in the denominator."""
    result = walkforward.run_backtest([2023], ["l3", "colley", "schedule_odds"])
    for name in ("l3", "colley", "schedule_odds"):
        block = result["systems"][name]
        assert block["retrodictive_violation_rate"] is not None
        assert block["retrodictive_violation_rate_full_season_refit"] is not None
        assert "walk-forward at the final bucket" in block["retrodictive_protocol"]
        row = block["retrodictive_violations"][0]
        assert row["games"] > row["full_season_refit"]["games"]  # the postseason

    # L3 has a walked hyperparameter, so the protocols genuinely disagree...
    l3 = result["systems"]["l3"]
    assert l3["retrodictive_violation_rate"] != l3["retrodictive_violation_rate_full_season_refit"]
    # ...and the in-sample blend is the FLATTERING one, which is exactly the
    # effect report 02 §3.3 legislates against
    assert l3["retrodictive_violation_rate_full_season_refit"] < l3["retrodictive_violation_rate"]


@needs_archive
def test_the_gate_is_evaluated_on_the_window_the_poll_is_published_in() -> None:
    """A publication gate scored on weeks that are never published is measuring a
    poll that does not exist. It used to run over `[backtest].first_eval_week`
    (week 2 on), which report 02 §4 explicitly declines to publish, and it
    therefore disagreed with the numbers the demo quoted. It now runs over
    `[publication].headline_start_week` and the wider view is kept as
    `gate_all_weeks`. Neither passes; this is not a change that rescued
    anything."""
    result = walkforward.run_backtest([2021, 2022, 2023], ["schedule_odds", "l3", "colley"])
    block = result["systems"]["schedule_odds"]
    gate, wide = block["gate"], block["gate_all_weeks"]
    assert "headline_start_week" in gate["window"]
    assert "DIAGNOSTIC" in wide["window"]
    headline = block["segments_from_headline_week"]["fbs_vs_fbs"]
    assert gate["observed"]["mae"] == pytest.approx(headline["mae"])
    assert gate["observed"]["su_accuracy"] == pytest.approx(headline["su_accuracy"])
    assert gate["passed"] is False and wide["passed"] is False
    # the published window is the kinder one, and it still fails every criterion
    assert gate["observed"]["mae"] < wide["observed"]["mae"]


@needs_archive
def test_the_harness_fits_with_the_config_it_was_handed() -> None:
    """Every rater used to fall back to `load_config()` when it was not given one,
    so a backtest under a non-default config would have scored our own layers
    under the DEFAULT constants while claiming to have varied them - which would
    have made the fit-universe and recency sensitivity studies measurements of
    nothing. Constraint 5: the config IS the methodology."""
    import copy

    changed = copy.deepcopy(CONFIG)
    changed["margin"]["beta_w"] = 0.0  # a constant only OUR layers read
    base = walkforward.run_backtest([2023], ["l2", "colley"], config=CONFIG)
    varied = walkforward.run_backtest([2023], ["l2", "colley"], config=changed)
    assert (
        base["systems"]["l2"]["retrodictive_violation_rate"]
        != varied["systems"]["l2"]["retrodictive_violation_rate"]
    )
    # ...and a baseline that reads none of it is untouched, which is what makes
    # the comparison above a test of plumbing rather than of noise
    assert (
        base["systems"]["colley"]["retrodictive_violation_rate"]
        == varied["systems"]["colley"]["retrodictive_violation_rate"]
    )


# ------------------------------------------- the leakage guarantee, at play level


def _planted_future_game() -> pl.DataFrame:
    """2023 Kent State 99, Georgia 0, in week 15. Absurd on purpose."""
    games = load_games([2023], universe="model")
    return games.head(1).with_columns(
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


def _planted_future_plays(n: int = 60) -> pl.DataFrame:
    """Sixty absurd plays belonging to that game, in the play frame's schema."""
    from cfbpoll.ingest.plays import load_plays

    template = load_plays([2023]).head(n)
    return template.with_columns(
        game_id=pl.Series([999_999_999] * n, dtype=pl.Int64),
        play_index=pl.Series(list(range(1, n + 1)), dtype=pl.Int32),
        offense=pl.Series(["Kent State"] * n),
        defense=pl.Series(["Georgia"] * n),
        play_type=pl.Series(["Rush"] * n),
        play_class=pl.Series(["rush"] * n),
        down=pl.Series([1] * n, dtype=pl.Int32),
        distance=pl.Series([10] * n, dtype=pl.Int32),
        yards_to_goal=pl.Series([5] * n, dtype=pl.Int32),
        period=pl.Series([1] * n, dtype=pl.Int32),
        is_snap=pl.Series([True] * n),
        offense_score_after=pl.Series(list(range(0, 7 * n, 7)), dtype=pl.Int32),
        defense_score_after=pl.Series([0] * n, dtype=pl.Int32),
    )


@needs_archive
def test_walk_forward_never_sees_a_planted_future_PLAY() -> None:
    """The play-level twin of the planted-future-game test, and the reason L1 is
    allowed to exist at all.

    L1 reads 170,000 rows per season instead of 1,200, so a slicing mistake there
    is both more likely and harder to spot. The guard is the same one: plays are
    joined to an ALREADY-TRUNCATED game frame with an inner join, so a play whose
    game is not in the window cannot arrive. Nothing about L1 selects its own rows.
    """
    from cfbpoll.ingest.plays import load_plays, plays_for

    poisoned_games = pl.concat([load_games([2023], universe="model"), _planted_future_game()]).sort(
        "game_id"
    )
    poisoned_plays = pl.concat([load_plays([2023]), _planted_future_plays()]).sort(
        ["game_id", "play_index"]
    )

    buckets = windows.season_buckets(poisoned_games, 2023)
    week15 = next(b for b in buckets if b.season_type == "regular" and b.week == 15)
    for bucket in buckets:
        if bucket.order > week15.order:
            continue
        train = windows.games_before(poisoned_games, bucket, buckets)
        train_plays = plays_for(poisoned_plays, train)
        assert 999_999_999 not in set(train_plays["game_id"].to_list()), bucket.label
        assert train_plays.filter(pl.col("game_id") == 999_999_999).is_empty(), bucket.label

    clean = windows.games_through(poisoned_games, season=2023, week=10, season_type="regular")
    assert plays_for(poisoned_plays, clean).filter(pl.col("game_id") == 999_999_999).is_empty()


@needs_archive
def test_the_planted_plays_do_change_L1_once_they_are_in_the_window() -> None:
    """The mirror of the guard, and an accidental demonstration of garbage time.

    Sixty first-and-goal touchdowns move Kent State's efficiency rating - so the
    guard above is doing real work rather than testing nothing. But they move it
    only a little, and the reason is worth recording: a 420-0 scoreboard is in
    garbage time from the second play on, so 52 of the 60 planted plays are
    zero-weighted before the ridge ever sees them. Report 02 §3.1's filter is not
    decoration; it is the thing standing between this layer and every blowout in
    the archive.
    """
    from cfbpoll.ingest.plays import load_plays, plays_for
    from cfbpoll.model import l1_efficiency

    games = load_games([2023], universe="model")
    plays = load_plays([2023])
    window = windows.games_through(games, season=2023, week=10, season_type="regular")

    honest = l1_efficiency.fit(plays_for(plays, window), window, CONFIG)
    poisoned_games = pl.concat([games, _planted_future_game().with_columns(
        week=pl.Series([9], dtype=pl.Int32),
        start_date=pl.Series(["2023-10-28T00:00:00.000Z"]).str.to_datetime(
            "%Y-%m-%dT%H:%M:%S%.3fZ", time_zone="UTC"
        ),
    )]).sort("game_id")
    poisoned_window = windows.games_through(
        poisoned_games, season=2023, week=10, season_type="regular"
    )
    poisoned_plays = pl.concat([plays, _planted_future_plays()]).sort(["game_id", "play_index"])
    poisoned = l1_efficiency.fit(
        plays_for(poisoned_plays, poisoned_window), poisoned_window, CONFIG
    )
    assert poisoned.net("Kent State") > honest.net("Kent State") + 0.015
    zeroed = (
        poisoned.params["garbage_time_plays_dropped"]
        - honest.params["garbage_time_plays_dropped"]
    )
    assert zeroed >= 45, f"garbage time zeroed only {zeroed} of 60 planted blowout plays"


# ------------------------------------------------- sigma, measured rather than assumed


def test_sigma_falls_back_and_floors_rather_than_trusting_a_thin_window() -> None:
    """The rule, stated once in `l3_power.estimate_sigma` and used everywhere.

    Fresh-eyes review S6: 15.3 is a sound estimate of the residual SD of margin
    around a GOOD PUBLIC MODEL's prediction and the wrong denominator for a
    system whose own walk-forward RMSE is 16.5. It survives as the thin-window
    fallback and as a floor, because a spuriously small sigma makes every tail
    too small and the headline key is a PRODUCT over 9 to 13 games."""
    from cfbpoll.model import l3_power

    floor = float(CONFIG["resume"]["sigma"])
    minimum = int(CONFIG["resume"]["sigma_min_out_of_sample_games"])

    thin = l3_power.estimate_sigma([30.0] * (minimum - 1), CONFIG)
    assert thin.value == floor and thin.source == "config_fallback_thin_window"

    small = l3_power.estimate_sigma([1.0] * (minimum + 10), CONFIG)
    assert small.value == floor and small.source == "config_floor"
    assert small.estimate is not None and small.estimate < floor

    real = l3_power.estimate_sigma([20.0] * (minimum + 10), CONFIG)
    assert real.value == pytest.approx(20.0) and real.source == "walk_forward_residuals"

    import copy

    pinned = copy.deepcopy(CONFIG)
    pinned["resume"]["sigma_estimator"] = "config"
    assert l3_power.estimate_sigma([20.0] * 500, pinned).value == floor


@needs_archive
def test_the_harness_gives_every_system_its_own_walk_forward_sigma() -> None:
    """Per system and per bucket. Scoring one system's probabilities with
    another's error dispersion measures neither, and a Brier or a calibration
    decile computed that way is not comparable across the table. The estimate is
    also strictly walk-forward: at bucket N it has seen only games predicted
    before N."""
    result = walkforward.run_backtest([2023], ["l3", "colley", "winpct"])
    weekly = result["weekly"]
    by_system = {
        name: [r for r in weekly if r["system"] == name] for name in ("l3", "colley", "winpct")
    }
    for rows in by_system.values():
        assert rows[0]["sigma_source"] == "config_fallback_thin_window"
        assert rows[-1]["sigma_source"] == "walk_forward_residuals"
        # it settles rather than wandering: the last three buckets agree closely
        tail = [r["sigma"] for r in rows[-3:]]
        assert max(tail) - min(tail) < 1.0

    # and the systems genuinely differ, which is the point of doing it per system
    finals = {name: rows[-1]["sigma"] for name, rows in by_system.items()}
    assert len(set(round(v, 6) for v in finals.values())) == 3
    assert finals["winpct"] > finals["l3"]  # a worse predictor has a wider sigma

    assert "PER SYSTEM, PER BUCKET" in result["protocol"]["sigma"]
    assert result["protocol"]["sigma_fallback"] == CONFIG["resume"]["sigma"]


@needs_archive
def test_estimating_sigma_does_not_close_the_calibration_gap() -> None:
    """MEASURED, AND IT GOES THE OTHER WAY. The review (S6) expected a fitted
    sigma to help the criterion the gate misses by the widest relative margin. It
    does not: the deviation grows, because the miss is an ASYMMETRY in the low
    deciles rather than an error of scale, and a scale parameter cannot fix a
    shape problem. Pinned here so nobody later assumes the fix worked, and
    reported in demo/backtest-2021-2023.md with both decile tables."""
    import copy

    pinned = copy.deepcopy(CONFIG)
    pinned["resume"]["sigma_estimator"] = "config"
    systems = ["schedule_odds", "l3"]
    after = walkforward.run_backtest([2021, 2022, 2023], systems, config=CONFIG)
    before = walkforward.run_backtest([2021, 2022, 2023], systems, config=pinned)

    a = after["systems"]["schedule_odds"]["segments_from_headline_week"]["fbs_vs_fbs"]
    b = before["systems"]["schedule_odds"]["segments_from_headline_week"]["fbs_vs_fbs"]
    threshold = CONFIG["gate"]["calibration_max_decile_deviation_pp"]

    assert b["sigma_mean"] == pytest.approx(CONFIG["resume"]["sigma"])
    assert a["sigma_mean"] > b["sigma_mean"]  # this system's own error is wider
    assert a["max_calibration_deviation_pp"] > b["max_calibration_deviation_pp"] > threshold

    # sigma enters the probability and not the predicted margin, so nothing about
    # the point forecast may move
    assert a["mae"] == pytest.approx(b["mae"])
    assert a["rmse"] == pytest.approx(b["rmse"])
    assert a["su_accuracy"] == pytest.approx(b["su_accuracy"])
