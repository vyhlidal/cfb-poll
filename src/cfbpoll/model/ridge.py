"""The shared penalised-least-squares solver and the lambda search.

Specified by report 02 §2.8 and §3.1.

    theta_hat = (Xᵀ W X + lambda * D)^-1 Xᵀ W y

D is diagonal with 1 in team positions and 0 for the intercept (L1) and the
home-field term, so those are UNPENALISED. XᵀWX and XᵀWy do not depend on lambda, so
form them once and reuse across the whole grid - the CV search is then a sequence
of cheap Cholesky solves on an already-formed matrix (report 02 §3.11).

Why the penalty is not optional, in one row (Sill 2010, report 02 §2.8):
unregularized least squares on a one-year sample scored WORSE than predicting the
mean (test RMSE 12.76 vs 12.58). Ridge at the same sample size scored 11.54.

Why this is not a reputation prior (report 02 §4): lambda is literally a ratio of
variances - noise variance over prior variance. It is a statement about how much
we do not know, identical for every team, containing no team-specific
information whatsoever. Colley's +2 pseudo-games, Bradley-Terry's phantom player,
Laplace's rule of succession and this penalty are the same mathematical object
under four names in four literatures, always solving identifiability on sparse
schedules, never encoding an opinion.

DETERMINISM (report 03 §9.3): there is no RNG anywhere in this module. Fold
assignment is a pure function of the sorted group ids, so a CV result depends on
the data and nothing else - not on hash seeds, not on core count, not on the
order rows arrived in. Callers should pin OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=
MKL_NUM_THREADS=1 (Makefile / CI do); the fits are sub-second and the threads buy
nothing but nondeterministic summation order.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import sparse
from scipy.linalg import cho_factor, cho_solve

__all__ = [
    "CVResult",
    "Sandwich",
    "cv_select_lambda",
    "difference_se",
    "group_folds",
    "normal_equations",
    "sandwich",
    "solve",
    "solve_normal",
]


def normal_equations(
    z: sparse.spmatrix,
    y: np.ndarray,
    w: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """(ZᵀWZ, ZᵀWy). Neither depends on lambda, so form them once per fold.

    This is the whole of report 02 §3.11's cost argument. At L2 the matrix is a
    few hundred on a side and it hardly matters; at L1 the design is ~170k x ~530
    and re-forming it for each of eleven lambdas in each of five folds would do
    55 sparse products where 5 suffice.
    """
    zw = z.T.multiply(w)  # (n_cols x n_rows), each column scaled by its weight
    a = np.asarray((zw @ z).todense(), dtype=np.float64)
    b = np.asarray(zw @ y, dtype=np.float64).ravel()
    return a, b


def solve_normal(
    a: np.ndarray,
    b: np.ndarray,
    penalty: np.ndarray,
    lam: float,
) -> np.ndarray:
    """Cholesky solve of (A + lambda*D) theta = b, without disturbing A."""
    m = a.copy()
    m[np.diag_indices_from(m)] += lam * penalty
    return cho_solve(cho_factor(m, lower=True, check_finite=False), b, check_finite=False)


def solve(
    z: sparse.spmatrix,
    y: np.ndarray,
    w: np.ndarray,
    penalty: np.ndarray,
    lam: float,
) -> np.ndarray:
    """theta = (ZᵀWZ + lambda*D)^-1 ZᵀWy, by Cholesky on the dense normal matrix.

    The normal matrix is (T+1) x (T+1) at L2 - a few hundred on a side - so densifying
    it costs nothing and buys a numerically clean, exactly reproducible solve.
    """
    a, b = normal_equations(z, y, w)
    return solve_normal(a, b, penalty, lam)


@dataclass(frozen=True)
class Sandwich:
    """The ridge sandwich covariance, and the two numbers it was built from.

    `cov` is in the units of the RESPONSE the fit was run on, which at L2 is the
    compressed margin and not points. Rescaling to points is the caller's job and
    is exactly the `b` (or `w2`) that already maps ratings to points - see
    `model/l4_resume.py::PowerSource`.
    """

    cov: np.ndarray
    residual_variance: float
    effective_df: float
    n_observations: int

    def se(self) -> np.ndarray:
        """Per-coefficient standard error: the square root of the diagonal."""
        return np.sqrt(np.clip(np.diag(self.cov), 0.0, None))

    def as_dict(self) -> dict[str, object]:
        return {
            "residual_variance": self.residual_variance,
            "residual_sd": float(np.sqrt(self.residual_variance)),
            "effective_df": self.effective_df,
            "n_observations": self.n_observations,
            "form": "sigma2 * (ZtWZ + lambda D)^-1 (ZtW^2Z) (ZtWZ + lambda D)^-1",
            "spec": "report 02 §3.3",
        }


def sandwich(
    z: sparse.spmatrix,
    y: np.ndarray,
    w: np.ndarray,
    penalty: np.ndarray,
    lam: float,
    theta: np.ndarray,
) -> Sandwich:
    """The ridge sandwich covariance of report 02 §3.3.

        Cov(theta_hat) = sigma^2 (ZᵀWZ + lambda D)^-1 (ZᵀW²Z) (ZᵀWZ + lambda D)^-1

    THE HISTORY OF THIS FUNCTION IS WORTH A PARAGRAPH. Report 02 §3.3 wrote this
    formula down and then set it aside as less "robust for publication" than a
    bootstrap - and specified the wrong bootstrap in the same sentence
    ("resample games with replacement"), which model/bootstrap.py copied
    faithfully into a docstring and never built. The independent review
    (docs/analysis/fresh-eyes-review.md, appendix) computed every standard error
    in its §4 from exactly this expression and endorsed it. The right instrument
    was in hand and was put down; this is picking it back up.

    IT IS NOT A SUBSTITUTE FOR THE BOOTSTRAP AND DOES NOT ANSWER THE SAME
    QUESTION. This is the sampling covariance of the RATINGS conditional on the
    observed results, which is what "how precisely is this team's rating pinned
    down" means, and it is what makes a matched-units statement like "James
    Madison minus Michigan is 8.6 +/- 4.2 points" computable. It says nothing
    about how far a RANK would move, because a rank is a function of every team's
    rating at once and of the record, and that is what the parametric bootstrap
    on the fixed schedule is for.

    `sigma^2` is estimated from the weighted residuals with the ridge effective
    degrees of freedom in the denominator - `trace((ZᵀWZ + lambda D)^-1 ZᵀWZ)`,
    which is the standard ridge edf and is strictly smaller than the column
    count, because shrinkage costs less than a free parameter per team.
    """
    zw = z.T.multiply(w)
    a_unpenalized = np.asarray((zw @ z).todense(), dtype=np.float64)
    meat = np.asarray((z.T.multiply(w**2) @ z).todense(), dtype=np.float64)

    penalised = a_unpenalized.copy()
    penalised[np.diag_indices_from(penalised)] += lam * penalty
    inverse = np.linalg.inv(penalised)

    resid = y - np.asarray(z @ theta).ravel()
    edf = float(np.trace(inverse @ a_unpenalized))
    weight_total = float(np.sum(w))
    denominator = max(weight_total - edf, 1.0)
    sigma2 = float(np.sum(w * resid**2) / denominator)

    return Sandwich(
        cov=sigma2 * (inverse @ meat @ inverse),
        residual_variance=sigma2,
        effective_df=edf,
        n_observations=int(z.shape[0]),
    )


def difference_se(cov: np.ndarray, i: int, j: int) -> float:
    """SE of (theta_i - theta_j). THE quantity a ranking argument is about.

    Var(a - b) = Var(a) + Var(b) - 2 Cov(a, b), and the covariance term is not a
    detail: two teams that played each other, or that share many opponents, have
    strongly correlated estimation errors, so the SE of their DIFFERENCE is much
    smaller than the two individual SEs would suggest. A page that publishes only
    per-team error bars and lets a reader add them in quadrature overstates the
    uncertainty of every comparison it is actually making.
    """
    var = float(cov[i, i] + cov[j, j] - 2.0 * cov[i, j])
    return float(np.sqrt(max(var, 0.0)))


def group_folds(groups: np.ndarray, n_folds: int) -> np.ndarray:
    """Deterministic GroupKFold assignment. No RNG, no shuffle, no hash order.

    Groups are ranked by id and dealt round-robin, which balances fold sizes
    exactly and is a pure function of the input. Report 02 §3.1 is emphatic that
    the group must be `game_id` and never a play: plays within a game are not
    independent and splitting them across folds leaks. At L2 one game is one row,
    so the grouping is the identity - but the harness is shared with L1, where it
    is load-bearing, and stating it here keeps the two honest.
    """
    if n_folds < 2:
        raise ValueError("n_folds must be at least 2")
    unique = np.unique(groups)
    fold_of_group = {g: i % n_folds for i, g in enumerate(unique)}
    return np.array([fold_of_group[g] for g in groups], dtype=np.int64)


@dataclass(frozen=True)
class CVResult:
    """The lambda search, published verbatim in model_params.json."""

    lam: float
    grid: tuple[float, ...]
    cv_error: tuple[float, ...]
    n_folds: int

    def as_dict(self) -> dict[str, object]:
        return {
            "lambda": self.lam,
            "grid": list(self.grid),
            "cv_weighted_mse": list(self.cv_error),
            "n_folds": self.n_folds,
        }


def cv_select_lambda(
    z: sparse.spmatrix,
    y: np.ndarray,
    w: np.ndarray,
    penalty: np.ndarray,
    groups: np.ndarray,
    grid: list[float] | tuple[float, ...],
    n_folds: int = 5,
) -> CVResult:
    """Pick lambda by grouped k-fold CV on weighted squared error.

    Ties are broken toward the LARGER lambda: when two penalties fit the held-out
    games equally well, the more shrunken one is the more honest claim about how
    much we know. That rule also makes the search reproducible under floating
    point wobble at the last bit.

    With fewer games than folds - week 1 of a season, or a challenger fitting a
    toy frame - CV is impossible and the largest lambda in the grid is returned.
    Shrinking hard on almost no data is the correct default and is exactly the
    behaviour report 02 §4 relies on for the early-season policy.
    """
    grid = tuple(float(g) for g in sorted(grid))
    n = z.shape[0]
    if n < n_folds * 2:
        return CVResult(
            lam=grid[-1], grid=grid, cv_error=tuple([float("nan")] * len(grid)), n_folds=0
        )

    folds = group_folds(groups, n_folds)
    errors = np.zeros(len(grid), dtype=np.float64)
    weight_total = 0.0

    for f in range(n_folds):
        test = folds == f
        train = ~test
        if not train.any() or not test.any():
            continue
        z_tr, z_te = z[train], z[test]
        a, b = normal_equations(z_tr, y[train], w[train])
        for i, lam in enumerate(grid):
            theta = solve_normal(a, b, penalty, lam)
            resid = y[test] - np.asarray(z_te @ theta).ravel()
            errors[i] += float(np.sum(w[test] * resid**2))
        weight_total += float(np.sum(w[test]))

    if weight_total > 0:
        errors /= weight_total

    best = int(np.argmax(errors[::-1] <= errors.min() + 1e-12))
    best = len(grid) - 1 - best  # largest lambda among the (near-)minimisers
    return CVResult(lam=grid[best], grid=grid, cv_error=tuple(errors.tolist()), n_folds=n_folds)
