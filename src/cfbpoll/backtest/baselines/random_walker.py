"""Baseline: the Callaghan/Mucha/Porter random-walker ranking.

Specified by report 02 §2.11 and §5.3.

Voters random-walk the schedule graph, voting for the winner of a game they
examine with probability p in (1/2, 1); the expected vote dynamics form a linear
ODE system whose steady state is the ranking.

THIS IS THE BASELINE THAT MIGHT GENUINELY BEAT US. Barrow et al. (2013), eight
methods over 56 NCAAF seasons with 20-fold CV, found that "the least squares and
random walker methods have significantly better predictive accuracy at the 95%
confidence level than the other methods considered." Least squares is our L2.
The random walker is the other one. Treat it as a real competitor rather than a
formality, and report it honestly if it wins.

The same authors' review of the BCS is also the sentence this project should
probably put on its About page: the true problem with the BCS standings lay not
in the computer algorithms but in how they were combined.

Diagnostic use worth having regardless (report 02 §2.11): eigenvector centrality
and connected-component structure of the schedule graph are cheap, and they are
exactly the "is the season knowable yet" measures the weeks 1-4 connectivity
report needs.

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
    """Random-walker ratings (challenger protocol, report 03 §7.3)."""
    raise NotImplementedError("baselines.random_walker.rate - scaffold; report 02 §2.11")


def schedule_connectivity(games: pl.DataFrame, through_week: int) -> dict[str, float]:
    """Graph diagnostics for the weeks 1-4 connectivity report (report 02 §4, Option B)."""
    raise NotImplementedError(
        "baselines.random_walker.schedule_connectivity - scaffold; report 02 §4"
    )
