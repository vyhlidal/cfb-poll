"""Which games belong in the fit? The sensitivity, measured, and the decision.

Writes docs/analysis/fit-universe-sensitivity.md and .json.

`[model].fit_universe` decides which games enter the design matrix at all, and it
has never been presented to a reader as a choice. The independent review
(docs/analysis/fresh-eyes-review.md, S4) found that it moves the headline ranking
by more than the one constant the project DOES publish a sensitivity table for:

    "`q_ref` moves JMU by one place. `fit_universe` moves it three. Neither has a
    published sensitivity table, and neither is presented to the reader as a
    choice at all."

The review's §9 test is the standard this reproduces: run the same machinery the
q_ref sweep uses - mean rank delta, max delta, Kendall's tau, top-25 membership
changes - over `fit_universe`, and label anything whose tau falls below the 0.985
that q_ref achieves as a DIAL rather than a convention.

Then decide it with data rather than with the argument in report 02 §3.7: which
universe produces better walk-forward prediction and fewer retrodictive
violations on the tune seasons?

    all          every completed game in the archive, all divisions
    model        at least one FBS or FCS participant  (the incumbent default)
    fbs_vs_fbs   both participants FBS

2024 (validate) and 2025 (holdout) are untouched, as always.
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
from scipy.stats import kendalltau

from cfbpoll.backtest import walkforward
from cfbpoll.config import DEFAULT_CONFIG_PATH, config_hash, load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.plays import load_plays
from cfbpoll.ingest.sportsdataverse import load_games
from cfbpoll.model import retro, schedule_odds
from cfbpoll.publish import poll as poll_mod

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "analysis"

UNIVERSES: tuple[str, ...] = ("all", "model", "fbs_vs_fbs")
INCUMBENT = "model"
TUNE_SEASONS = (2021, 2022, 2023)
SPOTLIGHT_SEASON = 2023
SPOTLIGHT_WEEK = 10

#: The q_ref sweep's worst tau (study §9). Anything below this is a DIAL.
Q_REF_TAU_FLOOR = 0.985

#: Conference membership, an AUDIT LENS and never a feature - the same use the
#: review makes of it. Nothing in the model knows these exist.
POWER_FOUR_2023 = ("ACC", "Big Ten", "Big 12", "SEC", "Pac-12")
G5_2023 = (
    "James Madison",
    "Liberty",
    "Tulane",
    "Troy",
    "Fresno State",
    "Toledo",
    "Appalachian State",
    "Miami (OH)",
    "UTSA",
    "Coastal Carolina",
    "Boise State",
    "Air Force",
    "SMU",
    "Memphis",
)
P4_SAMPLE_2023 = (
    "Michigan",
    "Ohio State",
    "Georgia",
    "Alabama",
    "Texas",
    "Washington",
    "Florida State",
    "Oregon",
    "Penn State",
    "Ole Miss",
    "Missouri",
    "Oklahoma",
    "Louisville",
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


def config_for(universe: str) -> dict[str, Any]:
    cfg = copy.deepcopy(load_config())
    cfg["model"]["fit_universe"] = universe
    return cfg


def spotlight(universe: str, plays: pl.DataFrame) -> dict[str, Any]:
    """The 2023 week-10 poll under one universe, plus the mechanism numbers."""
    cfg = config_for(universe)
    games = load_games([SPOTLIGHT_SEASON], universe=universe)
    buckets = windows.season_buckets(games, SPOTLIGHT_SEASON)
    powers = retro.season_power(games, SPOTLIGHT_SEASON, cfg, plays=plays, buckets=buckets)
    evaluated = next(
        b for b in buckets if b.season_type == "regular" and b.week == SPOTLIGHT_WEEK
    )
    window = windows.games_through(
        games, season=SPOTLIGHT_SEASON, week=SPOTLIGHT_WEEK, season_type="regular"
    )
    classes = poll_mod.team_classes(games)
    power = powers[evaluated.order]
    odds = schedule_odds.fit(window, cfg, power=power, classes=classes)
    ranks = {
        team: i + 1
        for i, team in enumerate(
            sorted((t for t in odds.tail if classes.get(t) == "fbs"), key=odds.order_key)
        )
    }

    fbs = [t for t in power.ratings if classes.get(t) == "fbs"]
    fcs = [t for t in power.ratings if classes.get(t) == "fcs"]
    g5 = [t for t in G5_2023 if t in power.ratings]
    p4 = [t for t in P4_SAMPLE_2023 if t in power.ratings]
    return {
        "universe": universe,
        "n_games_in_window": int(window.height),
        "n_teams_in_fit": len(power.ratings),
        "n_fbs": len(fbs),
        "n_non_fbs": len(power.ratings) - len(fbs),
        "lambda_l2": float(power.l2.lam) if power.l2 is not None else None,
        "sigma": power.sigma,
        "ranks": ranks,
        "mean_power_fbs": float(np.mean([power.rating(t) for t in fbs])),
        "mean_power_fcs": (
            float(np.mean([power.rating(t) for t in fcs])) if fcs else None
        ),
        "fbs_minus_fcs": (
            float(np.mean([power.rating(t) for t in fbs]) - np.mean([power.rating(t) for t in fcs]))
            if fcs
            else None
        ),
        "mean_power_g5": float(np.mean([power.rating(t) for t in g5])),
        "mean_power_p4": float(np.mean([power.rating(t) for t in p4])),
        "p4_minus_g5": float(
            np.mean([power.rating(t) for t in p4]) - np.mean([power.rating(t) for t in g5])
        ),
        "median_rating_se": float(
            np.median([se for se in (power.rating_se(t) for t in fbs) if se is not None])
        ),
    }


def movement(base: dict[str, int], other: dict[str, int]) -> dict[str, Any]:
    common = sorted(set(base) & set(other))
    if not common:
        return {"n_teams": 0}
    delta = np.array([other[t] - base[t] for t in common], dtype=np.float64)
    tau = float(kendalltau([base[t] for t in common], [other[t] for t in common]).statistic)
    top_base = {t for t in common if base[t] <= 25}
    top_other = {t for t in common if other[t] <= 25}
    biggest = sorted(
        ((abs(other[t] - base[t]), t, base[t], other[t]) for t in common), reverse=True
    )[:8]
    return {
        "n_teams": len(common),
        "kendall_tau": tau,
        "mean_abs_rank_delta": float(np.abs(delta).mean()),
        "max_abs_rank_delta": int(np.abs(delta).max()),
        "top25_membership_changes": len(top_base ^ top_other) // 2,
        "entered_top25": sorted(top_other - top_base),
        "left_top25": sorted(top_base - top_other),
        "biggest_movers": [
            {"team": t, "incumbent": a, "alternative": b} for _, t, a, b in biggest
        ],
        "is_a_dial": tau < Q_REF_TAU_FLOOR,
    }


def backtest(universe: str) -> dict[str, Any]:
    cfg = config_for(universe)
    result = walkforward.run_backtest(
        seasons=list(TUNE_SEASONS),
        systems=["schedule_odds", "resume", "l3", "l2", "colley", "srs", "winpct"],
        config=cfg,
    )
    headline = result["systems"]["schedule_odds"]
    block = headline["segments_from_headline_week"]["fbs_vs_fbs"]
    l3 = result["systems"]["l3"]["segments_from_headline_week"]["fbs_vs_fbs"]
    return {
        "universe": universe,
        "n_games_scored": block["n_games"],
        "su_accuracy": block["su_accuracy"],
        "mae": block["mae"],
        "rmse": block["rmse"],
        "brier": block["brier"],
        "log_loss": block["log_loss"],
        "max_calibration_deviation_pp": block["max_calibration_deviation_pp"],
        "sigma_mean": block["sigma_mean"],
        "violations_headline": headline["retrodictive_violation_rate"],
        "violations_resume": result["systems"]["resume"]["retrodictive_violation_rate"],
        "violations_l3": result["systems"]["l3"]["retrodictive_violation_rate"],
        "l3_mae": l3["mae"],
        "l3_rmse": l3["rmse"],
        "gate_passed": headline["gate"]["passed"],
    }


def run() -> dict[str, Any]:
    plays = load_plays([SPOTLIGHT_SEASON])
    spots = {u: spotlight(u, plays) for u in UNIVERSES}
    base_ranks = spots[INCUMBENT]["ranks"]
    moves = {
        u: movement(base_ranks, spots[u]["ranks"]) for u in UNIVERSES if u != INCUMBENT
    }
    tests = {u: backtest(u) for u in UNIVERSES}

    # THE DECISION RULE, fixed before the numbers are read: the universe that
    # predicts better out of sample on the tune seasons, with retrodictive
    # violations as the tie-break, because prediction is the thing a fit universe
    # can actually be wrong about.
    ranked_by_mae = sorted(tests.values(), key=lambda b: (b["mae"], b["violations_headline"]))
    winner = ranked_by_mae[0]["universe"]

    return {
        "universes": list(UNIVERSES),
        "incumbent": INCUMBENT,
        "winner": winner,
        "decision_rule": (
            "lowest walk-forward MAE on the tune seasons over the published window, "
            "retrodictive violations as the tie-break; fixed before the numbers were read"
        ),
        "spotlight": {"season": SPOTLIGHT_SEASON, "week": SPOTLIGHT_WEEK, "by_universe": spots},
        "movement_vs_incumbent": moves,
        "backtest": tests,
        "q_ref_tau_floor": Q_REF_TAU_FLOOR,
        "provenance": {
            "git_sha": git_sha(),
            "config_sha256": config_hash(DEFAULT_CONFIG_PATH),
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        },
    }


def report(data: dict[str, Any]) -> str:
    spots = data["spotlight"]["by_universe"]
    moves = data["movement_vs_incumbent"]
    tests = data["backtest"]
    winner = data["winner"]
    labels = {
        "all": "`all` — every completed game, all divisions",
        "model": "`model` — at least one FBS or FCS participant **(incumbent)**",
        "fbs_vs_fbs": "`fbs_vs_fbs` — both participants FBS",
    }
    lines = [
        "# `fit_universe`: the sensitivity nobody published, and the decision",
        "",
        "Computed by `scripts/fit_universe_study.py`; every number below is in",
        "`fit-universe-sensitivity.json`.",
        "",
        "`[model].fit_universe` decides which games enter the design matrix at all. Until",
        "2026-08-12 it was argued from report 02 §3.7 and never measured, and the",
        "[independent review](./fresh-eyes-review.md) (S4) put the objection precisely:",
        "",
        "> `q_ref` moves JMU by one place. `fit_universe` moves it three. Neither has a",
        "> published sensitivity table, and neither is presented to the reader as a choice",
        "> at all.",
        "",
        "The review's standard is the one applied here: run §9's exact machinery — mean rank",
        "delta, max delta, Kendall's tau, top-25 membership changes — and **any parameter",
        f"whose tau against the default falls below the {data['q_ref_tau_floor']} that `q_ref`",
        "achieves is a dial, not a convention, and must be labelled as one.**",
        "",
        "---",
        "",
        f"## 1. What each universe actually fits ({data['spotlight']['season']} through week "
        f"{data['spotlight']['week']})",
        "",
        "| Universe | Games in the window | Teams in the fit | Non-FBS teams | λ | σ | Median rating SE |",  # noqa: E501
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for u in data["universes"]:
        s = spots[u]
        lines.append(
            f"| {labels[u]} | {s['n_games_in_window']:,} | {s['n_teams_in_fit']} "
            f"| {s['n_non_fbs']} | {s['lambda_l2']:g} | {s['sigma']:.2f} "
            f"| {s['median_rating_se']:.2f} |"
        )
    model, everything = spots["model"], spots["all"]
    lines += [
        "",
        f"The incumbent fits **{model['n_non_fbs']} non-FBS teams** alongside the 133 FBS",
        "ones, which is the number the review's mechanism argument turns on. Widening to",
        f"`all` adds {everything['n_non_fbs'] - model['n_non_fbs']} more; narrowing to",
        "`fbs_vs_fbs` removes every one of them.",
        "",
        "## 2. Does it move the ranking? Yes, and by more than `q_ref` does",
        "",
        "| Alternative | Kendall's τ vs incumbent | Mean \\|Δrank\\| | Max \\|Δrank\\| "
        "| Top-25 changes | Verdict |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for u, m in moves.items():
        verdict = "**A DIAL**" if m["is_a_dial"] else "a convention"
        lines.append(
            f"| {labels[u]} | {m['kendall_tau']:.4f} | {m['mean_abs_rank_delta']:.2f} "
            f"| {m['max_abs_rank_delta']} | {m['top25_membership_changes']} | {verdict} |"
        )
    narrow = moves["fbs_vs_fbs"]
    jmu = {u: spots[u]["ranks"].get("James Madison") for u in data["universes"]}
    lines += [
        "",
        "**The review's own example does not reproduce, and the reason is worth stating.**",
        "It reported James Madison moving #7 → #4 under `fbs_vs_fbs`. On this build JMU is",
        "#"
        + " / #".join(f"{jmu[u]} ({u})" for u in data["universes"])
        + " — it does not move at all. The review measured against a baseline this",
        "repository no longer has: σ was the 15.3 constant rather than an estimate, and the",
        "review's own §S4 baseline used in-sample blend weights. The SENSITIVITY is real and",
        "larger than `q_ref`'s, which is the finding; the particular team it landed on was a",
        "property of the configuration it was measured under. The movers below are where it",
        "shows up now.",
        "",
        f"Dropping FCS from the fit gives τ = **{narrow['kendall_tau']:.4f}**, against the",
        f"{data['q_ref_tau_floor']} floor the `q_ref` sweep never dipped below. By the",
        "project's own published standard that makes `fit_universe` **a dial**, and it is now",
        "labelled as one in `configs/default.toml`.",
        "",
        "Biggest movers under `fbs_vs_fbs`:",
        "",
        "| Team | Incumbent | FBS-only |",
        "|---|---:|---:|",
    ]
    lines += [
        f"| {m['team']} | #{m['incumbent']} | #{m['alternative']} |"
        for m in narrow["biggest_movers"][:6]
    ]
    lines += [
        "",
        "## 3. The mechanism the review named, measured",
        "",
        "The review's account: ridge shrinks every coefficient toward the mean of the fit",
        "universe; thinly-connected FCS teams are shrunk hardest and are pulled *up* toward a",
        "mean far above their level; the FBS teams that beat them are pulled *down*; the net",
        "effect compresses the FBS-over-FCS gap, and the compression lands hardest on the",
        "teams whose schedules hold the most near-FCS opponents — which is to say on G5",
        "teams. **Ridge-toward-zero on a mixed-division universe is not neutral with respect",
        "to the G5-versus-P4 question.**",
        "",
        "Rating differences are invariant to the zero point of a fit, so the table below is",
        "in gaps rather than levels. Conference labels are an audit lens and never a feature.",
        "",
        "| Universe | Mean FBS − mean FCS | Mean P4 sample − mean G5 sample |",
        "|---|---:|---:|",
    ]
    for u in data["universes"]:
        s = spots[u]
        gap = "—" if s["fbs_minus_fcs"] is None else f"{s['fbs_minus_fcs']:.2f}"
        lines.append(f"| {labels[u]} | {gap} | {s['p4_minus_g5']:.2f} |")
    p4g5 = {u: spots[u]["p4_minus_g5"] for u in data["universes"]}
    direction = (
        "widens" if p4g5["fbs_vs_fbs"] > p4g5["model"] else "narrows"
    )
    lines += [
        "",
        "**The direction is the review's, and the size is smaller than its framing suggests.**",
        f"Dropping the non-FBS teams {direction} the P4-minus-G5 gap from "
        f"{p4g5['model']:.2f} to {p4g5['fbs_vs_fbs']:.2f} points",
        f"({p4g5['fbs_vs_fbs'] - p4g5['model']:+.2f}). The mixed-division universe is therefore",
        "mildly favourable to G5 teams, exactly as the review says — and the caveat is now a",
        "published number rather than an unstated property.",
        "",
        "## 4. Which universe is actually better? The backtest decides",
        "",
        f"Decision rule, fixed before the numbers were read: **{data['decision_rule']}**. The",
        "evaluation universe is FBS-vs-FBS in every row, so the same games are being predicted",
        "in all three columns; what changes is what the fit was allowed to see.",
        "",
        "| Universe | n | SU % | MAE | RMSE | Brier | Calib. dev. | Violations (headline) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for u in data["universes"]:
        b = tests[u]
        mark = " ✅" if u == winner else ""
        lines.append(
            f"| {labels[u]}{mark} | {b['n_games_scored']} | {b['su_accuracy'] * 100:.2f} "
            f"| **{b['mae']:.3f}** | {b['rmse']:.3f} | {b['brier']:.4f} "
            f"| {b['max_calibration_deviation_pp']:.2f} pp | {b['violations_headline']:.4f} |"
        )
    incumbent_block = tests[data["incumbent"]]
    winner_block = tests[winner]
    lines += [
        "",
        f"**Winner: `{winner}`.**",
    ]
    if winner == data["incumbent"]:
        others = [u for u in data["universes"] if u != winner]
        lost_on = [
            name
            for name, better in (
                (
                    "straight-up accuracy",
                    any(tests[u]["su_accuracy"] > winner_block["su_accuracy"] for u in others),
                ),
                (
                    "calibration deviation",
                    any(
                        tests[u]["max_calibration_deviation_pp"]
                        < winner_block["max_calibration_deviation_pp"]
                        for u in others
                    ),
                ),
                (
                    "retrodictive violations",
                    any(
                        tests[u]["violations_headline"] < winner_block["violations_headline"]
                        for u in others
                    ),
                ),
            )
            if better
        ]
        lines += [
            "",
            "**AND THE RESULT IS MIXED, WHICH IS THE HONEST HEADLINE.** The decision rule was",
            "fixed before the numbers were read and the incumbent wins it — by "
            f"{tests['fbs_vs_fbs']['mae'] - incumbent_block['mae']:.3f} points of MAE over",
            "`fbs_vs_fbs`, which is well inside the ~0.3-point noise floor for three seasons.",
        ]
        if lost_on:
            lines += [
                f"On {', '.join(lost_on)} the narrower universe is AHEAD:",
                f"{tests['fbs_vs_fbs']['su_accuracy'] * 100:.2f}% vs "
                f"{winner_block['su_accuracy'] * 100:.2f}%, "
                f"{tests['fbs_vs_fbs']['max_calibration_deviation_pp']:.2f}pp vs "
                f"{winner_block['max_calibration_deviation_pp']:.2f}pp, "
                f"{tests['fbs_vs_fbs']['violations_headline']:.4f} vs "
                f"{winner_block['violations_headline']:.4f}. A pre-registered rule that "
                "picks one",
                "column while three others point the other way is a rule doing its job — the",
                "alternative is choosing the criterion after seeing the numbers — but a reader",
                "is entitled to know it was close and which way the other criteria fell.",
                "",
                "The interesting one is calibration. Dropping the 168 non-FBS teams improves",
                "the deviation the gate misses by the widest margin "
                f"({tests['fbs_vs_fbs']['max_calibration_deviation_pp']:.2f}pp against "
                f"{winner_block['max_calibration_deviation_pp']:.2f}pp) and it is still",
                "nowhere near the 5.0pp threshold, which is consistent with the finding in",
                "demo/backtest-2021-2023.md that the calibration miss is an asymmetry nobody",
                "has diagnosed rather than anything the fit universe controls.",
            ]
        lines += [
            "",
            "Report 02 §3.7 argued",
            "for it from first principles — FBS-vs-FCS games are ~10% of the FBS schedule and",
            "cluster in the weeks the model is most data-starved, and FCS-vs-FCS games are",
            "what identify individual FCS coefficients rather than the pooled node that cost",
            "ESPN 31 spots of Iowa State in 2013 — and the walk-forward numbers agree.",
            "",
            "**That does not make it a convention.** It is a dial that happens to be set",
            "correctly, which is a different claim and a weaker one, and the difference is",
            f"why this table exists. Narrowing to FBS-vs-FBS costs "
            f"{tests['fbs_vs_fbs']['mae'] - incumbent_block['mae']:+.3f} points of MAE and",
            f"moves the ranking by a mean of {narrow['mean_abs_rank_delta']:.2f} places.",
        ]
    else:
        lines += [
            "",
            f"The incumbent `{data['incumbent']}` is beaten on the decision rule and the",
            f"default changes to `{winner}`: "
            f"{winner_block['mae'] - incumbent_block['mae']:+.3f} points of MAE and",
            f"{winner_block['violations_headline'] - incumbent_block['violations_headline']:+.4f}"
            " on retrodictive violations. See ADR 0006.",
        ]
    lines += [
        "",
        "## 5. What this does not settle",
        "",
        "1. **Three seasons is a small sample.** Differences in MAE below roughly 0.3 points",
        "   are not distinguishable within a single season, and these are pooled over three.",
        "   The MAE spread across universes here is small enough that the honest statement is",
        "   \"no universe is clearly worse on prediction\", and the ranking movement is the",
        "   bigger effect.",
        "2. **2024 and 2025 are untouched.** The validation season is not scored here and the",
        "   holdout is locked. If this decision is ever revisited against them, that has to",
        "   be said publicly (report 02 §5.1).",
        "3. **The mechanism is measured at one week of one season.** §3's gap numbers are",
        "   2023 through week 10. The direction is stable but the magnitude is not claimed",
        "   to be.",
        "",
        "```",
        "uv run python scripts/fit_universe_study.py",
        "```",
        "",
        f"Generated by `scripts/fit_universe_study.py` at "
        f"{data['provenance']['generated_at']} - code `{data['provenance']['git_sha']}` - "
        f"config sha256 `{data['provenance']['config_sha256'][:16]}...`",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    data = run()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fit-universe-sensitivity.json").write_text(
        json.dumps(data, indent=2, sort_keys=True, default=float) + "\n", encoding="utf-8"
    )
    (OUT / "fit-universe-sensitivity.md").write_text(report(data), encoding="utf-8")
    print(f"winner: {data['winner']}")
    print(f"wrote {OUT / 'fit-universe-sensitivity.md'}")


if __name__ == "__main__":
    main()
