"""L4 - Resume rating: the "deserve" number, and THE HEADLINE POLL.

Specified by report 02 §3.4. This is ESPN's Strength-of-Record idea put on the
points scale and made deterministic - a root-solve instead of a 20,000-run Monte
Carlo, so it is cheaper AND exactly reproducible.

For a team t with games g against opponents o_g at sites s_g (+1 home, -1 away,
0 neutral):

    mu_g(q) = q - Power_{o_g} + h * s_g
    P_g(q)  = Phi( mu_g(q) / sigma )
    E[W|q]  = sum_g P_g(q)

    Resume_t = the unique q* with E[W|q*] = W_t   (actual wins)

E[W|q] is strictly increasing and continuous in q, so bisection on q in
[-60, +60] converges to machine precision in ~60 iterations, each costing n
normal CDF evaluations. Microseconds per team. sigma = 15.3 points, confirmed
twice independently (report 02 §5.4).

Reads in one sentence a fan can parse: "given who they played and where, these
results are what a +18.4 team would be expected to produce."

Margin-aware variant (a Game Control analogue): solve instead for the q* where
the expected compressed margin equals the actual, using 20-node Gauss-Hermite
quadrature. Publish both; disagreement between them is informative.

WHAT "POWER" IS TODAY, AND WHY EVERY ARTIFACT SAYS SO. Report 02 §3.4 reads
opponent quality off L3, the blend of L1 efficiency and L2 results. Neither L1
nor L3 exists yet (report 02 Appendix B builds them fourth and fifth), so Power
here is L2 - and that is recorded as `power_source = "L2"`, `power_version =
"v0"` in model_params.json, in poll.json, and in every row of the retroactive
grid. When L3 lands, this module changes in exactly one place: `power_from_l2`
is replaced by a call into l3_power, the recorded source becomes "L3", and
nothing else in the resume math moves. That is the whole point of §3.4's
construction - the resume depends on opponent quality ONLY through Power.

THE UNITS PROBLEM, which is not optional. L2 ratings are in COMPRESSED-RESPONSE
units: the fit's response is `C*tanh(m/C) + beta_w*sign(m)`, not m, so a rating
difference of 1.0 is not one point. sigma is in points. Feeding raw L2 ratings
into the root-solve would silently rescale every win probability in the system.
So one ordinary least squares per fit maps them onto points:

    actual_margin ~ b * (rating_home - rating_away) + h_points * site

fitted with NO intercept (a zero rating difference at a neutral site must mean a
zero expected margin - that is what "points scale" means), and then
`Power_t = b * rho_t`. `b` and `h_points` are published every week beside lambda
and beta_w. The universe for that one regression is FBS-vs-FBS, because that is
where sigma = 15.3 came from; it falls back to the whole fit universe when a
window holds too few such games. Both constants live in [resume] in the config.

The resume is invariant to a constant shift of every Power rating - shift Power
by c and every q* shifts by c, leaving both the rank order and the
resume-minus-power gap untouched - so the zero point of the L2 fit (league
average over the model universe, which includes FCS) costs the ranking nothing.

SATURATION, i.e. the separation problem in its deterministic clothes. E[W|q]
approaches n from below as q grows without bound, so an UNDEFEATED team has no
finite root, and a WINLESS team has none at the bottom. This is exactly
Bradley-Terry's separation problem (report 02 §2.10) - a perfect record makes
the likelihood monotone and the maximum sits at infinity. Our regularization is
the bracket: `q_bounds` in the config, published, and a saturated team is
FLAGGED in every artifact rather than quietly reported as though it were a root.
Two consequences worth stating in public:

  1. On the wins-based resume no one-loss team can outrank an undefeated team,
     however soft the unbeaten schedule. That is not a bug; it is what "these
     results are consistent with arbitrarily high quality" means.
  2. Saturated teams all land on the same bound, so the published ORDER among
     them comes from the margin-aware variant, which is finite for every team
     and is published in the same table. The rule is `saturation_tiebreak` in
     the config and it is stated on the poll page, not hidden in code.

The resume target is RAW wins and RAW compressed margin, unweighted: the [weights]
game weights shape the Power fit, not the accomplishment. The bowl-weight policy
of report 02 §3.8 is honoured where it belongs - the final published poll is the
one computed before non-CFP bowls (`final_poll_excludes_non_cfp_bowls`), which is
a choice of evaluation window N, not a discount inside the root-solve.

FBS-vs-FCS games count in the resume. The opponent holds a real coefficient in
the same fit under the same penalty (report 02 §3.7), so beating an FCS team is
worth exactly what beating a team of that rating is worth - which is nearly
nothing, arrived at honestly rather than by a rule.

THE RETROACTIVE MECHANISM, in one substitution (report 02 §3.4, §3.6):
Resume_t depends on opponent quality ONLY through Power_{o_g}. Pass
through-week-N Power ratings and you get the live ranking R(N,N); pass
end-of-season Power ratings and you get the hindsight ranking R(N,final).
Nothing else changes. That is constraint 4, satisfied definitionally rather than
bolted on - and it is why the estimator is a batch refit and not an Elo. The two
argument surface lives in model/retro.py.

PURITY AND DETERMINISM. Every function here is pure. No I/O, no state, no RNG.
Teams are sorted by name, games sorted by game_id, and the returned mappings are
built in sorted order, so no dict iteration order can reach a file (report 03
§9.3 item 3). The batch solver is a fixed-iteration vectorised bisection - the
same number of operations in the same order for every input - and the scalar
reference implementations below are cross-checked against it in the tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl
from scipy.special import ndtr

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.model import design, l2_results

__all__ = [
    "L4Fit",
    "PowerSource",
    "power_source",
    "expected_compressed_margin",
    "expected_wins",
    "fit",
    "power_from_l2",
    "rate",
    "rate_hindsight",
    "resume_frame",
    "solve_quality",
    "solve_quality_margin",
]

LAYER = "L4 resume rating"
VERSION = "v0"

#: The version of the L2-as-Power path. A LAYER DECLARES ITS OWN VERSION rather
#: than reading one out of the config, because "which code produced this number"
#: is a fact about the code and not a methodology choice a user may set. Before
#: L3 existed the config carried `power_version` and `power_from_l2` stamped it;
#: once two Power sources exist that arrangement can only lie, because the config
#: holds one string and the run may take either path (a season with no play feed
#: falls back to L2 whatever the config says).
POWER_L2_VERSION = "v0"

#: Saturation codes, written to every artifact as `saturated`.
SATURATED_NONE = 0
SATURATED_HIGH = 1  # undefeated: E[W|q_max] still short of the actual win total
SATURATED_LOW = -1  # winless: E[W|q_min] still above the actual win total

#: A team's expected total may miss its actual by this much before we call the
#: bracket saturated. Well below the resolution of a win (1.0) and of a
#: compressed margin unit, and far above bisection's terminal error.
_SATURATION_TOL = 1e-9


# --------------------------------------------------------------------------- power


@dataclass(frozen=True)
class PowerSource:
    """Opponent quality on the POINTS scale, plus the provenance of every number.

    `ratings` is what the root-solve consumes; everything else exists so a reader
    can tell exactly which layer produced it and how it was rescaled.
    """

    ratings: dict[str, float]
    home_field: float
    scale: float
    source: str
    version: str
    scale_universe: str
    n_scale_games: int
    l2: l2_results.L2Fit | None = None
    l3: Any = None  # l3_power.L3Fit, typed loosely to keep the import one-way
    #: The multiplier that carries a compressed-response standard error onto the
    #: points scale. For the L2 path it is `scale` (the OLS `b`); for L3 it is
    #: `w2`, because the results core enters Power multiplied by w2.
    se_scale: float = 0.0
    #: What the published error bar does and does NOT propagate. Never None: a
    #: number with an unstated scope is worse than no number.
    se_note: str = ""
    #: sigma, ESTIMATED FROM THIS SYSTEM'S OWN WALK-FORWARD RESIDUALS over the
    #: data window this Power source belongs to, with the config's 15.3 as the
    #: thin-window fallback and floor (l3_power.estimate_sigma, review S6). None
    #: only when no walk produced one, in which case the config value is used and
    #: `sigma_for` records that it did.
    sigma: float | None = None
    sigma_source: str = ""
    sigma_n_games: int = 0

    def rating(self, team: str) -> float:
        """Unseen teams sit at 0.0 - the league-average prior, not a guess."""
        return self.ratings.get(team, 0.0)

    def rating_se(self, team: str) -> float | None:
        """Standard error of this team's Power rating, IN POINTS.

        From the ridge sandwich of report 02 §3.3 (model/ridge.py::sandwich),
        rescaled by whatever carries the results core onto the points scale. See
        `se_note` for what is propagated: with Power = L3 the efficiency half is
        held at its point estimate, because a play-level covariance is a
        different object and is not built.
        """
        if self.l2 is None or self.l2.sandwich is None:
            return None
        se = self.l2.rating_se().get(team)
        return None if se is None else abs(self.se_scale) * se

    def difference_se(self, a: str, b: str) -> float | None:
        """SE of Power(a) - Power(b), in points. THE quantity a ranking argument
        is about, and not the two individual errors added in quadrature - two
        teams that share opponents share estimation error (ridge.difference_se).
        """
        if self.l2 is None:
            return None
        se = self.l2.difference_se(a, b)
        return None if se is None else abs(self.se_scale) * se

    def as_params(self) -> dict[str, Any]:
        """The model_params.json block for the opponent-quality source."""
        params = {
            "power_source": self.source,
            "power_version": self.version,
            "power_scale_b": self.scale,
            "power_home_field_points": self.home_field,
            "power_scale_universe": self.scale_universe,
            "power_scale_n_games": self.n_scale_games,
            "power_se_scale": self.se_scale,
            "power_se_note": self.se_note,
            "power_sigma": self.sigma,
            "power_sigma_source": self.sigma_source or "config",
            "power_sigma_n_out_of_sample_games": self.sigma_n_games,
        }
        if self.l2 is not None and self.l2.sandwich is not None:
            params["power_se_median_points"] = float(
                np.median(
                    [abs(self.se_scale) * v for v in self.l2.rating_se().values()] or [float("nan")]
                )
            )
        if self.l3 is not None:
            params.update(self.l3.as_params())
        return params


def power_source(
    games: pl.DataFrame,
    config: dict[str, Any] | None = None,
    plays: pl.DataFrame | None = None,
    state: Any = None,
    l2fit: l2_results.L2Fit | None = None,
) -> PowerSource:
    """Opponent quality, from whichever layer `[resume].power_source` names.

    THIS FUNCTION IS THE WHOLE OF THE L2 -> L3 SWITCH. Report 02 §3.4 constructs
    the résumé so that it depends on opponent quality ONLY through Power, which
    means changing the source changes one call and no arithmetic anywhere else.
    Both remain available so the backtest can score them against each other
    rather than the choice being asserted.

    Falls back to L2 when `power_source = "L3"` but no plays are available - a
    season with no play feed, or a caller that has none - because a Power rating
    from the results core is a real answer and a crash is not. The returned
    `source` says which one it is, and every artifact stamps it.
    """
    cfg = config if config is not None else load_config()
    requested = str(cfg["resume"]["power_source"]).upper()
    if requested == "L3" and plays is not None:
        from cfbpoll.model import l3_power

        return l3_power.power_from_l3(games, plays, cfg, state=state, l2fit=l2fit)
    if requested not in ("L2", "L3"):
        raise ValueError(f"unknown resume.power_source {requested!r}; expected L2 | L3")
    return power_from_l2(games, cfg, l2fit=l2fit)


def sigma_for(power: PowerSource | None, config: dict[str, Any]) -> tuple[float, str]:
    """(sigma, source) for a fit reading opponent quality off `power`.

    THE ONE PLACE sigma IS DECIDED, so the résumé, the headline ordering and the
    bootstrap cannot disagree about the denominator of a win probability. A Power
    source that came out of a walk carries the estimate measured on that walk; one
    that did not falls back to `[resume].sigma` and says so.
    """
    fallback = float(config["resume"]["sigma"])
    if power is None or power.sigma is None:
        return fallback, "config"
    return float(power.sigma), power.sigma_source or "walk_forward_residuals"


def _fit_points_scale(games: pl.DataFrame, ratings: dict[str, float]) -> tuple[float, float, int]:
    """OLS of `margin ~ b*(rho_h - rho_a) + h_points*site`, no intercept.

    Returns (b, h_points, n_games). An empty or rank-deficient frame degrades to
    the minimum-norm solution rather than raising, which is what week 1 needs.
    """
    if games.is_empty():
        return (1.0, 0.0, 0)
    delta = np.array(
        [
            ratings.get(h, 0.0) - ratings.get(a, 0.0)
            for h, a in zip(games["home_team"].to_list(), games["away_team"].to_list(), strict=True)
        ],
        dtype=np.float64,
    )
    site = np.where(games["neutral_site"].to_numpy(), 0.0, 1.0)
    margin = (games["home_points"] - games["away_points"]).to_numpy().astype(np.float64)
    x = np.column_stack([delta, site])
    coef, *_ = np.linalg.lstsq(x, margin, rcond=None)
    return (float(coef[0]), float(coef[1]), int(games.height))


def power_from_l2(
    games: pl.DataFrame,
    config: dict[str, Any] | None = None,
    l2fit: l2_results.L2Fit | None = None,
) -> PowerSource:
    """Power = the L2 rating, rescaled to points. The v0 opponent-quality source.

    `games` is the exact window the Power fit may see - the K argument of
    R(N, K). Pass `l2fit` to reuse a fit that has already been computed for this
    window; the grid does exactly that, which is why the whole N x K triangle
    costs one L2 fit per column rather than one per cell.
    """
    cfg = config if config is not None else load_config()
    res = cfg["resume"]
    games = games.sort("game_id")
    fitted = l2fit if l2fit is not None else l2_results.fit(games, cfg)

    universe = str(res["power_scale_universe"])
    scale_games = games
    if universe == "fbs_vs_fbs":
        scale_games = games.filter(
            (pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs")
        )
    if scale_games.height < int(res["power_scale_min_games"]):
        scale_games = games
        universe = f"{universe}_fallback_all"

    b, h_points, n = _fit_points_scale(scale_games, fitted.ratings)
    return PowerSource(
        ratings={team: b * value for team, value in sorted(fitted.ratings.items())},
        home_field=h_points,
        scale=b,
        source="L2",
        version=POWER_L2_VERSION,
        scale_universe=universe,
        n_scale_games=n,
        l2=fitted,
        se_scale=b,
        se_note=(
            "ridge sandwich on the L2 fit (report 02 §3.3), rescaled to points by "
            "the same b that rescales the rating. It propagates the sampling "
            "uncertainty of the results core and NOT the uncertainty in b itself, "
            "which is second order at this sample size"
        ),
    )


# ------------------------------------------------------------------ the estimator


def expected_wins(
    q: float,
    opponent_power: list[float] | np.ndarray,
    sites: list[int] | np.ndarray,
    h: float,
    sigma: float,
) -> float:
    """E[W | q] against this exact schedule (report 02 §3.4).

    The scalar reference implementation. Strictly increasing and continuous in q,
    bounded above by the number of games and below by zero.
    """
    mu = q - np.asarray(opponent_power, dtype=np.float64) + h * np.asarray(sites, dtype=np.float64)
    return float(np.sum(ndtr(mu / sigma)))


def _gauss_hermite(nodes: int) -> tuple[np.ndarray, np.ndarray]:
    """Physicists' Gauss-Hermite nodes and weights, for E[f(m)], m ~ N(mu, sigma^2).

    E[f(m)] = (1/sqrt(pi)) * sum_i w_i * f(mu + sqrt(2)*sigma*x_i). 20 nodes is
    plenty for a tanh (report 02 §3.4); the integrand is smooth and bounded.
    """
    x, w = np.polynomial.hermite.hermgauss(int(nodes))
    return x, w / np.sqrt(np.pi)


def expected_compressed_margin(
    q: float,
    opponent_power: list[float] | np.ndarray,
    sites: list[int] | np.ndarray,
    h: float,
    sigma: float,
    c: float,
    beta_w: float,
    nodes: int = 20,
) -> float:
    """sum_g E[s | q] with s = C*tanh(m/C) + beta_w*sign(m), m ~ N(mu_g(q), sigma^2).

    The win-premium half is closed form - E[sign(m)] = 2*Phi(mu/sigma) - 1 - so
    only the tanh needs quadrature. That keeps the margin-aware variant within a
    small constant factor of the wins-based one.
    """
    mu = q - np.asarray(opponent_power, dtype=np.float64) + h * np.asarray(sites, dtype=np.float64)
    x, w = _gauss_hermite(nodes)
    m = mu[:, None] + np.sqrt(2.0) * sigma * x[None, :]
    tanh_part = (c * np.tanh(m / c)) @ w
    sign_part = beta_w * (2.0 * ndtr(mu / sigma) - 1.0)
    return float(np.sum(tanh_part + sign_part))


def _bisect(
    evaluate: Any,
    target: np.ndarray,
    lo: float,
    hi: float,
    max_iter: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised bisection for a strictly increasing `evaluate` (report 02 §3.4).

    One fixed-length loop over every team at once: the same number of operations
    in the same order for every input, which is what makes the grid reproducible
    bit for bit. Returns (q, saturation code).

    Saturation is decided BEFORE the loop, from the bracket endpoints, because
    that is the honest statement: an undefeated team's root is not at +60, it is
    absent, and +60 is where the published regularization puts it.
    """
    at_hi = evaluate(np.full(target.shape, hi, dtype=np.float64))
    at_lo = evaluate(np.full(target.shape, lo, dtype=np.float64))
    saturated = np.where(
        at_hi < target - _SATURATION_TOL,
        SATURATED_HIGH,
        np.where(at_lo > target + _SATURATION_TOL, SATURATED_LOW, SATURATED_NONE),
    ).astype(np.int64)

    low = np.full(target.shape, lo, dtype=np.float64)
    high = np.full(target.shape, hi, dtype=np.float64)
    for _ in range(int(max_iter)):
        mid = 0.5 * (low + high)
        below = evaluate(mid) < target
        low = np.where(below, mid, low)
        high = np.where(below, high, mid)
    q = 0.5 * (low + high)

    q = np.where(saturated == SATURATED_HIGH, hi, q)
    q = np.where(saturated == SATURATED_LOW, lo, q)
    return q, saturated


def solve_quality(
    actual_wins: float,
    opponent_power: list[float] | np.ndarray,
    sites: list[int] | np.ndarray,
    h: float,
    sigma: float,
    bounds: tuple[float, float] = (-60.0, 60.0),
    max_iter: int = 60,
) -> tuple[float, int]:
    """Bisect for E[W|q*] = actual wins (report 02 §3.4). Returns (q*, saturation).

    The scalar reference. `bounds` and `max_iter` come from [resume] in the
    config at every real call site; the defaults here match it so the function
    can be read and tested on its own.
    """
    power = np.asarray(opponent_power, dtype=np.float64)
    site = np.asarray(sites, dtype=np.float64)

    def evaluate(q: np.ndarray) -> np.ndarray:
        return np.array([expected_wins(float(v), power, site, h, sigma) for v in q])

    q, sat = _bisect(evaluate, np.array([float(actual_wins)]), bounds[0], bounds[1], max_iter)
    return float(q[0]), int(sat[0])


def solve_quality_margin(
    actual_score: float,
    opponent_power: list[float] | np.ndarray,
    sites: list[int] | np.ndarray,
    h: float,
    sigma: float,
    c: float,
    beta_w: float,
    nodes: int = 20,
    bounds: tuple[float, float] = (-60.0, 60.0),
    max_iter: int = 60,
) -> tuple[float, int]:
    """The margin-aware variant's scalar reference (report 02 §3.4).

    `actual_score` is sum_g of the SAME compressed response the L2 fit uses, so
    the two layers agree on what a 40-point win is worth. Unlike the wins-based
    variant this one has an interior root for every real team: the asymptote is
    n*(C + beta_w), which only a team that won every game by an infinite margin
    could reach.
    """
    power = np.asarray(opponent_power, dtype=np.float64)
    site = np.asarray(sites, dtype=np.float64)

    def evaluate(q: np.ndarray) -> np.ndarray:
        return np.array(
            [
                expected_compressed_margin(float(v), power, site, h, sigma, c, beta_w, nodes)
                for v in q
            ]
        )

    q, sat = _bisect(evaluate, np.array([float(actual_score)]), bounds[0], bounds[1], max_iter)
    return float(q[0]), int(sat[0])


# ------------------------------------------------------------------- the batch fit


@dataclass(frozen=True)
class _Schedule:
    """Every (team, opponent, site, margin) pair in a window, flattened once.

    One game contributes two rows - each participant's view of it - which is what
    makes the whole league's root-solve a single vectorised bisection.
    """

    teams: tuple[str, ...]
    team_index: np.ndarray
    opponent_power: np.ndarray
    sites: np.ndarray
    wins: np.ndarray
    compressed: np.ndarray

    @property
    def n_teams(self) -> int:
        return len(self.teams)


def _schedule(games: pl.DataFrame, power: PowerSource, c: float, beta_w: float) -> _Schedule:
    games = games.sort("game_id")
    home = games["home_team"].to_list()
    away = games["away_team"].to_list()
    margin = (games["home_points"] - games["away_points"]).to_numpy().astype(np.float64)
    neutral = games["neutral_site"].to_numpy()

    teams = tuple(sorted(set(home) | set(away)))
    index = {t: i for i, t in enumerate(teams)}

    n = len(home)
    team_index = np.empty(2 * n, dtype=np.int64)
    opponent = np.empty(2 * n, dtype=np.int64)
    sites = np.empty(2 * n, dtype=np.float64)
    signed = np.empty(2 * n, dtype=np.float64)

    team_index[0::2] = [index[t] for t in home]
    team_index[1::2] = [index[t] for t in away]
    opponent[0::2] = [index[t] for t in away]
    opponent[1::2] = [index[t] for t in home]
    sites[0::2] = np.where(neutral, 0.0, 1.0)
    sites[1::2] = np.where(neutral, 0.0, -1.0)
    signed[0::2] = margin
    signed[1::2] = -margin

    power_vector = np.array([power.rating(t) for t in teams], dtype=np.float64)
    return _Schedule(
        teams=teams,
        team_index=team_index,
        opponent_power=power_vector[opponent],
        sites=sites,
        wins=(signed > 0).astype(np.float64),
        compressed=design.compress_margin_array(signed, c, beta_w),
    )


@dataclass(frozen=True)
class L4Fit:
    """The resume layer's published output, and everything needed to audit it."""

    resume: dict[str, float]
    resume_margin: dict[str, float]
    saturated: dict[str, int]
    wins: dict[str, int]
    losses: dict[str, int]
    power: PowerSource
    sigma: float
    q_bounds: tuple[float, float]
    tiebreak: str
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def teams(self) -> tuple[str, ...]:
        return tuple(sorted(self.resume))

    def gap(self, team: str) -> float:
        """Resume minus Power - the publishable "over/under-performed" number."""
        return self.resume.get(team, 0.0) - self.power.rating(team)

    def order_key(self, team: str) -> tuple[float, float, str]:
        """The published rank order: resume, then the saturation tie-break, then name.

        The second element is the margin-aware resume when `saturation_tiebreak`
        is "margin" and a constant otherwise. Only saturated teams ever reach it:
        two unsaturated roots of a strictly monotone function are equal only if
        the schedules are, to the last bit.
        """
        second = self.resume_margin.get(team, 0.0) if self.tiebreak == "margin" else 0.0
        return (-self.resume.get(team, 0.0), -second, team)

    def as_params(self) -> dict[str, Any]:
        """The model_params.json payload for this layer (report 03 §5.3)."""
        saturated_high = sorted(t for t, s in self.saturated.items() if s == SATURATED_HIGH)
        saturated_low = sorted(t for t, s in self.saturated.items() if s == SATURATED_LOW)
        return {
            "layer": LAYER,
            "version": VERSION,
            "sigma": self.sigma,
            "q_bounds": list(self.q_bounds),
            "saturation_tiebreak": self.tiebreak,
            "n_saturated_high": len(saturated_high),
            "n_saturated_low": len(saturated_low),
            "saturated_high": saturated_high,
            **self.power.as_params(),
            **self.params,
        }


def fit(
    games: pl.DataFrame,
    config: dict[str, Any] | None = None,
    power: PowerSource | None = None,
    resume_games: pl.DataFrame | None = None,
    through: tuple[int, str, int] | None = None,
    plays: pl.DataFrame | None = None,
    state: Any = None,
) -> L4Fit:
    """Solve the resume for every team. Pure function of its arguments.

    `games` is the Power window (the K of R(N, K)); `resume_games` is the resume
    window (the N), defaulting to `games` for the live surface R(N, N). Passing a
    truncated `resume_games` with a full-season `games` is the entire hindsight
    mechanism of report 02 §3.6 variant A - one substitution, nothing else.

    `power` short-circuits the L2 fit when the caller already has one for this
    exact window.
    """
    cfg = config if config is not None else load_config()
    res = cfg["resume"]
    c = float(cfg["margin"]["c"])
    beta_w = float(cfg["margin"]["beta_w"])
    lo, hi = (float(x) for x in res["q_bounds"])
    max_iter = int(res["bisection_max_iter"])
    nodes = int(res["gauss_hermite_nodes"])
    tiebreak = str(res["saturation_tiebreak"])

    if through is not None:
        season, season_type, week = through
        games = windows.games_through(games, season=season, week=week, season_type=season_type)

    games = games.sort("game_id")
    if power is None:
        power = power_source(games, cfg, plays=plays, state=state)
    # sigma comes from the Power source's own walk-forward residuals, not from the
    # config constant (review S6). Resolved AFTER power, which is why it is here
    # and not with the other constants above.
    sigma, sigma_source = sigma_for(power, cfg)

    window = games if resume_games is None else resume_games.sort("game_id")
    if window.is_empty():
        return L4Fit(
            resume={},
            resume_margin={},
            saturated={},
            wins={},
            losses={},
            power=power,
            sigma=sigma,
            q_bounds=(lo, hi),
            tiebreak=tiebreak,
            params={"n_resume_games": 0, "n_resume_teams": 0},
        )

    sched = _schedule(window, power, c, beta_w)
    h = power.home_field
    n_teams = sched.n_teams

    wins_target = np.bincount(sched.team_index, weights=sched.wins, minlength=n_teams)
    margin_target = np.bincount(sched.team_index, weights=sched.compressed, minlength=n_teams)
    played = np.bincount(sched.team_index, minlength=n_teams).astype(np.float64)

    x, w = _gauss_hermite(nodes)

    def expected_wins_all(q: np.ndarray) -> np.ndarray:
        mu = q[sched.team_index] - sched.opponent_power + h * sched.sites
        return np.bincount(sched.team_index, weights=ndtr(mu / sigma), minlength=n_teams)

    def expected_margin_all(q: np.ndarray) -> np.ndarray:
        mu = q[sched.team_index] - sched.opponent_power + h * sched.sites
        m = mu[:, None] + np.sqrt(2.0) * sigma * x[None, :]
        per_game = (c * np.tanh(m / c)) @ w + beta_w * (2.0 * ndtr(mu / sigma) - 1.0)
        return np.bincount(sched.team_index, weights=per_game, minlength=n_teams)

    q_wins, saturated = _bisect(expected_wins_all, wins_target, lo, hi, max_iter)
    q_margin, _ = _bisect(expected_margin_all, margin_target, lo, hi, max_iter)

    teams = sched.teams
    return L4Fit(
        resume={t: float(q_wins[i]) for i, t in enumerate(teams)},
        resume_margin={t: float(q_margin[i]) for i, t in enumerate(teams)},
        saturated={t: int(saturated[i]) for i, t in enumerate(teams)},
        wins={t: int(wins_target[i]) for i, t in enumerate(teams)},
        losses={t: int(played[i] - wins_target[i]) for i, t in enumerate(teams)},
        power=power,
        sigma=sigma,
        q_bounds=(lo, hi),
        tiebreak=tiebreak,
        params={
            "n_resume_games": int(window.height),
            "n_resume_teams": n_teams,
            "gauss_hermite_nodes": nodes,
            "bisection_max_iter": max_iter,
            "sigma_source": sigma_source,
            "resume_target": "raw wins, and raw compressed margin; game weights "
            "shape the Power fit, not the accomplishment",
        },
    )


def resume_frame(fitted: L4Fit, classes: dict[str, str] | None = None) -> pl.DataFrame:
    """One row per team, sorted by the published order. The shape everything writes.

    Ranks are assigned over FBS teams only - the poll is a college football poll -
    while every team in the fit keeps its row and its classification, so the same
    file supports an all-divisions ranking for anyone who wants one (report 02
    §7.9, and publish/poll.py for the same decision at L2).
    """
    classes = classes or {}
    teams = sorted(fitted.resume, key=fitted.order_key)
    frame = pl.DataFrame(
        {
            "team": teams,
            "team_class": [classes.get(t, "unknown") for t in teams],
            "wins": pl.Series([fitted.wins[t] for t in teams], dtype=pl.Int32),
            "losses": pl.Series([fitted.losses[t] for t in teams], dtype=pl.Int32),
            "resume": [fitted.resume[t] for t in teams],
            "resume_margin": [fitted.resume_margin[t] for t in teams],
            "power": [fitted.power.rating(t) for t in teams],
            "gap": [fitted.gap(t) for t in teams],
            "saturated": pl.Series([fitted.saturated[t] for t in teams], dtype=pl.Int8),
        }
    )
    is_fbs = frame["team_class"] == "fbs"
    ranks = np.full(frame.height, 0, dtype=np.int32)
    ranks[is_fbs.to_numpy()] = np.arange(1, int(is_fbs.sum()) + 1, dtype=np.int32)
    return frame.with_columns(
        rank=pl.when(is_fbs).then(pl.Series(ranks)).otherwise(None).cast(pl.Int32)
    ).select(
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


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None = None,
    through_week: int | None = None,
    state: Any = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Challenger-protocol entry point (report 03 §7.3): the incumbent headline poll.

    `games` and `plays` arrive ALREADY truncated by the harness - no system
    selects its own rows - and `through_week` is informational. Returns the
    wins-based resume, which is the headline number; the margin-aware variant and
    the Power rating are on `fit()` for callers that want the whole picture.
    """
    del through_week
    return fit(games, config, plays=plays, state=state).resume


def rate_hindsight(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    eval_week: int,
    data_window: int,
    season: int | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    """R(eval_week, data_window): the retroactive surface (report 02 §3.6, variant A).

    Frozen-form hindsight: Power from the FULL season, Resume from that team's
    games THROUGH eval_week only. Answers the plain-English question "given what
    we now know about how good those opponents actually were, how good were the
    first N weeks of results?" The time-varying form (variant B, a state-space
    model) is a documented future direction, not v1.

    This is the convenience wrapper for a single cell keyed on regular-season week
    numbers. `model/retro.py` owns the bucket-ordered, all-season-types version
    and the full N x K grid.
    """
    del plays
    cfg = config if config is not None else load_config()
    if season is None:
        season = int(games["season"].min())  # type: ignore[arg-type]
    power_window = windows.games_through(games, season=season, week=data_window)
    resume_window = windows.games_through(games, season=season, week=eval_week)
    return fit(power_window, cfg, resume_games=resume_window).resume
