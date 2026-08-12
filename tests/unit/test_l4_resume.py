"""L4 résumé: the root-solve, its edge cases, and the retroactive substitution.

Report 02 §3.4 states four things as facts, and each one is a test here: E[W|q]
is strictly increasing and continuous; the root is unique where it exists; the
résumé depends on opponent quality ONLY through Power; and the margin-aware
variant answers a different question from the wins-based one.

The fifth fact is not in the report and is the interesting one: E[W|q] has no
root at all for an undefeated or winless team. That is Bradley-Terry separation
(report 02 §2.10) and the bracket is the regularization, so the behaviour at the
bound is specified and tested rather than discovered in production.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from cfbpoll.config import load_config
from cfbpoll.model import design, l4_resume

CONFIG = load_config()
SIGMA = float(CONFIG["resume"]["sigma"])
Q_LO, Q_HI = (float(x) for x in CONFIG["resume"]["q_bounds"])
C = float(CONFIG["margin"]["c"])
BETA_W = float(CONFIG["margin"]["beta_w"])


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


# ------------------------------------------------------------------- monotonicity


def test_expected_wins_is_strictly_increasing_in_q() -> None:
    """report 02 §3.4: this is what makes the root unique and bisection valid."""
    power = [10.0, -4.0, 22.0, 0.0, 7.5, -18.0]
    sites = [1, -1, 0, 1, -1, 0]
    grid = np.linspace(Q_LO, Q_HI, 601)
    values = np.array([l4_resume.expected_wins(q, power, sites, 2.8, SIGMA) for q in grid])
    assert np.all(np.diff(values) > 0)
    assert values[0] > 0.0 and values[-1] < len(power)


def test_expected_wins_is_bounded_by_the_schedule_length() -> None:
    power = [5.0] * 13
    sites = [0] * 13
    assert l4_resume.expected_wins(-1e6, power, sites, 2.8, SIGMA) == pytest.approx(0.0)
    assert l4_resume.expected_wins(1e6, power, sites, 2.8, SIGMA) == pytest.approx(13.0)


def test_expected_margin_is_strictly_increasing_and_bounded_by_c_plus_beta() -> None:
    power = [10.0, -4.0, 22.0, 0.0]
    sites = [1, -1, 0, 1]
    grid = np.linspace(Q_LO, Q_HI, 241)
    values = np.array(
        [
            l4_resume.expected_compressed_margin(q, power, sites, 2.8, SIGMA, C, BETA_W, 20)
            for q in grid
        ]
    )
    assert np.all(np.diff(values) > 0)
    assert abs(values[-1]) < len(power) * (C + BETA_W)


# ------------------------------------------------------------------ the root-solve


def test_the_root_is_the_root() -> None:
    """Solve, then evaluate: E[W|q*] must be the actual win total."""
    power = [12.0, 3.0, -6.0, 20.0, 1.0, -11.0, 8.0]
    sites = [1, 1, -1, 0, -1, 1, 0]
    for target in (1.0, 2.5, 4.0, 6.0):
        q, saturated = l4_resume.solve_quality(target, power, sites, 2.8, SIGMA, (Q_LO, Q_HI), 60)
        assert saturated == l4_resume.SATURATED_NONE
        assert l4_resume.expected_wins(q, power, sites, 2.8, SIGMA) == pytest.approx(
            target, abs=1e-9
        )


def test_the_root_is_reproducible() -> None:
    """Bit-for-bit, twice, and through both the scalar and the batch path."""
    games = round_robin()
    first = l4_resume.fit(games, CONFIG)
    second = l4_resume.fit(games, CONFIG)
    assert first.resume == second.resume
    assert first.resume_margin == second.resume_margin
    assert first.power.ratings == second.power.ratings


def test_batch_solver_agrees_with_the_scalar_reference() -> None:
    """The vectorised bisection and report 02 §3.4's plain implementation are one
    estimator. If they diverge, the fast path is not the documented one."""
    games = round_robin()
    fitted = l4_resume.fit(games, CONFIG)
    h = fitted.power.home_field

    for team in fitted.teams[:4]:
        home = games.filter(pl.col("home_team") == team)
        away = games.filter(pl.col("away_team") == team)
        power = [fitted.power.rating(t) for t in home["away_team"].to_list()] + [
            fitted.power.rating(t) for t in away["home_team"].to_list()
        ]
        sites = [0 if n else 1 for n in home["neutral_site"].to_list()] + [
            0 if n else -1 for n in away["neutral_site"].to_list()
        ]
        wins = float(
            (home["home_points"] > home["away_points"]).sum()
            + (away["away_points"] > away["home_points"]).sum()
        )
        q, _ = l4_resume.solve_quality(wins, power, sites, h, SIGMA, (Q_LO, Q_HI), 60)
        assert q == pytest.approx(fitted.resume[team], abs=1e-9)

        target = float(
            np.sum(
                design.compress_margin_array(
                    np.array(
                        (home["home_points"] - home["away_points"]).to_list()
                        + (away["away_points"] - away["home_points"]).to_list(),
                        dtype=float,
                    ),
                    C,
                    BETA_W,
                )
            )
        )
        qm, _ = l4_resume.solve_quality_margin(
            target, power, sites, h, SIGMA, C, BETA_W, 20, (Q_LO, Q_HI), 60
        )
        assert qm == pytest.approx(fitted.resume_margin[team], abs=1e-9)


def test_brentq_finds_the_same_root_as_the_bisection() -> None:
    """An independent solver on the same function, as a check on the fixed loop."""
    from scipy.optimize import brentq

    power = [12.0, 3.0, -6.0, 20.0, 1.0, -11.0, 8.0]
    sites = [1, 1, -1, 0, -1, 1, 0]
    target = 4.0
    ours, _ = l4_resume.solve_quality(target, power, sites, 2.8, SIGMA, (Q_LO, Q_HI), 60)
    theirs = brentq(
        lambda q: l4_resume.expected_wins(q, power, sites, 2.8, SIGMA) - target,
        Q_LO,
        Q_HI,
        xtol=1e-12,
    )
    assert ours == pytest.approx(theirs, abs=1e-8)


# --------------------------------------------------------------------- saturation


def test_undefeated_saturates_high_and_winless_saturates_low() -> None:
    """No finite root exists at either extreme. The bracket is the regularization."""
    power = [5.0] * 12
    sites = [1, -1] * 6

    q_hi, sat_hi = l4_resume.solve_quality(12.0, power, sites, 2.8, SIGMA, (Q_LO, Q_HI), 60)
    assert sat_hi == l4_resume.SATURATED_HIGH
    assert q_hi == Q_HI

    q_lo, sat_lo = l4_resume.solve_quality(0.0, power, sites, 2.8, SIGMA, (Q_LO, Q_HI), 60)
    assert sat_lo == l4_resume.SATURATED_LOW
    assert q_lo == Q_LO


def test_the_margin_variant_has_an_interior_root_for_an_undefeated_team() -> None:
    """Which is exactly why it is the published tie-break among saturated teams."""
    power = [5.0] * 12
    sites = [1, -1] * 6
    target = float(np.sum(design.compress_margin_array(np.full(12, 17.0), C, BETA_W)))
    q, saturated = l4_resume.solve_quality_margin(
        target, power, sites, 2.8, SIGMA, C, BETA_W, 20, (Q_LO, Q_HI), 60
    )
    assert saturated == l4_resume.SATURATED_NONE
    assert Q_LO < q < Q_HI


def test_saturated_teams_are_ordered_by_the_margin_variant() -> None:
    """Two undefeated teams, identical records, different schedules and margins."""
    classes = dict.fromkeys(["Strong", "Weak", "A", "B", "C", "D"], "fbs")
    games = frame(
        [
            ("Strong", "A", 42, 7, False),
            ("Strong", "B", 38, 10, False),
            ("Weak", "C", 17, 14, False),
            ("Weak", "D", 20, 17, False),
            ("A", "C", 31, 28, False),
            ("B", "D", 24, 21, False),
            ("A", "B", 27, 24, False),
            ("C", "D", 30, 27, False),
        ],
        classes,
    )
    fitted = l4_resume.fit(games, CONFIG)
    assert fitted.saturated["Strong"] == l4_resume.SATURATED_HIGH
    assert fitted.saturated["Weak"] == l4_resume.SATURATED_HIGH
    assert fitted.resume["Strong"] == fitted.resume["Weak"] == Q_HI
    assert fitted.resume_margin["Strong"] > fitted.resume_margin["Weak"]
    order = sorted(fitted.resume, key=fitted.order_key)
    assert order.index("Strong") < order.index("Weak")


# --------------------------------------------------- the retroactive substitution


def test_resume_rises_when_opponent_power_rises() -> None:
    """The Penn State principle (report 02 §3.6): the same results are worth more
    once we know the opponents were better. Hindsight is this substitution and
    nothing else."""
    games = round_robin()
    base = l4_resume.power_from_l2(games, CONFIG)
    lifted = l4_resume.PowerSource(
        ratings={t: v + 6.0 for t, v in base.ratings.items()},
        home_field=base.home_field,
        scale=base.scale,
        source=base.source,
        version=base.version,
        scale_universe=base.scale_universe,
        n_scale_games=base.n_scale_games,
    )
    before = l4_resume.fit(games, CONFIG, power=base)
    after = l4_resume.fit(games, CONFIG, power=lifted)
    for team in before.teams:
        if before.saturated[team] == l4_resume.SATURATED_NONE:
            assert after.resume[team] > before.resume[team]
        assert after.resume_margin[team] > before.resume_margin[team]


def test_an_undefeated_teams_margin_resume_rises_with_its_opponents() -> None:
    """Stated separately because the wins-based résumé of an undefeated team is
    saturated and CANNOT rise - it is already at the bound. The margin-aware
    variant is the number that carries the information for those teams, which is
    the second reason it is published."""
    classes = dict.fromkeys(["Unbeaten", "A", "B", "C"], "fbs")
    games = frame(
        [
            ("Unbeaten", "A", 28, 21, False),
            ("Unbeaten", "B", 31, 24, False),
            ("Unbeaten", "C", 24, 17, False),
            ("A", "B", 20, 17, False),
            ("B", "C", 27, 24, False),
            ("C", "A", 21, 20, False),
        ],
        classes,
    )
    base = l4_resume.power_from_l2(games, CONFIG)
    lifted = l4_resume.PowerSource(
        ratings={t: v + (9.0 if t != "Unbeaten" else 0.0) for t, v in base.ratings.items()},
        home_field=base.home_field,
        scale=base.scale,
        source=base.source,
        version=base.version,
        scale_universe=base.scale_universe,
        n_scale_games=base.n_scale_games,
    )
    before = l4_resume.fit(games, CONFIG, power=base)
    after = l4_resume.fit(games, CONFIG, power=lifted)
    assert before.saturated["Unbeaten"] == l4_resume.SATURATED_HIGH
    assert before.resume["Unbeaten"] == after.resume["Unbeaten"] == Q_HI
    assert after.resume_margin["Unbeaten"] > before.resume_margin["Unbeaten"]


def test_resume_is_invariant_to_a_constant_shift_of_power() -> None:
    """mu_g(q) = q - Power_opp + h*s, so shifting every Power by c shifts every q*
    by c. Rank order and the resume-minus-power gap are untouched, which is why
    the L2 fit's zero point (an average over a universe that includes FCS) costs
    the ranking nothing."""
    games = round_robin()
    base = l4_resume.power_from_l2(games, CONFIG)
    shifted = l4_resume.PowerSource(
        ratings={t: v + 13.5 for t, v in base.ratings.items()},
        home_field=base.home_field,
        scale=base.scale,
        source=base.source,
        version=base.version,
        scale_universe=base.scale_universe,
        n_scale_games=base.n_scale_games,
    )
    before = l4_resume.fit(games, CONFIG, power=base)
    after = l4_resume.fit(games, CONFIG, power=shifted)
    for team in before.teams:
        if before.saturated[team] != l4_resume.SATURATED_NONE:
            continue
        assert after.resume[team] - before.resume[team] == pytest.approx(13.5, abs=1e-6)
        assert after.gap(team) == pytest.approx(before.gap(team), abs=1e-6)
    assert sorted(before.resume, key=before.order_key) == sorted(after.resume, key=after.order_key)


# ------------------------------------------------------------------ the FCS games


def test_fcs_games_count_in_the_resume() -> None:
    """report 02 §3.7: the FCS opponent holds a real rating, so the game is worth
    what beating a team of that rating is worth. Not excluded, not special-cased."""
    classes = {"FBS1": "fbs", "FBS2": "fbs", "Cupcake": "fcs", "Other": "fcs"}
    games = frame(
        [
            ("FBS1", "Cupcake", 56, 0, False),
            ("FBS1", "FBS2", 21, 17, False),
            ("FBS2", "Other", 42, 10, False),
            ("Cupcake", "Other", 24, 21, False),
        ],
        classes,
    )
    fitted = l4_resume.fit(games, CONFIG)
    assert "Cupcake" in fitted.resume  # FCS teams get their own résumé too
    assert fitted.wins["FBS1"] == 2  # the FCS win is a win
    table = l4_resume.resume_frame(fitted, classes)
    assert table.filter(pl.col("team_class") == "fcs")["rank"].to_list() == [None, None]
    assert sorted(table.filter(pl.col("team_class") == "fbs")["rank"].to_list()) == [1, 2]


# --------------------------------------------------------------- the points scale


def test_power_is_rescaled_to_points_and_says_so() -> None:
    """L2 ratings are compressed-response units; sigma is points. The one OLS that
    reconciles them is published, not implicit."""
    games = round_robin()
    power = l4_resume.power_from_l2(games, CONFIG)
    assert power.scale > 0.0  # a better L2 rating must mean a bigger margin
    assert power.source == "L2" and power.version == "v0"
    params = power.as_params()
    assert params["power_scale_b"] == power.scale
    assert params["power_home_field_points"] == power.home_field
    assert power.l2 is not None
    # the rescaling is exactly a multiplication of the L2 coefficients
    for team, value in power.l2.ratings.items():
        assert power.rating(team) == pytest.approx(power.scale * value, abs=1e-12)


def test_empty_window_is_an_empty_fit_not_a_crash() -> None:
    games = round_robin()
    fitted = l4_resume.fit(games, CONFIG, resume_games=games.head(0))
    assert fitted.resume == {} and fitted.params["n_resume_games"] == 0
