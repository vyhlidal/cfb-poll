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

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.model import design, ridge

__all__ = ["L2Fit", "estimate_home_field", "fit", "rate"]

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

    def rating(self, team: str) -> float:
        """Ratings default to 0.0 - the league-average prior - for unseen teams."""
        return self.ratings.get(team, 0.0)

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

    ratings = {team: float(theta[i]) for i, team in enumerate(d.teams)}
    params = _static_params(cfg)
    params["home_field_home_and_home"] = estimate_home_field(games)
    return L2Fit(
        ratings=ratings,
        home_field=float(theta[d.site_index]),
        lam=cv.lam,
        n_games=d.Z.shape[0],
        n_teams=d.n_teams,
        cv=cv,
        params=params,
    )


def _static_params(cfg: dict[str, Any]) -> dict[str, Any]:
    """The constants that must appear in model_params.json every single week."""
    return {
        "C": float(cfg["margin"]["c"]),
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
