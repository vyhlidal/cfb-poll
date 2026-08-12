"""The four-layer rating model, and the challenger protocol.

Layer map (report 02 §1):
  EP            - our own next-score expected-points model         -> ep.py
  L1 efficiency - ridge on garbage-time-filtered play value       -> l1_efficiency.py
  L2 results    - ridge on compressed scoring margin             -> l2_results.py
  L3 power      - walk-forward stacked blend of L1 and L2        -> l3_power.py
  L4 resume     - root-solve for the quality q that explains the
                  actual results against this exact schedule     -> l4_resume.py

Headline poll = L4 Resume. L3 Power is published beside it, always, with the gap
shown (report 02 §3.5). Build order is report 02 Appendix B: L2 first, then the
backtest harness, then L4, then L1, then L3, then bootstrap.

STATUS: all four layers are real and `cfbpoll rank` publishes L4 with opponent
quality from the L3 blend (`power_source = "L3"`, `power_version = "v1"`). L2
remains available as a Power source and is what a season with no play archive
falls back to; whichever ran is stamped on every artifact. The per-play value L1
regresses on comes from ep.py - OUR expected-points model, because the archive's
`EPA` column is a third party's and report 01 §5.6 bans it. The two argument
surface R(N, K) that makes retroactive re-ranking definitional lives in retro.py.
Still unbuilt: the block bootstrap and its rank intervals.
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
        plays: one row per play, or None for a scores-only rater such as L2. A
            play-level rater handed None returns an empty mapping, which the
            harness reads as league average for everyone.
        through_week: the data window K. A rater must never look past it; that is
            the entire walk-forward protocol (report 02 §5.1).
        state: an optional per-season cache and out-of-sample accumulator
            (model/l3_power.py). Passing None is always correct and only slower;
            a rater that does not need it must accept and ignore it.

    Returns:
        A rating per team on the points scale, higher is better.
    """

    def __call__(
        self,
        games: pl.DataFrame,
        plays: pl.DataFrame | None,
        through_week: int,
        state: object = None,
    ) -> Ratings: ...
