"""The play loader, checked against the archive rather than against a mock.

Same standard as tests/unit/test_loader.py: every number here is a fact about the
2021-2023 archive, so an upstream schema drift or a filtering regression fails
the build instead of quietly reshaping L1.
"""

from __future__ import annotations

import polars as pl
import pytest

from cfbpoll.ingest.plays import (
    CANONICAL_COLUMNS,
    DEFAULT_ARCHIVE,
    DUPLICATE_PLAY_ROWS,
    PLAY_CLASSES,
    PLAY_TYPE_CLASS,
    RAW_COLUMNS,
    attach_games,
    join_report,
    load_plays,
    plays_for,
)
from cfbpoll.ingest.sportsdataverse import load_games

SEASONS = (2021, 2022, 2023)

#: FBS-vs-FBS play coverage is COMPLETE for the tune seasons. If this ever stops
#: being true, L1 is quietly fitting a different universe than L2 and the demo
#: numbers stop being comparable.
EXPECTED_FBS_VS_FBS_GAMES = {2021: 732, 2022: 734, 2023: 792}

pytestmark = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "pbp").exists(),
    reason="local archive not materialised; run `cfbpoll archive sync`",
)


@pytest.fixture(scope="module")
def plays() -> pl.DataFrame:
    return load_plays(SEASONS)


@pytest.fixture(scope="module")
def games() -> pl.DataFrame:
    return load_games(SEASONS, universe="model")


def test_canonical_schema(plays: pl.DataFrame) -> None:
    assert tuple(plays.columns) == CANONICAL_COLUMNS
    assert set(plays["play_class"].unique().to_list()) <= set(PLAY_CLASSES)
    assert plays["season"].n_unique() == len(SEASONS)


def test_no_third_party_model_output_survives_the_load(plays: pl.DataFrame) -> None:
    """The single most load-bearing test in this file (report 01 §5.6).

    These files ship a fitted expected-points model, a win-probability model, an
    Elo and a betting line. None of them may appear in a frame a fit can see.
    """
    banned = {
        "EPA",
        "ep_before",
        "ep_after",
        "ppa",
        "wpa",
        "wp_before",
        "wp_after",
        "def_wp_before",
        "def_wp_after",
        "ExpScoreDiff",
        "ExpScoreDiff_Time_Ratio",
        "fg_make_prob",
        "home_team_pregame_elo",
        "away_team_pregame_elo",
        "spread",
        "formatted_spread",
        "over_under",
        "No_Score_before",
        "FG_before",
        "TD_before",
        "No_Score_after",
        "FG_after",
        "TD_after",
    }
    assert banned.isdisjoint(set(RAW_COLUMNS))
    assert banned.isdisjoint(set(plays.columns))


def test_play_order_key_is_unique_within_a_game(plays: pl.DataFrame) -> None:
    """`game_row_number` is the only unique ordering key in the file: `row`
    restarts each half, `id_play` collides, `game_play_number` repeats on
    penalties."""
    assert plays.select("game_id", "play_index").n_unique() == plays.height


def test_exact_duplicate_rows_in_2021_are_dropped() -> None:
    """4,810 rows of play_by_play_2021.parquet are byte-identical repeats of
    another row in the same game (343 games). Left in, they would double the
    weight of a random 3% of 2021's plays."""
    for season, expected in ((2021, DUPLICATE_PLAY_ROWS[2021]), (2022, 0), (2023, 0)):
        raw = pl.read_parquet(
            DEFAULT_ARCHIVE / "pbp" / f"play_by_play_{season}.parquet",
            columns=["game_id", "game_row_number"],
        )
        dropped = raw.height - raw.select("game_id", "game_row_number").n_unique()
        assert dropped == expected, f"{season}: {dropped} duplicate rows, expected {expected}"


def test_the_archive_has_no_play_type_the_classifier_does_not_know(
    plays: pl.DataFrame, games: pl.DataFrame
) -> None:
    report = join_report(plays, games)
    assert report["unknown_play_types"] == []


def test_join_integrity_against_the_games_loader(plays: pl.DataFrame, games: pl.DataFrame) -> None:
    """Every play that reaches a fit belongs to a game in the games table, and
    the two sources agree on who was home."""
    report = join_report(plays, games)
    assert report["home_away_disagreements"] == 0
    joined = attach_games(plays, games)
    assert set(joined["game_id"].unique().to_list()) <= set(games["game_id"].to_list())


def test_orphan_plays_are_dropped_and_counted(plays: pl.DataFrame, games: pl.DataFrame) -> None:
    """86 game_ids in the 2021-2023 play files have no row in cfb_schedules_*.
    The schedule series is the authority; those plays must never reach a fit."""
    report = join_report(plays, games)
    assert report["orphan_plays"] > 0
    orphans = set(report["orphan_game_ids"])  # type: ignore[arg-type]
    joined = attach_games(plays, games)
    assert orphans.isdisjoint(set(joined["game_id"].unique().to_list()))


def test_fbs_vs_fbs_play_coverage_is_complete(plays: pl.DataFrame) -> None:
    for season, expected in EXPECTED_FBS_VS_FBS_GAMES.items():
        fbs = load_games([season], universe="fbs_vs_fbs")
        assert fbs.height == expected
        report = join_report(plays.filter(pl.col("season") == season), fbs)
        assert report["games_without_plays"] == 0


def test_week_and_season_type_come_from_the_games_table(
    plays: pl.DataFrame, games: pl.DataFrame
) -> None:
    """docs/data-findings.md §1. The play file carries its own `week` and
    `season_type` columns and this package refuses to read either."""
    assert "week" not in plays.columns
    assert "season_type" not in plays.columns
    assert "week" not in RAW_COLUMNS
    assert "season_type" not in RAW_COLUMNS
    joined = plays_for(plays, games)
    check = joined.select("game_id", "week", "season_type").unique()
    merged = check.join(games.select("game_id", "week", "season_type"), on="game_id", how="inner")
    assert merged.height == check.height


def test_snap_definition(plays: pl.DataFrame) -> None:
    """A snap is a genuine down-and-distance play in regulation. Kickoffs carry a
    dummy `down = 1` in this feed and must never be counted as one."""
    snaps = plays.filter(pl.col("is_snap"))
    assert snaps["down"].min() == 1
    assert snaps["down"].max() == 4
    assert snaps["yards_to_goal"].min() >= 1
    assert snaps["yards_to_goal"].max() <= 99
    assert snaps["period"].max() <= 4
    assert not snaps["play_class"].is_in(["kickoff", "two_point", "non_play"]).any()
    assert plays.filter(pl.col("play_class") == "kickoff")["is_snap"].sum() == 0


def test_kneels_and_spikes_are_detected(plays: pl.DataFrame) -> None:
    kneels = plays.filter(pl.col("is_kneel"))
    assert kneels.height > 1000  # ~940 in 2023 alone
    assert plays.filter(pl.col("is_spike")).height >= 40  # 46 across 2021-2023
    assert kneels.filter(pl.col("play_class") == "rush").height / kneels.height > 0.9


def test_score_margin_is_the_pre_snap_score(plays: pl.DataFrame) -> None:
    """Garbage time is decided on the score BEFORE the snap. Using the post-play
    score would let a touchdown push its own scoring play into garbage time."""
    scoring = plays.filter(pl.col("points_scored") > 0)
    assert scoring.height > 0
    # The first play of every game is at 0-0 whatever happens on it.
    firsts = plays.group_by("game_id").agg(pl.col("score_margin").sort_by("play_index").first())
    assert firsts["score_margin"].abs().max() == 0.0


def test_play_type_class_table_is_exhaustive_and_valid() -> None:
    assert set(PLAY_TYPE_CLASS.values()) <= set(PLAY_CLASSES)
    assert None in PLAY_TYPE_CLASS
