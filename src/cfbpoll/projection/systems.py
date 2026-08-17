"""The systems the chain scores, including the one this project now ships.

Every builder here has the same shape and the same discipline: it is handed one
target season and the seasons behind it, and it must return a rating for every
team it is willing to have an opinion about, using nothing from the target season
except the calendar, the FBS membership and the offseason table - all three of
which exist in August.

    carryover        last season's Power, unchanged. phi = 1, no terms, no fit.
                     The floor, and a stubbornly good one: mean reversion is a
                     positive affine map and cannot reorder anything, so on
                     straight-up accuracy this is "last season's ordering" and
                     nothing else.
    projection_v2    the recipe this project published as `projection-2.0.0`.
                     Four terms, ordinary least squares, one season of memory,
                     FCS ratings carried at face value. THE BASELINE THE NEW ONE
                     HAS TO BEAT, scored under the identical walk-forward
                     protocol rather than against its own published numbers.
    projection_v3    the liberated recipe. Same four terms, plus two changes that
                     were measured before they were adopted: a second season of
                     memory, and the cross-division correction from
                     `crossdivision.py`.
    ap_preseason     the AP writers' August ballot. A BASELINE, never an input.
                     It rates 25 teams and is silent about the other 109, so it
                     is given 25 down to 1 and a flat zero for everyone else -
                     crude, because the source is: the AP publishes no rating.

WHY v3 IS NOT MORE THAN THIS. The charter says everything except the two
untouchables is free, and the temptation is to spend that freedom immediately.
The two changes here were adopted because each was measured to help on the
owner's own criterion and each has a one-sentence football explanation. Terms
that could not clear both tests were left out, and the lever registry is where
they will go when they can.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

from cfbpoll.projection import crossdivision, offseason, recipe

__all__ = [
    "ProjectionLevers",
    "SeasonInputs",
    "prepare",
    "ap_preseason_builder",
    "builders",
    "carried_ratings",
    "carryover_builder",
    "fit_walk_forward",
    "projection_builder",
]


@dataclass(frozen=True)
class ProjectionLevers:
    """The projection-side lever settings, resolved to numbers.

    Mirrors the `projection.*` half of `cfbpoll.levers.LEVERS`. Held as a frozen
    dataclass rather than a dict so a grid search cannot mutate the cell it is
    scoring, and so a typo in a lever name is an AttributeError at the call site
    instead of a silently ignored key.
    """

    long_memory: float = 0.2
    cross_division_gap: float = 1.0
    promotion_credit: float = 1.0
    returning_production: float = 1.0
    coaching_change: float = 1.0
    portal: float = 1.0
    home_field: float = 1.5
    #: The extrapolation guard on the promotion bump. On by default: no promoted
    #: team is projected above the best first FBS season any promoted program has
    #: actually had. Off, and a program rated far above every previous promotion
    #: gets the full bump anyway.
    promotion_ceiling: bool = True

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> ProjectionLevers:
        """Read `[levers.projection]`. Missing keys fall back to the class defaults.

        Falling back rather than raising is deliberate: a fork running an older
        config should get a working board with the shipped values, not a crash on
        a key it has never heard of. What it must NOT get is a silent difference,
        so `as_dict` goes onto every artifact and the reader can see which values
        actually ran.
        """
        block = dict((config.get("levers") or {}).get("projection") or {})
        fields = {
            "long_memory": float,
            "cross_division_gap": float,
            "promotion_credit": float,
            "returning_production": float,
            "coaching_change": float,
            "portal": float,
            "home_field": float,
            "promotion_ceiling": bool,
        }
        kwargs = {
            name: cast(block[name]) for name, cast in fields.items() if name in block
        }
        return cls(**kwargs)

    @property
    def term_weights(self) -> dict[str, float]:
        return {
            "prior_power": 1.0,
            "returning_production": float(self.returning_production),
            "coaching_change": float(self.coaching_change),
            "net_portal": float(self.portal),
        }

    def as_dict(self) -> dict[str, float]:
        return {
            "projection.long_memory": float(self.long_memory),
            "projection.cross_division_gap": float(self.cross_division_gap),
            "projection.promotion_credit": float(self.promotion_credit),
            "projection.returning_production": float(self.returning_production),
            "projection.coaching_change": float(self.coaching_change),
            "projection.portal": float(self.portal),
            "projection.home_field": float(self.home_field),
            "projection.promotion_ceiling": float(self.promotion_ceiling),
        }


#: The shipped `projection-2.0.0` recipe, expressed as a lever setting so that the
#: old model and the new one are scored by the identical code path. One season of
#: memory, FCS ratings at face value, and the home-field constant believed exactly
#: as season Y-1's fit reported it.
V2_LEVERS = ProjectionLevers(
    long_memory=0.0,
    cross_division_gap=0.0,
    promotion_credit=0.0,
    home_field=1.0,
    promotion_ceiling=False,
)


def _blend(
    power_by_season: dict[int, dict[str, float]], source: int, long_memory: float
) -> dict[str, float]:
    """(1 - m) * Power(source) + m * Power(source - 1), over the union of both.

    A team present in only one of the two seasons keeps that season's rating
    rather than being averaged against a zero, which would read as "they were
    league-average the year they did not exist".
    """
    recent = power_by_season.get(int(source), {})
    older = power_by_season.get(int(source) - 1)
    m = float(long_memory)
    if not older or m <= 0.0:
        return dict(recent)
    out: dict[str, float] = {}
    for team in set(recent) | set(older):
        a, b = recent.get(team), older.get(team)
        if a is None:
            out[team] = float(b)
        elif b is None:
            out[team] = float(a)
        else:
            out[team] = (1.0 - m) * float(a) + m * float(b)
    return out


def carried_ratings(
    games: pl.DataFrame,
    target_season: int,
    power_by_season: dict[int, dict[str, float]],
    home_field_by_season: dict[int, float],
    fbs_by_season: dict[int, set[str]],
    levers: ProjectionLevers,
) -> tuple[dict[str, float], crossdivision.DivisionCalibration, dict[str, str]]:
    """What every team's prior rating is worth, on the FBS scale, in August of `target_season`.

    Two steps, both levered, both measured: blend in the season before last, then
    move anything that did not earn its rating against FBS opposition onto the
    FBS scale. The calibration is re-measured from seasons <= target-1 on every
    call, which is what keeps the chain walk-forward.
    """
    source = int(target_season) - 1
    blended = _blend(power_by_season, source, levers.long_memory)

    calibration = crossdivision.measure(
        games,
        power_by_season,
        home_field_by_season,
        fbs_by_season,
        through_season=source,
    )
    adjusted, provenance = crossdivision.adjust_carried_ratings(
        blended,
        source_fbs=fbs_by_season.get(source, set()),
        target_fbs=fbs_by_season.get(int(target_season), set()),
        calibration=calibration,
        gap_weight=levers.cross_division_gap,
        bump_weight=levers.promotion_credit,
        apply_ceiling=bool(levers.promotion_ceiling),
    )
    return adjusted, calibration, provenance


def fit_walk_forward(
    games: pl.DataFrame,
    target_season: int,
    power_by_season: dict[int, dict[str, float]],
    home_field_by_season: dict[int, float],
    fbs_by_season: dict[int, set[str]],
    levers: ProjectionLevers,
    archive_root: Any = None,
) -> tuple[recipe.Recipe | None, list[tuple[int, int]]]:
    """Fit the recipe on every transition whose TARGET season is strictly earlier.

    Returns `(None, [])` when no such transition exists, which is the honest
    answer for 2022 given an archive that starts in 2021: the alternative is to
    fit on the season being scored, and a recipe fitted on the outcomes it claims
    to project is a description.
    """
    target = int(target_season)
    seasons_with_power = sorted(power_by_season)
    transitions = [
        (s, s + 1)
        for s in seasons_with_power
        if s + 1 < target and (s + 1) in power_by_season and (s + 1) in fbs_by_season
    ]
    if not transitions:
        return None, []

    designs: list[pl.DataFrame] = []
    responses: list[np.ndarray] = []
    for _source, dest in transitions:
        prior, _cal, _prov = carried_ratings(
            games, dest, power_by_season, home_field_by_season, fbs_by_season, levers
        )
        teams = sorted(fbs_by_season[dest])
        design = recipe.build_design(prior, dest, teams, archive_root)
        designs.append(design)
        responses.append(
            np.array(
                [float(power_by_season[dest].get(t, 0.0)) for t in design["team"]],
                dtype=np.float64,
            )
        )
    return recipe.fit_recipe(designs, responses, transitions), transitions


def _rated_universe(
    fitted: recipe.Recipe,
    design: pl.DataFrame,
    prior: dict[str, float],
    levers: ProjectionLevers,
) -> dict[str, float]:
    """Projected Power for every team the design covers, plus every other team.

    Teams outside the design are FCS opponents the offseason feeds say nothing
    about. They get the mean-reversion-only projection - the recipe with its
    offseason terms silent - which is what "we know last season and nothing else"
    should produce, and it is the same rule `forward.rating_resolver` applies on
    the published board.
    """
    weights = levers.term_weights
    out = np.full(design.height, float(fitted.intercept), dtype=np.float64)
    for term, column in zip(recipe.TERMS, recipe.DESIGN_COLUMNS, strict=True):
        if term not in fitted.terms:
            continue
        column_values = design[column].fill_null(0.0).to_numpy().astype(np.float64)
        out = out + float(fitted.coefficients[term]) * weights.get(term, 1.0) * column_values
    ratings = dict(zip(design["team"].to_list(), (float(v) for v in out), strict=True))

    center = float(design["prior_power_center"][0]) if design.height else 0.0
    phi = float(fitted.coefficients.get("prior_power", 0.0))
    for team, value in prior.items():
        if team not in ratings:
            ratings[team] = float(fitted.intercept) + phi * (float(value) - center)
    return ratings


def projection_builder(levers: ProjectionLevers, archive_root: Any = None):
    """A chain builder for the recipe under one lever setting."""

    def build(
        *,
        games: pl.DataFrame,
        target_season: int,
        power_by_season: dict[int, dict[str, float]],
        home_field_by_season: dict[int, float],
        fbs_by_season: dict[int, set[str]],
    ) -> tuple[dict[str, float] | None, Any]:
        fitted, transitions = fit_walk_forward(
            games,
            target_season,
            power_by_season,
            home_field_by_season,
            fbs_by_season,
            levers,
            archive_root,
        )
        if fitted is None:
            return None, (
                f"no transition whose target season precedes {target_season}; a recipe "
                "would have to be fitted on the season it is projecting"
            )
        prior, calibration, provenance = carried_ratings(
            games, target_season, power_by_season, home_field_by_season, fbs_by_season, levers
        )
        teams = sorted(fbs_by_season.get(int(target_season), set()))
        design = recipe.build_design(prior, int(target_season), teams, archive_root)
        ratings = _rated_universe(fitted, design, prior, levers)
        promoted = sorted(t for t, p in provenance.items() if p.startswith("promoted"))
        at_ceiling = sorted(t for t, p in provenance.items() if p == "promoted_at_ceiling")
        return ratings, {
            "recipe": fitted.as_dict(),
            "fitted_on_transitions": [list(t) for t in transitions],
            "levers": levers.as_dict(),
            "home_field_scale": float(levers.home_field),
            "cross_division": calibration.as_dict(),
            "promoted_teams": promoted,
            "promoted_teams_at_ceiling": at_ceiling,
        }

    return build


def carryover_builder(
    *,
    games: pl.DataFrame,
    target_season: int,
    power_by_season: dict[int, dict[str, float]],
    home_field_by_season: dict[int, float],
    fbs_by_season: dict[int, set[str]],
) -> tuple[dict[str, float] | None, Any]:
    """Last season's Power, untouched. No fit, no terms, no adjustment."""
    prior = power_by_season.get(int(target_season) - 1)
    if not prior:
        return None, f"no fitted ratings for season {int(target_season) - 1}"
    return dict(prior), {"description": "season Y-1 final Power, carried unchanged"}


def ap_preseason_builder(archive_root: Any = None):
    """The AP August ballot as a rating vector. A baseline, and never an input."""

    def build(
        *,
        games: pl.DataFrame,
        target_season: int,
        power_by_season: dict[int, dict[str, float]],
        home_field_by_season: dict[int, float],
        fbs_by_season: dict[int, set[str]],
    ) -> tuple[dict[str, float] | None, Any]:
        table = offseason.ap_preseason(int(target_season), archive_root)
        if not table.height:
            return None, f"no archived AP preseason poll for {target_season}"
        ratings = {
            team: float(26 - rank)
            for team, rank in zip(
                table["team"].to_list(), table["ap_rank"].to_list(), strict=True
            )
        }
        return ratings, {
            "description": "26 - AP rank for the 25 ranked teams, 0 for everyone else",
            "n_ranked": len(ratings),
        }

    return build


@dataclass(frozen=True)
class SeasonInputs:
    """The three per-season facts every builder reads, gathered once.

    Computing `final_power` is the expensive part of this package - one L3 fit per
    bucket per season - and the chain, the board and the grading loop all want the
    same five seasons of it. Gathering them into one frozen object and passing it
    around is what keeps "the rating the projection carried" and "the rating the
    poll published" the same number rather than two computations of it.
    """

    power: dict[int, dict[str, float]]
    home_field: dict[int, float]
    fbs: dict[int, set[str]]


def prepare(
    games: pl.DataFrame,
    season_list: list[int],
    plays: pl.DataFrame | None = None,
    config: dict[str, Any] | None = None,
) -> SeasonInputs:
    """Final Power, fitted home field and FBS membership for each of `season_list`."""
    from cfbpoll.projection import seasons as season_facts

    power: dict[int, dict[str, float]] = {}
    home_field: dict[int, float] = {}
    fbs: dict[int, set[str]] = {}
    for season in sorted(int(s) for s in season_list):
        source = season_facts.final_power(games, season, plays, config)
        power[season] = dict(source.ratings)
        home_field[season] = float(source.home_field)
        fbs[season] = set(season_facts.fbs_teams(games, season))
    return SeasonInputs(power=power, home_field=home_field, fbs=fbs)


def builders(
    levers: ProjectionLevers | None = None, archive_root: Any = None
) -> dict[str, Any]:
    """The four systems the published chain scores, in the published column order."""
    live = levers if levers is not None else ProjectionLevers()
    return {
        "carryover": carryover_builder,
        "projection_v2": projection_builder(V2_LEVERS, archive_root),
        "projection_v3": projection_builder(live, archive_root),
        "ap_preseason": ap_preseason_builder(archive_root),
    }
