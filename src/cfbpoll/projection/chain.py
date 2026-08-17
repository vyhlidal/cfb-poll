"""Chain the seasons: fit on history, project the next one, score the games it called.

THE QUESTION THIS MODULE EXISTS TO ANSWER, in the owner's words: fit on history,
project each next season, and measure how many of that season's opening games the
projection actually got right - 2022 through 2025, walk-forward, with the old
model beside the new one in the same table.

WHAT WALK-FORWARD MEANS HERE, PRECISELY, because it is the only constraint this
module has and a loose version of it would make every number below a lie:

    for target season Y, a system may read
        game results from seasons <= Y - 1
        the offseason table for season Y      (returning production, portal,
                                               coaching - all knowable in August)
        the FBS membership and calendar of Y  (published years in advance)
    and it may not read
        a single result from season Y or later, including the games being scored.

Every constant a system carries is re-measured at each link from the seasons
behind it. `crossdivision.measure(..., through_season=Y-1)` is called per link
rather than once; the recipe is refitted on the transitions whose TARGET season is
strictly before Y; the home-field constant comes off season Y-1's own L3 fit. A
system that cannot be built that way for a given Y is reported as absent for that
Y rather than quietly given a shortcut - which is why `projection` has no 2022 row
and `carryover` does: with 2021 as the archive's first season there is no
transition to fit a recipe on before 2022, and inventing one would mean fitting on
the season being scored.

WHY STRAIGHT-UP ACCURACY, AND WHY THE HOME-FIELD CONSTANT IS NOT FITTED HERE

Straight-up accuracy - did the team the system favoured actually win - is the
metric because it is invariant to any positive rescaling of a rating, so it
measures the ORDERING and cannot be flattered by a system whose numbers happen to
be on a convenient scale. It has one dependency, and `fit.early_season_metrics`
gets it wrong in a way worth naming here rather than in a commit message: that
function fits `margin ~ a + b*delta + h*site` BY LEAST SQUARES ON THE VERY GAMES
IT THEN SCORES. The slope does not matter - SU is scale-invariant - but the
intercept and the site term do, and fitting them in-sample hands every system a
home-field advantage tuned on the answers. This module takes `h` from season
Y-1's fitted L3 home field instead, which is a number that existed in August, and
the sign rule is the whole predictor:

    pick the home team when   (rating_home - rating_away + h * at_a_venue) > 0

THE UNIVERSES, AND WHY BOTH ARE PUBLISHED

  fbs_vs_fbs   the hard subset, and the honest headline. About 48 games in week 1
               and 200 through week 4. Every other system anyone compares against
               is scored here too.
  all_fbs      every game with an FBS team in it, bridge games included. This is
               what a reader means by "week 1", because half of week 1 is an FBS
               team playing an FCS team, and a model that quietly drops those is
               scoring itself on the half of the slate it finds interesting.

Reporting only the first would hide the cross-division work; reporting only the
second would let a 94%-base-rate subset carry the headline. So both, always, with
their sample sizes attached.

TIES COUNT AS MISSES, NOT HALVES. A system with no opinion did not predict the
game. There are almost none in the data and the rule is stated so that a future
one cannot be quietly rounded in our favour.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

__all__ = [
    "UNIVERSES",
    "ChainLink",
    "ChainResult",
    "SystemBuilder",
    "accuracy",
    "game_frame",
    "run_chain",
    "summarise",
]

#: name -> the class filter applied to a season's games.
UNIVERSES: dict[str, tuple[str, ...]] = {
    "fbs_vs_fbs": ("fbs",),
    "all_fbs": ("fbs", "fcs", "ii", "iii", "unknown"),
}


def game_frame(
    games: pl.DataFrame,
    season: int,
    through_week: int,
    universe: str = "fbs_vs_fbs",
    from_week: int = 1,
) -> pl.DataFrame:
    """Completed regular-season games of `season` in `[from_week, through_week]`.

    `all_fbs` requires AT LEAST ONE side to be FBS; `fbs_vs_fbs` requires both.
    Postseason is excluded throughout - this module is about the start of a
    season, and a bowl game is neither week 1 nor early.
    """
    allowed = UNIVERSES[universe]
    frame = games.filter(
        (pl.col("season") == int(season))
        & (pl.col("season_type") == "regular")
        & (pl.col("week") >= int(from_week))
        & (pl.col("week") <= int(through_week))
        & pl.col("completed")
        & pl.col("home_points").is_not_null()
        & pl.col("away_points").is_not_null()
    )
    if universe == "fbs_vs_fbs":
        return frame.filter((pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs"))
    return frame.filter(
        ((pl.col("home_class") == "fbs") | (pl.col("away_class") == "fbs"))
        & pl.col("home_class").is_in(list(allowed))
        & pl.col("away_class").is_in(list(allowed))
    )


def accuracy(
    ratings: dict[str, float],
    frame: pl.DataFrame,
    home_field: float,
) -> dict[str, Any]:
    """Straight-up accuracy of one rating vector over one frame. No fitting.

    A team the system never rated sits at 0.0, which is the fit universe's
    league-average prior and is what `PowerSource.rating` already returns for an
    unseen team. `n_unrated_sides` counts how often that happened, because an
    accuracy figure propped up by a hundred default ratings is not the same
    number as one where every team was known.
    """
    if frame.is_empty():
        return {
            "n_games": 0,
            "su_accuracy": None,
            "n_correct": 0,
            "n_ties": 0,
            "n_unrated_sides": 0,
            "mean_abs_error": None,
        }
    correct = 0
    scored = 0
    ties = 0
    unrated = 0
    errors: list[float] = []
    for row in frame.iter_rows(named=True):
        home, away = row["home_team"], row["away_team"]
        unrated += int(home not in ratings) + int(away not in ratings)
        delta = float(ratings.get(home, 0.0)) - float(ratings.get(away, 0.0))
        if not row["neutral_site"]:
            delta += float(home_field)
        actual = float(row["home_points"] - row["away_points"])
        if actual == 0.0:
            # A tie is not scored and is not averaged either: `su_accuracy` and
            # `mean_abs_error` are published on the same row and must rest on the
            # same sample, or the row is two different measurements wearing one
            # sample size.
            ties += 1
            continue
        errors.append(abs(actual - delta))
        scored += 1
        correct += int(np.sign(delta) == np.sign(actual))
    return {
        "n_games": int(scored),
        "su_accuracy": (correct / scored) if scored else None,
        "n_correct": int(correct),
        "n_ties": int(ties),
        "n_unrated_sides": int(unrated),
        "mean_abs_error": float(np.mean(errors)) if errors else None,
    }


@dataclass(frozen=True)
class ChainLink:
    """One target season's worth of the chain: what each system said, and how it did."""

    target_season: int
    home_field: float
    home_field_source: str
    #: system -> universe -> window -> metrics
    scores: dict[str, dict[str, dict[str, Any]]]
    #: system -> whatever the builder wanted on the record (fitted coefficients,
    #: the transitions it used, the cross-division constants it carried).
    provenance: dict[str, Any] = field(default_factory=dict)
    absent: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_season": self.target_season,
            "home_field": round(float(self.home_field), 4),
            "home_field_source": self.home_field_source,
            "scores": self.scores,
            "provenance": self.provenance,
            "absent": self.absent,
        }


@dataclass(frozen=True)
class ChainResult:
    """The whole chain, plus the pooled table that is the headline."""

    links: tuple[ChainLink, ...]
    windows: dict[str, tuple[int, int]]
    systems: tuple[str, ...]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "protocol": (
                "Walk-forward. For target season Y every system reads results from "
                "seasons <= Y-1, the offseason table for Y and the calendar of Y, and "
                "nothing from Y itself. Straight-up accuracy, with the home-field "
                "constant taken from season Y-1's fitted L3 home field rather than "
                "fitted on the games being scored. Ties count as misses."
            ),
            "windows": {k: list(v) for k, v in self.windows.items()},
            "systems": list(self.systems),
            "links": [link.as_dict() for link in self.links],
            "summary": self.summary,
        }


#: A builder receives everything a system may legally see for one link and returns
#: `(ratings, provenance)`, or `(None, reason)` when it cannot be built honestly
#: for that target season.
SystemBuilder = Callable[..., tuple[dict[str, float] | None, Any]]


def run_chain(
    games: pl.DataFrame,
    target_seasons: Sequence[int],
    builders: dict[str, SystemBuilder],
    power_by_season: dict[int, dict[str, float]],
    home_field_by_season: dict[int, float],
    fbs_by_season: dict[int, set[str]],
    windows: dict[str, tuple[int, int]] | None = None,
    universes: Sequence[str] = ("fbs_vs_fbs", "all_fbs"),
) -> ChainResult:
    """Score every builder over every target season, in every window and universe.

    `builders` is an ordered mapping so the published table's column order is the
    caller's and not a dictionary's. Each builder is called with keyword
    arguments only, so adding a new fact a system may read does not silently
    reorder anybody's positional signature.
    """
    win = dict(windows) if windows else {"week_1": (1, 1), "weeks_1_4": (1, 4)}
    links: list[ChainLink] = []

    for target in [int(s) for s in target_seasons]:
        prior = target - 1
        home_field = float(home_field_by_season.get(prior, 0.0))
        frames = {
            (universe, name): game_frame(games, target, hi, universe, from_week=lo)
            for universe in universes
            for name, (lo, hi) in win.items()
        }
        scores: dict[str, dict[str, dict[str, Any]]] = {}
        provenance: dict[str, Any] = {}
        absent: dict[str, str] = {}

        for system, builder in builders.items():
            ratings, note = builder(
                games=games,
                target_season=target,
                power_by_season=power_by_season,
                home_field_by_season=home_field_by_season,
                fbs_by_season=fbs_by_season,
            )
            if ratings is None:
                absent[system] = str(note)
                continue
            provenance[system] = note
            # A system may scale the home-field constant it is scored with, which
            # is the `projection.home_field` lever. It never gets to choose the
            # constant itself - that comes off season Y-1's fit - so the most a
            # lever can do is say how much of it to believe.
            scale = 1.0
            if isinstance(note, dict):
                scale = float(note.get("home_field_scale", 1.0))
            system_h = home_field * scale
            scores[system] = {
                universe: {
                    name: accuracy(ratings, frames[(universe, name)], system_h)
                    for name in win
                }
                for universe in universes
            }
        links.append(
            ChainLink(
                target_season=target,
                home_field=home_field,
                home_field_source=f"season {prior} fitted L3 home field",
                scores=scores,
                provenance=provenance,
                absent=absent,
            )
        )

    return ChainResult(
        links=tuple(links),
        windows=win,
        systems=tuple(builders),
        summary=summarise(links, tuple(builders), win, universes),
    )


def summarise(
    links: Sequence[ChainLink],
    systems: Sequence[str],
    windows: dict[str, tuple[int, int]],
    universes: Sequence[str],
) -> dict[str, Any]:
    """Pooled accuracy per system, weighted by games rather than by season.

    Game-weighted, not season-weighted: a 39-game week 1 and a 53-game week 1 are
    different amounts of evidence, and averaging the two percentages would treat
    them as equal. `seasons_covered` rides along so a system that skipped a season
    cannot be compared with one that did not without the reader noticing.
    """
    out: dict[str, Any] = {}
    for universe in universes:
        block: dict[str, Any] = {}
        for system in systems:
            per_window: dict[str, Any] = {}
            for name in windows:
                correct = 0
                total = 0
                covered: list[int] = []
                errors: list[tuple[float, int]] = []
                for link in links:
                    cell = link.scores.get(system, {}).get(universe, {}).get(name)
                    if not cell or not cell["n_games"]:
                        continue
                    correct += int(cell["n_correct"])
                    total += int(cell["n_games"])
                    covered.append(link.target_season)
                    if cell["mean_abs_error"] is not None:
                        errors.append((float(cell["mean_abs_error"]), int(cell["n_games"])))
                if not total:
                    continue
                mae = (
                    sum(v * n for v, n in errors) / sum(n for _, n in errors) if errors else None
                )
                per_window[name] = {
                    "su_accuracy": correct / total,
                    "n_correct": correct,
                    "n_games": total,
                    "mean_abs_error": mae,
                    "seasons_covered": covered,
                }
            if per_window:
                block[system] = per_window
        out[universe] = block
    return out
