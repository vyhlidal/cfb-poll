"""The four-layer rating model, and the challenger protocol.

Layer map (report 02 §1):
  L1 efficiency - ridge on garbage-time-filtered play EPA        -> l1_efficiency.py
  L2 results    - ridge on compressed scoring margin             -> l2_results.py
  L3 power      - walk-forward stacked blend of L1 and L2        -> l3_power.py
  L4 resume     - root-solve for the quality q that explains the
                  actual results against this exact schedule     -> l4_resume.py

Headline poll = L4 Resume. L3 Power is published beside it, always, with the gap
shown (report 02 §3.5). Build order is report 02 Appendix B: L2 first, then the
backtest harness, then L4, then L1, then L3, then bootstrap.

STATUS: L2 and L4 are real, and L4 is what `cfbpoll rank` publishes. L1 and L3
are still scaffolds, so opponent quality in the résumé is L2 rescaled to points
and every artifact stamps `power_source = "L2"`, `power_version = "v0"`. The two
argument surface R(N, K) that makes retroactive re-ranking definitional lives in
retro.py. Signatures for the unbuilt layers are fixed here so that the challenge
harness (report 03 §7.3) has a contract to compile against.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps import cost off the CLI path
    import polars as pl

TeamId = int
Ratings = dict[TeamId, float]

__all__ = ["Rater", "Ratings", "TeamId"]


@runtime_checkable
class Rater(Protocol):
    """The challenger protocol, fixed by report 03 §7.3.

    A community challenger is either a parameter variant
    (configs/challengers/<name>.toml) or a module exposing this one function.
    `challenge.yml` then runs the entry through the IDENTICAL walk-forward
    harness, on the IDENTICAL MIT archive, against the IDENTICAL baselines, and
    posts a scorecard. That only works because fork PRs receive no secrets and
    the MIT archive needs none - the license split is load-bearing architecture,
    not paperwork.

    Args:
        games: one row per game through `through_week`. Never contains a column
            banned by report 02 §3.10 - `cfbpoll audit-features` enforces this.
        plays: one row per play, or None for a scores-only rater such as L2.
        through_week: the data window K. A rater must never look past it; that is
            the entire walk-forward protocol (report 02 §5.1).

    Returns:
        A rating per team on the points scale, higher is better.
    """

    def __call__(
        self,
        games: pl.DataFrame,
        plays: pl.DataFrame | None,
        through_week: int,
    ) -> Ratings: ...
