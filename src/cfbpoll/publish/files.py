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
    "rank_intervals.parquet",
    "model_params.json",
    "predictions.parquet",
    "poll.json",
    "poll.csv",
    "backtest_metrics.json",
    "_run.json",
)

#: Written by `cfbpoll rank` today. The rest of OUTPUT_FILENAMES belongs to
#: layers that do not exist yet, and writing an empty file for them would be a
#: fabricated capability.
L2_OUTPUTS: tuple[str, ...] = (
    "ratings_live.parquet",
    "ratings_live.csv",
    "poll.json",
    "poll.csv",
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
    ratings: pl.DataFrame,
    poll: pl.DataFrame,
    params: dict[str, Any],
    run: dict[str, Any],
    config_path: Path | None = None,
) -> list[Path]:
    """Write the L2-only artifact set. Returns the paths written, sorted."""
    out.mkdir(parents=True, exist_ok=True)

    ratings = ratings.sort(["rating", "team"], descending=[True, False])
    poll = poll.sort("rank")

    ratings.write_parquet(out / "ratings_live.parquet")
    ratings.write_csv(out / "ratings_live.csv")
    poll.write_csv(out / "poll.csv")

    _json_dump(
        out / "poll.json",
        {
            **{k: v for k, v in params.items() if k in ("season", "through", "layer", "version")},
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
            "files": sorted(L2_OUTPUTS),
        },
    )
    return sorted((out / name) for name in L2_OUTPUTS)


def canonicalize(src: Path, dest: Path) -> Path:
    """Emit the sorted, %.10g-formatted CSV that golden fixtures hash.

    Parquet embeds a `created_by` writer-version string, so byte-identical data
    can produce different file bytes. Hash the canonicalized data, not the file
    (report 03 §9.3 item 4). `_run.json` is deliberately NOT part of this: it
    carries a wall-clock timestamp by design.
    """
    ratings = pl.read_parquet(src / "ratings_live.parquet").sort(["team"])
    lines = ["team,rating"]
    lines += [f"{t},{r:.10g}" for t, r in zip(ratings["team"], ratings["rating"], strict=True)]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def write_run(out: Path, artifacts: dict[str, Any]) -> None:
    """Write the full out/ artifact set, once every layer exists."""
    raise NotImplementedError("publish.files.write_run - scaffold; see report 03 §5.3")
