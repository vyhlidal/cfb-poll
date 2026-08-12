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
    """Colley ratings (challenger protocol, report 03 §7.3). `plays` unused."""
    raise NotImplementedError("baselines.colley.rate - scaffold; see report 02 §2.1")
