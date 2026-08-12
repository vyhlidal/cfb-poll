"""Sparse design-matrix construction for L1 and L2.

Specified by report 02 §3.1 (L1) and §3.2 (L2).

L1: X is P x (2T+1) with EXACTLY three non-zeros per row - +1 in the offense
column for o(p), +1 in the defense column for d(p), and H_p in the HFA column
(+1 offense is home, -1 away, 0 neutral). Build it CSR; never materialise it
dense. T is roughly 264 (about 136 FBS plus about 128 FCS), P about 170k/season.

L2: Z is G x (T+1) - +1 home team, -1 away team, site_g in the unpenalised
home-field column. Note what ZᵀZ is on the team block: the schedule graph
Laplacian, the matrix at the heart of both Massey and Colley. Ridge makes it
L + lambda*I, which is positive definite for any lambda > 0 and therefore
invertible EVEN WHEN THE SCHEDULE GRAPH IS DISCONNECTED. That one line
eliminates the whole class of SRS failures seen in 2020 and in weeks 1-3 of any
season, without importing a byte of reputation.

NO SEPARATE INTERCEPT AT L2, and this is deliberate rather than an omission.
configs/default.toml lists `unpenalized = ["intercept", "home_field"]` as the
general rule across layers, and L1 does carry an intercept (report 02 §3.1:
`y_p = mu + alpha + beta + eta*H_p`). L2 does not: report 02 §3.2 fixes the
design at G x (T+1), and an intercept there is exactly collinear with the site
column in any window containing no neutral-site games - the normal matrix is
then singular in an UNPENALISED direction, which no amount of ridge can rescue,
and Cholesky fails outright. Fitting it anyway on 2021-2023 walk-forward moved
margin MAE by 0.02 points in the wrong direction, so nothing is lost. Neutral
sites take site_g = 0 and a consistent home/away orientation, per §3.2.

FCS teams get their own coefficients in the same fit under the same penalty.
Do NOT pool them into a single node - that is precisely ESPN's pre-2015 FPI
failure (report 02 §3.7).

STATUS: L2 is implemented. L1 (play level) is still a scaffold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl
from scipy import sparse

if TYPE_CHECKING:  # pragma: no cover
    pass

__all__ = [
    "GameDesign",
    "build_game_design",
    "compress_margin",
    "compress_margin_array",
    "game_weights",
]


@dataclass(frozen=True)
class GameDesign:
    """The L2 design: `Z @ theta ~ s`, weighted by `v`, penalised by `penalty`.

    Column layout, fixed and sorted so that no dict iteration order can ever
    reach a file (report 03 §9.3 item 3):

        0 .. T-1   one coefficient per team, teams sorted by name
        T          site / home field  (UNPENALISED)
    """

    Z: sparse.csr_matrix
    s: np.ndarray
    v: np.ndarray
    teams: tuple[str, ...]
    penalty: np.ndarray
    game_ids: np.ndarray

    @property
    def n_teams(self) -> int:
        return len(self.teams)

    @property
    def site_index(self) -> int:
        return len(self.teams)


def compress_margin(margin: float, c: float, beta_w: float) -> float:
    """s = C * tanh(m / C) + beta_w * sign(m)   (report 02 §3.2).

    C bounds the value of running up the score without discarding margin - the
    BCS's sportsmanship objection answered by construction rather than by
    throwing away the difference between 3 and 24. Beyond roughly four
    touchdowns additional points are worth essentially nothing, and unlike a hard
    cap there is no discontinuity in the derivative, so a team is never
    indifferent between 27 and 28 and then suddenly indifferent forever after.

    beta_w is the win premium: the discontinuity at zero that makes this a
    football ranking rather than a scoring-margin ranking. Sports-Reference's CFB
    SRS floors margin at +/-7, which corresponds to beta_w ~ 3.0 in this
    parameterisation, and Pasteur's range-adjusting translation is the same
    device arrived at independently.

    beta_w must be published prominently every week. It is the single most
    contested value in the system and hiding it would be a transparency failure.

    The response is bounded: |s| < C + beta_w, always.
    """
    return float(c * np.tanh(margin / c) + beta_w * np.sign(margin))


def compress_margin_array(margin: np.ndarray, c: float, beta_w: float) -> np.ndarray:
    """Vectorised `compress_margin`. Same function, one array at a time."""
    m = np.asarray(margin, dtype=np.float64)
    return c * np.tanh(m / c) + beta_w * np.sign(m)


def game_weights(games: pl.DataFrame, config: dict[str, Any]) -> np.ndarray:
    """v_g from [weights] in the config. Report 02 §3.8 sets the policy.

    Non-CFP bowls are down-weighted (0.25 by default) because their roster
    availability is systematically compromised - 78+ opt-outs and 431 portal
    entries in the 2021-22 postseason, and Florida State lost 33 players before
    the 2023 Orange Bowl. Those games measure something other than team quality.
    Conference championships and CFP games carry full weight: rosters intact,
    stakes maximal. FBS-vs-FCS carries full weight with no special handling.

    Recency `gamma^(weeks_ago)` is available and defaults to 1.0, i.e. off. A
    poll that says "who earned it" should not decide that September didn't count.
    """
    w = config["weights"]
    by_type = {
        "regular": float(w["regular_season"]),
        "conf_champ": float(w["conference_championship"]),
        "cfp": float(w["cfp"]),
        "bowl_non_cfp": float(w["bowl_non_cfp"]),
    }
    base = np.array(
        [by_type[t] for t in games["game_type"].to_list()],
        dtype=np.float64,
    )

    gamma = float(w.get("recency_gamma", 1.0))
    if gamma == 1.0:
        return base

    # weeks_ago is measured in whole weeks back from the last kickoff in the
    # frame, which is well-defined even when week numbers are not (see
    # ingest/windows.py for why week numbers are not).
    kickoff = games["start_date"].to_numpy().astype("datetime64[s]").astype("int64")
    weeks_ago = np.floor((kickoff.max() - kickoff) / (7 * 24 * 3600))
    return base * (gamma**weeks_ago)


def build_game_design(
    games: pl.DataFrame,
    config: dict[str, Any],
    teams: tuple[str, ...] | None = None,
) -> GameDesign:
    """Build the sparse L2 design matrix, compressed response and weight vector.

    `games` must already be the exact set of games the fit is allowed to see.
    This function does no filtering and no week arithmetic on purpose: report 02
    §5.1's walk-forward guarantee holds only if one module owns the slicing, and
    that module is `ingest/windows.py`.
    """
    g = games.sort("game_id")
    home = g["home_team"].to_list()
    away = g["away_team"].to_list()

    if teams is None:
        teams = tuple(sorted(set(home) | set(away)))
    index = {t: i for i, t in enumerate(teams)}

    n_games = g.height
    n_cols = len(teams) + 1

    margin = (g["home_points"] - g["away_points"]).to_numpy().astype(np.float64)
    s = compress_margin_array(
        margin, float(config["margin"]["c"]), float(config["margin"]["beta_w"])
    )
    v = game_weights(g, config)

    # site_g = 1 for a true home game, 0 at a neutral site (report 02 §3.2). At a
    # neutral site the home/away labels are just a consistent orientation.
    site = np.where(g["neutral_site"].to_numpy(), 0.0, 1.0)

    rows = np.repeat(np.arange(n_games), 3)
    cols = np.empty(n_games * 3, dtype=np.int64)
    vals = np.empty(n_games * 3, dtype=np.float64)
    cols[0::3] = [index[t] for t in home]
    vals[0::3] = 1.0
    cols[1::3] = [index[t] for t in away]
    vals[1::3] = -1.0
    cols[2::3] = len(teams)  # site / home field
    vals[2::3] = site

    z = sparse.csr_matrix((vals, (rows, cols)), shape=(n_games, n_cols))

    penalty = np.ones(n_cols, dtype=np.float64)
    penalty[len(teams)] = 0.0  # home field is UNPENALISED

    return GameDesign(
        Z=z,
        s=s,
        v=v,
        teams=teams,
        penalty=penalty,
        game_ids=g["game_id"].to_numpy(),
    )


def build_play_design(plays: Any, weights: Any | None = None) -> Any:
    """Build the sparse L1 design matrix, response and weight vector.

    Returns (X_csr, y, w, column_index) per report 02 §3.1.
    """
    raise NotImplementedError("design.build_play_design - scaffold; see report 02 §3.1")


def garbage_time_weight(quarter: int, score_margin: int, thresholds: dict[str, int]) -> float:
    """Return 0.0 for garbage-time plays, 1.0 otherwise (report 02 §3.1)."""
    raise NotImplementedError("design.garbage_time_weight - scaffold; see report 02 §3.1")
