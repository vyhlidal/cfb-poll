"""The benchmarks-only display set: what we compare against, and what we cannot.

`docs/data-sources.md` has said from the beginning that **every third-party
rating is a benchmark, never an input**. Until now that rule had an enforcement
mechanism (`cfbpoll audit-features`, an allow-list rebuild that fails closed) and
no ROSTER: nothing in the repository could say which third-party series exist,
what is known about each, or why some can be scored and others cannot. A rule
with no roster is a rule you cannot check yourself against.

This module is the roster. It holds no ratings and reads no files. It is
metadata, deliberately, because the interesting facts about a benchmark are not
its numbers:

  * whether its implementation is open, so a disagreement can be traced;
  * whether its author publishes error metrics, so "is it any good" has an
    answer that is not a vibe;
  * whether we may score it on our harness at all.

THE LAST ONE IS THE POINT, AND IT IS AN UNCOMFORTABLE ANSWER. A season-final
rating cannot be scored on a walk-forward harness. Every entry here whose only
public form is one number per team per season is `scorable = False`, and saying
so is more useful than a table of numbers that would silently compare a system
that saw the whole season against systems that saw through week N-1.

WHY THESE ARE ARCHIVED BUT NEVER PUBLISHED. The raw bodies live under
`archive/cfbd/`, which is gitignored, because CFBD's terms §3 bar operating "a
raw feed, public database mirror, proxy, substitute API". Derived analysis is
permitted and credited; redistribution is not. Our own re-implementations of SRS
and Elo (`backtest/baselines/`) are a different thing entirely - they are fitted
from the scoreboard, they are in the scored table, and they are not these.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["BENCHMARKS", "Benchmark", "by_name", "display_rows", "scorable"]


@dataclass(frozen=True)
class Benchmark:
    """One third-party rating series. Display and comparison only, never a feature."""

    name: str
    label: str
    provider: str
    author: str
    endpoint: str
    open_source: bool
    publishes_error_metrics: bool
    granularity: str  # "season" | "weekly"
    scorable: bool
    note: str

    @property
    def checkable(self) -> str:
        """The distinction that replaced 'transparent' as the differentiator."""
        if self.open_source and self.publishes_error_metrics:
            return "open and benchmarked"
        if self.publishes_error_metrics:
            return "benchmarked, closed implementation"
        if self.open_source:
            return "open implementation, no published error metrics"
        return "closed implementation, no published error metrics"


BENCHMARKS: tuple[Benchmark, ...] = (
    Benchmark(
        name="core",
        label="CORE (Context and Opponent-Relative Efficiency)",
        provider="CollegeFootballData.com",
        author="Bill Radjewski (Rad Sports Analytics LLC)",
        endpoint="/ratings/core",
        open_source=False,
        publishes_error_metrics=False,
        granularity="season",
        scorable=False,
        note=(
            "Published 2026-08-08 and the closest thing to a peer this project "
            "has: its own positioning sentence is 'CORE is an efficiency rating. "
            "It is not a forecast, point spread, win probability, resume ranking, "
            "or betting system.' The methodology is documented publicly; the "
            "implementation is not open (a code search of the CFBD org returns no "
            "CORE implementation), and no MAE, straight-up accuracy or calibration "
            "has been published for it. That is not a criticism - almost nobody "
            "publishes those - it is the specific gap this project exists to fill, "
            "and naming it precisely is more useful than implying more. The API "
            "serves one row per team per season (overall, offense, defense, plays, "
            "modelVersion), so it CANNOT be scored on the walk-forward harness "
            "without a weekly series: comparing a season-final number against "
            "systems that saw through week N-1 would flatter it and mean nothing."
        ),
    ),
    Benchmark(
        name="sp",
        label="SP+",
        provider="CollegeFootballData.com (mirrors Bill Connelly / ESPN)",
        author="Bill Connelly",
        endpoint="/ratings/sp",
        open_source=False,
        publishes_error_metrics=True,
        granularity="season",
        scorable=False,
        note=(
            "The most-cited alternative ranking in mainstream coverage, and "
            "DISQUALIFIED AS A TEMPLATE by constraint 2 rather than merely as a "
            "feature: it uses returning production and recruiting, which are "
            "reputation priors. Connelly does publish performance claims, "
            "including against the spread, which is more than most."
        ),
    ),
    Benchmark(
        name="fpi",
        label="ESPN FPI",
        provider="CollegeFootballData.com (mirrors ESPN)",
        author="ESPN",
        endpoint="/ratings/fpi",
        open_source=False,
        publishes_error_metrics=False,
        granularity="season",
        scorable=False,
        note=(
            "Also disqualified as a template by constraint 2. Third-party "
            "benchmarking exists even where the author publishes none: "
            "ThePredictionTracker has ranked FPI against ~50 systems for years."
        ),
    ),
    Benchmark(
        name="srs",
        label="CFBD SRS",
        provider="CollegeFootballData.com",
        author="Bill Radjewski",
        endpoint="/ratings/srs",
        open_source=False,
        publishes_error_metrics=False,
        granularity="season",
        scorable=False,
        note=(
            "NOT the `srs` row in our backtest table. That row is our own "
            "implementation of the Sports-Reference convention, fitted from the "
            "scoreboard walk-forward in `backtest/baselines/srs.py`, which is why "
            "it can be scored at all. This is the vendor's season-final series."
        ),
    ),
    Benchmark(
        name="elo",
        label="CFBD Elo",
        provider="CollegeFootballData.com",
        author="Bill Radjewski",
        endpoint="/ratings/elo",
        open_source=False,
        publishes_error_metrics=False,
        granularity="weekly",
        scorable=False,
        note=(
            "Weekly, and therefore the one entry here that could in principle be "
            "scored on the harness. It is not, yet, and the reason is honest "
            "rather than technical: CFBD warns that 'model changes can affect the "
            "comparability of values across periods', so a backtest resting on "
            "someone else's derived ratings can drift when they retrain. Our own "
            "Elo is in the scored table instead."
        ),
    ),
)


def by_name(name: str) -> Benchmark:
    """One benchmark, or a message naming the set."""
    for entry in BENCHMARKS:
        if entry.name == name:
            return entry
    raise KeyError(f"unknown benchmark {name!r}; the set is {[b.name for b in BENCHMARKS]}")


def scorable() -> tuple[Benchmark, ...]:
    """The benchmarks a walk-forward harness could legitimately score. Today: none."""
    return tuple(b for b in BENCHMARKS if b.scorable)


def display_rows() -> list[dict[str, str]]:
    """The comparison table, as data. Rendered by `cfbpoll benchmarks`."""
    return [
        {
            "name": b.name,
            "label": b.label,
            "author": b.author,
            "endpoint": b.endpoint,
            "open_source": "yes" if b.open_source else "no",
            "error_metrics": "yes" if b.publishes_error_metrics else "no",
            "granularity": b.granularity,
            "scorable": "yes" if b.scorable else "no",
            "standing": b.checkable,
        }
        for b in BENCHMARKS
    ]
