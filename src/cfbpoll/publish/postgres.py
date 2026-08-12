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

    A tension worth naming rather than papering over: §5.6 gives that table the
    primary key (season, week, rank), which cannot physically hold two runs' rows
    for one week. This loader therefore writes it ON CONFLICT DO NOTHING - the
    FIRST publication of a (season, week, rank) wins and is never overwritten,
    which preserves the integrity property the schema is actually protecting. A
    genuine correction needs a schema change (the run_id in the key), and that
    is a decision for an ADR, not for a loader to make silently.

IDEMPOTENCE, concretely. Every other table upserts on its natural key, and
`run_id` is a uuid5 over (season, week, git sha, config hash, archive hash,
ordering) - see serving.RUN_NAMESPACE. So re-running this command against the
same out/ hits the same primary keys and converges; re-running it after a code
change writes a genuinely new run and keeps the old one. The whole database can
be dropped and rebuilt from files at any time, which is what makes it a cache
rather than a source of truth.

Skips cleanly when DATABASE_URL is unset - a fork has no database and must still
produce a ranking.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cfbpoll.publish.serving import SERVING_TABLES, Bundle, build

__all__ = ["DDL", "SERVING_TABLES", "UPSERTS", "load", "statements", "tables_present"]

#: The schema of report 03 §5.6, verbatim, plus the three documented extensions
#: from `serving.py` (cfb_connectivity, cfb_divergence, cfb_artifacts). Every
#: statement is IF NOT EXISTS so the loader can create its own world on a fresh
#: database and be a no-op on an established one.
DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS cfb_teams (
      season          smallint    NOT NULL,
      team_id         integer     NOT NULL,
      school          text        NOT NULL,
      abbreviation    text,
      classification  text        NOT NULL,
      conference      text,
      -- §5.6 declared logo_url and no file column: the design already
      -- anticipated storing a REFERENCE rather than an asset (report 06 §8.1).
      -- The integer is the real record; the four URLs are built from it and
      -- stored so the site never derives a string either.
      espn_team_id    integer,
      logo_url        text,
      logo_url_2x     text,
      logo_url_dark   text,
      logo_url_dark_2x text,
      PRIMARY KEY (season, team_id)
    )
    """,
    "ALTER TABLE cfb_teams ADD COLUMN IF NOT EXISTS espn_team_id integer",
    "ALTER TABLE cfb_teams ADD COLUMN IF NOT EXISTS logo_url_2x text",
    "ALTER TABLE cfb_teams ADD COLUMN IF NOT EXISTS logo_url_dark text",
    "ALTER TABLE cfb_teams ADD COLUMN IF NOT EXISTS logo_url_dark_2x text",
    """
    CREATE TABLE IF NOT EXISTS cfb_games (
      game_id         bigint      PRIMARY KEY,
      season          smallint    NOT NULL,
      week            smallint    NOT NULL,
      season_type     text        NOT NULL,
      game_type       text        NOT NULL,
      start_date      timestamptz NOT NULL,
      completed       boolean     NOT NULL,
      neutral_site    boolean     NOT NULL,
      conference_game boolean,
      home_team_id    integer     NOT NULL,
      away_team_id    integer     NOT NULL,
      home_points     smallint,
      away_points     smallint,
      home_class      text        NOT NULL,
      away_class      text        NOT NULL,
      source          text        NOT NULL,
      ingested_at     timestamptz NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS cfb_games_season_week ON cfb_games (season, week)",
    """
    CREATE TABLE IF NOT EXISTS cfb_runs (
      run_id        uuid        PRIMARY KEY,
      ran_at        timestamptz NOT NULL,
      season        smallint    NOT NULL,
      through_week  smallint    NOT NULL,
      git_sha       text        NOT NULL,
      config_hash   text        NOT NULL,
      archive_hash  text,
      trigger       text        NOT NULL,
      status        text        NOT NULL,
      notes         text,
      published_at  timestamptz
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cfb_model_params (
      run_id  uuid    NOT NULL REFERENCES cfb_runs(run_id),
      name    text    NOT NULL,
      value   double precision NOT NULL,
      PRIMARY KEY (run_id, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cfb_ratings (
      run_id       uuid     NOT NULL REFERENCES cfb_runs(run_id),
      season       smallint NOT NULL,
      eval_week    smallint NOT NULL,
      data_window  smallint NOT NULL,
      team_id      integer  NOT NULL,
      layer        text     NOT NULL,
      rating       double precision NOT NULL,
      rank         integer,
      rating_lo90  double precision,
      rating_hi90  double precision,
      rank_lo90    integer,
      rank_hi90    integer,
      PRIMARY KEY (run_id, season, eval_week, data_window, team_id, layer)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS cfb_ratings_lookup
      ON cfb_ratings (season, eval_week, data_window, layer, rank)
    """,
    """
    CREATE TABLE IF NOT EXISTS cfb_poll_published (
      season        smallint    NOT NULL,
      week          smallint    NOT NULL,
      rank          integer     NOT NULL,
      team_id       integer     NOT NULL,
      resume_rating double precision NOT NULL,
      power_rating  double precision NOT NULL,
      rank_lo90     integer,
      rank_hi90     integer,
      prev_rank     integer,
      wins          smallint,
      losses        smallint,
      run_id        uuid        NOT NULL REFERENCES cfb_runs(run_id),
      published_at  timestamptz NOT NULL,
      PRIMARY KEY (season, week, rank)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cfb_predictions (
      run_id        uuid   NOT NULL REFERENCES cfb_runs(run_id),
      game_id       bigint NOT NULL,
      pred_margin   double precision NOT NULL,
      win_prob_home double precision NOT NULL,
      PRIMARY KEY (run_id, game_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cfb_backtest_metrics (
      run_id uuid NOT NULL REFERENCES cfb_runs(run_id),
      split  text NOT NULL,
      system text NOT NULL,
      metric text NOT NULL,
      value  double precision NOT NULL,
      PRIMARY KEY (run_id, split, system, metric)
    )
    """,
    # ------------------------------------------------- extensions to §5.6
    # THE SERVING SURFACE. The tables above are the analytical surface and are
    # written exactly as §5.6 specifies; this is what the website reads. See the
    # argument in publish/serving.py: §5.6 predates ADR 0005, the published row
    # is now twenty-plus fields (report 05 §3.1), and several of the things a
    # page prints are properties of the WEEK rather than of any team. Storing the
    # rendered document makes parity between the two backends a diff of two JSON
    # objects instead of a hope that two renderers agreed.
    """
    CREATE TABLE IF NOT EXISTS cfb_views (
      season  smallint NOT NULL,
      week    smallint NOT NULL,
      kind    text     NOT NULL,
      run_id  uuid     NOT NULL REFERENCES cfb_runs(run_id),
      payload jsonb    NOT NULL,
      PRIMARY KEY (season, week, kind)
    )
    """,
    # The week strip: every week of a season, played or not. An aggregate across
    # weeks, so no week's row can hold it and the loader merges it in place.
    """
    CREATE TABLE IF NOT EXISTS cfb_season_index (
      season              smallint NOT NULL PRIMARY KEY,
      headline_start_week smallint NOT NULL,
      weeks               jsonb    NOT NULL,
      updated_at          timestamptz NOT NULL
    )
    """,
    # Mean |Δrank| per evaluation week: an aggregate ACROSS weeks, so no single
    # week's page can hold it, and the site may not compute it.
    """
    CREATE TABLE IF NOT EXISTS cfb_divergence (
      season         smallint NOT NULL,
      eval_week      smallint NOT NULL,
      run_id         uuid     NOT NULL REFERENCES cfb_runs(run_id),
      mean_abs_delta double precision,
      max_abs_delta  double precision,
      n_teams        integer  NOT NULL,
      PRIMARY KEY (season, eval_week)
    )
    """,
    # A page that prints a checksum it computed itself is not publishing a
    # checksum.
    """
    CREATE TABLE IF NOT EXISTS cfb_artifacts (
      run_id      uuid NOT NULL REFERENCES cfb_runs(run_id),
      name        text NOT NULL,
      bytes       bigint NOT NULL,
      sha256      text NOT NULL,
      description text,
      PRIMARY KEY (run_id, name)
    )
    """,
)

#: (conflict target, updatable columns) per table. An empty column tuple means
#: DO NOTHING, which is how the append-only publication record is protected.
_CONFLICT: dict[str, tuple[str, tuple[str, ...]]] = {
    "cfb_teams": (
        "(season, team_id)",
        (
            "school",
            "abbreviation",
            "classification",
            "conference",
            "espn_team_id",
            "logo_url",
            "logo_url_2x",
            "logo_url_dark",
            "logo_url_dark_2x",
        ),
    ),
    "cfb_games": (
        "(game_id)",
        (
            "season", "week", "season_type", "game_type", "start_date", "completed",
            "neutral_site", "conference_game", "home_team_id", "away_team_id",
            "home_points", "away_points", "home_class", "away_class", "source", "ingested_at",
        ),
    ),
    "cfb_runs": (
        "(run_id)",
        ("ran_at", "season", "through_week", "git_sha", "config_hash", "archive_hash",
         "trigger", "status", "notes", "published_at"),
    ),
    "cfb_model_params": ("(run_id, name)", ("value",)),
    "cfb_ratings": (
        "(run_id, season, eval_week, data_window, team_id, layer)",
        ("rating", "rank", "rating_lo90", "rating_hi90", "rank_lo90", "rank_hi90"),
    ),
    # APPEND ONLY. The first publication of a (season, week, rank) wins forever.
    "cfb_poll_published": ("(season, week, rank)", ()),
    "cfb_predictions": ("(run_id, game_id)", ("pred_margin", "win_prob_home")),
    "cfb_backtest_metrics": ("(run_id, split, system, metric)", ("value",)),
    "cfb_views": ("(season, week, kind)", ("run_id", "payload")),
    "cfb_season_index": ("(season)", ("headline_start_week", "weeks", "updated_at")),
    "cfb_divergence": (
        "(season, eval_week)",
        ("run_id", "mean_abs_delta", "max_abs_delta", "n_teams"),
    ),
    "cfb_artifacts": ("(run_id, name)", ("bytes", "sha256", "description")),
}

#: JSONB columns need an explicit dump; psycopg will not guess.
_JSON_COLUMNS: dict[str, tuple[str, ...]] = {
    "cfb_views": ("payload",),
    "cfb_season_index": ("weeks",),
}

#: The order tables must be written in, so foreign keys are always satisfied.
UPSERTS: tuple[str, ...] = SERVING_TABLES


def _upsert_sql(table: str, columns: list[str]) -> str:
    target, updatable = _CONFLICT[table]
    names = ", ".join(columns)
    holes = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table} ({names}) VALUES ({holes}) ON CONFLICT {target} "
    settable = [c for c in updatable if c in columns]
    if not settable:
        return sql + "DO NOTHING"
    assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in settable)
    return sql + f"DO UPDATE SET {assignments}"


def statements(bundle: Bundle) -> list[tuple[str, list[list[Any]]]]:
    """(sql, parameter rows) per table, in foreign-key-safe order.

    Split out from `load` so the whole plan is testable with no database: the
    tests assert the ordering, the conflict clauses and the append-only rule
    without needing Postgres, which is the only way this stays covered in a CI
    job that has no secrets (report 03 §7.3).
    """
    plan: list[tuple[str, list[list[Any]]]] = []
    for table in UPSERTS:
        rows = bundle.tables.get(table) or []
        if not rows:
            continue
        columns = sorted(rows[0])
        json_columns = _JSON_COLUMNS.get(table, ())
        params = [
            [json.dumps(row[c], sort_keys=True) if c in json_columns else row[c] for c in columns]
            for row in rows
        ]
        plan.append((_upsert_sql(table, columns), params))
    return plan


def load(
    out: Path,
    database_url: str | None = None,
    archive: Path | None = None,
    backtest: Path | None = None,
    create: bool = True,
) -> dict[str, int]:
    """Load out/ into the cfb_* serving tables. No-op when there is no database.

    Returns rows written per table (empty when skipped), so the caller can say
    what happened rather than printing a shrug. `database_url` defaults to the
    DATABASE_URL environment variable; POSTGRES_URL is accepted as a fallback
    because that is the name the sandbox platform uses for the same Neon
    database, and having the two halves of one system disagree about the name of
    their shared connection string is a bug waiting to happen.
    """
    url = database_url or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not url:
        return {}

    import psycopg

    bundle = build(out, archive=archive, backtest=backtest)
    plan = statements(bundle)

    written: dict[str, int] = {}
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            if create:
                for ddl in DDL:
                    cur.execute(ddl)  # type: ignore[arg-type]
            for table, (sql, params) in zip(tables_present(bundle), plan, strict=True):
                cur.executemany(sql, params)  # type: ignore[arg-type]
                written[table] = len(params)
            written["cfb_season_index"] = _merge_season_index(cur, bundle, archive)
        conn.commit()
    return written


def _merge_season_index(cur: Any, bundle: Bundle, archive: Path | None) -> int:
    """Fold this week into the season's week list, in place, inside the same
    transaction.

    The week strip is an aggregate across weeks, so it cannot be derived from the
    one run being published. Read-modify-write against the stored list keeps the
    command idempotent and order-free — publish week 12 then week 3 and the strip
    is the same either way — and it uses `serving.merge_season_index`, the same
    function the fixture writer uses, so the two backends cannot disagree about
    which weeks exist.
    """
    from cfbpoll.publish import serving

    cur.execute("SELECT weeks FROM cfb_season_index WHERE season = %s", (bundle.season,))
    row = cur.fetchone()
    existing = list(row[0]) if row and row[0] else []
    start = serving.headline_start_week()
    weeks = serving.merge_season_index(
        existing,
        bundle.week_stub(),
        serving.scheduled_weeks(bundle.season, archive),
        start,
    )
    cur.execute(
        "INSERT INTO cfb_season_index (season, headline_start_week, weeks, updated_at) "
        "VALUES (%s, %s, %s, now()) ON CONFLICT (season) DO UPDATE SET "
        "headline_start_week = EXCLUDED.headline_start_week, weeks = EXCLUDED.weeks, "
        "updated_at = EXCLUDED.updated_at",
        (bundle.season, start, json.dumps(weeks, sort_keys=True)),
    )
    return len(weeks)


def tables_present(bundle: Bundle) -> list[str]:
    """The tables `statements` will actually emit, in the same order."""
    return [t for t in UPSERTS if bundle.tables.get(t)]
