#!/usr/bin/env python
"""Check a published lever grid against docs/fixture-contract-levers.md.

WHAT THIS IS FOR. The lever grid's entire claim is "the site does not compute, so
every board a reader can reach came out of the same pipeline that made the
published poll". That is a claim about seventy-two files, and a claim a reader
cannot check is a slogan. This script opens the manifest, opens every file the
manifest names, and fails on anything that would make the claim false.

    uv run python scripts/check_lever_grid.py --data <dir> --season 2025

IT FITS NOTHING AND READS NO ARCHIVE, so it needs no BLAS pin and runs in about a
second. It reads published JSON only, which is deliberate: a checker that recomputed
the boards would be a second implementation of the model, which is the exact thing
the grid exists to avoid.

THE TWO CHECKS THAT MATTER MOST are the last two. Eleven cells sit at constants
this project has already published under another name - the poll itself, both
alternate recipes, all eight playground variants - and this script asserts their
rows are the same rows. If the grid ever stops being the pipeline, that is where it
shows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from cfbpoll.publish import lever_grid as grid  # noqa: E402
from cfbpoll.publish import variants  # noqa: E402

#: What a row must round to before two documents are compared. It is
#: `variants.FLOAT_DECIMALS`, imported rather than repeated, because the published
#: documents were written at that precision and comparing at any other would either
#: pass on noise or fail on it. Report 03 §9.3: this pipeline reproduces to about
#: 1e-12 on Apple Silicon rather than bit for bit.
DECIMALS = variants.FLOAT_DECIMALS


class Failure(Exception):
    """One broken promise, with enough detail to fix it."""


def _load(path: Path) -> Any:
    if not path.exists():
        raise Failure(f"missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise Failure(f"unreadable JSON: {path}: {error}") from error


def _rows_by_team(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(row["team_id"]): row for row in rows}


def _compare_rows(
    label: str,
    ours: list[dict[str, Any]],
    theirs: list[dict[str, Any]],
    fields: tuple[str, ...] = variants.ROW_FIELDS,
) -> list[str]:
    """Every field of every team the two documents share. Returns problems.

    OVER THE ROWS THEY SHARE, not over both lists. A published week document
    carries the whole board and a thin document carries the top 40, and under a
    different ordering a team in one document's top 40 need not be in the other's.
    Comparing the intersection is the honest comparison; comparing the lists would
    fail on a difference that is a property of truncation rather than of the model.
    """
    mine, yours = _rows_by_team(ours), _rows_by_team(theirs)
    common = sorted(set(mine) & set(yours))
    if not common:
        return [f"{label}: the two documents share no team, so nothing was checked"]
    problems = []
    for team in common:
        for field in fields:
            a, b = mine[team].get(field), yours[team].get(field)
            if isinstance(a, float) or isinstance(b, float):
                a = round(float(a), DECIMALS) if a is not None else None
                b = round(float(b), DECIMALS) if b is not None else None
            if a != b:
                problems.append(f"{label}: team {team} field {field!r}: {a!r} != {b!r}")
    if problems:
        problems.append(f"{label}: {len(common)} teams compared")
    return problems


def check(data: Path, season: int) -> list[str]:
    """Every check in section 9 of the contract. Returns the list of problems."""
    problems: list[str] = []
    season_dir = Path(data) / str(season)
    man = _load(grid.manifest_path(data, season))

    # ---------------------------------------------------- the manifest's own shape
    if man.get("schema_version") != grid.SCHEMA_VERSION:
        problems.append(
            f"manifest schema_version is {man.get('schema_version')!r}, "
            f"expected {grid.SCHEMA_VERSION}"
        )
    if man.get("n_cells") != len(grid.CELLS):
        problems.append(f"manifest n_cells is {man.get('n_cells')!r}, expected {len(grid.CELLS)}")
    listed = len(man.get("cells") or [])
    if listed != len(grid.CELLS):
        problems.append(f"manifest lists {listed} cells, expected {len(grid.CELLS)}")
    weeks = list(man.get("weeks") or [])
    if not weeks:
        problems.append("manifest names no weeks, so it indexes nothing")
    published_ids = [c["id"] for c in man.get("cells") or [] if c.get("is_published")]
    if published_ids != [grid.published_cell().id]:
        problems.append(
            f"exactly one cell must be the published poll; manifest flags {published_ids}"
        )

    evidence_seen: dict[str, str] = {}

    # ------------------------------------------------------------ every cell file
    for entry in man.get("cells") or []:
        cell_id = str(entry["id"])
        try:
            cell = grid.by_id(cell_id)
        except KeyError as error:
            problems.append(str(error))
            continue

        # The addressing rule: the id must be what the slugs compose.
        if entry.get("slugs") != cell.slugs:
            problems.append(f"{cell_id}: manifest slugs {entry.get('slugs')} != {cell.slugs}")
        if entry.get("detents") != cell.published_settings:
            problems.append(
                f"{cell_id}: manifest detents {entry.get('detents')} != {cell.published_settings}"
            )

        for week in weeks:
            rel = (entry.get("files") or {}).get(str(week))
            if not rel:
                problems.append(f"{cell_id}: manifest names week {week} but carries no file for it")
                continue
            path = season_dir / rel
            try:
                doc = _load(path)
            except Failure as error:
                problems.append(str(error))
                continue

            if doc.get("schema_version") != grid.SCHEMA_VERSION:
                problems.append(f"{rel}: schema_version {doc.get('schema_version')!r}")
            if doc.get("season") != season or doc.get("week") != week:
                problems.append(
                    f"{rel}: says season {doc.get('season')} week {doc.get('week')}"
                )
            block = doc.get("cell") or {}
            if block.get("id") != cell_id:
                problems.append(f"{rel}: cell.id is {block.get('id')!r}, path says {cell_id!r}")
            if block.get("detents") != cell.published_settings:
                problems.append(f"{rel}: cell.detents disagree with the id")
            if block.get("changes") != cell.changes:
                problems.append(f"{rel}: cell.changes disagree with the id")

            agree = doc.get("agreement") or {}
            if agree.get("n_knobs_moved") != cell.n_knobs_moved:
                problems.append(f"{rel}: n_knobs_moved {agree.get('n_knobs_moved')!r}")
            # THE VERDICT RULE, and it is the one field this grid publishes less of
            # than the playground. `dial`/`convention` is a labelling standard fixed
            # by ADR 0006 against one-knob sweeps; on a two-knob cell the word would
            # be attributable to nothing.
            if cell.n_knobs_moved == 1:
                if agree.get("verdict") not in ("dial", "convention"):
                    problems.append(
                        f"{rel}: one knob moved, so a verdict is owed; got "
                        f"{agree.get('verdict')!r}"
                    )
            elif agree.get("verdict") is not None:
                problems.append(
                    f"{rel}: {cell.n_knobs_moved} knobs moved but verdict is "
                    f"{agree.get('verdict')!r}; it must be null"
                )
            if len(doc.get("rows") or []) > variants.TOP_N:
                problems.append(f"{rel}: {len(doc['rows'])} rows, contract says {variants.TOP_N}")

            # THE INTEGRITY BLOCK. Identical across every cell of a week, by
            # construction, because a lever moves values and never evidence.
            ev = json.dumps(block.get("evidence") or {}, sort_keys=True)
            key = f"week-{week:02d}"
            if key in evidence_seen and evidence_seen[key] != ev:
                problems.append(
                    f"{rel}: evidence block differs from another cell of the same "
                    f"week. The grid is comparing two different measurements."
                )
            evidence_seen.setdefault(key, ev)

    # ------------------------------- the cells that reproduce a published document
    for entry in man.get("cells") or []:
        equivalent = entry.get("equivalent_to")
        if not equivalent:
            continue
        cell_id = str(entry["id"])
        for week in weeks:
            rel = (entry.get("files") or {}).get(str(week))
            if not rel:
                continue
            ours = (_load(season_dir / rel)).get("rows") or []
            kind = equivalent["kind"]
            if kind == "house":
                other = season_dir / f"week-{week:02d}.json"
                theirs = (_load(other)).get("poll") or []
            elif kind == "recipe":
                other = season_dir / "recipes" / equivalent["id"] / f"week-{week:02d}.json"
                if not other.exists():
                    problems.append(
                        f"{cell_id}: claims to reproduce recipe {equivalent['id']!r} but "
                        f"{other} is not published, so the claim is unchecked"
                    )
                    continue
                theirs = (_load(other)).get("poll") or []
            else:
                other = season_dir / "variants" / equivalent["id"] / f"week-{week:02d}.json"
                if not other.exists():
                    problems.append(
                        f"{cell_id}: claims to reproduce variant {equivalent['id']!r} but "
                        f"{other} is not published, so the claim is unchecked"
                    )
                    continue
                theirs = (_load(other)).get("rows") or []
            problems.extend(
                _compare_rows(f"{cell_id} vs {kind} {equivalent['id']} week {week}", ours, theirs)
            )

    # The evidence block must also match the published poll's own.
    for week in weeks:
        house = _load(season_dir / f"week-{week:02d}.json")
        theirs = json.dumps((house.get("recipe") or {}).get("evidence") or {}, sort_keys=True)
        ours = evidence_seen.get(f"week-{week:02d}")
        if ours is not None and ours != theirs:
            problems.append(
                f"week {week}: the grid's evidence block differs from the published "
                f"poll's. A lever moved evidence, which it may not do."
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="The published fixture tree.")
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()

    try:
        problems = check(args.data, args.season)
    except Failure as error:
        print(f"FAIL  {error}")
        return 1

    if problems:
        print(f"FAIL  {len(problems)} problem(s) in {args.data}/{args.season}/lever-grid:")
        for problem in problems[:40]:
            print(f"  {problem}")
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        return 1

    man = _load(grid.manifest_path(args.data, args.season))
    labelled = sum(1 for c in man["cells"] if c["equivalent_to"])
    print(
        f"OK    {man['n_cells']} cells x weeks {man['weeks']} under "
        f"{args.data}/{args.season}/lever-grid"
    )
    print(
        f"      {labelled} of them reproduce an already-published board and every "
        f"shared row matches"
    )
    print("      every cell carries the published poll's own evidence digest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
