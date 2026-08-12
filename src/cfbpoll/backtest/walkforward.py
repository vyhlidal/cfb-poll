"""Strict walk-forward evaluation. No exceptions.

Specified by report 02 §5.1.

To predict week N of season S, fit on data through week N-1 of season S ONLY
(plus prior seasons only if a prior-carrying variant is explicitly under test,
and never in the primary system). Any accidental use of future data invalidates
the entire exercise, and it is the single easiest mistake to make when the
estimator is a batch refit - which is exactly why this module owns the slicing
and no model module is allowed to select its own rows.

Evaluation universe: FBS-vs-FBS regular season and conference championships.
FBS-vs-FCS games are reported SEPARATELY (they are easy and inflate accuracy).
Bowls are reported separately (roster chaos, report 02 §3.8).

The retroactive grid this produces is 5 seasons x 15 evaluation weeks x 15 data
windows - a few thousand solves, single-digit minutes on a laptop. It stays in
parquet as a release asset; it must never be loaded into Postgres (report 03 §5.4).

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl


def slice_through(games: pl.DataFrame, season: int, through_week: int) -> pl.DataFrame:
    """Return exactly the games a week-N fit is allowed to see. Leakage guard."""
    raise NotImplementedError("backtest.walkforward.slice_through - scaffold; report 02 §5.1")


def run(rater: Any, seasons: list[int], config: dict[str, Any]) -> Any:
    """Walk one or more seasons forward, returning per-game predictions and ratings."""
    raise NotImplementedError("backtest.walkforward.run - scaffold; see report 02 §5.1")


def retro_grid(rater: Any, seasons: list[int], config: dict[str, Any]) -> Any:
    """Compute the full R(N, K) grid: live R(N,N), hindsight R(N,final), and deltas.

    The "biggest retroactive movers" view - who the model was wrong about, in its
    own words, with the number quantified - is the most differentiated thing this
    project can ship, and it costs nothing extra once the grid exists
    (report 02 §3.6).
    """
    raise NotImplementedError("backtest.walkforward.retro_grid - scaffold; report 02 §3.6")
