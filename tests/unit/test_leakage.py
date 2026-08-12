"""The feature audit, tested the way the audit itself works: by planting things.

Report 02 §3.10's promise is that no banned input can reach a design matrix. A
test that only asserts the clean pipeline is clean would pass equally well
against an audit that returned `True` unconditionally, so the load-bearing tests
here are the ones that break the pipeline on purpose:

  * plant a banned column into the frame and have a layer genuinely consume it -
    the audit must name it and `--fail-on-banned` must exit non-zero;
  * plant it and have NO layer consume it - the audit must pass, and say the
    column was present, because a warning that fires on a column nobody read
    would train a reader to ignore the audit.
"""

from __future__ import annotations

from typing import Any

import polars as pl
import pytest
from typer.testing import CliRunner

from cfbpoll.cli import app
from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.plays import load_plays
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games
from cfbpoll.model import design
from cfbpoll.validate import leakage

runner = CliRunner()

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
def plays() -> pl.DataFrame:
    return load_plays([2023])


def test_every_layer_consumes_only_its_allow_list(
    window: pl.DataFrame, plays: pl.DataFrame
) -> None:
    """The whole pipeline, rebuilt from its allow-lists, bit for bit.

    This is the audit's positive result and it is a measurement rather than an
    assertion: every design matrix was rebuilt from a frame containing ONLY the
    allow-listed columns and came out identical."""
    report = leakage.audit(window, plays, CONFIG)
    assert report.passed, report.violations
    names = [layer.layer for layer in report.layers]
    assert names == [spec.name for spec in leakage.LAYERS]
    for layer in report.layers:
        assert layer.skipped is None, layer.layer
        assert layer.identical, layer.layer
        assert layer.consumed_outside_allow_list == (), layer.layer


def test_conference_identity_is_in_the_frame_and_provably_never_consumed(
    window: pl.DataFrame,
) -> None:
    """`conference_game` survives the loader's projection (the 2021 structural
    conference-championship fallback needs it) and matches the banned pattern
    `conference`. Every run therefore rebuilds every design matrix without it and
    gets the same bytes - which is what turns "we do not use conference identity"
    from a claim into a result."""
    assert "conference_game" in window.columns
    report = leakage.audit(window, None, CONFIG)
    fitted = {layer.layer: layer for layer in report.layers if layer.layer in ("L2", "L4")}
    for layer in fitted.values():
        assert "conference_game" in layer.banned_present
        assert "conference_game" not in layer.consumed_outside_allow_list
        assert layer.identical
    assert report.passed


def test_a_planted_banned_column_that_reaches_the_design_matrix_is_caught(
    window: pl.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE TEST THE AUDIT EXISTS FOR. `home_pregame_elo` is a real column in the
    shipped schedule file and a banned input (report 01 §5.6). Here L2 is made to
    actually consume it - the response picks up a multiple of it - and the audit
    must notice, name it, and refuse to pass."""
    real = design.build_game_design

    def leaky(games: pl.DataFrame, config: dict[str, Any], teams: Any = None) -> Any:
        built = real(games, config, teams=teams)
        if "home_pregame_elo" in games.columns:
            contaminated = built.s + 0.001 * games.sort("game_id")["home_pregame_elo"].to_numpy()
            return design.GameDesign(
                Z=built.Z,
                s=contaminated,
                v=built.v,
                teams=built.teams,
                penalty=built.penalty,
                game_ids=built.game_ids,
            )
        return built

    monkeypatch.setattr(design, "build_game_design", leaky)

    planted = window.with_columns(
        home_pregame_elo=pl.Series(
            [1500.0 + i for i in range(window.height)], dtype=pl.Float64
        )
    )
    report = leakage.audit(planted, None, CONFIG)
    l2 = next(layer for layer in report.layers if layer.layer == "L2")
    assert l2.consumed_outside_allow_list == ("home_pregame_elo",)
    assert l2.banned_consumed == ("home_pregame_elo",)
    assert not l2.identical
    assert not report.passed
    assert any("home_pregame_elo" in v for v in report.violations)

    with pytest.raises(leakage.BannedFeature):
        leakage.audit(planted, None, CONFIG, fail_on_banned=True)


def test_a_planted_column_nobody_reads_is_reported_and_does_not_fail(
    window: pl.DataFrame,
) -> None:
    """The other half, and it matters as much. A banned column sitting unread in
    the frame is the NORMAL state of this archive; if the audit failed on
    presence it would fail on every run and stop meaning anything. It is reported
    against the loader's own allow-list - which is a containment check, because a
    loader has no design matrix - and the fitted layers prove it unconsumed."""
    planted = window.with_columns(excitement_index=pl.lit(0.5))
    report = leakage.audit(planted, None, CONFIG)
    for name in ("L2", "L4", "schedule_odds"):
        layer = next(x for x in report.layers if x.layer == name)
        assert "excitement_index" in layer.banned_present
        assert layer.consumed_outside_allow_list == ()
        assert layer.identical


def test_the_ep_table_carries_no_team_dimension(window: pl.DataFrame, plays: pl.DataFrame) -> None:
    """EP reads the possession labels to SIGN the next score, which report 02
    §3.10's summary sentence ("not the teams") does not admit. The property that
    actually matters is asserted directly instead: the fitted table is indexed
    (down, distance bucket, yards-to-goal) and by nothing else, so no team
    identity can survive into a play value."""
    from cfbpoll.ingest.plays import plays_for
    from cfbpoll.model import ep

    joined = plays_for(plays, window)
    model = ep.fit(joined, CONFIG)
    edges = len(CONFIG["ep"]["distance_buckets"])
    assert model.table.shape == (4, edges + 2, ep.MAX_YARDS_TO_GOAL)
    assert "offense" in leakage.ALLOWED_BY_LAYER["EP"]
    assert leakage.EP_TEAM_LABELS_NOTE in dict(
        next(s for s in leakage.LAYERS if s.name == "EP").allowed
    ).values()


def test_every_allow_listed_column_carries_a_reason() -> None:
    """Constraint 5 applied to the audit itself: a bare list of column names is
    not a justification, and an allow-list nobody can read is one edit away from
    growing an entry nobody notices."""
    for spec in leakage.LAYERS:
        assert spec.allowed, spec.name
        for column, reason in spec.allowed.items():
            assert isinstance(reason, str) and len(reason) > 10, (spec.name, column)
        assert spec.spec


def test_the_banned_pattern_list_covers_what_the_archive_actually_ships() -> None:
    """The columns report 01 §5.6 names, checked against the pattern list rather
    than trusted to it. `our_ep_before` is OURS and must not match, which is the
    one exemption in the module and the reason it is spelled out there."""
    shipped = [
        "EPA",
        "ppa",
        "wpa",
        "wp_before",
        "ep_after",
        "home_pregame_elo",
        "home_postgame_elo",
        "excitement_index",
        "spread",
        "over_under",
        "ExpScoreDiff",
        "conference_game",
    ]
    assert set(leakage.banned_hits(shipped)) == set(shipped)
    assert leakage.banned_hits(["our_ep_before", "our_ep_after", "play_value"]) == ()


def test_the_cli_fails_the_build_on_a_banned_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--fail-on-banned` must really exit non-zero. Both workflows pass it and
    docs/constraints.md says it is the enforcement; if it exits 0 on a violation
    the whole claim is decorative."""
    real = leakage.audit

    def failing(*args: Any, **kwargs: Any) -> Any:
        report = real(*args, **kwargs)
        report.violations.append("planted: L2 consumes home_pregame_elo")
        return report

    monkeypatch.setattr(leakage, "audit", failing)
    result = runner.invoke(
        app,
        ["audit-features", "--season", "2023", "--through-week", "3", "--fail-on-banned"],
    )
    assert result.exit_code == 1, result.output
    assert "VIOLATION" in result.output

    monkeypatch.setattr(leakage, "audit", real)
    clean = runner.invoke(app, ["audit-features", "--season", "2023", "--through-week", "3"])
    assert clean.exit_code == 0, clean.output
    assert "PASS" in clean.output
