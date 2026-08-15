"""Season-level facts the projection reads: who is FBS, final Power, the settled poll.

This is the seam between the Projection and the Poll, and it is deliberately a
ONE-WAY seam. Everything here READS the poll's own machinery - `l4_resume`,
`retro`, `publish.poll` - and computes nothing of its own, so a projection can
never quietly disagree with the poll about what 2024 finally looked like. Nothing
in this module is importable from a poll layer, and `validate/leakage.py` proves
per run that no poll design matrix contains anything it produces.

"HOW THE SEASON ACTUALLY SETTLED" IS R(final, final), the last bucket of the
season evaluated with the whole season's data - the hindsight surface's last row.
That is the most complete statement the poll ever makes about a season, which is
the right thing to grade a preseason guess against.

It is NOT the same table as `[weights].final_poll_excludes_non_cfp_bowls`, which
governs the poll's own published "final poll" and stops before the non-CFP bowls.
Both are defensible and they differ, so this module names which one it uses in
`SETTLED_DEFINITION` and every artifact stamps it. Grading a preseason projection
against a table that excludes the postseason would mean throwing away the games
with the most information in them.

CACHING. A full-season L3 Power fit is fast (about a second) but the backtest
wants five seasons twice over, so results are memoised in-process, keyed on
(season, config hash). Nothing is written to disk: a cache file is a
reproducibility hazard the moment a config changes underneath it, and this is
cheap enough not to need one.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from cfbpoll.config import config_hash, load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.plays import plays_for
from cfbpoll.model import l4_resume, retro
from cfbpoll.publish import poll as poll_mod

__all__ = [
    "SETTLED_DEFINITION",
    "fbs_teams",
    "final_power",
    "settled_poll",
]

SETTLED_DEFINITION = (
    "R(final, final): the last bucket of the season evaluated with the whole "
    "season's data, postseason included at the config's game weights"
)

_POWER_CACHE: dict[tuple[int, str], l4_resume.PowerSource] = {}
_POLL_CACHE: dict[tuple[int, str], pl.DataFrame] = {}


def fbs_teams(games: pl.DataFrame, season: int) -> list[str]:
    """The FBS membership of one season, sorted. The universe a projection ranks."""
    return sorted(poll_mod.fbs_teams(games.filter(pl.col("season") == int(season))))


def final_power(
    games: pl.DataFrame,
    season: int,
    plays: pl.DataFrame | None = None,
    config: dict[str, Any] | None = None,
) -> l4_resume.PowerSource:
    """The season's final Power, from the poll's own layer. Never recomputed here.

    This is the quantity the projection regresses toward the mean of, and it is
    the quantity the projection's response is measured on. Both halves come
    through this one function so that "the thing we project" and "the thing we
    score against" cannot drift apart into two slightly different numbers.
    """
    cfg = config if config is not None else load_config()
    key = (int(season), config_hash())
    if key in _POWER_CACHE:
        return _POWER_CACHE[key]
    season_games = games.filter(pl.col("season") == int(season))
    window_plays = None if plays is None else plays_for(plays, season_games)
    fitted = l4_resume.power_source(season_games, cfg, plays=window_plays)
    _POWER_CACHE[key] = fitted
    return fitted


def settled_poll(
    games: pl.DataFrame,
    season: int,
    plays: pl.DataFrame | None = None,
    config: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """R(final, final) for one season: the poll as it finally settled.

    Returned in the poll's own published order with the poll's own rank column,
    because a projection that grades itself against a re-derived ranking is
    grading itself against a ranking nobody published.
    """
    cfg = config if config is not None else load_config()
    key = (int(season), config_hash())
    if key in _POLL_CACHE:
        return _POLL_CACHE[key]
    season_games = games.filter(pl.col("season") == int(season))
    buckets = windows.season_buckets(season_games, int(season))
    final = buckets[-1]
    cell = retro.cell(
        season_games,
        final,
        final,
        cfg,
        power=final_power(games, season, plays, cfg),
        plays=plays,
        final_order=final.order,
    )
    _POLL_CACHE[key] = cell
    return cell
