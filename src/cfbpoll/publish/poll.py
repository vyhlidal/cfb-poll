"""Turn a fit into the two published tables: full ratings, and the poll.

THE POLL IS ORDERED BY SCHEDULE ODDS (`[publication].headline_ordering`, decided
2026-08-12, docs/adr/0005-headline-ordering.md). The rank key is
`-log10 P(W >= W_t)`: how improbable it is that a team of reference quality q_ref
would have gone at least this well against this exact schedule. In one sentence a
fan can parse - THE HARDER IT WAS TO DO WHAT YOU DID, THE HIGHER YOU GO, measured
from results and never assumed from a conference name.

NOTHING WAS REMOVED WHEN THAT CHANGED. Every published row still carries the L4
résumé on the points scale ("these results are what a +18.4 team would be expected
to produce"), its margin-aware variant, its saturation flag, and the L3 Power
rating with the résumé-minus-power gap. Report 02 §3.5's argument is unaltered:
the two most common fan complaints ("you're just ranking who'd win" and "you're
ignoring that they got blown out") both need an on-page answer, and the Power
column and the gap ARE the answer. What changed on 2026-08-12 is which column
sorts the table.

Every published row also carries BOTH surfaces (live R(N,N), hindsight
R(N,final)), because report 02 §3.6 says to publish both and because a poll that
shows only the flattering surface is the failure this project exists to avoid. The
hindsight columns now move for unbeaten teams too, which they could not do under
the résumé ordering (study §5b) - that is the substantive gain from the change.

Four further presentation decisions live here and all are stated on the
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
   This is unchanged by the ordering decision and was not revisited.

3. SATURATED TEAMS ARE STILL MARKED IN THE TABLE. An undefeated team's wins-based
   résumé has no finite root (model/l4_resume.py explains why), so every unbeaten
   team sits on the published bracket. It no longer decides anything - the poll is
   not ordered on that column - and the flag stays precisely so a reader can see
   the property that made the résumé unusable as the headline.

4. q_ref IS ON THE ROW, WITH THE TEAM IT CAME FROM. The one free constant in the
   headline ordering is published per row rather than in a footnote, so any reader
   can look up that team in the same week's poll and check the constant against
   it (constraint 5).
"""

from __future__ import annotations

from typing import Any

import polars as pl

__all__ = [
    "HEADLINE_COLUMNS",
    "HEADLINE_ORDERINGS",
    "ORDERING_LAYER",
    "fbs_teams",
    "headline_frame",
    "headline_ordering",
    "order_by",
    "poll_frame",
    "publication_status",
    "ratings_frame",
    "team_classes",
    "team_records",
]

#: Every ordering the pipeline can be pointed at, mapped to the human-readable
#: layer name that appears on poll.json and model_params.json. `schedule_odds` is
#: the decision of 2026-08-12; `L4_resume` is what it replaced and remains
#: reachable, because a choice that cannot be switched back is not a choice.
ORDERING_LAYER: dict[str, str] = {
    "schedule_odds": "C_schedule_odds",
    "L4_resume": "L4_resume",
}
HEADLINE_ORDERINGS: tuple[str, ...] = tuple(ORDERING_LAYER)

#: (columns, descending) for each ordering, as a sort applied to a résumé/odds
#: table. Ascending tail then ascending mid-p then team is exactly
#: `schedule_odds.OddsFit.order_key`; mid-p only ever separates winless teams.
#: The odds sort deliberately keys on `tail_p` rather than on `odds_key`, because
#: `odds_key` is clamped at MAX_KEY and two different tails could share it.
ORDER_KEYS: dict[str, tuple[tuple[str, ...], tuple[bool, ...]]] = {
    "schedule_odds": (("tail_p", "mid_p", "team"), (False, False, False)),
    "L4_resume": (("resume", "resume_margin", "team"), (True, True, False)),
}

#: The published poll table, in order. The rank key is `odds_key` (and `tail_p`,
#: which is what it is a transform of); `resume`, `power` and `gap` are never
#: omitted (report 02 §3.5); the `*_hindsight` block is the same week re-scored
#: with the season's answers (report 02 §3.6).
HEADLINE_COLUMNS: tuple[str, ...] = (
    "rank",
    "team",
    "wins",
    "losses",
    "odds_key",
    "tail_p",
    "mid_p",
    "expected_wins",
    "surprise",
    "q_ref",
    "q_ref_team",
    "resume",
    "resume_margin",
    "power",
    "gap",
    "saturated",
    "rank_hindsight",
    "odds_key_hindsight",
    "tail_p_hindsight",
    "resume_hindsight",
    "resume_margin_hindsight",
    "power_hindsight",
    "gap_hindsight",
    "rank_delta",
    "team_class",
)


def headline_ordering(config: dict[str, Any]) -> str:
    """The ordering the poll is published in, validated against its display name.

    `[publication]` carries two strings that must agree: `headline_ordering`, which
    every code path reads, and `headline_layer`, which is the human-readable name
    stamped on artifacts and has been published since the L2 build. Two names for
    one fact is a drift hazard, so this turns it into an assertion: they are
    checked on every run rather than trusted.
    """
    pub = config["publication"]
    ordering = str(pub.get("headline_ordering", "schedule_odds"))
    if ordering not in ORDERING_LAYER:
        raise ValueError(
            f"unknown [publication].headline_ordering {ordering!r}; "
            f"expected one of {HEADLINE_ORDERINGS}"
        )
    declared = str(pub.get("headline_layer", ORDERING_LAYER[ordering]))
    if declared != ORDERING_LAYER[ordering]:
        raise ValueError(
            f"[publication].headline_layer is {declared!r} but headline_ordering is "
            f"{ordering!r}, whose layer is {ORDERING_LAYER[ordering]!r}. One of the two "
            "is wrong and an artifact would carry the wrong name (constraint 5)."
        )
    return ordering


def order_by(frame: pl.DataFrame, ordering: str, prefix: tuple[str, ...] = ()) -> pl.DataFrame:
    """Sort a published table into the headline order. The ONE place that rule lives.

    `prefix` is the leading key the caller needs (the grid sorts within each
    (N, K) cell), always ascending.
    """
    columns, descending = ORDER_KEYS[ordering]
    return frame.sort([*prefix, *columns], descending=[*([False] * len(prefix)), *descending])


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


#: Columns taken from BOTH surfaces, so the hindsight view of each is on the row.
#: Everything else (record, saturation flag, q_ref provenance, classification) is
#: a property of the evaluation week and is taken from the live table only.
_BOTH_SURFACES: tuple[str, ...] = (
    "rank",
    "odds_key",
    "tail_p",
    "resume",
    "resume_margin",
    "power",
    "gap",
)


def headline_frame(live: pl.DataFrame, hindsight: pl.DataFrame) -> pl.DataFrame:
    """The published poll: schedule-odds ranks, résumé and Power beside them, both
    surfaces, one row per team.

    Both arguments are single-evaluation-week tables from `model/retro.py` (the
    same schema the grid writes), already sorted into the headline order and
    already ranked. Only ranked teams appear, which is the FBS restriction of
    decision 1 above; `ratings_live.parquet` keeps everyone.

    Rank order is the LIVE ordering - R(N, N) is the poll as of week N. The
    hindsight columns are the retroactive view of the same week, and `rank_delta`
    is positive when a team rises in hindsight, i.e. when the live poll under-rated
    it. Since 2026-08-12 that delta is non-zero for unbeaten teams as well, which
    it structurally could not be under the résumé ordering.
    """
    keep = ["team", *_BOTH_SURFACES]
    a = live.filter(pl.col("rank").is_not_null())
    b = hindsight.filter(pl.col("rank").is_not_null()).select(keep)
    joined = (
        a.select(
            [
                *keep,
                "wins",
                "losses",
                "mid_p",
                "expected_wins",
                "surprise",
                "q_ref",
                "q_ref_team",
                "saturated",
                "team_class",
            ]
        )
        .join(b, on="team", how="left", suffix="_hindsight")
        .with_columns(rank_delta=pl.col("rank") - pl.col("rank_hindsight"))
    )
    return joined.select(HEADLINE_COLUMNS).sort("rank")


def publication_status(week: int, config: dict[str, Any]) -> tuple[bool, str | None]:
    """(provisional, label) for a given week, per [publication] in the config."""
    pub = config["publication"]
    provisional = int(week) < int(pub["headline_start_week"])
    return provisional, (str(pub["provisional_label"]) if provisional else None)
