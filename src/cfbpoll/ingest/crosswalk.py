"""ESPN <-> CFBD team and game id mapping.

Specified by report 01 §3.10. The `cfb_crosswalk` release assets (2014-2026, MIT)
map team and game ids across ESPN and CFBD, which is the piece that saves real
pain when reconciling the two pipelines - and reconciling them is the whole point
of running two, since the cross-source score check in report 01 §5.5 is one of
the validation gates that can halt a publication.

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import Any


def load(seasons: list[int], root: Any) -> Any:
    """Load the crosswalk CSVs into a lookup table."""
    raise NotImplementedError("ingest.crosswalk.load - scaffold; see report 01 §3.10")


def map_team_id(source: str, team_id: int, season: int) -> int:
    """Translate a team id between sources; raise on an unmapped id rather than guess."""
    raise NotImplementedError("ingest.crosswalk.map_team_id - scaffold; see report 01 §3.10")
