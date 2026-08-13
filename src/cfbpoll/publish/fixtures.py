"""Export the serving rows as JSON — the fork's data source, and the site's dev data.

Report 03 §6.3 recommends doing BOTH publication paths, because they serve
different audiences: the shared Neon database is the product surface, and the
published artifacts are the fork. This module is the second one made concrete.
A forker with no Neon account, no Vercel account and no domain still gets a
website with every real number in it, and the sandbox app in local development
renders live 2023 data with `POSTGRES_URL` unset.

The contract is `publish/serving.py`. Both backends emit the SAME documents;
this one writes them to disk and the Postgres loader writes them to tables, and
the site's typed loader cannot tell which it is talking to. That symmetry is the
whole design: one interface, two backends, and no page that works against one
and quietly breaks against the other.

IDEMPOTENT AND INCREMENTAL. `publish fixtures` for week 7 rewrites week 7's four
documents and rebuilds the two season-level files (`index.json`, which the week
strip reads, and `divergence.json`, which is an aggregate ACROSS weeks and so
cannot live in any one of them) from whatever is on disk. Running it fifteen
times in a row, or twice for the same week, converges to the same directory.

Layout, which the loader in the sandbox app depends on:

    <dir>/index.json                    every season, every week, the strip
    <dir>/<season>/week-NN.json         the poll table and its provenance
    <dir>/<season>/connectivity-NN.json the weeks 1-4 launch product
    <dir>/<season>/methodology-NN.json  constants, gate, "where this is weak"
    <dir>/<season>/data-NN.json         artifact index, sha256s, licences
    <dir>/<season>/divergence.json      mean |Δrank| by evaluation week
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cfbpoll.publish import serving
from cfbpoll.publish.serving import Bundle, build

__all__ = [
    "SCHEMA_VERSION",
    "export",
    "export_all",
    "rebuild_index",
    "run_directories",
    "week_documents",
]

#: Bumped when a document's shape changes. The site checks it on load and fails
#: loudly rather than rendering nulls, because a contract that drifts silently is
#: not a contract (report 05 §7.2).
SCHEMA_VERSION = 1

#: Written per week. The key is the filename stem; the value is the view name in
#: `serving.Bundle.views`.
DOCUMENTS: dict[str, str] = {
    "week": "week",
    "connectivity": "connectivity",
    "methodology": "methodology",
    "data": "data",
}


def _dump(path: Path, payload: Any) -> None:
    """Stable JSON: sorted keys, fixed separators, trailing newline.

    Same rule as `publish/files.py` and for the same reason (report 03 §9.3):
    the bytes must be a pure function of the computation, so a fixture set can be
    diffed and a change in the data is visible as a change in the file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def week_documents(bundle: Bundle) -> dict[str, Any]:
    """The four per-week documents, keyed by filename stem."""
    return {stem: bundle.views[view] for stem, view in DOCUMENTS.items()}


def run_directories(source: Path) -> list[Path]:
    """The run directories under `source`: either it is one, or it holds several.

    WHY THIS EXISTS, because it is the defect that let the site's fixture tree go
    stale while a session reported it regenerated.

    `export` publishes ONE week. The site reads a whole season, so regenerating
    the tree it serves meant looping a shell over fifteen run directories by
    hand. A regeneration procedure that lives in somebody's terminal history is
    not a procedure: it cannot be reviewed, it cannot be re-run by the next
    person, and there is no way to notice it was skipped. So `publish fixtures`
    accepts a directory of runs and does the loop itself, and the command that
    produces the published tree is one line that can be written down.

    A run directory is identified by `poll.json`, which `cfbpoll rank` always
    writes. Sorted by (season, week) so the index is rebuilt in calendar order
    and a partial failure leaves the earlier weeks correct.
    """
    source = Path(source)
    if (source / "poll.json").exists():
        return [source]
    found = sorted(p for p in source.iterdir() if p.is_dir() and (p / "poll.json").exists())
    if not found:
        raise serving.StaleRunError(
            f"{source} is neither a run directory (no poll.json) nor a directory of "
            f"them. `publish fixtures --from` wants what `cfbpoll rank --out` wrote."
        )

    def key(path: Path) -> tuple[int, int, str]:
        poll = json.loads((path / "poll.json").read_text(encoding="utf-8"))
        through = poll.get("through") or {}
        return (
            int(poll.get("season", 0)),
            int(through.get("week", 0)),
            str(through.get("season_type", "regular")),
        )

    return sorted(found, key=key)


def export_all(
    source: Path,
    dest: Path,
    archive: Path | None = None,
    backtest: Path | None = None,
) -> list[Path]:
    """Publish every run under `source`, then rebuild the index once.

    The index is rebuilt once at the end rather than after every week: it is a
    pure function of what is on disk (report 03 §9.3), so rebuilding it fifteen
    times produces the same bytes fifteen times and only the last one counts.
    """
    written: list[Path] = []
    runs = run_directories(source)
    for run in runs:
        resolved = backtest if backtest is not None else (run / "backtest_metrics.json")
        bundle = build(run, archive=archive, backtest=resolved if resolved.exists() else None)
        season_dir = dest / str(bundle.season)
        for stem, payload in week_documents(bundle).items():
            path = season_dir / f"{stem}-{bundle.week:02d}.json"
            _dump(path, payload)
            written.append(path)
    written.extend(rebuild_index(dest, archive=archive))
    return sorted(written)


def export(
    out: Path,
    dest: Path,
    archive: Path | None = None,
    backtest: Path | None = None,
) -> list[Path]:
    """Write one run's fixtures into `dest`. Returns the paths written, sorted.

    `out` is the directory `cfbpoll rank` produced. Everything else is derived by
    `serving.build`, so this function does no arithmetic of its own — which is
    the same rule the website obeys, applied one layer earlier.
    """
    bundle = build(out, archive=archive, backtest=backtest)
    season_dir = dest / str(bundle.season)
    written: list[Path] = []
    for stem, payload in week_documents(bundle).items():
        path = season_dir / f"{stem}-{bundle.week:02d}.json"
        _dump(path, payload)
        written.append(path)
    written.extend(rebuild_index(dest, archive=archive))
    return sorted(written)


def rebuild_index(dest: Path, archive: Path | None = None) -> list[Path]:
    """Rebuild `index.json` and every season's `divergence.json` from disk.

    Reading the fixtures back rather than accumulating state in memory is what
    makes the command safe to run one week at a time, in any order, as many times
    as you like. It is also what lets a fork regenerate the index after hand-
    editing a week out of the set.

    THE WEEK STRIP SHOWS UNPLAYED WEEKS (report 05 §2.2): "Weeks not yet played
    are dimmed and unclickable, not hidden. Seeing the empty right-hand side of
    the strip is part of the season narrative." So the index lists every regular
    week the schedule knows about and marks `played` only where a run exists —
    through `serving.merge_season_index`, the same function the Postgres loader
    calls, so the two backends cannot disagree about which weeks exist.
    """
    from cfbpoll.publish import serving

    headline_start = serving.headline_start_week()
    written: list[Path] = []
    seasons: list[dict[str, Any]] = []
    for season_dir in sorted(p for p in dest.iterdir() if p.is_dir() and p.name.isdigit()):
        season = int(season_dir.name)
        weeks: list[dict[str, Any]] = []
        divergence: list[dict[str, Any]] = []
        scheduled = serving.scheduled_weeks(season, archive)

        for path in sorted(season_dir.glob("week-*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            week = int(payload["week"])
            poll = payload.get("poll") or []
            deltas = [abs(r["rank_delta"]) for r in poll if r.get("rank_delta") is not None]
            weeks = serving.merge_season_index(
                weeks,
                {
                    "season": season,
                    "week": week,
                    "season_type": payload.get("season_type", "regular"),
                    "provisional": bool(payload.get("provisional", False)),
                    "played": True,
                    "published_at": (payload.get("run") or {}).get("published_at"),
                    "n_ranked": len(poll),
                },
                scheduled,
                headline_start,
            )
            if deltas:
                divergence.append(
                    {
                        "week": week,
                        "mean_abs_delta": sum(deltas) / len(deltas),
                        "max_abs_delta": max(deltas),
                    }
                )

        divergence.sort(key=lambda row: row["week"])
        path = season_dir / "divergence.json"
        _dump(path, divergence)
        written.append(path)

        seasons.append(
            {
                "season": season,
                "headline_start_week": headline_start,
                "weeks": weeks,
            }
        )

    # `generated_at` is the newest publication in the set, NOT the wall clock.
    # Report 03 §9.3: keep wall-clock timestamps out of everything except
    # _run.json. A wall clock here would make every republish a diff even when
    # not one number changed, which destroys the one property that makes a
    # fixture set reviewable. It is also the more useful value — the site's
    # freshness indicator wants "when was the newest poll published", not "when
    # did someone last run the exporter".
    published = [
        w["published_at"]
        for season in seasons
        for w in season["weeks"]
        if w.get("published_at")
    ]
    index = dest / "index.json"
    _dump(
        index,
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": max(published) if published else None,
            "generator": "cfbpoll publish fixtures",
            "seasons": seasons,
        },
    )
    written.append(index)
    return written
