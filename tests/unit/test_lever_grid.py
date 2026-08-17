"""The lever grid: the addressing rule, the withheld verdict, and the eleven anchors.

WHAT THESE TESTS ARE FOR. The grid makes three claims a reader cannot check
without re-running seventy-two fits, so they are checked here instead:

  1. THE ID IS THE ADDRESS. A panel composes `c-32-bw-7-odds` from three slider
     positions and fetches that path. If the id were ever not a pure function of
     the detents, the page would fetch a board the reader did not ask for and
     nothing downstream would notice, because every cell is a valid board.

  2. THE VERDICT IS WITHHELD WHERE IT CANNOT MEAN ANYTHING. `dial` and
     `convention` are a labelling standard ADR 0006 fixed against ONE-KNOB sweeps.
     A two-knob cell has a tau attributable to neither constant, so the word is
     `None` there, and a page that rendered `None` as "convention" would report a
     finding of no effect that nobody made.

  3. ELEVEN CELLS ARE ALREADY-PUBLISHED BOARDS UNDER ANOTHER NAME. The published
     poll, both alternate recipes and all eight playground variants sit at
     constants that are also grid cells. Here the CONSTANTS are checked to resolve
     identically through the real merge; `scripts/check_lever_grid.py` is what
     checks the published rows against each other once the grid exists.

Everything runs against a hand-built bundle and a hand-built fixture tree, so the
suite stays offline and fast. The one thing that cannot be faked, that the
seventy-two overlays resolve to the seventy-two intended methodologies, is checked
against the real `configs/default.toml`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from cfbpoll import levers, recipes
from cfbpoll.config import load_config
from cfbpoll.publish import lever_grid as grid
from cfbpoll.publish import variants
from cfbpoll.publish.serving import Bundle

# --------------------------------------------------------------------- fixtures


def _row(team_id: int, rank: int, **over: Any) -> dict[str, Any]:
    base = {
        "team_id": team_id,
        "rank": rank,
        "team": f"Team {team_id}",
        "one_in": 100 + rank,
        "odds_key": 3.2381094567,
        "resume": 60.0,
        "resume_margin": 39.4137254321,
        "power": 31.8068791234,
        "power_rank": rank,
        "gap": 28.1931214567,
        "rank_lo90": max(1, rank - 2),
        "rank_hi90": rank + 5,
        # Columns a week document carries and a cell document must not.
        "logo_url": "https://example.invalid/logo.png",
        "conference": "Big Ten",
        "wins": 12,
        "losses": 1,
        "tail_p": 0.0005,
    }
    base.update(over)
    return base


def _bundle(cell_id: str, n: int = 60, season: int = 2025, week: int = 16) -> Bundle:
    poll = [_row(team_id=100 + i, rank=i + 1) for i in range(n)]
    return Bundle(
        season=season,
        week=week,
        season_type="regular",
        run_id="00000000-0000-0000-0000-000000000000",
        views={
            "week": {
                "poll": poll,
                "recipe": {
                    "slug": cell_id,
                    "is_house": False,
                    "config_sha256": "c0ffee" * 10,
                    "evidence": {
                        "archive_manifest_sha256": "manifest:abc",
                        "fit_window_sha256": "def",
                        "n_games_in_fit": 1637,
                    },
                },
            }
        },
        recipe={"slug": cell_id, "is_house": False},
    )


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    dest = tmp_path / "cfb-poll-data"
    (dest / "2025").mkdir(parents=True)
    (dest / "2025" / "week-16.json").write_text(
        json.dumps(
            {
                "season": 2025,
                "week": 16,
                "poll": [_row(team_id=100 + i, rank=i + 1) for i in range(60)],
            }
        ),
        encoding="utf-8",
    )
    return dest


def _flat(mapping: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flat(value, f"{dotted}."))
        else:
            out[dotted] = value
    return out


# ------------------------------------------------------------------- the shape


def test_the_grid_is_six_by_four_by_three_and_every_id_is_unique() -> None:
    assert [len(axis.detents) for axis in grid.AXES] == [6, 4, 3]
    assert len(grid.CELLS) == 72
    assert len({cell.id for cell in grid.CELLS}) == 72


def test_every_id_is_a_path_segment_and_a_url_segment() -> None:
    for cell in grid.CELLS:
        assert cell.id == cell.id.lower()
        assert all(ch.isalnum() or ch == "-" for ch in cell.id), cell.id


def test_the_id_is_a_pure_function_of_the_three_slugs() -> None:
    """The addressing rule the site relies on. Section 6 of the contract."""
    for cell in grid.CELLS:
        slugs = cell.slugs
        composed = "-".join(
            f"{axis.slug_prefix}-{slugs[axis.key]}" if axis.slug_prefix else slugs[axis.key]
            for axis in grid.AXES
        )
        assert cell.id == composed
        assert grid.by_id(cell.id) is cell


def test_exactly_one_cell_is_the_published_poll() -> None:
    published = [cell for cell in grid.CELLS if cell.is_published]
    assert published == [grid.published_cell()]
    assert grid.published_cell().id == "c-32-bw-7-odds"
    assert grid.published_cell().changes == {}


def test_every_axis_contains_the_house_value_a_reader_started_from() -> None:
    """A grid that cannot show a reader where they started is not a grid."""
    base = load_config()
    for axis in grid.AXES:
        assert axis.house in [d.value for d in axis.detents], axis.key
        assert base[axis.table][axis.field] == axis.house, axis.key


def test_every_axis_is_a_registered_lever_and_the_prose_is_lifted_not_rewritten() -> None:
    """The panel and `cfbpoll levers` must say the same sentence about one knob."""
    for axis in grid.AXES:
        lever = levers.get(axis.key)
        assert axis.registry() is lever
        assert lever.label and lever.plain and lever.evidence


def test_the_detent_sets_are_the_ones_the_contract_argues_for() -> None:
    """Pinned, because a detent nobody can cite is a board no document explains.

    The citations are the table in section 2 of docs/fixture-contract-levers.md.
    `margin.c = 8` is deliberately absent: nothing in this repository argues for it.
    """
    published = {axis.key: [d.published_value for d in axis.detents] for axis in grid.AXES}
    assert published == {
        "margin.c": [1.0, 18.0, 24.0, 32.0, 48.0, "uncapped"],
        "margin.beta_w": [0.0, 3.0, 7.0, 12.0],
        "publication.headline_ordering": ["schedule_odds", "L4_resume", "L4_resume_margin"],
    }


def test_every_axis_is_exactly_the_registrys_own_published_choices() -> None:
    """AGREEMENT, ASSERTED. This test used to pin a disagreement.

    `Lever.sweep` promises "the values the site may offer without a refit" and
    `Lever.values` is a categorical lever's whole domain. Since this grid exists,
    that promise is a claim about files on disk: every value the registry offers
    has a precomputed board behind it, and every board has a registry entry that
    says a reader may ask for it. If the two sets ever diverge, one of them is
    lying to a panel - either a slider position with no file behind it, or a file
    no reader is allowed to reach.

    Both halves were ruled into agreement by the orchestrator on John's
    delegation, 2026-08-17: `margin.c`'s floor moved to 1.0 to admit `just-win`,
    and the ordering lever became all three legal strings to admit `full-merit`.
    """
    for axis in grid.AXES:
        assert tuple(d.value for d in axis.detents) == axis.registry().choices, axis.key


def test_the_ordering_axis_is_the_registrys_three_strings_and_the_configs(
) -> None:
    """One set of three orderings, named identically in three places."""
    from cfbpoll.publish.poll import ORDERING_LAYER

    lever = levers.get("publication.headline_ordering")
    assert lever.is_categorical
    assert {d.value for d in grid.AXES[2].detents} == set(ORDERING_LAYER)
    assert tuple(d.value for d in grid.AXES[2].detents) == lever.values
    assert lever.default == grid.AXES[2].house


def test_the_c_axis_floor_is_the_recipe_this_project_ships() -> None:
    """`just-win` ships at c = 1.0, the registry's floor is 1.0, and so is the grid's.

    Before the 2026-08-17 ruling the registry's floor was 18 and this test pinned
    the disagreement so it could not vanish quietly. It now asserts the agreement,
    for the same reason: three files have to keep saying the same number.
    """
    assert levers.get("margin.c").low == 1.0
    assert min(d.value for d in grid.AXES[0].detents) == 1.0
    shipped, _ = recipes.resolve("just-win")
    assert shipped["margin"]["c"] == 1.0


def test_every_grid_default_is_the_registrys_shipped_value() -> None:
    """The house cell must be the board `levers.defaults()` describes.

    This is only checkable now that a categorical lever publishes its string:
    while the ordering was encoded `1.0`, `defaults()` carried a number the config
    has never held and there was nothing to compare.
    """
    shipped = levers.defaults()
    for axis in grid.AXES:
        assert shipped[axis.key] == axis.house, axis.key
    assert grid.published_cell().settings == {a.key: a.house for a in grid.AXES}


# ------------------------------------------------------------------ the overlays


def test_every_cell_resolves_to_its_three_constants_and_moves_nothing_else(
    tmp_path: Path,
) -> None:
    """The whole grid, checked against the real default config through the real merge."""
    overlays = tmp_path / "overlays"
    assert len(grid.write_overlays(overlays)) == 72
    base = load_config()
    flat_base = _flat(base)

    for cell in grid.CELLS:
        cfg, recipe = recipes.resolve(cell.id, directory=overlays)
        assert recipe.slug == cell.id
        assert recipe.is_house is False
        for axis, detent in zip(grid.AXES, cell.detents, strict=True):
            got = cfg[axis.table][axis.field]
            assert got == detent.value or (
                isinstance(got, float)
                and isinstance(detent.value, float)
                and math.isinf(got)
                and math.isinf(detent.value)
            )
        moved = {k for k in flat_base if _flat(cfg).get(k) != flat_base.get(k)}
        # `headline_layer` is DERIVED from `headline_ordering` by `resolve` and is
        # not a fourth knob; publish/poll.py asserts the two agree on every run.
        assert moved <= set(cell.changes) | {"publication.headline_layer"}, (cell.id, moved)


def test_a_grid_cell_may_not_move_evidence(tmp_path: Path) -> None:
    overlays = tmp_path / "overlays"
    grid.write_overlays(overlays)
    for cell in grid.CELLS:
        recipes.assert_values_only(recipes.load(cell.id, directory=overlays).overrides, cell.id)


def test_generated_overlays_never_enter_the_published_roster(tmp_path: Path) -> None:
    grid.write_overlays(tmp_path / "overlays")
    assert [r["slug"] for r in recipes.roster()] == ["full-merit", "house", "just-win"]


def test_write_overlays_is_idempotent(tmp_path: Path) -> None:
    first = {p.name: p.read_bytes() for p in grid.write_overlays(tmp_path / "o")}
    second = {p.name: p.read_bytes() for p in grid.write_overlays(tmp_path / "o")}
    assert first == second


def test_uncapped_is_spelled_inf_in_the_toml_and_uncapped_everywhere_else(
    tmp_path: Path,
) -> None:
    """JSON has no infinity and `c = inf` is a real setting, not a missing one."""
    cell = grid.by_id("c-uncapped-bw-7-odds")
    assert "c = inf" in grid.overlay_toml(cell)
    assert cell.published_settings["margin.c"] == "uncapped"
    assert cell.changes["margin.c"] == "uncapped"
    overlays = tmp_path / "overlays"
    grid.write_overlays(overlays)
    cfg, _ = recipes.resolve(cell.id, directory=overlays)
    assert math.isinf(cfg["margin"]["c"])


# ------------------------------------------------------------- the eleven anchors


def test_eleven_cells_reproduce_an_already_published_board() -> None:
    labelled = {
        cell.id: grid.equivalent_to(cell, 2025, 16)
        for cell in grid.CELLS
        if grid.equivalent_to(cell, 2025, 16)
    }
    kinds: dict[str, int] = {}
    for entry in labelled.values():
        kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
    assert kinds == {"house": 1, "recipe": 2, "variant": 8}
    assert labelled["c-32-bw-7-odds"]["path"] == "2025/week-16.json"
    assert labelled["c-1-bw-7-resume"]["id"] == "just-win"
    assert labelled["c-uncapped-bw-12-resume-margin"]["id"] == "full-merit"
    # Every shipped playground variant is an edge of this grid, which is what makes
    # the grid checkable against something already on disk.
    assert {e["id"] for e in labelled.values() if e["kind"] == "variant"} == {
        v.id for v in variants.VARIANTS
    }


def test_an_anchor_cell_resolves_to_a_byte_identical_methodology(tmp_path: Path) -> None:
    """The claim `equivalent_to` makes, at the level of the resolved config.

    If these hashes ever diverge the two boards diverge, and a panel would be
    labelling a grid cell `Just Win` while showing a different ranking.
    """
    overlays = tmp_path / "overlays"
    grid.write_overlays(overlays)
    for cell_id, slug in [
        ("c-32-bw-7-odds", "house"),
        ("c-1-bw-7-resume", "just-win"),
        ("c-uncapped-bw-12-resume-margin", "full-merit"),
    ]:
        ours, _ = recipes.resolve(cell_id, directory=overlays)
        theirs, _ = recipes.resolve(slug)
        assert recipes.resolved_hash(ours) == recipes.resolved_hash(theirs), cell_id


# -------------------------------------------------------------- the agreement block


def _ranks(n: int = 60) -> dict[int, int]:
    return {100 + i: i + 1 for i in range(n)}


def test_the_house_cell_agrees_with_itself_and_is_owed_no_verdict() -> None:
    house = _ranks()
    got = grid.agreement(house, house, grid.published_cell())
    assert got["kendall_tau_vs_house"] == pytest.approx(1.0)
    assert got["n_knobs_moved"] == 0
    assert got["verdict"] is None


def test_a_one_knob_cell_carries_the_playgrounds_own_verdict() -> None:
    """Same tau, same threshold, same word, computed by the same function."""
    house = _ranks()
    moved = dict(house)
    moved[100], moved[101] = house[101], house[100]
    cell = grid.by_id("c-1-bw-7-odds")
    assert cell.n_knobs_moved == 1
    ours = grid.agreement(house, moved, cell)
    theirs = variants.agreement(house, moved)
    assert ours["kendall_tau_vs_house"] == theirs["kendall_tau_vs_house"]
    assert ours["n_moved_5_or_more"] == theirs["n_moved_5_or_more"]
    assert ours["verdict"] == theirs["verdict"]
    assert ours["tau_floor"] == variants.TAU_FLOOR


@pytest.mark.parametrize("cell_id", ["c-1-bw-7-resume", "c-uncapped-bw-12-resume-margin"])
def test_a_multi_knob_cell_publishes_the_tau_and_withholds_the_word(cell_id: str) -> None:
    """ADR 0006 fixed `dial` against one-knob sweeps and it stays that way.

    The number is still published, because "how different is this board" is a fair
    question at any number of knobs. It is the WORD that is unattributable.
    """
    house = _ranks()
    moved = {team: (rank + 7) % 60 + 1 for team, rank in house.items()}
    cell = grid.by_id(cell_id)
    assert cell.n_knobs_moved >= 2
    got = grid.agreement(house, moved, cell)
    assert got["verdict"] is None
    assert got["kendall_tau_vs_house"] < 1.0
    assert got["n_teams_compared"] == 60
    assert got["tau_floor"] == variants.TAU_FLOOR


# ---------------------------------------------------------------- the document


def test_the_document_carries_the_contract_and_nothing_else(tree: Path) -> None:
    cell = grid.by_id("c-1-bw-7-resume")
    doc = grid.document(_bundle(cell.id), cell, grid.house_ranks(tree, 2025, 16))
    assert set(doc) == {
        "schema_version",
        "season",
        "week",
        "season_type",
        "generator",
        "cell",
        "agreement",
        "rows",
    }
    assert doc["schema_version"] == grid.SCHEMA_VERSION
    assert doc["generator"] == "cfbpoll publish lever-grid"
    assert set(doc["cell"]) == {"id", "base", "detents", "changes", "config_sha256", "evidence"}
    assert doc["cell"]["base"] == grid.HOUSE_BASE
    # `detents` positions the sliders, `changes` is what the page says changed.
    assert doc["cell"]["detents"] == {
        "margin.c": 1.0,
        "margin.beta_w": 7.0,
        "publication.headline_ordering": "L4_resume",
    }
    assert doc["cell"]["changes"] == {
        "margin.c": 1.0,
        "publication.headline_ordering": "L4_resume",
    }


def test_the_rows_are_the_top_forty_in_rank_order_with_eleven_columns(tree: Path) -> None:
    cell = grid.by_id("c-18-bw-3-odds")
    doc = grid.document(_bundle(cell.id), cell, grid.house_ranks(tree, 2025, 16))
    assert len(doc["rows"]) == variants.TOP_N
    assert [r["rank"] for r in doc["rows"]] == list(range(1, variants.TOP_N + 1))
    for row in doc["rows"]:
        assert tuple(row) == variants.ROW_FIELDS
    # No display fields. A page joins on team_id against the week document it
    # already has open rather than reading a second copy of a mark.
    assert "logo_url" not in doc["rows"][0]


def test_the_evidence_block_is_the_house_weeks_and_is_not_recomputed(tree: Path) -> None:
    cell = grid.by_id("c-48-bw-12-resume")
    doc = grid.document(_bundle(cell.id), cell, grid.house_ranks(tree, 2025, 16))
    assert doc["cell"]["evidence"] == {
        "archive_manifest_sha256": "manifest:abc",
        "fit_window_sha256": "def",
        "n_games_in_fit": 1637,
    }


def test_publishing_the_same_run_twice_is_byte_identical(tree: Path) -> None:
    """Determinism is a feature, and it has to hold on the writing end too."""
    cell = grid.by_id("c-24-bw-0-resume-margin")
    house = grid.house_ranks(tree, 2025, 16)
    first = grid.document(_bundle(cell.id), cell, house)
    second = grid.document(_bundle(cell.id), cell, house)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_a_cell_cannot_be_published_without_the_house_week_to_compare_against(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="make fixtures"):
        grid.house_ranks(tmp_path, 2025, 16)


# ----------------------------------------------------------------- the manifest


def _publish_whole_grid(tree: Path, weeks: tuple[int, ...] = (16,)) -> None:
    for cell in grid.CELLS:
        for week in weeks:
            doc = grid.document(
                _bundle(cell.id, week=week), cell, grid.house_ranks(tree, 2025, week)
            )
            path = grid.cell_dir(tree, 2025, cell.id) / f"week-{week:02d}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")


def test_the_manifest_names_every_cell_its_detents_its_file_and_the_poll(tree: Path) -> None:
    _publish_whole_grid(tree)
    man = grid.manifest(tree, 2025)
    assert man["schema_version"] == grid.SCHEMA_VERSION
    assert man["n_cells"] == 72
    assert man["weeks"] == [16]
    assert man["top_n"] == variants.TOP_N
    assert man["tau_floor"] == variants.TAU_FLOOR
    assert man["published"]["cell_id"] == "c-32-bw-7-odds"
    assert len(man["cells"]) == 72
    assert [c["id"] for c in man["cells"] if c["is_published"]] == ["c-32-bw-7-odds"]
    for entry in man["cells"]:
        rel = entry["files"]["16"]
        assert rel == f"lever-grid/{entry['id']}/week-16.json"
        assert (tree / "2025" / rel).exists()
    assert [a["key"] for a in man["axes"]] == [axis.key for axis in grid.AXES]
    assert man["axes"][0]["label"] == levers.get("margin.c").label
    defaults = [d["value"] for a in man["axes"] for d in a["detents"] if d["default"]]
    assert defaults == [32.0, 7.0, "schedule_odds"]


def test_a_partial_grid_produces_no_manifest_rather_than_one_that_404s(tree: Path) -> None:
    """A panel cannot tell a missing file from a network fault, so it never sees one."""
    _publish_whole_grid(tree)
    (grid.cell_dir(tree, 2025, "c-48-bw-3-resume") / "week-16.json").unlink()
    with pytest.raises(FileNotFoundError, match="no complete week"):
        grid.manifest(tree, 2025)


def test_the_grid_subtree_is_a_sibling_of_variants_and_moves_nothing(tree: Path) -> None:
    _publish_whole_grid(tree)
    grid.write_manifest(tree, 2025)
    season = tree / "2025"
    assert (season / "lever-grid" / "manifest.json").exists()
    assert (season / "week-16.json").exists()
    # index.json is not this feature's business: a grid cell is not a recipe and
    # never enters the roster.
    assert not (tree / "index.json").exists()
    assert sorted(p.name for p in season.iterdir()) == ["lever-grid", "week-16.json"]
