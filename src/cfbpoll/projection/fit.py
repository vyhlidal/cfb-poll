"""Fitting the recipe, and the backtest whose headline question is the honest one.

    Did our August guess beat the sportswriters' August guess?

Four systems are scored, all against the same target and all through the same
code, because a comparison where the favourite gets its own function is not a
comparison:

  projection        the four-term recipe
  regress_only      the SAME recipe with only the prior-Power term. This is the
                    control that matters: if it ties the full recipe, then
                    returning production, coaching and the portal bought us
                    nothing and the honest thing is to say so in the artifact.
  naive_carryover   last season's final Power, unchanged. phi = 1, no terms, no
                    intercept, no fitting of any kind. The floor.
  ap_preseason      the AP writers' preseason top 25. The BASELINE, and never an
                    input to anything - `PROJECTION_BANNED` in the leakage audit
                    is what makes that mechanical rather than promised.

OUT OF SAMPLE, BY LEAVE-ONE-TRANSITION-OUT. The recipe has four coefficients and
three transitions, so scoring it on the transitions it was fitted on would be
reporting its own training error and calling it a result. Every number in the
`out_of_sample` block comes from a recipe fitted on the OTHER two transitions and
applied to the held-out one. The pooled in-sample fit is reported beside it, and
the gap between them is published rather than hidden, because on three seasons
that gap is the most informative number in the table.

THE THREE COMPARISONS, AND WHY EACH IS SHAPED THE WAY IT IS. The AP poll ranks 25
teams and is silent about the other 109, and every fair-comparison decision below
follows from taking that seriously rather than papering over it:

  top25_overlap            |system's top 25 AND the settled top 25|. Treatment-
                           free. No convention, no censoring, no charity in
                           either direction - both systems name 25 teams and we
                           count how many they got. This is the headline.

  mae_rank_top25_censored  over the teams that FINISHED top 25: mean |projected
                           rank - settled rank|, with EVERY system's rank
                           censored at 26. Identical censoring for all four, so
                           each is answering the AP's own question: "where did
                           you put this team, treating 'outside my top 25' as one
                           bucket". Uncensored, a full-rating system that buries
                           a team at 80 pays 75 while the AP's worst possible
                           error is 21, which would measure the shape of the
                           output rather than the quality of the guess.

  spearman_full            rank correlation over all FBS teams. Full-information
                           systems only; the AP is reported as null rather than
                           padded out to 134 teams with a convention that would
                           be inventing opinions it never expressed.

AND THE SECOND QUESTION, game prediction over the target season's first four
weeks. SU accuracy is the honest one there because it is invariant to any
positive affine map of the ratings, so it measures the ORDERING and nothing else.
MAE needs a scale, every system gets one from the same in-sample affine fit on
exactly those games, and that in-sample-ness is stated on the number rather than
buried: it is a fair comparison between systems and it is not an out-of-sample
error estimate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.projection import PROJECTION_VERSION, holdout, offseason, recipe, seasons

__all__ = [
    "AP_UNRANKED_RATING",
    "CENSOR_AT",
    "SYSTEMS",
    "TransitionData",
    "gather",
    "leave_one_out",
    "rank_metrics",
    "run",
    "early_season_metrics",
]

#: Where every system's rank is truncated for the fair comparison. 26 = "outside
#: a top 25", which is the finest distinction the AP poll is capable of making.
CENSOR_AT = 26

#: The pseudo-rating an AP-unranked team gets when the AP is used as a GAME
#: predictor. 26 - rank puts the AP #1 at 25 and the AP #25 at 1, and everyone
#: else at 0 - a flat "no opinion" tier of 109 teams. It is a crude rating and it
#: is crude because the source is: the AP does not publish a rating.
AP_UNRANKED_RATING = 0.0

SYSTEMS: tuple[str, ...] = ("projection", "regress_only", "naive_carryover", "ap_preseason")


@dataclass
class TransitionData:
    """One (source -> target) transition, with everything both halves need."""

    source_season: int
    target_season: int
    design: pl.DataFrame
    teams: tuple[str, ...]
    response: np.ndarray
    prior_power: dict[str, float]
    settled: pl.DataFrame
    ap: pl.DataFrame
    coverage: dict[str, Any]


def gather(
    games: pl.DataFrame,
    source_season: int,
    target_season: int,
    plays: pl.DataFrame | None = None,
    config: dict[str, Any] | None = None,
    archive_root: Any = None,
    with_response: bool = True,
) -> TransitionData:
    """Assemble one transition. `with_response=False` for a season not yet played.

    The 2026 application takes `with_response=False`: there is no target season
    to score against, which is the entire point of a preseason projection, and a
    zero-length response is what the type system should see rather than a
    fabricated one.
    """
    cfg = config if config is not None else load_config()
    prior = seasons.final_power(games, source_season, plays, cfg)
    teams = seasons.fbs_teams(games, target_season) if with_response else []
    if not with_response:
        raise ValueError("gather requires a played target season; use `project_forward`")

    design = recipe.build_design(prior.ratings, target_season, teams, archive_root)
    target_power = seasons.final_power(games, target_season, plays, cfg)
    response = np.array([target_power.rating(t) for t in design["team"]], dtype=np.float64)
    return TransitionData(
        source_season=int(source_season),
        target_season=int(target_season),
        design=design,
        teams=tuple(teams),
        response=response,
        prior_power=dict(prior.ratings),
        settled=seasons.settled_poll(games, target_season, plays, cfg),
        ap=offseason.ap_preseason(target_season, archive_root),
        coverage=offseason.coverage(
            target_season,
            teams,
            archive_root,
            prior_teams=seasons.fbs_teams(games, source_season),
        ),
    )


# ------------------------------------------------------------------- the rankings


def _settled_ranks(settled: pl.DataFrame) -> dict[str, int]:
    ranked = settled.filter(pl.col("rank").is_not_null())
    return dict(zip(ranked["team"].to_list(), ranked["rank"].to_list(), strict=True))


def _ranks_from_rating(ratings: dict[str, float], teams: list[str]) -> dict[str, int]:
    """Descending by rating, ties broken on team name. Deterministic by construction."""
    order = sorted(teams, key=lambda t: (-float(ratings.get(t, 0.0)), t))
    return {team: i + 1 for i, team in enumerate(order)}


def system_ranks(
    data: TransitionData,
    fitted: recipe.Recipe | None,
    regress: recipe.Recipe | None,
) -> dict[str, dict[str, int]]:
    """Every system's projected ranking of `data.teams`, as team -> rank.

    The AP's dictionary holds ONLY its 25 teams. A missing key means "this system
    expressed no opinion", which every metric below handles explicitly rather
    than by defaulting it to a number that looks like an opinion.
    """
    teams = list(data.teams)
    out: dict[str, dict[str, int]] = {}
    if fitted is not None:
        predicted = fitted.predict(data.design)
        out["projection"] = _ranks_from_rating(
            dict(zip(data.design["team"].to_list(), predicted, strict=True)), teams
        )
    if regress is not None:
        predicted = regress.predict(data.design)
        out["regress_only"] = _ranks_from_rating(
            dict(zip(data.design["team"].to_list(), predicted, strict=True)), teams
        )
    out["naive_carryover"] = _ranks_from_rating(data.prior_power, teams)
    out["ap_preseason"] = dict(
        zip(data.ap["team"].to_list(), data.ap["ap_rank"].to_list(), strict=True)
    ) if data.ap.height else {}
    return out


def rank_metrics(
    ranks: dict[str, int],
    settled: dict[str, int],
    full_information: bool,
    top_n: int = 25,
) -> dict[str, Any]:
    """Score one system's projected ranking against the settled one.

    `full_information` says whether this system ranked every team. A system that
    did not gets `spearman_full` = None instead of a number computed under a
    convention it never agreed to.
    """
    settled_top = {t for t, r in settled.items() if r <= top_n}
    system_top = {t for t, r in ranks.items() if r <= top_n}

    censored_errors = [
        abs(min(ranks.get(team, CENSOR_AT), CENSOR_AT) - min(settled[team], CENSOR_AT))
        for team in sorted(settled_top)
    ]
    out: dict[str, Any] = {
        "top25_overlap": len(system_top & settled_top),
        "top25_overlap_rate": (len(system_top & settled_top) / len(settled_top))
        if settled_top
        else None,
        "mae_rank_top25_censored": float(np.mean(censored_errors)) if censored_errors else None,
        "n_ranked": len(ranks),
    }
    if not full_information:
        out["mae_rank_top25_uncensored"] = None
        out["spearman_full"] = None
        return out

    uncensored = [abs(ranks[team] - settled[team]) for team in sorted(settled_top) if team in ranks]
    out["mae_rank_top25_uncensored"] = float(np.mean(uncensored)) if uncensored else None
    shared = sorted(set(ranks) & set(settled))
    if len(shared) > 2:
        a = np.array([ranks[t] for t in shared], dtype=np.float64)
        b = np.array([settled[t] for t in shared], dtype=np.float64)
        out["spearman_full"] = float(np.corrcoef(a, b)[0, 1])
        out["n_teams_compared"] = len(shared)
    else:
        out["spearman_full"] = None
    return out


# ------------------------------------------------------ the second question: games


def _affine_predictions(
    ratings: dict[str, float], frame: pl.DataFrame
) -> tuple[np.ndarray, np.ndarray]:
    """Predicted and actual margin, with ONE in-sample affine map per system.

    `margin ~ a + b*(r_home - r_away) + h*site`, least squares, minimum norm on a
    degenerate design - the same construction `walkforward._fit_affine` uses, and
    the same reason: without it a rating on the AP's 0-25 scale and a rating in
    points cannot both be scored on MAE.
    """
    delta = np.array(
        [
            float(ratings.get(h, 0.0)) - float(ratings.get(a, 0.0))
            for h, a in zip(frame["home_team"].to_list(), frame["away_team"].to_list(), strict=True)
        ],
        dtype=np.float64,
    )
    site = np.where(frame["neutral_site"].to_numpy().astype(bool), 0.0, 1.0)
    margin = (frame["home_points"] - frame["away_points"]).to_numpy().astype(np.float64)
    if margin.size == 0:
        return delta, margin
    x = np.column_stack([np.ones_like(delta), delta, site])
    coef, *_ = np.linalg.lstsq(x, margin, rcond=None)
    return x @ coef, margin


def early_season_metrics(
    games: pl.DataFrame,
    target_season: int,
    ratings: dict[str, float],
    through_week: int = 4,
) -> dict[str, Any]:
    """SU accuracy and MAE over the target season's first `through_week` weeks.

    FBS-vs-FBS regular season only, which is the backtest's primary universe
    (report 02 §5.1) and keeps this table comparable with everything else the
    project publishes. Ties in the rating differential count as a miss rather
    than a half, because a system with no opinion did not predict the game.
    """
    frame = windows.games_through(
        games, season=int(target_season), week=int(through_week), season_type="regular"
    ).filter((pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs"))
    if frame.is_empty():
        return {"n_games": 0, "su_accuracy": None, "mae": None}

    predicted, actual = _affine_predictions(ratings, frame)
    correct = np.sum(np.sign(predicted) == np.sign(actual)) / actual.size
    return {
        "n_games": int(actual.size),
        "su_accuracy": float(correct),
        "mae": float(np.mean(np.abs(predicted - actual))),
        "calibration": "in-sample affine map on exactly these games, identical for every system",
    }


def _system_ratings(
    data: TransitionData, fitted: recipe.Recipe | None, regress: recipe.Recipe | None
) -> dict[str, dict[str, float]]:
    """Each system as a RATING vector, for the game-prediction half."""
    out: dict[str, dict[str, float]] = {}
    if fitted is not None:
        out["projection"] = dict(
            zip(data.design["team"].to_list(), fitted.predict(data.design), strict=True)
        )
    if regress is not None:
        out["regress_only"] = dict(
            zip(data.design["team"].to_list(), regress.predict(data.design), strict=True)
        )
    out["naive_carryover"] = dict(data.prior_power)
    out["ap_preseason"] = {
        team: float(CENSOR_AT - rank)
        for team, rank in zip(data.ap["team"].to_list(), data.ap["ap_rank"].to_list(), strict=True)
    } if data.ap.height else {}
    return out


# ------------------------------------------------------------------ the whole run


def leave_one_out(
    transitions: list[TransitionData], terms: tuple[str, ...] = recipe.TERMS
) -> dict[int, recipe.Recipe]:
    """target season -> a recipe fitted on every OTHER transition. The honest fit.

    With three transitions each fold trains on two, which is thin and is meant to
    look thin: the published coefficient table is the pooled fit, and this exists
    so the backtest cannot quote a training error as a result.
    """
    out: dict[int, recipe.Recipe] = {}
    for held in transitions:
        others = [t for t in transitions if t.target_season != held.target_season]
        if not others:
            continue
        out[held.target_season] = recipe.fit_recipe(
            [t.design for t in others],
            [t.response for t in others],
            [(t.source_season, t.target_season) for t in others],
            terms=terms,
        )
    return out


def run(
    games: pl.DataFrame,
    transitions: list[tuple[int, int]],
    plays: pl.DataFrame | None = None,
    config: dict[str, Any] | None = None,
    archive_root: Any = None,
) -> dict[str, Any]:
    """Fit the recipe on `transitions`, score every system, and report all of it.

    Refuses to fit on a locked season before it does anything else, because a
    guard that runs after the expensive part is a guard that gets moved.
    """
    cfg = config if config is not None else load_config()
    holdout.assert_no_target_is_locked(transitions, cfg)

    data = [
        gather(games, source, target, plays, cfg, archive_root)
        for source, target in transitions
    ]
    pooled = recipe.fit_recipe(
        [t.design for t in data],
        [t.response for t in data],
        [(t.source_season, t.target_season) for t in data],
    )
    pooled_regress = recipe.fit_recipe(
        [t.design for t in data],
        [t.response for t in data],
        [(t.source_season, t.target_season) for t in data],
        terms=("prior_power",),
    )
    loo = leave_one_out(data)
    loo_regress = leave_one_out(data, terms=("prior_power",))

    per_season: list[dict[str, Any]] = []
    for item in data:
        settled = _settled_ranks(item.settled)
        held = loo.get(item.target_season)
        held_regress = loo_regress.get(item.target_season)
        ranks_oos = system_ranks(item, held, held_regress)
        ranks_ins = system_ranks(item, pooled, pooled_regress)
        ratings_oos = _system_ratings(item, held, held_regress)

        block: dict[str, Any] = {
            "source_season": item.source_season,
            "target_season": item.target_season,
            "n_teams": len(item.teams),
            "coverage": item.coverage,
            "settled_definition": seasons.SETTLED_DEFINITION,
            "out_of_sample": {},
            "in_sample": {},
            "early_season": {},
        }
        for system in SYSTEMS:
            full = system != "ap_preseason"
            if system in ranks_oos:
                block["out_of_sample"][system] = rank_metrics(ranks_oos[system], settled, full)
            if system in ranks_ins:
                block["in_sample"][system] = rank_metrics(ranks_ins[system], settled, full)
            if system in ratings_oos and ratings_oos[system]:
                block["early_season"][system] = early_season_metrics(
                    games, item.target_season, ratings_oos[system]
                )
        per_season.append(block)

    return {
        "projection_version": PROJECTION_VERSION,
        "settled_definition": seasons.SETTLED_DEFINITION,
        "transitions": [[t.source_season, t.target_season] for t in data],
        "recipe_pooled": pooled.as_dict(),
        "recipe_regress_only": pooled_regress.as_dict(),
        "leave_one_out_recipes": {
            str(season): fit.as_dict() for season, fit in sorted(loo.items())
        },
        "per_season": per_season,
        "summary": _summarise(per_season),
    }


def _summarise(per_season: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean of each metric across transitions, per system. The verdict, unspun."""
    out: dict[str, Any] = {}
    for block_name in ("out_of_sample", "in_sample", "early_season"):
        section: dict[str, Any] = {}
        for system in SYSTEMS:
            values: dict[str, list[float]] = {}
            for season in per_season:
                metrics = season[block_name].get(system)
                if not metrics:
                    continue
                for key, value in metrics.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        values.setdefault(key, []).append(float(value))
            if values:
                section[system] = {k: float(np.mean(v)) for k, v in sorted(values.items())}
        out[block_name] = section
    return out
