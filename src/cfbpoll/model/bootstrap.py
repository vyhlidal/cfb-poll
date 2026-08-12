"""Block bootstrap over games -> rating AND rank intervals.

Specified by report 02 §3.3 and report 03 §9.3.

Resample games with replacement, refit, repeat (default 1000 draws; 500 is the
documented floor). The useful output is not the rating interval but the RANK
interval: publishing "Team X is ranked 7th, 90% interval 4th-13th" every week,
forever - not just early in the season - is the single most honest thing a
computer poll can do, and no major system does it.

Embarrassingly parallel; seconds to a few minutes on 4 cores.

DETERMINISM IS A HARD REQUIREMENT, and it is cheap up front and expensive to
retrofit (report 03 §9.3):
  - never np.random.seed; use Generator(PCG64(seed))
  - derive per-draw seeds with SeedSequence.spawn so the result is identical on
    1 core or 16
  - sort before writing; dict and groupby iteration order must never reach a file

STATUS: SCAFFOLD. Build this SIXTH (report 02 Appendix B step 6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl


def run(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    config: dict[str, Any],
    draws: int = 1000,
    jobs: int = 4,
    seed: int | None = None,
) -> Any:
    """Refit `draws` times on resampled games; return the draw matrix."""
    raise NotImplementedError("bootstrap.run - scaffold; see report 02 §3.3")


def rank_intervals(draws: Any, level: float = 0.90) -> Any:
    """Collapse bootstrap draws into per-team rating and rank intervals."""
    raise NotImplementedError("bootstrap.rank_intervals - scaffold; see report 02 §3.3")
