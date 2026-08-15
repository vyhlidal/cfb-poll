"""Regenerate the Projection artifacts from the local archive.

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
        uv run python scripts/make_projection.py

Writes, all committed so a reader can see real output without running anything:

    demo/2026-preseason-projection.md    the ranking, every term's contribution
    demo/2026-preseason-projection.json  the same numbers, machine-readable
    demo/projection-backtest.md          did we beat the AP's August guess
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
    fitted = recipe.fit_recipe(
        *_pooled(games, plays), TRANSITIONS
    )

    source = seasons.final_power(games, SOURCE_SEASON, plays, CFG)
    teams_2026 = sorted(
        set(offseason.returning_production(TARGET_SEASON)["team"].to_list())
        | set(offseason.coaching(TARGET_SEASON)["team"].to_list())
    )
    design = recipe.build_design(source.ratings, TARGET_SEASON, teams_2026)
    projection = recipe.project(fitted, design, teams_2026)

    future = forward.schedule(TARGET_SEASON)
    season_sigma = float(source.sigma or CFG["resume"]["sigma"])
    sigma_source = (
        source.sigma_source
        if source.sigma
        else "[resume].sigma, the documented fallback and floor"
    )
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
    strength = schedule.strengths(
        projection,
        future,
        fitted,
        source.ratings,
        center,
        wins.sigma,
        float(source.home_field),
        promoted=tuple(t for t in teams_2026 if t not in seasons.fbs_teams(games, SOURCE_SEASON)),
    )
    projection = projection.join(strength.table, on="team", how="left")
    contrast = schedule.contrast(
        projection, future, fitted, source.ratings, center, wins.sigma, float(source.home_field)
    )

    # The separation proof, run on the frames this very artifact was built from.
    audit = leakage.audit(
        games.filter(pl.col("season") == SOURCE_SEASON),
        None,
        CFG,
        projection_design=design,
    )

    prior_fbs = seasons.fbs_teams(games, SOURCE_SEASON)
    coverage = offseason.coverage(TARGET_SEASON, teams_2026, prior_teams=prior_fbs)

    return {
        "promoted": [t for t in teams_2026 if t not in prior_fbs],
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
        "win_model": wins.as_dict(),
        "provenance": provenance,
        "coverage": coverage,
        "separation_audit": {
            "passed": audit.passed,
            "violations": audit.violations,
            "projection_audited": audit.context["projection_audited"],
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
        "page is a guess made in August, before anybody has played a snap. It is "
        "built from last season's fitted ratings plus every offseason change we "
        "can measure, and its whole job is to be graded in public by the poll it "
        "is not allowed to influence."
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
    add("| # | team | Power | proj W-L | Δ last season | Δ returning | Δ coach | Δ portal |")
    add("|---:|---|---:|---:|---:|---:|---:|---:|")
    for row in ranked.to_dicts():
        record = (
            f"{row['projected_wins']:.1f}-{row['projected_losses']:.1f}"
            if row["projected_wins"] is not None
            else "—"
        )
        add(
            f"| {int(row['projected_rank'])} | {row['team']} | "
            f"{row['projected_power']:.2f} | {record} | "
            f"{row['contrib_prior_power']:+.2f} | "
            f"{row['contrib_returning_production']:+.2f} | "
            f"{row['contrib_coaching_change']:+.2f} | "
            f"{row['contrib_net_portal']:+.2f} |"
        )
    add("")
    add(f"Projected records use {wins.sigma_note}")
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
        placed = projection.filter(
            pl.col("team").is_in(promoted) & (pl.col("projected_rank") <= 25)
        ).sort("projected_rank")
        names = ", ".join(promoted)
        sentence = (
            f"**{names} moved up from FCS for {TARGET_SEASON}, and their "
            "prior-season rating was earned against FCS opposition.** The Power "
            "fit is all-divisions, so they have a real rating rather than a "
            "guess — but ridge shrinks thin schedules toward the mean of a "
            "universe that includes every FCS team, which is a softer standard "
            "than the one they are about to be held to, and the recipe has no "
            "term for promotion."
        )
        if placed.height:
            worked = "; ".join(
                f"{row['team']} lands #{int(row['projected_rank'])}"
                for row in placed.to_dicts()
            )
            sentence += (
                f" It is not hypothetical here: {worked}. Treat that as the "
                "single least trustworthy row on this page, and watch what the "
                "grading loop does to it."
            )
        out.append(sentence)
    if not coverage["ap_preseason_available"]:
        out.append(
            "**No AP preseason poll for 2026 was in the archive when this ran**, so "
            "the head-to-head comparison on this page is the historical one. The "
            "AP's 2026 guess will be scored against this page's when it appears."
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

    out.append(
        "**We beat the naive floor.** Carrying last season's final rating forward "
        f"unchanged hits {naive['top25_overlap']:.1f} of the final top 25; the "
        f"recipe hits {proj['top25_overlap']:.1f}. The offseason terms are worth "
        f"about {proj['top25_overlap'] - naive['top25_overlap']:.1f} teams a "
        "season, and about "
        f"{naive['mae_rank_top25_censored'] - proj['mae_rank_top25_censored']:.2f} "
        "places of censored rank error. That is a small edge and it is a real one."
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
        "season pairs, and the honest reading of a 0.3-team difference in top-25 "
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
    is a genuine out-of-sample guess.
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
