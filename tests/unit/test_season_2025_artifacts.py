"""The three things the 2025 season shipped that nothing else in the suite covers.

  * the PINNED same-record pair, which is an editorial decision the pipeline
    validates instead of trusting (ADR 0012, [[publication.pinned_same_record_pairs]])
  * the revision tally, which is what the site's copy quotes and therefore has to
    be counted off published fields rather than recomputed
  * the 2025 Projection's substituted calendar, whose whole safety argument is
    that a result column cannot reach it

All offline, all synthetic, no archive.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from cfbpoll.config import load_config
from cfbpoll.publish import serving

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str) -> Any:
    """Import a `scripts/` module by path. They are tools, not a package."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _row(team: str, rank: int, record: str, one_in: int) -> dict[str, Any]:
    return {
        "team": team,
        "team_id": rank,
        "rank": rank,
        "record": record,
        "one_in": one_in,
        "tail_p": 1.0 / one_in,
        "power": 20.0 - rank,
        "q_ref_team": "Reference",
        "mark_bg": "#000000",
        "mark_fg": "#ffffff",
        "mark_label": team[:3].upper(),
    }


ROWS = [
    _row("Alpha", 1, "13-0", 1700),
    _row("Bravo", 2, "12-1", 86),
    _row("Charlie", 3, "12-1", 82),
    _row("Delta", 4, "11-2", 40),
    _row("Echo", 5, "12-1", 7),
]


# ------------------------------------------------------ the pinned same-record pair


def _config(pin: dict[str, Any] | None, exclude: list[str] | None = None) -> dict[str, Any]:
    return {
        "publication": {
            "pinned_same_record_pairs": [pin] if pin else [],
            "same_record_pair_exclude": exclude or [],
        }
    }


def test_the_pin_is_rendered_with_both_sides_and_its_reason() -> None:
    pin = {
        "season": 2025,
        "week": 16,
        "leader": "Bravo",
        "foil": "Echo",
        "why": "Same record, twelve places of daylight.",
    }
    pair = serving._pinned_same_record_pair(ROWS, 2025, 16, _config(pin))
    assert pair is not None
    assert pair["pinned"] is True
    assert pair["leader"]["team"] == "Bravo"
    assert pair["foil"]["team"] == "Echo"
    assert pair["leader"]["record"] == pair["foil"]["record"] == "12-1"
    assert pair["why"].startswith("Same record")
    # The slot carries display fields, so the module renders without a second read.
    assert pair["leader"]["mark_bg"] == "#000000"


def test_a_week_with_no_pin_is_a_legitimate_week() -> None:
    assert serving._pinned_same_record_pair(ROWS, 2025, 5, _config(None)) is None


def test_a_pin_naming_a_team_outside_the_top_25_refuses_to_publish() -> None:
    """The failure mode this guard exists for is SILENCE, not noise. A comparison
    module that quietly renders nothing is how a claim gets dropped without
    anybody deciding to drop it."""
    pin = {"season": 2025, "week": 16, "leader": "Bravo", "foil": "Nobody", "why": "x"}
    with pytest.raises(ValueError, match="not in the published top 25"):
        serving._pinned_same_record_pair(ROWS, 2025, 16, _config(pin))


def test_a_pin_whose_teams_do_not_share_a_record_refuses_to_publish() -> None:
    pin = {"season": 2025, "week": 16, "leader": "Bravo", "foil": "Delta", "why": "x"}
    with pytest.raises(ValueError, match="not the same record"):
        serving._pinned_same_record_pair(ROWS, 2025, 16, _config(pin))


def test_the_exclusion_list_is_honoured_mechanically() -> None:
    """The owner's constraint is a config line, not a habit."""
    pin = {"season": 2025, "week": 16, "leader": "Bravo", "foil": "Echo", "why": "x"}
    with pytest.raises(ValueError, match="excluded team"):
        serving._pinned_same_record_pair(ROWS, 2025, 16, _config(pin, exclude=["Echo"]))


def test_every_candidate_pair_is_published_so_the_pin_can_be_second_guessed() -> None:
    candidates = serving._same_record_candidates(ROWS, _config(None, exclude=["Echo"]))
    pairs = {(c["leader"], c["foil"]) for c in candidates}
    assert ("Bravo", "Charlie") in pairs
    assert ("Bravo", "Echo") in pairs
    # 13-0 and 11-2 are unique records here, so neither can pair with anything.
    assert not any("Alpha" in p or "Delta" in p for p in pairs)
    # Widest gap first, and the exclusion is FLAGGED rather than hidden.
    assert candidates[0]["rank_gap"] == 3
    assert any(c["excluded"] for c in candidates if c["foil"] == "Echo")


def test_the_shipped_pin_is_the_one_the_report_describes() -> None:
    """The live config, checked rather than trusted. Washington is an owner
    constraint and the 2025 pin is Georgia against James Madison."""
    publication = load_config()["publication"]
    assert publication["same_record_pair_exclude"] == ["Washington"]
    pins = publication["pinned_same_record_pairs"]
    pin = next(p for p in pins if p["season"] == 2025)
    assert (pin["week"], pin["leader"], pin["foil"]) == (16, "Georgia", "James Madison")
    assert "12-1" in pin["why"]
    assert not ({pin["leader"], pin["foil"]} & set(publication["same_record_pair_exclude"]))


# ------------------------------------------------------------- the revision tally


def test_the_revision_tally_counts_published_fields_and_nothing_else() -> None:
    revision = _load_script("make_revision_numbers")
    rows = [
        {"team": "A", "rank": 1, "hindsight_rank": 1, "rank_delta": 0, "record": "5-0"},
        {"team": "B", "rank": 2, "hindsight_rank": 5, "rank_delta": -3, "record": "4-1"},
        {"team": "C", "rank": 3, "hindsight_rank": 1, "rank_delta": 2, "record": "4-1"},
    ]
    tally = revision.tally(rows)
    assert tally["n_graded"] == 3
    assert tally["n_moved"] == 2
    assert tally["mean_abs_delta"] == pytest.approx((0 + 3 + 2) / 3)
    assert tally["max_abs_delta"] == 3

    move = revision.biggest_move(rows)
    assert move["team"] == "B"
    # rank_delta is rank minus hindsight_rank, so negative means the hindsight
    # surface put them LOWER: the live poll had them too high.
    assert move["direction"] == "over-rated live"


def test_a_week_with_no_hindsight_surface_tallies_to_nothing_rather_than_zero() -> None:
    """A live season's weeks have no hindsight rank at all, and 'no answer yet'
    must never render as 'moved zero places'."""
    revision = _load_script("make_revision_numbers")
    tally = revision.tally([{"team": "A", "rank": 1, "rank_delta": None}])
    assert tally["n_graded"] == 0
    assert tally["n_moved"] is None
    assert tally["mean_abs_delta"] is None


# -------------------------------------------------- the 2025 projection's calendar


def test_the_substituted_calendar_cannot_carry_a_result() -> None:
    """The safety argument for using the played season's own schedule is that the
    frame is built by NAMING seven columns, none of which is a score. If somebody
    widens that projection, this fails."""
    projection_2025 = _load_script("make_projection_2025")
    games = pl.DataFrame(
        {
            "game_id": [1, 2, 3],
            "season": [2025, 2025, 2025],
            "week": [1, 1, 1],
            "season_type": ["regular", "regular", "postseason"],
            "neutral_site": [False, True, False],
            "home_team": ["Alpha", "Bravo", "Charlie"],
            "away_team": ["Bravo", "Charlie", "Alpha"],
            "home_class": ["fbs", "fbs", "fbs"],
            "away_class": ["fbs", "ii", "fbs"],
            "home_points": [31, 17, 24],
            "away_points": [10, 20, 21],
        }
    )
    calendar = projection_2025.archived_calendar(2025, games)
    assert "home_points" not in calendar.columns
    assert "away_points" not in calendar.columns
    assert tuple(calendar.columns) == projection_2025.forward.SCHEDULE_COLUMNS
    # Regular season only, so the postseason row is gone; the D-II opponent stays
    # because its FBS host's schedule is what is being measured.
    assert sorted(calendar["game_id"].to_list()) == [1, 2]


def test_the_graded_season_is_read_from_the_config() -> None:
    """`graded_seasons` is what makes a second retrospective projection a config
    edit rather than a new script."""
    projection_2025 = _load_script("make_projection_2025")
    assert load_config()["projection"]["graded_seasons"] == [2025]
    assert projection_2025.TARGET_SEASON == 2025
    assert projection_2025.SOURCE_SEASON == 2024
    # The claim the artifact rests on: the recipe never saw the season it grades.
    # Since ADR 0014 the config list DOES contain 2024->2025 (the 2026 board is
    # entitled to it), so the guarantee moved to where it can be enforced - the
    # script derives its own transitions from its target season and refuses to
    # write if any of them reaches 2025.
    assert (2024, 2025) in projection_2025.TRANSITIONS
    legal = [(a, b) for a, b in projection_2025.TRANSITIONS if b < projection_2025.TARGET_SEASON]
    assert projection_2025._assert_walk_forward(legal)["checked"] is True
    with pytest.raises(SystemExit):
        projection_2025._assert_walk_forward([*legal, (2024, 2025)])


# ------------------------------------------------------------ the holdout record


def test_the_scoring_run_is_recorded_in_a_committed_file() -> None:
    """`out/` and `.cache/` are gitignored, so a single-shot test whose only
    record lived there would be a provenance claim nobody outside one machine
    could check. Both the run log and the metrics tree are committed."""
    log = REPO_ROOT / "demo" / "2025-holdout-run.log"
    metrics = REPO_ROOT / "demo" / "2025-holdout-metrics.json"
    assert log.exists() and metrics.exists()
    text = log.read_text(encoding="utf-8")
    assert "--unlock-holdout" in text
    assert "--seasons 2025" in text
    assert "# git:" in text and "# run at:" in text


def test_the_scorecard_stamps_the_config_that_was_scored_not_the_current_one() -> None:
    """THE BUG THIS GUARDS AGAINST SHIPPED. The scorecard stamped the config hash
    at RENDER time, so editing the config moved the hash printed beside the
    sentence "no constant was chosen after this was read" - which is exactly the
    hash a reader would use to check that sentence."""
    import json as _json

    scorecard = _json.loads(
        (REPO_ROOT / "demo" / "2025-holdout-scorecard.json").read_text(encoding="utf-8")
    )
    scored = scorecard["scored_with"]
    log = (REPO_ROOT / "demo" / "2025-holdout-run.log").read_text(encoding="utf-8")
    sha = next(
        ln.split("# git:", 1)[1].strip().split()[0]
        for ln in log.splitlines()
        if ln.startswith("# git:")
    )
    assert scored["git_sha"] == sha
    assert scored["config_sha256"] and len(scored["config_sha256"]) == 64
    # The config has moved since the run, so these must NOT be equal. If they ever
    # are, the stamp has started tracking the working tree again.
    assert scored["config_sha256"] != scorecard["rendered_with_config_hash"]


def test_the_verdict_is_the_one_the_adr_records() -> None:
    """One of five decidable criteria passes, two stay undecided, and the pass is
    MAE. If any of that changes, ADR 0012 is out of date."""
    import json as _json

    scorecard = _json.loads(
        (REPO_ROOT / "demo" / "2025-holdout-scorecard.json").read_text(encoding="utf-8")
    )
    verdict = scorecard["verdict"]
    assert verdict["passed"] is False
    assert verdict["n_decidable"] == 5
    assert verdict["passed_criteria"] == ["mae"]
    assert sorted(verdict["failed_criteria"]) == [
        "calibration",
        "rmse",
        "su_accuracy",
        "violations_vs_baselines",
    ]
    assert sorted(verdict["undecided_criteria"]) == [
        "brier_beats_all_baselines",
        "retro_vs_live_monotone",
    ]
    # The undecided pair is published with evidence and no verdict, on purpose.
    assert scorecard["brier_evidence"]["verdict"] is None
    assert scorecard["monotone_evidence"]["verdict"] is None
    assert scorecard["monotone_evidence"]["strictly_declining"] is False
