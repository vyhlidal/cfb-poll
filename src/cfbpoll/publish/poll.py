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
    "HEADLINE_INTERVAL_ORDERING",
    "HEADLINE_ORDERINGS",
    "INTERVAL_COLUMNS",
    "attach_intervals",
    "interval_columns",
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
#:
#: `L4_resume_margin` is the study's candidate B, promoted from "a column on every
#: row" to "an ordering the pipeline can be pointed at" when `configs/recipes/`
#: landed. Nothing about the house poll changed: B lost ADR 0005 on the evidence
#: and it still loses, and it is here because `full-merit` is the recipe whose
#: whole argument is that margin should decide, and a recipe that could not select
#: the margin ordering would not be that argument. The numbers B needs were already
#: computed on every row of every artifact this project has ever published.
ORDERING_LAYER: dict[str, str] = {
    "schedule_odds": "C_schedule_odds",
    "L4_resume": "L4_resume",
    "L4_resume_margin": "L4_resume_margin",
}
HEADLINE_ORDERINGS: tuple[str, ...] = tuple(ORDERING_LAYER)

#: (columns, descending) for each ordering, as a sort applied to a résumé/odds
#: table. Ascending tail then ascending mid-p then team is exactly
#: `schedule_odds.OddsFit.order_key`; mid-p only ever separates winless teams.
#: The odds sort deliberately keys on `tail_p` rather than on `odds_key`, because
#: `odds_key` is clamped at MAX_KEY and two different tails could share it.
#:
#: `L4_resume_margin` keys on the margin-aware résumé ALONE, with no wins-based
#: first key. That is what makes it a different ordering rather than a different
#: tie-break: under `L4_resume` the margin variant only ever separates teams
#: already tied on the bound, and under this one it decides everything.
ORDER_KEYS: dict[str, tuple[tuple[str, ...], tuple[bool, ...]]] = {
    "schedule_odds": (("tail_p", "mid_p", "team"), (False, False, False)),
    "L4_resume": (("resume", "resume_margin", "team"), (True, True, False)),
    "L4_resume_margin": (("resume_margin", "team"), (True, False)),
}

#: Headline ordering -> the `model/bootstrap.ORDERINGS` name whose rank interval
#: qualifies THIS headline's rank.
#:
#: THIS MAPPING IS LOAD-BEARING AND IT USED TO BE A CONSTANT. `rank_lo` and
#: `rank_hi` sit beside `rank` on every published row precisely because "#4" and
#: "#4, 90% interval 2-66" are different claims; an interval computed under a
#: different ordering from the rank it qualifies is not a weaker version of that
#: promise, it is a false one. Before `configs/recipes/` the poll only ever ran
#: one headline in anger, so the wiring was hard-coded to `schedule_odds` and the
#: defect was invisible. Recipes make the second and third headline real, so the
#: mapping is explicit and `interval_columns` is the only way to read it.
HEADLINE_INTERVAL_ORDERING: dict[str, str] = {
    "schedule_odds": "schedule_odds",
    "L4_resume": "resume",
    "L4_resume_margin": "resume_margin",
}

#: The published poll table, in order. The rank key is `odds_key` (and `tail_p`,
#: which is what it is a transform of); `resume`, `power` and `gap` are never
#: omitted (report 02 §3.5); the `*_hindsight` block is the same week re-scored
#: with the season's answers (report 02 §3.6).
HEADLINE_COLUMNS: tuple[str, ...] = (
    "rank",
    # THE INTERVAL SITS NEXT TO THE RANK, not at the end of the row. A rank
    # interval that a reader has to scroll to is a rank interval that does not
    # do its job: the whole point (report 02 §3.3) is that "#4" and "#4, 90%
    # interval 2-66" are different claims and only one of them is true.
    "rank_lo",
    "rank_hi",
    "rank_median",
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
    "resume_rank_lo",
    "resume_rank_hi",
    "power",
    "power_se",
    "power_rank_lo",
    "power_rank_hi",
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

def interval_columns(ordering: str = "schedule_odds") -> dict[str, tuple[str, str]]:
    """The interval columns, and the bootstrap ordering each one is read from.

    `headline_frame` fills them from `model/bootstrap.py` when a draw set is
    supplied and leaves them null when it is not, so a run without a bootstrap
    publishes an empty column rather than a fabricated one.

    The `rank_*` triple follows the headline; `resume_rank_*` and `power_rank_*`
    are fixed, because those two columns are on the row under every recipe and
    always mean the same thing.
    """
    if ordering not in HEADLINE_INTERVAL_ORDERING:
        raise ValueError(
            f"unknown headline ordering {ordering!r}; expected one of {HEADLINE_ORDERINGS}"
        )
    head = HEADLINE_INTERVAL_ORDERING[ordering]
    return {
        "rank_lo": (head, "lo"),
        "rank_hi": (head, "hi"),
        "rank_median": (head, "median"),
        "resume_rank_lo": ("resume", "lo"),
        "resume_rank_hi": ("resume", "hi"),
        "power_rank_lo": ("power", "lo"),
        "power_rank_hi": ("power", "hi"),
    }


#: The published default's mapping. The column NAMES do not depend on the
#: ordering, so this is also the schema of the interval block on every row.
INTERVAL_COLUMNS: dict[str, tuple[str, str]] = interval_columns()


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


def _empty_intervals(teams: list[str]) -> pl.DataFrame:
    """Null interval columns, for a run with no bootstrap. Never fabricated."""
    return pl.DataFrame(
        {
            "team": teams,
            **{name: pl.Series([None] * len(teams), dtype=pl.Int32) for name in INTERVAL_COLUMNS},
        }
    )


def attach_intervals(
    table: pl.DataFrame,
    intervals: pl.DataFrame | None,
    ordering: str = "schedule_odds",
) -> pl.DataFrame:
    """Join the bootstrap's per-team rank intervals onto a published table.

    `intervals` is `model/bootstrap.intervals(...)`. A team present in the poll
    but absent from the draws keeps null bounds, which is the honest answer and
    cannot happen on a real window (the draw set is the same FBS pool).

    `ordering` decides which bootstrap ordering the `rank_*` triple is read from,
    so the interval beside a rank is always an interval on THAT rank. See
    `HEADLINE_INTERVAL_ORDERING`.
    """
    teams = table["team"].to_list()
    if intervals is None:
        return table.join(_empty_intervals(teams), on="team", how="left")
    # SELECT-WITH-ALIAS RATHER THAN RENAME, because under `L4_resume` and
    # `L4_resume_margin` two published columns read the SAME bootstrap column:
    # `rank_lo` is the headline's lower bound and `resume_rank_lo` is the résumé's,
    # and under those recipes the headline IS the résumé. A rename map keyed on the
    # source silently collapses the pair and drops `rank_lo` from the frame.
    narrow = intervals.select(
        [
            pl.col("team"),
            *[
                pl.col(f"{source}_rank_{end}").alias(name)
                for name, (source, end) in sorted(interval_columns(ordering).items())
            ],
        ]
    )
    return table.join(narrow, on="team", how="left")


def headline_frame(
    live: pl.DataFrame,
    hindsight: pl.DataFrame,
    intervals: pl.DataFrame | None = None,
    ordering: str = "schedule_odds",
) -> pl.DataFrame:
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
                "power_se",
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
    return attach_intervals(joined, intervals, ordering).select(HEADLINE_COLUMNS).sort("rank")


def publication_status(week: int, config: dict[str, Any]) -> tuple[bool, str | None]:
    """(provisional, label) for a given week, per [publication] in the config."""
    pub = config["publication"]
    provisional = int(week) < int(pub["headline_start_week"])
    return provisional, (str(pub["provisional_label"]) if provisional else None)
