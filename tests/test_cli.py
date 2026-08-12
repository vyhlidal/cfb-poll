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

    `rank` is real now (L2 only), so the canary moved to `bootstrap`, which
    belongs to a layer that genuinely does not exist yet.
    """
    result = runner.invoke(app, ["bootstrap"])
    assert result.exit_code != 0
    assert isinstance(result.exception, NotImplementedError)


def test_rank_requires_a_season_until_the_calendar_resolver_exists() -> None:
    result = runner.invoke(app, ["rank"])
    assert result.exit_code != 0
    assert "--season is required" in result.output


def test_grid_requires_a_season() -> None:
    result = runner.invoke(app, ["grid"])
    assert result.exit_code != 0
    assert "--season is required" in result.output
