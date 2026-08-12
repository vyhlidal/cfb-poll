"""Load the SERVING SUBSET into Neon Postgres. Idempotent, and droppable.

Specified by report 03 §5.4 and §5.6. Tables are prefixed cfb_ per the sandbox
convention.

THE RULE, and it is a hard one: Postgres holds only what a page actually renders.
Neon's free tier is 0.5 GB per project. The full retroactive grid is ~1.78M rows
and would land at 250-400 MB with indexes - most of the free tier, for data the
website renders perhaps 1% of. So:

    parquet only   raw plays; the full N x K grid; every bootstrap draw
    Postgres       live R(N,N) and hindsight R(N,final) for L3 and L4 only;
                   the published weekly poll; games, teams, predictions, model
                   params, run metadata

That is well under 150 MB with indexes and leaves the shared sandbox database
usable by other apps. Nothing is hidden by this: the full grid stays downloadable
as a release asset and queryable in place with DuckDB. It is just not in the
wrong engine.

cfb_poll_published IS APPEND ONLY. Never UPDATE, never DELETE. A poll that can be
quietly rewritten is not a published record. Corrections get a new row set at a
new run_id with the old one retained.

Skips cleanly when DATABASE_URL is unset - a fork has no database and must still
produce a ranking.

STATUS: SCAFFOLD. The DDL in report 03 §5.6 is the specification; no migration
has been written yet.
"""

from __future__ import annotations

from pathlib import Path

SERVING_TABLES: tuple[str, ...] = (
    "cfb_teams",
    "cfb_games",
    "cfb_runs",
    "cfb_model_params",
    "cfb_ratings",
    "cfb_poll_published",
    "cfb_predictions",
    "cfb_backtest_metrics",
)


def load(out: Path, database_url: str | None) -> None:
    """Load out/ into the cfb_* serving tables. No-op when database_url is None."""
    raise NotImplementedError("publish.postgres.load - scaffold; see report 03 §5.4, §5.6")
