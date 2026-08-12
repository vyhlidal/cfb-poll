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
    margin = load()["margin"]
    assert margin["c"] == 24.0  # compression scale, report 02 §3.2
    assert margin["beta_w"] == 3.0  # win premium, report 02 §3.2
    assert min(margin["c_grid"]) == 18.0 and max(margin["c_grid"]) == 32.0
    assert min(margin["beta_w_grid"]) == 0.0 and max(margin["beta_w_grid"]) == 8.0


def test_resume_sigma() -> None:
    assert load()["resume"]["sigma"] == 15.3  # report 02 §3.4, §5.4


def test_garbage_time_thresholds() -> None:
    gt = load()["garbage_time"]["connelly"]  # Connelly's, report 02 §2.3
    assert [gt["q1"], gt["q2"], gt["q3"], gt["q4"]] == [43, 37, 29, 22]


def test_headline_starts_week_five() -> None:
    assert load()["publication"]["headline_start_week"] == 5  # report 02 §4


def test_headline_is_resume_with_power_beside_it() -> None:
    pub = load()["publication"]
    assert pub["headline_layer"] == "L4_resume"
    assert pub["companion_layer"] == "L3_power"


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
