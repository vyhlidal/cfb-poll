"""The backtest baselines (report 02 §5.3).

Each one is checked against the property its own literature states, on a toy
league small enough to reason about by hand, plus one sanity pass over the real
2023 archive.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from cfbpoll.backtest import baselines
from cfbpoll.backtest.baselines import colley, elo, random_walker, srs, winpct
from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.plays import load_plays, plays_for
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games

CONFIG = load_config()

needs_archive = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(), reason="local archive not materialised"
)


def toy(
    rows: list[tuple[str, str, int, int]], classes: dict[str, str] | None = None
) -> pl.DataFrame:
    classes = classes or {}
    return pl.DataFrame(
        {
            "game_id": pl.Series(list(range(1, len(rows) + 1)), dtype=pl.Int64),
            "start_date": pl.Series(
                [f"2023-09-{i + 1:02d}T00:00:00.000Z" for i in range(len(rows))]
            ).str.to_datetime("%Y-%m-%dT%H:%M:%S%.3fZ", time_zone="UTC"),
            "neutral_site": [False] * len(rows),
            "game_type": ["regular"] * len(rows),
            "home_team": [r[0] for r in rows],
            "away_team": [r[1] for r in rows],
            "home_points": pl.Series([r[2] for r in rows], dtype=pl.Int32),
            "away_points": pl.Series([r[3] for r in rows], dtype=pl.Int32),
            "home_class": [classes.get(r[0], "fbs") for r in rows],
            "away_class": [classes.get(r[1], "fbs") for r in rows],
        }
    )


ROUND_ROBIN = [
    ("A", "B", 28, 7),
    ("B", "C", 24, 10),
    ("C", "A", 3, 30),
    ("A", "D", 45, 0),
    ("B", "D", 20, 17),
    ("C", "D", 14, 10),
]


# ---------------------------------------------------------------------- registry


def test_registry_resolves_the_names_the_cli_accepts() -> None:
    assert baselines.resolve("walker") == "random_walker"
    assert baselines.resolve("l2") == "l2" == baselines.resolve("ours")
    assert baselines.resolve("HOME") == "home_team"
    with pytest.raises(KeyError):
        baselines.resolve("sagarin")


def test_every_rater_honours_the_challenger_protocol() -> None:
    """Every rater takes (games, plays, through_week, state) and returns floats.

    `l1` and `l3` need plays and return an empty mapping without them, which the
    harness reads as "league average for everyone" - the correct answer for a
    play-level system handed no plays, and the reason they are listed in
    PLAY_LEVEL_SYSTEMS so the harness knows to load the archive for them.
    """
    games = toy(ROUND_ROBIN)
    for name, rater in sorted(baselines.RATERS.items()):
        out = rater(games, None, 6, state=None)
        assert isinstance(out, dict), name
        assert all(isinstance(v, float) for v in out.values()), name
        if name in baselines.PLAY_LEVEL_SYSTEMS:
            continue
        assert set(out) >= {"A", "B", "C", "D"}, name


# ------------------------------------------------------------------------ winpct


def test_win_percentage_is_wins_over_games() -> None:
    r = winpct.rate(toy(ROUND_ROBIN))
    assert r["A"] == pytest.approx(3 / 3)
    assert r["D"] == pytest.approx(0 / 3)
    assert r["B"] == pytest.approx(2 / 3)


def test_home_team_always_wins_predicts_every_game() -> None:
    picks = winpct.home_team_always_wins(toy(ROUND_ROBIN))
    assert len(picks) == 6
    assert all(picks.values())


# ------------------------------------------------------------------------ Colley


def test_colley_conserves_the_average_rating_exactly() -> None:
    """report 02 §2.1: sum(r)/N = 1/2 exactly, with no renormalisation."""
    for rows in (ROUND_ROBIN, ROUND_ROBIN[:3], ROUND_ROBIN + [("D", "A", 1, 0)]):
        r = colley.rate(toy(rows))
        assert sum(r.values()) / len(r) == pytest.approx(0.5, abs=1e-12)


def test_colley_ignores_margin_entirely() -> None:
    """Wins and losses only - the property the BCS demanded and the reason the
    method is not a strong predictor (report 02 §2.1)."""
    blowouts = colley.rate(toy(ROUND_ROBIN))
    squeakers = colley.rate(
        toy([(h, a, 1, 0) if hp > ap else (h, a, 0, 1) for h, a, hp, ap in ROUND_ROBIN])
    )
    assert blowouts == pytest.approx(squeakers)


def test_colley_ranks_an_undefeated_team_first() -> None:
    r = colley.rate(toy(ROUND_ROBIN))
    assert max(r, key=lambda t: r[t]) == "A"


# --------------------------------------------------------------------------- SRS


def test_srs_caps_and_floors_the_margin() -> None:
    """A 1-point win counts as 7; a 60-point win counts as 24 (report 02 §2.2)."""
    one_point = srs.rate(toy([("A", "B", 21, 20), ("B", "A", 20, 21)]))
    seven = srs.rate(toy([("A", "B", 21, 14), ("B", "A", 14, 21)]))
    assert one_point == pytest.approx(seven)

    huge = srs.rate(toy([("A", "B", 60, 0), ("B", "A", 0, 60)]))
    capped = srs.rate(toy([("A", "B", 24, 0), ("B", "A", 0, 24)]))
    assert huge == pytest.approx(capped)


def test_srs_average_team_is_zero() -> None:
    r = srs.rate(toy(ROUND_ROBIN))
    assert sum(r.values()) / len(r) == pytest.approx(0.0, abs=1e-9)


def test_srs_lumps_non_majors_into_one_team() -> None:
    """Sports-Reference's convention, kept so the baseline is the real thing."""
    r = srs.rate(
        toy(
            [("A", "B", 21, 14), ("A", "Y", 50, 0), ("B", "Z", 40, 3)],
            classes={"Y": "fcs", "Z": "fcs"},
        )
    )
    assert srs.NON_MAJOR in r
    assert "Y" not in r and "Z" not in r


def test_srs_survives_a_disconnected_schedule_via_minimum_norm() -> None:
    r = srs.rate(toy([("A", "B", 21, 14), ("C", "D", 10, 3)]))
    assert set(r) == {"A", "B", "C", "D"}
    assert all(math.isfinite(v) for v in r.values())


# --------------------------------------------------------------------------- Elo


def test_elo_is_zero_sum_per_game() -> None:
    r = elo.rate(toy(ROUND_ROBIN))
    total = sum(r.values())
    assert total == pytest.approx(4 * CONFIG["baselines"]["elo"]["initial_fbs"], abs=1e-9)


def test_elo_starts_non_fbs_teams_lower() -> None:
    r = elo.rate(toy([("A", "B", 21, 14)], classes={"B": "fcs"}))
    assert r["B"] < CONFIG["baselines"]["elo"]["initial_fbs"]


def test_mov_multiplier_damps_blowouts_and_corrects_autocorrelation() -> None:
    """report 02 §2.7, Neil Paine's published formula."""
    assert elo.mov_multiplier(1, 1500, 1500) == pytest.approx(math.log(2) * 1.0)
    assert elo.mov_multiplier(50, 1500, 1500) < 4.0
    # A heavy favourite winning gains less than an equal team winning the same way.
    assert elo.mov_multiplier(20, 1800, 1400) < elo.mov_multiplier(20, 1500, 1500)


def test_elo_depends_on_order_which_is_exactly_why_it_is_not_the_core() -> None:
    """report 02 §2.7: Elo is path-dependent, so R(5, final) has no clean meaning."""
    forward = elo.rate(toy(ROUND_ROBIN))
    reordered = toy(list(reversed(ROUND_ROBIN)))
    backward = elo.rate(reordered)
    assert forward != pytest.approx(backward)


# ---------------------------------------------------------------- random walker


def test_random_walker_is_a_stationary_distribution_scaled_to_mean_one() -> None:
    r = random_walker.rate(toy(ROUND_ROBIN))
    assert sum(r.values()) / len(r) == pytest.approx(1.0, abs=1e-9)
    assert all(v > 0 for v in r.values())


def test_random_walker_ranks_the_undefeated_team_first() -> None:
    r = random_walker.rate(toy(ROUND_ROBIN))
    assert max(r, key=lambda t: r[t]) == "A"


def test_random_walker_survives_an_undefeated_team_without_patching() -> None:
    """p in (1/2, 1) keeps a back-edge on every game, so no dangling node
    (report 02 §2.11) - the failure that breaks PageRank on the win graph."""
    r = random_walker.rate(toy([("A", "B", 40, 0), ("A", "C", 35, 3), ("B", "C", 10, 7)]))
    assert all(math.isfinite(v) and v > 0 for v in r.values())


def test_connectivity_diagnostic_sees_the_early_season_fragmentation() -> None:
    split = random_walker.schedule_connectivity(toy([("A", "B", 7, 3), ("C", "D", 7, 3)]))
    assert split["n_components"] == 2.0
    assert split["largest_component_share"] == pytest.approx(0.5)
    joined = random_walker.schedule_connectivity(toy(ROUND_ROBIN))
    assert joined["n_components"] == 1.0


# --------------------------------------------------------------------- real data


@needs_archive
def test_all_baselines_agree_that_2023_was_michigan_and_ohio_state() -> None:
    games = windows.games_through(
        load_games([2023], universe="model"), season=2023, week=10, season_type="regular"
    )
    plays = plays_for(load_plays([2023]), games)
    for name, rater in sorted(baselines.RATERS.items()):
        ratings = rater(games, plays, 10, state=None)
        ranking = sorted(ratings, key=lambda t: -ratings[t])[:12]
        assert "Ohio State" in ranking or "Michigan" in ranking, name


@needs_archive
def test_connectivity_improves_through_the_season() -> None:
    games = load_games([2023], universe="model")
    early = random_walker.schedule_connectivity(
        windows.games_through(games, season=2023, week=2, season_type="regular")
    )
    late = random_walker.schedule_connectivity(
        windows.games_through(games, season=2023, week=10, season_type="regular")
    )
    assert early["n_components"] > late["n_components"] == 1.0
    assert early["largest_component_share"] < 1.0
