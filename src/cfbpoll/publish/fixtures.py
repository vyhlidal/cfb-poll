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

RECIPES ARE AN ADDITIVE EXTENSION OF EXACTLY THAT TREE (ADR 0011, and
docs/fixture-contract-recipes.md is the contract the site is owed):

    <dir>/<season>/recipes/<slug>/week-NN.json         one week under one lens
    <dir>/<season>/recipes/<slug>/methodology-NN.json  that lens's constants
    <dir>/<season>/recipes/<slug>/divergence.json      that lens's retro curve

NOTHING ABOVE MOVES AND `schema_version` DOES NOT CHANGE. `<season>/week-NN.json`
is still the published poll, still the house recipe, and a site that has never
heard of a recipe keeps reading exactly the paths it read before and keeps
getting the same numbers. That is not politeness: the site is a separate
repository on a separate deploy cadence, and a data contract that can only be
extended by breaking it is a contract that gets extended by nobody. The version
of the extension itself travels as `recipes_contract_version`, so a site can ask
whether recipes are present without asking whether the poll changed shape.

CONNECTIVITY AND /data ARE HOUSE-ONLY, and the reason is the whole point of the
feature. The connectivity report is a function of the SCHEDULE GRAPH, which is
evidence, and evidence is identical under every recipe by construction — writing
it three times would publish the same bytes three times and invite a reader to
wonder which one is right. The /data page indexes the artifacts of a PUBLISHED
run, and only the house recipe is published.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cfbpoll.publish import serving
from cfbpoll.publish.serving import Bundle, build

__all__ = [
    "RECIPE_DOCUMENTS",
    "RECIPES_CONTRACT_VERSION",
    "SCHEMA_VERSION",
    "export",
    "export_all",
    "rebuild_index",
    "run_directories",
    "season_dir",
    "week_documents",
]

#: Bumped when a document's shape changes. The site checks it on load and fails
#: loudly rather than rendering nulls, because a contract that drifts silently is
#: not a contract (report 05 §7.2).
#:
#: RECIPES DID NOT BUMP IT, and that is a deliberate reading of what this number
#: is for. Every path, every document and every field the site reads today is
#: unchanged; recipes add optional fields and an optional subtree. Bumping would
#: make the loader throw on a set that is strictly more capable than the one it
#: was written against, which is the opposite of failing loudly about a real
#: problem. The extension carries its own version below.
SCHEMA_VERSION = 1

#: The recipe extension's own version, published on `index.json`. A site reads it
#: to decide whether to render the selector at all, and it moves independently of
#: `SCHEMA_VERSION` because the two answer different questions: "has the poll
#: changed shape" and "which recipe contract is this set written to".
RECIPES_CONTRACT_VERSION = 1

#: Written per week for the published poll. The key is the filename stem; the
#: value is the view name in `serving.Bundle.views`.
DOCUMENTS: dict[str, str] = {
    "week": "week",
    "connectivity": "connectivity",
    "methodology": "methodology",
    "data": "data",
}

#: Written per week for an ALTERNATE LENS. Two documents rather than four: the
#: connectivity report is a function of the evidence and the evidence is identical
#: under every recipe, and the /data page indexes a published run of which there
#: is exactly one. See the module docstring.
RECIPE_DOCUMENTS: dict[str, str] = {
    "week": "week",
    "methodology": "methodology",
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
    """The per-week documents for this bundle, keyed by filename stem.

    Four for the published poll, two for an alternate lens. Which one a bundle is
    comes off the RUN (`serving.Bundle.recipe`, read from model_params.json), not
    off a flag, so a directory cannot be filed under the wrong lens by a typo.
    """
    documents = DOCUMENTS if bundle.is_house else RECIPE_DOCUMENTS
    return {stem: bundle.views[view] for stem, view in documents.items()}


def season_dir(dest: Path, season: int, recipe_slug: str = "house") -> Path:
    """Where one run's documents land. The house poll keeps the path it has.

    The published poll is `<dest>/<season>/`, exactly where it has always been, so
    a site that knows nothing about recipes is unaffected. An alternate lens lands
    under `<dest>/<season>/recipes/<slug>/`, which is a new subtree rather than a
    new shape.
    """
    base = Path(dest) / str(season)
    return base if recipe_slug == "house" else base / "recipes" / recipe_slug


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
        # THE GATE IS NOT ATTACHED TO AN ALTERNATE LENS. `[gate]` is written
        # against the published poll and `cfbpoll backtest` scores orderings under
        # the default config, so handing those metrics to a lens would put the
        # HOUSE poll's verdict on a page describing a different value system. The
        # recipe is read off the run's own model_params.json before the build, so
        # the decision is made from what the run IS rather than from a flag.
        if resolved.exists() and not _is_house_run(run):
            resolved = None  # type: ignore[assignment]
        bundle = build(run, archive=archive, backtest=resolved if resolved else None)
        target = season_dir(dest, bundle.season, bundle.recipe_slug)
        for stem, payload in week_documents(bundle).items():
            path = target / f"{stem}-{bundle.week:02d}.json"
            _dump(path, payload)
            written.append(path)
    written.extend(rebuild_index(dest, archive=archive))
    return sorted(written)


def _is_house_run(run: Path) -> bool:
    """Is this run directory the published poll? Read off its own artifact.

    A run written before `configs/recipes/` existed carries no recipe block and is
    the house poll by definition, which is what the default says.
    """
    try:
        params = json.loads((run / "model_params.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - checked by check_run_directory
        return True
    return bool((params.get("recipe") or {}).get("is_house", True))


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
    target = season_dir(dest, bundle.season, bundle.recipe_slug)
    written: list[Path] = []
    for stem, payload in week_documents(bundle).items():
        path = target / f"{stem}-{bundle.week:02d}.json"
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

    A SEASON WITH NO POLL BUT A PROJECTION IS INDEXED, WITH EVERY WEEK UNPLAYED,
    and the history of this branch is worth keeping because it is a coupling
    somebody will otherwise re-break.

    The Projection (ADR 0010) writes `<season>/projection.json` into this tree for
    a season that has not kicked off, so `<dest>/2026/` exists, holds no poll, and
    is named with digits like every other season directory. Indexing it originally
    put a season with zero played weeks at the top of `seasons[]`; the site took
    the current season to be `max(seasons)` and its current week to be the last
    PLAYED one, resolved 2026, found no week, and returned a 404 on the front
    door. The fix at the time was to skip such a directory entirely.

    That cost the 2026 week strip, which is supposed to render from day one:
    report 05 §2.2 says "weeks not yet played are dimmed and unclickable, not
    hidden. Seeing the empty right-hand side of the strip is part of the season
    narrative", and a season indexed nowhere has no strip to dim. So the guard is
    now on the SITE side, where it belongs — `frontDoorBoards` picks the newest
    season that has a played week rather than the newest season — and this
    function emits the season with `weeks[]` built from the schedule alone, every
    entry `played: false`, and `recipes: []`.

    THE TWO CHANGES ARE A PAIR. A fixture set written by this version and served
    by a site whose front door still resolves `max(seasons)` will 404 exactly as
    it did before. If that regression reappears, this is the half to look at
    second; the front door is the half to look at first.
    """
    from cfbpoll import recipes as recipes_mod
    from cfbpoll.publish import serving

    headline_start = serving.headline_start_week()
    written: list[Path] = []
    seasons: list[dict[str, Any]] = []
    for season_root in sorted(p for p in dest.iterdir() if p.is_dir() and p.name.isdigit()):
        season = int(season_root.name)
        published = sorted(season_root.glob("week-*.json"))
        if not published and not (season_root / "projection.json").exists():
            # Neither a season of this poll nor a season this project has said
            # anything about. A bare digit-named directory is not an entry.
            continue
        weeks: list[dict[str, Any]] = []
        scheduled = serving.scheduled_weeks(season, archive)

        if not published:
            # A PROJECTION-ONLY SEASON: no poll, but a schedule, so the strip can
            # be drawn entirely out of unplayed weeks. See the docstring for the
            # site-side half of this pair.
            seasons.append(
                {
                    "season": season,
                    "headline_start_week": headline_start,
                    "weeks": [
                        serving.unplayed_week(season, week, headline_start)
                        for week in scheduled
                    ],
                    "recipes": [],
                }
            )
            continue

        for path in published:
            payload = json.loads(path.read_text(encoding="utf-8"))
            weeks = serving.merge_season_index(
                weeks,
                {
                    "season": season,
                    "week": int(payload["week"]),
                    "season_type": payload.get("season_type", "regular"),
                    "provisional": bool(payload.get("provisional", False)),
                    "played": True,
                    "published_at": (payload.get("run") or {}).get("published_at"),
                    "n_ranked": len(payload.get("poll") or []),
                },
                scheduled,
                headline_start,
            )

        written.append(_write_divergence(season_root))

        # EACH ALTERNATE LENS GETS ITS OWN DIVERGENCE CURVE. Retro-vs-live
        # divergence is a property of an ORDERING - it is how far the retroactive
        # re-ranking moves the published one - so the house curve does not
        # describe a recipe that ranks on a different column. Under `just-win` it
        # is structurally pinned for every unbeaten team (ADR 0005 §A), which is
        # a finding the page should be able to draw rather than a caveat it has
        # to be told.
        present: list[dict[str, Any]] = []
        lens_root = season_root / "recipes"
        lenses = sorted(p for p in lens_root.iterdir() if p.is_dir()) if lens_root.is_dir() else []
        for lens in lenses:
            week_files = sorted(lens.glob("week-*.json"))
            if not week_files:
                continue
            written.append(_write_divergence(lens))
            present.append(
                {
                    "slug": lens.name,
                    "weeks": [int(json.loads(p.read_text("utf-8"))["week"]) for p in week_files],
                }
            )

        seasons.append(
            {
                "season": season,
                "headline_start_week": headline_start,
                "weeks": weeks,
                # Which lenses this season actually carries, and for which weeks.
                # The house poll is not listed: it is the season itself, it is
                # every week in `weeks`, and listing it beside the alternates
                # would blur the one distinction the page has to keep sharp.
                "recipes": present,
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
            # THE RECIPE ROSTER, so a selector can be built from ONE document.
            # Name, one-liner, manifesto, honest costs and the constants each one
            # changes all travel here; a page never has to open a week file to
            # find out what it is offering, and it never has to hold a copy of the
            # prose that would then drift from the config it describes.
            "recipes_contract_version": RECIPES_CONTRACT_VERSION,
            "recipes": recipes_mod.roster(),
        },
    )
    written.append(index)
    return written


def _write_divergence(directory: Path) -> Path:
    """`divergence.json` for one tree of `week-*.json` documents.

    Mean and maximum |Δrank| between the live and hindsight surfaces, per
    evaluation week. An aggregate ACROSS weeks, so it cannot live in any one of
    them, and it is computed once per tree rather than once per recipe-aware
    branch so the published poll and an alternate lens cannot end up with two
    slightly different definitions of the same curve.
    """
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("week-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        deltas = [
            abs(r["rank_delta"])
            for r in (payload.get("poll") or [])
            if r.get("rank_delta") is not None
        ]
        if deltas:
            rows.append(
                {
                    "week": int(payload["week"]),
                    "mean_abs_delta": sum(deltas) / len(deltas),
                    "max_abs_delta": max(deltas),
                }
            )
    rows.sort(key=lambda row: row["week"])
    path = directory / "divergence.json"
    _dump(path, rows)
    return path
