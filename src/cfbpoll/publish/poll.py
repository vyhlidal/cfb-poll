"""Turn a fit into the two published tables: full ratings, and the poll.

THE POLL IS THE RESUME (report 02 §3.5, and [publication] in the config). The
rank order is the L4 résumé rating - "given who they played and where, these
results are what a +18.4 team would be expected to produce" - and the L3 Power
rating sits beside every team with the gap between them shown. Never hide the
power number: the two most common fan complaints ("you're just ranking who'd
win" and "you're ignoring that they got blown out") both need an on-page answer,
and the gap IS the answer.

Every published row carries BOTH variants (wins-based and margin-aware) and BOTH
surfaces (live R(N,N), hindsight R(N,final)), because report 02 §3.4 and §3.6
say to publish both and because a poll that shows only the flattering surface is
the failure this project exists to avoid.

Three further presentation decisions live here and all are stated on the
methodology page rather than hidden in code:

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

3. SATURATED TEAMS ARE MARKED IN THE TABLE. An undefeated team's wins-based
   résumé has no finite root (model/l4_resume.py explains why), so every
   unbeaten team sits on the published bracket and the order among them comes
   from the margin-aware variant. That rule is `[resume].saturation_tiebreak`
   and it belongs on the page, not in a footnote.
"""

from __future__ import annotations

from typing import Any

import polars as pl

__all__ = [
    "HEADLINE_COLUMNS",
    "fbs_teams",
    "headline_frame",
    "poll_frame",
    "publication_status",
    "ratings_frame",
    "team_classes",
    "team_records",
]

#: The published poll table, in order. `resume` is the rank key; `power` and
#: `gap` are never omitted (report 02 §3.5); the `*_hindsight` block is the same
#: week re-scored with the season's answers (report 02 §3.6).
HEADLINE_COLUMNS: tuple[str, ...] = (
    "rank",
    "team",
    "wins",
    "losses",
    "resume",
    "resume_margin",
    "power",
    "gap",
    "saturated",
    "rank_hindsight",
    "resume_hindsight",
    "resume_margin_hindsight",
    "power_hindsight",
    "gap_hindsight",
    "rank_delta",
    "team_class",
)


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


def headline_frame(live: pl.DataFrame, hindsight: pl.DataFrame) -> pl.DataFrame:
    """The published poll: résumé ranks, Power beside them, both surfaces, one row.

    Both arguments are single-evaluation-week résumé tables from `model/retro.py`
    (the same schema the grid writes). Only ranked teams appear, which is the FBS
    restriction of decision 1 above; `ratings_live.parquet` keeps everyone.

    Rank order is the LIVE résumé - R(N, N) is the poll as of week N. The
    hindsight columns are the retroactive view of the same week, and
    `rank_delta` is positive when a team rises in hindsight, i.e. when the live
    poll under-rated it.
    """
    keep = ["team", "rank", "resume", "resume_margin", "power", "gap"]
    a = live.filter(pl.col("rank").is_not_null())
    b = hindsight.filter(pl.col("rank").is_not_null()).select(keep)
    joined = (
        a.select([*keep, "wins", "losses", "saturated", "team_class"])
        .join(b, on="team", how="left", suffix="_hindsight")
        .with_columns(rank_delta=pl.col("rank") - pl.col("rank_hindsight"))
    )
    return joined.select(HEADLINE_COLUMNS).sort("rank")


def publication_status(week: int, config: dict[str, Any]) -> tuple[bool, str | None]:
    """(provisional, label) for a given week, per [publication] in the config."""
    pub = config["publication"]
    provisional = int(week) < int(pub["headline_start_week"])
    return provisional, (str(pub["provisional_label"]) if provisional else None)
