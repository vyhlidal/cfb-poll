"""The parametric bootstrap and the ridge sandwich.

Two objects, two different questions, and the tests keep them apart:

  * the SANDWICH answers "how precisely is this rating pinned down", conditional
    on the observed results, and is what makes a matched-units statement like
    "James Madison minus Michigan is 8.6 +/- 2.7 points" computable;
  * the BOOTSTRAP answers "how far would this RANK move if the season were
    replayed", which is a function of every team's rating at once and of the
    record, and is the number that goes on the poll.

The load-bearing test in this file is the last one: the scheme report 02 §3.3
specified is run, and its own output disqualifies it.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from scipy import sparse

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.plays import load_plays
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games
from cfbpoll.model import bootstrap, l4_resume, retro, ridge, schedule_odds
from cfbpoll.publish import poll as poll_mod

CONFIG = load_config()

needs_archive = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised",
)

DRAWS = 60  # enough to exercise every path; the published run is [bootstrap].draws


@pytest.fixture(scope="module")
def fitted() -> tuple[pl.DataFrame, l4_resume.PowerSource, dict[str, str]]:
    games = load_games([2023], universe="model")
    plays = load_plays([2023])
    buckets = windows.season_buckets(games, 2023)
    powers = retro.season_power(games, 2023, CONFIG, plays=plays, buckets=buckets)
    evaluated = next(b for b in buckets if b.season_type == "regular" and b.week == 10)
    window = windows.games_through(games, season=2023, week=10, season_type="regular")
    return window, powers[evaluated.order], poll_mod.team_classes(games)


# --------------------------------------------------------------------- the sandwich


def test_the_sandwich_recovers_a_known_covariance_on_ordinary_least_squares() -> None:
    """With lambda = 0 and unit weights the sandwich collapses to the textbook
    OLS covariance sigma^2 (ZᵀZ)^-1, which is a check the formula can fail."""
    rng = np.random.Generator(np.random.PCG64(20260812))
    z = sparse.csr_matrix(rng.normal(size=(200, 4)))
    beta = np.array([1.0, -2.0, 0.5, 3.0])
    y = z @ beta + rng.normal(scale=2.0, size=200)
    w = np.ones(200)
    penalty = np.zeros(4)

    theta = ridge.solve(z, y, w, penalty, 0.0)
    result = ridge.sandwich(z, y, w, penalty, 0.0, theta)

    dense = np.asarray(z.todense())
    textbook = result.residual_variance * np.linalg.inv(dense.T @ dense)
    assert np.allclose(result.cov, textbook, rtol=1e-8)
    assert result.effective_df == pytest.approx(4.0)
    assert result.residual_variance == pytest.approx(4.0, rel=0.25)


def test_shrinkage_costs_less_than_a_free_parameter() -> None:
    """The ridge effective degrees of freedom is strictly below the column count
    and falls as the penalty rises. That is the whole reason `sigma^2` uses it
    rather than `n - p`."""
    rng = np.random.Generator(np.random.PCG64(7))
    z = sparse.csr_matrix(rng.normal(size=(120, 8)))
    y = rng.normal(size=120)
    w = np.ones(120)
    penalty = np.ones(8)
    edfs = [
        ridge.sandwich(z, y, w, penalty, lam, ridge.solve(z, y, w, penalty, lam)).effective_df
        for lam in (0.0, 1.0, 10.0, 100.0)
    ]
    assert edfs[0] == pytest.approx(8.0)
    assert edfs[0] > edfs[1] > edfs[2] > edfs[3]


def test_a_difference_standard_error_is_not_the_two_added_in_quadrature() -> None:
    """Var(a - b) = Var(a) + Var(b) - 2Cov(a, b), and the covariance term is the
    point: two teams that share opponents share estimation error, so the SE of
    their difference is materially smaller than quadrature would say. A page that
    published only per-team bars and let a reader add them would overstate the
    uncertainty of every comparison it is actually making."""
    cov = np.array([[4.0, 3.0], [3.0, 4.0]])
    assert ridge.difference_se(cov, 0, 1) == pytest.approx(np.sqrt(2.0))
    quadrature = np.sqrt(cov[0, 0] + cov[1, 1])
    assert ridge.difference_se(cov, 0, 1) < quadrature


@needs_archive
def test_every_power_rating_carries_a_standard_error_in_points(fitted) -> None:
    """Per team, per week, on the published row (report 02 §3.3). The scale is
    what carries a compressed-response error onto points, and with Power = L3
    that is `w2` - which the artifact states, because an error bar whose scope is
    unstated is worse than none."""
    _, power, _ = fitted
    assert power.se_scale != 0.0
    assert "LOWER BOUND" in power.se_note
    for team in ("Michigan", "James Madison", "Ohio State"):
        se = power.rating_se(team)
        assert se is not None and 0.0 < se < 10.0

    # the review's §4b finding, reproduced: the SE of a rating DIFFERENCE is
    # essentially uniform across pair types, so connectivity is not the binding
    # constraint on a G5-versus-P4 comparison
    within = power.difference_se("Michigan", "Penn State")
    across = power.difference_se("James Madison", "Michigan")
    assert within is not None and across is not None
    assert 0.7 < across / within < 1.4


# --------------------------------------------------------------------- the bootstrap


@needs_archive
def test_the_bootstrap_is_deterministic_and_independent_of_draw_count(fitted) -> None:
    """SeedSequence.spawn, per report 03 §9.3 item 2: draw i's stream depends on
    (root seed, i) and nothing else. So the same seed gives the same answer, and
    the first N draws of a 2N-draw run are the first N draws of an N-draw run -
    which is what "identical on 1 core or 16" actually requires."""
    window, power, classes = fitted
    a = bootstrap.run(window, power, CONFIG, classes=classes, draws=20, seed=1234)
    b = bootstrap.run(window, power, CONFIG, classes=classes, draws=20, seed=1234)
    for name in bootstrap.ORDERINGS:
        assert np.array_equal(a.rank[name], b.rank[name])
    assert np.array_equal(a.power, b.power)

    longer = bootstrap.run(window, power, CONFIG, classes=classes, draws=40, seed=1234)
    assert np.array_equal(longer.rank["schedule_odds"][:20], a.rank["schedule_odds"])

    different = bootstrap.run(window, power, CONFIG, classes=classes, draws=20, seed=99)
    assert not np.array_equal(different.rank["schedule_odds"], a.rank["schedule_odds"])


@needs_archive
def test_the_bootstrap_ranks_by_the_published_ordering_rule(fitted) -> None:
    """A second implementation of the ordering would let a bootstrap rank drift
    away from a published rank without anyone noticing, and nothing would catch
    it: both numbers would look plausible.

    So the bootstrap's ranking function is applied to the REAL fits and required
    to reproduce the ranks `publish/poll.py::order_by` produces from the same
    fits - including the tie-breaks, which is where a re-implementation goes
    wrong first. The headline breaks ties on mid-p (only ever among winless
    teams) and the résumé on the margin-aware variant (only ever among unbeaten
    ones), and a bootstrap that ignored either would silently disagree with the
    poll for exactly the teams the poll is argued about."""
    window, power, classes = fitted
    odds = schedule_odds.fit(window, CONFIG, power=power, classes=classes)
    resume = l4_resume.fit(window, CONFIG, power=power)
    ranked = tuple(sorted(t for t in power.ratings if classes.get(t, "fbs") == "fbs"))

    published = poll_mod.order_by(
        schedule_odds.odds_frame(odds, classes).filter(pl.col("rank").is_not_null()),
        "schedule_odds",
    )
    expected = {row["team"]: i + 1 for i, row in enumerate(published.iter_rows(named=True))}
    got = bootstrap._ranks(
        {t: (odds.tail[t], odds.mid_p[t]) for t in odds.tail}, ranked, descending=False, width=2
    )
    assert {team: int(got[i]) for i, team in enumerate(ranked)} == expected

    published_resume = poll_mod.order_by(
        l4_resume.resume_frame(resume, classes).filter(pl.col("rank").is_not_null()),
        "L4_resume",
    )
    expected_resume = {
        row["team"]: i + 1 for i, row in enumerate(published_resume.iter_rows(named=True))
    }
    got_resume = bootstrap._ranks(
        {t: (resume.resume[t], resume.resume_margin[t]) for t in resume.resume},
        ranked,
        descending=True,
        width=2,
    )
    assert {team: int(got_resume[i]) for i, team in enumerate(ranked)} == expected_resume


@needs_archive
def test_intervals_are_integers_and_contain_the_median(fitted) -> None:
    """A rank is a count of teams. "Ranked 4th, 90% interval 3.7th to 51.2nd" is a
    category error, so the percentile interpolation is lower/higher and the bounds
    stay integral."""
    window, power, classes = fitted
    draws = bootstrap.run(window, power, CONFIG, classes=classes, draws=DRAWS, seed=11)
    table = bootstrap.intervals(draws, 0.90)
    assert table.height == len(draws.teams)
    for name in bootstrap.ORDERINGS:
        lo = table[f"{name}_rank_lo"].to_numpy()
        hi = table[f"{name}_rank_hi"].to_numpy()
        median = table[f"{name}_rank_median"].to_numpy()
        assert lo.dtype.kind == "i" and hi.dtype.kind == "i"
        assert (lo <= median).all() and (median <= hi).all()
        assert (lo >= 1).all() and (hi <= len(draws.teams)).all()


@needs_archive
def test_the_bootstrap_median_is_worse_than_the_published_rank_for_unbeaten_teams(
    fitted,
) -> None:
    """The property that will surprise a reader, pinned so it is never mistaken
    for a bug. The headline ordering ranks teams by how improbable their record
    was; a record that is improbable is one that most simulated seasons do not
    repeat. 2023 James Madison is #4 with nine wins the model thought unlikely,
    and its bootstrap median is deep in the twenties."""
    window, power, classes = fitted
    draws = bootstrap.run(window, power, CONFIG, classes=classes, draws=200, seed=20260812)
    table = bootstrap.intervals(draws, 0.90)
    jmu = table.filter(pl.col("team") == "James Madison").to_dicts()[0]
    assert jmu["schedule_odds_rank_median"] > 15
    assert jmu["schedule_odds_rank_hi"] > 40
    assert 0.05 < bootstrap.probability_within(draws, "James Madison", 10, "schedule_odds") < 0.45
    # and the interval is wide for everyone, which is the finding, not an artefact
    widths = (
        table["schedule_odds_rank_hi"] - table["schedule_odds_rank_lo"]
    ).to_numpy()
    assert float(np.median(widths)) > 20


# --------------------------------------------------- the scheme that was specified


@needs_archive
def test_the_naive_resample_scheme_is_disqualified_by_its_own_output(fitted) -> None:
    """THE TEST THE REVIEW ASKED FOR (S3). Report 02 §3.3's parenthetical said
    "resample games with replacement, refit". Games are edges in the schedule
    graph, so that scheme can disconnect the graph or leave a team with no games
    at all - destroying exactly the connectivity whose uncertainty was being
    measured. The review's instruction was to report the fraction of draws in
    which that happens and, if it is materially above zero, treat the scheme as
    disqualified on its own output.

    It is essentially every draw."""
    window, _, _ = fitted
    report = bootstrap.naive_resample_diagnostic(window, draws=50, seed=4)
    assert report["fraction_broken_either_way"] > 0.9
    assert report["fraction_with_a_team_that_lost_every_game"] > 0.9
    assert "INVALID" in report["verdict"]
    # and nothing on a publication path calls it
    assert "naive" not in bootstrap.ORDERINGS
