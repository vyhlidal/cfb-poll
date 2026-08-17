"""The Sunday automation's structural promises, as tests.

These are cheap and they guard three claims that are easy to break silently:

  * `ops/preflight.py` names real CLI functions, so the job's "which verbs are
    missing" answer cannot go stale by a rename.
  * There is exactly ONE implementation of the weekly job. ADR 0002's fallback
    only works because the GitHub runner and the VPS timer run the same file;
    two transcriptions of a publication sequence would drift, and the drift
    would be discovered on the Sunday it mattered.
  * Nothing that was delivered-but-not-installed is armed. The n8n workflows are
    shipped inactive, and the workflow's `schedule:` third string is gated on
    `cfbpoll guard`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cfbpoll.config import REPO_ROOT
from cfbpoll.ops import preflight

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "weekly.yml"
RUNNER = REPO_ROOT / "ops" / "bin" / "weekly.sh"
UNIT = REPO_ROOT / "ops" / "systemd" / "cfb-poll-weekly.service"
TIMER = REPO_ROOT / "ops" / "systemd" / "cfb-poll-weekly.timer"
N8N = sorted((REPO_ROOT / "ops" / "n8n").glob("*.json"))


# ------------------------------------------------------------------- preflight


def test_every_preflight_step_names_a_real_cli_function():
    """A rename in cli.py must not turn the readiness check into a lie."""
    rows = preflight.report(required_only=False)
    assert len(rows) == len(preflight.WEEKLY_STEPS)
    assert {row["verb"] for row in rows} == {step.verb for step in preflight.WEEKLY_STEPS}


def test_preflight_detects_a_stub_and_an_implementation():
    from cfbpoll import cli

    assert preflight.is_stub(cli.validate) is True, "cfbpoll validate is still a stub today"
    assert preflight.is_stub(cli.rank) is False, "cfbpoll rank is real"


def test_required_only_is_a_subset_of_everything():
    everything = {row["verb"] for row in preflight.report(required_only=False)}
    required = {row["verb"] for row in preflight.report(required_only=True)}
    assert required < everything
    assert "publish postgres" not in required, (
        "the Postgres load must be optional: a fork has no database and must still publish"
    )


def test_the_guard_itself_is_not_a_stub():
    """If the guard were still a stub, every clock would be unguarded."""
    assert "guard" not in preflight.missing(required_only=True)


# ----------------------------------------------------- one job, one implementation


def test_the_runner_exists_and_is_executable():
    assert RUNNER.exists()
    assert RUNNER.stat().st_mode & 0o111, "ops/bin/weekly.sh must be executable"


@pytest.mark.parametrize("path", [WORKFLOW, UNIT])
def test_both_hosts_run_the_same_weekly_script(path: Path):
    """ADR 0002: 'the identical job ... no second implementation.'"""
    assert "ops/bin/weekly.sh" in path.read_text(encoding="utf-8"), (
        f"{path.name} must invoke ops/bin/weekly.sh rather than transcribing its steps"
    )


def test_the_workflow_pins_the_runner_image():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ubuntu-24.04" in text
    assert "runs-on: ubuntu-latest" not in text, "the -latest alias moves; reproducibility cannot"


def test_the_workflow_never_cancels_a_half_written_publication():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "cancel-in-progress: false" in text


def test_the_schedule_third_string_is_gated_on_the_guard():
    """The cron is live on purpose. It is only safe because every step after the
    guard is conditional on `should_run`."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "schedule:" in text and "cron:" in text
    assert "steps.guard.outputs.should_run == 'true'" in text


def test_no_r2_credential_survives_johns_ruling():
    """ADR 0015 removed the Cloudflare leg. A stale secret reference in a
    workflow is a claim that a bucket exists."""
    for path in [WORKFLOW, RUNNER]:
        text = path.read_text(encoding="utf-8").upper()
        for needle in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
            assert needle not in text, f"{path.name} still references {needle}"


def test_the_runner_sets_single_threaded_blas_itself():
    """Every make target sets these. This script is not a make target, and a
    multi-threaded reduction sums in a nondeterministic order."""
    text = RUNNER.read_text(encoding="utf-8")
    for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        assert f"export {var}=1" in text


# ------------------------------------------------- delivered, and not installed


@pytest.mark.parametrize("path", N8N, ids=lambda p: p.name)
def test_n8n_workflows_are_shipped_inactive_and_in_eastern_time(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["active"] is False, "an imported workflow must not start itself"
    assert payload["settings"]["timezone"] == "America/New_York", (
        "the cron expressions are bare local times; the workflow timezone is what "
        "makes them Eastern, and it is what survives daylight saving"
    )


@pytest.mark.parametrize("path", N8N, ids=lambda p: p.name)
def test_every_n8n_connection_points_at_a_node_that_exists(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = {node["name"] for node in payload["nodes"]}
    for source, spec in payload["connections"].items():
        assert source in names, f"{path.name}: connection from unknown node {source!r}"
        for group in spec["main"]:
            for link in group:
                assert link["node"] in names, f"{path.name}: link to unknown node {link['node']!r}"


def test_the_dispatch_workflow_posts_to_this_repository_and_declares_its_trigger():
    payload = json.loads((REPO_ROOT / "ops" / "n8n" / "sunday-dispatch.json").read_text("utf-8"))
    http = next(n for n in payload["nodes"] if n["type"] == "n8n-nodes-base.httpRequest")
    assert http["parameters"]["url"].endswith(
        "/repos/vyhlidal/cfb-poll/actions/workflows/weekly.yml/dispatches"
    )
    body = json.loads(http["parameters"]["jsonBody"])
    assert body["inputs"]["trigger"] == "n8n", (
        "the dispatch must name itself so ops/arming.toml can refuse it independently "
        "of a human clicking Run workflow"
    )


def test_no_secret_is_committed_in_the_delivered_n8n_workflows():
    for path in N8N:
        text = path.read_text(encoding="utf-8")
        assert "REPLACE_WITH_YOUR" in text, f"{path.name} must reference a credential, not hold one"
        assert "ghp_" not in text and "github_pat_" not in text


def test_the_timer_does_not_catch_up_a_missed_run():
    """`Persistent=true` would republish at 03:00 on a Wednesday after a reboot,
    which is the launchd failure mode ADR 0002 rejected the Mac for."""
    assert "Persistent=false" in TIMER.read_text(encoding="utf-8")


def test_the_service_reads_its_secrets_from_a_file_and_holds_none():
    text = UNIT.read_text(encoding="utf-8")
    assert "EnvironmentFile=-/etc/cfb-poll/weekly.env" in text
    assert "CFBD_API_KEY=" not in text
