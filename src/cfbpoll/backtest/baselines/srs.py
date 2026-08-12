"""Baseline: SRS with the Sports-Reference college football convention.

Specified by report 02 §2.2 and §5.3.

    R_i = MOV_i + (1/n_i) * sum_j R_j        average team = 0

Sports-Reference's CFB handling exactly: margin CAPPED at 24 and FLOORED at +/-7,
so a 1-point win is treated the same as a 7-point win. That floor is the direct
precedent for our win premium beta_w ~ 3.0 (report 02 §3.2).

Uncapped SRS IS the Massey least-squares rating - multiply by n_i and it is
row-for-row Massey's normal equations, with the zero-mean convention playing the
role of Massey's replaced all-ones row. Capped/floored CFB SRS is not plain least
squares.

This baseline keeps the failure mode we designed around: with a disconnected
schedule graph the matrix is singular and the solve simply fails (2020), and it
is near-singular in weeks 1-3. Our ridge term is exactly what removes that,
without importing reputation. Expect this baseline to fail early-season fits;
that is informative, and the harness should record it rather than paper over it.

Note this baseline also LUMPS non-major opponents into one team, per
Sports-Reference. We reject that convention for our own model (report 02 §3.7)
but keep it here so the baseline is the real thing.

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl

MOV_CAP = 24
MOV_FLOOR = 7


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    through_week: int,
) -> dict[int, float]:
    """SRS ratings (challenger protocol, report 03 §7.3). `plays` unused."""
    raise NotImplementedError("baselines.srs.rate - scaffold; see report 02 §2.2")
