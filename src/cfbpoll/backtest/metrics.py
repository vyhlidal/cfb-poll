"""Scoring metrics and the publication gate.

Specified by report 02 §5.2 and §5.4.

PREDICTIVE: straight-up accuracy, margin MAE and RMSE, Brier score, log loss, and
a calibration table (predicted decile vs observed win rate). Calibration matters
more than sharpness for a poll: a model that says 80% and is right 80% of the
time is trustworthy in a way a slightly sharper miscalibrated one is not.

RETRODICTIVE: violations - games where the final ranking places the loser above
the winner - and the distance to the MinV bound (minv.py, still a stub).

STABILITY: week-over-week rank churn; retro-vs-live divergence, which must
DECLINE monotonically in N or the retroactive product itself is unstable;
bootstrap interval coverage (do the published 90% rank intervals actually contain
the hindsight rank 90% of the time?). Only churn is available at L2 - the other
two need L4 and the bootstrap.

DESCRIPTIVE, NOT A TARGET: Kendall tau and Spearman rho against the final CFP
committee top-25. Fitting toward committee agreement would reintroduce human poll
bias through the back door - a subtle but complete violation of constraint 1.
Report the disagreements and let the disagreements be the product.

ATS is REPORTED, NEVER OPTIMISED (report 02 §5.4). Break-even at -110 is 52.38%.
Any sustained result above ~53% over 800+ games is an overfitting alarm until it
replicates out of sample. Not computed here: the archive carries no spreads.

The numeric gate lives in configs/default.toml under [gate].
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import norm

__all__ = [
    "brier",
    "calibration_table",
    "check_gate",
    "log_loss",
    "margin_errors",
    "rank_churn",
    "straight_up_accuracy",
    "summarize",
    "violations",
    "win_probability",
]

#: Probabilities are clipped before log loss so a single confident miss cannot
#: return infinity and destroy a whole season's number.
_EPS = 1e-9


def win_probability(predicted_margin: np.ndarray, sigma: float) -> np.ndarray:
    """P(home wins) = Phi(predicted margin / sigma), report 02 §3.4 and §5.4.

    sigma = 15.3 points, confirmed twice independently: the Prediction Tracker
    RMSE band for good public models, and a conditional-SD estimate of 15.35 for
    the 2021 season derived by a completely different method.
    """
    return np.asarray(norm.cdf(np.asarray(predicted_margin, dtype=np.float64) / sigma))


def straight_up_accuracy(predicted_margin: np.ndarray, actual_margin: np.ndarray) -> float:
    """Share of games in which the predicted side won.

    A predicted margin of exactly zero is scored 0.5 - a coin flip, honestly
    counted as one. It happens only for the home-team-always-wins floor at
    neutral sites and for systems that have not seen either team yet.
    """
    p = np.sign(np.asarray(predicted_margin, dtype=np.float64))
    a = np.sign(np.asarray(actual_margin, dtype=np.float64))
    if p.size == 0:
        return float("nan")
    return float(np.mean(np.where(p == 0, 0.5, (p == a).astype(np.float64))))


def margin_errors(predicted_margin: np.ndarray, actual_margin: np.ndarray) -> dict[str, float]:
    """MAE and RMSE of predicted vs actual margin."""
    resid = np.asarray(predicted_margin, dtype=np.float64) - np.asarray(
        actual_margin, dtype=np.float64
    )
    if resid.size == 0:
        return {"mae": float("nan"), "rmse": float("nan")}
    return {
        "mae": float(np.mean(np.abs(resid))),
        "rmse": float(np.sqrt(np.mean(resid**2))),
    }


def brier(prob: np.ndarray, won: np.ndarray) -> float:
    """Brier score on win probability. Benchmark against our own baselines only.

    No published CFB-specific Brier study was found; the widely circulated
    figures are NFL-only and are frequently misattributed to college football
    (report 02 §5.4).
    """
    p = np.asarray(prob, dtype=np.float64)
    y = np.asarray(won, dtype=np.float64)
    return float(np.mean((p - y) ** 2)) if p.size else float("nan")


def log_loss(prob: np.ndarray, won: np.ndarray) -> float:
    p = np.clip(np.asarray(prob, dtype=np.float64), _EPS, 1 - _EPS)
    y = np.asarray(won, dtype=np.float64)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))) if p.size else float("nan")


def calibration_table(
    prob: np.ndarray, won: np.ndarray, bins: int = 10, min_count: int = 20
) -> list[dict[str, float]]:
    """Predicted-probability decile vs observed win rate (report 02 §5.2).

    Bins are fixed-width on [0, 1] rather than quantile bins, so the table means
    the same thing for every system and across weeks. Bins holding fewer than
    `min_count` games are reported but excluded from the max-deviation summary,
    because a 3-game bin says nothing.
    """
    p = np.asarray(prob, dtype=np.float64)
    y = np.asarray(won, dtype=np.float64)
    edges = np.linspace(0.0, 1.0, bins + 1)
    out: list[dict[str, float]] = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (p >= lo) & (p < hi) if hi < 1.0 else (p >= lo) & (p <= hi)
        n = int(mask.sum())
        out.append(
            {
                "bin_low": float(lo),
                "bin_high": float(hi),
                "n": float(n),
                "mean_predicted": float(np.mean(p[mask])) if n else float("nan"),
                "observed_rate": float(np.mean(y[mask])) if n else float("nan"),
                "counted": float(n >= min_count),
            }
        )
    return out


def max_calibration_deviation_pp(table: list[dict[str, float]]) -> float:
    """The gate's calibration number: worst |observed - predicted|, in points."""
    devs = [
        abs(row["observed_rate"] - row["mean_predicted"]) * 100.0
        for row in table
        if row["counted"] and np.isfinite(row["observed_rate"])
    ]
    return float(max(devs)) if devs else float("nan")


def violations(
    ratings: dict[str, float],
    winners: list[str],
    losers: list[str],
) -> dict[str, float]:
    """Games whose loser is ranked above its winner. THE retrodictive metric.

    Coleman's literature is built on it, and his finding is the reason to
    compute it: every previously published system produced violations at least
    38% above the achievable minimum (report 02 §2.12). A team absent from the
    ratings is treated as the neutral 0.0 rather than dropped, so the denominator
    is every game.
    """
    if not winners:
        return {"violations": float("nan"), "violation_rate": float("nan"), "games": 0.0}
    bad = 0
    for w, ll in zip(winners, losers, strict=True):
        if ratings.get(w, 0.0) < ratings.get(ll, 0.0):
            bad += 1
    return {
        "violations": float(bad),
        "violation_rate": float(bad) / len(winners),
        "games": float(len(winners)),
    }


def rank_churn(
    previous: dict[str, int] | None,
    current: dict[str, int],
    top_n: int = 25,
) -> dict[str, float]:
    """Mean absolute rank change week over week, overall and in the top 25.

    Teams that appear in only one of the two weeks are skipped: a team's first
    appearance is not churn, it is arrival.
    """
    if not previous:
        return {"churn_all": float("nan"), "churn_top25": float("nan"), "n": 0.0}
    shared = sorted(set(previous) & set(current))
    if not shared:
        return {"churn_all": float("nan"), "churn_top25": float("nan"), "n": 0.0}
    deltas = np.array([abs(previous[t] - current[t]) for t in shared], dtype=np.float64)
    in_top = np.array([previous[t] <= top_n or current[t] <= top_n for t in shared], dtype=bool)
    return {
        "churn_all": float(np.mean(deltas)),
        "churn_top25": float(np.mean(deltas[in_top])) if in_top.any() else float("nan"),
        "n": float(len(shared)),
    }


def summarize(
    predicted_margin: np.ndarray,
    actual_margin: np.ndarray,
    sigma: float,
) -> dict[str, Any]:
    """Every predictive metric for one set of games, in one call."""
    predicted_margin = np.asarray(predicted_margin, dtype=np.float64)
    actual_margin = np.asarray(actual_margin, dtype=np.float64)
    prob = win_probability(predicted_margin, sigma)
    won = (actual_margin > 0).astype(np.float64)
    table = calibration_table(prob, won)
    return {
        "n_games": int(actual_margin.size),
        "su_accuracy": straight_up_accuracy(predicted_margin, actual_margin),
        **margin_errors(predicted_margin, actual_margin),
        "brier": brier(prob, won),
        "log_loss": log_loss(prob, won),
        "max_calibration_deviation_pp": max_calibration_deviation_pp(table),
        "calibration": table,
    }


def check_gate(results: dict[str, float], gate: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the publication gate from configs/default.toml [gate] (report 02 §5.4).

    Returns a per-criterion verdict rather than a bare bool, because "which one
    failed" is the only useful answer. Criteria that need layers or data we do
    not have yet (Brier vs all baselines, MinV distance, retro-vs-live
    monotonicity) are reported as `null` - not as passes.
    """
    checks: dict[str, Any] = {}
    su = results.get("su_accuracy")
    checks["su_accuracy"] = None if su is None else bool(su >= gate["su_accuracy_min"])
    mae = results.get("mae")
    checks["mae"] = None if mae is None else bool(mae <= gate["mae_max"])
    rmse = results.get("rmse")
    checks["rmse"] = None if rmse is None else bool(rmse <= gate["rmse_max"])
    dev = results.get("max_calibration_deviation_pp")
    checks["calibration"] = (
        None
        if dev is None or not np.isfinite(dev)
        else bool(dev <= gate["calibration_max_decile_deviation_pp"])
    )
    checks["brier_beats_all_baselines"] = None
    checks["violations_vs_baselines"] = None
    checks["retro_vs_live_monotone"] = None
    decided = [v for v in checks.values() if v is not None]
    checks["passed"] = bool(decided) and all(decided)
    checks["undecided"] = sorted(k for k, v in checks.items() if v is None)
    return checks
