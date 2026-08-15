"""The wall between the Projection and the Poll, tested by climbing over it.

ADR 0010's claim is that the Poll may never read the Projection. A test that only
asserts the clean pipeline is clean would pass against an audit that returned
`True` unconditionally, so the load-bearing tests here are the ones that plant a
projection input where it does not belong and require the audit to name it:

  * plant `returning_usage` in a POLL design matrix - the audit must call it a
    PROJECTION INPUT by name, not fold it into a generic "outside the allow-list";
  * plant one in the games FRAME - presence alone must fail, with no consumption
    test, which is the one asymmetry in the module;
  * plant the AP poll and CFBD's PPA in the PROJECTION design - the projection has
    its own deny-list and a baseline that is also an input measures nothing;
  * plant a WITHIN-SEASON quantity in the PROJECTION design - ADR 0013's temporal
    guard, added after `coach_change` spent three seasons reading a coaches file
    pulled after the season it was projecting. Every check above passed the whole
    time, because the column name was innocent and only the clock was wrong.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games
from cfbpoll.projection import recipe
from cfbpoll.validate import leakage

pytestmark = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised",
)

CONFIG = load_config()


@pytest.fixture(scope="module")
def window() -> pl.DataFrame:
    games = load_games([2023], universe="model")
    return windows.games_through(games, season=2023, week=6, season_type="regular")


@pytest.fixture(scope="module")
def design() -> pl.DataFrame:
    """A minimal projection design frame. Values are arbitrary; columns are not."""
    teams = [f"Team {i:03d}" for i in range(40)]
    rng = np.random.default_rng(20260815)
    return pl.DataFrame(
        {
            "team": teams,
            "season": pl.Series([2026] * len(teams), dtype=pl.Int32),
            "prior_power_centered": rng.normal(0.0, 12.0, len(teams)),
            "returning_usage_centered": rng.normal(0.0, 0.15, len(teams)),
            "coach_change": rng.integers(0, 2, len(teams)).astype(float),
            "portal_net_z": rng.normal(0.0, 1.0, len(teams)),
        }
    )


# ------------------------------------------------- the Poll may not read the Projection


def test_a_projection_input_planted_in_a_poll_design_matrix_is_caught() -> None:
    """THE TEST ADR 0010 EXISTS FOR. The audit must name the breach as its own kind.

    A generic "outside the allow-list" line would be true and useless: the whole
    point of the separation is that this particular trespass has a name, a
    direction and an ADR, and a reader who greps the CI log for it has to find it.
    """
    planted = ["game_id", "home_team", "away_team", "home_points", "away_points",
               "neutral_site", "returning_usage"]
    report = leakage.audit(matrices={"L2": planted}, config=CONFIG)

    assert not report.passed
    breach = [v for v in report.violations if "PROJECTION INPUT" in v]
    assert breach, report.violations
    assert "returning_usage" in breach[0]
    assert "ADR 0010" in breach[0]


@pytest.mark.parametrize(
    "column",
    ["returning_usage", "portal_net", "coach_change", "prior_power", "projected_rank"],
)
def test_every_projection_input_family_is_caught_in_a_poll_matrix(column: str) -> None:
    """One planted column per family, so a new term cannot be added to the recipe
    without either matching a pattern here or failing this test."""
    report = leakage.audit(matrices={"L4": ["game_id", "home_team", column]}, config=CONFIG)
    assert any("PROJECTION INPUT" in v and column in v for v in report.violations), (
        column,
        report.violations,
    )


FITTED_GAME_LAYERS = ("L2", "L3", "L4", "schedule_odds")


def test_presence_alone_fails_for_a_projection_input(window: pl.DataFrame) -> None:
    """The asymmetry, exercised, on the layers where it is visible.

    `excitement_index` sitting unread in a FITTED layer's frame is the normal
    state of this archive: it is reported, proved unconsumed, and raises nothing.
    `returning_usage` sitting equally unread in the same frames is a violation,
    because ESPN put the first one there and only this repository could have put
    the second.

    (The loaders are excluded because they have no design matrix at all - their
    allow-list IS their projection, so ANY extra column fails them, which is
    pre-existing behaviour and would blur the contrast this test is about.)
    """
    theirs = leakage.audit(window.with_columns(excitement_index=pl.lit(0.5)), None, CONFIG)
    for name in FITTED_GAME_LAYERS:
        layer = next(x for x in theirs.layers if x.layer == name)
        assert "excitement_index" in layer.banned_present
        assert layer.projection_inputs_present == ()
        assert layer.consumed_outside_allow_list == ()
        assert layer.ok, name

    ours = leakage.audit(window.with_columns(returning_usage=pl.lit(0.5)), None, CONFIG)
    assert any("PROJECTION INPUT present" in v for v in ours.violations), ours.violations
    for name in FITTED_GAME_LAYERS:
        layer = next(x for x in ours.layers if x.layer == name)
        assert layer.projection_inputs_present == ("returning_usage",), name
        assert not layer.ok, name
        # And still provably UNCONSUMED: the rebuild is untouched by this rule,
        # so the audit is failing on provenance rather than on a false positive.
        assert layer.consumed_outside_allow_list == (), name
        assert layer.identical, name


def test_fail_on_banned_raises_for_a_planted_projection_input(window: pl.DataFrame) -> None:
    """`--fail-on-banned` must really stop the build, not merely disapprove."""
    with pytest.raises(leakage.BannedFeature, match="PROJECTION INPUT"):
        leakage.audit(
            window.with_columns(coach_change=pl.lit(1)), None, CONFIG, fail_on_banned=True
        )


def test_the_clean_poll_pipeline_is_untouched_by_all_of_this(window: pl.DataFrame) -> None:
    """A machine that has never computed a projection gets exactly the report it
    always got: the same layers, in the same order, with no projection layer
    appearing as a permanently-skipped row a reader would learn to ignore."""
    report = leakage.audit(window, None, CONFIG)
    assert report.passed, report.violations
    assert [layer.layer for layer in report.layers] == [spec.name for spec in leakage.LAYERS]
    assert report.context["projection_audited"] is False
    assert all(layer.kind == "poll" for layer in report.layers)


# --------------------------------------- and the Projection may not read a human poll


def test_the_projection_layer_rebuilds_from_its_own_allow_list(design: pl.DataFrame) -> None:
    """The positive result, obtained the same way every poll layer obtains it:
    rebuild the design matrix from the allow-listed columns alone and require it
    bit-identical."""
    report = leakage.audit(config=CONFIG, projection_design=design)
    layer = next(x for x in report.layers if x.layer == "projection")
    assert layer.kind == "projection"
    assert layer.identical
    assert layer.consumed_outside_allow_list == ()
    assert layer.ok
    assert report.context["projection_audited"] is True


def test_the_projection_may_use_what_the_poll_may_not(design: pl.DataFrame) -> None:
    """Every recipe term is banned in the Poll and allowed in the Projection. That
    is the whole ADR, expressed as two assertions on the same list of names."""
    for column in recipe.DESIGN_COLUMNS:
        assert leakage.banned_hits([column], "poll") == (column,), column
        assert leakage.banned_hits([column], "projection") == (), column


def test_the_ap_poll_is_banned_from_the_projection_too(design: pl.DataFrame) -> None:
    """The line that shows the separation is a design and not an excuse. The AP
    preseason poll is this product's BASELINE, and a baseline that is also an
    input measures nothing at all."""
    for column in ("ap_rank", "ap_points", "preseason_rank", "coaches_poll_rank"):
        assert leakage.banned_hits([column], "projection") == (column,), column

    planted = design.with_columns(ap_rank=pl.lit(1))
    report = leakage.audit(config=CONFIG, projection_design=planted)
    layer = next(x for x in report.layers if x.layer == "projection")
    assert "ap_rank" in layer.banned_present
    # It is not consumed, because the probe rebuilds from the allow-list - which
    # is the proof, not the promise.
    assert layer.identical


def test_cfbds_own_ppa_is_banned_from_the_projection_and_rides_along_anyway() -> None:
    """The mechanical version of a modelling choice.

    CFBD's returning-production endpoint serves `usage` (a counting-stat share)
    and `percentPPA` (their proprietary fitted model) on the SAME row. The recipe
    uses the first. This test is why that is a fact about the code rather than a
    matter of anyone remembering it."""
    from cfbpoll.projection import offseason

    assert "returning_percent_ppa" in offseason.RETURNING_COLUMNS
    assert leakage.banned_hits(["returning_percent_ppa"], "projection") == (
        "returning_percent_ppa",
    )
    assert "returning_percent_ppa" not in leakage.ALLOWED_BY_PROJECTION_LAYER["projection"]
    assert leakage.banned_hits(["returning_usage_centered"], "projection") == ()


def test_a_third_party_rating_planted_in_the_projection_is_reported(
    design: pl.DataFrame,
) -> None:
    """SP+, FPI, Elo and CORE are benchmarks for both products. A projection
    resting on somebody else's retrained model is not our projection."""
    planted = design.with_columns(
        sp_plus_rating=pl.lit(10.0), fpi=pl.lit(3.0), cfbd_core=pl.lit(1.0)
    )
    report = leakage.audit(config=CONFIG, projection_design=planted)
    layer = next(x for x in report.layers if x.layer == "projection")
    assert set(layer.banned_present) == {"sp_plus_rating", "fpi", "cfbd_core"}
    assert layer.consumed_outside_allow_list == ()


def test_every_projection_allow_listed_column_carries_a_reason() -> None:
    """Constraint 5 applied to the Projection's own allow-list. Same standard the
    poll's layers are held to in test_leakage.py."""
    for spec in leakage.PROJECTION_LAYERS:
        assert spec.allowed, spec.name
        assert spec.spec
        for column, reason in spec.allowed.items():
            assert isinstance(reason, str) and len(reason) > 10, (spec.name, column)
        assert set(spec.allowed) == set(recipe.DESIGN_COLUMNS), spec.name


# ------------------------------------------- and the Projection may not read the future
#
# ADR 0013. The two halves above ask WHICH columns reached a fit. These ask WHEN
# their values became knowable, which is the question that would have caught a
# coaching term reading a coaches file pulled after the season it was projecting.


def test_a_planted_within_season_column_is_named_a_temporal_leak(
    design: pl.DataFrame,
) -> None:
    """THE PLANTED LEAK. A column whose value the projected season itself decides
    must be named as a TEMPORAL breach in its own words, with its own exception
    type, because "outside the allow-list" is a different problem with a different
    fix."""
    planted = design.with_columns(season_wins=pl.lit(9.0))
    report = leakage.audit(config=CONFIG, projection_design=planted)

    assert not report.passed
    breach = [v for v in report.violations if "TEMPORAL LEAK" in v]
    assert breach, report.violations
    assert "season_wins" in breach[0]
    assert "ADR 0013" in breach[0]

    layer = next(x for x in report.layers if x.layer == "projection")
    assert layer.temporal_hits == ("season_wins",)
    assert not layer.ok
    # And provably UNCONSUMED, exactly as the projection-input asymmetry is: the
    # guard fails on the clock, not on a rebuild that came out different.
    assert layer.identical
    assert layer.consumed_outside_allow_list == ()


def test_fail_on_banned_raises_the_temporal_type(design: pl.DataFrame) -> None:
    """`TemporalLeak` is a `BannedFeature`, so every existing caller keeps
    catching it, and a caller that wants to know the clock was the problem can
    now ask."""
    planted = design.with_columns(final_power_actual=pl.lit(20.0))
    with pytest.raises(leakage.TemporalLeak, match="TEMPORAL"):
        leakage.audit(config=CONFIG, projection_design=planted, fail_on_banned=True)
    with pytest.raises(leakage.BannedFeature):
        leakage.audit(config=CONFIG, projection_design=planted, fail_on_banned=True)


def test_an_undeclared_column_fails_closed(design: pl.DataFrame) -> None:
    """The half that actually holds. A leak nobody predicted will not match a
    pattern, so the gate is the positive declaration: every column present has to
    arrive with the sentence that says what settles its value and by when."""
    planted = design.with_columns(october_firing=pl.lit(1))
    report = leakage.audit(config=CONFIG, projection_design=planted)

    assert not report.passed
    breach = [v for v in report.violations if "TEMPORAL GUARD" in v]
    assert breach, report.violations
    assert "october_firing" in breach[0]
    assert leakage.banned_hits(["october_firing"], "projection") == ()


def test_the_real_projection_frame_clears_the_guard(design: pl.DataFrame) -> None:
    """The positive result, and the reason the declaration is worth maintaining:
    on a healthy frame the guard is silent, so a line in the CI log means
    something."""
    report = leakage.audit(config=CONFIG, projection_design=design)
    layer = next(x for x in report.layers if x.layer == "projection")
    assert layer.temporal_hits == ()
    assert layer.temporal_undeclared == ()
    assert layer.temporal_as_of
    assert layer.ok
    assert report.context["temporal_guard"]["as_of"] == layer.temporal_as_of


def test_the_recipes_own_columns_are_all_declared_knowable() -> None:
    """A term added to the recipe without a knowability sentence fails here rather
    than in a season's worth of published numbers."""
    for column in recipe.DESIGN_COLUMNS:
        assert column in leakage.PROJECTION_KNOWABLE_IN_AUGUST, column
        assert len(leakage.PROJECTION_KNOWABLE_IN_AUGUST[column]) > 20, column


def test_no_poll_layer_carries_a_temporal_guard() -> None:
    """A poll layer is fitted on games that have been played and has no August to
    be honest about. Giving it a guard would produce a check that passes
    vacuously on every run, which is how a check stops being read."""
    assert all(spec.temporal is None for spec in leakage.LAYERS)
    assert all(spec.temporal is not None for spec in leakage.PROJECTION_LAYERS)


def test_the_deny_patterns_do_not_fire_on_the_frame_they_guard() -> None:
    """`coach_of_record_source` is the near miss: a pattern on the bare word
    `record` would have reported a violation on every healthy run, and a guard
    that cries wolf every run is a guard nobody reads."""
    hits, _ = leakage.PROJECTION_TEMPORAL_GUARD.check(
        list(leakage.PROJECTION_KNOWABLE_IN_AUGUST)
    )
    assert hits == ()
