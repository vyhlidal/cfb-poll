"""The hyperparameter campaign and the calibration diagnosis, end to end.

Writes docs/analysis/tuning-campaign.json (every number) and fills in the results
sections of docs/analysis/tuning-campaign.md (the protocol header of which was
committed BEFORE this script existed - see `git log --follow` on that file).

Every constant in configs/default.toml is at an unfitted starting value and the
grids the config publishes have never been searched. The publication gate fails
all five decidable criteria. This script searches the grids under a protocol
fixed in advance, freezes one choice, evaluates it ONCE on 2024, and diagnoses
why the calibration miss is asymmetric.

STAGES, each resumable, each writing into the same JSON:

    grid         [margin].c x [margin].beta_w, the full 8 x 13 published grid
    modes        [garbage_time].mode x [margin.prediction_compression].enabled,
                 on the grid optimum and its neighbourhood
    validate     2024, ONCE, for the frozen winner and for the starting values
    calibration  the four pre-declared candidate fixes
    render       tuning-campaign.md from the JSON

2025 IS NEVER READ. No stage passes `unlock_holdout`, and `--seasons` cannot
reach it: the harness raises `HoldoutLocked` and this script does not catch it.

WHY THE GRID IS SCORED ON `l3` ALONE. The headline ordering `schedule_odds`
predicts through its Power source ([resume].power_source = "L3"), so its
predictive row IS L3's row by construction - the demo's gate numbers and L3's
segment numbers are the same floats. Scoring the grid on one system makes 104
cells affordable at full resolution instead of forcing a subsample. Violations,
which are about the ordering rather than about Power, are recomputed with the
full system list for the frozen winner only.
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

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "analysis"
JSON_PATH = OUT / "tuning-campaign.json"
MD_PATH = OUT / "tuning-campaign.md"

TUNE_SEASONS = (2021, 2022, 2023)
VALIDATE_SEASONS = (2024,)

#: The objective's system. See the module docstring for why one is enough.
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

#: The noise floor, in points of MAE, fixed by the protocol before any number was
#: read. It is not invented for this campaign: it is the margin by which ADR 0006
#: chose the fit universe and explicitly called "inside the noise floor for three
#: seasons". The same quantity cannot be noise when it decides one thing and
#: signal when it decides another.
NOISE_FLOOR_MAE = 0.055

#: A calibration fix is adopted only if it cuts the max decile deviation by at
#: least this much on the tune seasons AND holds direction on 2024.
CALIBRATION_ADOPT_PP = 2.0

_GAMES: pl.DataFrame | None = None
_PLAYS: pl.DataFrame | None = None
_SEASONS: tuple[int, ...] = ()


# ----------------------------------------------------------------------------
# the harness, wrapped once
# ----------------------------------------------------------------------------
def _init(seasons: tuple[int, ...]) -> None:
    """Load the archive once per process. Loading costs 0.23 s; refitting does not."""
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
    """One walk-forward run. `_GAMES`/`_PLAYS` are the process-wide archive."""
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
        elif key == "garbage_time_mode":
            cfg["garbage_time"]["mode"] = str(value)
        elif key == "prediction_compression":
            cfg["margin"]["prediction_compression"]["enabled"] = bool(value)
        elif key == "homefield_method":
            cfg["homefield"]["method"] = str(value)
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


def _run_cell(spec: dict[str, Any]) -> dict[str, Any]:
    """Pool worker: one grid cell, returned as a flat row."""
    base = load_config()
    cfg = _cell_config(base, **spec)
    result = _score(cfg, _SEASONS)
    return {**spec, **_summary(result)}


# ----------------------------------------------------------------------------
# stage 1 - the published C x beta_w grid, in full
# ----------------------------------------------------------------------------
def stage_grid(store: dict[str, Any], workers: int) -> None:
    cfg = load_config()
    c_grid = [float(x) for x in cfg["margin"]["c_grid"]]
    beta_grid = [float(x) for x in cfg["margin"]["beta_w_grid"]]
    specs = [{"c": c, "beta_w": b} for c in c_grid for b in beta_grid]

    started = datetime.now(UTC)
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init, initargs=(TUNE_SEASONS,)
    ) as pool:
        rows = list(pool.map(_run_cell, specs))
    elapsed = (datetime.now(UTC) - started).total_seconds()

    rows.sort(key=lambda r: (r["mae"], r["brier"]))
    store["grid"] = {
        "search_space": {"c": c_grid, "beta_w": beta_grid},
        "cells": rows,
        "n_cells": len(rows),
        "subsampled": False,
        "elapsed_seconds": elapsed,
        "objective": "walk-forward MAE, tune seasons, headline window, fbs_vs_fbs",
        "best": rows[0],
        "starting_values": next(
            r
            for r in rows
            if r["c"] == float(cfg["margin"]["c"]) and r["beta_w"] == float(cfg["margin"]["beta_w"])
        ),
    }


# ----------------------------------------------------------------------------
# stage 2 - the two mode switches
# ----------------------------------------------------------------------------
def stage_full(store: dict[str, Any], workers: int) -> None:
    """The COMPLETE factorial: C x beta_w x garbage_time x prediction_compression.

    The protocol's own escape clause: "the full 416 is run only if the second
    stage moves the optimum." A two-stage search that changes a mode has located
    (C, beta_w) under a different mode from the one it ends up recommending, and
    the honest repair is to search the product rather than to argue that the
    interaction is probably small.
    """
    cfg = load_config()
    c_grid = [float(x) for x in cfg["margin"]["c_grid"]]
    beta_grid = [float(x) for x in cfg["margin"]["beta_w_grid"]]
    specs = [
        {"c": c, "beta_w": b, "garbage_time_mode": gt, "prediction_compression": pc}
        for c in c_grid
        for b in beta_grid
        for gt in ("connelly", "strict")
        for pc in (False, True)
    ]
    started = datetime.now(UTC)
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init, initargs=(TUNE_SEASONS,)
    ) as pool:
        rows = list(pool.map(_run_cell, specs))
    elapsed = (datetime.now(UTC) - started).total_seconds()
    rows.sort(key=lambda r: (r["mae"], r["brier"]))
    incumbent = _starting_values()
    store["full_factorial"] = {
        "search_space": {
            "c": c_grid,
            "beta_w": beta_grid,
            "garbage_time_mode": ["connelly", "strict"],
            "prediction_compression": [False, True],
        },
        "cells": rows,
        "n_cells": len(rows),
        "elapsed_seconds": elapsed,
        "best": rows[0],
        "incumbent_cell": next(
            r
            for r in rows
            if r["c"] == incumbent["c"]
            and r["beta_w"] == incumbent["beta_w"]
            and r["garbage_time_mode"] == incumbent["garbage_time_mode"]
            and r["prediction_compression"] == incumbent["prediction_compression"]
        ),
        "corner_solution": {
            "c_at_grid_edge": rows[0]["c"] in (min(c_grid), max(c_grid)),
            "beta_w_at_grid_edge": rows[0]["beta_w"] in (min(beta_grid), max(beta_grid)),
        },
    }


def stage_modes(store: dict[str, Any], workers: int) -> None:
    """`garbage_time.mode` x `prediction_compression.enabled`, on the optimum
    and its four grid neighbours, so a mode that only wins at one point in
    (C, beta_w) cannot masquerade as a mode that wins."""
    cfg = load_config()
    c_grid = [float(x) for x in cfg["margin"]["c_grid"]]
    beta_grid = [float(x) for x in cfg["margin"]["beta_w_grid"]]
    best = store["grid"]["best"]
    ci = c_grid.index(best["c"])
    bi = beta_grid.index(best["beta_w"])
    def _clamp(values: list[float], index: int) -> float:
        return values[max(0, min(len(values) - 1, index))]

    neighbourhood = sorted(
        {
            (_clamp(c_grid, ci + dc), _clamp(beta_grid, bi + db))
            for dc, db in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))
        }
    )
    specs = [
        {"c": c, "beta_w": b, "garbage_time_mode": gt, "prediction_compression": pc}
        for c, b in neighbourhood
        for gt in ("connelly", "strict")
        for pc in (False, True)
    ]
    started = datetime.now(UTC)
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init, initargs=(TUNE_SEASONS,)
    ) as pool:
        rows = list(pool.map(_run_cell, specs))
    elapsed = (datetime.now(UTC) - started).total_seconds()
    rows.sort(key=lambda r: (r["mae"], r["brier"]))
    store["modes"] = {
        "neighbourhood": [{"c": c, "beta_w": b} for c, b in neighbourhood],
        "cells": rows,
        "n_cells": len(rows),
        "elapsed_seconds": elapsed,
        "best": rows[0],
    }


# ----------------------------------------------------------------------------
# stage 3 - freeze, then validate on 2024 exactly once
# ----------------------------------------------------------------------------
def _frozen_choice(store: dict[str, Any]) -> dict[str, Any]:
    """The tune-season winner, as a set of config overrides. Frozen before 2024.

    The full factorial wins when it exists, because the protocol says so: the
    two-stage search MOVED the optimum's mode, which is exactly the condition
    under which the protocol requires the product to be searched.
    """
    best = (store.get("full_factorial") or store["modes"])["best"]
    return {
        "c": best["c"],
        "beta_w": best["beta_w"],
        "garbage_time_mode": best["garbage_time_mode"],
        "prediction_compression": best["prediction_compression"],
    }


def _starting_values() -> dict[str, Any]:
    """The incumbent, as it actually ran - which is not what the config says.

    `[margin.prediction_compression].enabled = true` was configured and
    implemented NOWHERE in src/ until this campaign (fresh-eyes review S9), so
    every published number was produced with the compression OFF. The honest
    baseline is the one that produced the published numbers.
    """
    cfg = load_config()
    return {
        "c": float(cfg["margin"]["c"]),
        "beta_w": float(cfg["margin"]["beta_w"]),
        "garbage_time_mode": str(cfg["garbage_time"]["mode"]),
        "prediction_compression": False,
    }


def _run_validation_cell(spec: dict[str, Any]) -> dict[str, Any]:
    """Pool worker: one (config, season set) pair scored with the FULL system list.

    The full list is what makes the violations criterion evaluable at all - it is
    comparative, so every rival has to be in the same run - and it is what puts
    the headline ordering's own row in the gate rather than L3's.
    """
    seasons = TUNE_SEASONS if spec["season_set"] == "tune" else VALIDATE_SEASONS
    overrides = {k: v for k, v in spec.items() if k not in ("label", "season_set")}
    _init(seasons)
    cfg = _cell_config(load_config(), **overrides)
    result = _score(cfg, seasons, FULL_SYSTEMS)
    block = result["systems"]
    return {
        **spec,
        **_summary(result),
        "violation_rate": block[SYSTEM]["retrodictive_violation_rate"],
        "headline_violation_rate": block["schedule_odds"]["retrodictive_violation_rate"],
        "gate": block["schedule_odds"]["gate"],
        "calibration_table": _headline(result, SYSTEM)["calibration"],
    }


def stage_validate(store: dict[str, Any], workers: int) -> None:
    frozen = _frozen_choice(store)
    store["frozen_choice"] = frozen
    store["starting_values"] = _starting_values()

    specs = [
        {"label": "starting_values", "season_set": "tune", **store["starting_values"]},
        {"label": "frozen", "season_set": "tune", **frozen},
        {"label": "starting_values", "season_set": "validate", **store["starting_values"]},
        {"label": "frozen", "season_set": "validate", **frozen},
    ]

    with ProcessPoolExecutor(max_workers=min(workers, 4)) as pool:
        rows = list(pool.map(_run_validation_cell, specs))

    by_key = {(r["label"], r["season_set"]): r for r in rows}
    tune_delta = by_key[("frozen", "tune")]["mae"] - by_key[("starting_values", "tune")]["mae"]
    val_delta = (
        by_key[("frozen", "validate")]["mae"] - by_key[("starting_values", "validate")]["mae"]
    )
    store["validation"] = {
        "runs": rows,
        "tune_mae_delta": tune_delta,
        "validate_mae_delta": val_delta,
        "noise_floor_mae": NOISE_FLOOR_MAE,
        "adopted": bool(val_delta <= NOISE_FLOOR_MAE),
        "rule": (
            "adopt only if the frozen choice improves 2024 MAE against the starting "
            f"values or does not worsen it by more than {NOISE_FLOOR_MAE} points "
            "(ADR 0006's own noise floor). Otherwise the config keeps the starting "
            "values and the campaign reports failure."
        ),
        "evaluated_once": True,
    }


# ----------------------------------------------------------------------------
# stage 3b - what the frozen choice does to the POLL, not just to the forecast
# ----------------------------------------------------------------------------
#: The q_ref sweep's worst Kendall tau (headline-ordering study §9). This
#: project's own published standard: a parameter whose tau against the incumbent
#: falls below this is a DIAL and must be labelled as one (ADR 0006).
Q_REF_TAU_FLOOR = 0.985

RANK_SEASONS = (2021, 2022, 2023)


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
        "biggest_movers": [
            {"team": t, "incumbent": a, "frozen": b} for _, t, a, b in biggest
        ],
        "is_a_dial": tau < Q_REF_TAU_FLOOR,
    }


def stage_ranking(store: dict[str, Any], workers: int) -> None:
    """Does the frozen choice move the POLL? Measured by the project's own rule.

    THE OBJECTIVE IS PREDICTIVE AND beta_w IS NOT. The config calls beta_w "the
    single most contested value in the system" because it is the discontinuity
    that makes this a football ranking rather than a scoring-margin ranking - a
    statement about DESERT. A search that optimises margin MAE has no opinion
    about desert at all, so the ranking consequence of whatever it picks has to be
    measured separately and published beside the MAE gain, or the campaign is
    quietly buying a change to the poll with a number that was never about the
    poll.
    """
    del workers
    base_cfg = _cell_config(load_config(), **_starting_values())
    frozen_cfg = _cell_config(load_config(), **store["frozen_choice"])
    rows: dict[str, Any] = {}
    for season in RANK_SEASONS:
        plays = load_plays([season])
        base = _headline_ranks(base_cfg, season, plays)
        other = _headline_ranks(frozen_cfg, season, plays)
        rows[str(season)] = {
            "movement": _movement(base, other),
            "top10_incumbent": [t for t, r in sorted(base.items(), key=lambda kv: kv[1])[:10]],
            "top10_frozen": [t for t, r in sorted(other.items(), key=lambda kv: kv[1])[:10]],
        }
    taus = [rows[s]["movement"]["kendall_tau"] for s in rows]
    store["ranking_impact"] = {
        "tau_floor": Q_REF_TAU_FLOOR,
        "by_season": rows,
        "min_kendall_tau": float(min(taus)),
        "is_a_dial": bool(min(taus) < Q_REF_TAU_FLOOR),
        "standard": (
            "docs/analysis/headline-ordering-study.md §9 and ADR 0006: a parameter "
            "whose Kendall tau against the incumbent falls below the 0.985 that "
            "q_ref achieves is a DIAL, not a convention, and must be labelled as one"
        ),
    }


# ----------------------------------------------------------------------------
# stage 4 - the calibration diagnosis
# ----------------------------------------------------------------------------
def _decile_table(prob: np.ndarray, won: np.ndarray) -> list[dict[str, float]]:
    return metrics.calibration_table(prob, won)


def _max_dev(table: list[dict[str, float]]) -> float:
    return metrics.max_calibration_deviation_pp(table)


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval - the honest one for a 1-of-38 bin."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _predictions_frame(result: dict[str, Any], system: str = SYSTEM) -> pl.DataFrame:
    """Every FBS-vs-FBS game the harness scored, in bucket order.

    ALL weeks, not just the published ones. sigma accumulates from the first
    evaluable bucket, so an estimator refitted on "the residuals accumulated so
    far" has to see the same history the harness saw; the headline window is
    applied at EVALUATION time via `in_headline_window`, which is what the gate
    does.
    """
    rows = [
        r
        for r in result["predictions"]
        if r["system"] == system and r["segment"] == "fbs_vs_fbs"
    ]
    return pl.DataFrame(rows).sort(["season", "bucket_order", "game_id"])


def _t_probabilities(margin: np.ndarray, sigma: np.ndarray, df: float) -> np.ndarray:
    """P(margin > 0) under Student-t residuals with SD `sigma` and `df` degrees.

    `sigma` is a standard deviation, so the t SCALE is sigma*sqrt((df-2)/df) and
    the standardised argument picks up the reciprocal. Matching the second moment
    rather than the scale is the only way this is a comparison of shapes rather
    than a second, uncontrolled change of width.
    """
    if df <= 2.0:
        raise ValueError("t with df <= 2 has no finite variance; sigma would be meaningless")
    scale = np.asarray(sigma, dtype=np.float64) * math.sqrt((df - 2.0) / df)
    return np.asarray(stats.t.cdf(np.asarray(margin, dtype=np.float64) / scale, df))


def _sigma_walk_forward_heteroscedastic(
    frame: pl.DataFrame, min_games: int, floor: float
) -> np.ndarray:
    """sigma_g = a + b*|m_hat_g|, refitted at every bucket on exactly the
    out-of-sample residuals the harness had accumulated at that bucket.

    This reproduces the harness's own accumulation rule - per season, growing as
    the season is walked, with `[resume].sigma` as the thin-window fallback and
    floor - and changes only the SHAPE of the estimator from a constant to a line
    in the predicted absolute margin. Nothing here can see a game it is about to
    score: the fit at bucket b uses buckets < b of the same season.
    """
    frame = frame.with_row_index("row")
    out = np.full(frame.height, floor, dtype=np.float64)
    for season in sorted(frame["season"].unique().to_list()):
        sub = frame.filter(pl.col("season") == season).sort(["bucket_order", "game_id"])
        seen_abs: list[float] = []
        seen_res: list[float] = []
        for order in sorted(sub["bucket_order"].unique().to_list()):
            bucket = sub.filter(pl.col("bucket_order") == order)
            pred = bucket["predicted"].to_numpy().astype(np.float64)
            if len(seen_res) >= min_games:
                x = np.abs(np.asarray(seen_abs))
                r2 = np.asarray(seen_res) ** 2
                # Regress squared residual on |m_hat|, then take the root. Fitting
                # the variance rather than the SD is what makes the estimate
                # unbiased for the quantity sigma is defined as.
                coef = np.polyfit(x, r2, 1)
                var = np.polyval(coef, np.abs(pred))
                sigma = np.sqrt(np.maximum(var, floor**2))
            else:
                sigma = np.full(pred.shape, floor)
            out[bucket["row"].to_numpy()] = np.maximum(sigma, floor)
            seen_abs.extend(np.abs(pred).tolist())
            seen_res.extend(
                (bucket["actual"].to_numpy().astype(np.float64) - pred).tolist()
            )
    return out


def home_and_home(games: pl.DataFrame, within_season: bool = True) -> dict[str, Any]:
    """The Pasteur home-and-home estimate of h, implemented for real.

    `[homefield].method = "home_and_home"` has selected nothing since the config
    was written (fresh-eyes review S9): the live h is always a regression
    coefficient. This is the estimator the config names, with the standard error
    the config does not carry - and the standard error is the finding.

    THE ARGUMENT, which is the reason report 02 §3.2 prefers it: the schedule is
    structurally asymmetric. Power programmes buy home games that never get a
    return trip, so a regression coefficient on `site` is estimated partly off
    the difference between the teams that host and the teams that visit. A
    home-and-home pair is the SAME two teams in both venues, so the team effect
    differences out exactly and what is left is the venue:

        h = mean over pairs of  (m_host_leg + m_road_leg) / 2

    where both margins are taken from the perspective of the team hosting the
    first leg. Both legs must be non-neutral.

    `within_season=True` is the only setting a live poll may use, because
    constraint 2 forbids a prior season reaching anything the model uses. It is
    also the setting under which college football almost never supplies a pair:
    teams schedule home-and-home ACROSS years, not inside one. The
    `within_season=False` number is computed anyway, clearly labelled, because
    "the estimator the config names cannot be run" is a claim that has to be
    supported by running it both ways.
    """
    played = games.filter(~pl.col("neutral_site"))
    margins: dict[tuple[Any, str, str], float] = {}
    for season, home, away, hp, ap in zip(
        played["season"].to_list(),
        played["home_team"].to_list(),
        played["away_team"].to_list(),
        played["home_points"].to_list(),
        played["away_points"].to_list(),
        strict=True,
    ):
        key = (int(season) if within_season else 0, str(home), str(away))
        margins[key] = float(hp) - float(ap)
    seen: set[tuple[Any, str, str]] = set()
    halves: list[float] = []
    pairs: list[dict[str, Any]] = []
    for (season, home, away), margin in sorted(margins.items()):
        mirror = (season, away, home)
        if mirror not in margins:
            continue
        key = (season, *sorted((home, away)))
        if key in seen:
            continue
        seen.add(key)
        # `margin` is A's margin hosting B = (theta_A - theta_B) + h;
        # `margins[mirror]` is B's margin hosting A = (theta_B - theta_A) + h.
        # Their AVERAGE is h exactly - the team effect enters with opposite signs
        # and cancels, the venue enters with the same sign twice and does not.
        # (This is `l2_results.estimate_home_field`'s "sum over paired games,
        # divide by the number of games", written per pair so a standard error
        # over pairs is available.)
        half = (margin + margins[mirror]) / 2.0
        halves.append(half)
        pairs.append(
            {"season": season, "home_leg": home, "away_leg": away, "half_sum": half}
        )
    array = np.asarray(halves, dtype=np.float64)
    n = int(array.size)
    return {
        "within_season": within_season,
        "h": float(np.mean(array)) if n else float("nan"),
        "n_pairs": n,
        "standard_error": float(np.std(array, ddof=1) / math.sqrt(n)) if n > 1 else float("nan"),
        "median": float(np.median(array)) if n else float("nan"),
        "pairs": pairs,
    }


def stage_calibration(store: dict[str, Any], workers: int) -> None:
    del workers
    _init(TUNE_SEASONS)
    cfg = load_config()
    starting = _cell_config(cfg, **_starting_values())
    result = _score(starting, TUNE_SEASONS, GRID_SYSTEMS, collect_predictions=True)
    all_weeks = _predictions_frame(result)

    # THE EVALUATION WINDOW IS THE PUBLISHED ONE. Everything scored below is the
    # headline window; the wider frame exists only so an estimator refitted on
    # "the residuals so far" sees the history the harness saw.
    published = all_weeks["in_headline_window"].to_numpy()
    frame = all_weeks.filter(pl.col("in_headline_window"))
    predicted = frame["predicted"].to_numpy().astype(np.float64)
    actual = frame["actual"].to_numpy().astype(np.float64)
    sigma = frame["sigma"].to_numpy().astype(np.float64)
    residual = actual - predicted
    won = (actual > 0).astype(np.float64)
    neutral = frame["neutral_site"].to_numpy()

    base_prob = metrics.win_probability(predicted, sigma)
    base_table = _decile_table(base_prob, won)
    diag: dict[str, Any] = {
        "n_games": int(frame.height),
        "baseline": {
            "table": base_table,
            "max_deviation_pp": _max_dev(base_table),
            "brier": metrics.brier(base_prob, won),
            "log_loss": metrics.log_loss(base_prob, won),
            "sigma_mean": float(np.mean(sigma)),
        },
        "residuals": {
            "mean": float(np.mean(residual)),
            "sd": float(np.std(residual, ddof=1)),
            "rms": float(np.sqrt(np.mean(residual**2))),
            "skew": float(stats.skew(residual)),
            "excess_kurtosis": float(stats.kurtosis(residual)),
            "jarque_bera_p": float(stats.jarque_bera(residual).pvalue),
        },
    }

    # Every counted bin, with a Wilson interval, because the gate's number is the
    # WORST bin and the worst bin is usually the thinnest one.
    diag["baseline"]["bins_with_intervals"] = []
    for row in base_table:
        n = int(row["n"])
        if not n:
            continue
        k = int(round(row["observed_rate"] * n))
        lo, hi = _wilson(k, n)
        diag["baseline"]["bins_with_intervals"].append(
            {
                **row,
                "wins": k,
                "wilson_low": lo,
                "wilson_high": hi,
                "predicted_inside_interval": bool(lo <= row["mean_predicted"] <= hi),
            }
        )

    # -- candidate 1: Student-t margins ---------------------------------------
    # sigma enters ONLY the probability. The predicted margins, and therefore
    # MAE, RMSE, SU and the walk-forward sigma itself, are untouched by the
    # choice of distribution - so recomputing the table here is not an
    # approximation of what the harness would do, it is exactly it.
    df_fit, loc_fit, scale_fit = stats.t.fit(residual, floc=0.0)
    t_rows = []
    for df in sorted({round(float(df_fit), 3), 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 30.0}):
        if df <= 2.0:
            continue
        prob = _t_probabilities(predicted, sigma, df)
        table = _decile_table(prob, won)
        t_rows.append(
            {
                "df": df,
                "max_deviation_pp": _max_dev(table),
                "brier": metrics.brier(prob, won),
                "log_loss": metrics.log_loss(prob, won),
                "table": table,
            }
        )
    diag["candidate_1_student_t"] = {
        "fitted_df": float(df_fit),
        "fitted_scale": float(scale_fit),
        "fitted_loc": float(loc_fit),
        "normal_log_likelihood": float(
            np.sum(stats.norm.logpdf(residual, 0.0, np.sqrt(np.mean(residual**2))))
        ),
        "t_log_likelihood": float(np.sum(stats.t.logpdf(residual, df_fit, 0.0, scale_fit))),
        "sweep": sorted(t_rows, key=lambda r: r["max_deviation_pp"]),
        "best": min(t_rows, key=lambda r: r["max_deviation_pp"]),
    }

    # -- candidate 2: heteroscedastic sigma ------------------------------------
    absm = np.abs(predicted)
    edges = [0.0, 3.0, 7.0, 10.0, 14.0, 17.0, 21.0, 28.0, 1e9]
    by_mismatch = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (absm >= lo) & (absm < hi)
        n = int(mask.sum())
        if n < 20:
            continue
        by_mismatch.append(
            {
                "abs_predicted_low": lo,
                "abs_predicted_high": None if hi > 1e8 else hi,
                "n": n,
                "residual_sd": float(np.std(residual[mask], ddof=1)),
                "residual_mean": float(np.mean(residual[mask])),
                "mean_abs_predicted": float(np.mean(absm[mask])),
                "mean_predicted_prob": float(np.mean(base_prob[mask])),
                "observed_rate": float(np.mean(won[mask])),
            }
        )
    slope, intercept, r_value, p_value, stderr = stats.linregress(
        absm, residual**2
    )
    het_sigma = _sigma_walk_forward_heteroscedastic(
        all_weeks,
        min_games=int(cfg["resume"]["sigma_min_out_of_sample_games"]),
        floor=float(cfg["resume"]["sigma"]),
    )[published]
    het_prob = metrics.win_probability(predicted, het_sigma)
    het_table = _decile_table(het_prob, won)
    diag["candidate_2_heteroscedastic"] = {
        "variance_on_abs_predicted": {
            "slope": float(slope),
            "intercept": float(intercept),
            "r_value": float(r_value),
            "p_value": float(p_value),
            "stderr": float(stderr),
        },
        "residual_sd_by_mismatch": by_mismatch,
        "walk_forward": {
            "max_deviation_pp": _max_dev(het_table),
            "brier": metrics.brier(het_prob, won),
            "log_loss": metrics.log_loss(het_prob, won),
            "sigma_mean": float(np.mean(het_sigma)),
            "sigma_min": float(np.min(het_sigma)),
            "sigma_max": float(np.max(het_sigma)),
            "table": het_table,
        },
    }

    # -- candidate 3: home field ----------------------------------------------
    tune_games = _GAMES.filter(pl.col("season").is_in(list(TUNE_SEASONS)))
    hh = home_and_home(tune_games)
    hh_across = home_and_home(tune_games, within_season=False)
    hh_by_season = {
        str(season): home_and_home(_GAMES.filter(pl.col("season") == season))
        for season in TUNE_SEASONS
    }
    weekly = [r for r in result["weekly"] if r["system"] == SYSTEM]
    first_published = int(cfg["publication"]["headline_start_week"])
    regression_h = [r["calib_site"] for r in weekly if r["week"] >= first_published]
    home_slice = []
    for label, mask in (
        ("home site", ~neutral),
        ("neutral site", neutral),
    ):
        n = int(mask.sum())
        if not n:
            continue
        home_slice.append(
            {
                "slice": label,
                "n": n,
                "residual_mean": float(np.mean(residual[mask])),
                "residual_sd": float(np.std(residual[mask], ddof=1)),
                "mean_predicted_prob": float(np.mean(base_prob[mask])),
                "observed_rate": float(np.mean(won[mask])),
                "deviation_pp": float(
                    (np.mean(won[mask]) - np.mean(base_prob[mask])) * 100.0
                ),
            }
        )
    # Does the site effect depend on the mismatch? If it does, one constant
    # cannot be right for both a coin-flip and a blowout, and the low deciles
    # (where the home team is the underdog) are where a single h would show it.
    non_neutral = ~neutral
    site_by_mismatch = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = non_neutral & (absm >= lo) & (absm < hi)
        n = int(mask.sum())
        if n < 20:
            continue
        site_by_mismatch.append(
            {
                "abs_predicted_low": lo,
                "abs_predicted_high": None if hi > 1e8 else hi,
                "n": n,
                "residual_mean": float(np.mean(residual[mask])),
                "residual_se": float(
                    np.std(residual[mask], ddof=1) / math.sqrt(n)
                ),
            }
        )
    diag["candidate_3_homefield"] = {
        "home_and_home": {k: v for k, v in hh.items() if k != "pairs"},
        "home_and_home_across_seasons_NOT_USABLE_LIVE": {
            k: v for k, v in hh_across.items() if k != "pairs"
        },
        "home_and_home_by_season": {
            k: {kk: vv for kk, vv in v.items() if kk != "pairs"} for k, v in hh_by_season.items()
        },
        "regression_coefficient": {
            "mean": float(np.mean(regression_h)),
            "sd": float(np.std(regression_h, ddof=1)),
            "min": float(np.min(regression_h)),
            "max": float(np.max(regression_h)),
            "n_weeks": len(regression_h),
        },
        "config_h_pasteur": float(cfg["homefield"]["h_pasteur"]),
        "config_h_recent_estimate": float(cfg["homefield"]["h_recent_estimate"]),
        "residual_by_site": home_slice,
        "residual_by_mismatch_non_neutral": site_by_mismatch,
    }

    # -- NOT A CANDIDATE: what sigma is, and what it would have to be ----------
    # This block adopts nothing. It exists because a diagnosis that names four
    # suspects and eliminates all four owes the reader the thing it found while
    # looking. sigma is the ACCUMULATED walk-forward RMS residual, which at week
    # N includes the near-noise weeks 2-4 that the poll declines to publish; over
    # the published window the system's own RMSE is smaller. An estimator that is
    # right about the season as a whole is too wide for the part of the season
    # being scored, and too wide is exactly the shape the decile table has.
    #
    # The oracle row cannot be run walk-forward - it reads the RMSE of the games
    # it is scoring - and is here as a BOUND, not a proposal. Adopting anything
    # from this block would be choosing a fix that was not pre-declared, which is
    # the failure the protocol exists to prevent.
    oracle_sigma = float(np.sqrt(np.mean(residual**2)))
    sigma_rows = []
    for label, sig in (
        ("live: accumulated walk-forward RMS (incumbent)", sigma),
        (
            f"oracle: RMSE of the games being scored ({oracle_sigma:.2f}) - NOT RUNNABLE",
            oracle_sigma,
        ),
        ("the old constant 15.3", float(cfg["resume"]["sigma"])),
    ):
        prob = metrics.win_probability(predicted, sig)
        table = _decile_table(prob, won)
        sigma_rows.append(
            {
                "sigma": label,
                "sigma_mean": float(np.mean(np.asarray(sig, dtype=np.float64))),
                "max_deviation_pp": _max_dev(table),
                "brier": metrics.brier(prob, won),
                "log_loss": metrics.log_loss(prob, won),
                "table": table,
            }
        )
    diag["sigma_diagnostic_not_a_candidate"] = {
        "rows": sigma_rows,
        "window_rmse": oracle_sigma,
        "accumulated_sigma_mean": float(np.mean(sigma)),
        "note": (
            "DIAGNOSIS ONLY. The oracle row reads the RMSE of the games it scores "
            "and cannot be run walk-forward. Nothing here is adopted: it was not "
            "one of the four pre-declared candidates."
        ),
    }

    # -- candidate 4: favourite-longshot ---------------------------------------
    # The decile table's own rows, re-expressed in the quantity that would
    # explain them: for each bin, the mean predicted margin and the mean actual.
    fl_rows = []
    for row in base_table:
        n = int(row["n"])
        if n < 20:
            continue
        mask = (base_prob >= row["bin_low"]) & (
            base_prob <= row["bin_high"] if row["bin_high"] >= 1.0 else base_prob < row["bin_high"]
        )
        fl_rows.append(
            {
                "bin_low": row["bin_low"],
                "bin_high": row["bin_high"],
                "n": n,
                "mean_predicted_margin": float(np.mean(predicted[mask])),
                "mean_actual_margin": float(np.mean(actual[mask])),
                "residual_mean": float(np.mean(residual[mask])),
                "residual_se": float(np.std(residual[mask], ddof=1) / math.sqrt(n)),
                "mean_predicted": row["mean_predicted"],
                "observed_rate": row["observed_rate"],
                "deviation_pp": (row["observed_rate"] - row["mean_predicted"]) * 100.0,
            }
        )
    # The shrinkage test: regress actual margin on predicted margin. A slope
    # below 1 means the model over-predicts mismatches; above 1 means it
    # under-predicts them and the extremes are where it loses.
    fl_slope, fl_intercept, fl_r, fl_p, fl_se = stats.linregress(predicted, actual)
    diag["candidate_4_favourite_longshot"] = {
        "by_decile": fl_rows,
        "actual_on_predicted": {
            "slope": float(fl_slope),
            "intercept": float(fl_intercept),
            "r_value": float(fl_r),
            "p_value": float(fl_p),
            "stderr": float(fl_se),
        },
        "extreme_predictions": {
            "n_over_21": int(np.sum(absm > 21.0)),
            "mean_abs_predicted_over_21": float(np.mean(absm[absm > 21.0]))
            if np.any(absm > 21.0)
            else float("nan"),
            "mean_abs_actual_over_21": float(np.mean(np.abs(actual[absm > 21.0])))
            if np.any(absm > 21.0)
            else float("nan"),
        },
    }
    store["calibration_diagnosis"] = diag


def stage_calibration_validate(store: dict[str, Any], workers: int) -> None:
    """"...AND holds direction on 2024" - the second half of the adoption rule.

    Pre-declared. Every candidate's parameter is frozen at its TUNE-SEASON value
    (nu is the maximum-likelihood fit on tune residuals and is not refitted here),
    so 2024 decides direction and nothing else. Run under both the starting values
    and the frozen choice, because the tune-season improvement was measured under
    the starting values and a direction check has to be like for like.
    """
    del workers
    _init(VALIDATE_SEASONS)
    cfg = load_config()
    df = float(store["calibration_diagnosis"]["candidate_1_student_t"]["fitted_df"])
    out: dict[str, Any] = {"student_t_df_from_tune": df, "runs": {}}
    for label, overrides in (
        ("starting_values", _starting_values()),
        ("frozen", store["frozen_choice"]),
    ):
        run_cfg = _cell_config(cfg, **overrides)
        result = _score(run_cfg, VALIDATE_SEASONS, GRID_SYSTEMS, collect_predictions=True)
        all_weeks = _predictions_frame(result)
        published = all_weeks["in_headline_window"].to_numpy()
        frame = all_weeks.filter(pl.col("in_headline_window"))
        predicted = frame["predicted"].to_numpy().astype(np.float64)
        actual = frame["actual"].to_numpy().astype(np.float64)
        sigma = frame["sigma"].to_numpy().astype(np.float64)
        won = (actual > 0).astype(np.float64)
        residual = actual - predicted

        normal = _max_dev(_decile_table(metrics.win_probability(predicted, sigma), won))
        student = _max_dev(_decile_table(_t_probabilities(predicted, sigma, df), won))
        het = _sigma_walk_forward_heteroscedastic(
            all_weeks,
            min_games=int(cfg["resume"]["sigma_min_out_of_sample_games"]),
            floor=float(cfg["resume"]["sigma"]),
        )[published]
        hetdev = _max_dev(_decile_table(metrics.win_probability(predicted, het), won))
        slope, intercept, r_value, p_value, stderr = stats.linregress(predicted, actual)
        out["runs"][label] = {
            "n_games": int(frame.height),
            "normal_max_deviation_pp": normal,
            "student_t_max_deviation_pp": student,
            "student_t_delta_pp": normal - student,
            "heteroscedastic_max_deviation_pp": hetdev,
            "heteroscedastic_delta_pp": normal - hetdev,
            "residual_mean": float(np.mean(residual)),
            "actual_on_predicted": {
                "slope": float(slope),
                "intercept": float(intercept),
                "stderr": float(stderr),
                "r_value": float(r_value),
                "p_value": float(p_value),
            },
        }
    store["calibration_validation"] = out


# ----------------------------------------------------------------------------
# render - the markdown, from the JSON, with nothing typed by hand
# ----------------------------------------------------------------------------
#: The protocol, byte-identical to the version committed BEFORE any number was
#: read (commit 8bea5aa, "Pre-register the tuning-campaign protocol"). It lives
#: here so that regenerating the results cannot quietly reword the rule they were
#: judged by; `git diff` on the rendered file would show it immediately.
PROTOCOL = (ROOT / "docs" / "analysis" / "_tuning-campaign-protocol.md").read_text()


def _pp(value: float | None, digits: int = 2, plus: bool = False) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:+.{digits}f}" if plus else f"{value:.{digits}f}"


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


def _demo_cross_check(after: dict[str, Any]) -> str:
    """Assert the campaign's "after" gate equals the one the live demo computed.

    The demo is regenerated from `configs/default.toml`, which now carries the
    frozen choice; this document's "after" column was produced by overriding the
    same four keys. If those two ever disagree, one of them is lying about what the
    pipeline does, and a reader should be told which rather than left to diff two
    JSON files by hand. (Fresh-eyes review S1 is exactly this failure in the other
    direction: a page whose prose disagreed with the object it was generated from.)
    """
    demo = ROOT / "demo" / "backtest-2021-2023.json"
    if not demo.exists():
        return "> `demo/backtest-2021-2023.json` is absent - cross-check not run."
    observed = json.loads(demo.read_text())["systems"]["schedule_odds"]["gate"]["observed"]
    if observed == after["observed"]:
        return (
            "> **Checked and identical**, to the last float: "
            f"MAE {observed['mae']:.6f}, RMSE {observed['rmse']:.6f}, SU "
            f"{observed['su_accuracy']:.6f}, calibration "
            f"{observed['max_calibration_deviation_pp']:.6f} pp, violations "
            f"{observed['retrodictive_violation_rate']:.6f}."
        )
    return (
        "> **THEY DISAGREE.** This document says "
        f"`{json.dumps(after['observed'], sort_keys=True)}`; "
        f"`demo/backtest-2021-2023.json` says `{json.dumps(observed, sort_keys=True)}`. "
        "One of them is wrong and the campaign is not publishable until it is known "
        "which."
    )


def render(store: dict[str, Any]) -> None:  # noqa: PLR0915 - one long document
    grid, modes = store["grid"], store["modes"]
    val, diag = store["validation"], store["calibration_diagnosis"]
    frozen, start = store["frozen_choice"], store["starting_values"]
    runs = {(r["label"], r["season_set"]): r for r in val["runs"]}
    prov = store["provenance"]

    c_grid = grid["search_space"]["c"]
    beta_grid = grid["search_space"]["beta_w"]
    by_cell = {(r["c"], r["beta_w"]): r for r in grid["cells"]}
    best, base_cell = grid["best"], grid["starting_values"]

    lines: list[str] = [PROTOCOL.rstrip(), "", "---", ""]

    # ---------------- PART 1 ----------------
    lines += [
        "## PART 1 — THE C × β_w GRID",
        "",
        f"**{grid['n_cells']} cells, the full published grid, no subsample.** "
        f"{grid['elapsed_seconds'] / 60:.1f} minutes of wall clock. Each cell is a complete "
        "three-season walk-forward backtest; every number is MAE on the tune seasons over "
        "the headline window, FBS-vs-FBS.",
        "",
        "**This stage holds the two mode switches at the values `configs/default.toml` "
        "declares** — `garbage_time.mode = \"connelly\"` and "
        "`prediction_compression.enabled = true`. The second is not what has been RUNNING "
        "(it was implemented nowhere in `src/`), which is exactly why the cell marked "
        "\"incumbent\" below is the incumbent *(C, β_w)* and not the incumbent *system*. "
        "Part 2 searches the modes, Part 2b searches the product, and Part 4's baseline is "
        "the system as it actually ran.",
        "",
        "### MAE over the whole grid",
        "",
        "Rows are C, columns β_w. The incumbent cell is **bold**; the optimum is "
        "*italic*. Lower is better.",
        "",
        "| C \\ β_w | " + " | ".join(f"{b:g}" for b in beta_grid) + " |",
        "|---" * (len(beta_grid) + 1) + "|",
    ]
    for c in c_grid:
        cells = []
        for b in beta_grid:
            row = by_cell[(c, b)]
            text = f"{row['mae']:.3f}"
            if (c, b) == (best["c"], best["beta_w"]):
                text = f"*{text}*"
            if (c, b) == (base_cell["c"], base_cell["beta_w"]):
                text = f"**{text}**"
            cells.append(text)
        lines.append(f"| **{c:g}** | " + " | ".join(cells) + " |")

    spread = max(r["mae"] for r in grid["cells"]) - min(r["mae"] for r in grid["cells"])
    lines += [
        "",
        "### The ten best cells, and the incumbent",
        "",
        "| C | β_w | MAE | RMSE | SU % | Brier | Max calib. dev. |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in grid["cells"][:10]:
        lines.append(
            f"| {row['c']:g} | {row['beta_w']:g} | {row['mae']:.4f} | {row['rmse']:.4f} "
            f"| {row['su_accuracy'] * 100:.2f} | {row['brier']:.5f} "
            f"| {row['max_calibration_deviation_pp']:.2f} pp |"
        )
    rank = grid["cells"].index(base_cell) + 1
    lines += [
        f"| **{base_cell['c']:g}** | **{base_cell['beta_w']:g}** | **{base_cell['mae']:.4f}** "
        f"| **{base_cell['rmse']:.4f}** | **{base_cell['su_accuracy'] * 100:.2f}** "
        f"| **{base_cell['brier']:.5f}** "
        f"| **{base_cell['max_calibration_deviation_pp']:.2f} pp** |",
        "",
        f"The bold row is the incumbent (C, β_w) — **rank {rank} of {grid['n_cells']}**.",
        "",
        f"**The whole grid spans {spread:.3f} points of MAE.** The best cell "
        f"(C = {best['c']:g}, β_w = {best['beta_w']:g}) beats the incumbent "
        f"(C = {base_cell['c']:g}, β_w = {base_cell['beta_w']:g}) by "
        f"{base_cell['mae'] - best['mae']:.4f} points — against the "
        f"{NOISE_FLOOR_MAE} the protocol fixed as the noise floor before any of this was "
        "computed.",
        "",
    ]

    # ---------------- PART 2 ----------------
    lines += [
        "## PART 2 — THE MODE SWITCHES",
        "",
        "`[garbage_time].mode` and `[margin.prediction_compression].enabled`, on the grid "
        "optimum and its four neighbours, so a mode that only wins at one point in "
        "(C, β_w) cannot masquerade as a mode that wins.",
        "",
        "`[garbage_time].mode = \"leverage\"` **could not be searched**: it raises "
        "`NotImplementedError` because it needs a win-probability model this project does "
        "not have. That is a hole in the search, not a value that lost.",
        "",
        "`[margin.prediction_compression]` was configured `true` and implemented **nowhere "
        "in `src/`** (independent review S9), so every published number to date was produced "
        "with it OFF. It could not be searched until it was implemented; "
        "`model/design.py::compress_prediction` is that implementation, written to the "
        "config's own published formula.",
        "",
        "| C | β_w | garbage time | pred. compression | MAE | RMSE | SU % | Brier | Calib. dev. |",  # noqa: E501
        "|---:|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in modes["cells"]:
        lines.append(
            f"| {row['c']:g} | {row['beta_w']:g} | {row['garbage_time_mode']} "
            f"| {'on' if row['prediction_compression'] else 'off'} | {row['mae']:.4f} "
            f"| {row['rmse']:.4f} | {row['su_accuracy'] * 100:.2f} | {row['brier']:.5f} "
            f"| {row['max_calibration_deviation_pp']:.2f} pp |"
        )
    mbest = modes["best"]
    moved = (
        mbest["prediction_compression"] != True  # noqa: E712 - stage 1 held it at true
        or (mbest["c"], mbest["beta_w"]) != (best["c"], best["beta_w"])
        or mbest["garbage_time_mode"] != "connelly"
    )
    lines += [
        "",
        f"**The second stage moved the optimum**: {mbest['garbage_time_mode']} / "
        f"prediction compression "
        f"{'on' if mbest['prediction_compression'] else 'OFF'}, at C = {mbest['c']:g}, "
        f"β_w = {mbest['beta_w']:g}. "
        + (
            "The protocol's own escape clause fires — *\"the full 416 is run only if the "
            "second stage moves the optimum\"* — so it was run, and Part 2b supersedes both "
            "stages above."
            if moved
            else "It did not change the mode, so the two-stage result stands."
        ),
        "",
        "The neighbourhood holds "
        f"{len(modes['neighbourhood'])} points rather than five, because the stage-1 optimum "
        "sits on the EDGE of the published grid in both coordinates and the clamped "
        "neighbours collapse onto it. That is a fact about the grid and it is picked up "
        "again below.",
        "",
    ]

    # ---------------- PART 2b ----------------
    full = store.get("full_factorial")
    if full:
        fbest, fincumbent = full["best"], full["incumbent_cell"]
        frank = full["cells"].index(fincumbent) + 1
        corner = full["corner_solution"]
        lines += [
            "## PART 2b — THE COMPLETE FACTORIAL, WHICH IS THE ACTUAL DECISION SURFACE",
            "",
            f"**{full['n_cells']} cells** — C × β_w × garbage time × prediction compression, "
            f"searched as a product rather than in two stages. "
            f"{full['elapsed_seconds'] / 60:.1f} minutes of wall clock.",
            "",
            "| C | β_w | garbage time | pred. compression | MAE | RMSE | SU % | Brier | Calib. dev. |",  # noqa: E501
            "|---:|---:|---|---|---:|---:|---:|---:|---:|",
        ]
        for row in full["cells"][:15]:
            lines.append(
                f"| {row['c']:g} | {row['beta_w']:g} | {row['garbage_time_mode']} "
                f"| {'on' if row['prediction_compression'] else 'off'} | {row['mae']:.4f} "
                f"| {row['rmse']:.4f} | {row['su_accuracy'] * 100:.2f} | {row['brier']:.5f} "
                f"| {row['max_calibration_deviation_pp']:.2f} pp |"
            )
        lines += [
            f"| **{fincumbent['c']:g}** | **{fincumbent['beta_w']:g}** "
            f"| **{fincumbent['garbage_time_mode']}** "
            f"| **{'on' if fincumbent['prediction_compression'] else 'off'}** "
            f"| **{fincumbent['mae']:.4f}** | **{fincumbent['rmse']:.4f}** "
            f"| **{fincumbent['su_accuracy'] * 100:.2f}** | **{fincumbent['brier']:.5f}** "
            f"| **{fincumbent['max_calibration_deviation_pp']:.2f} pp** |",
            "",
            f"The bold row is **the system as it actually ran** — rank {frank} of "
            f"{full['n_cells']}. The winner beats it by "
            f"{fincumbent['mae'] - fbest['mae']:.4f} points of MAE.",
            "",
        ]
        if corner["c_at_grid_edge"] or corner["beta_w_at_grid_edge"]:
            edges = []
            if corner["c_at_grid_edge"]:
                edges.append(f"C = {fbest['c']:g}")
            if corner["beta_w_at_grid_edge"]:
                edges.append(f"β_w = {fbest['beta_w']:g}")
            lines += [
                "### THE WINNER IS A CORNER SOLUTION, AND THAT IS THE FINDING",
                "",
                f"**{' and '.join(edges)} sit on the EDGE of the published grid.** The "
                "optimum is therefore not bracketed: the data wants to keep going and the "
                "search space stops it. The protocol fixed the search space as *exactly the "
                "config grids* precisely so that this campaign could not widen the net after "
                "seeing the numbers, so the boundary is reported rather than crossed.",
                "",
                "It also says something about where those bounds came from. The independent "
                "review's §7 table lists C and β_w under *derivative without independent "
                "justification*: C's range is Pasteur's cap of 21 and the CFBD SRS "
                "walkthrough's ±28, β_w's is Sports-Reference's ±7 floor. Those are other "
                "people's answers on other people's datasets, and on this dataset the "
                "optimum leaves the interval they define. **Widening the grid is the first "
                "item for the next campaign, and it must be pre-registered before it is "
                "searched.**",
                "",
            ]
        lines += [""]

    # ---------------- PART 3 ----------------
    lines += [
        "## PART 3 — THE FROZEN CHOICE",
        "",
        "Frozen on the tune seasons, written here, and only then evaluated on 2024.",
        "",
        "| Parameter | Starting value | Frozen choice |",
        "|---|---|---|",
        f"| `[margin].c` | {start['c']:g} | **{frozen['c']:g}** |",
        f"| `[margin].beta_w` | {start['beta_w']:g} | **{frozen['beta_w']:g}** |",
        f"| `[garbage_time].mode` | {start['garbage_time_mode']} "
        f"| **{frozen['garbage_time_mode']}** |",
        f"| `[margin.prediction_compression].enabled` "
        f"| {'true' if start['prediction_compression'] else 'false (as it actually ran)'} "
        f"| **{'true' if frozen['prediction_compression'] else 'false'}** |",
        "",
        f"On the tune seasons that is **{_pp(val['tune_mae_delta'], 4, plus=True)}** points "
        "of MAE against the starting values.",
        "",
    ]

    # ---------------- PART 4 ----------------
    fv, sv = runs[("frozen", "validate")], runs[("starting_values", "validate")]
    ft, st = runs[("frozen", "tune")], runs[("starting_values", "tune")]
    lines += [
        "## PART 4 — 2024 VALIDATION, EVALUATED ONCE",
        "",
        "One evaluation, after the choice above was frozen. 2025 was not read.",
        "",
        "| | Tune 2021-2023 | | 2024 validation | |",
        "|---|---:|---:|---:|---:|",
        "| | starting | frozen | starting | frozen |",
        f"| n games | {st['n_games']} | {ft['n_games']} | {sv['n_games']} | {fv['n_games']} |",
        f"| **MAE** | {st['mae']:.4f} | {ft['mae']:.4f} | {sv['mae']:.4f} | {fv['mae']:.4f} |",
        f"| RMSE | {st['rmse']:.4f} | {ft['rmse']:.4f} | {sv['rmse']:.4f} | {fv['rmse']:.4f} |",
        f"| SU % | {st['su_accuracy'] * 100:.2f} | {ft['su_accuracy'] * 100:.2f} "
        f"| {sv['su_accuracy'] * 100:.2f} | {fv['su_accuracy'] * 100:.2f} |",
        f"| Brier | {st['brier']:.5f} | {ft['brier']:.5f} | {sv['brier']:.5f} "
        f"| {fv['brier']:.5f} |",
        f"| Max calib. dev. (pp) | {st['max_calibration_deviation_pp']:.2f} "
        f"| {ft['max_calibration_deviation_pp']:.2f} "
        f"| {sv['max_calibration_deviation_pp']:.2f} "
        f"| {fv['max_calibration_deviation_pp']:.2f} |",
        f"| Headline violations | {st['headline_violation_rate']:.4f} "
        f"| {ft['headline_violation_rate']:.4f} | {sv['headline_violation_rate']:.4f} "
        f"| {fv['headline_violation_rate']:.4f} |",
        "",
        f"**2024 MAE moves by {_pp(val['validate_mae_delta'], 4, plus=True)} points** "
        f"against the starting values. The rule fixed in advance: adopt only if this is an "
        f"improvement or a worsening no larger than {val['noise_floor_mae']} points.",
        "",
        f"**Verdict: {'ADOPTED' if val['adopted'] else 'REJECTED — the config keeps the starting values'}.**",  # noqa: E501
        "",
    ]

    # ---------------- PART 4b ----------------
    rank_block = store.get("ranking_impact")
    if rank_block:
        lines += [
            "## PART 4b — WHAT THE FROZEN CHOICE DOES TO THE POLL",
            "",
            "The objective is margin MAE. **β_w is not about margin MAE.** The config calls "
            "it the single most contested value in the system because it is the "
            "discontinuity that makes this a football ranking rather than a scoring-margin "
            "ranking — a statement about desert, which a predictive objective has no opinion "
            "about. So the ranking consequence is measured with the project's own standard "
            f"(headline-ordering study §9, ADR 0006): Kendall's τ against the "
            f"{rank_block['tau_floor']} that the published `q_ref` sweep never dipped below. "
            "Below it, the parameter is a **dial** and must be labelled as one.",
            "",
            "Final pre-postseason headline poll, each tune season, incumbent vs frozen:",
            "",
            "| Season | Kendall's τ | Mean \\|Δrank\\| | Max \\|Δrank\\| | Top-25 changes | Verdict |",  # noqa: E501
            "|---|---:|---:|---:|---:|---|",
        ]
        for season, block in sorted(rank_block["by_season"].items()):
            mv = block["movement"]
            lines.append(
                f"| {season} | {mv['kendall_tau']:.4f} | {mv['mean_abs_rank_delta']:.2f} "
                f"| {mv['max_abs_rank_delta']} | {mv['top25_membership_changes']} "
                f"| {'**A DIAL**' if mv['is_a_dial'] else 'a convention'} |"
            )
        lines += [
            "",
            f"**Minimum τ across the tune seasons: {rank_block['min_kendall_tau']:.4f}** — "
            + (
                "below the floor, so this change is a DIAL and is labelled as one in the "
                "config and in ADR 0007."
                if rank_block["is_a_dial"]
                else "above the floor, so by the project's own published standard the change "
                "is a convention rather than a dial. It is still published here, because "
                "\"small\" is a measurement and not an assurance."
            ),
            "",
            "Biggest movers, most recent tune season:",
            "",
            "| Team | Incumbent | Frozen |",
            "|---|---:|---:|",
        ]
        latest = max(rank_block["by_season"])
        for mover in rank_block["by_season"][latest]["movement"]["biggest_movers"]:
            lines.append(f"| {mover['team']} | {mover['incumbent']} | {mover['frozen']} |")
        lines += [""]

    # ---------------- PART 5 ----------------
    base = diag["baseline"]
    res = diag["residuals"]
    t1 = diag["candidate_1_student_t"]
    t2 = diag["candidate_2_heteroscedastic"]
    t3 = diag["candidate_3_homefield"]
    t4 = diag["candidate_4_favourite_longshot"]
    lines += [
        "## PART 5 — THE CALIBRATION DIAGNOSIS",
        "",
        f"All of this is measured on the **starting values**, tune seasons, headline window, "
        f"{diag['n_games']} FBS-vs-FBS games — the configuration whose decile table the demo "
        "publishes, so the diagnosis is about the miss that is actually on the page.",
        "",
        "### 5.0 The miss, with the interval the gate does not carry",
        "",
        "The gate's number is the **worst** decile, and the worst decile is usually the "
        "thinnest one. Here is every bin with a Wilson 95% interval on its observed rate.",
        "",
        "| Predicted decile | n | Wins | Mean predicted | Observed | 95% Wilson | Deviation | Predicted inside? |",  # noqa: E501
        "|---|---:|---:|---:|---:|---|---:|---|",
    ]
    for row in base["bins_with_intervals"]:
        dev = (row["observed_rate"] - row["mean_predicted"]) * 100.0
        inside = "yes" if row["predicted_inside_interval"] else "**no**"
        counted = "" if row["counted"] else " *(uncounted)*"
        lines.append(
            f"| {row['bin_low']:.1f}–{row['bin_high']:.1f}{counted} | {int(row['n'])} "
            f"| {row['wins']} | {row['mean_predicted']:.3f} | {row['observed_rate']:.3f} "
            f"| {row['wilson_low']:.3f}–{row['wilson_high']:.3f} | {dev:+.2f} pp | {inside} |"
        )
    worst = max(
        (r for r in base["bins_with_intervals"] if r["counted"]),
        key=lambda r: abs(r["observed_rate"] - r["mean_predicted"]),
    )
    lines += [
        "",
        f"**The gate criterion is decided by a bin holding {int(worst['n'])} games.** Its "
        f"observed rate is {worst['wins']} of {int(worst['n'])}, and the Wilson interval on "
        f"that is {worst['wilson_low']:.3f}–{worst['wilson_high']:.3f}. Whether the "
        f"predicted {worst['mean_predicted']:.3f} sits inside it is stated in the last "
        "column rather than argued about. This is reported as a property of the metric, "
        "**not** as a reason the criterion should be considered passed: the gate says what "
        "it says.",
        "",
        "### 5.1 What the residuals are",
        "",
        "| Quantity | Value |",
        "|---|---:|",
        f"| Mean residual (actual − predicted) | {res['mean']:+.4f} |",
        f"| SD | {res['sd']:.4f} |",
        f"| RMS | {res['rms']:.4f} |",
        f"| Skew | {res['skew']:+.4f} |",
        f"| Excess kurtosis | {res['excess_kurtosis']:+.4f} |",
        f"| Jarque-Bera p | {res['jarque_bera_p']:.4g} |",
        "",
        "### 5.2 Candidate 1 — Student-t game margins",
        "",
        f"Maximum likelihood on the walk-forward residuals, location fixed at zero, gives "
        f"**ν = {t1['fitted_df']:.2f}** and scale {t1['fitted_scale']:.3f}. Log likelihood "
        f"{t1['t_log_likelihood']:.1f} against the normal's "
        f"{t1['normal_log_likelihood']:.1f}.",
        "",
        "σ enters ONLY the probability: predicted margins, MAE, RMSE, straight-up accuracy "
        "and the walk-forward σ estimate itself are all untouched by the choice of "
        "distribution. So recomputing the decile table under a t is not an approximation of "
        "what the harness would do — it is exactly it, on the harness's own per-game output. "
        "The t scale is matched to the same second moment as the normal, so this is a "
        "comparison of SHAPES and not a second, uncontrolled change of width.",
        "",
        "| ν | Max decile deviation | Δ vs normal | Brier | Log loss |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(t1["sweep"], key=lambda r: r["df"]):
        lines.append(
            f"| {row['df']:g} | {row['max_deviation_pp']:.2f} pp "
            f"| {row['max_deviation_pp'] - base['max_deviation_pp']:+.2f} pp "
            f"| {row['brier']:.5f} | {row['log_loss']:.5f} |"
        )
    lines += [
        f"| *normal (incumbent)* | *{base['max_deviation_pp']:.2f} pp* | — "
        f"| *{base['brier']:.5f}* | *{base['log_loss']:.5f}* |",
        "",
        "### 5.3 Candidate 2 — heteroscedastic σ(|m̂|)",
        "",
        "Does residual variance depend on how big a mismatch the model thinks it is looking "
        "at? Regressing the squared residual on the predicted absolute margin:",
        "",
        "| Quantity | Value |",
        "|---|---:|",
        f"| Slope (variance per point of \\|m̂\\|) "
        f"| {t2['variance_on_abs_predicted']['slope']:+.4f} |",
        f"| Standard error | {t2['variance_on_abs_predicted']['stderr']:.4f} |",
        f"| p | {t2['variance_on_abs_predicted']['p_value']:.4g} |",
        "",
        "| Predicted \\|margin\\| | n | Residual SD | Residual mean | Mean predicted p | Observed |",  # noqa: E501
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in t2["residual_sd_by_mismatch"]:
        hi = "+" if row["abs_predicted_high"] is None else f"–{row['abs_predicted_high']:g}"
        lines.append(
            f"| {row['abs_predicted_low']:g}{hi} | {row['n']} | {row['residual_sd']:.3f} "
            f"| {row['residual_mean']:+.3f} | {row['mean_predicted_prob']:.3f} "
            f"| {row['observed_rate']:.3f} |"
        )
    wf = t2["walk_forward"]
    lines += [
        "",
        "Fitted walk-forward — the σ model refitted at every bucket on exactly the "
        "out-of-sample residuals the harness had accumulated at that bucket, the same rule "
        "and the same games the constant σ uses:",
        "",
        "| | Constant σ (incumbent) | σ(\\|m̂\\|) |",
        "|---|---:|---:|",
        f"| Max decile deviation | {base['max_deviation_pp']:.2f} pp "
        f"| {wf['max_deviation_pp']:.2f} pp |",
        f"| Brier | {base['brier']:.5f} | {wf['brier']:.5f} |",
        f"| Log loss | {base['log_loss']:.5f} | {wf['log_loss']:.5f} |",
        f"| Mean σ | {base['sigma_mean']:.2f} | {wf['sigma_mean']:.2f} "
        f"(range {wf['sigma_min']:.2f}–{wf['sigma_max']:.2f}) |",
        "",
        "### 5.4 Candidate 3 — home field, estimated the way the config says",
        "",
        "`[homefield].method = \"home_and_home\"` and `fit_both_and_publish = true` have "
        "selected nothing since the config was written (independent review S9). The "
        "estimator is implemented here with the standard error the config does not carry, "
        "and **the standard error is the finding**.",
        "",
        "| Estimate | h | n pairs | SE |",
        "|---|---:|---:|---:|",
        f"| Home-and-home, WITHIN season (the only form constraint 2 allows) "
        f"| {t3['home_and_home']['h']:.3f} | {t3['home_and_home']['n_pairs']} "
        f"| {t3['home_and_home']['standard_error']:.3f} |",
        f"| Home-and-home, ACROSS seasons (**not usable live**) "
        f"| {t3['home_and_home_across_seasons_NOT_USABLE_LIVE']['h']:.3f} "
        f"| {t3['home_and_home_across_seasons_NOT_USABLE_LIVE']['n_pairs']} "
        f"| {t3['home_and_home_across_seasons_NOT_USABLE_LIVE']['standard_error']:.3f} |",
        f"| Regression coefficient (what actually runs), mean over published weeks "
        f"| {t3['regression_coefficient']['mean']:.3f} "
        f"| {t3['regression_coefficient']['n_weeks']} weeks "
        f"| sd {t3['regression_coefficient']['sd']:.3f} |",
        f"| `[homefield].h_pasteur` (inherited constant) | {t3['config_h_pasteur']:.2f} | — | — |",  # noqa: E501
        f"| `[homefield].h_recent_estimate` (inherited constant) "
        f"| {t3['config_h_recent_estimate']:.2f} | — | — |",
        "",
        "Per season, within-season pairs only:",
        "",
        "| Season | h | n pairs | SE |",
        "|---|---:|---:|---:|",
    ]
    for season, block in sorted(t3["home_and_home_by_season"].items()):
        lines.append(
            f"| {season} | {block['h']:.3f} | {block['n_pairs']} "
            f"| {block['standard_error']:.3f} |"
        )
    lines += [
        "",
        "And where the miss actually sits, by venue and by mismatch:",
        "",
        "| Slice | n | Residual mean | Mean predicted p | Observed | Deviation |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in t3["residual_by_site"]:
        lines.append(
            f"| {row['slice']} | {row['n']} | {row['residual_mean']:+.3f} "
            f"| {row['mean_predicted_prob']:.3f} | {row['observed_rate']:.3f} "
            f"| {row['deviation_pp']:+.2f} pp |"
        )
    lines += [
        "",
        "| Non-neutral, predicted \\|margin\\| | n | Residual mean | SE |",
        "|---|---:|---:|---:|",
    ]
    for row in t3["residual_by_mismatch_non_neutral"]:
        hi = "+" if row["abs_predicted_high"] is None else f"–{row['abs_predicted_high']:g}"
        lines.append(
            f"| {row['abs_predicted_low']:g}{hi} | {row['n']} | {row['residual_mean']:+.3f} "
            f"| {row['residual_se']:.3f} |"
        )
    fl = t4["actual_on_predicted"]
    lines += [
        "",
        "### 5.5 Candidate 4 — favourite-longshot: where the asymmetry lives",
        "",
        "Regressing the actual margin on the predicted margin over the same games:",
        "",
        "| Quantity | Value |",
        "|---|---:|",
        f"| Slope | {fl['slope']:.4f} |",
        f"| Standard error | {fl['stderr']:.4f} |",
        f"| Intercept | {fl['intercept']:+.4f} |",
        f"| r | {fl['r_value']:.4f} |",
        "",
        "A slope below 1 means the model over-predicts mismatches and the extremes give "
        "points back; above 1 means it under-predicts them and the extremes are where it "
        "loses. Per decile, in points rather than in probability:",
        "",
        "| Predicted decile | n | Mean predicted margin | Mean actual margin | Residual mean | SE | Prob. deviation |",  # noqa: E501
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in t4["by_decile"]:
        lines.append(
            f"| {row['bin_low']:.1f}–{row['bin_high']:.1f} | {row['n']} "
            f"| {row['mean_predicted_margin']:+.2f} | {row['mean_actual_margin']:+.2f} "
            f"| {row['residual_mean']:+.2f} | {row['residual_se']:.2f} "
            f"| {row['deviation_pp']:+.2f} pp |"
        )
    ext = t4["extreme_predictions"]
    sd = diag["sigma_diagnostic_not_a_candidate"]
    lines += [
        "",
        f"{ext['n_over_21']} of {diag['n_games']} predictions exceed the "
        "`prediction_compression` threshold of 21 points; they average "
        f"{ext['mean_abs_predicted_over_21']:.2f} predicted against "
        f"{ext['mean_abs_actual_over_21']:.2f} actual.",
        "",
        "### 5.6 What the four candidates left behind — σ is STALE, not wrong",
        "",
        "**This section adopts nothing.** It was not one of the four pre-declared "
        "candidates, and a fix chosen after the fact is the failure the protocol exists to "
        "prevent. It is here because a diagnosis that eliminates all four suspects owes the "
        "reader the thing it found while looking.",
        "",
        "σ is the **accumulated** walk-forward RMS residual: at bucket N it has seen every "
        "out-of-sample game from the first evaluable bucket onward, including the near-noise "
        f"weeks 2-4 the poll declines to publish. Over the published window it averages "
        f"**{sd['accumulated_sigma_mean']:.2f}**, while the realised RMSE of exactly those "
        f"games is **{sd['window_rmse']:.2f}**. An estimator that is right about the season "
        "as a whole is too wide for the part of the season being scored — and too wide is "
        "precisely the shape the decile table has.",
        "",
        "| σ | Mean σ | Max decile deviation | Brier | Log loss |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in sd["rows"]:
        lines.append(
            f"| {row['sigma']} | {row['sigma_mean']:.2f} | {row['max_deviation_pp']:.2f} pp "
            f"| {row['brier']:.5f} | {row['log_loss']:.5f} |"
        )
    lines += [
        "",
        "The oracle row reads the RMSE of the games it is scoring and **cannot be run "
        "walk-forward**. It is a bound on what a better-targeted σ could buy, not a proposal. "
        "The obvious candidate — a trailing-window σ instead of a cumulative one — is the "
        "first item for the next campaign, and it must be pre-registered before it is run.",
        "",
    ]

    # ---------------- 5.7 the verdict, by the rule fixed in advance -----------
    hh_pairs = t3["home_and_home"]["n_pairs"]
    # THE CANDIDATE IS THE FITTED nu, NOT THE BEST nu IN THE SWEEP. The protocol
    # says "fit df on tune residuals"; picking the sweep row with the smallest
    # deviation would be choosing the parameter off the metric it is judged by,
    # which is the post-hoc failure this whole document is arranged to avoid. The
    # sweep is published above as sensitivity, and it is the sweep that carries
    # the finding - see the note in this row.
    fitted_row = min(t1["sweep"], key=lambda r: abs(r["df"] - t1["fitted_df"]))
    verdicts = [
        (
            "1 — Student-t margins",
            base["max_deviation_pp"] - fitted_row["max_deviation_pp"],
            f"at the FITTED ν = {t1['fitted_df']:.2f}, which is what the protocol "
            f"declared. Jarque-Bera p = {res['jarque_bera_p']:.3f}, skew "
            f"{res['skew']:+.3f}, excess kurtosis {res['excess_kurtosis']:+.3f}: these "
            f"residuals are not distinguishable from normal. Forcing ν = "
            f"{t1['best']['df']:g} would cut the deviation by "
            f"{base['max_deviation_pp'] - t1['best']['max_deviation_pp']:.2f} pp, but that "
            "is a SHARPENING device rather than a fat tail — see §5.5",
        ),
        (
            "2 — heteroscedastic σ(\\|m̂\\|)",
            base["max_deviation_pp"] - t2["walk_forward"]["max_deviation_pp"],
            f"variance-on-\\|m̂\\| slope {t2['variance_on_abs_predicted']['slope']:+.3f} "
            f"(p = {t2['variance_on_abs_predicted']['p_value']:.3g})",
        ),
        (
            "3 — home-and-home h",
            float("nan"),
            f"NOT TESTABLE AS A LIVE ESTIMATOR: {hh_pairs} within-season pairs in three "
            "seasons, and constraint 2 forbids the cross-season pairs that would give it a "
            "sample",
        ),
        (
            "4 — favourite-longshot",
            float("nan"),
            "**IT IS THIS ONE**, and it is a diagnosis rather than a knob. Regressing "
            f"actual on predicted margin gives a slope of {fl['slope']:.4f} ± "
            f"{fl['stderr']:.4f} — {(fl['slope'] - 1.0) / fl['stderr']:.1f} standard errors "
            f"ABOVE one — with an intercept of {fl['intercept']:+.3f}. The point forecasts "
            "are under-dispersed and tilted toward the home side; there is no constant in "
            "`configs/default.toml` that sets either",
        ),
    ]
    cval = store.get("calibration_validation", {}).get("runs", {}).get("starting_values", {})
    #: The tune bar and the 2024 direction check, applied mechanically. `student`
    #: and `heteroscedastic` are the only two candidates with a number on both
    #: sides; 3 is untestable as a live estimator and 4 is a diagnosis.
    directions = {
        "1": cval.get("student_t_delta_pp"),
        "2": cval.get("heteroscedastic_delta_pp"),
    }
    lines += [
        "### 5.7 The verdict, by the rule fixed before any of this was run",
        "",
        "> *A fix is adopted only if it cuts the maximum decile deviation by >= "
        f"{CALIBRATION_ADOPT_PP} pp on the tune seasons AND holds direction on 2024. "
        "Anything that fails that rule is documented as diagnosed-but-unfixed, with the "
        "evidence, and the config does not move.*",
        "",
        f"Incumbent max decile deviation: **{base['max_deviation_pp']:.2f} pp** on tune, "
        f"**{cval.get('normal_max_deviation_pp', float('nan')):.2f} pp** on 2024 "
        "(gate threshold 5.0 pp).",
        "",
        "The 2024 column freezes every candidate's parameter at its TUNE value - ν is "
        "the maximum-likelihood fit on tune residuals and is not refitted - so 2024 decides "
        "direction and nothing else.",
        "",
        "| Candidate | Tune Δ max decile dev. | Clears >= "
        f"{CALIBRATION_ADOPT_PP} pp? | 2024 Δ | Direction holds? | Verdict |",
        "|---|---:|---|---:|---|---|",
    ]
    any_adopted = False
    for name, delta, _note in verdicts:
        direction = directions.get(name.split(" ", 1)[0])
        if np.isfinite(delta):
            clears = delta >= CALIBRATION_ADOPT_PP
            holds = None if direction is None else bool(direction > 0.0)
            adopted = bool(clears and holds)
            any_adopted = any_adopted or adopted
            lines.append(
                f"| {name} | {delta:+.2f} pp | {'**YES**' if clears else 'no'} "
                f"| {'—' if direction is None else format(direction, '+.2f') + ' pp'} "
                f"| {'—' if holds is None else ('yes' if holds else '**no**')} "
                f"| {'**ADOPTED**' if adopted else 'diagnosed, not adopted'} |"
            )
        else:
            untestable = "not testable as a live estimator" if name.startswith("3") else (
                "**the diagnosis** — not a knob to turn"
            )
            lines.append(f"| {name} | — | no | — | — | {untestable} |")
    lines += [
        "",
        "Evidence, per candidate:",
        "",
        *[f"- **Candidate {name}** — {note}" for name, _delta, note in verdicts],
        "",
        (
            "**NO CANDIDATE IS ADOPTED. The calibration miss is DIAGNOSED AND UNFIXED, and "
            "the config does not move on account of it.**"
            if not any_adopted
            else "**At least one candidate clears both halves of the rule and is adopted.**"
        ),
        "",
        "### 5.8 WHICH SUSPECT IT WAS",
        "",
        "**Neither of the two the demo named.** The suspects on record were *the normal "
        "tail* and *the single home-field constant*. Both are eliminated by measurement, "
        "and what is left is a third thing that no constant in `configs/default.toml` "
        "controls.",
        "",
        f"- **The normal tail is eliminated.** Maximum likelihood puts ν at "
        f"{t1['fitted_df']:.1f}; skew is {res['skew']:+.3f}, excess kurtosis "
        f"{res['excess_kurtosis']:+.3f}, Jarque-Bera p = {res['jarque_bera_p']:.3f}. These "
        "residuals are not distinguishable from normal. The sweep's low-ν rows do cut the "
        "deviation, and that is informative rather than exculpatory: a t with a matched "
        "SECOND MOMENT and a small ν has a narrower body, so what those rows buy is "
        "SHARPNESS, not tail weight. The instrument that helps is the one that makes the "
        "probabilities more confident.",
        f"- **The single home-field constant is eliminated as the CAUSE**, and separately "
        "convicted of something else. The residual mean at home sites is "
        f"{t3['residual_by_site'][0]['residual_mean']:+.3f} points against "
        f"{t3['residual_by_site'][1]['residual_mean']:+.3f} at neutral sites — a bias, but "
        "an order of magnitude too small to make a 13.67 pp decile. What §5.4 does show is "
        "that the site coefficient the harness actually uses averages "
        f"{t3['regression_coefficient']['mean']:.2f} points with a standard deviation of "
        f"{t3['regression_coefficient']['sd']:.2f} across published weeks, against "
        f"{t3['home_and_home_across_seasons_NOT_USABLE_LIVE']['h']:.2f} ± "
        f"{t3['home_and_home_across_seasons_NOT_USABLE_LIVE']['standard_error']:.2f} from "
        f"{t3['home_and_home_across_seasons_NOT_USABLE_LIVE']['n_pairs']} home-and-home "
        "pairs. Only 37 of the 1,585 scored games are at neutral sites, so the intercept "
        "and the site term are very nearly collinear and h is barely identified. That is a "
        "real defect and it is not this one.",
        "",
        "**THE CAUSE IS UNDER-DISPERSION OF THE POINT FORECAST, TILTED TOWARD THE HOME "
        "SIDE.** Two numbers carry it, and both replicate on 2024:",
        "",
        "| | Tune 2021-2023 | 2024 |",
        "|---|---:|---:|",
        f"| Slope of actual on predicted margin | {fl['slope']:.4f} ± {fl['stderr']:.4f} "
        f"| {cval.get('actual_on_predicted', {}).get('slope', float('nan')):.4f} ± "
        f"{cval.get('actual_on_predicted', {}).get('stderr', float('nan')):.4f} |",
        f"| Intercept (points) | {fl['intercept']:+.3f} "
        f"| {cval.get('actual_on_predicted', {}).get('intercept', float('nan')):+.3f} |",
        f"| Mean residual (points) | {res['mean']:+.3f} "
        f"| {cval.get('residual_mean', float('nan')):+.3f} |",
        "",
        f"A slope of {fl['slope']:.3f} is "
        f"{(fl['slope'] - 1.0) / fl['stderr']:.1f} standard errors above one: when this "
        "system forecasts a 20-point margin the truth averages more than 20, and when it "
        "forecasts −20 the truth averages worse than −20. Probabilities built from "
        "under-dispersed margins are too close to 0.5 — low deciles land BELOW their "
        "predicted rate, high deciles ABOVE — and the negative intercept pushes the whole "
        "curve down, which is why the low end misses by 13.67 pp and the high end by 1.23 "
        "pp. **That is the asymmetry, and it is not a distributional assumption, a variance "
        "function or a home-field constant. It is the point forecast itself.**",
        "",
        "The mechanism has a name in this codebase. Both the affine points calibration and "
        "σ are fitted on the games ACCUMULATED SO FAR in the season, and the ratings that "
        "feed them get better as the season goes on. A slope fitted on weeks 2-9 under-"
        f"scales week 10, and a σ fitted on weeks 2-9 ({base['sigma_mean']:.2f}) over-covers "
        f"week 10 ({sd['window_rmse']:.2f}). The two errors compound in the same direction, "
        "and §5.6's oracle row is what the σ half alone is worth.",
        "",
        "**What that does NOT license.** The out-of-sample rule those estimators follow is "
        "not the defect and must not be relaxed: fitting either of them on the training "
        "window costs L2 0.44 points of MAE and inverts the ordering against Elo "
        "(demo/backtest-2021-2023.md). The defect is the SHAPE of the accumulation window, "
        "not the fact that it is out of sample. A trailing window is out of sample too.",
        "",
    ]

    # ---------------- PART 6 ----------------
    lines += [
        "## PART 6 — THE GATE, BEFORE AND AFTER",
        "",
        "The headline ordering's own gate object, on the tune seasons, headline window.",
        "",
        "### Before — the starting values",
        "",
        *_gate_table(st["gate"]),
        "",
        "### After — the frozen choice",
        "",
        *_gate_table(ft["gate"]),
        "",
        "```json",
        json.dumps(
            {
                "before": {k: v for k, v in st["gate"].items() if k != "violations_vs_baselines_detail"},  # noqa: E501
                "after": {k: v for k, v in ft["gate"].items() if k != "violations_vs_baselines_detail"},  # noqa: E501
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
        "Every cell above was produced by overriding the four named keys on "
        "`configs/default.toml`. Since ADR 0007 that file CARRIES the frozen choice, so "
        "the \"after\" gate in this document and the gate the live pipeline computes must "
        "be the same object. They are checked rather than assumed:",
        "",
        _demo_cross_check(ft["gate"]),
        "",
        f"*Generated by `scripts/tuning_campaign.py` at commit `{prov['commit'][:10]}`; "
        f"every number above is in `tuning-campaign.json`. Config hash "
        f"`{prov['config_hash'][:16]}` — the file as it stands NOW, carrying the frozen "
        "choice; the search cells were produced by explicit overrides on it rather than by "
        f"editing it. Holdout touched: {str(prov['holdout_touched']).lower()}.*",
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


def _save_store(store: dict[str, Any]) -> None:
    store["provenance"] = _provenance()
    JSON_PATH.write_text(json.dumps(store, indent=2, sort_keys=True, default=float) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stages",
        nargs="*",
        default=[
            "grid",
            "modes",
            "full",
            "validate",
            "ranking",
            "calibration",
            "calibration-validate",
            "render",
        ],
        help=(
            "grid | modes | full | validate | ranking | calibration | "
            "calibration-validate | render"
        ),
    )
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    store = _load_store()
    for stage in args.stages:
        print(f"[stage] {stage}", flush=True)
        if stage == "grid":
            stage_grid(store, args.workers)
            print("  best:", store["grid"]["best"], flush=True)
        elif stage == "full":
            stage_full(store, args.workers)
            print("  best:", store["full_factorial"]["best"], flush=True)
        elif stage == "modes":
            stage_modes(store, args.workers)
            print("  best:", store["modes"]["best"], flush=True)
        elif stage == "validate":
            stage_validate(store, args.workers)
            print("  frozen:", store["frozen_choice"], flush=True)
            print("  validation:", store["validation"]["validate_mae_delta"], flush=True)
        elif stage == "ranking":
            stage_ranking(store, args.workers)
            print("  min tau:", store["ranking_impact"]["min_kendall_tau"], flush=True)
        elif stage == "calibration":
            stage_calibration(store, args.workers)
            dev = store["calibration_diagnosis"]["baseline"]["max_deviation_pp"]
            print(f"  baseline max dev: {dev}", flush=True)
        elif stage == "calibration-validate":
            stage_calibration_validate(store, args.workers)
            runs = store["calibration_validation"]["runs"]
            print("  " + json.dumps(runs, default=float)[:400], flush=True)
        elif stage == "render":
            _save_store(store)
            render(store)
            print(f"  wrote: {MD_PATH.relative_to(ROOT)}", flush=True)
        else:
            raise SystemExit(f"unknown stage {stage!r}")
        _save_store(store)
    print(f"wrote: {JSON_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
