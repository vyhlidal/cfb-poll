"""Baselines: "home team always wins" (the floor) and naive win percentage.

Specified by report 02 §5.3. CFB home teams won 63.4-63.8% of games 2021-2024,
so the home-team rule is the floor any real system must clear decisively. Win
percentage is the naive wins-based ranking the project brief asks about - and
Dabadghao & Vaziri found win-loss ranking, the method leagues actually use for
seeding, is the worst performer almost everywhere (report 02 §2.15).

Win percentage has no opponent adjustment at all, which is exactly the point: it
is the control that shows what opponent adjustment is worth. Constraint 3 makes
opponent adjustment mandatory for the poll; this baseline exists to price it.
"""

from __future__ import annotations

import polars as pl

__all__ = ["home_team_always_wins", "rate"]


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None = None,
    through_week: int | None = None,
    state: object = None,
    config: dict | None = None,
) -> dict[str, float]:
    """Win percentage as a rating (challenger protocol, report 03 §7.3).

    `games` arrives ALREADY truncated by the harness; `plays` is unused.
    A team with no games is absent from the mapping, and the harness treats an
    absent team as the neutral rating for the system.
    """
    del plays, through_week, state
    wins: dict[str, float] = {}
    played: dict[str, float] = {}
    for home, away, hp, ap in zip(
        games["home_team"].to_list(),
        games["away_team"].to_list(),
        games["home_points"].to_list(),
        games["away_points"].to_list(),
        strict=True,
    ):
        played[home] = played.get(home, 0.0) + 1
        played[away] = played.get(away, 0.0) + 1
        wins.setdefault(home, 0.0)
        wins.setdefault(away, 0.0)
        if hp > ap:
            wins[home] += 1
        elif ap > hp:
            wins[away] += 1
        else:  # pragma: no cover - overtime makes ties impossible in modern CFB
            wins[home] += 0.5
            wins[away] += 0.5
    return {team: wins[team] / played[team] for team in sorted(wins)}


def home_team_always_wins(games: pl.DataFrame) -> dict[int, bool]:
    """The floor rule: predict the home team in every game, neutral sites included.

    Returned as game_id -> True so the harness can score it with the same code
    path as everything else. It has no ratings, so it is handled in the harness
    as a constant-prediction system rather than as a rater.
    """
    return {int(gid): True for gid in games["game_id"].to_list()}
