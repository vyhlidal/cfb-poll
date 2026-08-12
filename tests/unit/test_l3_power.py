"""L3: the blend, and the one thing that makes it legitimate.

Report 02 §3.3's whole instruction is "fit w1 and w2 on out-of-sample games
only". These tests check the arithmetic, and then check the ordering that makes
it out-of-sample - because the arithmetic is easy and the ordering is the part
that is easy to get silently wrong.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.plays import DEFAULT_ARCHIVE, load_plays, plays_for
from cfbpoll.ingest.sportsdataverse import load_games
from cfbpoll.model import design, l3_power, l4_resume

CONFIG = load_config()

pytestmark = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "pbp").exists(),
    reason="local archive not materialised; run `cfbpoll archive sync`",
)


@pytest.fixture(scope="module")
def games() -> pl.DataFrame:
    return load_games([2023], universe="model")


@pytest.fixture(scope="module")
def plays(games: pl.DataFrame) -> pl.DataFrame:
    return load_plays([2023])


@pytest.fixture(scope="module")
def walk(games: pl.DataFrame, plays: pl.DataFrame) -> dict[int, l3_power.L3Fit]:
    return l3_power.season_power(games, plays, 2023, CONFIG)


def test_blend_regression_has_no_intercept() -> None:
    """A zero differential at a neutral site must mean a zero expected margin.
    That is what "the points scale" means, and it is why h carries the whole site
    effect rather than sharing it with a constant."""
    eff = np.array([1.0, 2.0, 3.0, 4.0])
    res = np.array([0.0, 0.0, 0.0, 0.0])
    site = np.zeros(4)
    w = l3_power.fit_blend_weights(eff, res, site, 2.0 * eff, "test")
    assert w.w1 == pytest.approx(2.0)
    assert w.w2 == pytest.approx(0.0)
    assert w.home_field == pytest.approx(0.0)


def test_power_is_exactly_the_published_formula(walk: dict[int, l3_power.L3Fit]) -> None:
    """Power_t = w1*k*(alpha_t - beta_t) + w2*rho_t, and nothing else."""
    fitted = walk[max(walk)]
    for team in sorted(fitted.ratings)[:40]:
        expected = fitted.w1 * fitted.k * fitted.l1.net(team) + fitted.w2 * fitted.l2.rating(team)
        assert fitted.rating(team) == pytest.approx(expected, abs=1e-12)


def _power_difference(fitted: l3_power.L3Fit, sample: pl.DataFrame) -> np.ndarray:
    return np.array(
        [
            fitted.rating(h) - fitted.rating(a) + fitted.home_field * (0.0 if n else 1.0)
            for h, a, n in zip(
                sample["home_team"].to_list(),
                sample["away_team"].to_list(),
                sample["neutral_site"].to_list(),
                strict=True,
            )
        ]
    )


def test_the_prediction_is_the_power_difference_plus_home_field(
    walk: dict[int, l3_power.L3Fit], games: pl.DataFrame
) -> None:
    """m_hat = Power_h - Power_a + h*site. If this does not hold, the rating and
    the equation that defines it have come apart.

    The identity is asserted with `[margin.prediction_compression]` OFF, because
    since the tuning campaign of 2026-08-12 that transform is implemented and is
    applied to a FORECAST on its way out of `predict` (design.compress_prediction).
    The identity is a statement about the RATING; the compression is a statement
    about the forecast. Asserting the raw form here and the compressed form in the
    test below keeps the two claims separable, which is the lesson the independent
    review drew from the last set of tests that encoded a configurable policy
    (S13): assert the mechanism, and let the choice move freely.
    """
    fitted = walk[max(walk)]
    sample = games.head(50)
    off = {**CONFIG["margin"], "prediction_compression": {"enabled": False}}
    raw_config = {**CONFIG, "margin": off}
    raw = l3_power.L3Fit(
        ratings=fitted.ratings,
        weights=fitted.weights,
        k=fitted.k,
        l1=fitted.l1,
        l2=fitted.l2,
        config=raw_config,
    )
    assert np.allclose(raw.predict(sample), _power_difference(fitted, sample), atol=1e-10)


def test_prediction_compression_is_applied_to_the_forecast_when_enabled(
    walk: dict[int, l3_power.L3Fit], games: pl.DataFrame
) -> None:
    """`predict` returns the config's own published Pasteur transform of the
    Power difference - not some other compression, and not silently nothing.

    `[margin.prediction_compression]` was configured `true` and implemented
    NOWHERE in src/ until 2026-08-12 (independent review S9). This test is what
    stops it going back to being a comment.
    """
    fitted = walk[max(walk)]
    sample = games.head(200)
    enabled = {**CONFIG, "margin": {**CONFIG["margin"], "prediction_compression": {
        **CONFIG["margin"]["prediction_compression"], "enabled": True,
    }}}
    compressed = l3_power.L3Fit(
        ratings=fitted.ratings,
        weights=fitted.weights,
        k=fitted.k,
        l1=fitted.l1,
        l2=fitted.l2,
        config=enabled,
    )
    raw = _power_difference(fitted, sample)
    assert np.allclose(
        compressed.predict(sample), design.compress_prediction(raw, enabled), atol=1e-12
    )
    # It must actually bite on this sample, or the test proves nothing.
    assert np.any(np.abs(raw) > enabled["margin"]["prediction_compression"]["threshold"])
    assert np.all(np.abs(compressed.predict(sample)) <= np.abs(raw) + 1e-12)


def test_blend_weights_become_out_of_sample_and_stay_positive(
    walk: dict[int, l3_power.L3Fit],
) -> None:
    """The in-sample fallback fires only at the very start of a season, and once
    real out-of-sample games exist BOTH weights are positive.

    That second clause is the load-bearing one. Fitted in-sample on a full season
    the efficiency weight comes out NEGATIVE (w1 = -0.24 on 2023), because L2 has
    300 parameters on 1,200 games and fits its own training margins hard enough
    to make the blend use efficiency as a correction term. That is exactly the
    failure report 02 §3.3 legislates against, and it is why the ordering in
    walkforward.py and season_power matters more than the algebra.
    """
    settled = [f for f in walk.values() if f.weights.source == "out_of_sample"]
    assert len(settled) > 10
    for fitted in settled:
        assert fitted.w1 > 0.0, fitted.weights
        assert fitted.w2 > 0.0, fitted.weights
        assert fitted.home_field > 0.0, fitted.weights
    # Home field settles into the literature's band once the sample is real. The
    # first out-of-sample fits run on ~50 games and are wide (7 points in week 3
    # of 2023); by the published window they are not.
    mature = [f for f in settled if f.weights.n_games >= 300]
    assert len(mature) > 5
    for fitted in mature:
        assert 1.5 < fitted.home_field < 4.5, fitted.weights


def test_the_in_sample_fit_really_does_go_wrong(
    games: pl.DataFrame, plays: pl.DataFrame
) -> None:
    """The claim in the test above, made falsifiable rather than asserted."""
    fitted = l3_power.fit(games, plays_for(plays, games), CONFIG, state=None)
    assert fitted.weights.source == "training_window"
    assert fitted.w1 < 0.0


def test_a_game_joins_the_blend_sample_only_after_it_was_predicted(
    games: pl.DataFrame, plays: pl.DataFrame
) -> None:
    """THE OUT-OF-SAMPLE GUARANTEE, checked directly rather than by counting.

    Every row in the blend sample pairs a game's actual margin with features from
    a fit that had NOT seen that game. `season_power` gets that by construction -
    the fit live at bucket b-1 is the fit that predicted bucket b, because
    `games_through(b-1)` and `games_before(b)` are the same set of games - and
    this test replicates the walk and asserts the identity at every step.

    Note what is NOT claimed. The Power rating for data window K is allowed to
    use weights fitted on games inside K: K means "everything known through K",
    and bucket K's results are known through K. What must never happen is a
    weight informed by a game the paired fit had already seen, and that is what
    is checked here. The backtest harness has a stricter job - predicting bucket
    N with weights that have not seen bucket N at all - and does its own ordering
    in walkforward.py.
    """
    buckets = windows.season_buckets(games, 2023)
    fbs = (pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs")
    state = l3_power.SeasonState()
    previous = None
    for bucket in buckets:
        played = windows.games_in_bucket(games, bucket).filter(fbs)
        if previous is not None:
            before = windows.games_before(games, bucket, buckets)
            # the fit whose features are about to be stored saw exactly the games
            # BEFORE this bucket - never the ones it is being paired with
            assert previous.params["n_games"] == before.height, bucket.label
            assert set(played["game_id"].to_list()).isdisjoint(set(before["game_id"].to_list()))
            state.add(previous, played)
        window = windows.games_through(
            games, season=2023, week=bucket.week, season_type=bucket.season_type
        )
        previous = l3_power.fit(window, plays_for(plays, window), CONFIG, state=state)
    # bucket 0 never enters: nothing predicted it
    total_fbs = games.filter(fbs).height
    first = windows.games_in_bucket(games, buckets[0]).filter(fbs).height
    assert len(state) == total_fbs - first


def test_the_state_cache_cannot_return_a_stale_fit(
    games: pl.DataFrame, plays: pl.DataFrame
) -> None:
    """A different window, or a grown blend sample, is a different cache key."""
    state = l3_power.SeasonState()
    early = windows.games_through(games, season=2023, week=5, season_type="regular")
    late = windows.games_through(games, season=2023, week=10, season_type="regular")
    a = l3_power.fit(early, plays_for(plays, early), CONFIG, state=state)
    b = l3_power.fit(early, plays_for(plays, early), CONFIG, state=state)
    assert a is b  # same window, same sample -> the cached object
    c = l3_power.fit(late, plays_for(plays, late), CONFIG, state=state)
    assert c is not a
    state.add(a, windows.games_in_bucket(games, windows.season_buckets(games, 2023)[6]))
    d = l3_power.fit(early, plays_for(plays, early), CONFIG, state=state)
    assert d is not a  # the sample grew, so the weights may have moved


def test_power_from_l3_needs_no_rescaling(walk: dict[int, l3_power.L3Fit]) -> None:
    """The blend regression's response IS actual game margin, so Power is already
    in points and there is one fewer fitted constant between the résumé and the
    data than there was under L2 (report 02 §3.4)."""
    source = l3_power.power_source_for(walk[max(walk)])
    assert source.scale == 1.0
    assert source.source == "L3"
    assert source.l3 is not None
    params = source.as_params()
    assert params["w1_efficiency"] == walk[max(walk)].w1
    assert params["blend_weight_source"] in ("out_of_sample", "training_window")


def test_the_resume_reads_opponent_quality_off_l3_when_the_config_says_so(
    games: pl.DataFrame, plays: pl.DataFrame
) -> None:
    window = windows.games_through(games, season=2023, week=8, season_type="regular")
    source = l4_resume.power_source(window, CONFIG, plays=plays_for(plays, window))
    assert source.source == "L3"
    without = l4_resume.power_source(window, CONFIG, plays=None)
    assert without.source == "L2"  # graceful fallback, and it says so


def test_no_plays_degrades_to_the_results_core(games: pl.DataFrame) -> None:
    fitted = l3_power.fit(games, None, CONFIG)
    assert fitted.l1.n_plays == 0
    assert fitted.w1 * fitted.k * fitted.l1.net("Michigan") == 0.0
    assert fitted.rating("Michigan") == pytest.approx(fitted.w2 * fitted.l2.rating("Michigan"))
