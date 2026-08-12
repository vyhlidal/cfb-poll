"""The eight backtest baselines. Cheap to build, and they make the report credible.

Specified by report 02 §5.3. Five are computed here as raters; three are
reference series rather than models.

  COMPUTED (one module each, per report 03 §6.2)
    winpct.py         home-team-always-wins floor, and naive win percentage
    colley.py         the zero-margin, zero-prior BCS ancestor (~30 lines)
    srs.py            Sports-Reference CFB convention: +/-24 cap, +/-7 floor
    elo.py            K=25 with the 538 MOV multiplier and HFA
    random_walker.py  Callaghan/Mucha/Porter - statistically TIED with least
                      squares for NCAAF in Barrow et al., i.e. the one baseline
                      that might genuinely beat us

  REFERENCE SERIES (loaded, not fitted - functions below)
    closing_line      the practical ceiling. NEVER a model feature.
    cfp_committee     the comparison target, scored retrodictively with the same
                      code on the same games. If the model beats the committee on
                      violations, that is the headline finding.

The system names here must stay in sync with the `system` column of
cfb_backtest_metrics in report 03 §5.6:
    ours | colley | srs | elo | random_walker | closing_line | cfp

`l2` is our own system and is registered here alongside the baselines so the
harness scores every system through one identical code path. `home_team` has no
ratings at all and is handled in the harness as a constant-prediction system.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import polars as pl

from cfbpoll.backtest.baselines import colley, elo, random_walker, srs, winpct
from cfbpoll.model import l2_results

__all__ = ["RATERS", "SYSTEMS", "cfp_committee", "closing_line", "resolve"]

SYSTEMS = (
    "l2",
    "home_team",
    "winpct",
    "colley",
    "srs",
    "elo",
    "random_walker",
    "closing_line",
    "cfp",
)

#: system name -> rate(games, plays, through_week) -> {team: rating}
RATERS: dict[str, Callable[..., dict[str, float]]] = {
    "l2": l2_results.rate,
    "winpct": winpct.rate,
    "colley": colley.rate,
    "srs": srs.rate,
    "elo": elo.rate,
    "random_walker": random_walker.rate,
}

#: Names accepted on the command line, mapped to the canonical name written to
#: backtest_metrics.json and to cfb_backtest_metrics (report 03 §5.6).
ALIASES: dict[str, str] = {
    "ours": "l2",
    "l2_results": "l2",
    "walker": "random_walker",
    "randomwalker": "random_walker",
    "win_pct": "winpct",
    "home": "home_team",
    "home_field": "home_team",
}

#: The floor baseline. It has no ratings, so it is not in RATERS.
CONSTANT_SYSTEMS = ("home_team",)


def resolve(name: str) -> str:
    """Canonicalise a system name, or say clearly which names exist."""
    key = name.strip().lower()
    key = ALIASES.get(key, key)
    if key not in RATERS and key not in CONSTANT_SYSTEMS:
        raise KeyError(
            f"unknown system {name!r}; available: "
            f"{sorted(set(RATERS) | set(CONSTANT_SYSTEMS) | set(ALIASES))}"
        )
    return key


def closing_line(games: pl.DataFrame) -> Any:
    """Load historical closing spreads as a prediction series (report 02 §5.3).

    Baseline only. Market opinion is partly poll-driven and using it as a feature
    would also destroy independence from the thing we are measuring against
    (report 02 §3.10).

    NOT IMPLEMENTED: the archive carries no spreads. CFBD /lines is the intended
    source and the terms question in report 02 §3.9 is unresolved.
    """
    raise NotImplementedError("baselines.closing_line - no spread source in the archive; §5.3")


def cfp_committee(season: int) -> Any:
    """Load the final CFP committee ranking for a season (report 02 §5.3, §5.5).

    NOT IMPLEMENTED: the committee rankings are a HUMAN POLL. They are a
    comparison target scored with the same code on the same games, never a
    feature, and the loader must therefore live behind an explicit boundary that
    `cfbpoll audit-features` can see. Report 02 §5.5 carries the five final
    rankings verbatim for when it is built.
    """
    raise NotImplementedError("baselines.cfp_committee - scaffold; see report 02 §5.5")
