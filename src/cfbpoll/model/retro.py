"""R(N, K) - the two-argument estimator, and the retroactive grid.

Specified by report 02 §3.6. The whole of constraint 4 is this one definition:

    R(N, K) = ratings for evaluation week N, computed from data through week K

    live week N       = R(N, N)
    hindsight week N  = R(N, final)          [variant A, frozen form]

and the substitution that produces it is a single argument to `l4_resume.fit` and
to `schedule_odds.fit`: Power comes from the K window, the record is scored over
each team's games in the N window. Nothing else changes between the two surfaces -
not sigma, not the bracket, not q_ref's method, not the compression constants, not
a line of code. That is what report 02 §3.6 means by "one substitution", and it is
only available because every layer is a batch refit over a SET of games rather
than a sequence. An Elo, SP+'s Bayesian updating and FPI's iterative updating are
all path-dependent; none of them can produce R(5, final) without breaking their
own recursion.

WHAT THE HEADLINE ORDERING CHANGED HERE, on 2026-08-12 (ADR 0005). Every cell now
computes the schedule-odds fit beside the résumé fit, off the identical Power
source and the identical windows, and the cell is ordered and ranked on schedule
odds by default (`[publication].headline_ordering`). The résumé, its margin
variant, its saturation flag and Power all remain columns on every row.

That is not cosmetic for THIS module in particular, because it is what makes the
retroactive product real for the whole league. Under the résumé ordering an
unbeaten team's rating was the published bracket +60, which is not a function of
the schedule and therefore not a function of K, so substituting end-of-season
Power could not move it: `movers` reported 0.00 for every unbeaten team in 2023
from week 11 onward. A tail probability has no such degeneracy, so the movement
this module exists to publish now exists for every team (study §5b, §5c).

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

import numpy as np
import polars as pl

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.model import l4_resume, schedule_odds
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
    "odds_key",
    "tail_p",
    "mid_p",
    "expected_wins",
    "surprise",
    "q_ref",
    "q_ref_team",
    "resume",
    "resume_margin",
    "power",
    "gap",
    "saturated",
)

#: The per-team columns a cell carries, before the (N, K) coordinates are attached.
#: `_cell_frame` builds exactly these and `_label` prepends the rest.
_TEAM_COLUMNS: tuple[str, ...] = tuple(GRID_COLUMNS[11:])


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


def _cell_frame(
    fitted: l4_resume.L4Fit,
    odds: schedule_odds.OddsFit,
    classes: dict[str, str],
    ordering: str,
) -> pl.DataFrame:
    """One team per row: the headline key, the résumé, Power, and the provenance.

    Both fits are read off the SAME Power source over the SAME windows, so a
    difference between the two ranked orders is a difference between ordering
    rules and can never be a difference in data. That is the property the study
    was built on and it survives into the published artifact.

    Ranks go to FBS teams only - the poll is a college football poll - while every
    team in the fit keeps its row and its classification, so the same file supports
    an all-divisions ranking for anyone who wants one (report 02 §7.9).
    """
    teams = sorted(fitted.resume)
    frame = pl.DataFrame(
        {
            "team": teams,
            "team_class": [classes.get(t, "unknown") for t in teams],
            "wins": pl.Series([fitted.wins[t] for t in teams], dtype=pl.Int32),
            "losses": pl.Series([fitted.losses[t] for t in teams], dtype=pl.Int32),
            "odds_key": [odds.key.get(t, 0.0) for t in teams],
            "tail_p": [odds.tail.get(t, 1.0) for t in teams],
            "mid_p": [odds.mid_p.get(t, 1.0) for t in teams],
            "expected_wins": [odds.expected_wins.get(t, 0.0) for t in teams],
            "surprise": [odds.surprise(t) for t in teams],
            "q_ref": [odds.q_ref.value] * len(teams),
            "q_ref_team": [odds.q_ref.team] * len(teams),
            "resume": [fitted.resume[t] for t in teams],
            "resume_margin": [fitted.resume_margin[t] for t in teams],
            "power": [fitted.power.rating(t) for t in teams],
            "gap": [fitted.gap(t) for t in teams],
            "saturated": pl.Series([fitted.saturated[t] for t in teams], dtype=pl.Int8),
        }
    )
    frame = poll_mod.order_by(frame, ordering)
    is_fbs = frame["team_class"] == "fbs"
    ranks = np.full(frame.height, 0, dtype=np.int32)
    ranks[is_fbs.to_numpy()] = np.arange(1, int(is_fbs.sum()) + 1, dtype=np.int32)
    return frame.with_columns(
        rank=pl.when(is_fbs).then(pl.Series(ranks)).otherwise(None).cast(pl.Int32)
    ).select(_TEAM_COLUMNS)


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

    `power` short-circuits the Power fit for the K window, which is how `grid`
    pays for one fit per column instead of one per cell. `classes` and
    `final_order` likewise avoid recomputing something stable; all three are
    pure caches and none of them can change a number.

    Both orderings' numbers are computed here, always. Ranking on one of them is a
    config decision (`[publication].headline_ordering`); computing only one of them
    would make the comparison in docs/analysis/headline-ordering-study.md
    unreproducible from published artifacts, which is not a trade worth the
    microseconds.
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
    team_class = classes or poll_mod.team_classes(season_games)
    fitted = l4_resume.fit(power_window, cfg, power=power, resume_games=resume_window)
    # q_ref is read off the POWER window, which is the K of R(N, K) - so the
    # reference team is the one that was 25th when the data window closed, exactly
    # as the résumé's opponent quality is.
    odds = schedule_odds.fit(
        power_window, cfg, power=power, resume_games=resume_window, classes=team_class
    )
    table = _cell_frame(fitted, odds, team_class, poll_mod.headline_ordering(cfg))
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
    return _finalize(pl.concat(frames, how="vertical"), poll_mod.headline_ordering(cfg))


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
    return _finalize(pl.concat(frames, how="vertical"), poll_mod.headline_ordering(cfg))


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
    return _finalize(pl.concat(frames, how="vertical"), poll_mod.headline_ordering(cfg))


def _finalize(frame: pl.DataFrame, ordering: str) -> pl.DataFrame:
    """Impose the one sort order every writer uses. No other module re-sorts.

    Within each (N, K) cell the rows come out in the published headline order, so
    the file reads top-down as the poll does and `rank` is monotone in it. The rule
    itself lives in `publish/poll.ORDER_KEYS` because it is a publication decision,
    not a modelling one.
    """
    return poll_mod.order_by(
        frame.select(GRID_COLUMNS), ordering, prefix=("eval_order", "data_order")
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

    THE RANKS ARE THE HEADLINE RANKS, so since 2026-08-12 this table finally does
    what report 02 §3.6 advertised for the whole league. Under the wins-based
    résumé an unbeaten team's rating was the published q bound, which does not
    depend on the schedule and therefore does not depend on the data window, so
    every unbeaten team's `rank_delta` was structurally pinned near zero and was
    exactly zero from week 11 of 2023 onward. A tail probability moves, so they
    move (study §5b). `odds_delta` is the headline quantity's own change and
    `resume_delta` is kept beside it, because a row where the two disagree is
    exactly the kind of thing this view exists to surface.
    """
    keep = [
        "eval_order",
        "eval_label",
        "team",
        "rank",
        "odds_key",
        "tail_p",
        "resume",
        "resume_margin",
        "power",
        "gap",
    ]
    a = live.filter(pl.col("rank").is_not_null()).select(keep)
    b = hindsight.filter(pl.col("rank").is_not_null()).select(keep)
    if eval_order is not None:
        a = a.filter(pl.col("eval_order") == eval_order)
        b = b.filter(pl.col("eval_order") == eval_order)

    joined = a.join(b, on=["eval_order", "eval_label", "team"], how="inner", suffix="_hindsight")
    joined = joined.rename(
        {
            "rank": "rank_live",
            "odds_key": "odds_key_live",
            "tail_p": "tail_p_live",
            "resume": "resume_live",
            "resume_margin": "resume_margin_live",
            "power": "power_live",
            "gap": "gap_live",
        }
    ).with_columns(
        # A team that RISES in hindsight has a smaller rank number, so the signed
        # delta is live minus hindsight: positive means "we under-rated them".
        rank_delta=pl.col("rank_live") - pl.col("rank_hindsight"),
        odds_delta=pl.col("odds_key_hindsight") - pl.col("odds_key_live"),
        resume_delta=pl.col("resume_hindsight") - pl.col("resume_live"),
    )
    joined = joined.with_columns(abs_rank_delta=pl.col("rank_delta").abs()).sort(
        ["eval_order", "abs_rank_delta", "odds_delta", "team"],
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
