"""What an FCS-earned rating is worth on the FBS scale, checked against a truth we planted.

`crossdivision.py` publishes two constants and asks a reader to believe they mean
what the docstring says. A test can do better than believe: build a league where
the answer is KNOWN, inflate the stored FCS ratings by a constant on purpose, and
require the estimator to hand that constant back. If it does, the regression is
measuring the division boundary and not some artifact of the mismatch slate.

The other four properties here are the ones the rest of the package leans on:

  * too few bridge games means UNMEASURED and both constants at zero, stated
    rather than a shrug of an estimate off a handful of games;
  * `through_season` is a wall - a frame that also holds later seasons must give
    a bit-identical answer, because `chain.py` re-measures per link and calls
    that walk-forward;
  * the three provenance cases are distinguishable from outside, so an artifact
    can print which one every team got;
  * and the promotion ceiling holds, because the bump is fitted on six programs
    and applying it above the best of them is extrapolation wearing a
    measurement's clothes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import numpy as np
import polars as pl
import pytest

from cfbpoll.projection import crossdivision

# The schema the real loader produces, reproduced here so nothing in this file
# needs the archive on disk or the network.
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


def _score(margin: float) -> tuple[int, int]:
    """A scoreboard whose difference is exactly `margin`, with no negative points."""
    m = int(round(margin))
    return (21 + m, 21) if m >= 0 else (21, 21 - m)


def game(
    *,
    season: int,
    week: int,
    home: str,
    away: str,
    margin: float,
    home_class: str,
    away_class: str,
    neutral: bool = False,
    game_id: int = 0,
    season_type: str = "regular",
    game_type: str = "regular",
    completed: bool = True,
) -> dict[str, Any]:
    home_points, away_points = _score(margin)
    return {
        "game_id": int(game_id),
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
    numbered = [dict(row, game_id=i + 1) for i, row in enumerate(rows)]
    return pl.DataFrame(numbered, schema=GAME_SCHEMA)


# --------------------------------------------------------------- the planted league


#: How much the stored FCS ratings overstate the truth, in points. The estimator
#: has to find this and nothing else.
PLANTED_GAP = 12.0
TRUE_HOME_FIELD = 2.4
SEASONS = (2021, 2022, 2023)
FBS_TEAMS = [f"FBS {i:02d}" for i in range(20)]
FCS_TEAMS = [f"FCS {i:02d}" for i in range(14)]
#: Four crossover games per FBS team, hosted both ways in equal numbers.
BRIDGE_GAMES_PER_SEASON = 4 * len(FBS_TEAMS)


def planted_league(
    gap: float = PLANTED_GAP,
    noise_sd: float = 9.0,
    seed: int = 20260817,
    dispersion: float = 1.0,
) -> tuple[pl.DataFrame, dict[int, dict[str, float]], dict[int, float], dict[int, set[str]]]:
    """A league where the truth is known, and the STORED FCS ratings are wrong by `gap`.

    Margins are generated from the TRUE ratings plus a true home field. The
    ratings handed to the estimator are the true ones for FBS teams and
    `true + gap` for every FCS team, which is exactly the failure the module was
    written for: a rating earned against FCS opposition, carried at face value.

    Everything else is held flat - one home-field constant, no promotions, the
    same membership every season - so the only thing left for the bridge
    indicator to pick up is the planted gap.

    `dispersion` is the second dial and it plants the OTHER effect: at 1.35 every
    margin is a third bigger than the ratings say, which is this model's real
    behaviour - ridge shrinks, so a 20-point favourite wins by 27. It is the
    reason the raw bridge miss and the division gap are different numbers, and
    the test below plants it with no division gap at all to prove the estimator
    can tell them apart.
    """
    rng = np.random.default_rng(seed)
    true_fbs = dict(zip(FBS_TEAMS, np.linspace(18.0, -18.0, len(FBS_TEAMS)), strict=True))
    true_fcs = dict(zip(FCS_TEAMS, np.linspace(-16.0, -42.0, len(FCS_TEAMS)), strict=True))
    truth = {**true_fbs, **true_fcs}
    klass = {**dict.fromkeys(FBS_TEAMS, "fbs"), **dict.fromkeys(FCS_TEAMS, "fcs")}

    rows: list[dict[str, Any]] = []

    def play(season: int, week: int, home: str, away: str) -> None:
        margin = (
            float(dispersion) * (truth[home] - truth[away])
            + TRUE_HOME_FIELD
            + float(rng.normal(0.0, noise_sd))
        )
        rows.append(
            game(
                season=season,
                week=week,
                home=home,
                away=away,
                margin=margin,
                home_class=klass[home],
                away_class=klass[away],
            )
        )

    for season in SEASONS:
        # Inside FBS: a connected slate that anchors the intercept and the slope.
        for i, home in enumerate(FBS_TEAMS):
            for step in (1, 2, 3):
                play(season, 1 + step, home, FBS_TEAMS[(i + step) % len(FBS_TEAMS)])
        # The bridge, hosted both ways in equal numbers so the coefficient is not
        # identified off one hosting arrangement.
        for i, fbs in enumerate(FBS_TEAMS):
            for step in (0, 1, 2, 3):
                fcs = FCS_TEAMS[(i + step) % len(FCS_TEAMS)]
                if (i + step) % 2 == 0:
                    play(season, 1, fbs, fcs)
                else:
                    play(season, 1, fcs, fbs)
        # Inside FCS: where the inflated ratings cancel and say nothing.
        for i, home in enumerate(FCS_TEAMS):
            play(season, 2, home, FCS_TEAMS[(i + 1) % len(FCS_TEAMS)])

    stored = {t: float(v) for t, v in true_fbs.items()}
    stored.update({t: float(v) + float(gap) for t, v in true_fcs.items()})
    power_by_season = {season: dict(stored) for season in SEASONS}
    home_field_by_season = {season: TRUE_HOME_FIELD for season in SEASONS}
    fbs_by_season = {season: set(FBS_TEAMS) for season in SEASONS}
    return frame(rows), power_by_season, home_field_by_season, fbs_by_season


# ------------------------------------------------------------------- the recovery


def test_the_estimator_recovers_a_gap_that_was_planted_on_purpose() -> None:
    """THE TEST THIS MODULE STANDS OR FALLS ON.

    Every FCS rating in this league is inflated by exactly twelve points and
    nothing else is wrong. `cross_division_gap` is published as the amount an
    FCS-earned rating overstates on the FBS scale, stored negated so a consumer
    adds it - so it has to come back at about -12.

    If the estimator instead reported the raw bridge miss it would be far larger,
    because the model under-predicts every mismatch and that compression is what
    `dispersion` carries. Both are asserted here so the two numbers cannot be
    quietly conflated again.
    """
    games, power, home_field, fbs = planted_league()

    calibration = crossdivision.measure(games, power, home_field, fbs, through_season=2023)

    assert calibration.measured
    assert calibration.n_bridge_games == BRIDGE_GAMES_PER_SEASON * len(SEASONS)
    assert calibration.cross_division_gap == pytest.approx(-PLANTED_GAP, abs=1.5)
    # Nothing here compresses margins, so the dispersion slope is one. It is the
    # reason a raw miss and the division gap are different numbers, and on a
    # league with no compression they must agree.
    assert calibration.dispersion == pytest.approx(1.0, abs=0.1)
    assert calibration.raw_bridge_miss == pytest.approx(PLANTED_GAP, abs=1.5)
    # A t of ten or better on this much evidence; the standard error is real.
    assert calibration.cross_division_gap_se == pytest.approx(0.0, abs=1.5)
    assert abs(calibration.cross_division_gap) > 6.0 * calibration.cross_division_gap_se
    # No promotions in this league, so the second constant has nothing to say.
    assert calibration.promotion_bump == 0.0
    assert calibration.n_promoted_teams == 0


def test_the_raw_bridge_miss_is_not_the_gap_and_the_estimator_can_tell() -> None:
    """THE DISTINCTION THE WHOLE MODULE TURNS ON, planted in isolation.

    In this league the FCS ratings are exactly right and nothing crosses a
    division boundary badly. The only thing wrong is that every margin runs a
    third bigger than the ratings predict, which is this model's real behaviour -
    ridge shrinks, so a twenty-point favourite wins by twenty-seven.

    An estimator that reported the raw FBS-over-FCS miss would announce a large
    cross-division gap here and be WRONG, because the miss belongs to the
    mismatches rather than to the boundary. So: a raw miss in double figures, a
    gap indistinguishable from zero, and a dispersion slope that names the real
    culprit. Without this test the recovery above cannot tell the two apart,
    because a league with no compression makes them the same number.
    """
    games, power, home_field, fbs = planted_league(gap=0.0, dispersion=1.35, noise_sd=5.0)

    calibration = crossdivision.measure(games, power, home_field, fbs, through_season=2023)

    # The number that looks like the answer, and is not: the FBS side beats its
    # prediction by nine points a game and none of it is about divisions.
    assert calibration.raw_bridge_miss > 7.0
    # The number that is: no division boundary was planted, so none is reported.
    assert calibration.cross_division_gap == pytest.approx(0.0, abs=1.0)
    assert abs(calibration.cross_division_gap) < 0.25 * calibration.raw_bridge_miss
    # And the slope carries the whole of the difference, which is why it ships.
    assert calibration.dispersion == pytest.approx(1.35, abs=0.08)


def test_a_bigger_planted_gap_comes_back_bigger() -> None:
    """The estimator is a measurement, not a constant. Doubling the planted
    inflation has to move the answer by about the same amount, or it is reporting
    something about the slate rather than about the division boundary."""
    small, *rest = planted_league(gap=6.0)
    calibration_small = crossdivision.measure(small, *rest, through_season=2023)
    large, *rest_large = planted_league(gap=24.0)
    calibration_large = crossdivision.measure(large, *rest_large, through_season=2023)

    assert calibration_small.cross_division_gap == pytest.approx(-6.0, abs=1.5)
    assert calibration_large.cross_division_gap == pytest.approx(-24.0, abs=1.5)


def test_too_few_bridge_games_is_reported_as_unmeasured_rather_than_estimated() -> None:
    """A gap fitted on a dozen crossover games is not a smaller measurement, it is
    a different kind of claim. Below the floor the module says so and both
    constants sit at zero, which is the pre-liberation behaviour stated out loud.
    """
    games, power, home_field, fbs = planted_league()
    assert crossdivision.DEFAULT_MIN_BRIDGE_GAMES == 40

    # One season of this league holds exactly BRIDGE_GAMES_PER_SEASON crossovers;
    # ask for one more than the archive can offer.
    calibration = crossdivision.measure(
        games,
        power,
        home_field,
        fbs,
        through_season=2021,
        min_bridge_games=BRIDGE_GAMES_PER_SEASON + 1,
    )
    assert calibration.measured is False
    assert calibration.cross_division_gap == 0.0
    assert calibration.cross_division_gap_se == 0.0
    assert calibration.promotion_bump == 0.0
    assert calibration.promotion_bump_se == 0.0
    assert calibration.n_bridge_games == BRIDGE_GAMES_PER_SEASON
    assert calibration.through_season == 2021

    # And the floor itself is enough to be measured at all - the refusal is about
    # the sample being too small, not about the sample being awkward.
    assert crossdivision.measure(
        games,
        power,
        home_field,
        fbs,
        through_season=2021,
        min_bridge_games=BRIDGE_GAMES_PER_SEASON,
    ).measured


# -------------------------------------------------------------- the walk-forward wall


def promoted_league() -> tuple[
    pl.DataFrame, dict[int, dict[str, float]], dict[int, float], dict[int, set[str]]
]:
    """Three seasons, a different program promoted into each of the last two.

    Both halves of the calibration have something to chew on here - bridge games
    in every season and a promoted program playing FBS opponents in its first FBS
    season - so the wall test below is checking that a later season is invisible
    to BOTH estimates rather than only to the easy one.
    """
    rng = np.random.default_rng(4242)
    incumbents = [f"Host {i:02d}" for i in range(8)]
    visitors = [f"Visit {i:02d}" for i in range(8)]
    truth = {t: 12.0 - 3.0 * i for i, t in enumerate(incumbents)}
    truth.update({t: -20.0 - 2.0 * i for i, t in enumerate(visitors)})
    truth["Riser A"] = -8.0
    truth["Riser B"] = -6.0

    membership = {
        2021: set(incumbents),
        2022: set(incumbents) | {"Riser A"},
        2023: set(incumbents) | {"Riser A", "Riser B"},
    }
    everybody = set(truth)
    rows: list[dict[str, Any]] = []

    def play(season: int, member: set[str], week: int, home: str, away: str) -> None:
        margin = truth[home] - truth[away] + 2.0 + float(rng.normal(0.0, 8.0))
        rows.append(
            game(
                season=season,
                week=week,
                home=home,
                away=away,
                margin=margin,
                home_class="fbs" if home in member else "fcs",
                away_class="fbs" if away in member else "fcs",
            )
        )

    for season in (2021, 2022, 2023):
        member = membership[season]
        members = sorted(member)
        outsiders = sorted(everybody - member)
        # Bridge games, hosted both ways, three per FBS member.
        for i, team in enumerate(members):
            for step in (0, 1, 2):
                other = outsiders[(i + step) % len(outsiders)]
                if (i + step) % 2 == 0:
                    play(season, member, 1 + step, team, other)
                else:
                    play(season, member, 1 + step, other, team)
        # Inside FBS: everybody hosts three members, which is what gives a
        # promoted program its first-FBS-season games against FBS opposition.
        for i, team in enumerate(members):
            for step in (1, 2, 3):
                play(season, member, 4 + step, team, members[(i + step) % len(members)])

    power = {season: {t: float(v) for t, v in truth.items()} for season in (2021, 2022, 2023)}
    home_field = {season: 2.0 for season in (2021, 2022, 2023)}
    return frame(rows), power, home_field, membership


def test_a_season_the_estimator_was_told_not_to_read_cannot_change_the_answer() -> None:
    """THE PROPERTY `chain.py` DEPENDS ON, and the one a loose implementation
    would break silently.

    `crossdivision.measure(..., through_season=Y)` is called once per chain link,
    and the whole walk-forward claim is that a constant carried into season Y+1
    existed before season Y+1 was played. That is only true if the games of later
    seasons are invisible to the call - not down-weighted, not nearly harmless,
    invisible. So: measure through 2022 on a frame holding 2021-2023, and again
    on the same frame truncated at 2022, and require the identical object.
    """
    games, power, home_field, fbs = promoted_league()
    truncated = games.filter(pl.col("season") <= 2022)
    assert truncated.height < games.height  # the later season really is in there

    full_view = crossdivision.measure(games, power, home_field, fbs, through_season=2022)
    walled = crossdivision.measure(truncated, power, home_field, fbs, through_season=2022)

    assert full_view.measured and walled.measured
    # Not a vacuous comparison: both halves of the calibration were estimated.
    assert full_view.n_bridge_games > crossdivision.DEFAULT_MIN_BRIDGE_GAMES
    assert full_view.n_promotion_games > 0
    assert full_view.n_promoted_teams == 1  # Riser A, and not yet Riser B
    assert full_view == walled  # frozen dataclass: every field, exactly
    assert full_view.as_dict() == walled.as_dict()
    for field in (
        "cross_division_gap",
        "cross_division_gap_se",
        "promotion_bump",
        "promotion_bump_se",
        "dispersion",
        "raw_bridge_miss",
        "n_bridge_games",
        "n_promotion_games",
        "n_promoted_teams",
        "promotion_ceiling_rel",
        "promotion_ceiling_team",
        "promotion_ceiling_season",
    ):
        assert getattr(full_view, field) == getattr(walled, field), field

    # And the wall really is holding something back: the season beyond it carries
    # more bridge games and a second promotion, and reading it moves the answer.
    later = crossdivision.measure(games, power, home_field, fbs, through_season=2023)
    assert later.n_bridge_games > full_view.n_bridge_games
    assert later.n_promoted_teams == 2
    assert later.cross_division_gap != full_view.cross_division_gap


# ------------------------------------------------------------------ the provenance


def calibration(
    gap: float = -13.0,
    bump: float = 9.0,
    ceiling_rel: float = 0.0,
    ceiling_team: str = "",
) -> crossdivision.DivisionCalibration:
    return crossdivision.DivisionCalibration(
        cross_division_gap=gap,
        cross_division_gap_se=0.6,
        promotion_bump=bump,
        promotion_bump_se=1.9,
        dispersion=1.3,
        raw_bridge_miss=17.3,
        n_bridge_games=602,
        n_promotion_games=68,
        n_promoted_teams=6,
        through_season=2025,
        promotion_ceiling_rel=ceiling_rel,
        promotion_ceiling_team=ceiling_team,
        promotion_ceiling_season=2022 if ceiling_team else 0,
        promotion_support_max_rel=6.0,
    )


def test_the_three_cases_are_told_apart_and_named() -> None:
    """An artifact prints the provenance beside the row, so the three cases have
    to be distinguishable from outside: a team that was already FBS is untouched,
    an ordinary FCS opponent carries the gap alone, and a promoted program carries
    the gap AND the bump."""
    cal = calibration(gap=-13.0, bump=9.0)
    ratings = {"Incumbent": 10.0, "Stays FCS": 4.0, "Moves Up": 6.0}

    adjusted, provenance = crossdivision.adjust_carried_ratings(
        ratings,
        source_fbs={"Incumbent"},
        target_fbs={"Incumbent", "Moves Up"},
        calibration=cal,
    )

    assert provenance["Incumbent"] == "fbs"
    assert adjusted["Incumbent"] == 10.0  # a rating earned against FBS is not moved

    assert provenance["Stays FCS"] == "cross_division"
    assert adjusted["Stays FCS"] == pytest.approx(4.0 - 13.0)  # the gap, exactly

    assert provenance["Moves Up"] == "promoted"
    assert adjusted["Moves Up"] == pytest.approx(6.0 - 13.0 + 9.0)  # gap plus bump
    assert cal.promoted_net == pytest.approx(-4.0)

    assert set(adjusted) == set(ratings)  # nobody is dropped
    assert set(provenance) == set(ratings)  # and nobody goes unexplained


def test_the_lever_weights_at_zero_leave_every_rating_alone() -> None:
    """`gap_weight` and `bump_weight` are the lever hooks. At zero the reader has
    asked for the pre-liberation behaviour - FCS ratings at face value - and must
    get exactly that, not a rounded version of it."""
    cal = calibration()
    ratings = {"Incumbent": 10.0, "Stays FCS": 4.0, "Moves Up": 6.0}

    adjusted, provenance = crossdivision.adjust_carried_ratings(
        ratings,
        source_fbs={"Incumbent"},
        target_fbs={"Incumbent", "Moves Up"},
        calibration=cal,
        gap_weight=0.0,
        bump_weight=0.0,
    )
    assert adjusted == ratings
    # The provenance still names what WOULD have happened, so an artifact can say
    # "this team is a promotion, and you turned the credit off".
    assert provenance == {
        "Incumbent": "fbs",
        "Stays FCS": "cross_division",
        "Moves Up": "promoted",
    }

    # Half the gap is half the move; the hook is linear and not a switch.
    half, _ = crossdivision.adjust_carried_ratings(
        ratings,
        source_fbs={"Incumbent"},
        target_fbs={"Incumbent"},
        calibration=cal,
        gap_weight=0.5,
    )
    assert half["Stays FCS"] == pytest.approx(4.0 - 6.5)


def test_an_unmeasured_calibration_carries_every_rating_through_untouched() -> None:
    """When the archive never held enough bridge games there is nothing to apply,
    and the module says `unadjusted` rather than applying a zero and calling it a
    measurement. The distinction is the whole difference between "we corrected by
    nothing" and "we did not correct"."""
    unmeasured = crossdivision.DivisionCalibration(
        cross_division_gap=0.0,
        cross_division_gap_se=0.0,
        promotion_bump=0.0,
        promotion_bump_se=0.0,
        dispersion=1.0,
        raw_bridge_miss=0.0,
        n_bridge_games=11,
        n_promotion_games=0,
        n_promoted_teams=0,
        through_season=2021,
        measured=False,
    )
    ratings = {"Incumbent": 10.0, "Stays FCS": 4.0, "Moves Up": 6.0}
    adjusted, provenance = crossdivision.adjust_carried_ratings(
        ratings,
        source_fbs={"Incumbent"},
        target_fbs={"Incumbent", "Moves Up"},
        calibration=unmeasured,
    )
    assert adjusted == ratings
    assert set(provenance.values()) == {"unadjusted"}


# --------------------------------------------------------------------- the ceiling


def test_no_promoted_team_is_projected_above_the_best_promotion_on_record() -> None:
    """THE EXTRAPOLATION GUARD, which is the rule that decides the North Dakota
    State row.

    The bump is fitted on six programs whose FCS-year ratings topped out well
    below the team it is now being applied to. Rather than let the fit run off the
    end of its own support, a promoted team is capped at the best FIRST FBS SEASON
    a promoted program has actually had - and the cap is announced in the
    provenance so a reader can see the row was capped rather than measured.
    """
    cal = calibration(gap=-13.0, bump=9.0, ceiling_rel=5.0, ceiling_team="James Madison")
    # source_fbs mean is (10 + 0) / 2 = 5, so the ceiling lands at 10 on this scale.
    ratings = {"Incumbent A": 10.0, "Incumbent B": 0.0, "High": 20.0, "Low": 10.0}

    adjusted, provenance = crossdivision.adjust_carried_ratings(
        ratings,
        source_fbs={"Incumbent A", "Incumbent B"},
        target_fbs={"Incumbent A", "Incumbent B", "High", "Low"},
        calibration=cal,
    )

    # 20 - 13 + 9 = 16, which is above the ceiling, so it is held at the ceiling.
    assert provenance["High"] == "promoted_at_ceiling"
    assert adjusted["High"] == pytest.approx(10.0)
    # 10 - 13 + 9 = 6, comfortably inside the evidence, so it is left alone.
    assert provenance["Low"] == "promoted"
    assert adjusted["Low"] == pytest.approx(6.0)

    # Turning the guard off gives the uncapped arithmetic and says `promoted`,
    # which is the honest label for a number nobody measured.
    uncapped, uncapped_provenance = crossdivision.adjust_carried_ratings(
        ratings,
        source_fbs={"Incumbent A", "Incumbent B"},
        target_fbs={"Incumbent A", "Incumbent B", "High", "Low"},
        calibration=cal,
        apply_ceiling=False,
    )
    assert uncapped_provenance["High"] == "promoted"
    assert uncapped["High"] == pytest.approx(16.0)
    assert uncapped["Low"] == pytest.approx(6.0)

    # A calibration that never found a promotion has no ceiling to apply.
    no_ceiling, no_ceiling_provenance = crossdivision.adjust_carried_ratings(
        ratings,
        source_fbs={"Incumbent A", "Incumbent B"},
        target_fbs={"Incumbent A", "Incumbent B", "High", "Low"},
        calibration=calibration(gap=-13.0, bump=9.0, ceiling_rel=5.0, ceiling_team=""),
    )
    assert no_ceiling_provenance["High"] == "promoted"
    assert no_ceiling["High"] == pytest.approx(16.0)


# ---------------------------------------------------------------- the published dict


def test_the_calibration_ships_as_json_with_every_documented_field() -> None:
    """`as_dict` is what lands on a published artifact, so every field on it is
    either a number a reader can check or the size of the sample behind it. A
    missing key here is a claim published without its support."""
    document = calibration(ceiling_rel=5.75, ceiling_team="James Madison").as_dict()
    restored = json.loads(json.dumps(document))

    assert set(restored) == {
        "cross_division_gap",
        "cross_division_gap_se",
        "promotion_bump",
        "promotion_bump_se",
        "promoted_net",
        "dispersion",
        "raw_bridge_miss",
        "n_bridge_games",
        "n_promotion_games",
        "n_promoted_teams",
        "through_season",
        "measured",
        "promotion_ceiling_rel",
        "promotion_ceiling_team",
        "promotion_ceiling_season",
        "promotion_support_max_rel",
        "promotion_ceiling_rule",
        "definition",
    }
    # The two constants and their net are internally consistent on the page.
    assert restored["promoted_net"] == pytest.approx(
        restored["cross_division_gap"] + restored["promotion_bump"], abs=1e-6
    )
    # The rule reads as a football fact, naming who holds the ceiling and when.
    assert "James Madison" in restored["promotion_ceiling_rule"]
    assert "2022" in restored["promotion_ceiling_rule"]
    assert restored["definition"].strip()

    # And it survives the round trip off a real measurement too, numpy floats and
    # all - an artifact writer must never meet a np.float64 here.
    games, power, home_field, fbs = planted_league()
    measured = crossdivision.measure(games, power, home_field, fbs, through_season=2023).as_dict()
    assert json.loads(json.dumps(measured))["measured"] is True


# -------------------------------------------------------------------- the receipts


def receipt_league() -> tuple[pl.DataFrame, dict[int, dict[str, float]], dict[int, float]]:
    """One FCS program, two FBS opponents, and several games that must not appear."""
    rows = [
        # Deliberately out of chronological order in the frame.
        game(
            season=2024,
            week=2,
            home="Colorado",
            away="Dakota",
            margin=5.0,
            home_class="fbs",
            away_class="fcs",
        ),
        game(
            season=2023,
            week=3,
            home="Arizona",
            away="Dakota",
            margin=3.0,
            home_class="fbs",
            away_class="fcs",
        ),
        # An FCS-vs-FCS game: the opponent was not FBS, so it is not a receipt.
        game(
            season=2023,
            week=1,
            home="Dakota",
            away="Rival",
            margin=28.0,
            home_class="fcs",
            away_class="fcs",
        ),
        # A game Dakota was not in.
        game(
            season=2024,
            week=5,
            home="Arizona",
            away="Colorado",
            margin=7.0,
            home_class="fbs",
            away_class="fbs",
        ),
        # 2025: Dakota has been promoted, so it is FBS itself and this is not a
        # cross-division receipt however much it looks like one.
        game(
            season=2025,
            week=1,
            home="Arizona",
            away="Dakota",
            margin=1.0,
            home_class="fbs",
            away_class="fbs",
        ),
    ]
    power = {
        2023: {"Dakota": 24.5, "Arizona": 6.0, "Rival": -8.0},
        2024: {"Dakota": 23.0, "Colorado": 4.0, "Arizona": 5.0},
        2025: {"Dakota": 22.0, "Arizona": 5.5},
    }
    home_field = {2023: 2.5, 2024: 2.5, 2025: 2.5}
    return frame(rows), power, home_field


def test_receipts_return_only_the_games_that_cross_the_division_and_stay_in_order() -> None:
    """THE PRINTABLE PART. A gap estimated over 602 games is a fact about the
    league; a reader arguing about one program wants that program's own record
    against FBS teams, game by game, with the model's expectation beside it.

    So the filter is exact - the named team was NOT FBS and the opponent WAS -
    and the order is chronological, because a receipt printed out of order is a
    table nobody trusts.
    """
    games, power, home_field = receipt_league()

    out = crossdivision.receipts(games, "Dakota", power, home_field, through_season=2025)

    assert [(r["season"], r["week"], r["opponent"]) for r in out] == [
        (2023, 3, "Arizona"),
        (2024, 2, "Colorado"),
    ]
    assert out == sorted(out, key=lambda r: (r["season"], r["week"]))

    for receipt in out:
        assert receipt["result"] == "lost"  # both, by the scoreboard
        assert receipt["margin"] < 0
        assert receipt["at"] == "away"
        # The published arithmetic, checkable by hand from the two columns above.
        assert receipt["miss"] == pytest.approx(
            receipt["margin"] - receipt["model_expected_margin"]
        )
        # Carrying the FCS rating at face value, the model expected better than
        # this happened. That is the argument the whole module is making.
        assert receipt["miss"] < 0

    # 2023 away at Arizona: 24.5 - 6.0 - 2.5 = +16.0 expected, lost by 3.
    assert out[0]["model_expected_margin"] == pytest.approx(16.0)
    assert out[0]["margin"] == pytest.approx(-3.0)
    assert out[0]["miss"] == pytest.approx(-19.0)

    # The wall applies here too: nothing after `through_season` is readable.
    assert crossdivision.receipts(games, "Dakota", power, home_field, through_season=2023) == [
        out[0]
    ]
    # A team with no crossover history gets an empty list, not a guess.
    assert crossdivision.receipts(games, "Arizona", power, home_field, through_season=2025) == []


def test_season_receipts_cover_the_whole_season_worst_game_first() -> None:
    """The other half of the printable argument: not "what has this program done
    against FBS teams" but "why is this team rated where it is". Sorted by how far
    each game landed from expectation so the two or three games actually doing the
    work sit at the top instead of buried in a twelve-row table nobody reads."""
    rows = [
        game(
            season=2023,
            week=1,
            home="Dakota",
            away="Rival",
            margin=28.0,
            home_class="fcs",
            away_class="fcs",
        ),
        game(
            season=2023,
            week=3,
            home="Arizona",
            away="Dakota",
            margin=3.0,
            home_class="fbs",
            away_class="fcs",
        ),
        game(
            season=2023,
            week=6,
            home="Dakota",
            away="Cousin",
            margin=-2.0,
            home_class="fcs",
            away_class="fcs",
        ),
        game(
            season=2023,
            week=9,
            home="Dakota",
            away="Rival",
            margin=40.0,
            home_class="fcs",
            away_class="fcs",
            neutral=True,
        ),
        # A different season. `season_receipts` is asked for one, and gets one.
        game(
            season=2024,
            week=1,
            home="Dakota",
            away="Rival",
            margin=10.0,
            home_class="fcs",
            away_class="fcs",
        ),
    ]
    power = {"Dakota": 24.5, "Arizona": 6.0, "Rival": -8.0, "Cousin": 2.0}

    out = crossdivision.season_receipts(frame(rows), "Dakota", 2023, power, home_field=2.5)

    # Every game the team played that season, and nothing from any other.
    assert len(out) == 4
    assert sorted(r["week"] for r in out) == [1, 3, 6, 9]
    assert {r["season"] for r in out} == {2023}
    assert sorted(r["opponent"] for r in out) == ["Arizona", "Cousin", "Rival", "Rival"]

    # Worst first: ascending by how far the result fell short of expectation.
    misses = [r["miss"] for r in out]
    assert misses == sorted(misses)
    # Week 6 tops the card: a two-point home LOSS to a team rated 22 points below
    # them is a bigger hole than the three-point loss at Arizona, and the sort
    # says so without anybody having to read the scoreboard column.
    assert [r["week"] for r in out] == [6, 3, 1, 9]
    assert out[0]["miss"] == pytest.approx(-2.0 - (24.5 - 2.0 + 2.5))
    assert out[1]["miss"] == pytest.approx(-3.0 - (24.5 - 6.0 - 2.5))

    for receipt in out:
        assert receipt["miss"] == pytest.approx(
            round(receipt["margin"] - receipt["model_expected_margin"], 2), abs=1e-9
        )
        assert receipt["result"] in {"won", "lost", "tied"}
        assert receipt["opponent_power"] == pytest.approx(round(power[receipt["opponent"]], 2))

    # The neutral-site game gets no home field, which is the only reason its
    # expectation differs from the otherwise identical week-1 fixture. This is
    # the arithmetic, which is what the published number rests on; the `at`
    # LABEL for a neutral game whose nominal host is this team is a separate
    # question and is not asserted here.
    neutral = next(r for r in out if r["week"] == 9)
    hosted = next(r for r in out if r["week"] == 1)
    assert hosted["model_expected_margin"] - neutral["model_expected_margin"] == pytest.approx(2.5)
