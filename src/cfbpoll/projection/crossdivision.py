"""What an FCS-earned rating is worth on the FBS scale, measured from the games that cross.

THE PROBLEM, STATED AS THE 2026 PROJECTION STATED IT AGAINST ITSELF. North Dakota
State finished the 2025 fit on +24.52 Power - eighth of the 315 teams the
all-divisions universe rates, above Texas Tech and above Texas - because they beat
FCS opposition by a lot and the fit universe rates every division in one system.
They move up to FBS for 2026. Under `projection-2.0.0` that rating transplanted at
FACE VALUE and put them tenth in the published board, and the artifact said so in
its own caveats: "treat that as the single least trustworthy row on this page."

A caveat is not a treatment. This module is the treatment, and every number in it
is estimated from the FBS-vs-FCS games the archive already holds.

WHAT THE BRIDGE GAMES SAY, AND WHAT THEY DO NOT

Run the model's own prediction over the 602 FBS-vs-FCS games in 2021-2025 and the
FBS side beats it by **+17.3 points on average**. That is the headline number and
it is the wrong one to apply, because most of a 17-point miss is not about
divisions at all: this model under-predicts EVERY mismatch. Ridge shrinks, the
margin response is compressed, and the same regression over FBS-vs-FBS games says
`actual = 1.35 * predicted`. A 20-point favourite wins by 27.

So the estimator carries the model's own predicted margin as a regressor and asks
what is LEFT for the division boundary:

    actual_margin = a + b * predicted_margin + gap * bridge

`bridge` is +1 when the home team is FBS and the away team is not, -1 when it is
the other way round, and 0 for the 7,232 games inside one division. `gap` is what
this module publishes. Over 2021-2025 it is **13.4 points, standard error 0.6**,
a t of twenty-two, and it is stable walk-forward: measured on 2021 alone it is
9.4, and it converges to 13.4 as the bridge sample grows to 602 games. The
dispersion slope that explains the rest of the raw miss is 1.30.

That is the honest cross-division adjustment: **an FCS team's rating overstates
what it is worth against FBS opposition by about thirteen points**, over and above
the compression that affects everybody. It is stored negated, so a consumer adds
it.

AND THEN THE SECOND MEASUREMENT, WHICH CUTS THE OTHER WAY AND IS THE REASON THIS
MODULE HAS TWO CONSTANTS INSTEAD OF ONE

A team that is PROMOTED is not a randomly drawn FCS team. It is a program that
spent years buying its way to FBS scholarship numbers and FBS staff, and the
archive can score that directly: six programs moved up between 2022 and 2025 -
James Madison, Jacksonville State, Sam Houston, Kennesaw State, Delaware,
Missouri State - and they played 68 games against FBS opponents in their first
FBS season. Carry their FCS rating forward untouched and those 68 games come out
**-3.6 points, standard error 1.9**. Carry it forward with the full thirteen-point
division gap and nothing else and the error grows instead of shrinking: mean
absolute error goes from 12.4 points to about 14, and straight-up accuracy falls
from 69.1% to 63.2%.

Both numbers are real and they are not in conflict, because they answer different
questions:

    cross_division_gap   what an FCS roster is worth against FBS opposition
                         THIS SEASON, as an opponent.       -13.4, n=602 games
    promotion_bump       what a program gains by being the kind of program that
                         gets promoted.                      +9.8, n=68 games

A promoted team carries both, and they net to the -3.6 the 68 games actually
measured. An FCS team that stays FCS and shows up on somebody's schedule carries
only the first.

WHERE THIS IS THIN, SAID PLAINLY, BECAUSE IT IS THE PART THAT DECIDES NDSU

The promotion bump rests on six programs whose FCS-year ratings ran from -13.6 to
+6.0 relative to the FBS mean. **North Dakota State sits at +17.4, outside that
range at both ends of the argument**, and no amount of care makes six programs
into evidence about a seventh that is three standard deviations better than the
best of them. That is why `promotion_bump` is a LEVER with a published range and
not a buried constant: the default is the value 68 games chose, and a reader who
thinks a promoted program should not get credit it did not earn on the field can
set it to zero and watch the board move.

The one piece of direct evidence about North Dakota State is their own record
against FBS teams, and this module's `receipts` returns it so it can be printed
beside their row rather than summarised: they have played two, and lost both -
Arizona by 3 in 2022 and Colorado by 5 in 2024 - and in both the model, carrying
their FCS rating at face value, expected them to do better than they did.

WALK-FORWARD, LIKE EVERYTHING ELSE. `measure(..., through_season=Y)` reads games
from seasons <= Y and nothing later, so the constant a projection for season Y+1
carries is one that existed before season Y+1 started. `chain.py` depends on that
being true and `tests/unit/test_crossdivision.py` asserts it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

__all__ = [
    "DEFAULT_MIN_BRIDGE_GAMES",
    "DivisionCalibration",
    "adjust_carried_ratings",
    "bridge_frame",
    "measure",
    "promotion_frame",
    "receipts",
    "season_receipts",
]

#: Below this many bridge games the gap is not estimated at all and the
#: calibration reports itself as unmeasured. Three seasons of bridge games is
#: about 350; one season is about 120. Forty is a floor against a degenerate
#: fit, not a claim that forty is enough.
DEFAULT_MIN_BRIDGE_GAMES = 40

_NON_FBS = ("fcs", "ii", "iii", "unknown")


def _venue(at_home: bool, neutral: bool) -> str:
    """Where the named team played. NEUTRAL WINS over nominal hosting.

    A neutral-site game has a nominal home team in the schedule frame and no home
    field on the grass. The arithmetic has always used `site = 0.0` for these; the
    printed label used to say "home" for the nominal host, which is the kind of
    small lie that ends up quoted back at you.
    """
    if neutral:
        return "neutral"
    return "home" if at_home else "away"


@dataclass(frozen=True)
class DivisionCalibration:
    """Two measured constants, their standard errors, and the samples behind them.

    `as_dict` is what lands on a published artifact. Every field on it is either a
    number a reader can check or the size of the sample that produced it - there
    is no field here whose only support is that somebody chose it.
    """

    #: Points an FCS-earned rating overstates on the FBS scale, as a NEGATIVE
    #: number ready to be added to a rating. Estimated net of the model's general
    #: under-prediction of mismatches, which is what `dispersion` carries, and
    #: negated from the regression's own sign so that a consumer only ever adds.
    cross_division_gap: float
    cross_division_gap_se: float
    #: Points a promoted program gains back, as a POSITIVE number. Estimated on
    #: the games promoted teams actually played in their first FBS season.
    promotion_bump: float
    promotion_bump_se: float
    #: The slope of actual margin on predicted margin over every game in the
    #: universe. Published because it is the reason the raw bridge miss (+17.3)
    #: and the division gap (13.4) are different numbers, and a reader who sees
    #: only one of them will think the other is a mistake.
    dispersion: float
    #: The raw, uncorrected mean bridge miss. The number that looks like the
    #: answer and is not.
    raw_bridge_miss: float
    n_bridge_games: int
    n_promotion_games: int
    n_promoted_teams: int
    through_season: int
    #: THE EXTRAPOLATION GUARD, and the single most important number here for the
    #: North Dakota State row. The best FIRST FBS SEASON any promoted program has
    #: actually had, as a rating relative to that season's FBS mean. James Madison
    #: in 2022 holds it at +5.75, which was 32nd in FBS. No promoted team is
    #: projected above it, because the promotion bump is fitted on six programs
    #: and applying it to a team rated eleven points above the best of them is
    #: extrapolation wearing a measurement's clothes.
    promotion_ceiling_rel: float = 0.0
    #: Which program holds the ceiling, and in which season. Published so the rule
    #: reads as a football fact rather than a magic constant.
    promotion_ceiling_team: str = ""
    promotion_ceiling_season: int = 0
    #: The highest FCS-year rating in the promotion sample, also relative to the
    #: FBS mean. The top of the range the bump is actually evidence about.
    promotion_support_max_rel: float = 0.0
    #: False when the archive did not hold enough bridge games to estimate. Both
    #: constants are then 0.0 and the projection carries ratings unchanged, which
    #: is the pre-liberation behaviour and is stated rather than silently applied.
    measured: bool = True

    @property
    def promoted_net(self) -> float:
        """What a promoted team's rating actually moves by. The number to check."""
        return float(self.cross_division_gap + self.promotion_bump)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cross_division_gap": round(float(self.cross_division_gap), 4),
            "cross_division_gap_se": round(float(self.cross_division_gap_se), 4),
            "promotion_bump": round(float(self.promotion_bump), 4),
            "promotion_bump_se": round(float(self.promotion_bump_se), 4),
            "promoted_net": round(self.promoted_net, 4),
            "dispersion": round(float(self.dispersion), 4),
            "raw_bridge_miss": round(float(self.raw_bridge_miss), 4),
            "n_bridge_games": int(self.n_bridge_games),
            "n_promotion_games": int(self.n_promotion_games),
            "n_promoted_teams": int(self.n_promoted_teams),
            "through_season": int(self.through_season),
            "measured": bool(self.measured),
            "promotion_ceiling_rel": round(float(self.promotion_ceiling_rel), 4),
            "promotion_ceiling_team": self.promotion_ceiling_team,
            "promotion_ceiling_season": int(self.promotion_ceiling_season),
            "promotion_support_max_rel": round(float(self.promotion_support_max_rel), 4),
            "promotion_ceiling_rule": (
                "No promoted team is projected above the best first FBS season any "
                "promoted program has actually had. That ceiling is held by "
                f"{self.promotion_ceiling_team or 'nobody yet'}"
                + (f" in {self.promotion_ceiling_season}" if self.promotion_ceiling_season else "")
                + "."
            ),
            "definition": (
                "cross_division_gap is the coefficient on a bridge indicator in "
                "actual_margin ~ predicted_margin + bridge, over every game in the fit "
                "universe. It is the part of the FBS-over-FCS miss that belongs to the "
                "division boundary rather than to this model's general under-prediction "
                "of mismatches, which `dispersion` carries. promotion_bump is what "
                "promoted programs won back in their own first FBS seasons."
            ),
        }


def _in_universe(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.filter(
        pl.col("completed")
        & pl.col("home_points").is_not_null()
        & pl.col("away_points").is_not_null()
        & pl.col("home_class").is_in(["fbs", *_NON_FBS])
        & pl.col("away_class").is_in(["fbs", *_NON_FBS])
    )


def bridge_frame(
    games: pl.DataFrame,
    power_by_season: dict[int, dict[str, float]],
    home_field_by_season: dict[int, float],
    through_season: int,
) -> pl.DataFrame:
    """Every rated game in seasons <= `through_season`, with the model's own call on it.

    `bridge` is the signed division indicator: +1 when the home side is FBS and
    the visitor is not, -1 when the visitor is FBS and the host is not, 0 inside
    a division. Signed rather than absolute so the coefficient reads directly as
    "points the FBS side outperforms its prediction by", with no orientation step
    that could select on the predictor's own sign.
    """
    rows: list[dict[str, Any]] = []
    for season in sorted(s for s in power_by_season if s <= int(through_season)):
        power = power_by_season[season]
        h = float(home_field_by_season.get(season, 0.0))
        frame = _in_universe(games.filter(pl.col("season") == season))
        for row in frame.iter_rows(named=True):
            home, away = row["home_team"], row["away_team"]
            if home not in power or away not in power:
                continue
            home_fbs = row["home_class"] == "fbs"
            away_fbs = row["away_class"] == "fbs"
            site = 0.0 if row["neutral_site"] else 1.0
            rows.append(
                {
                    "season": season,
                    "predicted": float(power[home]) - float(power[away]) + site * h,
                    "actual": float(row["home_points"] - row["away_points"]),
                    "bridge": float(int(home_fbs) - int(away_fbs)),
                }
            )
    if not rows:
        return pl.DataFrame(
            schema={
                "season": pl.Int64,
                "predicted": pl.Float64,
                "actual": pl.Float64,
                "bridge": pl.Float64,
            }
        )
    return pl.DataFrame(rows)


def promotion_frame(
    games: pl.DataFrame,
    power_by_season: dict[int, dict[str, float]],
    home_field_by_season: dict[int, float],
    fbs_by_season: dict[int, set[str]],
    through_season: int,
) -> pl.DataFrame:
    """Games a promoted team played against FBS opposition in its FIRST FBS season.

    The predictor is the team's PRIOR (FCS) rating carried forward untouched, so
    the mean residual on this frame IS the promotion shift a projection would
    have suffered, in the units a projection works in.

    Opponents are restricted to FBS. A promoted team's remaining FCS opponents
    would price the residual with the very gap this frame exists to keep separate.
    """
    rows: list[dict[str, Any]] = []
    seasons = sorted(s for s in fbs_by_season if s <= int(through_season))
    for season in seasons:
        prior = season - 1
        if prior not in fbs_by_season or prior not in power_by_season:
            continue
        promoted = sorted(fbs_by_season[season] - fbs_by_season[prior])
        if not promoted:
            continue
        power = power_by_season[prior]
        h = float(home_field_by_season.get(prior, 0.0))
        frame = _in_universe(games.filter(pl.col("season") == season))
        for row in frame.iter_rows(named=True):
            for team, opponent, at_home in (
                (row["home_team"], row["away_team"], True),
                (row["away_team"], row["home_team"], False),
            ):
                if team not in promoted:
                    continue
                if opponent not in fbs_by_season[season] or opponent not in power:
                    continue
                if team not in power:
                    continue
                site = 0.0 if row["neutral_site"] else (1.0 if at_home else -1.0)
                margin = float(row["home_points"] - row["away_points"]) * (1.0 if at_home else -1.0)
                rows.append(
                    {
                        "season": season,
                        "team": team,
                        "opponent": opponent,
                        "predicted": float(power[team]) - float(power[opponent]) + site * h,
                        "actual": margin,
                    }
                )
    if not rows:
        return pl.DataFrame(
            schema={
                "season": pl.Int64,
                "team": pl.String,
                "opponent": pl.String,
                "predicted": pl.Float64,
                "actual": pl.Float64,
            }
        )
    return pl.DataFrame(rows)


def measure(
    games: pl.DataFrame,
    power_by_season: dict[int, dict[str, float]],
    home_field_by_season: dict[int, float],
    fbs_by_season: dict[int, set[str]],
    through_season: int,
    min_bridge_games: int = DEFAULT_MIN_BRIDGE_GAMES,
) -> DivisionCalibration:
    """Both constants, from seasons <= `through_season` and nothing later.

    The walk-forward guarantee is the whole point of the `through_season`
    argument: a projection for season Y calls this with `Y - 1`, so every number
    it carries existed before a snap of season Y was played.
    """
    through = int(through_season)
    bridge = bridge_frame(games, power_by_season, home_field_by_season, through)
    is_bridge = bridge.filter(pl.col("bridge") != 0.0) if bridge.height else bridge

    if is_bridge.height < int(min_bridge_games):
        return DivisionCalibration(
            cross_division_gap=0.0,
            cross_division_gap_se=0.0,
            promotion_bump=0.0,
            promotion_bump_se=0.0,
            dispersion=1.0,
            raw_bridge_miss=0.0,
            n_bridge_games=int(is_bridge.height),
            n_promotion_games=0,
            n_promoted_teams=0,
            through_season=through,
            measured=False,
        )

    y = bridge["actual"].to_numpy()
    p = bridge["predicted"].to_numpy()
    b = bridge["bridge"].to_numpy()
    design = np.column_stack([np.ones_like(y), p, b])
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ coefficients
    dof = max(len(y) - design.shape[1], 1)
    sigma2 = float(residual @ residual) / dof
    stderr = np.sqrt(np.clip(np.diag(np.linalg.pinv(design.T @ design)) * sigma2, 0.0, None))

    # The regression coefficient reads "points the FBS side beats its prediction
    # by". What a carried rating needs is the same quantity pointed the other way,
    # so it is negated here, once, and every consumer can simply add it.
    gap = -float(coefficients[2])
    gap_se = float(stderr[2])
    dispersion = float(coefficients[1])
    # `bridge` is +1 or -1 on this frame, so the mean miss is oriented onto the
    # FBS side rather than averaged across the two hosting arrangements, which
    # would cancel it to nearly zero and look like good news.
    raw = float(((is_bridge["actual"] - is_bridge["predicted"]) * is_bridge["bridge"]).mean())

    ceiling_rel, ceiling_team, ceiling_season, support_max = _promotion_support(
        power_by_season, fbs_by_season, through
    )

    promotion = promotion_frame(
        games, power_by_season, home_field_by_season, fbs_by_season, through
    )
    if promotion.height:
        # A promoted team carries `gap` PLUS `bump`, and these 68 games measure
        # the NET shift directly. Solving for the bump this way is what makes both
        # constants simultaneously true of the same sample instead of two
        # independent estimates that quietly double-count.
        miss = (promotion["actual"] - promotion["predicted"]).to_numpy()
        net = float(np.mean(miss))
        bump = net - gap
        # The bump is `net - gap`, so its uncertainty carries BOTH terms. Reporting
        # only the net's standard error would understate exactly the number this
        # module leans on when it argues the promotion evidence is thin, which is
        # the argument the North Dakota State row turns on.
        net_se = float(np.std(miss, ddof=1) / np.sqrt(len(miss))) if len(miss) > 1 else 0.0
        bump_se = float(np.sqrt(net_se**2 + gap_se**2))
        n_promoted = int(promotion["team"].n_unique())
    else:
        bump = 0.0
        bump_se = 0.0
        n_promoted = 0

    return DivisionCalibration(
        cross_division_gap=gap,
        cross_division_gap_se=gap_se,
        promotion_bump=bump,
        promotion_bump_se=bump_se,
        dispersion=dispersion,
        raw_bridge_miss=raw,
        n_bridge_games=int(is_bridge.height),
        n_promotion_games=int(promotion.height),
        n_promoted_teams=n_promoted,
        through_season=through,
        measured=True,
        promotion_ceiling_rel=ceiling_rel,
        promotion_ceiling_team=ceiling_team,
        promotion_ceiling_season=ceiling_season,
        promotion_support_max_rel=support_max,
    )


def _fbs_mean(power: dict[str, float], fbs: set[str]) -> float:
    """The FBS mean of one season's ratings. The origin every `rel` figure is on."""
    values = [float(power[t]) for t in fbs if t in power]
    return float(np.mean(values)) if values else 0.0


def _promotion_support(
    power_by_season: dict[int, dict[str, float]],
    fbs_by_season: dict[int, set[str]],
    through_season: int,
) -> tuple[float, str, int, float]:
    """(ceiling_rel, who holds it, when, top of the FCS-year support), all walk-forward.

    The ceiling is the best FIRST FBS SEASON on record for a promoted program,
    measured relative to that season's FBS mean so it is comparable across
    seasons whose rating scales differ. The support maximum is the best FCS-year
    rating in the same sample, and it is what says whether a new promotion is
    inside the evidence or outside it.
    """
    best_rel = float("-inf")
    best_team = ""
    best_season = 0
    support = float("-inf")
    for season in sorted(s for s in fbs_by_season if s <= int(through_season)):
        prior = season - 1
        if prior not in fbs_by_season or prior not in power_by_season:
            continue
        if season not in power_by_season:
            continue
        mean_now = _fbs_mean(power_by_season[season], fbs_by_season[season])
        mean_then = _fbs_mean(power_by_season[prior], fbs_by_season[prior])
        for team in sorted(fbs_by_season[season] - fbs_by_season[prior]):
            if team not in power_by_season[season] or team not in power_by_season[prior]:
                continue
            rel_after = float(power_by_season[season][team]) - mean_now
            rel_before = float(power_by_season[prior][team]) - mean_then
            support = max(support, rel_before)
            if rel_after > best_rel:
                best_rel, best_team, best_season = rel_after, team, int(season)
    if best_rel == float("-inf"):
        return 0.0, "", 0, 0.0
    return float(best_rel), best_team, best_season, float(support)


def adjust_carried_ratings(
    ratings: dict[str, float],
    source_fbs: set[str],
    target_fbs: set[str],
    calibration: DivisionCalibration,
    gap_weight: float = 1.0,
    bump_weight: float = 1.0,
    apply_ceiling: bool = True,
) -> tuple[dict[str, float], dict[str, str]]:
    """Move every non-FBS rating onto the FBS scale. Returns (ratings, provenance).

    Three cases, and the provenance string names which one every team got so an
    artifact can print it:

      `fbs`          the team was FBS in the source season. Untouched.
      `promoted`     the team was not FBS in the source season and IS FBS in the
                     target season. Carries the gap AND the bump.
      `cross_division` the team was not FBS in either. Carries the gap alone,
                     which is what an opponent is worth.

    `gap_weight` and `bump_weight` are the lever hooks. Both default to 1.0 - the
    measured values, applied in full - and both are exposed in the lever registry
    so a reader can turn either off and regenerate the board.
    """
    if not calibration.measured:
        return dict(ratings), dict.fromkeys(ratings, "unadjusted")

    gap = float(calibration.cross_division_gap) * float(gap_weight)
    bump = float(calibration.promotion_bump) * float(bump_weight)
    # The ceiling is expressed relative to the FBS mean, so it has to be put back
    # on the ratings' own origin before anything can be compared with it.
    ceiling = (
        _fbs_mean(ratings, source_fbs) + float(calibration.promotion_ceiling_rel)
        if apply_ceiling and calibration.promotion_ceiling_team
        else float("inf")
    )

    out: dict[str, float] = {}
    provenance: dict[str, str] = {}
    for team, rating in ratings.items():
        if team in source_fbs:
            out[team] = float(rating)
            provenance[team] = "fbs"
        elif team in target_fbs:
            promoted = float(rating) + gap + bump
            if promoted > ceiling:
                out[team] = ceiling
                provenance[team] = "promoted_at_ceiling"
            else:
                out[team] = promoted
                provenance[team] = "promoted"
        else:
            out[team] = float(rating) + gap
            provenance[team] = "cross_division"
    return out, provenance


def receipts(
    games: pl.DataFrame,
    team: str,
    power_by_season: dict[int, dict[str, float]],
    home_field_by_season: dict[int, float],
    through_season: int,
) -> list[dict[str, Any]]:
    """Every game `team` played against an FBS opponent while it was not FBS itself.

    THIS IS THE PRINTABLE PART. A cross-division adjustment estimated over 602
    games is a fact about the league; what a reader arguing about North Dakota
    State wants is North Dakota State's own record against FBS teams, and this
    returns it game by game with the model's expectation beside the result.
    """
    out: list[dict[str, Any]] = []
    for season in sorted(s for s in power_by_season if s <= int(through_season)):
        power = power_by_season[season]
        h = float(home_field_by_season.get(season, 0.0))
        frame = _in_universe(games.filter(pl.col("season") == season))
        for row in frame.iter_rows(named=True):
            for side, opponent, at_home, klass, opp_class in (
                (row["home_team"], row["away_team"], True, row["home_class"], row["away_class"]),
                (row["away_team"], row["home_team"], False, row["away_class"], row["home_class"]),
            ):
                if side != team or klass == "fbs" or opp_class != "fbs":
                    continue
                if side not in power or opponent not in power:
                    continue
                site = 0.0 if row["neutral_site"] else (1.0 if at_home else -1.0)
                margin = float(row["home_points"] - row["away_points"]) * (1.0 if at_home else -1.0)
                predicted = float(power[side]) - float(power[opponent]) + site * h
                out.append(
                    {
                        "season": int(season),
                        "week": int(row["week"]),
                        "opponent": opponent,
                        "at": _venue(at_home, bool(row["neutral_site"])),
                        "result": "won" if margin > 0 else ("tied" if margin == 0 else "lost"),
                        "margin": float(margin),
                        "model_expected_margin": float(predicted),
                        "miss": float(margin - predicted),
                    }
                )
    return sorted(out, key=lambda r: (r["season"], r["week"]))


def season_receipts(
    games: pl.DataFrame,
    team: str,
    season: int,
    power: dict[str, float],
    home_field: float,
) -> list[dict[str, Any]]:
    """One team's whole season, each game with the model's own expectation beside it.

    THE OTHER HALF OF THE PRINTABLE ARGUMENT. `receipts` answers "what has this
    FCS program done against FBS teams"; this answers "why is this FBS team rated
    where it is", which is the same question a reader asks about every contested
    row on the board. Sorted by how far the game landed from expectation, so the
    two or three games actually doing the work are at the top instead of buried in
    a twelve-row table nobody reads.

    The residual is NOT zero-centred and that is worth knowing before quoting one:
    ridge shrinkage compresses ratings, so the league-wide mean of this statistic
    is positive and a team at +3 is nearer average than it looks.
    """
    frame = _in_universe(games.filter(pl.col("season") == int(season)))
    out: list[dict[str, Any]] = []
    for row in frame.iter_rows(named=True):
        for side, opponent, at_home in (
            (row["home_team"], row["away_team"], True),
            (row["away_team"], row["home_team"], False),
        ):
            if side != team or side not in power or opponent not in power:
                continue
            site = 0.0 if row["neutral_site"] else (1.0 if at_home else -1.0)
            margin = float(row["home_points"] - row["away_points"]) * (1.0 if at_home else -1.0)
            predicted = float(power[side]) - float(power[opponent]) + site * float(home_field)
            out.append(
                {
                    "season": int(season),
                    "week": int(row["week"]),
                    "game_type": row["game_type"],
                    "opponent": opponent,
                    "opponent_power": round(float(power[opponent]), 2),
                    "at": _venue(at_home, bool(row["neutral_site"])),
                    "result": "won" if margin > 0 else ("tied" if margin == 0 else "lost"),
                    "margin": float(margin),
                    "model_expected_margin": round(float(predicted), 2),
                    "miss": round(float(margin - predicted), 2),
                }
            )
    return sorted(out, key=lambda r: r["miss"])
