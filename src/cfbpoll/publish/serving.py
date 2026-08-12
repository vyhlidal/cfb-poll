"""The serving contract — the ONE place that turns `out/` into rows a page renders.

Report 03 §6.3 fixes the dependency direction: **the standalone repo never
imports from the sandbox; the sandbox never computes anything.** §7.2 says it
again from the other side — every rendered number is a SELECT. This module is
what makes that enforceable rather than aspirational, because both publication
targets are built from it and cannot drift:

    postgres.py   loads these rows into the cfb_* schema of report 03 §5.6
    fixtures.py   writes the same rows as JSON for the fork and for site dev

If a number is going to appear on the website, it is computed HERE and it lands
in both. Report 05 §7.2 states the rule the two renderers have to obey — "Neither
renderer may compute a derived quantity. Not a gap, not an interval width, not a
percentage" — and the only way to honour it is to compute those quantities
upstream and publish them. That is why the published row carries `one_in`
alongside `tail_p`, `interval_width` alongside its two bounds, and `power_rank`
alongside `power`. Every one of those is a division or a sort that would
otherwise happen in a React component, where it could silently disagree with the
static build and with Postgres.

THREE TABLES HERE ARE NOT IN REPORT 03 §5.6, and each is a direct consequence of
that same rule:

    cfb_connectivity   the weeks 1-4 launch product (report 05 §9.1). A drawn
                       graph needs node positions, and computing a layout in the
                       browser is computing. Stored as one JSONB document per
                       (season, week) because it is a rendered diagnostic keyed
                       and versioned by run, never queried by field.
    cfb_divergence     mean |Δrank| per evaluation week — the curve report 05
                       §4.1 wants on the methodology page. It is an aggregate
                       ACROSS weeks, so no single week's page can hold it.
    cfb_artifacts      filename, size and sha256 per run, for the /data page.
                       A page that prints a checksum it computed itself is not
                       publishing a checksum.

TEAM IDENTITY comes from the raw schedule parquet, not from the model. The model
keys on team NAME throughout; the serving schema keys on `team_id` because a
website needs a stable key and a logo. The ids are ESPN's (cfbfastR is built on
ESPN's feed), which is what makes LOGO_TEMPLATE work. `conference` is read from
the same file and is annotated DISPLAY ONLY in §5.6 for a reason: report 02 §3.10
bans it as a feature and `cfbpoll audit-features` enforces that. Reading it here,
in the publication layer, downstream of every fit, is the only place it is safe.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from cfbpoll.config import REPO_ROOT

__all__ = [
    "Bundle",
    "LOGO_TEMPLATE",
    "SERVING_TABLES",
    "build",
    "team_dimension",
]

#: The cfb_* tables this project serves. The first eight are report 03 §5.6
#: verbatim; the last three are the documented extensions above.
SERVING_TABLES: tuple[str, ...] = (
    "cfb_teams",
    "cfb_games",
    "cfb_runs",
    "cfb_model_params",
    "cfb_ratings",
    "cfb_poll_published",
    "cfb_predictions",
    "cfb_backtest_metrics",
    "cfb_connectivity",
    "cfb_divergence",
    "cfb_artifacts",
)

#: ESPN's team-logo CDN. The `team_id`s in the SportsDataverse schedule parquet
#: ARE ESPN ids (cfbfastR wraps ESPN's feed), so this template resolves for every
#: team the archive knows. It is a URL, not a download: nothing in this project
#: redistributes a logo, and the site degrades to a monogram when it 404s or when
#: the reader is offline.
LOGO_TEMPLATE = "https://a.espncdn.com/i/teamlogos/ncaa/500/{team_id}.png"

#: uuid5 namespace for run ids. A run id must be a pure function of what produced
#: the run, or `publish postgres` could not be idempotent: re-running it against
#: the same out/ has to hit the same primary keys rather than accumulate a new
#: run every time. Content-addressed, exactly like the archive.
RUN_NAMESPACE = uuid.UUID("6f1d0b1a-2f2e-5a3c-9d44-cfb0011ca511")

#: `1 in N` is a display transform of `tail_p` (report 05 §3.2). Below this tail
#: the integer stops being meaningful to a reader and starts being an artifact of
#: float underflow, so it is clamped and the clamp is published.
MAX_ONE_IN = 10**15

#: Sections lifted verbatim out of the ADRs for the methodology page's "where
#: this is weak" (report 05 §9.1). Verbatim is the point: a project that
#: paraphrases its own recorded doubts is editing them.
WEAKNESS_SECTIONS: tuple[tuple[str, str], ...] = (
    ("0005-headline-ordering.md", "Where this decision is weak"),
    ("0005-headline-ordering.md", "The price of C, stated plainly"),
    ("0007-tuned-constants.md", "The two uncomfortable results"),
    ("0007-tuned-constants.md", "The calibration diagnosis: diagnosed, and deliberately unfixed"),
    ("0007-tuned-constants.md", "What this does not settle"),
    ("0006-fit-universe.md", "Consequences, including the uncomfortable ones"),
)

#: The artifact index's human column. Report 03 §5.3 fixes the filenames; this
#: fixes what each one is, so /data is a readable page and not a directory listing.
ARTIFACT_NOTES: dict[str, str] = {
    "ratings_live.parquet": "R(N,N) — every team in the fit, as of this week, every layer.",
    "ratings_live.csv": "The same rows as CSV, for readers with no parquet reader.",
    "ratings_hindsight.parquet": "R(N,final) — the same week re-scored with the season's answers.",
    "ratings_hindsight.csv": "The same rows as CSV.",
    "rank_intervals.parquet": "The bootstrap: 90% rank and rating intervals, 1,000 draws.",
    "rank_intervals.csv": "The same rows as CSV.",
    "poll.json": "The published poll: every column, top 25 and all ranked teams.",
    "poll.csv": "The published poll as CSV.",
    "model_params.json": "Every constant this run used. Every week, without exception.",
    "backtest_metrics.json": "Walk-forward scores against every baseline, and the gate.",
    "_run.json": "git sha, config hash, input manifest hash, timestamps. The receipt.",
}


# --------------------------------------------------------------------------- helpers


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _f(value: Any) -> float | None:
    """A float, or None for null/NaN/inf. JSON cannot carry NaN and neither can a
    reader; a missing number must arrive as missing rather than as `NaN`."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _i(value: Any) -> int | None:
    return None if value is None else int(value)


def _one_in(tail_p: float | None) -> int | None:
    """`1 in N`, the natural-frequency rendering of the tail (report 05 §3.2).

    KenPom's own redesign rationale is the argument: rescale a quantity so the
    number is humanly meaningful. A reader can rank `1 in 192` against `1 in 29`
    instantly and cannot rank `0.0052` against `0.0344`.
    """
    if tail_p is None or tail_p <= 0.0:
        return None
    return min(int(round(1.0 / tail_p)), MAX_ONE_IN)


def _rank_map(frame: pl.DataFrame, column: str, teams: set[str]) -> dict[str, int]:
    """Dense 1..n rank of `column`, descending, restricted to `teams`.

    This is the parenthetical in KenPom's value-with-rank pair — `28.10 (3)` —
    and report 05 §3.2 says it is what makes the Gap column readable. It is a
    sort, which means it is a computation, which means it happens here.
    """
    narrow = (
        frame.filter(pl.col("team").is_in(sorted(teams)))
        .select(["team", column])
        .drop_nulls(column)
        .sort([column, "team"], descending=[True, False])
    )
    return {team: i + 1 for i, team in enumerate(narrow["team"].to_list())}


def _extract_section(markdown: str, heading: str) -> str | None:
    """The body of one heading, up to the next heading of the SAME OR HIGHER level.

    Same-or-higher rather than "any heading" matters: `## The two uncomfortable
    results` in ADR 0007 is a wrapper whose entire content is two `###`
    subsections, and a naive stop-at-any-heading rule would publish it as empty —
    which is the worst possible failure for a block whose whole job is to carry
    the project's recorded doubts onto the page.
    """
    opener = re.compile(r"^(#{2,4})\s+" + re.escape(heading) + r"\s*$", re.MULTILINE)
    found = opener.search(markdown)
    if not found:
        return None
    level = len(found.group(1))
    rest = markdown[found.end() :]
    closer = re.compile(r"^#{1," + str(level) + r"}\s", re.MULTILINE)
    end = closer.search(rest)
    body = rest[: end.start()] if end else rest
    return body.strip() or None


# --------------------------------------------------------------------------- teams


def team_dimension(season: int, archive: Path) -> dict[str, dict[str, Any]]:
    """Team name -> the `cfb_teams` row, read from the raw schedule parquet.

    Deliberately NOT read through `ingest.sportsdataverse.canonical_games`: that
    loader's RAW_COLUMNS allow-list exists to keep `home_conference` and friends
    out of every code path that could reach a design matrix (report 01 §5.6). The
    columns are safe HERE and nowhere upstream, so this is the one function that
    opens the file for them, and it is downstream of every fit by construction.
    """
    path = archive / "schedules" / f"cfb_schedules_{season}.parquet"
    frame = pl.read_parquet(
        path,
        columns=[
            "home_id",
            "home_team",
            "home_conference",
            "home_division",
            "away_id",
            "away_team",
            "away_conference",
            "away_division",
        ],
    )
    out: dict[str, dict[str, Any]] = {}
    order = {"fbs": 0, "fcs": 1, "ii": 2, "iii": 3}
    for side in ("home", "away"):
        for tid, name, conf, div in zip(
            frame[f"{side}_id"].to_list(),
            frame[f"{side}_team"].to_list(),
            frame[f"{side}_conference"].to_list(),
            frame[f"{side}_division"].to_list(),
            strict=True,
        ):
            if name is None or tid is None:
                continue
            klass = div or "unknown"
            prior = out.get(name)
            if prior is not None and order.get(klass, 4) >= order.get(prior["classification"], 4):
                continue
            out[name] = {
                "season": int(season),
                "team_id": int(tid),
                "school": name,
                "abbreviation": None,
                "classification": klass,
                # DISPLAY ONLY. Never a model feature (report 02 §3.10).
                "conference": conf,
                "logo_url": LOGO_TEMPLATE.format(team_id=int(tid)),
            }
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------- bundle


@dataclass
class Bundle:
    """One run's serving rows, and the view documents assembled from them.

    `tables` is the relational form that `publish postgres` writes. `views` is the
    document form that `publish fixtures` writes and that the site's typed loader
    returns from EITHER backend — the Postgres backend rebuilds exactly these
    documents with SELECTs. Keeping both in one object is what stops the two
    surfaces from disagreeing about what a week is.
    """

    season: int
    week: int
    season_type: str
    run_id: str
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    views: dict[str, Any] = field(default_factory=dict)


def build(
    out: Path,
    archive: Path | None = None,
    backtest: Path | None = None,
    upcoming_weeks: int = 1,
) -> Bundle:
    """Turn one `out/` directory into its serving rows and view documents.

    `out` is what `cfbpoll rank` wrote: poll.json, model_params.json, _run.json,
    ratings_live.parquet, rank_intervals.parquet. `backtest` is an optional
    backtest_metrics.json — the methodology page's gate and baseline table come
    from it, and a run without one publishes a methodology page that says so
    rather than one that invents numbers.
    """
    from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE

    archive = archive or DEFAULT_ARCHIVE
    poll = _read_json(out / "poll.json")
    params = _read_json(out / "model_params.json")
    run_meta = _read_json(out / "_run.json")

    season = int(poll["season"])
    week = int(poll["through"]["week"])
    season_type = str(poll["through"]["season_type"])

    run_id = str(
        uuid.uuid5(
            RUN_NAMESPACE,
            "|".join(
                [
                    str(season),
                    str(week),
                    season_type,
                    str(run_meta.get("git_sha", "unknown")),
                    str(run_meta.get("config_hash", "")),
                    str(run_meta.get("archive_manifest_sha256", "")),
                    str(params.get("headline_ordering", "")),
                ]
            ),
        )
    )
    published_at = str(run_meta.get("generated_at") or datetime.now(UTC).isoformat())

    teams = team_dimension(season, archive)
    live = pl.read_parquet(out / "ratings_live.parquet")
    ranked = {row["team"] for row in poll["ranking"]}
    power_rank = _rank_map(live, "power", ranked)
    resume_rank = _rank_map(live, "resume", ranked)

    bundle = Bundle(
        season=season, week=week, season_type=season_type, run_id=run_id, tables={}, views={}
    )

    # ---------------------------------------------------------------- dimensions
    bundle.tables["cfb_teams"] = list(teams.values())
    bundle.tables["cfb_games"] = _games_rows(season, archive)

    # ---------------------------------------------------------------- provenance
    run_row = {
        "run_id": run_id,
        "ran_at": published_at,
        "season": season,
        "through_week": week,
        "git_sha": str(run_meta.get("git_sha", "unknown")),
        "config_hash": str(run_meta.get("config_hash", "")),
        "archive_hash": run_meta.get("archive_manifest_sha256"),
        "trigger": "manual",
        # Report 03 §7.2: the site must NEVER render a poll whose run is not
        # published. Every run this command writes is published by definition —
        # `rank` refuses to write one that failed the feature audit — so the
        # status is stated rather than guessed.
        "status": "published",
        "notes": None,
        "published_at": published_at,
    }
    bundle.tables["cfb_runs"] = [run_row]
    numeric, labels = _split_params(params)
    bundle.tables["cfb_model_params"] = [
        {"run_id": run_id, "name": name, "value": value} for name, value in sorted(numeric.items())
    ]

    # ---------------------------------------------------------------- the poll
    poll_rows, published_rows, rating_rows = _poll_rows(
        poll, teams, power_rank, resume_rank, run_id, season, week, published_at
    )
    bundle.tables["cfb_poll_published"] = published_rows
    bundle.tables["cfb_ratings"] = rating_rows
    bundle.tables["cfb_predictions"] = []

    widths = sorted(r["interval_width"] for r in poll_rows if r["interval_width"] is not None)
    median_width = float(_median(widths)) if widths else None
    deltas = [abs(r["rank_delta"]) for r in poll_rows if r["rank_delta"] is not None]

    model_params_doc = _params_doc(
        numeric, labels, run_row, season, week, params, poll.get("provisional", False)
    )

    bundle.views["week"] = {
        "season": season,
        "week": week,
        "season_type": season_type,
        "run": run_row,
        "params": model_params_doc,
        "provisional": bool(poll.get("provisional", False)),
        "provisional_label": poll.get("provisional_label"),
        "league_size": len(poll_rows),
        "median_interval_width": median_width,
        "hindsight_is_live": bool(params.get("hindsight_is_live", False)),
        "poll": poll_rows,
    }

    # ---------------------------------------------------------------- divergence
    bundle.tables["cfb_divergence"] = [
        {
            "run_id": run_id,
            "season": season,
            "eval_week": week,
            "mean_abs_delta": (sum(deltas) / len(deltas)) if deltas else None,
            "max_abs_delta": max(deltas) if deltas else None,
            "n_teams": len(poll_rows),
        }
    ]

    # ---------------------------------------------------------------- connectivity
    connectivity = _connectivity_view(
        season, week, season_type, archive, params, poll, poll_rows, median_width, upcoming_weeks
    )
    bundle.views["connectivity"] = connectivity
    bundle.tables["cfb_connectivity"] = [
        {
            "run_id": run_id,
            "season": season,
            "week": week,
            "payload": connectivity,
        }
    ]

    # ---------------------------------------------------------------- methodology
    metrics, gate = _backtest_rows(backtest, run_id)
    bundle.tables["cfb_backtest_metrics"] = metrics
    bundle.views["methodology"] = {
        "season": season,
        "week": week,
        "params": model_params_doc,
        "run": run_row,
        "metrics": [
            {k: v for k, v in row.items() if k != "run_id"} for row in metrics
        ],
        "gate": gate,
        "weaknesses": _weaknesses(),
        "divergence": [],  # filled by the fixture writer across weeks; see fixtures.py
    }

    # ---------------------------------------------------------------- artifacts
    artifacts = _artifact_rows(out, run_id)
    bundle.tables["cfb_artifacts"] = artifacts
    bundle.views["data"] = {
        "season": season,
        "week": week,
        "run": run_row,
        "artifacts": [{k: v for k, v in row.items() if k != "run_id"} for row in artifacts],
        "duckdb": _duckdb_one_liner(season, week),
        "licenses": _licenses(),
    }
    return bundle


def _median(values: list[float]) -> float:
    n = len(values)
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2.0


def _split_params(params: dict[str, Any]) -> tuple[dict[str, float], dict[str, str]]:
    """`cfb_model_params` takes doubles; the layer names and the ordering are
    strings and cannot live in that table. Both halves are published."""
    numeric: dict[str, float] = {}
    labels: dict[str, str] = {}
    for name, value in params.items():
        if isinstance(value, bool):
            labels[name] = "true" if value else "false"
        elif isinstance(value, (int, float)):
            got = _f(value)
            if got is not None:
                numeric[name] = got
        elif isinstance(value, str):
            labels[name] = value
    return numeric, labels


def _fmt(value: float | None, places: int = 3) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def _params_doc(
    numeric: dict[str, float],
    labels: dict[str, str],
    run: dict[str, Any],
    season: int,
    week: int,
    params: dict[str, Any],
    provisional: bool,
) -> dict[str, Any]:
    """The permanent constants footer of report 05 §2.3, PRE-RENDERED.

    Two lines, and the report is explicit that this block is a brand asset: no
    other rankings site in the sport carries one, and its presence on every page
    is the fastest way to communicate what kind of instrument this is. It is
    rendered here rather than in the browser for the same reason as everything
    else — the static build, the share card and the Next.js app must print the
    same characters.
    """
    q_ref = _f(params.get("q_ref"))
    q_team = params.get("q_ref_team")
    published = str(run["published_at"])[:19].replace("T", " ")
    line1 = (
        f"run {run['run_id'][:8]} · published {published} UTC · "
        f"code {str(run['git_sha'])[:7]} · config {str(run['config_hash'])[:8]}…"
    )
    line2 = " · ".join(
        [
            f"q_ref {_fmt(q_ref, 2)}" + (f" ({q_team})" if q_team else ""),
            f"β_w {_fmt(_f(numeric.get('beta_w')), 0)}",
            f"C {_fmt(_f(numeric.get('C')), 0)}",
            f"h {_fmt(_f(numeric.get('h_points')), 3)}",
            f"σ {_fmt(_f(numeric.get('sigma')), 3)}",
            f"λ₁ {_fmt(_f(numeric.get('lambda_l1')), 0)}",
            f"λ₂ {_fmt(_f(numeric.get('lambda_l2')), 1)}",
            f"k {_fmt(_f(numeric.get('k_points_per_unit')), 2)}",
            f"w₁ {_fmt(_f(numeric.get('w1_efficiency')), 4)}",
            f"w₂ {_fmt(_f(numeric.get('w2_results')), 4)}",
        ]
    )
    reproduce = f"uv run cfbpoll rank --season {season} --through-week {week} --out out/"
    del provisional
    return {
        "numeric": numeric,
        "labels": labels,
        "footer_lines": [line1, line2],
        "reproduce": reproduce,
    }


def _poll_rows(
    poll: dict[str, Any],
    teams: dict[str, dict[str, Any]],
    power_rank: dict[str, int],
    resume_rank: dict[str, int],
    run_id: str,
    season: int,
    week: int,
    published_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The published row, three ways: the view, `cfb_poll_published`, `cfb_ratings`."""
    view: list[dict[str, Any]] = []
    published: list[dict[str, Any]] = []
    ratings: list[dict[str, Any]] = []

    for row in poll["ranking"]:
        team = row["team"]
        dim = teams.get(team)
        team_id = int(dim["team_id"]) if dim else -abs(hash(team)) % 10**8
        lo, hi = _i(row.get("rank_lo")), _i(row.get("rank_hi"))
        wins, losses = int(row["wins"]), int(row["losses"])
        tail = _f(row.get("tail_p"))

        view.append(
            {
                "rank": int(row["rank"]),
                "team_id": team_id,
                "team": team,
                "abbreviation": dim["abbreviation"] if dim else None,
                "conference": dim["conference"] if dim else None,
                "logo_url": dim["logo_url"] if dim else None,
                "wins": wins,
                "losses": losses,
                "record": f"{wins}-{losses}",
                "odds_key": _f(row.get("odds_key")),
                "tail_p": tail,
                "one_in": _one_in(tail),
                "mid_p": _f(row.get("mid_p")),
                "expected_wins": _f(row.get("expected_wins")),
                "surprise": _f(row.get("surprise")),
                "resume": _f(row.get("resume")),
                "resume_margin": _f(row.get("resume_margin")),
                "resume_rank": resume_rank.get(team),
                "saturated": int(row.get("saturated") or 0),
                "power": _f(row.get("power")),
                "power_se": _f(row.get("power_se")),
                "power_rank": power_rank.get(team),
                "gap": _f(row.get("gap")),
                "rank_lo90": lo,
                "rank_hi90": hi,
                "rank_median": _i(row.get("rank_median")),
                "interval_width": (hi - lo) if (lo is not None and hi is not None) else None,
                "hindsight_rank": _i(row.get("rank_hindsight")),
                "rank_delta": _i(row.get("rank_delta")),
                "q_ref": _f(row.get("q_ref")),
                "q_ref_team": row.get("q_ref_team"),
            }
        )
        published.append(
            {
                "season": season,
                "week": week,
                "rank": int(row["rank"]),
                "team_id": team_id,
                "resume_rating": _f(row.get("resume")),
                "power_rating": _f(row.get("power")),
                "rank_lo90": lo,
                "rank_hi90": hi,
                "prev_rank": None,
                "wins": wins,
                "losses": losses,
                "run_id": run_id,
                "published_at": published_at,
            }
        )
        for layer, rating, rank, rlo, rhi in (
            ("C_schedule_odds", _f(row.get("odds_key")), int(row["rank"]), lo, hi),
            ("L3_power", _f(row.get("power")), power_rank.get(team), None, None),
            ("L4_resume", _f(row.get("resume")), resume_rank.get(team), None, None),
        ):
            if rating is None:
                continue
            ratings.append(
                {
                    "run_id": run_id,
                    "season": season,
                    "eval_week": week,
                    "data_window": week,  # K = N: the live surface
                    "team_id": team_id,
                    "layer": layer,
                    "rating": rating,
                    "rank": rank,
                    "rating_lo90": None,
                    "rating_hi90": None,
                    "rank_lo90": rlo,
                    "rank_hi90": rhi,
                }
            )
        # The hindsight surface, K = 99, is the other half of the retro product
        # (report 02 §3.6) and is what the Δ column reads.
        hind = _f(row.get("odds_key_hindsight"))
        if hind is not None:
            ratings.append(
                {
                    "run_id": run_id,
                    "season": season,
                    "eval_week": week,
                    "data_window": 99,
                    "team_id": team_id,
                    "layer": "C_schedule_odds",
                    "rating": hind,
                    "rank": _i(row.get("rank_hindsight")),
                    "rating_lo90": None,
                    "rating_hi90": None,
                    "rank_lo90": None,
                    "rank_hi90": None,
                }
            )
    return view, published, ratings


def _games_rows(season: int, archive: Path) -> list[dict[str, Any]]:
    from cfbpoll.ingest.sportsdataverse import canonical_games

    teams = team_dimension(season, archive)
    frame = canonical_games([season], archive)
    ingested = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    for row in frame.iter_rows(named=True):
        home = teams.get(row["home_team"])
        away = teams.get(row["away_team"])
        if home is None or away is None:
            continue
        start = row["start_date"]
        rows.append(
            {
                "game_id": int(row["game_id"]),
                "season": int(row["season"]),
                "week": int(row["week"]),
                "season_type": row["season_type"],
                "game_type": row["game_type"],
                "start_date": start.isoformat() if start is not None else None,
                "completed": bool(row["completed"]),
                "neutral_site": bool(row["neutral_site"]),
                "conference_game": row["conference_game"],
                "home_team_id": int(home["team_id"]),
                "away_team_id": int(away["team_id"]),
                "home_points": _i(row["home_points"]),
                "away_points": _i(row["away_points"]),
                "home_class": row["home_class"],
                "away_class": row["away_class"],
                "source": "sportsdataverse",
                "ingested_at": ingested,
            }
        )
    return rows


# --------------------------------------------------------------------- connectivity


def _connectivity_view(
    season: int,
    week: int,
    season_type: str,
    archive: Path,
    params: dict[str, Any],
    poll: dict[str, Any],
    poll_rows: list[dict[str, Any]],
    median_width: float | None,
    upcoming_weeks: int,
) -> dict[str, Any]:
    """The weeks 1-4 launch product, computed in full so the site draws it blind."""
    from cfbpoll.config import load_config
    from cfbpoll.ingest import windows
    from cfbpoll.ingest.sportsdataverse import canonical_games, load_games
    from cfbpoll.model import connectivity as conn

    cfg = load_config(REPO_ROOT / "configs" / "default.toml")
    headline_start = int(cfg["publication"]["headline_start_week"])

    games = load_games([season], archive, universe="model")
    window = windows.games_through(games, season=season, week=week, season_type=season_type)
    graph = conn.build_graph(window)
    comp = conn.components(graph)
    cut = conn.bridges(graph)
    positions = conn.layout(graph, comp)

    sizes: dict[int, int] = {}
    for cid in comp:
        sizes[cid] = sizes.get(cid, 0) + 1
    component_sizes = [sizes[c] for c in sorted(sizes)]
    largest_share = (component_sizes[0] / graph.n) if graph.n else 0.0

    degrees = graph.degrees()
    teams_dim = team_dimension(season, archive)
    nodes = [
        {
            "team_id": int(teams_dim[t]["team_id"]) if t in teams_dim else -i - 1,
            "team": t,
            "classification": graph.classification.get(t, "unknown"),
            "component": comp[i],
            "x": positions.x[i],
            "y": positions.y[i],
            "degree": degrees[i],
        }
        for i, t in enumerate(graph.teams)
    ]
    edges = [
        {"source": a, "target": b, "component": comp[a], "bridge": ei in cut}
        for ei, (a, b) in enumerate(graph.edges)
    ]

    # The bridges worth naming: the ones holding a non-trivial cluster on. A cut
    # edge that strands one team is arithmetic; a cut edge that strands forty is
    # a headline.
    bridge_games: list[dict[str, Any]] = []
    for ei in sorted(cut):
        near, far = conn.component_split(graph, ei)
        smaller = min(near, far)
        if smaller < 2:
            continue
        a, b = graph.edges[ei]
        bridge_games.append(
            {
                "game_id": graph.game_ids[ei],
                "week": graph.weeks[ei],
                "home": graph.teams[a],
                "away": graph.teams[b],
                "splits": [near, far],
                "note": (
                    f"{graph.teams[a]}–{graph.teams[b]} is the only game linking "
                    f"{smaller} teams to the other {max(near, far)}. Undo that one result "
                    "and the graph splits in two."
                ),
            }
        )
    bridge_games.sort(key=lambda g: (-min(g["splits"]), g["game_id"]))

    # What would have to be true: next week's slate, restricted to games that
    # would weld two currently-separate components.
    played_ids = set(window["game_id"].to_list())
    everything = canonical_games([season], archive)
    horizon = week + max(1, upcoming_weeks)
    upcoming = everything.filter(
        (pl.col("season_type") == "regular")
        & (pl.col("week") > week)
        & (pl.col("week") <= horizon)
        & ~pl.col("game_id").is_in(sorted(played_ids))
    )
    connectors = conn.would_connect(graph, upcoming, comp)[:12]
    for game in connectors:
        smaller = min(game["home_component_size"], game["away_component_size"])
        bigger = max(game["home_component_size"], game["away_component_size"])
        game["note"] = (
            f"{game['away']} at {game['home']}, week {game['week']}: the first game on the "
            f"schedule that would connect a group of {smaller} to the group of {bigger}. "
            "It is worth more to this poll than its TV slot suggests."
        )

    top_group = [r["team"] for r in poll_rows[:10]]
    distance = conn.distance_from(graph, top_group)
    far_from_top = sum(1 for d in distance.values() if d < 0 or d > 2)

    league = len(poll_rows)
    spanning = sum(
        1
        for r in poll_rows
        if r["interval_width"] is not None and league and r["interval_width"] >= 0.9 * (league - 1)
    )

    diagnostics = [
        {
            "label": "teams in the fit",
            "display": f"{graph.n}",
            "value": float(graph.n),
            "note": "Every team with at least one game against an FBS or FCS opponent.",
        },
        {
            "label": "games played",
            "display": f"{len(graph.edges)}",
            "value": float(len(graph.edges)),
            "note": None,
        },
        {
            "label": "connected components",
            "display": f"{len(component_sizes)}",
            "value": float(len(component_sizes)),
            "note": (
                "Separate islands of the schedule graph. Two teams in different components "
                "have no chain of results connecting them at all, at any length."
            ),
        },
        {
            "label": "largest component",
            "display": f"{component_sizes[0] if component_sizes else 0} teams "
            f"({largest_share * 100:.1f}%)",
            "value": largest_share,
            "note": "Share of the field that is mutually comparable through played games.",
        },
        {
            "label": "bridge games",
            "display": f"{len(bridge_games)}",
            "value": float(len(bridge_games)),
            "note": (
                "Single games whose removal would split the graph in two, each holding at "
                "least two teams on. Every rating on the far side rests on that one result."
            ),
        },
        {
            "label": "fitted λ₂ (results core)",
            "display": _fmt(_f(params.get("lambda_l2")), 3),
            "value": _f(params.get("lambda_l2")) or 0.0,
            "note": (
                "Chosen by cross-validation every week. λ is a ratio of variances — a "
                "statement about how much we do not know, containing no team-specific "
                "information whatsoever. It is large when the data is thin and falls as "
                "the season accumulates. Regularization is not a reputation prior."
            ),
        },
        {
            "label": "median 90% rank-interval width",
            "display": "—" if median_width is None else f"{median_width:.0f} places",
            "value": median_width or 0.0,
            "note": (
                f"Out of {league} ranked teams, from 1,000 replays of this exact schedule. "
                "This is the number that says whether the season has settled."
            ),
        },
        {
            "label": "teams whose interval spans the league",
            "display": f"{spanning}",
            "value": float(spanning),
            "note": "90% interval at least 90% as wide as the whole field.",
        },
        {
            "label": "teams no closer than three hops to the top ten",
            "display": f"{far_from_top}",
            "value": float(far_from_top),
            "note": (
                "They have not played a top-ten team and share no opponent with one. "
                "Their position relative to the top of the poll is an extrapolation."
            ),
        },
    ]

    provisional = bool(poll.get("provisional", False))
    counter = (
        f"The poll opens in Week {headline_start}. That date was published before the "
        "season and does not move. This is week "
        f"{week}, and what follows is a description of what is not yet knowable."
        if provisional
        else f"The poll opened in Week {headline_start}. This is week {week}; the schedule "
        "graph below is what the ranking is standing on."
    )

    sentences: list[str] = []
    if len(component_sizes) > 1:
        sentences.append(
            f"The field is in {len(component_sizes)} separate pieces. "
            f"{component_sizes[0]} teams are mutually comparable through played games; "
            f"the other {graph.n - component_sizes[0]} are not comparable to them at all yet, "
            "and no amount of arithmetic changes that."
        )
    else:
        sentences.append(
            "The graph is welded: every team is connected to every other through some chain "
            "of results. That is the condition under which a ranking is a measurement rather "
            "than an extrapolation, and it is why the opening week is week "
            f"{headline_start} and not week 1."
        )
    for game in connectors[:3]:
        sentences.append(game["note"])
    if bridge_games:
        sentences.append(bridge_games[0]["note"])

    return {
        "season": season,
        "week": week,
        "headline_start_week": headline_start,
        "counter": counter,
        "provisional_label": poll.get("provisional_label"),
        "diagnostics": diagnostics,
        "nodes": nodes,
        "edges": edges,
        "component_sizes": component_sizes,
        "bridge_games": bridge_games[:12],
        "would_connect": connectors,
        "what_would_have_to_be_true": sentences,
    }


# --------------------------------------------------------------------- methodology


def _backtest_rows(
    backtest: Path | None, run_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`cfb_backtest_metrics` rows and the publication gate, from the harness JSON."""
    if backtest is None or not backtest.exists():
        return [], []
    payload = _read_json(backtest)
    protocol = payload.get("protocol", {})
    seasons = protocol.get("seasons") or []
    split = f"tune_{min(seasons)}_{max(seasons)}" if seasons else "tune"

    rows: list[dict[str, Any]] = []
    wanted = ("n_games", "su_accuracy", "mae", "rmse", "brier", "log_loss")
    for system, block in sorted(payload.get("systems", {}).items()):
        segment = (block.get("segments_from_headline_week") or {}).get("fbs_vs_fbs") or {}
        for metric in wanted:
            value = _f(segment.get(metric))
            if value is not None:
                rows.append(
                    {
                        "run_id": run_id,
                        "split": split,
                        "system": system,
                        "metric": metric,
                        "value": value,
                    }
                )
        violations = _f(block.get("retrodictive_violation_rate"))
        if violations is not None:
            rows.append(
                {
                    "run_id": run_id,
                    "split": split,
                    "system": system,
                    "metric": "violations",
                    "value": violations,
                }
            )

    ours = (payload.get("systems", {}).get("schedule_odds") or {}).get("gate") or {}
    thresholds = ours.get("thresholds") or {}
    observed = ours.get("observed") or {}
    criteria = [
        ("su_accuracy", "Straight-up accuracy at or above the floor", "su_accuracy_min"),
        ("mae", "Mean absolute error at or below the ceiling", "mae_max"),
        ("rmse", "Root mean squared error at or below the ceiling", "rmse_max"),
        (
            "calibration",
            "Worst decile calibration deviation within tolerance",
            "calibration_max_decile_deviation_pp",
        ),
        ("violations_vs_baselines", "Retrodictive violations at or below every baseline", None),
        ("brier_beats_all_baselines", "Brier score beats every baseline", None),
        ("retro_vs_live_monotone", "Retro-vs-live divergence declines monotonically", None),
    ]
    gate: list[dict[str, Any]] = []
    for name, statement, threshold_key in criteria:
        verdict = ours.get(name)
        status = "not yet decided" if verdict is None else ("pass" if verdict else "FAIL")
        detail_bits: list[str] = []
        if threshold_key and thresholds.get(threshold_key) is not None:
            detail_bits.append(f"threshold {thresholds[threshold_key]}")
        obs = observed.get(
            {
                "su_accuracy": "su_accuracy",
                "mae": "mae",
                "rmse": "rmse",
                "calibration": "max_calibration_deviation_pp",
                "violations_vs_baselines": "retrodictive_violation_rate",
            }.get(name, "")
        )
        got = _f(obs)
        if got is not None:
            detail_bits.append(f"observed {got:.4g}")
        gate.append(
            {
                "name": name,
                "statement": statement,
                "status": status,
                "detail": "; ".join(detail_bits) or None,
            }
        )
    if ours:
        gate.append(
            {
                "name": "passed",
                "statement": "Every decided criterion passes",
                "status": "pass" if ours.get("passed") else "FAIL",
                "detail": (
                    "Undecided criteria are reported as undecided, never as passes: "
                    + ", ".join(ours.get("undecided") or ["none"])
                ),
            }
        )
    return rows, gate


def _weaknesses() -> list[dict[str, str]]:
    """The "where this is weak" blocks, lifted verbatim out of the ADRs (report 05 §9.1)."""
    out: list[dict[str, str]] = []
    for filename, heading in WEAKNESS_SECTIONS:
        path = REPO_ROOT / "docs" / "adr" / filename
        if not path.exists():
            continue
        body = _extract_section(path.read_text(encoding="utf-8"), heading)
        if body:
            out.append({"heading": heading, "body": body, "source": f"docs/adr/{filename}"})
    return out


# ---------------------------------------------------------------------------- data


def _artifact_rows(out: Path, run_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(out.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        rows.append(
            {
                "run_id": run_id,
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "description": ARTIFACT_NOTES.get(path.name, ""),
            }
        )
    return rows


def _duckdb_one_liner(season: int, week: int) -> str:
    """One line, copy-pasteable, no account, no clone (report 05 §9.1)."""
    tag = f"poll-{season}-w{week:02d}"
    url = f"https://github.com/vyhlidal/cfb-poll/releases/download/{tag}/ratings_live.parquet"
    return (
        f"duckdb -c \"SELECT team, rank, odds_key, power, gap FROM '{url}' "
        'WHERE rank IS NOT NULL ORDER BY rank LIMIT 25"'
    )


def _licenses() -> list[dict[str, str]]:
    return [
        {
            "name": "Our ratings and rankings — CC BY 4.0",
            "body": (
                "Everything this project computes and publishes is released under CC BY 4.0. "
                "Share and adapt it, including commercially, with credit and a link. "
                "Attribution: Ratings from cfb-poll (https://github.com/vyhlidal/cfb-poll), "
                "CC BY 4.0. We chose attribution over public domain for one reason: a ranking "
                "that travels without its methodology is exactly the thing this project exists "
                "to replace."
            ),
        },
        {
            "name": "Upstream inputs — SportsDataverse, MIT",
            "body": (
                "The input archive is republished from SportsDataverse under the MIT license, "
                "and that single fact is load-bearing for the whole project: it means a "
                "stranger can reproduce every ranking we have ever published with no API key, "
                "no account, and no permission from anyone."
            ),
        },
        {
            "name": "Code — MIT",
            "body": "The pipeline is MIT licensed. See LICENSE in the repository.",
        },
        {
            "name": "Team logos",
            "body": (
                "Logos are hot-linked from ESPN's CDN and are the property of their respective "
                "institutions. Nothing in this project redistributes them, and no logo is "
                "stored in the archive or in any published artifact."
            ),
        },
    ]
