"""Sparse design-matrix construction for L1 and L2.

Specified by report 02 §3.1 (L1) and §3.2 (L2).

L1: X is P x (2T+2) with EXACTLY four non-zeros per row - +1 in the offense
column for o(p), +1 in the defense column for d(p), H_p in the HFA column
(+1 offense is home, -1 away, 0 neutral), and 1 in the intercept column, which
report 02 §3.1's model equation carries as `mu` and its design-matrix paragraph
forgets. Build it CSR; never materialise it dense. T is roughly 264 (about 136
FBS plus about 128 FCS), P about 165k/season of scrimmage snaps.

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

Both layers are implemented. L1's site column is signed {+1, -1, 0} because the
home team is on offence only about half the time; L2's is {1, 0} because a game
has one host. That is not an inconsistency, it is the same effect in the two
units report 02 §3.1 and §3.2 respectively define it in.
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
    "PlayDesign",
    "build_game_design",
    "build_play_design",
    "garbage_time_weight",
    "play_weights",
    "compress_margin",
    "compress_margin_array",
    "compress_prediction",
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


def compress_prediction(margin: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    """Pasteur's compression of extreme PREDICTED margins (report 02 §2.13).

    Not to be confused with `compress_margin`, which transforms the L2 RESPONSE.
    This one transforms a FORECAST, and it exists because a linear rating
    difference overstates blowouts: the tail of the predicted-margin distribution
    is longer than the tail of the realised one, so the biggest predictions are
    the ones with the most to give back.

        |M| > threshold  ->  M* = sign(M) * (T + (1/a) * [(|M| - (T-1))^a - 1])

    written exactly as `[margin.prediction_compression]` publishes it, with
    T = threshold and a = alpha. It is continuous AND differentiable at the
    threshold - at |M| = T the bracket is zero and the derivative is
    (|M| - (T-1))^(a-1) = 1 - so nothing is discontinuous at the join, which is
    the same property that made tanh preferable to a hard cap one function above.

    WHERE THIS IS APPLIED, AND WHERE IT DELIBERATELY IS NOT. It applies to a
    forecast of an actual game: the backtest harness's predicted margin and
    `L3Fit.predict`. It does NOT apply inside the résumé root-solve or the
    schedule-odds tail, where `mu = q_ref - Power_opponent + h*site` is a
    COUNTERFACTUAL expected margin for a hypothetical reference-quality team
    rather than a forecast of a game anyone played. Pasteur's device is a
    forecasting correction and report 02 §2.13 places it in the prediction
    section; applying it to a counterfactual would compress the very quantity the
    headline ordering is defined on. The scope is stated here rather than left to
    be inferred from which call sites happen to have the import.

    Until the tuning campaign of 2026-08-12 this function did not exist and
    `[margin.prediction_compression]` was configured but implemented NOWHERE in
    `src/` (fresh-eyes review S9). It could not be backtested because it could not
    be run, so `docs/analysis/tuning-campaign.md` implemented it in order to
    search it.
    """
    pc = config["margin"]["prediction_compression"]
    m = np.asarray(margin, dtype=np.float64)
    if not bool(pc.get("enabled", False)):
        return m
    threshold = float(pc["threshold"])
    alpha = float(pc["alpha"])
    magnitude = np.abs(m)
    over = magnitude > threshold
    if not bool(np.any(over)):
        return m
    shifted = np.where(over, magnitude - (threshold - 1.0), 1.0)
    compressed = threshold + (np.power(shifted, alpha) - 1.0) / alpha
    return np.where(over, np.sign(m) * compressed, m)


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


@dataclass(frozen=True)
class PlayDesign:
    """The L1 design: `X @ theta ~ y`, weighted by `w`, penalised by `penalty`.

    Column layout, fixed and sorted so that no dict iteration order can ever
    reach a file (report 03 §9.3 item 3):

        0     .. T-1    offence coefficient per team, teams sorted by name
        T     .. 2T-1   defence coefficient per team, same order
        2T             home field  (UNPENALISED)
        2T+1           intercept   (UNPENALISED)

    Exactly four non-zeros per row, per report 02 §3.1 - the three it names plus
    the intercept, which §3.1's model equation carries as `mu`.
    """

    X: sparse.csr_matrix
    y: np.ndarray
    w: np.ndarray
    teams: tuple[str, ...]
    penalty: np.ndarray
    game_ids: np.ndarray

    @property
    def n_teams(self) -> int:
        return len(self.teams)

    @property
    def offense_slice(self) -> slice:
        return slice(0, len(self.teams))

    @property
    def defense_slice(self) -> slice:
        return slice(len(self.teams), 2 * len(self.teams))

    @property
    def site_index(self) -> int:
        return 2 * len(self.teams)

    @property
    def intercept_index(self) -> int:
        return 2 * len(self.teams) + 1


def garbage_time_weight(period: int, score_margin: float, thresholds: dict[str, int]) -> float:
    """0.0 for a garbage-time play, 1.0 otherwise (report 02 §3.1, after Connelly).

    The threshold is on the ABSOLUTE lead before the snap, so both sides of a
    blowout stop counting at the same moment - which is the point. A defence
    that surrenders a 60-yard run while up 45 in the fourth quarter has not
    revealed anything about its quality, and neither has the offence that ran it.

    Connelly's published thresholds fall through the game (43 / 37 / 29 / 22)
    because a 30-point lead means something very different in the first quarter
    than in the fourth. Overtime cannot be garbage time - the margin is zero by
    construction - and takes the fourth-quarter threshold anyway.
    """
    key = f"q{min(max(int(period), 1), 4)}"
    return 0.0 if abs(float(score_margin)) >= float(thresholds[key]) else 1.0


def play_weights(
    plays: pl.DataFrame,
    config: dict[str, Any],
    game_weights_by_id: dict[int, float] | None = None,
) -> np.ndarray:
    """w_p for the L1 fit: garbage time, dead plays, and the game's own weight.

    Report 02 §3.1 lists three rules and this implements all three.

    1. GARBAGE TIME -> 0, by `[garbage_time].mode`.
       "connelly" (default) and "strict" are the two published threshold sets.
       "leverage" - the continuous `w = 4*WP*(1-WP)` alternative - is NOT
       implemented and raises, because it needs a win-probability model. The
       archive ships one (`wp_before`) and it is banned as an input (report 01
       §5.6); building our own is a real piece of work and pretending otherwise
       by quietly reaching for the shipped column would be exactly the failure
       this project exists to avoid. It is a documented backtest alternative,
       not a live option, and the error message says so.

    2. KNEELS, SPIKES AND END-OF-HALF HEAVES -> 0, by
       `[garbage_time].zero_weight_plays`. A kneel-down is a clock decision, not
       an offence; charging a defence for allowing it would be absurd. The heave
       rule needs two constants and they are in the config with the rest.

    3. THE GAME'S OWN WEIGHT multiplies through, so a non-CFP bowl's plays are
       discounted at L1 exactly as its scoreboard is at L2 (report 02 §3.8). The
       weights come from `game_weights` on the games frame; passing them in
       avoids recomputing per-game facts once per play.
    """
    gt = config["garbage_time"]
    mode = str(gt["mode"])
    if mode == "leverage":
        raise NotImplementedError(
            "garbage_time.mode = 'leverage' needs a win-probability model of our own. "
            "The archive's wp_before is a third party's model output and is banned as an "
            "input (report 01 §5.6). Report 02 §3.1 lists leverage weighting as a backtest "
            "alternative to compare against, not as a live option; use 'connelly' or 'strict'."
        )
    if mode not in gt:
        raise ValueError(f"unknown garbage_time.mode {mode!r}; available: connelly | strict")
    thresholds = {k: int(v) for k, v in gt[mode].items()}

    period = plays["period"].to_numpy()
    margin = np.abs(plays["score_margin"].to_numpy())
    cutoff = np.array(
        [thresholds[f"q{min(max(int(p), 1), 4)}"] for p in period],
        dtype=np.float64,
    )
    w = np.where(margin >= cutoff, 0.0, 1.0)

    zero = {str(x) for x in gt.get("zero_weight_plays", [])}
    if "kneel" in zero:
        w = np.where(plays["is_kneel"].to_numpy(), 0.0, w)
    if "spike" in zero:
        w = np.where(plays["is_spike"].to_numpy(), 0.0, w)
    if "end_of_half_heave" in zero:
        heave = (
            np.isin(period, (2, 4))
            & (plays["clock_seconds"].to_numpy() <= int(gt["heave_max_clock_seconds"]))
            & (plays["yards_to_goal"].to_numpy() >= int(gt["heave_min_yards_to_goal"]))
            & (plays["play_class"].to_numpy() == "pass")
        )
        w = np.where(heave, 0.0, w)

    if game_weights_by_id:
        w = w * np.array(
            [game_weights_by_id.get(int(g), 1.0) for g in plays["game_id"].to_list()],
            dtype=np.float64,
        )
    return w


def build_play_design(
    plays: pl.DataFrame,
    config: dict[str, Any],
    teams: tuple[str, ...] | None = None,
    game_weights_by_id: dict[int, float] | None = None,
) -> PlayDesign:
    """Build the sparse L1 design matrix, response and weight vector (report 02 §3.1).

    `plays` must already carry `play_value` (see model/ep.py) and must already be
    the exact set of plays the fit is allowed to see. This function does no
    filtering and no week arithmetic on purpose, for the same reason
    `build_game_design` does not: report 02 §5.1's walk-forward guarantee holds
    only if one module owns the slicing, and that module is `ingest/windows.py`
    plus `ingest/plays.py::plays_for`.
    """
    p = plays.sort(["game_id", "play_index"])
    offense = p["offense"].to_list()
    defense = p["defense"].to_list()

    if teams is None:
        teams = tuple(sorted(set(offense) | set(defense)))
    index = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)
    n_rows = p.height
    n_cols = 2 * n_teams + 2

    y = p["play_value"].to_numpy().astype(np.float64)
    w = play_weights(p, config, game_weights_by_id)

    # H_p: +1 when the OFFENCE is the home team, -1 when it is the visitor, 0 at
    # a neutral site (report 02 §3.1). Note this is a different coding from L2's
    # site column, which is {1, 0}: at play level the home team is on offence
    # about half the time, so the effect has to be signed by who has the ball.
    site = np.where(
        p["neutral_site"].to_numpy(),
        0.0,
        np.where(p["offense_is_home"].to_numpy(), 1.0, -1.0),
    )

    rows = np.repeat(np.arange(n_rows), 4)
    cols = np.empty(n_rows * 4, dtype=np.int64)
    vals = np.empty(n_rows * 4, dtype=np.float64)
    cols[0::4] = [index[t] for t in offense]
    vals[0::4] = 1.0
    cols[1::4] = [n_teams + index[t] for t in defense]
    vals[1::4] = 1.0
    cols[2::4] = 2 * n_teams
    vals[2::4] = site
    cols[3::4] = 2 * n_teams + 1
    vals[3::4] = 1.0

    x = sparse.csr_matrix((vals, (rows, cols)), shape=(n_rows, n_cols))

    penalty = np.ones(n_cols, dtype=np.float64)
    penalty[2 * n_teams] = 0.0  # home field  - UNPENALISED
    penalty[2 * n_teams + 1] = 0.0  # intercept - UNPENALISED

    return PlayDesign(
        X=x,
        y=y,
        w=w,
        teams=teams,
        penalty=penalty,
        game_ids=p["game_id"].to_numpy(),
    )
