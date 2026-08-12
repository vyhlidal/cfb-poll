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

p, the iteration cap and the tolerance live in configs/default.toml under
[baselines.random_walker].
"""

from __future__ import annotations

import numpy as np
import polars as pl

from cfbpoll.config import load_config

__all__ = ["rate", "schedule_connectivity"]


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None = None,
    through_week: int | None = None,
    config: dict | None = None,
) -> dict[str, float]:
    """Random-walker ratings (challenger protocol, report 03 §7.3).

    A voter standing at team j picks one of j's games uniformly at random and
    moves to the winner with probability p, to the loser with probability 1-p.
    Those transition probabilities form a column-stochastic Markov chain whose
    stationary distribution is the ranking - the steady state of the paper's
    expected-vote ODE system. Ratings are returned scaled so the mean is 1.

    Note what p in (1/2, 1) buys: every edge keeps a back-transition, so an
    undefeated team is not a dangling node and the chain stays irreducible. That
    is the pathology that breaks Keener's binary construction and PageRank on the
    win graph (report 02 §2.11), and the random walker sidesteps it by design.

    Power iteration from a uniform start, so the answer is a pure function of the
    frame with no RNG involved.
    """
    del plays, through_week
    cfg = config if config is not None else load_config()
    rw = cfg["baselines"]["random_walker"]
    p = float(rw["p"])
    max_iter = int(rw["max_iterations"])
    tol = float(rw["tolerance"])

    home = games["home_team"].to_list()
    away = games["away_team"].to_list()
    hp = games["home_points"].to_list()
    ap = games["away_points"].to_list()

    teams = tuple(sorted(set(home) | set(away)))
    if not teams:
        return {}
    index = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    # flow[i, j] = expected votes moving from j to i per game examined
    flow = np.zeros((n, n), dtype=np.float64)
    played = np.zeros(n, dtype=np.float64)
    for h, a, hs, asc in zip(home, away, hp, ap, strict=True):
        i, j = index[h], index[a]
        played[i] += 1.0
        played[j] += 1.0
        if hs > asc:
            winner, loser = i, j
        elif asc > hs:
            winner, loser = j, i
        else:  # pragma: no cover
            flow[i, j] += 0.5
            flow[j, i] += 0.5
            continue
        flow[winner, loser] += p
        flow[loser, winner] += 1.0 - p

    played[played == 0.0] = 1.0
    transition = flow / played[None, :]
    # A voter that does not move stays put: the diagonal takes the remainder.
    np.fill_diagonal(transition, 1.0 - transition.sum(axis=0) + np.diag(transition))

    v = np.full(n, 1.0 / n, dtype=np.float64)
    for _ in range(max_iter):
        nxt = transition @ v
        total = nxt.sum()
        if total > 0:
            nxt /= total
        if np.max(np.abs(nxt - v)) < tol:
            v = nxt
            break
        v = nxt

    v = v * n  # mean 1, so the numbers read as "share of an average team's votes"
    return {team: float(v[i]) for i, team in enumerate(teams)}


def schedule_connectivity(games: pl.DataFrame, through_week: int | None = None) -> dict[str, float]:
    """Graph diagnostics for the weeks 1-4 connectivity report (report 02 §4, Option B).

    Cheap, and exactly the "is the season knowable yet" measures the early-season
    policy needs: how many teams, how many components, and how much of the field
    sits in the largest one. A near-singular week-2 SRS and a wild week-2 ranking
    are the same fact as a fragmented graph.
    """
    del through_week
    home = games["home_team"].to_list()
    away = games["away_team"].to_list()
    teams = sorted(set(home) | set(away))
    if not teams:
        return {"n_teams": 0.0, "n_components": 0.0, "largest_component_share": 0.0}

    parent = {t: t for t in teams}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for h, a in zip(home, away, strict=True):
        rh, ra = find(h), find(a)
        if rh != ra:
            parent[rh] = ra

    sizes: dict[str, int] = {}
    for t in teams:
        root = find(t)
        sizes[root] = sizes.get(root, 0) + 1
    return {
        "n_teams": float(len(teams)),
        "n_components": float(len(sizes)),
        "largest_component_share": float(max(sizes.values())) / len(teams),
    }
