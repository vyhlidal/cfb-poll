"""The learn track is checked mechanically, like every other published number here.

Two speeds, on purpose.

The fast tests in this file run in the ordinary suite. They are structural: the
modules exist, they link to each other, every command block carries a directive a
human can defend, and the voice rule that bans em dashes is enforced by a machine
rather than by remembering. None of them execute anything.

The slow test runs the whole track for real, in a scratch clone, and it is marked
`learn` so `pytest` skips it by default. Run it with:

    uv run pytest -m learn

or straight from the script, which prints far more:

    uv run python scripts/verify_learn_track.py

It downloads ~0.55 GB and takes roughly fifteen minutes. CI runs it on a schedule
of its own (.github/workflows/learn-track.yml), not on every push, because a
fifteen-minute job on every commit is a job people learn to ignore.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LEARN_DIR = REPO_ROOT / "docs" / "learn"
VERIFIER = REPO_ROOT / "scripts" / "verify_learn_track.py"

#: The seven modules of report 08's outline, plus the front door and the glossary.
EXPECTED_MODULES = [
    "01-what-you-are-about-to-build.md",
    "02-get-it-running.md",
    "03-read-the-poll.md",
    "04-read-the-scorecard.md",
    "05-change-one-number.md",
    "06-write-your-own-rating.md",
    "07-open-the-pull-request.md",
]

#: Section headings every module owes its reader. The shapes come from
#: XI-Marketing/brand/pedagogy-rubric.md, adapted from a screenshot-driven guide
#: to a terminal-driven one: the walkthrough segments carry command output where
#: the rubric expects screenshots, and "Coaching moves" becomes the
#: troubleshooting section, because a beginner who cannot debug needs that far
#: more than they need sample client language.
REQUIRED_SECTIONS = [
    "## Why a football fan cares",
    "## What you will be able to do",
    "## What you already have",
    "## The walkthrough",
    "## When it does not work",
    "## Try it",
    "## Check yourself",
    "## In the field",
    "## Quick reference",
]


def _load_verifier():
    spec = importlib.util.spec_from_file_location("verify_learn_track", VERIFIER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Registered before exec so the @dataclass in there can resolve its own module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify_learn_track = _load_verifier()


def test_the_track_exists_and_is_complete():
    assert LEARN_DIR.is_dir(), "docs/learn/ is missing"
    for name in ["README.md", "GLOSSARY.md", *EXPECTED_MODULES]:
        assert (LEARN_DIR / name).is_file(), f"docs/learn/{name} is missing"


def test_the_front_door_links_every_module():
    index = (LEARN_DIR / "README.md").read_text(encoding="utf-8")
    for name in EXPECTED_MODULES:
        assert name in index, f"docs/learn/README.md does not link {name}"


def test_every_module_links_the_next_one():
    """A reader who finishes a module must be told where to go."""
    for current, following in zip(EXPECTED_MODULES, EXPECTED_MODULES[1:], strict=False):
        text = (LEARN_DIR / current).read_text(encoding="utf-8")
        assert following in text, f"{current} does not point at {following}"


@pytest.mark.parametrize("name", EXPECTED_MODULES)
def test_every_module_carries_the_pedagogy_sections(name):
    text = (LEARN_DIR / name).read_text(encoding="utf-8")
    missing = [section for section in REQUIRED_SECTIONS if section not in text]
    assert not missing, f"{name} is missing: {missing}"


@pytest.mark.parametrize("path", sorted(LEARN_DIR.glob("*.md")), ids=lambda p: p.name)
def test_no_em_dashes_anywhere_in_the_manual(path):
    """The one typographic rule, enforced by a machine instead of by memory.

    Em and en dashes are banned in this manual. Restructure with a period, a
    comma or a colon.
    """
    text = path.read_text(encoding="utf-8")
    offenders = [
        (n, line)
        for n, line in enumerate(text.splitlines(), start=1)
        if "—" in line or "–" in line
    ]
    assert not offenders, f"{path.name} has dashes on lines: {[n for n, _ in offenders]}"


def test_every_command_block_parses_and_skips_are_justified():
    """Fail closed: an unmarked block runs, and a skip needs a reason on record."""
    blocks = verify_learn_track.collect_blocks(LEARN_DIR)
    assert blocks, "no command blocks found; the parser or the modules are broken"
    for block in blocks:
        if not block.run:
            assert block.reason, f"{block.where} skips verification without a reason"


def test_the_track_still_starts_from_an_empty_directory():
    """The first runnable command must be the clone. Nothing may be assumed present."""
    blocks = [b for b in verify_learn_track.collect_blocks(LEARN_DIR) if b.run]
    first = blocks[0].body
    assert "git clone" in first or "uv --version" in first, (
        f"the track's first runnable block is {blocks[0].where}, which is neither the "
        f"clone nor the uv check: {first!r}"
    )


def test_a_skip_with_no_reason_is_rejected():
    """The fail-closed rule is itself tested, because it is the whole guarantee."""
    with pytest.raises(verify_learn_track.DirectiveError):
        verify_learn_track.parse_directive("<!-- verify: skip -->")
    with pytest.raises(verify_learn_track.DirectiveError):
        verify_learn_track.parse_directive('<!-- verify: skip reason="" -->')
    with pytest.raises(verify_learn_track.DirectiveError):
        verify_learn_track.parse_directive("<!-- verify: maybe -->")

    run, reason, timeout = verify_learn_track.parse_directive("<!-- verify: run timeout=99 -->")
    assert run and not reason and timeout == 99


@pytest.mark.learn
def test_every_command_in_the_manual_actually_runs(tmp_path):
    """The real thing: the whole track, in order, in a clone with nothing set up.

    Deselected by default. `uv run pytest -m learn` to run it.
    """
    done = subprocess.run(
        [sys.executable, str(VERIFIER), "--workspace", str(tmp_path / "workspace")],
        capture_output=True,
        text=True,
        timeout=60 * 60,
    )
    sys.stdout.write(done.stdout)
    sys.stdout.write(done.stderr)
    assert done.returncode == 0, "a command in docs/learn/ no longer works"
