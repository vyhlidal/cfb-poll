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
backtest harness, then L4, then L1, then L3, then bootstrap. All of it is built.

STATUS: all four layers are real and `cfbpoll rank` publishes L4 with opponent
quality from the L3 blend (`power_source = "L3"`, `power_version = "v1"`). L2
remains available as a Power source and is what a season with no play archive
falls back to; whichever ran is stamped on every artifact. The per-play value L1
regresses on comes from ep.py - OUR expected-points model, because the archive's
`EPA` column is a third party's and report 01 §5.6 bans it. The two argument
surface R(N, K) that makes retroactive re-ranking definitional lives in retro.py.
The parametric bootstrap on the fixed schedule (bootstrap.py) publishes a 90%
rank interval beside every rank, and the ridge sandwich (ridge.py) publishes a
standard error beside every Power rating.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps import cost off the CLI path
    import polars as pl

#: THE KEY IS THE TEAM NAME, A STRING, and this annotation used to say otherwise.
#: It declared `TeamId = int` while every rater in the package returned
#: `{"Georgia": 18.4, ...}` off the canonical frame's `String` team columns, so
#: the one file the documentation calls authoritative was the one file a
#: challenger could not follow. AGENTS.md carried a paragraph telling readers to
#: disbelieve it, which is the sign that the fix belonged here rather than in
#: another warning. `game_id` really is an `Int64`; it is the team columns that
#: are strings, and nothing in this package is keyed on a team id.
#:
#: `TeamId` is gone rather than aliased to `str`, because a name that says "id"
#: over a value that is a school's name is the same wrong claim in a quieter
#: voice.
TeamName = str
Ratings = dict[TeamName, float]

__all__ = ["Rater", "Ratings", "TeamName"]


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

    THE SIGNATURE HERE IS THE ONE THE HARNESS CALLS, and getting that wrong is
    not a documentation defect, it is a `TypeError` on the first week. The call
    is `rate(games, plays, through_week, state=..., config=...)`
    (`backtest/walkforward.py`), so the three data arguments are positional and
    everything after them arrives by keyword. A three-argument `rate` raises.

    Write it exactly as the shipped example does, and default the keyword
    arguments so a rater that needs neither can ignore both:

        def rate(games, plays, through_week, config=None, state=None) -> dict[str, float]:

    Args:
        games: one row per game through `through_week`. Never contains a column
            banned by report 02 §3.10 - `cfbpoll audit-features` enforces this.
            `home_team` and `away_team` are `String`.
        plays: one row per play, or None for a scores-only rater such as L2. A
            play-level rater handed None returns an empty mapping, which the
            harness reads as league average for everyone.
        through_week: the data window K. A rater must never look past it; that is
            the entire walk-forward protocol (report 02 §5.1).
        config: the harness's own config, and it is passed on every call. A rater
            that falls back to `load_config()` when it is None scores the DEFAULT
            constants while claiming to have varied them, which is how a
            sensitivity sweep publishes a number about a model nobody ran.
        state: an optional per-season cache and out-of-sample accumulator
            (model/l3_power.py). Passing None is always correct and only slower;
            a rater that does not need it must accept and ignore it.

    Returns:
        A rating per team NAME on the points scale, higher is better. A team you
        omit is treated as league average, which is also what `{}` means.
    """

    def __call__(
        self,
        games: pl.DataFrame,
        plays: pl.DataFrame | None,
        through_week: int,
        config: dict[str, object] | None = None,
        state: object = None,
    ) -> Ratings: ...
