"""Which verbs the Sunday job calls, and which of them are still stubs.

This repository is an honest partial build: `cli._stub` raises
`NotImplementedError` rather than letting a command pretend to have worked. That
is the right behaviour for a person at a terminal and the wrong behaviour for an
unattended Sunday job, which would discover the gap forty minutes and 0.55 GB
into a run, after the archive sync and the fit, and report it as a failure at
the step that happened to be next rather than as the missing capability it is.

So the weekly job asks first. `cfbpoll preflight` walks the verbs the job will
actually call, reads each one's source for the `_stub(` marker, and prints the
list. It is deliberately derived from the code rather than from a hand-kept
table: the day somebody implements `cfbpoll validate`, this goes green on its
own, and nobody has to remember to delete a line.

`--required-only` is what the job runs. The optional steps (the CFBD leg, the
Postgres load) are the ones that must DEGRADE rather than fail, because a fork
gets no secrets and must still produce a ranking (ADR 0002).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

__all__ = ["Step", "WEEKLY_STEPS", "is_stub", "report"]

#: The marker `cli._stub` leaves in every unimplemented command body.
STUB_MARKER = "_stub("


@dataclass(frozen=True)
class Step:
    """One verb the weekly job calls, and what its absence would cost."""

    verb: str
    attribute: str
    required: bool
    note: str


#: The Sunday job, in the order `ops/bin/weekly.sh` runs it.
WEEKLY_STEPS: tuple[Step, ...] = (
    Step("guard", "guard", True, "the idempotency guard all three clocks share"),
    Step(
        "archive sync",
        "archive_sync",
        True,
        "the MIT archive, sha256-verified; this is the keyless leg a fork runs",
    ),
    Step(
        "ingest cfbd",
        "ingest_cfbd",
        False,
        "the private CFBD leg. Absent key must degrade to SportsDataverse, never fail",
    ),
    Step("audit-features", "audit_features", True, "no banned input reached a design matrix"),
    Step("rank", "rank", True, "fit L1-L4 and write the board"),
    Step(
        "validate",
        "validate",
        True,
        "the data-quality gate, AFTER the fit: it reads the run directory",
    ),
    Step("bootstrap", "bootstrap", True, "the 90% rank intervals"),
    Step("publish fixtures", "publish_fixtures", True, "the JSON tree the site reads"),
    Step("publish cards", "publish_cards", True, "the share cards"),
    Step(
        "publish postgres",
        "publish_postgres",
        False,
        "the serving tables. Skips cleanly when DATABASE_URL is unset",
    ),
    Step(
        "publish release",
        "publish_release",
        True,
        "the immutable release asset that is the canonical copy of a week",
    ),
)


def is_stub(func: Any) -> bool:
    """Does this command body call `cli._stub`? Read off the source, not a list."""
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):  # pragma: no cover - only for C or built-in callables
        return False
    return STUB_MARKER in source


def report(required_only: bool = False) -> list[dict[str, Any]]:
    """One row per weekly step: verb, required, implemented, note."""
    from cfbpoll import cli  # imported here: cli imports this module's CLI wrapper

    rows: list[dict[str, Any]] = []
    for step in WEEKLY_STEPS:
        if required_only and not step.required:
            continue
        func = getattr(cli, step.attribute, None)
        if func is None:
            raise AttributeError(
                f"ops.preflight names cfbpoll.cli:{step.attribute}, which does not exist. "
                "A renamed CLI function must be renamed here too, or the Sunday job "
                "checks a verb nobody calls."
            )
        rows.append(
            {
                "verb": step.verb,
                "required": step.required,
                "implemented": not is_stub(func),
                "note": step.note,
            }
        )
    return rows


def missing(required_only: bool = True) -> list[str]:
    """The verbs that would raise `NotImplementedError` if the job ran today."""
    return [row["verb"] for row in report(required_only=required_only) if not row["implemented"]]
