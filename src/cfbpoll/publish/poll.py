"""Turn a fit into the two published tables: full ratings, and the poll.

Two presentation decisions live here and both are stated on the methodology page
rather than hidden in code:

1. THE POLL RANKS FBS TEAMS. FCS and lower-division teams hold real coefficients
   in the same fit under the same penalty - that is report 02 §3.7's whole
   argument, and it is what stops a good FCS opponent from being invisible - but
   they are not ranked in a college football poll. Their ratings are published in
   full in `ratings_live.parquet` with their classification, so nothing is
   hidden and anyone can rank all 380 teams from the same file. Report 02 §7.9
   leaves an all-divisions product open; this is the v1 answer, not a claim that
   the other one is wrong.

2. BEFORE `headline_start_week` THE OUTPUT IS LABELLED PROVISIONAL, not
   suppressed (report 02 §4, recommendation item 2, and configs/default.toml
   [publication]). The estimator runs from week 1; the headline poll does not.
"""

from __future__ import annotations

from typing import Any

import polars as pl

__all__ = ["fbs_teams", "poll_frame", "ratings_frame", "team_records"]


def fbs_teams(games: pl.DataFrame) -> set[str]:
    """Every team classified FBS in the given frame."""
    home = games.filter(pl.col("home_class") == "fbs")["home_team"].to_list()
    away = games.filter(pl.col("away_class") == "fbs")["away_team"].to_list()
    return set(home) | set(away)


def team_classes(games: pl.DataFrame) -> dict[str, str]:
    """Map team -> classification, preferring the highest division seen."""
    order = {"fbs": 0, "fcs": 1, "ii": 2, "iii": 3, "unknown": 4}
    out: dict[str, str] = {}
    for team, klass in sorted(
        list(zip(games["home_team"].to_list(), games["home_class"].to_list(), strict=True))
        + list(zip(games["away_team"].to_list(), games["away_class"].to_list(), strict=True))
    ):
        if team not in out or order[klass] < order[out[team]]:
            out[team] = klass
    return out


def team_records(games: pl.DataFrame) -> dict[str, tuple[int, int]]:
    """Wins and losses per team over exactly the games given. Ties are impossible
    in modern college football (overtime), so a non-win is a loss."""
    record: dict[str, list[int]] = {}
    for home, away, hp, ap in zip(
        games["home_team"].to_list(),
        games["away_team"].to_list(),
        games["home_points"].to_list(),
        games["away_points"].to_list(),
        strict=True,
    ):
        record.setdefault(home, [0, 0])
        record.setdefault(away, [0, 0])
        if hp > ap:
            record[home][0] += 1
            record[away][1] += 1
        elif ap > hp:
            record[away][0] += 1
            record[home][1] += 1
    return {team: (w, ll) for team, (w, ll) in sorted(record.items())}


def ratings_frame(ratings: dict[str, float], games: pl.DataFrame) -> pl.DataFrame:
    """Every team in the fit, with its class and record. Sorted by rating."""
    classes = team_classes(games)
    records = team_records(games)
    teams = sorted(ratings)
    return pl.DataFrame(
        {
            "team": teams,
            "team_class": [classes.get(t, "unknown") for t in teams],
            "rating": [float(ratings[t]) for t in teams],
            "wins": [records.get(t, (0, 0))[0] for t in teams],
            "losses": [records.get(t, (0, 0))[1] for t in teams],
        }
    ).sort(["rating", "team"], descending=[True, False])


def poll_frame(ratings_tbl: pl.DataFrame, restrict_to: set[str] | None = None) -> pl.DataFrame:
    """The ranked table. Rank 1 is the highest rating; ties break by team name."""
    tbl = ratings_tbl
    if restrict_to is not None:
        tbl = tbl.filter(pl.col("team").is_in(sorted(restrict_to)))
    tbl = tbl.sort(["rating", "team"], descending=[True, False])
    return tbl.with_columns(rank=pl.int_range(1, tbl.height + 1).cast(pl.Int32)).select(
        "rank", "team", "rating", "wins", "losses", "team_class"
    )


def publication_status(week: int, config: dict[str, Any]) -> tuple[bool, str | None]:
    """(provisional, label) for a given week, per [publication] in the config."""
    pub = config["publication"]
    provisional = int(week) < int(pub["headline_start_week"])
    return provisional, (str(pub["provisional_label"]) if provisional else None)
