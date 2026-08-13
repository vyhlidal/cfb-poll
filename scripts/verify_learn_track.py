#!/usr/bin/env python
"""Run every command in `docs/learn/` in order, in a scratch clone, and report.

WHY THIS EXISTS. The learn track is written for someone who has never opened a
terminal. That reader cannot debug. A command that has rotted does not cost them
five minutes, it costs them the module, and probably the track. So the manual
gets the same treatment as every other published number in this repository:
nothing ships that a machine does not re-check.

HOW IT WORKS. Every fenced ```bash block in `docs/learn/*.md` is a command the
reader is told to type, so every one of them is executed here, in file order,
top to bottom, sharing one working directory. The workspace starts EMPTY: the
`git clone` in module 02 is what creates the clone, exactly as the reader
experiences it.

FAIL CLOSED. A ```bash block with no directive is RUN. Escaping verification
takes a deliberate, reasoned line of markdown:

    <!-- verify: skip reason="opens a GUI application" -->
    ```bash
    open out/poll.csv
    ```

A `skip` with no reason is an error. Adding an unrunnable command and forgetting
to say so fails loudly rather than quietly, which is the only arrangement that
survives a year of edits. Blocks that show OUTPUT rather than input are fenced
```text and are never executed.

Directives, all optional, on the line immediately above the fence:

    <!-- verify: run -->                     the default, stated for emphasis
    <!-- verify: run timeout=1800 -->        this block is allowed to take longer
    <!-- verify: skip reason="..." -->       excluded, with the reason on record

USAGE

    uv run python scripts/verify_learn_track.py                 # full cold run
    uv run python scripts/verify_learn_track.py --list          # what would run
    uv run python scripts/verify_learn_track.py --keep          # leave the clone
    uv run python scripts/verify_learn_track.py --module 02     # one module

A full cold run downloads ~0.55 GB and takes roughly fifteen minutes. Pass
`--archive-cache DIR` to symlink an already-downloaded archive into the fresh
clone between blocks; the sha256 verification still runs over every file, so the
check is the same one and only the download is saved. CI uses `actions/cache`
keyed on the archive lockfile instead, the same way `challenge.yml` does.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEARN_DIR = REPO_ROOT / "docs" / "learn"

#: Info strings whose blocks are commands the reader types. Anything else, and
#: in particular ```text, is prose or output and is never executed.
RUNNABLE_INFO = {"bash", "sh", "shell", "console"}

#: The marker a block prints so the next block inherits its working directory.
#: `cd` inside a block therefore behaves the way the reader experiences it.
CWD_MARKER = "__VERIFY_CWD__"

DEFAULT_TIMEOUT = 1800

_FENCE = re.compile(r"^(?P<indent>[ ]{0,3})(?P<ticks>`{3,})(?P<info>[^\n]*)$")
_DIRECTIVE = re.compile(r"^<!--\s*verify:\s*(?P<body>.*?)\s*-->$")
_REASON = re.compile(r'reason\s*=\s*"(?P<reason>[^"]*)"')
_TIMEOUT = re.compile(r"timeout\s*=\s*(?P<timeout>\d+)")


class DirectiveError(ValueError):
    """A verify directive that a human has to fix before anything can run."""


@dataclass
class Block:
    """One fenced command block, with wherever it came from attached."""

    module: str
    line: int
    info: str
    body: str
    run: bool
    reason: str
    timeout: int

    @property
    def where(self) -> str:
        return f"{self.module}:{self.line}"

    @property
    def first_line(self) -> str:
        for line in self.body.splitlines():
            if line.strip():
                return line.strip()
        return "(empty)"


def parse_directive(text: str) -> tuple[bool, str, int]:
    """Turn one `<!-- verify: ... -->` comment into (run, reason, timeout)."""
    match = _DIRECTIVE.match(text.strip())
    if match is None:
        raise DirectiveError(f"not a verify directive: {text!r}")

    body = match.group("body")
    timeout_match = _TIMEOUT.search(body)
    timeout = int(timeout_match.group("timeout")) if timeout_match else DEFAULT_TIMEOUT

    verb = body.split()[0] if body.split() else ""
    if verb == "run":
        return True, "", timeout
    if verb == "skip":
        reason_match = _REASON.search(body)
        if reason_match is None or not reason_match.group("reason").strip():
            raise DirectiveError(
                f'verify: skip needs a reason. Write: <!-- verify: skip reason="why" --> '
                f"(got {text.strip()!r})"
            )
        return False, reason_match.group("reason").strip(), timeout
    raise DirectiveError(f"unknown verify verb {verb!r} in {text.strip()!r}; use run or skip")


def parse_module(path: Path) -> list[Block]:
    """Extract every runnable block from one markdown file, in document order."""
    blocks: list[Block] = []
    lines = path.read_text(encoding="utf-8").splitlines()

    index = 0
    while index < len(lines):
        fence = _FENCE.match(lines[index])
        if fence is None:
            index += 1
            continue

        ticks = fence.group("ticks")
        info = fence.group("info").strip().lower()
        opened_at = index + 1

        # Find the closing fence of at least the same length.
        close = index + 1
        while close < len(lines):
            closer = _FENCE.match(lines[close])
            if closer is not None and closer.group("ticks").startswith(ticks) and not closer.group(
                "info"
            ).strip():
                break
            close += 1
        body = "\n".join(lines[index + 1 : close])
        index = close + 1

        if info not in RUNNABLE_INFO:
            continue

        # The directive is the nearest preceding non-blank line, if it is one.
        run, reason, timeout = True, "", DEFAULT_TIMEOUT
        look = opened_at - 2
        while look >= 0 and not lines[look].strip():
            look -= 1
        if look >= 0 and lines[look].strip().startswith("<!--") and "verify:" in lines[look]:
            try:
                run, reason, timeout = parse_directive(lines[look])
            except DirectiveError as exc:
                raise DirectiveError(f"{path.name}:{look + 1}: {exc}") from exc

        blocks.append(
            Block(
                module=path.name,
                line=opened_at,
                info=info,
                body=body,
                run=run,
                reason=reason,
                timeout=timeout,
            )
        )

    return blocks


def module_files(learn_dir: Path = LEARN_DIR) -> list[Path]:
    """Every learn-track document, in the order a reader meets them."""
    if not learn_dir.is_dir():
        raise FileNotFoundError(f"no learn track at {learn_dir}")
    numbered = sorted(p for p in learn_dir.glob("*.md") if p.name[0].isdigit())
    front = [learn_dir / "README.md"]
    back = [learn_dir / "GLOSSARY.md"]
    return [p for p in front + numbered + back if p.exists()]


def collect_blocks(learn_dir: Path = LEARN_DIR) -> list[Block]:
    """Every runnable block across the whole track, in reading order."""
    blocks: list[Block] = []
    for path in module_files(learn_dir):
        blocks.extend(parse_module(path))
    return blocks


def _seed_archive(workspace: Path, cache: Path | None) -> None:
    """Symlink an already-downloaded archive into the clone, once it exists.

    This saves the download and nothing else. `cfbpoll archive sync --verify`
    still sha256-checks every file against the committed lockfile, so the run
    verifies exactly what a cold run verifies.
    """
    if cache is None:
        return
    clone = workspace / "cfb-poll"
    target = clone / "archive" / "sportsdataverse"
    if not clone.is_dir() or target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(cache.resolve())


def run_block(block: Block, cwd: Path, env: dict[str, str]) -> tuple[int, str, Path, float]:
    """Run one block in `cwd`; return (returncode, output, next cwd, seconds)."""
    script = (
        "set -eu\n"
        f'cd "{cwd}"\n'
        f"{block.body}\n"
        f"printf '\\n{CWD_MARKER}%s\\n' \"$PWD\"\n"
    )
    started = time.monotonic()
    try:
        done = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=block.timeout,
            env=env,
        )
        code, output = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        code = 124
        output = f"{stdout}{stderr}\nTIMEOUT after {block.timeout}s"

    elapsed = time.monotonic() - started

    next_cwd = cwd
    for line in output.splitlines():
        if line.startswith(CWD_MARKER):
            candidate = Path(line[len(CWD_MARKER) :].strip())
            if candidate.is_dir():
                next_cwd = candidate
    cleaned = "\n".join(ln for ln in output.splitlines() if not ln.startswith(CWD_MARKER))
    return code, cleaned, next_cwd, elapsed


def verify(
    workspace: Path,
    learn_dir: Path = LEARN_DIR,
    only_module: str | None = None,
    archive_cache: Path | None = None,
    verbose: bool = False,
) -> int:
    """Execute the track. Returns a process exit code."""
    blocks = collect_blocks(learn_dir)
    if only_module:
        blocks = [b for b in blocks if b.module.startswith(only_module)]
        if not blocks:
            print(f"no blocks in a module matching {only_module!r}")
            return 1

    env = dict(os.environ)
    env.update(
        {
            # The same single-threaded BLAS the backtest and the challenge
            # workflow pin, for the same reason: a number that moves between
            # runs of the same code settles nothing (report 03 section 9.3).
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "PYTHONHASHSEED": "0",
            "TZ": "UTC",
            # A reader is not sitting at a prompt answering questions.
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    # A reader's shell has none of this. Running the verifier from inside this
    # repository's own activated environment would otherwise leak it into the
    # scratch clone and print warnings the manual never mentions.
    for leaked in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH"):
        env.pop(leaked, None)

    cwd = workspace
    ran = skipped = 0
    started = time.monotonic()

    for block in blocks:
        if not block.run:
            skipped += 1
            print(f"SKIP  {block.where:<44} {block.reason}", flush=True)
            continue

        # Flushed so a CI log shows which block is in flight rather than
        # nothing for fifteen minutes and then everything at once.
        print(f"  ..  {block.where:<44} {block.first_line[:52]}", flush=True)

        _seed_archive(workspace, archive_cache)
        code, output, cwd, elapsed = run_block(block, cwd, env)
        ran += 1

        if code != 0:
            print(f"FAIL  {block.where:<44} exit {code} after {elapsed:.1f}s")
            print()
            print("    The block, exactly as the reader would paste it:")
            for line in block.body.splitlines():
                print(f"      {line}")
            print()
            print("    What happened:")
            for line in output.splitlines()[-40:]:
                print(f"      {line}")
            print()
            print(
                f"{ran} blocks ran, {skipped} skipped, then "
                f"{block.module} broke. Everything after it is unverified."
            )
            return 1

        print(f"ok    {block.where:<44} {elapsed:6.1f}s  {block.first_line[:52]}", flush=True)
        if verbose:
            for line in output.splitlines():
                print(f"        {line}")

    total = time.monotonic() - started
    print()
    print(f"PASS  {ran} blocks ran, {skipped} skipped, {total / 60:.1f} minutes.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--learn-dir", type=Path, default=LEARN_DIR)
    parser.add_argument("--workspace", type=Path, default=None, help="Where the clone lands.")
    parser.add_argument("--keep", action="store_true", help="Leave the workspace behind.")
    parser.add_argument("--list", action="store_true", help="Show the plan and exit.")
    parser.add_argument("--module", default=None, help="Run one module, e.g. 02.")
    parser.add_argument(
        "--archive-cache", type=Path, default=None, help="Reuse a downloaded archive."
    )
    parser.add_argument("--verbose", action="store_true", help="Echo every block's output.")
    args = parser.parse_args(argv)

    if args.list:
        blocks = collect_blocks(args.learn_dir)
        for block in blocks:
            mark = "run " if block.run else "SKIP"
            note = block.reason if block.reason else block.first_line[:60]
            print(f"{mark}  {block.where:<44} {note}")
        runnable = sum(1 for b in blocks if b.run)
        print(f"\n{len(blocks)} command blocks, {runnable} runnable.")
        return 0

    workspace = args.workspace or Path(tempfile.mkdtemp(prefix="learn-track-"))
    workspace.mkdir(parents=True, exist_ok=True)
    print(f"workspace: {workspace}")
    print()

    try:
        return verify(
            workspace,
            learn_dir=args.learn_dir,
            only_module=args.module,
            archive_cache=args.archive_cache,
            verbose=args.verbose,
        )
    finally:
        if args.keep or args.workspace is not None:
            print(f"\nworkspace kept at {workspace}")
        else:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
