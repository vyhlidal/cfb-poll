"""Campaign 2, end to end: bracketing C, the accumulation window, and the h question.

Writes docs/analysis/campaign-2.json (every number) and renders
docs/analysis/campaign-2.md from it. The protocol header of that document is
docs/analysis/_campaign-2-protocol.md, committed BEFORE this script existed and
before any number below was read - see `git log --follow` on that file.

THREE LEADS, each with its adoption rule fixed in advance:

    1  bracket      [margin].c above its own grid edge, x [margin].beta_w.
                    Campaign 1's optimum sat at C = 32, the top of c_grid, so the
                    search never bracketed it. This grid ends at c = inf, which is
                    the identity response and therefore the LIMIT of the family:
                    it cannot produce another corner.
    2  trailing     Trailing-K-bucket sigma x trailing-K-bucket affine points
                    calibration, the fix campaign 1 diagnosed and refused to make
                    without pre-registering it first.
    3  homefield    A league-wide h anchored on home-and-home pairs from EARLIER
                    SEASONS. Run as an experiment; THE CONFIG DEFAULT DOES NOT
                    CHANGE whatever it shows, because this would be the project's
                    first cross-season fitted quantity and that is a question for
                    the owner (ADR 0008), not for a search.

STAGES, each resumable, each writing into the same JSON:

    bracket             lead 1's 42-cell grid, tune seasons
    trailing            lead 2's 25-cell factorial, tune seasons
    joint               the interaction cell, only if both leads cleared
    freeze              write the frozen choices - NO 2024 NUMBER IS READ HERE
    validate            2024, ONCE, for the incumbent and each frozen winner
    homefield           lead 3, both arms, tune and 2024
    dispersion          the slope of actual on predicted, before and after
    render              campaign-2.md from the JSON

2025 IS NEVER READ. No stage passes `unlock_holdout`, lead 3's prior-season
pooling excludes it explicitly, and the harness raises `HoldoutLocked` on any
attempt.

WHY THE GRIDS ARE SCORED ON `l3` ALONE. The headline ordering `schedule_odds`
predicts through its Power source ([resume].power_source = "L3"), so its
predictive row IS L3's row by construction. Violations, which are about the
ordering rather than about Power, are recomputed with the full system list for
the frozen winners only.

C IS CARRIED AS A STRING in this store ("32", "inf"). `float('inf')` serialises
as the non-standard literal `Infinity`, and a published artifact that only
Python's own parser will read is not a published artifact.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from scipy import stats

from cfbpoll.backtest import metrics, walkforward
from cfbpoll.config import DEFAULT_CONFIG_PATH, config_hash, load_config
from cfbpoll.ingest.plays import load_plays
from cfbpoll.ingest.sportsdataverse import load_games
from cfbpoll.model import l2_results

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "analysis"
JSON_PATH = OUT / "campaign-2.json"
MD_PATH = OUT / "campaign-2.md"
PROTOCOL_PATH = OUT / "_campaign-2-protocol.md"

TUNE_SEASONS = (2021, 2022, 2023)
VALIDATE_SEASONS = (2024,)
#: Every season in the archive that lead 3 may pool over. 2025 is the holdout and
#: is absent by construction rather than by filter.
ARCHIVE_SEASONS = (2021, 2022, 2023, 2024)

SYSTEM = "l3"
GRID_SYSTEMS = ("l3", "home_team")
FULL_SYSTEMS = (
    "schedule_odds",
    "resume",
    "l3",
    "l2",
    "l1",
    "colley",
    "srs",
    "elo",
    "walker",
    "winpct",
    "home_team",
)

#: LEAD 1's search space, verbatim from the pre-registered protocol §0.2.
C_GRID = ("32", "36", "40", "48", "64", "96", "inf")
BETA_GRID = (5.0, 6.0, 7.0, 8.0, 10.0, 12.0)

#: LEAD 2's search space, verbatim from the pre-registered protocol §0.3. 0 is the
#: cumulative window that runs today and is a cell of the grid, not a baseline
#: standing outside it.
TRAILING_GRID = (3, 4, 5, 6, 0)

#: ADR 0006's noise floor, in points of MAE, reused rather than reinvented for the
#: third campaign running. The same quantity cannot be noise when it decides one
#: thing and signal when it decides another.
NOISE_FLOOR_MAE = 0.055

#: LEAD 2's calibration bar, in percentage points. Campaign 1's own bar, reused.
CALIBRATION_ADOPT_PP = 2.0

_GAMES: pl.DataFrame | None = None
_PLAYS: pl.DataFrame | None = None
_SEASONS: tuple[int, ...] = ()


# ----------------------------------------------------------------------------
# the harness, wrapped once
# ----------------------------------------------------------------------------
def _init(seasons: tuple[int, ...]) -> None:
    """Load the archive once per process. Loading costs 0.22 s; refitting does not."""
    global _GAMES, _PLAYS, _SEASONS
    for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(var, "1")
    cfg = load_config()
    _SEASONS = seasons
    _GAMES = load_games(list(seasons), universe=str(cfg["model"]["fit_universe"]))
    _PLAYS = load_plays(list(seasons))


def _headline(result: dict[str, Any], system: str = SYSTEM) -> dict[str, Any]:
    return result["systems"][system]["segments_from_headline_week"]["fbs_vs_fbs"]


def _score(
    cfg: dict[str, Any],
    seasons: tuple[int, ...],
    systems: tuple[str, ...] = GRID_SYSTEMS,
    collect_predictions: bool = False,
) -> dict[str, Any]:
    assert _GAMES is not None and _PLAYS is not None, "call _init first"
    return walkforward.run_backtest(
        seasons=list(seasons),
        systems=list(systems),
        config=cfg,
        games=_GAMES,
        plays=_PLAYS,
        collect_predictions=collect_predictions,
    )


def _cell_config(base: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """A deep copy of the config with the named constants moved. Nothing else."""
    cfg = copy.deepcopy(base)
    for key, value in overrides.items():
        if key == "c":
            cfg["margin"]["c"] = float(value)
        elif key == "beta_w":
            cfg["margin"]["beta_w"] = float(value)
        elif key == "sigma_trailing":
            cfg["resume"]["sigma_trailing_buckets"] = int(value)
        elif key == "calib_trailing":
            cfg["backtest"]["calibration_trailing_buckets"] = int(value)
        elif key == "anchor":
            # THE ONLY PLACE IN THIS REPOSITORY THAT FLIPS THE CONSTRAINT KEY, and
            # it flips it for one run of one experiment. The harness fails closed
            # without it, which is what makes the default a constraint rather than
            # a preference.
            cfg["homefield"]["anchor_h_by_season"] = {str(k): float(v) for k, v in value.items()}
            cfg["homefield"]["anchor_provenance"] = "prior_season_home_and_home"
            cfg["constraints"]["allow_prior_season_data"] = True
        else:  # pragma: no cover - a typo here must not silently do nothing
            raise KeyError(f"unknown override {key!r}")
    return cfg


def _summary(result: dict[str, Any], system: str = SYSTEM) -> dict[str, Any]:
    h = _headline(result, system)
    return {
        "n_games": h["n_games"],
        "mae": h["mae"],
        "rmse": h["rmse"],
        "su_accuracy": h["su_accuracy"],
        "brier": h["brier"],
        "log_loss": h["log_loss"],
        "max_calibration_deviation_pp": h["max_calibration_deviation_pp"],
        "sigma_mean": h["sigma_mean"],
    }


def _incumbent() -> dict[str, Any]:
    """The config as ADR 0007 left it. Campaign 1's baseline is spent."""
    cfg = load_config()
    c = float(cfg["margin"]["c"])
    return {
        "c": "inf" if not np.isfinite(c) else f"{c:g}",
        "beta_w": float(cfg["margin"]["beta_w"]),
        "sigma_trailing": int(cfg["resume"]["sigma_trailing_buckets"]),
        "calib_trailing": int(cfg["backtest"]["calibration_trailing_buckets"]),
    }


def _run_cell(spec: dict[str, Any]) -> dict[str, Any]:
    """Pool worker: one grid cell, returned as a flat row."""
    cfg = _cell_config(load_config(), **spec)
    return {**spec, **_summary(_score(cfg, _SEASONS))}


# ----------------------------------------------------------------------------
# stage 1 - LEAD 1, bracketing C
# ----------------------------------------------------------------------------
def stage_bracket(store: dict[str, Any], workers: int) -> None:
    specs = [{"c": c, "beta_w": b} for c in C_GRID for b in BETA_GRID]
    started = datetime.now(UTC)
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init, initargs=(TUNE_SEASONS,)
    ) as pool:
        rows = list(pool.map(_run_cell, specs))
    elapsed = (datetime.now(UTC) - started).total_seconds()
    rows.sort(key=lambda r: (r["mae"], r["brier"]))
    incumbent = _incumbent()
    incumbent_cell = next(
        r for r in rows if r["c"] == incumbent["c"] and r["beta_w"] == incumbent["beta_w"]
    )
    best = rows[0]
    store["bracket"] = {
        "search_space": {"c": list(C_GRID), "beta_w": list(BETA_GRID)},
        "cells": rows,
        "n_cells": len(rows),
        "elapsed_seconds": elapsed,
        "best": best,
        "incumbent_cell": incumbent_cell,
        "incumbent_rank": rows.index(incumbent_cell) + 1,
        "tune_mae_delta": best["mae"] - incumbent_cell["mae"],
        "spread": max(r["mae"] for r in rows) - min(r["mae"] for r in rows),
        # C's grid ends at the LIMIT of the family, so "on the edge" means
        # something different at the two ends and is reported as two facts.
        "c_at_uncompressed_limit": best["c"] == "inf",
        "c_at_lower_edge": best["c"] == C_GRID[0],
        "beta_w_at_grid_edge": best["beta_w"] in (min(BETA_GRID), max(BETA_GRID)),
        "objective": "walk-forward MAE, tune seasons, headline window, fbs_vs_fbs",
    }


# ----------------------------------------------------------------------------
# stage 2 - LEAD 2, the shape of the accumulation window
# ----------------------------------------------------------------------------
def stage_trailing(store: dict[str, Any], workers: int) -> None:
    specs = [
        {"sigma_trailing": s, "calib_trailing": k}
        for s in TRAILING_GRID
        for k in TRAILING_GRID
    ]
    started = datetime.now(UTC)
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init, initargs=(TUNE_SEASONS,)
    ) as pool:
        rows = list(pool.map(_run_cell, specs))
    elapsed = (datetime.now(UTC) - started).total_seconds()
    # THE OBJECTIVE HERE IS CALIBRATION, and it is different from lead 1's on
    # purpose and in advance. Campaign 1 established that MAE is not what this
    # instrument moves; MAE and Brier are guards below, not the objective.
    rows.sort(key=lambda r: (r["max_calibration_deviation_pp"], r["brier"]))
    incumbent_cell = next(
        r for r in rows if r["sigma_trailing"] == 0 and r["calib_trailing"] == 0
    )
    best = rows[0]
    store["trailing"] = {
        "search_space": {
            "sigma_trailing": list(TRAILING_GRID),
            "calib_trailing": list(TRAILING_GRID),
        },
        "cells": rows,
        "n_cells": len(rows),
        "elapsed_seconds": elapsed,
        "best": best,
        "incumbent_cell": incumbent_cell,
        "incumbent_rank": rows.index(incumbent_cell) + 1,
        "tune_calibration_delta_pp": (
            incumbent_cell["max_calibration_deviation_pp"]
            - best["max_calibration_deviation_pp"]
        ),
        "tune_mae_delta": best["mae"] - incumbent_cell["mae"],
        "tune_brier_delta": best["brier"] - incumbent_cell["brier"],
        "spread_pp": (
            max(r["max_calibration_deviation_pp"] for r in rows)
            - min(r["max_calibration_deviation_pp"] for r in rows)
        ),
        "objective": (
            "maximum decile calibration deviation, tune seasons, headline window, "
            "fbs_vs_fbs; MAE and Brier are guards and not the objective"
        ),
    }
    store["trailing"]["paired_guard"] = _paired_guard(incumbent_cell, best)


def _per_game_brier(
    spec: dict[str, Any], seasons: tuple[int, ...]
) -> tuple[np.ndarray, list[dict[str, float]]]:
    """The per-game squared probability error, and the decile table it rolls up to.

    Per-game because the guard on Brier is a PAIRED standard error: both cells
    score the identical games, so pairing removes the game-to-game variance that
    dominates an unpaired comparison and would make any difference look like noise.
    """
    cfg = _cell_config(load_config(), **{k: v for k, v in spec.items() if k in _OVERRIDES})
    result = _score(cfg, seasons, GRID_SYSTEMS, collect_predictions=True)
    frame = _predictions_frame(result).filter(pl.col("in_headline_window"))
    predicted = frame["predicted"].to_numpy().astype(np.float64)
    sigma = frame["sigma"].to_numpy().astype(np.float64)
    won = (frame["actual"].to_numpy().astype(np.float64) > 0).astype(np.float64)
    prob = metrics.win_probability(predicted, sigma)
    return (prob - won) ** 2, metrics.calibration_table(prob, won)


_OVERRIDES = ("c", "beta_w", "sigma_trailing", "calib_trailing", "anchor")


def _paired_guard(incumbent: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """The Brier guard of protocol §0.5(3), computed rather than asserted."""
    _init(TUNE_SEASONS)
    base, base_table = _per_game_brier(incumbent, TUNE_SEASONS)
    other, other_table = _per_game_brier(candidate, TUNE_SEASONS)
    n = min(base.size, other.size)
    diff = other[:n] - base[:n]
    se = float(np.std(diff, ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    mean = float(np.mean(diff))
    return {
        "n_games": int(n),
        "brier_mean_paired_difference": mean,
        "brier_paired_standard_error": se,
        "brier_within_one_paired_se": bool(mean <= se),
        "incumbent_table": base_table,
        "candidate_table": other_table,
        "mae_noise_floor": NOISE_FLOOR_MAE,
        "note": (
            "the candidate's Brier may not exceed the incumbent's by more than one "
            "standard error of the PAIRED per-game difference (protocol §0.5). Both "
            "cells score the same games in the same order, so the pairing is exact"
        ),
    }


# ----------------------------------------------------------------------------
# stage 3 - the interaction, pre-registered
# ----------------------------------------------------------------------------
def _clears_lead1(store: dict[str, Any]) -> bool:
    return store["bracket"]["tune_mae_delta"] < 0.0


def _clears_lead2_tune(store: dict[str, Any]) -> bool:
    tr = store["trailing"]
    guard = tr["paired_guard"]
    return bool(
        tr["tune_calibration_delta_pp"] >= CALIBRATION_ADOPT_PP
        and tr["tune_mae_delta"] <= NOISE_FLOOR_MAE
        and guard["brier_within_one_paired_se"]
    )


def stage_joint(store: dict[str, Any], workers: int) -> None:
    """Lead 1's winner x lead 2's winner, which the protocol requires if both clear.

    Searching each lead against the current config is what makes the two results
    independent; it is also what leaves an interaction unmeasured, so the protocol
    fixed in advance that the joint cell has to clear both rules again.
    """
    del workers
    if not (_clears_lead1(store) and _clears_lead2_tune(store)):
        store["joint"] = {
            "run": False,
            "reason": (
                "the protocol runs the joint cell only when BOTH leads clear their "
                "own tune-season rule; they did not, so there is no interaction to "
                "measure"
            ),
            "lead1_clears": _clears_lead1(store),
            "lead2_clears_tune": _clears_lead2_tune(store),
        }
        return
    _init(TUNE_SEASONS)
    spec = {
        "c": store["bracket"]["best"]["c"],
        "beta_w": store["bracket"]["best"]["beta_w"],
        "sigma_trailing": store["trailing"]["best"]["sigma_trailing"],
        "calib_trailing": store["trailing"]["best"]["calib_trailing"],
    }
    row = {**spec, **_summary(_score(_cell_config(load_config(), **spec), TUNE_SEASONS))}
    incumbent = next(
        r
        for r in store["trailing"]["cells"]
        if r["sigma_trailing"] == 0 and r["calib_trailing"] == 0
    )
    store["joint"] = {
        "run": True,
        "cell": row,
        "vs_incumbent": {
            "mae_delta": row["mae"] - incumbent["mae"],
            "calibration_delta_pp": (
                incumbent["max_calibration_deviation_pp"] - row["max_calibration_deviation_pp"]
            ),
            "brier_delta": row["brier"] - incumbent["brier"],
        },
        "paired_guard": _paired_guard(incumbent, row),
    }


# ----------------------------------------------------------------------------
# stage 4 - freeze. NO 2024 NUMBER IS READ IN THIS STAGE.
# ----------------------------------------------------------------------------
def stage_freeze(store: dict[str, Any], workers: int) -> None:
    del workers
    incumbent = _incumbent()
    lead1 = {"c": store["bracket"]["best"]["c"], "beta_w": store["bracket"]["best"]["beta_w"]}
    lead2 = {
        "sigma_trailing": store["trailing"]["best"]["sigma_trailing"],
        "calib_trailing": store["trailing"]["best"]["calib_trailing"],
    }
    joint = store.get("joint") or {}
    store["frozen"] = {
        "incumbent": incumbent,
        "lead1": lead1,
        "lead2": lead2,
        "joint_run": bool(joint.get("run")),
        "lead1_cleared_tune": _clears_lead1(store),
        "lead2_cleared_tune": _clears_lead2_tune(store),
        "frozen_utc": datetime.now(UTC).isoformat(),
        "rule": (
            "lead 1 is adopted only if it improves tune MAE AND 2024 MAE improves "
            "too - direction, not magnitude, which is STRICTER than campaign 1's "
            "rule because this grid leaves the interval other people's published "
            "work justifies. lead 2 is adopted only if it cuts the tune max decile "
            f"deviation by >= {CALIBRATION_ADOPT_PP} pp, holds direction on 2024, "
            f"and keeps tune MAE within {NOISE_FLOOR_MAE} points and tune Brier "
            "within one paired standard error"
        ),
        "no_2024_number_has_been_read": True,
    }


# ----------------------------------------------------------------------------
# stage 5 - 2024, evaluated once per frozen choice
# ----------------------------------------------------------------------------
def _run_validation_cell(spec: dict[str, Any]) -> dict[str, Any]:
    """Pool worker: one (config, season set) pair scored with the FULL system list."""
    seasons = TUNE_SEASONS if spec["season_set"] == "tune" else VALIDATE_SEASONS
    overrides = {k: v for k, v in spec.items() if k in _OVERRIDES}
    _init(seasons)
    result = _score(_cell_config(load_config(), **overrides), seasons, FULL_SYSTEMS)
    block = result["systems"]
    return {
        **spec,
        **_summary(result),
        "violation_rate": block[SYSTEM]["retrodictive_violation_rate"],
        "headline_violation_rate": block["schedule_odds"]["retrodictive_violation_rate"],
        "gate": block["schedule_odds"]["gate"],
    }


def stage_validate(store: dict[str, Any], workers: int) -> None:
    frozen = store["frozen"]
    incumbent = frozen["incumbent"]
    arms: list[tuple[str, dict[str, Any]]] = [("incumbent", dict(incumbent))]
    arms.append(("lead1", {**incumbent, **frozen["lead1"]}))
    arms.append(("lead2", {**incumbent, **frozen["lead2"]}))
    if frozen["joint_run"]:
        arms.append(("joint", {**incumbent, **frozen["lead1"], **frozen["lead2"]}))

    specs = [
        {"label": label, "season_set": season_set, **overrides}
        for label, overrides in arms
        for season_set in ("tune", "validate")
    ]
    with ProcessPoolExecutor(max_workers=min(workers, len(specs))) as pool:
        rows = list(pool.map(_run_validation_cell, specs))

    by_key = {(r["label"], r["season_set"]): r for r in rows}
    base_t, base_v = by_key[("incumbent", "tune")], by_key[("incumbent", "validate")]

    verdicts: dict[str, Any] = {}
    for label, _ in arms:
        if label == "incumbent":
            continue
        tune, val = by_key[(label, "tune")], by_key[(label, "validate")]
        mae_t = tune["mae"] - base_t["mae"]
        mae_v = val["mae"] - base_v["mae"]
        cal_t = base_t["max_calibration_deviation_pp"] - tune["max_calibration_deviation_pp"]
        cal_v = base_v["max_calibration_deviation_pp"] - val["max_calibration_deviation_pp"]
        if label == "lead1":
            adopted = bool(mae_t < 0.0 and mae_v < 0.0)
            rule = "tune MAE improves AND 2024 MAE improves"
        else:
            guard = (store.get("joint") or {}).get("paired_guard") if label == "joint" else None
            guard = guard or store["trailing"]["paired_guard"]
            adopted = bool(
                cal_t >= CALIBRATION_ADOPT_PP
                and cal_v > 0.0
                and mae_t <= NOISE_FLOOR_MAE
                and guard["brier_within_one_paired_se"]
            )
            rule = (
                f"tune calibration improves >= {CALIBRATION_ADOPT_PP} pp, 2024 holds "
                f"direction, tune MAE within {NOISE_FLOOR_MAE}, tune Brier within one "
                "paired SE"
            )
        verdicts[label] = {
            "tune_mae_delta": mae_t,
            "validate_mae_delta": mae_v,
            "tune_calibration_delta_pp": cal_t,
            "validate_calibration_delta_pp": cal_v,
            "tune_brier_delta": tune["brier"] - base_t["brier"],
            "validate_brier_delta": val["brier"] - base_v["brier"],
            "tune_violation_delta": (
                tune["headline_violation_rate"] - base_t["headline_violation_rate"]
            ),
            "adopted": adopted,
            "rule": rule,
        }
    store["validation"] = {
        "runs": rows,
        "verdicts": verdicts,
        "evaluated_once": True,
        "noise_floor_mae": NOISE_FLOOR_MAE,
        "calibration_adopt_pp": CALIBRATION_ADOPT_PP,
    }


# ----------------------------------------------------------------------------
# stage 6 - LEAD 3, the home-field anchor
# ----------------------------------------------------------------------------
def _prior_season_h(season: int) -> dict[str, Any]:
    """h for `season`, pooled over every archived season STRICTLY BEFORE it.

    Walk-forward across seasons, exactly as everything else in this project is
    walk-forward within one. 2025 is not in `ARCHIVE_SEASONS` at all, so the
    holdout cannot leak into an anchor by arithmetic.
    """
    prior = [s for s in ARCHIVE_SEASONS if s < season]
    if not prior:
        return {"season": season, "prior_seasons": [], "n_pairs": 0, "h": float("nan")}
    universe = str(load_config()["model"]["fit_universe"])
    games = load_games(prior, universe=universe)
    estimate = l2_results.home_and_home_estimate(games, within_season=False)
    return {"season": season, "prior_seasons": prior, **estimate}


def stage_homefield(store: dict[str, Any], workers: int) -> None:
    del workers
    cfg = load_config()

    # ---- the estimates themselves, published before anything is run on them ----
    per_season = {str(s): _prior_season_h(s) for s in (*TUNE_SEASONS, *VALIDATE_SEASONS)}
    tune_games = load_games(list(TUNE_SEASONS), universe=str(cfg["model"]["fit_universe"]))
    pooled_tune = l2_results.home_and_home_estimate(tune_games, within_season=False)
    within_tune = l2_results.home_and_home_estimate(tune_games, within_season=True)

    # ---- the incumbent's own site coefficient, for the comparison that matters --
    _init(TUNE_SEASONS)
    incumbent_cfg = load_config()
    base_tune = _score(incumbent_cfg, TUNE_SEASONS, GRID_SYSTEMS, collect_predictions=True)
    first_published = int(cfg["publication"]["headline_start_week"])
    weekly = [
        r
        for r in base_tune["weekly"]
        if r["system"] == SYSTEM and r["week"] >= first_published
    ]
    regression_h = [r["calib_site"] for r in weekly]

    arms: dict[str, Any] = {}

    def _run(label: str, anchor: dict[int, float], seasons: tuple[int, ...]) -> dict[str, Any]:
        _init(seasons)
        run_cfg = _cell_config(load_config(), anchor=anchor)
        result = _score(run_cfg, seasons, FULL_SYSTEMS, collect_predictions=True)
        frame = _predictions_frame(result).filter(pl.col("in_headline_window"))
        predicted = frame["predicted"].to_numpy().astype(np.float64)
        actual = frame["actual"].to_numpy().astype(np.float64)
        slope, intercept, r_value, _p, stderr = stats.linregress(predicted, actual)
        return {
            "label": label,
            "anchor": {str(k): v for k, v in sorted(anchor.items())},
            "seasons": list(seasons),
            **_summary(result),
            "headline_violation_rate": result["systems"]["schedule_odds"][
                "retrodictive_violation_rate"
            ],
            "slope": float(slope),
            "slope_stderr": float(stderr),
            "intercept": float(intercept),
            "r_value": float(r_value),
            "residual_mean": float(np.mean(actual - predicted)),
            "prior_seasons_used": result["protocol"]["prior_seasons_used"],
        }

    def _baseline(seasons: tuple[int, ...]) -> dict[str, Any]:
        _init(seasons)
        result = _score(load_config(), seasons, FULL_SYSTEMS, collect_predictions=True)
        frame = _predictions_frame(result).filter(pl.col("in_headline_window"))
        predicted = frame["predicted"].to_numpy().astype(np.float64)
        actual = frame["actual"].to_numpy().astype(np.float64)
        slope, intercept, r_value, _p, stderr = stats.linregress(predicted, actual)
        return {
            "label": "incumbent",
            "anchor": {},
            "seasons": list(seasons),
            **_summary(result),
            "headline_violation_rate": result["systems"]["schedule_odds"][
                "retrodictive_violation_rate"
            ],
            "slope": float(slope),
            "slope_stderr": float(stderr),
            "intercept": float(intercept),
            "r_value": float(r_value),
            "residual_mean": float(np.mean(actual - predicted)),
            "prior_seasons_used": result["protocol"]["prior_seasons_used"],
        }

    # ARM A: the live-runnable form, if it were ratified. A season with no usable
    # prior pool simply carries no entry and keeps the fitted coefficient - the
    # boundary cases are in the table rather than smoothed away.
    anchor_a_tune = {
        s: float(per_season[str(s)]["h"])
        for s in TUNE_SEASONS
        if per_season[str(s)]["n_pairs"] > 0
    }
    anchor_a_val = {
        s: float(per_season[str(s)]["h"])
        for s in VALIDATE_SEASONS
        if per_season[str(s)]["n_pairs"] > 0
    }

    arms["incumbent_tune"] = _baseline(TUNE_SEASONS)
    arms["incumbent_validate"] = _baseline(VALIDATE_SEASONS)
    arms["arm_a_tune"] = _run("arm_a", anchor_a_tune, TUNE_SEASONS)
    arms["arm_a_validate"] = _run("arm_a", anchor_a_val, VALIDATE_SEASONS)
    # ARM B: NOT A LIVE ESTIMATOR. h pooled over 2021-2023, applied to 2021-2023 -
    # it reads the seasons it is scoring, exactly as campaign 1's oracle sigma row
    # did, and it exists for the same reason: to bound what a well-identified h
    # could be worth before anybody argues about whether to allow one.
    arms["arm_b_tune_NOT_RUNNABLE"] = _run(
        "arm_b", {s: float(pooled_tune["h"]) for s in TUNE_SEASONS}, TUNE_SEASONS
    )

    store["homefield"] = {
        "per_season_prior_pool": per_season,
        "pooled_tune_NOT_RUNNABLE": pooled_tune,
        "within_season_tune": within_tune,
        "regression_coefficient": {
            "mean": float(np.mean(regression_h)),
            "sd": float(np.std(regression_h, ddof=1)),
            "min": float(np.min(regression_h)),
            "max": float(np.max(regression_h)),
            "n_weeks": len(regression_h),
        },
        "config_h_pasteur": float(cfg["homefield"]["h_pasteur"]),
        "config_h_recent_estimate": float(cfg["homefield"]["h_recent_estimate"]),
        "arms": arms,
        "config_changed": False,
        "note": (
            "THE CONFIG DEFAULT DOES NOT CHANGE, whatever this table shows. That was "
            "fixed in the protocol before any number here was read, because "
            "anchoring h on earlier seasons would be this project's FIRST "
            "cross-season fitted quantity and that is a question for the owner "
            "(ADR 0008), not for a search"
        ),
    }


def _harness_refuses_without_the_flag() -> dict[str, Any]:
    """The guard, exercised rather than described.

    A constraint that is only enforced by a comment is a preference. This runs the
    anchored config with `[constraints].allow_prior_season_data` back at its live
    value and records what the harness did about it.
    """
    cfg = load_config()
    cfg["homefield"]["anchor_h_by_season"] = {"2023": 1.88}
    cfg["homefield"]["anchor_provenance"] = "prior_season_home_and_home"
    try:
        walkforward.homefield_anchor(cfg)
    except walkforward.PriorSeasonLocked as exc:
        return {"raised": True, "exception": type(exc).__name__, "message": str(exc)}
    return {"raised": False, "exception": None, "message": ""}


# ----------------------------------------------------------------------------
# stage 6b - what an arm does to the POLL, which the objective has no opinion about
# ----------------------------------------------------------------------------
#: The q_ref sweep's worst Kendall tau (headline-ordering study §9). The project's
#: own published standard: a change whose tau against the incumbent falls below
#: this is a DIAL and must be labelled as one (ADR 0006).
Q_REF_TAU_FLOOR = 0.985


def _headline_ranks(cfg: dict[str, Any], season: int, plays: pl.DataFrame) -> dict[str, int]:
    """The final pre-postseason headline poll under one config."""
    from cfbpoll.ingest import windows
    from cfbpoll.model import retro, schedule_odds
    from cfbpoll.publish import poll as poll_mod

    games = load_games([season], universe=str(cfg["model"]["fit_universe"]))
    buckets = windows.season_buckets(games, season)
    regular = [b for b in buckets if b.season_type == "regular"]
    evaluated = max(regular, key=lambda b: b.order)
    powers = retro.season_power(games, season, cfg, plays=plays, buckets=buckets)
    window = windows.games_through(
        games, season=season, week=evaluated.week, season_type="regular"
    )
    classes = poll_mod.team_classes(games)
    odds = schedule_odds.fit(window, cfg, power=powers[evaluated.order], classes=classes)
    return {
        team: i + 1
        for i, team in enumerate(
            sorted((t for t in odds.tail if classes.get(t) == "fbs"), key=odds.order_key)
        )
    }


def _movement(base: dict[str, int], other: dict[str, int]) -> dict[str, Any]:
    """§9's exact machinery, reused rather than reimplemented (ADR 0006's standard)."""
    from scipy.stats import kendalltau

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
        "biggest_movers": [{"team": t, "incumbent": a, "arm": b} for _, t, a, b in biggest],
        "is_a_dial": tau < Q_REF_TAU_FLOOR,
    }


def stage_ranking(store: dict[str, Any], workers: int) -> None:
    """Does an arm move the POLL? Measured by the project's own rule, and REPORTED.

    THIS IS A DISCLOSURE, NOT A GATE, and the distinction is stated here rather
    than left to be inferred. The adoption rules were fixed in the protocol and
    none of them mentions Kendall's tau; adding a rule now, after the numbers, is
    the failure the protocol exists to prevent. But ADR 0006 imposes a standing
    LABELLING obligation - a change whose tau against the incumbent falls below
    0.985 is a dial rather than a convention and must be called one - and campaign
    1 discharged exactly that obligation in its PART 4b. So does this.

    It matters more here than it did there. beta_w is the discontinuity that makes
    this a football ranking rather than a scoring-margin ranking, which is a
    statement about DESERT, and lead 1's objective is margin MAE, which has no
    opinion about desert at all. An arm that buys 0.006 points of MAE with a large
    ranking change is not obviously a good trade, and the only way a reader can
    judge that is to see both numbers.
    """
    del workers
    frozen = store["frozen"]
    incumbent = frozen["incumbent"]
    arms: dict[str, dict[str, Any]] = {"lead1": {**incumbent, **frozen["lead1"]}}
    if frozen["joint_run"]:
        arms["joint"] = {**incumbent, **frozen["lead1"], **frozen["lead2"]}

    base_cfg = _cell_config(
        load_config(), **{k: v for k, v in incumbent.items() if k in _OVERRIDES}
    )
    out: dict[str, Any] = {}
    for label, spec in arms.items():
        arm_cfg = _cell_config(load_config(), **{k: v for k, v in spec.items() if k in _OVERRIDES})
        by_season: dict[str, Any] = {}
        for season in TUNE_SEASONS:
            plays = load_plays([season])
            base = _headline_ranks(base_cfg, season, plays)
            other = _headline_ranks(arm_cfg, season, plays)
            by_season[str(season)] = {
                "movement": _movement(base, other),
                "top10_incumbent": [t for t, _ in sorted(base.items(), key=lambda kv: kv[1])[:10]],
                "top10_arm": [t for t, _ in sorted(other.items(), key=lambda kv: kv[1])[:10]],
            }
        taus = [by_season[s]["movement"]["kendall_tau"] for s in by_season]
        out[label] = {
            "by_season": by_season,
            "min_kendall_tau": float(min(taus)),
            "is_a_dial": bool(min(taus) < Q_REF_TAU_FLOOR),
        }
    store["ranking_impact"] = {
        "tau_floor": Q_REF_TAU_FLOOR,
        "arms": out,
        "standard": (
            "docs/analysis/headline-ordering-study.md §9 and ADR 0006: a parameter "
            "whose Kendall tau against the incumbent falls below the 0.985 that "
            "q_ref achieves is a DIAL, not a convention, and must be labelled as "
            "one. This is a LABELLING obligation and not an adoption rule - the "
            "adoption rules were fixed in the protocol and none of them is this"
        ),
    }


# ----------------------------------------------------------------------------
# stage 7 - the under-dispersion question, before and after
# ----------------------------------------------------------------------------
def _predictions_frame(result: dict[str, Any], system: str = SYSTEM) -> pl.DataFrame:
    rows = [
        r for r in result["predictions"] if r["system"] == system and r["segment"] == "fbs_vs_fbs"
    ]
    return pl.DataFrame(rows).sort(["season", "bucket_order", "game_id"])


def _dispersion(spec: dict[str, Any], seasons: tuple[int, ...]) -> dict[str, Any]:
    cfg = _cell_config(load_config(), **{k: v for k, v in spec.items() if k in _OVERRIDES})
    result = _score(cfg, seasons, GRID_SYSTEMS, collect_predictions=True)
    all_weeks = _predictions_frame(result)
    frame = all_weeks.filter(pl.col("in_headline_window"))
    predicted = frame["predicted"].to_numpy().astype(np.float64)
    actual = frame["actual"].to_numpy().astype(np.float64)
    sigma = frame["sigma"].to_numpy().astype(np.float64)
    residual = actual - predicted
    won = (actual > 0).astype(np.float64)
    slope, intercept, r_value, _p, stderr = stats.linregress(predicted, actual)
    table = metrics.calibration_table(metrics.win_probability(predicted, sigma), won)
    return {
        "n_games": int(frame.height),
        "slope": float(slope),
        "slope_stderr": float(stderr),
        "slope_z_above_one": float((slope - 1.0) / stderr),
        "intercept": float(intercept),
        "r_value": float(r_value),
        "residual_mean": float(np.mean(residual)),
        "residual_rms": float(np.sqrt(np.mean(residual**2))),
        "sigma_mean": float(np.mean(sigma)),
        "max_deviation_pp": metrics.max_calibration_deviation_pp(table),
        "table": table,
    }


def stage_dispersion(store: dict[str, Any], workers: int) -> None:
    """Is the under-dispersion fixed? The one question campaign 1 left open.

    The slope of actual on predicted margin was 1.1428 +/- 0.0435 on tune and
    1.2442 +/- 0.0851 on 2024, both measured on the PRE-ADR-0007 starting values.
    It is re-measured here on the incumbent this campaign actually started from, on
    each frozen arm, and on 2024 - because a campaign that changes sigma and the
    calibration slope owes a direct answer about the quantity it was aimed at
    rather than an inference from the decile table.
    """
    del workers
    frozen = store["frozen"]
    incumbent = frozen["incumbent"]
    arms = {
        "incumbent": dict(incumbent),
        "lead1": {**incumbent, **frozen["lead1"]},
        "lead2": {**incumbent, **frozen["lead2"]},
    }
    if frozen["joint_run"]:
        arms["joint"] = {**incumbent, **frozen["lead1"], **frozen["lead2"]}

    out: dict[str, Any] = {}
    for season_set, seasons in (("tune", TUNE_SEASONS), ("validate", VALIDATE_SEASONS)):
        _init(seasons)
        for label, spec in arms.items():
            out[f"{label}_{season_set}"] = _dispersion(spec, seasons)
    store["dispersion"] = {
        "arms": out,
        "campaign_1_reference": {
            "tune_slope": 1.1428,
            "tune_slope_stderr": 0.0435,
            "validate_slope": 1.2442,
            "validate_slope_stderr": 0.0851,
            "measured_on": "the pre-ADR-0007 starting values, C = 24 and beta_w = 3",
        },
    }
    store["constraint_guard"] = _harness_refuses_without_the_flag()


# ----------------------------------------------------------------------------
# render
# ----------------------------------------------------------------------------
PROTOCOL = PROTOCOL_PATH.read_text()


def _c_label(c: str) -> str:
    return "uncapped" if c == "inf" else c


def _k_label(k: int) -> str:
    return "all" if int(k) == 0 else str(int(k))


def _verdict(passed: Any) -> str:
    if passed is None:
        return "undecided"
    return "PASS" if passed else "**FAIL**"


def _gate_table(gate: dict[str, Any]) -> list[str]:
    obs, thr = gate["observed"], gate["thresholds"]
    return [
        "| Criterion | Threshold | Observed | Verdict |",
        "|---|---|---:|---|",
        f"| Straight-up accuracy | >= {thr['su_accuracy_min'] * 100:.2f}% "
        f"| {obs['su_accuracy'] * 100:.2f}% | {_verdict(gate['su_accuracy'])} |",
        f"| Margin MAE | <= {thr['mae_max']} | {obs['mae']:.3f} | {_verdict(gate['mae'])} |",
        f"| Margin RMSE | <= {thr['rmse_max']} | {obs['rmse']:.3f} | {_verdict(gate['rmse'])} |",
        f"| Max decile calibration deviation | <= "
        f"{thr['calibration_max_decile_deviation_pp']} pp "
        f"| {obs['max_calibration_deviation_pp']:.2f} pp | {_verdict(gate['calibration'])} |",
        f"| Retrodictive violations vs every scored system | at or below all of "
        f"`{thr['violations_must_beat']}` | {obs['retrodictive_violation_rate']:.4f} "
        f"| {_verdict(gate['violations_vs_baselines'])} |",
    ]


def _decile_rows(table: list[dict[str, float]]) -> list[str]:
    out = [
        "| Predicted decile | n | Mean predicted | Observed | Deviation |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in table:
        if not row["n"]:
            continue
        dev = (row["observed_rate"] - row["mean_predicted"]) * 100.0
        thin = "" if row["counted"] else " *(uncounted)*"
        out.append(
            f"| {row['bin_low']:.1f}–{row['bin_high']:.1f}{thin} | {int(row['n'])} "
            f"| {row['mean_predicted']:.3f} | {row['observed_rate']:.3f} | {dev:+.2f} pp |"
        )
    return out


def _demo_cross_check(observed_here: dict[str, Any]) -> str:
    demo = ROOT / "demo" / "backtest-2021-2023.json"
    if not demo.exists():
        return "> `demo/backtest-2021-2023.json` is absent - cross-check not run."
    observed = json.loads(demo.read_text())["systems"]["schedule_odds"]["gate"]["observed"]
    if observed == observed_here:
        return (
            "> **Checked and identical**, to the last float: "
            f"MAE {observed['mae']:.6f}, RMSE {observed['rmse']:.6f}, SU "
            f"{observed['su_accuracy']:.6f}, calibration "
            f"{observed['max_calibration_deviation_pp']:.6f} pp, violations "
            f"{observed['retrodictive_violation_rate']:.6f}."
        )
    return (
        "> **THEY DISAGREE.** This document says "
        f"`{json.dumps(observed_here, sort_keys=True)}`; "
        f"`demo/backtest-2021-2023.json` says `{json.dumps(observed, sort_keys=True)}`. "
        "One of them is wrong and the campaign is not publishable until it is known which."
    )


def render(store: dict[str, Any]) -> None:  # noqa: PLR0915 - one long document
    br, tr = store["bracket"], store["trailing"]
    frozen, val = store["frozen"], store["validation"]
    hf, disp = store["homefield"], store["dispersion"]
    runs = {(r["label"], r["season_set"]): r for r in val["runs"]}
    verdicts = val["verdicts"]
    prov = store["provenance"]
    adopted = [k for k, v in verdicts.items() if v["adopted"]]

    lines: list[str] = [
        "<!-- GENERATED by scripts/campaign_2.py. Do not edit by hand. -->",
        "",
        "> ## STATUS: CLOSED, 2026-08-12",
        "> ",
        "> **What moved:** "
        + (
            ", ".join(sorted(adopted))
            if adopted
            else "**nothing. All three leads leave `configs/default.toml` where ADR 0007 put it.**"
        )
        + ".",
        "> ",
        f"> **Lead 1 — C is bracketed now.** The widened grid ends at `c = inf`, the "
        f"uncompressed identity response, so it cannot produce another corner. The "
        f"optimum is C = {_c_label(br['best']['c'])}, β_w = {br['best']['beta_w']:g}, "
        f"which beats the incumbent by {-br['tune_mae_delta']:.4f} points of tune MAE "
        f"across a grid spanning {br['spread']:.3f}.",
        "> ",
        f"> **Lead 2 — the accumulation window.** The best trailing cell is σ over "
        f"{_k_label(tr['best']['sigma_trailing'])} buckets and the calibration over "
        f"{_k_label(tr['best']['calib_trailing'])}, worth "
        f"{tr['tune_calibration_delta_pp']:+.2f} pp of tune calibration deviation "
        f"against a bar of {CALIBRATION_ADOPT_PP} pp.",
        "> ",
        "> **Lead 3 — the home-field anchor was run and the config did not move, as "
        "the protocol said it would not.** What it raises is a constraint question "
        "and [ADR 0008](../adr/0008-league-structural-home-field.md) puts it to the "
        "owner, unresolved and labelled as such.",
        "> ",
        "> The protocol below is reproduced **verbatim from the commit that "
        "pre-registered it**. Where it speaks in the future tense about numbers, that "
        "was true when it was written and is the point of writing it first.",
        "",
        "---",
        "",
        PROTOCOL.rstrip(),
        "",
        "---",
        "",
    ]

    # ---------------- LEAD 1 ----------------
    lines += [
        "## PART 1 — LEAD 1: BRACKETING C",
        "",
        f"**{br['n_cells']} cells, the full pre-registered grid, no subsample.** "
        f"{br['elapsed_seconds'] / 60:.1f} minutes of wall clock. Every number is "
        "walk-forward MAE on the tune seasons over the headline window, FBS-vs-FBS, "
        "with garbage time at `connelly` and prediction compression off — the two "
        "values campaign 1's 416-cell factorial chose in 208 of 208 paired cells each.",
        "",
        "Rows are C, columns β_w. The incumbent cell is **bold**; the optimum is "
        "*italic*. Lower is better.",
        "",
        "| C \\ β_w | " + " | ".join(f"{b:g}" for b in BETA_GRID) + " |",
        "|---" * (len(BETA_GRID) + 1) + "|",
    ]
    by_cell = {(r["c"], r["beta_w"]): r for r in br["cells"]}
    best, incumbent_cell = br["best"], br["incumbent_cell"]
    for c in C_GRID:
        cells = []
        for b in BETA_GRID:
            row = by_cell[(c, b)]
            text = f"{row['mae']:.3f}"
            if (c, b) == (best["c"], best["beta_w"]):
                text = f"*{text}*"
            if (c, b) == (incumbent_cell["c"], incumbent_cell["beta_w"]):
                text = f"**{text}**"
            cells.append(text)
        lines.append(f"| **{_c_label(c)}** | " + " | ".join(cells) + " |")

    lines += [
        "",
        "### The ten best cells, and the incumbent",
        "",
        "| C | β_w | MAE | RMSE | SU % | Brier | Max calib. dev. |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in br["cells"][:10]:
        lines.append(
            f"| {_c_label(row['c'])} | {row['beta_w']:g} | {row['mae']:.4f} "
            f"| {row['rmse']:.4f} | {row['su_accuracy'] * 100:.2f} | {row['brier']:.5f} "
            f"| {row['max_calibration_deviation_pp']:.2f} pp |"
        )
    lines += [
        f"| **{_c_label(incumbent_cell['c'])}** | **{incumbent_cell['beta_w']:g}** "
        f"| **{incumbent_cell['mae']:.4f}** | **{incumbent_cell['rmse']:.4f}** "
        f"| **{incumbent_cell['su_accuracy'] * 100:.2f}** | **{incumbent_cell['brier']:.5f}** "
        f"| **{incumbent_cell['max_calibration_deviation_pp']:.2f} pp** |",
        "",
        f"The bold row is the incumbent — **rank {br['incumbent_rank']} of "
        f"{br['n_cells']}**. **The whole grid spans {br['spread']:.3f} points of MAE**, "
        f"and the best cell beats the incumbent by {-br['tune_mae_delta']:.4f} — against "
        f"the {NOISE_FLOOR_MAE} the protocol fixed as the noise floor before any of this "
        "was computed.",
        "",
        "### Is the corner resolved?",
        "",
    ]
    if br["c_at_uncompressed_limit"]:
        lines += [
            "**THE OPTIMUM IS `c = inf`: THIS DATASET DOES NOT WANT THE TANH AT ALL.** "
            "That is a substantive claim about the model rather than a request for a "
            "wider grid — `inf` is the limit of the family, so there is nothing above "
            "it to search. It says the compression that answers the BCS sportsmanship "
            "objection costs MAE on this data, which is a trade the project may still "
            "want to make for reasons that are not predictive.",
            "",
        ]
    elif br["c_at_lower_edge"]:
        lines += [
            f"**The optimum is at C = {_c_label(best['c'])}, the BOTTOM of the widened "
            "grid**, which is campaign 1's own optimum and the bottom of this grid by "
            "construction. The widening was upward, so a lower optimum would be a "
            "corner in the other direction and is reported as one.",
            "",
        ]
    else:
        lines += [
            f"**Yes. C = {_c_label(best['c'])} is INTERIOR to the widened grid** — "
            f"{C_GRID[0]} and `inf` are both searched and neither wins. Campaign 1's "
            "corner was a property of a grid whose bounds were Pasteur's cap of 21 and "
            "the CFBD SRS walkthrough's ±28, and on this dataset the answer sits above "
            "both of them and below the point where compression stops mattering. **The "
            "question ADR 0007 left open is closed.**",
            "",
        ]
    if br["beta_w_at_grid_edge"]:
        lines += [
            f"**β_w = {best['beta_w']:g} is on the edge of its own grid** and is "
            "reported as an edge exactly as C = 32 was.",
            "",
        ]

    # ---------------- LEAD 2 ----------------
    lines += [
        "## PART 2 — LEAD 2: THE SHAPE OF THE ACCUMULATION WINDOW",
        "",
        f"**{tr['n_cells']} cells**, searched as a product rather than in two stages, "
        f"because both estimators enter the same probability. "
        f"{tr['elapsed_seconds'] / 60:.1f} minutes of wall clock. The objective here is "
        "the **maximum decile calibration deviation**, which is a different objective "
        "from lead 1's and was declared as one in advance; MAE and Brier are guards.",
        "",
        "Rows are the σ window, columns the calibration window, both in buckets. "
        "*(all, all)* is the estimator that runs today and is **bold**; the optimum is "
        "*italic*. Lower is better.",
        "",
        "| σ \\ calib. | " + " | ".join(_k_label(k) for k in TRAILING_GRID) + " |",
        "|---" * (len(TRAILING_GRID) + 1) + "|",
    ]
    by_trail = {(r["sigma_trailing"], r["calib_trailing"]): r for r in tr["cells"]}
    tbest, tincumbent = tr["best"], tr["incumbent_cell"]
    for s in TRAILING_GRID:
        cells = []
        for k in TRAILING_GRID:
            row = by_trail[(s, k)]
            text = f"{row['max_calibration_deviation_pp']:.2f}"
            if (s, k) == (tbest["sigma_trailing"], tbest["calib_trailing"]):
                text = f"*{text}*"
            if (s, k) == (0, 0):
                text = f"**{text}**"
            cells.append(text)
        lines.append(f"| **{_k_label(s)}** | " + " | ".join(cells) + " |")

    lines += [
        "",
        "### Every cell, on every column that decides anything",
        "",
        "| σ window | calib. window | Max calib. dev. | MAE | RMSE | SU % | Brier | Mean σ |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in tr["cells"]:
        mark = "**" if (row["sigma_trailing"], row["calib_trailing"]) == (0, 0) else ""
        lines.append(
            f"| {mark}{_k_label(row['sigma_trailing'])}{mark} "
            f"| {mark}{_k_label(row['calib_trailing'])}{mark} "
            f"| {row['max_calibration_deviation_pp']:.2f} pp | {row['mae']:.4f} "
            f"| {row['rmse']:.4f} | {row['su_accuracy'] * 100:.2f} | {row['brier']:.5f} "
            f"| {row['sigma_mean']:.2f} |"
        )
    guard = tr["paired_guard"]
    lines += [
        "",
        f"The best cell cuts the deviation by **{tr['tune_calibration_delta_pp']:+.2f} pp** "
        f"against a bar of {CALIBRATION_ADOPT_PP} pp fixed in advance, and the whole grid "
        f"spans {tr['spread_pp']:.2f} pp. Its guards, both declared before it was run:",
        "",
        "| Guard | Threshold | Observed | Clears? |",
        "|---|---|---:|---|",
        f"| Tune MAE vs incumbent | <= +{NOISE_FLOOR_MAE} | "
        f"{tr['tune_mae_delta']:+.4f} | "
        f"{'yes' if tr['tune_mae_delta'] <= NOISE_FLOOR_MAE else '**no**'} |",
        f"| Tune Brier vs incumbent | <= +1 paired SE "
        f"({guard['brier_paired_standard_error']:.5f}) "
        f"| {guard['brier_mean_paired_difference']:+.5f} | "
        f"{'yes' if guard['brier_within_one_paired_se'] else '**no**'} |",
        "",
        "The Brier guard is a **paired** standard error over the identical "
        f"{guard['n_games']} games. Both cells score the same games in the same order, "
        "so pairing removes the game-to-game variance that would otherwise swamp any "
        "difference and make the guard vacuous.",
        "",
        "The incumbent's decile table, and the best cell's, in the gate's own bins:",
        "",
        "**Incumbent — σ over all buckets, calibration over all buckets**",
        "",
        *_decile_rows(guard["incumbent_table"]),
        "",
        f"**Best cell — σ over {_k_label(tbest['sigma_trailing'])}, calibration over "
        f"{_k_label(tbest['calib_trailing'])}**",
        "",
        *_decile_rows(guard["candidate_table"]),
        "",
    ]
    del tincumbent

    # ---------------- the joint cell ----------------
    joint = store.get("joint") or {}
    lines += ["### The interaction, which the protocol required in advance", ""]
    if joint.get("run"):
        cell, vs = joint["cell"], joint["vs_incumbent"]
        lines += [
            "Both leads cleared their own tune-season rule, so the joint cell was run:",
            "",
            "| | MAE | Max calib. dev. | Brier | vs incumbent (MAE) | vs incumbent (calib.) |",
            "|---|---:|---:|---:|---:|---:|",
            f"| joint | {cell['mae']:.4f} | {cell['max_calibration_deviation_pp']:.2f} pp "
            f"| {cell['brier']:.5f} | {vs['mae_delta']:+.4f} "
            f"| {vs['calibration_delta_pp']:+.2f} pp |",
            "",
        ]
    else:
        lines += [
            "> " + joint.get("reason", "not run") + ".",
            "",
            f"Lead 1 cleared its tune rule: **{joint.get('lead1_clears')}**. Lead 2 "
            f"cleared its tune rule: **{joint.get('lead2_clears_tune')}**.",
            "",
        ]

    # ---------------- PART 3: the frozen choices ----------------
    lines += [
        "## PART 3 — THE FROZEN CHOICES",
        "",
        "Frozen on the tune seasons, committed in writing, and only then evaluated on "
        "2024. The commit that froze them contains no 2024 number.",
        "",
        "| Lead | Parameter | Incumbent | Frozen |",
        "|---|---|---|---|",
        f"| 1 | `[margin].c` | {_c_label(frozen['incumbent']['c'])} "
        f"| **{_c_label(frozen['lead1']['c'])}** |",
        f"| 1 | `[margin].beta_w` | {frozen['incumbent']['beta_w']:g} "
        f"| **{frozen['lead1']['beta_w']:g}** |",
        f"| 2 | `[resume].sigma_trailing_buckets` "
        f"| {_k_label(frozen['incumbent']['sigma_trailing'])} "
        f"| **{_k_label(frozen['lead2']['sigma_trailing'])}** |",
        f"| 2 | `[backtest].calibration_trailing_buckets` "
        f"| {_k_label(frozen['incumbent']['calib_trailing'])} "
        f"| **{_k_label(frozen['lead2']['calib_trailing'])}** |",
        "",
        "## PART 4 — 2024, EVALUATED ONCE PER ARM",
        "",
        "One evaluation per arm, after the choices above were frozen. 2025 was not read. "
        "**2024 has now been read twice** — once by campaign 1 and once here — and ADR "
        "0007 required that every decision reading it again say so publicly. This is that "
        "statement.",
        "",
        "| | Tune 2021-2023 | | | 2024 validation | | |",
        "|---|---:|---:|---:|---:|---:|---:|",
        "| | incumbent | lead 1 | lead 2 | incumbent | lead 1 | lead 2 |",
    ]

    def _cells(field: str, fmt: str, scale: float = 1.0) -> str:
        out = []
        for season_set in ("tune", "validate"):
            for label in ("incumbent", "lead1", "lead2"):
                value = runs[(label, season_set)][field]
                out.append(format(int(value) if fmt == "d" else value * scale, fmt))
        return " | ".join(out)

    lines += [
        f"| n games | {_cells('n_games', 'd')} |",
        f"| **MAE** | {_cells('mae', '.4f')} |",
        f"| RMSE | {_cells('rmse', '.4f')} |",
        f"| SU % | {_cells('su_accuracy', '.2f', 100.0)} |",
        f"| Brier | {_cells('brier', '.5f')} |",
        f"| Max calib. dev. (pp) | {_cells('max_calibration_deviation_pp', '.2f')} |",
        f"| Headline violations | {_cells('headline_violation_rate', '.4f')} |",
        "",
        "### The verdicts, by the rules fixed before any of this was run",
        "",
        "| Arm | Tune Δ MAE | 2024 Δ MAE | Tune Δ calib. | 2024 Δ calib. | Verdict |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for label in ("lead1", "lead2", "joint"):
        if label not in verdicts:
            continue
        v = verdicts[label]
        lines.append(
            f"| {label} | {v['tune_mae_delta']:+.4f} | {v['validate_mae_delta']:+.4f} "
            f"| {v['tune_calibration_delta_pp']:+.2f} pp "
            f"| {v['validate_calibration_delta_pp']:+.2f} pp "
            f"| {'**ADOPTED**' if v['adopted'] else '**REJECTED** — the config keeps the incumbent'} |"  # noqa: E501
        )
    lines += [
        "",
        *[f"- **{label}** — rule: *{verdicts[label]['rule']}*" for label in sorted(verdicts)],
        "",
    ]

    # ---------------- PART 4b: what an arm does to the poll ----------------
    rank_block = store.get("ranking_impact")
    if rank_block:
        lines += [
            "## PART 4b — WHAT AN ARM DOES TO THE POLL",
            "",
            "**This is a disclosure, not a gate.** The adoption rules were fixed in the "
            "protocol and none of them mentions Kendall's τ; adding one now, after the "
            "numbers, would be the failure the protocol exists to prevent. But ADR 0006 "
            "imposes a standing labelling obligation — a change whose τ against the "
            f"incumbent falls below the {rank_block['tau_floor']} that the published "
            "`q_ref` sweep never dipped below is a **dial** rather than a convention and "
            "must be called one — and campaign 1 discharged exactly that obligation in "
            "its PART 4b.",
            "",
            "It matters more here. `β_w` is the discontinuity that makes this a football "
            "ranking rather than a scoring-margin ranking, which is a statement about "
            "**desert**, and lead 1's objective is margin MAE, which has no opinion about "
            "desert at all. An arm that buys a few thousandths of a point of MAE with a "
            "large ranking change is not obviously a good trade, and the only way a "
            "reader can judge it is to see both numbers side by side.",
            "",
            "Final pre-postseason headline poll, each tune season, incumbent vs arm:",
            "",
            "| Arm | Season | Kendall's τ | Mean \\|Δrank\\| | Max \\|Δrank\\| | Top-25 changes | Verdict |",  # noqa: E501
            "|---|---|---:|---:|---:|---:|---|",
        ]
        for label in sorted(rank_block["arms"]):
            block = rank_block["arms"][label]
            for season in sorted(block["by_season"]):
                mv = block["by_season"][season]["movement"]
                lines.append(
                    f"| {label} | {season} | {mv['kendall_tau']:.4f} "
                    f"| {mv['mean_abs_rank_delta']:.2f} | {mv['max_abs_rank_delta']} "
                    f"| {mv['top25_membership_changes']} "
                    f"| {'**A DIAL**' if mv['is_a_dial'] else 'a convention'} |"
                )
        for label in sorted(rank_block["arms"]):
            block = rank_block["arms"][label]
            latest = max(block["by_season"])
            lines += [
                "",
                f"**`{label}`: minimum τ across the tune seasons is "
                f"{block['min_kendall_tau']:.4f}** — "
                + (
                    "**below the floor, so this is a DIAL by the project's own published "
                    "standard and is labelled as one in the config and in the ADR.**"
                    if block["is_a_dial"]
                    else "above the floor, so by the project's own published standard the "
                    "change is a convention rather than a dial. It is still published "
                    "here, because \"small\" is a measurement and not an assurance."
                ),
                "",
                f"Biggest movers, {latest}:",
                "",
                "| Team | Incumbent | Arm |",
                "|---|---:|---:|",
            ]
            for mover in block["by_season"][latest]["movement"]["biggest_movers"]:
                lines.append(f"| {mover['team']} | {mover['incumbent']} | {mover['arm']} |")
            lines += [
                "",
                f"Top ten, {latest} — incumbent: "
                + ", ".join(block["by_season"][latest]["top10_incumbent"]),
                "",
                f"Top ten, {latest} — `{label}`: "
                + ", ".join(block["by_season"][latest]["top10_arm"]),
                "",
            ]

    # ---------------- PART 5: the under-dispersion question ----------------
    ref = disp["campaign_1_reference"]
    lines += [
        "## PART 5 — IS THE UNDER-DISPERSION FIXED?",
        "",
        "Campaign 1's diagnosis was that the point forecasts are under-dispersed: the "
        f"slope of actual on predicted margin was {ref['tune_slope']:.4f} ± "
        f"{ref['tune_slope_stderr']:.4f} on tune and {ref['validate_slope']:.4f} ± "
        f"{ref['validate_slope_stderr']:.4f} on 2024, measured on "
        f"{ref['measured_on']}. A campaign that changes σ and the calibration slope owes "
        "a direct answer about that quantity rather than an inference from the decile "
        "table, so here it is, re-measured on this campaign's own incumbent and on every "
        "arm.",
        "",
        "| Arm | Season set | Slope | SE | σ above 1 | Intercept | Mean residual | Mean σ | Max calib. dev. |",  # noqa: E501
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key in sorted(disp["arms"]):
        row = disp["arms"][key]
        label, season_set = key.rsplit("_", 1)
        lines.append(
            f"| {label} | {season_set} | {row['slope']:.4f} | {row['slope_stderr']:.4f} "
            f"| {row['slope_z_above_one']:+.1f} | {row['intercept']:+.3f} "
            f"| {row['residual_mean']:+.3f} | {row['sigma_mean']:.2f} "
            f"| {row['max_deviation_pp']:.2f} pp |"
        )
    lines += [""]

    # ---------------- PART 6: lead 3 ----------------
    lines += [
        "## PART 6 — LEAD 3: THE LEAGUE-STRUCTURAL HOME FIELD",
        "",
        "**Read the protocol's PART 0.5 first.** It states the case for and the case "
        "against ratifying a cross-season `h`, in full, and it was written before any "
        "number in this section existed. Nothing below is allowed to re-weight it.",
        "",
        "### What the estimator gives, season by season",
        "",
        "`h` for a season is pooled over every archived season **strictly before** it — "
        "walk-forward across seasons, exactly as everything else here is walk-forward "
        "within one. 2025 is not in the pool at all.",
        "",
        "| Season | Prior seasons pooled | h | n pairs | SE |",
        "|---|---|---:|---:|---:|",
    ]
    for season in sorted(hf["per_season_prior_pool"]):
        row = hf["per_season_prior_pool"][season]
        pooled = ", ".join(str(s) for s in row["prior_seasons"]) or "**none**"
        h = "—" if not row["n_pairs"] else f"{row['h']:.3f}"
        se = row.get("standard_error")
        se_text = "—" if se is None or not np.isfinite(se) else f"{se:.3f}"
        lines.append(f"| {season} | {pooled} | {h} | {row['n_pairs']} | {se_text} |")

    reg = hf["regression_coefficient"]
    lines += [
        "",
        "Against the two numbers campaign 1 put on the record, and the constants the "
        "config carries as reference values:",
        "",
        "| Estimate | h | n | SE |",
        "|---|---:|---:|---:|",
        f"| The site coefficient that ACTUALLY RUNS, mean over published weeks "
        f"| {reg['mean']:.3f} | {reg['n_weeks']} weeks | sd {reg['sd']:.3f} |",
        f"| Home-and-home, pooled over 2021-2023 (**not runnable live**) "
        f"| {hf['pooled_tune_NOT_RUNNABLE']['h']:.3f} "
        f"| {hf['pooled_tune_NOT_RUNNABLE']['n_pairs']} pairs "
        f"| {hf['pooled_tune_NOT_RUNNABLE']['standard_error']:.3f} |",
        f"| Home-and-home, WITHIN season (the only form constraint 2 allows) "
        f"| {hf['within_season_tune']['h']:.3f} "
        f"| {hf['within_season_tune']['n_pairs']} pairs "
        f"| {hf['within_season_tune']['standard_error']:.3f} |",
        f"| `[homefield].h_pasteur` (inherited constant) | {hf['config_h_pasteur']:.2f} | — | — |",
        f"| `[homefield].h_recent_estimate` (inherited constant) "
        f"| {hf['config_h_recent_estimate']:.2f} | — | — |",
        "",
        "### What anchoring it does",
        "",
        "| Arm | Seasons | MAE | RMSE | SU % | Brier | Max calib. dev. | Violations | Slope |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key in (
        "incumbent_tune",
        "arm_a_tune",
        "arm_b_tune_NOT_RUNNABLE",
        "incumbent_validate",
        "arm_a_validate",
    ):
        row = hf["arms"][key]
        lines.append(
            f"| {key.replace('_', ' ')} | {'-'.join(str(s) for s in (row['seasons'][0], row['seasons'][-1]))} "  # noqa: E501
            f"| {row['mae']:.4f} | {row['rmse']:.4f} | {row['su_accuracy'] * 100:.2f} "
            f"| {row['brier']:.5f} | {row['max_calibration_deviation_pp']:.2f} pp "
            f"| {row['headline_violation_rate']:.4f} | {row['slope']:.4f} |"
        )

    guard_block = store.get("constraint_guard", {})
    lines += [
        "",
        "### The default did not move, and the guard is exercised rather than described",
        "",
        "`configs/default.toml` carries `[homefield].anchor_h_by_season = {}` and "
        "`[constraints].allow_prior_season_data = false`, exactly as it did before this "
        "campaign opened. The protocol fixed that before the numbers above existed.",
        "",
        "A constraint enforced only by a comment is a preference. So the harness is "
        "asked, here, to run an anchored config with the constraint key at its live "
        "value:",
        "",
        f"> `{guard_block.get('exception') or 'nothing'}` raised: "
        f"**{guard_block.get('raised')}**",
        "",
        "```",
        (guard_block.get("message") or "").strip(),
        "```",
        "",
        "The only place in this repository that flips "
        "`[constraints].allow_prior_season_data` is `scripts/campaign_2.py`'s `anchor` "
        "override, for the duration of one experiment.",
        "",
    ]

    # ---------------- PART 7: the gate ----------------
    before = runs[("incumbent", "tune")]["gate"]
    lines += [
        "## PART 7 — THE GATE, BEFORE AND AFTER",
        "",
        "The headline ordering's own gate object, on the tune seasons, headline window.",
        "",
        "### Before — the incumbent, which is the config as ADR 0007 left it",
        "",
        *_gate_table(before),
        "",
    ]
    after_label = "joint" if verdicts.get("joint", {}).get("adopted") else None
    if after_label is None:
        after_label = next(
            (k for k in ("lead2", "lead1") if verdicts.get(k, {}).get("adopted")), None
        )
    if after_label is None:
        lines += [
            "### After — **there is no after**",
            "",
            "No arm cleared its pre-registered rule, so `configs/default.toml` is "
            "unchanged and the gate table above is also the table below. That is the "
            "campaign reporting a negative result rather than finding something to "
            "adopt, which is what the protocol was written to make possible.",
            "",
        ]
        after_observed = before["observed"]
    else:
        after = runs[(after_label, "tune")]["gate"]
        lines += [
            f"### After — the adopted arm (`{after_label}`)",
            "",
            *_gate_table(after),
            "",
        ]
        after_observed = after["observed"]

    lines += [
        "```json",
        json.dumps(
            {
                "before": {
                    k: v for k, v in before.items() if k != "violations_vs_baselines_detail"
                },
                "after": {
                    k: v
                    for k, v in runs[(after_label or "incumbent", "tune")]["gate"].items()
                    if k != "violations_vs_baselines_detail"
                },
            },
            indent=2,
            sort_keys=True,
            default=float,
        ),
        "```",
        "",
        "---",
        "",
        "### The page cannot disagree with the pipeline",
        "",
        "The demo is regenerated from `configs/default.toml`; this document's gate was "
        "produced by overriding named keys on the same file. If those two ever disagree, "
        "one of them is lying about what the pipeline does.",
        "",
        _demo_cross_check(after_observed),
        "",
        f"*Generated by `scripts/campaign_2.py` at commit `{prov['commit'][:10]}`; every "
        f"number above is in `campaign-2.json`. Config hash `{prov['config_hash'][:16]}`. "
        f"Holdout touched: {str(prov['holdout_touched']).lower()}.*",
        "",
    ]
    MD_PATH.write_text("\n".join(lines))


# ----------------------------------------------------------------------------
# provenance and IO
# ----------------------------------------------------------------------------
def _provenance() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # pragma: no cover
        commit = "unknown"
    return {
        "generated_utc": datetime.now(UTC).isoformat(),
        "commit": commit,
        "config": str(DEFAULT_CONFIG_PATH.relative_to(ROOT)),
        "config_hash": config_hash(DEFAULT_CONFIG_PATH),
        "tune_seasons": list(TUNE_SEASONS),
        "validate_seasons": list(VALIDATE_SEASONS),
        "holdout_touched": False,
    }


def _load_store() -> dict[str, Any]:
    if JSON_PATH.exists():
        return json.loads(JSON_PATH.read_text())
    return {}


def _valid_json(obj: Any) -> Any:
    """nan and inf out, null in.

    `json.dumps` writes `NaN` and `Infinity` by default and only Python's own
    parser reads them back. A published artifact that one language can read is not
    a published artifact, and this campaign has both: `c = inf` is a real value of
    a real parameter, and a standard error over one pair is undefined.
    """
    if isinstance(obj, dict):
        return {k: _valid_json(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_valid_json(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def _save_store(store: dict[str, Any]) -> None:
    store["provenance"] = _provenance()
    JSON_PATH.write_text(
        json.dumps(
            _valid_json(store), indent=2, sort_keys=True, default=float, allow_nan=False
        )
        + "\n"
    )


STAGES = {
    "bracket": stage_bracket,
    "trailing": stage_trailing,
    "joint": stage_joint,
    "freeze": stage_freeze,
    "validate": stage_validate,
    "ranking": stage_ranking,
    "homefield": stage_homefield,
    "dispersion": stage_dispersion,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stages",
        nargs="*",
        default=[*STAGES, "render"],
        help=" | ".join([*STAGES, "render"]),
    )
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    store = _load_store()
    for stage in args.stages:
        print(f"[stage] {stage}", flush=True)
        if stage == "render":
            _save_store(store)
            render(store)
            print(f"  wrote: {MD_PATH.relative_to(ROOT)}", flush=True)
        elif stage in STAGES:
            STAGES[stage](store, args.workers)
            print("  " + json.dumps(store.get(stage, {}), default=float)[:600], flush=True)
        else:
            raise SystemExit(f"unknown stage {stage!r}")
        _save_store(store)
    print(f"wrote: {JSON_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
