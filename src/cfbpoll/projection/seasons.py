"""Season-level facts the projection reads: who is FBS, final Power, the settled poll.

This is the seam between the Projection and the Poll, and it is deliberately a
ONE-WAY seam. Everything here READS the poll's own machinery - `l4_resume`,
`retro`, `publish.poll` - and computes nothing of its own, so a projection can
never quietly disagree with the poll about what 2024 finally looked like. Nothing
in this module is importable from a poll layer, and `validate/leakage.py` proves
per run that no poll design matrix contains anything it produces.

ONE DEFINITION OF POWER, AND THIS MODULE IS WHERE IT IS PINNED (ADR 0013).
`projection-1.0.0` had two. Its input and its response were
`l4_resume.power_source` over a whole season at once - a full-season refit whose
blend weights are in-sample - while the grading page's `actual_power` came off
`retro.season_power(...)[final]`, the WALK-FORWARD surface the poll publishes
every week. The two are related by `graded = -3.65 + 0.70 * response` over 2025's
136 teams, so every team looked seven points over-projected and the league-wide
attribution read that scale change as a coefficient error. `projection-2.0.0`
adopts the PUBLISHED-POLL definition on both sides: `final_power` below now
returns the walk-forward Power at the season's last bucket, which is the exact
object `grade.grade_season` scores against and the exact object the poll's own
gate uses. The full-season refit remains available to the poll's diagnostics; it
is no longer reachable from anything the Projection publishes.

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

CACHING. The walk-forward Power is one L3 fit PER BUCKET rather than one per
season, so a season costs about fifteen times what the old full-season refit did
and the backtest wants five seasons of it. The whole walk is memoised in-process,
keyed on (season, config hash), and `season_power_walk` is public so that
`grade.grade_season` reads the same cached dict instead of computing a second
copy of the identical object. Nothing is written to disk: a cache file is a
reproducibility hazard the moment a config changes underneath it.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from cfbpoll.config import config_hash, load_config
from cfbpoll.ingest import windows
from cfbpoll.model import l4_resume, retro
from cfbpoll.publish import poll as poll_mod

__all__ = [
    "POWER_DEFINITION",
    "SETTLED_DEFINITION",
    "fbs_teams",
    "final_power",
    "season_power_walk",
    "settled_poll",
]

SETTLED_DEFINITION = (
    "R(final, final): the last bucket of the season evaluated with the whole "
    "season's data, postseason included at the config's game weights"
)

#: WHICH POWER, in one sentence, stamped on every projection artifact beside
#: `SETTLED_DEFINITION`. A published number whose scale is unstated is how
#: `projection-1.0.0` ended up comparing two of them (ADR 0013).
POWER_DEFINITION = (
    "retro.season_power(...)[final]: the WALK-FORWARD Power at the season's last "
    "bucket, whose blend weights are estimated out of sample week by week. This "
    "is the surface the poll publishes, the surface the gate uses, and the "
    "surface the grading page scores against. It is the projection's input, its "
    "response and its grading target, and they are the same object"
)

_WALK_CACHE: dict[tuple[int, str], dict[int, l4_resume.PowerSource]] = {}
_POLL_CACHE: dict[tuple[int, str], pl.DataFrame] = {}


def fbs_teams(games: pl.DataFrame, season: int) -> list[str]:
    """The FBS membership of one season, sorted. The universe a projection ranks."""
    return sorted(poll_mod.fbs_teams(games.filter(pl.col("season") == int(season))))


def season_power_walk(
    games: pl.DataFrame,
    season: int,
    plays: pl.DataFrame | None = None,
    config: dict[str, Any] | None = None,
) -> dict[int, l4_resume.PowerSource]:
    """bucket.order -> the poll's own walk-forward Power for that data window.

    Straight through to `retro.season_power`, memoised. Public so the grading
    loop can pass the cached dict back into `retro.live_surface` and
    `retro.hindsight_surface` rather than paying for the walk twice and risking
    two copies of a number that must be one number.
    """
    cfg = config if config is not None else load_config()
    key = (int(season), config_hash())
    cached = _WALK_CACHE.get(key)
    if cached is not None:
        return cached
    season_games = games.filter(pl.col("season") == int(season))
    walk = retro.season_power(season_games, int(season), cfg, plays=plays)
    _WALK_CACHE[key] = walk
    return walk


def final_power(
    games: pl.DataFrame,
    season: int,
    plays: pl.DataFrame | None = None,
    config: dict[str, Any] | None = None,
) -> l4_resume.PowerSource:
    """The season's final PUBLISHED Power. The one definition. See `POWER_DEFINITION`.

    This is the quantity the projection regresses toward the mean of, it is the
    quantity the projection's response is measured on, and it is the quantity the
    grading page calls `actual_power`. All three come through this one function
    so that "the thing we project" and "the thing we score against" cannot drift
    apart into two slightly different numbers - which is exactly what they did
    under `projection-1.0.0`, by seven points a team.
    """
    cfg = config if config is not None else load_config()
    season_games = games.filter(pl.col("season") == int(season))
    walk = season_power_walk(games, season, plays, cfg)
    buckets = windows.season_buckets(season_games, int(season))
    return walk[buckets[-1].order]


def settled_poll(
    games: pl.DataFrame,
    season: int,
    plays: pl.DataFrame | None = None,
    config: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """R(final, final) for one season: the poll as it finally settled.

    Returned in the poll's own published order with the poll's own rank column,
    because a projection that grades itself against a re-derived ranking is
    grading itself against a ranking nobody published. The Power handed in is the
    walk-forward one, so this table is the same R(final, final) the hindsight
    surface's last row carries and not a second construction of it.
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
