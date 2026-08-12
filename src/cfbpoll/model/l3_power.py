"""L3 - Power rating: the walk-forward stacked blend of L1 and L2.

Specified by report 02 §3.3.

    m_hat_g = w1 * k * ((alpha_h - beta_h) - (alpha_a - beta_a))
            + w2 * (rho_h - rho_a)
            + h * site_g

    Power_t = w1 * k * (alpha_t - beta_t) + w2 * rho_t

(On why the efficiency differential is written with matching subscripts rather
than the crossed ones report 02 §3.3 prints, see model/l1_efficiency.py's
docstring: the crossed form contradicts §3.3's own definition of Power_t, and the
matching form is what the physics gives.)

DO NOT HAND-PICK w1 AND w2. Estimate them on OUT-OF-SAMPLE games only - fit on
weeks <= N-1, evaluate on week N, pooled across the training seasons. Publish w1,
w2 and k every week. Report 02 §3.3 expects w1 to dominate late (efficiency is
more stable) and w2 to matter more early (a scoreboard result is worth a lot when
you have three games). If the fitted weights say otherwise, publish that instead:
the backtest decides, not the narrative.

WHY OUT-OF-SAMPLE IS NOT PEDANTRY. Fitting the blend on the training window reads
the weights off games both layers were fit on, which flatters whichever layer
fits its own training data hardest. L1 has ~2,000 parameters and 170,000 rows;
L2 has ~300 parameters and 1,200 rows. In-sample they are not remotely
comparable, and a stacked blend fitted in-sample will hand the weight to whichever
one overfits more. This is the same argument, and the same fix, that
backtest/walkforward.py already applies to its per-system points calibration.

NO INTERCEPT. A zero differential at a neutral site must mean a zero expected
margin; that is what "the points scale" means, and it is why `h` carries the
whole site effect rather than sharing it with a constant.

THE FALLBACK, AND WHEN IT FIRES. Before `[blend].min_out_of_sample_games` have
accumulated - the first few evaluable weeks of a season - there is nothing
out-of-sample to fit on, and the training window is used instead. Every artifact
records `blend_weight_source` as `out_of_sample` or `training_window` so a reader
always knows which one produced the number in front of them.

POWER IS THE PREDICTIVE NUMBER: expected margin against an average team on a
neutral field. It is never hidden - it is published beside the Résumé rating
every week, with the gap shown, so that the two most common fan complaints
("you're just ranking who'd win" / "you're ignoring that they got blown out")
both have an on-page answer (report 02 §3.5).

STATE, AND WHY IT IS A CACHE RATHER THAN A MEMORY. `SeasonState` holds two
things: the accumulated out-of-sample rows, and a fit cache keyed on an exact
fingerprint of (games window, plays window, number of accumulated rows). The
fingerprint is what makes the cache incapable of returning a stale answer - a
different window is a different key, and a grown blend sample is a different key.
Passing no state at all is always correct and only slower.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from cfbpoll.config import load_config
from cfbpoll.model import l1_efficiency, l2_results, l4_resume

__all__ = [
    "BlendWeights",
    "L3Fit",
    "SeasonState",
    "SigmaEstimate",
    "estimate_sigma",
    "fit",
    "fit_blend_weights",
    "power_from_l3",
    "power_source_for",
    "rate",
    "season_power",
]


@dataclass(frozen=True)
class SigmaEstimate:
    """sigma, where it came from, and how many games it was estimated on.

    THE REVIEW'S S6 IN ONE OBJECT. sigma is the denominator of every win
    probability the poll publishes and therefore of the headline rank key, and it
    used to be the constant 15.3 - a sound estimate of the residual SD of margin
    around a GOOD PUBLIC MODEL's prediction, which is not the same thing as around
    ours. This is ours, measured, with the literature value kept as the
    thin-window fallback and as a floor.
    """

    value: float
    source: str
    n_games: int
    estimate: float | None = None
    floor: float = 0.0

    def as_params(self) -> dict[str, Any]:
        return {
            "sigma": self.value,
            "sigma_source": self.source,
            "sigma_n_out_of_sample_games": self.n_games,
            "sigma_walk_forward_estimate": self.estimate,
            "sigma_floor": self.floor,
        }


def estimate_sigma(
    residuals: Any,
    config: dict[str, Any],
    n_games: int | None = None,
) -> SigmaEstimate:
    """Root-mean-square walk-forward residual, with the config value as fallback.

    `residuals` are OUT-OF-SAMPLE prediction errors in points: each one is a game
    predicted by a fit that had not seen it. The rule, stated once here and used
    everywhere:

      * fewer than `[resume].sigma_min_out_of_sample_games` residuals -> the
        config's sigma, because the estimate would be noise;
      * an estimate below the config's sigma -> the config's sigma, as a FLOOR.
        A spuriously small sigma makes every tail too small, and because the
        headline key is a product over 9 to 13 games the error compounds. The
        literature value is the right thing to refuse to go below;
      * otherwise the estimate.

    `[resume].sigma_estimator = "config"` restores the pre-2026-08-12 behaviour,
    so the old choice stays reachable and measurable rather than asserted away.
    """
    res = config["resume"]
    floor = float(res["sigma"])
    minimum = int(res.get("sigma_min_out_of_sample_games", 40))
    if str(res.get("sigma_estimator", "walk_forward_residuals")) != "walk_forward_residuals":
        return SigmaEstimate(value=floor, source="config", n_games=0, floor=floor)

    array = np.asarray(list(residuals), dtype=np.float64)
    n = int(array.size if n_games is None else n_games)
    if array.size < minimum:
        return SigmaEstimate(
            value=floor, source="config_fallback_thin_window", n_games=n, floor=floor
        )
    estimate = float(np.sqrt(np.mean(array**2)))
    if estimate < floor:
        return SigmaEstimate(
            value=floor, source="config_floor", n_games=n, estimate=estimate, floor=floor
        )
    return SigmaEstimate(
        value=estimate,
        source="walk_forward_residuals",
        n_games=n,
        estimate=estimate,
        floor=floor,
    )

LAYER = "L3 power rating"
VERSION = "v1"


@dataclass(frozen=True)
class BlendWeights:
    """(w1, w2, h) plus where they came from. Published every week."""

    w1: float
    w2: float
    home_field: float
    source: str
    n_games: int


def fit_blend_weights(
    efficiency: np.ndarray,
    results: np.ndarray,
    site: np.ndarray,
    margin: np.ndarray,
    source: str,
) -> BlendWeights:
    """OLS of `margin ~ w1*efficiency + w2*results + h*site`, NO intercept.

    Minimum-norm on a degenerate design rather than raising: in a window with no
    neutral-site games, or before L1 has any plays at all, a column can be
    identically zero and least squares should degrade gracefully instead of
    taking the poll down.
    """
    if margin.size == 0:
        return BlendWeights(w1=0.0, w2=0.0, home_field=0.0, source="empty", n_games=0)
    x = np.column_stack([efficiency, results, site])
    coef, *_ = np.linalg.lstsq(x, margin, rcond=None)
    return BlendWeights(
        w1=float(coef[0]),
        w2=float(coef[1]),
        home_field=float(coef[2]),
        source=source,
        n_games=int(margin.size),
    )


@dataclass
class SeasonState:
    """Per-season out-of-sample accumulator plus a fingerprinted fit cache.

    `add` is called by the harness AFTER a bucket has been predicted and scored,
    with the features computed from the fit that predicted it. That ordering is
    the whole out-of-sample guarantee: a game contributes to the weights only
    once it has already been predicted with weights that did not see it.
    """

    efficiency: list[float] = field(default_factory=list)
    results: list[float] = field(default_factory=list)
    site: list[float] = field(default_factory=list)
    margin: list[float] = field(default_factory=list)
    #: The walk-forward residual of each accumulated game: actual margin minus the
    #: margin the fit that PREDICTED it forecast. Stored at the moment of
    #: prediction rather than recomputed later with the current weights, because
    #: the current weights have since seen the game and the residual would flatter
    #: the model by exactly the amount sigma is supposed to measure.
    residual: list[float] = field(default_factory=list)
    cache: dict[tuple[Any, ...], L3Fit] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.margin)

    def add(self, fitted: L3Fit, games: pl.DataFrame) -> None:
        if games.is_empty():
            return
        eff, res, site = fitted.features(games)
        actual = (games["home_points"] - games["away_points"]).to_numpy().astype(np.float64)
        predicted = fitted.predict(games)
        self.efficiency.extend(eff.tolist())
        self.results.extend(res.tolist())
        self.site.extend(site.tolist())
        self.margin.extend(actual.tolist())
        self.residual.extend((actual - predicted).tolist())

    def sigma(self, config: dict[str, Any]) -> SigmaEstimate:
        """The walk-forward sigma from everything accumulated so far."""
        return estimate_sigma(self.residual, config)

    def weights(self) -> BlendWeights:
        return fit_blend_weights(
            np.array(self.efficiency),
            np.array(self.results),
            np.array(self.site),
            np.array(self.margin),
            source="out_of_sample",
        )


@dataclass(frozen=True)
class L3Fit:
    """The blended Power rating, and every number needed to reproduce it."""

    ratings: dict[str, float]
    weights: BlendWeights
    k: float
    l1: l1_efficiency.L1Fit
    l2: l2_results.L2Fit
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def w1(self) -> float:
        return self.weights.w1

    @property
    def w2(self) -> float:
        return self.weights.w2

    @property
    def home_field(self) -> float:
        return self.weights.home_field

    def rating(self, team: str) -> float:
        """Unseen teams sit at 0.0 - the league-average prior, not a guess."""
        return self.ratings.get(team, 0.0)

    def features(self, games: pl.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(k * efficiency differential, results differential, site) per game.

        These are the three columns the blend regression sees, and the three the
        out-of-sample accumulator stores. Keeping them in one place is what makes
        "the weights were fitted on exactly the features that predicted" checkable
        rather than hopeful.
        """
        home = games["home_team"].to_list()
        away = games["away_team"].to_list()
        eff = self.k * np.array(
            [self.l1.net(h) - self.l1.net(a) for h, a in zip(home, away, strict=True)],
            dtype=np.float64,
        )
        res = np.array(
            [self.l2.rating(h) - self.l2.rating(a) for h, a in zip(home, away, strict=True)],
            dtype=np.float64,
        )
        site = np.where(games["neutral_site"].to_numpy(), 0.0, 1.0)
        return eff, res, site

    def predict(self, games: pl.DataFrame) -> np.ndarray:
        eff, res, site = self.features(games)
        return self.w1 * eff + self.w2 * res + self.home_field * site

    def as_params(self) -> dict[str, Any]:
        """The model_params.json payload for this layer (report 03 §5.3).

        w1, w2, k, h and both lambdas, every week, per report 02 §3.3.
        """
        return {
            "layer": LAYER,
            "version": VERSION,
            "w1_efficiency": self.w1,
            "w2_results": self.w2,
            "k_points_per_unit": self.k,
            "h_points": self.home_field,
            "blend_weight_source": self.weights.source,
            "blend_n_games": self.weights.n_games,
            "lambda_l1": self.l1.lam,
            "lambda_l2": self.l2.lam,
            # The layers below, in full and nested so nothing collides. Constraint
            # 5 says every constant the model used is published every week, and
            # that includes L1's garbage-time thresholds and the shape of our own
            # expected-points curve, not just the two blend weights.
            "l1": self.l1.as_params(),
            **self.params,
        }


def _fingerprint(games: pl.DataFrame, plays: pl.DataFrame | None, n_rows: int) -> tuple[Any, ...]:
    """An exact key for the (window, window, blend sample) a fit depends on.

    Exact rather than approximate: two different windows cannot collide on
    (row count, min id, max id, id sum), and a grown blend sample changes the
    key by construction. A cache that cannot go stale is worth the four numbers.
    """
    ids = games["game_id"]
    return (
        int(games.height),
        int(ids.min() or 0),
        int(ids.max() or 0),
        int(ids.sum() or 0),
        0 if plays is None else int(plays.height),
        n_rows,
    )


def fit(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    config: dict[str, Any] | None = None,
    state: SeasonState | None = None,
    l1fit: l1_efficiency.L1Fit | None = None,
    l2fit: l2_results.L2Fit | None = None,
) -> L3Fit:
    """Fit L1, fit L2, blend them on out-of-sample games, and rate every team.

    `games` and `plays` are the exact windows the fit may see; this function does
    no slicing (report 02 §5.1). `state` is an optional per-season cache and
    out-of-sample accumulator - see the module docstring.
    """
    cfg = config if config is not None else load_config()
    blend_cfg = cfg["blend"]
    min_oos = int(blend_cfg.get("min_out_of_sample_games", 40))

    key = _fingerprint(games, plays, 0 if state is None else len(state))
    if state is not None and key in state.cache:
        return state.cache[key]

    games = games.sort("game_id")
    l2 = l2fit if l2fit is not None else l2_results.fit(games, cfg)
    if l1fit is not None:
        l1 = l1fit
    elif plays is None or plays.is_empty():
        # No play archive: the blend degrades to the results core, which is a
        # real answer and is stamped as such (`power_source` on every artifact).
        l1 = l1_efficiency.empty_fit(cfg)
    else:
        l1 = l1_efficiency.fit(plays, games, cfg)

    unset = BlendWeights(w1=0.0, w2=0.0, home_field=0.0, source="unset", n_games=0)
    partial = L3Fit(ratings={}, weights=unset, k=l1.k, l1=l1, l2=l2)

    if state is not None and len(state) >= min_oos:
        weights = state.weights()
    else:
        eff, res, site = partial.features(games)
        margin = (games["home_points"] - games["away_points"]).to_numpy().astype(np.float64)
        weights = fit_blend_weights(eff, res, site, margin, source="training_window")

    teams = sorted(set(l2.ratings) | set(l1.alpha) | set(l1.beta))
    ratings = {t: weights.w1 * l1.k * l1.net(t) + weights.w2 * l2.rating(t) for t in teams}

    fitted = L3Fit(
        ratings=ratings,
        weights=weights,
        k=l1.k,
        l1=l1,
        l2=l2,
        params={
            "estimator": str(blend_cfg["estimator"]),
            "fit_out_of_sample_only": bool(blend_cfg["fit_out_of_sample_only"]),
            "min_out_of_sample_games": min_oos,
            "n_teams": len(teams),
            "n_games": int(games.height),
            "n_plays": l1.n_plays,
        },
    )
    if state is not None:
        state.cache[key] = fitted
    return fitted


def power_from_l3(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    config: dict[str, Any] | None = None,
    state: SeasonState | None = None,
    l1fit: l1_efficiency.L1Fit | None = None,
    l2fit: l2_results.L2Fit | None = None,
) -> l4_resume.PowerSource:
    """Opponent quality for the résumé, from the blend (report 02 §3.4).

    No rescaling step, unlike `l4_resume.power_from_l2`: the blend regression's
    response IS actual game margin, so Power is already in points and `scale` is
    1.0 by construction. That is one fewer fitted constant between the résumé and
    the data, and it is the reason report 02 §3.4 reads opponent quality off L3
    rather than off L2 in the first place.
    """
    cfg = config if config is not None else load_config()
    return power_source_for(fit(games, plays, cfg, state=state, l1fit=l1fit, l2fit=l2fit))


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None = None,
    through_week: int | None = None,
    state: SeasonState | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Challenger-protocol entry point (report 03 §7.3): the incumbent Power rating.

    This is the exact signature a community challenger must implement to be
    scored by challenge.yml against the incumbent on the identical harness.
    `games` and `plays` arrive ALREADY truncated by the harness; `through_week`
    is informational; `state` is the optional per-season cache.
    """
    del through_week
    return fit(games, plays, config, state=state).ratings


def season_power(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    season: int,
    config: dict[str, Any] | None = None,
    buckets: list[Any] | None = None,
    season_sigma: dict[int, SigmaEstimate] | None = None,
) -> dict[int, L3Fit]:
    """bucket.order -> the L3 fit whose Power is live as of that bucket.

    THE WALK-FORWARD BLEND, OUTSIDE THE BACKTEST HARNESS. `cfbpoll rank` and the
    retroactive grid both need blend weights, and weights fitted on the window
    they are about to rate would be in-sample - the exact thing report 02 §3.3
    forbids. So the season is walked once, forward, and the out-of-sample sample
    grows as it goes.

    The walk costs ONE L1+L2 fit per bucket, not two, because
    `games_through(b-1)` and `games_before(b)` are the same set of games: the fit
    that is live at bucket b-1 is also the fit that predicted bucket b, so it is
    the one whose features enter the blend sample for bucket b's games. Reusing
    it is not a shortcut, it is the definition.

    Returns every bucket, so a caller that wants one week takes one key and a
    caller that wants the whole grid takes all of them.
    """
    from cfbpoll.ingest import windows
    from cfbpoll.ingest.plays import plays_for

    cfg = config if config is not None else load_config()
    season_games = games.filter(pl.col("season") == season)
    all_buckets = buckets if buckets is not None else windows.season_buckets(season_games, season)

    season_sigma = {} if season_sigma is None else season_sigma
    state = SeasonState()
    out: dict[int, L3Fit] = {}
    sigmas: dict[int, SigmaEstimate] = {}
    previous: L3Fit | None = None
    for bucket in all_buckets:
        if previous is not None:
            played = windows.games_in_bucket(season_games, bucket).filter(
                (pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs")
            )
            state.add(previous, played)
        window = windows.games_through(
            season_games, season=season, week=bucket.week, season_type=bucket.season_type
        )
        window_plays = None if plays is None else plays_for(plays, window)
        fitted = fit(window, window_plays, cfg, state=state)
        out[bucket.order] = fitted
        # sigma AS OF THIS BUCKET: estimated on residuals from games already
        # predicted, so it is walk-forward in the same sense the blend weights are.
        sigmas[bucket.order] = state.sigma(cfg)
        previous = fitted
    season_sigma.update(sigmas)
    return out


def power_source_for(
    fitted: L3Fit, sigma: SigmaEstimate | None = None
) -> l4_resume.PowerSource:
    """Wrap an already-computed L3 fit as opponent quality for the résumé.

    `sigma` is the walk-forward estimate measured on the state that produced this
    fit. Passing None leaves the résumé and the headline ordering on the config's
    fallback, which is correct for a caller with no walk behind it and is recorded
    as `sigma_source = "config"` rather than left to be assumed.
    """
    return l4_resume.PowerSource(
        ratings=dict(sorted(fitted.ratings.items())),
        home_field=fitted.home_field,
        scale=1.0,
        source="L3",
        version=VERSION,
        scale_universe="blend_regression_on_actual_margin",
        n_scale_games=fitted.weights.n_games,
        l2=fitted.l2,
        l3=fitted,
        sigma=None if sigma is None else sigma.value,
        sigma_source=("config" if sigma is None else sigma.source),
        sigma_n_games=0 if sigma is None else sigma.n_games,
        # Power = w1*k*(alpha - beta) + w2*rho, and the blend regression's
        # response is already points, so the results core enters multiplied by
        # w2 and a compressed-response standard error is carried across by w2.
        se_scale=fitted.w2,
        se_note=(
            "ridge sandwich on the L2 half only (report 02 §3.3), carried onto "
            "the points scale by w2. THE EFFICIENCY HALF IS HELD AT ITS POINT "
            "ESTIMATE: a play-level covariance over ~2,000 coefficients and "
            "170,000 correlated rows is a different object and is not built, so "
            "this is a LOWER BOUND on the uncertainty of an L3 rating. The "
            "parametric bootstrap inherits the same limitation and says so"
        ),
    )
