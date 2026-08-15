"""The fair-comparison protocol, and the future-schedule reader.

The backtest's headline is "did we beat the sportswriters", and the only way that
sentence means anything is if the comparison is not quietly rigged in either
direction. The AP poll ranks 25 teams and says nothing about the other 109, so
every scoring decision has to be checked against that asymmetry rather than
assumed past it. These tests pin the four that matter:

  * top-25 overlap is treatment-free - no convention can tilt it;
  * rank MAE censors EVERY system at 26, so a 134-team rating is not punished for
    having opinions the AP was never asked for;
  * the AP gets `None` on full-information metrics rather than a number computed
    under a convention it never agreed to;
  * leave-one-out really leaves one out.

And separately: `forward.schedule` must project six columns off a body that ships
pregame Elo, an excitement index and a win probability. The cheapest way to prove
a third party's model never reached us is to never load it.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE
from cfbpoll.projection import fit, forward, recipe

pytestmark = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised",
)

SETTLED = {f"Team {i:03d}": i for i in range(1, 41)}


# ------------------------------------------------------------- the fair comparison


def test_top25_overlap_is_treatment_free() -> None:
    """No convention, no censoring, no charity. Both systems name 25 teams and we
    count how many finished there - which is why this is the headline."""
    perfect = dict(SETTLED)
    assert fit.rank_metrics(perfect, SETTLED, True)["top25_overlap"] == 25

    # A 25-team poll that named 20 of the right teams scores 20, whether or not
    # it has opinions about anybody else.
    ap = {team: rank for team, rank in SETTLED.items() if rank <= 20}
    ap.update({f"Team {i:03d}": i - 15 for i in range(31, 36)})
    assert fit.rank_metrics(ap, SETTLED, False)["top25_overlap"] == 20


def test_every_system_is_censored_at_the_same_place() -> None:
    """The decision that keeps the AP comparison honest in BOTH directions.

    Uncensored, a full-rating system that buries a team at #80 pays 75 places
    while the AP's worst possible error is 21 - which would measure the shape of
    the output rather than the quality of the projection. Censored at 26, both are
    answering the AP's own question."""
    assert fit.CENSOR_AT == 26

    # We had the eventual #1 at #80. The AP simply did not rank them.
    ours = dict(SETTLED)
    ours["Team 001"] = 80
    theirs = {team: rank for team, rank in SETTLED.items() if rank <= 25 and team != "Team 001"}

    mine = fit.rank_metrics(ours, SETTLED, True)
    ap = fit.rank_metrics(theirs, SETTLED, False)

    # Same censored penalty for the same mistake: 25 places, both of us.
    assert mine["mae_rank_top25_censored"] == pytest.approx(25 / 25)
    assert ap["mae_rank_top25_censored"] == pytest.approx(25 / 25)
    # And the uncensored number, which is why the censoring exists.
    assert mine["mae_rank_top25_uncensored"] == pytest.approx(79 / 25)


def test_the_ap_is_not_padded_out_to_a_full_rating() -> None:
    """A 25-team poll gets `None` on metrics that need 134 opinions, rather than
    a number invented from a convention it never expressed."""
    ap = {team: rank for team, rank in SETTLED.items() if rank <= 25}
    metrics = fit.rank_metrics(ap, SETTLED, full_information=False)
    assert metrics["spearman_full"] is None
    assert metrics["mae_rank_top25_uncensored"] is None
    assert metrics["top25_overlap"] == 25
    assert metrics["mae_rank_top25_censored"] is not None

    full = fit.rank_metrics(dict(SETTLED), SETTLED, full_information=True)
    assert full["spearman_full"] == pytest.approx(1.0)
    assert full["mae_rank_top25_uncensored"] == 0.0


def test_a_perfect_ranking_scores_perfectly_and_a_reversed_one_does_not() -> None:
    """The metric's own sanity, so a sign error cannot hide inside a close result."""
    perfect = fit.rank_metrics(dict(SETTLED), SETTLED, True)
    reversed_ranks = {team: 41 - rank for team, rank in SETTLED.items()}
    worst = fit.rank_metrics(reversed_ranks, SETTLED, True)
    assert perfect["mae_rank_top25_censored"] == 0.0
    assert worst["mae_rank_top25_censored"] > perfect["mae_rank_top25_censored"]
    assert worst["spearman_full"] == pytest.approx(-1.0)
    assert worst["top25_overlap"] < perfect["top25_overlap"]


def test_leave_one_out_really_leaves_one_out() -> None:
    """Otherwise every number in the backtest is a training error wearing a
    different name."""
    rng = np.random.default_rng(3)
    data = []
    for source, target in ((2021, 2022), (2022, 2023), (2023, 2024)):
        teams = [f"Team {i:03d}" for i in range(30)]
        design = pl.DataFrame(
            {
                "team": teams,
                "season": pl.Series([target] * 30, dtype=pl.Int32),
                "prior_power_centered": rng.normal(0, 12, 30),
                "returning_usage_centered": rng.normal(0, 0.15, 30),
                "coach_change": (rng.random(30) < 0.25).astype(float),
                "portal_net_z": rng.normal(0, 1, 30),
            }
        )
        data.append(
            fit.TransitionData(
                source_season=source,
                target_season=target,
                design=design,
                teams=tuple(teams),
                response=rng.normal(15, 12, 30),
                prior_power=dict.fromkeys(teams, 0.0),
                settled=pl.DataFrame(),
                ap=pl.DataFrame(),
                coverage={},
            )
        )

    folds = fit.leave_one_out(data)
    assert set(folds) == {2022, 2023, 2024}
    for held, fitted in folds.items():
        targets = {target for _, target in fitted.transitions}
        assert held not in targets, held
        assert len(fitted.transitions) == 2


def test_su_accuracy_is_invariant_to_rescaling_a_rating() -> None:
    """Why SU is the honest number in the game-prediction half: it measures the
    ORDERING and nothing else, so a rating on the AP's 0-25 scale and one in
    points are comparable without anybody being handed a scale."""
    from cfbpoll.ingest.sportsdataverse import load_games

    games = load_games([2023])
    teams = sorted(
        set(games.filter(pl.col("season") == 2023)["home_team"].unique().to_list())
    )
    ratings = {team: float(i % 40) for i, team in enumerate(teams)}
    scaled = {team: 3.7 * value + 100.0 for team, value in ratings.items()}

    first = fit.early_season_metrics(games, 2023, ratings)
    second = fit.early_season_metrics(games, 2023, scaled)
    assert first["n_games"] == second["n_games"] > 0
    assert first["su_accuracy"] == pytest.approx(second["su_accuracy"])
    assert first["mae"] == pytest.approx(second["mae"], abs=1e-6)


def test_the_system_roster_is_the_one_the_artifacts_report() -> None:
    """A comparison whose roster can drift is a comparison nobody can quote."""
    assert fit.SYSTEMS == (
        "projection",
        "regress_only",
        "naive_carryover",
        "ap_preseason",
    )


# ---------------------------------------------------------------- one Power, ADR 0013


def test_the_projection_predicts_the_power_the_grading_page_scores_against() -> None:
    """THE DEFECT ADR 0013 REPAIRS, asserted where it cannot be argued about.

    `projection-1.0.0` fitted and predicted `l4_resume.power_source` over a whole
    season at once, and graded against `retro.season_power[final]`, the
    walk-forward surface the poll publishes. The two are related by
    `graded = -3.65 + 0.70 * response`, so every team looked seven points
    over-projected and the league attribution read that scale change as a
    coefficient error. This test is the reason that cannot come back: the
    recipe's response and the grading page's answer key have to be the same
    numbers, team by team, to floating point.
    """
    from cfbpoll.config import load_config
    from cfbpoll.ingest import windows
    from cfbpoll.ingest.plays import load_plays
    from cfbpoll.ingest.sportsdataverse import load_games
    from cfbpoll.model import retro
    from cfbpoll.projection import seasons

    config = load_config()
    games = load_games([2024])
    plays = load_plays([2024])
    season_games = games.filter(pl.col("season") == 2024)

    published = retro.season_power(season_games, 2024, config, plays=plays)
    final_order = windows.season_buckets(season_games, 2024)[-1].order
    ours = seasons.final_power(games, 2024, plays, config)

    assert ours.source == "L3"
    assert ours.ratings == published[final_order].ratings
    assert "walk-forward" in seasons.POWER_DEFINITION.lower()


# --------------------------------------------------------- the future-schedule reader


def test_the_future_schedule_reader_loads_six_columns_and_no_models() -> None:
    """CFBD's /games body ships `homePregameElo`, `excitementIndex` and a postgame
    win probability alongside the calendar. This is report 01 §5.6's trap in its
    purest form, and the answer is to never load them."""
    frame = forward.schedule(2026)
    if not frame.height:
        pytest.skip("private CFBD archive does not hold the 2026 schedule")

    assert tuple(frame.columns) == forward.SCHEDULE_COLUMNS
    from cfbpoll.validate import leakage

    assert leakage.banned_hits(frame.columns) == ()
    assert frame["game_id"].n_unique() == frame.height
    assert frame["home_team"].null_count() == 0
    assert frame["away_team"].null_count() == 0


def test_a_missing_schedule_is_an_empty_frame_not_a_crash(tmp_path) -> None:
    """A fork with no CFBD archive gets a projection without win totals - a
    smaller product, not a broken one."""
    frame = forward.schedule(2026, tmp_path)
    assert frame.height == 0
    assert tuple(frame.columns) == forward.SCHEDULE_COLUMNS


def test_the_projection_sigma_is_wider_than_the_in_season_one() -> None:
    """The honest part. In August the poll does not know the Power ratings, it has
    a projection of them, and both teams carry that error independently."""
    fitted = recipe.Recipe(
        intercept=15.0,
        coefficients=dict.fromkeys(recipe.TERMS, 1.0),
        se=dict.fromkeys(recipe.TERMS, 1.0),
        intercept_se=1.0,
        transitions=((2025, 2026),),
        n_teams=100,
        r_squared=0.5,
        residual_sd=9.0,
    )
    sigma = forward.projection_sigma(fitted, 15.3)
    assert sigma == pytest.approx(np.sqrt(15.3**2 + 2 * 81.0))
    assert sigma > 15.3
    # A recipe with no residual error at all would collapse to the in-season sd.
    exact = recipe.Recipe(**{**fitted.__dict__, "residual_sd": 0.0})
    assert forward.projection_sigma(exact, 15.3) == pytest.approx(15.3)


def test_expected_wins_sum_to_the_number_of_games_played() -> None:
    """Every game hands out exactly one win, so the league's projected wins must
    equal its game count. A drift here means a schedule row counted twice."""
    teams = ["Alpha", "Bravo", "Charlie", "Delta"]
    fitted = recipe.Recipe(
        intercept=15.0,
        coefficients={
            "prior_power": 0.7,
            "returning_production": 7.0,
            "coaching_change": -2.0,
            "net_portal": -0.4,
        },
        se=dict.fromkeys(recipe.TERMS, 1.0),
        intercept_se=1.0,
        transitions=((2025, 2026),),
        n_teams=4,
        r_squared=0.5,
        residual_sd=9.0,
    )
    projection = pl.DataFrame(
        {"team": teams, "projected_power": [30.0, 22.0, 14.0, 5.0]}
    )
    future = pl.DataFrame(
        {
            "game_id": [1, 2, 3, 4, 5, 6],
            "week": pl.Series([1, 2, 3, 4, 5, 6], dtype=pl.Int32),
            "neutral_site": [False, False, True, False, False, True],
            "home_team": ["Alpha", "Alpha", "Bravo", "Charlie", "Delta", "Alpha"],
            "away_team": ["Bravo", "Charlie", "Charlie", "Delta", "Bravo", "Delta"],
            "home_class": ["fbs"] * 6,
            "away_class": ["fbs"] * 6,
        }
    )
    wins = forward.expected_wins(projection, future, fitted, {}, 0.0, 15.3, 2.5)

    assert wins.table["projected_wins"].sum() == pytest.approx(future.height)
    assert wins.table["scheduled_games"].sum() == 2 * future.height
    assert wins.table["opponent_source"].to_list() == ["projection"] * len(teams)
    # The better team is projected to win more of the same number of games.
    table = dict(
        zip(
            wins.table["team"].to_list(), wins.table["projected_wins"].to_list(), strict=True
        )
    )
    assert table["Alpha"] > table["Delta"]
    assert "sqrt" in wins.sigma_note


def test_an_opponent_the_recipe_cannot_see_is_flagged_not_blended_in() -> None:
    """An FCS opponent has no returning-production row anywhere. It gets the
    mean-reversion-only projection, and the teams that played it say so."""
    fitted = recipe.Recipe(
        intercept=15.0,
        coefficients={
            "prior_power": 0.7,
            "returning_production": 7.0,
            "coaching_change": -2.0,
            "net_portal": -0.4,
        },
        se=dict.fromkeys(recipe.TERMS, 1.0),
        intercept_se=1.0,
        transitions=((2025, 2026),),
        n_teams=2,
        r_squared=0.5,
        residual_sd=9.0,
    )
    projection = pl.DataFrame({"team": ["Alpha"], "projected_power": [30.0]})
    future = pl.DataFrame(
        {
            "game_id": [1],
            "week": pl.Series([1], dtype=pl.Int32),
            "neutral_site": [False],
            "home_team": ["Alpha"],
            "away_team": ["Some FCS School"],
            "home_class": ["fbs"],
            "away_class": ["fcs"],
        }
    )
    wins = forward.expected_wins(
        projection, future, fitted, {"Some FCS School": -20.0}, 0.0, 15.3, 2.5
    )
    sources = dict(
        zip(
            wins.table["team"].to_list(),
            wins.table["opponent_source"].to_list(),
            strict=True,
        )
    )
    assert sources["Alpha"] == "mixed"
    assert sources["Some FCS School"] == "projection"
