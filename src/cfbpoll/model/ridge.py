"""The shared penalised-least-squares solver and the lambda search.

Specified by report 02 §2.8 and §3.1.

    theta_hat = (Xᵀ W X + lambda * D)^-1 Xᵀ W y_tilde

D is diagonal with 1 in team positions and 0 for the intercept and the home-field
term, so those two are UNPENALISED. XᵀWX and XᵀWy do not depend on lambda, so
form them once and reuse across the whole grid - the CV search is then a sequence
of cheap Cholesky solves on an already-formed 530x530 matrix (report 02 §3.11).

Why the penalty is not optional, in one row (Sill 2010, report 02 §2.8):
unregularized least squares on a one-year sample scored WORSE than predicting the
mean (test RMSE 12.76 vs 12.58). Ridge at the same sample size scored 11.54.

Why this is not a reputation prior (report 02 §4): lambda is literally a ratio of
variances - noise variance over prior variance. It is a statement about how much
we do not know. Every team gets the identical penalty and there are no
team-specific constants anywhere in this file, which is an auditable claim.

Lambda is chosen by GroupKFold CROSS-VALIDATION GROUPED ON game_id, never on
play. Plays within a game are not independent and splitting them across folds
leaks (report 02 §3.1).

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import Any


def solve(xtwx: Any, xtwy: Any, lam: float, penalty_diag: Any) -> Any:
    """Solve the penalised normal equations for one lambda."""
    raise NotImplementedError("ridge.solve - scaffold; see report 02 §3.1")


def select_lambda(
    design: Any,
    groups: Any,
    grid: list[float],
    n_splits: int = 5,
) -> float:
    """Pick lambda by GroupKFold CV grouped on game_id.

    Expect lambda to be large early in the season and to decline as data
    accumulates - the published CFBD implementation observed exactly this
    ("smaller datasets require higher values"). That behaviour is what makes
    ridge the early-season stabiliser instead of a reputation prior
    (report 02 §4, Option A machinery under Option B publication policy).
    """
    raise NotImplementedError("ridge.select_lambda - scaffold; see report 02 §3.1")
