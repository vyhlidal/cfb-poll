"""Sparse design-matrix construction for L1 and L2.

Specified by report 02 §3.1 (L1) and §3.2 (L2).

L1: X is P x (2T+1) with EXACTLY three non-zeros per row - +1 in the offense
column for o(p), +1 in the defense column for d(p), and H_p in the HFA column
(+1 offense is home, -1 away, 0 neutral). Build it CSR; never materialise it
dense. T is roughly 264 (about 136 FBS plus about 128 FCS), P about 170k/season.

L2: Z is G x (T+1) - +1 home team, -1 away team, site_g in the HFA column.
Note what ZᵀZ is: the schedule graph Laplacian, the matrix at the heart of both
Massey and Colley. Ridge makes it L + lambda*I, which is positive definite for
any lambda > 0 and therefore invertible EVEN WHEN THE SCHEDULE GRAPH IS
DISCONNECTED. That one line eliminates the whole class of SRS failures seen in
2020 and in weeks 1-3 of any season, without importing a byte of reputation.

FCS teams get their own coefficients in the same fit under the same penalty.
Do NOT pool them into a single node - that is precisely ESPN's pre-2015 FPI
failure (report 02 §3.7).

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl


def build_play_design(plays: pl.DataFrame, weights: Any | None = None) -> Any:
    """Build the sparse L1 design matrix, response and weight vector.

    Returns (X_csr, y, w, column_index) per report 02 §3.1.
    """
    raise NotImplementedError("design.build_play_design - scaffold; see report 02 §3.1")


def build_game_design(games: pl.DataFrame, weights: Any | None = None) -> Any:
    """Build the sparse L2 design matrix, compressed response and weight vector.

    Returns (Z_csr, s, v, column_index) per report 02 §3.2.
    """
    raise NotImplementedError("design.build_game_design - scaffold; see report 02 §3.2")


def compress_margin(margin: float, c: float, beta_w: float) -> float:
    """s = C * tanh(m / C) + beta_w * sign(m)   (report 02 §3.2).

    C bounds the value of running up the score without discarding margin - the
    BCS's sportsmanship objection answered by construction rather than by
    throwing away the difference between 3 and 24. beta_w is the win premium: the
    discontinuity at zero that makes this a football ranking rather than a
    scoring-margin ranking. Sports-Reference's CFB SRS floors margin at +/-7,
    which corresponds to beta_w ~ 3.0 in this parameterisation.

    beta_w must be published prominently every week. It is the single most
    contested value in the system and hiding it would be a transparency failure.
    """
    raise NotImplementedError("design.compress_margin - scaffold; see report 02 §3.2")


def garbage_time_weight(quarter: int, score_margin: int, thresholds: dict[str, int]) -> float:
    """Return 0.0 for garbage-time plays, 1.0 otherwise (report 02 §3.1).

    Default thresholds are Connelly's, from configs/default.toml: a lead of 43+
    in Q1, 37+ in Q2, 29+ in Q3, 22+ in Q4. Kneel-downs, spikes and end-of-half
    heaves are also zero-weighted. The stricter 28/24/21/16 set and the continuous
    leverage weight w = 4*WP*(1-WP) are backtest alternatives; publish which one
    is live and why.
    """
    raise NotImplementedError("design.garbage_time_weight - scaffold; see report 02 §3.1")
