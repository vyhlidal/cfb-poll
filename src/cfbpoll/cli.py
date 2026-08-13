"""The `cfbpoll` command line interface.

Specified by research report 03 §4.6 (the weekly workflow), §9.1 (the one-command
fork story) and §9.2 (the byte-match replay job). Every verb invoked by
.github/workflows/weekly.yml and .github/workflows/reproducibility.yml is defined
here, so that the workflows are a readable specification of the pipeline even
before the pipeline exists.

STATUS: PARTIAL. `rank`, `grid`, `backtest`, `audit-features` and both publish
targets (`publish postgres`, `publish fixtures`) are real and run offline against
the local MIT archive. `rank` publishes the schedule-odds ordering as the
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

from pathlib import Path
from typing import Annotated, Any

import typer

__all__ = ["app"]

_EPILOG = "Docs: docs/methodology.md - Constraints: docs/constraints.md - License: MIT"

app = typer.Typer(
    name="cfbpoll",
    help=(
        "An open, bias-free college football ranking. "
        "PARTIAL BUILD: `rank`, `grid`, `backtest` and `audit-features` work. The "
        "headline poll is the schedule-odds ordering; opponent quality is the L3 "
        "blend of L1 efficiency and L2 results, and the resume is published beside "
        "every team. The remaining commands are stubs and raise NotImplementedError."
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

app.add_typer(ingest_app)
app.add_typer(archive_app)
app.add_typer(publish_app)
app.add_typer(site_app)
app.add_typer(challenge_app)


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
    season: Annotated[str | None, typer.Option(help="Season; blank = current.")] = None,
    week: Annotated[str | None, typer.Option(help="Week; blank = from /calendar.")] = None,
) -> None:
    """Data-quality gate. On failure: halt, alert, publish nothing.

    WILL DO: every assertion in report 01 §5.5 - completed flags and non-null
    scores for every FBS-vs-FBS game, sane week game counts, no team twice, box
    scores reconciling to final scores, bounded week-over-week rating movement,
    a cross-source CFBD-vs-SportsDataverse score diff, and the known-bug guard
    that no December/January game is bucketed into week 1 (game_id 401778314).
    """
    _stub("validate", "report 01 §5.5")


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


@app.command()
def rank(
    config: Annotated[Path, typer.Option(help="Model config TOML.")] = Path("configs/default.toml"),
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

    from cfbpoll.config import load_config
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
    cfg = load_config(config)

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

    table = poll_mod.headline_frame(live, hindsight, interval_table)
    provisional, label = poll_mod.publication_status(week_i, cfg)
    ordering = poll_mod.headline_ordering(cfg)

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
    }
    written = files.write_rank_outputs(
        out, live, hindsight, table, params, run, config_path=config, intervals=interval_table
    )

    saturated = int(table.filter(pl.col("saturated") != 0).height)
    typer.echo(
        f"{schedule_odds.LAYER} {schedule_odds.VERSION} - the headline ordering "
        f"(Power = {params['power_source']} {params['power_version']}) - "
        f"{season_i} through {evaluated.label}: {window.height} games, "
        f"{live.height} teams, {table.height} ranked, "
        f"lambda_l2={l2.lam:g} h={power.home_field:.3f}"
        if l2 is not None
        else f"{schedule_odds.LAYER} - {season_i} through {evaluated.label}"
    )
    typer.echo(
        f"  rank key -log10 P(W >= W_t), q_ref = {odds.q_ref.value:.2f} points"
        + (f" ({odds.q_ref.team})" if odds.q_ref.team else "")
        + f" by {odds.q_ref.method}; margin never enters the key"
    )
    typer.echo(
        f"  {saturated} ranked team(s) saturated at the q bound (*) on the RESUME "
        "column, which is published beside the key and no longer orders the poll "
        "(docs/adr/0005-headline-ordering.md)" + ("  [PROVISIONAL]" if provisional else "")
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
        f"{'#':>3} {'90% int':>9}  {'team':<24}{'-log10P':>9}{'P':>10}{'resume':>9}"
        f"{'power':>8}{'+/-':>6}{'gap':>7}   rec   retro"
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
            f"{row['rank']:>3} {interval}  {row['team']:<24}{row['odds_key']:>9.3f}"
            f"{row['tail_p']:>10.2e}{row['resume']:>8.2f}{mark}"
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
    variant (`.py` exposing `rate(games, plays, through_week)`) is registered as
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
) -> None:
    """Idempotency guard: has this week already been published?

    WILL DO: query cfb_poll_published, print `already_published=true|false` to
    $GITHUB_OUTPUT, and exit 0 either way. This is what lets three independent
    triggers (n8n dispatch, the schedule: fallback, and the VPS systemd timer)
    share one job without ever double-publishing (report 03 §4.1, §4.3).
    """
    _stub("guard", "report 03 §4.1")


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
    out: Annotated[Path, typer.Option(help="Directory to publish.")] = Path("out"),
) -> None:
    """Publish out/ as an immutable GitHub Release asset (the canonical copy).

    WILL DO: create/attach assets on tag `poll-{season}-w{NN}`. Release assets are
    the right transport because they carry no bandwidth restriction, where Git LFS
    bills the repo OWNER for every fork's downloads (report 03 §5.2).
    """
    _stub("publish release", "report 03 §5.2")


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
        str, typer.Option(help="Card variant. Currently: connectivity.")
    ] = "connectivity",
    backtest: Annotated[
        Path | None,
        typer.Option(help="Gate metrics JSON. Default: <from>/backtest_metrics.json"),
    ] = None,
    png: Annotated[bool, typer.Option(help="Also rasterise to PNG.")] = True,
) -> None:
    """Render the weekly share card: SVG in the pipeline, PNG beside it.

    Report 05 §6.1 puts this in the Python job rather than in a Next.js
    `opengraph-image` route for two reasons that decide it: the static fork needs
    the image and an edge-runtime route cannot prerender one, and a share card is
    a published claim that must be frozen at publication like the poll it depicts.

    NO SCHOOL LOGO, EVER (report 06 §8.3). The renderer draws generated marks
    only, fetches nothing, and `tests/unit/test_share_cards.py` fails the build if
    an `<image>` element or an external host ever appears in a card.

    The SVG is a pure function of the published documents on any machine. The PNG
    is deterministic given the same renderer and fonts; resvg resolves the font
    stack against the host, which is stated rather than papered over.
    """
    from cfbpoll.publish import cards

    resolved = backtest if backtest is not None else (from_ / "backtest_metrics.json")
    written = cards.export(
        from_,
        out,
        variant=variant,
        backtest=resolved if resolved.exists() else None,
        png=png,
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


if __name__ == "__main__":  # pragma: no cover
    app()
