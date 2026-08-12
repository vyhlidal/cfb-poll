"""The `cfbpoll` command line interface.

Specified by research report 03 §4.6 (the weekly workflow), §9.1 (the one-command
fork story) and §9.2 (the byte-match replay job). Every verb invoked by
.github/workflows/weekly.yml and .github/workflows/reproducibility.yml is defined
here, so that the workflows are a readable specification of the pipeline even
before the pipeline exists.

STATUS: PARTIAL. `rank`, `grid` and `backtest` are real and run offline against
the local MIT archive. `rank` publishes the L4 résumé as the headline, per report
02 §3.5, with opponent quality from the L3 blend of L1 efficiency and L2 results
(`[resume].power_source`); a season with no play archive falls back to L2 and
says so on every artifact. The bootstrap rank intervals and everything else are
still stubs that raise NotImplementedError when invoked - `--help` is accurate
about what each verb WILL do, and no command silently pretends to have worked.

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
        "PARTIAL BUILD: `rank`, `grid` and `backtest` work. The headline poll is "
        "the L4 resume rating; opponent quality is the L3 blend of L1 efficiency "
        "and L2 results. The bootstrap and every other command are stubs and "
        "raise NotImplementedError."
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


def _sha256_or_none(path: Path) -> str | None:
    """sha256 of a file for the run record, or None when it is not there."""
    import hashlib

    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    from cfbpoll.model import l4_resume, retro, schedule_odds
    from cfbpoll.publish import files
    from cfbpoll.publish import poll as poll_mod

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
    powers = retro.season_power(games, season_i, cfg, plays=plays, buckets=buckets)
    power = powers[evaluated.order]
    classes = poll_mod.team_classes(games)
    fitted = l4_resume.fit(window, cfg, power=power)
    odds = schedule_odds.fit(window, cfg, power=power, classes=classes)

    live = retro.cell(games, evaluated, evaluated, cfg, power=power, classes=classes)
    hindsight = retro.cell(games, evaluated, final, cfg, power=powers[final.order], classes=classes)
    table = poll_mod.headline_frame(live, hindsight)
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
        "layers_implemented": (["L1", "L2", "L3", "L4"] if plays is not None else ["L2", "L4"]),
        "layers_missing": ["bootstrap"],
        "seed": seed if seed is not None else cfg["bootstrap"]["seed"],
    }
    run = {
        "season": season_i,
        "through_week": week_i,
        "archive": str(DEFAULT_ARCHIVE),
        "archive_manifest_sha256": _sha256_or_none(DEFAULT_ARCHIVE / "_manifest.json"),
        "n_games_in_fit": int(window.height),
        "n_teams_in_fit": int(live.height),
        "n_ranked_teams": int(table.height),
    }
    written = files.write_rank_outputs(out, live, hindsight, table, params, run, config_path=config)

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
    typer.echo(
        f"{'#':>3}  {'team':<24}{'-log10P':>9}{'P':>10}{'resume':>9}"
        f"{'power':>8}{'gap':>7}   rec   retro"
    )
    for row in table.head(25).iter_rows(named=True):
        mark = "*" if row["saturated"] else " "
        typer.echo(
            f"{row['rank']:>3}  {row['team']:<24}{row['odds_key']:>9.3f}"
            f"{row['tail_p']:>10.2e}{row['resume']:>8.2f}{mark}"
            f"{row['power']:>8.2f}{row['gap']:>7.2f}"
            f"  {row['wins']}-{row['losses']}  {row['rank_delta']:+d}"
        )
    typer.echo("wrote: " + ", ".join(p.name for p in written))


@app.command()
def backtest(
    config: Annotated[Path, typer.Option(help="Model config TOML.")] = Path("configs/default.toml"),
    systems: Annotated[
        str,
        typer.Option(
            help="Comma-separated systems, e.g. resume,l3,l2,l1,colley,srs,elo,walker,winpct."
        ),
    ] = "resume,l3,l2,l1,colley,srs,elo,walker,winpct",
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
    .md §1). For 2021 and 2022 the archive carries NO postseason rows at all, so
    "final" in those seasons means through conference championships - state that
    caveat anywhere those seasons are shown.
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
            else "through conference championships - this season carries NO "
            "postseason rows in cfb_schedules (docs/data-findings.md)"
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
        "archive_manifest_sha256": _sha256_or_none(DEFAULT_ARCHIVE / "_manifest.json"),
        "n_games_in_season": int(games.height),
        "n_grid_rows": int(triangle.height),
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
            f"  NOTE: {season_i} carries no postseason rows in the archive; "
            '"final" means through conference championships.'
        )
    typer.echo("wrote: " + ", ".join(p.name for p in written))


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
