"""Real tests. These pass today.

They assert two things about the scaffold that actually matter:
  1. the package imports and the CLI surface is complete and matches the workflows
  2. every stub FAILS LOUDLY rather than silently pretending to have worked
"""

from __future__ import annotations

import typer
from typer.testing import CliRunner

from cfbpoll.cli import app

runner = CliRunner()

# Every verb invoked by .github/workflows/weekly.yml and reproducibility.yml,
# plus the Makefile. If a workflow calls something not in this set, or this set
# grows a verb no workflow or doc mentions, they have drifted apart.
EXPECTED_COMMANDS = {
    "ingest",
    "archive",
    "validate",
    "audit-features",
    "rank",
    "grid",
    "bootstrap",
    "guard",
    "canonicalize",
    "publish",
    "site",
}


def test_help_runs() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "rank" in result.output


def test_expected_commands_are_registered() -> None:
    command = typer.main.get_command(app)
    registered = set(command.commands)  # type: ignore[attr-defined]
    missing = EXPECTED_COMMANDS - registered
    assert not missing, f"CLI is missing commands the workflows call: {sorted(missing)}"


def test_subcommand_help_runs() -> None:
    for group, sub in (("ingest", "cfbd"), ("archive", "sync"), ("publish", "release")):
        result = runner.invoke(app, [group, sub, "--help"])
        assert result.exit_code == 0, f"{group} {sub} --help failed"


def test_stubs_fail_loudly() -> None:
    """A stub must raise, not return quietly. No fabricated capabilities.

    THE CANARY HAS MOVED TWICE, and both times because the thing it was watching
    got built: first `rank`, then `bootstrap` (the parametric intervals, 2026-08
    -12). It is now `guard`, which belongs to the publication plumbing and
    genuinely does not exist. When that is built, move it again rather than
    deleting the test - the property under test is that this repository never
    pretends, and it needs a live subject."""
    result = runner.invoke(app, ["guard"])
    assert result.exit_code != 0
    assert isinstance(result.exception, NotImplementedError)


def test_bootstrap_is_no_longer_a_stub() -> None:
    """It raised NotImplementedError until 2026-08-12 while
    `[publication].publish_rank_intervals` said "every week, forever" and
    weekly.yml called it. Now it runs, and it runs the PARAMETRIC scheme on the
    fixed schedule rather than the invalid resample-with-replacement the scaffold
    specified (docs/analysis/fresh-eyes-review.md, S3)."""
    result = runner.invoke(app, ["bootstrap", "--help"])
    assert result.exit_code == 0
    assert "PARAMETRIC ON THE FIXED SCHEDULE" in result.output
    assert runner.invoke(app, ["bootstrap"]).exit_code != 0  # --season is required


def test_rank_requires_a_season_until_the_calendar_resolver_exists() -> None:
    result = runner.invoke(app, ["rank"])
    assert result.exit_code != 0
    assert "--season is required" in result.output


def test_grid_requires_a_season() -> None:
    result = runner.invoke(app, ["grid"])
    assert result.exit_code != 0
    assert "--season is required" in result.output


def test_publish_fixtures_runs_end_to_end_through_the_cli(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The layer nothing covered, which is why the defect shipped.

    Every fixtures test called `fixtures.export(...)` directly and every command
    run in anger passed an explicit `--from`. So the CLI's own argument handling —
    the thing an operator actually types — had no coverage at all, and the failure
    it produced on a stale default `--from out` reached the terminal as a polars
    ColumnNotFoundError six frames deep.
    """
    import json
    from pathlib import Path

    import polars as pl

    from tests.unit.test_publish_serving import _row  # the shared row builder

    run = tmp_path / "runs" / "w02"
    run.mkdir(parents=True)
    ranking = [_row(1, "Ohio State"), _row(2, "Alabama", power=20.0, gap=40.0)]
    (run / "poll.json").write_text(
        json.dumps(
            {
                "season": 2023,
                "through": {"season_type": "regular", "week": 2},
                "provisional": False,
                "provisional_label": None,
                "ranking": ranking,
                "top25": ranking,
            }
        )
    )
    (run / "model_params.json").write_text(json.dumps({"season": 2023, "q_ref": 14.26}))
    (run / "_run.json").write_text(
        json.dumps({"season": 2023, "through_week": 2, "git_sha": "abc", "config_hash": "d"})
    )
    pl.DataFrame(
        {"team": ["Ohio State", "Alabama"], "power": [28.1, 20.0], "resume": [60.0, 55.0]}
    ).write_parquet(run / "ratings_live.parquet")

    dest = tmp_path / "site-data"
    result = runner.invoke(
        app, ["publish", "fixtures", "--from", str(tmp_path / "runs"), "--out", str(dest)]
    )
    assert result.exit_code == 0, result.output
    assert "1 runs" not in result.output  # one run takes the single-run path

    written = Path(dest) / "2023" / "week-02.json"
    assert written.exists()
    poll = json.loads(written.read_text())["poll"]
    assert poll, "the published document must carry rows"
    for row in poll:
        assert row.get("mark_bg") and row.get("mark_fg") and row.get("mark_label")


def test_publish_fixtures_reports_a_stale_run_directory_clearly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A pre-L3 `out/` must produce an instruction, not a polars traceback."""
    import json

    import polars as pl

    from cfbpoll.publish.serving import StaleRunError

    run = tmp_path / "out"
    run.mkdir()
    (run / "poll.json").write_text(
        json.dumps(
            {
                "season": 2023,
                "through": {"season_type": "regular", "week": 10},
                "ranking": [],
                "top25": [],
            }
        )
    )
    (run / "model_params.json").write_text("{}")
    (run / "_run.json").write_text(json.dumps({"season": 2023, "through_week": 10}))
    pl.DataFrame({"team": ["Ohio State"], "rating": [28.1]}).write_parquet(
        run / "ratings_live.parquet"
    )

    result = runner.invoke(
        app, ["publish", "fixtures", "--from", str(run), "--out", str(tmp_path / "d")]
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, StaleRunError)
    assert "cfbpoll rank" in str(result.exception)
