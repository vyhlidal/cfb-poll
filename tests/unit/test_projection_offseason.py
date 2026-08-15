"""The offseason ingest, tested against the archive it actually reads.

Coverage is the thing worth asserting here, because coverage is what the product
publishes as a caveat and a caveat that drifts away from the data is worse than
no caveat. The tests below pin the properties the artifacts claim: that names
match the games frame almost exactly, that every miss is explained, that portal
destinations are systematically thinner than origins, and that the offence-only
hole in returning production is real rather than a hedge.

Every test skips cleanly without the private CFBD archive, which is the posture
the rest of the repository takes toward it: `archive/` is gitignored because CFBD
terms §3 bar republishing raw bodies, so a fork has no way to run these.
"""

from __future__ import annotations

import polars as pl
import pytest

from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games
from cfbpoll.projection import offseason

DESIGN_SEASONS = (2022, 2023, 2024)

pytestmark = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised",
)


def _has_cfbd(season: int) -> bool:
    return bool(offseason.returning_production(season).height)


requires_cfbd = pytest.mark.skipif(
    not _has_cfbd(2024), reason="private CFBD offseason archive not present"
)


@pytest.fixture(scope="module")
def games() -> pl.DataFrame:
    return load_games([2021, 2022, 2023, 2024])


def _fbs(games: pl.DataFrame, season: int) -> list[str]:
    frame = games.filter(pl.col("season") == season)
    return sorted(
        set(frame.filter(pl.col("home_class") == "fbs")["home_team"].to_list())
        | set(frame.filter(pl.col("away_class") == "fbs")["away_team"].to_list())
    )


@requires_cfbd
@pytest.mark.parametrize("season", DESIGN_SEASONS)
def test_every_coverage_gap_is_explained(games: pl.DataFrame, season: int) -> None:
    """The claim on the published artifact: every team missing from returning
    production is NEW TO FBS and therefore has no prior FBS production to return.

    That distinction is the difference between a coverage number a reader can act
    on and one that just looks bad, and it is asserted rather than asserted-in-
    prose."""
    report = offseason.coverage(
        season, _fbs(games, season), prior_teams=_fbs(games, season - 1)
    )
    assert report["returning_production"]["missing_unexplained"] == []
    assert report["returning_production"]["rate"] > 0.97
    assert report["portal"]["rate"] == 1.0
    assert report["coaching"]["rate"] == 1.0


@requires_cfbd
@pytest.mark.parametrize("season", DESIGN_SEASONS)
def test_portal_destinations_are_thinner_than_origins(season: int) -> None:
    """The caveat every artifact carries, as a measurement.

    `origin` is complete and `destination` is not, so departures are measured
    well and arrivals are not - and the recipe's decision to standardise the net
    term WITHIN each season depends on this being true and on the rate drifting
    between cycles."""
    frame = offseason.portal(season)
    assert frame.height
    rate = float(frame["portal_in_coverage"][0])
    assert 0.4 < rate < 1.0, rate
    assert frame["portal_out"].sum() > frame["portal_in"].sum()


@requires_cfbd
def test_the_destination_rate_really_does_drift_across_cycles() -> None:
    """Why the portal term is standardised per season rather than pooled raw.

    If this ever stops being true, pooling raw counts becomes defensible and the
    recipe should be revisited - so the drift is pinned rather than assumed."""
    rates = {
        season: float(offseason.portal(season)["portal_in_coverage"][0])
        for season in DESIGN_SEASONS
    }
    assert max(rates.values()) - min(rates.values()) > 0.05, rates


@requires_cfbd
def test_returning_production_is_offence_only() -> None:
    """The hole, asserted so it cannot quietly become a hedge.

    CFBD serves offensive usage and its three unit splits, and nothing defensive
    at all. If a defensive field ever appears this test fails and the artifacts'
    "offence only" caveat has to be rewritten - which is the correct outcome."""
    frame = offseason.returning_production(2024)
    assert frame.height
    columns = set(frame.columns)
    assert {"returning_usage", "returning_passing_usage", "returning_receiving_usage",
            "returning_rushing_usage"} <= columns
    assert not any("defen" in c or "defensive" in c for c in columns)


@requires_cfbd
def test_the_ppa_column_is_carried_and_is_not_the_usage_column() -> None:
    """Both fields are on the same CFBD row and they are genuinely different
    numbers. Carrying the one we refuse is what makes the refusal checkable."""
    frame = offseason.returning_production(2024).drop_nulls(
        ["returning_usage", "returning_percent_ppa"]
    )
    assert frame.height > 100
    usage = frame["returning_usage"].to_numpy()
    ppa = frame["returning_percent_ppa"].to_numpy()
    assert not (usage == ppa).all()


@requires_cfbd
@pytest.mark.parametrize("season", DESIGN_SEASONS)
def test_a_coaching_change_is_a_change_of_name_and_unknowns_stay_unknown(
    season: int,
) -> None:
    """`coach_change` is 1, 0 or null - never a guess. A school with no
    prior-season row is a new FBS member, and "we do not know" and "they fired
    someone" are different facts."""
    frame = offseason.coaching(season)
    assert frame.height > 120
    assert set(frame["coach_change"].drop_nulls().unique().to_list()) <= {0, 1}
    changed = frame.filter(pl.col("coach_change") == 1)
    assert changed.height > 5
    for row in changed.to_dicts():
        assert row["coach_name"] != row["coach_name_prior"]
    unchanged = frame.filter(pl.col("coach_change") == 0)
    for row in unchanged.to_dicts():
        assert row["coach_name"] == row["coach_name_prior"]
    for row in frame.filter(pl.col("coach_change").is_null()).to_dicts():
        assert row["coach_name_prior"] is None


@requires_cfbd
def test_an_interim_does_not_become_the_head_coach() -> None:
    """A school can carry more than one coach row in a season and the primary is
    picked by games worked. Rice 2024 is the worked example: a four-game interim
    beside the coach who worked the rest."""
    frame = offseason.coaching(2025)
    rice = frame.filter(pl.col("team") == "Rice")
    assert rice.height == 1
    assert rice["coach_name_prior"][0] not in (None, "Pete Alamar")


@requires_cfbd
def test_the_ap_baseline_ranks_exactly_twenty_five_teams() -> None:
    """The AP poll ranks 25 teams and is silent about the other 109, and every
    fair-comparison decision in the backtest follows from taking that seriously
    rather than padding it out."""
    for season in DESIGN_SEASONS:
        frame = offseason.ap_preseason(season)
        assert frame.height == 25, season
        assert frame["ap_rank"].to_list() == list(range(1, 26)), season
        assert frame["team"].n_unique() == 25, season


@requires_cfbd
def test_the_joined_table_keeps_a_team_that_only_one_source_has() -> None:
    """Outer join, so a thin portal file cannot make a team vanish from a ranking.
    Nulls survive to `recipe.build_design`, which imputes once, in public."""
    table = offseason.table(2024)
    assert table.height >= offseason.returning_production(2024).height
    assert table["team"].n_unique() == table.height


def test_missing_archive_returns_empty_frames_rather_than_raising(tmp_path) -> None:
    """A fork with no CFBD archive gets a DEGRADED run, not a failed one - the
    same posture `cfbd.archived_games` takes toward a missing postseason pull."""
    assert offseason.returning_production(2024, tmp_path).height == 0
    assert offseason.portal(2024, tmp_path).height == 0
    assert offseason.coaching(2024, tmp_path).height == 0
    assert offseason.ap_preseason(2024, tmp_path).height == 0
    report = offseason.coverage(2024, ["Anywhere"], tmp_path)
    assert report["returning_production"]["rate"] == 0.0
    assert report["ap_preseason_available"] is False


def test_the_pull_budget_is_pinned() -> None:
    """Four calls per season, guarded against drift the way
    `cfbd.WEEKLY_CALL_BUDGET` is."""
    assert offseason.PULL_CALL_BUDGET == 4
    assert offseason.AP_POLL_NAME == "AP Top 25"
