"""MinV - the minimum-violations retrodictive bound (Coleman).

Specified by report 02 §2.12.

Maximising retrodictive accuracy is equivalent to minimising violations, and
Coleman formulates the exact optimum as a mixed binary integer program. His
finding is the reason to compute it: EVERY previously published ranking system
produced violations at least 38% above the achievable minimum. A system landing
within ~20-25% of the bound would be genuinely notable.

MinV is to the retrodictive dimension what the closing spread is to the
predictive one: the ceiling you measure yourself against, not a target you fit
toward. A good heuristic bound is acceptable for v1; the exact program uses
scipy.optimize.milp (HiGHS).

DO NOT copy Coleman's meta-ranking approach. It ingests other systems, several of
which carry recruiting priors and some of which are opaque - constraint 5 leakage
at minimum and constraint 2 leakage in practice.

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import Any


def minimum_violations(games: Any, exact: bool = False) -> int:
    """Return the minimum achievable violation count (exact MILP, or a heuristic)."""
    raise NotImplementedError("backtest.minv.minimum_violations - scaffold; report 02 §2.12")
