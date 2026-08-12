"""Baseline: Elo - the sequential alternative we deliberately rejected.

Specified by report 02 §2.7 and §5.3.

    R' = R + K(S - E),   E = 1 / (1 + 10^((R_opp - R)/400))

with the 538 margin-of-victory and autocorrelation multiplier, published by Neil
Paine (the author of 538's NFL Elo):

    MOV multiplier = ln(|PD| + 1) * [ 2.2 / ((Elo_W - Elo_L) * 0.001 + 2.2) ]

using PRE-GAME ratings. The second factor is not optional: adding MOV to plain
Elo breaks the zero-expected-change property, because favourites win by larger
margins, and without the correction strong teams' ratings drift upward without
bound. Our ridge fits get that guard for free by being batch estimators with no
accumulation dynamic at all.

CFB constants: the published CFBD tutorial uses K = 25, initial 1500 FBS / 1200
non-FBS, with no HFA, no MOV and no offseason regression. 538's
COLLEGE-FOOTBALL-specific constants are unrecoverable - every fivethirtyeight.com
URL now redirects away and the parameters were never published. DO NOT state CFB
Elo numbers as though they were 538's (report 02 §2.7, Appendix A).

Why Elo is a baseline and not the core (report 02 §2.7): it is path-dependent, so
retroactive re-ranking has no clean definition; its only week-1 stabiliser is
last season's rating, which is exactly the reputation prior constraint 2 bans;
and its opponent adjustment credits you for the opponent's rating AT THE TIME,
not their true quality, which is the very thing this project exists to correct.

Every constant lives in configs/default.toml under [baselines.elo], with the
sourcing caveat attached: the CFB-specific 538 constants are unrecoverable, so
the MOV multiplier and home-field values here are the NFL ones and are stated as
an approximation rather than as 538's college numbers.
"""

from __future__ import annotations

import math

import polars as pl

from cfbpoll.config import load_config

__all__ = ["mov_multiplier", "rate"]


def mov_multiplier(
    point_diff: float, elo_winner: float, elo_loser: float, denominator: float = 2.2
) -> float:
    """The 538 MOV + autocorrelation multiplier, on PRE-GAME ratings.

        ln(|PD| + 1) * [ d / ((Elo_W - Elo_L) * 0.001 + d) ],  d = 2.2

    `ln(|PD|+1)` is the diminishing-returns margin term. The second factor is the
    autocorrelation correction, and it is not optional: adding margin to plain
    Elo breaks the zero-expected-change property, because favourites win by
    larger margins than underdogs, and without the correction strong teams drift
    upward without bound (report 02 §2.7). Our ridge fit needs no equivalent
    guard because a batch least-squares estimator has no accumulation dynamic
    at all.
    """
    return math.log(abs(point_diff) + 1.0) * (
        denominator / ((elo_winner - elo_loser) * 0.001 + denominator)
    )


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None = None,
    through_week: int | None = None,
    config: dict | None = None,
) -> dict[str, float]:
    """Elo after replaying games in order (challenger protocol, report 03 §7.3).

    `games` arrives ALREADY truncated by the harness. Games are replayed in
    kickoff order, ties broken by game_id, so the sequence is a pure function of
    the frame - which matters more here than anywhere else in the package,
    because Elo is the one system whose answer depends on the order.

    No offseason regression and no carryover: each call starts every team at its
    initial rating. That is not a courtesy to our own constraint 2 - it is what
    the walk-forward protocol requires, since the harness never hands a system
    games from a previous season.
    """
    del plays, through_week
    cfg = config if config is not None else load_config()
    e = cfg["baselines"]["elo"]
    k = float(e["k_factor"])
    hfa = float(e["home_field_elo"])
    denom = float(e["mov_autocorrelation_denominator"])

    ordered = games.sort(["start_date", "game_id"])
    initial = {
        team: (float(e["initial_fbs"]) if klass == "fbs" else float(e["initial_non_fbs"]))
        for team, klass in sorted(
            list(zip(ordered["home_team"].to_list(), ordered["home_class"].to_list(), strict=True))
            + list(
                zip(ordered["away_team"].to_list(), ordered["away_class"].to_list(), strict=True)
            )
        )
    }
    ratings = dict(initial)

    for home, away, hp, ap, neutral in zip(
        ordered["home_team"].to_list(),
        ordered["away_team"].to_list(),
        ordered["home_points"].to_list(),
        ordered["away_points"].to_list(),
        ordered["neutral_site"].to_list(),
        strict=True,
    ):
        rh = ratings[home] + (0.0 if neutral else hfa)
        ra = ratings[away]
        expected_home = 1.0 / (1.0 + 10.0 ** ((ra - rh) / 400.0))
        if hp > ap:
            actual, winner_elo, loser_elo = 1.0, rh, ra
        elif ap > hp:
            actual, winner_elo, loser_elo = 0.0, ra, rh
        else:  # pragma: no cover - overtime makes ties impossible in modern CFB
            actual, winner_elo, loser_elo = 0.5, rh, ra
        mult = mov_multiplier(float(hp - ap), winner_elo, loser_elo, denom)
        delta = k * mult * (actual - expected_home)
        ratings[home] += delta
        ratings[away] -= delta

    return {team: float(ratings[team]) for team in sorted(ratings)}
