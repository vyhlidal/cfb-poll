"""Candidate ordering C: the exact Poisson-binomial, and the claims made for it.

Four things are asserted about this module in its own docstring and in
docs/analysis/headline-ordering-study.md, and each one is a test here:

  1. the tail is EXACT - it matches brute-force enumeration over all 2^n outcomes
     for every n <= 12, to machine precision;
  2. MARGIN NEVER ENTERS - perturb every final score while preserving every
     winner and not one published number moves;
  3. the ordering is INVARIANT to the zero point of the Power fit, under every
     rank-derived q_ref (and, as documented, not under `fixed`);
  4. UNBEATEN TEAMS ARE STRICTLY ORDERED by schedule, which is the exact thing
     the wins-based résumé cannot do because it saturates.

Plus the determinism the whole repository is built on: same input, same bits,
regardless of row order or how the sum is arranged.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import polars as pl
import pytest

from cfbpoll.config import load_config
from cfbpoll.model import l4_resume, schedule_odds

CONFIG = load_config()
SIGMA = float(CONFIG["resume"]["sigma"])


def frame(rows: list[tuple[str, str, int, int, bool]], classes: dict[str, str]) -> pl.DataFrame:
    """(home, away, home_points, away_points, neutral) -> a canonical game frame."""
    return pl.DataFrame(
        {
            "game_id": pl.Series(np.arange(len(rows)) + 1, dtype=pl.Int64),
            "season": pl.Series([2023] * len(rows), dtype=pl.Int32),
            "week": pl.Series([1] * len(rows), dtype=pl.Int32),
            "season_type": ["regular"] * len(rows),
            "game_type": ["regular"] * len(rows),
            "neutral_site": [r[4] for r in rows],
            "home_team": [r[0] for r in rows],
            "away_team": [r[1] for r in rows],
            "home_points": pl.Series([r[2] for r in rows], dtype=pl.Int32),
            "away_points": pl.Series([r[3] for r in rows], dtype=pl.Int32),
            "home_class": [classes[r[0]] for r in rows],
            "away_class": [classes[r[1]] for r in rows],
        }
    )


def power_source(ratings: dict[str, float], home_field: float = 2.5) -> l4_resume.PowerSource:
    return l4_resume.PowerSource(
        ratings=dict(sorted(ratings.items())),
        home_field=home_field,
        scale=1.0,
        source="test",
        version="test",
        scale_universe="test",
        n_scale_games=0,
    )


def round_robin(n_teams: int = 10, seed: int = 20260812) -> pl.DataFrame:
    """A connected double round-robin with a real strength gradient."""
    rng = np.random.Generator(np.random.PCG64(seed))
    teams = [f"T{i:02d}" for i in range(n_teams)]
    strength = np.linspace(18.0, -18.0, n_teams)
    rows = []
    for i in range(n_teams):
        for j in range(n_teams):
            if i == j:
                continue
            margin = strength[i] - strength[j] + 3.0 + rng.normal(0, 12)
            rows.append((teams[i], teams[j], int(round(21 + margin)), 21, False))
    return frame(rows, dict.fromkeys(teams, "fbs"))


# --------------------------------------------------- 1. exactness of the tail


def brute_force_pmf(probabilities: list[float]) -> np.ndarray:
    """P(W = k) by summing over ALL 2^n outcomes. The definition, run literally.

    Only usable for small n, which is exactly why it is the reference: the DP is
    the clever version and this is the one nobody can get subtly wrong.
    """
    n = len(probabilities)
    pmf = np.zeros(n + 1, dtype=np.float64)
    for outcome in itertools.product([0, 1], repeat=n):
        weight = 1.0
        for won, p in zip(outcome, probabilities, strict=True):
            weight *= p if won else (1.0 - p)
        pmf[sum(outcome)] += weight
    return pmf


@pytest.mark.parametrize("n", list(range(1, 13)))
def test_dp_matches_brute_force_enumeration(n: int) -> None:
    """report: 'exact O(n^2) dynamic program'. This is what exact has to mean."""
    rng = np.random.Generator(np.random.PCG64(1000 + n))
    for _ in range(5):
        p = rng.uniform(0.01, 0.99, size=n)
        dp = schedule_odds.poisson_binomial_pmf(p)
        bf = brute_force_pmf(p.tolist())
        assert dp.shape == bf.shape
        assert np.allclose(dp, bf, rtol=0.0, atol=1e-14)


@pytest.mark.parametrize("n", [1, 4, 8, 12])
def test_tail_matches_brute_force_enumeration(n: int) -> None:
    rng = np.random.Generator(np.random.PCG64(7000 + n))
    p = rng.uniform(0.05, 0.95, size=n)
    dp = schedule_odds.poisson_binomial_pmf(p)
    bf = brute_force_pmf(p.tolist())
    for k in range(n + 1):
        assert schedule_odds.tail_at_least(dp, k) == pytest.approx(float(np.sum(bf[k:])), abs=1e-14)
        assert schedule_odds.mid_p_at_least(dp, k) == pytest.approx(
            float(np.sum(bf[k:]) - 0.5 * bf[k]), abs=1e-14
        )


def test_pmf_is_a_distribution() -> None:
    rng = np.random.Generator(np.random.PCG64(11))
    for n in (1, 3, 15):
        pmf = schedule_odds.poisson_binomial_pmf(rng.uniform(0.0, 1.0, size=n))
        assert pmf.size == n + 1
        assert (pmf >= 0.0).all()
        assert math.fsum(pmf.tolist()) == pytest.approx(1.0, abs=1e-14)


def test_identical_probabilities_reduce_to_the_binomial() -> None:
    """The one case with a closed form. If this failed, nothing else would matter."""
    n, p = 13, 0.62
    pmf = schedule_odds.poisson_binomial_pmf([p] * n)
    for k in range(n + 1):
        expected = math.comb(n, k) * p**k * (1 - p) ** (n - k)
        assert pmf[k] == pytest.approx(expected, rel=1e-12)


def test_undefeated_tail_is_the_product_of_win_probabilities() -> None:
    p = [0.9, 0.8, 0.75, 0.95, 0.6]
    pmf = schedule_odds.poisson_binomial_pmf(p)
    assert schedule_odds.tail_at_least(pmf, len(p)) == pytest.approx(math.prod(p), rel=1e-12)


def test_tail_at_zero_wins_is_one() -> None:
    pmf = schedule_odds.poisson_binomial_pmf([0.3, 0.4, 0.5])
    assert schedule_odds.tail_at_least(pmf, 0) == pytest.approx(1.0, abs=1e-15)


# ------------------------------------------------------------- 2. determinism


def test_pmf_is_order_independent_to_machine_precision() -> None:
    """W is a sum, so its distribution cannot depend on the order of the games."""
    rng = np.random.Generator(np.random.PCG64(31))
    p = rng.uniform(0.05, 0.95, size=12)
    base = schedule_odds.poisson_binomial_pmf(p)
    for seed in range(5):
        shuffled = np.array(p)
        np.random.Generator(np.random.PCG64(seed)).shuffle(shuffled)
        assert np.allclose(schedule_odds.poisson_binomial_pmf(shuffled), base, atol=1e-15)


def test_fit_is_bit_identical_across_repeated_calls_and_row_order() -> None:
    games = round_robin()
    power = power_source({f"T{i:02d}": v for i, v in enumerate(np.linspace(18, -18, 10))})
    a = schedule_odds.fit(games, CONFIG, power=power)
    b = schedule_odds.fit(games.sample(fraction=1.0, shuffle=True, seed=5), CONFIG, power=power)
    assert a.tail == b.tail
    assert a.key == b.key
    assert a.mid_p == b.mid_p


# ------------------------------------------------- 3. margin never enters this module


def test_scores_may_change_freely_if_winners_do_not() -> None:
    """The central claim of candidate C, asserted rather than promised.

    Every winner is preserved; every margin is scrambled. The wins-based résumé
    is likewise unmoved (it counts wins), the MARGIN-AWARE résumé - candidate B -
    moves a great deal, and that contrast is the whole reason the study treats B
    and C as different answers rather than two flavours of one.
    """
    games = round_robin()
    power = power_source({f"T{i:02d}": v for i, v in enumerate(np.linspace(18, -18, 10))})

    rng = np.random.Generator(np.random.PCG64(99))
    margin = (games["home_points"] - games["away_points"]).to_numpy()
    scrambled = np.sign(margin) * rng.integers(1, 60, size=margin.size)
    perturbed = games.with_columns(
        home_points=pl.Series((21 + scrambled).astype(np.int32), dtype=pl.Int32),
        away_points=pl.Series(np.full(margin.size, 21, dtype=np.int32), dtype=pl.Int32),
    )

    base = schedule_odds.fit(games, CONFIG, power=power)
    moved = schedule_odds.fit(perturbed, CONFIG, power=power)
    assert base.tail == moved.tail
    assert base.key == moved.key
    assert base.expected_wins == moved.expected_wins

    b_base = l4_resume.fit(games, CONFIG, power=power)
    b_moved = l4_resume.fit(perturbed, CONFIG, power=power)
    assert b_base.resume == b_moved.resume  # wins-based résumé: also unmoved
    assert b_base.resume_margin != b_moved.resume_margin  # margin-aware: moves


# ----------------------------------------------------- 4. invariance and q_ref


@pytest.mark.parametrize("method", ["power_rank_25", "power_rank_10", "mean_top_25", "mean_fbs"])
def test_ordering_is_invariant_to_a_constant_shift_of_power(method: str) -> None:
    """Shift every Power rating and q_ref shifts with it, so no tail moves."""
    games = round_robin(n_teams=12)
    ratings = {f"T{i:02d}": float(v) for i, v in enumerate(np.linspace(20, -20, 12))}
    classes = dict.fromkeys(ratings, "fbs")

    base = schedule_odds.fit(
        games, CONFIG, power=power_source(ratings), classes=classes, q_ref_method=method
    )
    shifted_ratings = {t: v + 37.5 for t, v in ratings.items()}
    shifted = schedule_odds.fit(
        games, CONFIG, power=power_source(shifted_ratings), classes=classes, q_ref_method=method
    )
    assert base.q_ref.value + 37.5 == pytest.approx(shifted.q_ref.value, abs=1e-9)
    for team in base.tail:
        assert base.tail[team] == pytest.approx(shifted.tail[team], rel=1e-12)


def test_fixed_q_ref_is_documented_as_breaking_that_invariance() -> None:
    """`fixed` is offered so the choice is visible, not because it is safe."""
    games = round_robin(n_teams=12)
    ratings = {f"T{i:02d}": float(v) for i, v in enumerate(np.linspace(20, -20, 12))}
    classes = dict.fromkeys(ratings, "fbs")
    base = schedule_odds.fit(
        games, CONFIG, power=power_source(ratings), classes=classes, q_ref_method="fixed"
    )
    shifted = schedule_odds.fit(
        games,
        CONFIG,
        power=power_source({t: v + 37.5 for t, v in ratings.items()}),
        classes=classes,
        q_ref_method="fixed",
    )
    assert base.tail != shifted.tail


def test_q_ref_names_the_team_it_came_from() -> None:
    """Constraint 5: the one free constant is auditable against the same week's poll."""
    ratings = {f"T{i:02d}": float(30 - i) for i in range(40)}
    power = power_source(ratings)
    classes = dict.fromkeys(ratings, "fbs")
    q = schedule_odds.reference_quality(power, classes, method="power_rank_25")
    assert q.team == "T24"  # the 25th-best by Power
    assert q.value == pytest.approx(30.0 - 24)
    assert q.n_pool == 40

    mean_top = schedule_odds.reference_quality(power, classes, method="mean_top_25")
    assert mean_top.team is None
    assert mean_top.value == pytest.approx(float(np.mean([30.0 - i for i in range(25)])))


def test_q_ref_pool_is_fbs_only() -> None:
    ratings = {"A": 5.0, "B": 4.0, "C": 99.0}
    classes = {"A": "fbs", "B": "fbs", "C": "fcs"}
    q = schedule_odds.reference_quality(power_source(ratings), classes, method="power_rank_10")
    assert q.n_pool == 2
    assert q.team == "B"  # short pool degrades to the last team, and says so
    assert q.method == "power_rank_10_short_pool"


def test_unknown_q_ref_method_raises() -> None:
    with pytest.raises(ValueError, match="unknown q_ref method"):
        schedule_odds.reference_quality(power_source({"A": 1.0}), method="vibes")


# ------------------------------- 5. the property the résumé's saturation cannot have


def test_unbeaten_teams_are_strictly_ordered_by_schedule_difficulty() -> None:
    """The structural point of the whole study.

    Two 3-0 teams: one beat the three strongest opponents, one beat the three
    weakest. The wins-based résumé puts them both on the same published bound;
    candidate C separates them, and in the right direction.
    """
    classes = {t: "fbs" for t in ("Hard", "Soft", "A", "B", "C", "X", "Y", "Z")}
    rows = [
        ("Hard", "A", 21, 20, True),
        ("Hard", "B", 21, 20, True),
        ("Hard", "C", 21, 20, True),
        ("Soft", "X", 21, 20, True),
        ("Soft", "Y", 21, 20, True),
        ("Soft", "Z", 21, 20, True),
    ]
    games = frame(rows, classes)
    ratings = {
        "A": 20.0,
        "B": 18.0,
        "C": 16.0,
        "X": -16.0,
        "Y": -18.0,
        "Z": -20.0,
        "Hard": 0.0,
        "Soft": 0.0,
    }
    power = power_source(ratings, home_field=0.0)

    odds = schedule_odds.fit(games, CONFIG, power=power, classes=classes, q_ref_method="mean_fbs")
    assert odds.tail["Hard"] < odds.tail["Soft"]
    assert odds.key["Hard"] > odds.key["Soft"]

    resume = l4_resume.fit(games, CONFIG, power=power)
    assert resume.saturated["Hard"] == l4_resume.SATURATED_HIGH
    assert resume.saturated["Soft"] == l4_resume.SATURATED_HIGH
    assert resume.resume["Hard"] == resume.resume["Soft"]  # both on the bound


def test_winless_teams_are_separated_by_the_mid_p_tie_break() -> None:
    """The plain tail is exactly 1.0 for both; mid-p is what breaks it, correctly."""
    classes = {t: "fbs" for t in ("Hard", "Soft", "A", "B", "C", "X", "Y", "Z")}
    rows = [
        ("A", "Hard", 21, 20, True),
        ("B", "Hard", 21, 20, True),
        ("C", "Hard", 21, 20, True),
        ("X", "Soft", 21, 20, True),
        ("Y", "Soft", 21, 20, True),
        ("Z", "Soft", 21, 20, True),
    ]
    ratings = {
        "A": 20.0,
        "B": 18.0,
        "C": 16.0,
        "X": -16.0,
        "Y": -18.0,
        "Z": -20.0,
        "Hard": 0.0,
        "Soft": 0.0,
    }
    odds = schedule_odds.fit(
        frame(rows, classes),
        CONFIG,
        power=power_source(ratings, home_field=0.0),
        classes=classes,
        q_ref_method="mean_fbs",
    )
    assert odds.tail["Hard"] == pytest.approx(1.0, abs=1e-15)
    assert odds.tail["Soft"] == pytest.approx(1.0, abs=1e-15)
    assert odds.mid_p["Hard"] < odds.mid_p["Soft"]  # 0-3 vs the best is less damning
    assert odds.order_key("Hard") < odds.order_key("Soft")


def test_a_harder_schedule_at_equal_record_always_ranks_higher() -> None:
    """Stochastic dominance: no q_ref choice can invert this one."""
    for method in ("power_rank_25", "mean_top_25", "power_rank_10", "mean_fbs"):
        classes = {t: "fbs" for t in ("Hard", "Soft", "A", "B", "C", "X", "Y", "Z")}
        rows = [
            ("Hard", "A", 21, 20, True),
            ("Hard", "B", 21, 20, True),
            ("Hard", "C", 20, 21, True),
            ("Soft", "X", 21, 20, True),
            ("Soft", "Y", 21, 20, True),
            ("Soft", "Z", 20, 21, True),
        ]
        ratings = {
            "A": 20.0,
            "B": 18.0,
            "C": 16.0,
            "X": -16.0,
            "Y": -18.0,
            "Z": -20.0,
            "Hard": 0.0,
            "Soft": 0.0,
        }
        odds = schedule_odds.fit(
            frame(rows, classes),
            CONFIG,
            power=power_source(ratings, home_field=0.0),
            classes=classes,
            q_ref_method=method,
        )
        assert odds.wins["Hard"] == odds.wins["Soft"] == 2
        assert odds.tail["Hard"] < odds.tail["Soft"], method


# --------------------------------------------------------------- 6. the plumbing


def test_home_field_moves_the_probability_the_right_way() -> None:
    """Beating the same opponent on the road is less likely, hence more impressive."""
    p_home = schedule_odds.win_probabilities(10.0, [10.0], [1], 3.0, SIGMA)
    p_away = schedule_odds.win_probabilities(10.0, [10.0], [-1], 3.0, SIGMA)
    p_neutral = schedule_odds.win_probabilities(10.0, [10.0], [0], 3.0, SIGMA)
    assert float(p_away[0]) < float(p_neutral[0]) < float(p_home[0])
    assert float(p_neutral[0]) == pytest.approx(0.5)


def test_expected_wins_agrees_with_the_resume_layer() -> None:
    """C's E[W] at q_ref must be L4's E[W|q] at q = q_ref. Same mu, same sigma."""
    opponents = [12.0, -3.0, 8.0, 0.5, -14.0]
    sites = [1, -1, 0, 1, -1]
    _, _, expected = schedule_odds.schedule_odds(3, opponents, sites, 6.0, 2.5, SIGMA)
    assert expected == pytest.approx(
        l4_resume.expected_wins(6.0, opponents, sites, 2.5, SIGMA), rel=1e-12
    )


def test_empty_window_returns_an_empty_fit() -> None:
    games = round_robin()
    power = power_source({f"T{i:02d}": v for i, v in enumerate(np.linspace(18, -18, 10))})
    fitted = schedule_odds.fit(games, CONFIG, power=power, resume_games=games.head(0))
    assert fitted.tail == {}
    assert fitted.params["n_record_games"] == 0


def test_odds_frame_ranks_fbs_only_and_is_sorted_by_the_key() -> None:
    classes = {"A": "fbs", "B": "fbs", "F": "fcs"}
    rows = [("A", "F", 40, 3, False), ("B", "F", 40, 3, False), ("A", "B", 30, 10, False)]
    games = frame(rows, classes)
    fitted = schedule_odds.fit(
        games, CONFIG, power=power_source({"A": 5.0, "B": 3.0, "F": -25.0}), classes=classes
    )
    table = schedule_odds.odds_frame(fitted, classes)
    assert table.filter(pl.col("team_class") == "fcs")["rank"].to_list() == [None]
    fbs = table.filter(pl.col("team_class") == "fbs")
    assert fbs["rank"].to_list() == [1, 2]
    assert fbs["odds_key"].to_list() == sorted(fbs["odds_key"].to_list(), reverse=True)


def test_record_window_and_power_window_can_differ() -> None:
    """The retroactive substitution: Power from K, record from N. One argument."""
    games = round_robin()
    power = power_source({f"T{i:02d}": v for i, v in enumerate(np.linspace(18, -18, 10))})
    early = games.head(30)
    live = schedule_odds.fit(early, CONFIG, power=power)
    hindsight = schedule_odds.fit(games, CONFIG, power=power, resume_games=early)
    assert live.tail == hindsight.tail  # same Power, same window -> same answer
    assert live.params["n_record_games"] == 30
    assert hindsight.params["n_record_games"] == 30


def test_key_is_minus_log10_of_the_tail() -> None:
    games = round_robin()
    power = power_source({f"T{i:02d}": v for i, v in enumerate(np.linspace(18, -18, 10))})
    fitted = schedule_odds.fit(games, CONFIG, power=power)
    for team, tail in fitted.tail.items():
        assert fitted.key[team] == pytest.approx(-math.log10(tail), rel=1e-12)


def test_as_params_publishes_q_ref_and_the_method() -> None:
    games = round_robin()
    power = power_source({f"T{i:02d}": v for i, v in enumerate(np.linspace(18, -18, 10))})
    classes = dict.fromkeys(power.ratings, "fbs")
    params = schedule_odds.fit(games, CONFIG, power=power, classes=classes).as_params()
    assert params["q_ref_method"].startswith("power_rank_25")
    assert "q_ref" in params and "q_ref_team" in params
    assert params["tail_method"] == "exact_poisson_binomial_dp"
    assert params["ranking_key"].startswith("-log10(P(W >= W_t))")
