"""L3 - Power rating: the walk-forward stacked blend of L1 and L2.

Specified by report 02 §3.3.

    m_hat_g = w1 * k * ((alpha_h - beta_a) - (alpha_a - beta_h))
            + w2 * (rho_h - rho_a)
            + h * site_g

    Power_t = w1 * k * (alpha_t - beta_t) + w2 * rho_t

Do NOT hand-pick w1 and w2. Estimate them on OUT-OF-SAMPLE games only - fit on
weeks <= N-1, evaluate on week N, pooled across training seasons. Publish w1, w2
and k every week. Expect w1 to dominate late (efficiency is more stable) and w2
to matter more early (a scoreboard result is worth a lot when you have three
games). If the fitted weights say otherwise, publish that instead: the backtest
decides, not the narrative.

Power is the PREDICTIVE number: expected margin against an average team on a
neutral field. It is never hidden - it is published beside the Resume rating
every week, with the gap shown, so that the two most common fan complaints
("you're just ranking who'd win" / "you're ignoring that they got blown out")
both have an on-page answer (report 02 §3.5).

STATUS: SCAFFOLD. Build this FIFTH (report 02 Appendix B step 5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl


def fit_blend_weights(l1: Any, l2: Any, holdout_games: pl.DataFrame) -> tuple[float, float]:
    """Fit (w1, w2) on out-of-sample games only (report 02 §3.3)."""
    raise NotImplementedError("l3_power.fit_blend_weights - scaffold; see report 02 §3.3")


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    through_week: int,
) -> dict[int, float]:
    """Challenger-protocol entry point (report 03 §7.3): the incumbent Power rating.

    This is the exact signature a community challenger must implement to be
    scored by challenge.yml against the incumbent on the identical harness.
    """
    raise NotImplementedError("l3_power.rate - scaffold; see report 02 §3.3")
