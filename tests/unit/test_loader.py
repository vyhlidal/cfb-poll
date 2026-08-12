"""The games loader, checked against facts established by the verified backfill.

These are not smoke tests. Every number here comes from docs/data-findings.md or
from report 01's independently-counted totals, so a silent upstream change or a
filtering regression fails the build rather than quietly reshaping the poll.
"""

from __future__ import annotations

import polars as pl
import pytest

from cfbpoll.ingest import windows
from cfbpoll.ingest.sportsdataverse import (
    CANONICAL_COLUMNS,
    DEFAULT_ARCHIVE,
    GAME_TYPES,
    canonical_games,
    fbs_vs_fbs,
    load_games,
    model_universe,
)

SEASONS = (2021, 2022, 2023, 2024, 2025)

#: report 01, re-verified during the backfill: 3,864 completed FBS-vs-FBS games.
EXPECTED_FBS_VS_FBS = {2021: 732, 2022: 734, 2023: 792, 2024: 798, 2025: 808}

pytestmark = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised; run `cfbpoll archive sync`",
)


@pytest.fixture(scope="module")
def raw() -> pl.DataFrame:
    return canonical_games(SEASONS)


@pytest.fixture(scope="module")
def games() -> pl.DataFrame:
    return load_games(SEASONS, universe="model")


def test_canonical_schema(raw: pl.DataFrame) -> None:
    assert tuple(raw.columns) == CANONICAL_COLUMNS
    assert raw["game_id"].n_unique() == raw.height
    assert set(raw["game_type"].unique().to_list()) <= set(GAME_TYPES)


def test_no_banned_columns_survive_the_load(raw: pl.DataFrame) -> None:
    """home_pregame_elo and excitement_index are someone else's model output."""
    banned = {"home_pregame_elo", "away_pregame_elo", "excitement_index", "home_post_win_prob"}
    assert banned.isdisjoint(set(raw.columns))


def test_fbs_vs_fbs_counts_match_the_backfill(raw: pl.DataFrame) -> None:
    completed = raw.filter(
        pl.col("completed")
        & pl.col("home_points").is_not_null()
        & pl.col("away_points").is_not_null()
    )
    counts = fbs_vs_fbs(completed).group_by("season").len().sort("season").to_dict(as_series=False)
    got = dict(zip(counts["season"], counts["len"], strict=True))
    assert got == EXPECTED_FBS_VS_FBS
    assert sum(got.values()) == 3864


def test_canceled_app_state_liberty_is_excluded_by_the_completed_filter(
    raw: pl.DataFrame,
) -> None:
    """docs/data-findings.md §4: 2024 has 799 scheduled FBS-vs-FBS games, 798 completed."""
    scheduled = fbs_vs_fbs(raw.filter(pl.col("season") == 2024))
    assert scheduled.height == 799
    row = scheduled.filter(pl.col("game_id") == 401640992)
    assert row.height == 1
    assert row["completed"][0] is False
    assert row["home_points"][0] is None
    modelled = load_games([2024], universe="fbs_vs_fbs")
    assert modelled.height == 798
    assert 401640992 not in set(modelled["game_id"].to_list())


def test_completed_but_scoreless_rows_are_also_dropped(raw: pl.DataFrame) -> None:
    """Two 2025 D-II games carry completed=True with null points."""
    bad = raw.filter(
        pl.col("completed") & (pl.col("home_points").is_null() | pl.col("away_points").is_null())
    )
    assert bad.height == 2
    kept = load_games([2025], universe="all")
    assert set(bad["game_id"].to_list()).isdisjoint(set(kept["game_id"].to_list()))


def test_game_401778314_is_keyed_by_season_type_not_week(raw: pl.DataFrame) -> None:
    """docs/data-findings.md §1: a December bowl labelled week=1.

    Keyed on week alone it lands in the season opener. Keyed on
    (season_type, week) it is a postseason bucket that sorts last.
    """
    row = raw.filter(pl.col("game_id") == 401778314)
    assert row.height == 1
    assert row["week"][0] == 1
    assert row["season_type"][0] == "postseason"
    assert row["start_date"][0].month == 12
    assert row["game_type"][0] == "bowl_non_cfp"

    buckets = windows.season_buckets(load_games([2025], universe="model"), 2025)
    postseason_w1 = next(b for b in buckets if b.season_type == "postseason" and b.week == 1)
    assert postseason_w1.order == max(b.order for b in buckets)


def test_naive_week_filter_would_leak_december_into_week_one(raw: pl.DataFrame) -> None:
    """The bug this whole module exists to prevent, asserted as a fact about the data."""
    naive = raw.filter((pl.col("season") == 2025) & (pl.col("week") == 1) & pl.col("completed"))
    assert naive.filter(pl.col("start_date").dt.month() == 12).height > 0
    correct = windows.games_through(
        load_games([2025], universe="model"), season=2025, week=1, season_type="regular"
    )
    assert correct.filter(pl.col("start_date").dt.month() == 12).height == 0


def test_division_guard_is_clean_on_the_model_universe(games: pl.DataFrame) -> None:
    """docs/data-findings.md §2: the guard runs AFTER classification filtering."""
    assert windows.suspicious_buckets(games).height == 0


def test_conference_championships_are_identified_every_season(games: pl.DataFrame) -> None:
    counts = (
        games.filter(pl.col("game_type") == "conf_champ")
        .group_by("season")
        .len()
        .sort("season")
        .to_dict(as_series=False)
    )
    got = dict(zip(counts["season"], counts["len"], strict=True))
    # Ten FBS conference championship games in 2021-2023 (the Pac-12 collapse
    # takes it to nine from 2024). 2021 is the structural fallback's only
    # customer: that season carries no `notes` at all.
    assert got == {2021: 10, 2022: 10, 2023: 10, 2024: 9, 2025: 9}


def test_2021_structural_fallback_excludes_the_covid_makeup_game(games: pl.DataFrame) -> None:
    """California-USC, 4 Dec 2021, was a postponed regular-season game, not a title game."""
    week14 = games.filter(
        (pl.col("season") == 2021) & (pl.col("week") == 14) & (pl.col("home_class") == "fbs")
    )
    labels = dict(zip(week14["home_team"].to_list(), week14["game_type"].to_list(), strict=True))
    assert labels["California"] == "regular"
    assert labels["Alabama"] == "conf_champ"


def test_postseason_absent_from_2021_and_2022(raw: pl.DataFrame) -> None:
    """A real archive fact worth failing on if it ever changes: no bowls before 2023."""
    early = raw.filter(pl.col("season").is_in([2021, 2022]))
    assert early["season_type"].unique().to_list() == ["regular"]
    assert set(early["game_type"].unique().to_list()) == {"regular", "conf_champ"}


def test_cfp_and_bowls_split_correctly(games: pl.DataFrame) -> None:
    counts = (
        games.filter(pl.col("season") >= 2023)
        .group_by(["season", "game_type"])
        .len()
        .sort(["season", "game_type"])
    )
    got = {(int(s), t): int(n) for s, t, n in counts.iter_rows()}
    assert got[(2023, "cfp")] == 3  # two semifinals plus the title game
    assert got[(2024, "cfp")] == 11  # the first 12-team bracket
    assert got[(2025, "cfp")] == 11
    assert got[(2023, "bowl_non_cfp")] == 39
    assert got[(2024, "bowl_non_cfp")] == 35
    assert got[(2025, "bowl_non_cfp")] == 35


def test_model_universe_is_wider_than_fbs_and_narrower_than_all() -> None:
    every = load_games([2023], universe="all")
    model = load_games([2023], universe="model")
    fbs = load_games([2023], universe="fbs_vs_fbs")
    assert fbs.height < model.height < every.height
    assert model.height == model_universe(every).height
    # FCS-vs-FCS coverage is what identifies individual FCS coefficients
    # (report 02 §3.7's open data dependency, now closed).
    fcs_only = model.filter((pl.col("home_class") == "fcs") & (pl.col("away_class") == "fcs"))
    assert fcs_only.height == 635


def test_loader_is_deterministic() -> None:
    a = load_games([2023], universe="model")
    b = load_games([2023], universe="model")
    assert a.equals(b)
    assert a["game_id"].is_sorted()
