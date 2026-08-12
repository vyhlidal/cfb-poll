"""SportsDataverse bulk archive - the backfill and the standing fallback.

Specified by report 01 §3.10 and §4.2.

WHERE THE DATA ACTUALLY IS, because the obvious guess is wrong:
the bulk play-by-play is NOT in `cfbfastR-data/pbp/parquet/` - that directory is
stale and stops at 2021. The live data lives in RELEASE ASSETS of a different
repo: `sportsdataverse/sportsdataverse-data`, tag `cfbfastR_cfb_pbp`.

Schedules: use the `cfb_schedules_*` series and filter yourself. It is NOT
interchangeable with `schedules_*` - for 2024, cfb_schedules has 3,801 rows (all
divisions) against schedules' 865 (FBS subset), and the convention is
inconsistent across years.

Verified sizes, 2021-2025 parquet: 73.7 / 108.8 / 110.7 / 120.8 / 131.2 MB,
about 0.55 GB total. FBS-vs-FBS coverage 100/100/100/100/99.9 percent, 3,864
games. The single 2025 gap is game_id 401778314 - a December bowl mislabelled
week = 1, which validate/data_quality.py guards against by name.

Refresh: Sunday ~02:30 ET in season, verified against real commit history, which
sits comfortably inside the 24-hour freshness requirement.

LICENSE: MIT, and this is the load-bearing fact of the whole project. It means we
may REPUBLISH this archive, so a stranger can reproduce every ranking we have
ever published with no API key, no account, and no permission from anyone.

BEWARE WHAT IS IN THESE FILES: the PBP parquet ships precomputed EPA and wpa, and
the schedules ship home_pregame_elo and excitement_index. Those are someone
else's model output. They must never leak into a design matrix just because they
are conveniently present in the same file (report 01 §5.6);
`cfbpoll audit-features` is the enforcement.

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import Any

RELEASE_REPO = "sportsdataverse/sportsdataverse-data"
PBP_RELEASE_TAG = "cfbfastR_cfb_pbp"
SCHEDULE_SERIES = "cfb_schedules"  # NOT "schedules" - report 01 §3.10


def download_season(season: int, dest: Any, verify: bool = True) -> Any:
    """Download one season's parquet assets and sha256-verify against the manifest."""
    raise NotImplementedError("ingest.sportsdataverse.download_season - scaffold; report 01 §3.10")


def backfill(seasons: list[int], dest: Any) -> Any:
    """Backfill 2021-2025. Ten HTTPS downloads, zero API quota, ~0.55 GB.

    Report 01 §5.4(6): do this before anything else is built. Until it exists,
    every day of delay is a day an upstream outage costs us the backtest.
    """
    raise NotImplementedError("ingest.sportsdataverse.backfill - scaffold; report 01 §5.4")
