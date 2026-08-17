"""The guard is the only thing standing between three clocks and two polls.

Everything here is offline. `decide()` takes a `week_resolver` seam precisely so
that the one step needing a CFBD key can be tested without one, which is also
what makes the guard runnable in a fork.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cfbpoll.ops import guard

# ------------------------------------------------------------------- the season


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        ("2026-08-30T12:00:00+00:00", 2026),  # opening weekend
        ("2026-12-07T12:00:00+00:00", 2026),  # championship weekend
        ("2027-01-12T12:00:00+00:00", 2026),  # the January title game is LAST season
        ("2027-02-01T12:00:00+00:00", 2027),  # February flips it
        ("2027-06-15T12:00:00+00:00", 2027),  # the offseason belongs to the season ahead
    ],
)
def test_current_season_puts_january_with_the_season_that_started_in_august(moment, expected):
    assert guard.current_season(datetime.fromisoformat(moment)) == expected


def test_current_season_defaults_to_now_without_raising():
    assert guard.current_season() >= 2026


# ------------------------------------------------------------------- the switch


def test_a_missing_arming_file_arms_nothing(tmp_path):
    armed = guard.load_arming(tmp_path / "nope.toml")
    assert armed.present is False
    for trigger in ("n8n", "schedule", "vps_timer"):
        assert armed.allows(trigger) is False


def test_a_human_is_never_refused_even_with_no_file(tmp_path):
    """A switch that can lock John out of his own repository is worse than the
    failure it prevents, so `manual` is special-cased rather than configured."""
    assert guard.load_arming(tmp_path / "nope.toml").allows("manual") is True


def test_an_absent_trigger_line_is_a_disarmed_trigger(tmp_path):
    path = tmp_path / "arming.toml"
    path.write_text("[triggers]\nn8n = true\n")
    armed = guard.load_arming(path)
    assert armed.allows("n8n") is True
    assert armed.allows("schedule") is False
    assert "no `schedule` line" in armed.reason("schedule")


def test_a_misspelled_trigger_is_refused_loudly(tmp_path):
    """Silently ignoring `sched = true` would leave a switch that does nothing
    and reads as if it does something."""
    path = tmp_path / "arming.toml"
    path.write_text("[triggers]\nsched = true\n")
    with pytest.raises(guard.GuardError, match="unknown trigger"):
        guard.load_arming(path)


def test_the_committed_arming_file_parses_and_names_only_known_triggers():
    armed = guard.load_arming(guard.ARMING_PATH)
    assert armed.present, f"{guard.ARMING_PATH} must exist: it is the safety catch"
    assert set(armed.triggers) <= set(guard.TRIGGERS)
    assert set(armed.steps) <= set(guard.STEPS)


# --------------------------------------------------------------- the steps table


def test_a_missing_arming_file_arms_no_step_either(tmp_path):
    armed = guard.load_arming(tmp_path / "nope.toml")
    assert armed.allows_step("delivery") is False
    assert "does not exist" in armed.step_reason("delivery")


def test_there_is_no_human_exemption_for_a_step(tmp_path):
    """`allows` waves a human through; `allows_step` waves nobody through.

    Starting a run is not the same act as deploying a public website, and being
    able to rehearse the whole job without touching the site depends on the two
    staying separate.
    """
    path = tmp_path / "arming.toml"
    path.write_text("[triggers]\nn8n = true\n\n[steps]\ndelivery = false\n")
    armed = guard.load_arming(path)
    assert armed.allows("manual") is True
    assert armed.allows_step("delivery") is False


def test_an_absent_step_line_is_a_disarmed_step(tmp_path):
    path = tmp_path / "arming.toml"
    path.write_text("[triggers]\nn8n = true\n")
    armed = guard.load_arming(path)
    assert armed.allows_step("delivery") is False
    assert "no `delivery` line" in armed.step_reason("delivery")


def test_a_misspelled_step_is_refused_loudly(tmp_path):
    path = tmp_path / "arming.toml"
    path.write_text("[steps]\ndelivry = true\n")
    with pytest.raises(guard.GuardError, match="unknown step"):
        guard.load_arming(path)


def test_asking_about_an_unknown_step_raises(tmp_path):
    armed = guard.load_arming(tmp_path / "nope.toml")
    with pytest.raises(guard.GuardError, match="unknown step"):
        armed.allows_step("deploy-everything")


def test_an_armed_step_reads_as_armed(tmp_path):
    path = tmp_path / "arming.toml"
    path.write_text("[steps]\ndelivery = true\n")
    armed = guard.load_arming(path)
    assert armed.allows_step("delivery") is True
    assert "armed" in armed.step_reason("delivery")


def test_a_step_name_is_not_a_valid_trigger():
    """`--trigger delivery` would be nonsense; the namespaces stay separate."""
    assert not set(guard.STEPS) & set(guard.TRIGGERS)
    with pytest.raises(guard.GuardError, match="unknown trigger"):
        guard.decide(trigger="delivery", season=2026, week=1, resolve_week=False)


# ---------------------------------------------------------------- already published


def _publish(root: Path, season: int, week: int) -> None:
    directory = root / str(season)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / guard.week_document_name(week)).write_text(
        json.dumps({"season": season, "week": week})
    )


def test_published_weeks_reads_the_house_tree_and_ignores_the_lenses(tmp_path):
    _publish(tmp_path, 2026, 5)
    _publish(tmp_path, 2026, 12)
    lens = tmp_path / "2026" / "recipes" / "just-win"
    lens.mkdir(parents=True)
    (lens / "week-07.json").write_text("{}")

    assert guard.published_weeks(tmp_path, 2026) == [5, 12]
    assert guard.published_weeks(tmp_path, 2025) == []
    assert guard.published_on_disk(tmp_path, 2026, 12) is True
    assert guard.published_on_disk(tmp_path, 2026, 7) is False


def test_week_document_name_matches_what_publish_fixtures_actually_writes():
    """A drift alarm, not a formatting test.

    `publish/fixtures.py` builds the filename itself; if that format string
    changes, the guard would start looking for a document nobody writes and would
    cheerfully republish every week forever.
    """
    from cfbpoll.publish import fixtures

    source = Path(fixtures.__file__).read_text(encoding="utf-8")
    assert 'f"{stem}-{bundle.week:02d}.json"' in source
    assert guard.week_document_name(7) == "week-07.json"
    assert guard.week_document_name(16) == "week-16.json"


# --------------------------------------------------------------------- the verdict


def _resolver(week: int = 9, season_type: str = "regular"):
    def resolve(season: int) -> tuple[int, str]:
        return week, season_type

    return resolve


def _armed(**flags) -> guard.Arming:
    return guard.Arming(path=Path("test"), present=True, triggers=dict(flags))


def test_a_disarmed_clock_does_not_run_even_with_everything_else_ready(tmp_path):
    decision = guard.decide(
        trigger="schedule",
        season=2026,
        week=9,
        fixtures=tmp_path,
        arming=_armed(schedule=False),
        resolve_week=False,
    )
    assert decision.armed is False
    assert decision.already_published is False
    assert decision.should_run is False
    assert any("DISARMED" in note for note in decision.notes)


def test_an_armed_clock_runs_an_unpublished_week(tmp_path):
    decision = guard.decide(
        trigger="schedule",
        season=2026,
        week=9,
        fixtures=tmp_path,
        arming=_armed(schedule=True),
        resolve_week=False,
    )
    assert decision.should_run is True
    assert decision.week_source == "input"


def test_an_already_published_week_stops_every_trigger(tmp_path):
    _publish(tmp_path, 2026, 9)
    for trigger in ("manual", "n8n", "schedule", "vps_timer"):
        decision = guard.decide(
            trigger=trigger,
            season=2026,
            week=9,
            fixtures=tmp_path,
            arming=_armed(n8n=True, schedule=True, vps_timer=True),
            resolve_week=False,
        )
        assert decision.already_published is True, trigger
        assert decision.should_run is False, trigger
        assert decision.published_where[0].startswith("disk:")


def test_the_live_week_comes_from_the_calendar_when_no_week_is_given(tmp_path):
    decision = guard.decide(
        trigger="manual",
        season=2026,
        fixtures=tmp_path,
        arming=_armed(),
        week_resolver=_resolver(week=11, season_type="postseason"),
    )
    assert (decision.week, decision.season_type) == (11, "postseason")
    assert decision.week_source == "calendar"
    assert decision.should_run is True


def test_an_unresolvable_week_is_a_no_op_and_says_why(tmp_path):
    """No CFBD key means no live week. The honest answer is "I do not know",
    never a guessed week number that would publish the wrong board."""

    def broken(season: int) -> tuple[int, str]:
        raise RuntimeError("CFBD_API_KEY is not set and no .env carries it")

    decision = guard.decide(
        trigger="n8n",
        season=2026,
        fixtures=tmp_path,
        arming=_armed(n8n=True),
        week_resolver=broken,
    )
    assert decision.week is None
    assert decision.week_source == "unresolved"
    assert decision.should_run is False
    assert any("CFBD_API_KEY" in note for note in decision.notes)


def test_no_resolve_week_never_touches_the_network(tmp_path):
    def explode(season: int) -> tuple[int, str]:  # pragma: no cover - must not run
        raise AssertionError("the resolver was called despite --no-resolve-week")

    decision = guard.decide(
        trigger="manual",
        season=2026,
        fixtures=tmp_path,
        arming=_armed(),
        resolve_week=False,
        week_resolver=explode,
    )
    assert decision.week_source == "unresolved"


def test_an_unknown_trigger_raises_rather_than_defaulting_to_allowed():
    with pytest.raises(guard.GuardError, match="unknown trigger"):
        guard.decide(trigger="cron", season=2026, week=1, arming=_armed())


def test_the_season_is_derived_when_it_is_not_given(tmp_path):
    decision = guard.decide(
        trigger="manual",
        week=3,
        fixtures=tmp_path,
        arming=_armed(),
        resolve_week=False,
        now=datetime(2027, 1, 4, tzinfo=UTC),
    )
    assert decision.season == 2026
    assert any("Feb-to-Jan convention" in note for note in decision.notes)


# ------------------------------------------------------------------ the wire format


def test_outputs_are_all_strings_because_github_actions_reads_text(tmp_path):
    decision = guard.decide(
        trigger="manual", season=2026, week=4, arming=_armed(), resolve_week=False
    )
    outputs = decision.as_outputs()
    assert all(isinstance(v, str) for v in outputs.values())
    assert outputs["should_run"] in {"true", "false"}
    assert outputs["season"] == "2026"
    assert outputs["week"] == "4"


def test_write_github_output_appends_key_value_lines(tmp_path):
    decision = guard.decide(
        trigger="manual", season=2026, week=4, arming=_armed(), resolve_week=False
    )
    target = tmp_path / "outputs.txt"
    target.write_text("pre_existing=1\n")
    guard.write_github_output(decision, target)
    lines = target.read_text().splitlines()
    assert lines[0] == "pre_existing=1"
    assert "should_run=true" in lines
    assert "season=2026" in lines


def test_write_github_output_is_a_no_op_when_unset(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    decision = guard.decide(
        trigger="manual", season=2026, week=4, arming=_armed(), resolve_week=False
    )
    assert guard.write_github_output(decision) is None


def test_as_json_carries_the_reasons_not_just_the_verdict():
    decision = guard.decide(
        trigger="schedule", season=2026, week=4, arming=_armed(schedule=False), resolve_week=False
    )
    payload = json.loads(guard.as_json(decision))
    assert payload["should_run"] == "false"
    assert payload["notes"], "a verdict with no reasons is not reviewable"
