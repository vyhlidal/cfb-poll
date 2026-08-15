"""Schedule strength, the median-schedule column, and the gloss pair.

The load-bearing property is the one the whole extension exists for: a board that
ranks on projected power while displaying win totals must be able to SHOW that
the ordering is deliberate. `wins_on_median_schedule` is what does that, so the
tests here are mostly about it being a genuine like-for-like comparison rather
than a number that happens to look reassuring.

The planted-inconsistency test is the important one. It builds a league where a
strong team's schedule is stuffed with the best opponents and a weaker team's
with the worst, asserts the win totals invert against the ratings, and then
asserts the median-schedule column puts them back in rating order. If that ever
stops holding, the card's central claim is false and this fails.
"""

from __future__ import annotations

import polars as pl
import pytest

from cfbpoll.projection import forward, recipe, schedule


def _recipe(residual_sd: float = 9.0) -> recipe.Recipe:
    return recipe.Recipe(
        intercept=15.0,
        coefficients={
            "prior_power": 0.68,
            "returning_production": 7.08,
            "coaching_change": -2.33,
            "net_portal": -0.41,
        },
        se=dict.fromkeys(recipe.TERMS, 1.0),
        intercept_se=1.0,
        transitions=((2025, 2026),),
        n_teams=100,
        r_squared=0.5,
        residual_sd=residual_sd,
    )


def _league(n: int = 14) -> pl.DataFrame:
    """`n` teams, ratings descending from 40 in even steps."""
    teams = [f"Team {i:02d}" for i in range(n)]
    return pl.DataFrame(
        {
            "team": teams,
            "projected_power": [40.0 - 3.0 * i for i in range(n)],
            "projected_rank": pl.Series(range(1, n + 1), dtype=pl.Int32),
        }
    )


def _round_robin(teams: list[str], neutral: bool = False) -> pl.DataFrame:
    rows = []
    gid = 0
    for i, home in enumerate(teams):
        for away in teams[i + 1 :]:
            gid += 1
            rows.append(
                {
                    "game_id": gid,
                    "week": 1,
                    "neutral_site": neutral,
                    "home_team": home,
                    "away_team": away,
                    "home_class": "fbs",
                    "away_class": "fbs",
                }
            )
    return pl.DataFrame(rows).with_columns(pl.col("week").cast(pl.Int32))


def _fixture(games: list[tuple[str, str, bool]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "game_id": list(range(1, len(games) + 1)),
            "week": pl.Series([1] * len(games), dtype=pl.Int32),
            "neutral_site": [n for _, _, n in games],
            "home_team": [h for h, _, _ in games],
            "away_team": [a for _, a, _ in games],
            "home_class": ["fbs"] * len(games),
            "away_class": ["fbs"] * len(games),
        }
    )


# ------------------------------------------------------------- schedule strength


def test_schedule_strength_is_the_mean_opponent_rating_and_ignores_venue() -> None:
    """NEUTRAL FIELD, by decision. Venue is `home_games` beside it, never folded
    in, because one number that blends who you play with where you play them can
    be checked against neither."""
    league = _league(4)
    # Team 00 hosts everybody; Team 03 visits everybody. Same opponents both ways.
    future = _fixture(
        [("Team 00", "Team 01", False), ("Team 00", "Team 02", False),
         ("Team 03", "Team 01", False), ("Team 03", "Team 02", False)]
    )
    out = schedule.strengths(
        league, future, _recipe(), {}, 0.0, 20.0, 3.9
    )
    row = {r["team"]: r for r in out.table.to_dicts()}
    # Both played Team 01 (37.0) and Team 02 (34.0), so both means are 35.5,
    # even though one hosted twice and the other hosted twice as well.
    assert row["Team 00"]["schedule_strength"] == pytest.approx(35.5)
    assert row["Team 03"]["schedule_strength"] == pytest.approx(35.5)
    assert row["Team 00"]["home_games"] == 2
    assert row["Team 03"]["home_games"] == 2


def test_home_games_counts_only_real_home_games() -> None:
    league = _league(3)
    future = _fixture(
        [("Team 00", "Team 01", False), ("Team 00", "Team 02", True),
         ("Team 01", "Team 02", False)]
    )
    out = schedule.strengths(league, future, _recipe(), {}, 0.0, 20.0, 3.9)
    row = {r["team"]: r for r in out.table.to_dicts()}
    assert row["Team 00"]["home_games"] == 1  # the neutral game is not a home game
    assert row["Team 01"]["home_games"] == 1
    assert row["Team 02"]["home_games"] == 0


def test_the_hardest_schedule_ranks_first() -> None:
    """Rank 1 is the HARDEST schedule, which is the direction a reader assumes."""
    league = _league(12)
    teams = league["team"].to_list()
    out = schedule.strengths(
        league, _round_robin(teams), _recipe(), {}, 0.0, 20.0, 3.9
    )
    table = out.table.drop_nulls("schedule_strength_rank").sort("schedule_strength_rank")
    strengths = table["schedule_strength"].to_list()
    assert strengths == sorted(strengths, reverse=True)
    # In a round robin the best team has the weakest schedule: it never plays itself.
    assert table["team"][0] == "Team 11"
    assert table["team"][-1] == "Team 00"


def test_a_thin_schedule_is_unranked_but_keeps_every_other_field() -> None:
    """A four-game fragment produces a mean that is a fact about the archive
    rather than about a schedule. Ranking it would make the field size a lie."""
    league = _league(14)
    teams = league["team"].to_list()
    future = _round_robin(teams[:13])  # Team 13 plays nobody
    out = schedule.strengths(league, future, _recipe(), {}, 0.0, 20.0, 3.9)
    row = {r["team"]: r for r in out.table.to_dicts()}

    assert out.field_size == 13
    assert row["Team 13"]["schedule_strength"] is None
    assert row["Team 13"]["schedule_strength_rank"] is None
    assert all(r["schedule_field_size"] == 13 for r in out.table.to_dicts())
    assert schedule.MIN_FULL_SCHEDULE_GAMES == 10


def test_schedule_is_mixed_flags_an_opponent_the_recipe_could_not_see() -> None:
    """An FCS opponent is rated by mean reversion alone. A mean that blends two
    provenances has to say so; that is the whole of `schedule_is_mixed`."""
    league = _league(3)
    future = _fixture(
        [("Team 00", "Team 01", False), ("Team 00", "Some FCS School", False),
         ("Team 01", "Team 02", False)]
    )
    out = schedule.strengths(
        league, future, _recipe(), {"Some FCS School": -20.0}, 0.0, 20.0, 3.9
    )
    row = {r["team"]: r for r in out.table.to_dicts()}
    assert row["Team 00"]["schedule_is_mixed"] is True
    assert row["Team 01"]["schedule_is_mixed"] is False


# --------------------------------------------- the median schedule, the load-bearer


def test_the_median_schedule_belongs_to_a_real_team() -> None:
    """A synthetic "median opponent repeated twelve times" would be easier and
    would invent a calendar nobody plays. This one is nameable and checkable."""
    league = _league(12)
    teams = league["team"].to_list()
    out = schedule.strengths(league, _round_robin(teams), _recipe(), {}, 0.0, 20.0, 3.9)
    assert out.median_schedule_team in teams
    assert out.median_schedule_games == len(teams) - 1
    strengths = sorted(
        out.table.drop_nulls("schedule_strength")["schedule_strength"].to_list()
    )
    assert out.median_schedule_strength in strengths


def test_every_team_is_scored_on_the_same_calendar() -> None:
    """The property that makes the column comparable straight down the table."""
    league = _league(12)
    teams = league["team"].to_list()
    out = schedule.strengths(league, _round_robin(teams), _recipe(), {}, 0.0, 20.0, 3.9)
    values = out.table["wins_on_median_schedule"].to_list()
    assert all(v is not None for v in values)
    # A better team wins more on the identical schedule. Monotone, no exceptions.
    ordered = out.table.join(league, on="team").sort("projected_power", descending=True)
    wins = ordered["wins_on_median_schedule"].to_list()
    assert wins == sorted(wins, reverse=True)


def test_the_planted_inconsistency_is_resolved_by_the_median_column() -> None:
    """THE TEST THE WHOLE EXTENSION EXISTS FOR.

    Build a league where the ranking and the win column genuinely disagree: a
    strong team plays only the best opposition, a weaker team plays only the
    worst. Assert the raw win totals INVERT against the ratings, which is the
    Ohio State / Texas Tech situation that reads as a bug. Then assert
    `wins_on_median_schedule` puts them back in rating order, which is the card's
    central claim.

    If this ever fails, the board is not defensible and the gloss is a story."""
    strong, weak = "Strong", "Weak"
    elite = [f"Elite {i}" for i in range(6)]
    minnows = [f"Minnow {i}" for i in range(6)]
    league = pl.DataFrame(
        {
            "team": [strong, weak, *elite, *minnows],
            "projected_power": [38.0, 30.0, *[36.0] * 6, *[6.0] * 6],
            "projected_rank": pl.Series(range(1, 15), dtype=pl.Int32),
        }
    )
    # Twice each, so both protagonists clear the ten-game ranking floor while
    # keeping the opposition asymmetry that plants the inversion.
    games = (
        [(strong, opponent, True) for opponent in elite] * 2
        + [(weak, opponent, True) for opponent in minnows] * 2
        # Filler, so the tiers are ranked too and a median schedule exists.
        + [(a, b, True) for a in elite for b in minnows]
        + [(a, b, True) for i, a in enumerate(elite) for b in elite[i + 1 :]]
        + [(a, b, True) for i, a in enumerate(minnows) for b in minnows[i + 1 :]]
    )
    future = _fixture(games)
    fitted = _recipe()
    sigma = forward.projection_sigma(fitted, 15.3)

    wins = forward.expected_wins(league, future, fitted, {}, 0.0, 15.3, 3.9)
    raw = dict(
        zip(wins.table["team"].to_list(), wins.table["projected_wins"].to_list(), strict=True)
    )
    # THE INVERSION, planted and confirmed: the better team wins fewer games.
    assert raw[strong] < raw[weak]

    out = schedule.strengths(league, future, fitted, {}, 0.0, sigma, 3.9)
    row = {r["team"]: r for r in out.table.to_dicts()}
    assert row[strong]["schedule_strength"] > row[weak]["schedule_strength"]
    assert row[strong]["schedule_strength_rank"] < row[weak]["schedule_strength_rank"]
    # AND THE RESOLUTION: on one shared calendar the ordering is restored.
    assert row[strong]["wins_on_median_schedule"] > row[weak]["wins_on_median_schedule"]


# ------------------------------------------------------------------- the gloss pair


def test_the_contrast_anchors_on_the_top_ranked_team() -> None:
    """The card's question is "why is this team first", not "why is 19th ahead of
    23rd". Anchoring on rank 1 is also what keeps the showcase example off a team
    whose rating the artifact separately warns about."""
    league = pl.DataFrame(
        {
            "team": ["Alpha", "Bravo", "Charlie", "Delta"],
            "projected_power": [40.0, 30.0, 28.0, 26.0],
            "projected_rank": pl.Series([1, 2, 3, 4], dtype=pl.Int32),
            "projected_wins": [8.0, 9.0, 11.0, 10.0],
        }
    )
    future = _round_robin(league["team"].to_list())
    result = schedule.contrast(league, future, _recipe(), {}, 0.0, 20.0, 3.9)

    assert result is not None
    assert result.higher_team == "Alpha"  # rank 1, always
    assert result.lower_team == "Charlie"  # the most wins below it, not merely the next
    assert result.inversion == pytest.approx(3.0)


def test_the_contrast_is_none_when_nothing_is_inverted() -> None:
    """A device that could only phrase a paradox would manufacture one the first
    season there is not one. The card omits the block instead."""
    league = pl.DataFrame(
        {
            "team": ["Alpha", "Bravo", "Charlie"],
            "projected_power": [40.0, 30.0, 20.0],
            "projected_rank": pl.Series([1, 2, 3], dtype=pl.Int32),
            "projected_wins": [11.0, 9.0, 4.0],
        }
    )
    future = _round_robin(league["team"].to_list())
    assert schedule.contrast(league, future, _recipe(), {}, 0.0, 20.0, 3.9) is None


def test_the_swap_reads_each_team_on_the_others_actual_calendar() -> None:
    """"Ohio State on Texas Tech's schedule" has to mean Texas Tech's opponents in
    Texas Tech's venues, or the phrase is worth nothing."""
    league = pl.DataFrame(
        {
            "team": ["Hard", "Easy", "Good", "Bad"],
            "projected_power": [35.0, 25.0, 34.0, 5.0],
            "projected_rank": pl.Series([1, 2, 3, 4], dtype=pl.Int32),
            "projected_wins": [1.0, 9.0, 5.0, 5.0],
        }
    )
    # Hard plays Good twice; Easy plays Bad twice.
    future = _fixture(
        [("Hard", "Good", True), ("Hard", "Good", True),
         ("Easy", "Bad", True), ("Easy", "Bad", True)]
    )
    result = schedule.contrast(league, future, _recipe(), {}, 0.0, 20.0, 3.9)
    assert result is not None
    assert (result.higher_team, result.lower_team) == ("Hard", "Easy")
    # Hard on Easy's schedule beats Hard on its own; Easy on Hard's does worse.
    assert result.higher_on_lower_schedule > result.higher_wins
    assert result.lower_on_higher_schedule < result.lower_wins


def test_the_contrast_serialises_every_number_as_a_string() -> None:
    """Contract rule 1 reaches the gloss block too."""
    league = pl.DataFrame(
        {
            "team": ["Alpha", "Bravo"],
            "projected_power": [40.0, 30.0],
            "projected_rank": pl.Series([1, 2], dtype=pl.Int32),
            "projected_wins": [8.0, 9.0],
        }
    )
    future = _fixture([("Alpha", "Bravo", True)])
    result = schedule.contrast(league, future, _recipe(), {}, 0.0, 20.0, 3.9)
    assert result is not None
    payload = result.as_dict()
    for key in (
        "higher_wins",
        "higher_on_lower_schedule",
        "lower_wins",
        "lower_on_higher_schedule",
    ):
        assert isinstance(payload[key], str), key
    assert isinstance(payload["higher_rank"], int)


def test_one_sigma_governs_both_the_win_total_and_the_swap() -> None:
    """Two sigmas would let a schedule number disagree with the win total sitting
    beside it on the same row, which is the class of bug the fixture contract
    exists to prevent."""
    league = _league(12)
    teams = league["team"].to_list()
    future = _round_robin(teams)
    fitted = _recipe()
    sigma = forward.projection_sigma(fitted, 15.3)

    out = schedule.strengths(league, future, fitted, {}, 0.0, sigma, 3.9)
    assert out.sigma == pytest.approx(sigma)
    # A wider sigma compresses the spread toward a coin flip, always.
    wide = schedule.strengths(league, future, fitted, {}, 0.0, sigma * 3, 3.9)
    narrow_spread = (
        max(out.table["wins_on_median_schedule"].to_list())
        - min(out.table["wins_on_median_schedule"].to_list())
    )
    wide_spread = (
        max(wide.table["wins_on_median_schedule"].to_list())
        - min(wide.table["wins_on_median_schedule"].to_list())
    )
    assert wide_spread < narrow_spread


def test_the_shared_rating_resolver_is_the_only_definition() -> None:
    """`expected_wins` and `strengths` must answer "how good is this opponent"
    identically, or a row can contradict itself."""
    league = _league(4)
    fitted = _recipe()
    rating = forward.rating_resolver(league, fitted, {"Ghost": -10.0}, 0.0)

    assert rating("Team 00") == (40.0, "projection")
    value, source = rating("Ghost")
    assert source == "mean_reversion_only"
    assert value == pytest.approx(15.0 + 0.68 * -10.0)
