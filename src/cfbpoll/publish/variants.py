"""The knob playground: eight one-knob perturbations of the published poll.

WHAT THIS IS FOR. `configs/recipes/` offers three NAMED VALUE SYSTEMS, each an
argument about what football results are for, each published with its manifesto
and its costs. This module offers something smaller and colder: one constant
moved one click, with no argument attached, so a reader can find out for
themselves which of this project's constants actually decide the ranking and
which are conventions that could have been set differently without anybody
noticing. A recipe asks "what do you value?". A variant asks "does this knob
even matter?", and publishes the measured answer rather than a paragraph.

THE ANSWER IS A WORD THE PIPELINE CHOSE, NOT ONE A PAGE PICKED. Every document
carries `agreement.verdict`, either `"convention"` or `"dial"`, computed here
against the 0.985 Kendall's tau line this project has published since ADR 0006
and applied unchanged in ADR 0007, ADR 0009 and both tuning campaigns:

    a parameter whose tau against the incumbent falls below the 0.985 that the
    published q_ref sweep never dipped below is a DIAL, not a convention, and
    must be labelled as one.

That is a LABELLING obligation, and it is discharged here rather than on the
site, for the same reason every other number is: the site does not compute
(report 03 §6.3, report 05 §7.2). A page that decided the word itself could
decide it differently from the campaign documents, and then the project would be
publishing two definitions of "dial" and no way to tell which one a reader saw.

A THIN ORDERING DOCUMENT, NOT A WEEK. `<season>/week-NN.json` is 200 KB: every
ranked team, every column, the marks, the logos, the provenance, the whole poll.
That is the right size for the poll and the wrong size for a knob. A variant is
interesting only as an ORDERING - which teams moved, how far, and whether the
board is recognisably the same board - so a variant document carries the top 40
rows, eleven columns, and the agreement statistics, and nothing else. It weighs
about 8 KB, of which 7 KB is the forty rows and well over half of that is the
column names repeated forty times. A columnar encoding would roughly halve it,
and it is not worth it: eight variants of a week is 63 KB against 200 KB for the
week itself, and a self-describing row that can be read beside a poll row without
a schema in the reader's head is worth more than the 3 KB.

    <dir>/<season>/variants/<variant-id>/week-NN.json

WHAT A VARIANT MAY NOT DO, and it is the same rule recipes obey: a variant
changes VALUES, never EVIDENCE. The overlays this module generates are loaded
through `recipes.load`, which runs `assert_values_only` against
`recipes.EVIDENCE_KEYS` before any fit, and resolved through
`config.merge_overlay`, which refuses a key `configs/default.toml` does not
define. The consequence is published rather than promised: `variant.evidence`
carries the same three digests the house week carries, and
`tests/unit/test_variants.py` asserts they are equal to the house week's, per
week, for every variant. If they ever differ, the comparison is between two
different measurements and the tau beside it means nothing.

VARIANTS ARE NOT RECIPES AND DO NOT ENTER THE ROSTER. They are precomputed into
their own subtree, they are never `publish fixtures`' business, and
`recipes.roster()` never sees them, so `index.json` and the site's recipe
selector are untouched by anything in this file.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "HOUSE_BASE",
    "ROW_FIELDS",
    "SCHEMA_VERSION",
    "TAU_FLOOR",
    "TOP_N",
    "VARIANTS",
    "Variant",
    "agreement",
    "by_id",
    "document",
    "export",
    "house_ranks",
    "overlay_toml",
    "variant_dir",
    "write_overlays",
]

#: This document's own shape. It is a NEW document at a NEW path, so it starts at
#: 1 and it is deliberately not `fixtures.SCHEMA_VERSION`: the poll's contract and
#: the playground's contract answer different questions and must be able to move
#: independently. A site reads this one to decide whether it understands a variant
#: document, and the poll's to decide whether it understands a week.
SCHEMA_VERSION = 1

#: THE LINE BETWEEN A CONVENTION AND A DIAL, and it is not this module's number.
#: It is the floor the published `q_ref` sensitivity sweep never dipped below
#: (docs/analysis/headline-ordering-study.md §9), fixed as the labelling standard
#: by ADR 0006 and applied unchanged by ADR 0007's frozen constants, ADR 0009's
#: accumulation window, and both tuning campaigns. It is repeated here rather than
#: imported because `scripts/tuning_campaign.py` is a study script and a published
#: document must not depend on one, but it is the SAME number and
#: `tests/unit/test_variants.py` asserts the two agree.
TAU_FLOOR = 0.985

#: How many rows a variant document carries. The poll ranks about 136 FBS teams;
#: a knob is interesting at the top of the board, where a place is worth something,
#: and forty rows is fifteen past the top 25 the page draws - far enough to show a
#: team entering or leaving it and to show the churn just below the cut.
#:
#: THE AGREEMENT STATISTICS ARE NOT COMPUTED ON THESE FORTY. See `agreement`.
TOP_N = 40

#: The columns on a variant row, in the order the contract lists them. Every one
#: is copied from the house week document's own poll row, computed by
#: `publish/serving.py`, so a variant row cannot drift from a poll row: there is
#: no second definition of `one_in` or `power_rank` in this file to drift.
ROW_FIELDS: tuple[str, ...] = (
    "team_id",
    "rank",
    "one_in",
    "odds_key",
    "resume",
    "resume_margin",
    "power",
    "power_rank",
    "gap",
    "rank_lo90",
    "rank_hi90",
)

#: What every variant is measured against, and the only base there is. A variant
#: is the published poll with one constant moved; a variant of a variant would be
#: a two-knob experiment whose tau nobody could attribute to either knob.
HOUSE_BASE = "house"

#: Rounding applied to the float columns. SIX DECIMALS IS A STATEMENT ABOUT WHAT
#: THE MODEL SUPPORTS, not a way to save bytes. Report 03 §9.3 records that this
#: pipeline reproduces to about 1e-12 on Apple Silicon rather than bit-for-bit, so
#: a playground document publishing seventeen significant digits would invite a
#: reader to diff two boards at a precision the arithmetic does not have and read
#: the noise as a finding. The poll publishes full precision because it is the
#: product; this is a comparison surface and rounds to what is comparable.
FLOAT_DECIMALS = 6


@dataclass(frozen=True)
class Variant:
    """One knob at one setting. `id` is a path segment and a stable identifier."""

    id: str
    #: The dotted key exactly as it appears in `configs/default.toml`, so a reader
    #: can find the constant and the paragraph above it that argues for its value.
    axis: str
    #: The value the axis takes under this variant. `math.inf` is a real setting of
    #: `margin.c` - the member of the tanh family that does not compress at all -
    #: and is published by the name campaign 2 gave it rather than dropped.
    value: Any

    @property
    def overrides(self) -> dict[str, Any]:
        """The sparse override, nested for TOML. `{"margin": {"beta_w": 0.0}}`."""
        table, _, key = self.axis.partition(".")
        if not table or not key:
            raise ValueError(
                f"variant {self.id!r} has axis {self.axis!r}, which is not a "
                f"`table.key` path into configs/default.toml."
            )
        return {table: {key: self.value}}

    @property
    def changes(self) -> dict[str, Any]:
        """The published `changes` map: dotted key -> JSON-safe value."""
        return {self.axis: _jsonable(self.value)}


#: THE EIGHT VARIANTS, THREE AXES, EVERY OTHER CONSTANT AT ITS HOUSE VALUE.
#:
#: One knob moves per variant and the rest stay where `configs/default.toml` puts
#: them (`margin.c = 32.0`, `margin.beta_w = 7.0`,
#: `publication.headline_ordering = "schedule_odds"`). That is what makes the tau
#: attributable: a document reporting a two-knob change reports a number no reader
#: can assign to either knob, which is worse than reporting nothing.
#:
#: WHY THESE VALUES AND NOT OTHERS. They are not invented here. `beta_w` at 0.0 is
#: the bottom of campaign 1's grid and the setting that removes the win premium
#: entirely, turning a football ranking into a scoring-margin ranking; 3.0 is
#: Sports-Reference CFB SRS's +/-7 margin floor expressed in these units and the
#: value this project itself used before ADR 0007; 12.0 is the top of campaign 2's
#: grid. `margin.c` at 1.0 is compression so hard that every win is worth
#: essentially the same; 18.0 sits below the fitted 32.0 with the old 24.0 between
#: them; `inf` is the top of the grid campaign 2 pre-registered. The two orderings
#: are candidates A and B of the headline ordering study, which is where the house
#: choice came from. Every one of these is a value some defensible poll does use.
#:
#: THE GRID LIVES HERE RATHER THAN IN configs/default.toml ON PURPOSE. The config
#: is the methodology and `config_hash` is on every published run's receipt, so
#: adding a playground table to it would change that hash for every house run and
#: make the poll's provenance depend on an experiment the poll does not use.
VARIANTS: tuple[Variant, ...] = (
    Variant(id="margin-beta-w-0", axis="margin.beta_w", value=0.0),
    Variant(id="margin-beta-w-3", axis="margin.beta_w", value=3.0),
    Variant(id="margin-beta-w-12", axis="margin.beta_w", value=12.0),
    Variant(id="margin-c-1", axis="margin.c", value=1.0),
    Variant(id="margin-c-18", axis="margin.c", value=18.0),
    Variant(id="margin-c-uncapped", axis="margin.c", value=math.inf),
    Variant(id="ordering-l4-resume", axis="publication.headline_ordering", value="L4_resume"),
    Variant(
        id="ordering-l4-resume-margin",
        axis="publication.headline_ordering",
        value="L4_resume_margin",
    ),
)


def by_id(variant_id: str) -> Variant:
    """One variant by its identifier. Raises `KeyError` naming the eight."""
    for variant in VARIANTS:
        if variant.id == variant_id:
            return variant
    raise KeyError(f"no variant {variant_id!r}. Known: {', '.join(v.id for v in VARIANTS)}.")


# ------------------------------------------------------------------------- helpers


def _jsonable(value: Any) -> Any:
    """JSON carries no infinity, and `margin.c = inf` is a real setting.

    Same rule and the same two names as `recipes._jsonable`, because a variant of
    `margin.c` and the `full-merit` recipe publish the same constant and a reader
    comparing the two documents must not find it spelled two ways.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return "uncapped" if value > 0 else "-uncapped"
    return value


def _round(value: Any) -> Any:
    if isinstance(value, float) and math.isfinite(value):
        return round(value, FLOAT_DECIMALS)
    return value


def _dump(path: Path, payload: Any) -> None:
    """Stable JSON: sorted keys, compact separators, trailing newline.

    Sorted keys for the same reason every other document in this tree sorts them
    (report 03 §9.3): the bytes must be a pure function of the computation, so a
    change in the data is visible as a change in the file. COMPACT rather than
    `indent=2`, which is the one place this differs from `publish/fixtures.py`,
    because forty rows of eleven columns pretty-printed is 13 KB of mostly
    whitespace for a document whose entire reason to exist is being small enough
    that a page can fetch eight of them.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )


def overlay_toml(variant: Variant) -> str:
    """The generated overlay for one variant, as TOML text.

    It is a REAL RECIPE FILE - a `[recipe]` block plus the one constant it changes
    - so `cfbpoll rank --recipe-dir` loads it through exactly the machinery a
    hand-written recipe goes through: `assert_values_only` refuses it if it names
    an evidence key, `merge_overlay` refuses it if it names a key the default
    config does not define, and the run it produces stamps the variant's own id on
    `model_params.json` rather than claiming to be the house poll.

    THE PROSE IS MECHANICAL AND SAYS SO. `recipes.load` requires a name, a
    one-liner, a manifesto and at least one tradeoff, because a published value
    system that will not state its own cost is a marketing page. A variant is not
    a value system and has no case to make: it is one constant moved so the data
    can be asked whether that matters. So the generated prose describes the
    mechanical change and points at the measurement, and the variant document
    itself carries none of it - only the axis, the value, and the verdict.
    """
    value = _toml_value(variant.value)
    table, _, key = variant.axis.partition(".")
    return f"""\
# GENERATED by cfbpoll.publish.variants. Do not edit; edit VARIANTS and regenerate.
#
# One knob of configs/default.toml at one setting, with every other constant left
# where the published poll leaves it. This file exists so `cfbpoll rank` can
# produce a run that names the knob it turned. It is scratch: it is not a named
# value system, it is not in configs/recipes/, and it never reaches the roster
# that builds the site's recipe selector.

[recipe]
slug = "{variant.id}"
name = "{variant.axis} = {_jsonable(variant.value)}"
stance = 1
one_liner = "The published poll with {variant.axis} set to {_jsonable(variant.value)}."

manifesto = \"\"\"
A variant, not a recipe. Every constant here is the published poll's except
{variant.axis}, which is {_jsonable(variant.value)} instead of the value
configs/default.toml argues for. There is no case for this setting in this file
and none is implied. The point of moving one constant on its own is that the
ranking it produces can be compared with the published one and the difference
attributed to that constant rather than to a combination, which is what the
agreement block on the published variant document reports.
\"\"\"

tradeoffs = [
{_TRADEOFFS}
]

[{table}]
{key} = {value}
"""


#: What a generated overlay says its costs are. `recipes.load` requires at least
#: one, because a published value system that will not state its own cost is a
#: marketing page. These two are the honest ones for a variant, and they are the
#: same two for all eight because they are properties of BEING a variant rather
#: than of any particular knob.
_VARIANT_TRADEOFFS: tuple[str, ...] = (
    "It is one knob, so it answers one question and no larger one. Whether this "
    "constant matters is not whether the model is right.",
    "It carries no gate verdict and no backtest. The publication gate is written "
    "against the published poll, and nothing here was scored against it.",
)

_TRADEOFFS = "\n".join(f"    {json.dumps(t)}," for t in _VARIANT_TRADEOFFS)


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


def write_overlays(directory: Path, variants: tuple[Variant, ...] = VARIANTS) -> list[Path]:
    """Generate every variant's overlay into `directory`. Returns the paths, sorted.

    Idempotent: the text is a pure function of the `Variant`, so regenerating over
    an existing directory converges rather than accumulating.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for variant in variants:
        path = directory / f"{variant.id}.toml"
        path.write_text(overlay_toml(variant), encoding="utf-8")
        written.append(path)
    return sorted(written)


def variant_dir(dest: Path, season: int, variant_id: str) -> Path:
    """Where one variant's documents land: `<dest>/<season>/variants/<id>/`.

    A sibling of `recipes/` and for the same reason it is a subtree rather than a
    new shape: nothing above it moves, and a site that has never heard of a
    variant keeps reading exactly the paths it read before.
    """
    return Path(dest) / str(season) / "variants" / variant_id


# --------------------------------------------------------------------- the numbers


def house_ranks(dest: Path, season: int, week: int) -> dict[int, int]:
    """`{team_id: rank}` for the published poll of one week, read off the tree.

    READ FROM THE PUBLISHED FIXTURE RATHER THAN RE-RANKED. The house board a
    variant is compared against must be the board the site shows, byte for byte,
    or the agreement statistics describe a comparison no reader can reproduce by
    opening the two documents. It also means the twelve house weeks are ranked
    once, by `make fixtures`, rather than once per variant.
    """
    path = Path(dest) / str(season) / f"week-{week:02d}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist, so there is no published poll to compare a "
            f"variant against. Run `make fixtures` for {season} first: a variant is "
            f"defined as a difference from the house board and cannot be published "
            f"without one."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(row["team_id"]): int(row["rank"]) for row in payload.get("poll") or []}


def agreement(house: dict[int, int], variant: dict[int, int]) -> dict[str, Any]:
    """How far this variant's board is from the house board, and what to call it.

    COMPUTED ON THE WHOLE COMMON BOARD, NOT ON THE FORTY ROWS PUBLISHED. The 0.985
    line is a published standard with a fixed meaning: `scripts/tuning_campaign.py`
    and `scripts/campaign_2.py` both compute tau over every FBS team the two
    orderings share, and ADR 0006 fixed the threshold against sweeps done that way.
    Computing it over a truncated top 40 and then judging it against the same
    number would be a different statistic wearing the same threshold, which is
    exactly the quiet incomparability the recipe contract exists to prevent.
    `n_teams_compared` is published so a page cannot misread which board it is.

    `n_moved_5_or_more` counts teams whose rank changed by at least five places in
    either direction. Tau is a single number about a whole ordering and says
    nothing about whether the movement is spread thin or concentrated; the count
    is the second question, and five places is roughly the width of the rank
    intervals this project publishes, so a team that moved five has moved further
    than its own uncertainty.
    """
    from scipy.stats import kendalltau

    common = sorted(set(house) & set(variant))
    if not common:
        raise ValueError(
            "the house board and the variant board share no team. They are not two "
            "readings of one week and nothing may be computed across them."
        )
    tau = float(kendalltau([house[t] for t in common], [variant[t] for t in common]).statistic)
    moved = sum(1 for t in common if abs(variant[t] - house[t]) >= 5)
    return {
        "kendall_tau_vs_house": tau,
        "n_moved_5_or_more": moved,
        "n_teams_compared": len(common),
        # THE WORD, CHOSEN HERE. Strictly below the floor is a dial; at or above it
        # is a convention. The comparison is the same one ADR 0006 fixed and
        # `scripts/tuning_campaign.py` spells `tau < Q_REF_TAU_FLOOR`.
        "verdict": "dial" if tau < TAU_FLOOR else "convention",
        # Published beside the verdict so the page never has to hold its own copy
        # of the threshold, and so a reader can check the word against the number.
        "tau_floor": TAU_FLOOR,
    }


def document(
    bundle: Any,
    variant: Variant,
    house: dict[int, int],
    top_n: int = TOP_N,
) -> dict[str, Any]:
    """The thin ordering document for one variant of one week.

    `bundle` is what `publish.serving.build` returned for the variant's run. Every
    row value is lifted from `bundle.views["week"]["poll"]`, which is the same
    computation that produced the house week's rows, so the two documents are
    comparable column by column without this module defining a single number of
    its own.
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
        "generator": "cfbpoll publish variants",
        "variant": {
            "id": variant.id,
            "axis": variant.axis,
            "value": _jsonable(variant.value),
            "base": HOUSE_BASE,
            "changes": variant.changes,
            # The hash of the RESOLVED methodology this run used, which is what
            # distinguishes two variants sharing one base config.
            "config_sha256": recipe.get("config_sha256"),
            # THE INTEGRITY BLOCK, IDENTICAL TO THE HOUSE WEEK'S BY CONSTRUCTION,
            # lifted from the same place the house week lifts it. "A variant
            # changes values, never evidence" is a claim, and a claim a reader
            # cannot check is a slogan: these three fields let a page assert it
            # against the house document it is sitting beside.
            "evidence": dict(recipe.get("evidence") or {}),
        },
        "agreement": agreement(house, ranks),
        "rows": rows,
    }


def export(
    run: Path,
    dest: Path,
    variant: Variant,
    archive: Path | None = None,
) -> Path:
    """Publish one variant run as one thin document. Returns the path written.

    NO INDEX IS REBUILT AND NO DIVERGENCE CURVE IS WRITTEN, which is the whole
    difference between this and `publish/fixtures.py`. `index.json` is the POLL's
    index; a variant is not a week of the poll, it publishes no gate, and a retro
    divergence curve for a knob would be a second aggregate nobody asked for.
    """
    from cfbpoll.publish.serving import build

    bundle = build(run, archive=archive, backtest=None)
    house = house_ranks(dest, bundle.season, bundle.week)
    payload = document(bundle, variant, house)
    path = variant_dir(dest, bundle.season, variant.id) / f"week-{bundle.week:02d}.json"
    _dump(path, payload)
    return path
