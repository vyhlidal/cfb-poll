"""The recipe. Four terms, every coefficient published, rough by design.

    P_hat(t, Y) = a
                + phi   * (Power(t, Y-1) - mean_FBS Power(Y-1))     mean reversion
                + b_rp  * (returning_usage(t, Y) - mean_FBS)        returning production
                + b_hc  * coach_change(t, Y)                        new head coach
                + b_pf  * z(portal_net(t, Y))                       net portal flow

and the projected ranking is the FBS teams sorted by P_hat descending. That is
the whole model. It is four numbers and an intercept, fitted by ordinary least
squares on three season transitions, and it is deliberately not more than that:
this is v1 of a product whose value is the GRADING LOOP, and a recipe a reader
cannot hold in their head cannot be argued with in public.

WHAT IT PREDICTS, AND WHY THAT IS NOT WHAT THE POLL RANKS. The response is the
target season's final L3 POWER rating - a points-scale estimate of team strength.
The Poll's headline key is schedule odds, -log10 P(W >= W_t), which is a function
of the record and the schedule and therefore cannot exist before anyone has
played. So the Projection ranks Power and the Poll ranks schedule odds, they are
DIFFERENT QUANTITIES, and every comparison between them in this package is a
comparison of ORDERINGS - rank correlation, set overlap, rank error - never of
values. Saying that out loud is cheaper than letting a reader assume the two
numbers are the same number at different times.

WHY EACH TERM IS SHAPED THE WAY IT IS:

  phi IS LITERALLY THE MEAN-REVERSION COEFFICIENT because the prior rating is
  centred on the source season's FBS mean. phi = 1 is "last year's rating, kept";
  phi = 0 is "everyone starts at the league average". The fitted value is the
  answer to "how much of last season survives", and it is a number the reader can
  check against their own intuition in one glance.

  RETURNING PRODUCTION IS CENTRED AND UNSCALED, so b_rp reads as "points of Power
  per unit of returning offensive usage share" - the swing from returning nobody
  to returning everybody. THIS TERM IS OFFENCE ONLY. CFBD serves no defensive
  returning production of any kind, so the offence/defence split this recipe was
  asked for is half built and the half that exists is the offensive half. That is
  a hole in the DATA, stated as one everywhere the term appears, not a modelling
  choice.

  COACHING CHANGE IS AN UNCENTRED BINARY, so b_hc reads directly as "points of
  Power associated with a new head coach", and the intercept `a` is the projected
  Power of a league-average team that kept its coach. No coach is credited by
  name and there is no tenure term: one coefficient applies to every school that
  changed, which is the difference between a structural fact and FPI's coaching
  reputation prior.

  NET PORTAL IS STANDARDISED WITHIN EACH SEASON, and that is forced rather than
  chosen. CFBD's `destination` field is populated on 60% of 2022 portal rows and
  78% of 2026 rows, so `portal_net` is on a different scale in every cycle and
  pooling raw counts across transitions would fit a coefficient to a data-quality
  drift. Per-season standardisation makes the term "how unusual was this team's
  net flow, relative to its own cycle", which is the only version of the question
  the data can answer. `portal_out` is complete and `portal_in` is not; the
  asymmetry rides along on every artifact.

MISSING VALUES ARE IMPUTED HERE, ONCE, IN PUBLIC. A team with no returning
production row (a first-year FBS member) gets the season's FBS mean, which
contributes exactly zero after centring - "we know nothing, so this term says
nothing". A team with no prior-season fitted rating gets 0.0, which is the fit
universe's league-average prior and is what `PowerSource.rating` already returns
for an unseen team. Every imputation is flagged per team on the output frame, so
a reader can see which rows are imputed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from cfbpoll.projection import PROJECTION_VERSION, offseason

__all__ = [
    "DESIGN_COLUMNS",
    "TERMS",
    "Recipe",
    "build_design",
    "fit_recipe",
    "project",
    "term_contributions",
]

#: The recipe's terms, in the order they appear in the design matrix and in every
#: published table. `intercept` is not a term - it is the level - and it is kept
#: out of this tuple so "which term was wrong" can never answer "the intercept".
TERMS: tuple[str, ...] = (
    "prior_power",
    "returning_production",
    "coaching_change",
    "net_portal",
)

#: The design matrix's columns, one per term, in the same order. These names are
#: what `validate/leakage.py` audits: every one of them matches a pattern that is
#: BANNED in every poll layer and ALLOWED in this one.
DESIGN_COLUMNS: tuple[str, ...] = (
    "prior_power_centered",
    "returning_usage_centered",
    "coach_change",
    "portal_net_z",
)


@dataclass(frozen=True)
class Recipe:
    """Five published numbers and the provenance of every one of them.

    `coefficients` is keyed by `TERMS`; `intercept` is the level. `se` carries
    the OLS standard errors beside them, because a coefficient without one
    invites a reader to believe it harder than the data supports - and three
    season transitions is not many.
    """

    intercept: float
    coefficients: dict[str, float]
    se: dict[str, float]
    intercept_se: float
    transitions: tuple[tuple[int, int], ...]
    n_teams: int
    r_squared: float
    residual_sd: float
    version: str = PROJECTION_VERSION
    #: Which terms were actually fitted. A recipe fitted with `terms=("prior_power",)`
    #: is the mean-reversion-only baseline, and it is the same class so that the
    #: backtest scores it through the identical code path.
    terms: tuple[str, ...] = TERMS

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "terms": list(self.terms),
            "intercept": self.intercept,
            "intercept_se": self.intercept_se,
            "coefficients": {k: self.coefficients[k] for k in self.terms},
            "standard_errors": {k: self.se[k] for k in self.terms},
            "fitted_on_transitions": [list(t) for t in self.transitions],
            "n_team_seasons": self.n_teams,
            "r_squared": self.r_squared,
            "residual_sd": self.residual_sd,
        }

    def predict(self, design: pl.DataFrame) -> np.ndarray:
        """P_hat for every row of a design frame built by `build_design`."""
        out = np.full(design.height, float(self.intercept), dtype=np.float64)
        for term, column in zip(TERMS, DESIGN_COLUMNS, strict=True):
            if term not in self.terms:
                continue
            out = out + float(self.coefficients[term]) * _col(design, column)
        return out


def _col(frame: pl.DataFrame, name: str) -> np.ndarray:
    return frame[name].fill_null(0.0).to_numpy().astype(np.float64)


# ------------------------------------------------------------------- the design


def build_design(
    source_power: dict[str, float],
    target_season: int,
    teams: list[str],
    archive_root: Any = None,
) -> pl.DataFrame:
    """One row per team of `teams`, carrying every term the recipe consumes.

    `source_power` is the SOURCE season's final Power ratings - the output of
    `l4_resume.power_source` over that whole season - and `teams` is the TARGET
    season's FBS membership, because a projection is about who is going to play.

    Centring constants are computed over `teams` and are published on the frame
    (`*_center` columns are constant down the frame on purpose): a reader
    reproducing a single team's projection by hand needs them, and burying them
    in a fitting function would make the arithmetic uncheckable.
    """
    off = offseason.table(target_season, archive_root)
    frame = pl.DataFrame({"team": sorted(set(teams))}).join(off, on="team", how="left")

    prior = np.array([float(source_power.get(t, 0.0)) for t in frame["team"]], dtype=np.float64)
    prior_known = np.array([t in source_power for t in frame["team"]], dtype=bool)
    # The centring mean is over the teams that HAVE a fitted prior rating, so a
    # season with several new FBS members does not drag the league average down
    # by counting their imputed zeros as observations.
    prior_center = float(prior[prior_known].mean()) if prior_known.any() else 0.0

    usage = frame["returning_usage"].to_numpy().astype(np.float64)
    usage_known = ~frame["returning_usage"].is_null().to_numpy()
    usage_center = float(usage[usage_known].mean()) if usage_known.any() else 0.0
    usage_filled = np.where(usage_known, usage, usage_center)

    coach = frame["coach_change"].to_numpy()
    coach_known = ~frame["coach_change"].is_null().to_numpy()
    coach_rate = (
        float(np.asarray(coach, dtype=np.float64)[coach_known].mean()) if coach_known.any() else 0.0
    )
    coach_filled = np.where(coach_known, np.asarray(coach, dtype=np.float64), coach_rate)

    net = frame["portal_net"].to_numpy()
    net_known = ~frame["portal_net"].is_null().to_numpy()
    net_f = np.where(net_known, np.asarray(net, dtype=np.float64), 0.0)
    net_center = float(net_f[net_known].mean()) if net_known.any() else 0.0
    net_sd = float(net_f[net_known].std(ddof=1)) if int(net_known.sum()) > 1 else 0.0
    net_z = (net_f - net_center) / net_sd if net_sd > 0 else np.zeros_like(net_f)
    net_z = np.where(net_known, net_z, 0.0)

    return frame.with_columns(
        season=pl.lit(int(target_season), dtype=pl.Int32),
        prior_power=pl.Series(prior),
        prior_power_centered=pl.Series(prior - prior_center),
        prior_power_center=pl.lit(prior_center),
        prior_power_imputed=pl.Series((~prior_known).astype(np.int8), dtype=pl.Int8),
        returning_usage_filled=pl.Series(usage_filled),
        returning_usage_centered=pl.Series(usage_filled - usage_center),
        returning_usage_center=pl.lit(usage_center),
        returning_usage_imputed=pl.Series((~usage_known).astype(np.int8), dtype=pl.Int8),
        coach_change=pl.Series(coach_filled),
        coach_change_rate=pl.lit(coach_rate),
        coach_change_imputed=pl.Series((~coach_known).astype(np.int8), dtype=pl.Int8),
        portal_net_z=pl.Series(net_z),
        portal_net_center=pl.lit(net_center),
        portal_net_sd=pl.lit(net_sd),
        portal_net_imputed=pl.Series((~net_known).astype(np.int8), dtype=pl.Int8),
    ).sort("team")


# ------------------------------------------------------------------- the fitting


def fit_recipe(
    designs: list[pl.DataFrame],
    responses: list[np.ndarray],
    transitions: list[tuple[int, int]],
    terms: tuple[str, ...] = TERMS,
) -> Recipe:
    """Pooled OLS of the target season's final Power on the recipe's terms.

    Pooled rather than per-transition because three seasons is already thin and
    four coefficients per season would be fitting noise. The cost is that the
    recipe cannot express "returning production mattered more in 2023", which is
    a real limitation and exactly the kind of thing the grading loop is built to
    detect over future seasons.
    """
    columns = [c for term, c in zip(TERMS, DESIGN_COLUMNS, strict=True) if term in terms]
    blocks = [np.column_stack([np.ones(d.height)] + [_col(d, c) for c in columns]) for d in designs]
    x = np.vstack(blocks)
    y = np.concatenate([np.asarray(r, dtype=np.float64) for r in responses])

    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ coef
    dof = max(int(x.shape[0] - x.shape[1]), 1)
    sigma2 = float(resid @ resid) / dof
    xtx_inv = np.linalg.pinv(x.T @ x)
    stderr = np.sqrt(np.clip(np.diag(xtx_inv) * sigma2, 0.0, None))

    total = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float(resid @ resid) / total if total > 0 else 0.0

    fitted_terms = [term for term in TERMS if term in terms]
    return Recipe(
        intercept=float(coef[0]),
        intercept_se=float(stderr[0]),
        coefficients={term: float(coef[i + 1]) for i, term in enumerate(fitted_terms)},
        se={term: float(stderr[i + 1]) for i, term in enumerate(fitted_terms)},
        transitions=tuple((int(a), int(b)) for a, b in transitions),
        n_teams=int(x.shape[0]),
        r_squared=r2,
        residual_sd=float(np.sqrt(sigma2)),
        terms=tuple(fitted_terms),
    )


# ------------------------------------------------------------------ applying it


def term_contributions(recipe: Recipe, design: pl.DataFrame) -> pl.DataFrame:
    """Every term's signed contribution in points, per team, plus the total.

    THIS TABLE IS THE PRODUCT. A projected rank is an opinion; a projected rank
    with "+4.1 from last season, -1.8 because the offence left, -2.3 for the new
    coach" beside it is an argument, and an argument is the thing the grading
    loop can later say was wrong. `contrib_*` columns sum to `projected_power`
    exactly, intercept included, which `tests/unit/test_projection_recipe.py`
    asserts rather than trusting.
    """
    out = design.select(["team", "season"])
    total = np.full(design.height, float(recipe.intercept), dtype=np.float64)
    out = out.with_columns(contrib_intercept=pl.lit(float(recipe.intercept)))
    for term, column in zip(TERMS, DESIGN_COLUMNS, strict=True):
        if term not in recipe.terms:
            out = out.with_columns(**{f"contrib_{term}": pl.lit(0.0)})
            continue
        # `+ 0.0` normalises IEEE negative zero, which a negative coefficient
        # times an exact zero produces on every row where a term does not apply.
        # It is arithmetically identical and it is the difference between a
        # published table reading "-0.00" for 105 teams that did not change coach
        # and reading "0.00", which is what actually happened to them.
        contribution = float(recipe.coefficients[term]) * _col(design, column) + 0.0
        total = total + contribution
        out = out.with_columns(**{f"contrib_{term}": pl.Series(contribution)})
    return out.with_columns(projected_power=pl.Series(total))


def project(
    recipe: Recipe,
    design: pl.DataFrame,
    ranked_teams: list[str] | None = None,
) -> pl.DataFrame:
    """The projection: one row per team, ranked by projected Power, terms attached.

    `ranked_teams` restricts which teams receive a rank - the FBS membership -
    while every team in the design keeps its row, exactly as `retro._cell_frame`
    does it for the poll. Ties break on team name so the order is a pure function
    of the numbers and the alphabet, and never of frame construction order.
    """
    contributions = term_contributions(recipe, design)
    frame = design.join(contributions.drop("season"), on="team", how="left")
    frame = frame.sort(["projected_power", "team"], descending=[True, False])

    eligible = set(ranked_teams) if ranked_teams is not None else set(frame["team"].to_list())
    ranks: list[int | None] = []
    seen = 0
    for team in frame["team"].to_list():
        if team in eligible:
            seen += 1
            ranks.append(seen)
        else:
            ranks.append(None)
    return frame.with_columns(
        projected_rank=pl.Series(ranks, dtype=pl.Int32),
        recipe_version=pl.lit(recipe.version),
    )


@dataclass(frozen=True)
class SeasonInputs:
    """Everything one transition needs, gathered once so the fit cannot re-read.

    Held as a frozen dataclass rather than a tuple because a transition carries
    six things and positional unpacking of six things is how a source season and
    a target season end up swapped in a backtest nobody re-reads.
    """

    source_season: int
    target_season: int
    design: pl.DataFrame
    response: np.ndarray
    teams: tuple[str, ...]
    coverage: dict[str, Any] = field(default_factory=dict)
