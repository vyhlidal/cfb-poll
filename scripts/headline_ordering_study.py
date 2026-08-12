"""Regenerate every number in docs/analysis/headline-ordering-study.md.

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
      uv run python scripts/headline_ordering_study.py --out out/ordering-study

Three candidate headline orderings, one dataset, eight axes. The three differ in
NOTHING except the rank key: each evaluation cell computes one Power source, one
L4 fit and one schedule-odds fit, and all three orderings are read off those same
objects. Any difference in the tables below is therefore a difference between the
ordering rules and cannot be a difference in the data.

    A  wins-based résumé, margin-aware variant as the tie-break among the
       saturated (unbeaten) teams only. THE CURRENT BEHAVIOUR.
           key = (-resume, -resume_margin, team)
    B  margin-aware résumé as the ordering for everyone.
           key = (-resume_margin, team)
    C  schedule odds: -log10 P(W >= W_t) for a reference-quality team against the
       exact schedule (model/schedule_odds.py). Margin never enters.
           key = (tail, mid_p, team)

and one NON-CANDIDATE reference ordering, carried through every table so that the
axes can be read honestly rather than credulously:

    P  the L3 Power rating itself. Power is the COMPANION layer and report 02 §3.5
       rules it out as the headline on purpose - a poll ordered by Power answers
       "who would win", not "who earned it". It is here because forward ordering
       accuracy is a PREDICTION metric, and knowing what a pure prediction scores
       on it is the only way to tell whether a résumé ordering doing well on that
       axis is evidence of desert or evidence of having quietly become a power
       rating.
           key = (-power, team)

Protocol, per report 02 §5.1: tune on 2021-2023, validate on 2024, and 2025 stays
locked. This script never loads 2025.

TWO DATA LIMITS ARE BINDING AND ARE CARRIED INTO EVERY TABLE (docs/data-findings.md):
  * 2021 and 2022 carry NO postseason rows at all, so "final" for those seasons
    means through conference championships, and they cannot appear in the
    postseason test at all.
  * The archive carries no CFP committee poll, so committee ranks in the case
    table come from report 02 §5.5's verified lists and are marked as such.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from scipy.stats import kendalltau, norm

from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.plays import load_plays
from cfbpoll.ingest.sportsdataverse import canonical_games, load_games
from cfbpoll.model import l4_resume, retro, schedule_odds

ORDERINGS: tuple[str, ...] = ("A", "B", "C", "P")
TUNE_SEASONS: tuple[int, ...] = (2021, 2022, 2023)
VALIDATE_SEASONS: tuple[int, ...] = (2024,)
SEASONS: tuple[int, ...] = TUNE_SEASONS + VALIDATE_SEASONS

#: Seasons whose archive carries postseason rows (docs/data-findings.md, and the
#: block comment in ingest/sportsdataverse.py).
POSTSEASON_SEASONS: tuple[int, ...] = (2023, 2024)

#: The six bowls of the New Year's Six, matched on the games table's `notes`.
NY6 = ("Rose", "Sugar", "Orange", "Cotton", "Fiesta", "Peach")

#: Final CFP committee rankings, report 02 §5.5, verified against official CFP
#: releases. 2021-2023 published a top 25 but §5.5 records only the top of each;
#: a team absent here is recorded as "not in §5.5's list", never as unranked.
COMMITTEE_FINAL: dict[int, dict[str, int]] = {
    2021: {"Alabama": 1, "Michigan": 2, "Georgia": 3, "Cincinnati": 4, "Notre Dame": 5,
           "Ohio State": 6},
    2022: {"Georgia": 1, "Michigan": 2, "TCU": 3, "Ohio State": 4, "Alabama": 5},
    2023: {"Michigan": 1, "Washington": 2, "Texas": 3, "Alabama": 4, "Florida State": 5},
    2024: {"Oregon": 1, "Georgia": 2, "Texas": 3, "Penn State": 4, "Notre Dame": 5,
           "Ohio State": 6, "Tennessee": 7, "Indiana": 8, "Boise State": 9, "SMU": 10,
           "Alabama": 11, "Arizona State": 12},
}

CASES: tuple[tuple[int, str], ...] = (
    (2023, "Liberty"),
    (2023, "James Madison"),
    (2021, "Cincinnati"),
    (2022, "Tulane"),
    (2024, "Army"),
    (2024, "Boise State"),
)


# --------------------------------------------------------------------------- ranks


@dataclass(frozen=True)
class Cell:
    """One R(N, K): the three orderings, plus everything they were read off."""

    season: int
    eval_order: int
    eval_label: str
    data_order: int
    surface: str  # "live" | "hindsight"
    ranks: dict[str, dict[str, int]]  # ordering -> team -> rank
    resume: l4_resume.L4Fit
    odds: schedule_odds.OddsFit
    fbs_teams: tuple[str, ...]


def _rank(order_key: Any, teams: list[str]) -> dict[str, int]:
    return {t: i + 1 for i, t in enumerate(sorted(teams, key=order_key))}


def cell_ranks(
    resume: l4_resume.L4Fit, odds: schedule_odds.OddsFit, fbs: list[str]
) -> dict[str, dict[str, int]]:
    """The three candidate orderings over the SAME fits. This is the whole study."""
    return {
        "A": _rank(resume.order_key, fbs),
        "B": _rank(lambda t: (-resume.resume_margin.get(t, 0.0), t), fbs),
        "C": _rank(odds.order_key, fbs),
        "P": _rank(lambda t: (-resume.power.rating(t), t), fbs),
    }


def build_cells(
    games: pl.DataFrame,
    plays: pl.DataFrame,
    season: int,
    cfg: dict[str, Any],
) -> tuple[list[Cell], list[windows.Bucket], dict[int, l4_resume.PowerSource]]:
    """Both surfaces, every bucket, all three orderings. One Power walk per season."""
    season_games = games.filter(pl.col("season") == season)
    buckets = windows.season_buckets(season_games, season)
    powers = retro.season_power(games, season, cfg, plays=plays, buckets=buckets)
    classes = _team_classes(season_games)
    final = buckets[-1]

    cells: list[Cell] = []
    for bucket in buckets:
        record = windows.games_through(
            season_games, season=season, week=bucket.week, season_type=bucket.season_type
        )
        fbs = sorted(
            {
                t
                for t in set(record["home_team"].to_list()) | set(record["away_team"].to_list())
                if classes.get(t) == "fbs"
            }
        )
        for surface, data_bucket in (("live", bucket), ("hindsight", final)):
            power_window = windows.games_through(
                season_games,
                season=season,
                week=data_bucket.week,
                season_type=data_bucket.season_type,
            )
            power = powers[data_bucket.order]
            resume = l4_resume.fit(power_window, cfg, power=power, resume_games=record)
            odds = schedule_odds.fit(
                power_window, cfg, power=power, resume_games=record, classes=classes
            )
            cells.append(
                Cell(
                    season=season,
                    eval_order=bucket.order,
                    eval_label=bucket.label,
                    data_order=data_bucket.order,
                    surface=surface,
                    ranks=cell_ranks(resume, odds, fbs),
                    resume=resume,
                    odds=odds,
                    fbs_teams=tuple(fbs),
                )
            )
    return cells, buckets, powers


def _team_classes(games: pl.DataFrame) -> dict[str, str]:
    out: dict[str, str] = {}
    for h, a, hc, ac in zip(
        games["home_team"].to_list(),
        games["away_team"].to_list(),
        games["home_class"].to_list(),
        games["away_class"].to_list(),
        strict=True,
    ):
        out[h] = hc
        out[a] = ac
    return out


def pick(cells: list[Cell], surface: str, eval_order: int) -> Cell:
    for c in cells:
        if c.surface == surface and c.eval_order == eval_order:
            return c
    raise KeyError(f"no {surface} cell at eval_order {eval_order}")


# ------------------------------------------------------- 1. the simulation question


def compress_prediction(margin: float, threshold: float, alpha: float) -> float:
    """Pasteur's compression of extreme PREDICTIONS, report 02 §2.13.

    `[margin.prediction_compression]` is enabled in the config and is not yet
    applied anywhere on the model path, so this study computes it explicitly and
    reports both numbers rather than silently reporting one of them.
    """
    m = abs(float(margin))
    if m <= threshold:
        return float(margin)
    compressed = threshold + (1.0 / alpha) * ((m - (threshold - 1.0)) ** alpha - 1.0)
    return math.copysign(compressed, margin)


def head_to_head(
    powers: dict[int, l4_resume.PowerSource],
    order: int,
    a: str,
    b: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """L3 predicted margin for a on a NEUTRAL field against b, and P(a wins)."""
    power = powers[order]
    sigma = float(cfg["resume"]["sigma"])
    pc = cfg["margin"]["prediction_compression"]
    raw = power.rating(a) - power.rating(b)
    comp = (
        compress_prediction(raw, float(pc["threshold"]), float(pc["alpha"]))
        if bool(pc["enabled"])
        else raw
    )
    return {
        "team": a,
        "opponent": b,
        "power_team": power.rating(a),
        "power_opponent": power.rating(b),
        "predicted_margin_raw": float(raw),
        "predicted_margin_compressed": float(comp),
        "p_team_wins": float(norm.cdf(raw / sigma)),
    }


# ---------------------------------------------------- 2. retrodictive violations


def violations(ranks: dict[str, int], games: pl.DataFrame) -> dict[str, float]:
    """Games whose loser is ranked above its winner (report 02 §2.12, §5.2)."""
    margin = (games["home_points"] - games["away_points"]).to_numpy()
    home = games["home_team"].to_list()
    away = games["away_team"].to_list()
    bad = 0
    total = 0
    for h, a, m in zip(home, away, margin, strict=True):
        if h not in ranks or a not in ranks or m == 0:
            continue
        total += 1
        winner, loser = (h, a) if m > 0 else (a, h)
        if ranks[winner] > ranks[loser]:
            bad += 1
    return {
        "violations": float(bad),
        "games": float(total),
        "rate": float(bad) / total if total else float("nan"),
    }


def fbs_pair(games: pl.DataFrame) -> pl.DataFrame:
    return games.filter((pl.col("home_class") == "fbs") & (pl.col("away_class") == "fbs"))


# ------------------------------------------------------ 3. forward ordering accuracy


def forward_accuracy(
    ranks: dict[str, int], future: pl.DataFrame, top_n: int | None = None
) -> dict[str, float]:
    """Among future games between two ranked teams, does the better-ranked team win?

    The natural out-of-sample test of an ORDERING, as opposed to of a rating: it
    asks only what the ordering claims, which is who is ahead of whom.
    """
    margin = (future["home_points"] - future["away_points"]).to_numpy()
    home = future["home_team"].to_list()
    away = future["away_team"].to_list()
    hits = 0.0
    total = 0
    for h, a, m in zip(home, away, margin, strict=True):
        if h not in ranks or a not in ranks or m == 0:
            continue
        if top_n is not None and (ranks[h] > top_n or ranks[a] > top_n):
            continue
        total += 1
        favourite = h if ranks[h] < ranks[a] else a
        winner = h if m > 0 else a
        hits += 1.0 if favourite == winner else 0.0
    return {"hits": hits, "games": float(total), "rate": hits / total if total else float("nan")}


def games_after(season_games: pl.DataFrame, bucket_order: int, buckets: list[windows.Bucket]):
    later = [b for b in buckets if b.order > bucket_order]
    if not later:
        return season_games.head(0)
    keep = pl.DataFrame(
        {
            "season_type": [b.season_type for b in later],
            "week": pl.Series([b.week for b in later], dtype=pl.Int32),
        }
    )
    return season_games.join(keep, on=["season_type", "week"], how="semi")


# ---------------------------------------------------------------- 4. the postseason


def pre_postseason_bucket(
    season_games: pl.DataFrame, buckets: list[windows.Bucket]
) -> windows.Bucket | None:
    """The last bucket before any FBS postseason game. The final poll of record.

    `[weights].final_poll_excludes_non_cfp_bowls = true` says the final published
    poll is the one computed BEFORE non-CFP bowls, which is a choice of window,
    not a discount. This is that window.
    """
    post = season_games.filter(pl.col("game_type").is_in(["cfp", "bowl_non_cfp"]))
    if post.is_empty():
        return None
    orders = {
        b.order
        for b in buckets
        if not windows.games_in_bucket(post, b).is_empty()
    }
    first_post = min(orders)
    before = [b for b in buckets if b.order < first_post]
    return before[-1] if before else None


def postseason_segments(
    season_games: pl.DataFrame, notes: dict[int, str]
) -> dict[str, pl.DataFrame]:
    post = fbs_pair(season_games.filter(pl.col("game_type").is_in(["cfp", "bowl_non_cfp"])))
    ids = post["game_id"].to_list()
    is_ny6 = [any(n in (notes.get(int(g)) or "") for n in NY6) for g in ids]
    ny6 = post.filter(pl.Series(is_ny6))
    return {
        "cfp": post.filter(pl.col("game_type") == "cfp"),
        "ny6_non_cfp": ny6.filter(pl.col("game_type") != "cfp"),
        "bowls_non_cfp": post.filter(pl.col("game_type") == "bowl_non_cfp"),
        "all_postseason": post,
    }


# ------------------------------------------------------------------ orchestration


def run(out_dir: Path) -> dict[str, Any]:
    cfg = load_config()
    out_dir.mkdir(parents=True, exist_ok=True)

    games = load_games(list(SEASONS))
    # RAW plays: `plays_for` inside the L3 walk does the join itself, and joining
    # twice duplicates the games columns. The harness passes raw plays too.
    plays = load_plays(list(SEASONS))
    raw = canonical_games(list(SEASONS))
    notes_by_id = dict(
        zip(
            [int(g) for g in raw["game_id"].to_list()],
            _notes_column(list(SEASONS)),
            strict=True,
        )
    )

    report: dict[str, Any] = {"config_seasons": list(SEASONS), "orderings": list(ORDERINGS)}
    per_season: dict[int, dict[str, Any]] = {}
    all_cells: dict[int, list[Cell]] = {}
    all_buckets: dict[int, list[windows.Bucket]] = {}
    all_powers: dict[int, dict[int, l4_resume.PowerSource]] = {}

    for season in SEASONS:
        cells, buckets, powers = build_cells(games, plays, season, cfg)
        all_cells[season] = cells
        all_buckets[season] = buckets
        all_powers[season] = powers
        per_season[season] = {"buckets": [b.label for b in buckets]}

    report["study_1_head_to_head"] = study_1(all_powers, all_buckets, games, cfg)
    report["study_2_violations"] = study_2(all_cells, all_buckets, games)
    report["study_3_forward"] = study_3(all_cells, all_buckets, games, cfg)
    report["study_4_postseason"] = study_4(all_cells, all_buckets, games, notes_by_id)
    report["study_5_retro_convergence"] = study_5(all_cells, all_buckets)
    report["study_6_cases"] = study_6(all_cells, all_buckets, games)
    report["study_7_churn"] = study_7(all_cells, all_buckets, cfg)
    report["study_8_qref"] = study_8(all_cells, all_buckets, all_powers, games, cfg)
    report["study_9_boards"] = study_9(all_cells, all_buckets, games)
    report["per_season"] = {str(k): v for k, v in per_season.items()}

    (out_dir / "study.json").write_text(json.dumps(report, indent=2, default=float))
    return report


def _notes_column(seasons: list[int]) -> list[str | None]:
    from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE

    frames = [
        pl.read_parquet(
            DEFAULT_ARCHIVE / "schedules" / f"cfb_schedules_{s}.parquet",
            columns=["game_id", "notes"],
        )
        for s in sorted(set(seasons))
    ]
    joined = pl.concat(frames, how="vertical").sort("game_id")
    return joined["notes"].to_list()


def study_1(powers, buckets, games, cfg) -> dict[str, Any]:
    """L3 predicted margins for the flagship pairs, on a neutral field."""
    rows: list[dict[str, Any]] = []
    for season, a, b, tag in (
        (2023, "Liberty", "Georgia", "flagship"),
        (2021, "Cincinnati", "Alabama", "flagship"),
        (2023, "James Madison", "Michigan", "jmu_vs_top10"),
        (2023, "James Madison", "Georgia", "jmu_vs_top10"),
        (2023, "Liberty", "Oregon", "played_it"),
    ):
        season_games = games.filter(pl.col("season") == season)
        pre = pre_postseason_bucket(season_games, buckets[season])
        live_order = pre.order if pre is not None else buckets[season][-1].order
        final_order = buckets[season][-1].order
        for surface, order in (("live_final", live_order), ("hindsight_final", final_order)):
            row = head_to_head(powers[season], order, a, b, cfg)
            row |= {"season": season, "surface": surface, "tag": tag}
            rows.append(row)

    # The top-10 Power teams of 2023, so "JMU vs a top-10 team" is a stated set.
    season_games = games.filter(pl.col("season") == 2023)
    classes = _team_classes(season_games)
    final_power = powers[2023][buckets[2023][-1].order]
    top10 = sorted(
        (t for t in final_power.ratings if classes.get(t) == "fbs"),
        key=lambda t: (-final_power.rating(t), t),
    )[:10]
    jmu = [
        head_to_head(powers[2023], buckets[2023][-1].order, "James Madison", t, cfg)
        | {"season": 2023, "surface": "hindsight_final", "tag": "jmu_vs_each_top10"}
        for t in top10
    ]
    return {"pairs": rows, "top10_2023": top10, "jmu_vs_top10": jmu}


def study_2(cells, buckets, games) -> dict[str, Any]:
    """Retrodictive violations, per ordering, per season, on both surfaces."""
    final_rows: list[dict[str, Any]] = []
    by_week: list[dict[str, Any]] = []
    for season, season_cells in cells.items():
        season_games = games.filter(pl.col("season") == season)
        for cell in season_cells:
            record = fbs_pair(
                windows.games_through(
                    season_games,
                    season=season,
                    week=_bucket_at(buckets[season], cell.eval_order).week,
                    season_type=_bucket_at(buckets[season], cell.eval_order).season_type,
                )
            )
            for ordering in ORDERINGS:
                v = violations(cell.ranks[ordering], record)
                row = {
                    "season": season,
                    "surface": cell.surface,
                    "eval_label": cell.eval_label,
                    "eval_order": cell.eval_order,
                    "ordering": ordering,
                    **v,
                }
                by_week.append(row)
                if cell.eval_order == buckets[season][-1].order:
                    final_rows.append(row)
    return {"final": final_rows, "by_week": by_week}


def _bucket_at(buckets: list[windows.Bucket], order: int) -> windows.Bucket:
    for b in buckets:
        if b.order == order:
            return b
    raise KeyError(order)


def study_3(cells, buckets, games, cfg) -> dict[str, Any]:
    """Forward ordering accuracy: among FUTURE games, does the higher rank win?"""
    start_week = int(cfg["publication"]["headline_start_week"])
    rows: list[dict[str, Any]] = []
    for season, season_cells in cells.items():
        season_games = games.filter(pl.col("season") == season)
        for cell in season_cells:
            if cell.surface != "live":
                continue
            bucket = _bucket_at(buckets[season], cell.eval_order)
            if bucket.season_type != "regular" or bucket.week < start_week:
                continue
            future = fbs_pair(games_after(season_games, cell.eval_order, buckets[season]))
            regular = future.filter(pl.col("game_type").is_in(["regular", "conf_champ"]))
            for ordering in ORDERINGS:
                ranks = cell.ranks[ordering]
                rows.append(
                    {
                        "season": season,
                        "eval_label": cell.eval_label,
                        "eval_week": bucket.week,
                        "ordering": ordering,
                        "all_pairs": forward_accuracy(ranks, regular),
                        "top25_pairs": forward_accuracy(ranks, regular, top_n=25),
                    }
                )
    return {"rows": rows}


def study_4(cells, buckets, games, notes) -> dict[str, Any]:
    """The postseason test. 2023 and 2024 only - 2021/2022 carry no postseason rows."""
    rows: list[dict[str, Any]] = []
    for season in POSTSEASON_SEASONS:
        season_games = games.filter(pl.col("season") == season)
        pre = pre_postseason_bucket(season_games, buckets[season])
        if pre is None:
            continue
        cell = pick(cells[season], "live", pre.order)
        segments = postseason_segments(season_games, notes)
        for name, frame in segments.items():
            for ordering in ORDERINGS:
                rows.append(
                    {
                        "season": season,
                        "poll_bucket": pre.label,
                        "segment": name,
                        "ordering": ordering,
                        **forward_accuracy(cell.ranks[ordering], frame),
                    }
                )
    return {"rows": rows, "seasons_available": list(POSTSEASON_SEASONS)}


def study_5(cells, buckets) -> dict[str, Any]:
    """Retro-convergence: mean |rank_live - rank_hindsight| by week, per ordering."""
    rows: list[dict[str, Any]] = []
    for season, season_cells in cells.items():
        for bucket in buckets[season]:
            live = pick(season_cells, "live", bucket.order)
            hind = pick(season_cells, "hindsight", bucket.order)
            for ordering in ORDERINGS:
                a, b = live.ranks[ordering], hind.ranks[ordering]
                shared = sorted(set(a) & set(b))
                deltas = np.array([abs(a[t] - b[t]) for t in shared], dtype=np.float64)
                top = np.array([a[t] <= 25 or b[t] <= 25 for t in shared], dtype=bool)
                rows.append(
                    {
                        "season": season,
                        "eval_label": bucket.label,
                        "eval_order": bucket.order,
                        "eval_week": bucket.week,
                        "eval_season_type": bucket.season_type,
                        "ordering": ordering,
                        "mean_abs_delta": float(deltas.mean()) if deltas.size else float("nan"),
                        "max_abs_delta": float(deltas.max()) if deltas.size else float("nan"),
                        "mean_abs_delta_top25": float(deltas[top].mean())
                        if top.any()
                        else float("nan"),
                        "n_teams": int(deltas.size),
                    }
                )
    return {
        "rows": rows,
        "unbeaten_tracks": _unbeaten_tracks(cells, buckets),
        "unbeaten_movement": _unbeaten_movement(cells, buckets),
    }


def _unbeaten_movement(cells, buckets) -> list[dict[str, Any]]:
    """live -> hindsight movement restricted to UNBEATEN teams. The owner's question.

    "If, by week 13 it's clear that Liberty's schedule is actually quite tough in
    weeks 1-5 maybe things change?" - this is that, in numbers, for every unbeaten
    team in every week of every season under all three orderings.
    """
    out: list[dict[str, Any]] = []
    for season, season_cells in cells.items():
        for bucket in buckets[season]:
            live = pick(season_cells, "live", bucket.order)
            hind = pick(season_cells, "hindsight", bucket.order)
            unbeaten = sorted(
                t
                for t in live.fbs_teams
                if live.resume.losses.get(t, 1) == 0 and live.resume.wins.get(t, 0) > 0
            )
            if not unbeaten:
                continue
            row: dict[str, Any] = {
                "season": season,
                "eval_label": bucket.label,
                "eval_order": bucket.order,
                "eval_week": bucket.week,
                "eval_season_type": bucket.season_type,
                "n_unbeaten": len(unbeaten),
            }
            for ordering in ORDERINGS:
                d = np.array(
                    [abs(live.ranks[ordering][t] - hind.ranks[ordering][t]) for t in unbeaten],
                    dtype=np.float64,
                )
                row[f"mean_move_{ordering}"] = float(d.mean())
                row[f"max_move_{ordering}"] = float(d.max())
            out.append(row)
    return out


def _unbeaten_tracks(cells, buckets) -> list[dict[str, Any]]:
    """Every week of Liberty 2023 (and the other cases) on both surfaces."""
    out: list[dict[str, Any]] = []
    for season, team in CASES:
        for bucket in buckets[season]:
            live = pick(cells[season], "live", bucket.order)
            hind = pick(cells[season], "hindsight", bucket.order)
            if team not in live.ranks["A"]:
                continue
            row: dict[str, Any] = {
                "season": season,
                "team": team,
                "eval_label": bucket.label,
                "eval_order": bucket.order,
                "wins": live.resume.wins.get(team),
                "losses": live.resume.losses.get(team),
                "saturated": live.resume.saturated.get(team),
            }
            for ordering in ORDERINGS:
                row[f"live_{ordering}"] = live.ranks[ordering].get(team)
                row[f"hindsight_{ordering}"] = hind.ranks[ordering].get(team)
                row[f"move_{ordering}"] = live.ranks[ordering].get(team, 0) - hind.ranks[
                    ordering
                ].get(team, 0)
            row["tail_live"] = live.odds.tail.get(team)
            row["tail_hindsight"] = hind.odds.tail.get(team)
            row["q_ref_live"] = live.odds.q_ref.value
            row["q_ref_hindsight"] = hind.odds.q_ref.value
            out.append(row)
    return out


def study_9(cells, buckets, games) -> dict[str, Any]:
    """The boards themselves, and the structural fact the whole study turns on.

    `unbeaten_floor` is the claim in numbers: under A a SATURATED (unbeaten) team
    sits on the published bracket, every other unbeaten team sits on the same
    bracket, and every one-loss team's root is strictly below it. So an unbeaten
    team's rank under A is bounded above by the number of unbeaten teams, on BOTH
    surfaces, whatever the season later reveals about its schedule. The count of
    unbeaten-below-one-loss inversions under A must therefore be exactly zero,
    and that is asserted here rather than argued.
    """
    boards: list[dict[str, Any]] = []
    inversions: list[dict[str, Any]] = []
    for season in SEASONS:
        season_games = games.filter(pl.col("season") == season)
        pre = pre_postseason_bucket(season_games, buckets[season])
        poll = pre if pre is not None else buckets[season][-1]
        for surface in ("live", "hindsight"):
            cell = pick(cells[season], surface, poll.order)
            unbeaten = sorted(
                t
                for t in cell.fbs_teams
                if cell.resume.losses.get(t, 1) == 0 and cell.resume.wins.get(t, 0) > 0
            )
            for ordering in ORDERINGS:
                ranks = cell.ranks[ordering]
                top = sorted(ranks, key=lambda t: ranks[t])[:25]
                boards.append(
                    {
                        "season": season,
                        "surface": surface,
                        "poll_bucket": poll.label,
                        "ordering": ordering,
                        "top25": [
                            {
                                "rank": ranks[t],
                                "team": t,
                                "record": f"{cell.resume.wins[t]}-{cell.resume.losses[t]}",
                                "unbeaten": cell.resume.losses[t] == 0,
                            }
                            for t in top
                        ],
                    }
                )
                worst_unbeaten = max((ranks[t] for t in unbeaten), default=0)
                below = sorted(
                    t
                    for t in cell.fbs_teams
                    if cell.resume.losses.get(t, 0) >= 1 and ranks[t] < worst_unbeaten
                )
                inversions.append(
                    {
                        "season": season,
                        "surface": surface,
                        "ordering": ordering,
                        "n_unbeaten": len(unbeaten),
                        "unbeaten": unbeaten,
                        "worst_unbeaten_rank": worst_unbeaten,
                        "n_one_loss_or_worse_ranked_above_an_unbeaten": len(below),
                        "teams_above": below[:12],
                    }
                )
    return {"boards": boards, "unbeaten_floor": inversions}


def study_6(cells, buckets, games) -> dict[str, Any]:
    """The case table: where each team lands under each ordering, live and hindsight."""
    rows: list[dict[str, Any]] = []
    for season, team in CASES:
        season_games = games.filter(pl.col("season") == season)
        pre = pre_postseason_bucket(season_games, buckets[season])
        final = buckets[season][-1]
        poll = pre if pre is not None else final
        live = pick(cells[season], "live", poll.order)
        hind = pick(cells[season], "hindsight", poll.order)
        if team not in live.ranks["A"]:
            rows.append({"season": season, "team": team, "note": "absent from the fit"})
            continue
        row: dict[str, Any] = {
            "season": season,
            "team": team,
            "poll_bucket": poll.label,
            "record": f"{live.resume.wins[team]}-{live.resume.losses[team]}",
            "saturated": live.resume.saturated[team],
            "committee_final": COMMITTEE_FINAL.get(season, {}).get(team),
            "committee_source": "report 02 §5.5 (verified CFP release)",
            "tail_live": live.odds.tail.get(team),
            "tail_hindsight": hind.odds.tail.get(team),
            "power_live": live.resume.power.rating(team),
            "power_hindsight": hind.resume.power.rating(team),
        }
        for ordering in ORDERINGS:
            row[f"live_{ordering}"] = live.ranks[ordering][team]
            row[f"hindsight_{ordering}"] = hind.ranks[ordering][team]
        row["subsequent"] = _subsequent_results(season_games, team, poll)
        rows.append(row)
    return {"rows": rows}


def _subsequent_results(season_games: pl.DataFrame, team: str, poll: windows.Bucket) -> list[str]:
    later = season_games.filter(
        (pl.col("home_team") == team) | (pl.col("away_team") == team)
    ).filter(pl.col("game_type").is_in(["cfp", "bowl_non_cfp"]))
    out = []
    for r in later.iter_rows(named=True):
        home, away = r["home_team"], r["away_team"]
        hp, ap = r["home_points"], r["away_points"]
        opponent = away if home == team else home
        ours, theirs = (hp, ap) if home == team else (ap, hp)
        out.append(f"{'W' if ours > theirs else 'L'} {ours}-{theirs} vs {opponent}")
    return out


def study_7(cells, buckets, cfg) -> dict[str, Any]:
    """Week-over-week rank churn on the live surface, per ordering."""
    start_week = int(cfg["publication"]["headline_start_week"])
    rows: list[dict[str, Any]] = []
    for season, season_cells in cells.items():
        ordered = [b for b in buckets[season]]
        for prev, cur in zip(ordered[:-1], ordered[1:], strict=True):
            if cur.season_type != "regular" or cur.week < start_week:
                continue
            a_cell = pick(season_cells, "live", prev.order)
            b_cell = pick(season_cells, "live", cur.order)
            for ordering in ORDERINGS:
                a, b = a_cell.ranks[ordering], b_cell.ranks[ordering]
                shared = sorted(set(a) & set(b))
                d = np.array([abs(a[t] - b[t]) for t in shared], dtype=np.float64)
                top = np.array([a[t] <= 25 or b[t] <= 25 for t in shared], dtype=bool)
                rows.append(
                    {
                        "season": season,
                        "from": prev.label,
                        "to": cur.label,
                        "ordering": ordering,
                        "churn_all": float(d.mean()) if d.size else float("nan"),
                        "churn_top25": float(d[top].mean()) if top.any() else float("nan"),
                        "n": int(d.size),
                    }
                )
    return {"rows": rows}


def study_8(cells, buckets, powers, games, cfg) -> dict[str, Any]:
    """Does C's q_ref choice materially move the ordering?"""
    methods = list(cfg["schedule_odds"]["q_ref_sensitivity"])
    rows: list[dict[str, Any]] = []
    liberty: list[dict[str, Any]] = []
    for season in SEASONS:
        season_games = games.filter(pl.col("season") == season)
        classes = _team_classes(season_games)
        pre = pre_postseason_bucket(season_games, buckets[season])
        poll = pre if pre is not None else buckets[season][-1]
        record = windows.games_through(
            season_games, season=season, week=poll.week, season_type=poll.season_type
        )
        power = powers[season][poll.order]
        fbs = sorted({t for t in _teams(record) if classes.get(t) == "fbs"})
        base_ranks: dict[str, dict[str, int]] = {}
        for method in methods:
            fitted = schedule_odds.fit(
                record, cfg, power=power, resume_games=record, classes=classes,
                q_ref_method=method,
            )
            base_ranks[method] = _rank(fitted.order_key, fbs)
            rows.append(
                {
                    "season": season,
                    "poll_bucket": poll.label,
                    "method": method,
                    "q_ref": fitted.q_ref.value,
                    "q_ref_team": fitted.q_ref.team,
                }
            )
            for s, team in CASES:
                if s == season and team in base_ranks[method]:
                    liberty.append(
                        {
                            "season": season,
                            "team": team,
                            "method": method,
                            "rank": base_ranks[method][team],
                            "tail": fitted.tail[team],
                        }
                    )
        default = base_ranks[methods[0]]
        for method in methods[1:]:
            other = base_ranks[method]
            shared = sorted(set(default) & set(other))
            d = np.array([abs(default[t] - other[t]) for t in shared], dtype=np.float64)
            top_default = {t for t in shared if default[t] <= 25}
            top_other = {t for t in shared if other[t] <= 25}
            tau = kendalltau(
                [default[t] for t in shared], [other[t] for t in shared]
            ).statistic
            rows.append(
                {
                    "season": season,
                    "poll_bucket": poll.label,
                    "method": method,
                    "vs_default_mean_abs_rank_delta": float(d.mean()),
                    "vs_default_max_abs_rank_delta": float(d.max()),
                    "vs_default_kendall_tau": float(tau),
                    "top25_membership_changes": len(top_default ^ top_other) // 2,
                }
            )
    return {"rows": rows, "cases": liberty, "methods": methods}


def _teams(frame: pl.DataFrame) -> set[str]:
    return set(frame["home_team"].to_list()) | set(frame["away_team"].to_list())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="out/ordering-study", type=Path)
    args = parser.parse_args()
    report = run(args.out)
    print(f"wrote {args.out / 'study.json'}")
    print(json.dumps({k: type(v).__name__ for k, v in report.items()}, indent=2))


if __name__ == "__main__":
    main()
