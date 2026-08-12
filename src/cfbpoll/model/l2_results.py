"""L2 - results core: ridge on compressed scoring margin.

Specified by report 02 §3.2.

    s_g = C * tanh(m_g / C) + beta_w * sign(m_g)          (the response)
    s_g = rho_h - rho_a + h * site_g + eps_g              (the model)

h is unpenalised. h should also be estimated INDEPENDENTLY from home-and-home
series only, per Pasteur, because the regression's schedule is structurally
asymmetric - power programs buy home games that never get a return trip.
Pasteur obtained ~3.70 points; recent independent estimates put CFB home field
nearer 2.8. Fit both ways, compare, publish both.

Game weights v_g: non-CFP bowls down-weighted (roster availability is
systematically compromised); conference championships and CFP games at full
weight; FBS-vs-FCS at full weight with no special handling (report 02 §3.8, §3.7).
The live values live in configs/default.toml under [weights].

This layer alone is a complete, working, constraint-compliant ranking system in
roughly 100 lines. Everything after it is improvement, not prerequisite.

STATUS: SCAFFOLD. Build this FIRST (report 02 Appendix B step 1, report 03 §10
step 4). Ship the smallest real thing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl


def fit(games: pl.DataFrame, config: dict[str, Any], through_week: int) -> Any:
    """Fit the L2 ridge and return (rho, h, lambda_used)."""
    raise NotImplementedError("l2_results.fit - scaffold; see report 02 §3.2")


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    through_week: int,
) -> dict[int, float]:
    """Challenger-protocol entry point (report 03 §7.3). `plays` is unused by L2."""
    raise NotImplementedError("l2_results.rate - scaffold; see report 02 §3.2")


def estimate_home_field(games: pl.DataFrame) -> float:
    """Estimate h from home-and-home series only (report 02 §3.2, after Pasteur)."""
    raise NotImplementedError("l2_results.estimate_home_field - scaffold; report 02 §3.2")
