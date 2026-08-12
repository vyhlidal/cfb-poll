"""L4 - Resume rating: the "deserve" number, and THE HEADLINE POLL.

Specified by report 02 §3.4. This is ESPN's Strength-of-Record idea put on the
points scale and made deterministic - a root-solve instead of a 20,000-run Monte
Carlo, so it is cheaper AND exactly reproducible.

For a team t with games g against opponents o_g at sites s_g:

    mu_g(q) = q - Power_{o_g} + h * s_g
    P_g(q)  = Phi( mu_g(q) / sigma )
    E[W|q]  = sum_g P_g(q)

    Resume_t = the unique q* with E[W|q*] = W_t   (actual wins)

E[W|q] is strictly increasing and continuous in q, so bisection on q in
[-60, +60] converges to machine precision in ~40 iterations, each costing n
normal CDF evaluations. Microseconds per team. sigma = 15.3 points, confirmed
twice independently (report 02 §5.4).

Reads in one sentence a fan can parse: "given who they played and where, these
results are what a +18.4 team would be expected to produce."

Margin-aware variant (a Game Control analogue): solve instead for the q* where
the expected compressed margin equals the actual, using 20-node Gauss-Hermite
quadrature. Publish both; disagreement between them is informative.

THE RETROACTIVE MECHANISM, in one substitution (report 02 §3.4, §3.6):
Resume_t depends on opponent quality ONLY through Power_{o_g}. Pass
through-week-N Power ratings and you get the live ranking R(N,N); pass
end-of-season Power ratings and you get the hindsight ranking R(N,final).
Nothing else changes. That is constraint 4, satisfied definitionally rather than
bolted on - and it is why the estimator is a batch refit and not an Elo.

STATUS: SCAFFOLD. Build this THIRD (report 02 Appendix B step 3), on top of L2
and before any play-by-play work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl


def expected_wins(
    q: float,
    opponent_power: list[float],
    sites: list[int],
    h: float,
    sigma: float,
) -> float:
    """E[W | q] against this exact schedule (report 02 §3.4)."""
    raise NotImplementedError("l4_resume.expected_wins - scaffold; see report 02 §3.4")


def solve_quality(
    actual_wins: float,
    opponent_power: list[float],
    sites: list[int],
    h: float,
    sigma: float,
) -> float:
    """Bisect on q in [-60, +60] for E[W|q*] = actual wins (report 02 §3.4)."""
    raise NotImplementedError("l4_resume.solve_quality - scaffold; see report 02 §3.4")


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    through_week: int,
) -> dict[int, float]:
    """Challenger-protocol entry point (report 03 §7.3): the incumbent headline poll."""
    raise NotImplementedError("l4_resume.rate - scaffold; see report 02 §3.4")


def rate_hindsight(
    games: pl.DataFrame,
    plays: pl.DataFrame | None,
    eval_week: int,
    data_window: int,
) -> dict[int, float]:
    """R(eval_week, data_window): the retroactive surface (report 02 §3.6, variant A).

    Frozen-form hindsight: Power from the FULL season, Resume from that team's
    games THROUGH eval_week only. Answers the plain-English question "given what
    we now know about how good those opponents actually were, how good were the
    first N weeks of results?" The time-varying form (variant B, a state-space
    model) is a documented future direction, not v1.
    """
    raise NotImplementedError("l4_resume.rate_hindsight - scaffold; see report 02 §3.6")
