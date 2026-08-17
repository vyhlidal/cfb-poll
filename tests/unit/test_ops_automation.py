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

    assert preflight.is_stub(cli.canonicalize) is True, "cfbpoll canonicalize is still a stub today"
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
def test_n8n_workflows_are_shipped_inactive_and_in_pacific_time(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["active"] is False, "an imported workflow must not start itself"
    assert payload["settings"]["timezone"] == "America/Los_Angeles", (
        "the cron expressions are bare local times; the workflow timezone is what "
        "makes them Pacific, and it is what survives daylight saving"
    )


@pytest.mark.parametrize("path", N8N, ids=lambda p: p.name)
def test_every_n8n_clock_fires_on_tuesday(path: Path):
    """THE DEFECT THIS EXISTS TO CATCH is the one John caught by hand.

    Week 1 of the 2026 FBS season does not end until SMU finishes at Florida
    State on Labor Day MONDAY, and most other weeks do not end until a Hawai'i
    nightcap that kicks 20:59 PT. A Sunday clock published a week before the
    week was over, silently, and the guard then marked it published. The day of
    week is the whole fix, so it is pinned rather than left to a comment.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    crons = [
        interval["expression"]
        for node in payload["nodes"]
        if node["type"] == "n8n-nodes-base.scheduleTrigger"
        for interval in node["parameters"]["rule"]["interval"]
        if interval.get("field") == "cronExpression"
    ]
    assert crons, f"{path.name} has no schedule trigger with a cron expression"
    for expression in crons:
        assert expression.split()[-1] == "2", (
            f"{path.name}: {expression!r} does not fire on Tuesday (day-of-week 2). "
            "See docs/runbooks/sunday-automation.md for the schedule evidence."
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


def test_the_timer_fires_on_tuesday_in_pacific_time():
    """Same defect as the n8n clocks, on the other host. The timezone suffix is
    the point: a hardcoded UTC hour is an hour wrong for half of every season."""
    assert "OnCalendar=Tue *-*-* 08:30:00 America/Los_Angeles" in TIMER.read_text(
        encoding="utf-8"
    )


def test_the_github_third_string_fires_on_tuesday():
    """GitHub cron is UTC and has no timezone field, so the day of week is the
    only thing pinnable here. 11:43 UTC is 04:43 PDT, deliberately early."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'cron: "43 11 * 8-12,1 TUE"' in text


def test_the_service_reads_its_secrets_from_a_file_and_holds_none():
    text = UNIT.read_text(encoding="utf-8")
    assert "EnvironmentFile=-/etc/cfb-poll/weekly.env" in text
    assert "CFBD_API_KEY=" not in text


# ------------------------------------------------------------------- delivery

DELIVER = REPO_ROOT / "ops" / "bin" / "deliver-fixtures.sh"


def test_the_delivery_script_exists_and_is_executable():
    assert DELIVER.exists()
    assert DELIVER.stat().st_mode & 0o111


def test_delivery_is_disarmed_in_the_committed_switch():
    """The one `true` in this repository that would deploy a public website."""
    from cfbpoll.ops import guard

    assert guard.load_arming(guard.ARMING_PATH).allows_step("delivery") is False


def test_a_disarmed_delivery_prints_no_path_and_exits_zero(tmp_path):
    """weekly.sh reads `prepare`'s stdout as a directory. Disarmed, it must be
    empty, so the caller falls back to its own FIXTURES rather than publishing
    into a path named after a log line."""
    proc = subprocess.run(
        ["bash", str(DELIVER), "prepare"],
        env={**os.environ, "SANDBOX_CONTENTS_PAT": "unused", "DELIVERY_CLONE": str(tmp_path / "c")},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
    assert "DISARMED" in proc.stderr


def test_a_missing_credential_skips_rather_than_fails(tmp_path):
    """Same posture DATABASE_URL gets: a fork runs the whole job and delivers
    nothing, instead of failing at the last step."""
    env = {k: v for k, v in os.environ.items() if k != "SANDBOX_CONTENTS_PAT"}
    arming = tmp_path / "arming.toml"
    arming.write_text("[steps]\ndelivery = true\n")
    proc = subprocess.run(
        ["bash", str(DELIVER), "prepare"],
        env={**env, "ARMING_FILE": str(arming), "DELIVERY_CLONE": str(tmp_path / "c")},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
    assert "SANDBOX_CONTENTS_PAT is not set" in proc.stderr


def test_the_delivery_script_never_sweeps_the_site_repo_or_embeds_a_token():
    text = DELIVER.read_text(encoding="utf-8")
    # Comments are stripped first: the script explains WHY it does not sweep the
    # site repo, and the explanation naturally contains the thing it refuses.
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert "git add -A" not in code and "add --all" not in code, (
        "the site repo is somebody else's working tree; stage by explicit pathspec"
    )
    # A tokenised remote URL persists in .git/config. GIT_ASKPASS does not.
    assert "GIT_ASKPASS" in text
    assert "@github.com" not in text, "no credential-in-URL remote"
    assert "GIT_TERMINAL_PROMPT=0" in text, "must never hang waiting for a human"


def _stand_in_remote(tmp_path: Path) -> Path:
    """A bare repo with a fixture tree in it, standing in for vyhlidal/sandbox."""
    remote = tmp_path / "sandbox.git"
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "--quiet", "--bare", str(remote)], check=True)
    subprocess.run(["git", "clone", "--quiet", str(remote), str(seed)], check=True)
    data = seed / "cfb-poll-data" / "2023"
    data.mkdir(parents=True)
    (data / "week-05.json").write_text('{"season": 2023, "week": 5}\n')
    (seed / "cfb-poll-data" / "index.json").write_text('{"seasons": [{"season": 2023}]}\n')
    git = ["git", "-C", str(seed), "-c", "user.email=a@b", "-c", "user.name=seed"]
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "--quiet", "-m", "the site"], check=True)
    subprocess.run(["git", "-C", str(seed), "branch", "-M", "main"], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "--quiet", "origin", "main"], check=True)
    return remote


def _deliver_env(tmp_path: Path, remote: Path) -> dict[str, str]:
    arming = tmp_path / "arming.toml"
    arming.write_text("[steps]\ndelivery = true\n")
    return {
        **os.environ,
        "ARMING_FILE": str(arming),
        "SANDBOX_REMOTE": str(remote),
        "SANDBOX_CONTENTS_PAT": "local-stand-in-no-auth-needed",
        "DELIVERY_CLONE": str(tmp_path / "clone"),
        "SEASON": "2023",
        "WEEK": "6",
        "SEASON_TYPE": "regular",
        "GITHUB_SHA": "0123456789abcdef0123456789abcdef01234567",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "vyhlidal/cfb-poll",
        "GITHUB_RUN_ID": "424242",
    }


def _head(remote: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(remote), "rev-parse", "main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_delivery_carries_provenance_and_is_idempotent(tmp_path):
    """The two properties the site's history depends on, end to end.

    A stand-in remote rather than a mock, because the failure modes that matter
    here are git's: what gets staged, whether an unchanged tree still produces a
    commit, and whether a second run leaves a trace.
    """
    remote = _stand_in_remote(tmp_path)
    env = _deliver_env(tmp_path, remote)
    before = _head(remote)

    prepare = subprocess.run(
        ["bash", str(DELIVER), "prepare"], env=env, capture_output=True, text=True, timeout=300
    )
    assert prepare.returncode == 0, prepare.stderr
    target = Path(prepare.stdout.strip())
    assert target.is_dir()
    # The clone carries the season already on the site: this is what stops
    # `publish fixtures` rebuilding an index that names one week.
    assert (target / "2023" / "week-05.json").exists()

    # Cloning and writing locally must not move the remote.
    assert _head(remote) == before, "prepare touched the remote"

    (target / "2023" / "week-06.json").write_text('{"season": 2023, "week": 6}\n')

    push = subprocess.run(
        ["bash", str(DELIVER), "push"], env=env, capture_output=True, text=True, timeout=300
    )
    assert push.returncode == 0, push.stderr
    after = _head(remote)
    assert after != before, "the week was never delivered"

    message = subprocess.run(
        ["git", "-C", str(remote), "log", "-1", "--format=%B", "main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "2023" in message and "week 06" in message, "the week is not named"
    assert env["GITHUB_SHA"] in message, "the model sha is not named"
    assert f"actions/runs/{env['GITHUB_RUN_ID']}" in message, "the run URL is not named"

    # Re-deliver the identical tree: no commit, no push, no trace.
    subprocess.run(["rm", "-rf", env["DELIVERY_CLONE"]], check=True)
    again = subprocess.run(
        ["bash", str(DELIVER), "prepare"], env=env, capture_output=True, text=True, timeout=300
    )
    assert again.returncode == 0, again.stderr
    repeat = subprocess.run(
        ["bash", str(DELIVER), "push"], env=env, capture_output=True, text=True, timeout=300
    )
    assert repeat.returncode == 0, repeat.stderr
    assert _head(remote) == after, "a re-run added an empty commit to the site's history"
    assert "nothing to push" in repeat.stderr


def test_the_site_pat_is_scoped_to_the_delivery_steps_only():
    """The compute step runs the model and every wheel in uv.lock. It has no
    business holding a credential that can write to the website.

    Text rather than a YAML parse, because pyyaml is not a dependency of this
    project and adding one so a test can read a file the rest of the suite reads
    as text would be a poor trade. Steps begin at a known indent, which is
    enough to attribute an `env:` entry to the step that owns it.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    head, _, body = text.partition("\n    steps:\n")
    assert body, "could not find the job's steps block"
    assert "SANDBOX_CONTENTS_PAT" not in head, "the PAT must not be job-wide env"

    blocks = body.split("\n      - ")
    holders = []
    for block in blocks:
        if "SANDBOX_CONTENTS_PAT" not in block:
            continue
        first = block.strip().splitlines()[0]
        holders.append(first)
    assert holders, "no step can deliver"
    for first in holders:
        assert "Delivery" in first, f"a non-delivery step holds the site PAT: {first}"

    assert text.index("name: Run the weekly job") < text.index(
        "name: Delivery - push to the site repo"
    ), "the push must come after the job that runs the gate"
