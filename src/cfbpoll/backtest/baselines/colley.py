"""Baseline: the Colley Matrix - the "bias-free" BCS ancestor.

Specified by report 02 §2.1 and §5.3.

    C_ii = 2 + n_i
    C_ij = -n_ij   (i != j)
    b_i  = 1 + (w_i - l_i) / 2
    solve C r = b, rank descending

Wins and losses only. No margin, no home field, no priors of any kind.

The identity that organises the whole report: C = 2I + L, where L is the schedule
graph Laplacian, which is also XᵀX for the Massey/SRS design. So COLLEY = MASSEY
+ 2I - ridge regression with lambda = 2, shrinking toward 0.500, on a response of
sign(margin)/2. Without the +2 the matrix is SINGULAR and the method does not
work at all. The most famously bias-free BCS component was regularized, which is
most of the argument that our ridge penalty is constraint-compliant
(report 02 §4).

Property test candidate (tests/property/): Colley conserves sum(r)/N = 0.5
EXACTLY, with no renormalisation. That is a cheap, sharp correctness check.

The pseudo-game count lives in configs/default.toml under [baselines.colley].
"""

from __future__ import annotations

import numpy as np
import polars as pl

from cfbpoll.config import load_config

__all__ = ["rate"]


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None = None,
    through_week: int | None = None,
    config: dict | None = None,
    state: object = None,
) -> dict[str, float]:
    """Colley ratings (challenger protocol, report 03 §7.3). `plays` unused.

    `games` arrives ALREADY truncated by the harness. Wins and losses only: the
    scores are read solely to decide who won.
    """
    del plays, through_week, state
    cfg = config if config is not None else load_config()
    pseudo = float(cfg["baselines"]["colley"]["pseudo_games"])

    home = games["home_team"].to_list()
    away = games["away_team"].to_list()
    hp = games["home_points"].to_list()
    ap = games["away_points"].to_list()

    teams = tuple(sorted(set(home) | set(away)))
    if not teams:
        return {}
    index = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    c = np.zeros((n, n), dtype=np.float64)
    b = np.ones(n, dtype=np.float64)
    np.fill_diagonal(c, pseudo)

    for h, a, hs, asc in zip(home, away, hp, ap, strict=True):
        i, j = index[h], index[a]
        c[i, i] += 1.0
        c[j, j] += 1.0
        c[i, j] -= 1.0
        c[j, i] -= 1.0
        if hs > asc:
            b[i] += 0.5
            b[j] -= 0.5
        elif asc > hs:
            b[j] += 0.5
            b[i] -= 0.5

    r = np.linalg.solve(c, b)
    return {team: float(r[i]) for i, team in enumerate(teams)}
