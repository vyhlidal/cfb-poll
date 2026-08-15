"""Schedule strength, and the number that makes the board's ordering self-evident.

THE PROBLEM THIS EXISTS FOR, in the owner's own test case: the 2026 projection
ranks Ohio State first on 9.1 projected wins and Texas Tech seventh on 10.0. A
reader who sees a board sorted one way and a win column that disagrees with it
concludes the board is broken, and they are right to, because nothing on the page
reconciles the two. The reconciling quantity is schedule difficulty, and until
now it was computed inside `forward.expected_wins` and thrown away.

THREE QUANTITIES, AND THEY DO DIFFERENT JOBS. Publishing all three is not
belt-and-braces; each one fails at what the next one does.

  schedule_strength         mean opponent projected power over a team's games.
                            Lets a reader LOOK UP that Ohio State's schedule is
                            hard. It does not tell them what that is worth in
                            wins, which is the unit the column beside it is in.

  wins_on_median_schedule   this team's rating run against ONE schedule that
                            every team is scored on. THE LOAD-BEARING FIELD.
                            It does the reader's second step for them: the
                            column is directly comparable down the table, so
                            "Ohio State above Texas Tech" stops needing an
                            explanation the moment you can see Ohio State wins
                            more games than Texas Tech does against the same
                            opposition.

  the pairwise swap         "Ohio State would win 10.6 on Texas Tech's schedule;
                            Texas Tech would win 8.2 on Ohio State's." The most
                            vivid of the three and the only one that does not
                            scale: it is O(n^2) and it needs two named teams, so
                            it is the GLOSS device for one sentence and never a
                            column. `contrast` builds exactly one of them.

NEUTRAL FIELD, AND VENUE PUBLISHED SEPARATELY. `schedule_strength` is the mean
opponent rating with no home-field term in it at all, because a single number
that silently blends "who you play" with "where you play them" cannot be checked
by a reader against either. Home-field is 3.95 points and a team hosts six or
seven games, so this is a material choice rather than a rounding one - which is
why `home_games` ships beside it instead of being folded in. `wins_on_median_
schedule` DOES carry site, because it is a win total and a win total that ignored
venue would be wrong rather than merely incomplete.

THE MEDIAN SCHEDULE IS A REAL TEAM'S SCHEDULE, NOT A SYNTHETIC ONE. The team
whose `schedule_strength` is the median gets its actual calendar - its opponents,
its home-and-away pattern, its game count - and every team is scored against that
same calendar. A synthetic "median opponent repeated twelve times" would be
easier and would invent a schedule nobody plays; this one is nameable, and the
name is published (`median_schedule_team`) so a reader can go and check it.

WHAT THE RANK DOES NOT SAY. `schedule_strength_rank` is computed over teams with
a full schedule in the archive, and its tail is soft for a reason that is
published rather than buried: North Dakota State and Sacramento State moved up
from FCS for 2026 and their prior-season ratings were earned against FCS
opposition, so a schedule containing them is rated against a number fitted on a
softer standard than the one they are about to be held to. `promotion_note`
carries that onto the artifact.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

import polars as pl

from cfbpoll.projection import forward, recipe

__all__ = [
    "MIN_FULL_SCHEDULE_GAMES",
    "Contrast",
    "ScheduleStrength",
    "contrast",
    "strengths",
]

#: Below this many scheduled games a team is left out of the RANKING, though it
#: keeps every other field. A four-game fragment in the archive produces a mean
#: opponent rating that is a fact about the archive rather than about a schedule,
#: and ranking it against teams with twelve would make the field size a lie.
MIN_FULL_SCHEDULE_GAMES = 10


@dataclass(frozen=True)
class ScheduleStrength:
    """Per-team schedule quantities, plus the constants that produced them."""

    table: pl.DataFrame
    median_schedule_team: str
    median_schedule_strength: float
    median_schedule_games: int
    field_size: int
    sigma: float
    home_field: float
    #: Teams promoted from FCS for this season, whose prior rating was earned
    #: against FCS opposition. Published because it is the soft tail of the rank.
    promoted: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "median_schedule_team": self.median_schedule_team,
            "median_schedule_strength": self.median_schedule_strength,
            "median_schedule_games": self.median_schedule_games,
            "field_size": self.field_size,
            "sigma": self.sigma,
            "home_field_points": self.home_field,
            "promoted_from_fcs": list(self.promoted),
            "min_full_schedule_games": MIN_FULL_SCHEDULE_GAMES,
        }


def _games_by_team(future: pl.DataFrame) -> dict[str, list[tuple[str, float]]]:
    """team -> [(opponent, site term in points-sign for THIS team)].

    The site term is +1 at home, -1 away, 0 neutral, so a caller multiplies it by
    home-field once and cannot get the sign backwards for the away side.
    """
    out: dict[str, list[tuple[str, float]]] = {}
    for row in future.iter_rows(named=True):
        home, away = str(row["home_team"]), str(row["away_team"])
        site = 0.0 if bool(row["neutral_site"]) else 1.0
        out.setdefault(home, []).append((away, site))
        out.setdefault(away, []).append((home, -site))
    return out


def strengths(
    projection: pl.DataFrame,
    future: pl.DataFrame,
    fitted: recipe.Recipe,
    prior_power: dict[str, float],
    prior_center: float,
    sigma: float,
    home_field: float,
    promoted: tuple[str, ...] = (),
) -> ScheduleStrength:
    """Every schedule quantity, for every team the projection ranks.

    `sigma` is `forward.projection_sigma(...)` - the AUGUST dispersion, wider
    than the in-season one because both teams' ratings are projections. Passing
    it in rather than recomputing it here means the win totals on this table and
    the ones in `forward.expected_wins` cannot come from two different sigmas.
    """
    rating = forward.rating_resolver(projection, fitted, prior_power, prior_center)
    schedules = _games_by_team(future)
    teams = sorted(projection["team"].to_list())

    strength: dict[str, float] = {}
    home_games: dict[str, int] = {}
    mixed: dict[str, bool] = {}
    counts: dict[str, int] = {}

    for team in teams:
        games = schedules.get(team, [])
        counts[team] = len(games)
        if not games:
            continue
        ratings = [rating(opponent) for opponent, _ in games]
        # NEUTRAL FIELD: opponent quality only. Venue is `home_games`, published
        # beside it and never folded in.
        strength[team] = sum(value for value, _ in ratings) / len(ratings)
        home_games[team] = sum(1 for _, site in games if site > 0)
        mixed[team] = any(source != "projection" for _, source in ratings)

    ranked = sorted(
        (t for t in strength if counts[t] >= MIN_FULL_SCHEDULE_GAMES),
        key=lambda t: (-strength[t], t),
    )
    rank = {team: i + 1 for i, team in enumerate(ranked)}

    # The median team by schedule strength. `statistics.median_low` picks an
    # actual member rather than averaging the middle two, which is the whole
    # point: the schedule has to belong to somebody.
    median_value = statistics.median_low([strength[t] for t in ranked]) if ranked else 0.0
    median_team = next((t for t in ranked if strength[t] == median_value), "")
    median_games = schedules.get(median_team, [])

    on_median = {
        team: _wins_against(rating(team)[0], median_games, rating, sigma, home_field)
        for team in teams
    }

    table = pl.DataFrame(
        {
            "team": teams,
            "schedule_strength": [strength.get(t) for t in teams],
            "schedule_strength_rank": pl.Series(
                [rank.get(t) for t in teams], dtype=pl.Int32
            ),
            "schedule_field_size": pl.Series([len(ranked)] * len(teams), dtype=pl.Int32),
            "home_games": pl.Series([home_games.get(t) for t in teams], dtype=pl.Int32),
            "schedule_is_mixed": [mixed.get(t) for t in teams],
            "wins_on_median_schedule": [on_median.get(t) for t in teams],
        }
    ).sort("team")

    return ScheduleStrength(
        table=table,
        median_schedule_team=median_team,
        median_schedule_strength=float(median_value),
        median_schedule_games=len(median_games),
        field_size=len(ranked),
        sigma=float(sigma),
        home_field=float(home_field),
        promoted=tuple(promoted),
    )


def _wins_against(
    team_rating: float,
    games: list[tuple[str, float]],
    rating: Any,
    sigma: float,
    home_field: float,
) -> float:
    """Expected wins for a team of `team_rating` against one calendar.

    Same construction as `forward.expected_wins`, same sigma, same independence
    assumption, and it reads the site term off the calendar being borrowed - so
    "Ohio State on Texas Tech's schedule" means Texas Tech's opponents in Texas
    Tech's venues, which is the only reading of that phrase that is worth
    anything.
    """
    total = 0.0
    for opponent, site in games:
        opponent_rating, _ = rating(opponent)
        total += forward.normal_cdf(
            (team_rating - opponent_rating + site * home_field) / sigma
        )
    return total


@dataclass(frozen=True)
class Contrast:
    """One pair of teams whose ranking and win totals disagree, and the swap."""

    higher_team: str
    higher_rank: int
    higher_wins: float
    higher_on_lower_schedule: float
    lower_team: str
    lower_rank: int
    lower_wins: float
    lower_on_higher_schedule: float
    inversion: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "higher_team": self.higher_team,
            "higher_rank": self.higher_rank,
            "higher_wins": f"{self.higher_wins:.1f}",
            "higher_on_lower_schedule": f"{self.higher_on_lower_schedule:.1f}",
            "lower_team": self.lower_team,
            "lower_rank": self.lower_rank,
            "lower_wins": f"{self.lower_wins:.1f}",
            "lower_on_higher_schedule": f"{self.lower_on_higher_schedule:.1f}",
        }


def contrast(
    projection: pl.DataFrame,
    future: pl.DataFrame,
    fitted: recipe.Recipe,
    prior_power: dict[str, float],
    prior_center: float,
    sigma: float,
    home_field: float,
    top_n: int = 25,
) -> Contrast | None:
    """The gloss pair: the TOP-RANKED team against the top-25 team that wins most.

    ANCHORED ON RANK 1, DELIBERATELY, AND THE FIRST RULE I WROTE WAS WORSE. The
    obvious rule is "maximise the inversion anywhere in the table". On the 2026
    projection that selects Michigan at 19 against North Dakota State at 23, a
    2.5-win gap, and it is wrong twice over. It answers a question nobody asked -
    a reader challenges the team at the top of the board, not the gap between
    19th and 23rd - and it stakes the method's showcase example on North Dakota
    State, whose rating was earned against FCS opposition and which this same
    module publishes a `promotion_note` about precisely because it is the least
    trustworthy number on the page.

    So the anchor is the top-ranked team and the partner is the top-25 team with
    the most projected wins. That is the sentence the card actually needs: "here
    is why the team we put first is first, even though somebody below it wins
    more games." It is deterministic, it needs no exclusion list (a promoted team
    can only be selected by winning the most games in the top 25, on its own
    schedule, which is a fact worth glossing if it ever happens), and on the 2026
    projection it lands on Ohio State against Texas Tech, which is the case the
    owner asked to be made objective.

    RETURNS NONE WHEN THE TOP TEAM ALSO WINS THE MOST, and that is the important
    half. A season where the board and the win column agree at the top needs no
    gloss, and a device that could only phrase a paradox would be manufacturing
    one the first year there is not one. The card renders this block or omits it;
    it never explains an inversion that is not there.
    """
    rating = forward.rating_resolver(projection, fitted, prior_power, prior_center)
    schedules = _games_by_team(future)

    rows = [
        row
        for row in projection.sort("projected_rank").to_dicts()
        if row.get("projected_rank") is not None
        and int(row["projected_rank"]) <= top_n
        and row.get("projected_wins") is not None
    ]
    if len(rows) < 2:
        return None

    higher = rows[0]
    # Ties break on the better rank, so the partner is a pure function of the
    # numbers and never of frame order.
    lower = min(
        rows[1:], key=lambda r: (-float(r["projected_wins"]), int(r["projected_rank"]))
    )
    gap = float(lower["projected_wins"]) - float(higher["projected_wins"])
    if gap <= 0:
        return None

    higher_team, lower_team = str(higher["team"]), str(lower["team"])
    return Contrast(
        higher_team=higher_team,
        higher_rank=int(higher["projected_rank"]),
        higher_wins=float(higher["projected_wins"]),
        higher_on_lower_schedule=_wins_against(
            rating(higher_team)[0], schedules.get(lower_team, []), rating, sigma, home_field
        ),
        lower_team=lower_team,
        lower_rank=int(lower["projected_rank"]),
        lower_wins=float(lower["projected_wins"]),
        lower_on_higher_schedule=_wins_against(
            rating(lower_team)[0], schedules.get(higher_team, []), rating, sigma, home_field
        ),
        inversion=gap,
    )
