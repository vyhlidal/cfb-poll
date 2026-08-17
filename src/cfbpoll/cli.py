"""The `cfbpoll` command line interface.

Specified by research report 03 §4.6 (the weekly workflow), §9.1 (the one-command
fork story) and §9.2 (the byte-match replay job). Every verb invoked by
.github/workflows/weekly.yml and .github/workflows/reproducibility.yml is defined
here, so that the workflows are a readable specification of the pipeline even
before the pipeline exists.

STATUS: PARTIAL. `rank`, `grid`, `backtest`, `audit-features`, `validate` and the
publish targets (`publish release`, `publish postgres`, `publish fixtures`) are
real and run offline against the local MIT archive - `publish release` needs the
network only for the upload leg, and `--dry-run` builds the identical bundle
without it. `rank` publishes the schedule-odds ordering as the
headline (ADR 0005), with opponent quality from the L3 blend of L1 efficiency and
L2 results (`[resume].power_source`); a season with no play archive falls back to
L2 and says so on every artifact. `rank` runs the feature audit BEFORE it fits
anything, so no poll is published from a fit that was not audited (report 02
§3.10). The remaining verbs are still stubs that raise NotImplementedError when
invoked - `--help` is accurate about what each verb WILL do, and no command
silently pretends to have worked.

Season/week options are typed as strings rather than integers on purpose: GitHub
Actions passes an empty string for an omitted workflow input, and blank means
"resolve the current week from the CFBD /calendar endpoint" (report 01 §3.7).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

__all__ = ["app"]

_EPILOG = "Docs: docs/methodology.md - Constraints: docs/constraints.md - License: MIT"


def _repo_scripts(name: str) -> Any:
    """Import a module from the repository's `scripts/` directory, by name.

    THIS EXISTS BECAUSE `make projection-fixture` DID NOT RUN, EVER, from a clean
    checkout. Three commands here call into `scripts/`, and a bare
    `from scripts import make_projection` only resolves when the working directory
    happens to be on `sys.path`. It is when you run `python scripts/foo.py` or
    `python -c`; it is NOT when you run the installed console script, because
    `sys.path[0]` is then the venv's `bin` directory. Two of the three targets
    call the script file directly and worked, `projection-fixture` goes through
    the CLI verb, and it raised `ModuleNotFoundError: No module named 'scripts'`
    on the day it was written. The one target whose whole purpose is to stop the
    published board going stale was the one target that could not run.

    `REPO_ROOT` is the package's own parent, so this works from a clone however it
    was invoked and fails honestly from an installed wheel, where `scripts/` is
    genuinely not shipped.
    """
    import importlib
    import sys

    from cfbpoll.config import REPO_ROOT

    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        return importlib.import_module(f"scripts.{name}")
    except ModuleNotFoundError as exc:  # pragma: no cover - installed-wheel path
        raise ModuleNotFoundError(
            f"could not import scripts/{name}.py from {root}. This command reads the "
            "repository's own scripts/ directory, so it needs a clone rather than an "
            "installed wheel. Run it from the repository root."
        ) from exc

app = typer.Typer(
    name="cfbpoll",
    help=(
        "An open, bias-free college football ranking. "
        "PARTIAL BUILD: `rank`, `grid`, `backtest`, `audit-features`, `validate` and "
        "`publish` work. The headline poll is the schedule-odds ordering; opponent "
        "quality is the L3 blend of L1 efficiency and L2 results, and the resume is "
        "published beside every team. The remaining commands are stubs and raise "
        "NotImplementedError."
    ),
    epilog=_EPILOG,
    no_args_is_help=True,
    add_completion=False,
)

ingest_app = typer.Typer(
    name="ingest",
    help="Pull a season or week from a source into the append-only raw archive.",
    no_args_is_help=True,
)
archive_app = typer.Typer(
    name="archive",
    help="Manage the content-addressed raw archive (report 01 §5.4).",
    no_args_is_help=True,
)
publish_app = typer.Typer(
    name="publish",
    help="Publish out/ to its destinations. Files are canonical; Postgres is a cache.",
    no_args_is_help=True,
)
site_app = typer.Typer(
    name="site",
    help="Build the zero-account static site from out/ (report 03 §7.1).",
    no_args_is_help=True,
)
challenge_app = typer.Typer(
    name="challenge",
    help="Score a community entry through the identical harness (report 03 §7.3).",
    no_args_is_help=True,
)
projection_app = typer.Typer(
    name="projection",
    help=(
        "THE PROJECTION - a labelled prediction, and NEVER the poll. A preseason "
        "ranking from last season's fitted ratings plus the offseason, published "
        "to be graded in public by the poll it may not touch (ADR 0010)."
    ),
    no_args_is_help=True,
)

app.add_typer(ingest_app)
app.add_typer(archive_app)
app.add_typer(publish_app)
app.add_typer(site_app)
app.add_typer(challenge_app)
app.add_typer(projection_app)


#: Headline ordering -> (the column that sorted the table, its terminal header,
#: the one sentence that says what the key MEANS). The rank key is the single most
#: important thing a run has to be able to state about itself, and two of the
#: three recipes rank on something other than the schedule odds, so it is looked
#: up rather than assumed (ADR 0011). `publish/poll.ORDER_KEYS` is the authority
#: on the sort itself; this is only how a human is told about it.
_HEADLINE_KEY: dict[str, tuple[str, str, str]] = {
    "schedule_odds": (
        "odds_key",
        "-log10P",
        "-log10 P(W >= W_t): how improbable this record was against this exact schedule",
    ),
    "L4_resume": (
        "resume",
        "resume",
        "the wins-based resume: what quality of team these WINS imply, margin excluded",
    ),
    "L4_resume_margin": (
        "resume_margin",
        "r-margin",
        "the margin-aware resume: what quality of team these SCORES imply, margin included",
    ),
}


def _stub(what: str, spec: str) -> None:
    """Fail loudly and honestly. No command may silently pretend to have worked."""
    raise NotImplementedError(
        f"{what} is not implemented yet. This repository is a scaffold. "
        f"Specified by {spec}. See docs/methodology.md for the build order."
    )


def _parse_seasons(spec: str) -> list[int]:
    """'2021-2023' or '2021,2022' -> [2021, 2022, 2023]. Sorted, deduplicated."""
    out: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo, hi = (int(x) for x in chunk.split("-", 1))
            out.update(range(lo, hi + 1))
        else:
            out.add(int(chunk))
    if not out:
        raise typer.BadParameter(f"no seasons parsed from {spec!r}")
    return sorted(out)


def _game_sources(frame: Any) -> dict[str, int]:
    """`{'sportsdataverse': 730, 'cfbd': 38}` — provenance for the run record.

    Published because a fork's answer legitimately differs from ours for 2021 and
    2022: `archive/cfbd/` is private under CFBD terms §3, so a stranger's frame is
    the MIT parquet alone and their hindsight surface stops at conference
    championship weekend. A run that cannot say which archives it read cannot
    explain that difference, and an unexplained difference in a reproducibility
    claim is worse than a documented one.
    """
    if "source" not in frame.columns:
        return {}
    counts = frame.group_by("source").len().sort("source")
    return {str(k): int(v) for k, v in zip(counts["source"], counts["len"], strict=True)}


def _sha256_or_none(path: Path) -> str | None:
    """sha256 of a file for the run record, or None when it is not there."""
    import hashlib

    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _archive_identity(archive_root: Path) -> str | None:
    """What the run actually read, as one digest, for `_run.json`.

    Two provenances, one field. A machine that ran the backfill has the archive's
    own `_manifest.json`; a fork has no manifest at all, because `archive sync`
    materialises files from the committed LOCKFILE. Reporting `None` for the fork
    - which is what happened - means the artifact that is supposed to prove which
    bytes produced a ranking is silent on exactly the run where a stranger most
    needs it. Prefer the manifest, fall back to the lock, and say which.
    """
    manifest = _sha256_or_none(archive_root / "_manifest.json")
    if manifest is not None:
        return f"manifest:{manifest}"
    lock = _sha256_or_none(Path("data/manifests/sportsdataverse.lock.json"))
    return f"lock:{lock}" if lock is not None else None


def _plays_if_needed(cfg: dict, seasons: list[int]) -> Any:
    """The play archive, when opponent quality is L3 and the files are there.

    Returns None otherwise, and every downstream layer falls back to L2 and says
    so on the artifact. A missing play file is a degraded run, not a failed one:
    a Power rating from the results core is a real answer.
    """
    if str(cfg["resume"]["power_source"]).upper() != "L3":
        return None
    from cfbpoll.ingest.plays import DEFAULT_ARCHIVE as PLAY_ARCHIVE
    from cfbpoll.ingest.plays import load_plays

    if not all((PLAY_ARCHIVE / "pbp" / f"play_by_play_{s}.parquet").exists() for s in seasons):
        typer.echo(
            "note: play-by-play parquet missing for one or more seasons; "
            "Power falls back to L2 and every artifact will say so."
        )
        return None
    return load_plays(seasons)


# --------------------------------------------------------------------------- ingest


@ingest_app.command("cfbd")
def ingest_cfbd(
    season: Annotated[str | None, typer.Option(help="Season; blank = current.")] = None,
    week: Annotated[str | None, typer.Option(help="Week; blank = from /calendar.")] = None,
    postseason: Annotated[
        bool, typer.Option(help="Pull the season's postseason /games instead of a week.")
    ] = False,
    teams: Annotated[
        bool, typer.Option(help="Pull /teams/fbs for the season (colors, ids, conference).")
    ] = False,
    ratings: Annotated[
        str | None,
        typer.Option(help="Pull /ratings/{sp,srs,elo,fpi,core}. BENCHMARK ONLY, never an input."),
    ] = None,
    seasons: Annotated[
        str | None, typer.Option(help="Seasons for --ratings, e.g. '2021-2024'.")
    ] = None,
    abort_if_remaining_calls_below: Annotated[
        int, typer.Option(help="Quota guard: abort before spending the last N monthly calls.")
    ] = 200,
    archive_root: Annotated[
        Path | None, typer.Option(help="Private archive root; default archive/cfbd.")
    ] = None,
) -> None:
    """Pull from the CFBD REST API into the PRIVATE archive, quota-guarded.

    The default is the 22-call weekly sequence of report 01 §3.7 in its stated
    order - GET /info first so the job fails fast on quota, GET /calendar to
    resolve the week so it is never hardcoded, then results, detail, aggregates,
    benchmarks, context. `--postseason` and `--teams` are the narrow, cheap pulls
    the 2021-2022 backfill and the team-color map need.

    Every raw response body is written unmodified before anything parses it
    (report 01 §5.4), and `archive/` is gitignored because CFBD terms §3 bar
    republishing raw API data. Requires CFBD_API_KEY; a fork without one runs the
    SportsDataverse leg and simply sees fewer games.
    """
    from cfbpoll.ingest import cfbd

    root = archive_root or cfbd.DEFAULT_ARCHIVE

    # `--ratings` is season-list scoped rather than single-season, because a
    # benchmark series is only interesting across the seasons the backtest
    # covers. It is also the cheapest pull here: one call per season.
    if ratings:
        with cfbd.Session(archive_root=root) as session:
            info = session.check_quota(abort_if_remaining_calls_below)
            typer.echo(
                f"CFBD {info.get('tierName')}: {info.get('remainingCalls')} of "
                f"{info.get('monthlyLimit')} calls remain (resets {info.get('resetAt')})"
            )
            years = _parse_seasons(seasons) if seasons else [int(season)] if season else []
            if not years:
                raise typer.BadParameter("--ratings needs --seasons (or --season)")
            pulled = cfbd.pull_ratings(ratings, years, session=session)
            for year_, rows in sorted(pulled.items()):
                typer.echo(
                    f"{year_} /ratings/{ratings}: "
                    f"{len(rows) if rows is not None else 0} rows archived"
                )
            typer.echo(
                f"{session.calls} calls spent. BENCHMARK ONLY: these bodies are "
                "private under CFBD terms §3 and are banned as model inputs by "
                "docs/constraints.md, enforced by `cfbpoll audit-features`."
            )
        return

    if season is None or not season.strip():
        raise typer.BadParameter("--season is required for --postseason and --teams pulls")
    year = int(season)

    with cfbd.Session(archive_root=root) as session:
        info = session.check_quota(abort_if_remaining_calls_below)
        typer.echo(
            f"CFBD {info.get('tierName')}: {info.get('remainingCalls')} of "
            f"{info.get('monthlyLimit')} calls remain (resets {info.get('resetAt')})"
        )
        if postseason:
            result = cfbd.pull_postseason(year, session=session)
            typer.echo(f"{year} postseason: {len(result['games'] or [])} games archived")
        if teams:
            from cfbpoll.ingest import teams as team_colors

            rows = cfbd.pull_teams(year, session=session)
            typer.echo(f"{year} /teams/fbs: {len(rows)} teams archived")
            # Rebuild the committed colour map from EVERY archived /teams body,
            # not just this one: a later season wins on any field, so a rebuild
            # from one pull would drop teams the others carry.
            built = team_colors.build_color_map()
            typer.echo(
                f"rebuilt {team_colors.COLOR_MAP_PATH.relative_to(cfbd.REPO_ROOT)}: "
                f"{len(built)} teams"
            )
        if not (postseason or teams):
            resolved = int(week) if week and week.strip() else cfbd.resolve_week(year)[0]
            session.close()
            out = cfbd.pull_week(year, resolved, root, min_remaining=0)
            typer.echo(f"{year} week {resolved}: {out['calls']} calls archived")
            return
        typer.echo(f"calls spent this run: {session.calls}")


@ingest_app.command("sportsdataverse")
def ingest_sportsdataverse(
    season: Annotated[str | None, typer.Option(help="Season; blank = current.")] = None,
) -> None:
    """Pull play-by-play and schedules from the MIT SportsDataverse release assets.

    WILL DO: fetch from `sportsdataverse/sportsdataverse-data` release tag
    `cfbfastR_cfb_pbp` (report 01 §3.10) - NOT the stale cfbfastR-data/pbp path -
    and use the `cfb_schedules_*` series, never `schedules_*`. This is the leg
    that needs no API key, which is what makes a fork work with zero secrets.
    """
    _stub("ingest sportsdataverse", "report 01 §3.10")


# --------------------------------------------------------------------------- archive


@archive_app.command("lock")
def archive_lock(
    repo: Annotated[str, typer.Option(help="owner/name that publishes the release.")] = (
        "vyhlidal/cfb-poll"
    ),
    tag: Annotated[str, typer.Option(help="Release tag holding the assets.")] = "archive-v1",
    root: Annotated[
        Path, typer.Option(help="Archive directory holding _manifest.json.")
    ] = Path("archive/sportsdataverse"),
    out: Annotated[Path, typer.Option(help="Lockfile to write.")] = Path(
        "data/manifests/sportsdataverse.lock.json"
    ),
) -> None:
    """Generate the committed lockfile from a completed backfill's manifest.

    The manifest under `archive/sportsdataverse/` records where each file came
    from upstream, on the machine that pulled it. The lockfile is the same set of
    digests addressed to everyone else: it names the release asset that serves
    each file, so `archive sync` can rebuild the archive on a clone that has
    never seen an API key.

    Run this after a backfill or after cutting a new release tag, and commit the
    result. It is small, it is deterministic, and `weekly.yml` keys its archive
    cache on `hashFiles()` of it.
    """
    import json

    from cfbpoll.ingest import archive as archive_mod

    manifest_path = root / archive_mod.MANIFEST_NAME
    if not manifest_path.exists():
        raise typer.BadParameter(
            f"{manifest_path} does not exist. The lockfile is derived from a "
            "completed backfill; there is nothing to derive it from yet."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = archive_mod.build_lock(manifest, repo=repo, tag=tag)
    written = archive_mod.write_lock(lock, out)
    typer.echo(
        f"wrote {written}: {lock['file_count']} assets, "
        f"{lock['total_bytes']:,} bytes, release {repo}@{tag}"
    )


@archive_app.command("sync")
def archive_sync(
    source: Annotated[str, typer.Option(help="sportsdataverse | cfbd")] = "sportsdataverse",
    seasons: Annotated[
        str | None, typer.Option(help="Comma-separated seasons; blank = all in the manifest.")
    ] = None,
    verify: Annotated[
        bool, typer.Option(help="sha256-check every file, not just its size.")
    ] = False,
    repair: Annotated[
        bool, typer.Option(help="Replace a local file whose digest disagrees with the lock.")
    ] = False,
    only: Annotated[
        str | None,
        typer.Option(help="Comma-separated path prefixes, e.g. 'schedules,crosswalk'."),
    ] = None,
    lock: Annotated[Path, typer.Option(help="Lockfile to sync against.")] = Path(
        "data/manifests/sportsdataverse.lock.json"
    ),
    root: Annotated[Path, typer.Option(help="Where the archive lands.")] = Path(
        "archive/sportsdataverse"
    ),
) -> None:
    """Materialise the MIT archive locally from our published release assets.

    ~0.55 GB for 2021-2025, from a public GitHub release. No account, no token,
    no API key, on any platform that can reach github.com. Every file's sha256 is
    checked against data/manifests/sportsdataverse.lock.json BEFORE any consumer
    reads it, and a mismatch is a hard failure rather than a warning.

    Downloads land on `<name>.part` and are renamed only once the digest matches,
    so an interrupted sync is resumable and any file that exists is a file that
    was checked. `--seasons` narrows the pull by year - a scores-only run needs
    the schedules and crosswalk and not the 0.52 GB of play-by-play.

    CFBD's archive is NOT synced by this command and never will be: its terms
    forbid operating a mirror or substitute API, so `archive/cfbd/` is private and
    a fork's 2021-2022 postseason legitimately differs from ours. `_run.json`
    records which archives a run actually read, so that difference is visible
    rather than mysterious.
    """
    from cfbpoll.ingest import archive as archive_mod

    if source != "sportsdataverse":
        raise typer.BadParameter(
            f"--source {source!r} is not syncable. Only the MIT SportsDataverse "
            "class is republished; CFBD raw responses are private under its terms "
            "(report 01 §4.1). See docs/data-sources.md."
        )

    payload = archive_mod.read_lock(lock)
    prefixes = [p.strip() for p in only.split(",") if p.strip()] if only else None
    if seasons:
        years = {str(y) for y in _parse_seasons(seasons)}
        keep = [f["path"] for f in payload["files"] if any(y in f["asset"] for y in years)]
        # Files with no year in the name (the licence, the roster crosswalk) are
        # not season-scoped and are always needed.
        keep += [
            f["path"]
            for f in payload["files"]
            if not any(char.isdigit() for char in f["asset"])
        ]
        prefixes = sorted(set(keep) | set(prefixes or []))

    summary = archive_mod.sync_from_lock(
        payload,
        root,
        verify=verify,
        repair=repair,
        only=prefixes,
        log=typer.echo,
    )
    typer.echo(
        f"archive {summary['root']} @ {summary['tag']}: {summary['checked']} checked, "
        f"{summary['downloaded']} downloaded ({summary['bytes_downloaded']:,} bytes), "
        f"{summary['ok']} verified"
    )


@archive_app.command("push")
def archive_push(
    target: Annotated[str, typer.Option(help="Object-storage target. Currently: r2.")] = "r2",
    scope: Annotated[
        str, typer.Option(help="Which archive class to push. Currently: cfbd.")
    ] = "cfbd",
) -> None:
    """Push the PRIVATE CFBD archive to object storage.

    WILL DO: append-only writes to a private Cloudflare R2 bucket, never
    overwriting. CFBD terms §3 prohibit redistributing raw API data without
    permission (report 01 §4.1(3)), so this class of bytes must never reach the
    public repo or a release asset.

    NOT CONFIGURED: no R2 bucket exists yet. The target is a stub; the credentials
    (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY) are unset.
    """
    _stub("archive push", "report 03 §5.2 (R2 target not yet provisioned)")


# --------------------------------------------------------------------------- pipeline


@app.command()
def validate(
    season: Annotated[str | None, typer.Option(help="Season; blank = read it from --from.")] = None,
    week: Annotated[str | None, typer.Option(help="Week; blank = read it from --from.")] = None,
    season_type: Annotated[
        str, typer.Option(help="regular | postseason. Buckets key on this, never on week alone.")
    ] = "regular",
    from_: Annotated[
        Path | None,
        typer.Option("--from", help="This week's run directory. Needed by the movement check."),
    ] = None,
    previous: Annotated[
        Path | None,
        typer.Option(help="Last week's run directory; blank = look beside --from."),
    ] = None,
    max_rating_move: Annotated[
        float | None,
        typer.Option(
            help="Power points a team may move week over week; blank = the measured "
            "default in validate/data_quality.py."
        ),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option(help="Treat a SKIPPED check as a failure. For a runner that has every input."),
    ] = False,
    out: Annotated[
        Path | None, typer.Option(help="Verdict JSON; blank = <--from>/validation.json.")
    ] = None,
) -> None:
    """Data-quality gate. On failure: halt, alert, publish nothing.

    Every assertion in report 01 §5.5, each one reported BY NAME with its
    verdict and the value it measured: completed flags and non-null scores for
    every FBS-vs-FBS game, a sane week game count, no team twice, every
    /teams/fbs team present with a plausible games-played count, box scores
    reconciling to final scores, bounded week-over-week rating movement, a
    cross-source CFBD-vs-SportsDataverse score diff, and the known-bug guard
    that no December/January game is bucketed into REGULAR week 1.

    THREE OUTCOMES, NEVER TWO. A check whose input is absent reports SKIPPED,
    never passed. Four of the eight read the PRIVATE CFBD archive or a second
    run directory and a fork has neither, so "we could not look" and "we looked
    and it was fine" must not print the same word. `--strict` promotes any skip
    to a failure, which is what a runner that knows it has every input should
    pass.

    TWO OF §5.5's SENTENCES ARE WRONG AS WRITTEN and are implemented as the
    smallest honest version instead. The December/week-1 guard is division-aware
    and keyed on (season_type, week), because four D-II championship games dated
    2025-12-13 carry season_type='regular', week=1 and all 240 archived
    postseason week-1 games are correctly bucketed (docs/data-findings.md §1,
    §2). "No team appears twice" allows two appearances in regular week 1, where
    upstream folds week 0 in, and four in a postseason bucket, where the 12-team
    CFP plays four rounds. Both allowances are measured over 2021-2025 and named
    as constants in validate/data_quality.py.

    Exits non-zero on any failure and prints the failing checks last, so an
    unattended runner's log ends with the reason it stopped.
    """
    import json

    from cfbpoll.validate import data_quality

    if from_ is not None and not from_.exists():
        raise typer.BadParameter(f"--from {from_} does not exist")

    record: dict[str, Any] = {}
    if from_ is not None and (from_ / "_run.json").exists():
        record = json.loads((from_ / "_run.json").read_text(encoding="utf-8"))

    if season is None or not str(season).strip():
        if not record:
            raise typer.BadParameter(
                "--season is required unless --from points at a run directory whose "
                "_run.json carries it. Resolving the CURRENT week needs CFBD's "
                "/calendar, which needs an API key (report 01 §3.7)."
            )
        season_i = int(record["season"])
    else:
        season_i = int(season)
    if week is None or not str(week).strip():
        if not record:
            raise typer.BadParameter("--week is required unless --from carries it")
        week_i = int(record["through_week"])
    else:
        week_i = int(week)

    # LAST WEEK, WITHOUT MAKING ANYBODY TYPE IT. The weekly job writes each run
    # into its own directory under one parent, so the previous week is a sibling
    # whose _run.json says week - 1. Discovery is refused when two siblings claim
    # the same week, because guessing which one produced the published poll is
    # exactly the kind of quiet choice this repository does not make.
    resolved_previous = previous
    if resolved_previous is None and from_ is not None:
        resolved_previous = _sibling_run(from_, season_i, week_i - 1)

    report = data_quality.validate_week(
        season_i,
        week_i,
        season_type=season_type,
        run=from_,
        previous=resolved_previous,
        max_rating_move=(
            max_rating_move
            if max_rating_move is not None
            else data_quality.MAX_RATING_MOVE_POINTS
        ),
        strict=strict,
    )

    typer.echo(
        f"{season_i} {season_type} week {week_i}: "
        f"{sum(1 for c in report.checks if c.status == data_quality.PASS)} pass, "
        f"{len(report.failures)} fail, {len(report.skipped)} skipped"
        + ("  [STRICT]" if strict else "")
    )
    for check in report.checks:
        mark = {data_quality.PASS: "ok  ", data_quality.FAIL: "FAIL", data_quality.SKIP: "SKIP"}[
            check.status
        ]
        typer.echo(f"  {mark} {check.name:<36} {check.detail}")

    destination = out if out is not None else ((from_ or Path("out")) / "validation.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    typer.echo(f"wrote: {destination}")

    if not report.passed:
        reasons = report.failures or report.skipped
        typer.echo("")
        typer.echo(
            "HALT. Publish nothing. "
            + ("; ".join(f"{c.name}: {c.detail}" for c in reasons))
        )
        typer.echo(
            "Report 01 §5.2: keep the previous week's published ranking and say the "
            "current one failed validation. Publishing late costs less than publishing wrong."
        )
        raise typer.Exit(code=1)


def _sibling_run(run: Path, season: int, week: int) -> Path | None:
    """The run directory beside `run` that holds (season, week). None if unclear."""
    import json

    parent = run.parent
    if not parent.exists():
        return None
    found: list[Path] = []
    for candidate in sorted(parent.iterdir()):
        if not candidate.is_dir() or candidate == run:
            continue
        record_path = candidate / "_run.json"
        if not record_path.exists():
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if int(record.get("season", -1)) == season and int(record.get("through_week", -1)) == week:
            found.append(candidate)
    return found[0] if len(found) == 1 else None


@app.command()
def benchmarks(
    out: Annotated[Path | None, typer.Option(help="Write the table as JSON to this path.")] = None,
) -> None:
    """The third-party ratings we compare against. BENCHMARKS ONLY, NEVER INPUTS.

    `docs/data-sources.md` has always stated the rule and `cfbpoll audit-features`
    has always enforced it, but nothing could enumerate the set until now, and a
    rule with no roster is a rule nobody can check you against.

    The two columns that matter are `open_source` and `error_metrics`, because
    together they are the differentiation this project is actually claiming.
    "Transparent" stopped being a differentiator the day a free, well-documented
    rating shipped from inside the data layer. "Checkable" did not.

    `scorable` says whether the harness could legitimately score a series. Today
    every answer is no, and the reason is worth more than a table would be: these
    are published one row per team per SEASON, and putting a season-final number
    in a walk-forward table beside systems that saw through week N-1 would
    flatter it and measure nothing.
    """
    import json

    from cfbpoll import benchmarks as bench

    rows = bench.display_rows()
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")

    header = f"{'name':<7}{'open':>6}{'metrics':>9}{'weekly':>8}{'scorable':>10}  {'author'}"
    typer.echo(header)
    for entry in bench.BENCHMARKS:
        typer.echo(
            f"{entry.name:<7}{'yes' if entry.open_source else 'no':>6}"
            f"{'yes' if entry.publishes_error_metrics else 'no':>9}"
            f"{'yes' if entry.granularity == 'weekly' else 'no':>8}"
            f"{'yes' if entry.scorable else 'no':>10}  {entry.author}"
        )
    typer.echo(
        "\nNone of these is ever a model input. The enforcement is an ALLOW-LIST "
        "rebuild of every design matrix (`cfbpoll audit-features`), so a rating "
        "nobody thought to ban by name still fails closed."
    )
    if out is not None:
        typer.echo(f"wrote: {out}")


@app.command("audit-features")
def audit_features(
    season: Annotated[str | None, typer.Option(help="Season to audit; blank = all.")] = None,
    through_week: Annotated[
        str | None, typer.Option(help="Audit the window through this week; blank = the season.")
    ] = None,
    fail_on_banned: Annotated[
        bool, typer.Option(help="Exit non-zero if a banned column reached a model matrix.")
    ] = False,
    out: Annotated[
        Path | None, typer.Option(help="Write the full report as JSON to this path.")
    ] = None,
) -> None:
    """Poll-input leakage audit. Constraint 1 is easy to violate by accident.

    Asserts that the columns entering every design matrix are exactly the allowed
    list in report 02 §3.10 (L1: OUR play value, offense/defense team id, site,
    quarter, score margin, clock; L2: final score, team ids, site, game type; L3:
    L1+L2 outputs; L4: L3 outputs, win/loss, schedule; schedule odds: the same
    plus division class for the q_ref pool) and that no banned input appears -
    AP/Coaches/CFP rankings, recruiting or talent composites, returning
    production, prior-season ratings, SP+/FPI, third-party EPA/WPA/Elo, Vegas
    lines, or conference identity. The banned table is reproduced in
    docs/constraints.md.

    HOW IT KNOWS, rather than assumes: every design matrix is rebuilt from the
    frame RESTRICTED to its layer's allow-list and required to be bit-identical
    to the one the unrestricted frame produced (src/cfbpoll/validate/leakage.py).
    A column outside the allow-list that changes or breaks the rebuild is named
    by ablation. `conference_game` is in the schedule frame every single run, and
    every single run proves no fit consumed it.

    `--fail-on-banned` exits non-zero on any violation. Both weekly.yml and
    reproducibility.yml pass it, and `cfbpoll rank` runs this audit before it
    fits anything whenever `[constraints].fail_build_on_banned_feature` is true.
    """
    import json

    from cfbpoll.config import load_config
    from cfbpoll.ingest import windows
    from cfbpoll.ingest.plays import DEFAULT_ARCHIVE as PLAY_ARCHIVE
    from cfbpoll.ingest.plays import load_plays
    from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games
    from cfbpoll.validate import leakage

    cfg = load_config()
    if season is None or str(season).strip() == "":
        seasons = sorted(
            int(p.stem.rsplit("_", 1)[-1])
            for p in (DEFAULT_ARCHIVE / "schedules").glob("*.parquet")
        )
    else:
        seasons = _parse_seasons(str(season))
    if not seasons:
        raise typer.BadParameter("no seasons found in the archive; run `cfbpoll archive sync`")

    reports: list[dict[str, Any]] = []
    failed = False
    for one in seasons:
        games = load_games([one], universe=str(cfg["model"]["fit_universe"]))
        if through_week is not None and str(through_week).strip() != "":
            games = windows.games_through(
                games, season=one, week=int(through_week), season_type="regular"
            )
        plays = None
        if (PLAY_ARCHIVE / "pbp" / f"play_by_play_{one}.parquet").exists():
            plays = load_plays([one])
        report = leakage.audit(games, plays, cfg, fail_on_banned=False)
        reports.append({"season": one, **report.as_dict()})
        failed = failed or not report.passed
        typer.echo(
            f"{one}: {'PASS' if report.passed else 'FAIL'} - "
            f"{len(report.layers)} layers, {report.context['n_games']} games, "
            f"{report.context['n_plays']} plays"
        )
        for layer in report.layers:
            mark = "ok " if layer.ok else "FAIL"
            skip = f"  SKIPPED: {layer.skipped}" if layer.skipped else ""
            banned = (
                f"  banned-pattern columns present and proved unconsumed: "
                f"{list(layer.banned_present)}"
                if layer.banned_present and layer.ok
                else ""
            )
            typer.echo(
                f"  {mark} {layer.layer:<14} {len(layer.allowed):>2} allowed, "
                f"{len(layer.extra_present):>2} other column(s) present, "
                f"{len(layer.consumed_outside_allow_list)} consumed{skip}{banned}"
            )
        for violation in report.violations:
            typer.echo(f"  VIOLATION: {violation}")

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(reports, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        typer.echo(f"wrote: {out}")

    if failed and fail_on_banned:
        raise typer.Exit(code=1)


@app.command("recipes")
def list_recipes(
    out: Annotated[Path | None, typer.Option(help="Write the roster as JSON to this path.")] = None,
) -> None:
    """The named value systems the poll can be read under (configs/recipes/).

    A ranking is a value system, so this project ships more than one and names
    them. `full-merit` takes margin at face value; `house` is the published poll
    and compresses margin in the engine while keeping it out of the headline;
    `just-win` compresses margin almost to nothing and ranks on wins alone.

    A RECIPE CHANGES VALUES, NEVER EVIDENCE. Every recipe reads the same archive
    through the same walk-forward window under the same constraints, and
    `recipes.EVIDENCE_KEYS` makes that a load-time refusal rather than a
    convention. Only `house` is published as the poll; the rest are alternate
    lenses and every artifact they touch says so.
    """
    import json

    from cfbpoll import recipes as recipes_mod

    roster = recipes_mod.roster()
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(roster, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for entry in roster:
        flag = "  [PUBLISHED POLL, default]" if entry["is_house"] else "  [alternate lens]"
        typer.echo(f"{entry['slug']:<12}{entry['name']:<18}{flag}")
        typer.echo(f"  {entry['one_liner']}")
        changes = entry["changes"]
        typer.echo(
            "  changes: "
            + (", ".join(f"{k} = {v}" for k, v in changes.items()) if changes else "nothing at all")
        )
        for cost in entry["tradeoffs"]:
            typer.echo(f"  cost: {cost}")
        typer.echo("")
    if out is not None:
        typer.echo(f"wrote: {out}")


@app.command()
def rank(
    config: Annotated[Path, typer.Option(help="Model config TOML.")] = Path("configs/default.toml"),
    recipe: Annotated[
        str, typer.Option(help="Named value system from configs/recipes/. Default: the house poll.")
    ] = "house",
    recipe_dir: Annotated[
        Path | None,
        typer.Option(
            help="Look --recipe up here instead of configs/recipes/. For the variants "
            "playground; generated overlays obey every rule a hand-written recipe does "
            "and never enter the published roster."
        ),
    ] = None,
    season: Annotated[str | None, typer.Option(help="Season; blank = current.")] = None,
    through_week: Annotated[
        str | None, typer.Option(help="Data window K. Blank = latest completed week.")
    ] = None,
    seed: Annotated[int | None, typer.Option(help="Seed for any stochastic step.")] = None,
    draws: Annotated[
        int | None,
        typer.Option(help="Bootstrap draws; blank = [bootstrap].draws. 0 skips the intervals."),
    ] = None,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out"),
) -> None:
    """Fit the model and write the ratings, the poll and the run record.

    THE HEADLINE IS SCHEDULE ODDS (`[publication].headline_ordering`, decided
    2026-08-12, docs/adr/0005-headline-ordering.md). Teams are ranked by
    -log10 P(W >= W_t): how improbable it is that a team of reference quality
    q_ref would have gone at least this well against this exact schedule. The
    harder it was to do what you did, the higher you go - measured from results,
    never assumed.

    NOTHING WAS DROPPED. The L4 resume on the points scale, its margin-aware
    variant, its saturation flag, and the Power rating with the resume-minus-power
    gap are printed beside every team and are columns on every published row
    (report 02 §3.4, §3.5). Both surfaces (live R(N,N) and hindsight R(N,final))
    reach poll.json and poll.csv, and the hindsight column now moves for unbeaten
    teams too - which it structurally could not do under the resume ordering.

    OPPONENT QUALITY IS L3, the walk-forward blend of L1 efficiency and L2
    results, whenever `[resume].power_source` says so and the play archive is
    present; the blend weights come from a forward walk of the season, so they
    are fitted only on games already predicted (report 02 §3.3). A season with no
    play feed falls back to L2 rescaled to points. Whichever ran is stamped as
    `power_source` / `power_version` on model_params.json, poll.json and every
    ratings row. The bootstrap rank intervals are still not built.

    Writes ratings_live.parquet, ratings_hindsight.parquet (+ .csv),
    poll.json/poll.csv, model_params.json and _run.json to --out. Report 03 §5.3
    fixes those filenames. `cfbpoll grid` writes the same two surfaces for every
    week of a season at once, in the same schema.

    Weeks before configs/default.toml's headline_start_week are written as
    clearly-labelled provisional output, never as "the poll" (report 02 §4).
    """
    import polars as pl

    from cfbpoll import recipes as recipes_mod
    from cfbpoll.ingest import windows
    from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games
    from cfbpoll.model import bootstrap as bootstrap_mod
    from cfbpoll.model import l4_resume, retro, schedule_odds
    from cfbpoll.publish import files
    from cfbpoll.publish import poll as poll_mod
    from cfbpoll.validate import leakage

    if season is None or str(season).strip() == "":
        raise typer.BadParameter(
            "--season is required until the CFBD /calendar resolver exists "
            "(report 01 §3.7). Try --season 2023."
        )
    season_i = int(season)
    # THE RECIPE IS RESOLVED BEFORE ANYTHING ELSE HAPPENS. `resolve` merges the
    # recipe's diff onto `--config` through `merge_overlay`, which refuses a key
    # the base does not define, and `assert_values_only` has already refused any
    # key that would change what EVIDENCE the run reads. Every line below this one
    # is identical for every recipe; only the constants differ.
    try:
        cfg, chosen = recipes_mod.resolve(recipe, config, directory=recipe_dir)
    except recipes_mod.RecipeError as error:
        raise typer.BadParameter(str(error)) from error

    games = load_games([season_i], universe=str(cfg["model"]["fit_universe"]))
    plays = _plays_if_needed(cfg, [season_i])
    buckets = windows.season_buckets(games, season_i)
    regular = [b for b in buckets if b.season_type == "regular"]
    if through_week is None or str(through_week).strip() == "":
        week_i = max(b.week for b in regular)
    else:
        week_i = int(through_week)

    evaluated = next(b for b in regular if b.week == week_i)
    final = buckets[-1]

    window = windows.games_through(games, season=season_i, week=week_i, season_type="regular")

    # THE PRE-FIT AUDIT (report 02 §3.10). Every design matrix this run is about
    # to build is rebuilt from the allow-list projection of this exact window and
    # required to be bit-identical, BEFORE a single rating is fitted. It costs
    # about a second and it is the difference between "the constitution is
    # enforced" and "the constitution is asserted".
    audit_report = leakage.audit(
        window,
        plays,
        cfg,
        fail_on_banned=bool(cfg["constraints"]["fail_build_on_banned_feature"]),
    )
    typer.echo(
        f"feature audit: {'PASS' if audit_report.passed else 'FAIL'} - "
        f"{len(audit_report.layers)} layers rebuilt from their allow-lists; "
        f"banned-pattern columns present and proved unconsumed: "
        f"{sorted({c for lay in audit_report.layers for c in lay.banned_present}) or 'none'}"
    )

    powers = retro.season_power(games, season_i, cfg, plays=plays, buckets=buckets)
    power = powers[evaluated.order]
    classes = poll_mod.team_classes(games)
    fitted = l4_resume.fit(window, cfg, power=power)
    odds = schedule_odds.fit(window, cfg, power=power, classes=classes)

    live = retro.cell(games, evaluated, evaluated, cfg, power=power, classes=classes)
    hindsight = retro.cell(games, evaluated, final, cfg, power=powers[final.order], classes=classes)

    # THE INTERVALS. `[publication].publish_rank_intervals` says "every week,
    # forever"; this is where that happens. The scheme is parametric on the FIXED
    # schedule - outcomes redrawn from the fitted model, refit, re-ranked - and
    # NOT the resample-games-with-replacement the scaffold specified, which is
    # invalid on a schedule graph (model/bootstrap.py).
    n_draws = int(draws if draws is not None else cfg["bootstrap"]["draws"])
    root_seed = int(seed if seed is not None else cfg["bootstrap"]["seed"])
    draw_set = None
    interval_table = None
    if bool(cfg["publication"]["publish_rank_intervals"]) and n_draws > 0:
        draw_set = bootstrap_mod.run(
            window, power, cfg, classes=classes, draws=n_draws, seed=root_seed
        )
        interval_table = bootstrap_mod.intervals(draw_set, float(cfg["bootstrap"]["interval"]))

    ordering = poll_mod.headline_ordering(cfg)
    # The interval beside a rank must be an interval on THAT rank, so the ordering
    # is threaded into the join rather than assumed (publish/poll.py's
    # HEADLINE_INTERVAL_ORDERING).
    table = poll_mod.headline_frame(live, hindsight, interval_table, ordering)
    provisional, label = poll_mod.publication_status(week_i, cfg)

    l2 = power.l2
    params = {
        # The résumé's block first, then the headline ordering's, so the two
        # `layer`/`version` pairs cannot collide: the headline's wins the key and
        # the résumé's is preserved under `resume_layer` / `resume_version`.
        **fitted.as_params(),
        **(l2.as_params() if l2 is not None else {}),
        "resume_layer": l4_resume.LAYER,
        "resume_version": l4_resume.VERSION,
        **odds.as_params(),
        "layer": schedule_odds.LAYER,
        "version": schedule_odds.VERSION,
        "season": season_i,
        "through": {"season_type": evaluated.season_type, "week": evaluated.week},
        "provisional": provisional,
        "provisional_label": label,
        "headline_ordering": ordering,
        "headline_layer": cfg["publication"]["headline_layer"],
        "headline_decided": "2026-08-12, docs/adr/0005-headline-ordering.md",
        # WHICH VALUE SYSTEM PRODUCED THIS RANKING, on the artifact, by name, with
        # its manifesto and its costs attached (ADR 0011). Every run carries it,
        # including the house run, because "no recipe was named" and "the house
        # recipe ran" are the same event and an artifact that leaves a reader to
        # infer which is being coy about what produced a number.
        "recipe": chosen.as_dict(),
        "recipe_config_sha256": recipes_mod.resolved_hash(cfg),
        "companion_layer": cfg["publication"]["companion_layer"],
        "hindsight_variant": retro.HINDSIGHT_VARIANT,
        "hindsight_data_bucket": final.label,
        "hindsight_is_live": final.order == evaluated.order,
        "layers_implemented": (
            ["L1", "L2", "L3", "L4", "bootstrap"]
            if plays is not None
            else ["L2", "L4", "bootstrap"]
        ),
        "layers_missing": [],
        "seed": root_seed,
        "interval_level": float(cfg["bootstrap"]["interval"]),
        **(draw_set.as_params() if draw_set is not None else {"bootstrap_draws": 0}),
        # Constraint 5: the audit that licensed this run is published with it,
        # not merely run and forgotten.
        "feature_audit": {
            "passed": audit_report.passed,
            "spec": "report 02 §3.10",
            "method": "allow-list rebuild, bit-identity required",
            "layers": [layer.layer for layer in audit_report.layers],
            "layers_skipped": sorted(
                layer.layer for layer in audit_report.layers if layer.skipped
            ),
            "banned_pattern_columns_present_and_unconsumed": sorted(
                {c for layer in audit_report.layers for c in layer.banned_present}
            ),
            "violations": list(audit_report.violations),
        },
    }
    run = {
        "season": season_i,
        "through_week": week_i,
        "archive": str(DEFAULT_ARCHIVE),
        "archive_manifest_sha256": _archive_identity(DEFAULT_ARCHIVE),
        "n_games_in_fit": int(window.height),
        "n_teams_in_fit": int(live.height),
        "n_ranked_teams": int(table.height),
        "game_sources": _game_sources(window),
        "recipe": chosen.slug,
        "recipe_base_config": str(config),
        # The hash of the RESOLVED methodology, not of a file. `config_hash` below
        # still hashes the base config's bytes, so a house run's receipt is
        # unchanged; this is the field that distinguishes two recipes sharing one
        # base, and it is a pure function of every constant that ran (ADR 0011).
        "recipe_config_sha256": recipes_mod.resolved_hash(cfg),
        # THE EVIDENCE DIGEST. Same archive, same window, same games, under every
        # recipe. It is published on every run so the claim is checkable by diffing
        # two receipts rather than by trusting this sentence; the assertion itself
        # lives in tests/unit/test_recipes.py.
        "fit_window_sha256": leakage.digest(window),
    }
    written = files.write_rank_outputs(
        out, live, hindsight, table, params, run, config_path=config, intervals=interval_table
    )

    saturated = int(table.filter(pl.col("saturated") != 0).height)
    typer.echo(
        f"recipe {chosen.slug!r} ({chosen.name}): "
        + ("THE PUBLISHED POLL" if chosen.is_house else recipes_mod.ALTERNATE_LABEL)
        + " - "
        + chosen.one_liner
    )
    # WHAT ACTUALLY SORTED THIS TABLE, named on the terminal as well as on the
    # artifact. Two of the three recipes rank on a column that is not the schedule
    # odds, and a run that prints "the headline ordering is schedule odds" while
    # ranking on the résumé is lying to the one person who can still catch it.
    key_column, key_header, key_note = _HEADLINE_KEY[ordering]
    typer.echo(
        f"{cfg['publication']['headline_layer']} - the headline ordering "
        f"(Power = {params['power_source']} {params['power_version']}) - "
        f"{season_i} through {evaluated.label}: {window.height} games, "
        f"{live.height} teams, {table.height} ranked, "
        f"lambda_l2={l2.lam:g} h={power.home_field:.3f}"
        if l2 is not None
        else f"{cfg['publication']['headline_layer']} - {season_i} through {evaluated.label}"
    )
    typer.echo(f"  rank key {key_note}")
    typer.echo(
        f"  q_ref = {odds.q_ref.value:.2f} points"
        + (f" ({odds.q_ref.team})" if odds.q_ref.team else "")
        + f" by {odds.q_ref.method}"
        + (
            "; margin never enters the key"
            if ordering == "schedule_odds"
            else "; the schedule odds are published beside every team but do not sort this table"
        )
    )
    typer.echo(
        f"  {saturated} ranked team(s) saturated at the q bound (*) on the RESUME column"
        + (
            ", which IS the key under this recipe: every one of them is tied at the "
            "bound and separated only by the margin-aware tie-break"
            if ordering == "L4_resume"
            else ", which is published beside the key and does not order this table"
        )
        + ("  [PROVISIONAL]" if provisional else "")
    )
    if draw_set is not None:
        level = int(round(100 * float(cfg["bootstrap"]["interval"])))
        typer.echo(
            f"  {level}% rank intervals from {draw_set.n_draws} parametric draws on the "
            f"FIXED schedule (seed {draw_set.seed}, sigma {draw_set.sigma:g}); "
            "games are graph edges, so resampling them with replacement is invalid "
            "and is not what this does"
        )
    typer.echo(
        f"{'#':>3} {'90% int':>9}  {'team':<24}{key_header + ' *':>11}{'-log10P':>9}"
        f"{'resume':>9}{'r-margin':>10}{'power':>8}{'+/-':>6}{'gap':>7}   rec   retro"
    )
    for row in table.head(25).iter_rows(named=True):
        mark = "*" if row["saturated"] else " "
        interval = (
            f"{row['rank_lo']:>4}-{row['rank_hi']:<4}"
            if row["rank_lo"] is not None
            else " " * 9
        )
        se = f"{row['power_se']:>6.2f}" if row["power_se"] is not None else " " * 6
        typer.echo(
            f"{row['rank']:>3} {interval}  {row['team']:<24}{row[key_column]:>11.3f}"
            f"{row['odds_key']:>9.3f}{row['resume']:>8.2f}{mark}{row['resume_margin']:>10.2f}"
            f"{row['power']:>8.2f}{se}{row['gap']:>7.2f}"
            f"  {row['wins']}-{row['losses']}  {row['rank_delta']:+d}"
        )
    typer.echo("wrote: " + ", ".join(p.name for p in written))


@app.command()
def backtest(
    config: Annotated[Path, typer.Option(help="Model config TOML.")] = Path("configs/default.toml"),
    systems: Annotated[
        str,
        typer.Option(
            help=(
                "Comma-separated systems, e.g. "
                "schedule_odds,resume,l3,l2,l1,colley,srs,elo,walker,winpct."
            )
        ),
    ] = "schedule_odds,resume,l3,l2,l1,colley,srs,elo,walker,winpct",
    seasons: Annotated[
        str, typer.Option(help="Seasons: '2021-2023' or '2021,2022,2023'.")
    ] = "2021-2023",
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out"),
    unlock_holdout: Annotated[
        bool,
        typer.Option(
            "--unlock-holdout",
            help="Score the held-out season. SINGLE SHOT. Do not use casually.",
        ),
    ] = False,
) -> None:
    """Strict walk-forward backtest against every baseline. Writes backtest_metrics.json.

    To predict bucket N of a season the harness fits through bucket N-1 of the
    SAME season and nothing else - no prior seasons, no future games (report 02
    §5.1). The FBS-vs-FBS universe is the headline; FBS-vs-FCS, non-CFP bowls and
    CFP games are reported separately because they measure different things.

    The home-team-always-wins floor is always included, whether or not it is
    named in --systems: a table without its floor is not a table.

    `schedule_odds` is the HEADLINE ORDERING (ADR 0005) and `resume` is the
    ordering it replaced. Both are RETRODICTIVE ratings, so both are scored on
    violations and both predict margins through their shared Power source - which
    is `[resume].power_source`, so their predictive columns are L3's (or L2's) by
    construction, and the violations column is the one that is about them
    (report 02 §3.5, §5.4). Keeping the old headline permanently in the table is
    the point: the decision that replaced it stays checkable every week rather
    than being frozen in a document.

    THE CLAIM UNDER TEST is report 02 §3.3: the L3 blend beats the L2 results
    core. Both are in the default --systems list, scored by the same code on the
    same games, and `blend` in backtest_metrics.json carries the w1/w2/k
    trajectory that produced the L3 row.

    2025 IS HELD OUT. The harness refuses to score it unless --unlock-holdout is
    passed by a human who has read report 02 §5.1 and accepts that it is a
    single-shot test.
    """
    import json

    from cfbpoll.backtest import walkforward
    from cfbpoll.config import load_config

    cfg = load_config(config)
    wanted = [s for s in (x.strip() for x in systems.split(",")) if s]
    if "home_team" not in wanted and "home" not in wanted:
        wanted.append("home_team")

    result = walkforward.run_backtest(
        seasons=_parse_seasons(seasons),
        systems=wanted,
        config=cfg,
        unlock_holdout=unlock_holdout,
    )

    out.mkdir(parents=True, exist_ok=True)
    path = out / "backtest_metrics.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True, default=float) + "\n")

    headline_week = result["protocol"]["headline_start_week"]
    typer.echo(
        f"walk-forward {result['protocol']['seasons']} - FBS-vs-FBS, "
        f"weeks >= {headline_week} (the published window)"
    )
    typer.echo(
        f"{'system':<14}{'n':>6}{'SU%':>8}{'MAE':>8}{'RMSE':>8}{'Brier':>8}{'logloss':>9}{'viol%':>8}{'churn':>8}"
    )
    for name, block in result["systems"].items():
        s = block["segments_from_headline_week"].get("fbs_vs_fbs")
        if not s:
            continue
        viol = block["retrodictive_violation_rate"]
        churn = block["rank_churn"]["mean_all"]
        typer.echo(
            f"{name:<14}{s['n_games']:>6}{s['su_accuracy'] * 100:>8.2f}{s['mae']:>8.3f}"
            f"{s['rmse']:>8.3f}{s['brier']:>8.4f}{s['log_loss']:>9.4f}"
            f"{(viol * 100 if viol is not None else float('nan')):>8.2f}"
            f"{(churn if churn is not None else float('nan')):>8.2f}"
        )
    blend = result.get("blend") or []
    if blend:
        last = blend[-1]
        typer.echo(
            f"L3 blend, last bucket ({last['bucket']}): w1={last['w1']:.4f} "
            f"w2={last['w2']:.4f} k={last['k']:.2f} h={last['h_points']:.2f} "
            f"({last['weight_source']}, n={last['n_blend_games']}); "
            f"contribution SD efficiency={last['efficiency_contribution_sd']:.2f} "
            f"results={last['results_contribution_sd']:.2f}"
        )
    typer.echo(f"wrote: {path}")


@challenge_app.command("run")
def challenge_run(
    entry: Annotated[
        Path, typer.Option(help="configs/challengers/<name>.toml, or a .py exposing rate().")
    ],
    seasons: Annotated[
        str, typer.Option(help="Seasons: '2021-2023' or '2021,2022,2023'.")
    ] = "2021-2023",
    config: Annotated[Path, typer.Option(help="Incumbent config.")] = Path("configs/default.toml"),
    systems: Annotated[
        str | None, typer.Option(help="Comparison set; blank = the published one.")
    ] = None,
    out: Annotated[Path, typer.Option(help="Where the scorecard lands.")] = Path("out/challenge"),
) -> None:
    """Score a challenger through the IDENTICAL walk-forward harness. Writes a scorecard.

    Same `run_backtest`, same frames, same seasons, same baselines, same
    publication gate as `demo/backtest-2021-2023.md`. Nothing in the challenge
    path re-implements a metric, because a number produced by code that only
    challengers run would settle nothing.

    A parameter variant (`.toml`) overrides only the constants it names and is run
    against the default config in the same command, so the comparison is two runs
    of one harness rather than one run against a remembered number. A structural
    variant (`.py` exposing
    `rate(games, plays, through_week, config=None, state=None)`) is registered as
    one more system in a single run and needs no merge at all.

    2025 IS A SEALED HOLDOUT and this command never unlocks it. Tune on 2021-2023,
    validate on 2024, and if you tune against 2025 and say nothing your result
    means nothing - which is a fact about the exercise, not a rule we can enforce
    on your laptop.
    """
    from cfbpoll.backtest import challenge as challenge_mod

    who = challenge_mod.load_challenger(entry, config)
    wanted = [s.strip() for s in systems.split(",")] if systems else None
    typer.echo(f"challenger {who.name!r} ({who.kind}) from {who.entry}")

    result = challenge_mod.run_challenge(
        who, _parse_seasons(seasons), systems=wanted, config_path=config
    )
    written = challenge_mod.write_scorecard(result, out)

    verdict = result["verdict"]
    for row in result["scorecard"]:
        mark = "better" if row["better"] else "worse "
        typer.echo(
            f"  {mark}  {row['label']:<24} incumbent {row['incumbent']:>10.4f}  "
            f"challenger {row['challenger']:>10.4f}  ({row['delta']:+.4f})"
        )
    typer.echo(
        f"{len(verdict['beats_incumbent_on'])} of "
        f"{len(verdict['beats_incumbent_on']) + len(verdict['loses_to_incumbent_on'])} "
        f"metrics beat the incumbent; clears the gate: {verdict['challenger_clears_gate']} "
        f"(incumbent: {verdict['incumbent_clears_gate']})"
    )
    typer.echo(f"wrote: {written['markdown']} and {written['json']}")


@app.command()
def grid(
    config: Annotated[Path, typer.Option(help="Model config TOML.")] = Path("configs/default.toml"),
    season: Annotated[str | None, typer.Option(help="Season to compute the triangle for.")] = None,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out"),
    movers_top: Annotated[int, typer.Option(help="Rows kept in retro_movers.csv per week.")] = 25,
) -> None:
    """Compute the full R(N, K) retroactive triangle for a season.

    R(N, K) is the ratings for evaluation week N computed from data through week
    K (report 02 §3.6). K >= N always. The diagonal R(N, N) is the poll as it was
    published; the last column R(N, final) is the same weeks re-scored with the
    season's answers - hindsight variant A, frozen form: Power from the full
    season, resume from each team's games through week N.

    Writes ratings_grid.parquet (+ .csv), ratings_live.parquet, ratings_hindsight
    .parquet, retro_movers.csv, model_params.json and _run.json to --out.

    N and K are BUCKETS ordered by first kickoff, not bare week numbers: week
    numbering inside a season is neither monotone nor unique (docs/data-findings
    .md §1). 2021 and 2022 carry no postseason rows in the MIT parquet; since the
    2026-08-12 CFBD backfill those 80 games come from the private archive instead,
    so "final" means final for every season we hold. A fork without that archive
    gets the shorter window and the run record's `game_sources` says which it was.
    """
    from cfbpoll.config import load_config
    from cfbpoll.ingest import windows
    from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games
    from cfbpoll.model import retro
    from cfbpoll.publish import files
    from cfbpoll.publish import poll as poll_mod

    if season is None or str(season).strip() == "":
        raise typer.BadParameter("--season is required. Try --season 2023.")
    season_i = int(season)
    cfg = load_config(config)

    games = load_games([season_i], universe=str(cfg["model"]["fit_universe"]))
    plays = _plays_if_needed(cfg, [season_i])
    buckets = windows.season_buckets(games, season_i)
    powers = retro.season_power(games, season_i, cfg, plays=plays, buckets=buckets)
    triangle = retro.grid(games, season_i, cfg, buckets, powers=powers)
    live, hindsight = retro.surfaces(triangle)

    movers = retro.movers_by_week(live, hindsight, buckets, top_n=movers_top)

    final = buckets[-1]
    has_postseason = any(b.season_type == "postseason" for b in buckets)
    params = {
        "layer": "C schedule odds",
        "version": "v0",
        "resume_layer": "L4 resume rating",
        "resume_version": "v0",
        "headline_ordering": poll_mod.headline_ordering(cfg),
        "headline_decided": "2026-08-12, docs/adr/0005-headline-ordering.md",
        "season": season_i,
        "hindsight_variant": retro.HINDSIGHT_VARIANT,
        "n_buckets": len(buckets),
        "n_cells": len(buckets) * (len(buckets) + 1) // 2,
        "buckets": [
            {"order": b.order, "season_type": b.season_type, "week": b.week, "label": b.label}
            for b in buckets
        ],
        "final_bucket": final.label,
        "season_has_postseason_rows": has_postseason,
        "final_means": (
            "through the postseason in the archive"
            if has_postseason
            else "through conference championships - no postseason rows in "
            "cfb_schedules and no CFBD backfill present (docs/data-findings.md §13)"
        ),
        "headline_layer": cfg["publication"]["headline_layer"],
        "companion_layer": cfg["publication"]["companion_layer"],
        **{k: v for k, v in cfg["resume"].items()},
        **{f"schedule_odds_{k}": v for k, v in cfg["schedule_odds"].items()},
        **powers[final.order].as_params(),
    }
    run = {
        "season": season_i,
        "archive": str(DEFAULT_ARCHIVE),
        "archive_manifest_sha256": _archive_identity(DEFAULT_ARCHIVE),
        "n_games_in_season": int(games.height),
        "n_grid_rows": int(triangle.height),
        "game_sources": _game_sources(games),
    }
    written = files.write_grid_outputs(
        out, triangle, live, hindsight, movers, params, run, config_path=config
    )

    typer.echo(
        f"R(N, K) for {season_i}: {len(buckets)} buckets, "
        f"{len(buckets) * (len(buckets) + 1) // 2} cells, {triangle.height:,} rows "
        f"(hindsight variant {retro.HINDSIGHT_VARIANT}, final = {final.label})"
    )
    if not has_postseason:
        typer.echo(
            f"  NOTE: no postseason rows for {season_i} in either archive; "
            '"final" means through conference championships.'
        )
    typer.echo("wrote: " + ", ".join(p.name for p in written))


@app.command()
def bootstrap(
    config: Annotated[Path, typer.Option(help="Model config TOML.")] = Path("configs/default.toml"),
    season: Annotated[str | None, typer.Option(help="Season; required.")] = None,
    through_week: Annotated[
        str | None, typer.Option(help="Window; blank = latest completed week.")
    ] = None,
    draws: Annotated[
        int | None, typer.Option(help="Draws; blank = [bootstrap].draws.")
    ] = None,
    jobs: Annotated[int, typer.Option(help="Parallel workers. Currently ignored.")] = 4,
    seed: Annotated[
        int | None, typer.Option(help="Root seed; SeedSequence.spawn per draw.")
    ] = None,
    naive_diagnostic: Annotated[
        bool,
        typer.Option(help="Also run the INVALID resample-with-replacement scheme and report it."),
    ] = False,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out"),
) -> None:
    """Bootstrap the ratings into rating AND rank intervals.

    PARAMETRIC ON THE FIXED SCHEDULE, and the correction matters. Report 02 §3.3
    specified "resample games with replacement, refit", and the scaffold's
    docstring copied it. That scheme is invalid here: games are EDGES in the
    schedule graph, not exchangeable observations, and resampling edges can
    disconnect the graph or strand a team with no games - destroying exactly the
    connectivity structure whose uncertainty was being measured. The schedule was
    also fixed years in advance and is not random.

    So the schedule is held fixed and the OUTCOMES are redrawn from the fitted
    model - `m_g ~ Normal(Power_h - Power_a + h*site, sigma^2)` - then refit and
    re-ranked, 1,000 times. Each draw is a complete alternative season on the real
    calendar, and the rank interval is the spread of a team's rank across them.
    Writes rank_intervals.parquet with 90% intervals on rank (all three published
    orderings) and on the Power rating. Publishing "ranked 7th, 90% interval
    4th-13th" every week is the single most honest thing a computer poll can do
    and no major system does it.

    `--naive-diagnostic` runs the INVALID scheme too and reports how often it
    breaks the graph, so the disqualification is a measurement rather than an
    argument (docs/analysis/fresh-eyes-review.md, S3).

    Determinism is a requirement, not a nicety: never np.random.seed; an explicit
    Generator(PCG64(seed)) with per-draw seeds from SeedSequence.spawn, so results
    are identical on 1 core or 16 (report 03 §9.3). `--jobs` is accepted and
    ignored - the draws run sequentially and parallelising them later cannot move
    a published number, which is precisely why the seeding is done this way.

    `cfbpoll rank` already runs this and writes the same file; this verb exists so
    the intervals can be recomputed at a different draw count or seed without
    refitting the poll.
    """
    import json

    from cfbpoll.config import load_config
    from cfbpoll.ingest import windows
    from cfbpoll.ingest.sportsdataverse import load_games
    from cfbpoll.model import bootstrap as bootstrap_mod
    from cfbpoll.model import retro
    from cfbpoll.publish import poll as poll_mod

    if season is None or str(season).strip() == "":
        raise typer.BadParameter("--season is required. Try --season 2023.")
    season_i = int(season)
    cfg = load_config(config)

    games = load_games([season_i], universe=str(cfg["model"]["fit_universe"]))
    plays = _plays_if_needed(cfg, [season_i])
    buckets = windows.season_buckets(games, season_i)
    regular = [b for b in buckets if b.season_type == "regular"]
    week_i = (
        max(b.week for b in regular)
        if through_week is None or str(through_week).strip() == ""
        else int(through_week)
    )
    evaluated = next(b for b in regular if b.week == week_i)
    window = windows.games_through(games, season=season_i, week=week_i, season_type="regular")
    powers = retro.season_power(games, season_i, cfg, plays=plays, buckets=buckets)
    classes = poll_mod.team_classes(games)

    draw_set = bootstrap_mod.run(
        window,
        powers[evaluated.order],
        cfg,
        classes=classes,
        draws=draws,
        seed=seed,
    )
    table = bootstrap_mod.intervals(draw_set, float(cfg["bootstrap"]["interval"])).sort("team")

    out.mkdir(parents=True, exist_ok=True)
    table.write_parquet(out / "rank_intervals.parquet")
    table.write_csv(out / "rank_intervals.csv")
    typer.echo(
        f"{draw_set.n_draws} parametric draws on the fixed {season_i} schedule through "
        f"{evaluated.label} (seed {draw_set.seed}, sigma {draw_set.sigma:g}, "
        f"lambda {draw_set.lam:g}, jobs requested {jobs} / used 1)"
    )
    typer.echo(f"  {draw_set.note}")
    if naive_diagnostic:
        report = bootstrap_mod.naive_resample_diagnostic(window, draws=draw_set.n_draws)
        (out / "naive_resample_diagnostic.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        typer.echo(
            "  the INVALID scheme, measured: "
            f"{report['fraction_broken_either_way']:.1%} of draws disconnect the graph or "
            f"strand a team (largest component {report['mean_largest_component_share']:.1%} "
            "of teams on average)"
        )
    typer.echo(f"wrote: {(out / 'rank_intervals.parquet').name}, rank_intervals.csv")


@app.command()
def guard(
    season: Annotated[str | None, typer.Option(help="Season; blank = current.")] = None,
    week: Annotated[str | None, typer.Option(help="Week; blank = from /calendar.")] = None,
    trigger: Annotated[
        str, typer.Option(help="Which clock is asking: manual, n8n, schedule, vps_timer.")
    ] = "manual",
    fixtures: Annotated[
        Path | None, typer.Option(help="Published fixture tree to check on disk.")
    ] = None,
    published_url: Annotated[
        str | None, typer.Option(help="Base URL of the published tree, e.g. https://.../data.")
    ] = None,
    arming: Annotated[
        Path | None, typer.Option(help="Arming switch. Default: ops/arming.toml.")
    ] = None,
    resolve_week: Annotated[
        bool, typer.Option(help="Resolve the live week from CFBD /calendar. Costs one call.")
    ] = True,
    outputs: Annotated[
        Path | None,
        typer.Option(help="Append key=value lines here. Default: $GITHUB_OUTPUT when set."),
    ] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Print the decision as JSON.")] = False,
) -> None:
    """Idempotency guard: may this trigger run, and is this week already published?

    Prints `already_published=`, `armed=`, `should_run=`, the resolved season and
    week and where the evidence came from to $GITHUB_OUTPUT when it is set, and
    to stdout always. **It exits 0 whatever it decides**, because "no, and
    correctly so" is the expected answer on most Sundays and a guard that paints
    the build red for it is a guard somebody will mute.

    This is what lets three independent triggers - the n8n dispatch, the
    `schedule:` third string and the VPS systemd timer - share one job without
    ever double-publishing (ADR 0002).

    THE ONE STEP THAT NEEDS A SECRET IS HERE. Resolving "the current live week"
    means GET /calendar, which needs CFBD_API_KEY. Without a key, pass `--week`
    or accept `week_source=unresolved` and `should_run=false`; the guard says
    which happened rather than inventing a week number.
    """
    from cfbpoll.ops import guard as guard_ops

    decision = guard_ops.decide(
        trigger=trigger,
        season=season,
        week=week,
        fixtures=fixtures,
        published_url=published_url,
        arming=guard_ops.load_arming(arming),
        resolve_week=resolve_week,
    )
    written = guard_ops.write_github_output(decision, outputs)

    if json_out:
        typer.echo(guard_ops.as_json(decision))
    else:
        for key, value in decision.as_outputs().items():
            typer.echo(f"{key}={value}")
        typer.echo("")
        for note in decision.notes:
            typer.echo(f"  - {note}")
        typer.echo("")
        typer.echo(
            "SHOULD RUN" if decision.should_run else "NO-OP: the job will do nothing and exit 0"
        )
    if written is not None:
        typer.echo(f"(also appended to {written})")


@app.command()
def preflight(
    required_only: Annotated[
        bool, typer.Option(help="Check only the steps the weekly job cannot skip.")
    ] = True,
    fail_on_missing: Annotated[
        bool, typer.Option(help="Exit non-zero if a required verb is still a stub.")
    ] = False,
) -> None:
    """Which verbs the Sunday job calls are still stubs? Read off the source.

    The weekly job runs eleven verbs and this repository is a partial build, so
    some of them raise NotImplementedError. Discovering that forty minutes and
    0.55 GB into an unattended run - and reporting it as "step 7 failed" rather
    than "these three commands do not exist yet" - is the kind of failure report
    that costs a Sunday. So the job asks first.

    The answer is derived from `cli._stub`'s marker in each command body, never
    from a hand-kept list, so implementing a verb turns its row green with no
    second edit anywhere.
    """
    from cfbpoll.ops import preflight as pre

    rows = pre.report(required_only=required_only)
    typer.echo(f"{'verb':<20}{'required':>10}{'built':>8}  note")
    for row in rows:
        typer.echo(
            f"{row['verb']:<20}{'yes' if row['required'] else 'no':>10}"
            f"{'yes' if row['implemented'] else 'NO':>8}  {row['note']}"
        )
    gaps = [row["verb"] for row in rows if not row["implemented"]]
    typer.echo("")
    if not gaps:
        typer.echo("every checked verb is implemented.")
        return
    typer.echo(f"{len(gaps)} verb(s) still stubbed: {', '.join(gaps)}")
    typer.echo("The Sunday job cannot complete a publication until these are real.")
    if fail_on_missing:
        raise typer.Exit(code=1)


@app.command()
def canonicalize(
    src: Annotated[Path, typer.Argument(help="Directory of model output to canonicalize.")],
    to: Annotated[Path, typer.Option("--to", help="Destination CSV.")] = Path("canonical.csv"),
) -> None:
    """Emit a canonical, hashable CSV of a run's output.

    WILL DO: sort by an explicit key and format floats as %.10g into one CSV.
    Parquet embeds a `created_by` writer-version string, so two byte-identical
    datasets can produce different file bytes - therefore the golden fixtures in
    data/manifests/golden/ hash THIS, not the parquet (report 03 §9.3 item 4).
    """
    _stub("canonicalize", "report 03 §9.3")


# --------------------------------------------------------------------------- publish


@publish_app.command("release")
def publish_release(
    from_: Annotated[
        Path, typer.Option("--from", help="Run directory to publish.")
    ] = Path("out"),
    out: Annotated[
        Path | None,
        typer.Option(
            help="Where the bundle is staged; blank = <--from>/release. Keep it out of "
            "a directory `publish fixtures --from` scans: a staged bundle carries a "
            "poll.json and would be mistaken for a run."
        ),
    ] = None,
    tag: Annotated[
        str | None,
        typer.Option(help="Release tag; blank = poll-{season}-w{NN} from the run record."),
    ] = None,
    repo: Annotated[
        str, typer.Option(help="owner/name that owns the release.")
    ] = "vyhlidal/cfb-poll",
    fixtures: Annotated[
        Path | None,
        typer.Option(help="Published JSON tree to attach, e.g. site/_data/2023."),
    ] = None,
    cards: Annotated[
        Path | None, typer.Option(help="Share-card directory to attach, e.g. out/share.")
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Build and verify the bundle. No network, no gh, nothing published.",
        ),
    ] = False,
) -> None:
    """Publish a run as an immutable GitHub Release (the canonical copy).

    Creates tag `poll-{season}-w{NN}` and attaches every artifact the run wrote,
    plus whatever `--fixtures` and `--cards` point at, plus `SHA256SUMS` and a
    `manifest.json` carrying the sha256, byte count and provenance of each one.
    Release assets are the right transport because they carry no bandwidth
    restriction, where Git LFS bills the repo OWNER for every fork's downloads
    (report 03 §5.2, ADR 0003).

    IMMUTABLE MEANS IMMUTABLE. If the tag already exists this refuses and exits
    non-zero. It never edits a release, never re-uploads over an asset, and has
    no --force. A corrected week is a NEW tag - the same rule that makes
    cfb_poll_published append-only (ADR 0004), for the same reason: a published
    number that can be quietly rewritten is not a published number.

    ONLY THE HOUSE RECIPE gets the derived tag. An alternate lens (ADR 0011) must
    be given an explicit --tag, because publishing a different value system to
    the URL every downstream reader treats as THE poll for that week would be a
    silent substitution.

    `--dry-run` BUILDS THE REAL BUNDLE and verifies every staged byte against the
    manifest it just wrote, with no network and no `gh`. It is not a rehearsal:
    the manifest is a pure function of the run directory, so the bytes it
    produces are the bytes that would be published, and staging the same run
    twice produces an identical manifest.
    """
    from cfbpoll.publish import release as release_mod

    bundle, url = release_mod.publish(
        from_,
        tag,
        repo=repo,
        dest=out,
        fixtures=fixtures,
        cards=cards,
        dry_run=dry_run,
    )
    manifest = bundle.manifest
    typer.echo(
        f"{bundle.tag}: {manifest['asset_count']} assets, {bundle.total_bytes:,} bytes, "
        f"recipe {manifest['recipe']}"
        + ("  [PROVISIONAL WEEK]" if manifest["provisional"] else "")
    )
    for asset in bundle.assets:
        typer.echo(f"  {asset.sha256[:16]}  {asset.bytes:>12,}  {asset.name}")
    if bundle.missing:
        typer.echo(
            f"  not in this run and therefore not published: {', '.join(bundle.missing)}"
        )
    typer.echo(f"staged: {bundle.directory}")
    typer.echo(f"manifest: {bundle.manifest_path.name} sha256 {bundle.manifest_sha256()}")
    if dry_run:
        typer.echo(
            "DRY RUN: nothing was published and nothing on the network was contacted, "
            f"so whether {repo}@{bundle.tag} already exists is UNKNOWN here. The real "
            "run checks it before it uploads and refuses rather than overwriting."
        )
        return
    typer.echo(f"published: {url}")


@publish_app.command("postgres")
def publish_postgres(
    from_: Annotated[
        Path, typer.Option("--from", help="Model output directory to load from.")
    ] = Path("out"),
    backtest: Annotated[
        Path | None,
        typer.Option(help="Gate metrics JSON. Default: <from>/backtest_metrics.json"),
    ] = None,
    database_url: Annotated[
        str | None, typer.Option(help="Postgres URL. Default: $DATABASE_URL, then $POSTGRES_URL.")
    ] = None,
    create: Annotated[
        bool, typer.Option(help="Run CREATE TABLE IF NOT EXISTS before loading.")
    ] = True,
) -> None:
    """Load the serving subset into Postgres. Idempotent; safe to re-run.

    Writes the cfb_* tables of report 03 §5.6 - and ONLY the serving subset
    (§5.4). The full retroactive grid and the bootstrap draws stay in parquet;
    Postgres is a cache that can be dropped and rebuilt, never the source of
    truth. cfb_poll_published is append-only: never UPDATE, never DELETE, and the
    first publication of a (season, week, rank) wins forever.

    Idempotent because `run_id` is a uuid5 over the season, the week, the git
    sha, the config hash and the archive hash - so re-running against the same
    out/ hits the same primary keys and converges, while a run after a code
    change writes a genuinely new run and keeps the old one.

    SKIPS CLEANLY WHEN DATABASE_URL IS UNSET, because a fork has no database and
    must still produce a ranking. That is a success, not an error, and it says so.
    """
    from cfbpoll.publish import postgres

    resolved = backtest if backtest is not None else (from_ / "backtest_metrics.json")
    written = postgres.load(
        from_,
        database_url=database_url,
        backtest=resolved if resolved.exists() else None,
        create=create,
    )
    if not written:
        typer.echo(
            "no DATABASE_URL (or POSTGRES_URL) set - skipped the Postgres load. "
            "The files in "
            f"{from_} are the source of truth and are unaffected; a fork with no "
            "database is fully supported (report 03 §5.4)."
        )
        return
    total = sum(written.values())
    typer.echo(f"loaded {total} rows into {len(written)} cfb_* tables:")
    for table, count in sorted(written.items()):
        typer.echo(f"  {table:<24}{count:>8}")


@publish_app.command("fixtures")
def publish_fixtures(
    out: Annotated[
        Path, typer.Option(help="Destination directory for the JSON fixture set.")
    ] = Path("site/_data"),
    from_: Annotated[
        Path, typer.Option("--from", help="Model output directory to export.")
    ] = Path("out"),
    backtest: Annotated[
        Path | None,
        typer.Option(help="Gate metrics JSON. Default: <from>/backtest_metrics.json"),
    ] = None,
    index_only: Annotated[
        bool, typer.Option("--index-only", help="Rebuild index.json and divergence.json only.")
    ] = False,
) -> None:
    """Export the same serving rows as JSON files. The fork's data source.

    Report 03 §6.3 recommends BOTH publication paths because they serve different
    audiences: Neon is the product surface, and published artifacts are the fork.
    This is the second one. A forker with no database gets a website with every
    real number in it, and the sandbox app in local development renders live data
    with POSTGRES_URL unset.

    Identical documents to `publish postgres`, from the identical builder in
    publish/serving.py, so the site's loader cannot tell which backend it is
    talking to and no page can work against one and quietly break against the
    other.

    IDEMPOTENT AND INCREMENTAL: exporting week 7 rewrites week 7's four documents
    and rebuilds the two season-level files from whatever is already on disk. Run
    it fifteen times, or twice for the same week; it converges.

    `--from` TAKES EITHER ONE RUN OR A DIRECTORY OF THEM. The site reads a whole
    season, so publishing it used to mean looping a shell over fifteen run
    directories by hand — a procedure that lives in a terminal history, which is
    to say a procedure nobody can review or repeat. Point `--from` at the parent
    and this command does the loop, so the command that produces the published
    tree is one line somebody can write down.
    """
    from cfbpoll.publish import fixtures

    if index_only:
        written = fixtures.rebuild_index(out)
        typer.echo(f"rebuilt: {', '.join(str(p.relative_to(out)) for p in written)}")
        return

    runs = fixtures.run_directories(from_)
    resolved = backtest if backtest is not None else (from_ / "backtest_metrics.json")
    explicit = resolved if resolved.exists() else None
    # ALWAYS say how many runs were found. `--from out` publishes ONE week when
    # out/ is a run and fifteen when it is a season of them, and an operator who
    # cannot see which happened is one silent no-op away from a stale site.
    typer.echo(
        f"{len(runs)} run{'' if len(runs) == 1 else 's'} under {from_}: "
        + ", ".join(r.name for r in runs)
    )
    if len(runs) > 1:
        written = fixtures.export_all(from_, out, backtest=explicit)
    else:
        written = fixtures.export(runs[0], out, backtest=explicit)
    if resolved is None or not resolved.exists():
        typer.echo(
            "note: no backtest_metrics.json found, so the methodology page will say the "
            "gate has not been evaluated for this run rather than inventing one. "
            "Run `cfbpoll backtest` first to fill it."
        )
    typer.echo(f"wrote {len(written)} files to {out}:")
    for path in written:
        typer.echo(f"  {path.relative_to(out)}")


@publish_app.command("variants")
def publish_variants(
    out: Annotated[
        Path, typer.Option(help="Destination tree. The published poll must already be in it.")
    ] = Path("site/_data"),
    from_: Annotated[
        Path,
        typer.Option("--from", help="Directory of variant runs, one subdirectory per week."),
    ] = Path(".cache/variants/runs"),
    variant: Annotated[
        str, typer.Option(help="Which variant these runs are. One of `cfbpoll publish variants`.")
    ] = "",
) -> None:
    """Publish one variant's weeks as THIN ORDERING DOCUMENTS (the knob playground).

    A variant is the published poll with ONE constant moved and every other left
    alone, so a reader can find out which of this project's constants decide the
    ranking and which are conventions. Each document carries the top 40 rows,
    eleven columns, and an agreement block whose `verdict` is the word `dial` or
    `convention`, chosen here against the 0.985 Kendall's tau line ADR 0006 fixed
    - never by the page, which does not compute.

    IT WRITES ONLY `<season>/variants/<id>/`. No index is rebuilt, no divergence
    curve is written and the published poll is not touched, so this composes with
    `publish fixtures` and neither overwrites the other. The house week must
    already be on disk: a variant is defined as a difference from the house board
    and there is nothing to compare against without one.
    """
    import json

    from cfbpoll.publish import fixtures
    from cfbpoll.publish import variants as variants_mod

    if not variant:
        raise typer.BadParameter(
            "--variant is required. A run directory does not say which knob produced "
            "it in a form this command should trust, and filing a variant under the "
            "wrong id would publish a tau attributed to the wrong constant. Known: "
            + ", ".join(v.id for v in variants_mod.VARIANTS)
        )
    try:
        chosen = variants_mod.by_id(variant)
    except KeyError as error:
        raise typer.BadParameter(str(error)) from error

    runs = fixtures.run_directories(from_)
    typer.echo(
        f"{len(runs)} run{'' if len(runs) == 1 else 's'} under {from_} for "
        f"variant {chosen.id!r} ({chosen.axis} = {chosen.value})"
    )
    written = [variants_mod.export(run, out, chosen) for run in runs]
    for path in written:
        payload = json.loads(path.read_text(encoding="utf-8"))
        agree = payload["agreement"]
        typer.echo(
            f"  {path.relative_to(out)}  {path.stat().st_size:>6,d} B  "
            f"tau={agree['kendall_tau_vs_house']:.4f}  "
            f"moved>=5: {agree['n_moved_5_or_more']:>3d}  {agree['verdict'].upper()}"
        )


@publish_app.command("lever-grid")
def publish_lever_grid(
    out: Annotated[
        Path, typer.Option(help="Destination tree. The published poll must already be in it.")
    ] = Path("site/_data"),
    from_: Annotated[
        Path,
        typer.Option("--from", help="Directory of runs for ONE cell, one subdirectory per week."),
    ] = Path(".cache/lever-grid/runs"),
    cell: Annotated[
        str, typer.Option(help="Which grid cell these runs are, e.g. `c-32-bw-7-odds`.")
    ] = "",
    manifest: Annotated[
        bool,
        typer.Option(
            "--manifest",
            help="Write the manifest from what is on disk instead of publishing a cell.",
        ),
    ] = False,
    season: Annotated[
        int, typer.Option(help="Season, for --manifest only. Ignored otherwise.")
    ] = 0,
) -> None:
    """Publish one LEVER GRID cell's weeks, or (with --manifest) the grid's index.

    The grid is every combination of three published levers, precomputed, so a
    reader can move them and see a real alternative poll instantly. The site does
    not compute: every board here came out of this `cfbpoll rank`, which is what
    keeps the comparison with the published poll checkable. Contract:
    docs/fixture-contract-levers.md.

    TWO MODES, AND THE MANIFEST IS THE SECOND ONE ON PURPOSE. A manifest is a
    statement about the WHOLE grid, so writing it once per cell would produce
    seventy-two manifests, seventy-one of which described a grid that was not
    finished. `make lever-grid` publishes every cell and then writes the manifest
    once, last, and `--manifest` refuses to write at all unless every cell carries
    the week.

    IT WRITES ONLY `<season>/lever-grid/`. No index is rebuilt, no divergence curve
    is written and the published poll is not touched, so this composes with
    `publish fixtures`, `publish variants` and `make recipe-fixtures`, and none of
    them overwrites another's files. The house week must already be on disk: a cell
    is defined as a difference from the house board and there is nothing to compare
    against without one.
    """
    import json

    from cfbpoll.publish import fixtures
    from cfbpoll.publish import lever_grid as grid

    if manifest:
        if not season:
            raise typer.BadParameter("--manifest needs --season. It writes one season's index.")
        path = grid.write_manifest(out, season)
        payload = json.loads(path.read_text(encoding="utf-8"))
        typer.echo(
            f"{path}  {path.stat().st_size:,d} B  "
            f"{payload['n_cells']} cells x weeks {payload['weeks']}"
        )
        labelled = sum(1 for c in payload["cells"] if c["equivalent_to"])
        typer.echo(
            f"  {labelled} cells reproduce an already-published document "
            f"(the poll, two recipes, eight playground variants)."
        )
        return

    if not cell:
        raise typer.BadParameter(
            "--cell is required. A run directory does not say which combination "
            "produced it in a form this command should trust, and filing a board "
            "under the wrong cell would hand a reader a poll they did not ask for. "
            f"There are {len(grid.CELLS)}; the published poll is "
            f"{grid.published_cell().id!r}."
        )
    try:
        chosen = grid.by_id(cell)
    except KeyError as error:
        raise typer.BadParameter(str(error)) from error

    runs = fixtures.run_directories(from_)
    settings = ", ".join(f"{k} = {v}" for k, v in chosen.published_settings.items())
    typer.echo(
        f"{len(runs)} run{'' if len(runs) == 1 else 's'} under {from_} for cell "
        f"{chosen.id!r} ({settings})"
    )
    for run in runs:
        path = grid.export(run, out, chosen)
        payload = json.loads(path.read_text(encoding="utf-8"))
        agree = payload["agreement"]
        verdict = agree["verdict"] or f"{agree['n_knobs_moved']} knobs, no verdict"
        typer.echo(
            f"  {path.relative_to(out)}  {path.stat().st_size:>6,d} B  "
            f"tau={agree['kendall_tau_vs_house']:.4f}  "
            f"moved>=5: {agree['n_moved_5_or_more']:>3d}  {verdict.upper()}"
        )


# --------------------------------------------------------------------------- site


@publish_app.command("cards")
def publish_cards(
    out: Annotated[
        Path, typer.Option(help="Destination directory for the share cards.")
    ] = Path("out/share"),
    from_: Annotated[
        Path, typer.Option("--from", help="Model output directory to render.")
    ] = Path("out"),
    variant: Annotated[
        str,
        typer.Option(
            help="Card variant: connectivity, top5, top10, top25_x, top25_instagram, "
            "projection_top5, projection_top10, projection_top25, projection_grid, "
            "comparison, "
            "comparison_tall, comparison_square, disagreement."
        ),
    ] = "connectivity",
    projection: Annotated[
        Path | None,
        typer.Option(
            help="The published projection.json a projection_* variant draws, and "
            "the board a comparison card puts its own column from. Ignored by the rest."
        ),
    ] = None,
    compare: Annotated[
        Path | None,
        typer.Option(
            help="A comparison spec: the external boards, their ranks and the URL "
            "each was read from. Required by the comparison and disagreement variants."
        ),
    ] = None,
    backtest: Annotated[
        Path | None,
        typer.Option(help="Gate metrics JSON. Default: <from>/backtest_metrics.json"),
    ] = None,
    png: Annotated[bool, typer.Option(help="Also rasterise to PNG.")] = True,
    fetch_logos: Annotated[
        bool,
        typer.Option(
            help="Fetch any school mark missing from .cache/logos/ and pin it in "
            "data/logo-cache-manifest.json. Off renders from whatever is cached."
        ),
    ] = True,
) -> None:
    """Render the weekly share card: SVG in the pipeline, PNG beside it.

    Report 05 §6.1 puts this in the Python job rather than in a Next.js
    `opengraph-image` route for two reasons that decide it: the static fork needs
    the image and an edge-runtime route cannot prerender one, and a share card is
    a published claim that must be frozen at publication like the poll it depicts.

    THE CARDS CARRY REAL SCHOOL MARKS. Report 06 §8.3 said never and the owner
    overturned it: "every social post everywhere uses college logos, we're not
    making T-shirts". The marks are drawn unaltered, for identification, and the
    site carries the disclaimer. What the CI guard enforces now is that a card is
    SELF-CONTAINED: every `<image>` is a `data:` URI over bytes from the pinned
    cache, and an external host in a card SVG still fails the build, because a
    card that hotlinks is a blank square the first time somebody reposts it.

    The SVG is a pure function of (the published documents + the pinned logo
    cache). The one network call is the cache warm, which happens before anything
    is drawn and skips whatever is already on disk. The PNG is deterministic given
    the same renderer and the vendored fonts, which `render_png` pins.
    """
    from cfbpoll.publish import cards

    if variant in cards.COMPARISON_VARIANTS:
        if projection is None or compare is None:
            raise typer.BadParameter(
                f"{variant} draws a published board beside external ones. Pass both "
                "--projection <data root>/<season>/projection.json and --compare "
                "<spec>.json."
            )
        written = cards.export_comparison(
            projection, compare, out, variant=variant, png=png, fetch_logos=fetch_logos
        )
    elif variant in cards.PROJECTION_VARIANTS:
        if projection is None:
            raise typer.BadParameter(
                f"{variant} draws the published projection document. Pass "
                "--projection <data root>/<season>/projection.json."
            )
        written = cards.export_projection(
            projection, out, variant=variant, png=png, fetch_logos=fetch_logos
        )
    else:
        resolved = backtest if backtest is not None else (from_ / "backtest_metrics.json")
        written = cards.export(
            from_,
            out,
            variant=variant,
            backtest=resolved if resolved.exists() else None,
            png=png,
            fetch_logos=fetch_logos,
        )
    for path in written:
        typer.echo(f"wrote {path} ({path.stat().st_size:,} bytes)")


@site_app.command("build")
def site_build(
    from_: Annotated[Path, typer.Option("--from", help="Model output directory.")] = Path("out"),
    to: Annotated[Path, typer.Option("--to", help="Static site output.")] = Path("site/_build"),
) -> None:
    """Build the zero-account static site from published files.

    WILL DO: render a directory of HTML+JSON that opens with
    `python -m http.server` - no Vercel account, no Neon account, no domain.
    Every rendered number must come from a published artifact, and every page must
    show published_at, git_sha and the model constants, beta_w especially
    (report 03 §7.2, report 02 §3.2).
    """
    _stub("site build", "report 03 §7.1, §7.2")


@projection_app.command("ingest")
def projection_ingest(
    seasons: Annotated[
        str, typer.Option(help="Seasons to pull, e.g. '2021-2026' or '2024,2026'.")
    ],
    min_remaining: Annotated[
        int, typer.Option(help="Abort if fewer than this many CFBD calls remain.")
    ] = 200,
) -> None:
    """Pull the offseason facts the Projection runs on. Four calls per season.

    Returning production, the transfer portal, who is coaching, and the AP
    preseason poll - which is a BASELINE and never an input, enforced by
    `PROJECTION_BANNED_PATTERNS` in the leakage audit rather than by anyone
    remembering.

    THE QUOTA GUARD RUNS FIRST, so the job fails before it half-completes, and
    every raw body is archived VERBATIM before it is parsed. `archive/` is
    gitignored: CFBD terms §3 bar republishing raw responses, so these never
    leave this disk. What may be published is analysis derived from them.
    """
    from cfbpoll.projection import offseason

    years = _parse_seasons(seasons)
    result = offseason.pull(years, min_remaining=min_remaining)
    typer.echo(f"pulled {len(years)} season(s) in {result['calls']} calls")
    for season in years:
        sizes = {
            name: len(result.get(f"{name}_{season}") or [])
            for name in ("returning", "portal", "coaches", "rankings")
        }
        typer.echo(f"  {season}: " + "  ".join(f"{k}={v}" for k, v in sizes.items()))


@projection_app.command("fixture")
def projection_fixture(
    to: Annotated[
        Path, typer.Option("--to", help="The site's data root, e.g. ../sandbox/cfb-poll-data.")
    ],
    status: Annotated[
        str, typer.Option(help="'published' renders the table; 'coming' keeps the card dark.")
    ] = "published",
    top_n: Annotated[
        int,
        typer.Option(
            help="How many teams to publish. 0 publishes the whole board, which is "
            "the default: the site renders 25 and the rest are for the reader who "
            "goes looking for a row the copy named."
        ),
    ] = 0,
) -> None:
    """Write `<to>/<season>/projection.json` for the site's projection card.

    The card's contract lives in `src/lib/cfb-poll/projection.ts` and binds this
    command to two rules: the site derives NOTHING, so `projected_wins` ships
    pre-formatted as a string; and `status` is authoritative, so a finished
    projection can sit on disk dark until somebody decides to show it.

    Team marks and logo URLs come from the poll's own machinery, because the
    projection card and the poll table share a page and a school whose colours
    changed between them would read as a bug in whichever one the reader trusts
    less.

    IT FITS, so run it through `make projection-fixture` rather than bare: the
    recipe is an OLS solve and the carried ratings come off the walk-forward L3,
    and the target carries the single-threaded BLAS pin that keeps a reduction
    summing in the same order twice.
    """
    from datetime import UTC, datetime

    from cfbpoll.config import DEFAULT_CONFIG_PATH, config_hash, load_config
    from cfbpoll.projection import publish as projection_publish
    from cfbpoll.publish.files import git_sha
    make_projection = _repo_scripts("make_projection")

    cfg = load_config()
    season = int(cfg["projection"]["target_season"])
    state = make_projection.build()

    document = projection_publish.build(
        state["projection"],
        season,
        cfg,
        # AFFIRMATIVE, AND DASHLESS, both on purpose. Report 08 bans em dashes and
        # "X, not Y" constructions from the front door's visible copy, and this
        # string is printed verbatim as the card's heading. The first version of
        # it broke both rules at once and read as the one sentence somebody else
        # wrote. `_assert_no_em_dash` now catches half of that mechanically; the
        # other half is saying what this IS rather than what it is not.
        headline=(
            f"This is the model's {season} preseason projection, built in August "
            "about a season the poll will go on to measure."
        ),
        basis=(
            "It runs last season's final ratings through a four-term recipe with "
            "every offseason change the model can measure: returning production, "
            "the transfer portal and coaching moves."
        ),
        note=(
            "It is frozen the moment it publishes and is never edited, so when it "
            "turns out to be wrong you can see exactly how wrong and which "
            "offseason assumption did the damage."
        ),
        status=status,
        published_at=datetime.now(UTC).isoformat(timespec="seconds"),
        top_n=(int(top_n) or None),
        # Schedule strength, the median-schedule column and the gloss pair. These
        # are what make the board's ordering checkable rather than assertable: it
        # ranks on projected power and displays wins, and without them a reader
        # cannot tell a deliberate ordering from a broken one.
        strength=state["schedule_strength"],
        contrast=state["contrast"],
        sigma=state["wins"].sigma,
        # The honest result travels WITH the ranking, templated from the numbers
        # the backtest just measured rather than typed. The site prints nothing it
        # did not read out of a file, and "the AP beat us" is exactly the kind of
        # sentence that must not live in a component.
        backtest=state["backtest"]["summary"],
        # THE PROMOTION CAVEAT IS TEMPLATED FROM THE MEASURED CONSTANTS, not from
        # a sentence somebody typed. Before ADR 0014 there were no constants to
        # template it from and the sentence said the bottom of the board was soft;
        # there are now, and it says what the correction is and what it rests on.
        calibration=state["cross_division"],
        # THE PROJECTION'S OWN RECEIPT rather than the poll's, which is what the
        # front door was printing under this board.
        recipe=state["recipe"],
        source_season=int(cfg["projection"]["projection_source_season"]),
        git_sha=git_sha(),
        config_hash=config_hash(DEFAULT_CONFIG_PATH),
    )
    path = projection_publish.write(document, to)
    typer.echo(f"wrote {path} ({len(document['rows'])} rows, status={document['status']})")


@projection_app.command("build")
def projection_build() -> None:
    """Regenerate every Projection artifact under demo/. No network.

    Thin on purpose: `scripts/make_projection.py` is the one place the artifacts
    are produced, so a reader auditing a published number has exactly one file to
    read rather than two implementations to diff.
    """
    make_projection = _repo_scripts("make_projection")

    make_projection.main()


@projection_app.command("chain")
def projection_chain() -> None:
    """Score every season's August projection against what actually happened. No network.

    The accuracy scoreboard that replaced the gate: fit on history, project the
    next season, and count how many of its opening games the projection called
    right, beside the AP's August ballot and beside doing nothing at all. Writes
    `demo/projection-chain.{md,json}` and `demo/levers.json`.
    """
    make_chain = _repo_scripts("make_chain")

    make_chain.main()


@app.command("levers")
def levers_command(
    surface: Annotated[
        str, typer.Option(help="Filter to one product: poll, projection, both, or all.")
    ] = "all",
    as_json: Annotated[bool, typer.Option("--json", help="Emit the registry as JSON.")] = False,
) -> None:
    """Print the lever registry: every knob, in football words, with its evidence.

    A choice only the author can make is not transparency, it is an assertion
    with the source code attached. This prints what a reader is allowed to change,
    what the shipped value is, and what measured it.
    """
    from cfbpoll import levers as registry

    selected = (
        registry.LEVERS
        if surface == "all"
        else registry.for_surface(surface)  # type: ignore[arg-type]
    )
    if as_json:
        document = registry.registry_document()
        keys = {lever.key for lever in selected}
        document["levers"] = [row for row in document["levers"] if row["key"] in keys]
        typer.echo(json.dumps(document, indent=2))
        return

    for lever in selected:
        typer.echo(f"{lever.key}  [{lever.surface}]")
        typer.echo(f"  {lever.label}")
        if lever.is_categorical:
            # A CATEGORICAL LEVER HAS NO RANGE TO PRINT. Printing "range 0 to 2"
            # over three named orderings would invite the reader to ask for 1.5.
            typer.echo(
                f"  one of {', '.join(lever.values)}, default {lever.default}"
            )
        else:
            high = "no limit" if lever.high == float("inf") else f"{lever.high:g}"
            typer.echo(f"  range {lever.low:g} to {high}, default {lever.default:g}")
        typer.echo(f"  {lever.plain}")
        typer.echo(f"  evidence: {lever.evidence}")
        if lever.measured_effect:
            typer.echo(f"  effect:   {lever.measured_effect}")
        typer.echo("")
    for item in registry.registry_document()["untouchable"]:
        typer.echo(f"NOT A LEVER — {item['rule']}")
        typer.echo(f"  {item['detail']}")
        typer.echo("")


@projection_app.command("audit")
def projection_audit(
    season: Annotated[str, typer.Option(help="Season whose games frame is audited.")] = "2025",
    fail_on_banned: Annotated[
        bool, typer.Option(help="Exit non-zero if the separation is violated.")
    ] = False,
) -> None:
    """THE SEPARATION PROOF (ADR 0010). Both products, both deny-lists, one report.

    Runs the ordinary poll audit and hands it the Projection's design matrix as
    well, so one command proves both halves: every poll design matrix rebuilt
    from its allow-list and bit-identical, and the projection design matrix
    rebuilt from ITS allow-list - which allows returning production, the portal,
    coaching change and a prior season's ratings, and still bans human polls and
    third-party fitted models.

    A projection input found anywhere near a poll layer is a violation on sight,
    with no consumption test, because this repository is the only thing that
    writes those columns.
    """
    import json

    from cfbpoll.config import load_config
    from cfbpoll.ingest.plays import load_plays
    from cfbpoll.ingest.sportsdataverse import load_games
    from cfbpoll.projection import recipe
    from cfbpoll.projection import seasons as projection_seasons
    from cfbpoll.validate import leakage

    cfg = load_config()
    source = int(season)
    target = int(cfg["projection"]["target_season"])
    games = load_games([source])
    plays = load_plays([source])

    power = projection_seasons.final_power(games, source, plays, cfg)
    teams = projection_seasons.fbs_teams(games, source)
    design = recipe.build_design(power.ratings, target, teams)

    report = leakage.audit(games, None, cfg, projection_design=design)
    for layer in report.layers:
        mark = "ok " if layer.ok else "FAIL"
        typer.echo(f"  [{mark}] {layer.kind:<10} {layer.layer}")
    typer.echo(json.dumps({"passed": report.passed, "violations": report.violations}, indent=1))
    if fail_on_banned and not report.passed:
        raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
