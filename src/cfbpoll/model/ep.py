"""Our own expected-points model, and the per-play value L1 regresses on.

THIS MODULE EXISTS BECAUSE OF ONE CONSTRAINT. Report 02 §3.1 specifies L1 as a
ridge on play-level EPA, and the archive ships an `EPA` column that would make
this file unnecessary. That column is a third party's fitted expected-points
model evaluated on our data, and report 01 §5.6 bans black-box inputs. The ban is
not fussiness: the entire claim of this project is that every number is derived
from published rules and public data, and a ranking whose central input is
someone else's unpublished model cannot make that claim. So we fit our own, from
the scoreboard, in about a hundred lines, and publish the whole thing.

The precomputed column is used in exactly one place - `shipped_epa_correlation`,
a DIAGNOSTIC that no fit calls and that names the banned column in its own
signature so nobody can reach it by accident.

THE MODEL, IN FULL. This is the Carter/Romer/Burke next-score construction, the
oldest and most-published expected-points formulation there is.

  1. TARGET. For every play, find the first scoring event at or after it in the
     same scoring segment (first half, second half, or overtime - see below), and
     value it from the perspective of the team with the ball:

         next_score_p = +v  if the team in possession at p scores next
                        -v  if their opponent scores next
                         0  if nobody scores again in the segment

     with v snapped to the published football values {7, 3, 2}: a touchdown is
     worth 7 (the score plus its expected point-after), a field goal 3, a safety
     2. Snapping is what keeps a missed extra point out of an offense's rating.

  2. STATE. EP is a function of `(down, distance bucket, yards to goal)` and
     nothing else. Not the clock, not the score, not the teams. Score and clock
     effects are real, and they are handled where report 02 §3.1 puts them - in
     the garbage-time weights - rather than smuggled into the value of a play.
     Distance buckets are goal-to-go / 1-3 / 4-6 / 7-10 / 11+ from the config.

  3. ESTIMATOR. Cell means, smoothed along the field with a Gaussian kernel and
     then shrunk up a two-level hierarchy:

         EP_global(y)     = kernel-smoothed mean over every snap at yardline y
         EP_down(d, y)    = (n·smooth(d, y) + m·EP_global(y)) / (n + m)
         EP(d, b, y)      = (n·smooth(d, b, y) + m·EP_down(d, y)) / (n + m)

     `m` is one published pseudo-count, the same object as the ridge penalty and
     Colley's +2: a statement about how little a thin cell tells us, identical
     for every cell, containing no team information whatsoever.

  4. PER-PLAY VALUE. The columns are named `our_ep_before` / `our_ep_after` /
     `play_value`, deliberately NOT `ep_before` / `ep_after` / `EPA`, which are
     the archive's own banned columns. A reader of any artifact can tell at a
     glance whose model produced a number, and a test asserts the banned names
     never appear in a frame a fit can see.

         value_p = EP_after - EP_before

     where EP_before is EP at the snap; EP_after is the points scored on the play
     if it scored, the next snap's EP (negated if possession changed) if the
     segment continued, and 0 if the segment ended. Scoring on a non-snap row
     between two snaps - a kickoff-return touchdown - is attributed to nobody,
     which is the same policy as report 02 §3.1's decision to leave special teams
     to the scoreboard.

SCORING SEGMENTS, NOT HALVES. "Next score in the half" is ill-defined in this
feed because its `half` column folds every overtime period into the second half,
which would let a fourth-quarter play's target be an overtime score. Regulation
ends at the end of the fourth quarter and so does the target.

WALK-FORWARD SAFETY, STATED PLAINLY. An EP model is a model, so it is subject to
the same rule as every other: it may only see data the fit is allowed to see.
`[ep].fit_scope` decides:

  "training_window" (DEFAULT) - fit on exactly the plays handed in. The harness
      has already truncated them to weeks <= N-1, so there is NO leakage at all,
      not even into the tune seasons. The cost is one group-by per week, which is
      milliseconds, and a table that moves slightly week to week - which is
      correct, because early in a season we genuinely know less about the value
      of 3rd-and-4 than we do in November.

  "frozen" - fit once on `[ep].frozen_seasons` and reuse. This is the simplest
      thing that works and it is what report 02 Appendix B sketches, but it means
      the 2021-2023 backtest is scored with an EP table that saw all of 2021-2023,
      including the weeks being predicted. That is real leakage. It is small (the
      table is a league-wide field-position curve, not a team-specific quantity)
      but it is not zero, and any number produced under this scope must say so.
      Offered so the choice is visible rather than assumed; not the default.

In production the two scopes converge: the training window at week N of season S
is every game of season S before week N, and constraint 2 forbids reaching back
into season S-1 for anything the model uses.

DETERMINISM. No RNG. Every table is a fixed-shape numpy array built from sorted
group keys; the kernel is a closed-form matrix. Same input, same bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from cfbpoll.config import load_config

__all__ = [
    "MAX_YARDS_TO_GOAL",
    "EPModel",
    "canonical_points",
    "distance_bucket",
    "fit",
    "next_score_targets",
    "play_values",
    "shipped_epa_correlation",
]

#: Yards-to-goal runs 1..99. 100 would be a touchback taken at the goal line and
#: the feed does not produce it as a snap state; 0 is a touchdown, not a state.
MAX_YARDS_TO_GOAL = 99

#: Distance-bucket labels, in table order. Index 0 is goal-to-go, which is not a
#: distance at all but a different kind of state: on 3rd-and-goal from the 2 the
#: value of a first down and the value of a touchdown are the same thing.
BUCKET_LABELS: tuple[str, ...] = ("goal_to_go", "1-3", "4-6", "7-10", "11+")

LAYER = "EP expected points"
VERSION = "v1"


def canonical_points(delta: np.ndarray, td: float, fg: float, safety: float) -> np.ndarray:
    """Snap a scoreboard change to a published football point value.

    The scoreboard says 6, 7, 8 or (with a defensive two-point return) 9 for the
    touchdown family, 3 for a field goal, 2 for a safety. Snapping to one value
    per family keeps kicker variance and two-point-conversion strategy out of an
    offense's efficiency rating, which is what the rating is trying not to be
    about. The thresholds are midpoints and the rule is one line:

        |d| >= 5.5      -> touchdown value
        2.5 <= |d| < 5.5 -> field goal value
        0 < |d| < 2.5    -> safety value

    0.9% of scoring rows across 2021-2023 exceed a single score's value because
    the feed's scoreboard skipped a row and the monotone repair collapsed two
    events into one (docs/data-findings.md §12). Those land on the touchdown
    value, which is the closest true statement available.
    """
    d = np.asarray(delta, dtype=np.float64)
    magnitude = np.abs(d)
    value = np.where(
        magnitude >= 5.5,
        td,
        np.where(magnitude >= 2.5, fg, np.where(magnitude > 0.0, safety, 0.0)),
    )
    return np.sign(d) * value


def distance_bucket(distance: pl.Expr, yards_to_goal: pl.Expr, edges: list[int]) -> pl.Expr:
    """Bucket index for the EP table. 0 is goal-to-go; the rest are `edges`.

    Goal-to-go is decided by the state, not by a flag: if a first down and the
    goal line are the same place, the down is goal-to-go.
    """
    expr = pl.when(distance >= yards_to_goal).then(0)
    for i, edge in enumerate(edges):
        expr = expr.when(distance <= edge).then(i + 1)
    return expr.otherwise(len(edges) + 1).cast(pl.Int32)


def next_score_targets(plays: pl.DataFrame, config: dict[str, Any] | None = None) -> pl.DataFrame:
    """Attach `next_score`: the next scoring event, signed to the team with the ball.

    `plays` must be the JOINED frame (`ingest.plays.attach_games`), because
    `points_scored` is rebuilt there off the scoreboard - the feed's own
    `score_pts` column is unusable (docs/data-findings.md §12).

    The scan is a backward fill within (game_id, score_segment) over the rows
    that scored, which is exactly "the first scoring event at or after this row";
    a row that scores is its own next score. A segment with no further scoring
    yields 0, which is the correct expectation and not a missing value.
    """
    cfg = config if config is not None else load_config()
    pts = cfg["ep"]

    df = plays.sort(["game_id", "play_index"])
    snapped = canonical_points(
        df["points_scored"].to_numpy(),
        float(pts["touchdown_points"]),
        float(pts["field_goal_points"]),
        float(pts["safety_points"]),
    )
    df = df.with_columns(scored=pl.Series(snapped, dtype=pl.Float64))

    # The scoring TEAM, not the scoring side: `points_scored` is signed to the
    # offense of the row it happened on, and the row we are valuing may have a
    # different offense.
    df = df.with_columns(
        _event_team=pl.when(pl.col("scored") > 0)
        .then(pl.col("offense"))
        .when(pl.col("scored") < 0)
        .then(pl.col("defense"))
        .otherwise(None),
        _event_points=pl.when(pl.col("scored") != 0).then(pl.col("scored").abs()).otherwise(None),
    )
    df = df.with_columns(
        _next_team=pl.col("_event_team").backward_fill().over(["game_id", "score_segment"]),
        _next_points=pl.col("_event_points").backward_fill().over(["game_id", "score_segment"]),
    )
    return df.with_columns(
        next_score=pl.when(pl.col("_next_team").is_null())
        .then(0.0)
        .when(pl.col("_next_team") == pl.col("offense"))
        .then(pl.col("_next_points"))
        .otherwise(-pl.col("_next_points"))
    ).drop("_event_team", "_event_points", "_next_team", "_next_points", "scored")


def _kernel(bandwidth: float, size: int) -> np.ndarray:
    """Row-stochastic Gaussian smoother over yards-to-goal. Pure function of h."""
    grid = np.arange(1, size + 1, dtype=np.float64)
    d = grid[:, None] - grid[None, :]
    return np.exp(-0.5 * (d / float(bandwidth)) ** 2)


@dataclass(frozen=True)
class EPModel:
    """The fitted table, plus everything needed to publish and audit it.

    `table[d, b, y]` is EP for down `d+1`, distance bucket `b`, yards-to-goal
    `y+1`. 4 x 5 x 99 = 1,980 numbers, all of them ours.
    """

    table: np.ndarray
    counts: np.ndarray
    edges: tuple[int, ...]
    bandwidth: float
    shrinkage: float
    n_plays: int
    scope: str
    seasons: tuple[int, ...]
    params: dict[str, Any] = field(default_factory=dict)

    def value(self, down: int, bucket: int, yards_to_goal: int) -> float:
        """EP for one state. Out-of-range states clamp rather than raise: a fit
        must never fall over on a feed oddity in week 9."""
        d = min(max(int(down), 1), 4) - 1
        b = min(max(int(bucket), 0), self.table.shape[1] - 1)
        y = min(max(int(yards_to_goal), 1), MAX_YARDS_TO_GOAL) - 1
        return float(self.table[d, b, y])

    def lookup(self, down: np.ndarray, bucket: np.ndarray, yards_to_goal: np.ndarray) -> np.ndarray:
        """Vectorised `value`. The only form any hot path uses."""
        d = np.clip(np.asarray(down, dtype=np.int64), 1, 4) - 1
        b = np.clip(np.asarray(bucket, dtype=np.int64), 0, self.table.shape[1] - 1)
        y = np.clip(np.asarray(yards_to_goal, dtype=np.int64), 1, MAX_YARDS_TO_GOAL) - 1
        return self.table[d, b, y]

    def as_params(self) -> dict[str, Any]:
        """The model_params.json block. The whole 1,980-cell table is too big for
        a weekly JSON, so what is published here is the shape of it: the first-and-10
        curve at six yardlines, which is the part a reader can check against
        intuition, plus every constant that produced it."""
        first_and_ten = {
            f"1st_and_10_from_{y}": round(self.value(1, 3, y), 4)
            for y in (99, 80, 65, 50, 35, 20, 10)
        }
        return {
            "layer": LAYER,
            "version": VERSION,
            "ep_scope": self.scope,
            "ep_seasons": list(self.seasons),
            "ep_n_plays": self.n_plays,
            "ep_distance_bucket_edges": list(self.edges),
            "ep_kernel_bandwidth_yards": self.bandwidth,
            "ep_shrinkage_prior_plays": self.shrinkage,
            "ep_curve": first_and_ten,
            **self.params,
        }


def fit(plays: pl.DataFrame, config: dict[str, Any] | None = None) -> EPModel:
    """Fit the expected-points table on exactly the plays given. Pure function.

    `plays` is the JOINED frame and is already truncated by the harness: this
    function does no slicing and no week arithmetic, for the same reason no model
    module does (report 02 §5.1).
    """
    cfg = config if config is not None else load_config()
    settings = cfg["ep"]
    edges = [int(e) for e in settings["distance_buckets"]]
    bandwidth = float(settings["kernel_bandwidth_yards"])
    prior = float(settings["shrinkage_prior_plays"])
    n_buckets = len(edges) + 2

    frame = next_score_targets(plays, cfg).filter(pl.col("is_snap"))
    frame = frame.with_columns(
        _bucket=distance_bucket(pl.col("distance"), pl.col("yards_to_goal"), edges)
    )

    sums = np.zeros((4, n_buckets, MAX_YARDS_TO_GOAL), dtype=np.float64)
    counts = np.zeros_like(sums)
    if frame.height:
        agg = frame.group_by(["down", "_bucket", "yards_to_goal"]).agg(
            total=pl.col("next_score").sum(), n=pl.len()
        )
        d = agg["down"].to_numpy().astype(np.int64) - 1
        b = np.clip(agg["_bucket"].to_numpy().astype(np.int64), 0, n_buckets - 1)
        y = agg["yards_to_goal"].to_numpy().astype(np.int64) - 1
        sums[d, b, y] = agg["total"].to_numpy()
        counts[d, b, y] = agg["n"].to_numpy().astype(np.float64)

    kernel = _kernel(bandwidth, MAX_YARDS_TO_GOAL)

    def smooth(numerator: np.ndarray, denominator: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        num = numerator @ kernel.T
        den = denominator @ kernel.T
        mean = np.divide(num, den, out=np.zeros_like(num), where=den > 0)
        return mean, den

    global_mean, _ = smooth(sums.sum(axis=(0, 1)), counts.sum(axis=(0, 1)))
    down_mean, down_n = smooth(sums.sum(axis=1), counts.sum(axis=1))
    cell_mean, cell_n = smooth(sums, counts)

    ep_down = (down_n * down_mean + prior * global_mean[None, :]) / (down_n + prior)
    table = (cell_n * cell_mean + prior * ep_down[:, None, :]) / (cell_n + prior)

    seasons = tuple(sorted(int(s) for s in plays["season"].unique().to_list()))
    return EPModel(
        table=table,
        counts=counts,
        edges=tuple(edges),
        bandwidth=bandwidth,
        shrinkage=prior,
        n_plays=int(frame.height),
        scope=str(settings["fit_scope"]),
        seasons=seasons,
        params={"ep_method": str(settings["method"])},
    )


def play_values(
    plays: pl.DataFrame,
    model: EPModel,
    config: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """Attach `play_value` - our EPA - to every snap. One row per snap, in order.

    Returns only the snaps: a kickoff has no down-and-distance state, so it has
    no expected-points change to attribute, and report 02 §3.1 leaves special
    teams to the scoreboard anyway.
    """
    cfg = config if config is not None else load_config()
    settings = cfg["ep"]
    edges = [int(e) for e in settings["distance_buckets"]]

    snaps = plays.sort(["game_id", "play_index"]).filter(pl.col("is_snap"))
    if snaps.is_empty():
        return snaps.with_columns(
            our_ep_before=pl.lit(0.0, dtype=pl.Float64),
            our_ep_after=pl.lit(0.0, dtype=pl.Float64),
            play_value=pl.lit(0.0, dtype=pl.Float64),
        )

    bucket = distance_bucket(pl.col("distance"), pl.col("yards_to_goal"), edges)
    snaps = snaps.with_columns(_bucket=bucket)
    our_ep_before = model.lookup(
        snaps["down"].to_numpy(), snaps["_bucket"].to_numpy(), snaps["yards_to_goal"].to_numpy()
    )
    snaps = snaps.with_columns(our_ep_before=pl.Series(our_ep_before, dtype=pl.Float64))

    scored = canonical_points(
        snaps["points_scored"].to_numpy(),
        float(settings["touchdown_points"]),
        float(settings["field_goal_points"]),
        float(settings["safety_points"]),
    )
    snaps = snaps.with_columns(_scored=pl.Series(scored, dtype=pl.Float64))

    # The next snap in the same scoring segment. Non-snap rows between the two -
    # kickoffs, timeouts, the end of a quarter - are transitions we do not model,
    # so they are stepped over rather than valued.
    group = ["game_id", "score_segment"]
    snaps = snaps.with_columns(
        _next_ep=pl.col("our_ep_before").shift(-1).over(group),
        _next_offense=pl.col("offense").shift(-1).over(group),
    )
    continuation = (
        pl.when(pl.col("_next_ep").is_null())
        .then(0.0)  # the segment ended; nothing more is expected from it
        .when(pl.col("_next_offense") == pl.col("offense"))
        .then(pl.col("_next_ep"))
        .otherwise(-pl.col("_next_ep"))
    )
    outcome = pl.when(pl.col("_scored") != 0).then(pl.col("_scored")).otherwise(continuation)
    return (
        snaps.with_columns(our_ep_after=outcome)
        .with_columns(play_value=pl.col("our_ep_after") - pl.col("our_ep_before"))
        .drop("_next_ep", "_next_offense", "_scored")
    )


def shipped_epa_correlation(
    valued: pl.DataFrame,
    season: int,
    archive: Any = None,
) -> dict[str, float]:
    """DIAGNOSTIC ONLY. Correlation of our play value with the archive's `EPA`.

    This function reads a banned column. That is the entire reason it is a
    separate, explicitly named, never-called-by-a-fit function whose signature
    says `season` and `archive` rather than taking a frame: there is no way to
    get this number into a design matrix without deleting this docstring first.

    What the number is for: if our expected-points model and the shipped one
    agree closely, the constraint has cost us nothing measurable and we can say
    so with a figure. If they disagree, that is worth knowing and publishing too.
    Either way it is a comparison, never an input (report 02 §3.10).
    """
    from cfbpoll.ingest.plays import DEFAULT_ARCHIVE

    root = DEFAULT_ARCHIVE if archive is None else archive
    path = root / "pbp" / f"play_by_play_{int(season)}.parquet"
    theirs = (
        pl.read_parquet(path, columns=["game_id", "game_row_number", "EPA"])
        .with_columns(pl.col("game_id").cast(pl.Int64), pl.col("game_row_number").cast(pl.Int32))
        .rename({"game_row_number": "play_index", "EPA": "shipped_epa"})
        .unique(subset=["game_id", "play_index"], keep="first")
    )
    joined = (
        valued.filter(pl.col("season") == int(season))
        .select("game_id", "play_index", "play_value")
        .join(theirs, on=["game_id", "play_index"], how="inner")
        .drop_nulls()
    )
    if joined.height < 2:
        return {"n": float(joined.height), "pearson_r": float("nan"), "mean_abs_diff": float("nan")}
    ours = joined["play_value"].to_numpy()
    thm = joined["shipped_epa"].to_numpy()
    return {
        "n": float(joined.height),
        "pearson_r": float(np.corrcoef(ours, thm)[0, 1]),
        "mean_abs_diff": float(np.mean(np.abs(ours - thm))),
        "sd_ours": float(np.std(ours)),
        "sd_theirs": float(np.std(thm)),
    }
