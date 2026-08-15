"""Recipes — the named value systems the poll can be read under.

A ranking is a value system. It is not a fact about football, it is an argument
about what football results are FOR, and every constant in `configs/default.toml`
is a sentence in that argument. This module makes the argument selectable: three
named stances, each a complete methodology, each computable from the same
evidence, each published with the case for it and the bill for it.

THE AXIS THE THREE RECIPES SPAN, in the project owner's words:

    One end is fully meritocratic. Best team wins, we measure as fairly as we
    can, nothing else matters, and margin counts for exactly what it is worth.
    The other end protects sportsmanship, because if point differential pays,
    teams WILL run up the score on an overmatched opponent. Everyone has seen
    it. But ignoring margin entirely throws away the information in a 70 point
    win against a 1 point win, and that information is real.

`full-merit` is the first end. `just-win` is the second. `house` is the poll this
project publishes, which sits between them on purpose and pays for the position.

THE ONE RULE THAT MAKES THIS HONEST RATHER THAN A TOY: a recipe changes VALUES,
never EVIDENCE. Every recipe reads the same archive, the same window, the same
walk-forward slicing, and passes the same leakage audit. Nothing in
`EVIDENCE_KEYS` below may appear in a recipe file, and `assert_values_only`
refuses the file if it does — so "same data, different values" is enforced at
load time rather than promised in a paragraph. `tests/unit/test_recipes.py`
proves the consequence directly: it digests the ingested frames under all three
and asserts the bytes are identical.

WHY THE FILES ARE DIFFS AND THE RESOLVED CONFIG IS WHOLE. A recipe file carries a
`[recipe]` block and ONLY the constants it changes, exactly like
`configs/challengers/`. It is resolved through `config.merge_overlay`, which
REFUSES a key `configs/default.toml` does not define, so a typo cannot silently
produce a finding about a model nobody ran. What a run then publishes is the
RESOLVED config in full, hashed, on `_run.json` — because constraint 5 says the
config is the methodology, and a methodology that a reader has to reconstruct by
applying a diff in their head is not published. Diff on disk so it cannot drift
from the default; whole on the artifact so it cannot be misread.

THE HOUSE RECIPE OVERRIDES NOTHING, and that is the strongest available statement
that the published poll is unaffected by the existence of the others.
`house.toml` carries a `[recipe]` block and not one constant, so
`resolve("house")` is `configs/default.toml` byte for byte and
`test_the_house_recipe_is_the_default_config` asserts it.
"""

from __future__ import annotations

import hashlib
import json
import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cfbpoll.config import DEFAULT_CONFIG_PATH, REPO_ROOT, load_config, merge_overlay

__all__ = [
    "EVIDENCE_KEYS",
    "HOUSE",
    "Recipe",
    "RECIPES_DIR",
    "RecipeError",
    "assert_values_only",
    "available",
    "load",
    "resolve",
    "resolved_hash",
    "roster",
    "slugs",
]

#: Where the recipe files live.
RECIPES_DIR = REPO_ROOT / "configs" / "recipes"

#: The recipe the site serves by default and the only one this project PUBLISHES
#: as its poll. Every other recipe is an alternate lens and is labelled as one on
#: every artifact it touches.
HOUSE = "house"

#: The label an alternate lens carries, everywhere, in the same words. Kept here
#: rather than in the site so both publication targets and the share cards print
#: identical characters (report 05 §7.2).
ALTERNATE_LABEL = "ALTERNATE LENS. Not the published poll."

#: CONFIG KEYS A RECIPE MAY NEVER TOUCH, as `dotted.path` strings, because they
#: decide what EVIDENCE the model sees rather than what the model VALUES.
#:
#: This list is the whole integrity claim in machine-readable form. A recipe that
#: could move `[model].fit_universe` would be reading a different set of games; a
#: recipe that could move `[backtest].walk_forward_strict` or `[ep].fit_scope`
#: would be reading games from the future; a recipe that could move
#: `[constraints]` would be reading banned columns. None of those is a value
#: judgement about football and every one of them would make two recipes
#: incomparable, which is precisely what a side-by-side page must not do.
#:
#: `[weights]` is here for a reason worth stating, because it looks like a value
#: and is not. The non-CFP bowl weight is 0.25 because 78+ opt-outs and 431
#: portal entries hit the 2021-22 postseason and FSU lost 33 players before the
#: 2023 Orange Bowl (report 02 §3.8). That is a statement about how well a game
#: MEASURES a team, which is evidence quality, and it is the same statement under
#: every value system. Recipes disagree about what to do with a measurement. They
#: do not get to disagree about how good it is.
EVIDENCE_KEYS: tuple[str, ...] = (
    "backtest.first_eval_week",
    "backtest.holdout_locked",
    "backtest.holdout_seasons",
    "backtest.tune_seasons",
    "backtest.universe",
    "backtest.validate_seasons",
    "backtest.walk_forward_strict",
    "constraints",
    "ep.fit_scope",
    "ep.frozen_seasons",
    "fcs",
    "homefield.anchor_h_by_season",
    "homefield.anchor_provenance",
    "meta.frozen",
    "model.fit_universe",
    "weights",
)


class RecipeError(ValueError):
    """A recipe file is not a recipe.

    Its own type because every way of failing here is a content error a human has
    to fix in a TOML file, never a bug in a caller.
    """


@dataclass(frozen=True)
class Recipe:
    """One named value system: who it is for, what it costs, and what it sets."""

    slug: str
    name: str
    one_liner: str
    manifesto: str
    tradeoffs: tuple[str, ...]
    #: Position on the merit-to-sportsmanship axis, for ordering the selector.
    #: 0 is fully meritocratic, 1 is the house, 2 protects sportsmanship. It
    #: decides display order and nothing else; no number reads it.
    stance: int
    overrides: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    @property
    def is_house(self) -> bool:
        return self.slug == HOUSE

    def flat_overrides(self) -> dict[str, Any]:
        """`{"margin.c": "uncapped", "publication.headline_ordering": "..."}`.

        Flattened and JSON-safe, because this is what a page prints under "what
        this recipe changes" and a reader should see the dotted key exactly as it
        appears in `configs/default.toml`.
        """
        return {k: _jsonable(v) for k, v in sorted(_flatten(self.overrides).items())}

    def as_dict(self) -> dict[str, Any]:
        """The published recipe block. Same object on model_params.json, on
        poll.json and in the fixture set, so no surface can describe a recipe
        differently from another (report 05 §7.2)."""
        return {
            "slug": self.slug,
            "name": self.name,
            "one_liner": self.one_liner,
            "manifesto": self.manifesto,
            "tradeoffs": list(self.tradeoffs),
            "stance": self.stance,
            "is_house": self.is_house,
            "label": None if self.is_house else ALTERNATE_LABEL,
            "changes": self.flat_overrides(),
            "source": (None if self.path is None else _source_path(self.path)),
        }


# --------------------------------------------------------------------------- helpers


def _source_path(path: Path) -> str:
    """The recipe file, repo-relative when it lives in the repo.

    A hand-written recipe is `configs/recipes/full-merit.toml` and always will be.
    A generated variant overlay lives in scratch, which is normally `.cache/` —
    inside the repo — but need not be, and `relative_to` raises rather than
    falling back. The published string is for a reader to find the file with, so
    an absolute path is a worse answer than a relative one and a crash is a worse
    answer than either.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _flatten(mapping: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, f"{dotted}."))
        else:
            out[dotted] = value
    return out


def _jsonable(value: Any) -> Any:
    """JSON cannot carry infinity and neither can a fixture file.

    `[margin].c = inf` is A REAL VALUE OF THE PARAMETER — the member of the tanh
    family that does not compress at all, which campaign 2 pre-registered and
    searched (docs/analysis/campaign-2.md, lead 1). It is published by the name
    campaign 2 gave it rather than dropped, because a constant that vanishes from
    `model_params.json` when it happens to be infinite is a transparency failure
    on exactly the recipe whose whole argument is that constant.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return "uncapped" if value > 0 else "-uncapped"
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def assert_values_only(overrides: dict[str, Any], slug: str) -> None:
    """Refuse a recipe that moves EVIDENCE rather than VALUES. See `EVIDENCE_KEYS`.

    Checked at load time, before any fit, so a recipe that would make the
    side-by-side comparison meaningless cannot be run at all — never mind
    published. A prefix match is deliberate: naming `constraints` blocks every key
    under it, so a future key added to that table is protected the day it is added
    rather than the day somebody remembers to add it here.
    """
    flat = _flatten(overrides)
    bad = sorted(
        key
        for key in flat
        if any(key == locked or key.startswith(f"{locked}.") for locked in EVIDENCE_KEYS)
    )
    if bad:
        raise RecipeError(
            f"recipe {slug!r} sets {bad}, which decides what EVIDENCE the model "
            f"sees rather than what it VALUES. A recipe changes values, never "
            f"evidence: every recipe must read the same games, through the same "
            f"walk-forward window, under the same constraints, or the side-by-side "
            f"comparison is between two different measurements and means nothing. "
            f"See EVIDENCE_KEYS in src/cfbpoll/recipes.py."
        )


def _require(block: dict[str, Any], key: str, path: Path) -> Any:
    if key not in block or block[key] in (None, "", []):
        raise RecipeError(
            f"{path}: [recipe] is missing {key!r}. Every recipe publishes its name, "
            f"its one-line summary, its manifesto and at least one honest tradeoff. "
            f"A value system that will not state its own cost is a marketing page."
        )
    return block[key]


# ----------------------------------------------------------------------------- load


def slugs() -> tuple[str, ...]:
    """Every recipe on disk, house first, then merit-to-sportsmanship order."""
    return tuple(r.slug for r in available())


def available(directory: Path | None = None) -> tuple[Recipe, ...]:
    """Every recipe in `configs/recipes/`, in display order.

    Display order is `stance`, so the selector reads left to right along the axis
    the recipes exist to span rather than alphabetically, which would put the
    house poll first and imply the other two are footnotes.

    `directory` DEFAULTS TO `configs/recipes/` AND `roster()` NEVER PASSES IT, so
    the published selector shows the three named value systems and nothing else no
    matter what other overlay directories exist on the machine. See `load`.
    """
    root = Path(directory) if directory is not None else RECIPES_DIR
    if not root.is_dir():
        return ()
    found = [load(path.stem, directory=root) for path in sorted(root.glob("*.toml"))]
    return tuple(sorted(found, key=lambda r: (r.stance, r.slug)))


def load(slug: str, directory: Path | None = None) -> Recipe:
    """Parse one recipe file. Raises `RecipeError` on anything a human must fix.

    `directory` OVERRIDES WHERE THE FILE IS LOOKED UP, and exists for the variants
    playground (`publish/variants.py`), which generates one overlay per knob
    setting into scratch and needs `cfbpoll rank` to produce artifacts that name
    the knob rather than claiming to be the house poll. Everything else about a
    recipe still applies to those files: `assert_values_only` refuses one that
    moves evidence, and `merge_overlay` refuses a key the default config does not
    define, so a generated overlay is held to exactly the rules a hand-written one
    is. What `directory` does NOT do is enter the roster: `roster()` and the
    zero-argument `available()` read `configs/recipes/` only, so a scratch overlay
    can never reach the site's selector or `index.json`.
    """
    root = Path(directory) if directory is not None else RECIPES_DIR
    path = root / f"{slug}.toml"
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in root.glob("*.toml"))) or "none"
        raise RecipeError(f"no recipe {slug!r} in {root}. Available: {known}.")
    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    block = raw.pop("recipe", None)
    if not isinstance(block, dict):
        raise RecipeError(
            f"{path}: no [recipe] block. A recipe file is a `[recipe]` block plus "
            f"ONLY the constants it changes from configs/default.toml."
        )
    declared = str(block.get("slug", slug))
    if declared != slug:
        raise RecipeError(
            f"{path}: [recipe].slug is {declared!r} but the filename says {slug!r}. "
            f"The filename is the identifier every URL and every artifact carries."
        )
    tradeoffs = tuple(str(t).strip() for t in _require(block, "tradeoffs", path))
    assert_values_only(raw, slug)
    if slug == HOUSE and raw:
        raise RecipeError(
            f"{path}: the house recipe must override NOTHING. It is "
            f"configs/default.toml, which is what makes 'the published poll is "
            f"unaffected by the other recipes' a fact about the files rather than "
            f"a claim in a paragraph. Found: {sorted(_flatten(raw))}."
        )
    return Recipe(
        slug=slug,
        name=str(_require(block, "name", path)),
        one_liner=str(_require(block, "one_liner", path)).strip(),
        manifesto=" ".join(str(_require(block, "manifesto", path)).split()),
        tradeoffs=tradeoffs,
        stance=int(_require(block, "stance", path)),
        overrides=raw,
        path=path,
    )


def resolve(
    slug: str,
    base: Path | dict[str, Any] | None = None,
    directory: Path | None = None,
) -> tuple[dict[str, Any], Recipe]:
    """`(resolved config, recipe)`. The one place a recipe becomes a methodology.

    `base` defaults to `configs/default.toml`. Merging goes through
    `config.merge_overlay`, so a key the base config does not define is REFUSED
    rather than accepted, and a recipe that misspells `beta_w` fails loudly
    instead of publishing a poll under constants nobody set.

    `directory` is passed straight to `load`; see its docstring.
    """
    recipe = load(slug, directory=directory)
    if isinstance(base, dict):
        config = base
    else:
        config = load_config(base or DEFAULT_CONFIG_PATH)
    if not recipe.overrides:
        return config, recipe
    merged = merge_overlay(config, recipe.overrides)
    # `[publication].headline_layer` is a DERIVED display string and the two names
    # are asserted to agree on every run (publish/poll.headline_ordering). A
    # recipe that moves the ordering and not the layer would fail that assertion
    # from inside a fit, six frames deep, so it is derived here instead and a
    # recipe that states both inconsistently is caught by the same assertion at
    # the top of the run.
    from cfbpoll.publish.poll import ORDERING_LAYER

    ordering = str(merged["publication"]["headline_ordering"])
    if ordering in ORDERING_LAYER and "headline_layer" not in _flatten(recipe.overrides):
        merged["publication"] = {
            **merged["publication"],
            "headline_layer": ORDERING_LAYER[ordering],
        }
    return merged, recipe


def resolved_hash(config: dict[str, Any]) -> str:
    """sha256 of a RESOLVED config, for `_run.json`.

    `config.config_hash` hashes file bytes, which is the right answer when a run
    is one file and no answer at all when it is a file plus a diff. This hashes
    the merged methodology itself, canonically (sorted keys, infinities named), so
    two runs agree on the hash if and only if they agree on every constant —
    which is the property `_run.json` exists to give a reader.
    """
    payload = json.dumps(_jsonable(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def roster() -> list[dict[str, Any]]:
    """The published recipe roster: what a selector needs, without opening a week.

    Written into `index.json` by `publish fixtures` (see
    docs/fixture-contract-recipes.md), so the site can build the picker from one
    document and never has to guess which recipes a season carries.
    """
    return [{**r.as_dict(), "default": r.is_house} for r in available()]
