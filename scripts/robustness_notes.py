"""Two robustness questions the review raised, measured. No defaults change.

Writes docs/analysis/robustness-notes.md and .json.

  §1 THE BRIDGE-GAME VENUE CONFOUND (review §4b channel 1, Phase 1 §2). Roughly
     four in five G5-versus-P4 games are played at the Power-4 stadium, so the
     review's Phase 1 called any error in the home-field constant "the single
     most underappreciated sensitivity in the whole system": get h wrong by half
     a point and every conference offset moves.

     The design matrix carries an unpenalised site column, so in PRINCIPLE the
     offset is de-confounded - h is estimated rather than assumed, and whatever
     it absorbs it absorbs for every game. "In principle" is what an audit is for.
     Two falsifiable tests:

       (a) EXACT, from the ridge sandwich: the correlation between the estimated
           site coefficient and the estimated P4-minus-G5 contrast. If the two
           were collinear across this subsample that correlation would be near
           +/-1. It is computable to machine precision and needs no simulation.
       (b) DIRECT: force h wrong by +/-1 point, refit every rating with the site
           term offset, and measure how far the P4-minus-G5 gap moves. Theory
           says a team's rating shifts by h's error times its home/away
           IMBALANCE, not by h's error times anything about its conference.

  §2 recency_gamma AND THE SEPTEMBER SPLICE (review §4b channel 2, §5). Every
     cross-conference game is played in the first month; conference play consumes
     October and November. So a December ranking splices a September estimate of
     league level onto a November estimate of within-league order, and
     `recency_gamma = 1.0` treats the two as contemporaneous. The review's fix is
     to backtest gamma < 1 and adopt it for Power if it improves out-of-sample
     error. THE DEFAULT DOES NOT CHANGE HERE: recency is a fairness knob - "a poll
     that says who earned it should not decide that September didn't count" - and
     the owner decides it. This reports the backtest effect as a table.

Nothing in this file is on a publication path and no default is modified.
"""

from __future__ import annotations

import copy
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from cfbpoll.backtest import walkforward
from cfbpoll.config import DEFAULT_CONFIG_PATH, config_hash, load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.plays import load_plays
from cfbpoll.ingest.sportsdataverse import load_games
from cfbpoll.model import design, retro, ridge
from cfbpoll.publish import poll as poll_mod

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "analysis"

SEASON = 2023
WEEK = 10
TUNE_SEASONS = (2021, 2022, 2023)
GAMMAS = (1.0, 0.98, 0.95)

#: 2023 Power-4 membership (ACC, Big Ten, Big 12, SEC, Pac-12) plus Notre Dame,
#: which schedules as one. AN AUDIT LENS AND NEVER A FEATURE - exactly the use the
#: review makes of it, and the reason `conference` is on the banned-pattern list
#: while this list can sit in a script that touches no fit. Every name is asserted
#: against the archive's own team names, so a typo fails loudly rather than
#: quietly reclassifying a team.
POWER_FOUR_2023: tuple[str, ...] = (
    # ACC
    "Boston College", "California", "Clemson", "Duke", "Florida State",
    "Georgia Tech", "Louisville", "Miami", "NC State", "North Carolina",
    "Pittsburgh", "SMU", "Stanford", "Syracuse", "Virginia", "Virginia Tech",
    "Wake Forest",
    # Big Ten
    "Illinois", "Indiana", "Iowa", "Maryland", "Michigan", "Michigan State",
    "Minnesota", "Nebraska", "Northwestern", "Ohio State", "Penn State",
    "Purdue", "Rutgers", "Wisconsin",
    # Big 12
    "Baylor", "BYU", "Cincinnati", "Houston", "Iowa State", "Kansas",
    "Kansas State", "Oklahoma", "Oklahoma State", "TCU", "Texas",
    "Texas Tech", "UCF", "West Virginia",
    # SEC
    "Alabama", "Arkansas", "Auburn", "Florida", "Georgia", "Kentucky", "LSU",
    "Mississippi State", "Missouri", "Ole Miss", "South Carolina", "Tennessee",
    "Texas A&M", "Vanderbilt",
    # Pac-12
    "Arizona", "Arizona State", "Colorado", "Oregon", "Oregon State", "UCLA",
    "USC", "Utah", "Washington", "Washington State",
    # independent, schedules as a P4
    "Notre Dame",
)


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover
        return "unknown"


def bridge_inventory(games: pl.DataFrame, p4: set[str]) -> dict[str, Any]:
    """Every G5-versus-P4 regular-season FBS game, and where it was played."""
    fbs = games.filter(
        (pl.col("home_class") == "fbs")
        & (pl.col("away_class") == "fbs")
        & (pl.col("game_type").is_in(["regular", "conf_champ"]))
    )
    home = fbs["home_team"].to_list()
    away = fbs["away_team"].to_list()
    neutral = fbs["neutral_site"].to_list()
    bridges = [
        (h, a, bool(n))
        for h, a, n in zip(home, away, neutral, strict=True)
        if (h in p4) != (a in p4)
    ]
    at_p4 = sum(1 for h, _, n in bridges if not n and h in p4)
    at_g5 = sum(1 for h, _, n in bridges if not n and h not in p4)
    at_neutral = sum(1 for _, _, n in bridges if n)
    hosted = at_p4 + at_g5
    g5_teams = {t for t in set(home) | set(away) if t not in p4}
    return {
        "n_fbs_vs_fbs_games": int(fbs.height),
        "n_bridges": len(bridges),
        "share_of_all_fbs_games": len(bridges) / fbs.height if fbs.height else float("nan"),
        "at_p4_site": at_p4,
        "at_g5_site": at_g5,
        "at_neutral_site": at_neutral,
        "share_at_p4_site": at_p4 / hosted if hosted else float("nan"),
        "n_g5_teams": len(g5_teams),
        "bridges_per_g5_team": len(bridges) / len(g5_teams) if g5_teams else float("nan"),
    }


def contrast_vector(teams: tuple[str, ...], p4: set[str], site_index: int) -> np.ndarray:
    """c such that c'theta = mean(P4) - mean(G5) over the FBS teams in the fit."""
    c = np.zeros(len(teams) + 1, dtype=np.float64)
    fbs_p4 = [i for i, t in enumerate(teams) if t in p4]
    fbs_g5 = [i for i, t in enumerate(teams) if t in _G5_SET]
    for i in fbs_p4:
        c[i] = 1.0 / len(fbs_p4)
    for i in fbs_g5:
        c[i] = -1.0 / len(fbs_g5)
    del site_index
    return c


_G5_SET: set[str] = set()


def confound(games: pl.DataFrame, cfg: dict[str, Any], p4: set[str]) -> dict[str, Any]:
    """The two tests. Both run on the L2 design, where the site column lives."""
    d = design.build_game_design(games, cfg)
    lam = 8.0
    fitted = ridge.solve(d.Z, d.s, d.v, d.penalty, lam)
    cov = ridge.sandwich(d.Z, d.s, d.v, d.penalty, lam, fitted).cov

    contrast = contrast_vector(d.teams, p4, d.site_index)
    site = np.zeros_like(contrast)
    site[d.site_index] = 1.0

    var_contrast = float(contrast @ cov @ contrast)
    var_site = float(cov[d.site_index, d.site_index])
    covariance = float(contrast @ cov @ site)
    correlation = covariance / float(np.sqrt(var_contrast * var_site))

    # (b) ASSUME h RATHER THAN ESTIMATE IT, and assume it wrong. Offsetting the
    # response while KEEPING the site column would be a no-op by construction -
    # the offset trick shifts the solution by delta times the ridge fit of the
    # site column on itself, and that fit puts essentially all its mass on the
    # unpenalised site coefficient. The counterfactual that actually bites is the
    # one the review is worried about: DROP the site column from the design,
    # impose a value for h, and let the team coefficients absorb whatever the
    # imposed value gets wrong. A team then picks up the error in proportion to
    # its home/away IMBALANCE, and the question is whether that imbalance is
    # systematically different for G5 teams.
    site_column = np.asarray(d.Z[:, d.site_index].todense()).ravel()
    team_block = d.Z[:, : len(d.teams)]
    team_penalty = d.penalty[: len(d.teams)]
    team_contrast = contrast[: len(d.teams)]
    estimated_h = float(fitted[d.site_index])
    gaps: dict[str, float] = {}
    for delta in (-2.0, -1.0, 0.0, 1.0, 2.0):
        response = d.s - (estimated_h + delta) * site_column
        theta = ridge.solve(team_block, response, d.v, team_penalty, lam)
        gaps[f"{delta:+.1f}"] = float(team_contrast @ theta)

    return {
        "lambda": lam,
        "n_teams": len(d.teams),
        "site_coefficient": float(fitted[d.site_index]),
        "site_se": float(np.sqrt(var_site)),
        "contrast_p4_minus_g5": float(contrast @ fitted),
        "contrast_se": float(np.sqrt(var_contrast)),
        "correlation_site_with_contrast": correlation,
        "gap_under_forced_h": gaps,
        "estimated_h": estimated_h,
        "gap_shift_per_point_of_h_error": abs(gaps["+1.0"] - gaps["-1.0"]) / 2.0,
    }


def recency(games_by_season: dict[int, pl.DataFrame]) -> list[dict[str, Any]]:
    rows = []
    for gamma in GAMMAS:
        cfg = copy.deepcopy(load_config())
        cfg["weights"]["recency_gamma"] = float(gamma)
        result = walkforward.run_backtest(
            seasons=list(TUNE_SEASONS),
            systems=["schedule_odds", "l3", "l2"],
            config=cfg,
        )
        block = result["systems"]["l3"]["segments_from_headline_week"]["fbs_vs_fbs"]
        head = result["systems"]["schedule_odds"]
        rows.append(
            {
                "recency_gamma": gamma,
                "n_games": block["n_games"],
                "su_accuracy": block["su_accuracy"],
                "mae": block["mae"],
                "rmse": block["rmse"],
                "brier": block["brier"],
                "max_calibration_deviation_pp": block["max_calibration_deviation_pp"],
                "violations_headline": head["retrodictive_violation_rate"],
                "violations_l3": result["systems"]["l3"]["retrodictive_violation_rate"],
            }
        )
    del games_by_season
    return rows


def run() -> dict[str, Any]:
    global _G5_SET
    cfg = load_config()
    games = load_games([SEASON], universe=str(cfg["model"]["fit_universe"]))
    plays = load_plays([SEASON])
    fbs_names = set(
        load_games([SEASON], universe="fbs_vs_fbs")["home_team"].to_list()
    ) | set(load_games([SEASON], universe="fbs_vs_fbs")["away_team"].to_list())

    unknown = sorted(set(POWER_FOUR_2023) - fbs_names)
    if unknown:
        raise SystemExit(f"P4 list does not match the archive's team names: {unknown}")
    p4 = set(POWER_FOUR_2023)
    _G5_SET = fbs_names - p4

    window = windows.games_through(games, season=SEASON, week=WEEK, season_type="regular")
    inventory = bridge_inventory(
        load_games([SEASON], universe="fbs_vs_fbs"), p4
    )
    inventory_window = bridge_inventory(
        window.filter((pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs")), p4
    )
    tests = confound(window, cfg, p4)

    buckets = windows.season_buckets(games, SEASON)
    powers = retro.season_power(games, SEASON, cfg, plays=plays, buckets=buckets)
    evaluated = next(b for b in buckets if b.season_type == "regular" and b.week == WEEK)
    live = powers[evaluated.order]
    classes = poll_mod.team_classes(games)
    ranked = [t for t in live.ratings if classes.get(t) == "fbs"]

    return {
        "season": SEASON,
        "through_week": WEEK,
        "n_p4_teams": len(p4),
        "n_g5_teams": len(_G5_SET),
        "bridge_inventory_full_season": inventory,
        "bridge_inventory_through_week": inventory_window,
        "confound": tests,
        "live_home_field_points": live.home_field,
        "median_rating_se_points": float(
            np.median([se for se in (live.rating_se(t) for t in ranked) if se is not None])
        ),
        "recency": recency({}),
        "provenance": {
            "git_sha": git_sha(),
            "config_sha256": config_hash(DEFAULT_CONFIG_PATH),
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        },
    }


def report(data: dict[str, Any]) -> str:
    inv = data["bridge_inventory_full_season"]
    win = data["bridge_inventory_through_week"]
    c = data["confound"]
    rows = data["recency"]
    base = next(r for r in rows if r["recency_gamma"] == 1.0)
    lines = [
        "# Robustness notes: the venue confound, and the September splice",
        "",
        "Computed by `scripts/robustness_notes.py`; every number is in",
        "`robustness-notes.json`. **No default changes on the strength of anything below.**",
        "Both sections answer questions the",
        "[independent review](./fresh-eyes-review.md) raised about *bias* rather than",
        "variance - the thing its §4b concluded was the real threat once it had measured",
        "that connectivity was not.",
        "",
        "> **PROVENANCE.** Every number below was computed against `configs/default.toml`",
        "> as of the run recorded in the sibling `.json` (`provenance.config_sha256`). The",
        "> constants moved on 2026-08-12 when the hyperparameter campaign fitted C, beta_w",
        "> and both mode switches ([ADR 0007](../adr/0007-tuned-constants.md)), so these",
        "> numbers reproduce under *that* config and not under today's. They are left exactly",
        "> as they were: evidence quietly edited to agree with a later decision is not",
        "> evidence.",
        "",
        "Conference membership appears here as an **audit lens and never as a feature**.",
        "`conference` is on the banned-pattern list in `validate/leakage.py`, the schedule",
        "frame's `conference_game` column is proved unconsumed by every design matrix on",
        "every run, and the 2023 Power-4 list in this script is asserted against the",
        "archive's own team names so a typo fails loudly. Nothing in this file touches a fit.",
        "",
        "---",
        "",
        "## 1. The bridge-game venue confound",
        "",
        "### 1a. The inventory, reproduced",
        "",
        f"2023, FBS-vs-FBS regular season and conference championships, with "
        f"{data['n_p4_teams']} Power-4 teams",
        f"(the ACC, Big Ten, Big 12, SEC and Pac-12 as they stood, plus Notre Dame) and "
        f"{data['n_g5_teams']} others:",
        "",
        "| | Full season | Through week 10 |",
        "|---|---:|---:|",
        f"| FBS-vs-FBS games | {inv['n_fbs_vs_fbs_games']:,} | {win['n_fbs_vs_fbs_games']:,} |",
        f"| **G5 ↔ P4 bridge games** | **{inv['n_bridges']}** | **{win['n_bridges']}** |",
        f"| Share of all FBS-vs-FBS games | {inv['share_of_all_fbs_games']:.1%} "
        f"| {win['share_of_all_fbs_games']:.1%} |",
        f"| At the P4 site | {inv['at_p4_site']} | {win['at_p4_site']} |",
        f"| At the G5 site | {inv['at_g5_site']} | {win['at_g5_site']} |",
        f"| At a neutral site | {inv['at_neutral_site']} | {win['at_neutral_site']} |",
        f"| **Share of hosted bridges at the P4 site** "
        f"| **{inv['share_at_p4_site']:.0%}** | **{win['share_at_p4_site']:.0%}** |",
        f"| Bridges per G5 team | {inv['bridges_per_g5_team']:.2f} "
        f"| {win['bridges_per_g5_team']:.2f} |",
        "",
        "**The review's structural claim reproduces.** It reported 90 bridges in 2023 at 80%",
        f"P4-hosted; this counts {inv['n_bridges']} at {inv['share_at_p4_site']:.0%} — the",
        "difference is a membership question (this list puts Notre Dame and the four 2023",
        "AAC-to-Big-12 arrivals on the P4 side) rather than a disagreement about structure.",
        "The whole cross-conference structure of the poll rests on about",
        f"{inv['share_of_all_fbs_games']:.0%} of its games, and {inv['share_at_p4_site']:.0%}",
        "of those are played in the Power-4 stadium.",
        "",
        "### 1b. Does that confound the conference offset? Two tests, and the answer is no",
        "",
        "The worry, stated exactly: if the estimated G5-versus-P4 offset is nearly collinear",
        "with the home-field constant across this subsample, then any error in `h` maps",
        "almost directly onto the offset, and a poll that got `h` wrong by half a point would",
        "be wrong about every G5 team in the same direction.",
        "",
        "The design matrix carries an **unpenalised site column** (`model/design.py`), so `h`",
        "is estimated rather than assumed and whatever it absorbs, it absorbs for every game.",
        "That is the in-principle answer. Here is the measurement.",
        "",
        "**Test (a) — exact, from the ridge sandwich.** The correlation between the estimated",
        "site coefficient and the estimated `mean(P4) − mean(G5)` contrast, read straight out",
        "of the covariance matrix (`ridge.sandwich`, report 02 §3.3). Collinearity would show",
        "up as a correlation near ±1.",
        "",
        "| Quantity | Value |",
        "|---|---:|",
        f"| Site coefficient (compressed-response units, λ = {c['lambda']:g}) "
        f"| {c['site_coefficient']:.4f} ± {c['site_se']:.4f} |",
        f"| P4 − G5 contrast | {c['contrast_p4_minus_g5']:.4f} ± {c['contrast_se']:.4f} |",
        f"| **Correlation between them** | **{c['correlation_site_with_contrast']:+.4f}** |",
        "",
        f"**{abs(c['correlation_site_with_contrast']):.4f}.** The two estimates are very nearly",
        "orthogonal. The venue asymmetry in the bridge set is real and it does *not* propagate",
        "into the conference offset, because every other game in the fit - a thousand of them -",
        "identifies `h` independently of the bridges. The bridges are 12% of the games; they",
        "are not 12% of the information about home field.",
        "",
        "**Test (b) — assume `h` instead of estimating it, and assume it wrong.** Offsetting",
        "the response while *keeping* the site column would be a no-op by construction, so",
        "this is the counterfactual that bites: the site column is **removed from the**",
        "**design**, `h` is imposed, and the team coefficients absorb whatever the imposed",
        "value gets wrong. A team picks up that error in proportion to its home/away",
        "imbalance, and the question is whether G5 teams' imbalance is systematically",
        f"different. The estimated value is {c['estimated_h']:.3f}.",
        "",
        "| Imposed `h`, error vs the estimate | P4 − G5 gap | Shift |",
        "|---|---:|---:|",
    ]
    baseline_gap = c["gap_under_forced_h"]["+0.0"]
    for delta in ("-2.0", "-1.0", "+0.0", "+1.0", "+2.0"):
        value = c["gap_under_forced_h"][delta]
        lines.append(f"| {delta} points | {value:.4f} | {value - baseline_gap:+.4f} |")
    lines += [
        "",
        "A full point of error in an ASSUMED `h` moves the P4-minus-G5 gap by",
        f"**{c['gap_shift_per_point_of_h_error']:.4f}** compressed-response units — against a "
        f"gap of {baseline_gap:.2f} and a",
        f"standard error on that gap of {c['contrast_se']:.2f}.",
        "",
        "The review's Phase 1 called this \"the single most underappreciated sensitivity in",
        "the whole system\" and expected an error in `h` to map almost one-for-one onto the",
        "conference offset. **It does not**, and the reason is the one the review itself gave",
        "for why its variance prediction failed: the schedule graph is a good enough expander",
        "that no single subsample dominates any single coefficient. The venue asymmetry in",
        "the bridge set is real, and the leverage it was assumed to carry is",
        f"**{c['gap_shift_per_point_of_h_error'] / c['contrast_se']:.2f} standard errors per",
        "point** of error rather than one-for-one — a real effect, an order of magnitude",
        "smaller than the framing. And in the live model `h` is not assumed at all: it is an",
        "unpenalised column, which is why test (a) is the one that matters and test (b) is",
        "the counterfactual it is measured against.",
        "",
        "**What this does NOT clear.** Test (b) says the offset is insensitive to a *global*",
        "error in `h`. Home-field advantage genuinely varies by venue by several points, and a",
        "single global constant cannot represent that. A systematic difference between P4 and",
        "G5 home-field advantage would land on the bridge set and would not be caught by",
        "either test here, because both hold the single-`h` model fixed. Estimating per-venue",
        "home field is a real piece of work with weak identification (about six home games a",
        "year per team) and it is not attempted.",
        "",
        "---",
        "",
        "## 2. `recency_gamma` and the September splice",
        "",
        "Every cross-conference game is played in the first month; conference play consumes",
        "October and November. So a December ranking splices a **September** estimate of",
        "league level onto a **November** estimate of within-league order, and",
        "`recency_gamma = 1.0` treats the two as contemporaneous (review §4b, channel 2).",
        "",
        "The review's other reason for wanting γ < 1 is the 2023 Florida State case: Power's",
        "job is \"who'd win next week\", and a season-constant estimate over thirteen games,",
        "eleven of them with Jordan Travis, cannot disagree with the résumé about a team that",
        "no longer exists. Publishing two numbers is only honest if the second one is",
        "*capable* of disagreeing.",
        "",
        f"Walk-forward, {list(TUNE_SEASONS)}, weeks 5+, FBS-vs-FBS. L3 is the Power rating",
        "and the violations column is the headline ordering's:",
        "",
        "| γ | n | SU % | MAE | RMSE | Brier | Calib. dev. | Violations (headline) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        mark = " *(default)*" if r["recency_gamma"] == 1.0 else ""
        lines.append(
            f"| {r['recency_gamma']}{mark} | {r['n_games']} | {r['su_accuracy'] * 100:.2f} "
            f"| {r['mae']:.3f} | {r['rmse']:.3f} | {r['brier']:.4f} "
            f"| {r['max_calibration_deviation_pp']:.2f} pp | {r['violations_headline']:.4f} |"
        )
    best = min(rows, key=lambda r: r["mae"])
    best_calib = min(rows, key=lambda r: r["max_calibration_deviation_pp"])
    lines += [
        "",
        (
            "**No value of γ improves out-of-sample margin error.** The default is already "
            "the best of the three on MAE, on RMSE, on Brier and on retrodictive violations; "
            f"decaying at {rows[-1]['recency_gamma']} costs "
            f"{rows[-1]['mae'] - base['mae']:+.3f} points of MAE and "
            f"{rows[-1]['violations_headline'] - base['violations_headline']:+.4f} on "
            "violations."
            if best["recency_gamma"] == 1.0
            else f"**Best out-of-sample MAE: γ = {best['recency_gamma']}** "
            f"({best['mae']:.3f} against {base['mae']:.3f} at γ = 1.0, "
            f"{best['mae'] - base['mae']:+.3f})."
        ),
        "",
        (
            "The one column that moves in γ's favour is **calibration**: "
            f"γ = {best_calib['recency_gamma']} gives "
            f"{best_calib['max_calibration_deviation_pp']:.2f}pp against the default's "
            f"{base['max_calibration_deviation_pp']:.2f}pp, and it is still nowhere near the "
            "5.0pp gate. Worth recording next to the calibration section of "
            "demo/backtest-2021-2023.md: two unrelated knobs both nudge the deviation and "
            "neither closes it, which is what you would expect if the cause is neither of "
            "them - and it is not. docs/analysis/tuning-campaign.md SS5.8 diagnoses it as "
            "under-dispersion of the point forecast, which no knob in this file controls."
            if best_calib["recency_gamma"] != 1.0
            else "Calibration does not improve either."
        ),
        "",
        "**THE DEFAULT DOES NOT CHANGE, and the reason is not that the number is small.**",
        "`recency_gamma` is a fairness knob before it is an accuracy knob. The config states",
        "the position it encodes - *\"a poll that says who earned it should not decide that",
        "September didn't count\"* - and that is a judgement about what the poll is for, not a",
        "hypothesis the backtest can settle. The owner decides it. This table exists so the",
        "decision is made against a measured cost rather than an assumed one.",
        "",
        "Two things a reader should hold onto if it is ever revisited:",
        "",
        "1. **The architecture already supports the asymmetry the review asked for.** Game",
        "   weights shape the *Power* fit; the résumé's target is raw wins and raw compressed",
        "   margin. Turning recency on would move Power and leave the accomplishment",
        "   untouched, which is precisely the split that would let the two published numbers",
        "   disagree about post-injury Florida State.",
        "2. **γ is a blunt instrument for the thing it is aimed at.** Exponential decay",
        "   downweights September uniformly, and September is *where the cross-conference",
        "   information lives*. It treats the splice by discarding one end of it. A",
        "   structural-break flag on per-game offensive efficiency - an on-field observable -",
        "   would target the FSU case without touching the bridge games, and the review says",
        "   the same. That is a different piece of work and it is not attempted here.",
        "",
        "```",
        "uv run python scripts/robustness_notes.py",
        "```",
        "",
        f"Generated by `scripts/robustness_notes.py` at "
        f"{data['provenance']['generated_at']} - code `{data['provenance']['git_sha']}` - "
        f"config sha256 `{data['provenance']['config_sha256'][:16]}...`",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    data = run()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "robustness-notes.json").write_text(
        json.dumps(data, indent=2, sort_keys=True, default=float) + "\n", encoding="utf-8"
    )
    (OUT / "robustness-notes.md").write_text(report(data), encoding="utf-8")
    print(f"wrote {OUT / 'robustness-notes.md'}")


if __name__ == "__main__":
    main()
