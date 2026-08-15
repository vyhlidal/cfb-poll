"""The grading loop. "We thought this, here is what we now know, here is what was wrong."

This is the product. The 2026 top 25 is the thing that gets screenshotted; THIS is
the thing that makes publishing it defensible, because a preseason ranking whose
author never returns to it is an opinion, and a preseason ranking that gets marked
in public every week against a poll it is not allowed to influence is a
measurement.

WHAT IT COMPARES. Three rankings, per evaluation week N of the target season:

    projected_rank      the Projection, published before week 1 and NEVER
                        recomputed. It is frozen the moment it ships; a
                        projection that drifts is a projection that cannot be
                        graded.
    live_rank           R(N, N) - the poll as it was published in week N
    hindsight_rank      R(N, final) - the same week re-scored with the season's
                        answers, which is constraint 4's whole product

Both poll surfaces come out of `model/retro.py` untouched. The Projection reads
them; it never writes to them, and no number it produces can reach them.

THE TWO DELTAS SAY DIFFERENT THINGS AND KEEPING THEM APART IS THE POINT.
`projection_vs_live` is "how wrong were we about what would happen so far".
`projection_vs_hindsight` is "how wrong were we about what these teams turned out
to BE" - which is the fairer question in week 5, because in week 5 the live poll
is itself provisional and grading a preseason guess against a provisional answer
double-counts the noise. The published headline uses hindsight and shows live
beside it.

ATTRIBUTION, AT TWO LEVELS, AND NEITHER IS A CAUSAL CLAIM.

  PER TEAM, it is accounting. Each recipe term contributed a signed number of
  points to that team's projection - a CREDIT if positive, a DEBIT if negative,
  both measured against a league-average team. When the team lands below its
  projection, the largest positive contribution is the credit that did not pay
  off, and that is the sentence we publish: "we credited Texas +4.1 points for
  returning production; they are 6.4 points below the projection." It says which
  term was carrying the error, not which term CAUSED it, and the difference is
  stated on the artifact rather than left for a reader to assume.

  ACROSS THE LEAGUE, it is a regression and it is the half that improves the
  model. Regress every team's projection error on each term's contribution:

      error_t = g_0 + sum_j g_j * contribution_jt + e_t

  A negative g_j means teams we credited on term j systematically underperformed
  - we OVER-CREDITED that term this season - and the size of g_j says by how
  much. That is a falsifiable, season-over-season statement about the recipe
  rather than about a team, it is exactly what the next version's coefficient
  should move toward, and it is why this loop is worth running for a decade.

  THE STATISTICAL HEALTH WARNING, published beside the numbers rather than in a
  footnote: with about 134 teams and four terms this regression is estimable, and
  the terms are correlated with each other (a team that changed coach also tends
  to lose production), so a single season's g_j is suggestive and not a verdict.
  One season is one data point about the recipe. The loop's value is cumulative.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.model import retro
from cfbpoll.projection import PROJECTION_VERSION, recipe, seasons

__all__ = [
    "GRADE_COLUMNS",
    "attribution",
    "grade_season",
    "grade_week",
    "story_lines",
]

GRADE_COLUMNS: tuple[str, ...] = (
    "season",
    "eval_order",
    "eval_label",
    "team",
    "projected_rank",
    "projected_power",
    "live_rank",
    "hindsight_rank",
    "delta_vs_live",
    "delta_vs_hindsight",
    "actual_power",
    "power_error",
    "contrib_intercept",
    "contrib_prior_power",
    "contrib_returning_production",
    "contrib_coaching_change",
    "contrib_net_portal",
    "suspect_term",
    "suspect_contribution",
)


def _rank_map(frame: pl.DataFrame, eval_order: int) -> dict[str, int]:
    sub = frame.filter((pl.col("eval_order") == eval_order) & pl.col("rank").is_not_null())
    return dict(zip(sub["team"].to_list(), sub["rank"].to_list(), strict=True))


def _power_map(frame: pl.DataFrame, eval_order: int) -> dict[str, float]:
    sub = frame.filter(pl.col("eval_order") == eval_order)
    return dict(zip(sub["team"].to_list(), sub["power"].to_list(), strict=True))


def _suspect(row: dict[str, Any], error: float) -> tuple[str | None, float]:
    """The term carrying the error: the largest contribution pointing the wrong way.

    Over-projected (error < 0) means we look for the biggest CREDIT that did not
    pay off. Under-projected (error > 0) means the biggest DEBIT we should not
    have applied. The intercept is excluded because "the league average was
    wrong" is not an offseason assumption anybody made about a team.
    """
    signed = {
        term: float(row.get(f"contrib_{term}", 0.0) or 0.0)
        for term in recipe.TERMS
    }
    wanted = [
        (abs(value), term, value)
        for term, value in signed.items()
        if (value > 0 and error < 0) or (value < 0 and error > 0)
    ]
    if not wanted:
        return (None, 0.0)
    _, term, value = max(wanted, key=lambda item: (item[0], item[1]))
    return (term, value)


def grade_week(
    projection: pl.DataFrame,
    live: pl.DataFrame,
    hindsight: pl.DataFrame,
    eval_order: int,
    eval_label: str,
    season: int,
) -> pl.DataFrame:
    """One evaluation week: projection against both poll surfaces, with attribution.

    Only teams the poll RANKED in that week appear, because a rank delta against
    a team the poll never ranked is not a number. The projection's own rank is
    kept even when it is outside 25 - "we had them 41st and they are 6th" is the
    row a reader most wants to see.
    """
    live_ranks = _rank_map(live, eval_order)
    hind_ranks = _rank_map(hindsight, eval_order)
    hind_power = _power_map(hindsight, eval_order)

    projected = dict(
        zip(projection["team"].to_list(), projection["projected_rank"].to_list(), strict=True)
    )
    projected_power = dict(
        zip(projection["team"].to_list(), projection["projected_power"].to_list(), strict=True)
    )
    contributions = {row["team"]: row for row in projection.to_dicts()}

    rows: list[dict[str, Any]] = []
    for team in sorted(set(live_ranks) | set(hind_ranks)):
        p_rank = projected.get(team)
        p_power = projected_power.get(team)
        actual = hind_power.get(team)
        error = (
            float(actual) - float(p_power)
            if actual is not None and p_power is not None
            else None
        )
        source = contributions.get(team, {})
        suspect, suspect_value = _suspect(source, error) if error is not None else (None, 0.0)
        rows.append(
            {
                "season": int(season),
                "eval_order": int(eval_order),
                "eval_label": str(eval_label),
                "team": team,
                "projected_rank": p_rank,
                "projected_power": p_power,
                "live_rank": live_ranks.get(team),
                "hindsight_rank": hind_ranks.get(team),
                # Positive means the poll has them HIGHER than we projected, i.e.
                # we under-rated them. Same sign convention as retro.movers, on
                # purpose: two tables with opposite conventions is how a reader
                # ends up quoting the wrong direction.
                "delta_vs_live": (
                    p_rank - live_ranks[team] if p_rank is not None and team in live_ranks else None
                ),
                "delta_vs_hindsight": (
                    p_rank - hind_ranks[team] if p_rank is not None and team in hind_ranks else None
                ),
                "actual_power": actual,
                "power_error": error,
                **{
                    f"contrib_{term}": source.get(f"contrib_{term}")
                    for term in ("intercept", *recipe.TERMS)
                },
                "suspect_term": suspect,
                "suspect_contribution": suspect_value,
            }
        )
    frame = pl.DataFrame(rows) if rows else pl.DataFrame(schema={c: pl.Null for c in GRADE_COLUMNS})
    return frame.select(GRADE_COLUMNS).sort(["eval_order", "hindsight_rank", "team"])


def attribution(graded: pl.DataFrame) -> dict[str, Any]:
    """League-level: regress the projection error on each term's contribution.

    Returns one coefficient per term with its standard error and a plain sentence.
    A NEGATIVE coefficient on term j means the teams that term credited came in
    below their projections - we over-credited it - and a positive one means we
    under-credited it. Zero, within a standard error or two, means the term was
    priced about right this season, which is also a result.
    """
    usable = graded.filter(pl.col("power_error").is_not_null())
    columns = [f"contrib_{term}" for term in recipe.TERMS]
    usable = usable.drop_nulls(columns)
    if usable.height <= len(columns) + 1:
        return {"n_teams": int(usable.height), "terms": {}, "note": "too few teams to attribute"}

    x = np.column_stack(
        [np.ones(usable.height)]
        + [usable[c].to_numpy().astype(np.float64) for c in columns]
    )
    y = usable["power_error"].to_numpy().astype(np.float64)
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ coef
    dof = max(int(x.shape[0] - x.shape[1]), 1)
    sigma2 = float(resid @ resid) / dof
    stderr = np.sqrt(np.clip(np.diag(np.linalg.pinv(x.T @ x)) * sigma2, 0.0, None))

    terms: dict[str, Any] = {}
    for i, term in enumerate(recipe.TERMS):
        value = float(coef[i + 1])
        error = float(stderr[i + 1])
        z = value / error if error > 0 else 0.0
        if abs(z) < 2.0:
            verdict = "priced about right"
        elif value < 0:
            verdict = "OVER-credited"
        else:
            verdict = "UNDER-credited"
        terms[term] = {
            "coefficient": value,
            "standard_error": error,
            "z": z,
            "verdict": verdict,
            "sentence": _attribution_sentence(term, value, z, verdict),
        }
    return {
        "n_teams": int(usable.height),
        "intercept": float(coef[0]),
        "terms": terms,
        "health_warning": (
            "One season is one data point about the recipe, and the terms are "
            "correlated with each other - a team that changed coach also tends "
            "to lose production - so a single season's coefficient is suggestive "
            "and not a verdict. The loop's value is cumulative."
        ),
    }


_TERM_NAMES = {
    "prior_power": "last season's rating",
    "returning_production": "returning production",
    "coaching_change": "the coaching-change penalty",
    "net_portal": "net portal flow",
}


def _attribution_sentence(term: str, value: float, z: float, verdict: str) -> str:
    name = _TERM_NAMES.get(term, term)
    if verdict == "priced about right":
        return (
            f"We priced {name} about right: teams it credited came in within "
            f"{abs(z):.1f} standard errors of their projection."
        )
    direction = "below" if value < 0 else "above"
    return (
        f"We {verdict.lower()} {name}: every point of Power this term handed a "
        f"team, that team finished {abs(value):.2f} points {direction} its "
        f"projection ({abs(z):.1f} standard errors)."
    )


def grade_season(
    projection: pl.DataFrame,
    games: pl.DataFrame,
    season: int,
    plays: pl.DataFrame | None = None,
    config: dict[str, Any] | None = None,
    from_week: int | None = None,
) -> dict[str, Any]:
    """The whole loop for one season: every week graded, plus the attribution.

    `from_week` defaults to `[publication].headline_start_week`, because grading a
    frozen preseason guess against a poll the project itself declines to publish
    would be scoring it against a number nobody was shown. The earlier weeks are
    still computed and carried in `weeks`; `headline_week` names the first one the
    published surface leads with.
    """
    cfg = config if config is not None else load_config()
    season_games = games.filter(pl.col("season") == int(season))
    buckets = windows.season_buckets(season_games, int(season))
    powers = retro.season_power(season_games, int(season), cfg, plays=plays, buckets=buckets)
    live = retro.live_surface(
        season_games, int(season), cfg, buckets=buckets, plays=plays, powers=powers
    )
    hindsight = retro.hindsight_surface(
        season_games, int(season), cfg, buckets=buckets, plays=plays, powers=powers
    )

    start = int(from_week or cfg["publication"]["headline_start_week"])
    frames = [
        grade_week(projection, live, hindsight, b.order, b.label, int(season)) for b in buckets
    ]
    graded = pl.concat([f for f in frames if f.height], how="vertical") if frames else None
    if graded is None or not graded.height:
        return {"season": int(season), "weeks": [], "attribution": {}, "n_weeks": 0}

    final_order = buckets[-1].order
    headline = next(
        (b for b in buckets if b.season_type == "regular" and b.week >= start), buckets[-1]
    )
    return {
        "season": int(season),
        "projection_version": PROJECTION_VERSION,
        "settled_definition": seasons.SETTLED_DEFINITION,
        "headline_week": headline.label,
        "headline_eval_order": headline.order,
        "weeks": [
            {"eval_order": b.order, "eval_label": b.label, "n_teams": int(f.height)}
            for b, f in zip(buckets, frames, strict=True)
            if f.height
        ],
        "n_weeks": len([f for f in frames if f.height]),
        "table": graded,
        "attribution": attribution(graded.filter(pl.col("eval_order") == final_order)),
        "attribution_at_headline": attribution(
            graded.filter(pl.col("eval_order") == headline.order)
        ),
    }


def story_lines(
    graded: pl.DataFrame, eval_order: int, top_n: int = 5, within_rank: int = 25
) -> list[str]:
    """The published sentences, in the "we thought / we now know / what was wrong" shape.

    Ordered by the size of the miss against the HINDSIGHT surface, because that
    is the surface that answers "what did these teams turn out to be" rather than
    "what had happened by Tuesday". Every sentence names the projection as a
    projection, in the sentence itself and not only in a header - a line that gets
    screenshotted has to carry its own label.

    `within_rank` keeps a row only when the team is inside the top N on ONE of
    the two rankings. Without it this table is permanently owned by the bottom of
    the league, where a nine-win improvement is worth ninety places and a
    top-25-relevant miss of twenty is invisible: 2024's four largest raw misses
    are UL Monroe (#130 -> #33) and three like it. Both interesting rows survive
    the filter - a team we had 9th that finished 105th, and a team we had 106th
    that finished 13th - because each is inside 25 on one side.
    """
    week = graded.filter(
        (pl.col("eval_order") == eval_order)
        & pl.col("delta_vs_hindsight").is_not_null()
        & pl.col("projected_rank").is_not_null()
    )
    if within_rank:
        week = week.filter(
            (pl.col("projected_rank") <= within_rank) | (pl.col("hindsight_rank") <= within_rank)
        )
    if not week.height:
        return []
    week = week.with_columns(miss=pl.col("delta_vs_hindsight").abs()).sort(
        ["miss", "team"], descending=[True, False]
    )

    lines: list[str] = []
    for row in week.head(top_n).to_dicts():
        team = row["team"]
        projected = int(row["projected_rank"])
        actual = int(row["hindsight_rank"])
        direction = "under-rated" if projected > actual else "over-rated"
        suspect = row.get("suspect_term")
        contribution = float(row.get("suspect_contribution") or 0.0)
        error = float(row.get("power_error") or 0.0)
        tail = (
            f" The projection's largest term pointing the wrong way was "
            f"{_TERM_NAMES.get(suspect, suspect)}, worth "
            f"{contribution:+.2f} points of Power."
            if suspect
            else " No single term of the projection points the wrong way; the miss "
            "is in the level, not in one assumption."
        )
        lines.append(
            f"The projection had {team} at #{projected}. The poll now has them at "
            f"#{actual} — we {direction} them by {abs(projected - actual)} places, "
            f"and they are {error:+.1f} points of Power off the projected figure."
            + tail
        )
    return lines
