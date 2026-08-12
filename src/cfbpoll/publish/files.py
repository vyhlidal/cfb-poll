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
Reproducibility does not require language monoculture, it requires open,
plain-format data - and it costs nothing.

Determinism rules that live here (report 03 §9.3): sort by an explicit key before
writing; never let dict or groupby iteration order reach a file.

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def write_run(out: Path, artifacts: dict[str, Any]) -> None:
    """Write the full out/ artifact set, sorted and deterministically formatted."""
    raise NotImplementedError("publish.files.write_run - scaffold; see report 03 §5.3")


def canonicalize(out: Path, dest: Path) -> None:
    """Emit the sorted, %.10g-formatted CSV that golden fixtures hash.

    Parquet embeds a `created_by` writer-version string, so byte-identical data
    can produce different file bytes. Hash the canonicalized data, not the file
    (report 03 §9.3 item 4).
    """
    raise NotImplementedError("publish.files.canonicalize - scaffold; see report 03 §9.3")
