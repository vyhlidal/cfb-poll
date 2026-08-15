"""Offseason facts from CFBD: returning production, the portal, and who is coaching.

THE PULL IS SMALL AND IT IS ARCHIVED BEFORE IT IS PARSED, exactly as
`ingest/cfbd.py` does it, and for the same two reasons: CFBD terms §3 bar
republishing raw bodies, so `archive/` is gitignored and these never leave this
disk; and a parse failure must be diagnosable from bytes already on disk rather
than by spending quota twice.

FOUR ENDPOINTS, ALL VERIFIED ON THE FREE TIER on 2026-08-15 against a key whose
`/info` reports `tierName: "Free"`, `monthlyLimit: 1000`:

  /player/returning?year=Y    one row per FBS team. Returning production FOR
                              season Y, i.e. what survived the offseason INTO Y.
  /player/portal?year=Y       one row per transfer in the cycle that ends before
                              season Y. `origin` and `destination` are school
                              names.
  /coaches?year=Y             one row per coach, each carrying a `seasons` list.
                              A school can appear more than once in a year
                              (interims, and coaches who left before working a
                              game), so `_august_coach` decides which of them
                              opened the season - from prior-season continuity,
                              never from the season's own games count. See ADR
                              0013: the games count was `projection-1.0.0`'s
                              temporal leak.
  /rankings?year=Y&week=1     the AP preseason top 25. BASELINE ONLY. It is the
                              thing this product is trying to beat and it is
                              banned from every projection design matrix by
                              `PROJECTION_BANNED` in validate/leakage.py.

COVERAGE, MEASURED RATHER THAN ASSUMED, and the honest version is in
`coverage()`. Team names match the games frame almost exactly - 133 of 134 FBS
teams for 2024 returning production, 134 of 134 for portal origins and coaches -
so this module matches on the school name and REPORTS every team it could not
match instead of silently dropping it. The one 2024 miss is Kennesaw State, whose
first FBS season was 2024 and which therefore has no prior FBS production to
return. That is a correct absence, not a gap, and `coverage` says which kind each
miss is by checking whether the team played FBS the season before.

THE PORTAL IS THE WEAK DATA AND SAYING SO IS PART OF SHIPPING IT.
`origin` is populated on every row we have ever pulled. `destination` is NOT:
2,654 of 3,378 rows for 2024 (78.6%) and 3,467 of 4,441 for 2026 (78.1%). A null
destination is a player who entered the portal and had not landed anywhere when
CFBD last wrote the row - which means PORTAL_IN IS SYSTEMATICALLY UNDERCOUNTED,
by an amount that differs year to year, while PORTAL_OUT is complete. Every
consumer of `portal_net` is inheriting that bias and `portal_out` is the half a
reader should trust. `stars` is populated on 2,996 of 3,378 rows and `rating` on
1,852; neither is used, because a recruiting rating is the exact reputation
signal this project exists to avoid and using it in the projection - where it
would be legal - would make the poll's refusal look like a technicality.

DETERMINISM. Every frame this module returns is sorted on `team` before it is
handed back, and no dict iteration order reaches a number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from cfbpoll.ingest import cfbd

__all__ = [
    "AP_POLL_NAME",
    "COACH_OF_RECORD_SOURCES",
    "PULL_CALL_BUDGET",
    "RETURNING_COLUMNS",
    "ap_preseason",
    "august_head_coaches",
    "coaching",
    "coverage",
    "portal",
    "pull",
    "returning_production",
    "table",
]

#: CFBD's name for the poll we compare against. `/rankings?week=1` also serves
#: the Coaches, FCS and Division II/III polls, and picking by exact name rather
#: than by position is what keeps a reordering upstream from silently swapping
#: our baseline for somebody else's.
AP_POLL_NAME = "AP Top 25"

#: What one `pull` of one season costs. Guard against drift, same discipline as
#: `cfbd.WEEKLY_CALL_BUDGET`.
PULL_CALL_BUDGET = 4

#: The returning-production columns this module carries, and the ONE it refuses.
#:
#: `usage` and its three unit splits are shares of a team's own counting stats -
#: snaps, carries, targets - which are facts about who is on the field. CFBD also
#: serves `percentPPA`, and PPA is CFBD's own fitted model, whose "exact formulas,
#: fitted coefficients, training artifacts, and every implementation detail are
#: not part of the public documentation". It is carried here as
#: `returning_percent_ppa` so the choice is visible and the correlation between
#: the two is publishable, and `PROJECTION_BANNED` in validate/leakage.py makes
#: it MECHANICALLY unreachable by the recipe rather than merely unused.
RETURNING_COLUMNS: tuple[str, ...] = (
    "returning_usage",
    "returning_passing_usage",
    "returning_receiving_usage",
    "returning_rushing_usage",
    "returning_percent_ppa",
)


# --------------------------------------------------------------------------- the pull


def pull(
    seasons: list[int],
    archive_root: str | Path | None = None,
    *,
    min_remaining: int = cfbd.DEFAULT_MIN_REMAINING,
    include_rankings: bool = True,
    session: cfbd.Session | None = None,
) -> dict[str, Any]:
    """Archive the offseason bodies for each season. Four calls per season, plus one.

    Quota is checked FIRST and once, so the job fails before it half-completes -
    the same ordering `cfbd.pull_week` uses and for the same reason.

    Everything is `required=False`: a season whose portal file CFBD has not
    written yet must degrade to a missing term with a stated coverage number, not
    to a crash. The archive is the record of what was and was not there.
    """
    own = session is None
    sess = session or cfbd.Session(archive_root=Path(archive_root or cfbd.DEFAULT_ARCHIVE))
    spent_before = sess.calls
    try:
        if own:
            sess.check_quota(min_remaining)
        out: dict[str, Any] = {}
        for season in sorted({int(s) for s in seasons}):
            bucket = f"{season}/season"
            out[f"returning_{season}"] = sess.fetch(
                "/player/returning", {"year": season}, bucket=bucket, required=False
            )
            out[f"portal_{season}"] = sess.fetch(
                "/player/portal", {"year": season}, bucket=bucket, required=False
            )
            out[f"coaches_{season}"] = sess.fetch(
                "/coaches", {"year": season}, bucket=bucket, required=False
            )
            if include_rankings:
                out[f"rankings_{season}"] = sess.fetch(
                    "/rankings",
                    {"year": season, "week": 1, "seasonType": "regular"},
                    bucket=bucket,
                    required=False,
                )
        out["calls"] = sess.calls - spent_before
        out["log"] = sess.log
        return out
    finally:
        if own:
            sess.close()


# ------------------------------------------------------- reading the archive back
#
# EVERYTHING BELOW IS OFFLINE, by the same construction as `cfbd.archived_games`:
# no Session, no httpx, no quota. The recipe and the backtest run from the
# archive, so a projection is reproducible without a key on a machine that holds
# the archive, and is a stated DEGRADED run on one that does not.


def _body(endpoint: str, season: int, archive_root: Any, params: dict[str, Any]) -> Any:
    bodies = cfbd.archived_bodies(endpoint, f"{season}/season", archive_root, params=params)
    if not bodies:
        return None
    return json.loads(bodies[-1].read_text(encoding="utf-8"))


def returning_production(
    season: int, archive_root: str | Path | None = None
) -> pl.DataFrame:
    """Per-team returning production for `season`. Empty frame when unarchived.

    `usage` is the headline: the share of last season's offensive usage that is
    back on the roster. The three unit splits ride along because they are free
    and because a team that returns its receivers and none of its line is a
    different bet from one that returns the reverse - and because the recipe is
    published, a reader can check for themselves that v1 uses only the aggregate.

    THIS IS OFFENCE ONLY, AND THAT IS A HOLE. CFBD serves no defensive returning
    production of any kind, so the "returning production (offense/defense)" split
    the design asked for is HALF BUILT: the offensive half is measured and the
    defensive half does not exist in the data. Every artifact says so rather than
    letting a reader assume the term covers both sides of the ball.
    """
    payload = _body("/player/returning", season, archive_root, {"year": season})
    if not isinstance(payload, list) or not payload:
        schema = {"team": pl.String, **{c: pl.Float64 for c in RETURNING_COLUMNS}}
        return pl.DataFrame(schema=schema)
    rows = [
        {
            "team": str(r.get("team", "")),
            "returning_usage": _f(r.get("usage")),
            "returning_passing_usage": _f(r.get("passingUsage")),
            "returning_receiving_usage": _f(r.get("receivingUsage")),
            "returning_rushing_usage": _f(r.get("rushingUsage")),
            "returning_percent_ppa": _f(r.get("percentPPA")),
        }
        for r in payload
        if r.get("team")
    ]
    return pl.DataFrame(rows).unique(subset="team", keep="first").sort("team")


def portal(season: int, archive_root: str | Path | None = None) -> pl.DataFrame:
    """Per-team portal flow into `season`: bodies out, bodies in, and the net.

    COUNTS OF PLAYERS, deliberately unweighted. CFBD serves `stars` and `rating`
    on most rows and a star-weighted net would be a better predictor; it would
    also be a recruiting composite, which is the single input the poll's
    constraint 2 names first. The projection is allowed to use one and declines
    to, because "we could have and did not" is the only version of that sentence
    worth publishing. The columns are archived, so anyone may disagree in a fork.

    `portal_out` is complete. `portal_in` is NOT - see the module docstring - and
    `portal_in_coverage` carries the season's populated-destination rate on every
    row so the number never travels without the caveat attached to it.
    """
    payload = _body("/player/portal", season, archive_root, {"year": season})
    if not isinstance(payload, list) or not payload:
        return pl.DataFrame(
            schema={
                "team": pl.String,
                "portal_out": pl.Int32,
                "portal_in": pl.Int32,
                "portal_net": pl.Int32,
                "portal_in_coverage": pl.Float64,
            }
        )
    out: dict[str, int] = {}
    inn: dict[str, int] = {}
    landed = 0
    for row in payload:
        origin = row.get("origin")
        destination = row.get("destination")
        if origin:
            out[str(origin)] = out.get(str(origin), 0) + 1
        if destination:
            landed += 1
            inn[str(destination)] = inn.get(str(destination), 0) + 1
    coverage_rate = landed / len(payload) if payload else 0.0
    teams = sorted(set(out) | set(inn))
    return pl.DataFrame(
        {
            "team": teams,
            "portal_out": pl.Series([out.get(t, 0) for t in teams], dtype=pl.Int32),
            "portal_in": pl.Series([inn.get(t, 0) for t in teams], dtype=pl.Int32),
            "portal_net": pl.Series(
                [inn.get(t, 0) - out.get(t, 0) for t in teams], dtype=pl.Int32
            ),
            "portal_in_coverage": [coverage_rate] * len(teams),
        }
    ).sort("team")


def _coach_rows(payload: Any, season: int) -> dict[str, list[tuple[str, int]]]:
    """school -> [(coach name, games worked)] for `season`, sorted for determinism.

    The raw shape of CFBD's file, before any decision is taken about which of
    them was actually running the program. A school appears more than once
    whenever it changed coaches during the season, and it also appears more than
    once when a coach who never worked a game is carried on the roster: CFBD's
    2024 file has Buffalo with Maurice Linguist at **zero** games beside Pete
    Lembo's thirteen, because Linguist left in January and the row stayed.
    """
    if not isinstance(payload, list):
        return {}
    rows: dict[str, list[tuple[str, int]]] = {}
    for coach in payload:
        first = str(coach.get("firstName") or "").strip()
        last = str(coach.get("lastName") or "").strip()
        name = f"{first} {last}".strip()
        for row in coach.get("seasons") or []:
            if int(row.get("year", 0)) != int(season):
                continue
            school = str(row.get("school") or "")
            if not school or not name:
                continue
            rows.setdefault(school, []).append((name, int(row.get("games") or 0)))
    return {school: sorted(v) for school, v in sorted(rows.items())}


#: How `_august_coach` decided, per school. Published on the offseason frame,
#: because the three cases carry different amounts of confidence and a column
#: that hides which one applied is a column a reader has to trust rather than
#: check.
COACH_OF_RECORD_SOURCES: tuple[str, ...] = (
    "sole_coach_of_record",
    "prior_season_continuity",
    "inferred_from_games",
)


def _august_coach(
    rows: dict[str, list[tuple[str, int]]], prior_rows: dict[str, list[tuple[str, int]]]
) -> dict[str, tuple[str, str]]:
    """school -> (the head coach at the START of the season, how we know).

    THIS IS THE TEMPORAL FIX (ADR 0013). The version this replaced took the coach
    with the most games, from a `/coaches?year=Y` file pulled AFTER season Y had
    been played. A school that fires its head coach in October and whose interim
    then works more games than he did came out of that function as the interim,
    so `coach_change` read 1 for a firing that had not happened in August. Five
    schools were docked 2.33 points of projected Power that way in 2025, Penn
    State among them, and the leak FLATTERS the model, because coaches get fired
    for losing and a false "new coach" flag lands on teams about to underperform.

    The rule here uses only facts an August reader has:

      1. A coach with ZERO games did not open the season. He is dropped from the
         candidate pool whenever anybody at that school worked one, which is what
         separates Buffalo's phantom Linguist row from a real mid-season change.
         In a season nobody has played yet every row is zero, so the pool is
         every row and this step is a no-op - which is the correct behaviour for
         the file the live projection actually reads.
      2. One candidate means one head coach, and somebody coached game one.
      3. More than one candidate means the season had a mid-season change in it.
         The August coach is then the one who was already at that school the
         season before, and PRIOR-SEASON CONTINUITY IS THE ONLY THING THAT
         DECIDES IT. No within-season quantity is consulted.

    WHEN CONTINUITY FINDS NOBODY the school both hired in the offseason and
    changed again during the season, so `coach_change` is 1 whichever candidate
    was the August man and the leak cannot reach the number. The NAME still has
    to be filled in, it is taken from the games count as the least-bad guess, and
    it is stamped `inferred_from_games` so that "this string is a guess and the
    flag beside it is not" is visible rather than assumed.
    `tests/unit/test_projection_offseason.py` asserts the implication
    (`inferred_from_games` => `coach_change != 0`) instead of trusting it.
    """
    out: dict[str, tuple[str, str]] = {}
    for school, entries in rows.items():
        played = [entry for entry in entries if entry[1] >= 1]
        candidates = played or list(entries)
        if not candidates:
            continue
        if len(candidates) == 1:
            out[school] = (candidates[0][0], "sole_coach_of_record")
            continue
        prior_names = {name for name, _ in prior_rows.get(school, [])}
        continuing = [entry for entry in candidates if entry[0] in prior_names]
        if continuing:
            # Ties break on (games, name) so the answer never depends on file
            # order. More than one continuing head coach at one school is not a
            # thing that happens; the max is here so that it cannot crash if it
            # ever does.
            name = max(continuing, key=lambda entry: (entry[1], entry[0]))[0]
            out[school] = (name, "prior_season_continuity")
            continue
        name = max(candidates, key=lambda entry: (entry[1], entry[0]))[0]
        out[school] = (name, "inferred_from_games")
    return out


def august_head_coaches(
    season: int, archive_root: str | Path | None = None
) -> dict[str, tuple[str, str]]:
    """school -> (head coach at the start of `season`, how we know). Offline.

    Public because the temporal claim this module makes is worth being able to
    check from the outside: hand it a season and it answers with the man who
    opened it, and the second element says whether that answer came from there
    being only one candidate, from prior-season continuity, or from a games count
    that could not decide the flag anyway.
    """
    return _august_coach(
        _coach_rows(_body("/coaches", season, archive_root, {"year": season}), season),
        _coach_rows(
            _body("/coaches", season - 1, archive_root, {"year": season - 1}), season - 1
        ),
    )


def coaching(season: int, archive_root: str | Path | None = None) -> pl.DataFrame:
    """Who opens `season` as head coach, and whether that is a change from `season - 1`.

    `coach_change` is 1 when the head coach at the START of `season` differs by
    NAME from the head coach at the start of the season before, and 0 when it
    matches. Both sides come through `_august_coach`, so the question the column
    answers is "did this program replace its head coach over the offseason" and
    not "did anything happen to its head coach at any point in either year".
    A school with no prior-season row - a new FBS member - gets `coach_change`
    null rather than 1, because "we do not know" and "they fired someone" are
    different facts and the recipe treats the unknown as the league mean.

    KNOWABLE IN AUGUST, WHICH IS THE WHOLE POINT (ADR 0013). Everything about
    `season - 1` is settled by the August this column is read in, and nothing
    about `season` itself is consulted beyond the roster of names, which is why
    `validate/leakage.py`'s TEMPORAL guard admits `coach_change` and would refuse
    the version of this function that shipped in `projection-1.0.0`.

    THE ONE PLACE THE ARCHIVE CANNOT REACH, stated rather than papered over: the
    earliest archived coaches file is 2021, so `_august_coach` has no continuity
    anchor for 2021 itself and falls back to the games count for the three 2021
    schools that changed coach mid-season. Those are all on the PRIOR side of the
    2021 -> 2022 transition, i.e. in the past relative to the projection that
    reads them, so it is an accuracy limit and not a leak. It is published per
    team in `coach_of_record_source_prior`.

    WHAT THIS TERM IS NOT. It is a binary "is the head coach new", not coaching
    QUALITY and not coordinator movement. FPI uses coaching tenure as a
    reputation prior and this deliberately does not: no coach is credited or
    debited by name, and the fitted coefficient is one number that applies to
    every school that changed. Whether that is a good model of coaching change is
    exactly the kind of thing the grading loop exists to find out.
    """
    now = august_head_coaches(season, archive_root)
    before = august_head_coaches(season - 1, archive_root)
    teams = sorted(now)
    return pl.DataFrame(
        {
            "team": teams,
            "coach_name": [now[t][0] for t in teams],
            "coach_of_record_source": [now[t][1] for t in teams],
            "coach_name_prior": [before[t][0] if t in before else None for t in teams],
            "coach_of_record_source_prior": [
                before[t][1] if t in before else None for t in teams
            ],
            "coach_change": pl.Series(
                [None if t not in before else int(now[t][0] != before[t][0]) for t in teams],
                dtype=pl.Int32,
            ),
        }
    ).sort("team")


def ap_preseason(season: int, archive_root: str | Path | None = None) -> pl.DataFrame:
    """The AP preseason top 25 for `season`. A BASELINE. Never an input.

    Returned as (team, ap_rank, ap_points) for the 25 ranked teams and nothing
    else, because that is all the AP publishes: the honest comparison has to
    respect that a human preseason poll differentiates 25 teams and is silent
    about the other 109, and a baseline padded out to look like a full rating
    would be flattering it rather than measuring it.
    """
    payload = _body(
        "/rankings",
        season,
        archive_root,
        {"year": season, "week": 1, "seasonType": "regular"},
    )
    empty = pl.DataFrame(
        schema={"team": pl.String, "ap_rank": pl.Int32, "ap_points": pl.Float64}
    )
    if not isinstance(payload, list) or not payload:
        return empty
    for week in payload:
        for poll in week.get("polls") or []:
            if str(poll.get("poll")) != AP_POLL_NAME:
                continue
            ranks = poll.get("ranks") or []
            if not ranks:
                continue
            return (
                pl.DataFrame(
                    {
                        "team": [str(r.get("school")) for r in ranks],
                        "ap_rank": pl.Series(
                            [int(r.get("rank", 0)) for r in ranks], dtype=pl.Int32
                        ),
                        "ap_points": [_f(r.get("points")) for r in ranks],
                    }
                )
                .unique(subset="team", keep="first")
                .sort("ap_rank")
            )
    return empty


# ------------------------------------------------------------------- the joined view


def table(season: int, archive_root: str | Path | None = None) -> pl.DataFrame:
    """One row per team with every offseason column, outer-joined on the school name.

    Outer, not inner: a team missing from one file must survive with a null in
    that column so `coverage` can count it and the recipe can decide what to do
    about it, rather than vanishing from a ranking because a portal file was
    thin. Every downstream consumer sees the nulls and none of them may silently
    impute - `recipe.build_design` does the imputation, once, in public.
    """
    frames = [
        returning_production(season, archive_root),
        portal(season, archive_root),
        coaching(season, archive_root),
    ]
    joined = frames[0]
    for frame in frames[1:]:
        joined = joined.join(frame, on="team", how="full", coalesce=True)
    return joined.sort("team")


def coverage(
    season: int,
    teams: list[str],
    archive_root: str | Path | None = None,
    prior_teams: list[str] | None = None,
) -> dict[str, Any]:
    """What fraction of `teams` each offseason source actually covers, and who is missing.

    `prior_teams` is the FBS membership of the season before. A team missing from
    returning production that was NOT in FBS last season is a CORRECT absence -
    it has no prior FBS production to return - and separating those from real
    gaps is the difference between a coverage number a reader can act on and one
    that just looks bad. Kennesaw State in 2024 is the worked example.
    """
    wanted = sorted(set(teams))
    prior = set(prior_teams or [])
    report: dict[str, Any] = {"season": int(season), "n_teams": len(wanted)}
    sources = {
        "returning_production": returning_production(season, archive_root),
        "portal": portal(season, archive_root),
        "coaching": coaching(season, archive_root),
    }
    for name, frame in sources.items():
        have = set(frame["team"].to_list()) if frame.height else set()
        missing = sorted(set(wanted) - have)
        new_members = [t for t in missing if prior and t not in prior]
        report[name] = {
            "covered": len(set(wanted) & have),
            "rate": (len(set(wanted) & have) / len(wanted)) if wanted else 0.0,
            "missing": missing,
            "missing_but_new_to_fbs": new_members,
            "missing_unexplained": [t for t in missing if t not in new_members],
        }
    portal_frame = sources["portal"]
    report["portal_destination_coverage"] = (
        float(portal_frame["portal_in_coverage"][0]) if portal_frame.height else 0.0
    )
    ap = ap_preseason(season, archive_root)
    report["ap_preseason_available"] = bool(ap.height)
    report["ap_preseason_n"] = int(ap.height)
    return report


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
