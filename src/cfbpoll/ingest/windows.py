"""Week windows: the ONLY sanctioned way to say "through week N".

docs/data-findings.md §1 is binding and it is the reason this module exists:

    every week-scoped query, join, or bucket must condition on
    (season, season_type, week). A bare `week` filter is a bug.

Week numbering inside a season is not monotone and is not unique. The 2023
postseason contains week 1 (the 42 bowls, played 16 Dec - 9 Jan) AND weeks 11-15
(the FCS and D-II/D-III brackets, played from late November). 2025 contains week
1 and weeks 13-14. A `week <= N` filter therefore silently mixes January into
November, which in a walk-forward backtest is not a cosmetic bug - it is leakage
of the future into the fit, which invalidates the entire exercise.

The fix: a *bucket* is the pair (season_type, week). Buckets inside a season are
ordered by the earliest kickoff they contain, and "through bucket B" means every
game in a bucket ordered at or before B. Ordering by data rather than by
convention is what makes this immune to whichever numbering the upstream feed
happens to use in a given year.

The division-aware guard from docs/data-findings.md §2 lives here too, as
`suspicious_buckets`: it is applied to an ALREADY-FILTERED frame, so the four
D-II/D-III championship games dated 2025-12-13 that carry
season_type='regular', week=1 never reach it and never false-positive.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

__all__ = [
    "Bucket",
    "bucket_table",
    "games_before",
    "games_in_bucket",
    "games_through",
    "season_buckets",
    "suspicious_buckets",
]

#: A regular-season week that spans more than this many days is a numbering bug,
#: not a schedule. Postseason buckets legitimately span weeks (2025-26 bowl
#: season runs 14 Dec - 20 Jan) and are exempt. Derived from the data: the widest
#: regular-season bucket in 2021-2025 within the model universe is 8 days.
REGULAR_BUCKET_MAX_SPAN_DAYS = 21


@dataclass(frozen=True, order=True)
class Bucket:
    """One (season, season_type, week) window, with its position in the season."""

    order: int
    season: int
    season_type: str
    week: int

    @property
    def key(self) -> tuple[int, str, int]:
        return (self.season, self.season_type, self.week)

    @property
    def label(self) -> str:
        return f"{self.season}-{self.season_type[:4]}-w{self.week:02d}"


def bucket_table(games: pl.DataFrame) -> pl.DataFrame:
    """One row per (season, season_type, week), ordered within season by first kickoff.

    Ties on first kickoff are broken by (season_type, week) so the ordering is a
    pure function of the frame and never depends on row or dict order
    (report 03 §9.3 item 3).
    """
    agg = (
        games.group_by(["season", "season_type", "week"])
        .agg(
            first_kickoff=pl.col("start_date").min(),
            last_kickoff=pl.col("start_date").max(),
            n_games=pl.len(),
        )
        .sort(["season", "first_kickoff", "season_type", "week"])
    )
    return agg.with_columns(
        order=pl.int_range(pl.len()).over("season").cast(pl.Int32),
        span_days=(pl.col("last_kickoff") - pl.col("first_kickoff")).dt.total_days(),
    )


def season_buckets(games: pl.DataFrame, season: int) -> list[Bucket]:
    """Every bucket of one season, in play order."""
    tbl = bucket_table(games.filter(pl.col("season") == season))
    return [
        Bucket(order=int(r[0]), season=season, season_type=str(r[1]), week=int(r[2]))
        for r in tbl.select("order", "season_type", "week").iter_rows()
    ]


def games_through(
    games: pl.DataFrame,
    season: int,
    week: int,
    season_type: str = "regular",
    inclusive: bool = True,
) -> pl.DataFrame:
    """Exactly the games a fit "through (season, season_type, week)" may see.

    Every other module must go through this function. No model or baseline is
    allowed to select its own rows: the whole point of report 02 §5.1's strict
    walk-forward is that one piece of code owns the slicing and can be tested
    against a deliberately planted future game.
    """
    tbl = bucket_table(games.filter(pl.col("season") == season))
    match = tbl.filter((pl.col("season_type") == season_type) & (pl.col("week") == week))
    if match.is_empty():
        raise KeyError(
            f"no games in bucket (season={season}, season_type={season_type!r}, week={week}); "
            f"available: {tbl.select('season_type', 'week').rows()}"
        )
    cutoff = int(match["order"][0])
    keep = tbl.filter(pl.col("order") <= cutoff if inclusive else pl.col("order") < cutoff)
    return games.filter(pl.col("season") == season).join(
        keep.select("season_type", "week"), on=["season_type", "week"], how="semi"
    )


def games_in_bucket(games: pl.DataFrame, bucket: Bucket) -> pl.DataFrame:
    """The games of exactly one bucket."""
    return games.filter(
        (pl.col("season") == bucket.season)
        & (pl.col("season_type") == bucket.season_type)
        & (pl.col("week") == bucket.week)
    )


def games_before(games: pl.DataFrame, bucket: Bucket, all_buckets: list[Bucket]) -> pl.DataFrame:
    """Every game in the same season strictly before `bucket`. The training window."""
    prior = [b for b in all_buckets if b.order < bucket.order and b.season == bucket.season]
    if not prior:
        return games.head(0)
    keep = pl.DataFrame(
        {
            "season_type": [b.season_type for b in prior],
            "week": pl.Series([b.week for b in prior], dtype=pl.Int32),
        }
    )
    return games.filter(pl.col("season") == bucket.season).join(
        keep, on=["season_type", "week"], how="semi"
    )


def suspicious_buckets(games: pl.DataFrame) -> pl.DataFrame:
    """Division-aware week-numbering guard (docs/data-findings.md §2).

    Call this on an ALREADY-FILTERED frame - the FBS/FCS model universe, not the
    raw archive. Returns the regular-season buckets whose kickoffs span more days
    than a week can. An empty frame is a pass.
    """
    tbl = bucket_table(games)
    too_wide = pl.col("span_days") > REGULAR_BUCKET_MAX_SPAN_DAYS
    return tbl.filter((pl.col("season_type") == "regular") & too_wide).sort(["season", "week"])
