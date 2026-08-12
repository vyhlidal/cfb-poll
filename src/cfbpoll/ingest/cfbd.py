"""CFBD REST API v2 client - the weekly in-season pull.

Specified by report 01 §3.7 (the Sunday job), §3.6 (endpoints), §4.1 (terms).

THE CALL SEQUENCE IS 22 CALLS AND THE ORDER IS LOAD-BEARING:
   1 GET /info                      quota check FIRST, so the job fails fast and
                                    loud rather than half-completing
   2 GET /calendar                  resolve the current week W; NEVER hardcode it
   3 GET /games?week=W              results
   4 GET /games?week=W+1            next slate, for projections
   5 GET /games/teams?week=W        box scores
   6 GET /drives?week=W
   7 GET /plays?week=W              (year AND week are both required)
   8 GET /stats/game/advanced?week=W
   9 GET /stats/season
  10 GET /stats/season/advanced
  11 GET /ppa/teams
  12 GET /wepa/team/season          (Tier 1+)
13-17 GET /ratings/{sp,srs,elo,fpi,core}   BENCHMARKS ONLY, NEVER INPUTS
  18 GET /rankings                  BENCHMARK ONLY - human polls are constraint 1
  19 GET /records
  20 GET /lines                     BACKTEST BASELINE ONLY, never a feature
  21 GET /games/weather             (Tier 1+)
  22 GET /info/usage?days=7         log what we actually spent

Raw data precedes aggregates, and benchmarks/context come last, so that a
failure late still leaves everything needed to compute a ranking.

Chunky, not chatty: every call is season- or week-scoped, never team-scoped.
CFBD's own guidance - "loop over ~15 weeks rather than 130+ teams". Per-team
looping would cost ~138x more for identical data.

Budget: ~110 calls/month against Tier 1's 5,000. About 45x headroom.

TERMS (report 01 §4.1): attribution is explicitly NOT required and we give it
anyway, everywhere. Raw CFBD responses must never reach the public repo - they go
to the private archive only. The key lives in an Authorization header, never in a
URL, and never in the manifest.

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import Any

WEEKLY_CALL_BUDGET = 22
"""Steady-state calls per weekly run (report 01 §3.7). Guard against drift."""


def check_quota(min_remaining: int = 200) -> dict[str, Any]:
    """GET /info; abort the run if remainingCalls is below the floor."""
    raise NotImplementedError("ingest.cfbd.check_quota - scaffold; see report 01 §3.7")


def resolve_week(season: int) -> tuple[int, str]:
    """GET /calendar; return (week, season_type). The week is never hardcoded."""
    raise NotImplementedError("ingest.cfbd.resolve_week - scaffold; see report 01 §3.7")


def pull_week(season: int, week: int, archive_root: Any) -> dict[str, Any]:
    """Run the 22-call sequence, archiving each raw body before parsing anything."""
    raise NotImplementedError("ingest.cfbd.pull_week - scaffold; see report 01 §3.7")
