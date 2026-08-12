"""Pre-publication data-quality assertions.

Specified by report 01 §5.5. CFBD's terms disclaim all warranty on accuracy, so
validation is OUR responsibility, not theirs.

Before publishing, assert:
  - every FBS-vs-FBS game in the week has completed = true and non-null scores
  - the week's game count is within a sane range, and no team appears twice
  - every team in /teams/fbs appears in cumulative stats with a plausible
    games-played count
  - box score totals reconcile against /games final scores
  - week-over-week rating movement is bounded - an implausible jump is a
    data-error signal, not a ranking insight
  - CROSS-SOURCE: scores for the completed week match between CFBD and the
    SportsDataverse refresh
  - KNOWN-BUG GUARD: no game bucketed into week = 1 with a December or January
    start_date. The live example is game_id 401778314 (Minnesota 20,
    New Mexico 17, 2025-12-26), a bowl mislabelled week 1 upstream
    (report 01 §3.10). The Postgres schema carries the same guard as a CHECK
    constraint (report 03 §5.6).

On failure: halt, alert, publish nothing.

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl

KNOWN_MISLABELLED_GAME_IDS = (401778314,)
"""Upstream bugs seen in the wild. Documented, not silently patched."""


def check_week(games: pl.DataFrame, season: int, week: int) -> list[str]:
    """Run every gate; return the list of failures (empty means publishable)."""
    raise NotImplementedError("validate.data_quality.check_week - scaffold; report 01 §5.5")


def cross_source_scores(cfbd: Any, sportsdataverse: Any) -> list[str]:
    """Diff the two independent pipelines over the same games (report 01 §5.5)."""
    raise NotImplementedError(
        "validate.data_quality.cross_source_scores - scaffold; report 01 §5.5"
    )
