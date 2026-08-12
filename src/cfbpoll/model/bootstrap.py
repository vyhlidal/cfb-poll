"""Parametric bootstrap on the FIXED schedule -> rating AND rank intervals.

Specified by report 02 §3.3 and report 03 §9.3, with the resampling scheme
corrected. The useful output is not the rating interval but the RANK interval:
publishing "Team X is ranked 7th, 90% interval 4th-13th" every week, forever -
not just early in the season - is the single most honest thing a computer poll
can do, and no major system does it.

THE SCHEME REPORT 02 §3.3 SPECIFIED IS INVALID HERE, AND THIS MODULE USED TO SAY
SO IN ITS OWN DOCSTRING WITHOUT NOTICING. The parenthetical was "resample games
with replacement, refit", and this file copied it faithfully. Games are not
exchangeable observations: they are EDGES IN THE SCHEDULE GRAPH, and the graph's
connectivity is the thing that identifies a cross-conference comparison at all.
Resampling edges with replacement can disconnect the graph, can leave a team with
zero games, and destroys exactly the structure whose uncertainty is being
measured. It also treats the schedule as random when it was fixed years in
advance by human beings with television contracts.

    `naive_resample_diagnostic` runs the invalid scheme and reports how often it
    breaks the graph, so the disqualification is a measurement rather than an
    argument. On 2023 through week 10 it disconnects the graph or strands a team
    in essentially every draw.

WHAT THIS DOES INSTEAD. The schedule is held fixed and the OUTCOMES are redrawn
from the fitted model:

    mu_g   = Power_home - Power_away + h * site_g          (the fitted model)
    m_g    ~ Normal(mu_g, sigma^2)                          (a simulated season)
    refit  -> rho*, Power*, resume*, schedule odds*         (a simulated poll)

Each draw is a complete alternative season played on the real calendar, and the
rank interval is the spread of a team's rank across those seasons. Everything the
poll publishes is recomputed by the SAME functions the poll uses -
`l4_resume.fit` and `schedule_odds.fit` - so a bootstrap rank cannot drift away
from a published rank through a second implementation.

TWO PROPERTIES OF THE ANSWER THAT WILL SURPRISE A READER, and both are correct:

  1. The bootstrap MEDIAN rank is worse than the published rank for nearly every
     undefeated team. Under the model's own estimate of these teams' quality,
     going 9-0 is an unlikely outcome, so most simulated seasons do not repeat
     it. That is not a bug in the interval: the headline ordering ranks teams by
     how improbable their record was, and a record that is improbable is one that
     usually does not happen again.
  2. The intervals are wide. 2023 James Madison at published rank #4 carries a
     90% interval that runs deep into the fifties. A poll that prints an integer
     without that interval is claiming a precision it does not have, and the
     independent review's first line of attack was exactly this
     (docs/analysis/fresh-eyes-review.md §8 item 1).

WHAT IS AND IS NOT PROPAGATED. With `[resume].power_source = "L3"` the EFFICIENCY
half of Power is held at its point estimate across draws, because plays are not
resimulated - a generative model of 170,000 correlated snaps is a different
project. The results core, the record, every win probability, q_ref and both
orderings are all redrawn. The interval is therefore a LOWER BOUND on total
uncertainty, and `Draws.note` says so in every artifact. With `power_source =
"L2"` nothing is held fixed and the propagation is complete.

lambda IS HELD AT THE VALUE THE REAL DATA SELECTED, and the normal matrix is
factored ONCE. The bootstrap propagates sampling uncertainty at a fixed
hyperparameter, which is the standard construction; re-running the CV inside
every draw would also fold in the CV's own variance, which is a different (and
much less interesting) quantity. Because the design Z, the weights v and the
penalty are all fixed by the fixed schedule, `ZᵀWZ + lambda*D` is fixed too - so
one Cholesky factorisation serves all 1,000 draws and a refit costs one sparse
matrix-vector product and one back-substitution.

DETERMINISM IS A HARD REQUIREMENT, and it is cheap up front and expensive to
retrofit (report 03 §9.3):
  - never np.random.seed; use Generator(PCG64(seed))
  - derive per-draw seeds with SeedSequence.spawn so the result is identical on
    1 core or 16, and identical whether draws run in any order
  - sort before writing; dict and groupby iteration order must never reach a file

The draws run sequentially. `[bootstrap].jobs` is recorded on the artifact and is
NOT used, and that is stated rather than implied: with SeedSequence.spawn the
per-draw streams are already independent of scheduling, so an executor can be
dropped in later without moving a single published number. 1,000 draws on a
full-season window take about half a minute on one core.

STATUS: IMPLEMENTED.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl
from scipy.linalg import cho_factor, cho_solve

from cfbpoll.config import load_config
from cfbpoll.model import design, l4_resume, schedule_odds

__all__ = [
    "ORDERINGS",
    "Draws",
    "intervals",
    "naive_resample_diagnostic",
    "rank_intervals",
    "run",
]

#: The three orderings a rank interval is published for. The headline is the one
#: that sorts the table; the other two are on every row already (report 02 §3.5),
#: so leaving them without an interval would say the uncertainty applies only to
#: the column we chose.
ORDERINGS: tuple[str, ...] = ("schedule_odds", "resume", "power")


@dataclass(frozen=True)
class Draws:
    """Every simulated season's ranks and ratings, plus the provenance.

    `rank[ordering]` is a (draws x teams) integer array over `teams`, which is
    the sorted FBS set of the window. A rank is 1-based, as published.
    """

    teams: tuple[str, ...]
    rank: dict[str, np.ndarray]
    power: np.ndarray
    n_draws: int
    sigma: float
    seed: int
    lam: float
    power_source: str
    note: str
    params: dict[str, Any] = field(default_factory=dict)

    def as_params(self) -> dict[str, Any]:
        return {
            "bootstrap_draws": self.n_draws,
            "bootstrap_seed": self.seed,
            "bootstrap_sigma": self.sigma,
            "bootstrap_lambda": self.lam,
            "bootstrap_scheme": "parametric_on_fixed_schedule",
            "bootstrap_orderings": list(ORDERINGS),
            "bootstrap_power_source": self.power_source,
            "bootstrap_note": self.note,
            **self.params,
        }


# ------------------------------------------------------------------ the fixed parts


@dataclass(frozen=True)
class _Prepared:
    """Everything that does not change from draw to draw, computed once."""

    games: pl.DataFrame
    zw: Any  # (T+1) x G, the weighted transpose - one sparse product per draw
    factor: Any  # Cholesky of ZᵀWZ + lambda*D
    teams: tuple[str, ...]
    site_index: int
    mu: np.ndarray
    c: float
    beta_w: float
    sigma: float
    lam: float


def _prepare(
    games: pl.DataFrame,
    power: l4_resume.PowerSource,
    cfg: dict[str, Any],
    sigma: float,
) -> _Prepared:
    games = games.sort("game_id")
    d = design.build_game_design(games, cfg)
    lam = float(power.l2.lam) if power.l2 is not None else float(max(cfg["ridge"]["l2_grid"]))

    normal = np.asarray((d.Z.T.multiply(d.v) @ d.Z).todense(), dtype=np.float64)
    normal[np.diag_indices_from(normal)] += lam * d.penalty

    site = np.where(games["neutral_site"].to_numpy(), 0.0, 1.0)
    mu = (
        np.array(
            [
                power.rating(h) - power.rating(a)
                for h, a in zip(
                    games["home_team"].to_list(), games["away_team"].to_list(), strict=True
                )
            ],
            dtype=np.float64,
        )
        + power.home_field * site
    )

    return _Prepared(
        games=games,
        zw=d.Z.T.multiply(d.v),
        factor=cho_factor(normal, lower=True, check_finite=False),
        teams=d.teams,
        site_index=d.site_index,
        mu=mu,
        c=float(cfg["margin"]["c"]),
        beta_w=float(cfg["margin"]["beta_w"]),
        sigma=sigma,
        lam=lam,
    )


def _draw_power(
    prepared: _Prepared,
    margin: np.ndarray,
    power: l4_resume.PowerSource,
    cfg: dict[str, Any],
) -> l4_resume.PowerSource:
    """Refit the results core on one simulated season and rebuild Power from it.

    The rescaling mirrors whatever the live Power source did, because a bootstrap
    that rebuilt Power a second way would be measuring a different estimator:

      L2  refit b and h_points by the same no-intercept OLS `power_from_l2` uses
      L3  hold w1, k and h at the values the walk-forward blend fitted on REAL
          data and vary only the w2*rho half, because plays are not resimulated
    """
    s = design.compress_margin_array(margin, prepared.c, prepared.beta_w)
    theta = cho_solve(prepared.factor, np.asarray(prepared.zw @ s).ravel(), check_finite=False)
    rho = {team: float(theta[i]) for i, team in enumerate(prepared.teams)}

    if power.source == "L3" and power.l3 is not None:
        blend = power.l3
        efficiency = {t: blend.w1 * blend.k * blend.l1.net(t) for t in rho}
        ratings = {t: efficiency.get(t, 0.0) + blend.w2 * rho[t] for t in sorted(rho)}
        return l4_resume.PowerSource(
            ratings=ratings,
            home_field=power.home_field,
            scale=1.0,
            source="L3",
            version=power.version,
            scale_universe=power.scale_universe,
            n_scale_games=power.n_scale_games,
            se_scale=blend.w2,
            se_note=power.se_note,
        )

    scale_games = prepared.games.with_columns(
        home_points=pl.Series(margin, dtype=pl.Float64), away_points=pl.lit(0.0)
    )
    b, h_points, n = l4_resume._fit_points_scale(scale_games, rho)
    return l4_resume.PowerSource(
        ratings={t: b * v for t, v in sorted(rho.items())},
        home_field=h_points,
        scale=b,
        source="L2",
        version=power.version,
        scale_universe=power.scale_universe,
        n_scale_games=n,
        se_scale=b,
        se_note=power.se_note,
    )


def _ranks(
    values: dict[str, Any],
    teams: tuple[str, ...],
    descending: bool,
    width: int = 1,
) -> np.ndarray:
    """1-based ranks over `teams`, ties broken by name so the map is a function.

    `values` maps a team to a float or to a tuple of floats - the résumé needs
    two, because every undefeated team saturates at the same q bound and the
    published order among them comes from the margin-aware variant
    (`[resume].saturation_tiebreak`). `width` says how many, so a missing team
    falls to the neutral zero in the same shape.
    """
    sign = -1.0 if descending else 1.0
    default: Any = 0.0 if width == 1 else (0.0,) * width

    def key(team: str) -> tuple[Any, ...]:
        value = values.get(team, default)
        parts = (value,) if width == 1 else tuple(value)
        return (*(sign * float(v) for v in parts), team)

    order = sorted(teams, key=key)
    position = {team: i + 1 for i, team in enumerate(order)}
    return np.array([position[t] for t in teams], dtype=np.int32)


def run(
    games: pl.DataFrame,
    power: l4_resume.PowerSource,
    config: dict[str, Any] | None = None,
    classes: dict[str, str] | None = None,
    draws: int | None = None,
    seed: int | None = None,
    sigma: float | None = None,
) -> Draws:
    """Simulate `draws` seasons on the fixed schedule and re-rank each one.

    `games` is the exact window the poll was computed over and `power` is the
    fitted Power source that ranked it - the same two objects `cfbpoll rank`
    already holds, so the bootstrap is about the poll that was published rather
    than about a re-derived approximation of it.
    """
    cfg = config if config is not None else load_config()
    boot = cfg["bootstrap"]
    n_draws = int(draws if draws is not None else boot["draws"])
    root_seed = int(seed if seed is not None else boot["seed"])
    # sigma comes from the SAME place the résumé and the headline ordering get it
    # (l4_resume.sigma_for): this system's own walk-forward residuals, with the
    # config constant as the thin-window fallback and floor. Simulating from a
    # sigma the poll does not use would make the interval an interval on a
    # different model (review S6).
    sigma_source = "explicit_argument"
    if sigma is None:
        sigma, sigma_source = l4_resume.sigma_for(power, cfg)
    sigma = float(sigma)

    if classes is None:
        classes = schedule_odds.team_classes(games)
    ranked = tuple(sorted(t for t in power.ratings if classes.get(t, "fbs") == "fbs"))

    prepared = _prepare(games, power, cfg, sigma)
    n_games = prepared.games.height

    rank = {name: np.zeros((n_draws, len(ranked)), dtype=np.int32) for name in ORDERINGS}
    power_draws = np.zeros((n_draws, len(ranked)), dtype=np.float64)

    # SeedSequence.spawn, per report 03 §9.3 item 2: draw i's stream depends on
    # (root seed, i) and on nothing else - not on core count, not on the order
    # the draws happen to run in, not on how many were requested before it.
    children = np.random.SeedSequence(root_seed).spawn(n_draws)

    for i, child in enumerate(children):
        rng = np.random.Generator(np.random.PCG64(child))
        margin = prepared.mu + sigma * rng.standard_normal(n_games)
        # A tie is impossible in modern college football (overtime), and a margin
        # of exactly 0.0 has probability zero in this continuous draw; nudging it
        # is a guard against a pathological sigma, not a real case.
        margin = np.where(margin == 0.0, 1e-9, margin)

        drawn = _draw_power(prepared, margin, power, cfg)
        simulated = prepared.games.with_columns(
            home_points=pl.Series(margin, dtype=pl.Float64), away_points=pl.lit(0.0)
        )
        resume = l4_resume.fit(simulated, cfg, power=drawn)
        odds = schedule_odds.fit(simulated, cfg, power=drawn, classes=classes)

        # The two published orderings, by exactly the keys publish/poll.py sorts
        # on: ascending tail then mid-p for the headline; résumé then the
        # margin-aware tie-break for the one it replaced.
        rank["schedule_odds"][i] = _ranks(
            {t: (odds.tail[t], odds.mid_p[t]) for t in odds.tail},
            ranked,
            descending=False,
            width=2,
        )
        rank["resume"][i] = _ranks(
            {t: (resume.resume[t], resume.resume_margin[t]) for t in resume.resume},
            ranked,
            descending=True,
            width=2,
        )
        rank["power"][i] = _ranks(drawn.ratings, ranked, descending=True)
        power_draws[i] = np.array([drawn.rating(t) for t in ranked], dtype=np.float64)

    note = (
        "parametric on the FIXED schedule: outcomes redrawn from the fitted "
        "model, refit, re-ranked. Games are edges in the schedule graph and are "
        "not exchangeable, so resampling them with replacement - which report 02 "
        "§3.3's parenthetical specified - is invalid here; see "
        "naive_resample_diagnostic."
    )
    if power.source == "L3":
        note += (
            " The L1 efficiency half of Power is held at its point estimate "
            "because plays are not resimulated, so these intervals are a LOWER "
            "BOUND on total uncertainty."
        )
    return Draws(
        teams=ranked,
        rank=rank,
        power=power_draws,
        n_draws=n_draws,
        sigma=sigma,
        seed=root_seed,
        lam=prepared.lam,
        power_source=power.source,
        note=note,
        params={
            "bootstrap_n_games": int(n_games),
            "bootstrap_n_ranked_teams": len(ranked),
            "bootstrap_jobs_requested": int(boot.get("jobs", 1)),
            "bootstrap_jobs_used": 1,
            "bootstrap_jobs_note": (
                "draws run sequentially; per-draw streams come from "
                "SeedSequence.spawn, so parallelising later cannot move a "
                "published number (report 03 §9.3 item 2)"
            ),
            "bootstrap_sigma_source": sigma_source,
            "bootstrap_lambda_note": (
                "held at the value the real data's CV selected; the bootstrap "
                "propagates sampling uncertainty at a fixed hyperparameter"
            ),
        },
    )


def intervals(draws: Draws, level: float | None = None) -> pl.DataFrame:
    """Collapse the draws into per-team rank and rating intervals, one row per team.

    The interval is the equal-tailed percentile interval: at level 0.90 the
    bounds are the 5th and 95th percentiles of the draw distribution, taken with
    the `lower`/`higher` interpolation that keeps a rank an integer. A rank is a
    count of teams, and reporting "ranked 4th, 90% interval 3.7th to 51.2nd"
    would be a category error.
    """
    if level is None:
        level = float(load_config()["bootstrap"]["interval"])
    lo_q = 100.0 * (1.0 - level) / 2.0
    hi_q = 100.0 - lo_q

    frame: dict[str, Any] = {"team": list(draws.teams)}
    for name in ORDERINGS:
        block = draws.rank[name]
        frame[f"{name}_rank_lo"] = np.percentile(block, lo_q, axis=0, method="lower").astype(int)
        frame[f"{name}_rank_hi"] = np.percentile(block, hi_q, axis=0, method="higher").astype(int)
        frame[f"{name}_rank_median"] = np.percentile(block, 50.0, axis=0, method="nearest").astype(
            int
        )
    frame["power_lo"] = np.percentile(draws.power, lo_q, axis=0)
    frame["power_hi"] = np.percentile(draws.power, hi_q, axis=0)
    frame["power_bootstrap_median"] = np.percentile(draws.power, 50.0, axis=0)
    return pl.DataFrame(frame).sort("team")


#: Backwards-compatible name. The scaffold exported `rank_intervals`; the
#: workflows and report 03 §5.3 both say `rank_intervals.parquet`.
rank_intervals = intervals


def probability_within(draws: Draws, team: str, top_n: int, ordering: str) -> float:
    """P(this team finishes in the top N under this ordering), across the draws.

    The sentence a reader actually wants under a rank interval: "James Madison is
    #4, and the model gives it a 22% chance of being a genuine top-ten team."
    """
    if team not in draws.teams:
        return float("nan")
    index = draws.teams.index(team)
    block = draws.rank[ordering][:, index]
    return float(np.count_nonzero(block <= int(top_n)) / block.size)


# ------------------------------------------------------- the scheme that was wrong


def naive_resample_diagnostic(
    games: pl.DataFrame,
    draws: int = 1000,
    seed: int = 20260812,
) -> dict[str, Any]:
    """Run the INVALID scheme and count how often it destroys the graph.

    Report 02 §3.3's parenthetical said "resample games with replacement, refit",
    and the review (S3) asked for the disqualification to be measured rather than
    argued: over N draws, in what fraction does the schedule graph gain a second
    component, or some team lose every one of its games?

    This function exists to be run once and quoted. It is not on any publication
    path and nothing consumes its output.
    """
    games = games.sort("game_id")
    home = games["home_team"].to_list()
    away = games["away_team"].to_list()
    teams = sorted(set(home) | set(away))
    index = {t: i for i, t in enumerate(teams)}
    edges = np.array([[index[h], index[a]] for h, a in zip(home, away, strict=True)])
    n_games = len(home)

    disconnected = 0
    stranded = 0
    both = 0
    max_component_share: list[float] = []
    for child in np.random.SeedSequence(seed).spawn(int(draws)):
        rng = np.random.Generator(np.random.PCG64(child))
        picked = edges[rng.integers(0, n_games, size=n_games)]
        seen = np.zeros(len(teams), dtype=bool)
        seen[picked[:, 0]] = True
        seen[picked[:, 1]] = True
        lost = int(len(teams) - np.count_nonzero(seen))

        parent = list(range(len(teams)))

        def find(x: int, parent: list[int] = parent) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for u, v in picked:
            ru, rv = find(int(u)), find(int(v))
            if ru != rv:
                parent[ru] = rv
        roots: dict[int, int] = {}
        for i in range(len(teams)):
            if seen[i]:
                roots[find(i)] = roots.get(find(i), 0) + 1
        components = len(roots)
        largest = max(roots.values()) if roots else 0
        max_component_share.append(largest / len(teams))

        if components > 1:
            disconnected += 1
        if lost:
            stranded += 1
        if components > 1 or lost:
            both += 1

    return {
        "scheme": "resample games with replacement (report 02 §3.3 parenthetical)",
        "verdict": "INVALID for a schedule graph; not used anywhere in this package",
        "draws": int(draws),
        "n_games": n_games,
        "n_teams": len(teams),
        "fraction_disconnected": disconnected / draws,
        "fraction_with_a_team_that_lost_every_game": stranded / draws,
        "fraction_broken_either_way": both / draws,
        "mean_largest_component_share": float(math.fsum(max_component_share) / draws),
    }
