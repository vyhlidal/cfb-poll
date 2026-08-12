"""The poll-input leakage audit. This module fails the build on banned features.

Specified by report 02 §3.10. Backs `cfbpoll audit-features --fail-on-banned`,
which runs in both weekly.yml and reproducibility.yml.

ALLOWED, and nothing else:
  L1: play EPA, offense team id, defense team id, home/away/neutral, quarter,
      score margin, clock (the last three only for garbage-time filtering)
  L2: final score, team ids, home/away/neutral, game type
  L3: L1 and L2 outputs
  L4: L3 outputs, win/loss, schedule

BANNED, with the reason (the same table is reproduced in docs/constraints.md):
  AP / Coaches / CFP rankings          constraint 1, directly
  recruiting rankings, talent          constraint 2 - reputation prior
  returning production / starters      constraint 2
  prior-season ratings of any kind     constraint 2
  SP+ or FPI as features               indirect violation - both embed
                                       recruiting-based priors, so importing
                                       them imports the prior
  Vegas lines as features              market opinion is partly poll-driven, and
                                       it destroys independence from the very
                                       baseline we measure against
  conference identity as a feature     a reputation prior in disguise. Conference
                                       strength must EMERGE from results
  brand / stadium prestige / TV rating obviously

THE TRAP THIS EXISTS FOR: the SportsDataverse parquet files ship precomputed
`EPA` and `wpa` columns, and the schedules ship `home_pregame_elo`,
`home_postgame_elo` and `excitement_index` (report 01 §5.6). Those are someone
else's model output sitting in the same file as the facts. They must not reach a
design matrix just because they are convenient.

A CI check that fails the build if any banned column reaches a model matrix is
cheap insurance and a good open-source signal.

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import Any

BANNED_COLUMN_PATTERNS: tuple[str, ...] = (
    "ap_",
    "coaches_",
    "cfp_rank",
    "poll",
    "recruit",
    "talent",
    "returning_",
    "prior_season",
    "sp_plus",
    "sp+",
    "fpi",
    "spread",
    "line",
    "moneyline",
    "over_under",
    "conference",
    "elo",
    "excitement_index",
)
"""Indicative, not final. The real gate is an ALLOW-list check (see audit)."""

ALLOWED_BY_LAYER: dict[str, tuple[str, ...]] = {
    "L1": ("epa", "offense_team_id", "defense_team_id", "site", "quarter", "score_margin", "clock"),
    "L2": ("home_points", "away_points", "home_team_id", "away_team_id", "site", "game_type"),
    "L3": ("l1_rating", "l2_rating"),
    "L4": ("power_rating", "win", "loss", "opponent_team_id", "site"),
}


def audit(matrices: dict[str, Any], fail_on_banned: bool = False) -> list[str]:
    """Assert every design matrix contains only its layer's allowed columns.

    Allow-list, not deny-list: a new banned input nobody thought of must fail
    closed. Returns the list of violations; raises when fail_on_banned is set.
    """
    raise NotImplementedError("validate.leakage.audit - scaffold; see report 02 §3.10")
