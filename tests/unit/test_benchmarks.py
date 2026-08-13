"""The benchmarks-only display set, and the line it must never cross.

One rule, tested three ways: a third-party rating may be displayed, compared
against and argued with, and may never be a model input. The audit
(`validate/leakage.py`) is what enforces that on real frames; these tests keep
the ROSTER honest, because a roster that quietly acquired a scorable entry, or a
name that collided with an allow-listed column, would be the first step toward
the audit having something to catch.
"""

from __future__ import annotations

import pytest

from cfbpoll import benchmarks
from cfbpoll.ingest import cfbd
from cfbpoll.validate import leakage


def test_every_benchmark_names_an_author_and_an_endpoint() -> None:
    assert benchmarks.BENCHMARKS, "an empty roster is the same as no rule"
    for entry in benchmarks.BENCHMARKS:
        assert entry.author, entry.name
        assert entry.endpoint.startswith("/ratings/"), entry.name
        assert entry.granularity in ("season", "weekly"), entry.name
        assert len(entry.note) > 80, f"{entry.name}: a benchmark with no note is a logo"


def test_core_is_attributed_correctly_and_described_honestly() -> None:
    """The name is Bill Radjewski. Getting it wrong is the cheapest possible own goal.

    And the two facts about CORE that matter are the ones this project's
    differentiation now rests on: the implementation is closed, and no error
    metrics are published. Both are stated as facts rather than as complaints,
    and both are pinned here so a later edit cannot soften them by accident.
    """
    core = benchmarks.by_name("core")
    assert core.author.startswith("Bill Radjewski")
    assert "Radford" not in core.author
    assert core.open_source is False
    assert core.publishes_error_metrics is False
    assert core.checkable == "closed implementation, no published error metrics"
    assert core.provider == "CollegeFootballData.com"


def test_nothing_in_the_roster_is_scorable_and_the_reason_is_recorded() -> None:
    """Today the honest answer is none, and that must be said rather than implied.

    A season-final rating in a walk-forward table beside systems that saw through
    week N-1 would flatter it and measure nothing. If an entry ever becomes
    scorable, this test fails and whoever changed it has to say why in the diff.
    """
    assert benchmarks.scorable() == ()
    for entry in benchmarks.BENCHMARKS:
        if entry.granularity == "season":
            assert not entry.scorable, f"{entry.name}: season-final cannot be walked forward"


def test_a_benchmark_name_is_never_mistaken_for_one_of_our_scored_systems() -> None:
    """`srs` and `elo` exist on both sides and mean different things.

    The rows in the backtest table are OUR implementations, fitted from the
    scoreboard walk-forward. The roster entries are the vendor's season-final
    series. Conflating them would put a number in a published table that no code
    in this repository produced, so both notes have to say so.
    """
    from cfbpoll.backtest import baselines

    for name in ("srs", "elo"):
        entry = benchmarks.by_name(name)
        assert name in baselines.RATERS
        assert "our own" in entry.note.lower() or "ours" in entry.note.lower()


def test_the_roster_matches_what_the_client_will_actually_fetch() -> None:
    assert {b.name for b in benchmarks.BENCHMARKS} == set(cfbd.BENCHMARK_RATINGS)


def test_an_unknown_benchmark_names_the_set() -> None:
    with pytest.raises(KeyError, match="unknown benchmark"):
        benchmarks.by_name("kenpom")


# ------------------------------------------------- the line, and the false positive


def test_a_core_column_would_be_named_by_the_deny_list() -> None:
    """The allow-list catches it either way; this makes the REPORT say which.

    `validate/leakage.py` fails closed on any column outside a layer's allow-list,
    so a CORE column could never reach a design matrix whether or not it were
    named here. Naming it is about the report: an operator reading a violation
    wants "core_rating" in the message, not "an unlisted column".
    """
    for column in ("cfbd_core", "core_rating", "core_overall", "team_core"):
        assert leakage.banned_hits([column]), column


def test_the_core_pattern_does_not_fire_on_the_scoreboard() -> None:
    """The trap, and the reason the pattern is not the bare substring "core".

    "core" is inside "score". A deny pattern that fires on `score_margin` and
    `home_score_after` would flag half the allow-list on every run, and a report
    that cries wolf on the scoreboard is a report nobody reads on the day it
    matters.
    """
    for column in (
        "score",
        "score_margin",
        "home_score_after",
        "away_score_after",
        "offense_score_after",
        "defense_score_after",
        "points_scored",
        "score_segment",
    ):
        assert not leakage.banned_hits([column]), column


def test_no_benchmark_name_appears_in_any_layer_allow_list() -> None:
    """The rule, stated as a property of the code rather than of a paragraph."""
    names = {b.name for b in benchmarks.BENCHMARKS}
    for layer, allowed in leakage.ALLOWED_BY_LAYER.items():
        for column in allowed:
            assert column.lower() not in names, f"{layer} allows a benchmark name: {column}"
