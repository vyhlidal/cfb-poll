"""L1 - opponent-adjusted efficiency via ridge on play-level value.

Specified by report 02 §3.1 (design) and §2.8 (the ancestor implementation).

    y_p = mu + alpha_{o(p)} + beta_{d(p)} + eta * H_p + eps_p

alpha_t is offensive rating (value/play above average), beta_t is defensive
rating (value/play ALLOWED above average, so more negative is better), eta is
home field. mu and eta are unpenalised.

`y_p` is OUR per-play value, from `model/ep.py`, not the archive's `EPA` column.
That is the whole reason ep.py exists; report 01 §5.6 bans black-box inputs and
report 02 §2.8's ancestor implementation used a column we are not allowed to use.
Ours correlates with theirs at r = 0.847 - reported, never fed in.

Opponent adjustment is SIMULTANEOUS, not iterative. Solving offense and defense
jointly in one linear system is both more correct and cheaper than iterative
averaging, and it makes the "10 sacks against an FCS team" problem vanish by
construction (report 02 §1, commitment 3).

WHICH PLAYS ARE IN THE FIT. Rush, pass and other scrimmage plays (fumbles,
safeties). NOT special teams - report 02 §3.1 excludes them from L1 in v1
because ST value is very noisy at 12-game samples and the scoreboard already
contains it, so L2 picks it up. NOT penalty rows either: this feed records an
accepted penalty as a SEPARATE row alongside the play it modifies, so a penalty
row's value is real but it is an officiating event rather than an execution
play, and including it would let the same snap contribute twice. Both exclusions
are `[efficiency].design_play_classes` and both are reversible from the config.

CONVERTING TO POINTS. Report 02 §3.1: regress actual game margin on the
efficiency differential and read off k, which should land near the number of
offensive plays a team runs per game (roughly 65-72). Fit it walk-forward; do
not hard-code it.

    margin_g = a + k * ((alpha_h - beta_h) - (alpha_a - beta_a)) + c * site_g

A DEVIATION FROM THE REPORT'S ALGEBRA, STATED PLAINLY. Report 02 §3.1 and §3.3
both write that differential as `(alpha_h - beta_a) - (alpha_a - beta_h)`, and
that expression is not consistent with §3.3's own definition of the rating it is
supposed to produce, `Power_t = w1*k*(alpha_t - beta_t) + w2*rho_t`. The physics
settles it. Home's expected scoring rate against this opponent is `mu + alpha_h +
beta_a`; away's is `mu + alpha_a + beta_h`; so

    margin / plays = (alpha_h + beta_a) - (alpha_a + beta_h)
                   = (alpha_h - beta_h) - (alpha_a - beta_a)

which is exactly Power_h - Power_a, as §3.3 requires. The report's version swaps
the two defensive subscripts and would make the blend equation disagree with the
rating it defines. We implement the consistent one and record the correction
here rather than silently.

UNIT SPLITS. The same model on a filtered dataset, one extra fit each for rush
and pass. They are NOT used in the v1 ranking (`unit_splits_in_ranking = false`);
they exist for explanation - "this team's #3 is carried by the nation's #2 rush
defence" - and for the falsifiable matchup test in report 02 §6.

PURITY AND DETERMINISM. `fit` is a pure function of (plays, games, config). No
I/O, no state, no RNG. Teams sorted by name, plays sorted by (game_id,
play_index), returned mappings built in sorted order, so no dict iteration order
can reach a file (report 03 §9.3 item 3). Pin the BLAS thread count to 1.

CONSTRAINT AUDIT. The columns that reach the design matrix are: our own play
value (from the scoreboard), team ids, site, and the game weights. Nothing else.
No poll, no recruiting, no returning production, no prior-season rating, no
third-party rating, no conference, no betting line, and no third-party expected
points (report 02 §3.10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from cfbpoll.config import load_config
from cfbpoll.model import design, ep, ridge

__all__ = [
    "L1Fit",
    "UnitFit",
    "empty_fit",
    "efficiency_to_points",
    "fit",
    "net_efficiency_differential",
]

LAYER = "L1 efficiency core"
VERSION = "v1"


@dataclass(frozen=True)
class UnitFit:
    """One unit-split fit (rush or pass). Explanation only - never in the ranking."""

    unit: str
    alpha: dict[str, float]
    beta: dict[str, float]
    home_field: float
    intercept: float
    lam: float
    n_plays: int

    def net(self, team: str) -> float:
        return self.alpha.get(team, 0.0) - self.beta.get(team, 0.0)


@dataclass(frozen=True)
class L1Fit:
    """Everything a published efficiency rating needs to be auditable."""

    alpha: dict[str, float]
    beta: dict[str, float]
    home_field: float
    intercept: float
    lam: float
    k: float
    k_intercept: float
    k_site: float
    n_plays: int
    n_teams: int
    n_games: int
    cv: ridge.CVResult
    ep_model: ep.EPModel
    units: dict[str, UnitFit] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)

    def net(self, team: str) -> float:
        """alpha_t - beta_t, in value/play. Unseen teams sit at league average."""
        return self.alpha.get(team, 0.0) - self.beta.get(team, 0.0)

    @property
    def net_ratings(self) -> dict[str, float]:
        return {t: self.net(t) for t in sorted(set(self.alpha) | set(self.beta))}

    def points(self, team: str) -> float:
        """The efficiency rating on the POINTS scale: k * (alpha_t - beta_t)."""
        return self.k * self.net(team)

    @property
    def point_ratings(self) -> dict[str, float]:
        return {t: self.points(t) for t in sorted(set(self.alpha) | set(self.beta))}

    def predict(self, home: str, away: str, neutral: bool = False) -> float:
        """Predicted margin from efficiency alone, in points."""
        site = 0.0 if neutral else 1.0
        return self.k_intercept + self.points(home) - self.points(away) + self.k_site * site

    def as_params(self) -> dict[str, Any]:
        """The model_params.json payload for this layer (report 03 §5.3)."""
        return {
            "layer": LAYER,
            "version": VERSION,
            "lambda": self.lam,
            "home_field_value_per_play": self.home_field,
            "intercept_value_per_play": self.intercept,
            "k_points_per_unit": self.k,
            "k_intercept": self.k_intercept,
            "k_site_points": self.k_site,
            "n_plays": self.n_plays,
            "n_teams": self.n_teams,
            "n_games_for_k": self.n_games,
            "cv": self.cv.as_dict(),
            "unit_splits": {
                unit: {"lambda": u.lam, "n_plays": u.n_plays, "home_field": u.home_field}
                for unit, u in sorted(self.units.items())
            },
            # Nested, not merged: the expected-points model declares its own
            # `layer` and `version` and spreading it here would overwrite L1's.
            "ep": self.ep_model.as_params(),
            **self.params,
        }


def empty_fit(config: dict[str, Any] | None = None) -> L1Fit:
    """A neutral L1: every team at league average, no plays behind it.

    This is what a scores-only run gets - a challenger that declares no play
    dependency, a season with no play feed, a week before any game has been
    played. It is a real answer (alpha = beta = 0 IS "we know nothing yet, so
    league average") rather than a crash, and it makes the L3 blend degrade to
    the L2 results core instead of falling over.
    """
    cfg = config if config is not None else load_config()
    return _empty(cfg, ep.EPModel(
        table=np.zeros((4, len(cfg["ep"]["distance_buckets"]) + 2, ep.MAX_YARDS_TO_GOAL)),
        counts=np.zeros((4, len(cfg["ep"]["distance_buckets"]) + 2, ep.MAX_YARDS_TO_GOAL)),
        edges=tuple(int(e) for e in cfg["ep"]["distance_buckets"]),
        bandwidth=float(cfg["ep"]["kernel_bandwidth_yards"]),
        shrinkage=float(cfg["ep"]["shrinkage_prior_plays"]),
        n_plays=0,
        scope=str(cfg["ep"]["fit_scope"]),
        seasons=(),
    ))


def _empty(cfg: dict[str, Any], model: ep.EPModel) -> L1Fit:
    grid = tuple(float(x) for x in sorted(cfg["ridge"]["l1_grid"]))
    return L1Fit(
        alpha={},
        beta={},
        home_field=0.0,
        intercept=0.0,
        lam=grid[-1],
        k=float(cfg["efficiency"]["k_start"]),
        k_intercept=0.0,
        k_site=0.0,
        n_plays=0,
        n_teams=0,
        n_games=0,
        cv=ridge.CVResult(lam=grid[-1], grid=grid, cv_error=(), n_folds=0),
        ep_model=model,
        params=_static_params(cfg),
    )


def _static_params(cfg: dict[str, Any]) -> dict[str, Any]:
    """The constants that must appear in model_params.json every single week."""
    eff = cfg["efficiency"]
    gt = cfg["garbage_time"]
    return {
        "garbage_time_mode": str(gt["mode"]),
        "garbage_time_thresholds": dict(gt[str(gt["mode"])]),
        "zero_weight_plays": list(gt["zero_weight_plays"]),
        "special_teams": str(eff["special_teams"]),
        "design_play_classes": list(eff["design_play_classes"]),
        "unit_splits_in_ranking": bool(eff["unit_splits_in_ranking"]),
        "recency_gamma": float(cfg["weights"]["recency_gamma"]),
    }


def _solve_one(
    plays: pl.DataFrame,
    cfg: dict[str, Any],
    teams: tuple[str, ...] | None,
    weights_by_game: dict[int, float],
    lam: float | None = None,
) -> tuple[design.PlayDesign, np.ndarray, ridge.CVResult]:
    d = design.build_play_design(plays, cfg, teams=teams, game_weights_by_id=weights_by_game)
    grid = cfg["ridge"]["l1_grid"]
    if lam is None:
        cv = ridge.cv_select_lambda(
            d.X,
            d.y,
            d.w,
            d.penalty,
            groups=d.game_ids,
            grid=grid,
            n_folds=int(cfg["ridge"]["cv_folds"]),
        )
        lam = cv.lam
    else:
        cv = ridge.CVResult(
            lam=lam, grid=tuple(float(g) for g in sorted(grid)), cv_error=(), n_folds=0
        )
    theta = ridge.solve(d.X, d.y, d.w, d.penalty, lam)
    return d, theta, cv


def net_efficiency_differential(
    games: pl.DataFrame,
    net: dict[str, float],
) -> np.ndarray:
    """(alpha_h - beta_h) - (alpha_a - beta_a) per game. See the module docstring
    for why this is not the expression report 02 §3.1 prints."""
    return np.array(
        [
            net.get(h, 0.0) - net.get(a, 0.0)
            for h, a in zip(games["home_team"].to_list(), games["away_team"].to_list(), strict=True)
        ],
        dtype=np.float64,
    )


def _fit_k(
    games: pl.DataFrame,
    net: dict[str, float],
    cfg: dict[str, Any],
) -> tuple[float, float, float, int, str]:
    """OLS of `margin ~ a + k*differential + c*site`. Returns (k, a, c, n, universe).

    Report 02 §3.1 asks for k walk-forward, and within a walk-forward step the
    games available are exactly the training window - the same games the ridge
    was fitted on. That is in-sample for k and deliberately so: k is a UNIT
    CONVERSION, not a predictor. It is also, structurally, unidentifiable
    separately from L3's w1, which multiplies it (report 02 §3.3); k is published
    because §3.1 says to publish it and because its magnitude is a sanity check
    on the whole layer, not because the blend depends on its exact value.
    """
    eff = cfg["efficiency"]
    universe = str(eff["k_scale_universe"])
    scale = games
    if universe == "fbs_vs_fbs":
        scale = games.filter((pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs"))
    if scale.height < int(eff["k_scale_min_games"]):
        scale = games
        universe = f"{universe}_fallback_all"
    if scale.is_empty():
        return (float(eff["k_start"]), 0.0, 0.0, 0, universe)

    delta = net_efficiency_differential(scale, net)
    site = np.where(scale["neutral_site"].to_numpy(), 0.0, 1.0)
    margin = (scale["home_points"] - scale["away_points"]).to_numpy().astype(np.float64)
    x = np.column_stack([np.ones_like(delta), delta, site])
    coef, *_ = np.linalg.lstsq(x, margin, rcond=None)
    return (float(coef[1]), float(coef[0]), float(coef[2]), int(scale.height), universe)


def fit(
    plays: pl.DataFrame,
    games: pl.DataFrame,
    config: dict[str, Any] | None = None,
    ep_model: ep.EPModel | None = None,
) -> L1Fit:
    """Fit the L1 ridge. Pure function of (plays, games, config).

    `plays` is the JOINED play frame (`ingest.plays.plays_for`) already truncated
    to the window the fit may see; `games` is the matching game frame, used for
    the game weights and for the points-scale regression. Neither is sliced here:
    one module owns the slicing (report 02 §5.1).

    `ep_model` short-circuits the expected-points fit when the caller already has
    one for this exact window, which is how a season's walk costs one EP fit per
    week rather than one per layer per week.
    """
    cfg = config if config is not None else load_config()
    eff = cfg["efficiency"]

    if ep_model is None:
        ep_model = _fit_ep(plays, cfg)

    if plays.is_empty() or games.is_empty():
        return _empty(cfg, ep_model)

    valued = ep.play_values(plays, ep_model, cfg)
    keep = [str(c) for c in eff["design_play_classes"]]
    valued = valued.filter(pl.col("play_class").is_in(keep))
    if valued.is_empty():
        return _empty(cfg, ep_model)

    weights_by_game = dict(
        zip(
            [int(g) for g in games["game_id"].to_list()],
            design.game_weights(games, cfg).tolist(),
            strict=True,
        )
    )

    d, theta, cv = _solve_one(valued, cfg, None, weights_by_game)
    teams = d.teams
    alpha = {t: float(theta[i]) for i, t in enumerate(teams)}
    beta = {t: float(theta[d.n_teams + i]) for i, t in enumerate(teams)}
    net = {t: alpha[t] - beta[t] for t in teams}

    k, k_intercept, k_site, n_k_games, k_universe = _fit_k(games, net, cfg)

    units: dict[str, UnitFit] = {}
    if bool(eff["unit_splits"]):
        for unit in ("rush", "pass"):
            subset = valued.filter(pl.col("play_class") == unit)
            if subset.is_empty():
                continue
            # The unit fits share the base fit's lambda and team index rather
            # than searching their own. Sharing the index keeps every team in
            # every table (a team that never ran the ball still needs a row), and
            # sharing lambda keeps the three fits comparable, which is the only
            # thing the unit splits are for.
            du, tu, _ = _solve_one(subset, cfg, teams, weights_by_game, lam=cv.lam)
            units[unit] = UnitFit(
                unit=unit,
                alpha={t: float(tu[i]) for i, t in enumerate(teams)},
                beta={t: float(tu[du.n_teams + i]) for i, t in enumerate(teams)},
                home_field=float(tu[du.site_index]),
                intercept=float(tu[du.intercept_index]),
                lam=cv.lam,
                n_plays=int(subset.height),
            )

    params = _static_params(cfg)
    params["k_scale_universe"] = k_universe
    params["effective_plays"] = float(np.sum(d.w))
    params["garbage_time_plays_dropped"] = int(np.sum(d.w == 0.0))
    return L1Fit(
        alpha=alpha,
        beta=beta,
        home_field=float(theta[d.site_index]),
        intercept=float(theta[d.intercept_index]),
        lam=cv.lam,
        k=k,
        k_intercept=k_intercept,
        k_site=k_site,
        n_plays=int(valued.height),
        n_teams=d.n_teams,
        n_games=n_k_games,
        cv=cv,
        ep_model=ep_model,
        units=units,
        params=params,
    )


def _fit_ep(plays: pl.DataFrame, cfg: dict[str, Any]) -> ep.EPModel:
    """The expected-points table for this window, per `[ep].fit_scope`.

    "training_window" fits on exactly these plays and leaks nothing. "frozen"
    loads `[ep].frozen_seasons` off the archive, which is simpler and is what
    report 02 Appendix B sketches, and which means any number produced under it
    has seen the weeks it is predicting. model/ep.py's docstring says so at
    length; this is where the choice is made.
    """
    scope = str(cfg["ep"]["fit_scope"])
    if scope == "training_window":
        return ep.fit(plays, cfg)
    if scope == "frozen":
        from cfbpoll.ingest.plays import attach_games, load_plays
        from cfbpoll.ingest.sportsdataverse import load_games

        seasons = [int(s) for s in cfg["ep"]["frozen_seasons"]]
        frozen_games = load_games(seasons, universe=str(cfg["model"]["fit_universe"]))
        return ep.fit(attach_games(load_plays(seasons), frozen_games), cfg)
    raise ValueError(f"unknown ep.fit_scope {scope!r}; expected training_window | frozen")


def efficiency_to_points(
    alpha: dict[str, float],
    beta: dict[str, float],
    k: float,
) -> dict[str, float]:
    """Rescale (alpha_t - beta_t) from value/play to the points scale using k."""
    teams = sorted(set(alpha) | set(beta))
    return {t: k * (alpha.get(t, 0.0) - beta.get(t, 0.0)) for t in teams}


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None = None,
    through_week: int | None = None,
    state: Any = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Challenger-protocol entry point (report 03 §7.3): efficiency alone, in points.

    `games` and `plays` arrive ALREADY truncated by the harness - no system is
    allowed to select its own rows - and `through_week` is informational. L1 on
    its own is not the poll and is not expected to beat L2; it is published as a
    system so that the blend's contribution is visible rather than asserted.
    """
    del through_week, state
    if plays is None:
        return {}
    return fit(plays, games, config).point_ratings
