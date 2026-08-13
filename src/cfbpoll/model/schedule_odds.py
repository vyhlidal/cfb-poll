"""Schedule odds - THE HEADLINE ORDERING. How improbable is this record?

Adopted as the headline on 2026-08-12 by the project owner, on the evidence of
docs/analysis/headline-ordering-study.md, where this module was candidate C.
The decision and the rejected alternatives are docs/adr/0005-headline-ordering.md;
the knob is `[publication].headline_ordering`. The promise the poll now makes:

    THE HARDER IT WAS TO DO WHAT YOU DID, THE HIGHER YOU GO - measured, never
    assumed.

That last clause is the whole point and it is what this module buys. An unbeaten
Group of Five team probably would not survive a Big Ten schedule; a poll may only
say so if it DERIVED it from on-field results. Assuming it is how you get AP-style
conference bias. Nothing in this file knows what a conference is: opponent quality
arrives as a Power rating fitted from results, and the answer for 2023 Liberty
(#10 live, #8 in hindsight, behind a 12-1 Georgia at #7) is an output rather than
an input.

It is ESPN's Strength-of-Record (report 02 §2.4) taken at its literal word:

    SOR = "the chance of an average Top-25 team having the team's record or
           better, given the opponents the team has played"

L4 (model/l4_resume.py) reads that sentence as a QUALITY question and inverts it:
what q makes E[W|q] equal the actual win total? This module reads the same
sentence as a PROBABILITY question and answers it directly: hold quality fixed at
a published reference q_ref, and compute the tail probability that a team of that
quality would have gone at least this well against this exact schedule.

    p_g   = Phi( (q_ref - Power_{o_g} + h * s_g) / sigma )      per game
    P_t   = P(W >= W_t)  for W ~ PoissonBinomial(p_1..p_n)
    key_t = -log10(P_t)                                          higher is better

WHY THIS IS A DIFFERENT ANSWER AND NOT A RESTATEMENT. L4's root-solve has no
finite solution for an undefeated team - E[W|q] approaches n from below, so the
estimate runs off to +infinity and the published bracket truncates it
(l4_resume.py, SATURATION). Every unbeaten team therefore lands on the same
number and the wins-based résumé cannot, even in principle, rank a 13-0 team
against a soft schedule below a 12-1 team against a brutal one. The tail
probability has no such degeneracy: P(W >= n) = prod_g p_g is finite, strictly
positive, and strictly ordered by schedule difficulty. Going 13-0 through a
schedule a reference team beats 90% of the time at every stop is a 0.25
probability event; going 12-1 through a schedule it beats 60% of the time is a
0.013 event. The second one is harder, and this ordering says so.

That is the whole methodological content of this ordering, and it is the reason it
became the headline: the wins-based résumé cannot answer the owner's question by
construction, and the margin-aware variant can only answer it by importing margin.
This answers it using nothing but who you played, where, and whether you won.

YOUR OWN MARGIN NEVER ENTERS. Not as a tie-break, not as a secondary key,
nowhere. The schedule flattener below carries opponent Power, site, and a boolean
win - there is no margin column in this module to leak from, which makes the
claim checkable by reading the code rather than by trusting this paragraph.
`tests/unit/test_schedule_odds.py::test_scores_may_change_freely_if_winners_do_not`
pins it: hold `power` fixed, perturb every final score while preserving every
winner, and every number here is bit-identical.

YOUR OPPONENTS' MARGINS PRICE YOUR WINS, and this docstring used to omit that.
The wider sentence - "margin never enters" full stop - is true of this file and
false of the poll it produces, because `power` is the L3 blend of a ridge fit on
compressed scoring margin and a play-value fit, `q_ref` is read off those same
ratings, and `h` is the blend regression's site coefficient with actual margin as
its response. The independent review caught it (docs/analysis/fresh-eyes-review.md,
S5) and wrote the true version, which is the one above.
`::test_refitting_opponent_quality_from_scrambled_scores_does_move_the_ranking`
refits Power from the scrambled scores the way `cfbpoll rank` does and asserts the
published ordering MOVES, so the narrow claim cannot silently widen again. This is
still the meaningful property: a one-point win and a forty-point win over the same
opponent are worth exactly the same to the team that won them.

EXACT, NOT SIMULATED. ESPN's SOR is reportedly a ~20,000-run Monte Carlo. A
Poisson-binomial over n <= 15 independent games has an exact O(n^2) dynamic
program - the same convolution a first course in probability derives - so the
whole league costs microseconds and is reproducible bit for bit forever. Report
02 §2.4 already made this argument for the résumé's root-solve; it applies with
even more force here, because a Monte Carlo estimate of a 1e-9 tail is not an
estimate of anything.

q_ref, AND WHY IT IS PUBLISHED. The reference quality is the one free constant in
this ordering and it must never be a hidden dial. `[schedule_odds].q_ref_method`
fixes it and every artifact records the method, the resulting points value, and -
for the default method - the NAME OF THE TEAM it came from, so a reader can check
the constant against the same week's poll. The default reading of "an average
Top-25 team" is the Power rating of the 25th-ranked Power team that week:

  * it is a single identifiable team, nameable every week, which `mean_top_25`
    is not;
  * it sits at the boundary of the group ESPN names, so it is the least
    flattering defensible choice - a higher q_ref makes every record look less
    improbable and compresses the whole table toward zero;
  * it moves with the league rather than being frozen at some historical number,
    which matters because Power's zero point is the fit's league average and
    that is not a fixed quantity.

`mean_top_25`, `power_rank_10`, `mean_fbs` and `fixed` are all implemented so the
sensitivity of the ordering to this choice can be measured instead of asserted;
docs/analysis/headline-ordering-study.md §9 reports it and the answer is that the
constant is safe: across a 16-point swing in reference quality, Kendall's tau
against the default never dropped below 0.985, the mean rank change never reached
one place, and at most one team entered or left the top 25 in any season.

INVARIANCE, which is the property that makes the choice defensible. Shift every
Power rating by a constant c and every rank-derived q_ref shifts by c too, so
every mu_g, every p_g and every tail is unchanged. The ordering therefore does
not depend on the zero point of the Power fit - exactly the invariance
l4_resume.py relies on for the same reason. A `fixed` q_ref breaks it, which is
precisely why `fixed` is not the default and why anyone using it must publish the
number.

THE RETROACTIVE SURFACE IS THE SAME ONE SUBSTITUTION. Like the résumé, the tail
depends on opponent quality ONLY through Power (and through q_ref, which is
itself read off Power). Pass through-week-N Power and you get the live ordering
R(N, N); pass end-of-season Power and you get the hindsight ordering R(N, final).
Unlike the wins-based résumé, an unbeaten team's number MOVES between the two
surfaces, because a tail probability is not saturated - which is the structural
point the study set out to test, and the reason constraint 4 is now satisfied for
every team rather than for every team that has lost a game. Measured over
2021-2024, restricted to unbeaten teams: this ordering moves them 1.34 places on
average between the two surfaces where the wins-based résumé moves them 0.395,
and from week 11 of 2023 onward the résumé moved them exactly zero.

PURITY AND DETERMINISM. Every function is pure: no I/O, no state, no RNG. Teams
are sorted by name, games by game_id, mappings are built in sorted order, and the
tail sums use `math.fsum` so the result does not depend on summation order
(report 03 §9.3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl
from scipy.special import ndtr

from cfbpoll.config import load_config
from cfbpoll.model.l4_resume import PowerSource

__all__ = [
    "OddsFit",
    "QRef",
    "Q_REF_METHODS",
    "fit",
    "mid_p_at_least",
    "odds_frame",
    "poisson_binomial_pmf",
    "rate",
    "reference_quality",
    "schedule_odds",
    "tail_at_least",
    "team_classes",
    "win_probabilities",
]

LAYER = "C schedule odds"
VERSION = "v0"

#: The published q_ref methods. `power_rank_25` is the default; see the module
#: docstring for why, and `[schedule_odds]` in configs/default.toml for the knob.
Q_REF_METHODS: tuple[str, ...] = (
    "power_rank_25",
    "power_rank_10",
    "mean_top_25",
    "mean_fbs",
    "fixed",
)

#: A tail smaller than this is reported AT this value rather than as zero, so the
#: -log10 key stays finite. With sigma = 15.3 and Power bounded by the fit, the
#: smallest per-game win probability a real schedule produces is ~0.02, so a
#: 15-game sweep floors out around 1e-26 and this clamp has never fired on real
#: data. It exists so that a pathological config cannot produce an infinity in a
#: published file.
MIN_TAIL = 1e-300

#: The largest key the clamp above can produce. Published so the ceiling is a
#: stated number rather than a surprise.
MAX_KEY = 300.0


# --------------------------------------------------------------- reference quality


def team_classes(games: pl.DataFrame) -> dict[str, str]:
    """team -> division, read off the game frame, preferring the highest seen.

    THIS EXISTS SO THE q_ref POOL CANNOT SILENTLY GO WRONG. `reference_quality`
    treats an unclassified team as FBS, which is the right default for a
    hand-built test frame and precisely the wrong one for a real window: a season
    frame carries ~250 FCS and lower-division teams, and letting them into the
    pool would move "the 25th-best team" by whatever the fit happened to say about
    them. `fit` therefore derives the classification from the Power window itself
    whenever the caller does not supply one, rather than defaulting the whole
    league to FBS. Duplicated from publish/poll.py on purpose: a model module may
    not import a publish module, and this is four lines.
    """
    order = {"fbs": 0, "fcs": 1, "ii": 2, "iii": 3, "unknown": 4}
    out: dict[str, str] = {}
    if "home_class" not in games.columns or "away_class" not in games.columns:
        return out
    pairs = sorted(
        list(zip(games["home_team"].to_list(), games["home_class"].to_list(), strict=True))
        + list(zip(games["away_team"].to_list(), games["away_class"].to_list(), strict=True))
    )
    for team, klass in pairs:
        if team not in out or order.get(klass, 4) < order.get(out[team], 4):
            out[team] = klass
    return out


@dataclass(frozen=True)
class QRef:
    """The reference quality q_ref, and the full provenance of the number.

    `team` is the team the value was read off when the method names one, and None
    otherwise. Publishing it is what turns q_ref from a dial into an auditable
    fact: a reader can look up that team in the same week's poll.
    """

    value: float
    method: str
    team: str | None
    n_pool: int

    def as_params(self) -> dict[str, Any]:
        return {
            "q_ref": self.value,
            "q_ref_method": self.method,
            "q_ref_team": self.team,
            "q_ref_pool_size": self.n_pool,
        }


def reference_quality(
    power: PowerSource,
    classes: dict[str, str] | None = None,
    method: str = "power_rank_25",
    fixed_value: float = 0.0,
) -> QRef:
    """q_ref from this week's Power ratings (report 02 §2.4's "average Top-25 team").

    The pool is FBS teams only - a college football poll's reference team is a
    college football team - and it is sorted by Power descending with ties broken
    on team name so the choice is a pure function of the fit.

    A pool smaller than the requested rank degrades to the last team in the pool
    rather than raising: week 1 of a season in which only twenty FBS teams have
    played is a real window, and the fallback is recorded in `method`.
    """
    if method not in Q_REF_METHODS:
        raise ValueError(f"unknown q_ref method {method!r}; expected one of {Q_REF_METHODS}")
    if method == "fixed":
        return QRef(value=float(fixed_value), method="fixed", team=None, n_pool=0)

    classes = classes or {}
    pool = sorted(
        (t for t in power.ratings if classes.get(t, "fbs") == "fbs"),
        key=lambda t: (-power.rating(t), t),
    )
    if not pool:
        return QRef(value=0.0, method=f"{method}_empty_pool", team=None, n_pool=0)

    if method == "mean_fbs":
        value = float(np.mean([power.rating(t) for t in pool]))
        return QRef(value=value, method=method, team=None, n_pool=len(pool))

    if method == "mean_top_25":
        top = pool[: min(25, len(pool))]
        name = method if len(pool) >= 25 else f"{method}_short_pool"
        value = float(np.mean([power.rating(t) for t in top]))
        return QRef(value=value, method=name, team=None, n_pool=len(pool))

    rank = 25 if method == "power_rank_25" else 10
    index = min(rank, len(pool)) - 1
    name = method if len(pool) >= rank else f"{method}_short_pool"
    return QRef(
        value=float(power.rating(pool[index])), method=name, team=pool[index], n_pool=len(pool)
    )


# ------------------------------------------------------- the exact Poisson-binomial


def poisson_binomial_pmf(probabilities: list[float] | np.ndarray) -> np.ndarray:
    """P(W = k) for k = 0..n, W a sum of INDEPENDENT non-identical Bernoullis.

    The exact O(n^2) convolution: start from the degenerate distribution on zero
    wins and fold one game in at a time. No Monte Carlo, no normal approximation,
    no saddlepoint - with n <= 15 the exact answer is cheaper than any estimate of
    it, and it is reproducible bit for bit.

    Returns an array of length n + 1 summing to 1.
    """
    p = np.asarray(probabilities, dtype=np.float64)
    if p.ndim != 1:
        raise ValueError("probabilities must be one-dimensional")
    pmf = np.zeros(p.size + 1, dtype=np.float64)
    pmf[0] = 1.0
    for i in range(p.size):
        q = float(p[i])
        # The right-hand side is fully evaluated before assignment, so this is a
        # correct in-place fold and not a partially-updated one.
        pmf[1 : i + 2] = pmf[1 : i + 2] * (1.0 - q) + pmf[0 : i + 1] * q
        pmf[0] *= 1.0 - q
    return pmf


def tail_at_least(pmf: np.ndarray, wins: int) -> float:
    """P(W >= wins). `math.fsum` so the answer does not depend on summation order."""
    k = max(0, min(int(wins), pmf.size - 1))
    return float(math.fsum(pmf[k:].tolist()))


def mid_p_at_least(pmf: np.ndarray, wins: int) -> float:
    """P(W > wins) + 0.5 * P(W = wins) - the standard mid-p correction.

    THE TIE-BREAK, AND THE ONLY PLACE IT MATTERS. The plain tail is exactly 1.0
    for every winless team no matter what it played, so 0-12 against the hardest
    schedule in the country and 0-12 against the softest would tie and fall
    through to alphabetical order. Mid-p separates them the right way round - a
    larger P(W = 0) means the reference team would plausibly have gone winless
    too, which is less damning - and for every other record it is a strictly
    monotone function of the same quantities, so it cannot reorder anything the
    primary key already separates.
    """
    k = max(0, min(int(wins), pmf.size - 1))
    return float(math.fsum(pmf[k:].tolist()) - 0.5 * float(pmf[k]))


def win_probabilities(
    q_ref: float,
    opponent_power: list[float] | np.ndarray,
    sites: list[int] | np.ndarray,
    h: float,
    sigma: float,
) -> np.ndarray:
    """p_g = Phi((q_ref - Power_opp + h*site) / sigma). The same mu as report 02 §3.4."""
    mu = (
        float(q_ref)
        - np.asarray(opponent_power, dtype=np.float64)
        + float(h) * np.asarray(sites, dtype=np.float64)
    )
    return np.asarray(ndtr(mu / float(sigma)), dtype=np.float64)


def schedule_odds(
    wins: int,
    opponent_power: list[float] | np.ndarray,
    sites: list[int] | np.ndarray,
    q_ref: float,
    h: float,
    sigma: float,
) -> tuple[float, float, float]:
    """(tail, mid_p, expected_wins) for one team's exact schedule. Scalar reference.

    The whole of candidate C for a single team, in five lines, with nothing in it
    that a reader has to take on trust.
    """
    p = win_probabilities(q_ref, opponent_power, sites, h, sigma)
    pmf = poisson_binomial_pmf(p)
    return (
        tail_at_least(pmf, wins),
        mid_p_at_least(pmf, wins),
        float(math.fsum(p.tolist())),
    )


def _key(tail: float) -> float:
    """-log10(P), clamped so a pathological config cannot write an infinity."""
    return float(min(MAX_KEY, -math.log10(max(tail, MIN_TAIL))))


# ------------------------------------------------------------------- the batch fit


@dataclass(frozen=True)
class _Schedule:
    """Every (team, opponent power, site, won) triple in a window.

    NOTE WHAT IS ABSENT: there is no margin column. Candidate C cannot use margin
    because this structure does not carry it.
    """

    teams: tuple[str, ...]
    team_index: np.ndarray
    opponent_power: np.ndarray
    sites: np.ndarray
    won: np.ndarray


def _schedule(games: pl.DataFrame, power: PowerSource) -> _Schedule:
    games = games.sort("game_id")
    home = games["home_team"].to_list()
    away = games["away_team"].to_list()
    home_won = (games["home_points"] - games["away_points"]).to_numpy().astype(np.float64) > 0.0
    neutral = games["neutral_site"].to_numpy()

    teams = tuple(sorted(set(home) | set(away)))
    index = {t: i for i, t in enumerate(teams)}

    n = len(home)
    team_index = np.empty(2 * n, dtype=np.int64)
    opponent = np.empty(2 * n, dtype=np.int64)
    sites = np.empty(2 * n, dtype=np.float64)
    won = np.empty(2 * n, dtype=bool)

    team_index[0::2] = [index[t] for t in home]
    team_index[1::2] = [index[t] for t in away]
    opponent[0::2] = [index[t] for t in away]
    opponent[1::2] = [index[t] for t in home]
    sites[0::2] = np.where(neutral, 0.0, 1.0)
    sites[1::2] = np.where(neutral, 0.0, -1.0)
    won[0::2] = home_won
    won[1::2] = ~home_won

    power_vector = np.array([power.rating(t) for t in teams], dtype=np.float64)
    return _Schedule(
        teams=teams,
        team_index=team_index,
        opponent_power=power_vector[opponent],
        sites=sites,
        won=won,
    )


@dataclass(frozen=True)
class OddsFit:
    """Candidate C's published output, and everything needed to audit it."""

    tail: dict[str, float]
    mid_p: dict[str, float]
    key: dict[str, float]
    expected_wins: dict[str, float]
    wins: dict[str, int]
    losses: dict[str, int]
    q_ref: QRef
    power: PowerSource
    sigma: float
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def teams(self) -> tuple[str, ...]:
        return tuple(sorted(self.tail))

    def surprise(self, team: str) -> float:
        """W_t - E[W | q_ref]: wins above what the reference team would manage.

        Published beside the key because it is the same story in units a fan
        already has. It is NOT the rank key: two teams can be equally many wins
        above expectation with very different probabilities of getting there.
        """
        return float(self.wins.get(team, 0)) - self.expected_wins.get(team, 0.0)

    def order_key(self, team: str) -> tuple[float, float, str]:
        """The published rank order: least probable record first.

        Ascending tail, then ascending mid-p (which only ever separates winless
        teams - see `mid_p_at_least`), then team name.
        """
        return (self.tail.get(team, 1.0), self.mid_p.get(team, 1.0), team)

    def as_params(self) -> dict[str, Any]:
        return {
            "layer": LAYER,
            "version": VERSION,
            "sigma": self.sigma,
            "ranking_key": "-log10(P(W >= W_t)) under a Poisson-binomial over the "
            "exact schedule; margin never enters",
            "tail_method": "exact_poisson_binomial_dp",
            "tie_break": "mid_p",
            "min_tail": MIN_TAIL,
            **self.q_ref.as_params(),
            **self.power.as_params(),
            **self.params,
        }


def fit(
    games: pl.DataFrame,
    config: dict[str, Any] | None = None,
    power: PowerSource | None = None,
    resume_games: pl.DataFrame | None = None,
    classes: dict[str, str] | None = None,
    q_ref_method: str | None = None,
    plays: pl.DataFrame | None = None,
    state: Any = None,
) -> OddsFit:
    """Schedule odds for every team. Pure function of its arguments.

    The argument surface deliberately mirrors `l4_resume.fit`, so the study could
    hand all three candidate orderings the identical Power source and the
    identical windows and know that nothing but the ordering rule differs - and so
    that the harness, the grid and the CLI can call either one interchangeably now
    that this one is the headline.

    `games` is the POWER window (the K of R(N, K)) and also the window q_ref is
    read off; `resume_games` is the RECORD window (the N), defaulting to `games`
    for the live surface. That split is the entire retroactive mechanism, exactly
    as it is for the résumé.

    `classes` defaults to the classification carried by `games` itself, so the
    q_ref pool is FBS-only without the caller having to remember (see
    `team_classes`). `plays` and `state` are forwarded to the Power source and are
    what make `[resume].power_source = "L3"` reachable from here.
    """
    from cfbpoll.model import l4_resume

    cfg = config if config is not None else load_config()
    odds_cfg = cfg.get("schedule_odds", {})
    method = q_ref_method or str(odds_cfg.get("q_ref_method", "power_rank_25"))
    fixed_value = float(odds_cfg.get("q_ref_fixed_points", 0.0))

    games = games.sort("game_id")
    if power is None:
        power = l4_resume.power_source(games, cfg, plays=plays, state=state)
    # ONE PLACE DECIDES sigma, and it is l4_resume.sigma_for. The résumé and this
    # ordering must not disagree about the denominator of a win probability: they
    # are published on the same row and a reader is entitled to assume the two
    # numbers were computed against the same assumption (review S6).
    sigma, sigma_source = l4_resume.sigma_for(power, cfg)

    if classes is None:
        classes = team_classes(games)
    q_ref = reference_quality(power, classes, method=method, fixed_value=fixed_value)
    window = games if resume_games is None else resume_games.sort("game_id")

    if window.is_empty():
        return OddsFit(
            tail={},
            mid_p={},
            key={},
            expected_wins={},
            wins={},
            losses={},
            q_ref=q_ref,
            power=power,
            sigma=sigma,
            params={"n_record_games": 0, "n_teams": 0, "sigma_source": sigma_source},
        )

    sched = _schedule(window, power)
    h = power.home_field
    p_all = win_probabilities(q_ref.value, sched.opponent_power, sched.sites, h, sigma)

    tail: dict[str, float] = {}
    mid: dict[str, float] = {}
    key: dict[str, float] = {}
    expected: dict[str, float] = {}
    wins: dict[str, int] = {}
    losses: dict[str, int] = {}

    for i, team in enumerate(sched.teams):
        rows = sched.team_index == i
        p = p_all[rows]
        w = int(np.count_nonzero(sched.won[rows]))
        pmf = poisson_binomial_pmf(p)
        t = tail_at_least(pmf, w)
        tail[team] = t
        mid[team] = mid_p_at_least(pmf, w)
        key[team] = _key(t)
        expected[team] = float(math.fsum(p.tolist()))
        wins[team] = w
        losses[team] = int(p.size) - w

    return OddsFit(
        tail=tail,
        mid_p=mid,
        key=key,
        expected_wins=expected,
        wins=wins,
        losses=losses,
        q_ref=q_ref,
        power=power,
        sigma=sigma,
        params={
            "n_record_games": int(window.height),
            "n_teams": len(sched.teams),
            "max_games_one_team": int(np.bincount(sched.team_index).max()),
            "sigma_source": sigma_source,
        },
    )


def odds_frame(fitted: OddsFit, classes: dict[str, str] | None = None) -> pl.DataFrame:
    """One row per team in published order. The same shape `l4_resume.resume_frame` writes.

    Ranks are assigned over FBS teams only, for the same reason and by the same
    rule as the résumé's: every team in the fit keeps its row, but the poll is a
    college football poll.
    """
    classes = classes or {}
    teams = sorted(fitted.tail, key=fitted.order_key)
    frame = pl.DataFrame(
        {
            "team": teams,
            "team_class": [classes.get(t, "unknown") for t in teams],
            "wins": pl.Series([fitted.wins[t] for t in teams], dtype=pl.Int32),
            "losses": pl.Series([fitted.losses[t] for t in teams], dtype=pl.Int32),
            "odds_key": [fitted.key[t] for t in teams],
            "tail_p": [fitted.tail[t] for t in teams],
            "mid_p": [fitted.mid_p[t] for t in teams],
            "expected_wins": [fitted.expected_wins[t] for t in teams],
            "surprise": [fitted.surprise(t) for t in teams],
            "power": [fitted.power.rating(t) for t in teams],
        }
    )
    is_fbs = frame["team_class"] == "fbs"
    ranks = np.full(frame.height, 0, dtype=np.int32)
    ranks[is_fbs.to_numpy()] = np.arange(1, int(is_fbs.sum()) + 1, dtype=np.int32)
    return frame.with_columns(
        rank=pl.when(is_fbs).then(pl.Series(ranks)).otherwise(None).cast(pl.Int32)
    ).select(
        "rank",
        "team",
        "team_class",
        "wins",
        "losses",
        "odds_key",
        "tail_p",
        "mid_p",
        "expected_wins",
        "surprise",
        "power",
    )


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None = None,
    through_week: int | None = None,
    state: Any = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Challenger-protocol entry point (report 03 §7.3): the headline poll's number.

    `games` and `plays` arrive ALREADY truncated by the harness - no system selects
    its own rows - and `through_week` is informational.

    Returns `-log10 P(W >= W_t)`, higher is better, which is the published rank
    key. ONE THING THIS SCALAR CANNOT CARRY, stated so nobody discovers it as a
    surprise: the published order breaks exact ties on mid-p, and the only exact
    ties are among WINLESS teams, whose plain tail is 1.0 by definition and whose
    key is therefore 0.0 for all of them. A harness that sorts on a single float
    breaks those ties by team name instead. It cannot affect retrodictive
    violations - a winless team is never the winner of anything, so no tie at zero
    can appear in a winner/loser pair - and it moves rank churn only among teams
    that have not won a game. The full ordering, mid-p included, is what
    `OddsFit.order_key` and every published artifact use.
    """
    del through_week
    return fit(games, config, plays=plays, state=state).key
