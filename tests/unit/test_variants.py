"""The knob playground: the document, the arithmetic, and the two rules.

WHAT THESE TESTS ARE FOR. A variant document makes two claims a reader cannot
check for themselves without re-running the model, so both are checked here
instead:

  1. THE VERDICT IS THE PROJECT'S OWN RULE, APPLIED. `agreement.verdict` prints
     the word "dial" or "convention" against the 0.985 Kendall's tau line ADR
     0006 fixed. A page that showed the word without the pipeline having computed
     it, or a pipeline that used a different threshold from the campaign
     documents, would publish two definitions of "dial" with no way to tell which
     one a reader saw. So the tau is checked against a hand-computed value, the
     threshold against `scripts/tuning_campaign.py`'s copy, and the boundary is
     pinned on both sides.

  2. A VARIANT CHANGES VALUES, NEVER EVIDENCE. Same rule as a recipe, same
     enforcement, and here it is checked as a property of the generated overlays
     rather than trusted: every one of the eight is refused if it names an
     evidence key, none of them is a no-op, and the three-digest evidence block a
     variant publishes is asserted equal to the house week's.

Everything runs against a hand-built bundle and a hand-built fixture tree, so the
suite stays offline and fast. The one thing that cannot be faked - that the eight
overlays resolve to the eight intended constants through the real merge - is
checked against the real `configs/default.toml`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from cfbpoll import recipes
from cfbpoll.config import load_config
from cfbpoll.publish import variants
from cfbpoll.publish.serving import Bundle

# --------------------------------------------------------------------- fixtures


def _row(team_id: int, rank: int, **over: Any) -> dict[str, Any]:
    """A poll row with every column `ROW_FIELDS` reads, plus the ones it ignores.

    The extra columns are the point: a variant row is a PROJECTION of a poll row,
    and a test whose input carried only the eleven published fields would not
    notice the projection quietly widening.
    """
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
        # Columns a week document carries and a variant document must not.
        "logo_url": "https://example.invalid/logo.png",
        "mark_bg": "#123456",
        "conference": "Big Ten",
        "wins": 12,
        "losses": 1,
        "tail_p": 0.0005,
        "hindsight_rank": rank,
        "rank_delta": 0,
    }
    base.update(over)
    return base


def _bundle(n: int = 60, season: int = 2025, week: int = 16) -> Bundle:
    """A bundle shaped exactly like `serving.build`'s, with `n` ranked teams."""
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
                    "slug": "margin-beta-w-0",
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
        recipe={"slug": "margin-beta-w-0", "is_house": False},
    )


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A destination tree holding one published house week, and nothing else."""
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


# ------------------------------------------------------------- the eight variants


def test_there_are_eight_variants_on_three_axes_and_every_id_is_a_path_segment() -> None:
    assert len(variants.VARIANTS) == 8
    assert len({v.id for v in variants.VARIANTS}) == 8
    axes: dict[str, int] = {}
    for v in variants.VARIANTS:
        axes[v.axis] = axes.get(v.axis, 0) + 1
    assert axes == {
        "margin.beta_w": 3,
        "margin.c": 3,
        "publication.headline_ordering": 2,
    }
    for v in variants.VARIANTS:
        # A variant id is a directory name and a URL segment. Anything needing an
        # escape would make the published path and the id two different strings.
        assert v.id == v.id.lower()
        assert all(ch.isalnum() or ch == "-" for ch in v.id), v.id


def test_every_variant_resolves_to_its_one_constant_and_changes_exactly_one_thing(
    tmp_path: Path,
) -> None:
    """The whole attributability claim, checked against the real default config.

    A variant document reports one tau and attributes it to one constant. If an
    overlay moved two constants, or moved one the merge silently ignored, that
    attribution would be false and nothing downstream could detect it.
    """
    overlays = tmp_path / "overlays"
    variants.write_overlays(overlays)
    base = load_config()

    for v in variants.VARIANTS:
        cfg, recipe = recipes.resolve(v.id, directory=overlays)
        table, _, key = v.axis.partition(".")

        assert recipe.slug == v.id
        assert recipe.is_house is False
        assert recipe.flat_overrides() == v.changes

        got, house = cfg[table][key], base[table][key]
        assert got == v.value or (math.isinf(got) and math.isinf(v.value))
        # A VARIANT EQUAL TO THE HOUSE VALUE IS A NO-OP EXPERIMENT: it would
        # publish tau = 1.0 and the word "convention" about a knob nobody turned.
        assert got != house, f"{v.id} does not move {v.axis} off its house value"

        # Nothing else moved. Compared as flattened dotted keys so a nested table
        # replaced wholesale is caught rather than compared reference-to-reference.
        moved = {
            k
            for k in _flat(base)
            if _flat(cfg).get(k) != _flat(base).get(k)
        }
        # `headline_layer` is DERIVED from `headline_ordering` by `resolve` and is
        # not a second knob; publish/poll.py asserts the two agree on every run.
        assert moved <= {v.axis, "publication.headline_layer"}, (v.id, moved)


def _flat(mapping: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flat(value, f"{dotted}."))
        else:
            out[dotted] = value
    return out


def test_a_variant_may_not_move_evidence(tmp_path: Path) -> None:
    """The one rule, enforced by the machinery a hand-written recipe goes through.

    Not a restatement of `test_recipes.py`: what is checked here is that a
    GENERATED overlay is loaded through the same refusal, so the playground cannot
    become the hole in the rule the recipes obey.
    """
    overlays = tmp_path / "overlays"
    variants.write_overlays(overlays)
    for v in variants.VARIANTS:
        recipes.assert_values_only(recipes.load(v.id, directory=overlays).overrides, v.id)

    (overlays / "sneaky.toml").write_text(
        variants.overlay_toml(variants.VARIANTS[0]).replace(
            "[margin]\nbeta_w = 0.0", '[model]\nfit_universe = "all"'
        ).replace('slug = "margin-beta-w-0"', 'slug = "sneaky"'),
        encoding="utf-8",
    )
    with pytest.raises(recipes.RecipeError, match="EVIDENCE"):
        recipes.load("sneaky", directory=overlays)


def test_generated_overlays_never_enter_the_published_roster(tmp_path: Path) -> None:
    """`index.json` and the site's recipe selector must not grow eight entries."""
    variants.write_overlays(tmp_path / "overlays")
    assert [r["slug"] for r in recipes.roster()] == ["full-merit", "house", "just-win"]
    assert set(recipes.slugs()) == {"full-merit", "house", "just-win"}


def test_write_overlays_is_idempotent(tmp_path: Path) -> None:
    first = {p.name: p.read_bytes() for p in variants.write_overlays(tmp_path / "o")}
    second = {p.name: p.read_bytes() for p in variants.write_overlays(tmp_path / "o")}
    assert first == second


def test_uncapped_is_published_by_name_in_both_the_toml_and_the_document() -> None:
    """`margin.c = inf` is a real setting and JSON has no infinity.

    It is spelled `inf` in TOML and `"uncapped"` in JSON, which is exactly what
    `configs/recipes/full-merit.toml` and `recipes._jsonable` already do. A reader
    comparing a variant document with the full-merit week must not find the same
    constant spelled two ways.
    """
    v = variants.by_id("margin-c-uncapped")
    assert math.isinf(v.value)
    assert "c = inf" in variants.overlay_toml(v)
    assert v.changes == {"margin.c": "uncapped"}


def test_by_id_names_the_alternatives_when_it_fails() -> None:
    with pytest.raises(KeyError, match="margin-beta-w-0"):
        variants.by_id("no-such-knob")


# ------------------------------------------------------------------ the arithmetic


def test_kendall_tau_against_a_hand_computed_value() -> None:
    """Five teams, one adjacent transposition, computed by hand.

    tau_b = (concordant - discordant) / n(n-1)/2 with no ties. Five teams give
    ten pairs; swapping the ranks of exactly one adjacent pair makes that one pair
    discordant and leaves nine concordant, so tau = (9 - 1) / 10 = 0.8.
    """
    house = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
    variant = {1: 1, 2: 3, 3: 2, 4: 4, 5: 5}
    got = variants.agreement(house, variant)
    assert got["kendall_tau_vs_house"] == pytest.approx(0.8)
    assert got["n_teams_compared"] == 5
    # Neither team moved five places, so the second statistic is not the first.
    assert got["n_moved_5_or_more"] == 0
    assert got["verdict"] == "dial"


def test_an_identical_board_is_perfect_agreement_and_a_convention() -> None:
    ranks = {i: i for i in range(1, 40)}
    got = variants.agreement(ranks, dict(ranks))
    assert got["kendall_tau_vs_house"] == pytest.approx(1.0)
    assert got["n_moved_5_or_more"] == 0
    assert got["verdict"] == "convention"


def test_n_moved_5_or_more_counts_both_directions_and_is_inclusive_at_five() -> None:
    house = {1: 1, 2: 2, 3: 10, 4: 20, 5: 30}
    variant = {1: 6, 2: 3, 3: 5, 4: 24, 5: 30}
    #            +5     +1     -5     +4      0
    got = variants.agreement(house, variant)
    assert got["n_moved_5_or_more"] == 2


def test_agreement_is_computed_only_on_teams_both_boards_carry() -> None:
    """A team in one board and not the other cannot contribute to a rank change."""
    house = {1: 1, 2: 2, 3: 3}
    variant = {2: 1, 3: 2, 99: 3}
    got = variants.agreement(house, variant)
    assert got["n_teams_compared"] == 2


def test_two_boards_sharing_no_team_are_refused_rather_than_scored() -> None:
    with pytest.raises(ValueError, match="share no team"):
        variants.agreement({1: 1}, {2: 1})


# -------------------------------------------------------------------- the verdict


@pytest.mark.parametrize(
    ("tau", "expected"),
    [
        (0.9849999, "dial"),
        (0.985, "convention"),  # AT the floor is a convention: the rule is `tau <`
        (0.9850001, "convention"),
        (1.0, "convention"),
        (0.0, "dial"),
    ],
)
def test_the_verdict_threshold_is_pinned_on_both_sides(
    tau: float, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The boundary case is the one that matters and the one nobody checks.

    ADR 0006 and `scripts/tuning_campaign.py` both spell the rule
    `tau < Q_REF_TAU_FLOOR`, so a tau exactly at the floor is a CONVENTION. An
    implementation using `<=` would relabel every knob that lands precisely on
    the published number, which is the one place the two documents would be read
    side by side.
    """

    class _Result:
        statistic = tau

    monkeypatch.setattr(
        "scipy.stats.kendalltau", lambda *a, **k: _Result(), raising=True
    )
    got = variants.agreement({1: 1, 2: 2}, {1: 1, 2: 2})
    assert got["kendall_tau_vs_house"] == pytest.approx(tau)
    assert got["verdict"] == expected
    assert got["tau_floor"] == variants.TAU_FLOOR


def test_the_tau_floor_is_the_projects_published_number_not_a_second_one() -> None:
    """0.985 appears in this module and in the campaign script. They must agree.

    If they ever drift, this project publishes two definitions of "dial" - one in
    `docs/analysis/` and one on the site - and no reader can tell which they are
    looking at.
    """
    source = Path(__file__).resolve().parents[2] / "scripts" / "tuning_campaign.py"
    text = source.read_text(encoding="utf-8")
    assert f"Q_REF_TAU_FLOOR = {variants.TAU_FLOOR}" in text


# ------------------------------------------------------------------- the document


def test_the_document_carries_the_contract_and_nothing_else(tree: Path) -> None:
    bundle = _bundle()
    house = variants.house_ranks(tree, 2025, 16)
    doc = variants.document(bundle, variants.by_id("margin-beta-w-0"), house)

    assert set(doc) == {
        "schema_version",
        "season",
        "week",
        "season_type",
        "generator",
        "variant",
        "agreement",
        "rows",
    }
    assert doc["schema_version"] == variants.SCHEMA_VERSION == 1
    assert (doc["season"], doc["week"], doc["season_type"]) == (2025, 16, "regular")

    assert set(doc["variant"]) == {
        "id",
        "axis",
        "value",
        "base",
        "changes",
        "config_sha256",
        "evidence",
    }
    assert doc["variant"]["id"] == "margin-beta-w-0"
    assert doc["variant"]["axis"] == "margin.beta_w"
    assert doc["variant"]["value"] == 0.0
    assert doc["variant"]["base"] == "house"
    assert doc["variant"]["changes"] == {"margin.beta_w": 0.0}

    assert set(doc["agreement"]) == {
        "kendall_tau_vs_house",
        "n_moved_5_or_more",
        "n_teams_compared",
        "verdict",
        "tau_floor",
    }


def test_the_rows_are_the_top_forty_in_rank_order_with_eleven_columns(tree: Path) -> None:
    bundle = _bundle(n=60)
    doc = variants.document(bundle, variants.VARIANTS[0], variants.house_ranks(tree, 2025, 16))
    rows = doc["rows"]

    assert len(rows) == variants.TOP_N == 40
    assert [r["rank"] for r in rows] == list(range(1, 41))
    for row in rows:
        assert set(row) == set(variants.ROW_FIELDS)
        # The week document's presentation columns must not leak into a thin one.
        assert "logo_url" not in row and "team" not in row and "conference" not in row


def test_a_board_shorter_than_forty_publishes_what_it_has(tree: Path) -> None:
    doc = variants.document(
        _bundle(n=12), variants.VARIANTS[0], variants.house_ranks(tree, 2025, 16)
    )
    assert len(doc["rows"]) == 12


def test_the_evidence_block_is_the_house_weeks_and_is_not_recomputed(tree: Path) -> None:
    """The integrity claim, as a property of where the number comes from.

    `document` must LIFT the three digests off the bundle that `serving.build`
    produced, not assemble its own. A module that built its own would be a second
    definition of "the evidence this run read", and the two would eventually
    disagree on exactly the document whose job is to prove they cannot.
    """
    bundle = _bundle()
    doc = variants.document(bundle, variants.VARIANTS[0], variants.house_ranks(tree, 2025, 16))
    assert doc["variant"]["evidence"] == bundle.views["week"]["recipe"]["evidence"]
    assert set(doc["variant"]["evidence"]) == {
        "archive_manifest_sha256",
        "fit_window_sha256",
        "n_games_in_fit",
    }


def test_floats_are_rounded_to_the_published_precision(tree: Path) -> None:
    doc = variants.document(_bundle(), variants.VARIANTS[0], variants.house_ranks(tree, 2025, 16))
    row = doc["rows"][0]
    assert row["odds_key"] == 3.238109
    assert row["gap"] == 28.193121
    # Integers stay integers rather than becoming 1.0.
    assert isinstance(row["rank"], int) and isinstance(row["power_rank"], int)


def test_publishing_the_same_run_twice_is_byte_identical(tree: Path, tmp_path: Path) -> None:
    """Determinism, as bytes on disk rather than as equal dictionaries.

    Report 03 §9.3: the bytes must be a pure function of the computation, so a
    fixture set can be diffed and a change in the data is visible as a change in
    the file. Two dictionaries comparing equal would not catch a set iterating in
    a different order or a float formatted two ways.
    """
    doc = variants.document(_bundle(), variants.VARIANTS[0], variants.house_ranks(tree, 2025, 16))
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    variants._dump(a, doc)
    variants._dump(b, doc)
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes().endswith(b"\n")

    rebuilt = variants.document(
        _bundle(), variants.VARIANTS[0], variants.house_ranks(tree, 2025, 16)
    )
    variants._dump(b, rebuilt)
    assert a.read_bytes() == b.read_bytes()


def test_the_document_stays_thin(tree: Path, tmp_path: Path) -> None:
    """A size ceiling, because "thin" is the entire reason this document exists.

    Ten kilobytes is not the target - about eight is - it is the point at which
    the document has stopped being a cheap comparison surface and somebody should
    have to argue for the change rather than let it drift there one column at a
    time.
    """
    doc = variants.document(_bundle(), variants.VARIANTS[0], variants.house_ranks(tree, 2025, 16))
    path = tmp_path / "week-16.json"
    variants._dump(path, doc)
    assert path.stat().st_size < 10_000


def test_a_variant_cannot_be_published_without_the_house_week_to_compare_against(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="make fixtures"):
        variants.house_ranks(tmp_path, 2025, 16)


def test_the_variant_subtree_is_a_sibling_of_recipes_and_moves_nothing(tmp_path: Path) -> None:
    got = variants.variant_dir(tmp_path, 2025, "margin-c-1")
    assert got == tmp_path / "2025" / "variants" / "margin-c-1"
