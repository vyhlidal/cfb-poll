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
from cfbpoll.ingest.plays import load_plays, plays_for
from cfbpoll.ingest.sportsdataverse import load_games
from cfbpoll.model import design, l3_power

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
    """A season's out-of-sample (delta, site, margin) triples, and its residuals.

    The residuals are what sigma is estimated from (review S6). They are the
    error of the prediction AS IT WAS MADE - stored at prediction time rather
    than recomputed later with the current calibration, because the current
    calibration has since seen the game and the residual would flatter the system
    by exactly the amount sigma is supposed to measure."""

    delta: list[float] = field(default_factory=list)
    site: list[float] = field(default_factory=list)
    margin: list[float] = field(default_factory=list)
    residual: list[float] = field(default_factory=list)

    def add(
        self,
        delta: np.ndarray,
        site: np.ndarray,
        margin: np.ndarray,
        predicted: np.ndarray | None = None,
    ) -> None:
        self.delta.extend(delta.tolist())
        self.site.extend(site.tolist())
        self.margin.extend(margin.tolist())
        if predicted is not None:
            self.residual.extend((margin - predicted).tolist())

    def coefficients(self) -> tuple[float, float, float]:
        return _fit_affine(np.array(self.delta), np.array(self.site), np.array(self.margin))

    def sigma(self, config: dict[str, Any]) -> l3_power.SigmaEstimate:
        """This system's own walk-forward sigma, from everything predicted so far."""
        return l3_power.estimate_sigma(self.residual, config)

    def __len__(self) -> int:
        return len(self.margin)


def _predict(
    ratings: dict[str, float],
    test: pl.DataFrame,
    coef: tuple[float, float, float],
    config: dict[str, Any] | None = None,
) -> np.ndarray:
    """The calibrated points-scale forecast, after `[margin.prediction_compression]`.

    The compression is applied to EVERY system or to none of them, from the same
    config, because a correction that only the home team's rival gets is not a
    comparison. It changes no ranking - it is monotone - and it is applied after
    the affine calibration rather than before, because the thing Pasteur's device
    is about is an extreme number of POINTS, not an extreme rating gap.
    """
    a, b, h = coef
    site = np.where(test["neutral_site"].to_numpy(), 0.0, 1.0)
    raw = a + b * rating_deltas(ratings, test) + h * site
    return raw if config is None else design.compress_prediction(raw, config)


def _cached_ratings(
    name: str,
    train: pl.DataFrame,
    train_plays: pl.DataFrame | None,
    week: int | None,
    cache: dict[str, dict[str, float]],
    state: l3_power.SeasonState | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    """One fit per system per bucket, memoised so a system that predicts through
    another (baselines.prediction_source) does not refit it. The cache is
    per-bucket and every rater receives the identical already-truncated frames.

    `state` is the per-season L3 cache and out-of-sample blend accumulator. It is
    passed to every rater and ignored by every rater that does not need it, which
    keeps one code path rather than a special case for our own layers.

    `config` IS THE HARNESS'S CONFIG, and passing it is not a nicety. Every rater
    used to fall back to `load_config()` when it was not given one, so a backtest
    run under a non-default config - the fit-universe sensitivity of
    docs/analysis/fit-universe-sensitivity.md, the recency sweep in
    docs/analysis/robustness-notes.md - would have silently scored our own layers
    under the DEFAULT constants while claiming to have varied them. Constraint 5
    says the config is the methodology; a harness that fits with a config other
    than the one it was handed is publishing a number about a model nobody ran."""
    if name not in cache:
        cache[name] = baselines.RATERS[name](
            train, train_plays, week, state=state, config=config
        )
    return cache[name]


def _ranking(ratings: dict[str, float], teams: set[str]) -> dict[str, int]:
    ranked = sorted((t for t in ratings if t in teams), key=lambda t: (-ratings[t], t))
    return {team: i + 1 for i, team in enumerate(ranked)}


@dataclass
class _Accumulator:
    predicted: list[float] = field(default_factory=list)
    actual: list[float] = field(default_factory=list)
    #: The sigma that was LIVE when each game was predicted. Pooled segments are
    #: scored with it per game rather than with one number for the whole pool,
    #: because "what did this system believe about its own error when it made
    #: this forecast" is a property of the forecast and not of the bucket it
    #: later lands in.
    sigma: list[float] = field(default_factory=list)


def _pooled_rate(rows: list[dict[str, Any]]) -> float | None:
    """Violations / games pooled over seasons, or None when nothing was scored."""
    played = sum(r["games"] for r in rows)
    return float(sum(r["violations"] for r in rows) / played) if rows and played else None


def _winner_loser(games: pl.DataFrame) -> tuple[list[str], list[str]]:
    """(winners, losers), one entry per game. Ties are impossible (overtime)."""
    home = games["home_team"].to_list()
    away = games["away_team"].to_list()
    hp = games["home_points"].to_list()
    ap = games["away_points"].to_list()
    winners = [h if a_ < h_ else a for h, a, h_, a_ in zip(home, away, hp, ap, strict=True)]
    losers = [a if a_ < h_ else h for h, a, h_, a_ in zip(home, away, hp, ap, strict=True)]
    return winners, losers


def run_backtest(
    seasons: list[int],
    systems: list[str],
    config: dict[str, Any] | None = None,
    games: pl.DataFrame | None = None,
    unlock_holdout: bool = False,
    first_eval_week: int | None = None,
    plays: pl.DataFrame | None = None,
    collect_predictions: bool = False,
) -> dict[str, Any]:
    """Walk every season forward and score every system. Returns the metrics tree.

    `unlock_holdout` exists so the single-shot 2025 evaluation is possible ONCE,
    deliberately, by a human typing a flag. Nothing in this repository passes it.

    `collect_predictions` adds a `predictions` key holding EVERY scored game with
    the margin that was forecast, the margin that happened, and the sigma that was
    live at the moment - the residual-level view. It is off by default because it
    is ~25,000 rows for a three-season ten-system run and `backtest_metrics.json`
    is a published artifact. It exists so that a diagnosis of the calibration miss
    (docs/analysis/tuning-campaign.md) can slice the residuals THE HARNESS ACTUALLY
    PRODUCED rather than reconstructing them in a script that would drift from it.
    """
    cfg = config if config is not None else load_config()
    bt = cfg["backtest"]
    sigma_fallback = float(cfg["resume"]["sigma"])

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

    # The play archive is loaded only when a system asks for it. `resume` asks
    # for it whenever its Power source is L3, because the résumé is only as
    # good as the opponent quality it reads (report 02 §3.4).
    sources = {baselines.prediction_source(name, cfg) for name in canonical}
    needs_plays = bool((set(canonical) | sources) & baselines.PLAY_LEVEL_SYSTEMS)
    if needs_plays and plays is None:
        plays = load_plays(seasons)

    use_oos = bool(bt.get("calibration_out_of_sample", True))
    min_oos = int(bt.get("calibration_min_out_of_sample_games", 40))
    headline_week = int(cfg["publication"]["headline_start_week"])

    rows: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    pooled: dict[tuple[str, str, str], _Accumulator] = {}
    churn_rows: list[dict[str, Any]] = []
    blend_rows: list[dict[str, Any]] = []
    final_violations: dict[str, list[dict[str, Any]]] = {s: [] for s in canonical}
    connectivity: list[dict[str, Any]] = []

    for season in seasons:
        season_games = games.filter(pl.col("season") == season)
        buckets = windows.season_buckets(season_games, season)
        previous_rank: dict[str, dict[str, int]] = {}
        calibration: dict[str, _Calibration] = {name: _Calibration() for name in canonical}
        # ONE blend accumulator per season. Report 02 §3.3 pools the
        # out-of-sample games "across the training seasons", but pooling across
        # seasons inside a walk-forward run would carry information from season
        # S-1 into season S's weights, and constraint 2 forbids prior seasons
        # reaching anything the model uses. Per-season is the strict reading and
        # it is the one implemented; the weights converge within four weeks
        # anyway (see the trajectory in demo/backtest-2021-2023.md).
        blend = l3_power.SeasonState() if needs_plays else None

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

            # The play-level walk-forward slice. `plays_for` inner-joins on the
            # already-truncated game frame, so a play belonging to a future game
            # cannot arrive - tests/property plants one and asserts it does not.
            train_plays = None if plays is None else plays_for(plays, train)

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

            # One fit per system per bucket, shared with any system that predicts
            # through it (baselines.PREDICTION_SOURCE). No system ever sees a
            # frame other than `train`.
            fits: dict[str, dict[str, float]] = {"home_team": {}}

            # ONE L1+L2+L3 computation per bucket, seeded into the cache for all
            # three names plus the résumé's Power source. Without this the same
            # ridge would be refitted up to four times per week, and - worse -
            # `l3_power.rate` would reach for the default config while this
            # function holds a possibly different one.
            l3fit = None
            if blend is not None and train_plays is not None:
                l3fit = l3_power.fit(train, train_plays, cfg, state=blend)
                fits["l3"] = l3fit.ratings
                fits["l2"] = l3fit.l2.ratings
                fits["l1"] = l3fit.l1.point_ratings
                # report 02 §3.3: publish w1, w2 and k EVERY week. This is that
                # trajectory, and it is what makes "efficiency dominates late"
                # a falsifiable claim rather than a story.
                eff, res, _ = l3fit.features(train_fbs)
                blend_rows.append(
                    {
                        "season": season,
                        "bucket": bucket.label,
                        "week": bucket.week,
                        "season_type": bucket.season_type,
                        "w1": l3fit.w1,
                        "w2": l3fit.w2,
                        "k": l3fit.k,
                        "h_points": l3fit.home_field,
                        "lambda_l1": l3fit.l1.lam,
                        "lambda_l2": l3fit.l2.lam,
                        "weight_source": l3fit.weights.source,
                        "n_blend_games": l3fit.weights.n_games,
                        # The two weights are on different feature scales, so
                        # comparing them directly says nothing. These are the
                        # standard deviations each term actually contributes to a
                        # predicted margin, which is the comparable quantity.
                        "efficiency_contribution_sd": float(np.std(l3fit.w1 * eff)),
                        "results_contribution_sd": float(np.std(l3fit.w2 * res)),
                    }
                )

            for name in canonical:
                ratings = _cached_ratings(
                    name, train, train_plays, bucket.week, fits, blend, cfg
                )
                predict_with = _cached_ratings(
                    baselines.prediction_source(name, cfg),
                    train,
                    train_plays,
                    bucket.week,
                    fits,
                    blend,
                    cfg,
                )

                pool = calibration[name]
                if use_oos and len(pool) >= min_oos:
                    coef = pool.coefficients()
                    coef_source = "out_of_sample"
                else:
                    coef = calibrate(predict_with, train_fbs)
                    coef_source = "training_window"

                # THIS SYSTEM'S OWN SIGMA, AS OF THIS BUCKET (review S6). It is
                # estimated from the walk-forward residuals accumulated so far,
                # so it has seen only games already predicted, and it falls back
                # to [resume].sigma while the window is thin. Computed before the
                # bucket is scored and used for every probability in it.
                sigma_now = pool.sigma(cfg)

                in_headline = bucket.season_type != "regular" or bucket.week >= headline_week
                for segment in sorted(test["segment"].unique().to_list()):
                    sub = test.filter(pl.col("segment") == segment)
                    predicted = _predict(predict_with, sub, coef, cfg)
                    actual = (sub["home_points"] - sub["away_points"]).to_numpy().astype(float)
                    for cut in ("all",) + (("headline",) if in_headline else ()):
                        acc = pooled.setdefault((name, segment, cut), _Accumulator())
                        acc.predicted.extend(predicted.tolist())
                        acc.actual.extend(actual.tolist())
                        acc.sigma.extend([sigma_now.value] * len(actual))
                    if collect_predictions:
                        predictions.extend(
                            {
                                "system": name,
                                "season": season,
                                "week": bucket.week,
                                "season_type": bucket.season_type,
                                # The AUTHORITATIVE ordering of buckets within a
                                # season, by first kickoff (ingest/windows.py).
                                # A consumer that re-derived it from (week,
                                # season_type) would reintroduce the 2023
                                # postseason's week-1-and-11-15 collision.
                                "bucket": bucket.label,
                                "bucket_order": bucket.order,
                                "segment": segment,
                                "in_headline_window": in_headline,
                                "game_id": int(gid),
                                "home_team": str(ht),
                                "away_team": str(at),
                                "neutral_site": bool(ns),
                                "predicted": float(pm),
                                "actual": float(am),
                                "sigma": sigma_now.value,
                            }
                            for gid, ht, at, ns, pm, am in zip(
                                sub["game_id"].to_list(),
                                sub["home_team"].to_list(),
                                sub["away_team"].to_list(),
                                sub["neutral_site"].to_list(),
                                predicted.tolist(),
                                actual.tolist(),
                                strict=True,
                            )
                        )
                    if segment == "fbs_vs_fbs":
                        pool.add(
                            rating_deltas(predict_with, sub),
                            np.where(sub["neutral_site"].to_numpy(), 0.0, 1.0),
                            actual,
                            predicted,
                        )
                        summary = metrics.summarize(predicted, actual, sigma_now.value)
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
                                **sigma_now.as_params(),
                                **summary,
                            }
                        )

                current_rank = _ranking(ratings, fbs_now)
                churn = metrics.rank_churn(previous_rank.get(name), current_rank)
                churn_rows.append(
                    {"system": name, "season": season, "bucket": bucket.label, **churn}
                )
                previous_rank[name] = current_rank

            # THE OUT-OF-SAMPLE GUARANTEE, in one statement and its position.
            # This bucket's games join the blend sample only AFTER they have been
            # predicted, using the features of the fit that predicted them. Move
            # this line above the loop and w1/w2 become in-sample, which is
            # precisely the failure report 02 §3.3 legislates against.
            if l3fit is not None:
                blend.add(l3fit, test.filter(pl.col("segment") == "fbs_vs_fbs"))

        # ------------------------------------------------------------------
        # THE RETRODICTIVE PASS, in two protocols. Report 02 §2.12 and §5.2
        # define the metric - games whose loser the final rating ranks above the
        # winner - and leave the fitting protocol implicit. There are two
        # defensible readings and this harness ran the wrong one as its only
        # number until the fresh-eyes review (S1) noticed that the harness and
        # docs/analysis/headline-ordering-study.md disagreed by protocol rather
        # than by arithmetic.
        #
        #   PUBLISHED   walk-forward at the final bucket. Every hyperparameter is
        #               the one that was live when the season ended - in
        #               particular the L3 blend weights, which were fitted only
        #               on games already predicted. Scored over EVERY FBS-vs-FBS
        #               game of the season, postseason included.
        #               THIS IS HOW THE POLL IS ACTUALLY PRODUCED, week by week,
        #               by `retro.season_power`, so it is the definition the gate
        #               is evaluated on and the one the study used.
        #
        #   DIAGNOSTIC  full-season refit with no walk left to do, which means
        #               the blend weights are fitted IN-SAMPLE - exactly what
        #               report 02 §3.3 legislates against - and scored over the
        #               `fbs_vs_fbs` segment only, i.e. excluding the postseason.
        #               Reported because it is what this harness computed before,
        #               and dropping it silently would make the change invisible.
        #
        # Both are written to backtest_metrics.json for every system.
        # ------------------------------------------------------------------
        full = season_games
        full_plays = None if plays is None else plays_for(plays, full)
        all_fbs = full.filter(
            (pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs")
        )
        published_pairs = _winner_loser(all_fbs)
        diagnostic_pairs = _winner_loser(full.filter(pl.col("segment") == "fbs_vs_fbs"))

        walk_forward_fits: dict[str, dict[str, float]] = {"home_team": {}}
        refit_fits: dict[str, dict[str, float]] = {"home_team": {}}
        if blend is not None and full_plays is not None:
            # One L1+L2+L3 per protocol, seeded for the three names that read it,
            # exactly as the walk loop does. `state=blend` is the whole of the
            # published protocol: the blend weights are the accumulated
            # out-of-sample ones rather than weights fitted on the season being
            # scored.
            walked = l3_power.fit(full, full_plays, cfg, state=blend)
            walk_forward_fits |= {
                "l3": walked.ratings,
                "l2": walked.l2.ratings,
                "l1": walked.l1.point_ratings,
            }
            refitted = l3_power.fit(full, full_plays, cfg, state=None)
            refit_fits |= {
                "l3": refitted.ratings,
                "l2": refitted.l2.ratings,
                "l1": refitted.l1.point_ratings,
            }

        for name in canonical:
            if name == "home_team":
                continue
            published = _cached_ratings(name, full, full_plays, None, walk_forward_fits, blend, cfg)
            diagnostic = _cached_ratings(name, full, full_plays, None, refit_fits, None, cfg)
            final_violations[name].append(
                {
                    "season": season,
                    **metrics.violations(published, *published_pairs),
                    "full_season_refit": metrics.violations(diagnostic, *diagnostic_pairs),
                }
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
                    np.array(acc.predicted),
                    np.array(acc.actual),
                    np.array(acc.sigma),
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
            "retrodictive_violation_rate": _pooled_rate(violations_rows),
            "retrodictive_violation_rate_full_season_refit": _pooled_rate(
                [v["full_season_refit"] for v in violations_rows]
            ),
            "retrodictive_protocol": (
                "PUBLISHED: walk-forward at the final bucket - every "
                "hyperparameter is the one that was live when the season ended, "
                "which is how the poll is produced week by week - scored over "
                "every FBS-vs-FBS game of the season, postseason included. "
                "`*_full_season_refit` is the DIAGNOSTIC: a full-season refit, "
                "whose L3 blend weights are in-sample because there is no walk "
                "left to do, scored over the fbs_vs_fbs segment only"
            ),
        }
    # The violations criterion is comparative, so it can only be evaluated once
    # every system has a rate (report 02 §5.4, [gate].violations_must_beat).
    violation_rates = {n: per_system[n]["retrodictive_violation_rate"] for n in canonical}
    for name in canonical:
        # THE GATE IS EVALUATED ON THE PUBLISHED WINDOW. It used to be evaluated
        # on `segments`, which starts at `first_eval_week` (2) - the near-noise
        # regime report 02 §4 explicitly declines to publish. A publication gate
        # scored on weeks that are never published is measuring a poll that does
        # not exist, and it disagreed with the numbers the demo quoted, which
        # were the headline-window ones. `gate_all_weeks` keeps the wider view as
        # a diagnostic so the change is visible rather than silent. Neither
        # window passes: the calibration criterion is missed by 4.2pp on the
        # published window and by 6.4pp on the wider one.
        headline = per_system[name]["segments_from_headline_week"]
        segments = per_system[name]["segments"]
        if "fbs_vs_fbs" in headline:
            per_system[name]["gate"] = metrics.check_gate(
                headline["fbs_vs_fbs"],
                cfg["gate"],
                violation_rate=violation_rates[name],
                baseline_violation_rates=violation_rates,
                system=name,
            )
            per_system[name]["gate"]["window"] = (
                f"FBS-vs-FBS, weeks >= [publication].headline_start_week "
                f"({headline_week}) - the published poll's own window"
            )
        if "fbs_vs_fbs" in segments:
            per_system[name]["gate_all_weeks"] = metrics.check_gate(
                segments["fbs_vs_fbs"],
                cfg["gate"],
                violation_rate=violation_rates[name],
                baseline_violation_rates=violation_rates,
                system=name,
            )
            per_system[name]["gate_all_weeks"]["window"] = (
                f"FBS-vs-FBS, weeks >= [backtest].first_eval_week ({min_week}) - "
                "a DIAGNOSTIC. These weeks are not published as the poll"
            )

    return {
        "protocol": {
            "walk_forward": "fit through bucket N-1 of the same season, predict bucket N",
            "spec": "report 02 §5.1",
            "seasons": seasons,
            "systems": canonical,
            "universe": bt["universe"],
            "first_eval_week": min_week,
            "min_training_games": min_training,
            "sigma_fallback": sigma_fallback,
            "sigma_estimator": str(cfg["resume"].get("sigma_estimator", "config")),
            "sigma": (
                "PER SYSTEM, PER BUCKET: the root-mean-square walk-forward residual "
                "of that system's own predictions over the out-of-sample games "
                "accumulated so far, with [resume].sigma as the thin-window "
                "fallback and floor (review S6). `weekly[].sigma` carries the value "
                "that was live for each row and `segments[].sigma_mean` the mean "
                "over a pooled segment"
            ),
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
            "prediction_sources": {
                name: baselines.prediction_source(name, cfg) for name in canonical
            },
            "power_source": str(cfg["resume"]["power_source"]),
            "plays_loaded": bool(plays is not None),
            "blend_weights_pooled_over": "one season, never across seasons (constraint 2)",
            "prediction_source_note": (
                "a system whose prediction source is not itself is a RETRODICTIVE "
                "rating scored on violations, and predicts through the rating it "
                "was built on (report 02 §3.5, backtest/baselines/__init__.py)"
            ),
            "prior_seasons_used": False,
        },
        "systems": per_system,
        "weekly": rows,
        **({"predictions": predictions} if collect_predictions else {}),
        "blend": blend_rows,
        "connectivity": connectivity,
    }


def retro_grid(
    seasons: list[int],
    config: dict[str, Any] | None = None,
    games: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """The full R(N, K) grid for each season, stacked (report 02 §3.6).

    The "biggest retroactive movers" view - who the model was wrong about, in its
    own words, with the number quantified - is the most differentiated thing this
    project can ship, and it costs nothing extra once the grid exists. The
    estimator itself lives in `model/retro.py`; this is the harness-side entry
    point that loads seasons and stacks them.
    """
    from cfbpoll.model import retro

    cfg = config if config is not None else load_config()
    seasons = sorted(int(s) for s in seasons)
    if games is None:
        games = load_games(seasons, universe=str(cfg["model"]["fit_universe"]))
    return pl.concat([retro.grid(games, season, cfg) for season in seasons], how="vertical").sort(
        ["season", "eval_order", "data_order", "resume", "resume_margin", "team"],
        descending=[False, False, False, True, True, False],
    )


def run(rater: Callable[..., Any], seasons: list[int], config: dict[str, Any]) -> Any:
    """Deprecated alias kept so the scaffold's name resolves. Use run_backtest."""
    raise NotImplementedError("backtest.walkforward.run - use run_backtest (report 02 §5.1)")
