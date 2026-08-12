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

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import Any

SYSTEMS = (
    "ours",
    "home_team",
    "winpct",
    "colley",
    "srs",
    "elo",
    "random_walker",
    "closing_line",
    "cfp",
)


def closing_line(games: Any) -> Any:
    """Load historical closing spreads as a prediction series (report 02 §5.3).

    Baseline only. Market opinion is partly poll-driven and using it as a feature
    would also destroy independence from the thing we are measuring against
    (report 02 §3.10).
    """
    raise NotImplementedError("baselines.closing_line - scaffold; see report 02 §5.3")


def cfp_committee(season: int) -> Any:
    """Load the final CFP committee ranking for a season (report 02 §5.3, §5.5)."""
    raise NotImplementedError("baselines.cfp_committee - scaffold; see report 02 §5.5")
