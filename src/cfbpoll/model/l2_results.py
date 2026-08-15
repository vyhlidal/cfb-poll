"""L2 - results core: ridge on compressed scoring margin.

Specified by report 02 §3.2.

    s_g = C * tanh(m_g / C) + beta_w * sign(m_g)          (the response)
    s_g = rho_h - rho_a + h * site_g + eps_g              (the model)

`h` is unpenalised; every team coefficient carries the same penalty. There is no
separate intercept - report 02 §3.2 fixes the L2 design at G x (T+1), and see
model/design.py for why adding one is not merely redundant but singular.
h is ALSO estimated independently from home-and-home series only, per Pasteur,
because the regression's schedule is structurally asymmetric - power programs buy
home games that never get a return trip. Pasteur obtained ~3.70 points; recent
independent estimates put CFB home field nearer 2.8. Both are computed and both
are published; the regression coefficient is the one the model uses, because the
home-and-home estimator needs consecutive seasons and constraint 2 forbids prior
seasons in a fit.

Game weights v_g: non-CFP bowls down-weighted (roster availability is
systematically compromised); conference championships and CFP games at full
weight; FBS-vs-FCS at full weight with no special handling (report 02 §3.8, §3.7).
The live values live in configs/default.toml under [weights].

Every FBS team, every FCS team, and every lower-division team that appears in the
frame gets its OWN coefficient under the SAME penalty. No pooled "FCS" node -
that is precisely ESPN's pre-2015 FPI failure, which cost Iowa State 31 spots for
losing to a North Dakota State the model could not know was good (report 02 §3.7).

This layer alone is a complete, working, constraint-compliant ranking system.
Everything after it is improvement, not prerequisite.

PURITY AND DETERMINISM. `fit` is a pure function of (games, config, through).
It performs no I/O, holds no state, and contains no RNG. Inputs are sorted by
game_id, teams are sorted by name, and the returned mapping is built in sorted
order, so no dict iteration order can reach a file (report 03 §9.3 item 3).
Callers should pin the BLAS thread count to 1 (see ridge.py).

CONSTRAINT AUDIT. The columns that reach the design matrix are: final score,
team ids, site, game type. Nothing else. No poll, no recruiting, no returning
production, no prior-season rating, no third-party rating, no conference, no
betting line (report 02 §3.10).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.model import design, ridge

__all__ = ["L2Fit", "estimate_home_field", "fit", "home_and_home_estimate", "rate"]

LAYER = "L2 results core"
VERSION = "v0"


@dataclass(frozen=True)
class L2Fit:
    """Everything a published poll needs to be auditable."""

    ratings: dict[str, float]
    home_field: float
    lam: float
    n_games: int
    n_teams: int
    cv: ridge.CVResult
    params: dict[str, Any] = field(default_factory=dict)
    #: Teams in DESIGN-MATRIX ORDER, which is what indexes `sandwich.cov`. Sorted
    #: by name, so it is a pure function of the frame.
    teams: tuple[str, ...] = ()
    #: The ridge sandwich covariance of the team coefficients, in COMPRESSED-
    #: RESPONSE units (report 02 §3.3, model/ridge.py::sandwich). None only for
    #: an empty fit.
    sandwich: ridge.Sandwich | None = None

    def rating(self, team: str) -> float:
        """Ratings default to 0.0 - the league-average prior - for unseen teams."""
        return self.ratings.get(team, 0.0)

    def rating_se(self) -> dict[str, float]:
        """Per-team standard error, in compressed-response units. Empty if unfitted."""
        if self.sandwich is None:
            return {}
        se = self.sandwich.se()
        return {team: float(se[i]) for i, team in enumerate(self.teams)}

    def difference_se(self, a: str, b: str) -> float | None:
        """SE of rating(a) - rating(b), in compressed-response units.

        None when either team is absent from the fit. See ridge.difference_se for
        why this is not the two individual errors added in quadrature.
        """
        if self.sandwich is None:
            return None
        index = {team: i for i, team in enumerate(self.teams)}
        if a not in index or b not in index:
            return None
        return ridge.difference_se(self.sandwich.cov, index[a], index[b])

    def predict(self, home: str, away: str, neutral: bool = False) -> float:
        """Predicted compressed-response margin. Points-scale calibration is the
        backtest harness's job (see backtest/walkforward.py)."""
        site = 0.0 if neutral else 1.0
        return self.rating(home) - self.rating(away) + self.home_field * site

    def as_params(self) -> dict[str, Any]:
        """The model_params.json payload for this layer (report 03 §5.3)."""
        return {
            "layer": LAYER,
            "version": VERSION,
            "lambda": self.lam,
            "home_field": self.home_field,
            "n_games": self.n_games,
            "n_teams": self.n_teams,
            "cv": self.cv.as_dict(),
            **self.params,
        }


def fit(
    games: pl.DataFrame,
    config: dict[str, Any] | None = None,
    through: tuple[int, str, int] | None = None,
) -> L2Fit:
    """Fit the L2 ridge. Pure function of (games, config, through).

    `through` is the (season, season_type, week) triple of docs/data-findings.md
    §1 - never a bare week. When given, the frame is sliced by
    `ingest.windows.games_through`, which is the only sanctioned slicer.
    """
    cfg = config if config is not None else load_config()

    if through is not None:
        season, season_type, week = through
        games = windows.games_through(games, season=season, week=week, season_type=season_type)

    games = games.sort("game_id")
    if games.is_empty():
        return L2Fit(
            ratings={},
            home_field=0.0,
            lam=float(max(cfg["ridge"]["l2_grid"])),
            n_games=0,
            n_teams=0,
            cv=ridge.CVResult(
                lam=float(max(cfg["ridge"]["l2_grid"])),
                grid=tuple(float(x) for x in sorted(cfg["ridge"]["l2_grid"])),
                cv_error=(),
                n_folds=0,
            ),
            params=_static_params(cfg),
        )

    d = design.build_game_design(games, cfg)
    cv = ridge.cv_select_lambda(
        d.Z,
        d.s,
        d.v,
        d.penalty,
        groups=d.game_ids,
        grid=cfg["ridge"]["l2_grid"],
        n_folds=int(cfg["ridge"]["cv_folds"]),
    )
    theta = ridge.solve(d.Z, d.s, d.v, d.penalty, cv.lam)
    cov = ridge.sandwich(d.Z, d.s, d.v, d.penalty, cv.lam, theta)

    ratings = {team: float(theta[i]) for i, team in enumerate(d.teams)}
    params = _static_params(cfg)
    params["home_field_home_and_home"] = estimate_home_field(games)
    params["sandwich"] = cov.as_dict()
    return L2Fit(
        ratings=ratings,
        home_field=float(theta[d.site_index]),
        lam=cv.lam,
        n_games=d.Z.shape[0],
        n_teams=d.n_teams,
        cv=cv,
        params=params,
        teams=d.teams,
        sandwich=cov,
    )


def _publishable(value: float) -> float | str:
    """A constant that JSON can carry, without dropping the one that it cannot.

    `[margin].c = inf` is a REAL value of the parameter and not a missing one: it
    is the limit of the tanh family, `s = m + beta_w*sign(m)`, which campaign 2
    pre-registered and searched and which `configs/recipes/full-merit.toml`
    selects. JSON has no infinity, `json.dumps` would emit the invalid literal
    `Infinity`, and any writer with `allow_nan=False` (publish/fixtures.py) would
    raise instead. So the limit is published under the name campaign 2 gave it.

    Dropping it would be worse than either. `model_params.json` publishes every
    constant a run used, every week, without exception (constraint 5), and the one
    week it is allowed to omit a constant must not be the week that constant is
    the entire argument.
    """
    number = float(value)
    if math.isfinite(number):
        return number
    return "uncapped" if number > 0 else "-uncapped"


def _static_params(cfg: dict[str, Any]) -> dict[str, Any]:
    """The constants that must appear in model_params.json every single week."""
    return {
        "C": _publishable(cfg["margin"]["c"]),
        "beta_w": float(cfg["margin"]["beta_w"]),  # PUBLISH THIS PROMINENTLY - §3.2
        "recency_gamma": float(cfg["weights"]["recency_gamma"]),
        "weight_bowl_non_cfp": float(cfg["weights"]["bowl_non_cfp"]),
        "weight_conference_championship": float(cfg["weights"]["conference_championship"]),
        "weight_cfp": float(cfg["weights"]["cfp"]),
        "weight_regular_season": float(cfg["weights"]["regular_season"]),
        "cv_folds": int(cfg["ridge"]["cv_folds"]),
        "cv_group": str(cfg["ridge"]["cv_group"]),
        "unpenalized": list(cfg["ridge"]["unpenalized"]),
    }


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None = None,
    through_week: int | None = None,
    state: object = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Challenger-protocol entry point (report 03 §7.3). `plays` is unused by L2.

    `games` arrives ALREADY truncated by the harness - no system is allowed to
    select its own rows - and `through_week` is informational.
    """
    del plays, through_week, state
    return fit(games, config).ratings


def estimate_home_field(games: pl.DataFrame) -> float | None:
    """Estimate h from home-and-home series only (report 02 §3.2, after Pasteur).

    Sum the margins from the home team's perspective across every pair of games
    in which A hosted B once and B hosted A another time, and divide by the
    number of games. Neutral-site games are excluded: there is no host.

    This removes the structural asymmetry that biases a regression estimate -
    power programs buy home games against opponents who never get a return trip,
    so the average home team is also the better team. It needs a return trip to
    exist, which within a single season it almost never does. Returns None when
    the frame contains no such pair, which is the normal within-season case, and
    the number is published as a comparison rather than used in the fit
    (constraint 2 forbids prior seasons reaching an estimate the model uses).
    """
    g = games.filter(~pl.col("neutral_site"))
    if g.is_empty():
        return None
    margins: dict[tuple[str, str], list[float]] = {}
    for home, away, hp, ap in zip(
        g["home_team"].to_list(),
        g["away_team"].to_list(),
        g["home_points"].to_list(),
        g["away_points"].to_list(),
        strict=True,
    ):
        margins.setdefault((home, away), []).append(float(hp - ap))

    total = 0.0
    count = 0
    for (home, away), values in sorted(margins.items()):
        reverse = margins.get((away, home))
        if not reverse:
            continue
        total += sum(values)
        count += len(values)
    if count == 0:
        return None
    return float(np.round(total / count, 10))


def home_and_home_estimate(
    games: pl.DataFrame, within_season: bool = True
) -> dict[str, Any]:
    """`estimate_home_field` written per PAIR, so a standard error exists.

    The point estimate is the same quantity `estimate_home_field` returns and the
    two are asserted equal in the tests. What is added is the thing the config
    never carried and campaign 1 found was the finding: how many pairs the
    estimate rests on, and how wide it is.

    THE ARGUMENT, which is why report 02 §3.2 prefers this estimator to a
    regression coefficient: the schedule is structurally asymmetric. Power
    programmes buy home games that never get a return trip, so a regression on
    `site` is estimated partly off the difference between the teams that host and
    the teams that visit. A home-and-home pair is the SAME two teams in both
    venues, so the team effect differences out exactly and what is left is the
    venue:

        h = mean over pairs of  (m_host_leg + m_road_leg) / 2

    with both margins from the perspective of the team hosting that leg. Both legs
    must be non-neutral - a neutral site has no host.

    `within_season=True` is the only form constraint 2 allows today, and it is
    also the form college football almost never supplies: teams schedule
    home-and-home ACROSS years, not inside one. 2021-2023 yields 21 within-season
    pairs and 1,113 pooled. Whether the pooled form may ever be used is ADR 0008's
    question and this function takes no position on it; it computes both and
    labels which is which.
    """
    played = games.filter(~pl.col("neutral_site"))
    margins: dict[tuple[Any, str, str], float] = {}
    for season, home, away, hp, ap in zip(
        played["season"].to_list(),
        played["home_team"].to_list(),
        played["away_team"].to_list(),
        played["home_points"].to_list(),
        played["away_points"].to_list(),
        strict=True,
    ):
        margins[(int(season) if within_season else 0, str(home), str(away))] = float(hp) - float(ap)

    seen: set[tuple[Any, str, str]] = set()
    halves: list[float] = []
    for (season, home, away), margin in sorted(margins.items()):
        mirror = margins.get((season, away, home))
        if mirror is None:
            continue
        key = (season, *sorted((home, away)))
        if key in seen:
            continue
        seen.add(key)
        halves.append((margin + mirror) / 2.0)

    array = np.asarray(halves, dtype=np.float64)
    n = int(array.size)
    return {
        "h": float(np.mean(array)) if n else float("nan"),
        "n_pairs": n,
        "standard_error": float(np.std(array, ddof=1) / np.sqrt(n)) if n > 1 else float("nan"),
        "sd": float(np.std(array, ddof=1)) if n > 1 else float("nan"),
        "median": float(np.median(array)) if n else float("nan"),
        "within_season": bool(within_season),
        "seasons": sorted({int(s) for s in games["season"].to_list()}),
    }
