"""R(N, K): the two-argument estimator, its triangle, and the two surfaces.

Report 02 §3.6 makes four claims that are testable and are tested here:

  live week N is R(N, N); hindsight week N is R(N, final); the two differ by ONE
  substitution and nothing else; and the whole thing is a pure function of a SET
  of games, so the grid's diagonal and the directly-computed live surface must
  agree exactly rather than approximately.

The grid is restricted to the first few buckets of a season in most tests. The
estimator does not care how many buckets it is handed - `grid` takes the list -
and a six-bucket triangle exercises every branch a nineteen-bucket one does.
"""

from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games
from cfbpoll.model import l2_results, l4_resume, retro

CONFIG = load_config()
SEASON = 2021  # no postseason rows in the archive: "final" = conference championships

pytestmark = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised",
)


@pytest.fixture(scope="module")
def games() -> pl.DataFrame:
    return load_games([SEASON], universe=str(CONFIG["model"]["fit_universe"]))


@pytest.fixture(scope="module")
def buckets(games: pl.DataFrame) -> list[windows.Bucket]:
    return windows.season_buckets(games, SEASON)[:6]


@pytest.fixture(scope="module")
def triangle(games: pl.DataFrame, buckets: list[windows.Bucket]) -> pl.DataFrame:
    return retro.grid(games, SEASON, CONFIG, buckets)


def test_the_triangle_is_upper_triangular_and_complete(
    triangle: pl.DataFrame, buckets: list[windows.Bucket]
) -> None:
    """K >= N, one cell per pair, nothing missing and nothing extra."""
    pairs = set(
        zip(triangle["eval_order"].to_list(), triangle["data_order"].to_list(), strict=True)
    )
    expected = {(n.order, k.order) for n in buckets for k in buckets if k.order >= n.order}
    assert pairs == expected
    assert all(k >= n for n, k in pairs)


def test_data_before_evaluation_is_refused(
    games: pl.DataFrame, buckets: list[windows.Bucket]
) -> None:
    """Scoring games the rater has not seen is not hindsight, it is leakage."""
    with pytest.raises(ValueError, match="K >= N"):
        retro.cell(games, buckets[3], buckets[1], CONFIG)


def test_grid_diagonal_is_the_live_surface_exactly(
    games: pl.DataFrame, buckets: list[windows.Bucket], triangle: pl.DataFrame
) -> None:
    """R(N,N) read off the grid must equal R(N,N) computed directly. Not close - equal.

    Both paths run the same fixed-iteration bisection over the same inputs, so
    any difference at all means one of them is not the documented estimator.
    """
    from_grid, _ = retro.surfaces(triangle)
    direct = retro.live_surface(games, SEASON, CONFIG, buckets)
    assert_frame_equal(from_grid, direct, check_exact=True)


def test_grid_last_column_is_the_hindsight_surface_exactly(
    games: pl.DataFrame, buckets: list[windows.Bucket], triangle: pl.DataFrame
) -> None:
    _, from_grid = retro.surfaces(triangle)
    direct = retro.hindsight_surface(games, SEASON, CONFIG, buckets)
    assert_frame_equal(from_grid, direct, check_exact=True)


def test_hindsight_of_the_final_week_is_live_of_the_final_week(
    triangle: pl.DataFrame, buckets: list[windows.Bucket]
) -> None:
    """At N = final there is no hindsight to have: R(final, final) is both."""
    live, hindsight = retro.surfaces(triangle)
    final = buckets[-1].order
    a = live.filter(pl.col("eval_order") == final)
    b = hindsight.filter(pl.col("eval_order") == final)
    assert_frame_equal(a, b, check_exact=True)


def test_hindsight_power_is_the_full_window_fit(
    games: pl.DataFrame, buckets: list[windows.Bucket], triangle: pl.DataFrame
) -> None:
    """The ONE substitution: Power comes from K, not from N (report 02 §3.6 A)."""
    _, hindsight = retro.surfaces(triangle)
    final = buckets[-1]
    window = windows.games_through(
        games.filter(pl.col("season") == SEASON),
        season=SEASON,
        week=final.week,
        season_type=final.season_type,
    )
    power = l4_resume.power_from_l2(window, CONFIG)
    for order in sorted({b.order for b in buckets}):
        week = hindsight.filter(pl.col("eval_order") == order)
        for team, value in zip(week["team"].to_list(), week["power"].to_list(), strict=True):
            assert value == pytest.approx(power.rating(team), abs=1e-12)


def test_live_power_is_the_evaluation_window_fit(
    games: pl.DataFrame, buckets: list[windows.Bucket], triangle: pl.DataFrame
) -> None:
    live, _ = retro.surfaces(triangle)
    bucket = buckets[3]
    window = windows.games_through(
        games.filter(pl.col("season") == SEASON),
        season=SEASON,
        week=bucket.week,
        season_type=bucket.season_type,
    )
    power = l4_resume.power_from_l2(window, CONFIG)
    week = live.filter(pl.col("eval_order") == bucket.order)
    for team, value in zip(week["team"].to_list(), week["power"].to_list(), strict=True):
        assert value == pytest.approx(power.rating(team), abs=1e-12)


def test_records_are_the_evaluation_window_not_the_data_window(triangle: pl.DataFrame) -> None:
    """Frozen form: the resume is over games through N, however much data K holds."""
    for order in sorted(set(triangle["eval_order"].to_list())):
        cells = triangle.filter(pl.col("eval_order") == order)
        played = cells.select(
            (pl.col("wins") + pl.col("losses")).sum().over("data_order").alias("n")
        )
        assert played["n"].n_unique() == 1


def test_movers_sign_convention(triangle: pl.DataFrame) -> None:
    """Positive rank_delta means the team ROSE in hindsight - we under-rated them."""
    live, hindsight = retro.surfaces(triangle)
    table = retro.movers(live, hindsight)
    assert table.height > 0
    delta = table["rank_live"] - table["rank_hindsight"]
    assert table["rank_delta"].to_list() == delta.to_list()
    assert (table["abs_rank_delta"] >= 0).all()
    risers = table.filter(pl.col("rank_delta") > 0)
    if risers.height:
        assert (risers["rank_hindsight"] < risers["rank_live"]).all()


def test_movers_by_week_covers_every_week_but_the_first(
    triangle: pl.DataFrame, buckets: list[windows.Bucket]
) -> None:
    live, hindsight = retro.surfaces(triangle)
    table = retro.movers_by_week(live, hindsight, buckets, top_n=10)
    assert sorted(set(table["eval_order"].to_list())) == [b.order for b in buckets[1:]]
    assert table.group_by("eval_order").len()["len"].max() <= 10


def test_the_grid_is_reproducible(
    games: pl.DataFrame, buckets: list[windows.Bucket], triangle: pl.DataFrame
) -> None:
    assert_frame_equal(triangle, retro.grid(games, SEASON, CONFIG, buckets), check_exact=True)


def test_power_column_is_l2_rescaled_to_points(
    games: pl.DataFrame, buckets: list[windows.Bucket]
) -> None:
    """The published `power` is the L2 coefficient times the published scale b."""
    bucket = buckets[-1]
    window = windows.games_through(
        games.filter(pl.col("season") == SEASON),
        season=SEASON,
        week=bucket.week,
        season_type=bucket.season_type,
    )
    l2 = l2_results.fit(window, CONFIG)
    power = l4_resume.power_from_l2(window, CONFIG, l2fit=l2)
    cell = retro.cell(games, bucket, bucket, CONFIG)
    row = cell.filter(pl.col("team") == cell["team"][0]).row(0, named=True)
    assert row["power"] == pytest.approx(power.scale * l2.ratings[row["team"]], abs=1e-12)


def test_2021_has_no_postseason_rows(games: pl.DataFrame) -> None:
    """docs/data-findings.md, and the caveat every 2021/2022 demo must carry:
    "final" in these seasons means through conference championships."""
    assert set(games["season_type"].unique().to_list()) == {"regular"}
