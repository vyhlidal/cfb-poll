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
