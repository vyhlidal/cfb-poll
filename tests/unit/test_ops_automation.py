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
import os
import shlex
import subprocess
from pathlib import Path

import pytest
import typer

from cfbpoll.cli import app
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


def _dry_run_commands(tmp_path: Path) -> list[list[str]]:
    """Every `cfbpoll` command the runner WOULD issue, taken from a real dry run.

    Parsing the shell script with a regex would test an approximation of the
    script. Running it in DRY_RUN mode and reading the lines it prints tests the
    thing itself, including the flags assembled at runtime into arrays.
    """
    env = {
        **os.environ,
        "DRY_RUN": "true",
        "SKIP_SYNC": "true",
        "STRICT_PREFLIGHT": "false",
        "PUBLISH": "true",
        "TRIGGER": "manual",
        "SEASON": "2026",
        "WEEK": "7",  # explicit, so the guard never calls CFBD /calendar
        "FIXTURES": str(tmp_path / "data"),
        "OUT": str(tmp_path / "out"),
        "RELEASE_STAGE": str(tmp_path / "release"),
    }
    proc = subprocess.run(
        ["bash", str(RUNNER)], env=env, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    commands = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("[dry-run] "):
            continue
        parts = shlex.split(line[len("[dry-run] ") :])
        if "cfbpoll" in parts:
            commands.append(parts[parts.index("cfbpoll") + 1 :])
    assert commands, "a dry run printed no cfbpoll commands at all"
    return commands


def test_every_flag_the_runner_passes_exists_on_the_verb_it_calls(tmp_path):
    """THE DEFECT THIS EXISTS TO CATCH is a flag that looks right and is not.

    `publish release --out out/` read as "publish the run in out/" and actually
    meant "stage the bundle into out/", where `publish fixtures --from out`
    would then read the staged bundle's poll.json as an extra run and publish a
    week nobody ranked. Nothing about that is visible until a phantom week shows
    up in the index, so it is exactly the kind of error that has to be caught
    mechanically rather than by reading.

    A verb that is still a stub is skipped rather than checked: its flags target
    the signature the built verb will have, and the runner does not invoke it
    while it is a stub. This test starts checking it on the day it is built,
    which is the day the flags first matter.
    """
    root = typer.main.get_command(app)
    for parts in _dry_run_commands(tmp_path):
        words = [p for p in parts if not p.startswith("-")]
        flags = {p.split("=")[0] for p in parts if p.startswith("--")}

        command, verb = root, []
        for word in words:
            sub = getattr(command, "commands", {}).get(word)
            if sub is None:
                break
            command, _ = sub, verb.append(word)
        assert verb, f"the runner calls `cfbpoll {' '.join(parts[:2])}`, which is not a verb"

        known = {opt for p in command.params for opt in p.opts if opt.startswith("--")}
        # Boolean typer options also accept their --no- form.
        known |= {opt.replace("--", "--no-", 1) for opt in known}
        unknown = flags - known
        assert not unknown, (
            f"`cfbpoll {' '.join(verb)}` does not accept {sorted(unknown)}. "
            f"It accepts: {sorted(known)}"
        )


def test_the_runner_never_stages_a_release_bundle_inside_the_run_directory(tmp_path):
    """The staged bundle carries a poll.json. Inside OUT, `publish fixtures`
    reads it as a run. The runner refuses rather than publishing a phantom week."""
    env = {
        **os.environ,
        "DRY_RUN": "true",
        "SKIP_SYNC": "true",
        "TRIGGER": "manual",
        "SEASON": "2026",
        "WEEK": "7",
        "OUT": str(tmp_path / "out"),
        "RELEASE_STAGE": str(tmp_path / "out" / "release"),
    }
    (tmp_path / "out").mkdir()
    proc = subprocess.run(
        ["bash", str(RUNNER)], env=env, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 2
    assert "is inside OUT" in proc.stderr


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
