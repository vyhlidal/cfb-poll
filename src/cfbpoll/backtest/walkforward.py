"""Strict walk-forward evaluation. No exceptions.

Specified by report 02 §5.1.

To predict week N of season S, fit on data through week N-1 of season S ONLY
(plus prior seasons only if a prior-carrying variant is explicitly under test,
and never in the primary system). Any accidental use of future data invalidates
the entire exercise, and it is the single easiest mistake to make when the
estimator is a batch refit - which is exactly why this module owns the slicing
and no model module is allowed to select its own rows. Every rater receives an
already-truncated frame; `tests/property` plants a future game and asserts it
never reaches one.

Evaluation universe: FBS-vs-FBS regular season and conference championships.
FBS-vs-FCS games are reported SEPARATELY (they are easy and inflate accuracy).
Bowls and CFP games are reported separately too (roster chaos, report 02 §3.8).

THE HOLDOUT IS LOCKED. 2025 is a single-shot test (report 02 §5.1) and this
module refuses to touch it unless `unlock_holdout=True` is passed explicitly. No
code path in this repository passes it. If the hyperparameters are ever re-tuned
after seeing 2025, that must be said publicly and the season re-designated.

PUTTING EVERY SYSTEM ON THE POINTS SCALE. Ratings are not comparable across
systems: Elo lives on a 400-point logit scale, win percentage on [0, 1], Colley
on [0, 1] around 0.5, the random walker on a unitless dominance scale, and even
our own L2 ratings are in compressed-response units rather than points, because
the tanh response is not the identity. So each system gets ONE ordinary least
squares fit per week:

    actual_margin ~ a + b * (rating_home - rating_away) + h * site

and predictions come from that. It changes no straight-up number, because SU
accuracy is invariant to a positive affine map; without it, MAE and Brier would
be meaningless for five of the six systems and the baseline table would be
theatre.

That fit uses OUT-OF-SAMPLE games - the walk-forward predictions already made
earlier in the same season - per report 02 §3.3, which prescribes exactly this
for the L3 blend weights. The reason is not pedantry. Fitting the slope on the
training window reads it off games the rater was fit on, so it flatters whichever
system fits its own training data hardest and then over-disperses that system's
out-of-sample predictions. Measured across 2021-2023 it costs L2 0.44 points of
MAE and inverts the ordering against Elo. Before enough out-of-sample games have
accumulated, the training window is the fallback. Either way no future game is
ever touched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from cfbpoll.backtest import baselines, metrics
from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.sportsdataverse import load_games

__all__ = ["HoldoutLocked", "calibrate", "run_backtest", "segment_games", "slice_through"]

#: Fewer training games than this and no week is scored: the calibration would be
#: fitting three parameters to noise.
MIN_CALIBRATION_GAMES = 10


class HoldoutLocked(RuntimeError):
    """Raised when a run would touch a held-out season without --unlock-holdout."""


def slice_through(games: pl.DataFrame, season: int, through_week: int) -> pl.DataFrame:
    """Return exactly the games a week-N fit is allowed to see. Leakage guard.

    A thin, deliberately boring wrapper over `ingest.windows.games_through`, kept
    because report 02 §5.1's guarantee is a property of ONE slicing function and
    this is the name the rest of the package looks for.
    """
    return windows.games_through(games, season=season, week=through_week, season_type="regular")


def segment_games(games: pl.DataFrame) -> pl.DataFrame:
    """Attach the reporting segment of report 02 §5.1.

    fbs_vs_fbs   both FBS, regular season or conference championship - PRIMARY
    fbs_vs_fcs   exactly one FBS participant; easy games that inflate accuracy
    bowl         non-CFP bowls; roster availability is systematically compromised
    cfp          playoff games; rosters intact, stakes maximal
    other        no FBS participant; not reported
    """
    both = (pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs")
    one = (pl.col("home_class") == "fbs") ^ (pl.col("away_class") == "fbs")
    return games.with_columns(
        segment=pl.when(pl.col("game_type") == "cfp")
        .then(pl.lit("cfp"))
        .when(pl.col("game_type") == "bowl_non_cfp")
        .then(pl.lit("bowl"))
        .when(both)
        .then(pl.lit("fbs_vs_fbs"))
        .when(one)
        .then(pl.lit("fbs_vs_fcs"))
        .otherwise(pl.lit("other"))
    )


def _fit_affine(
    delta: np.ndarray, site: np.ndarray, margin: np.ndarray
) -> tuple[float, float, float]:
    """OLS of `margin ~ a + b*delta + h*site`, minimum-norm on a degenerate design.

    The home-team floor has no rating spread at all, so its delta column is
    identically zero; least squares in the minimum-norm sense degrades that to an
    intercept-plus-site model instead of raising.
    """
    if margin.size == 0:
        return (0.0, 0.0, 0.0)
    x = np.column_stack([np.ones_like(delta), delta, site])
    coef, *_ = np.linalg.lstsq(x, margin, rcond=None)
    return (float(coef[0]), float(coef[1]), float(coef[2]))


def rating_deltas(ratings: dict[str, float], games: pl.DataFrame) -> np.ndarray:
    """rating(home) - rating(away) per game. An unseen team is the neutral 0.0."""
    return np.array(
        [
            ratings.get(h, 0.0) - ratings.get(a, 0.0)
            for h, a in zip(games["home_team"].to_list(), games["away_team"].to_list(), strict=True)
        ],
        dtype=np.float64,
    )


def calibrate(
    ratings: dict[str, float],
    train: pl.DataFrame,
) -> tuple[float, float, float]:
    """In-sample fallback calibration, on the training window. See the module
    docstring for why this is the fallback and not the default."""
    if train.is_empty():
        return (0.0, 0.0, 0.0)
    return _fit_affine(
        rating_deltas(ratings, train),
        np.where(train["neutral_site"].to_numpy(), 0.0, 1.0),
        (train["home_points"] - train["away_points"]).to_numpy().astype(np.float64),
    )


@dataclass
class _Calibration:
    """Accumulates a season's out-of-sample (delta, site, margin) triples."""

    delta: list[float] = field(default_factory=list)
    site: list[float] = field(default_factory=list)
    margin: list[float] = field(default_factory=list)

    def add(self, delta: np.ndarray, site: np.ndarray, margin: np.ndarray) -> None:
        self.delta.extend(delta.tolist())
        self.site.extend(site.tolist())
        self.margin.extend(margin.tolist())

    def coefficients(self) -> tuple[float, float, float]:
        return _fit_affine(np.array(self.delta), np.array(self.site), np.array(self.margin))

    def __len__(self) -> int:
        return len(self.margin)


def _predict(
    ratings: dict[str, float],
    test: pl.DataFrame,
    coef: tuple[float, float, float],
) -> np.ndarray:
    a, b, h = coef
    site = np.where(test["neutral_site"].to_numpy(), 0.0, 1.0)
    return a + b * rating_deltas(ratings, test) + h * site


def _ranking(ratings: dict[str, float], teams: set[str]) -> dict[str, int]:
    ranked = sorted((t for t in ratings if t in teams), key=lambda t: (-ratings[t], t))
    return {team: i + 1 for i, team in enumerate(ranked)}


@dataclass
class _Accumulator:
    predicted: list[float] = field(default_factory=list)
    actual: list[float] = field(default_factory=list)


def run_backtest(
    seasons: list[int],
    systems: list[str],
    config: dict[str, Any] | None = None,
    games: pl.DataFrame | None = None,
    unlock_holdout: bool = False,
    first_eval_week: int | None = None,
) -> dict[str, Any]:
    """Walk every season forward and score every system. Returns the metrics tree.

    `unlock_holdout` exists so the single-shot 2025 evaluation is possible ONCE,
    deliberately, by a human typing a flag. Nothing in this repository passes it.
    """
    cfg = config if config is not None else load_config()
    bt = cfg["backtest"]
    sigma = float(cfg["resume"]["sigma"])

    seasons = sorted(int(s) for s in seasons)
    locked = set(int(s) for s in bt["holdout_seasons"])
    trespass = sorted(locked & set(seasons))
    if trespass and bool(bt["holdout_locked"]) and not unlock_holdout:
        raise HoldoutLocked(
            f"season(s) {trespass} are the held-out single-shot test (report 02 §5.1). "
            "The harness will not score them without unlock_holdout=True, and no code "
            "path in this repository passes it. If the hyperparameters are ever "
            "re-tuned after seeing them, say so publicly and re-designate the split."
        )

    canonical = [baselines.resolve(s) for s in systems]
    min_week = int(first_eval_week if first_eval_week is not None else bt["first_eval_week"])
    min_training = int(bt["min_training_games"])

    if games is None:
        games = load_games(seasons, universe=str(cfg["model"]["fit_universe"]))
    games = segment_games(games)

    use_oos = bool(bt.get("calibration_out_of_sample", True))
    min_oos = int(bt.get("calibration_min_out_of_sample_games", 40))
    headline_week = int(cfg["publication"]["headline_start_week"])

    rows: list[dict[str, Any]] = []
    pooled: dict[tuple[str, str, str], _Accumulator] = {}
    churn_rows: list[dict[str, Any]] = []
    final_violations: dict[str, list[dict[str, Any]]] = {s: [] for s in canonical}
    connectivity: list[dict[str, Any]] = []

    for season in seasons:
        season_games = games.filter(pl.col("season") == season)
        buckets = windows.season_buckets(season_games, season)
        previous_rank: dict[str, dict[str, int]] = {}
        calibration: dict[str, _Calibration] = {name: _Calibration() for name in canonical}

        for bucket in buckets:
            if bucket.order == 0:
                continue
            train = windows.games_before(season_games, bucket, buckets)
            if train.height < min_training:
                continue
            if bucket.season_type == "regular" and bucket.week < min_week:
                continue
            test = windows.games_in_bucket(season_games, bucket).filter(
                pl.col("segment") != "other"
            )
            if test.is_empty():
                continue

            train_fbs = train.filter(pl.col("segment") == "fbs_vs_fbs")
            if train_fbs.height < MIN_CALIBRATION_GAMES:
                continue

            fbs_now = set(train.filter(pl.col("home_class") == "fbs")["home_team"].to_list()) | set(
                train.filter(pl.col("away_class") == "fbs")["away_team"].to_list()
            )

            connectivity.append(
                {
                    "season": season,
                    "bucket": bucket.label,
                    "week": bucket.week,
                    "season_type": bucket.season_type,
                    "n_train_games": int(train.height),
                    **baselines.random_walker.schedule_connectivity(train),
                }
            )

            for name in canonical:
                if name == "home_team":
                    ratings: dict[str, float] = {}
                else:
                    ratings = baselines.RATERS[name](train, None, bucket.week)

                pool = calibration[name]
                if use_oos and len(pool) >= min_oos:
                    coef = pool.coefficients()
                    coef_source = "out_of_sample"
                else:
                    coef = calibrate(ratings, train_fbs)
                    coef_source = "training_window"

                in_headline = bucket.season_type != "regular" or bucket.week >= headline_week
                for segment in sorted(test["segment"].unique().to_list()):
                    sub = test.filter(pl.col("segment") == segment)
                    predicted = _predict(ratings, sub, coef)
                    actual = (sub["home_points"] - sub["away_points"]).to_numpy().astype(float)
                    for cut in ("all",) + (("headline",) if in_headline else ()):
                        acc = pooled.setdefault((name, segment, cut), _Accumulator())
                        acc.predicted.extend(predicted.tolist())
                        acc.actual.extend(actual.tolist())
                    if segment == "fbs_vs_fbs":
                        pool.add(
                            rating_deltas(ratings, sub),
                            np.where(sub["neutral_site"].to_numpy(), 0.0, 1.0),
                            actual,
                        )
                        summary = metrics.summarize(predicted, actual, sigma)
                        summary.pop("calibration")
                        rows.append(
                            {
                                "system": name,
                                "season": season,
                                "week": bucket.week,
                                "season_type": bucket.season_type,
                                "bucket": bucket.label,
                                "n_train_games": int(train.height),
                                "calibration_source": coef_source,
                                "calib_intercept": coef[0],
                                "calib_slope": coef[1],
                                "calib_site": coef[2],
                                **summary,
                            }
                        )

                current_rank = _ranking(ratings, fbs_now)
                churn = metrics.rank_churn(previous_rank.get(name), current_rank)
                churn_rows.append(
                    {"system": name, "season": season, "bucket": bucket.label, **churn}
                )
                previous_rank[name] = current_rank

        # Retrodictive pass: fit on the whole season, then count violations over
        # every FBS-vs-FBS game it was fit on (report 02 §2.12, §5.2).
        full = season_games
        season_fbs = full.filter(pl.col("segment") == "fbs_vs_fbs")
        winners = [
            h if hp > ap else a
            for h, a, hp, ap in zip(
                season_fbs["home_team"].to_list(),
                season_fbs["away_team"].to_list(),
                season_fbs["home_points"].to_list(),
                season_fbs["away_points"].to_list(),
                strict=True,
            )
        ]
        losers = [
            a if hp > ap else h
            for h, a, hp, ap in zip(
                season_fbs["home_team"].to_list(),
                season_fbs["away_team"].to_list(),
                season_fbs["home_points"].to_list(),
                season_fbs["away_points"].to_list(),
                strict=True,
            )
        ]
        for name in canonical:
            if name == "home_team":
                continue
            ratings = baselines.RATERS[name](full, None, None)
            final_violations[name].append(
                {"season": season, **metrics.violations(ratings, winners, losers)}
            )

    per_system: dict[str, Any] = {}
    for name in canonical:
        segments: dict[str, Any] = {}
        headline: dict[str, Any] = {}
        for segment in ("fbs_vs_fbs", "fbs_vs_fcs", "bowl", "cfp"):
            for cut, target in (("all", segments), ("headline", headline)):
                acc = pooled.get((name, segment, cut))
                if acc is None or not acc.actual:
                    continue
                target[segment] = metrics.summarize(
                    np.array(acc.predicted), np.array(acc.actual), sigma
                )
        churn = [c for c in churn_rows if c["system"] == name and np.isfinite(c["churn_all"])]
        violations_rows = final_violations.get(name, [])
        per_system[name] = {
            "segments": segments,
            "segments_from_headline_week": headline,
            "rank_churn": {
                "mean_all": float(np.mean([c["churn_all"] for c in churn])) if churn else None,
                "mean_top25": float(np.nanmean([c["churn_top25"] for c in churn]))
                if churn
                else None,
                "by_bucket": churn,
            },
            "retrodictive_violations": violations_rows,
            "retrodictive_violation_rate": (
                float(
                    sum(v["violations"] for v in violations_rows)
                    / sum(v["games"] for v in violations_rows)
                )
                if violations_rows and sum(v["games"] for v in violations_rows)
                else None
            ),
        }
        if "fbs_vs_fbs" in segments:
            per_system[name]["gate"] = metrics.check_gate(segments["fbs_vs_fbs"], cfg["gate"])

    return {
        "protocol": {
            "walk_forward": "fit through bucket N-1 of the same season, predict bucket N",
            "spec": "report 02 §5.1",
            "seasons": seasons,
            "systems": canonical,
            "universe": bt["universe"],
            "first_eval_week": min_week,
            "min_training_games": min_training,
            "sigma": sigma,
            "holdout_seasons": sorted(locked),
            "holdout_touched": bool(trespass),
            "headline_start_week": headline_week,
            "calibration": (
                "per system per week, OLS of actual margin on "
                "[1, rating difference, site], fitted on the out-of-sample "
                "walk-forward predictions already accumulated earlier in the same "
                "season (report 02 §3.3); the training window is the fallback until "
                f"{min_oos} out-of-sample games exist"
            ),
            "calibration_out_of_sample": use_oos,
            "prior_seasons_used": False,
        },
        "systems": per_system,
        "weekly": rows,
        "connectivity": connectivity,
    }


def retro_grid(rater: Any, seasons: list[int], config: dict[str, Any]) -> Any:
    """Compute the full R(N, K) grid: live R(N,N), hindsight R(N,final), and deltas.

    The "biggest retroactive movers" view - who the model was wrong about, in its
    own words, with the number quantified - is the most differentiated thing this
    project can ship, and it costs nothing extra once the grid exists
    (report 02 §3.6). It needs L4, so it is still a stub.
    """
    raise NotImplementedError("backtest.walkforward.retro_grid - needs L4; report 02 §3.6")


def run(rater: Callable[..., Any], seasons: list[int], config: dict[str, Any]) -> Any:
    """Deprecated alias kept so the scaffold's name resolves. Use run_backtest."""
    raise NotImplementedError("backtest.walkforward.run - use run_backtest (report 02 §5.1)")
