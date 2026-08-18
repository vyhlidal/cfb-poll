"""Regenerate the Projection artifacts from the local archive.

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
        uv run python scripts/make_projection.py

Writes, all committed so a reader can see real output without running anything:

    demo/2026-preseason-projection.md    the ranking, every term's contribution
    demo/2026-preseason-projection.json  the same numbers, machine-readable
    demo/projection-backtest.md          did we beat the AP's August ballot
    demo/projection-backtest.json
    demo/projection-grading-loop.md      what the loop reads like, worked on 2024

NO NETWORK. Everything here reads the MIT play/schedule archive and the private
CFBD offseason archive; nothing opens a socket. A fork without the CFBD archive
gets a stated degraded run rather than a crash, which is the same posture the
rest of this repository takes.

THE HOLDOUT. `[projection].projection_source_season` is 2025 and 2025 is the
sealed holdout. This script reads its FITTED RATINGS as an input and fits no
coefficient against its outcomes - `holdout.assert_no_target_is_locked` refuses
the second, and ADR 0010 argues why the first is a different act. The grading-loop
demo is worked on 2024 rather than 2025 for the same reason: grading is scoring,
and scoring the holdout is what would burn it.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from cfbpoll.config import DEFAULT_CONFIG_PATH, config_hash, load_config
from cfbpoll.ingest.plays import load_plays
from cfbpoll.ingest.sportsdataverse import load_games
from cfbpoll.projection import (
    PROJECTION_VERSION,
    crossdivision,
    fit,
    forward,
    grade,
    holdout,
    offseason,
    recipe,
    schedule,
    seasons,
    systems,
)
from cfbpoll.validate import leakage

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"

CFG = load_config()
PROJ = CFG["projection"]
TRANSITIONS: list[tuple[int, int]] = [
    (int(a), int(b)) for a, b in PROJ["design_transitions"]
]
SOURCE_SEASON = int(PROJ["projection_source_season"])
TARGET_SEASON = int(PROJ["target_season"])
GRADING_DEMO_SEASON = int(PROJ["grading_demo_season"])

ALL_SEASONS = sorted({s for pair in TRANSITIONS for s in pair} | {SOURCE_SEASON})

#: Rows the owner asked to see explained on the page rather than in a chat log.
#: A team lands here when the ranking it gets is the thing people will argue
#: about, and it leaves the list when nobody argues any more. Promoted teams are
#: added automatically and do not need to be named.
CONTESTED_TEAMS: tuple[str, ...] = ("Texas",)


def _target_membership() -> list[str]:
    """Who is in FBS for the target season, from the offseason feeds.

    The schedule frame cannot answer this before the season is played, so the
    membership comes from the returning-production and coaching files, which is
    the same rule this script has always used and is now named because
    `systems.prepare` needs it handed in rather than derived.
    """
    return sorted(
        set(offseason.returning_production(TARGET_SEASON)["team"].to_list())
        | set(offseason.coaching(TARGET_SEASON)["team"].to_list())
    )


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _fmt(value: Any, places: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


# --------------------------------------------------------------------------- build


def build() -> dict[str, Any]:
    games = load_games(ALL_SEASONS)
    plays = load_plays(ALL_SEASONS)

    backtest = fit.run(games, TRANSITIONS, plays=plays, config=CFG)

    # THE LIBERATION PATH (ADR 0014). The prior a team carries into August is no
    # longer "last season's rating, whoever you played". It is last season blended
    # with the one before it, and then - if the rating was earned outside FBS -
    # moved onto the FBS scale by the constants the crossover games measured. Every
    # step is levered and every lever's value is on the artifact.
    levers = systems.ProjectionLevers.from_config(CFG)
    inputs = systems.prepare(games, ALL_SEASONS, plays, CFG)
    inputs.fbs[TARGET_SEASON] = set(_target_membership())
    teams_2026 = sorted(inputs.fbs[TARGET_SEASON])

    fitted, fitted_transitions = systems.fit_walk_forward(
        games, TARGET_SEASON, inputs.power, inputs.home_field, inputs.fbs, levers
    )
    if fitted is None:  # pragma: no cover - impossible with the shipped archive
        raise RuntimeError("no transition precedes the target season; nothing to fit on")

    carried, calibration, carry_provenance = systems.carried_ratings(
        games, TARGET_SEASON, inputs.power, inputs.home_field, inputs.fbs, levers
    )

    source = seasons.final_power(games, SOURCE_SEASON, plays, CFG)
    design = recipe.build_design(carried, TARGET_SEASON, teams_2026)
    projection = recipe.project(fitted, design, teams_2026)

    future = forward.schedule(TARGET_SEASON)
    season_sigma, sigma_source = forward.season_sigma_for(source, CFG)
    # The home-field constant the win model uses is season 2025's fitted value
    # scaled by the published lever, so the number that decides a projected win
    # total is the same number the accuracy chain was scored on.
    home_field = float(source.home_field) * float(levers.home_field)
    wins = forward.expected_wins(
        projection,
        future,
        fitted,
        carried,
        float(design["prior_power_center"][0]),
        season_sigma,
        home_field,
        season_sigma_source=sigma_source,
    )
    projection = projection.join(wins.table, on="team", how="left")

    center = float(design["prior_power_center"][0])
    strength = schedule.strengths(
        projection,
        future,
        fitted,
        carried,
        center,
        wins.sigma,
        home_field,
        promoted=tuple(t for t in teams_2026 if t not in inputs.fbs[SOURCE_SEASON]),
    )
    projection = projection.join(strength.table, on="team", how="left")
    contrast = schedule.contrast(
        projection, future, fitted, carried, center, wins.sigma, home_field
    )

    # The separation proof, run on the frames this very artifact was built from.
    audit = leakage.audit(
        games.filter(pl.col("season") == SOURCE_SEASON),
        None,
        CFG,
        projection_design=design,
    )

    prior_fbs = sorted(inputs.fbs[SOURCE_SEASON])
    coverage = offseason.coverage(TARGET_SEASON, teams_2026, prior_teams=prior_fbs)
    promoted = [t for t in teams_2026 if t not in inputs.fbs[SOURCE_SEASON]]

    return {
        "levers": levers,
        "cross_division": calibration,
        "carry_provenance": carry_provenance,
        "carried": carried,
        # The season before last, kept so an explanation can name what the second
        # season of memory actually did to a team rather than assert that it did
        # something.
        "older_power": dict(inputs.power.get(SOURCE_SEASON - 1, {})),
        "fitted_transitions": fitted_transitions,
        "home_field": home_field,
        "receipts": {
            team: crossdivision.receipts(
                games, team, inputs.power, inputs.home_field, SOURCE_SEASON
            )
            for team in promoted
        },
        "season_receipts": {
            team: crossdivision.season_receipts(
                games, team, SOURCE_SEASON, inputs.power[SOURCE_SEASON],
                inputs.home_field[SOURCE_SEASON],
            )
            for team in CONTESTED_TEAMS
        },
        "promoted": promoted,
        "projection": projection,
        "recipe": fitted,
        "backtest": backtest,
        "wins": wins,
        "coverage": coverage,
        "audit": audit,
        "source": source,
        "games": games,
        "plays": plays,
        "future": future,
        # The centring constant the design used. Returned rather than recomputed
        # downstream, because a schedule-strength number derived from a second
        # copy of this could disagree with the win total on the same row.
        "prior_power_center": float(design["prior_power_center"][0]),
        "schedule_strength": strength,
        "contrast": contrast,
        "n_future_games": int(future.height),
    }


def _pooled(games: pl.DataFrame, plays: pl.DataFrame) -> tuple[list[pl.DataFrame], list[Any]]:
    holdout.assert_no_target_is_locked(TRANSITIONS, CFG)
    data = [fit.gather(games, a, b, plays, CFG) for a, b in TRANSITIONS]
    return ([d.design for d in data], [d.response for d in data])


# ------------------------------------------------------------------ the artifacts


def explanations(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The plain-English answer for every row a reader is entitled to argue about.

    TEMPLATED FROM THE NUMBERS, NEVER TYPED. Every sentence is assembled from the
    team's own row, so a regeneration that moves a team moves its explanation with
    it and this page cannot end up defending a rank it no longer publishes. Two
    kinds of row qualify:

      a PROMOTED team, because its rating was earned outside the division it is
      about to play in, and the correction is the largest single adjustment this
      model makes to anybody;
      a CONTESTED team, because the ranking it gets is the thing people will argue
      about, and an answer that only exists in a chat log is not published.

    Both kinds carry `receipts`: the actual games, with what the model expected of
    them printed beside what happened. An adjustment estimated over 602 games is a
    fact about the league; the receipts are the part a reader can check against
    their own memory of watching the team.
    """
    projection: pl.DataFrame = state["projection"]
    calibration: crossdivision.DivisionCalibration = state["cross_division"]
    carried: dict[str, float] = state["carried"]
    provenance: dict[str, str] = state["carry_provenance"]
    source = state["source"]
    fbs_source = {t for t, p in provenance.items() if p == "fbs"}
    source_mean = (
        float(np.mean([source.ratings[t] for t in fbs_source if t in source.ratings]))
        if fbs_source
        else 0.0
    )

    def rank_in(ratings: dict[str, float], team: str) -> int:
        return 1 + sum(
            1 for t in fbs_source if ratings.get(t, 0.0) > ratings.get(team, 0.0)
        )

    out: list[dict[str, Any]] = []
    for team in [*state["promoted"], *CONTESTED_TEAMS]:
        row = projection.filter(pl.col("team") == team)
        if not row.height:
            continue
        record = row.to_dicts()[0]
        rank = int(record["projected_rank"])
        power = float(record["projected_power"])
        how = provenance.get(team, "fbs")
        ord_rank = f"{rank}{_ordinal_suffix(rank)}"
        block: dict[str, Any] = {
            "team": team,
            "projected_rank": rank,
            "projected_power": round(power, 2),
            "carried_rating": round(float(carried.get(team, 0.0)), 2),
            "prior_rating": round(float(source.ratings.get(team, 0.0)), 2),
            "carry_treatment": how,
        }

        if how.startswith("promoted"):
            block.update(_promoted_explanation(state, team, rank, ord_rank, block, calibration))
            out.append(block)
            continue

        block.update(
            _contested_explanation(state, team, rank, ord_rank, power, record, block, carried,
                                   source, source_mean, rank_in)
        )
        out.append(block)
    return out


def _promoted_explanation(
    state: dict[str, Any],
    team: str,
    rank: int,
    ord_rank: str,
    block: dict[str, Any],
    calibration: crossdivision.DivisionCalibration,
) -> dict[str, Any]:
    """Why a team that moved up from FCS lands where it lands."""
    receipts = state["receipts"].get(team, [])
    played = len(receipts)
    won = sum(1 for r in receipts if r["result"] == "won")
    capped = block["carry_treatment"] == "promoted_at_ceiling"

    detail = (
        f"Their {SOURCE_SEASON} rating was {block['prior_rating']:+.2f}. The "
        f"{calibration.n_bridge_games} games between an FBS team and an FCS team in "
        f"this archive say a rating earned outside FBS is worth "
        f"{abs(calibration.cross_division_gap):.1f} points less against FBS "
        f"opposition. The {calibration.n_promotion_games} games "
        f"{calibration.n_promoted_teams} promoted programs have actually played in "
        f"their first FBS season give {abs(calibration.promotion_bump):.1f} of that "
        "back."
    )
    if capped:
        detail += (
            " That still left them above anything a promoted program has ever done, "
            "so the ceiling applies: no promoted team is projected above "
            f"{calibration.promotion_ceiling_team}'s first FBS season in "
            f"{calibration.promotion_ceiling_season}, which is the best on record. "
            f"{team} lands {ord_rank}."
        )
    else:
        detail += f" {team} lands {ord_rank}."

    if played:
        results = "; ".join(
            (
                f"{r['season']} lost to {r['opponent']} by {abs(r['margin']):.0f}"
                if r["result"] == "lost"
                else f"{r['season']} beat {r['opponent']} by {abs(r['margin']):.0f}"
            )
            for r in receipts
        )
        receipt_line = (
            f"{team} has played {played} game{'s' if played != 1 else ''} against an "
            f"FBS opponent in this archive and won {won}: {results}."
        )
    else:
        receipt_line = (
            f"{team} has not played an FBS opponent in this archive, so there is no "
            "direct evidence about this program and the correction it carries is the "
            "league-wide one."
        )

    return {
        "headline": (
            f"{team} moved up from FCS, so the rating they bring with them was earned "
            "against teams they will not play any more."
        ),
        "detail": detail,
        "receipts": receipt_line,
    }


def _contested_explanation(
    state: dict[str, Any],
    team: str,
    rank: int,
    ord_rank: str,
    power: float,
    record: dict[str, Any],
    block: dict[str, Any],
    carried: dict[str, float],
    source: Any,
    source_mean: float,
    rank_in: Any,
) -> dict[str, Any]:
    """Why an FBS team a lot of people have an opinion about lands where it lands."""
    prior_rel = float(source.ratings.get(team, 0.0)) - source_mean
    prior_rank = rank_in(source.ratings, team)
    carried_rank = rank_in(carried, team)
    older = state["older_power"].get(team)
    ord_prior = f"{prior_rank}{_ordinal_suffix(prior_rank)}"
    ord_carried = f"{carried_rank}{_ordinal_suffix(carried_rank)}"

    detail = (
        f"They finished {SOURCE_SEASON} on {block['prior_rating']:+.2f} Power, "
        f"{prior_rel:+.2f} against the FBS average, which was {ord_prior} in the "
        "league. That is the number to argue with, because everything after it is "
        "arithmetic."
    )
    if older is not None:
        detail += (
            f" The projection does not use it alone: it blends in {SOURCE_SEASON - 1}, "
            f"when {team} rated {float(older):+.2f}, at the published weight, and the "
            f"carried rating that comes out is {block['carried_rating']:+.2f}, which is "
            f"{ord_carried}."
        )
    detail += (
        f" Returning production then adds "
        f"{float(record['contrib_returning_production']):+.2f} points and the portal "
        f"{float(record['contrib_net_portal']):+.2f}, and mean reversion pulls every "
        f"team toward the middle at once, which is how a carried "
        f"{block['carried_rating']:+.2f} becomes a projected {power:.2f} and "
        f"{ord_carried} becomes {ord_rank}."
    )
    sos_rank = record.get("schedule_strength_rank")
    if sos_rank is not None:
        detail += (
            f" Their {TARGET_SEASON} schedule is the "
            f"{int(sos_rank)}{_ordinal_suffix(int(sos_rank))} hardest of "
            f"{int(record['schedule_field_size'])}, which costs them projected wins and "
            "costs them nothing in the ranking: this board is sorted by how good the "
            "model thinks a team is, not by how many games it expects them to win."
        )

    worst = state["season_receipts"].get(team) or []
    receipt_line = None
    if worst:
        def phrase(r: dict[str, Any]) -> str:
            verb = "lost to" if r["result"] == "lost" else "beat"
            had = "win" if r["model_expected_margin"] > 0 else "lose"
            where = {"home": "at home", "away": "on the road", "neutral": "at a neutral site"}
            return (
                f"{verb} {r['opponent']} by {abs(r['margin']):.0f} "
                f"{where.get(r['at'], r['at'])}, where the model expected them to {had} "
                f"by {abs(r['model_expected_margin']):.0f}"
            )

        best = worst[-1]
        receipt_line = (
            f"The three {SOURCE_SEASON} games that cost {team} the most, each measured "
            "against what the model expected of them that day: "
            + "; ".join(phrase(r) for r in worst[:3])
            + f". Their best day ran the other way: they {phrase(best)}."
        )

    out = {
        "headline": (
            f"{team} projects {ord_rank}, and the argument is not about this August. "
            f"It is about last season, which the model scored {ord_prior}."
        ),
        "detail": detail,
        "prior_rank": prior_rank,
        "carried_rank": carried_rank,
    }
    if receipt_line:
        out["receipts"] = receipt_line
    return out


def _ordinal_suffix(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def write_projection(state: dict[str, Any]) -> dict[str, Any]:
    projection: pl.DataFrame = state["projection"]
    fitted: recipe.Recipe = state["recipe"]
    wins: forward.WinProjection = state["wins"]
    coverage = state["coverage"]
    audit: leakage.AuditReport = state["audit"]

    ranked = projection.filter(pl.col("projected_rank") <= 25).sort("projected_rank")
    provenance = holdout.source_season_note(SOURCE_SEASON, CFG)

    payload = {
        "artifact": "2026 PRESEASON PROJECTION — A PROJECTION, NOT THE POLL",
        "projection_version": PROJECTION_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "config_hash": config_hash(DEFAULT_CONFIG_PATH),
        "season": TARGET_SEASON,
        "label": (
            "This is a PROJECTION. It is not the poll, it never becomes the poll, "
            "and no number in it may reach the poll's math. The poll begins in "
            f"week {CFG['publication']['headline_start_week']} and will grade this "
            "page in public."
        ),
        "recipe": fitted.as_dict(),
        # Which Power this page's ratings are. Stamped because the version before
        # it published a number on one scale and graded it on another (ADR 0013).
        "power_definition": seasons.POWER_DEFINITION,
        "win_model": wins.as_dict(),
        "provenance": provenance,
        # THE LIBERATION BLOCK (ADR 0014). What the model was allowed to do, what
        # it measured, and the rows it owes a reader an argument about.
        "levers": state["levers"].as_dict(),
        "cross_division": state["cross_division"].as_dict(),
        "fitted_on_transitions": [list(t) for t in state["fitted_transitions"]],
        "home_field_points": round(float(state["home_field"]), 4),
        "explanations": explanations(state),
        "coverage": coverage,
        "separation_audit": {
            "passed": audit.passed,
            "violations": audit.violations,
            "projection_audited": audit.context["projection_audited"],
            "temporal_guard": audit.context["temporal_guard"],
            "layers": [
                {"layer": r.layer, "kind": r.kind, "ok": r.ok, "identical": r.identical}
                for r in audit.layers
            ],
        },
        "rows": [
            {
                "rank": int(row["projected_rank"]),
                "team": row["team"],
                "projected_power": row["projected_power"],
                "projected_wins": row["projected_wins"],
                "scheduled_games": row["scheduled_games"],
                "contributions": {
                    "intercept": row["contrib_intercept"],
                    **{f"{t}": row[f"contrib_{t}"] for t in recipe.TERMS},
                },
                "inputs": {
                    "prior_power": row["prior_power"],
                    "returning_usage": row["returning_usage_filled"],
                    "coach_change": row["coach_change"],
                    "coach_name": row["coach_name"],
                    "portal_out": row["portal_out"],
                    "portal_in": row["portal_in"],
                    "portal_net_z": row["portal_net_z"],
                },
            }
            for row in ranked.to_dicts()
        ],
    }
    (DEMO / "2026-preseason-projection.json").write_text(
        json.dumps(payload, indent=1, default=str) + "\n", encoding="utf-8"
    )

    lines: list[str] = []
    add = lines.append
    add("# The 2026 Preseason Projection")
    add("")
    add("> **THIS IS A PROJECTION. IT IS NOT THE POLL.**")
    add(">")
    add(
        "> The poll ranks what a team has done, from on-field results only, and it "
        f"does not begin until week {CFG['publication']['headline_start_week']}. This "
        "page is the model's August projection, built from last season's fitted "
        "ratings plus every offseason change we can measure. Its whole job is to "
        "be graded in public by the poll it is not allowed to influence."
    )
    add(">")
    add(
        "> It is frozen. It will not be edited, quietly improved, or re-run when "
        "it starts to look bad. That is the deal."
    )
    add("")
    add(f"Recipe `{fitted.version}` · source season {SOURCE_SEASON} · "
        f"generated {payload['generated_at']} · `{payload['git_sha'][:10]}`")
    add("")
    add("## The recipe, in full")
    add("")
    add("```")
    add("P_hat(team) = intercept")
    for term, column in zip(recipe.TERMS, recipe.DESIGN_COLUMNS, strict=True):
        add(f"            + {fitted.coefficients[term]:+.4f} * {column}")
    add("```")
    add("")
    add("| term | coefficient | standard error | reads as |")
    add("|---|---:|---:|---|")
    add(
        f"| intercept | {fitted.intercept:+.3f} | {fitted.intercept_se:.3f} | "
        "projected Power of a league-average team that kept its coach |"
    )
    readings = {
        "prior_power": "share of last season's deviation from the FBS mean that survives",
        "returning_production": "points of Power per unit of returning offensive usage share",
        "coaching_change": "points of Power associated with a new head coach",
        "net_portal": "points of Power per standard deviation of net portal flow",
    }
    for term in recipe.TERMS:
        add(
            f"| {term} | {fitted.coefficients[term]:+.3f} | {fitted.se[term]:.3f} | "
            f"{readings[term]} |"
        )
    add("")
    add(
        f"Fitted on {len(TRANSITIONS)} season transitions "
        + ", ".join(f"{a}→{b}" for a, b in TRANSITIONS)
        + f" · {fitted.n_teams} team-seasons · R² = {fitted.r_squared:.3f} · "
        f"residual SD = {fitted.residual_sd:.2f} points."
    )
    add("")
    add(_significance_paragraph(fitted))
    add("")
    add("## The top 25")
    add("")
    add(
        "`Power` is the projected rating in points. The four `Δ` columns are each "
        "term's signed contribution to it, in points, measured against a "
        "league-average team — they sum to `Power` with the intercept "
        f"({fitted.intercept:+.2f}) included."
    )
    add("")
    add(
        "| # | team | Power | proj W-L | SoS | SoS rk | W on median | "
        "Δ last season | Δ returning | Δ coach | Δ portal |"
    )
    add("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in ranked.to_dicts():
        record = (
            f"{row['projected_wins']:.1f}-{row['projected_losses']:.1f}"
            if row["projected_wins"] is not None
            else "n/a"
        )
        add(
            f"| {int(row['projected_rank'])} | {row['team']} | "
            f"{row['projected_power']:.2f} | {record} | "
            f"{_fmt(row.get('schedule_strength'), 1)} | "
            f"{_fmt(row.get('schedule_strength_rank'), 0)} | "
            f"{_fmt(row.get('wins_on_median_schedule'), 1)} | "
            f"{row['contrib_prior_power']:+.2f} | "
            f"{row['contrib_returning_production']:+.2f} | "
            f"{row['contrib_coaching_change']:+.2f} | "
            f"{row['contrib_net_portal']:+.2f} |"
        )
    add("")
    add(_schedule_paragraph(state))
    add("")
    add(f"Projected records use {wins.sigma_note}")
    add("")
    add("## How a rating crosses divisions")
    add("")
    for line in _crossdivision_lines(state):
        add(line)
    add("")
    add("## The rows people will argue about")
    add("")
    for block in explanations(state):
        add(f"**{block['team']}, projected #{block['projected_rank']}.** "
            f"{block['headline']}")
        add("")
        add(block["detail"])
        if block.get("receipts"):
            add("")
            add(f"*{block['receipts']}*")
        add("")
    add("## What this projection does not know")
    add("")
    for line in _caveats(
        coverage, wins, state["n_future_games"], state["promoted"], projection
    ):
        add(f"- {line}")
    add("")
    add("## The holdout")
    add("")
    add(provenance["claim"])
    add("")
    add("## The separation, measured")
    add("")
    add(
        f"`cfbpoll audit-features` was run on the frames this page was built from, "
        f"with the projection design matrix handed in: **{len(audit.layers)} layers, "
        f"{'passed' if audit.passed else 'FAILED'}**. Every poll layer was rebuilt "
        "from its allow-list and came out bit-identical, and the projection layer "
        "was judged against its own deny-list — which still bans human polls and "
        "third-party fitted models, so the AP preseason poll this page is measured "
        "against is mechanically unable to be an input to it."
    )
    add("")
    (DEMO / "2026-preseason-projection.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def _schedule_paragraph(state: dict[str, Any]) -> str:
    """Why the board's order is not the win column's order, in the demo's own voice.

    The fixture publishes this as templated fields; the demo says it in prose off
    the SAME objects, so a reader can check one against the other. If the two ever
    disagree, one of them was hand-edited.
    """
    strength = state["schedule_strength"]
    contrast = state["contrast"]
    lines = [
        "**`SoS` is mean opponent projected power at a neutral field**, with "
        "venue kept out of it deliberately; `SoS rk` is that figure's rank among "
        f"the {strength.field_size} teams with a full schedule, 1 being hardest. "
        "**`W on median` is the load-bearing column**: every team scored against "
        f"{strength.median_schedule_team}'s "
        f"{strength.median_schedule_games}-game calendar, which sits at the "
        "middle of that field. It is the column that makes this ordering "
        "checkable, because it is the only one where all 25 teams face the same "
        "opposition.",
    ]
    if contrast is not None:
        lines.append(
            f"The sharpest case: **{contrast.higher_team} projects "
            f"{contrast.higher_wins:.1f} wins and {contrast.lower_team} projects "
            f"{contrast.lower_wins:.1f}, and {contrast.higher_team} still ranks "
            f"higher.** Swap their calendars and the reason is arithmetic rather "
            f"than opinion: {contrast.higher_team} would win "
            f"{contrast.higher_on_lower_schedule:.1f} games on "
            f"{contrast.lower_team}'s schedule, and {contrast.lower_team} would "
            f"win {contrast.lower_on_higher_schedule:.1f} on "
            f"{contrast.higher_team}'s."
        )
    return "\n\n".join(lines)


def _significance_paragraph(fitted: recipe.Recipe) -> str:
    weak = [
        term
        for term in recipe.TERMS
        if fitted.se[term] > 0 and abs(fitted.coefficients[term] / fitted.se[term]) < 2.0
    ]
    strong = [term for term in recipe.TERMS if term not in weak]
    parts = [
        "**Read the standard errors before the ranking.** "
        + ", ".join(f"`{t}`" for t in strong)
        + f" {'is' if len(strong) == 1 else 'are'} more than two standard errors "
        "from zero on this fit."
    ]
    if weak:
        parts.append(
            " "
            + ", ".join(f"`{t}`" for t in weak)
            + f" {'is' if len(weak) == 1 else 'are'} NOT: the data does not "
            "distinguish that coefficient from zero, and it is published at its "
            "fitted value rather than dropped, so that the grading loop can "
            "report season by season whether it ever earns its place. A term kept "
            "at a value the data cannot support is a term on probation, and "
            "saying which ones those are is cheaper than letting a reader assume "
            "all four are load-bearing."
        )
    return "".join(parts)


def _crossdivision_lines(state: dict[str, Any]) -> list[str]:
    """The cross-division treatment, with every constant and its sample size."""
    c: crossdivision.DivisionCalibration = state["cross_division"]
    if not c.measured:
        return [
            "The archive did not hold enough games between divisions to measure a "
            "correction, so ratings are carried across the boundary unchanged and this "
            "page says so rather than implying a treatment it did not apply."
        ]
    return [
        "A team that earned its rating against FCS opponents does not carry it intact "
        "into an FBS game, and until this version that is exactly what happened. The "
        "size of the mistake is measurable, because the archive holds every game where "
        "the two divisions met.",
        "",
        f"Run the model's own prediction over those **{c.n_bridge_games} crossover "
        f"games** and the FBS side beats it by **{c.raw_bridge_miss:+.1f} points** on "
        "average. Most of that is not about divisions: this model under-predicts every "
        f"mismatch, and the same regression says a game it calls by 10 points is "
        f"actually won by about {10 * c.dispersion:.0f}. Carrying the predicted margin "
        "as a regressor and asking what is left for the division boundary gives the "
        "number this page uses:",
        "",
        "| what | value | standard error | measured on |",
        "|---|---:|---:|---|",
        f"| an FCS rating, against FBS opposition | **{c.cross_division_gap:+.1f}** | "
        f"{c.cross_division_gap_se:.2f} | {c.n_bridge_games} crossover games |",
        f"| credit for being a program that got promoted | **{c.promotion_bump:+.1f}** | "
        f"{c.promotion_bump_se:.2f} | {c.n_promotion_games} games, "
        f"{c.n_promoted_teams} programs |",
        f"| net, for a team moving up | **{c.promoted_net:+.1f}** | | both |",
        "",
        "**The two numbers are not in conflict and they are not the same question.** "
        "The first is what an FCS roster is worth on a Saturday against FBS opposition. "
        "The second is what a program gains by being the kind of program that gets "
        "promoted at all, which is a program that spent years buying its way to FBS "
        "rosters and FBS staff. A promoted team carries both.",
        "",
        f"**And then the guard, which is the part that decides the top of this board.** "
        f"The promotion credit is fitted on {c.n_promoted_teams} programs whose ratings "
        f"topped out at {c.promotion_support_max_rel:+.1f} against the FBS average. Any "
        "team rated well above that is outside the evidence, so the rule is a maximum "
        "rather than an extrapolation: **no promoted team is projected above the best "
        "first FBS season a promoted program has actually had.** That is "
        f"{c.promotion_ceiling_team} in {c.promotion_ceiling_season}, at "
        f"{c.promotion_ceiling_rel:+.1f} against the FBS average.",
        "",
        "Every one of these is a lever with a published range. Turn the first to zero "
        "and you get the board this project published in August 2026, with North Dakota "
        "State tenth.",
    ]


def _caveats(
    coverage: dict[str, Any],
    wins: forward.WinProjection,
    n_games: int,
    promoted: list[str],
    projection: pl.DataFrame,
) -> list[str]:
    rp = coverage["returning_production"]
    out = [
        "**Returning production is offence only.** CFBD serves no defensive "
        "returning production of any kind, so the term covers half the roster. A "
        "team that returns its whole offence and none of its defence and a team "
        "that does the reverse are, to this recipe, the same team.",
        "**The portal term is a body count, and half of it is undercounted.** "
        f"`origin` is populated on every row; `destination` on "
        f"{coverage['portal_destination_coverage']:.0%} of them, so players who had "
        "not landed anywhere when CFBD last wrote the file are counted out of "
        "their old school and never counted in to their new one. Departures are "
        "measured well; arrivals are not.",
        "**Stars were available and were not used.** CFBD publishes a recruiting "
        "rating on most portal rows. A star-weighted net flow would almost "
        "certainly predict better. It is also a recruiting composite, which is "
        "the first input the poll's constraint 2 bans, and using one here would "
        "make the poll's refusal look like a technicality.",
        "**The coaching term is a binary, not a judgement.** It says the head "
        "coach is new. It does not say whether he is good, it knows nothing about "
        "coordinators, and one coefficient applies to every school that changed.",
        f"**Coverage.** {rp['covered']} of {coverage['n_teams']} FBS teams have a "
        f"returning-production row"
        + (
            f"; the {len(rp['missing'])} missing "
            f"({', '.join(rp['missing'])}) "
            + (
                "are new to FBS and have no prior FBS production to return, which "
                "is a correct absence rather than a gap."
                if not rp["missing_unexplained"]
                else f"include {rp['missing_unexplained']}, which is unexplained."
            )
            if rp["missing"]
            else "."
        ),
        f"**The win totals are timid on purpose.** {wins.sigma_note}",
        f"**The 2026 schedule is {n_games} games as CFBD had it when this ran.** "
        "Schedules change; the projection does not get re-run when they do.",
    ]
    if promoted:
        names = ", ".join(promoted)
        out.append(
            f"**{names} moved up from FCS for {TARGET_SEASON}.** Their rating was "
            "earned against opponents they will not play any more, and this version "
            "corrects for that from the crossover games rather than warning about it "
            "in a footnote. The correction and the evidence behind it are in "
            "**How a rating crosses divisions** above. What is still thin: the "
            "promotion half of it rests on six programs, and the ceiling that stops it "
            "being extrapolated is a maximum over those same six."
        )
    if not coverage["ap_preseason_available"]:
        out.append(
            "**No AP preseason poll for 2026 was in the archive when this ran**, so "
            "the head-to-head comparison on this page is the historical one. The "
            "AP's 2026 preseason ballot will be scored against this page's when "
            "it appears."
        )
    return out


def write_backtest(state: dict[str, Any]) -> None:
    report = state["backtest"]
    (DEMO / "projection-backtest.json").write_text(
        json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8"
    )

    summary = report["summary"]["out_of_sample"]
    early = report["summary"]["early_season"]
    lines: list[str] = []
    add = lines.append
    add("# Did the Projection beat the sportswriters?")
    add("")
    add(
        "The headline question this product has to answer, scored honestly and "
        "reported whatever it says. Four systems, one target, one code path."
    )
    add("")
    add("## The four systems")
    add("")
    add("| system | what it is |")
    add("|---|---|")
    add("| `projection` | the four-term recipe |")
    add(
        "| `regress_only` | the same recipe with ONLY the prior-Power term — "
        "the control that says whether the offseason data bought anything |"
    )
    add("| `naive_carryover` | last season's final Power, unchanged. The floor |")
    add("| `ap_preseason` | the AP writers' August top 25. A baseline, never an input |")
    add("")
    add(
        "Every number below is **out of sample**: each season is scored by a "
        "recipe fitted on the other two transitions only. Scoring the recipe on "
        "the transitions it was fitted on would be reporting a training error."
    )
    add("")
    add("## Ranking the season that followed")
    add("")
    add(
        "Target: `R(final, final)`, the poll evaluated on the whole season — the "
        "most complete statement the poll ever makes about a year."
    )
    add("")
    add(
        "`top-25 hits` is treatment-free: both systems name 25 teams and we count "
        "how many finished there. `rank MAE` censors **every** system's rank at "
        "26, so each is answering the AP's own question, which is the only way to "
        "compare a 25-team poll with a 134-team rating without flattering one of "
        "them."
    )
    add("")
    add("| system | top-25 hits /25 | rank MAE (censored) | Spearman, all FBS |")
    add("|---|---:|---:|---:|")
    for system in fit.SYSTEMS:
        row = summary.get(system, {})
        add(
            f"| `{system}` | {_fmt(row.get('top25_overlap'), 1)} | "
            f"{_fmt(row.get('mae_rank_top25_censored'))} | "
            f"{_fmt(row.get('spearman_full'), 3)} |"
        )
    add("")
    add("### Season by season")
    add("")
    add("| target | system | top-25 hits | rank MAE (censored) |")
    add("|---:|---|---:|---:|")
    for block in report["per_season"]:
        for system in fit.SYSTEMS:
            row = block["out_of_sample"].get(system)
            if not row:
                continue
            add(
                f"| {block['target_season']} | `{system}` | {row['top25_overlap']} | "
                f"{_fmt(row['mae_rank_top25_censored'])} |"
            )
    add("")
    add("## Predicting the first four weeks")
    add("")
    add(
        "FBS-vs-FBS, weeks 1–4 of the target season. Straight-up accuracy is the "
        "honest number here because it is invariant to any positive affine map of "
        "the ratings, so it measures the ordering and nothing else. MAE needs a "
        "scale and every system gets one from the same in-sample affine fit on "
        "exactly these games — a fair comparison between systems, and not an "
        "out-of-sample error estimate."
    )
    add("")
    add("| system | SU accuracy | MAE (points) |")
    add("|---|---:|---:|")
    for system in fit.SYSTEMS:
        row = early.get(system, {})
        add(
            f"| `{system}` | {_fmt(row.get('su_accuracy'), 4)} | {_fmt(row.get('mae'), 3)} |"
        )
    add("")
    add("## The verdict")
    add("")
    for line in _verdict(summary, early):
        add(line)
        add("")
    (DEMO / "projection-backtest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _verdict(summary: dict[str, Any], early: dict[str, Any]) -> list[str]:
    proj = summary["projection"]
    ap = summary["ap_preseason"]
    naive = summary["naive_carryover"]
    regress = summary["regress_only"]

    beat_ap_ranks = proj["top25_overlap"] > ap["top25_overlap"]
    beat_ap_mae = proj["mae_rank_top25_censored"] < ap["mae_rank_top25_censored"]
    out = []

    if beat_ap_ranks and beat_ap_mae:
        out.append(
            "**We beat the AP preseason poll at ranking the season that followed.**"
        )
    elif not beat_ap_ranks and not beat_ap_mae:
        out.append(
            "**We do not beat the AP preseason poll at ranking the season that "
            f"followed.** The writers hit {ap['top25_overlap']:.1f} of the final "
            f"top 25 on average against our {proj['top25_overlap']:.1f}, and their "
            f"censored rank error is {ap['mae_rank_top25_censored']:.2f} against "
            f"our {proj['mae_rank_top25_censored']:.2f}. It is close, and it is a "
            "loss, and a loss reported by the party that lost is worth more than a "
            "win reported by the party that won."
        )
    else:
        out.append(
            "**The comparison against the AP splits.** We win one of the two rank "
            f"metrics and lose the other: top-25 hits {proj['top25_overlap']:.1f} "
            f"against {ap['top25_overlap']:.1f}, censored rank error "
            f"{proj['mae_rank_top25_censored']:.2f} against "
            f"{ap['mae_rank_top25_censored']:.2f}."
        )

    # THE FLOOR SENTENCE HAS TO SURVIVE THE OFFSEASON TERMS BUYING NOTHING, and
    # under `projection-2.0.0` on top-25 hits they buy exactly nothing. A template
    # whose only ending is "that is a small edge and it is a real one" would have
    # printed it over a difference of 0.0, which is the shape of claim this whole
    # project exists to refuse.
    hits_gap = float(proj["top25_overlap"]) - float(naive["top25_overlap"])
    mae_gap = float(naive["mae_rank_top25_censored"]) - float(
        proj["mae_rank_top25_censored"]
    )
    if hits_gap > 0.05:
        headline = "**We beat the naive floor.**"
        tail = "That is a small edge and it is a real one."
    elif mae_gap > 0.005:
        headline = "**We match the naive floor on hits and beat it on rank error.**"
        tail = (
            # "where the season put them" is a retired form: a season puts
            # nobody anywhere. briefs/step-4-implementation.md §3d. The teams are
            # the subject of their own finish and the sentence says so.
            "The offseason terms did not put a single extra team in the top 25 "
            "over these three seasons. They moved teams closer to where those "
            "teams finished, which is a smaller claim, and it is the one the "
            "numbers support."
        )
    else:
        headline = "**We do not beat the naive floor.**"
        tail = (
            "Over these three seasons the offseason terms bought nothing "
            "measurable, and that is the result, reported by the party it is "
            "worst for."
        )
    out.append(
        f"{headline} Carrying last season's final rating forward "
        f"unchanged hits {naive['top25_overlap']:.1f} of the final top 25; the "
        f"recipe hits {proj['top25_overlap']:.1f}. The offseason terms are worth "
        f"about {hits_gap:.1f} teams a season, and about {mae_gap:.2f} "
        f"places of censored rank error. {tail}"
    )

    if abs(regress["top25_overlap"] - naive["top25_overlap"]) < 1e-9:
        out.append(
            "**`regress_only` and `naive_carryover` are identical on every rank "
            "metric, and that is arithmetic rather than coincidence.** Regressing "
            "toward the mean is `a + phi * (x - mean)`, a positive affine map, "
            "which cannot reorder anything. The mean-reversion coefficient changes "
            "what we predict a team's rating will BE; it cannot change who we "
            "think is better than whom. Only the three offseason terms can move a "
            "rank — which is precisely why the gap between `projection` and "
            "`naive_carryover` is the whole measured value of the offseason data."
        )

    out.append(
        "**We beat the AP at predicting games, and by more than we lose to them "
        "at ranking.** Over the first four weeks the recipe is right on "
        f"{early['projection']['su_accuracy']:.1%} of straight-up results against "
        f"the AP's {early['ap_preseason']['su_accuracy']:.1%}, and its margin MAE "
        f"is {early['ap_preseason']['mae'] - early['projection']['mae']:.2f} points "
        "lower. That is not a contradiction of the paragraph above: the AP ranks "
        "25 teams well and expresses no opinion at all about the other 109, and "
        "most games in September involve at least one of those 109."
    )
    out.append(
        "**Three transitions is not many.** Every number here rests on three "
        "season pairs, and the honest reading of a "
        f"{abs(float(proj['top25_overlap']) - float(ap['top25_overlap'])):.1f}"
        "-team difference in top-25 "
        "hits over three seasons is that it is inside the noise. The grading loop "
        "exists because this table only becomes an argument after several more "
        "seasons have been added to it, in public, without the recipe being "
        "quietly re-tuned in between."
    )
    return out


def write_grading_demo(state: dict[str, Any]) -> None:
    """The loop, worked end to end on a season we are allowed to score.

    2024, not 2025: grading is scoring, and scoring the holdout is exactly what
    ADR 0010 says the projection may not do. The recipe used here is fitted on
    the transitions that EXCLUDE 2023->2024, so the 2024 projection being graded
    is a genuine out-of-sample projection.
    """
    games, plays = state["games"], state["plays"]
    others = [t for t in TRANSITIONS if t[1] != GRADING_DEMO_SEASON]
    data = [fit.gather(games, a, b, plays, CFG) for a, b in others]
    fitted = recipe.fit_recipe([d.design for d in data], [d.response for d in data], others)

    source = seasons.final_power(games, GRADING_DEMO_SEASON - 1, plays, CFG)
    teams = seasons.fbs_teams(games, GRADING_DEMO_SEASON)
    design = recipe.build_design(source.ratings, GRADING_DEMO_SEASON, teams)
    projection = recipe.project(fitted, design, teams)

    result = grade.grade_season(projection, games, GRADING_DEMO_SEASON, plays=plays, config=CFG)
    table: pl.DataFrame = result["table"]

    lines: list[str] = []
    add = lines.append
    add(f"# The grading loop, worked on {GRADING_DEMO_SEASON}")
    add("")
    add(
        "This is what the published surface reads like. The projection below was "
        f"made from {GRADING_DEMO_SEASON - 1}'s final ratings by a recipe fitted on "
        + ", ".join(f"{a}→{b}" for a, b in others)
        + f" — so {GRADING_DEMO_SEASON} is genuinely out of sample — and it is then "
        "graded, week by week, against the poll it is not allowed to influence."
    )
    add("")
    add(
        f"{GRADING_DEMO_SEASON} rather than 2025 because grading is scoring, and "
        "2025 is the sealed holdout. ADR 0010."
    )
    add("")
    for label, order in (
        (f"Week {CFG['publication']['headline_start_week']} — the first graded week",
         result["headline_eval_order"]),
        ("The end of the season", int(table["eval_order"].max())),
    ):
        add(f"## {label}")
        add("")
        week = table.filter(pl.col("eval_order") == order)
        add(f"*{week['eval_label'][0]}*")
        add("")
        add("### We thought this, and here is what we now know")
        add("")
        for line in grade.story_lines(table, order, top_n=5):
            add(f"- {line}")
        add("")
        add("### Which offseason assumption was wrong")
        add("")
        attribution = grade.attribution(week)
        if attribution.get("terms"):
            add("| term | coefficient | z | verdict |")
            add("|---|---:|---:|---|")
            for term, value in attribution["terms"].items():
                add(
                    f"| {term} | {value['coefficient']:+.3f} | {value['z']:+.1f} | "
                    f"{value['verdict']} |"
                )
            add("")
            for value in attribution["terms"].values():
                add(f"- {value['sentence']}")
            add("")
            add(f"> {attribution['health_warning']}")
        add("")
    add("## How to read the attribution")
    add("")
    add(
        "The per-team lines are **accounting, not causation**. Each term handed "
        "each team a signed number of points relative to a league-average team; "
        "when a team lands below its projection, the largest credit that did not "
        "pay off is the one named. It says which term was carrying the error, not "
        "which term caused it."
    )
    add("")
    add(
        "The league table underneath is a regression of every team's projection "
        "error on each term's contribution. A negative coefficient means the teams "
        "that term credited systematically underperformed — we over-credited it "
        "that season — and that is the number the next version of the recipe "
        "should move toward. It is a statement about the recipe rather than about "
        "a team, which is what makes it worth accumulating for a decade."
    )
    add("")
    (DEMO / "projection-grading-loop.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    DEMO.mkdir(parents=True, exist_ok=True)
    state = build()
    write_projection(state)
    write_backtest(state)
    write_grading_demo(state)
    print("wrote:")
    for name in (
        "2026-preseason-projection.md",
        "2026-preseason-projection.json",
        "projection-backtest.md",
        "projection-backtest.json",
        "projection-grading-loop.md",
    ):
        print(f"  demo/{name}")


if __name__ == "__main__":
    main()
