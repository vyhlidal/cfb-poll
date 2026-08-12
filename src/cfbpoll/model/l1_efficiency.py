"""L1 - opponent-adjusted efficiency via ridge on play-level EPA.

Specified by report 02 §3.1 (design) and §2.8 (the ancestor implementation).

    y_p = mu + alpha_{o(p)} + beta_{d(p)} + eta * H_p + eps_p

alpha_t is offensive rating (EPA/play above average), beta_t is defensive rating
(EPA/play ALLOWED above average, so more negative is better), eta is home field.
mu and eta are unpenalised.

Opponent adjustment is SIMULTANEOUS, not iterative. Solving offense and defense
jointly in one linear system is both more correct and cheaper than iterative
averaging, and it makes the "10 sacks against an FCS team" problem vanish by
construction (report 02 §1, commitment 3).

Converting to points: fit k walk-forward by regressing actual game margin on the
efficiency differential; k should land near the number of offensive plays per
game (roughly 65-72). Do not hard-code it (report 02 §3.1).

Special teams are deliberately excluded from L1 in v1 - ST EPA is very noisy at
12-game samples and the scoreboard already contains it, so L2 picks it up.

Unit splits (rush/pass offense and defense) are the same code on a filtered
dataset. They are NOT used in the v1 ranking; they exist for explainability and
for the falsifiable matchup test in report 02 §6.

STATUS: SCAFFOLD. Build this FOURTH (report 02 Appendix B step 4) - largest
accuracy gain, largest data dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl


def fit(plays: pl.DataFrame, config: dict[str, Any], through_week: int) -> Any:
    """Fit the L1 ridge and return (alpha, beta, eta, mu, lambda_used)."""
    raise NotImplementedError("l1_efficiency.fit - scaffold; see report 02 §3.1")


def efficiency_to_points(
    alpha: dict[int, float],
    beta: dict[int, float],
    k: float,
) -> dict[int, float]:
    """Rescale (alpha_t - beta_t) from EPA/play to the points scale using k."""
    raise NotImplementedError("l1_efficiency.efficiency_to_points - scaffold; report 02 §3.1")
