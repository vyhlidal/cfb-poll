"""WORKED EXAMPLE 2 of 2: a structural variant.

A challenger is a module exposing exactly this:

    def rate(games, plays, through_week, config=None, state=None) -> dict[str, float]

`games` and `plays` are ALREADY TRUNCATED to `through_week` by the harness, so
the walk-forward guard lives there rather than in your code. You cannot see a
game you are about to be scored on, whatever you do in here. `plays` is `None`
unless you declare `needs_plays = true`, and everything after `through_week` is
keyword-only so the harness can add arguments without breaking your entry.

THE CLAIM THIS ENTRY MAKES. Every opponent-adjusted rating in the comparison set
solves a linear system: SRS averages point differential against schedule, Colley
does it on wins, and the L2 results core is ridge on a compressed margin. This
one does not solve anything. It is iterative proportional adjustment - the
oldest idea in the sport's rating literature and the one every modern method
replaced: rate each team by its average margin, then repeat, subtracting the
average rating of the opponents it actually played.

It is deliberately a WEAK entry, and being weak is the point of shipping it as
the example. A worked example whose only job is to look good teaches a
challenger nothing about what the harness does when an idea does not work, and
the scorecard committed beside this file is more useful for showing a real loss
than it would be for showing a manufactured win. The interesting question it
does answer honestly: how much of the L2 results core's advantage is the ridge
penalty and the simultaneous solve, and how much is just "adjust for schedule at
all"?

Run it:

    uv run cfbpoll challenge run --entry configs/challengers/iterative_margin.py

Everything here is ~40 lines of numpy and polars, uses no config constant, and
holds no state between weeks. That is intentional: an entry should be readable
in one sitting, or it is not a worked example.
"""

from __future__ import annotations

import numpy as np
import polars as pl

CHALLENGER = {
    "name": "iterative-margin",
    "kind": "structural",
    "author": "cfb-poll (worked example)",
    "needs_plays": False,
    "notes": (
        "Iterative proportional schedule adjustment on raw margin, capped at 28. "
        "No linear solve, no penalty, no prior. The question it answers is how "
        "much of the results core's edge comes from the simultaneous solve rather "
        "than from adjusting for schedule at all."
    ),
}

#: Rounds of adjustment. Enough to converge on a connected graph, few enough that
#: a fragmented September graph cannot run away.
ROUNDS = 12

#: Blowout cap, in points. SRS in this repository uses +/-24; 28 is chosen to be
#: visibly NOT the incumbent's convention, so nobody can mistake this entry for a
#: reimplementation of a baseline that is already in the table.
CAP = 28.0


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None = None,
    through_week: int | None = None,
    config: dict | None = None,
    state: object = None,
) -> dict[str, float]:
    """Average capped margin, iteratively adjusted for the opponents actually played."""
    if games.is_empty():
        return {}

    home = games["home_team"].to_list()
    away = games["away_team"].to_list()
    margin = np.clip(
        (games["home_points"] - games["away_points"]).to_numpy().astype(np.float64), -CAP, CAP
    )

    # Sorted, so the team order - and therefore every floating-point reduction
    # below - is a function of the data rather than of dict insertion order.
    teams = sorted(set(home) | set(away))
    index = {team: i for i, team in enumerate(teams)}
    h = np.array([index[t] for t in home])
    a = np.array([index[t] for t in away])

    played = np.zeros(len(teams))
    np.add.at(played, h, 1.0)
    np.add.at(played, a, 1.0)
    played = np.maximum(played, 1.0)

    ratings = np.zeros(len(teams))
    for _ in range(ROUNDS):
        # Each game contributes (my margin + my opponent's current rating).
        credit = np.zeros(len(teams))
        np.add.at(credit, h, margin + ratings[a])
        np.add.at(credit, a, -margin + ratings[h])
        ratings = credit / played
        ratings -= ratings.mean()  # the zero point is arbitrary; fix it every round

    return {team: float(ratings[i]) for i, team in enumerate(teams)}
