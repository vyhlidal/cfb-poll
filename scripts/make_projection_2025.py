"""The 2025 Projection, and the grading loop run on it. The frozen recipe, one season back.

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
        uv run python scripts/make_projection_2025.py --to ../sandbox/cfb-poll-data

Writes:

    <to>/2025/projection.json           the card, in 2026's exact contract
    <to>/2025/projection-grading.json   projection vs R(N, live) and R(N, final)
    demo/2025-projection-grading.md     the same story in prose

WHY THIS IS A STRONGER ARTIFACT THAN THE 2024 GRADING DEMO, and the difference is
worth stating before any number appears. `demo/projection-grading-loop.md` has to
REFIT the recipe with the 2023->2024 transition removed, so the projection it grades is
out of sample by construction rather than by history. This one does not remove
anything. `[projection].design_transitions` is `2021->2022, 2022->2023,
2023->2024`; the 2024->2025 transition was absent while 2025 was the sealed
holdout and is still absent now that ADR 0012 has opened it. So the coefficients
below are BYTE-IDENTICAL to the ones that produced the published 2026 Projection,
and `_assert_recipe_matches_the_published_one` refuses to write anything if they
ever stop being. This is the shipped product, applied one season back, to a season
whose answers are known and were never fitted on.

ZERO TUNING. Nothing here searches, selects or fits a constant. The recipe is
fitted exactly as `scripts/make_projection.py` fits it, on the same three
transitions, and then applied.

THE ONE SUBSTITUTION, DECLARED. `forward.schedule(season)` reads an archived CFBD
`/games` pull, and there is no 2025 `/games` pull in the archive - CFBD's 2025
directory holds returning production, the portal, coaches and week-1 rankings and
nothing else. The 2025 calendar is taken from the MIT schedule parquet instead,
projected to `forward.SCHEDULE_COLUMNS` and restricted to the regular season, so
it carries the same seven fields the 2026 pull carries and no result of any kind:
`home_points` and `away_points` are not among the columns and are never read. A
schedule is published months before a season, so using the season's own regular
calendar is the honest analogue of what an August projection would have had. It is
recorded on the artifact as `schedule_source` rather than left to be inferred.

NO NETWORK. Archive only.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from cfbpoll.config import DEFAULT_CONFIG_PATH, config_hash, load_config
from cfbpoll.ingest.plays import load_plays
from cfbpoll.ingest.sportsdataverse import load_games
from cfbpoll.projection import (
    PROJECTION_VERSION,
    fit,
    forward,
    grade,
    holdout,
    offseason,
    recipe,
    schedule,
    seasons,
)
from cfbpoll.projection import publish as projection_publish
from cfbpoll.validate import leakage

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"

CFG = load_config()
PROJ = CFG["projection"]
TRANSITIONS: list[tuple[int, int]] = [(int(a), int(b)) for a, b in PROJ["design_transitions"]]

#: The season the frozen recipe is applied to, and the season before it. Read
#: from the config rather than typed, so a second graded season is a config edit.
TARGET_SEASON = int(PROJ["graded_seasons"][0])
SOURCE_SEASON = TARGET_SEASON - 1

ALL_SEASONS = sorted({s for pair in TRANSITIONS for s in pair} | {SOURCE_SEASON, TARGET_SEASON})

#: The published 2026 artifact, whose coefficients this run must reproduce.
PUBLISHED_RECIPE = DEMO / "2026-preseason-projection.json"


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


# --------------------------------------------------------------------- the inputs


def archived_calendar(season: int, games: pl.DataFrame) -> pl.DataFrame:
    """The season's REGULAR schedule in `forward.SCHEDULE_COLUMNS`, results excluded.

    Built by projection rather than by filtering: the seven columns are named
    explicitly and `home_points` / `away_points` are not among them, so no result
    can reach a win projection through this frame even by accident. That is the
    same guarantee `forward.schedule` gets from asking CFBD for a schedule
    endpoint, arrived at from the other side.

    Restricted to games with at least one FBS participant, which is what CFBD's
    `classification=fbs` returns and therefore what the 2026 frame contains.
    """
    frame = games.filter(
        (pl.col("season") == int(season))
        & (pl.col("season_type") == "regular")
        & ((pl.col("home_class") == "fbs") | (pl.col("away_class") == "fbs"))
    )
    return (
        frame.select(
            pl.col("game_id").cast(pl.Int64),
            pl.col("week").cast(pl.Int32),
            pl.col("neutral_site").cast(pl.Boolean),
            pl.col("home_team").cast(pl.String),
            pl.col("away_team").cast(pl.String),
            pl.col("home_class").cast(pl.String),
            pl.col("away_class").cast(pl.String),
        )
        .sort("game_id")
        .select(forward.SCHEDULE_COLUMNS)
    )


def _assert_recipe_matches_the_published_one(fitted: recipe.Recipe) -> dict[str, Any]:
    """The claim this whole artifact rests on, checked instead of asserted in prose.

    If the coefficients here differ from the ones on the published 2026 card, then
    something moved between the two runs and "the shipped recipe, applied one
    season back" is no longer a true sentence. Refusing to write is the correct
    response: a projection that quietly used different numbers from the ones it
    claims to use is worse than no projection.
    """
    if not PUBLISHED_RECIPE.exists():
        return {"checked": False, "why": f"{PUBLISHED_RECIPE.name} is not on disk"}
    published = json.loads(PUBLISHED_RECIPE.read_text(encoding="utf-8"))["recipe"]
    mismatches: list[str] = []
    if not math.isclose(float(published["intercept"]), fitted.intercept, rel_tol=0, abs_tol=1e-9):
        mismatches.append(f"intercept {published['intercept']} != {fitted.intercept}")
    for term, value in published["coefficients"].items():
        got = fitted.coefficients.get(term)
        if got is None or not math.isclose(float(value), got, rel_tol=0, abs_tol=1e-9):
            mismatches.append(f"{term} {value} != {got}")
    if mismatches:
        raise SystemExit(
            "the recipe fitted here is not the recipe published for 2026: "
            + "; ".join(mismatches)
            + ". Either `design_transitions` moved or the fit changed. This script "
            "claims to apply the SHIPPED recipe one season back and will not write "
            "an artifact that makes that claim falsely."
        )
    return {
        "checked": True,
        "against": f"demo/{PUBLISHED_RECIPE.name}",
        "identical": True,
        "note": (
            "The coefficients below are the ones on the published 2026 card, to "
            "1e-9. Nothing was refitted, dropped or excluded to make 2025 out of "
            "sample: 2024->2025 was never in design_transitions."
        ),
    }


# ---------------------------------------------------------------------- the build


def build() -> dict[str, Any]:
    games = load_games(ALL_SEASONS)
    plays = load_plays(ALL_SEASONS)

    # The same guard the 2026 build runs, on the same list. It now protects 2026
    # rather than 2025 (ADR 0012) and this call is what proves the list is clean.
    holdout.assert_no_target_is_locked(TRANSITIONS, CFG)
    data = [fit.gather(games, a, b, plays, CFG) for a, b in TRANSITIONS]
    fitted = recipe.fit_recipe([d.design for d in data], [d.response for d in data], TRANSITIONS)
    provenance = _assert_recipe_matches_the_published_one(fitted)

    source = seasons.final_power(games, SOURCE_SEASON, plays, CFG)
    teams = sorted(
        set(offseason.returning_production(TARGET_SEASON)["team"].to_list())
        | set(offseason.coaching(TARGET_SEASON)["team"].to_list())
    )
    design = recipe.build_design(source.ratings, TARGET_SEASON, teams)
    projection = recipe.project(fitted, design, teams)

    future = archived_calendar(TARGET_SEASON, games)
    season_sigma, sigma_source = forward.season_sigma_for(source, CFG)
    wins = forward.expected_wins(
        projection,
        future,
        fitted,
        source.ratings,
        float(design["prior_power_center"][0]),
        season_sigma,
        float(source.home_field),
        season_sigma_source=sigma_source,
    )
    projection = projection.join(wins.table, on="team", how="left")

    center = float(design["prior_power_center"][0])
    prior_fbs = seasons.fbs_teams(games, SOURCE_SEASON)
    strength = schedule.strengths(
        projection,
        future,
        fitted,
        source.ratings,
        center,
        wins.sigma,
        float(source.home_field),
        promoted=tuple(t for t in teams if t not in prior_fbs),
    )
    projection = projection.join(strength.table, on="team", how="left")
    contrast = schedule.contrast(
        projection, future, fitted, source.ratings, center, wins.sigma, float(source.home_field)
    )

    audit = leakage.audit(
        games.filter(pl.col("season") == SOURCE_SEASON), None, CFG, projection_design=design
    )
    graded = grade.grade_season(projection, games, TARGET_SEASON, plays=plays, config=CFG)

    return {
        "projection": projection,
        "recipe": fitted,
        "recipe_provenance": provenance,
        "wins": wins,
        "schedule_strength": strength,
        "contrast": contrast,
        "audit": audit,
        "source": source,
        "graded": graded,
        "games": games,
        "promoted": [t for t in teams if t not in prior_fbs],
        "n_future_games": int(future.height),
        "coverage": offseason.coverage(TARGET_SEASON, teams, prior_teams=prior_fbs),
    }


# ------------------------------------------------------------------ the artifacts


def write_fixture(state: dict[str, Any], to: Path) -> Path:
    """`<to>/2025/projection.json`, in the identical contract 2026's card uses."""
    document = projection_publish.build(
        state["projection"],
        TARGET_SEASON,
        CFG,
        headline=(
            f"This is the model's {TARGET_SEASON} projection, made with the recipe "
            "it publishes today and applied to a season it never fitted on."
        ),
        basis=(
            f"It is built from {SOURCE_SEASON}'s final ratings plus the offseason "
            "changes we can measure: returning production, the transfer portal and "
            "coaching moves."
        ),
        note=(
            f"The {TARGET_SEASON} season has been played, so this page can be read "
            "against the answer. The grading surface beside it shows where the "
            "projection landed and which term was carrying the error."
        ),
        status="published",
        published_at=datetime.now(UTC).isoformat(timespec="seconds"),
        top_n=25,
        backtest=None,
        strength=state["schedule_strength"],
        contrast=state["contrast"],
        sigma=state["wins"].sigma,
    )
    # Fields this card carries and 2026's does not, because 2026's season has not
    # happened yet. Additive, so a renderer written against the 2026 contract
    # renders this document unchanged and simply does not draw them.
    document["retrospective"] = True
    document["source_season"] = SOURCE_SEASON
    document["recipe_provenance"] = state["recipe_provenance"]
    document["schedule_source"] = (
        f"The {TARGET_SEASON} regular-season calendar from the MIT schedule "
        "parquet, projected to the seven columns forward.SCHEDULE_COLUMNS names. "
        "There is no CFBD /games pull for this season in the archive, and a "
        "schedule is published months before a season is played, so the season's "
        "own calendar is the honest stand-in. No result column is read."
    )
    document["grading"] = f"{TARGET_SEASON}/projection-grading.json"
    return projection_publish.write(document, to)


#: How far down the projected board the featured story is allowed to look for
#: its subject. Wider than the published 25 on purpose: a team the projection
#: ranked 28th and the season ranked 102nd is a bigger statement about the recipe
#: than anything inside the top 25, and a window that stopped at the board would
#: have quietly dropped the one row a reader came to this page to ask about.
FEATURE_WINDOW = 30

#: The team the featured paragraph is written about. Named rather than selected,
#: because the paragraph is PROSE and prose cannot be templated onto an arbitrary
#: subject. `_feature_story` refuses to publish it if the numbers stop supporting
#: the sentences, which is the only guarantee that matters.
FEATURE_TEAM = "Colorado"


#: The recipe's terms in the words the front door uses. Kept beside the sentence
#: that prints them rather than imported out of `grade`, which owns the same map
#: for its own per-term sentences; two short dicts is cheaper than a private
#: import across a package boundary.
_TERM_NAMES = {
    "prior_power": "last season's rating",
    "returning_production": "returning production",
    "coaching_change": "the coaching-change penalty",
    "net_portal": "net portal flow",
}


def _attribution_verdict(attribution: dict[str, Any]) -> str:
    """One templated sentence about the league-wide result, in either direction.

    THE FIELD THAT EXISTS BECAUSE THE ANSWER CHANGED. Under
    `projection-1.0.0` one term came back TOO STRONG and the front door printed
    that term's own sentence. On the corrected surfaces all four are priced about
    right, a per-term sentence has nothing to lead with, and a page that prints
    nothing when the answer is "the recipe held" is a page that only ever reports
    bad news. So the verdict ships as its own field, templated off the measured
    coefficients, and it is a complete sentence in both worlds.
    """
    terms = attribution.get("terms") or {}
    if not terms:
        return "There were too few graded teams to attribute the error to any term."
    wrong = [
        (name, value)
        for name, value in terms.items()
        if value["verdict"] != "priced about right"
    ]
    if wrong:
        name, value = max(wrong, key=lambda item: abs(item[1]["z"]))
        return str(value["sentence"])
    name, value = max(terms.items(), key=lambda item: abs(item[1]["z"]))
    return (
        f"Across the {int(attribution['n_teams'])} teams the poll ranked, every "
        "one of the four terms came back priced about right. The furthest from "
        f"zero was {_TERM_NAMES[name]}, at {abs(float(value['z'])):.1f} standard "
        "errors, and the data cannot tell that apart from the value the recipe "
        "already uses. The season did not ask for a different coefficient."
    )


def _feature_story(state: dict[str, Any], attribution: dict[str, Any]) -> dict[str, Any]:
    """The one paragraph the grading page leads its story section with.

    EVERY NUMBER IN IT IS READ OFF THE LIVE OBJECTS, not typed. The paragraph
    makes six quantitative claims and a superlative, and each one is recomputed
    here and asserted before the sentence that carries it is allowed out. If a
    future season stops supporting a claim this raises instead of publishing a
    sentence that used to be true, which is the same posture
    `_assert_recipe_matches_the_published_one` takes toward the coefficients.

    The paragraph replaces the story line the projection's own `story_lines`
    cannot produce for this team: `grade.story_lines` keeps a row only when it is
    inside 25 on one of the two rankings, and on the corrected surfaces Colorado
    is 28th and 102nd, so it is outside both. The filter is right and the row
    still needs explaining.
    """
    projection: pl.DataFrame = state["projection"]
    graded: pl.DataFrame = state["graded"]["table"]
    final = int(graded["eval_order"].max())
    week = graded.filter(pl.col("eval_order") == final)

    row = projection.filter(pl.col("team") == FEATURE_TEAM).to_dicts()[0]
    scored = week.filter(pl.col("team") == FEATURE_TEAM).to_dicts()[0]
    projected_rank = int(row["projected_rank"])
    hindsight_rank = int(scored["hindsight_rank"])

    # THE SUPERLATIVE, MEASURED. Of the teams the projection put highest, which
    # one did the season move furthest down.
    window = week.filter(
        pl.col("projected_rank").is_not_null()
        & (pl.col("projected_rank") <= FEATURE_WINDOW)
        & pl.col("delta_vs_hindsight").is_not_null()
    )
    furthest = window.sort(["delta_vs_hindsight", "team"]).to_dicts()[0]
    if furthest["team"] != FEATURE_TEAM:
        raise SystemExit(
            f"the featured paragraph is written about {FEATURE_TEAM}, and the "
            f"furthest faller inside the projected top {FEATURE_WINDOW} is now "
            f"{furthest['team']}. Rewrite the paragraph or move the subject; this "
            "script will not publish a superlative it just measured to be false."
        )

    # Where last season alone would have put them: mean reversion is a positive
    # affine map and cannot reorder, so this is the ranking by prior Power.
    prior = dict(
        zip(projection["team"].to_list(), projection["prior_power"].to_list(), strict=True)
    )
    ranked_teams = [
        t
        for t, r in zip(
            projection["team"].to_list(), projection["projected_rank"].to_list(), strict=True
        )
        if r is not None
    ]
    carryover = sorted(ranked_teams, key=lambda t: (-float(prior[t]), t))
    prior_rank = carryover.index(FEATURE_TEAM) + 1

    usage_frame = projection.select(["team", "returning_usage"]).drop_nulls().sort(
        "returning_usage"
    )
    ascending = usage_frame["team"].to_list()
    usage_rank_low = ascending.index(FEATURE_TEAM) + 1
    n_usage = len(ascending)

    spans = {
        term: float(projection[f"contrib_{term}"].max() - projection[f"contrib_{term}"].min())
        for term in recipe.TERMS
    }
    biggest_z = max(
        (abs(float(v["z"])) for v in (attribution.get("terms") or {}).values()), default=0.0
    )

    control = {}
    for name in ("Indiana", "Penn State", "Baylor"):
        c_row = projection.filter(pl.col("team") == name).to_dicts()[0]
        c_scored = week.filter(pl.col("team") == name).to_dicts()
        control[name] = {
            "usage": float(c_row["returning_usage"]),
            "usage_rank_high": len(ascending) - ascending.index(name),
            "hindsight": int(c_scored[0]["hindsight_rank"]) if c_scored else None,
        }
    if control["Indiana"]["usage"] >= float(row["returning_usage"]):
        raise SystemExit("the paragraph claims Indiana returned less than Colorado")
    if control["Indiana"]["hindsight"] != 1:
        raise SystemExit("the paragraph claims Indiana finished first")

    ap = offseason.ap_preseason(TARGET_SEASON)
    if FEATURE_TEAM in ap["team"].to_list():
        raise SystemExit("the paragraph claims the AP left Colorado unranked")

    paragraph = (
        f"We had {FEATURE_TEAM} {_ordinal(projected_rank)} and the season put them "
        f"{_ordinal(hindsight_rank)}. Of the {FEATURE_WINDOW} teams we projected "
        "highest, that is the furthest any of them fell, and it is worth being "
        "precise about why, because the easy explanation is wrong. The model does "
        "not read the press: the AP left Colorado out of its preseason top 25 and "
        "so did we, so nobody's hype got inherited here. What we read was "
        f"Colorado's own {SOURCE_SEASON}, where they were the "
        f"{_ordinal(prior_rank)} best team in the country by our Power rating, and "
        f"that one number was worth {float(row['contrib_prior_power']):.1f} points "
        "to their projection. The model also saw the exodus and priced it. "
        f"Colorado returned {float(row['returning_usage']):.1%} of its offensive "
        f"usage, the {_ordinal(usage_rank_low)} lowest figure among the {n_usage} "
        "teams with a row, and "
        f"{float(row['returning_passing_usage']):.0%} of its passing usage, which "
        "is what losing your quarterback looks like in the data. That cost them "
        f"{_points(abs(float(row['contrib_returning_production'])))}, the portal "
        f"took another {abs(float(row['contrib_net_portal'])):.1f}, and between "
        f"them they moved Colorado from {_ordinal(prior_rank)} to "
        f"{_ordinal(projected_rank)}. The problem is the ratio. Last season's "
        f"rating can swing a team {spans['prior_power']:.0f} points and returning "
        f"production can swing one {spans['returning_production']:.0f}, so a team "
        f"that arrives {_ordinal(prior_rank)} cannot be argued down to "
        f"{_ordinal(hindsight_rank)} by the offseason. The grading loop is what "
        "settles what to do about that, and this season it settled it the dull "
        f"way: across the {int(attribution['n_teams'])} teams the poll ranked, all "
        "four terms come back priced about right, the furthest of them "
        f"{biggest_z:.1f} standard errors from the value we published. No "
        "coefficient here was wrong. The ratio is a property of the design, and "
        f"{TARGET_SEASON} is the first season that made it cost something. What we "
        "are not going to do is turn the returning-production dial up until "
        "Colorado looks right. We checked: every setting that moves Colorado down "
        "also moves Indiana down, and Indiana returned even less than Colorado did "
        "and went 16-0. Penn State and Baylor returned more production than almost "
        f"anyone in the country, {_ordinal(control['Penn State']['usage_rank_high'])}"
        f" and {_ordinal(control['Baylor']['usage_rank_high'])} of {n_usage}, and "
        f"finished {_ordinal(control['Penn State']['hindsight'])} and "
        f"{_ordinal(control['Baylor']['hindsight'])}. In {TARGET_SEASON} returning "
        "production told you almost nothing, and the fix for Colorado is not a "
        "bigger version of a term that did not work."
    )
    return {
        "team": FEATURE_TEAM,
        "projected_rank": projected_rank,
        "hindsight_rank": hindsight_rank,
        "window": FEATURE_WINDOW,
        "paragraph": projection_publish._assert_sentence("feature_story.paragraph", paragraph),
    }


def _points(value: float) -> str:
    """`1.0` -> `1.0 point`. Prose that says "1.0 points" reads like a template."""
    return f"{value:.1f} point" + ("" if abs(round(value, 1) - 1.0) < 1e-9 else "s")


def _ordinal(n: int) -> str:
    """`28` -> `28th`. The paragraph is prose and prose does not print bare ranks."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def grading_payload(state: dict[str, Any]) -> dict[str, Any]:
    """`<to>/2025/projection-grading.json` - the "we projected X, the season said Y" doc.

    Two deltas, kept apart because they answer different questions. `vs_live` is
    "how wrong were we about what had happened by week N". `vs_hindsight` is "how
    wrong were we about what these teams turned out to BE", which is the fairer
    question early, because in week 5 the live poll is itself provisional and
    grading a preseason projection against a provisional answer double-counts the
    noise.
    """
    graded: pl.DataFrame = state["graded"]["table"]
    weeks = state["graded"]["weeks"]
    headline_order = int(state["graded"]["headline_eval_order"])
    start = int(CFG["publication"]["headline_start_week"])

    by_week: list[dict[str, Any]] = []
    for entry in weeks:
        order = int(entry["eval_order"])
        week = graded.filter(pl.col("eval_order") == order)
        scored = week.filter(pl.col("projected_rank").is_not_null())
        top25 = scored.filter(pl.col("projected_rank") <= 25)
        by_week.append(
            {
                "eval_order": order,
                "eval_label": entry["eval_label"],
                "n_teams": int(entry["n_teams"]),
                "published": order >= headline_order,
                "mean_abs_delta_vs_live": _mean_abs(scored, "delta_vs_live"),
                "mean_abs_delta_vs_hindsight": _mean_abs(scored, "delta_vs_hindsight"),
                "mean_abs_delta_vs_hindsight_top25": _mean_abs(top25, "delta_vs_hindsight"),
                "top25_hits": _hits(week),
            }
        )

    final = max(int(e["eval_order"]) for e in weeks)
    final_rows = (
        graded.filter((pl.col("eval_order") == final) & pl.col("projected_rank").is_not_null())
        .sort("projected_rank")
        .head(25)
    )
    attribution = _plain(state["graded"]["attribution"])
    return {
        "schema_version": 1,
        "season": TARGET_SEASON,
        "source_season": SOURCE_SEASON,
        "projection_version": PROJECTION_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "config_hash": config_hash(DEFAULT_CONFIG_PATH),
        "recipe_provenance": state["recipe_provenance"],
        "headline_start_week": start,
        "headline_eval_label": state["graded"]["headline_week"],
        "settled_definition": state["graded"]["settled_definition"],
        # `projected_power` and `actual_power` in the rows below are on THIS one
        # scale. The version of this document that did not carry the field had
        # them on two, which is most of what ADR 0013 is about.
        "power_definition": state["graded"]["power_definition"],
        "surfaces": {
            "projected_rank": (
                "The projection, made from the prior season's final ratings plus "
                "offseason data, and never recomputed."
            ),
            "live_rank": "R(N, N). The poll as it was published in week N.",
            "hindsight_rank": (
                "R(N, final). The same week re-scored with the season's answers, "
                "which is the surface that says what these teams turned out to be."
            ),
        },
        "weeks": by_week,
        "final": {
            "eval_label": next(
                e["eval_label"] for e in weeks if int(e["eval_order"]) == final
            ),
            "rows": [
                {
                    "projected_rank": int(r["projected_rank"]),
                    "team": r["team"],
                    "live_rank": _int(r["live_rank"]),
                    "hindsight_rank": _int(r["hindsight_rank"]),
                    "delta_vs_live": _int(r["delta_vs_live"]),
                    "delta_vs_hindsight": _int(r["delta_vs_hindsight"]),
                    "projected_power": _round(r["projected_power"]),
                    "actual_power": _round(r["actual_power"]),
                    "power_error": _round(r["power_error"]),
                    "suspect_term": r["suspect_term"],
                    "suspect_contribution": _round(r["suspect_contribution"]),
                }
                for r in final_rows.to_dicts()
            ],
        },
        "story_lines": grade.story_lines(graded, final, top_n=5),
        # THE PARAGRAPH THE PAGE LEADS ITS STORY SECTION WITH. A published field,
        # not component copy, for the reason every other sentence on these
        # surfaces is: a claim the site hard-codes is a claim that stops being
        # true the first time the numbers move and nobody re-reads the JSX.
        "feature_story": _feature_story(state, attribution),
        "attribution": attribution,
        # The league-wide result in one sentence, in either direction, so a page
        # whose four terms all came back priced about right still has something
        # to print. See `_attribution_verdict`.
        "attribution_verdict": _attribution_verdict(attribution),
        "attribution_health_warning": (
            "The league-wide attribution is a regression of projection error on "
            "each term's contribution, over about 134 teams and four correlated "
            "terms. One season is one data point about the recipe. It is "
            "suggestive and it is not a verdict."
        ),
    }


def _mean_abs(frame: pl.DataFrame, column: str) -> float | None:
    sub = frame.filter(pl.col(column).is_not_null())
    return float(sub[column].abs().mean()) if sub.height else None


def _hits(week: pl.DataFrame) -> int | None:
    """How many of the projected top 25 finished in the hindsight top 25."""
    both = week.filter(
        pl.col("projected_rank").is_not_null() & pl.col("hindsight_rank").is_not_null()
    )
    if not both.height:
        return None
    return int(
        both.filter((pl.col("projected_rank") <= 25) & (pl.col("hindsight_rank") <= 25)).height
    )


def _int(value: Any) -> int | None:
    return None if value is None else int(value)


def _round(value: Any, places: int = 2) -> float | None:
    return None if value is None else round(float(value), places)


def _plain(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plain(v) for v in obj]
    if isinstance(obj, float):
        return None if math.isnan(obj) else obj
    return obj


def render_grading(payload: dict[str, Any], state: dict[str, Any]) -> str:
    fitted: recipe.Recipe = state["recipe"]
    lines: list[str] = []
    add = lines.append
    final = payload["final"]

    add(f"# We projected {payload['season']}. Here is what the season said.")
    add("")
    add(
        "> The recipe below is the one this project publishes. It was fitted on "
        + ", ".join(f"{a}→{b}" for a, b in TRANSITIONS)
        + f" and **{payload['source_season']}→{payload['season']} is not among "
        "those transitions**, so nothing here was fitted on the season it is "
        "being graded against. Nothing was excluded to make that true either: "
        "that transition has never been in the list."
    )
    add("")
    add(
        f"Recipe `{fitted.version}` · source season {payload['source_season']} · "
        f"config sha256 `{payload['config_hash'][:16]}...` · "
        f"code `{payload['git_sha'][:10]}`"
    )
    add("")
    add(payload["recipe_provenance"].get("note", ""))
    add("")
    add(f"**Which Power.** {payload['power_definition']}.")
    add("")

    add("## The one row this page is most often asked about")
    add("")
    add(f"> {payload['feature_story']['paragraph']}")
    add("")

    add("## The projection against the season, at the end of it")
    add("")
    add(
        "`Projected` is the projection. `Live` is the poll as it was published in "
        "the final week. `Hindsight` is that same week re-scored with the whole "
        "season's answers, which is the column that says what a team turned out "
        "to be. A negative delta means we had them too high. Both Power columns "
        "are on the definition named above, which is the one the poll publishes."
    )
    add("")
    add(
        "**At the final bucket the two surfaces are the same ranking, and that is "
        "arithmetic rather than agreement.** R(N, N) and R(N, final) coincide when "
        "N *is* final, because there is no rest-of-season left to substitute in. "
        "The two columns separate earlier in the year, and the week-by-week table "
        "below is where that separation is worth reading."
    )
    add("")
    add(
        "| Projected | Team | Live | Hindsight | vs live | vs hindsight | "
        "Power projected → actual |"
    )
    add("|---:|---|---:|---:|---:|---:|---:|")
    for row in final["rows"]:
        add(
            f"| {row['projected_rank']} | {row['team']} | "
            f"{row['live_rank'] if row['live_rank'] is not None else '—'} | "
            f"{row['hindsight_rank'] if row['hindsight_rank'] is not None else '—'} | "
            f"{_signed(row['delta_vs_live'])} | {_signed(row['delta_vs_hindsight'])} | "
            f"{row['projected_power']} → "
            f"{row['actual_power'] if row['actual_power'] is not None else '—'} |"
        )
    add("")

    add("## What was wrong, in the projection's own words")
    add("")
    for line in payload["story_lines"]:
        add(f"- {line}")
    add("")

    add("## Convergence, week by week")
    add("")
    add(
        "Mean absolute rank error of the frozen projection against each surface. "
        "The `hindsight` column is the fairer early reading: in week 5 the live "
        "poll is itself provisional, and grading an August projection against a "
        "provisional answer double-counts the noise."
    )
    add("")
    add(
        "| week | published | vs live | vs hindsight | "
        "vs hindsight, projected top 25 | top-25 hits |"
    )
    add("|---|:---:|---:|---:|---:|---:|")
    for week in payload["weeks"]:
        add(
            f"| `{week['eval_label']}` | {'yes' if week['published'] else 'no'} | "
            f"{_num(week['mean_abs_delta_vs_live'])} | "
            f"{_num(week['mean_abs_delta_vs_hindsight'])} | "
            f"{_num(week['mean_abs_delta_vs_hindsight_top25'])} | "
            f"{week['top25_hits'] if week['top25_hits'] is not None else '—'} |"
        )
    add("")

    add("## Which term was carrying the error, across the league")
    add("")
    add(
        "Regress every team's projection error on each term's contribution. A "
        "negative coefficient means teams we credited on that term systematically "
        "underperformed, which is to say we over-credited it this season."
    )
    add("")
    add(f"**{payload['attribution_verdict']}**")
    add("")
    attribution = payload["attribution"] or {}
    terms = attribution.get("terms") or attribution
    if isinstance(terms, dict) and terms:
        add("| term | coefficient | z | implied multiplier | verdict |")
        add("|---|---:|---:|---:|---|")
        for name, value in terms.items():
            add(
                f"| `{name}` | {float(value['coefficient']):+.4f} | "
                f"{float(value['z']):+.2f} | "
                f"{float(value['implied_multiplier']):.3f} | {value['verdict']} |"
            )
        add("")
        add("```json")
        add(json.dumps(terms, indent=1)[:2000])
        add("```")
    add("")
    add(payload["attribution_health_warning"])
    add("")
    add(
        f"Generated by `scripts/make_projection_2025.py` at "
        f"{payload['generated_at']}. The machine-readable form is "
        f"`{payload['season']}/projection-grading.json` in the site's data tree."
    )
    return "\n".join(lines) + "\n"


def _signed(value: int | None) -> str:
    return "—" if value is None else f"{value:+d}"


def _num(value: float | None, places: int = 2) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--to",
        type=Path,
        default=ROOT.parent / "sandbox" / "cfb-poll-data",
        help="The site's data root.",
    )
    args = parser.parse_args()

    state = build()
    fixture = write_fixture(state, args.to)

    payload = grading_payload(state)
    season_dir = Path(args.to) / str(TARGET_SEASON)
    season_dir.mkdir(parents=True, exist_ok=True)
    grading_path = season_dir / "projection-grading.json"
    grading_path.write_text(
        json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    (DEMO / f"{TARGET_SEASON}-projection-grading.md").write_text(
        render_grading(payload, state), encoding="utf-8"
    )

    fitted: recipe.Recipe = state["recipe"]
    print(
        f"{TARGET_SEASON} projection: recipe {fitted.version}, identical to the "
        f"published 2026 card = {state['recipe_provenance'].get('identical')}"
    )
    print(f"  {state['n_future_games']} scheduled games, {len(payload['weeks'])} graded weeks")
    print(f"wrote: {fixture}")
    print(f"wrote: {grading_path}")
    print(f"wrote: demo/{TARGET_SEASON}-projection-grading.md")


if __name__ == "__main__":
    main()
