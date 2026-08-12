"""Baseline: Elo - the sequential alternative we deliberately rejected.

Specified by report 02 §2.7 and §5.3.

    R' = R + K(S - E),   E = 1 / (1 + 10^((R_opp - R)/400))

with the 538 margin-of-victory and autocorrelation multiplier, published by Neil
Paine (the author of 538's NFL Elo):

    MOV multiplier = ln(|PD| + 1) * [ 2.2 / ((Elo_W - Elo_L) * 0.001 + 2.2) ]

using PRE-GAME ratings. The second factor is not optional: adding MOV to plain
Elo breaks the zero-expected-change property, because favourites win by larger
margins, and without the correction strong teams' ratings drift upward without
bound. Our ridge fits get that guard for free by being batch estimators with no
accumulation dynamic at all.

CFB constants: the published CFBD tutorial uses K = 25, initial 1500 FBS / 1200
non-FBS, with no HFA, no MOV and no offseason regression. 538's
COLLEGE-FOOTBALL-specific constants are unrecoverable - every fivethirtyeight.com
URL now redirects away and the parameters were never published. DO NOT state CFB
Elo numbers as though they were 538's (report 02 §2.7, Appendix A).

Why Elo is a baseline and not the core (report 02 §2.7): it is path-dependent, so
retroactive re-ranking has no clean definition; its only week-1 stabiliser is
last season's rating, which is exactly the reputation prior constraint 2 bans;
and its opponent adjustment credits you for the opponent's rating AT THE TIME,
not their true quality, which is the very thing this project exists to correct.

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl

K_FACTOR = 25
INITIAL_FBS = 1500
INITIAL_NON_FBS = 1200


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    through_week: int,
) -> dict[int, float]:
    """Elo ratings after replaying games in order (challenger protocol, report 03 §7.3)."""
    raise NotImplementedError("baselines.elo.rate - scaffold; see report 02 §2.7")


def mov_multiplier(point_diff: float, elo_winner: float, elo_loser: float) -> float:
    """The 538 MOV + autocorrelation multiplier, on PRE-GAME ratings."""
    raise NotImplementedError("baselines.elo.mov_multiplier - scaffold; see report 02 §2.7")
