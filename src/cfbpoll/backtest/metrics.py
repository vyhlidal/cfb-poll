"""Scoring metrics and the publication gate.

Specified by report 02 §5.2 and §5.4.

PREDICTIVE: straight-up accuracy, margin MAE and RMSE, Brier score, log loss, and
a calibration plot (predicted decile vs observed win rate). Calibration matters
more than sharpness for a poll: a model that says 80% and is right 80% of the
time is trustworthy in a way a slightly sharper miscalibrated one is not.

RETRODICTIVE: violations - games where the final ranking places the loser above
the winner - and the distance to the MinV bound (minv.py).

STABILITY: week-over-week rank churn; retro-vs-live divergence, which must
DECLINE monotonically in N or the retroactive product itself is unstable;
bootstrap interval coverage (do the published 90% rank intervals actually contain
the hindsight rank 90% of the time?).

DESCRIPTIVE, NOT A TARGET: Kendall tau and Spearman rho against the final CFP
committee top-25. Fitting toward committee agreement would reintroduce human poll
bias through the back door - a subtle but complete violation of constraint 1.
Report the disagreements and let the disagreements be the product.

ATS is REPORTED, NEVER OPTIMISED (report 02 §5.4). Break-even at -110 is 52.38%.
Any sustained result above ~53% over 800+ games is an overfitting alarm until it
replicates out of sample.

The numeric gate lives in configs/default.toml under [gate].

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import Any


def straight_up_accuracy(predictions: Any) -> float:
    """Share of games where the higher-rated team (with home field) won."""
    raise NotImplementedError("backtest.metrics.straight_up_accuracy - scaffold; report 02 §5.2")


def margin_errors(predictions: Any) -> dict[str, float]:
    """MAE and RMSE of predicted vs actual margin."""
    raise NotImplementedError("backtest.metrics.margin_errors - scaffold; report 02 §5.2")


def brier(predictions: Any) -> float:
    """Brier score on win probability. Benchmark against our own baselines only.

    No published CFB-specific Brier study was found; the widely circulated
    figures are NFL-only and are frequently misattributed to college football
    (report 02 §5.4).
    """
    raise NotImplementedError("backtest.metrics.brier - scaffold; see report 02 §5.2")


def violations(ranking: Any, games: Any) -> int:
    """Count games whose loser is ranked above its winner. The retrodictive metric."""
    raise NotImplementedError("backtest.metrics.violations - scaffold; report 02 §2.12, §5.2")


def check_gate(results: dict[str, float], gate: dict[str, float]) -> bool:
    """Evaluate the publication gate from configs/default.toml [gate] (report 02 §5.4)."""
    raise NotImplementedError("backtest.metrics.check_gate - scaffold; see report 02 §5.4")
