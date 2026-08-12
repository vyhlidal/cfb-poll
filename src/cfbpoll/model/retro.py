"""R(N, K) - the two-argument estimator, and the retroactive grid.

Specified by report 02 §3.6. The whole of constraint 4 is this one definition:

    R(N, K) = ratings for evaluation week N, computed from data through week K

    live week N       = R(N, N)
    hindsight week N  = R(N, final)          [variant A, frozen form]

and the substitution that produces it is a single argument to `l4_resume.fit`:
Power comes from the K window, the resume is solved over each team's games in
the N window. Nothing else changes between the two surfaces - not sigma, not the
bracket, not the compression constants, not a line of code. That is what report
02 §3.6 means by "one substitution", and it is only available because every
layer is a batch refit over a SET of games rather than a sequence. An Elo, SP+'s
Bayesian updating and FPI's iterative updating are all path-dependent; none of
them can produce R(5, final) without breaking their own recursion.

VARIANT A, AND WHY NOT B. Frozen-form hindsight answers "given what we now know
about how good those opponents actually were, how good were the first N weeks of
results?" - which is the plain-English meaning of "week 13 revealed they were
overrated in week 5". Variant B (a time-varying kernel-weighted Power_t(N), i.e.
a state-space model in the Glickman & Stern sense) answers a different and harder
question, "how good was this team in fact at week 5", and report 02 §3.6 defers
it. This module implements A and says so in every artifact.

BUCKETS, NOT WEEK NUMBERS. N and K are (season_type, week) BUCKETS ordered by
first kickoff, per docs/data-findings.md §1 and ingest/windows.py. Week numbering
inside a season is neither monotone nor unique - the 2023 postseason holds week 1
(the 42 bowls) AND weeks 11-15 (the FCS bracket) - so a grid indexed on bare week
numbers would silently mix January into November. The grid's `eval_order` and
`data_order` columns are the ordering that actually governs, and the `*_label`
columns are what a human reads.

THE TRIANGLE IS UPPER TRIANGULAR BY CONSTRUCTION. K >= N always: evaluating week
N with data that stops before week N would mean scoring games the rater has not
seen, which is not hindsight, it is nonsense. `grid` enforces it rather than
trusting callers.

COST. One POWER fit per COLUMN of the grid, not one per cell - the Power fit
depends on K alone. With Power = L3 that is one L1 + one L2 + one blend per
column, and the whole 2023 grid (19 buckets, 190 cells) runs in well under a
minute on a laptop, which is what report 02 §3.11 predicted.

THE BLEND WEIGHTS ARE WALK-FORWARD HERE TOO. Power at column K is the L3 fit
that was live at K, with blend weights fitted on games predicted BEFORE K -
`l3_power.season_power` walks the season once and hands back one fit per bucket.
Fitting the weights on the K window itself would be in-sample, which report 02
§3.3 forbids, and it would quietly make the hindsight surface better than any
live surface could ever have been.

DETERMINISM. Every frame is sorted on an explicit key before it is returned, no
dict or group-by iteration order reaches a file, and there is no RNG anywhere on
this path (report 03 §9.3).
"""

from __future__ import annotations

from typing import Any

import polars as pl

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.model import l4_resume
from cfbpoll.publish import poll as poll_mod

__all__ = [
    "GRID_COLUMNS",
    "HINDSIGHT_VARIANT",
    "cell",
    "grid",
    "hindsight_surface",
    "divergence",
    "live_surface",
    "season_power",
    "movers",
    "movers_by_week",
    "surfaces",
]

#: Stated in every artifact so no reader has to guess which one they are holding.
HINDSIGHT_VARIANT = "A_frozen_form"

GRID_COLUMNS: tuple[str, ...] = (
    "season",
    "eval_order",
    "eval_season_type",
    "eval_week",
    "eval_label",
    "data_order",
    "data_season_type",
    "data_week",
    "data_label",
    "is_live",
    "is_hindsight",
    "rank",
    "team",
    "team_class",
    "wins",
    "losses",
    "resume",
    "resume_margin",
    "power",
    "gap",
    "saturated",
)


def _through(games: pl.DataFrame, bucket: windows.Bucket) -> pl.DataFrame:
    """Every game in the season at or before `bucket`. The one sanctioned slicer."""
    return windows.games_through(
        games, season=bucket.season, week=bucket.week, season_type=bucket.season_type
    )


def _label(
    frame: pl.DataFrame,
    evaluated: windows.Bucket,
    data: windows.Bucket,
    final_order: int,
) -> pl.DataFrame:
    """Attach the (N, K) coordinates and the two surface flags to a résumé table."""
    return frame.with_columns(
        season=pl.lit(evaluated.season, dtype=pl.Int32),
        eval_order=pl.lit(evaluated.order, dtype=pl.Int32),
        eval_season_type=pl.lit(evaluated.season_type),
        eval_week=pl.lit(evaluated.week, dtype=pl.Int32),
        eval_label=pl.lit(evaluated.label),
        data_order=pl.lit(data.order, dtype=pl.Int32),
        data_season_type=pl.lit(data.season_type),
        data_week=pl.lit(data.week, dtype=pl.Int32),
        data_label=pl.lit(data.label),
        is_live=pl.lit(evaluated.order == data.order),
        is_hindsight=pl.lit(data.order == final_order),
    ).select(GRID_COLUMNS)


def cell(
    games: pl.DataFrame,
    evaluated: windows.Bucket,
    data: windows.Bucket,
    config: dict[str, Any] | None = None,
    power: l4_resume.PowerSource | None = None,
    classes: dict[str, str] | None = None,
    final_order: int | None = None,
    plays: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """One R(N, K). `games` is the whole season; this function does the slicing.

    `power` short-circuits the L2 fit for the K window, which is how `grid`
    pays for one fit per column instead of one per cell. `classes` and
    `final_order` likewise avoid recomputing something stable; all three are
    pure caches and none of them can change a number.
    """
    cfg = config if config is not None else load_config()
    if data.order < evaluated.order:
        raise ValueError(
            f"R(N, K) requires K >= N: asked for eval {evaluated.label} with data "
            f"{data.label}, which would score games the rater has not seen"
        )
    season_games = games.filter(pl.col("season") == evaluated.season)
    power_window = _through(season_games, data)
    resume_window = _through(season_games, evaluated)
    if power is None:
        from cfbpoll.ingest.plays import plays_for

        window_plays = None if plays is None else plays_for(plays, power_window)
        power = l4_resume.power_source(power_window, cfg, plays=window_plays)
    fitted = l4_resume.fit(power_window, cfg, power=power, resume_games=resume_window)
    table = l4_resume.resume_frame(fitted, classes or poll_mod.team_classes(season_games))
    if final_order is None:
        final_order = _season_buckets(games, evaluated.season)[-1].order
    return _label(table, evaluated, data, final_order)


def _season_buckets(games: pl.DataFrame, season: int) -> list[windows.Bucket]:
    return windows.season_buckets(games.filter(pl.col("season") == season), season)


def season_power(
    games: pl.DataFrame,
    season: int,
    config: dict[str, Any] | None = None,
    plays: pl.DataFrame | None = None,
    buckets: list[windows.Bucket] | None = None,
) -> dict[int, l4_resume.PowerSource]:
    """bucket.order -> opponent quality for that data window K.

    One entry per COLUMN of the grid. With `[resume].power_source = "L3"` this is
    the walk-forward blend (see the module docstring); with "L2", or with no play
    archive, it is the L2 rating rescaled to points. Either way the résumé math
    downstream is identical - that is report 02 §3.4's whole construction.
    """
    cfg = config if config is not None else load_config()
    all_buckets = buckets if buckets is not None else _season_buckets(games, season)
    season_games = games.filter(pl.col("season") == season)

    if plays is not None and str(cfg["resume"]["power_source"]).upper() == "L3":
        from cfbpoll.model import l3_power

        walk = l3_power.season_power(season_games, plays, season, cfg, buckets=all_buckets)
        return {order: l3_power.power_source_for(f) for order, f in walk.items()}

    return {
        b.order: l4_resume.power_from_l2(_through(season_games, b), cfg) for b in all_buckets
    }


def live_surface(
    games: pl.DataFrame,
    season: int,
    config: dict[str, Any] | None = None,
    buckets: list[windows.Bucket] | None = None,
    plays: pl.DataFrame | None = None,
    powers: dict[int, l4_resume.PowerSource] | None = None,
) -> pl.DataFrame:
    """R(N, N) for every N: the poll as it was published, week by week."""
    cfg = config if config is not None else load_config()
    all_buckets = buckets if buckets is not None else _season_buckets(games, season)
    season_games = games.filter(pl.col("season") == season)
    classes = poll_mod.team_classes(season_games)
    final_order = all_buckets[-1].order
    if powers is None:
        powers = season_power(games, season, cfg, plays=plays, buckets=all_buckets)
    frames = [
        cell(
            season_games,
            b,
            b,
            cfg,
            power=powers[b.order],
            classes=classes,
            final_order=final_order,
        )
        for b in all_buckets
    ]
    return _finalize(pl.concat(frames, how="vertical"))


def hindsight_surface(
    games: pl.DataFrame,
    season: int,
    config: dict[str, Any] | None = None,
    buckets: list[windows.Bucket] | None = None,
    plays: pl.DataFrame | None = None,
    powers: dict[int, l4_resume.PowerSource] | None = None,
) -> pl.DataFrame:
    """R(N, final) for every N: the same weeks, re-scored with the season's answers.

    `final` is the LAST bucket of the season by kickoff order, which for a season
    whose archive carries a postseason means the postseason is in the Power fit
    (non-CFP bowls at their configured weight, CFP games at full weight). For
    2021 and 2022 the archive carries no postseason rows at all, so "final" there
    means through conference championships - a caveat that belongs on any demo
    touching those seasons (docs/data-findings.md).
    """
    cfg = config if config is not None else load_config()
    all_buckets = buckets if buckets is not None else _season_buckets(games, season)
    season_games = games.filter(pl.col("season") == season)
    classes = poll_mod.team_classes(season_games)
    final = all_buckets[-1]
    if powers is None:
        powers = season_power(games, season, cfg, plays=plays, buckets=all_buckets)
    power = powers[final.order]
    frames = [
        cell(season_games, b, final, cfg, power=power, classes=classes, final_order=final.order)
        for b in all_buckets
    ]
    return _finalize(pl.concat(frames, how="vertical"))


def grid(
    games: pl.DataFrame,
    season: int,
    config: dict[str, Any] | None = None,
    buckets: list[windows.Bucket] | None = None,
    plays: pl.DataFrame | None = None,
    powers: dict[int, l4_resume.PowerSource] | None = None,
) -> pl.DataFrame:
    """The full upper-triangular N x K surface, K >= N. One L2 fit per column.

    Report 02 §3.6 asks for both surfaces to be stored for every week of every
    season, "plus the delta", and notes that it costs nothing extra once the grid
    exists. This is that grid; `surfaces` and `movers` are the two views of it the
    report names.
    """
    cfg = config if config is not None else load_config()
    all_buckets = buckets if buckets is not None else _season_buckets(games, season)
    season_games = games.filter(pl.col("season") == season)
    classes = poll_mod.team_classes(season_games)

    if powers is None:
        powers = season_power(games, season, cfg, plays=plays, buckets=all_buckets)

    frames: list[pl.DataFrame] = []
    for data in all_buckets:
        power = powers[data.order]
        for evaluated in all_buckets:
            if evaluated.order > data.order:
                continue
            frames.append(
                cell(
                    season_games,
                    evaluated,
                    data,
                    cfg,
                    power=power,
                    classes=classes,
                    final_order=all_buckets[-1].order,
                )
            )
    return _finalize(pl.concat(frames, how="vertical"))


def _finalize(frame: pl.DataFrame) -> pl.DataFrame:
    """Impose the one sort order every writer uses. No other module re-sorts."""
    return frame.select(GRID_COLUMNS).sort(
        ["eval_order", "data_order", "resume", "resume_margin", "team"],
        descending=[False, False, True, True, False],
    )


def surfaces(grid_frame: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(live, hindsight) pulled out of a computed grid. R(N,N) and R(N,final)."""
    return (
        grid_frame.filter(pl.col("is_live")),
        grid_frame.filter(pl.col("is_hindsight")),
    )


def movers(
    live: pl.DataFrame,
    hindsight: pl.DataFrame,
    eval_order: int | None = None,
    top_n: int | None = None,
) -> pl.DataFrame:
    """|rank(R(N,N)) - rank(R(N,final))| per team: who the model was wrong about.

    Report 02 §3.6 calls this "the most differentiated thing this project can
    ship". It is a join and a subtraction, because the grid already did the work.

    Only ranked (FBS) teams appear: a rank delta is meaningless for a team that
    was never in the poll. `eval_order` restricts to one evaluation week;
    `top_n` keeps the largest absolute moves.
    """
    keep = ["eval_order", "eval_label", "team", "rank", "resume", "resume_margin", "power", "gap"]
    a = live.filter(pl.col("rank").is_not_null()).select(keep)
    b = hindsight.filter(pl.col("rank").is_not_null()).select(keep)
    if eval_order is not None:
        a = a.filter(pl.col("eval_order") == eval_order)
        b = b.filter(pl.col("eval_order") == eval_order)

    joined = a.join(b, on=["eval_order", "eval_label", "team"], how="inner", suffix="_hindsight")
    joined = joined.rename(
        {
            "rank": "rank_live",
            "resume": "resume_live",
            "resume_margin": "resume_margin_live",
            "power": "power_live",
            "gap": "gap_live",
        }
    ).with_columns(
        # A team that RISES in hindsight has a smaller rank number, so the signed
        # delta is live minus hindsight: positive means "we under-rated them".
        rank_delta=pl.col("rank_live") - pl.col("rank_hindsight"),
        resume_delta=pl.col("resume_hindsight") - pl.col("resume_live"),
    )
    joined = joined.with_columns(abs_rank_delta=pl.col("rank_delta").abs()).sort(
        ["eval_order", "abs_rank_delta", "resume_delta", "team"],
        descending=[False, True, True, False],
    )
    return joined.head(top_n) if top_n is not None else joined


def divergence(live: pl.DataFrame, hindsight: pl.DataFrame) -> pl.DataFrame:
    """Mean and max |rank(R(N,N)) - rank(R(N,final))| per evaluation week.

    Report 02 §5.2 lists retro-vs-live divergence as a STABILITY metric and says
    it must decline in N or the retroactive product itself is unstable: the later
    the week, the less the rest of the season can teach us about it, and at
    N = final there is nothing left to learn and the divergence is zero by
    definition. Publishing the curve is how that claim stays falsifiable.
    """
    table = movers(live, hindsight)
    return (
        table.group_by(["eval_order", "eval_label"])
        .agg(
            mean_abs_rank_delta=pl.col("abs_rank_delta").mean(),
            max_abs_rank_delta=pl.col("abs_rank_delta").max(),
            n_teams=pl.len(),
        )
        .sort("eval_order")
    )


def movers_by_week(
    live: pl.DataFrame,
    hindsight: pl.DataFrame,
    buckets: list[windows.Bucket],
    top_n: int = 25,
) -> pl.DataFrame:
    """`movers` for every evaluation week, stacked. The published retro_movers.csv.

    Week 1's bucket is skipped: with one game played, a rank delta is a statement
    about the schedule graph rather than about a team.
    """
    frames = [
        f
        for f in (movers(live, hindsight, eval_order=b.order, top_n=top_n) for b in buckets[1:])
        if f.height
    ]
    if not frames:
        return movers(live, hindsight).head(0)
    return pl.concat(frames, how="vertical")
