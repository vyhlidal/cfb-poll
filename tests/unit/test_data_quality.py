"""The data-quality gate: every assertion in report 01 §5.5, and its three outcomes.

Most of this runs on synthetic frames, on purpose. The gate's job is to fail on
bad data, and bad data is exactly what the archive does not contain - a test that
only ever sees the real archive can prove a check passes and can never prove it
would catch anything. The archive-gated block at the bottom is the other half:
that the checks agree with the real bytes, including the two amendments in
docs/data-findings.md that report 01 predates.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from cfbpoll.ingest.sportsdataverse import CANONICAL_COLUMNS, DEFAULT_ARCHIVE
from cfbpoll.validate import data_quality as dq

SCHEMA = {
    "game_id": pl.Int64,
    "season": pl.Int32,
    "week": pl.Int32,
    "season_type": pl.Utf8,
    "game_type": pl.Utf8,
    "start_date": pl.Datetime(time_zone="UTC"),
    "completed": pl.Boolean,
    "neutral_site": pl.Boolean,
    "conference_game": pl.Boolean,
    "home_team": pl.Utf8,
    "away_team": pl.Utf8,
    "home_points": pl.Int32,
    "away_points": pl.Int32,
    "home_class": pl.Utf8,
    "away_class": pl.Utf8,
    "source": pl.Utf8,
}


def _game(
    game_id: int,
    home: str,
    away: str,
    *,
    week: int = 10,
    season: int = 2023,
    season_type: str = "regular",
    month: int = 11,
    day: int = 4,
    year: int | None = None,
    completed: bool = True,
    home_points: int | None = 24,
    away_points: int | None = 17,
    home_class: str = "fbs",
    away_class: str = "fbs",
) -> dict[str, Any]:
    return {
        "game_id": game_id,
        "season": season,
        "week": week,
        "season_type": season_type,
        "game_type": "regular",
        "start_date": datetime(year or season, month, day, 18, 0, tzinfo=UTC),
        "completed": completed,
        "neutral_site": False,
        "conference_game": True,
        "home_team": home,
        "away_team": away,
        "home_points": home_points,
        "away_points": away_points,
        "home_class": home_class,
        "away_class": away_class,
        "source": "sportsdataverse",
    }


def _frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=SCHEMA).select(list(CANONICAL_COLUMNS))


def _scored(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.filter(
        pl.col("completed")
        & pl.col("home_points").is_not_null()
        & pl.col("away_points").is_not_null()
    )


def _pair(n: int, week: int = 10, **kw: Any) -> list[dict[str, Any]]:
    """n distinct FBS-vs-FBS games in one week, no team repeated."""
    return [
        _game(1000 + i, f"Home {i}", f"Away {i}", week=week, **kw) for i in range(n)
    ]


# --------------------------------------------------------- bullet 1: completeness


def test_completed_and_scored_passes_a_finished_week() -> None:
    check = dq.completed_and_scored(_frame(_pair(5)), 2023, "regular", 10)
    assert check.status == dq.PASS
    assert check.measured["n_completed_with_scores"] == 5


def test_completed_and_scored_fails_and_names_the_game() -> None:
    rows = _pair(4) + [_game(9999, "Rice", "Tulane", completed=False, home_points=None)]
    check = dq.completed_and_scored(_frame(rows), 2023, "regular", 10)
    assert check.status == dq.FAIL
    assert check.measured["offending_game_ids"] == [9999]
    assert "9999" in check.detail


def test_completed_but_scoreless_is_a_failure_too() -> None:
    """Two 2025 D-II rows carry completed=True with null points; the flag is not enough."""
    rows = _pair(3) + [_game(8888, "A", "B", home_points=None, away_points=None)]
    check = dq.completed_and_scored(_frame(rows), 2023, "regular", 10)
    assert check.status == dq.FAIL
    assert check.measured["offending_game_ids"] == [8888]


def test_a_documented_cancellation_is_not_a_data_error() -> None:
    """App State-Liberty, 401640992, was canceled (docs/data-findings.md §4)."""
    gid = dq.KNOWN_CANCELLED_GAME_IDS[0]
    rows = _pair(3) + [
        _game(gid, "App State", "Liberty", completed=False, home_points=None, away_points=None)
    ]
    check = dq.completed_and_scored(_frame(rows), 2023, "regular", 10)
    assert check.status == dq.PASS
    assert check.measured["n_known_cancelled"] == 1
    assert "cancellation" in check.detail


def test_completeness_skips_rather_than_passes_an_empty_bucket() -> None:
    check = dq.completed_and_scored(_frame(_pair(3)), 2023, "regular", 11)
    assert check.status == dq.SKIP


# ------------------------------------------------- bullet 2: count, and no repeats


def test_week_game_count_fails_above_the_measured_ceiling() -> None:
    frame = _frame(_pair(dq.MAX_WEEK_GAMES + 1))
    check = dq.week_game_count(_scored(frame), 2023, "regular", 10)
    assert check.status == dq.FAIL
    assert check.measured["n_games"] == dq.MAX_WEEK_GAMES + 1


def test_one_game_is_a_real_week() -> None:
    """Army-Navy has its own week in every season, with exactly one FBS game."""
    check = dq.week_game_count(_frame([_game(1, "Army", "Navy", week=15)]), 2023, "regular", 15)
    assert check.status == dq.PASS


def test_no_team_twice_fails_in_an_ordinary_week() -> None:
    rows = _pair(3) + [_game(77, "Home 0", "Someone Else")]
    check = dq.no_team_twice(_frame(rows), 2023, "regular", 10)
    assert check.status == dq.FAIL
    assert check.measured["over_allowance"] == [{"team": "Home 0", "appearances": 2}]


def test_regular_week_one_allows_two_because_upstream_folds_week_zero_into_it() -> None:
    rows = _pair(2, week=1) + [_game(77, "Home 0", "Week Zero Opponent", week=1)]
    check = dq.no_team_twice(_frame(rows), 2023, "regular", 1)
    assert check.status == dq.PASS
    assert check.measured["allowance"] == dq.MAX_TEAM_APPEARANCES_REGULAR_WEEK_ONE

    over = rows + [_game(78, "Home 0", "A Third Opponent", week=1)]
    assert dq.no_team_twice(_frame(over), 2023, "regular", 1).status == dq.FAIL


def test_a_postseason_bucket_holds_every_cfp_round_at_once() -> None:
    rounds = [
        _game(1, "Ohio State", "Tennessee", week=1, season_type="postseason", month=12, day=21),
        _game(2, "Oregon", "Ohio State", week=1, season_type="postseason", year=2025, month=1),
        _game(3, "Texas", "Ohio State", week=1, season_type="postseason", year=2025, month=1),
        _game(4, "Notre Dame", "Ohio State", week=1, season_type="postseason", year=2025, month=1),
    ]
    check = dq.no_team_twice(_frame(rounds), 2023, "postseason", 1)
    assert check.status == dq.PASS
    assert check.measured["max_appearances"] == 4


# ------------------------------------------- bullet 3: the roster and games played


def test_roster_check_skips_without_the_private_teams_body() -> None:
    check = dq.teams_present_with_plausible_games(_frame(_pair(3)), [], 10)
    assert check.status == dq.SKIP
    assert "PRIVATE" in check.detail


def test_roster_check_fails_on_a_team_that_never_appears() -> None:
    window = _frame(_pair(3))
    teams = [{"school": "Home 0"}, {"school": "Away 0"}, {"school": "Nowhere State"}]
    check = dq.teams_present_with_plausible_games(window, teams, 1)
    assert check.status == dq.FAIL
    assert check.measured["missing"] == ["Nowhere State"]


def test_roster_check_fails_on_an_implausible_games_played_count() -> None:
    window = _frame(_pair(3))
    check = dq.teams_present_with_plausible_games(window, [{"school": "Home 0"}], 12)
    assert check.status == dq.FAIL
    assert check.measured["implausible"] == [{"team": "Home 0", "games_played": 1}]


# ---------------------------------------------------------- bullet 4: box scores


def test_box_scores_reconcile_from_games_teams() -> None:
    frame = _scored(_frame([_game(1, "Home", "Away", home_points=24, away_points=17)]))
    bodies = [
        {
            "id": 1,
            "teams": [
                {"team": "Home", "homeAway": "home", "points": 24},
                {"team": "Away", "homeAway": "away", "points": 17},
            ],
        }
    ]
    check = dq.box_scores_reconcile(frame, bodies, [])
    assert check.status == dq.PASS
    assert check.measured == {
        "source": "/games/teams",
        "n_compared": 2,
        "n_disagreements": 0,
        "disagreements": [],
    }


def test_box_scores_that_disagree_with_the_final_score_halt_publication() -> None:
    frame = _scored(_frame([_game(1, "Home", "Away", home_points=24, away_points=17)]))
    bodies = [{"id": 1, "teams": [{"team": "Home", "points": 21}]}]
    check = dq.box_scores_reconcile(frame, bodies, [])
    assert check.status == dq.FAIL
    assert check.measured["disagreements"] == ["1 Home: box 21 vs final 24"]


def test_line_scores_are_the_fallback_reconciliation() -> None:
    frame = _scored(_frame([_game(1, "Home", "Away", home_points=24, away_points=17)]))
    games = [{"id": 1, "homeLineScores": [7, 3, 7, 7], "awayLineScores": [0, 10, 0, 7]}]
    check = dq.box_scores_reconcile(frame, [], games)
    assert check.status == dq.PASS
    assert check.measured["source"] == "/games lineScores"

    broken = [{"id": 1, "homeLineScores": [7, 3, 7, 0], "awayLineScores": [0, 10, 0, 7]}]
    assert dq.box_scores_reconcile(frame, [], broken).status == dq.FAIL


def test_box_scores_skip_when_nothing_is_archived() -> None:
    frame = _scored(_frame(_pair(2)))
    assert dq.box_scores_reconcile(frame, [], []).status == dq.SKIP


# ------------------------------------------------------ bullet 5: rating movement


def _run_dir(path: Path, teams: dict[str, float], *, provisional: bool = False) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "team": sorted(teams),
            "power": [teams[t] for t in sorted(teams)],
            "rank": list(range(1, len(teams) + 1)),
        }
    ).write_parquet(path / "ratings_live.parquet")
    (path / "poll.json").write_text(json.dumps({"provisional": provisional}), encoding="utf-8")
    return path


def test_rating_movement_passes_inside_the_bound(tmp_path: Path) -> None:
    was = _run_dir(tmp_path / "w09", {"A": 20.0, "B": 10.0})
    now = _run_dir(tmp_path / "w10", {"A": 22.0, "B": 9.0})
    check = dq.rating_movement_bounded(now, was)
    assert check.status == dq.PASS
    assert check.measured["max_move_points"] == pytest.approx(2.0)
    assert check.measured["max_move_team"] == "A"


def test_an_implausible_jump_is_a_data_error_signal(tmp_path: Path) -> None:
    was = _run_dir(tmp_path / "w09", {"A": 20.0, "B": 10.0})
    now = _run_dir(tmp_path / "w10", {"A": 60.0, "B": 9.0})
    check = dq.rating_movement_bounded(now, was)
    assert check.status == dq.FAIL
    assert check.measured["over_bound"] == [{"team": "A", "move_points": 40.0}]


def test_a_provisional_week_skips_rather_than_being_judged(tmp_path: Path) -> None:
    """Before week 5 the schedule graph is barely connected; 2023 w02 moved 24.89."""
    was = _run_dir(tmp_path / "w01", {"A": 20.0})
    now = _run_dir(tmp_path / "w02", {"A": 60.0}, provisional=True)
    check = dq.rating_movement_bounded(now, was)
    assert check.status == dq.SKIP
    assert "PROVISIONAL" in check.detail


def test_rating_movement_skips_without_a_previous_run(tmp_path: Path) -> None:
    now = _run_dir(tmp_path / "w10", {"A": 20.0})
    assert dq.rating_movement_bounded(now, None).status == dq.SKIP
    assert dq.rating_movement_bounded(now, tmp_path / "nope").status == dq.SKIP


# ------------------------------------------------------- bullet 6: the two sources


def test_cross_source_passes_when_both_pipelines_agree() -> None:
    frame = _scored(_frame([_game(1, "Home", "Away", home_points=24, away_points=17)]))
    rows = [{"id": 1, "homePoints": 24, "awayPoints": 17}]
    check = dq.cross_source(frame, rows)
    assert check.status == dq.PASS
    assert check.measured["n_compared"] == 1


def test_cross_source_names_the_disagreement() -> None:
    frame = _scored(_frame([_game(1, "Home", "Away", home_points=24, away_points=17)]))
    rows = [{"id": 1, "homePoints": 24, "awayPoints": 20}]
    check = dq.cross_source(frame, rows)
    assert check.status == dq.FAIL
    assert "CFBD 24-20 vs SportsDataverse 24-17" in check.measured["disagreements"][0]


def test_a_game_cfbd_has_and_the_parquet_does_not_is_a_failure() -> None:
    frame = _scored(_frame([_game(1, "Home", "Away")]))
    rows = [
        {"id": 1, "homePoints": 24, "awayPoints": 17},
        {"id": 2, "homePoints": 7, "awayPoints": 3},
    ]
    check = dq.cross_source(frame, rows)
    assert check.status == dq.FAIL
    assert check.measured["only_in_cfbd"] == [2]


def test_cross_source_skips_for_a_fork_with_no_private_archive() -> None:
    check = dq.cross_source(_scored(_frame(_pair(2))), [])
    assert check.status == dq.SKIP
    assert "PRIVATE" in check.detail


# --------------------------------------------------- bullet 7: the known-bug guard


def test_december_in_regular_week_one_is_the_bug_the_guard_is_for() -> None:
    rows = _pair(2, week=1) + [_game(4242, "Minnesota", "New Mexico", week=1, month=12, day=26)]
    check = dq.no_december_january_week_one(_frame(rows), 2023)
    assert check.status == dq.FAIL
    assert check.measured["offending_game_ids"] == [4242]


def test_the_guard_is_division_aware(tmp_path: Path) -> None:
    """Four D-II/D-III championships dated 2025-12-13 carry regular, week=1.

    docs/data-findings.md §2: the guard as report 01 wrote it false-positives on
    exactly these, which is why it filters on classification first.
    """
    rows = _pair(2, week=1) + [
        _game(1, "John Carroll", "Berry", week=1, month=12, day=13, home_class="iii",
              away_class="iii"),
        _game(2, "Ferris State", "Newberry", week=1, month=12, day=13, home_class="ii",
              away_class="ii"),
    ]
    check = dq.no_december_january_week_one(_frame(rows), 2023)
    assert check.status == dq.PASS


def test_a_postseason_december_week_one_is_correctly_bucketed_not_a_bug() -> None:
    """401778314's real home: postseason week 1 (docs/data-findings.md §1, §14.3)."""
    rows = _pair(2, week=1) + [
        _game(401778314, "Minnesota", "New Mexico", week=1, season_type="postseason",
              month=12, day=26)
    ]
    check = dq.no_december_january_week_one(_frame(rows), 2023)
    assert check.status == dq.PASS
    assert check.measured["n_week_one_december_january_all_buckets"] == 1


# ------------------------------------------------------------- report semantics


def test_a_skip_is_not_a_pass_and_strict_says_so() -> None:
    checks = (
        dq.Check("a", "spec", dq.PASS, "fine"),
        dq.Check("b", "spec", dq.SKIP, "no input"),
    )
    lenient = dq.Report(2023, 10, "regular", checks)
    assert lenient.passed
    assert dq.Report(2023, 10, "regular", checks, strict=True).passed is False
    assert lenient.as_dict()["n_skip"] == 1
    assert lenient.as_dict()["spec"] == "research report 01 §5.5"


def test_one_failure_fails_the_report() -> None:
    checks = (dq.Check("a", "spec", dq.PASS, "fine"), dq.Check("b", "spec", dq.FAIL, "bad"))
    assert dq.Report(2023, 10, "regular", checks).passed is False


def test_check_week_returns_the_failures_as_strings() -> None:
    """The scaffold's published signature, kept: empty means publishable."""
    clean = _frame(_pair(5))
    assert dq.check_week(clean, 2023, 10) == []
    dirty = _frame(_pair(4) + [_game(9999, "Rice", "Tulane", completed=False, home_points=None)])
    failures = dq.check_week(dirty, 2023, 10)
    assert len(failures) == 1
    assert failures[0].startswith("completed_and_scored:")


# ------------------------------------------------------ against the real archive

pytestmark_archive = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised; run `cfbpoll archive sync`",
)


@pytestmark_archive
def test_2023_week_10_passes_every_check_it_can_run() -> None:
    """The one week with a CFBD body in the archive, so all seven data checks run.

    Numbers are facts about the backfilled archive: 62 completed FBS-vs-FBS
    games, 133 FBS teams, 65 games in the CFBD body, every score identical.
    """
    report = dq.validate_week(2023, 10)
    by_name = {c.name: c for c in report.checks}
    assert report.passed
    assert by_name["completed_and_scored"].measured["n_completed_with_scores"] == 62
    assert by_name["cross_source_scores"].status == dq.PASS
    assert by_name["cross_source_scores"].measured["n_disagreements"] == 0
    assert by_name["cross_source_scores"].measured["n_compared"] == 65
    assert by_name["box_scores_reconcile"].status == dq.PASS
    assert by_name["teams_present_with_plausible_games"].measured["n_fbs_teams"] == 133
    # The one input this week does not have: two consecutive run directories.
    assert by_name["rating_movement_bounded"].status == dq.SKIP


@pytestmark_archive
def test_every_season_in_the_archive_clears_the_week_one_guard() -> None:
    """Whether the amended guard is quiet on real data, which is the whole point."""
    from cfbpoll.ingest.sportsdataverse import canonical_games

    frame = canonical_games([2021, 2022, 2023, 2024, 2025])
    for season in (2021, 2022, 2023, 2024, 2025):
        check = dq.no_december_january_week_one(frame, season)
        assert check.status == dq.PASS, check.detail
        # ... and it is quiet because it is amended, not because there is
        # nothing there: the naive count is in the tens every season.
        assert check.measured["n_week_one_december_january_all_buckets"] > 0
