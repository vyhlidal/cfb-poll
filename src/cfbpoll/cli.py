"""The `cfbpoll` command line interface.

Specified by research report 03 §4.6 (the weekly workflow), §9.1 (the one-command
fork story) and §9.2 (the byte-match replay job). Every verb invoked by
.github/workflows/weekly.yml and .github/workflows/reproducibility.yml is defined
here, so that the workflows are a readable specification of the pipeline even
before the pipeline exists.

STATUS: SCAFFOLD. `--help` works and is accurate about what each verb WILL do.
Every command raises NotImplementedError when actually invoked. Nothing here
computes, fetches, or publishes anything yet.

Season/week options are typed as strings rather than integers on purpose: GitHub
Actions passes an empty string for an omitted workflow input, and blank means
"resolve the current week from the CFBD /calendar endpoint" (report 01 §3.7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

__all__ = ["app"]

_EPILOG = "Docs: docs/methodology.md - Constraints: docs/constraints.md - License: MIT"

app = typer.Typer(
    name="cfbpoll",
    help=(
        "An open, bias-free college football ranking. "
        "SCAFFOLD BUILD: every command is a stub and raises NotImplementedError."
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

app.add_typer(ingest_app)
app.add_typer(archive_app)
app.add_typer(publish_app)
app.add_typer(site_app)


def _stub(what: str, spec: str) -> None:
    """Fail loudly and honestly. No command may silently pretend to have worked."""
    raise NotImplementedError(
        f"{what} is not implemented yet. This repository is a scaffold. "
        f"Specified by {spec}. See docs/methodology.md for the build order."
    )


# --------------------------------------------------------------------------- ingest


@ingest_app.command("cfbd")
def ingest_cfbd(
    season: Annotated[str | None, typer.Option(help="Season; blank = current.")] = None,
    week: Annotated[str | None, typer.Option(help="Week; blank = from /calendar.")] = None,
    abort_if_remaining_calls_below: Annotated[
        int, typer.Option(help="Quota guard: abort before spending the last N monthly calls.")
    ] = 200,
) -> None:
    """Pull one week from the CFBD REST API (22 chunky calls, quota-guarded).

    WILL DO: the call sequence in report 01 §3.7 in its stated order - GET /info
    first so the job fails fast on quota, GET /calendar to resolve the week so it
    is never hardcoded, then results, detail, aggregates, benchmarks, context.
    Every raw response body is written to the PRIVATE archive unmodified before
    anything parses it (report 01 §5.4). Requires CFBD_API_KEY; a fork without
    one must degrade to the SportsDataverse leg rather than fail.
    """
    _stub("ingest cfbd", "report 01 §3.7")


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


@archive_app.command("sync")
def archive_sync(
    source: Annotated[str, typer.Option(help="sportsdataverse | cfbd")] = "sportsdataverse",
    seasons: Annotated[
        str | None, typer.Option(help="Comma-separated seasons; blank = all in the manifest.")
    ] = None,
    verify: Annotated[
        bool, typer.Option(help="sha256-check every file against the manifest.")
    ] = False,
) -> None:
    """Materialise the raw archive locally from the published release assets.

    WILL DO: download each asset listed in data/manifests/sportsdataverse.lock.json
    (~0.55 GB for 2021-2025) and verify its sha256 BEFORE any consumer reads it.
    A checksum mismatch is a hard failure, not a warning.
    """
    _stub("archive sync", "report 01 §5.4 and report 03 §5.3")


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


@app.command("audit-features")
def audit_features(
    season: Annotated[str | None, typer.Option(help="Season to audit; blank = all.")] = None,
    fail_on_banned: Annotated[
        bool, typer.Option(help="Exit non-zero if a banned column reached a model matrix.")
    ] = False,
) -> None:
    """Poll-input leakage audit. Constraint 1 is easy to violate by accident.

    WILL DO: assert that the columns entering every design matrix are exactly the
    allowed list in report 02 §3.10 (L1: play EPA, offense/defense team id,
    site, quarter, score margin, clock; L2: final score, team ids, site, game
    type; L3: L1+L2 outputs; L4: L3 outputs, win/loss, schedule) and that no
    banned input appears - AP/Coaches/CFP rankings, recruiting or talent
    composites, returning production, prior-season ratings, SP+/FPI, Vegas lines,
    or conference identity. The banned table is reproduced in docs/constraints.md.
    """
    _stub("audit-features", "report 02 §3.10")


@app.command()
def rank(
    config: Annotated[Path, typer.Option(help="Model config TOML.")] = Path("configs/default.toml"),
    season: Annotated[str | None, typer.Option(help="Season; blank = current.")] = None,
    through_week: Annotated[
        str | None, typer.Option(help="Data window K. Blank = latest completed week.")
    ] = None,
    seed: Annotated[int | None, typer.Option(help="Seed for any stochastic step.")] = None,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out"),
) -> None:
    """Fit L1-L4 and write the ratings, the poll, and the run record.

    WILL DO: L1 ridge on garbage-time-filtered play EPA, L2 ridge on compressed
    margin, L3 walk-forward blend, L4 resume root-solve - then write
    ratings_live.parquet, ratings_hindsight.parquet, poll.json/poll.csv,
    model_params.json (every constant, every week) and _run.json (git_sha,
    config_hash, archive_sha) to --out. Report 03 §5.3 fixes those filenames.

    The headline poll is L4 Resume; L3 Power is always published beside it
    (report 02 §3.5). Weeks before configs/default.toml's headline_start_week are
    written as clearly-labelled provisional output, never as "the poll".
    """
    _stub("rank", "report 02 §3.1-§3.5, report 03 §5.3")


@app.command()
def bootstrap(
    draws: Annotated[int, typer.Option(help="Block-bootstrap resamples.")] = 1000,
    jobs: Annotated[int, typer.Option(help="Parallel workers.")] = 4,
    seed: Annotated[
        int | None, typer.Option(help="Root seed; SeedSequence.spawn per draw.")
    ] = None,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out"),
) -> None:
    """Block-bootstrap the ratings into rating AND rank intervals.

    WILL DO: resample games with replacement, refit, and write rank_intervals.parquet
    with 90% intervals on both rating and rank (report 02 §3.3). Publishing
    "ranked 7th, 90% interval 4th-13th" every week is the single most honest thing
    a computer poll can do and no major system does it.

    Determinism is a requirement, not a nicety: never np.random.seed; use an
    explicit Generator(PCG64(seed)) with per-draw seeds from SeedSequence.spawn so
    results are identical on 1 core or 16 (report 03 §9.3).
    """
    _stub("bootstrap", "report 02 §3.3, report 03 §9.3")


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
    out: Annotated[Path, typer.Option(help="Directory to load from.")] = Path("out"),
) -> None:
    """Load the serving subset into Postgres. Idempotent; safe to re-run.

    WILL DO: write the cfb_* tables in report 03 §5.6 - and ONLY the serving
    subset (§5.4). The full retroactive grid and the bootstrap draws stay in
    parquet; Postgres is a cache that can be dropped and rebuilt, never the source
    of truth. cfb_poll_published is append-only: never UPDATE, never DELETE.

    Skips cleanly when DATABASE_URL is unset, because a fork has no database.
    """
    _stub("publish postgres", "report 03 §5.4, §5.6")


# --------------------------------------------------------------------------- site


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
