"""Write out/ - the source of truth.

Filenames are fixed by report 03 §5.3 and must not drift; the site, the release
step and the Postgres loader all key off them:

    ratings_live.parquet       R(N,N) for every layer
    ratings_hindsight.parquet  R(N,final)
    ratings_grid.parquet       the full N x K retroactive grid
    rank_intervals.parquet     bootstrap 90% rank + rating intervals
    model_params.json          lambda, C, beta_w, h, k, w1, w2, sigma - EVERY
                               constant, EVERY week
    predictions.parquet        next slate
    poll.json / poll.csv       the headline top 25 + full ranking, human-readable
    backtest_metrics.json
    _run.json                  git_sha, config_hash, archive_sha, input manifest,
                               timestamps

_run.json is what makes any published poll traceable to the exact code, config
and inputs that produced it. It is cheap, and it is the difference between "open
source" and "auditable".

EVERY OUTPUT IS WRITTEN AS BOTH PARQUET AND CSV where shape allows. That is an
explicit design commitment (report 03 §3): an R contributor can then do their
entire analysis against our artifacts without touching our pipeline.

Determinism rules that live here (report 03 §9.3): sort by an explicit key before
writing; never let dict or groupby iteration order reach a file; keep wall-clock
timestamps out of everything except `_run.json`, which is excluded from the
golden hash for exactly that reason.

STATUS: the L2-only subset is implemented - ratings_live, poll.json/csv,
model_params.json, _run.json. The hindsight grid, the bootstrap intervals and
the next-slate predictions arrive with L3/L4 and the bootstrap.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from cfbpoll.config import DEFAULT_CONFIG_PATH, config_hash

__all__ = ["OUTPUT_FILENAMES", "canonicalize", "write_rank_outputs"]

OUTPUT_FILENAMES: tuple[str, ...] = (
    "ratings_live.parquet",
    "ratings_hindsight.parquet",
    "ratings_grid.parquet",
    "retro_movers.csv",
    "rank_intervals.parquet",
    "model_params.json",
    "predictions.parquet",
    "poll.json",
    "poll.csv",
    "backtest_metrics.json",
    "_run.json",
)

#: Written by `cfbpoll rank`: one evaluation week N, both surfaces, and the
#: bootstrap's rank intervals. `predictions.parquet` (the next slate) is the only
#: name in OUTPUT_FILENAMES this command does not write, and writing an empty
#: file for it would be a fabricated capability.
RANK_OUTPUTS: tuple[str, ...] = (
    "ratings_live.parquet",
    "ratings_live.csv",
    "ratings_hindsight.parquet",
    "ratings_hindsight.csv",
    "rank_intervals.parquet",
    "rank_intervals.csv",
    "poll.json",
    "poll.csv",
    "model_params.json",
    "_run.json",
)

#: Written by `cfbpoll grid`: every evaluation week N of a season, against every
#: data window K >= N. `ratings_live` and `ratings_hindsight` carry the SAME
#: schema `rank` writes, with more rows - the diagonal and the last column of the
#: same triangle - so running `grid` after `rank` into one directory is strictly
#: more complete rather than a conflict.
GRID_OUTPUTS: tuple[str, ...] = (
    "ratings_grid.parquet",
    "ratings_grid.csv",
    "ratings_live.parquet",
    "ratings_live.csv",
    "ratings_hindsight.parquet",
    "ratings_hindsight.csv",
    "retro_movers.csv",
    "model_params.json",
    "_run.json",
)


def _json_dump(path: Path, payload: Any) -> None:
    """Stable JSON: sorted keys, fixed separators, trailing newline."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - a tarball checkout has no git
        return "unknown"


def write_rank_outputs(
    out: Path,
    live: pl.DataFrame,
    hindsight: pl.DataFrame,
    poll: pl.DataFrame,
    params: dict[str, Any],
    run: dict[str, Any],
    config_path: Path | None = None,
    intervals: pl.DataFrame | None = None,
) -> list[Path]:
    """Write one evaluation week's artifact set. Returns the paths written, sorted.

    `live` and `hindsight` are R(N, N) and R(N, final) for the same N, in the
    schema `model/retro.py` defines, already sorted by its ordering rule - so
    `ratings_live.parquet` here is one slice of what `cfbpoll grid` writes for a
    whole season, not a different shape. `poll` is the joined headline table.
    """
    out.mkdir(parents=True, exist_ok=True)
    poll = poll.sort("rank")

    live.write_parquet(out / "ratings_live.parquet")
    live.write_csv(out / "ratings_live.csv")
    hindsight.write_parquet(out / "ratings_hindsight.parquet")
    hindsight.write_csv(out / "ratings_hindsight.csv")
    poll.write_csv(out / "poll.csv")

    # The bootstrap's own artifact, sorted by team so the bytes are a pure
    # function of the computation (report 03 §9.3). A run with no draws writes
    # the schema with no rows rather than no file, because "we did not bootstrap
    # this week" is a fact a downstream reader needs to be able to see.
    intervals = (
        intervals if intervals is not None else pl.DataFrame({"team": []}, schema={"team": pl.Utf8})
    )
    intervals = intervals.sort("team")
    intervals.write_parquet(out / "rank_intervals.parquet")
    intervals.write_csv(out / "rank_intervals.csv")

    _json_dump(
        out / "poll.json",
        {
            **{
                k: v
                for k, v in params.items()
                if k
                in (
                    "season",
                    "through",
                    "layer",
                    "version",
                    "resume_layer",
                    "resume_version",
                    "headline_ordering",
                    "headline_layer",
                    "headline_decided",
                    "companion_layer",
                    "power_source",
                    "power_version",
                    "hindsight_variant",
                    "hindsight_data_bucket",
                    "hindsight_is_live",
                    "saturation_tiebreak",
                    # The headline ordering's one free constant, with the team it
                    # was read off, on the poll itself rather than in a footnote.
                    "q_ref",
                    "q_ref_method",
                    "q_ref_team",
                    "ranking_key",
                )
            },
            "provisional": params.get("provisional"),
            "provisional_label": params.get("provisional_label"),
            "top25": poll.head(25).to_dicts(),
            "ranking": poll.to_dicts(),
        },
    )
    _json_dump(out / "model_params.json", params)
    _json_dump(
        out / "_run.json",
        {
            **run,
            "git_sha": _git_sha(),
            "config_hash": config_hash(config_path or DEFAULT_CONFIG_PATH),
            "config_path": str(config_path or DEFAULT_CONFIG_PATH),
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "files": sorted(RANK_OUTPUTS),
        },
    )
    return sorted((out / name) for name in RANK_OUTPUTS)


def write_grid_outputs(
    out: Path,
    grid: pl.DataFrame,
    live: pl.DataFrame,
    hindsight: pl.DataFrame,
    movers: pl.DataFrame,
    params: dict[str, Any],
    run: dict[str, Any],
    config_path: Path | None = None,
) -> list[Path]:
    """Write the retroactive artifact set: the N x K triangle and its two surfaces.

    Every frame arrives already sorted by `model/retro.py`'s single ordering
    rule; nothing here re-sorts, so the file bytes are a pure function of the
    computation (report 03 §9.3).
    """
    out.mkdir(parents=True, exist_ok=True)

    grid.write_parquet(out / "ratings_grid.parquet")
    grid.write_csv(out / "ratings_grid.csv")
    live.write_parquet(out / "ratings_live.parquet")
    live.write_csv(out / "ratings_live.csv")
    hindsight.write_parquet(out / "ratings_hindsight.parquet")
    hindsight.write_csv(out / "ratings_hindsight.csv")
    movers.write_csv(out / "retro_movers.csv")

    _json_dump(out / "model_params.json", params)
    _json_dump(
        out / "_run.json",
        {
            **run,
            "git_sha": _git_sha(),
            "config_hash": config_hash(config_path or DEFAULT_CONFIG_PATH),
            "config_path": str(config_path or DEFAULT_CONFIG_PATH),
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "files": sorted(GRID_OUTPUTS),
        },
    )
    return sorted((out / name) for name in GRID_OUTPUTS)


def _g(value: Any) -> str:
    """%.10g for a number, empty for a null. The canonical float format."""
    return "" if value is None else format(float(value), ".10g")


def canonicalize(src: Path, dest: Path) -> Path:
    """Emit the sorted, %.10g-formatted CSV that golden fixtures hash.

    Parquet embeds a `created_by` writer-version string, so byte-identical data
    can produce different file bytes. Hash the canonicalized data, not the file
    (report 03 §9.3 item 4). `_run.json` is deliberately NOT part of this: it
    carries a wall-clock timestamp by design.
    """
    ratings = pl.read_parquet(src / "ratings_live.parquet").sort(["eval_order", "team"])
    lines = ["eval_label,team,odds_key,tail_p,resume,resume_margin,power,power_se"]
    lines += [
        f"{row['eval_label']},{row['team']},{row['odds_key']:.10g},{row['tail_p']:.10g},"
        f"{row['resume']:.10g},{row['resume_margin']:.10g},{row['power']:.10g},"
        f"{_g(row.get('power_se'))}"
        for row in ratings.iter_rows(named=True)
    ]

    # THE INTERVALS ARE PART OF THE REPLAY, not an extra. They come out of a
    # seeded RNG, which is exactly the kind of thing that silently stops being
    # reproducible, so the golden hash covers them (report 03 §9.3 item 2).
    interval_path = src / "rank_intervals.parquet"
    if interval_path.exists():
        table = pl.read_parquet(interval_path)
        if table.height:
            columns = [c for c in sorted(table.columns) if c != "team"]
            lines.append("")
            lines.append("team," + ",".join(columns))
            lines += [
                row["team"] + "," + ",".join(_g(row[c]) for c in columns)
                for row in table.sort("team").iter_rows(named=True)
            ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def write_run(out: Path, artifacts: dict[str, Any]) -> None:
    """Write the full out/ artifact set, once every layer exists."""
    raise NotImplementedError("publish.files.write_run - scaffold; see report 03 §5.3")
