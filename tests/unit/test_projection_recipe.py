"""The recipe's arithmetic, its determinism, and the holdout lock around it.

The properties worth testing here are the ones a reader is entitled to check by
hand from a published artifact:

  * the term contributions SUM to the projected rating, intercept included -
    otherwise the "Δ" columns on the published table are decoration;
  * mean reversion cannot reorder anything, which is the finding that makes the
    gap between `projection` and `naive_carryover` the whole measured value of
    the offseason data;
  * the same inputs give the same ranking, byte for byte, on any machine;
  * and the holdout may be READ and may never be FITTED ON.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from cfbpoll.backtest.walkforward import HoldoutLocked
from cfbpoll.config import load_config
from cfbpoll.projection import holdout, recipe

CONFIG = load_config()


@pytest.fixture
def design() -> pl.DataFrame:
    teams = [f"Team {i:03d}" for i in range(60)]
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


@pytest.fixture
def fitted(design: pl.DataFrame) -> recipe.Recipe:
    rng = np.random.default_rng(7)
    truth = (
        14.0
        + 0.7 * design["prior_power_centered"].to_numpy()
        + 7.0 * design["returning_usage_centered"].to_numpy()
        - 2.0 * design["coach_change"].to_numpy()
        + rng.normal(0.0, 4.0, design.height)
    )
    return recipe.fit_recipe([design], [truth], [(2025, 2026)])


# ---------------------------------------------------------------------- arithmetic


def test_the_term_contributions_sum_to_the_projected_rating(
    design: pl.DataFrame, fitted: recipe.Recipe
) -> None:
    """The published table's Δ columns must add up, or they are decoration.

    A reader who wants to check one row of demo/2026-preseason-projection.md by
    hand adds four numbers and the intercept and expects the Power column. This
    is that promise as an assertion."""
    table = recipe.term_contributions(fitted, design)
    total = table["contrib_intercept"].to_numpy()
    for term in recipe.TERMS:
        total = total + table[f"contrib_{term}"].to_numpy()
    np.testing.assert_allclose(total, table["projected_power"].to_numpy(), rtol=0, atol=1e-9)
    np.testing.assert_allclose(
        table["projected_power"].to_numpy(), fitted.predict(design), rtol=0, atol=1e-9
    )


def test_a_term_that_does_not_apply_contributes_positive_zero(
    design: pl.DataFrame, fitted: recipe.Recipe
) -> None:
    """IEEE negative zero, which a negative coefficient times an exact zero
    produces, must not reach a published table. `-0.00` in the coach column for
    the hundred schools that kept their coach is a small lie about what happened
    to them."""
    table = recipe.term_contributions(fitted, design)
    kept = design["coach_change"].to_numpy() == 0.0
    values = table["contrib_coaching_change"].to_numpy()[kept]
    assert values.size
    assert np.all(np.signbit(values) == False)  # noqa: E712 - signbit, not truthiness


def test_mean_reversion_cannot_reorder_anything(design: pl.DataFrame) -> None:
    """THE FINDING THE BACKTEST RESTS ON. `a + phi * (x - mean)` is a positive
    affine map, so a recipe with only the prior-Power term produces exactly the
    ranking of the prior Power itself, for ANY phi > 0.

    That is why `regress_only` and `naive_carryover` tie on every rank metric,
    and therefore why the gap between the full recipe and the naive floor is the
    entire measured value of the offseason data."""
    prior = design["prior_power_centered"].to_numpy()
    teams = design["team"].to_list()
    by_prior = [teams[int(i)] for i in np.argsort(-prior, kind="stable")]

    for phi in (0.05, 0.5, 0.9, 1.0, 3.0):
        only = recipe.Recipe(
            intercept=14.0,
            coefficients={"prior_power": phi},
            se={"prior_power": 0.0},
            intercept_se=0.0,
            transitions=((2025, 2026),),
            n_teams=design.height,
            r_squared=0.0,
            residual_sd=1.0,
            terms=("prior_power",),
        )
        projected = recipe.project(only, design, design["team"].to_list())
        assert projected["team"].to_list() == by_prior, phi


def test_the_projection_is_deterministic(design: pl.DataFrame, fitted: recipe.Recipe) -> None:
    """Report 03 §9.3 applies to this product too: same inputs, same bytes."""
    first = recipe.project(fitted, design, design["team"].to_list())
    second = recipe.project(fitted, design.sample(fraction=1.0, shuffle=True, seed=3),
                            design["team"].to_list())
    assert first["team"].to_list() == second["team"].to_list()
    np.testing.assert_allclose(
        first["projected_power"].to_numpy(), second["projected_power"].to_numpy(), atol=1e-12
    )


def test_ties_break_on_team_name_and_not_on_frame_order() -> None:
    """Two teams with identical inputs must rank alphabetically, whichever order
    they arrived in - otherwise a published rank depends on how a frame was
    built."""
    frame = pl.DataFrame(
        {
            "team": ["Zeta", "Alpha"],
            "season": pl.Series([2026, 2026], dtype=pl.Int32),
            "prior_power_centered": [5.0, 5.0],
            "returning_usage_centered": [0.0, 0.0],
            "coach_change": [0.0, 0.0],
            "portal_net_z": [0.0, 0.0],
        }
    )
    only = recipe.Recipe(
        intercept=1.0,
        coefficients=dict.fromkeys(recipe.TERMS, 1.0),
        se=dict.fromkeys(recipe.TERMS, 0.0),
        intercept_se=0.0,
        transitions=((2025, 2026),),
        n_teams=2,
        r_squared=0.0,
        residual_sd=1.0,
    )
    assert recipe.project(only, frame, ["Alpha", "Zeta"])["team"].to_list() == ["Alpha", "Zeta"]


def test_only_ranked_teams_get_a_rank(design: pl.DataFrame, fitted: recipe.Recipe) -> None:
    """Every team keeps its row; only the eligible membership gets a number. Same
    construction retro._cell_frame uses for the poll."""
    eligible = design["team"].to_list()[:20]
    projected = recipe.project(fitted, design, eligible)
    ranked = projected.filter(pl.col("projected_rank").is_not_null())
    assert projected.height == design.height
    assert set(ranked["team"].to_list()) == set(eligible)
    assert ranked["projected_rank"].to_list() == list(range(1, 21))


def test_a_fit_with_fewer_terms_is_the_same_class(design: pl.DataFrame) -> None:
    """`regress_only` must go through the identical code path as the full recipe,
    or the backtest is comparing two implementations rather than two models."""
    y = np.asarray(design["prior_power_centered"].to_numpy()) * 0.6 + 12.0
    full = recipe.fit_recipe([design], [y], [(2025, 2026)])
    partial = recipe.fit_recipe([design], [y], [(2025, 2026)], terms=("prior_power",))
    assert partial.terms == ("prior_power",)
    assert set(partial.coefficients) == {"prior_power"}
    assert partial.as_dict()["coefficients"].keys() == {"prior_power"}
    contributions = recipe.term_contributions(partial, design)
    assert contributions["contrib_net_portal"].to_list() == [0.0] * design.height
    assert full.terms == recipe.TERMS


# ------------------------------------------------------------------- the holdout


def test_a_season_may_be_read_and_may_not_be_fitted_on() -> None:
    """ADR 0010 §3, restated by ADR 0012 as two assertions about an ACT.

    CHANGED 2026-08-15. This test read `holdout_seasons(CONFIG) == {2025}` and
    asserted that fitting 2024->2025 raised. 2025 was scored once on 2026-08-15
    and is open, so the season under guard is now 2026 - the season the recipe
    PREDICTS, and the one the project publishes a live board and a live grade
    for. The rule did not change and neither did the exception; the list did.
    """
    assert holdout.no_fit_seasons(CONFIG) == {2026}
    assert holdout.holdout_seasons is holdout.no_fit_seasons  # the old name still works

    # Reading: any season may be a source, and nothing objects.
    holdout.assert_no_target_is_locked([(2025, 2024)], CONFIG)
    holdout.assert_no_target_is_locked([(2024, 2025)], CONFIG)

    # Fitting: a no-fit TARGET is refused, with the backtest's own exception.
    with pytest.raises(HoldoutLocked, match="2026"):
        holdout.assert_no_target_is_locked([(2025, 2026)], CONFIG)


def test_the_shipped_design_transitions_never_target_a_no_fit_season() -> None:
    """The live config, checked rather than trusted. If somebody adds 2025->2026
    to `design_transitions` this fails, which is the point."""
    transitions = [(int(a), int(b)) for a, b in CONFIG["projection"]["design_transitions"]]
    holdout.assert_no_target_is_locked(transitions, CONFIG)
    assert CONFIG["projection"]["projection_source_season"] == 2025
    assert all(target not in holdout.no_fit_seasons(CONFIG) for _, target in transitions)


def test_the_design_transitions_include_every_completed_season() -> None:
    """The freeze is gone and this is what replaced it (ADR 0014).

    Until 2026-08-17 this test asserted that 2024->2025 stayed OUT, because the
    recipe was frozen and one set of coefficients had to serve every season. That
    bought one sentence and cost a season of data on every future refit. The
    vintage record buys the same sentence for nothing, so the list now grows as
    seasons close, and the rule that protects a reader moved from this list to the
    place it can actually be enforced: `systems.fit_walk_forward` derives each
    projection's transitions from its own target season.
    """
    targets = {int(b) for _, b in CONFIG["projection"]["design_transitions"]}
    assert targets == {2022, 2023, 2024, 2025}
    # And the rule that did not go away: nothing may fit on the season it predicts.
    assert int(CONFIG["projection"]["target_season"]) not in targets


def test_a_projection_never_fits_on_the_season_it_projects() -> None:
    """The one guarantee the freeze was standing in for, enforced by construction.

    `fit_walk_forward` builds its own transition list from the target season
    rather than reading one, so no config edit can hand a projection the outcomes
    it claims to predict. The rating inputs here are synthetic and the games frame
    is never reached, because the derivation happens before any of it is used:
    a target with no earlier transition returns `(None, [])` and says why.
    """
    from cfbpoll.projection import systems

    power = {season: {"A": 1.0, "B": 0.0} for season in (2021, 2022, 2023, 2024, 2025)}
    fbs = {season: {"A", "B"} for season in power}
    home = dict.fromkeys(power, 2.0)

    fitted, transitions = systems.fit_walk_forward(
        pl.DataFrame(), 2021, power, home, fbs, systems.ProjectionLevers()
    )
    assert fitted is None
    assert transitions == []


def test_the_provenance_block_is_never_silent() -> None:
    """An absent field must never be mistakable for a false one, so the block is
    emitted either way and says which case it is."""
    unlocked = holdout.source_season_note(2023, CONFIG)
    assert unlocked["source_season_is_holdout"] is False
    assert unlocked["holdout_use"] is None
    assert unlocked["projection_source_season"] == 2023
    assert "holdout_seasons" in unlocked


def test_a_season_that_was_the_holdout_keeps_saying_so() -> None:
    """ADR 0012 consequence 4: the provenance survives the unlock.

    2025 is an ordinary season now, so `source_season_is_holdout` is False. A
    reader of a 2026 artifact built on 2025's ratings is still owed the history,
    so the block names the date it was scored and points at the scorecard. A
    silence here would be the quiet kind of dishonesty.
    """
    note = holdout.source_season_note(2025, CONFIG)
    assert note["source_season_is_holdout"] is False
    assert note["source_season_was_scored_holdout"] is True
    assert note["scored_on"] == "2026-08-15"
    assert "scored exactly once" in note["claim"]
    assert "2025-holdout-scorecard" in note["claim"]

    ordinary = holdout.source_season_note(2023, CONFIG)
    assert ordinary["source_season_was_scored_holdout"] is False
    assert ordinary["scored_on"] is None
