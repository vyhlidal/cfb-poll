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

`l1`, `l2`, `l3`, `resume` and `schedule_odds` are our own layers and are
registered here alongside the baselines so the harness scores every system through
one identical code path. That is not bookkeeping: the whole claim under test in
report 02 §3.3 is that the L3 blend beats the L2 results core, and the only way to
make that falsifiable is for both to be scored by the same code on the same games.
`l1` is registered for the same reason - efficiency alone is not expected to beat
either, and publishing it is how the blend's contribution stays visible rather
than asserted. `home_team` has no ratings at all and is handled in the harness as
a constant-prediction system.

`schedule_odds` IS THE HEADLINE ORDERING and `resume` IS THE ONE IT REPLACED, and
BOTH stay in the scored set permanently (ADR 0005, 2026-08-12). The decision
between them was made on measured retrodictive violations and measured forward
ordering accuracy; leaving the loser out of the table afterwards would make the
decision unfalsifiable from that week on. They are within 0.4 percentage points of
each other on violations over 2021-2024 and the harness is where anyone - us
included - finds out if that stops being true.

WHY BOTH NEED A PREDICTION PROXY. Each is retrodictive by construction (report 02
§3.4, §3.5): they answer "what do these results imply", not "who wins next week".
For the résumé two consequences make it uninterpretable as a margin predictor, and
both are properties of the estimator rather than accidents:

  1. Every undefeated team sits on the same q bound, so the rating difference
     between an unbeaten team and anyone else is a truncation artefact.
  2. The résumé is a monotone but strongly nonlinear function of Power, so the
     one affine map the harness fits per week cannot be right for both ends of
     the table at once.

Schedule odds has the same problem in a different shape: -log10 of a tail
probability is a log-scale quantity that grows with the number of games played, so
a week-5 key and a week-13 key are not on the same scale, and no single affine map
takes it to points.

So both PREDICT with the Power source they were built on and are SCORED on the
retrodictive metrics - violations first, which is the gate the L2-only build
rightly missed (report 02 §5.4, `[gate].violations_must_beat`). Reporting a
margin MAE for either one's own rating scale would be measuring the wrong thing
and flattering nobody. Which Power source that is comes from the config, so
`prediction_source` is a function of it rather than a constant.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import polars as pl

from cfbpoll.backtest.baselines import colley, elo, random_walker, srs, winpct
from cfbpoll.model import l1_efficiency, l2_results, l3_power, l4_resume, schedule_odds

__all__ = [
    "PLAY_LEVEL_SYSTEMS",
    "PREDICTION_SOURCE",
    "RATERS",
    "RETRODICTIVE_SYSTEMS",
    "SYSTEMS",
    "cfp_committee",
    "closing_line",
    "prediction_source",
    "resolve",
]

SYSTEMS = (
    "schedule_odds",
    "resume",
    "l3",
    "l2",
    "l1",
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
    "schedule_odds": schedule_odds.rate,
    "resume": l4_resume.rate,
    "l3": l3_power.rate,
    "l2": l2_results.rate,
    "l1": l1_efficiency.rate,
    "winpct": winpct.rate,
    "colley": colley.rate,
    "srs": srs.rate,
    "elo": elo.rate,
    "random_walker": random_walker.rate,
}

#: Systems that ORDER rather than predict. Their margin columns come from their
#: Power source and their own column is `retrodictive_violation_rate`; see the
#: module docstring. Named so a reader of backtest_metrics.json can tell which
#: rows are being scored on the metric they exist for.
RETRODICTIVE_SYSTEMS: frozenset[str] = frozenset({"schedule_odds", "resume"})

#: Systems that cannot be fitted from the scoreboard alone. The harness loads the
#: play archive only when one of these is asked for, so a scores-only run costs
#: nothing (report 03 §7.3: a challenger declares what it needs).
PLAY_LEVEL_SYSTEMS: frozenset[str] = frozenset({"l1", "l3"})

#: system name -> the system whose ratings produce its MARGIN predictions. Absent
#: means "its own". See the module docstring: both retrodictive orderings are
#: desert measures and predict with their Power source - which is
#: `[resume].power_source`, so the mapping is a function of the config rather than
#: a constant. The dict is the L2-era default and `prediction_source` is what the
#: harness calls.
PREDICTION_SOURCE: dict[str, str] = {"resume": "l2", "schedule_odds": "l2"}


def prediction_source(name: str, config: dict[str, Any] | None = None) -> str:
    """The system whose ratings produce `name`'s margin predictions.

    The two retrodictive orderings predict with the Power source they were built
    on (see the module docstring), and that source is `[resume].power_source`.
    Flipping the config from L2 to L3 must therefore move their prediction proxy
    with it, or the harness would score them through a layer they did not use -
    which would be a silent, invisible lie in the one table that is supposed to
    settle whether L3 beat L2.
    """
    if name in RETRODICTIVE_SYSTEMS and config is not None:
        return "l3" if str(config["resume"]["power_source"]).upper() == "L3" else "l2"
    return PREDICTION_SOURCE.get(name, name)


#: Names accepted on the command line, mapped to the canonical name written to
#: backtest_metrics.json and to cfb_backtest_metrics (report 03 §5.6).
ALIASES: dict[str, str] = {
    "ours": "l2",
    "l2_results": "l2",
    "l4": "resume",
    "l4_resume": "resume",
    "odds": "schedule_odds",
    "schedule-odds": "schedule_odds",
    "scheduleodds": "schedule_odds",
    "sor": "schedule_odds",
    "headline": "schedule_odds",
    "walker": "random_walker",
    "l1_efficiency": "l1",
    "efficiency": "l1",
    "l3_power": "l3",
    "power": "l3",
    "randomwalker": "random_walker",
    "win_pct": "winpct",
    "home": "home_team",
    "home_field": "home_team",
}

#: The floor baseline. It has no ratings, so it is not in RATERS.
CONSTANT_SYSTEMS = ("home_team",)


def resolve(name: str, extra: Mapping[str, Any] | None = None) -> str:
    """Canonicalise a system name, or say clearly which names exist.

    `extra` is the challenge harness's rater map (`backtest/challenge.py`). A
    challenger is scored as one more name in the same `--systems` list, through
    the same walk, against the same baselines, which is the only arrangement in
    which "did it beat the model" has a mechanical answer. It is passed in rather
    than registered globally so that importing a stranger's module cannot change
    what `cfbpoll backtest` scores.
    """
    key = name.strip().lower()
    key = ALIASES.get(key, key)
    if key not in RATERS and key not in CONSTANT_SYSTEMS and key not in (extra or {}):
        raise KeyError(
            f"unknown system {name!r}; available: "
            f"{sorted(set(RATERS) | set(CONSTANT_SYSTEMS) | set(ALIASES) | set(extra or {}))}"
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
