"""SportsDataverse bulk archive - the backfill, the standing fallback, and the loader.

Specified by report 01 §3.10 and §4.2; the binding data rules are docs/data-findings.md.

WHERE THE DATA ACTUALLY IS, because the obvious guess is wrong:
the bulk play-by-play is NOT in `cfbfastR-data/pbp/parquet/` - that directory is
stale and stops at 2021. The live data lives in RELEASE ASSETS of a different
repo: `sportsdataverse/sportsdataverse-data`, tag `cfbfastR_cfb_pbp`.

Schedules: use the `cfb_schedules_*` series and filter yourself. It is NOT
interchangeable with `schedules_*` - for 2024, cfb_schedules has 3,801 rows (all
divisions) against schedules' 865 (FBS subset), and the convention is
inconsistent across years (docs/data-findings.md §5).

Verified sizes, 2021-2025 parquet: 73.7 / 108.8 / 110.7 / 120.8 / 131.2 MB,
about 0.55 GB total. FBS-vs-FBS coverage 100/100/100/100/99.9 percent, 3,864
completed games (732/734/792/798/808).

Refresh: Sunday ~02:30 ET in season, verified against real commit history, which
sits comfortably inside the 24-hour freshness requirement.

LICENSE: MIT, and this is the load-bearing fact of the whole project. It means we
may REPUBLISH this archive, so a stranger can reproduce every ranking we have
ever published with no API key, no account, and no permission from anyone.

BEWARE WHAT IS IN THESE FILES: the PBP parquet ships precomputed EPA and wpa, and
the schedules ship home_pregame_elo and excitement_index. Those are someone
else's model output. They must never leak into a design matrix just because they
are conveniently present in the same file (report 01 §5.6);
`cfbpoll audit-features` is the enforcement. `RAW_COLUMNS` below is the complete
allow-list of columns this module will read, and it is deliberately short.

BINDING RULES APPLIED HERE (docs/data-findings.md):
  1. Every week-scoped operation keys on (season, season_type, week). A bare
     `week` filter is a bug - postseason week numbering mixes two conventions
     inside a single season (2023 postseason holds week 1 AND weeks 11-15).
  2. The `completed` filter is load-bearing. 2024 has 799 scheduled FBS-vs-FBS
     games and 798 completed: App State-Liberty (401640992) was canceled.
     Non-null scores are required on top of `completed`, because two 2025
     D-II games carry completed=True with null points.
  4. Division guards are applied AFTER classification filtering - four `week=1`
     games dated 2025-12-13 with season_type='regular' are D-II/D-III
     championships and would false-positive a naive December/week-1 guard.
  5. `cfb_schedules_*`, never `schedules_*`.

SCHEMA DRIFT, found while building this: `attendance` is Int32 in some seasons
and Boolean in others, so a naive `pl.concat` over the five files raises. This
module selects an explicit column list and casts, which sidesteps it entirely
and is why RAW_COLUMNS exists as an explicit tuple rather than a `*`.

STATUS: the loader is real. `download_season`/`backfill` remain stubs - the
archive was materialised by the step-1 backfill and this package reads it
offline. There is NO network access on any model or backtest path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from cfbpoll.config import REPO_ROOT

__all__ = [
    "CLASSES",
    "DEFAULT_ARCHIVE",
    "GAME_TYPES",
    "canonical_games",
    "fbs_vs_fbs",
    "load_games",
    "model_universe",
]

RELEASE_REPO = "sportsdataverse/sportsdataverse-data"
PBP_RELEASE_TAG = "cfbfastR_cfb_pbp"
SCHEDULE_SERIES = "cfb_schedules"  # NOT "schedules" - report 01 §3.10

DEFAULT_ARCHIVE = REPO_ROOT / "archive" / "sportsdataverse"

#: The only columns read out of the schedule parquet. Everything else in the file
#: - home_pregame_elo, home_post_win_prob, excitement_index - is a third party's
#: model output and is banned as a feature (report 01 §5.6, report 02 §3.10).
RAW_COLUMNS: tuple[str, ...] = (
    "game_id",
    "season",
    "week",
    "season_type",
    "start_date",
    "completed",
    "neutral_site",
    "conference_game",
    "home_team",
    "away_team",
    "home_points",
    "away_points",
    "home_division",
    "away_division",
    "notes",
)

CANONICAL_COLUMNS: tuple[str, ...] = (
    "game_id",
    "season",
    "week",
    "season_type",
    "game_type",
    "start_date",
    "completed",
    "neutral_site",
    "conference_game",
    "home_team",
    "away_team",
    "home_points",
    "away_points",
    "home_class",
    "away_class",
)

GAME_TYPES: tuple[str, ...] = ("regular", "conf_champ", "cfp", "bowl_non_cfp")
CLASSES: tuple[str, ...] = ("fbs", "fcs", "ii", "iii", "unknown")

# --------------------------------------------------------------------- game_type
#
# Derivation, in full, because this is the one column in the canonical frame that
# does not exist in the source and every downstream weight depends on it.
#
# Only FBS-vs-FBS games can carry a postseason label. Everything else - FCS
# playoffs, D-II/D-III championship brackets, FBS-vs-FCS regular season - is
# `regular` at full weight. That is not a shrug: the 0.25 bowl weight exists
# because non-CFP bowls have a systematic roster-availability problem (78+
# opt-outs and 431 portal entries in the 2021-22 postseason, report 02 §3.8) and
# that problem is an FBS phenomenon. An FCS quarterfinal is played with an intact
# roster and deserves full weight.
#
#   cfp           season_type == 'postseason' AND notes match CFP_PATTERN
#   bowl_non_cfp  season_type == 'postseason' AND not cfp
#   conf_champ    notes match CONF_CHAMP_PATTERN (2022-2025), or the structural
#                 fallback below for a season whose notes are entirely absent
#   regular       everything else
#
# Two data facts force the fallback:
#
#  (a) 2021 and 2022 carry NO postseason rows at all in cfb_schedules - 2021's
#      season_type column has exactly one value, 'regular'. So `cfp` and
#      `bowl_non_cfp` are structurally absent for those two seasons, and the
#      732/734 FBS-vs-FBS counts are regular season plus conference
#      championships plus Army-Navy, with no bowls. (Verified: 2023 = 750
#      regular + 42 postseason = 792.)
#  (b) 2021 has zero non-null `notes` on any FBS-vs-FBS game, so the notes rule
#      that identifies the ten 2022-2025 conference championships every year
#      cannot fire. The fallback is structural and, checked against 2021, exact:
#          championship week  = 1 + the last regular week with >= 25 FBS-vs-FBS
#                               games (i.e. the last full slate)
#          conf_champ         = a championship-week FBS-vs-FBS conference game in
#                               which BOTH teams have already played >= 12 games
#      The second clause is what separates the ten real title games (both
#      participants 12-12) from California-USC, a COVID-postponed regular-season
#      game replayed on championship Saturday (both participants 11-11).
#
# Numerical consequence of a conf_champ misclassification: none. [weights] gives
# conference_championship and regular_season the same 1.0. The label is for
# reporting and for the "which games count" rule in report 02 §7.6.
CFP_PATTERN = r"(?i)college football playoff|\bcfp\b"
CONF_CHAMP_PATTERN = r"(?i)championship"

_FULL_SLATE_GAMES = 25  # a "full regular-season Saturday" for the fallback above
_MIN_GAMES_BEFORE_TITLE_GAME = 12  # a conference champion has finished its season


def _read_season(season: int, archive: Path) -> pl.DataFrame:
    path = archive / "schedules" / f"{SCHEDULE_SERIES}_{season}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"missing schedule parquet for {season}: {path}. "
            "Run `cfbpoll archive sync --verify` (report 01 §5.4)."
        )
    return pl.read_parquet(path, columns=list(RAW_COLUMNS)).with_columns(
        pl.col("game_id").cast(pl.Int64),
        pl.col("season").cast(pl.Int32),
        pl.col("week").cast(pl.Int32),
        pl.col("home_points").cast(pl.Int32),
        pl.col("away_points").cast(pl.Int32),
    )


def _derive_game_type(df: pl.DataFrame) -> pl.DataFrame:
    """Attach `game_type`. See the block comment above for the full derivation."""
    fbs_pair = (pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs")
    notes = pl.col("notes").fill_null("")
    is_cfp = notes.str.contains(CFP_PATTERN)
    is_champ_note = notes.str.contains(CONF_CHAMP_PATTERN)

    df = df.with_columns(_fbs_pair=fbs_pair)

    # Structural fallback, per season, only where a season has no usable notes.
    fallback_ids: set[int] = set()
    for season in sorted(df["season"].unique().to_list()):
        season_fbs = df.filter((pl.col("season") == season) & pl.col("_fbs_pair"))
        if season_fbs.filter(pl.col("notes").is_not_null()).height:
            continue  # notes are present for this season; the notes rule governs
        fallback_ids |= _structural_conf_champs(df.filter(pl.col("season") == season), season_fbs)

    is_fallback = pl.col("game_id").is_in(sorted(fallback_ids)) if fallback_ids else pl.lit(False)

    game_type = (
        pl.when(~pl.col("_fbs_pair"))
        .then(pl.lit("regular"))
        .when((pl.col("season_type") == "postseason") & is_cfp)
        .then(pl.lit("cfp"))
        .when(pl.col("season_type") == "postseason")
        .then(pl.lit("bowl_non_cfp"))
        .when(is_champ_note | is_fallback)
        .then(pl.lit("conf_champ"))
        .otherwise(pl.lit("regular"))
    )
    return df.with_columns(game_type=game_type).drop("_fbs_pair")


def _structural_conf_champs(season_all: pl.DataFrame, season_fbs: pl.DataFrame) -> set[int]:
    """The notes-blind fallback. Returns the game_ids to label `conf_champ`."""
    regular = season_fbs.filter(pl.col("season_type") == "regular")
    if regular.is_empty():
        return set()
    counts = regular.group_by("week").len().sort("week")
    full = counts.filter(pl.col("len") >= _FULL_SLATE_GAMES)
    if full.is_empty():
        return set()
    champ_week = int(full["week"].max()) + 1  # type: ignore[arg-type]

    candidates = regular.filter((pl.col("week") == champ_week) & pl.col("conference_game"))
    if candidates.is_empty():
        return set()

    # "Games already played" counts every game involving the team, so an FCS
    # tune-up counts - a conference champion has played 12 by title-game day.
    played = season_all.filter(pl.col("week") < champ_week)
    tally: dict[str, int] = {}
    for home, away in zip(
        played["home_team"].to_list(), played["away_team"].to_list(), strict=True
    ):
        tally[home] = tally.get(home, 0) + 1
        tally[away] = tally.get(away, 0) + 1

    out: set[int] = set()
    for gid, home, away in zip(
        candidates["game_id"].to_list(),
        candidates["home_team"].to_list(),
        candidates["away_team"].to_list(),
        strict=True,
    ):
        if (
            tally.get(home, 0) >= _MIN_GAMES_BEFORE_TITLE_GAME
            and tally.get(away, 0) >= _MIN_GAMES_BEFORE_TITLE_GAME
        ):
            out.add(int(gid))
    return out


def canonical_games(
    seasons: list[int] | tuple[int, ...],
    archive: str | Path | None = None,
) -> pl.DataFrame:
    """Load the requested seasons into ONE canonical frame. No filtering applied.

    Includes scheduled-but-unplayed games so that callers can see them; use
    `load_games` for the modelling frame, which applies the completed filter.
    """
    root = Path(archive) if archive is not None else DEFAULT_ARCHIVE
    frames = [_read_season(int(s), root) for s in sorted(set(int(s) for s in seasons))]
    df = pl.concat(frames, how="vertical")

    df = df.with_columns(
        home_class=pl.col("home_division").fill_null("unknown"),
        away_class=pl.col("away_division").fill_null("unknown"),
        start_date=pl.col("start_date").str.to_datetime(
            "%Y-%m-%dT%H:%M:%S%.3fZ", time_zone="UTC", strict=False
        ),
    )
    df = _derive_game_type(df)
    return df.select(CANONICAL_COLUMNS).sort("game_id")


def load_games(
    seasons: list[int] | tuple[int, ...],
    archive: str | Path | None = None,
    universe: str = "model",
) -> pl.DataFrame:
    """The modelling frame: completed games with scores, in a chosen universe.

    universe:
      "all"          every completed game in the archive, all divisions
      "model"        every completed game with at least one FBS or FCS
                     participant (the fit universe - see [model] in the config)
      "fbs_vs_fbs"   the evaluation universe of report 02 §5.1
    """
    df = canonical_games(seasons, archive)
    df = df.filter(
        pl.col("completed")
        & pl.col("home_points").is_not_null()
        & pl.col("away_points").is_not_null()
    )
    if universe == "all":
        return df
    if universe == "model":
        return model_universe(df)
    if universe == "fbs_vs_fbs":
        return fbs_vs_fbs(df)
    raise ValueError(f"unknown universe {universe!r}; expected all|model|fbs_vs_fbs")


def fbs_vs_fbs(games: pl.DataFrame) -> pl.DataFrame:
    """The evaluation universe: both participants FBS (report 02 §5.1)."""
    return games.filter((pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs"))


def model_universe(games: pl.DataFrame) -> pl.DataFrame:
    """The fit universe: at least one FBS or FCS participant.

    Wider than FBS-vs-FBS on purpose. FBS-vs-FCS games are ~10% of the FBS
    schedule and are concentrated in exactly the weeks we are most data-starved,
    so excluding them (as the published CFBD ridge implementation does) throws
    away the early season (report 02 §3.7). Including FCS-vs-FCS games is what
    identifies the individual FCS coefficients rather than a pooled node - the
    pre-2015 FPI failure. FCS-vs-D-II games come along with that and give the
    handful of D-II opponents their own shrunken coefficients too.

    Excluded: D-II-vs-D-II and D-III-vs-D-III, which cannot reach an FBS team
    through any chain that matters and would triple the design matrix.
    """
    return games.filter(
        pl.col("home_class").is_in(["fbs", "fcs"]) | pl.col("away_class").is_in(["fbs", "fcs"])
    )


def download_season(season: int, dest: Any, verify: bool = True) -> Any:
    """Download one season's parquet assets and sha256-verify against the manifest."""
    raise NotImplementedError("ingest.sportsdataverse.download_season - scaffold; report 01 §3.10")


def backfill(seasons: list[int], dest: Any) -> Any:
    """Backfill 2021-2025. Ten HTTPS downloads, zero API quota, ~0.55 GB."""
    raise NotImplementedError("ingest.sportsdataverse.backfill - scaffold; report 01 §5.4")
