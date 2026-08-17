"""Pre-publication data-quality assertions. The gate that halts publication.

Specified by report 01 §5.5. CFBD's terms disclaim all warranty on accuracy, so
validation is OUR responsibility, not theirs.

The seven bullets of §5.5, each one a named check below:

  1. every FBS-vs-FBS game in the week has completed = true and non-null scores
     -> `completed_and_scored`
  2. the week's game count is within a sane range, and no team appears twice
     -> `week_game_count`, `no_team_twice`
  3. every team in /teams/fbs appears in cumulative stats with a plausible
     games-played count -> `teams_present_with_plausible_games`
  4. box score totals reconcile against /games final scores
     -> `box_scores_reconcile`
  5. week-over-week rating movement is bounded - an implausible jump is a
     data-error signal, not a ranking insight -> `rating_movement_bounded`
  6. CROSS-SOURCE: scores for the completed week match between CFBD and the
     SportsDataverse refresh -> `cross_source_scores`
  7. KNOWN-BUG GUARD: no game bucketed into week = 1 with a December or January
     start_date -> `no_december_january_week_one`

On failure: halt, alert, publish nothing.

THREE OUTCOMES, NEVER TWO. A check whose input is absent is `skip`, never
`pass`. Four of the seven read the PRIVATE CFBD archive or a second run
directory, and a fork has neither; reporting those as passes would turn "we
could not look" into "we looked and it was fine", which is the exact failure a
data-quality gate exists to prevent. `--strict` promotes any skip to a failure
for a runner that knows its inputs should all be present.

WHERE THIS DEPARTS FROM §5.5 AS WRITTEN, and why. Report 01 was written before
the backfill; docs/data-findings.md amended it and is binding:

  * §5.5's guard "no week = 1 game with a December start_date" false-positives
    on four D-II/D-III championship games dated 2025-12-13 that carry
    season_type = 'regular', week = 1 (data-findings §2). The guard here is
    division-aware AND keyed on (season_type, week), so those four never reach
    it. `game_id 401778314` - report 01's own example - is in fact archived as
    POSTSEASON week 1 (data-findings §1, §14.3), where a December kickoff is
    correct, so it is not a live failure either. What the guard catches is the
    thing that would actually be a bug: a December or January game bucketed into
    the REGULAR season's week 1, which a walk-forward window would read as a
    September result.

  * "no team appears twice" is false for two bucket shapes and true everywhere
    else, measured over 2021-2025: regular week 1 folds upstream's week 0 into
    it (a team can legitimately appear twice), and a postseason bucket holds
    every CFP round at once (a 12-team-era champion appears four times). Those
    allowances are structural and are stated as constants rather than hidden in
    a tolerance.

  * "the week's game count is within a sane range" cannot be a full-slate
    number. Championship week and the Army-Navy week are real weeks with 9-11
    and 1 FBS-vs-FBS games. The bound implemented is the honest weak one - at
    least one game, at most `MAX_WEEK_GAMES` - and it is the weakest check here.

STATUS: implemented. `cfbpoll validate` drives it.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

__all__ = [
    "Check",
    "Report",
    "check_week",
    "cross_source_scores",
    "validate_week",
]

PASS = "pass"
FAIL = "fail"
SKIP = "skip"

KNOWN_MISLABELLED_GAME_IDS = (401778314,)
"""Upstream bugs seen in the wild. Documented, not silently patched.

401778314 is New Mexico at Minnesota, 2025-12-26, which report 01 §5.5 cites as
a bowl mislabelled `week = 1`. In the archive as it actually ships it is
`season_type = 'postseason'`, `week = 1` - correct under the postseason's own
numbering (docs/data-findings.md §1). It is listed here because the id is quoted
in three documents and a reader needs to be able to find out what became of it.
"""

KNOWN_CANCELLED_GAME_IDS = (401640992,)
"""Scheduled FBS-vs-FBS games that were never played. Not a data error.

App State-Liberty, 2024-09-28, `completed = False` with null scores
(docs/data-findings.md §4). Named here so the completeness check can tell a
cancellation from a missing result instead of halting publication over one.
"""

#: An FBS-vs-FBS week holding more games than this is a numbering or a join bug.
#: Measured over 2021-2025: the largest regular-season week is 67 (2024 w14 and
#: 2025 w14), the smallest is 1 (Army-Navy, its own week in every season).
MAX_WEEK_GAMES = 70
MIN_WEEK_GAMES = 1

#: How many times one team may appear inside one bucket. Measured over
#: 2021-2025, FBS-vs-FBS, completed: regular weeks 2+ never exceed 1; regular
#: week 1 reaches 2 because upstream folds "week 0" into it; a postseason bucket
#: reaches 4 because the 12-team CFP plays four rounds inside one bucket.
MAX_TEAM_APPEARANCES_DEFAULT = 1
MAX_TEAM_APPEARANCES_REGULAR_WEEK_ONE = 2
MAX_TEAM_APPEARANCES_POSTSEASON = 4

#: A team's games-played through a window, as a band around the number of
#: PLAYABLE buckets in that window - buckets holding at least one FBS-vs-FBS
#: game, which is not the same as the number of buckets. The 2023 window through
#: regular week 15 contains 20 buckets and only 15 of them are weeks an FBS team
#: could have played in; the other five are FCS and D-II bracket rounds whose
#: first kickoff sorts them into the middle of December.
#:
#: The upper bound is `n_buckets + 1` because week 1 carries upstream's week 0 as
#: well and a team can legitimately appear in it twice. The lower bound is
#: `n_buckets - GAMES_PLAYED_SLACK` and covers bye weeks plus the tail weeks in
#: which most teams do not play at all. Measured for 2023: through w05, 4-6 games
#: against 5 playable buckets; through w15, 12-14 against 15. The slack of 5
#: leaves two games of headroom at the tightest point.
GAMES_PLAYED_SLACK = 5
GAMES_PLAYED_OVERRUN = 1

#: Week-over-week movement of the Power rating, in points, that is a data-error
#: signal rather than football. Measured on the 2023 R(N,N) diagonal
#: (`cfbpoll grid`), largest absolute move of any team in the fit universe:
#: w05 10.80, w06 8.05, w07 5.85, w08 6.45, w09 4.63, w10 4.78, w11 4.12,
#: w12 4.53, w13 4.32, w14 2.00, w15 2.04. The published window starts at week 5
#: (`[publication].headline_start_week`); before it the schedule graph is barely
#: connected and the same measurement reads 24.89 at w02, which is why a
#: provisional run skips this check rather than being judged against a bound
#: built for a connected graph.
MAX_RATING_MOVE_POINTS = 15.0


@dataclass(frozen=True)
class Check:
    """One assertion from report 01 §5.5, its verdict, and what it measured."""

    name: str
    spec: str
    status: str
    detail: str
    measured: dict[str, Any] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status == FAIL

    @property
    def skipped(self) -> bool:
        return self.status == SKIP

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "spec": self.spec,
            "status": self.status,
            "detail": self.detail,
            "measured": self.measured,
        }


@dataclass(frozen=True)
class Report:
    """Every check for one (season, season_type, week), and the verdict."""

    season: int
    week: int
    season_type: str
    checks: tuple[Check, ...]
    context: dict[str, Any] = field(default_factory=dict)
    strict: bool = False

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.failed)

    @property
    def skipped(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.skipped)

    @property
    def passed(self) -> bool:
        """Publishable. Under `--strict` a skipped check is not a pass."""
        return not self.failures and not (self.strict and self.skipped)

    def as_dict(self) -> dict[str, Any]:
        return {
            "spec": "research report 01 §5.5",
            "season": self.season,
            "season_type": self.season_type,
            "week": self.week,
            "strict": self.strict,
            "passed": self.passed,
            "n_pass": sum(1 for c in self.checks if c.status == PASS),
            "n_fail": len(self.failures),
            "n_skip": len(self.skipped),
            "checks": [c.as_dict() for c in self.checks],
            "context": self.context,
        }


# --------------------------------------------------------------------- helpers


def _bucket_rows(games: pl.DataFrame, season: int, season_type: str, week: int) -> pl.DataFrame:
    return games.filter(
        (pl.col("season") == season)
        & (pl.col("season_type") == season_type)
        & (pl.col("week") == week)
    )


def _fbs_pair(games: pl.DataFrame) -> pl.DataFrame:
    return games.filter((pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs"))


def _scored(games: pl.DataFrame) -> pl.DataFrame:
    return games.filter(
        pl.col("completed")
        & pl.col("home_points").is_not_null()
        & pl.col("away_points").is_not_null()
    )


def _team_appearance_allowance(season_type: str, week: int) -> int:
    if season_type != "regular":
        return MAX_TEAM_APPEARANCES_POSTSEASON
    if week == 1:
        return MAX_TEAM_APPEARANCES_REGULAR_WEEK_ONE
    return MAX_TEAM_APPEARANCES_DEFAULT


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------- the checks
#
# Every one takes what it needs, returns a Check, and never raises on a missing
# input - an absent input is a `skip` with the reason in `detail`.


def completed_and_scored(
    scheduled: pl.DataFrame, season: int, season_type: str, week: int
) -> Check:
    """§5.5(1): every FBS-vs-FBS game in the week is completed with both scores."""
    name, spec = "completed_and_scored", "report 01 §5.5 bullet 1"
    bucket = _fbs_pair(_bucket_rows(scheduled, season, season_type, week))
    if bucket.is_empty():
        return Check(
            name,
            spec,
            SKIP,
            f"no FBS-vs-FBS game is archived in ({season}, {season_type}, week {week})",
            {"n_scheduled": 0},
        )
    unplayed = bucket.join(_scored(bucket).select("game_id"), on="game_id", how="anti")
    cancelled = unplayed.filter(pl.col("game_id").is_in(list(KNOWN_CANCELLED_GAME_IDS)))
    offenders = unplayed.filter(~pl.col("game_id").is_in(list(KNOWN_CANCELLED_GAME_IDS)))
    measured = {
        "n_scheduled": int(bucket.height),
        "n_completed_with_scores": int(bucket.height - unplayed.height),
        "n_known_cancelled": int(cancelled.height),
        "offending_game_ids": sorted(int(g) for g in offenders["game_id"].to_list()),
    }
    if offenders.height:
        return Check(
            name,
            spec,
            FAIL,
            f"{offenders.height} of {bucket.height} FBS-vs-FBS games are not completed "
            f"with both scores: {measured['offending_game_ids']}",
            measured,
        )
    tail = f" ({cancelled.height} known cancellation)" if cancelled.height else ""
    return Check(
        name,
        spec,
        PASS,
        f"{measured['n_completed_with_scores']} of {bucket.height} FBS-vs-FBS games "
        f"completed with both scores{tail}",
        measured,
    )


def week_game_count(scored: pl.DataFrame, season: int, season_type: str, week: int) -> Check:
    """§5.5(2a): the week's game count is within a sane range.

    THE WEAKEST CHECK HERE, and deliberately so. A full-slate floor would fail
    every championship week and every Army-Navy week, which are real weeks with
    9-11 and 1 FBS-vs-FBS games respectively.
    """
    name, spec = "week_game_count", "report 01 §5.5 bullet 2"
    n = int(_fbs_pair(_bucket_rows(scored, season, season_type, week)).height)
    measured = {"n_games": n, "min": MIN_WEEK_GAMES, "max": MAX_WEEK_GAMES}
    if n < MIN_WEEK_GAMES or n > MAX_WEEK_GAMES:
        return Check(
            name,
            spec,
            FAIL,
            f"{n} completed FBS-vs-FBS games is outside "
            f"[{MIN_WEEK_GAMES}, {MAX_WEEK_GAMES}]",
            measured,
        )
    return Check(
        name,
        spec,
        PASS,
        f"{n} completed FBS-vs-FBS games, inside [{MIN_WEEK_GAMES}, {MAX_WEEK_GAMES}]",
        measured,
    )


def no_team_twice(scored: pl.DataFrame, season: int, season_type: str, week: int) -> Check:
    """§5.5(2b): no team appears twice in the week, with the structural allowances."""
    name, spec = "no_team_twice", "report 01 §5.5 bullet 2"
    bucket = _fbs_pair(_bucket_rows(scored, season, season_type, week))
    if bucket.is_empty():
        return Check(
            name,
            spec,
            SKIP,
            f"no completed FBS-vs-FBS game in ({season}, {season_type}, week {week})",
            {"n_games": 0},
        )
    allowance = _team_appearance_allowance(season_type, week)
    counts = Counter(bucket["home_team"].to_list() + bucket["away_team"].to_list())
    over = sorted((team, n) for team, n in counts.items() if n > allowance)
    measured = {
        "n_teams": len(counts),
        "max_appearances": max(counts.values()),
        "allowance": allowance,
        "over_allowance": [{"team": t, "appearances": n} for t, n in over],
    }
    if over:
        return Check(
            name,
            spec,
            FAIL,
            f"{len(over)} team(s) appear more than {allowance} time(s): "
            + ", ".join(f"{t} x{n}" for t, n in over),
            measured,
        )
    return Check(
        name,
        spec,
        PASS,
        f"{len(counts)} teams, most-played appears {measured['max_appearances']}x "
        f"(allowance {allowance})",
        measured,
    )


def teams_present_with_plausible_games(
    window: pl.DataFrame, fbs_teams: list[dict[str, Any]], n_buckets: int
) -> Check:
    """§5.5(3): every /teams/fbs team appears with a plausible games-played count.

    THE SMALLEST HONEST READING. §5.5 says "cumulative stats", which is CFBD's
    /stats/season endpoint; that body is not in the archive for most seasons and
    a fork will never have it. The season-to-date GAME frame is the cumulative
    record every layer of this project actually reads, so that is what is
    counted here. Skipped, not passed, when the /teams/fbs roster is absent.
    """
    name, spec = "teams_present_with_plausible_games", "report 01 §5.5 bullet 3"
    if not fbs_teams:
        return Check(
            name,
            spec,
            SKIP,
            "no archived /teams/fbs body for this season: the FBS roster is the "
            "PRIVATE CFBD archive (terms §3) and a fork does not have it",
            {},
        )
    schools = sorted({str(t["school"]) for t in fbs_teams if t.get("school")})
    counts = Counter(window["home_team"].to_list() + window["away_team"].to_list())
    lo = max(1, n_buckets - GAMES_PLAYED_SLACK)
    hi = n_buckets + GAMES_PLAYED_OVERRUN
    missing = [s for s in schools if s not in counts]
    implausible = sorted(
        (s, counts[s]) for s in schools if s in counts and not (lo <= counts[s] <= hi)
    )
    played = sorted(counts[s] for s in schools if s in counts)
    measured = {
        "n_fbs_teams": len(schools),
        "n_missing": len(missing),
        "missing": missing[:20],
        "games_played_min": played[0] if played else None,
        "games_played_max": played[-1] if played else None,
        "plausible_range": [lo, hi],
        "n_buckets_in_window": n_buckets,
        "implausible": [{"team": t, "games_played": n} for t, n in implausible],
    }
    if missing or implausible:
        return Check(
            name,
            spec,
            FAIL,
            f"{len(missing)} FBS team(s) absent from the window and {len(implausible)} "
            f"with a games-played count outside [{lo}, {hi}]",
            measured,
        )
    return Check(
        name,
        spec,
        PASS,
        f"all {len(schools)} FBS teams present, {played[0]}-{played[-1]} games played "
        f"against {n_buckets} buckets (plausible {lo}-{hi})",
        measured,
    )


def box_scores_reconcile(
    scored: pl.DataFrame,
    box_scores: list[dict[str, Any]],
    game_bodies: list[dict[str, Any]],
) -> Check:
    """§5.5(4): box score totals reconcile against the final scores.

    Two independent reconciliations, whichever is archived, preferring the first:

      * `/games/teams` - each team's `points` against that game's final score;
      * `/games` `homeLineScores`/`awayLineScores` - the quarter-by-quarter
        scoring summing to the same team's final.

    Both are compared against the CANONICAL frame - the one the model reads -
    rather than against another field of the same body, because the question
    that matters is whether the number we are about to publish is the number
    that was scored.
    """
    name, spec = "box_scores_reconcile", "report 01 §5.5 bullet 4"
    final: dict[int, tuple[str, str, int, int]] = {
        int(r["game_id"]): (
            str(r["home_team"]),
            str(r["away_team"]),
            int(r["home_points"]),
            int(r["away_points"]),
        )
        for r in scored.iter_rows(named=True)
    }

    disagreements: list[str] = []
    compared = 0
    source = ""

    if box_scores:
        source = "/games/teams"
        for body in box_scores:
            gid = int(body.get("id", 0))
            if gid not in final:
                continue
            home, away, hp, ap = final[gid]
            for line in body.get("teams") or []:
                team, points = str(line.get("team")), line.get("points")
                if points is None:
                    continue
                expected = hp if team == home else ap if team == away else None
                if expected is None:
                    continue
                compared += 1
                if int(points) != int(expected):
                    disagreements.append(f"{gid} {team}: box {points} vs final {expected}")
    elif game_bodies:
        source = "/games lineScores"
        for body in game_bodies:
            gid = int(body.get("id", 0))
            if gid not in final:
                continue
            _, _, hp, ap = final[gid]
            for side, expected in (("home", hp), ("away", ap)):
                lines = body.get(f"{side}LineScores")
                if not lines:
                    continue
                compared += 1
                total = sum(int(x) for x in lines)
                if total != int(expected):
                    disagreements.append(
                        f"{gid} {side}: line scores {lines} sum to {total} vs final {expected}"
                    )

    if not compared:
        return Check(
            name,
            spec,
            SKIP,
            "no archived box score for this week: /games/teams and the /games "
            "line scores are the PRIVATE CFBD archive (terms §3)",
            {"n_compared": 0},
        )
    measured = {
        "source": source,
        "n_compared": compared,
        "n_disagreements": len(disagreements),
        "disagreements": sorted(disagreements)[:20],
    }
    if disagreements:
        return Check(
            name,
            spec,
            FAIL,
            f"{len(disagreements)} of {compared} box-score totals disagree with the "
            f"final score ({source})",
            measured,
        )
    return Check(
        name,
        spec,
        PASS,
        f"{compared} box-score totals reconcile against the final scores ({source})",
        measured,
    )


def rating_movement_bounded(
    current: Path | None,
    previous: Path | None,
    max_move: float = MAX_RATING_MOVE_POINTS,
) -> Check:
    """§5.5(5): week-over-week rating movement is bounded.

    Compares the Power rating - the points-scale rating every other published
    column is built on - between two run directories. The headline key is a
    -log10 tail probability whose scale is not points and which legitimately
    swings by orders of magnitude, so it is reported as context and is not the
    thing bounded.
    """
    name, spec = "rating_movement_bounded", "report 01 §5.5 bullet 5"
    if current is None or previous is None:
        return Check(
            name,
            spec,
            SKIP,
            "needs this week's run directory and last week's; pass --from and "
            "--previous (or put the two runs side by side under one parent)",
            {},
        )
    paths = {
        "current": current / "ratings_live.parquet",
        "previous": previous / "ratings_live.parquet",
    }
    absent = sorted(k for k, p in paths.items() if not p.exists())
    if absent:
        return Check(
            name,
            spec,
            SKIP,
            f"no ratings_live.parquet in the {' and '.join(absent)} run directory",
            {"missing": [str(paths[k]) for k in absent]},
        )

    poll = _read_json(current / "poll.json") or {}
    if poll.get("provisional"):
        return Check(
            name,
            spec,
            SKIP,
            "this run is PROVISIONAL (before [publication].headline_start_week). "
            "Ratings legitimately move ~25 points a week while the schedule graph "
            "is still connecting, so a bound built for the published window would "
            "be measuring the wrong season",
            {"provisional": True},
        )

    now = pl.read_parquet(paths["current"]).select("team", "power", "rank")
    was = pl.read_parquet(paths["previous"]).select("team", "power", "rank")
    joined = was.join(now, on="team", suffix="_now").with_columns(
        move=(pl.col("power_now") - pl.col("power")).abs(),
        rank_move=(pl.col("rank_now") - pl.col("rank")).abs(),
    )
    if joined.is_empty():
        return Check(
            name,
            spec,
            SKIP,
            "the two run directories share no team; they are not consecutive weeks "
            "of one season",
            {"n_compared": 0},
        )
    over = joined.filter(pl.col("move") > max_move).sort("move", descending=True)
    worst = joined.sort("move", descending=True).head(1)
    measured = {
        "n_compared": int(joined.height),
        "max_move_points": float(worst["move"][0]),
        "max_move_team": str(worst["team"][0]),
        "max_rank_move": (
            int(joined["rank_move"].max()) if joined["rank_move"].max() is not None else None
        ),
        "bound_points": float(max_move),
        "n_over_bound": int(over.height),
        "over_bound": [
            {"team": str(t), "move_points": float(m)}
            for t, m in zip(
                over.head(20)["team"].to_list(), over.head(20)["move"].to_list(), strict=True
            )
        ],
    }
    if over.height:
        return Check(
            name,
            spec,
            FAIL,
            f"{over.height} team(s) moved more than {max_move:g} Power points; worst "
            f"{measured['max_move_team']} {measured['max_move_points']:.2f}",
            measured,
        )
    return Check(
        name,
        spec,
        PASS,
        f"largest Power move {measured['max_move_points']:.2f} points "
        f"({measured['max_move_team']}) over {joined.height} teams, bound {max_move:g}",
        measured,
    )


def cross_source_scores(cfbd: Any, sportsdataverse: Any) -> list[str]:
    """Diff the two independent pipelines over the same games (report 01 §5.5).

    `cfbd` is the parsed `/games` body; `sportsdataverse` is the canonical frame
    for the same bucket. Returns one string per disagreement, empty when they
    agree. The join key is `game_id`: CFBD ids ARE the SportsDataverse ids,
    measured 126 of 126 with zero exceptions (docs/data-findings.md §3, and the
    ID FINDING block in ingest/sportsdataverse.py).
    """
    by_id = {
        int(r["game_id"]): r
        for r in sportsdataverse.iter_rows(named=True)
        if r["home_points"] is not None and r["away_points"] is not None
    }
    out: list[str] = []
    for row in cfbd:
        gid = int(row.get("id", 0))
        mine = by_id.get(gid)
        if mine is None:
            continue
        theirs = (row.get("homePoints"), row.get("awayPoints"))
        if theirs[0] is None or theirs[1] is None:
            continue
        ours = (int(mine["home_points"]), int(mine["away_points"]))
        if (int(theirs[0]), int(theirs[1])) != ours:
            out.append(
                f"{gid} {mine['home_team']} v {mine['away_team']}: "
                f"CFBD {theirs[0]}-{theirs[1]} vs SportsDataverse {ours[0]}-{ours[1]}"
            )
    return sorted(out)


def cross_source(scored: pl.DataFrame, cfbd_rows: list[dict[str, Any]]) -> Check:
    """§5.5(6): the completed week's scores match between CFBD and SportsDataverse."""
    name, spec = "cross_source_scores", "report 01 §5.5 bullet 6"
    if not cfbd_rows:
        return Check(
            name,
            spec,
            SKIP,
            "no archived CFBD /games body for this bucket: the CFBD archive is "
            "PRIVATE (terms §3) and a fork runs on the MIT parquet alone",
            {"n_compared": 0},
        )
    ours = {int(g) for g in scored["game_id"].to_list()}
    theirs = {int(r["id"]) for r in cfbd_rows if r.get("id") is not None}
    shared = ours & theirs
    disagreements = cross_source_scores(cfbd_rows, scored)
    measured = {
        "n_cfbd_games": len(theirs),
        "n_sportsdataverse_games": len(ours),
        "n_compared": len(shared),
        "n_only_in_cfbd": len(theirs - ours),
        "only_in_cfbd": sorted(theirs - ours)[:20],
        "n_disagreements": len(disagreements),
        "disagreements": disagreements[:20],
    }
    if not shared:
        return Check(
            name,
            spec,
            SKIP,
            f"the archived CFBD body holds {len(theirs)} games and none of them are "
            "in this bucket's SportsDataverse frame; there is nothing to diff",
            measured,
        )
    if disagreements or theirs - ours:
        return Check(
            name,
            spec,
            FAIL,
            f"{len(disagreements)} score disagreement(s) and {len(theirs - ours)} game(s) "
            f"CFBD has that the parquet does not, over {len(shared)} shared games",
            measured,
        )
    return Check(
        name,
        spec,
        PASS,
        f"{len(shared)} games compared, every score identical between CFBD and "
        "SportsDataverse",
        measured,
    )


def no_december_january_week_one(scheduled: pl.DataFrame, season: int) -> Check:
    """§5.5(7): no REGULAR week-1 game with a December or January start_date.

    Division-aware, per docs/data-findings.md §2, and keyed on
    (season_type, week) per §1. Both amendments are load-bearing: without the
    first this fires on four D-II/D-III championship games dated 2025-12-13,
    and without the second it fires on all 240 postseason week-1 games in the
    archive, every one of which is correctly bucketed.
    """
    name, spec = "no_december_january_week_one", "report 01 §5.5 bullet 7"
    season_rows = scheduled.filter(pl.col("season") == season)
    if season_rows.is_empty():
        return Check(name, spec, SKIP, f"no games archived for {season}", {})
    involves_fbs = season_rows.filter(
        (pl.col("home_class") == "fbs") | (pl.col("away_class") == "fbs")
    )
    offenders = involves_fbs.filter(
        (pl.col("season_type") == "regular")
        & (pl.col("week") == 1)
        & pl.col("start_date").dt.month().is_in([12, 1])
    )
    ids = sorted(int(g) for g in offenders["game_id"].to_list())
    naive = season_rows.filter(
        (pl.col("week") == 1) & pl.col("start_date").dt.month().is_in([12, 1])
    )
    measured = {
        "n_offenders": len(ids),
        "offending_game_ids": ids[:20],
        "n_week_one_december_january_all_buckets": int(naive.height),
        "known_mislabelled_ids": list(KNOWN_MISLABELLED_GAME_IDS),
    }
    if ids:
        return Check(
            name,
            spec,
            FAIL,
            f"{len(ids)} FBS game(s) sit in REGULAR week 1 with a December/January "
            f"kickoff: {ids}",
            measured,
        )
    return Check(
        name,
        spec,
        PASS,
        f"no FBS game in regular week 1 has a December/January kickoff "
        f"({naive.height} such games exist in {season}, all correctly bucketed elsewhere)",
        measured,
    )


# ------------------------------------------------------------------- the driver


def validate_week(
    season: int,
    week: int,
    *,
    season_type: str = "regular",
    archive: Path | None = None,
    cfbd_archive: Path | None = None,
    run: Path | None = None,
    previous: Path | None = None,
    max_rating_move: float = MAX_RATING_MOVE_POINTS,
    strict: bool = False,
) -> Report:
    """Run every §5.5 assertion for one bucket. Nothing here fits or writes.

    Reads the MIT archive through the same loader every model layer uses, and
    the PRIVATE CFBD archive through the offline readers in `ingest/cfbd.py`,
    which never construct a session and never touch the network.
    """
    from cfbpoll.ingest import cfbd as cfbd_mod
    from cfbpoll.ingest import windows
    from cfbpoll.ingest.sportsdataverse import canonical_games, model_universe

    scheduled = canonical_games([season], archive)
    scored = _scored(scheduled)

    bucket_table = windows.bucket_table(scored.filter(pl.col("season") == season))
    match = bucket_table.filter(
        (pl.col("season_type") == season_type) & (pl.col("week") == week)
    )
    if match.is_empty():
        window = scored.head(0)
    else:
        window = windows.games_through(
            model_universe(scored), season=season, week=week, season_type=season_type
        )
    # PLAYABLE buckets, not buckets. See GAMES_PLAYED_SLACK: an FCS quarterfinal
    # is a bucket in this window and is not a week any FBS team could have played.
    n_buckets = int(_fbs_pair(window).select("season_type", "week").unique().height)

    cfbd_rows = cfbd_mod.archived_week_games(
        season, week, season_type=season_type, archive_root=cfbd_archive
    )
    box = cfbd_mod.archived_box_scores(
        season, week, season_type=season_type, archive_root=cfbd_archive
    )
    fbs_teams = cfbd_mod.archived_teams(season, cfbd_archive)

    bucket_scored = _bucket_rows(scored, season, season_type, week)
    checks = (
        completed_and_scored(scheduled, season, season_type, week),
        week_game_count(scored, season, season_type, week),
        no_team_twice(scored, season, season_type, week),
        teams_present_with_plausible_games(window, fbs_teams, n_buckets),
        box_scores_reconcile(bucket_scored, box, cfbd_rows),
        rating_movement_bounded(run, previous, max_rating_move),
        cross_source(bucket_scored, cfbd_rows),
        no_december_january_week_one(scheduled, season),
    )
    context = {
        "archive": str(archive) if archive is not None else None,
        "n_games_in_season": int(scored.filter(pl.col("season") == season).height),
        "n_buckets_in_window": n_buckets,
        "n_games_in_window": int(window.height),
        "run": str(run) if run is not None else None,
        "previous_run": str(previous) if previous is not None else None,
        # Which CFBD inputs this bucket actually found, one flag each. "The CFBD
        # archive exists" is not the question a reader has when three checks
        # skipped; "which of them did I have" is.
        "cfbd_inputs_found": {
            "games": bool(cfbd_rows),
            "box_scores": bool(box),
            "teams_fbs": bool(fbs_teams),
        },
    }
    return Report(
        season=season,
        week=week,
        season_type=season_type,
        checks=checks,
        context=context,
        strict=strict,
    )


def check_week(games: pl.DataFrame, season: int, week: int) -> list[str]:
    """Run every gate that reads only a games frame; return the failures.

    The frame-only subset of `validate_week`, kept because it is the signature
    the scaffold published and because it is the useful shape for a caller that
    already holds a frame - a test, a notebook, a fork's own harness. The four
    checks that read the private CFBD archive or a second run directory are not
    here; use `validate_week` for the full gate. Empty means publishable.
    """
    scored = _scored(games)
    checks = (
        completed_and_scored(games, season, "regular", week),
        week_game_count(scored, season, "regular", week),
        no_team_twice(scored, season, "regular", week),
        no_december_january_week_one(games, season),
    )
    return [f"{c.name}: {c.detail}" for c in checks if c.failed]
