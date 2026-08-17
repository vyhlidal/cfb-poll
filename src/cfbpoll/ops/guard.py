"""The idempotency guard: three clocks, one job, no double publication.

ADR 0002 gives the Sunday poll three independent triggers on purpose — an n8n
dispatch from the VPS at 06:00 ET, a GitHub `schedule:` cron deliberately early,
and a systemd timer on the VPS at 08:30 ET — because the failure this project
keeps meeting is the silent one, and one clock is one silence away from a missed
week. Three clocks are only safe if all three ask the same question first, and
this module is that question.

It answers two things, and it is important that they are separate:

  * **Is this week already published?** Read off whatever evidence exists: the
    fixture tree on disk (ADR 0004 — files are truth), the published tree over
    HTTPS, and `cfb_poll_published` in Postgres. Any one of them saying yes is
    enough. None of them being *reachable* is NOT a yes, and this module says so
    rather than guessing.

  * **Is this trigger armed?** Nothing in this repository may fire on its own
    yet. `ops/arming.toml` is the switch, it is committed default-off, and every
    automatic trigger is refused until a human flips its line. A `manual`
    dispatch is always allowed, because a human at a keyboard is not a clock.

Exit code is not the channel. This module returns a decision; the caller prints
it and exits 0 either way. A guard that exits non-zero when the answer is "no,
and correctly so" turns every quiet Sunday into a red build, which is how alerts
get muted and how the dangerous silence gets built on purpose.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cfbpoll.config import REPO_ROOT

__all__ = [
    "ARMING_PATH",
    "STEPS",
    "TRIGGERS",
    "Arming",
    "Decision",
    "current_season",
    "decide",
    "load_arming",
    "published_weeks",
    "week_document_name",
]

#: The committed, default-off arming switch. One file, one line per trigger.
ARMING_PATH = REPO_ROOT / "ops" / "arming.toml"

#: Every trigger that may reach the weekly job, and which of them is a human.
#: `manual` is a person clicking "Run workflow"; the other three are clocks.
TRIGGERS: tuple[str, ...] = ("manual", "n8n", "schedule", "vps_timer")

#: A clock trigger with no line in `ops/arming.toml` is refused. Absent means no.
HUMAN_TRIGGER = "manual"

#: Steps inside the job that write somewhere OUTSIDE this repository, and so get
#: their own switch rather than riding on whichever clock happened to fire.
#:
#: `delivery` pushes the published fixture tree into the site repository, which
#: auto-deploys thepoll.ai. That is a different kind of act from "rank a week
#: into out/", and a human arming the Sunday clock has not thereby agreed to let
#: a runner write to a second repository. Kept out of TRIGGERS deliberately:
#: TRIGGERS answers "who is asking", and `--trigger delivery` would be nonsense.
STEPS: tuple[str, ...] = ("delivery",)


class GuardError(RuntimeError):
    """The guard could not be evaluated in a way the caller must not paper over."""


# --------------------------------------------------------------------- arming


@dataclass(frozen=True)
class Arming:
    """What `ops/arming.toml` says, plus where it said it.

    A missing file arms nothing. That is the correct default for a switch whose
    entire job is "do not fire yet": the failure mode of a missing config should
    never be a publication.
    """

    path: Path
    present: bool
    triggers: dict[str, bool]
    steps: dict[str, bool] = field(default_factory=dict)

    def allows(self, trigger: str) -> bool:
        if trigger == HUMAN_TRIGGER:
            return True
        return bool(self.triggers.get(trigger, False))

    def reason(self, trigger: str) -> str:
        if trigger == HUMAN_TRIGGER:
            return "manual dispatch: a human is the authority, no arming needed"
        if not self.present:
            return f"{self.path} does not exist, so no automatic trigger is armed"
        if trigger not in self.triggers:
            return (
                f"[triggers] in {self.path} has no `{trigger}` line; an absent "
                "trigger is a disarmed trigger"
            )
        state = "armed" if self.triggers[trigger] else "DISARMED"
        return f"[triggers] {trigger} = {str(self.triggers[trigger]).lower()} ({state})"

    def allows_step(self, step: str) -> bool:
        """Is a step that writes outside this repository armed?

        NOTE THE MISSING SPECIAL CASE. `allows` waves a human through, because a
        person clicking Run is not a clock. There is no equivalent here on
        purpose: `delivery` pushes to the site repository and deploys the public
        site, and "a human started the run" is not consent to publish. A manual
        rehearsal with delivery disarmed is the whole point of being able to
        rehearse.
        """
        if step not in STEPS:
            raise GuardError(f"unknown step {step!r}. Known: {list(STEPS)}")
        return bool(self.steps.get(step, False))

    def step_reason(self, step: str) -> str:
        if not self.present:
            return f"{self.path} does not exist, so no step is armed"
        if step not in self.steps:
            return (
                f"[steps] in {self.path} has no `{step}` line; an absent step is "
                "a disarmed step"
            )
        state = "armed" if self.steps[step] else "DISARMED"
        return f"[steps] {step} = {str(self.steps[step]).lower()} ({state})"


def _table(
    payload: dict[str, Any], name: str, known: tuple[str, ...], path: Path
) -> dict[str, bool]:
    raw = payload.get(name) or {}
    if not isinstance(raw, dict):
        raise GuardError(f"{path}: [{name}] must be a table, got {type(raw).__name__}")
    parsed = {str(k): bool(v) for k, v in raw.items()}
    unknown = sorted(set(parsed) - set(known))
    if unknown:
        raise GuardError(
            f"{path}: unknown {name[:-1]}(s) {unknown}. Known: {list(known)}. "
            "A misspelled name would read as disarmed forever, which is a switch "
            "that silently does nothing."
        )
    return parsed


def load_arming(path: str | Path | None = None) -> Arming:
    """Read the arming switch. Anything unreadable disarms everything."""
    p = Path(path) if path is not None else ARMING_PATH
    if not p.exists():
        return Arming(path=p, present=False, triggers={}, steps={})
    with p.open("rb") as fh:
        payload = tomllib.load(fh)
    return Arming(
        path=p,
        present=True,
        triggers=_table(payload, "triggers", TRIGGERS, p),
        steps=_table(payload, "steps", STEPS, p),
    )


# ---------------------------------------------------------------- the calendar


def current_season(now: datetime | None = None) -> int:
    """Which college football season a moment belongs to.

    **This is a convention introduced by this module, not something the pipeline
    already knew.** Nothing else in the repository derives a season from a clock:
    every other entry point takes `--season` explicitly, and `cfbd.resolve_week`
    takes a season and resolves only the WEEK inside it. So this is the smallest
    honest bridge between "it is Sunday" and "rank season Y".

    The rule: February through December belong to that calendar year; January
    belongs to the previous one, because a January bowl or playoff game is the
    tail of the season that started the previous August. February is the boundary
    rather than January because the national championship falls in January.

    A wrong answer here is loud, not quiet: the archive holds no games for a
    season that has not started, so the rank fails rather than publishing a
    plausible-looking empty board. Pass `--season` on any run where that is not
    good enough.
    """
    moment = now if now is not None else datetime.now(UTC)
    return moment.year if moment.month >= 2 else moment.year - 1


def week_document_name(week: int) -> str:
    """`week-07.json` — the published document `publish fixtures` writes.

    Zero-padded to two digits, matching `publish/fixtures.py`'s
    `f"{stem}-{bundle.week:02d}.json"`. Duplicating the format string is a drift
    hazard, so this is the one place the guard spells it and there is a test that
    pins it against a real export.
    """
    return f"week-{int(week):02d}.json"


# ------------------------------------------------------------ published or not


def published_weeks(fixtures: str | Path, season: int) -> list[int]:
    """Which weeks of `season` already exist in a fixture tree on disk.

    `<fixtures>/<season>/week-NN.json`, which is the published poll's path and
    has been since the fixture contract was written. Recipe lenses live under
    `<season>/recipes/<slug>/` and are deliberately not counted: a lens is not
    the poll, and a week whose lens published but whose poll did not is exactly
    the half-finished state the guard has to notice.
    """
    directory = Path(fixtures) / str(int(season))
    if not directory.is_dir():
        return []
    weeks: list[int] = []
    for path in sorted(directory.glob("week-*.json")):
        tail = path.stem.split("-", 1)[1]
        if tail.isdigit():
            weeks.append(int(tail))
    return sorted(weeks)


def published_on_disk(fixtures: str | Path, season: int, week: int) -> bool:
    return int(week) in published_weeks(fixtures, season)


def published_over_https(base_url: str, season: int, week: int, timeout: float = 15.0) -> bool:
    """Is `<base_url>/<season>/week-NN.json` served and parseable?

    This is the check a GitHub runner can actually make. The runner has the code
    but not the fixture tree — the published documents live in a separate data
    directory the site reads — so on CI the disk check above is always empty and
    would answer "not published" every single time. The URL check is what makes
    the guard mean anything off the VPS.

    A 404 is a clean "no". Anything else that is not a parseable document with
    the right season and week is also "no", but it raises rather than returning
    False when the server is reachable and answering nonsense, because a poll
    tree that serves malformed JSON is a fact somebody needs to hear about.
    """
    import httpx

    url = f"{base_url.rstrip('/')}/{int(season)}/{week_document_name(week)}"
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    if response.status_code == 404:
        return False
    if response.status_code >= 400:
        raise GuardError(f"HTTP {response.status_code} from {url}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise GuardError(f"{url} did not return JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise GuardError(f"{url} returned {type(payload).__name__}, expected an object")
    return True


def published_in_postgres(season: int, week: int, database_url: str | None = None) -> bool | None:
    """Is there a `cfb_poll_published` row for this week? `None` when unconfigured.

    `None` is not `False` and the caller must keep them apart. A fork has no
    database and must still publish; a run that cannot reach the database has not
    learned that the week is unpublished, it has learned nothing.
    """
    url = database_url or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not url:
        return None
    import psycopg

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM cfb_poll_published WHERE season = %s AND week = %s LIMIT 1",
            (int(season), int(week)),
        )
        return cur.fetchone() is not None


# ------------------------------------------------------------------- the verdict


@dataclass(frozen=True)
class Decision:
    """Everything the caller needs, and nothing it has to recompute."""

    trigger: str
    season: int | None
    week: int | None
    season_type: str
    week_source: str  # "input" | "calendar" | "unresolved"
    armed: bool
    already_published: bool
    published_where: tuple[str, ...]
    should_run: bool
    notes: tuple[str, ...]

    def as_outputs(self) -> dict[str, str]:
        """The `key=value` pairs a GitHub Actions step reads back."""
        return {
            "trigger": self.trigger,
            "season": "" if self.season is None else str(self.season),
            "week": "" if self.week is None else str(self.week),
            "season_type": self.season_type,
            "week_source": self.week_source,
            "armed": "true" if self.armed else "false",
            "already_published": "true" if self.already_published else "false",
            "published_where": ",".join(self.published_where),
            "should_run": "true" if self.should_run else "false",
        }


def resolve_week_from_cfbd(season: int) -> tuple[int, str]:
    """The live week, from CFBD `/calendar`. Costs one call and needs the key.

    Wrapped rather than called directly so the one place in the automation that
    needs a secret is named, importable and mockable. `cfbd.resolve_week` does
    the work; this adds nothing but a seam.
    """
    from cfbpoll.ingest import cfbd

    return cfbd.resolve_week(int(season))


def decide(
    *,
    trigger: str = HUMAN_TRIGGER,
    season: int | str | None = None,
    week: int | str | None = None,
    fixtures: str | Path | None = None,
    published_url: str | None = None,
    database_url: str | None = None,
    arming: Arming | None = None,
    resolve_week: bool = True,
    now: datetime | None = None,
    week_resolver: Any = None,
) -> Decision:
    """Should the weekly job run, and why or why not.

    Never raises for the ordinary "no". The three ways to get a `False` — a
    disarmed trigger, an unresolvable week, an already-published week — are all
    normal Sunday outcomes and all carry a note saying which one happened.
    """
    if trigger not in TRIGGERS:
        raise GuardError(f"unknown trigger {trigger!r}. Known: {list(TRIGGERS)}")

    notes: list[str] = []
    switch = arming if arming is not None else load_arming()
    armed = switch.allows(trigger)
    notes.append(switch.reason(trigger))

    resolved_season = int(season) if season not in (None, "") else current_season(now)
    if season in (None, ""):
        notes.append(
            f"season not given; using {resolved_season} by the Feb-to-Jan convention "
            "in ops.guard.current_season"
        )

    season_type = "regular"
    resolved_week: int | None
    if week not in (None, ""):
        resolved_week = int(week)  # type: ignore[arg-type]
        week_source = "input"
    elif not resolve_week:
        resolved_week, week_source = None, "unresolved"
        notes.append("--no-resolve-week: the live week was not looked up")
    else:
        resolver = week_resolver or resolve_week_from_cfbd
        try:
            resolved_week, season_type = resolver(resolved_season)
            week_source = "calendar"
            notes.append(
                f"live week {resolved_week} ({season_type}) resolved from CFBD /calendar: "
                "one API call, and the ONLY step in this job that requires the key"
            )
        except Exception as exc:  # noqa: BLE001 - any failure here means "we do not know"
            resolved_week, week_source = None, "unresolved"
            notes.append(
                f"could not resolve the live week: {type(exc).__name__}: {exc}. "
                "Pass --week explicitly, or give the job a CFBD key."
            )

    where: list[str] = []
    if resolved_week is not None:
        if fixtures is not None:
            if published_on_disk(fixtures, resolved_season, resolved_week):
                where.append(f"disk:{fixtures}")
            else:
                notes.append(
                    f"no {week_document_name(resolved_week)} under "
                    f"{Path(fixtures) / str(resolved_season)}"
                )
        if published_url:
            try:
                if published_over_https(published_url, resolved_season, resolved_week):
                    where.append(f"https:{published_url}")
            except Exception as exc:  # noqa: BLE001 - unreachable is not "unpublished"
                notes.append(f"published-url check inconclusive: {type(exc).__name__}: {exc}")
        state = None
        try:
            state = published_in_postgres(resolved_season, resolved_week, database_url)
        except Exception as exc:  # noqa: BLE001 - same posture as the URL check
            notes.append(f"postgres check inconclusive: {type(exc).__name__}: {exc}")
        if state is None:
            notes.append("no DATABASE_URL: skipped the cfb_poll_published check")
        elif state:
            where.append("postgres:cfb_poll_published")

    already = bool(where)
    if already:
        notes.append(f"week {resolved_week} of {resolved_season} is already published")

    should_run = armed and resolved_week is not None and not already
    return Decision(
        trigger=trigger,
        season=resolved_season,
        week=resolved_week,
        season_type=season_type,
        week_source=week_source,
        armed=armed,
        already_published=already,
        published_where=tuple(where),
        should_run=should_run,
        notes=tuple(notes),
    )


def write_github_output(decision: Decision, path: str | Path | None = None) -> Path | None:
    """Append the decision to `$GITHUB_OUTPUT`, or nowhere when it is unset."""
    target = path if path is not None else os.environ.get("GITHUB_OUTPUT")
    if not target:
        return None
    destination = Path(target)
    with destination.open("a", encoding="utf-8") as fh:
        for key, value in decision.as_outputs().items():
            fh.write(f"{key}={value}\n")
    return destination


def as_json(decision: Decision) -> str:
    payload: dict[str, Any] = dict(decision.as_outputs())
    payload["notes"] = list(decision.notes)
    return json.dumps(payload, indent=2, sort_keys=True)
