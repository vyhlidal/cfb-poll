"""The 2025 holdout scorecard: the single sanctioned scoring pass, written down.

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
        uv run python scripts/make_holdout_scorecard.py

Writes:

    demo/2025-holdout-scorecard.md      the verdict, every criterion, in prose
    demo/2025-holdout-scorecard.json    the same numbers, machine-readable

THIS SCRIPT DOES NOT SCORE ANYTHING. It reads the metrics tree that
`cfbpoll backtest --seasons 2025 --unlock-holdout` already wrote and formats it.
That separation is the point: the scoring pass happened once, by a human typing a
flag, and is recorded in `demo/2025-holdout-run.log` with its command, its git sha
and its timestamp. Re-running this file re-renders a document; it cannot re-run
the test, and it cannot quietly become a loop somebody tunes against.

Everything the document says about WHEN and WITH WHAT the test was run is read out
of that log and out of git at the sha the log names, so re-rendering this file
after the config changes does not move one character of the provenance.

INPUTS, all local, no network:

    out/holdout-2025/backtest_metrics.json   the one-shot run, or its committed
    demo/2025-holdout-metrics.json           copy, which is what a fork reads
    demo/2025-holdout-run.log                the command, the sha and the date
    demo/backtest-2021-2023.json             the tune seasons, for contrast
    out/grid-2025/ratings_{live,hindsight}.parquet   the divergence curve

THE TWO UNDECIDED CRITERIA ARE NOT ADJUDICATED HERE, and that is deliberate.
`brier_beats_all_baselines` and `retro_vs_live_monotone` have been reported as
`null` by `metrics.check_gate` since before the constants were frozen. Deciding
either of them now - after seeing the holdout - would be choosing a rule against
a result, which is the same failure the holdout exists to prevent, one level up.
So this document publishes the EVIDENCE for both in full and leaves the verdict
where the harness leaves it. A successor campaign should pre-register the rule
and then decide them, in that order.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from cfbpoll.config import DEFAULT_CONFIG_PATH, config_hash, load_config

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


def _first(*candidates: Path) -> Path:
    """The first path that exists, or the last one so the error names the fallback."""
    for path in candidates:
        if path.exists():
            return path
    return candidates[-1]


#: THE COMMITTED COPIES ARE THE RECORD. `out/` and `.cache/` are gitignored, so a
#: run log and a metrics tree that lived only there would be a provenance claim
#: nobody outside this machine could check - which is the one thing a single-shot
#: test cannot afford. The originals are preferred when present, because a
#: regeneration on the machine that ran the test should read what that run wrote;
#: the committed copies are the fallback and are what a fork gets.
HOLDOUT_METRICS = _first(
    ROOT / "out" / "holdout-2025" / "backtest_metrics.json",
    DEMO / "2025-holdout-metrics.json",
)
TUNE_METRICS = DEMO / "backtest-2021-2023.json"
GRID_DIR = ROOT / "out" / "grid-2025"
RUN_LOG = _first(ROOT / ".cache" / "holdout-2025.log", DEMO / "2025-holdout-run.log")

#: The house ordering. The gate is written against this system and no other.
HOUSE = "schedule_odds"

#: Which criteria the harness decides, in the order the gate states them.
DECIDABLE: tuple[tuple[str, str, str | None, str | None], ...] = (
    ("su_accuracy", "Straight-up accuracy at or above the floor", "su_accuracy_min", "su_accuracy"),
    ("mae", "Mean absolute error at or below the ceiling", "mae_max", "mae"),
    ("rmse", "Root mean squared error at or below the ceiling", "rmse_max", "rmse"),
    (
        "calibration",
        "Worst decile calibration deviation within tolerance",
        "calibration_max_decile_deviation_pp",
        "max_calibration_deviation_pp",
    ),
    (
        "violations_vs_baselines",
        "Retrodictive violations at or below every scored system",
        "violations_must_beat",
        "retrodictive_violation_rate",
    ),
)

UNDECIDED: tuple[tuple[str, str], ...] = (
    ("brier_beats_all_baselines", "Brier score beats every baseline"),
    ("retro_vs_live_monotone", "Retro-vs-live divergence declines monotonically"),
)


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def _fmt(value: float | None, places: int = 4) -> str:
    return "n/a" if value is None else f"{value:.{places}f}"


def _pct(value: float | None, places: int = 2) -> str:
    return "n/a" if value is None else f"{value * 100:.{places}f}%"


# ------------------------------------------------------------------ the readings


def system_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per scored system, off the published window, FBS-vs-FBS."""
    rows: list[dict[str, Any]] = []
    for name, block in sorted(payload.get("systems", {}).items()):
        segment = (block.get("segments_from_headline_week") or {}).get("fbs_vs_fbs") or {}
        rows.append(
            {
                "system": name,
                "n_games": int(segment.get("n_games") or 0),
                "su_accuracy": _f(segment.get("su_accuracy")),
                "mae": _f(segment.get("mae")),
                "rmse": _f(segment.get("rmse")),
                "brier": _f(segment.get("brier")),
                "log_loss": _f(segment.get("log_loss")),
                "violations": _f(block.get("retrodictive_violation_rate")),
                "rank_churn_mean": _f((block.get("rank_churn") or {}).get("mean_all")),
            }
        )
    return rows


def divergence_curve(grid_dir: Path) -> list[dict[str, Any]]:
    """Mean and max |Δrank| between R(N, N) and R(N, final), per evaluation week.

    The SAME definition the published `divergence.json` uses - every ranked team,
    absolute rank change, per evaluation bucket - computed here off the grid
    rather than off the fixture tree so the scorecard does not depend on the site
    having been published yet.
    """
    live = pl.read_parquet(grid_dir / "ratings_live.parquet")
    hind = pl.read_parquet(grid_dir / "ratings_hindsight.parquet")
    joined = (
        live.filter(pl.col("rank").is_not_null())
        .select("eval_order", "eval_label", "team", "rank")
        .join(
            hind.filter(pl.col("rank").is_not_null()).select(
                "eval_order", "team", pl.col("rank").alias("rank_hindsight")
            ),
            on=["eval_order", "team"],
            how="inner",
        )
        .with_columns(delta=(pl.col("rank") - pl.col("rank_hindsight")).abs())
    )
    curve = (
        joined.group_by("eval_order", "eval_label")
        .agg(
            n_teams=pl.len(),
            mean_abs_delta=pl.col("delta").mean(),
            max_abs_delta=pl.col("delta").max(),
        )
        .sort("eval_order")
    )
    return [
        {
            "eval_order": int(r["eval_order"]),
            "eval_label": str(r["eval_label"]),
            "n_teams": int(r["n_teams"]),
            "mean_abs_delta": float(r["mean_abs_delta"]),
            "max_abs_delta": int(r["max_abs_delta"]),
        }
        for r in curve.to_dicts()
    ]


def monotone_evidence(curve: list[dict[str, Any]], from_label_week: int) -> dict[str, Any]:
    """Where the curve rises, in the published window. EVIDENCE, not a verdict."""
    window = [row for row in curve if row["eval_order"] >= from_label_week]
    rises = [
        {
            "from": window[i - 1]["eval_label"],
            "to": window[i]["eval_label"],
            "mean_abs_delta_from": window[i - 1]["mean_abs_delta"],
            "mean_abs_delta_to": window[i]["mean_abs_delta"],
            "step": window[i]["mean_abs_delta"] - window[i - 1]["mean_abs_delta"],
        }
        for i in range(1, len(window))
        if window[i]["mean_abs_delta"] > window[i - 1]["mean_abs_delta"]
    ]
    return {
        "window_first": window[0]["eval_label"] if window else None,
        "window_last": window[-1]["eval_label"] if window else None,
        "first_mean_abs_delta": window[0]["mean_abs_delta"] if window else None,
        "last_mean_abs_delta": window[-1]["mean_abs_delta"] if window else None,
        "strictly_declining": not rises,
        "rises": rises,
        "verdict": None,
        "why_no_verdict": (
            "`[gate].retro_vs_live_divergence_monotone` has never been wired into "
            "`metrics.check_gate`, which has reported it as undecided since before "
            "the constants were frozen. The criterion does not say whether "
            "'monotone' means strictly, or in the published window, or up to some "
            "tolerance, and picking one of those readings after seeing this curve "
            "would be choosing a rule against a result. The evidence is published "
            "in full; the rule is a successor campaign's to pre-register."
        ),
    }


def brier_evidence(rows: list[dict[str, Any]], baselines: tuple[str, ...]) -> dict[str, Any]:
    """Who beat the house on Brier. EVIDENCE, not a verdict."""
    ours = next((r["brier"] for r in rows if r["system"] == HOUSE), None)
    beaten: dict[str, float] = {}
    lost_to: dict[str, float] = {}
    tied: dict[str, float] = {}
    for row in rows:
        # The home-team floor is excluded for the same reason the violations
        # criterion excludes it: it has no ratings, so beating it measures nothing.
        if row["system"] in (HOUSE, "home_team") or row["brier"] is None or ours is None:
            continue
        if row["brier"] < ours:
            lost_to[row["system"]] = row["brier"]
        elif row["brier"] > ours:
            beaten[row["system"]] = row["brier"]
        else:
            tied[row["system"]] = row["brier"]
    return {
        "house_brier": ours,
        "beaten": dict(sorted(beaten.items())),
        "tied": dict(sorted(tied.items())),
        "lost_to": dict(sorted(lost_to.items())),
        "named_baselines": list(baselines),
        "lost_to_named_baselines": {k: v for k, v in sorted(lost_to.items()) if k in baselines},
        "verdict": None,
        "why_no_verdict": (
            "`[gate].brier_must_beat_all_baselines` has never been wired into "
            "`metrics.check_gate` either, and 'baseline' is not defined anywhere "
            "in the config: the competition systems and this project's own lower "
            "layers are both in the table. Under either reading the house loses, "
            "and the losers are named above, so nothing is being hidden by "
            "leaving the boolean where the harness leaves it."
        ),
    }


# ------------------------------------------------------------------- the artifact


def build() -> dict[str, Any]:
    cfg = load_config()
    holdout = _read(HOLDOUT_METRICS)
    tune = _read(TUNE_METRICS)

    protocol = holdout.get("protocol", {})
    gate_cfg = cfg["gate"]
    house = holdout["systems"][HOUSE]
    gate = house["gate"]
    observed = gate.get("observed") or {}

    rows_2025 = system_table(holdout)
    rows_tune = system_table(tune)
    curve = divergence_curve(GRID_DIR)
    headline_week = int(cfg["publication"]["headline_start_week"])

    criteria: list[dict[str, Any]] = []
    for name, statement, threshold_key, observed_key in DECIDABLE:
        verdict = gate.get(name)
        criteria.append(
            {
                "name": name,
                "statement": statement,
                "threshold_key": threshold_key,
                "threshold": gate_cfg.get(threshold_key),
                "observed": _f(observed.get(observed_key)) if observed_key else None,
                "verdict": "pass" if verdict else "FAIL",
                "decided": True,
            }
        )
    for name, statement in UNDECIDED:
        criteria.append(
            {
                "name": name,
                "statement": statement,
                "threshold_key": None,
                "threshold": None,
                "observed": None,
                "verdict": "undecided",
                "decided": False,
            }
        )

    decided = [c for c in criteria if c["decided"]]
    passed = [c for c in decided if c["verdict"] == "pass"]
    failed = [c for c in decided if c["verdict"] == "FAIL"]

    tune_house = next(r for r in rows_tune if r["system"] == HOUSE)
    house_2025 = next(r for r in rows_2025 if r["system"] == HOUSE)

    return {
        "artifact": "THE 2025 HOLDOUT SCORECARD - the single sanctioned scoring pass",
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scored_at": _scored_at(),
        "scored_with": _scored_with(),
        # The RENDER-time identity, kept clearly apart from the SCORED-time one
        # above. Both are useful and confusing them is how a provenance claim
        # quietly becomes false.
        "rendered_with_git_sha": _git_sha(),
        "rendered_with_config_hash": config_hash(DEFAULT_CONFIG_PATH),
        "rendered_with_config_version": cfg["meta"]["config_version"],
        "season": 2025,
        "system": HOUSE,
        "command": _command(),
        "provenance": {
            "constants_frozen_before_scored": True,
            "frozen_by": [
                "docs/adr/0007-tuned-constants.md (2026-08-12)",
                "docs/adr/0009-accumulation-window.md (2026-08-12)",
            ],
            "tune_seasons": list(cfg["backtest"]["tune_seasons"]),
            "validate_seasons": list(cfg["backtest"]["validate_seasons"]),
            "scored_once": True,
            "claim": (
                "No constant in configs/default.toml was chosen after reading any "
                "number below. The constants were fitted on 2021-2023, validated "
                "once on 2024, and frozen on 2026-08-12; 2025 was scored for the "
                "first time on 2026-08-15 and this document is that result, "
                "published whatever it says. See docs/adr/0012-2025-opens.md."
            ),
        },
        "window": {
            "universe": protocol.get("universe"),
            "headline_start_week": headline_week,
            "walk_forward": protocol.get("walk_forward"),
            "n_games": house_2025["n_games"],
            "description": gate.get("window"),
        },
        "verdict": {
            "passed": bool(gate.get("passed")),
            "n_decidable": len(decided),
            "n_passed": len(passed),
            "n_failed": len(failed),
            "passed_criteria": [c["name"] for c in passed],
            "failed_criteria": [c["name"] for c in failed],
            "undecided_criteria": [c["name"] for c in criteria if not c["decided"]],
            "one_line": (
                f"{len(passed)} of {len(decided)} decidable criteria pass. "
                "The gate does not clear on 2025."
            ),
        },
        "criteria": criteria,
        "violations_detail": gate.get("violations_vs_baselines_detail"),
        "brier_evidence": brier_evidence(
            rows_2025, ("colley", "srs", "elo", "random_walker", "winpct")
        ),
        "divergence_curve": curve,
        "monotone_evidence": monotone_evidence(curve, headline_week - 1),
        "systems_2025": rows_2025,
        "systems_tune_2021_2023": rows_tune,
        "segments_2025": {
            key: {k: _f(v) for k, v in value.items() if k != "calibration"}
            for key, value in (house.get("segments") or {}).items()
        },
        "calibration_deciles_2025": (
            (house.get("segments_from_headline_week") or {})
            .get("fbs_vs_fbs", {})
            .get("calibration")
        ),
        "tune_vs_holdout": {
            metric: {
                "tune_2021_2023": tune_house[metric],
                "holdout_2025": house_2025[metric],
            }
            for metric in ("su_accuracy", "mae", "rmse", "brier", "log_loss", "violations")
        },
        "rank_churn_2025": house.get("rank_churn"),
        "connectivity_2025": holdout.get("connectivity"),
    }


def _scored_with() -> dict[str, str | None]:
    """The code and the config AS THEY WERE WHEN THE TEST WAS RUN.

    THE BUG THIS EXISTS TO FIX ACTUALLY SHIPPED, for about half an hour. The
    scorecard stamped `config_hash(DEFAULT_CONFIG_PATH)` and `git rev-parse HEAD`,
    which are the config and the code AT RENDER TIME. Re-rendering the document
    after editing the config therefore moved the hash printed beside the sentence
    "no constant was chosen after this was read" - which is precisely the claim
    the hash is there to let a reader check, and precisely the hash that must not
    move.

    The run log records the sha the scoring pass ran at. Everything below is read
    out of git AT THAT SHA, so re-rendering this document a year from now prints
    the same provenance it prints today.
    """
    sha = None
    if RUN_LOG.exists():
        for line in RUN_LOG.read_text(encoding="utf-8").splitlines():
            if line.startswith("# git:"):
                sha = line.split("# git:", 1)[1].strip().split()[0]
                break
    config_sha256 = None
    config_version = None
    if sha:
        try:
            blob = subprocess.run(
                ["git", "show", f"{sha}:configs/default.toml"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout
            config_sha256 = hashlib.sha256(blob).hexdigest()
            config_version = tomllib.loads(blob.decode("utf-8"))["meta"]["config_version"]
        except Exception:  # noqa: BLE001 - a shallow clone is a legitimate state
            config_sha256 = None
    return {
        "git_sha": sha,
        "config_sha256": config_sha256,
        "config_version": config_version,
        "note": (
            "The code and the config AS THEY WERE WHEN THE SCORING PASS RAN, read "
            "out of git at the sha the run log records. These do not move when this "
            "document is re-rendered, which is the whole point of printing them."
        ),
    }


def _command() -> str:
    return (
        "OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "
        "uv run cfbpoll backtest --config configs/default.toml "
        "--systems schedule_odds,resume,l3,l2,l1,colley,srs,elo,walker,winpct "
        "--seasons 2025 --out out/holdout-2025 --unlock-holdout"
    )


def _scored_at() -> str | None:
    """The timestamp on the run log, so the artifact cannot claim a later date."""
    if not RUN_LOG.exists():
        return None
    for line in RUN_LOG.read_text(encoding="utf-8").splitlines():
        if line.startswith("# run at:"):
            return line.split("# run at:", 1)[1].strip()
    return None


# ---------------------------------------------------------------------- markdown


def render(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    verdict = payload["verdict"]

    add("# The 2025 holdout scorecard")
    add("")
    add("> **THE GATE DOES NOT CLEAR.** " + verdict["one_line"])
    add(">")
    add(
        "> This is the one scoring pass 2025 was reserved for. The constants were "
        "fitted on 2021-2023, validated once on 2024 and frozen on 2026-08-12, "
        "**before this season was ever scored**. It was scored on "
        f"{(payload['scored_at'] or 'the date below')}, once, and the result is "
        "published exactly as it came out."
    )
    add("")
    scored_with = payload["scored_with"]
    add(
        f"Season {payload['season']} · system `{payload['system']}` · "
        f"config `{scored_with['config_version'] or 'unknown'}` sha256 "
        f"`{(scored_with['config_sha256'] or 'unknown')[:16]}...` · code "
        f"`{(scored_with['git_sha'] or 'unknown')[:10]}`"
    )
    add("")
    add(
        "**Those are the code and the config AS THEY WERE WHEN THIS WAS SCORED**, "
        "read out of git at the sha the run log records, so they do not move when "
        "this document is re-rendered. That is the whole reason for printing them: "
        "a hash beside the sentence \"no constant was chosen after this was read\" "
        "is worthless if it tracks the current file."
    )
    add("")
    add("```")
    add(payload["command"])
    add("```")
    add("")

    window = payload["window"]
    add(
        f"Everything below is the published window: {window['universe']}, weeks "
        f">= {window['headline_start_week']}, {window['n_games']:,} games, strict "
        "walk-forward (fit through bucket N-1 of the same season, predict bucket N)."
    )
    add("")

    add("## The gate, criterion by criterion")
    add("")
    add("| criterion | threshold | observed | verdict |")
    add("|---|---|---:|:---:|")
    for c in payload["criteria"]:
        if not c["decided"]:
            add(f"| {c['statement']} | — | — | **undecided** |")
            continue
        threshold = c["threshold"]
        if c["name"] == "violations_vs_baselines":
            shown_threshold = f"`{threshold}`"
            shown_observed = _pct(c["observed"])
        elif c["name"] == "su_accuracy":
            shown_threshold = _pct(_f(threshold))
            shown_observed = _pct(c["observed"])
        elif c["name"] == "calibration":
            shown_threshold = f"{threshold} pp"
            shown_observed = f"{c['observed']:.2f} pp"
        else:
            shown_threshold = f"{threshold}"
            shown_observed = _fmt(c["observed"], 3)
        mark = "pass" if c["verdict"] == "pass" else "**FAIL**"
        add(f"| {c['statement']} | {shown_threshold} | {shown_observed} | {mark} |")
    add("")
    add(
        f"**{verdict['n_passed']} of {verdict['n_decidable']} decidable criteria "
        f"pass.** Two more are reported as undecided and are not converted into "
        "passes anywhere in this document."
    )
    add("")

    add("### The one that passes, and it is worth saying plainly")
    add("")
    tvh = payload["tune_vs_holdout"]
    add(
        f"Mean absolute error is **{tvh['mae']['holdout_2025']:.3f} points** against a "
        f"ceiling of {payload['criteria'][1]['threshold']}. **No tune season ever "
        f"cleared it**: the same ordering on 2021-2023 reads "
        f"{tvh['mae']['tune_2021_2023']:.3f}. A fully held-out season is where the "
        "margin ceiling was met for the first time, and it was met by a model that "
        "had never been shown the season. That is the one line in this document "
        "that reads better than the tune seasons did."
    )
    add("")

    add("### The four that fail")
    add("")
    su_floor = _f(payload["criteria"][0]["threshold"]) or 0.0
    su_seen = tvh["su_accuracy"]["holdout_2025"]
    short_by = (su_floor - su_seen) * 100
    short_games = round((su_floor - su_seen) * payload["window"]["n_games"])
    add(
        f"- **Straight-up accuracy** {_pct(su_seen)} against a {_pct(su_floor)} floor. "
        f"Short by {short_by:.2f} percentage points, which is {short_games} games in "
        f"{payload['window']['n_games']}."
    )
    add(
        f"- **RMSE** {tvh['rmse']['holdout_2025']:.3f} against a "
        f"{payload['criteria'][2]['threshold']} ceiling. MAE clears and RMSE does "
        "not, which is what a season with fat tails looks like: the typical miss is "
        "inside the target and the large misses are larger than the target allows."
    )
    add(
        f"- **Calibration** {payload['criteria'][3]['observed']:.2f} pp worst-decile "
        f"deviation against a {payload['criteria'][3]['threshold']} pp tolerance. This "
        "is the criterion two tuning campaigns have now attacked directly; ADR 0009 "
        "took it from 11.28 pp to 7.37 pp on the tune seasons and said in the same "
        "breath that it still failed. On a season nobody fitted, it is worse than the "
        "tuned figure, not better."
    )
    detail = payload["violations_detail"] or {}
    lost = detail.get("lost_to") or {}
    lost_str = ", ".join(f"{k} {v * 100:.2f}%" for k, v in sorted(lost.items()))
    add(
        f"- **Retrodictive violations** {_pct(detail.get('rate'))}, which loses to "
        f"{lost_str}. It is the same rival that has beaten this criterion since the "
        "fresh-eyes review widened it: win percentage does not lose to anything on a "
        "metric that ignores schedule entirely, and the gate was rewritten to stop "
        "curating its rivals rather than to be easier to pass."
    )
    add("")

    add("### The two that stay undecided, and why they are not decided here")
    add("")
    brier = payload["brier_evidence"]
    add(
        f"**Brier beats every baseline.** The house scores "
        f"{brier['house_brier']:.4f}. It loses to "
        + ", ".join(f"`{k}` ({v:.4f})" for k, v in brier["lost_to"].items())
        + ", ties "
        + (", ".join(f"`{k}`" for k in brier["tied"]) or "nothing")
        + " (which share its prediction source by construction), and beats "
        + ", ".join(f"`{k}`" for k in brier["beaten"])
        + ". The home-team floor is excluded, as it is from the violations "
        "criterion, because beating a system with no ratings measures nothing."
    )
    add("")
    add(brier["why_no_verdict"])
    add("")
    mono = payload["monotone_evidence"]
    add(
        f"**Retro-vs-live divergence declines monotonically.** Over the published "
        f"window the curve falls from {mono['first_mean_abs_delta']:.2f} places at "
        f"`{mono['window_first']}` to {mono['last_mean_abs_delta']:.2f} at "
        f"`{mono['window_last']}`. It is **not strictly monotone**: "
        + (
            "; ".join(
                f"`{r['from']}` → `{r['to']}` rises by {r['step']:.2f} places"
                for r in mono["rises"]
            )
            or "no step rises"
        )
        + "."
    )
    add("")
    add(mono["why_no_verdict"])
    add("")

    add("## The whole table, 2025, every system scored")
    add("")
    add("| system | n | SU% | MAE | RMSE | Brier | log loss | viol% | churn |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in _ordered(payload["systems_2025"]):
        add(
            f"| `{row['system']}` | {row['n_games']} | "
            f"{_pct(row['su_accuracy'])} | {_fmt(row['mae'], 3)} | "
            f"{_fmt(row['rmse'], 3)} | {_fmt(row['brier'])} | "
            f"{_fmt(row['log_loss'])} | {_pct(row['violations'])} | "
            f"{_fmt(row['rank_churn_mean'], 2)} |"
        )
    add("")
    add(
        "`home_team` is the floor and is always in the table whether or not it is "
        "asked for. `resume` is the ordering the headline replaced and stays scored "
        "forever, so the 2026-08-12 decision remains checkable rather than archived."
    )
    add("")

    add("## The same table on the tune seasons, for contrast")
    add("")
    add("2021-2023, the seasons the constants were fitted on.")
    add("")
    add("| system | n | SU% | MAE | RMSE | Brier | viol% |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for row in _ordered(payload["systems_tune_2021_2023"]):
        add(
            f"| `{row['system']}` | {row['n_games']} | {_pct(row['su_accuracy'])} | "
            f"{_fmt(row['mae'], 3)} | {_fmt(row['rmse'], 3)} | {_fmt(row['brier'])} | "
            f"{_pct(row['violations'])} |"
        )
    add("")
    add("### The house ordering, tune against holdout")
    add("")
    add("| metric | tune 2021-2023 | holdout 2025 | direction |")
    add("|---|---:|---:|:---:|")
    better_when_low = {"mae", "rmse", "brier", "log_loss", "violations"}
    for metric, pair in payload["tune_vs_holdout"].items():
        a, b = pair["tune_2021_2023"], pair["holdout_2025"]
        if a is None or b is None:
            arrow = "—"
        elif metric in better_when_low:
            arrow = "better" if b < a else "worse"
        else:
            arrow = "better" if b > a else "worse"
        places = 2 if metric == "su_accuracy" else 4
        shown_a = _pct(a) if metric in ("su_accuracy", "violations") else _fmt(a, places)
        shown_b = _pct(b) if metric in ("su_accuracy", "violations") else _fmt(b, places)
        add(f"| {metric} | {shown_a} | {shown_b} | {arrow} |")
    add("")
    add(
        "Read this table for its shape and not for a win anywhere: one season is one "
        "season, and 567 games is a small number to hang an inference on."
    )
    add("")

    add("## The divergence curve on 2025")
    add("")
    add(
        "Mean and maximum absolute rank change between R(N, N), the poll as it was "
        "published in week N, and R(N, final), the same week re-scored with the "
        "season's answers. Every ranked team, every evaluation bucket."
    )
    add("")
    add("| evaluation bucket | teams | mean \\|Δrank\\| | max \\|Δrank\\| |")
    add("|---|---:|---:|---:|")
    for row in payload["divergence_curve"]:
        add(
            f"| `{row['eval_label']}` | {row['n_teams']} | "
            f"{row['mean_abs_delta']:.2f} | {row['max_abs_delta']} |"
        )
    add("")

    add("## Segments, because they measure different things")
    add("")
    add("| segment | n | SU% | MAE | RMSE | Brier |")
    add("|---|---:|---:|---:|---:|---:|")
    for name, seg in sorted(payload["segments_2025"].items()):
        add(
            f"| `{name}` | {int(seg['n_games'])} | {_pct(seg['su_accuracy'])} | "
            f"{_fmt(seg['mae'], 3)} | {_fmt(seg['rmse'], 3)} | {_fmt(seg['brier'])} |"
        )
    add("")
    add(
        "The gate reads `fbs_vs_fbs` and nothing else. FBS-vs-FCS is a different "
        "question with a 92% straight-up rate and a 24-point mean error, bowls are "
        "35 games played by teams with opt-outs, and the CFP is 11. None of the "
        "three is a sample anybody should quote a verdict off."
    )
    add("")

    add("## What this scorecard licenses, and what it does not")
    add("")
    add(
        "- **It licenses publishing 2025 as an example season.** The number that was "
        "protected was the integrity of the tuning, and the tuning is over: nothing "
        "here selected a constant, because every constant was frozen three days before "
        "this season was read."
    )
    add(
        "- **It does not license a re-tune.** Any constant moved after today has been "
        "moved by somebody who has seen this page, and the honest way to do that is a "
        "pre-registered campaign on a re-designated split, announced in public, exactly "
        "as ADR 0007 required of 2024."
    )
    add(
        "- **It does not make the poll publishable by the project's own standard.** "
        "The gate exists to be failed in public. It fails here for the fourth "
        "consecutive published evaluation, on the same four criteria, and the site "
        "should say so with this page linked."
    )
    add(
        "- **It does not decide the two undecided criteria.** The evidence for both is "
        "above. The rule for either is a successor campaign's to pre-register."
    )
    add("")
    add(
        f"Generated by `scripts/make_holdout_scorecard.py` at "
        f"{payload['generated_at']} from the metrics tree the single scoring pass "
        "wrote. That tree and its run log are committed as "
        "`demo/2025-holdout-metrics.json` and `demo/2025-holdout-run.log`, because "
        "`out/` and `.cache/` are gitignored and a provenance record nobody outside "
        "one machine can read is not a record."
    )
    return "\n".join(lines) + "\n"


def _ordered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """House first, its predecessor second, our layers, then the competition, floor last."""
    order = {
        "schedule_odds": 0,
        "resume": 1,
        "l3": 2,
        "l2": 3,
        "l1": 4,
        "colley": 5,
        "srs": 6,
        "elo": 7,
        "random_walker": 8,
        "winpct": 9,
        "home_team": 10,
    }
    return sorted(rows, key=lambda r: (order.get(r["system"], 99), r["system"]))


def main() -> None:
    payload = build()
    DEMO.mkdir(parents=True, exist_ok=True)
    (DEMO / "2025-holdout-scorecard.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    (DEMO / "2025-holdout-scorecard.md").write_text(render(payload), encoding="utf-8")
    verdict = payload["verdict"]
    print(
        f"2025 holdout scorecard: {verdict['n_passed']}/{verdict['n_decidable']} "
        f"decidable criteria pass, {len(verdict['undecided_criteria'])} undecided. "
        f"passed={verdict['passed']}"
    )
    print("wrote: demo/2025-holdout-scorecard.md, demo/2025-holdout-scorecard.json")


if __name__ == "__main__":
    main()
