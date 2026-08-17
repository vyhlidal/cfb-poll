"""The walk-forward chain: which games get scored, how they are scored, and how they pool.

`chain.py` publishes a table that compares four systems across four seasons, and
everything a reader could dispute about that table lives in three functions:

  * `game_frame` decides WHICH games count. Get the universe rule wrong and the
    headline is scored on a slate nobody agreed to - the module's own words are
    that a model quietly dropping the bridge games is "scoring itself on the half
    of the slate it finds interesting".
  * `accuracy` decides WHAT COUNTS AS RIGHT. Straight-up, with the home-field
    constant handed in rather than fitted on the games being scored, and a tie
    counted as a miss because a system with no opinion did not predict the game.
  * `summarise` decides HOW THE SEASONS ADD UP, and it is game-weighted. A
    39-game week 1 and a 53-game week 1 are different amounts of evidence, so the
    pooled figure is total-correct over total-games and never the mean of the
    rates.

Plus the two structural promises: a system that cannot be built honestly for a
target season is reported ABSENT with its reason rather than quietly given a
shortcut, and a builder may scale the home-field constant it is scored with -
the `projection.home_field` lever - but never choose it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import polars as pl
import pytest

from cfbpoll.projection import chain

# The loader's schema, rebuilt in-file so nothing here touches the archive.
GAME_SCHEMA: dict[str, Any] = {
    "game_id": pl.Int64,
    "season": pl.Int32,
    "week": pl.Int32,
    "season_type": pl.String,
    "game_type": pl.String,
    "start_date": pl.Datetime(time_unit="ms", time_zone="UTC"),
    "completed": pl.Boolean,
    "neutral_site": pl.Boolean,
    "conference_game": pl.Boolean,
    "home_team": pl.String,
    "away_team": pl.String,
    "home_points": pl.Int32,
    "away_points": pl.Int32,
    "home_class": pl.String,
    "away_class": pl.String,
    "source": pl.String,
}


def game(
    *,
    home: str,
    away: str,
    home_points: int | None,
    away_points: int | None,
    home_class: str = "fbs",
    away_class: str = "fbs",
    season: int = 2024,
    week: int = 1,
    season_type: str = "regular",
    game_type: str = "regular",
    completed: bool = True,
    neutral: bool = False,
) -> dict[str, Any]:
    return {
        "game_id": 0,
        "season": int(season),
        "week": int(week),
        "season_type": season_type,
        "game_type": game_type,
        "start_date": datetime(int(season), 9, 1, tzinfo=UTC),
        "completed": completed,
        "neutral_site": neutral,
        "conference_game": False,
        "home_team": home,
        "away_team": away,
        "home_points": home_points,
        "away_points": away_points,
        "home_class": home_class,
        "away_class": away_class,
        "source": "synthetic",
    }


def frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(
        [dict(row, game_id=i + 1) for i, row in enumerate(rows)], schema=GAME_SCHEMA
    )


def pairs(f: pl.DataFrame) -> set[tuple[str, str]]:
    return set(zip(f["home_team"].to_list(), f["away_team"].to_list(), strict=True))


# --------------------------------------------------------------- which games count


def slate() -> pl.DataFrame:
    """One season built so that every exclusion rule has something to exclude."""
    return frame(
        [
            game(home="W1 both fbs", away="Fbs A", home_points=24, away_points=17, week=1),
            game(
                home="W1 bridge",
                away="Fcs A",
                home_points=45,
                away_points=3,
                week=1,
                away_class="fcs",
            ),
            game(
                home="Fcs B",
                away="Fcs C",
                home_points=21,
                away_points=20,
                week=1,
                home_class="fcs",
                away_class="fcs",
            ),
            game(home="W3 both fbs", away="Fbs B", home_points=31, away_points=28, week=3),
            game(home="W5 both fbs", away="Fbs C", home_points=10, away_points=7, week=5),
            # A bowl game. Neither week 1 nor early, and the module says so.
            game(
                home="Bowl home",
                away="Bowl away",
                home_points=35,
                away_points=31,
                week=1,
                season_type="postseason",
                game_type="postseason",
            ),
            # Kicked off, not finished.
            game(
                home="In progress",
                away="Fbs D",
                home_points=7,
                away_points=0,
                week=1,
                completed=False,
            ),
            # Marked complete but the scoreboard never arrived.
            game(home="No score", away="Fbs E", home_points=None, away_points=None, week=1),
            # A different season entirely.
            game(
                home="Last year",
                away="Fbs F",
                home_points=20,
                away_points=13,
                week=1,
                season=2023,
            ),
        ]
    )


def test_game_frame_scores_the_regular_season_window_and_nothing_else() -> None:
    """Four exclusions in one place, because each of them silently doubles the
    sample if it fails: another season, the postseason, a game still in progress,
    and a game with no scoreboard."""
    week_one = chain.game_frame(slate(), 2024, through_week=1, universe="fbs_vs_fbs")

    assert pairs(week_one) == {("W1 both fbs", "Fbs A")}
    assert "Bowl home" not in week_one["home_team"].to_list()  # postseason
    assert "In progress" not in week_one["home_team"].to_list()  # not completed
    assert "No score" not in week_one["home_team"].to_list()  # null points
    assert "Last year" not in week_one["home_team"].to_list()  # wrong season
    assert week_one["season"].to_list() == [2024]


def test_game_frame_respects_both_ends_of_the_week_window() -> None:
    """`from_week` exists so a window can start late. A window that silently began
    at week 1 would let a "weeks 3-5" row quote a week-1 sample."""
    through_five = chain.game_frame(slate(), 2024, through_week=5)
    assert pairs(through_five) == {
        ("W1 both fbs", "Fbs A"),
        ("W3 both fbs", "Fbs B"),
        ("W5 both fbs", "Fbs C"),
    }

    middle = chain.game_frame(slate(), 2024, through_week=4, from_week=2)
    assert pairs(middle) == {("W3 both fbs", "Fbs B")}

    # Both ends are inclusive, which is what "weeks 1-4" means to a reader.
    assert chain.game_frame(slate(), 2024, through_week=3, from_week=3).height == 1
    assert chain.game_frame(slate(), 2024, through_week=2, from_week=2).is_empty()


def test_the_two_universes_draw_the_line_where_the_module_says_they_do() -> None:
    """`fbs_vs_fbs` needs BOTH sides FBS; `all_fbs` needs AT LEAST ONE.

    The second is what a reader means by "week 1", because half of week 1 is an
    FBS team playing an FCS team. Neither universe may swallow a game between two
    non-FBS teams: nobody is claiming this project ranks the FCS slate, and a
    94%-base-rate mismatch between two teams outside the universe would flatter
    every system in the table.
    """
    hard = chain.game_frame(slate(), 2024, through_week=1, universe="fbs_vs_fbs")
    wide = chain.game_frame(slate(), 2024, through_week=1, universe="all_fbs")

    assert pairs(hard) == {("W1 both fbs", "Fbs A")}
    assert pairs(wide) == {("W1 both fbs", "Fbs A"), ("W1 bridge", "Fcs A")}

    # The bridge game is the difference between the two, and it is the whole
    # reason both are published.
    assert pairs(wide) - pairs(hard) == {("W1 bridge", "Fcs A")}
    # And the FCS-vs-FCS game is in neither.
    assert ("Fcs B", "Fcs C") not in pairs(wide)
    assert ("Fcs B", "Fcs C") not in pairs(hard)
    assert set(chain.UNIVERSES) == {"fbs_vs_fbs", "all_fbs"}


# ------------------------------------------------------------- what counts as right


def test_accuracy_counts_exactly_the_games_it_had_an_opinion_about() -> None:
    """Straight-up accuracy over a frame where the answer can be worked out by
    hand, so the published percentage has an arithmetic check behind it.

    Three things are pinned at once, and each is a rule the module states in
    prose: a TIE is a miss and never a half, it does not enter the denominator;
    an unrated team sits at the league-average 0.0 and is COUNTED, because an
    accuracy figure propped up by default ratings is not the same number as one
    where every team was known; and mean absolute error is taken over every game
    and the tie is excluded from both figures, so the two numbers on the row rest
    on the same sample.
    """
    ratings = {"A": 10.0, "B": 0.0, "C": -5.0}
    scored = frame(
        [
            # delta = 10 - 0 + 3 = +13, A wins by 7. Right.
            game(home="A", away="B", home_points=28, away_points=21),
            # delta = 0 - 10 + 3 = -7, A wins by 4 on the road. Right.
            game(home="B", away="A", home_points=17, away_points=21),
            # delta = -5 - 0 + 3 = -2, and C wins by 1 at home. Wrong.
            game(home="C", away="B", home_points=21, away_points=20),
            # A tie. No opinion was tested, so it scores nothing either way.
            game(home="A", away="B", home_points=14, away_points=14),
            # One unrated side, treated as league average. delta = +13, A by 20.
            game(home="A", away="Unrated", home_points=41, away_points=21),
            # Two unrated sides. delta = 0 - 0 + 3 = +3, home by 2. Right.
            game(home="Ghost", away="Phantom", home_points=23, away_points=21),
        ]
    )

    out = chain.accuracy(ratings, scored, home_field=3.0)

    assert out["n_games"] == 5  # the tie is not in the denominator
    assert out["n_correct"] == 4
    assert out["su_accuracy"] == pytest.approx(4 / 5)
    assert out["n_ties"] == 1
    assert out["n_unrated_sides"] == 3  # Unrated, Ghost, Phantom
    # MAE is over the five SCORED games: (6 + 3 + 3 + 7 + 1) / 5. The tie is out of
    # both figures, because `su_accuracy` and `mean_abs_error` are published on the
    # same row and have to rest on the same sample, or the row is two measurements
    # sharing one sample size.
    assert out["mean_abs_error"] == pytest.approx(20 / 5)


def test_an_empty_frame_reports_no_opinion_rather_than_a_score() -> None:
    """`su_accuracy` of None is not zero. A system with no games in a window has
    not been shown to be wrong, and `summarise` skips it rather than pooling a
    zero into somebody's headline."""
    out = chain.accuracy({"A": 1.0}, frame([]).head(0), home_field=2.0)
    assert out["n_games"] == 0
    assert out["su_accuracy"] is None
    assert out["mean_abs_error"] is None
    assert out["n_correct"] == 0 and out["n_ties"] == 0 and out["n_unrated_sides"] == 0


def test_home_field_applies_only_at_a_venue_and_here_it_flips_the_call() -> None:
    """The sign rule IS the predictor: pick the home team when
    `rating_home - rating_away + h * at_a_venue > 0`.

    So the same fixture, same ratings, same result, played at a neutral site
    instead of at home has to come out the other way. Built as the pair rather
    than asserted about one of them, because a home-field term that was applied
    everywhere - or nowhere - would still pass a test that only looked at one.
    """
    ratings = {"Host": 0.0, "Guest": 3.0}
    # Host is the weaker team and wins by one at home.
    at_home = frame([game(home="Host", away="Guest", home_points=21, away_points=20)])
    at_neutral = frame(
        [game(home="Host", away="Guest", home_points=21, away_points=20, neutral=True)]
    )

    # delta = 0 - 3 + 5 = +2, so the home side is favoured and the call lands.
    assert chain.accuracy(ratings, at_home, home_field=5.0)["su_accuracy"] == 1.0
    # delta = 0 - 3 = -3 on neutral ground, so the call goes to Guest and misses.
    assert chain.accuracy(ratings, at_neutral, home_field=5.0)["su_accuracy"] == 0.0

    # And the constant has to be big enough to matter: at h = 1 the venue does not
    # rescue the weaker side, which is what makes the flip above a real flip.
    assert chain.accuracy(ratings, at_home, home_field=1.0)["su_accuracy"] == 0.0


# ----------------------------------------------------------------------- the chain


def toy_games() -> pl.DataFrame:
    """Two week-1 games and one week-3 game, one of each universe."""
    return frame(
        [
            game(home="Host", away="Guest", home_points=21, away_points=20, week=1),
            game(
                home="Host",
                away="Small",
                home_points=42,
                away_points=7,
                week=1,
                away_class="fcs",
            ),
            game(home="Guest", away="Host", home_points=30, away_points=10, week=3),
        ]
    )


TOY_INPUTS: dict[str, Any] = {
    "power_by_season": {2023: {"Host": 0.0, "Guest": 3.0}},
    "home_field_by_season": {2023: 5.0},
    "fbs_by_season": {2023: {"Host", "Guest"}, 2024: {"Host", "Guest"}},
}


def present_builder(**_: Any) -> tuple[dict[str, float], Any]:
    return {"Host": 0.0, "Guest": 3.0, "Small": -20.0}, {"description": "a toy system"}


def absent_builder(*, target_season: int, **_: Any) -> tuple[None, str]:
    return None, f"no transition whose target season precedes {target_season}"


def test_a_system_that_cannot_be_built_honestly_is_reported_absent_with_its_reason() -> None:
    """The module's own example is `projection` having no 2022 row: with 2021 as
    the archive's first season there is no transition to fit on, and inventing one
    would mean fitting on the season being scored.

    An absent system must therefore leave a NAMED HOLE with a sentence in it -
    never a zero, never a quietly-omitted column, and never a score.
    """
    result = chain.run_chain(
        toy_games(),
        [2024],
        {"present": present_builder, "absent": absent_builder},
        **TOY_INPUTS,
    )

    assert len(result.links) == 1
    link = result.links[0]

    assert link.absent["absent"] == "no transition whose target season precedes 2024"
    assert "absent" not in link.scores  # no score, not a zero
    assert "absent" not in link.provenance
    # The column still exists in the published order, so the hole is visible.
    assert result.systems == ("present", "absent")

    # The system that could be built is scored in every universe and every window.
    assert set(link.scores["present"]) == {"fbs_vs_fbs", "all_fbs"}
    for universe in ("fbs_vs_fbs", "all_fbs"):
        assert set(link.scores["present"][universe]) == {"week_1", "weeks_1_4"}
        for cell in link.scores["present"][universe].values():
            assert set(cell) == {
                "n_games",
                "su_accuracy",
                "n_correct",
                "n_ties",
                "n_unrated_sides",
                "mean_abs_error",
            }
    assert link.provenance["present"] == {"description": "a toy system"}

    # The home-field constant came off season Y-1's fit and says so.
    assert link.home_field == 5.0
    assert link.home_field_source == "season 2023 fitted L3 home field"

    # The bridge game is only in the wide universe, so the samples differ.
    assert link.scores["present"]["fbs_vs_fbs"]["week_1"]["n_games"] == 1
    assert link.scores["present"]["all_fbs"]["week_1"]["n_games"] == 2


def test_a_builder_may_scale_the_home_field_it_is_scored_with_and_it_changes_the_answer() -> None:
    """THE LEVER HOOK, and the reason it is a hook rather than a free parameter.

    A system never gets to choose the home-field constant - that comes off season
    Y-1's own fit - but `projection.home_field` lets it say how much of it to
    believe. Two builders with IDENTICAL ratings and different scales therefore
    have to come out with different accuracy, or the lever is decoration.

    Host is rated three points below Guest and wins by one at home. At full home
    field the call lands; with the home field switched off it does not.
    """
    def believer(**_: Any) -> tuple[dict[str, float], Any]:
        return {"Host": 0.0, "Guest": 3.0}, {"home_field_scale": 1.0}

    def ignorer(**_: Any) -> tuple[dict[str, float], Any]:
        return {"Host": 0.0, "Guest": 3.0}, {"home_field_scale": 0.0}

    def silent(**_: Any) -> tuple[dict[str, float], Any]:
        return {"Host": 0.0, "Guest": 3.0}, "a note that is not a dict"

    result = chain.run_chain(
        frame([game(home="Host", away="Guest", home_points=21, away_points=20, week=1)]),
        [2024],
        {"believer": believer, "ignorer": ignorer, "silent": silent},
        **TOY_INPUTS,
    )
    week_one = {
        system: block["fbs_vs_fbs"]["week_1"] for system, block in result.links[0].scores.items()
    }

    assert week_one["believer"]["n_games"] == week_one["ignorer"]["n_games"] == 1
    assert week_one["believer"]["su_accuracy"] == 1.0  # 0 - 3 + 5 = +2, home
    assert week_one["ignorer"]["su_accuracy"] == 0.0  # 0 - 3 + 0 = -3, away
    # A builder that says nothing about the scale believes the constant exactly.
    assert week_one["silent"]["su_accuracy"] == 1.0
    # The link still reports the UNSCALED constant, because that is the fact about
    # season 2023 and the scale is a fact about one system.
    assert result.links[0].home_field == 5.0


# -------------------------------------------------------------------- the pooling


def cell(n_games: int, n_correct: int, mean_abs_error: float) -> dict[str, Any]:
    return {
        "n_games": n_games,
        "su_accuracy": n_correct / n_games,
        "n_correct": n_correct,
        "n_ties": 0,
        "n_unrated_sides": 0,
        "mean_abs_error": mean_abs_error,
    }


def test_the_pooled_figure_is_weighted_by_games_and_not_by_season() -> None:
    """THE ONE THAT WOULD BE WRONG AND LOOK RIGHT.

    A ten-game season at 90% and a ninety-game season at 50% pool to 54%, not to
    70%. Averaging the two rates would treat ten games and ninety games as equal
    evidence, and a system that happened to shine in a thin season would carry a
    headline it did not earn. The two numbers are far enough apart here that a
    season-weighted implementation cannot pass by accident.
    """
    windows = {"week_1": (1, 1)}
    thin = chain.ChainLink(
        target_season=2023,
        home_field=2.0,
        home_field_source="season 2022 fitted L3 home field",
        scores={"s": {"u": {"week_1": cell(10, 9, 10.0)}}},
    )
    thick = chain.ChainLink(
        target_season=2024,
        home_field=2.0,
        home_field_source="season 2023 fitted L3 home field",
        scores={"s": {"u": {"week_1": cell(90, 45, 20.0)}}},
    )

    pooled = chain.summarise([thin, thick], ("s",), windows, ("u",))["u"]["s"]["week_1"]

    assert pooled["n_games"] == 100
    assert pooled["n_correct"] == 54
    assert pooled["su_accuracy"] == pytest.approx(0.54)
    assert pooled["su_accuracy"] != pytest.approx((0.9 + 0.5) / 2)  # the season-weighted trap
    # Mean absolute error pools the same way: (10*10 + 90*20) / 100.
    assert pooled["mean_abs_error"] == pytest.approx(19.0)
    # `seasons_covered` rides along so a system that skipped a season cannot be
    # compared with one that did not without the reader noticing.
    assert pooled["seasons_covered"] == [2023, 2024]


def test_a_system_with_no_games_in_a_window_is_left_out_of_the_pool() -> None:
    """A window a system was never scored in must not appear as a zero. `summarise`
    drops the empty cell and the `seasons_covered` list is what says so."""
    windows = {"week_1": (1, 1)}
    scored = chain.ChainLink(
        target_season=2023,
        home_field=2.0,
        home_field_source="x",
        scores={"s": {"u": {"week_1": cell(20, 15, 12.0)}}},
    )
    empty = chain.ChainLink(
        target_season=2024,
        home_field=2.0,
        home_field_source="x",
        scores={
            "s": {
                "u": {
                    "week_1": {
                        "n_games": 0,
                        "su_accuracy": None,
                        "n_correct": 0,
                        "n_ties": 0,
                        "n_unrated_sides": 0,
                        "mean_abs_error": None,
                    }
                }
            }
        },
    )

    pooled = chain.summarise([scored, empty], ("s",), windows, ("u",))["u"]["s"]["week_1"]
    assert pooled["n_games"] == 20
    assert pooled["seasons_covered"] == [2023]

    # A system that was never scored at all gets no block rather than an empty one.
    assert chain.summarise([empty], ("s",), windows, ("u",))["u"] == {}


# --------------------------------------------------------------- the published dict


def test_the_result_ships_as_json_and_carries_the_protocol_it_was_run_under() -> None:
    """A published chain is only checkable if the rules travel with it. The
    protocol string is where a reader learns that the home-field constant was not
    fitted on the games being scored and that ties counted as misses - so it has
    to survive serialisation along with everything else."""
    result = chain.run_chain(
        toy_games(),
        [2024],
        {"present": present_builder, "absent": absent_builder},
        **TOY_INPUTS,
    )

    document = result.as_dict()
    restored = json.loads(json.dumps(document))

    assert set(restored) == {"protocol", "windows", "systems", "links", "summary"}
    protocol = restored["protocol"]
    assert "Walk-forward" in protocol
    assert "Ties count as misses" in protocol
    assert "nothing from Y itself" in protocol

    assert restored["systems"] == ["present", "absent"]
    assert restored["windows"] == {"week_1": [1, 1], "weeks_1_4": [1, 4]}
    assert restored["links"][0]["target_season"] == 2024
    assert restored["links"][0]["home_field"] == 5.0
    assert restored["links"][0]["absent"]["absent"].startswith("no transition")
    assert "present" in restored["summary"]["fbs_vs_fbs"]
    assert "absent" not in restored["summary"]["fbs_vs_fbs"]
    # The summary is the same object the result computed, not a second pass.
    assert restored["summary"] == json.loads(json.dumps(result.summary))
