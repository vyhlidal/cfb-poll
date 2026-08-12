"""configs/default.toml must parse, and must carry the constants the reports fix.

This is a real test and it passes today. It is deliberately about the values the
research pinned down (report 02 §3.1-§3.5, §4, §5.4), because a silent drift in
one of those is exactly the kind of change that should never happen unnoticed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "default.toml"


def load() -> dict:
    with CONFIG_PATH.open("rb") as fh:
        return tomllib.load(fh)


def test_config_parses() -> None:
    assert load()["meta"]["frozen"] is False


def test_margin_constants() -> None:
    """The two most contested constants, and the grids they were searched over.

    C and beta_w were the research report's starting values (24.0 / 3.0) until the
    hyperparameter campaign of 2026-08-12 fitted them on 2021-2023 and validated
    the choice once on 2024 (docs/adr/0007-tuned-constants.md). That campaign did
    NOT widen the grid when its optimum landed on C's upper bound - widening the
    net after seeing where the answer went is the failure a protocol exists to
    prevent - and it published the corner instead.

    CAMPAIGN 2 WIDENED IT, ONCE, UNDER PRE-REGISTRATION
    (docs/analysis/_campaign-2-protocol.md, committed before any number was read),
    and the grid now ends at `inf`: the identity response, the limit of the family,
    which is why this endpoint cannot move again for the same reason.
    """
    margin = load()["margin"]
    assert margin["c"] == 32.0  # FITTED, ADR 0007 (was 24.0, report 02 §3.2)
    assert margin["beta_w"] == 7.0  # FITTED, ADR 0007 (was 3.0, report 02 §3.2)
    assert min(margin["c_grid"]) == 18.0
    assert margin["c_grid"][-1] == float("inf")  # campaign 2: the uncompressed limit
    assert min(margin["beta_w_grid"]) == 0.0 and max(margin["beta_w_grid"]) == 12.0


def test_every_searched_constant_is_a_member_of_its_own_published_grid() -> None:
    """THE INVARIANT, which outlives any particular fitted value.

    A live constant outside the grid the config publishes for it would be a value
    no backtest ever scored - the search space and the answer have to be the same
    object. Asserting the mechanism rather than the choice is the lesson the
    independent review drew from the tests that broke when the headline ordering
    moved (S13): assert what must always hold, and let the choice move freely.
    """
    margin = load()["margin"]
    assert margin["c"] in margin["c_grid"]
    assert margin["beta_w"] in margin["beta_w_grid"]


def test_prediction_compression_is_implemented_and_its_state_is_deliberate() -> None:
    """`[margin.prediction_compression]` was configured `true` and implemented
    NOWHERE in src/ until 2026-08-12 (fresh-eyes review S9), so every published
    number was produced with it off while the config said on. It is implemented
    now, it was searched in all 416 cells, and it lost on the objective in 208 of
    208 paired cells - so the config says `false` and means it."""
    from cfbpoll.model import design

    pc = load()["margin"]["prediction_compression"]
    assert pc["enabled"] is False  # SEARCHED, ADR 0007 (was true and inert)
    assert pc["threshold"] == 21.0 and pc["alpha"] == 0.8
    assert callable(design.compress_prediction)


def test_resume_sigma() -> None:
    assert load()["resume"]["sigma"] == 15.3  # report 02 §3.4, §5.4


def test_garbage_time_thresholds() -> None:
    gt = load()["garbage_time"]["connelly"]  # Connelly's, report 02 §2.3
    assert [gt["q1"], gt["q2"], gt["q3"], gt["q4"]] == [43, 37, 29, 22]


def test_headline_starts_week_five() -> None:
    assert load()["publication"]["headline_start_week"] == 5  # report 02 §4


def test_headline_is_schedule_odds_with_resume_and_power_beside_it() -> None:
    """ADAPTED 2026-08-12, and this is the one assertion in the file whose truth
    genuinely changed rather than drifted.

    It previously asserted `headline_layer == "L4_resume"`, which was correct from
    commit 50f4058 until the owner's decision on the evidence of
    docs/analysis/headline-ordering-study.md (docs/adr/0005-headline-ordering.md).
    The shape of the assertion - the config names the headline, and the other two
    numbers are named beside it rather than dropped - is unchanged, and that is the
    part that was ever load-bearing. The résumé did not go away; it stopped
    sorting the table."""
    pub = load()["publication"]
    assert pub["headline_ordering"] == "schedule_odds"
    assert pub["headline_layer"] == "C_schedule_odds"
    assert pub["resume_layer"] == "L4_resume"
    assert pub["companion_layer"] == "L3_power"


def test_the_two_names_for_the_headline_cannot_drift_apart() -> None:
    """`headline_ordering` is what the code reads; `headline_layer` is what the
    artifacts print. Two names for one fact is a drift hazard, so publish/poll.py
    checks them on every run instead of trusting them (constraint 5)."""
    from cfbpoll.publish import poll as poll_mod

    cfg = load()
    assert poll_mod.headline_ordering(cfg) == cfg["publication"]["headline_ordering"]


def test_the_rejected_ordering_is_still_reachable() -> None:
    """A choice that cannot be switched back is not a choice. The résumé ordering
    lost on the evidence of the study; it did not stop being implemented."""
    from cfbpoll.publish import poll as poll_mod

    assert set(poll_mod.HEADLINE_ORDERINGS) == {"schedule_odds", "L4_resume"}


def test_q_ref_convention_and_its_sensitivity_set_are_published() -> None:
    """The ONE free constant in the headline ordering, and the alternatives the
    study measured it against (§9: tau >= 0.985 across a 16-point q_ref swing)."""
    odds = load()["schedule_odds"]
    assert odds["q_ref_method"] == "power_rank_25"
    assert odds["q_ref_sensitivity"][0] == "power_rank_25"
    assert set(odds["q_ref_sensitivity"]) == {
        "power_rank_25",
        "mean_top_25",
        "power_rank_10",
        "mean_fbs",
    }


def test_bootstrap_draws() -> None:
    assert load()["bootstrap"]["draws"] == 1000  # report 02 §3.3


def test_holdout_season_is_locked() -> None:
    backtest = load()["backtest"]
    assert backtest["holdout_seasons"] == [2025]  # single shot, report 02 §5.1
    assert backtest["holdout_locked"] is True


def test_constraints_are_enforced_by_default() -> None:
    c = load()["constraints"]
    assert c["fail_build_on_banned_feature"] is True
    assert c["allow_prior_season_data"] is False
    assert c["allow_conference_as_feature"] is False
    assert c["allow_third_party_ratings_as_features"] is False


def test_the_fit_universe_is_labelled_as_the_dial_it_is() -> None:
    """ADR 0006. `fit_universe` moves the ranking by more than `q_ref` does
    (Kendall's tau 0.9344 against the q_ref sweep's 0.985 floor), and until
    2026-08-12 it was argued from report 02 §3.7 and never measured. The value is
    unchanged - it won a rule fixed before the numbers were read - but a reader
    can now tell it was a choice, which was the fresh-eyes review's actual charge
    (S4)."""
    cfg = load()
    assert cfg["model"]["fit_universe"] == "model"
    text = CONFIG_PATH.read_text(encoding="utf-8")
    assert "THIS IS A DIAL, NOT A CONVENTION" in text
    assert "docs/adr/0006-fit-universe.md" in text
    # the G5 caveat is stated where the choice is made, not only in the analysis
    assert "favourable to G5 teams" in text


def test_sigma_is_a_fallback_and_a_floor_rather_than_the_live_value() -> None:
    """Review S6: 15.3 is the residual SD around a GOOD PUBLIC MODEL's prediction
    and this system's own walk-forward RMSE is 16.5, so the constant asserted a
    precision the model had not demonstrated - inside the denominator of every
    published win probability. It survives as what it is actually good for."""
    res = load()["resume"]
    assert res["sigma"] == 15.3  # report 02 §3.4, §5.4 - now the fallback and floor
    assert res["sigma_estimator"] == "walk_forward_residuals"
    assert res["sigma_min_out_of_sample_games"] == 40


def test_the_violations_gate_does_not_curate_its_rivals() -> None:
    """Review S1: the list named Colley and SRS and omitted win percentage, which
    beats every other system in the table. A gate whose rival list is drawn around
    the systems it clears is not a gate."""
    assert load()["gate"]["violations_must_beat"] == "all_scored_systems"


def test_the_accumulation_windows_are_cumulative_and_that_is_a_measured_choice() -> None:
    """Campaign 2's second lead searched trailing windows for both estimators.

    0 means "every out-of-sample game of the season so far", which is what has
    always run. Whatever the campaign found, the values here and the search that
    produced them have to be the same object - the invariant the review drew out
    of ADR 0007 - so this asserts the key EXISTS and is an integer, and leaves the
    choice free to move.
    """
    cfg = load()
    assert isinstance(cfg["resume"]["sigma_trailing_buckets"], int)
    assert isinstance(cfg["backtest"]["calibration_trailing_buckets"], int)
    assert cfg["resume"]["sigma_trailing_buckets"] >= 0
    assert cfg["backtest"]["calibration_trailing_buckets"] >= 0


def test_the_home_field_anchor_is_off_and_the_constraint_that_holds_it_off_is_on() -> None:
    """ADR 0008 IS OPEN. Campaign 2 ran the anchored h as a pre-registered
    experiment and the protocol said, before any number was read, that the config
    would not move whatever it showed - because anchoring h on earlier seasons
    would be this project's FIRST cross-season fitted quantity, and that is a
    question for the owner rather than for a search.

    This test is what makes that sentence enforceable. If the anchor is ever
    switched on, this test fails, and whoever switched it on has to say so in an
    ADR rather than in a diff.
    """
    cfg = load()
    assert cfg["homefield"]["anchor_h_by_season"] == {}
    assert cfg["homefield"]["anchor_provenance"] == "none"
    assert cfg["constraints"]["allow_prior_season_data"] is False


def test_every_fitted_quantity_is_still_within_season() -> None:
    """The premise campaign 2 had to correct on the record.

    It was said in the course of setting that campaign up that anchoring h across
    seasons would extend an existing precedent, because the EP layer already fits
    across seasons. It does not: `[ep].fit_scope` is "training_window", and
    `frozen_seasons` is an alternative the config names and no code path selects.
    There is no precedent to extend, and this test is here so the claim stays
    false-if-false rather than resting on somebody's memory of the config.
    """
    cfg = load()
    assert cfg["ep"]["fit_scope"] == "training_window"
    assert cfg["blend"]["fit_out_of_sample_only"] is True
