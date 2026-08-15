"""Projecting a season nobody has played yet, and putting a win total on it.

Everything else in this package works on seasons with results in them. This is
the part that runs in August, and the two things it has to do that no backtest
needs are: read a schedule of games that have not happened, and turn a projected
Power rating into a number a reader actually wants ("how many do they win?").

READING A FUTURE SCHEDULE. CFBD's `/games?year=2026` serves 888 rows with
`completed: false` and null scores. That body also ships `homePregameElo`,
`excitementIndex` and a postgame win probability - a third party's fitted models
sitting in the same file as the calendar, which is report 01 §5.6's trap in its
purest form. `schedule` below projects six columns and nothing else, so those
never enter a frame this package holds, let alone one it computes from.

THE UNCERTAINTY IS THE HONEST PART, and it is why the win totals look timid. A
game's margin is

    margin = (Power_home - Power_away) + h + game noise

and in-season the poll knows the Power ratings. In August it does not: it has a
PROJECTION of them, whose own residual SD is `recipe.residual_sd` - about nine
points on the fits published here. Both teams carry that error independently, so

    sd(margin | projection) = sqrt( sigma_game^2 + 2 * residual_sd^2 )

which is roughly 21 points against the ~16.5 the in-season poll works with. That
is a 27% wider distribution, it pushes every win probability toward a coin flip,
and it is not a defect being confessed - it is the correct statement of how much
less anyone knows in August, and a projection that produced confident win totals
would be lying about exactly that. `WinProjection.sigma_note` carries the
arithmetic onto the artifact so the number never travels without it.

TEAMS THE RECIPE CANNOT SEE. An FBS team's 2026 opponents include FCS teams, and
CFBD publishes no returning production, portal or coaching row for those. They
get the MEAN-REVERSION-ONLY projection - intercept plus phi times their centred
2025 rating - which is the recipe with its offseason terms silent, because that
is what "we know last season and nothing else" should produce. Flagged per game
in `opponent_source` rather than blended in quietly.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from cfbpoll.ingest import cfbd
from cfbpoll.projection import recipe

__all__ = [
    "SCHEDULE_COLUMNS",
    "WinProjection",
    "expected_wins",
    "normal_cdf",
    "rating_resolver",
    "projection_sigma",
    "schedule",
    "season_sigma_for",
]

#: The only six things this package reads off a future schedule. Everything else
#: in that body - Elo, excitement index, win probability - is a third party's
#: model, and the cheapest way to prove it never reached us is to never load it.
SCHEDULE_COLUMNS: tuple[str, ...] = (
    "game_id",
    "week",
    "neutral_site",
    "home_team",
    "away_team",
    "home_class",
    "away_class",
)


def schedule(
    season: int, archive_root: str | Path | None = None, season_type: str = "regular"
) -> pl.DataFrame:
    """The archived future schedule, projected to `SCHEDULE_COLUMNS`. Offline.

    Empty frame when the pull is not in the archive, which is the correct answer
    for a fork with no key: a projection without win totals is a smaller product,
    not a broken one.
    """
    bodies = cfbd.archived_bodies(
        "/games",
        f"{season}/season",
        archive_root,
        params={"year": season, "seasonType": season_type, "classification": "fbs"},
    )
    empty = pl.DataFrame(
        schema={
            "game_id": pl.Int64,
            "week": pl.Int32,
            "neutral_site": pl.Boolean,
            "home_team": pl.String,
            "away_team": pl.String,
            "home_class": pl.String,
            "away_class": pl.String,
        }
    )
    if not bodies:
        return empty
    payload = json.loads(bodies[-1].read_text(encoding="utf-8"))
    rows = [
        {
            "game_id": int(g.get("id", 0)),
            "week": int(g.get("week", 0)),
            "neutral_site": bool(g.get("neutralSite", False)),
            "home_team": str(g.get("homeTeam") or ""),
            "away_team": str(g.get("awayTeam") or ""),
            "home_class": str(g.get("homeClassification") or "unknown"),
            "away_class": str(g.get("awayClassification") or "unknown"),
        }
        for g in (payload if isinstance(payload, list) else [])
        if g.get("homeTeam") and g.get("awayTeam")
    ]
    if not rows:
        return empty
    return pl.DataFrame(rows).sort("game_id").select(SCHEDULE_COLUMNS)


#: `l3_power.SigmaEstimate.source` in words a reader of the front door can use.
#: The projection publishes `sigma_note` verbatim on the card, so a bare
#: `config_floor` would arrive on the page as a variable name.
_SIGMA_PROSE: dict[str, str] = {
    "walk_forward_residuals": (
        "this system's own walk-forward residuals over the source season"
    ),
    "config_floor": (
        "[resume].sigma, the documented floor, which the source season's own "
        "walk-forward estimate came in under"
    ),
    "config": "[resume].sigma, the documented fallback and floor",
}


def season_sigma_for(source: Any, config: dict[str, Any]) -> tuple[float, str]:
    """(sigma, a sentence fragment saying where it came from) for a source season.

    Wraps `l4_resume.sigma_for` so the projection's denominator is decided in the
    same one place the poll's is, and translates its provenance token into
    something the card can print. Both scripts call this rather than each
    assembling the phrase, because two copies of a caveat is two chances for one
    of them to stop being true.
    """
    from cfbpoll.model import l4_resume

    value, token = l4_resume.sigma_for(source, config)
    return float(value), _SIGMA_PROSE.get(token, token)


def projection_sigma(fitted: recipe.Recipe, season_sigma: float) -> float:
    """sd of a game margin GIVEN a projection, not given a fitted rating.

    sqrt(sigma_game^2 + 2 * residual_sd^2). Both teams' projections carry the
    recipe's own residual error and they are independent draws, hence the 2.
    """
    return float(math.sqrt(season_sigma**2 + 2.0 * float(fitted.residual_sd) ** 2))


@dataclass(frozen=True)
class WinProjection:
    """Expected wins per team, and every constant that produced them."""

    table: pl.DataFrame
    sigma: float
    season_sigma: float
    residual_sd: float
    home_field: float
    n_games: int
    sigma_note: str
    #: Where `season_sigma` came from. A full-season one-shot Power fit does not
    #: run the walk-forward sigma estimator - that is a property of the weekly
    #: walk, not of a season - so this is normally the config's 15.3, which
    #: `[resume].sigma` documents as the fallback and the floor. Published
    #: because an unstated provenance on a number this load-bearing is a small
    #: lie about how much is known.
    season_sigma_source: str = "unstated"

    def as_dict(self) -> dict[str, Any]:
        return {
            "sigma": self.sigma,
            "season_sigma": self.season_sigma,
            "season_sigma_source": self.season_sigma_source,
            "recipe_residual_sd": self.residual_sd,
            "home_field_points": self.home_field,
            "n_games": self.n_games,
            "sigma_note": self.sigma_note,
        }


def normal_cdf(x: float) -> float:
    """Phi. Public because the schedule-strength module scores the same games."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


#: Backwards-compatible private alias. `expected_wins` was written against it and
#: renaming a function is not worth touching the arithmetic it is embedded in.
_normal_cdf = normal_cdf


def rating_resolver(
    projection: pl.DataFrame,
    fitted: recipe.Recipe,
    prior_power: dict[str, float],
    prior_center: float,
) -> Callable[[str], tuple[float, str]]:
    """team -> (projected rating, provenance). ONE definition, two consumers.

    `expected_wins` and `schedule.strengths` both have to answer "how good do we
    think this opponent is", and the answer has two cases: a team the recipe
    could see, and a team it could not. Two copies of that rule would be two
    chances for a schedule-strength number to disagree with the win total sitting
    beside it on the same row, which is exactly the kind of self-contradiction
    the fixture contract exists to prevent.

    The provenance string is returned rather than swallowed because it is what
    `opponent_source` and the row-level `schedule_is_mixed` flag are built from:
    an FCS opponent has no returning-production, portal or coaching row anywhere,
    so it gets the MEAN-REVERSION-ONLY projection - the recipe with its offseason
    terms silent, which is what "we know last season and nothing else" should
    produce - and any average that mixes the two kinds has to say so.
    """
    projected = dict(
        zip(projection["team"].to_list(), projection["projected_power"].to_list(), strict=True)
    )
    intercept = float(fitted.intercept)
    phi = float(fitted.coefficients["prior_power"])

    def rating(team: str) -> tuple[float, str]:
        if team in projected:
            return float(projected[team]), "projection"
        base = float(prior_power.get(team, 0.0)) - prior_center
        return (intercept + phi * base, "mean_reversion_only")

    return rating


def expected_wins(
    projection: pl.DataFrame,
    future: pl.DataFrame,
    fitted: recipe.Recipe,
    prior_power: dict[str, float],
    prior_center: float,
    season_sigma: float,
    home_field: float,
    season_sigma_source: str = "unstated",
) -> WinProjection:
    """Sum of win probabilities over each team's schedule. One row per FBS team.

    Independence across a team's own games is assumed, which is the same
    assumption `model/schedule_odds.py` makes for the poll's headline key and is
    documented there: a team's games share the team, so the assumption is about
    the residuals and not about the opponents. It is what makes an exact answer
    available at all, and the projection's uncertainty dwarfs the correction it
    would buy.
    """
    rating = rating_resolver(projection, fitted, prior_power, prior_center)
    sigma = projection_sigma(fitted, season_sigma)
    wins: dict[str, float] = {}
    games: dict[str, int] = {}
    sources: dict[str, set[str]] = {}

    for row in future.iter_rows(named=True):
        home, away = row["home_team"], row["away_team"]
        r_home, src_home = rating(home)
        r_away, src_away = rating(away)
        site = 0.0 if row["neutral_site"] else float(home_field)
        p_home = _normal_cdf((r_home - r_away + site) / sigma)
        for team, probability, other_source in (
            (home, p_home, src_away),
            (away, 1.0 - p_home, src_home),
        ):
            wins[team] = wins.get(team, 0.0) + probability
            games[team] = games.get(team, 0) + 1
            sources.setdefault(team, set()).add(other_source)

    teams = sorted(wins)
    table = pl.DataFrame(
        {
            "team": teams,
            "projected_wins": [wins[t] for t in teams],
            "scheduled_games": pl.Series([games[t] for t in teams], dtype=pl.Int32),
            "projected_losses": [games[t] - wins[t] for t in teams],
            "opponent_source": [
                "projection" if sources[t] == {"projection"} else "mixed" for t in teams
            ],
        }
    ).sort("team")

    return WinProjection(
        table=table,
        sigma=sigma,
        season_sigma=float(season_sigma),
        residual_sd=float(fitted.residual_sd),
        home_field=float(home_field),
        n_games=int(future.height),
        season_sigma_source=str(season_sigma_source),
        sigma_note=(
            f"sd(margin | projection) = sqrt({season_sigma:.2f}^2 + 2 * "
            f"{fitted.residual_sd:.2f}^2) = {sigma:.2f} points, with the first "
            f"term from {season_sigma_source}. The second term "
            "is the recipe's own residual error, carried by both teams "
            "independently. In-season the poll works with the first term alone; "
            "in August it does not have that luxury, and every win probability "
            "here is correspondingly closer to a coin flip."
        ),
    )
