"""Baselines: "home team always wins" (the floor) and naive win percentage.

Specified by report 02 §5.3. CFB home teams won 63.4-63.8% of games 2021-2024,
so the home-team rule is the floor any real system must clear decisively. Win
percentage is the naive wins-based ranking the project brief asks about - and
Dabadghao & Vaziri found win-loss ranking, the method leagues actually use for
seeding, is the worst performer almost everywhere (report 02 §2.15).

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    through_week: int,
) -> dict[int, float]:
    """Win percentage as a rating (challenger protocol, report 03 §7.3)."""
    raise NotImplementedError("baselines.winpct.rate - scaffold; see report 02 §5.3")


def home_team_always_wins(games: pl.DataFrame) -> dict[int, bool]:
    """The floor rule: predict the home team in every game."""
    raise NotImplementedError("baselines.winpct.home_team_always_wins - scaffold; report 02 §5.3")
