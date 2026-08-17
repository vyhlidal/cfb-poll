"""The lever grid: every combination of three published levers, precomputed.

WHAT THIS IS FOR, AND THE RULE THAT SHAPES ALL OF IT. `publish/variants.py` moves
ONE constant one click and asks whether that constant decides the ranking. This
module asks the next question, which is the one a reader actually wants: "what
would the poll look like if I set these three things the way I believe them?" The
answer has to be a board that came out of this pipeline, so it is precomputed. A
continuous slider would need a fit per request and a fit per request is a model in
the browser, and the moment there are two implementations of this model they drift
and the checkable promise is gone. Hence a GRID: six by four by three, seventy-two
boards, one of which is the published poll.

THE CONTRACT IS docs/fixture-contract-levers.md AND IT WAS WRITTEN FIRST. Field
names, the manifest schema, the addressing rule and the two places where
`src/cfbpoll/levers.py` disagrees with this grid are all argued there rather than
here.

NOTHING IN THIS FILE DEFINES A NUMBER. Rows, rounding, the tau, the moved count and
the 0.985 line are all imported from `publish/variants.py`, which imported the row
values from `publish/serving.py` in the first place. A lever board and a playground
variant sit beside each other on the same page; if this module held its own copy of
`ROW_FIELDS` or its own tau, the two documents would eventually disagree about the
same week and no reader could tell which was right.

THE ONE THING THIS MODULE PUBLISHES LESS OF THAN THE PLAYGROUND: the verdict.
`dial` and `convention` are a labelling standard with a fixed meaning, fixed by
ADR 0006 against ONE-KNOB sweeps, and `publish/variants.py` exists precisely so a
tau can be attributed to a single constant. A cell that moved two knobs has a tau
nobody can assign to either, so `agreement.verdict` is `None` there. The tau itself
is still published, because "how different is this board" is a fair question at any
number of knobs. It is the WORD that is unattributable, not the number.

A LEVER MOVES VALUES, NEVER EVIDENCE, and it is the same enforcement recipes and
variants get rather than a promise made here: the generated overlays are loaded
through `recipes.load`, which runs `assert_values_only` against
`recipes.EVIDENCE_KEYS` before any fit, and resolved through `config.merge_overlay`,
which refuses a key `configs/default.toml` does not define. The consequence is
published per cell in `cell.evidence` and checked by `scripts/check_lever_grid.py`.

GRID CELLS ARE NOT RECIPES AND DO NOT ENTER THE ROSTER. They are precomputed into
their own subtree, `publish fixtures` never sees them, `recipes.roster()` never
sees them, and `index.json` is untouched.
"""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cfbpoll.publish.variants import (
    ROW_FIELDS,
    TAU_FLOOR,
    TOP_N,
    _dump,
    _jsonable,
    _round,
    house_ranks,
)
from cfbpoll.publish.variants import agreement as _tau_agreement

__all__ = [
    "AXES",
    "CELLS",
    "HOUSE_BASE",
    "SCHEMA_VERSION",
    "Axis",
    "Cell",
    "Detent",
    "agreement",
    "by_id",
    "cell_dir",
    "document",
    "equivalent_to",
    "export",
    "grid_dir",
    "manifest",
    "manifest_path",
    "overlay_toml",
    "write_manifest",
    "write_overlays",
]

#: This document's own shape, and it is deliberately neither `fixtures.SCHEMA_VERSION`
#: nor `variants.SCHEMA_VERSION`. Three contracts answering three questions have to
#: be able to move independently, or a change to the poll's shape forces a version
#: bump on a playground document that did not change.
SCHEMA_VERSION = 1

#: What every cell is measured against: the published poll, and the only base there
#: is. The house cell is the poll itself and its tau against itself is 1.0.
HOUSE_BASE = "house"


@dataclass(frozen=True)
class Detent:
    """One click of one lever. `slug` is the path segment and the id fragment."""

    value: Any
    slug: str

    @property
    def published_value(self) -> Any:
        """The value as it is published. `inf` is `"uncapped"`; see `_jsonable`."""
        return _jsonable(self.value)


@dataclass(frozen=True)
class Axis:
    """One lever, its detents, and where the published poll sits on it."""

    #: The dotted key exactly as `configs/default.toml` spells it, which is also the
    #: key `src/cfbpoll/levers.py` registers it under. One string, two purposes, on
    #: purpose: the page reads the label out of the registry by this key.
    key: str
    #: What the id fragment is prefixed with. Empty for the ordering, whose slugs
    #: are already words (`odds`, `resume`, `resume-margin`) rather than numbers
    #: that would be unreadable without one.
    slug_prefix: str
    detents: tuple[Detent, ...]
    #: The house value, which must be one of `detents`. Asserted in
    #: `tests/unit/test_lever_grid.py`: a grid whose axis does not contain the
    #: published setting cannot show a reader where they started.
    house: Any

    @property
    def table(self) -> str:
        return self.key.partition(".")[0]

    @property
    def field(self) -> str:
        return self.key.partition(".")[2]

    def registry(self) -> Any:
        """This axis's entry in the lever registry. Raises if it is not registered.

        THE PROSE IS LIFTED RATHER THAN REWRITTEN. `label`, `plain` and `evidence`
        on the manifest come from `src/cfbpoll/levers.py`, so the panel and
        `cfbpoll levers` say the same sentence about the same knob. A second copy
        here would be a second thing to keep in step and the first drift would be
        invisible.
        """
        from cfbpoll import levers

        return levers.get(self.key)


#: THE THREE LEVERS AND THEIR DETENTS. Every value below is one some document in
#: this repository already argues for, and the table of citations is section 2 of
#: docs/fixture-contract-levers.md. The two omissions worth knowing about are
#: argued there too: `margin.c = 8` is not here because nothing cites it, and
#: `weights.recency_gamma` is not a fourth axis because it would multiply the cost
#: of the grid by five.
#:
#: THE GRID LIVES HERE RATHER THAN IN configs/default.toml FOR THE REASON
#: `publish/variants.py` gives: the config is the methodology and `config_hash` is
#: on every published run's receipt, so a playground table in it would change that
#: hash for every house run and make the poll's provenance depend on an experiment
#: the poll does not use.
AXES: tuple[Axis, ...] = (
    Axis(
        key="margin.c",
        slug_prefix="c",
        detents=(
            # `just-win`'s constant, and the `margin-c-1` playground variant.
            Detent(1.0, "1"),
            # The floor of campaign 1's grid, and the `margin-c-18` variant.
            Detent(18.0, "18"),
            # This project's own value before ADR 0007 replaced it.
            Detent(24.0, "24"),
            # Fitted 2026-08-12 over a 416-cell factorial. ADR 0007. THE POLL.
            Detent(32.0, "32"),
            # `levers.get("margin.c").sweep`.
            Detent(48.0, "48"),
            # `full-merit`'s constant, the `margin-c-uncapped` variant, and the top
            # of the grid campaign 2 pre-registered. `inf` is the LIMIT of the tanh
            # family and a real setting; `design.tanh_term` takes it explicitly.
            Detent(math.inf, "uncapped"),
        ),
        house=32.0,
    ),
    Axis(
        key="margin.beta_w",
        slug_prefix="bw",
        # `levers.get("margin.beta_w").sweep` exactly, which is also the set the
        # shipped playground variants use. 3 is Sports-Reference CFB SRS's margin
        # floor expressed in these units.
        detents=(Detent(0.0, "0"), Detent(3.0, "3"), Detent(7.0, "7"), Detent(12.0, "12")),
        house=7.0,
    ),
    Axis(
        key="publication.headline_ordering",
        slug_prefix="",
        # ALL THREE LEGAL STRINGS, which is one more than the registry's sweep can
        # express. See section 2 of the contract: `L4_resume_margin` is
        # `full-merit`'s ordering and dropping it would remove the constant that IS
        # that recipe's argument.
        detents=(
            Detent("schedule_odds", "odds"),
            Detent("L4_resume", "resume"),
            Detent("L4_resume_margin", "resume-margin"),
        ),
        house="schedule_odds",
    ),
)


@dataclass(frozen=True)
class Cell:
    """One combination: one detent on each axis. `id` is a path segment."""

    #: Parallel to `AXES`, one detent per axis, same order.
    detents: tuple[Detent, ...]

    @property
    def id(self) -> str:
        """`c-32-bw-7-odds`. A PURE FUNCTION OF THE SLUGS, which is the addressing
        rule the site relies on: a panel composes this from three slider positions
        and never scans the manifest's `cells` array to find a file.
        """
        parts = []
        for axis, detent in zip(AXES, self.detents, strict=True):
            parts.append(f"{axis.slug_prefix}-{detent.slug}" if axis.slug_prefix else detent.slug)
        return "-".join(parts)

    @property
    def settings(self) -> dict[str, Any]:
        """Every axis, dotted key -> raw value. ALL THREE, not a diff."""
        return {axis.key: detent.value for axis, detent in zip(AXES, self.detents, strict=True)}

    @property
    def published_settings(self) -> dict[str, Any]:
        """Every axis, dotted key -> JSON-safe value."""
        return {key: _jsonable(value) for key, value in self.settings.items()}

    @property
    def slugs(self) -> dict[str, str]:
        return {axis.key: detent.slug for axis, detent in zip(AXES, self.detents, strict=True)}

    @property
    def changes(self) -> dict[str, Any]:
        """Only what differs from the published poll, dotted key -> JSON-safe value.

        `settings` positions the sliders and `changes` is what the page says
        changed. They are different questions and the contract publishes both.
        """
        return {
            axis.key: _jsonable(detent.value)
            for axis, detent in zip(AXES, self.detents, strict=True)
            if detent.value != axis.house
        }

    @property
    def n_knobs_moved(self) -> int:
        return len(self.changes)

    @property
    def is_published(self) -> bool:
        """True for the one cell that IS the published poll."""
        return self.n_knobs_moved == 0

    @property
    def overrides(self) -> dict[str, Any]:
        """The overlay, nested for TOML. ALL THREE KEYS, including unmoved ones.

        Writing the house value explicitly rather than omitting it is deliberate.
        `merge_overlay` treats a key set to its default as a no-op, so the resolved
        config and therefore `config_sha256` are unchanged either way; what the
        explicit form buys is a run whose overlay file states, on its face, every
        constant the reader chose. A run directory that has to be diffed against
        configs/default.toml to say what it was is a run directory nobody can read.
        """
        nested: dict[str, dict[str, Any]] = {}
        for axis, detent in zip(AXES, self.detents, strict=True):
            nested.setdefault(axis.table, {})[axis.field] = detent.value
        return nested


#: EVERY COMBINATION, IN A FIXED ORDER. `itertools.product` varies the last axis
#: fastest, so the ordering is `margin.c` outermost and the headline ordering
#: innermost, which is the order the contract's table lists them in and the order a
#: manifest reader sees. It is deterministic, which is what matters: the manifest's
#: `cells` array must be a pure function of this file.
CELLS: tuple[Cell, ...] = tuple(
    Cell(detents=combo) for combo in itertools.product(*(axis.detents for axis in AXES))
)

_BY_ID: dict[str, Cell] = {cell.id: cell for cell in CELLS}


def by_id(cell_id: str) -> Cell:
    """One cell by its identifier. Raises `KeyError` rather than guessing."""
    try:
        return _BY_ID[cell_id]
    except KeyError:
        raise KeyError(
            f"no lever-grid cell {cell_id!r}. There are {len(CELLS)}; the published "
            f"poll is {published_cell().id!r}."
        ) from None


def published_cell() -> Cell:
    """The one cell that is the published poll: every axis at its house value."""
    return by_id(Cell(detents=tuple(_house_detent(axis) for axis in AXES)).id)


def _house_detent(axis: Axis) -> Detent:
    for detent in axis.detents:
        if detent.value == axis.house:
            return detent
    raise ValueError(
        f"axis {axis.key!r} has house value {axis.house!r}, which is not one of its "
        f"detents. A grid that cannot show a reader where they started is not a grid."
    )


# ------------------------------------------------------------------- the overlays


#: What a generated overlay says its costs are. `recipes.load` requires at least
#: one, because a published value system that will not state its own cost is a
#: marketing page. These are properties of BEING a grid cell rather than of any
#: particular combination, which is why they are the same three for all seventy-two.
_CELL_TRADEOFFS: tuple[str, ...] = (
    "It is a point on a grid, not an argument. Nothing here says these constants "
    "are right; the grid exists so a reader can find out what their own answer "
    "would have looked like.",
    "It carries no gate verdict and no backtest. The publication gate is written "
    "against the published poll, and nothing in this grid was scored against it.",
    "Two or three constants move at once in most cells, so the difference from the "
    "published board cannot be attributed to any one of them. That is why the "
    "published document withholds the dial-or-convention verdict off the one-knob "
    "edges of the grid.",
)

_TRADEOFF_LINES = "\n".join(f"    {json.dumps(t)}," for t in _CELL_TRADEOFFS)


def _toml_value(value: Any) -> str:
    """A Python value as TOML. `inf` is spelled `inf`, exactly as full-merit does."""
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)
    return repr(value)


def overlay_toml(cell: Cell) -> str:
    """The generated overlay for one cell, as TOML text.

    It is a REAL RECIPE FILE, so `cfbpoll rank --recipe-dir` loads it through
    exactly the machinery a hand-written recipe goes through: `assert_values_only`
    refuses it if it names an evidence key, `merge_overlay` refuses it if it names
    a key the default config does not define, and the run it produces stamps the
    cell's own id on `model_params.json` rather than claiming to be the house poll.

    THE PROSE IS MECHANICAL AND SAYS SO, for the reason `variants.overlay_toml`
    gives: a grid cell is not a value system and has no case to make.
    """
    settings = ", ".join(
        f"{key} = {_jsonable(value)}" for key, value in cell.settings.items()
    )
    blocks = []
    for table, entries in cell.overrides.items():
        lines = "\n".join(f"{key} = {_toml_value(value)}" for key, value in entries.items())
        blocks.append(f"[{table}]\n{lines}")
    body = "\n\n".join(blocks)
    return f"""\
# GENERATED by cfbpoll.publish.lever_grid. Do not edit; edit AXES and regenerate.
#
# One cell of the published lever grid: three constants of configs/default.toml at
# one setting each, with every other constant left where the published poll leaves
# it. This file exists so `cfbpoll rank` can produce a run that names the
# combination it ran. It is scratch: it is not a named value system, it is not in
# configs/recipes/, and it never reaches the roster that builds the site's recipe
# selector.

[recipe]
slug = "{cell.id}"
name = "{settings}"
stance = 1
one_liner = "The published poll with {settings}."

manifesto = \"\"\"
A grid cell, not a recipe. Every constant here is the published poll's except the
ones a reader moved, and there is no case for this combination in this file and
none is implied. The point of precomputing the whole grid is that the board a
reader reaches came out of this pipeline rather than out of a reimplementation of
it in a browser, which is what makes it checkable against the published poll
sitting beside it.
\"\"\"

tradeoffs = [
{_TRADEOFF_LINES}
]

{body}
"""


def write_overlays(directory: Path, cells: tuple[Cell, ...] = CELLS) -> list[Path]:
    """Generate every cell's overlay into `directory`. Returns the paths, sorted.

    Idempotent: the text is a pure function of the `Cell`, so regenerating over an
    existing directory converges rather than accumulating.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for cell in cells:
        path = directory / f"{cell.id}.toml"
        path.write_text(overlay_toml(cell), encoding="utf-8")
        written.append(path)
    return sorted(written)


# ----------------------------------------------------------------------- the paths


def grid_dir(dest: Path, season: int) -> Path:
    """`<dest>/<season>/lever-grid/`. A sibling of `variants/` and `recipes/`."""
    return Path(dest) / str(season) / "lever-grid"


def cell_dir(dest: Path, season: int, cell_id: str) -> Path:
    """`<dest>/<season>/lever-grid/<cell-id>/`."""
    return grid_dir(dest, season) / cell_id


def manifest_path(dest: Path, season: int) -> Path:
    """`<dest>/<season>/lever-grid/manifest.json`. The one-fetch board."""
    return grid_dir(dest, season) / "manifest.json"


# --------------------------------------------------------------------- the numbers


def agreement(house: dict[int, int], cell_ranks: dict[int, int], cell: Cell) -> dict[str, Any]:
    """`variants.agreement` plus the knob count, minus the word where it cannot mean anything.

    THE TAU, THE MOVED COUNT AND THE FLOOR ARE NOT RECOMPUTED HERE. They come out
    of `publish/variants.py` unchanged, which is what lets a page put a lever board
    and a playground variant side by side and compare the two numbers.

    THE VERDICT IS WITHHELD OFF THE ONE-KNOB EDGES. `dial` and `convention` are a
    labelling standard whose meaning ADR 0006 fixed against one-knob sweeps, and a
    cell that moved two constants has a tau no reader can assign to either. A page
    must render `null` as no verdict rather than as "convention": the absence of a
    label is not a finding of no effect, and publishing the word here would put a
    second, looser definition of `dial` in front of readers who have already seen
    the strict one on the playground.

    `n_moved_5_or_more` carries the same warning it carries on a variant document.
    It is a LEGIBILITY count, not a significance test: the published 90% rank
    intervals on this poll have a median width of 75 places, so five places is deep
    inside the uncertainty the project already publishes.
    """
    stats = _tau_agreement(house, cell_ranks)
    moved = cell.n_knobs_moved
    return {
        "kendall_tau_vs_house": stats["kendall_tau_vs_house"],
        "n_moved_5_or_more": stats["n_moved_5_or_more"],
        "n_teams_compared": stats["n_teams_compared"],
        "tau_floor": TAU_FLOOR,
        "n_knobs_moved": moved,
        "verdict": stats["verdict"] if moved == 1 else None,
    }


def document(bundle: Any, cell: Cell, house: dict[int, int], top_n: int = TOP_N) -> dict[str, Any]:
    """The thin ordering document for one cell of one week.

    `bundle` is what `publish.serving.build` returned for the cell's run. Every row
    value is lifted from `bundle.views["week"]["poll"]`, the same computation that
    produced the house week's rows, so a cell row cannot drift from a poll row:
    there is no second definition of `one_in` or `power_rank` anywhere in this file.
    """
    week_view = bundle.views["week"]
    poll = week_view["poll"]
    recipe = week_view["recipe"]

    ranks = {int(row["team_id"]): int(row["rank"]) for row in poll}
    rows = [
        {field: _round(row.get(field)) for field in ROW_FIELDS}
        for row in sorted(poll, key=lambda r: int(r["rank"]))[:top_n]
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "season": int(bundle.season),
        "week": int(bundle.week),
        "season_type": str(bundle.season_type),
        "generator": "cfbpoll publish lever-grid",
        "cell": {
            "id": cell.id,
            "base": HOUSE_BASE,
            "detents": cell.published_settings,
            "changes": cell.changes,
            # The hash of the RESOLVED methodology this run used, which is what
            # distinguishes two cells sharing one base config.
            "config_sha256": recipe.get("config_sha256"),
            # THE INTEGRITY BLOCK, IDENTICAL ACROSS ALL SEVENTY-TWO CELLS AND
            # IDENTICAL TO THE HOUSE WEEK'S BY CONSTRUCTION. "A lever moves values,
            # never evidence" is a claim, and a claim a reader cannot check is a
            # slogan: these three fields let a page assert it against the published
            # poll it is sitting beside, and `scripts/check_lever_grid.py` asserts
            # it across every file the manifest names.
            "evidence": dict(recipe.get("evidence") or {}),
        },
        "agreement": agreement(house, ranks, cell),
        "rows": rows,
    }


def export(run: Path, dest: Path, cell: Cell, archive: Path | None = None) -> Path:
    """Publish one cell run as one thin document. Returns the path written.

    NO MANIFEST IS REBUILT HERE. The manifest is a statement about the whole grid
    and writing it once per cell would mean seventy-two manifests, seventy-one of
    which described a grid that was not finished. `write_manifest` is a separate
    step and the make target runs it last.
    """
    from cfbpoll.publish.serving import build

    bundle = build(run, archive=archive, backtest=None)
    house = house_ranks(dest, bundle.season, bundle.week)
    payload = document(bundle, cell, house)
    path = cell_dir(dest, bundle.season, cell.id) / f"week-{bundle.week:02d}.json"
    _dump(path, payload)
    return path


# -------------------------------------------------------------------- equivalence


def _recipe_settings() -> dict[str, dict[str, Any]]:
    """`{slug: {axis key: published value}}` for every shipped recipe.

    RESOLVED RATHER THAN READ OFF THE OVERRIDE BLOCK. `just-win.toml` states
    `beta_w = 7.0` explicitly even though that is the house value, so comparing
    override blocks would miss it while comparing resolved constants does not. This
    fits nothing and reads no archive; it merges TOML.
    """
    from cfbpoll import recipes

    out: dict[str, dict[str, Any]] = {}
    for entry in recipes.roster():
        slug = str(entry["slug"])
        config, _ = recipes.resolve(slug)
        out[slug] = {
            axis.key: _jsonable(config[axis.table][axis.field]) for axis in AXES
        }
    return out


def _variant_changes() -> dict[str, dict[str, Any]]:
    """`{variant id: its one change}` for the eight shipped playground variants."""
    from cfbpoll.publish import variants

    return {variant.id: dict(variant.changes) for variant in variants.VARIANTS}


def equivalent_to(cell: Cell, season: int, week: int) -> dict[str, Any] | None:
    """What already-published document this cell reproduces, or `None`.

    DERIVED FROM THE CONSTANTS, NOT FROM A DIFF OF THE DOCUMENTS. This says "these
    are `just-win`'s constants"; `scripts/check_lever_grid.py` is what then proves
    the two boards actually agree. Splitting it that way is deliberate: a label
    computed from a diff could not go stale and also could not be wrong in a way
    worth catching, and the whole point of the check script is to catch a grid that
    stopped being the pipeline.

    Priority is recipe before variant because a recipe is the more specific claim
    and, today, no cell matches both: `full-merit` and `just-win` each move two or
    three constants, and a variant is one by definition.
    """
    from cfbpoll import recipes

    settings = cell.published_settings
    for slug, resolved in sorted(_recipe_settings().items()):
        if resolved != settings:
            continue
        if slug == recipes.HOUSE:
            return {
                "kind": "house",
                "id": slug,
                "path": f"{season}/week-{week:02d}.json",
            }
        return {
            "kind": "recipe",
            "id": slug,
            "path": f"{season}/recipes/{slug}/week-{week:02d}.json",
        }
    for variant_id, changes in sorted(_variant_changes().items()):
        if changes == cell.changes:
            return {
                "kind": "variant",
                "id": variant_id,
                "path": f"{season}/variants/{variant_id}/week-{week:02d}.json",
            }
    return None


# ----------------------------------------------------------------------- manifest


def _axis_document(axis: Axis) -> dict[str, Any]:
    lever = axis.registry()
    return {
        "key": axis.key,
        "label": lever.label,
        "plain": lever.plain,
        "evidence": lever.evidence,
        "slug_prefix": axis.slug_prefix,
        "detents": [
            {
                "value": detent.published_value,
                "slug": detent.slug,
                "default": detent.value == axis.house,
            }
            for detent in axis.detents
        ],
    }


def published_weeks(dest: Path, season: int) -> list[int]:
    """Which weeks the grid carries, read off disk rather than assumed.

    A WEEK COUNTS ONLY IF EVERY CELL HAS IT. A manifest that named a week half the
    grid was missing would hand a panel a slider position that 404s, and the panel
    cannot tell a missing file from a network fault. An incomplete week is
    therefore omitted here and reported by the caller.
    """
    weeks: set[int] | None = None
    for cell in CELLS:
        found = {
            int(path.stem.split("-")[-1])
            for path in cell_dir(dest, season, cell.id).glob("week-*.json")
        }
        weeks = found if weeks is None else (weeks & found)
    return sorted(weeks or set())


def manifest(dest: Path, season: int, weeks: list[int] | None = None) -> dict[str, Any]:
    """The whole grid as one document. See section 4 of the contract."""
    resolved = list(weeks) if weeks is not None else published_weeks(dest, season)
    if not resolved:
        raise FileNotFoundError(
            f"no complete week of the lever grid under {grid_dir(dest, season)}. A "
            f"week counts only when all {len(CELLS)} cells carry it, so a partial "
            f"generation produces no manifest rather than a manifest that 404s."
        )
    latest = resolved[-1]
    house = published_cell()
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": "cfbpoll publish lever-grid",
        "season": int(season),
        "weeks": resolved,
        "n_cells": len(CELLS),
        "top_n": TOP_N,
        "tau_floor": TAU_FLOOR,
        "published": {
            "cell_id": house.id,
            "detents": house.published_settings,
            "note": (
                "This combination is the published poll. Its board is "
                f"{season}/week-NN.json and the grid's copy of it is the cell file, "
                "which carries the same rows."
            ),
        },
        "axes": [_axis_document(axis) for axis in AXES],
        "cells": [
            {
                "id": cell.id,
                "detents": cell.published_settings,
                "slugs": cell.slugs,
                "changes": cell.changes,
                "n_knobs_moved": cell.n_knobs_moved,
                "is_published": cell.is_published,
                "files": {
                    str(week): f"lever-grid/{cell.id}/week-{week:02d}.json"
                    for week in resolved
                },
                # Computed against the LATEST week only, because the equivalence is
                # a statement about constants and the path it names is per week.
                "equivalent_to": equivalent_to(cell, season, latest),
            }
            for cell in CELLS
        ],
    }


def write_manifest(dest: Path, season: int, weeks: list[int] | None = None) -> Path:
    """Write `<season>/lever-grid/manifest.json`. Returns the path."""
    path = manifest_path(dest, season)
    _dump(path, manifest(dest, season, weeks=weeks))
    return path
