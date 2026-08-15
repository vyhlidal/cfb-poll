"""Recipes: the integrity properties, and the ones that are only claims until tested.

ADR 0011 rests on one sentence — **a recipe changes VALUES, never EVIDENCE** — and
a sentence is not an assurance. Three of the tests here are that sentence made
falsifiable:

  * `test_recipe_selection_changes_zero_ingested_bytes` digests the frames every
    recipe actually fits on and asserts they are byte-identical.
  * `test_every_recipe_passes_the_leakage_audit` runs the real pre-fit audit under
    every recipe with `fail_on_banned` set, so a recipe that reached a banned
    column would fail here exactly as it would fail a publication run.
  * `test_a_recipe_may_not_move_the_evidence` plants an evidence key in a recipe
    and asserts the loader refuses it, which is the guard that keeps the first two
    tests true for recipes nobody has written yet.

And one that is the other half of the same promise:
`test_the_house_recipe_is_the_default_config` asserts the published poll is
`configs/default.toml` under this machinery, unchanged, with an empty diff.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cfbpoll import recipes
from cfbpoll.cli import app
from cfbpoll.config import DEFAULT_CONFIG_PATH, load_config
from cfbpoll.ingest.plays import DEFAULT_ARCHIVE as PLAY_ARCHIVE
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE
from cfbpoll.publish import poll as poll_mod
from cfbpoll.validate import leakage

runner = CliRunner()

#: The week every archive-backed test here fits on. Late enough that the graph is
#: welded and the poll is not provisional, early enough to stay cheap.
WEEK = 10
SEASON = 2023

needs_archive = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised",
)


def _window(config: dict[str, Any]):
    """The exact frame a run under this config would fit on. Nothing else."""
    from cfbpoll.ingest import windows
    from cfbpoll.ingest.sportsdataverse import load_games

    games = load_games([SEASON], universe=str(config["model"]["fit_universe"]))
    return windows.games_through(games, season=SEASON, week=WEEK, season_type="regular")


def _raw_plays() -> Any:
    """The RAW play frame, which is what `leakage.audit` wants: it does the join to
    the window itself, because the join is one of the things it audits."""
    from cfbpoll.ingest.plays import load_plays

    if not (PLAY_ARCHIVE / "pbp" / f"play_by_play_{SEASON}.parquet").exists():
        return None
    return load_plays([SEASON])


def _joined_plays(window) -> Any:
    from cfbpoll.ingest.plays import plays_for

    raw = _raw_plays()
    return None if raw is None else plays_for(raw, window)


# ------------------------------------------------------------------ the roster


def test_the_three_recipes_span_the_axis_and_exactly_one_is_published() -> None:
    """The feature is three named stances on one axis, with one of them published.

    `stance` decides display order and nothing else, so the selector reads left to
    right along the argument rather than alphabetically, which would put the house
    poll first and imply the other two are footnotes.
    """
    roster = recipes.available()
    assert [r.slug for r in roster] == ["full-merit", "house", "just-win"]
    assert [r.stance for r in roster] == [0, 1, 2]
    assert sum(1 for r in roster if r.is_house) == 1
    assert recipes.load(recipes.HOUSE).is_house


def test_every_recipe_states_its_own_cost() -> None:
    """A value system that will not state its own cost is a marketing page.

    Checked here as well as in `recipes.load` because the loader's refusal only
    fires on a MISSING list, and a single empty string would satisfy it. This is
    the assertion that the costs are actually written.
    """
    for recipe in recipes.available():
        assert recipe.tradeoffs, recipe.slug
        assert all(len(cost) > 60 for cost in recipe.tradeoffs), recipe.slug
        # The manifesto is ONE paragraph and is published pre-collapsed, so both
        # renderers print the same characters into the same single <p> and neither
        # has to decide what a line break in a TOML string meant.
        assert "\n" not in recipe.manifesto, recipe.slug
        assert len(recipe.manifesto) > 400, recipe.slug
        assert recipe.one_liner and "\n" not in recipe.one_liner


def test_the_recipe_prose_is_in_the_owner_voice() -> None:
    """No em dashes anywhere a reader sees, which is a standing house rule for
    published prose and is easiest to enforce where the prose is data."""
    for recipe in recipes.available():
        text = " ".join([recipe.name, recipe.one_liner, recipe.manifesto, *recipe.tradeoffs])
        assert "—" not in text and "–" not in text, recipe.slug


def test_every_recipe_selects_an_ordering_the_pipeline_implements() -> None:
    """A recipe naming an ordering with no sort rule would fail inside a fit."""
    for recipe in recipes.available():
        config, _ = recipes.resolve(recipe.slug)
        ordering = poll_mod.headline_ordering(config)  # asserts the two names agree
        assert ordering in poll_mod.ORDER_KEYS
        assert ordering in poll_mod.HEADLINE_INTERVAL_ORDERING


def test_the_three_recipes_do_not_all_rank_on_the_same_column() -> None:
    """If they did, this would be a config-tweaking feature rather than an axis."""
    orderings = {
        recipes.resolve(r.slug)[0]["publication"]["headline_ordering"]
        for r in recipes.available()
    }
    assert orderings == {"schedule_odds", "L4_resume", "L4_resume_margin"}


# ------------------------------------------------------- the house recipe is the poll


def test_the_house_recipe_is_the_default_config() -> None:
    """THE PUBLISHED POLL IS UNAFFECTED BY THE EXISTENCE OF THE OTHERS.

    Not a promise in a paragraph. `house.toml` carries a `[recipe]` block and not
    one constant, so the resolved config is `configs/default.toml` exactly, and
    this equality is what makes that checkable rather than asserted.
    """
    resolved, recipe = recipes.resolve(recipes.HOUSE)
    assert recipe.overrides == {}
    assert recipe.flat_overrides() == {}
    assert resolved == load_config(DEFAULT_CONFIG_PATH)


def test_the_house_recipe_may_never_grow_a_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard that keeps the property above true next year.

    A house recipe that quietly grew one constant would make the published poll a
    thing assembled from two files, and "the poll did not change" would become an
    argument rather than an equality. `recipes.load` refuses it.
    """
    monkeypatch.setattr(recipes, "RECIPES_DIR", tmp_path)
    (tmp_path / "house.toml").write_text(
        '[recipe]\nslug = "house"\nname = "The House Poll"\nstance = 1\n'
        'one_liner = "x"\nmanifesto = "y"\ntradeoffs = ["z"]\n'
        "\n[margin]\nbeta_w = 8.0\n",
        encoding="utf-8",
    )
    with pytest.raises(recipes.RecipeError, match="must override NOTHING"):
        recipes.load("house")

    # And the committed file has not: every non-comment line belongs to [recipe].
    body = (Path(__file__).parents[2] / "configs" / "recipes" / "house.toml").read_text("utf-8")
    section = None
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("["):
            section = stripped
        assert section == "[recipe]", f"house.toml left [recipe]: {stripped!r}"


# ----------------------------------------------------------- values, never evidence


@pytest.mark.parametrize(
    "planted",
    [
        {"model": {"fit_universe": "fbs_vs_fbs"}},
        {"backtest": {"walk_forward_strict": False}},
        {"backtest": {"holdout_seasons": [2024]}},
        {"constraints": {"allow_conference_as_feature": True}},
        {"ep": {"fit_scope": "frozen"}},
        {"weights": {"bowl_non_cfp": 1.0}},
        {"fcs": {"pool_into_single_node": True}},
    ],
)
def test_a_recipe_may_not_move_the_evidence(planted: dict[str, Any]) -> None:
    """Every one of these would make two recipes incomparable.

    A recipe that could move `fit_universe` would be reading a different set of
    games; one that could move `walk_forward_strict` or `ep.fit_scope` would be
    reading games from the future; one that could move `[constraints]` would be
    reading banned columns. Put any of them on a side-by-side page and the reader
    is comparing two measurements, not two value systems.

    `[weights]` is in the list and looks like a value. It is not: the non-CFP bowl
    weight is a statement about how well a game MEASURES a team, and it is the same
    statement under every value system.
    """
    with pytest.raises(recipes.RecipeError, match="EVIDENCE"):
        recipes.assert_values_only(planted, "planted")


def test_the_evidence_guard_matches_by_prefix() -> None:
    """Naming a table locks every key under it, including keys added later.

    A guard that has to be updated whenever the table it protects grows is a guard
    that is one forgotten commit from useless.
    """
    with pytest.raises(recipes.RecipeError):
        recipes.assert_values_only({"constraints": {"a_key_invented_today": True}}, "planted")


def test_a_recipe_that_names_nothing_is_refused() -> None:
    """`merge_overlay`'s rule, reached through `resolve`: an override that names a
    key the default config does not define changes nothing, silently, and you
    would then publish a finding about a model nobody ran."""
    base = load_config(DEFAULT_CONFIG_PATH)
    with pytest.raises(KeyError, match="betaw"):
        from cfbpoll.config import merge_overlay

        merge_overlay(base, {"betaw": 4.0})


def test_the_values_each_recipe_actually_changes() -> None:
    """The published `changes` object, which is what a page prints under "what this
    recipe changes". Every key here is a VALUE and the list is short on purpose."""
    changes = {r.slug: r.flat_overrides() for r in recipes.available()}
    assert changes["house"] == {}
    assert changes["full-merit"] == {
        "margin.beta_w": 12.0,
        "margin.c": "uncapped",  # JSON has no infinity; the limit is published by name
        "publication.headline_ordering": "L4_resume_margin",
    }
    assert changes["just-win"] == {
        "margin.beta_w": 7.0,
        "margin.c": 1.0,
        "publication.headline_ordering": "L4_resume",
    }
    # `full-merit` really does switch the compression off, rather than setting it
    # very high: `inf` is the limit of the tanh family and `design.tanh_term` takes
    # it explicitly, because numpy would evaluate inf * tanh(m/inf) as nan.
    config, _ = recipes.resolve("full-merit")
    assert math.isinf(config["margin"]["c"])


def test_the_resolved_hash_is_a_function_of_every_constant() -> None:
    """`config_hash` hashes file bytes, which is the right answer for one file and
    no answer at all for a file plus a diff."""
    hashes = {
        r.slug: recipes.resolved_hash(recipes.resolve(r.slug)[0]) for r in recipes.available()
    }
    assert len(set(hashes.values())) == 3
    assert hashes["house"] == recipes.resolved_hash(load_config(DEFAULT_CONFIG_PATH))


# --------------------------------------------------- the evidence, actually measured


@needs_archive
def test_recipe_selection_changes_zero_ingested_bytes() -> None:
    """THE CLAIM, MEASURED. Same archive, same window, same games, same plays.

    This is the assertion `EVIDENCE_KEYS` exists to make true and it is deliberately
    made downstream of the loader rather than by inspecting the recipe files: it
    digests the frames a run under each recipe would actually fit on, so a leak
    through some path nobody thought to lock would still be caught here.
    """
    digests = set()
    play_digests = set()
    counts = set()
    for recipe in recipes.available():
        config, _ = recipes.resolve(recipe.slug)
        window = _window(config)
        digests.add(leakage.digest(window))
        counts.add(window.height)
        plays = _joined_plays(window)
        play_digests.add(None if plays is None else leakage.digest(plays))
    assert len(digests) == 1, "two recipes fit on different games"
    assert len(play_digests) == 1, "two recipes fit on different plays"
    assert len(counts) == 1


@needs_archive
def test_every_recipe_passes_the_leakage_audit() -> None:
    """Constraint 1 holds under every value system, or the value system is void.

    `fail_on_banned=True` is the same setting a publication run uses, so this is
    the real audit and not a lenient copy of it: a recipe that reached a banned
    column would raise here exactly as `cfbpoll rank` would refuse to publish it.
    """
    for recipe in recipes.available():
        config, _ = recipes.resolve(recipe.slug)
        window = _window(config)
        report = leakage.audit(window, _raw_plays(), config, fail_on_banned=True)
        assert report.passed, (recipe.slug, report.violations)
        assert report.violations == []
        assert len(report.layers) == 9
        # Every layer either rebuilt bit-identically from its allow-list or said
        # why it could not run. A silent pass is the failure mode this audit exists
        # to prevent, so it is asserted rather than assumed.
        assert all(layer.ok for layer in report.layers), recipe.slug


# ------------------------------------------------------------------- end to end


@pytest.fixture(scope="module")
def ranked(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One run per recipe, plus a second house run with no `--recipe` at all."""
    if not (DEFAULT_ARCHIVE / "schedules").exists():  # pragma: no cover
        pytest.skip("local archive not materialised")
    root = tmp_path_factory.mktemp("recipes")
    out: dict[str, Path] = {}
    for slug in [r.slug for r in recipes.available()] + ["_no_flag"]:
        target = root / slug
        argv = ["rank", "--season", str(SEASON), "--through-week", str(WEEK), "--draws", "24"]
        if slug != "_no_flag":
            argv += ["--recipe", slug]
        result = runner.invoke(app, [*argv, "--out", str(target)])
        assert result.exit_code == 0, result.output
        out[slug] = target
    return out


def _poll(run: Path) -> dict[str, Any]:
    return json.loads((run / "poll.json").read_text(encoding="utf-8"))


@needs_archive
def test_omitting_the_flag_publishes_the_house_poll_to_the_last_byte(
    ranked: dict[str, Path],
) -> None:
    """The regression this whole feature must never cause.

    `poll.csv` is every published number for every ranked team. Adding recipes
    moved none of them.
    """
    assert (ranked["house"] / "poll.csv").read_bytes() == (
        ranked["_no_flag"] / "poll.csv"
    ).read_bytes()
    assert _poll(ranked["house"])["ranking"] == _poll(ranked["_no_flag"])["ranking"]
    assert _poll(ranked["house"])["recipe"]["slug"] == "house"


@needs_archive
def test_every_run_says_which_value_system_produced_it(ranked: dict[str, Path]) -> None:
    """Constraint 5, applied to the recipe. "No recipe was named" and "the house
    recipe ran" are the same event, so every run carries the block, including the
    run that did not pass the flag."""
    for slug, run in ranked.items():
        expected = "house" if slug == "_no_flag" else slug
        params = json.loads((run / "model_params.json").read_text(encoding="utf-8"))
        block = params["recipe"]
        assert block["slug"] == expected
        assert block["manifesto"] and block["tradeoffs"]
        assert (block["label"] is None) == (expected == "house")
        assert params["headline_layer"] == poll_mod.ORDERING_LAYER[params["headline_ordering"]]
        # poll.json carries it too: it is the document a reader opens first.
        assert _poll(run)["recipe"]["slug"] == expected


@needs_archive
def test_the_receipts_prove_same_evidence_different_values(ranked: dict[str, Path]) -> None:
    """Three runs, three methodologies, one set of games. Checkable by diffing two
    `_run.json` files, which is what the site prints on a comparison page."""
    receipts = {
        slug: json.loads((run / "_run.json").read_text(encoding="utf-8"))
        for slug, run in ranked.items()
    }
    assert len({r["fit_window_sha256"] for r in receipts.values()}) == 1
    assert len({r["n_games_in_fit"] for r in receipts.values()}) == 1
    assert len({r["archive_manifest_sha256"] for r in receipts.values()}) == 1
    # ...and three genuinely different methodologies, or there is nothing to choose
    # between. `_no_flag` and `house` are the same methodology and must collide.
    resolved = {slug: r["recipe_config_sha256"] for slug, r in receipts.items()}
    assert resolved["house"] == resolved["_no_flag"]
    assert len({resolved[s] for s in ("house", "full-merit", "just-win")}) == 3


@needs_archive
def test_each_recipe_is_deterministic(ranked: dict[str, Path], tmp_path: Path) -> None:
    """Same recipe, same seed, same bytes. Per recipe, not just for the house poll.

    Determinism is a requirement of this project rather than a nicety (report 03
    §9.3), and it is a property of a METHODOLOGY. A recipe that produced a
    different poll on a second run would make every comparison in
    demo/2023-recipes.md unrepeatable.
    """
    for slug in ("full-merit", "just-win"):
        again = tmp_path / f"{slug}-again"
        result = runner.invoke(
            app,
            [
                "rank", "--season", str(SEASON), "--through-week", str(WEEK),
                "--draws", "24", "--recipe", slug, "--out", str(again),
            ],
        )
        assert result.exit_code == 0, result.output
        for name in ("poll.csv", "ratings_live.csv", "rank_intervals.csv"):
            assert (again / name).read_bytes() == (ranked[slug] / name).read_bytes(), (slug, name)


@needs_archive
def test_the_rank_interval_belongs_to_the_rank_it_sits_beside(ranked: dict[str, Path]) -> None:
    """The defect the second headline surfaced, asserted closed.

    Under `just-win` the headline IS the wins-based résumé, so `rank_lo`/`rank_hi`
    on the poll must be the RESUME ordering's interval out of the bootstrap, not
    the schedule odds'. The wiring used to be hard-coded to the schedule odds,
    which was invisible while only one headline ever ran in anger.

    Asserted as an exact column identity against `rank_intervals.csv`, and then
    asserted non-vacuous: for the two recipes that do not rank on the schedule
    odds, the published interval must actually DIFFER from the schedule-odds one
    somewhere, or this test would pass just as happily against the bug.
    """
    import polars as pl

    source = {"house": "schedule_odds", "full-merit": "resume_margin", "just-win": "resume"}
    for slug, expected in source.items():
        table = pl.read_csv(ranked[slug] / "poll.csv").select(
            "team", "rank_lo", "rank_hi", "rank_median"
        )
        draws = pl.read_csv(ranked[slug] / "rank_intervals.csv")
        joined = table.join(draws, on="team", how="inner")
        assert joined.height == table.height, slug
        for end in ("lo", "hi", "median"):
            assert joined[f"rank_{end}"].to_list() == joined[f"{expected}_rank_{end}"].to_list(), (
                slug,
                end,
            )
        if expected != "schedule_odds":
            assert (
                joined["rank_lo"].to_list() != joined["schedule_odds_rank_lo"].to_list()
            ), f"{slug}: the two orderings agree everywhere, so this proves nothing"


# ------------------------------------------------------------- the fixture contract


@pytest.fixture(scope="module")
def published(ranked: dict[str, Path], tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The three runs exported as a fixture tree. docs/fixture-contract-recipes.md."""
    from cfbpoll.publish import fixtures

    dest = tmp_path_factory.mktemp("fixtures")
    for slug in ("house", "full-merit", "just-win"):
        fixtures.export(ranked[slug], dest)
    return dest


@needs_archive
def test_the_published_poll_keeps_the_path_it_has_always_had(published: Path) -> None:
    """The contract's whole compatibility claim: nothing moved.

    A site that has never heard of a recipe reads exactly the paths it read
    before, gets the same documents, and passes the same `schema_version` check.
    """
    season = published / "2023"
    for stem in ("week", "connectivity", "methodology", "data"):
        assert (season / f"{stem}-{WEEK:02d}.json").exists(), stem
    assert (season / "divergence.json").exists()

    index = json.loads((published / "index.json").read_text(encoding="utf-8"))
    from cfbpoll.publish.fixtures import SCHEMA_VERSION

    assert index["schema_version"] == SCHEMA_VERSION == 1


@needs_archive
def test_an_alternate_lens_is_a_new_subtree_not_a_new_shape(published: Path) -> None:
    """Two documents per lens, in the same shape, under `recipes/<slug>/`.

    Connectivity and /data are house-only on purpose: the connectivity report is a
    function of the schedule graph, which is EVIDENCE and is identical under every
    recipe, and /data indexes the artifacts of a published run of which there is
    exactly one.
    """
    lenses = published / "2023" / "recipes"
    assert sorted(p.name for p in lenses.iterdir()) == ["full-merit", "just-win"]
    for slug in ("full-merit", "just-win"):
        got = sorted(p.name for p in (lenses / slug).iterdir())
        assert got == ["divergence.json", f"methodology-{WEEK:02d}.json", f"week-{WEEK:02d}.json"]
        # The document shape is the published poll's, key for key.
        house = json.loads((published / "2023" / f"week-{WEEK:02d}.json").read_text("utf-8"))
        lens = json.loads((lenses / slug / f"week-{WEEK:02d}.json").read_text("utf-8"))
        assert sorted(house) == sorted(lens)
        assert sorted(house["poll"][0]) == sorted(lens["poll"][0])


@needs_archive
def test_there_is_no_recipes_house_directory(published: Path) -> None:
    """The house recipe IS the season directory.

    A duplicate copy under a slug would be two files that must agree forever, and
    the first time they disagreed the site would show the published poll twice,
    differently.
    """
    assert not (published / "2023" / "recipes" / "house").exists()


@needs_archive
def test_the_index_carries_the_roster_a_selector_needs(published: Path) -> None:
    """One document, so a page never opens a week file to find out what it offers
    and never holds its own copy of prose that would drift from the config."""
    index = json.loads((published / "index.json").read_text(encoding="utf-8"))
    assert index["recipes_contract_version"] == 1
    roster = {r["slug"]: r for r in index["recipes"]}
    assert set(roster) == {"full-merit", "house", "just-win"}
    assert [r["slug"] for r in index["recipes"]] == ["full-merit", "house", "just-win"]
    assert sum(1 for r in roster.values() if r["default"]) == 1
    assert roster["house"]["default"] is True and roster["house"]["label"] is None
    for slug in ("full-merit", "just-win"):
        assert roster[slug]["label"] == recipes.ALTERNATE_LABEL
        assert roster[slug]["manifesto"] and roster[slug]["tradeoffs"]
        assert roster[slug]["changes"]

    # Presence, per season, so a selector can disable a week that was never
    # published rather than 404 on click. The house poll is not listed: it is the
    # season itself.
    season = next(s for s in index["seasons"] if s["season"] == 2023)
    assert season["recipes"] == [
        {"slug": "full-merit", "weeks": [WEEK]},
        {"slug": "just-win", "weeks": [WEEK]},
    ]


@needs_archive
def test_every_published_week_carries_its_own_integrity_block(published: Path) -> None:
    """"Same data, different values" printable from the documents themselves.

    A claim a reader cannot check is a slogan, so the archive digest, the
    fit-window digest and the game count travel on every recipe's week document
    and are identical across lenses.
    """
    docs = [published / "2023" / f"week-{WEEK:02d}.json"] + [
        published / "2023" / "recipes" / slug / f"week-{WEEK:02d}.json"
        for slug in ("full-merit", "just-win")
    ]
    evidence = []
    for path in docs:
        block = json.loads(path.read_text(encoding="utf-8"))["recipe"]
        assert block["config_sha256"]
        evidence.append(json.dumps(block["evidence"], sort_keys=True))
    assert len(set(evidence)) == 1, evidence
    assert json.loads(evidence[0])["fit_window_sha256"]


@needs_archive
def test_an_alternate_lens_publishes_no_gate_verdict_and_says_why(published: Path) -> None:
    """`[gate]` is written against the PUBLISHED poll. Attaching those numbers to a
    lens would print the house poll's verdict on a page describing a different
    value system, and an empty table with no explanation reads as an oversight."""
    for slug in ("full-merit", "just-win"):
        doc = json.loads(
            (published / "2023" / "recipes" / slug / f"methodology-{WEEK:02d}.json").read_text(
                "utf-8"
            )
        )
        assert doc["gate"] == [] and doc["metrics"] == []
        assert "not applied per recipe" in doc["gate_note"]
        assert doc["recipe"]["slug"] == slug
        # The constants ARE published for a lens. Only the verdict is absent.
        assert doc["params"]["footer_lines"]
        assert doc["weaknesses"]


@needs_archive
def test_the_uncapped_compression_reaches_the_page_as_a_word(published: Path) -> None:
    """JSON has no infinity and `publish/fixtures.py` writes with allow_nan=False,
    so an unhandled `C = inf` would either emit an invalid literal or raise. The
    constant that IS full-merit's argument must not be the one that goes missing."""
    doc = json.loads(
        (published / "2023" / "recipes" / "full-merit" / f"methodology-{WEEK:02d}.json").read_text(
            "utf-8"
        )
    )
    assert doc["params"]["labels"]["C"] == "uncapped"
    assert "C uncapped" in doc["params"]["footer_lines"][1]
    assert "β_w 12" in doc["params"]["footer_lines"][1]


@needs_archive
def test_full_merit_puts_beaten_teams_over_unbeaten_ones_and_just_win_never_can(
    ranked: dict[str, Path],
) -> None:
    """The two structural facts the recipes exist to make visible.

    Under `just-win` no team with a loss can EVER outrank an unbeaten team: every
    undefeated team saturates at the published bracket, which is the top of the
    key. Under `full-merit` that constraint does not exist and the 2023 board
    exercises it hard. These are properties of the orderings (ADR 0005), not
    outcomes of this particular season, and the season is where they show.
    """
    for slug, expect_inversion in (("just-win", False), ("full-merit", True)):
        rows = _poll(ranked[slug])["ranking"]
        unbeaten_worst = max((r["rank"] for r in rows if r["losses"] == 0), default=0)
        beaten_best = min((r["rank"] for r in rows if r["losses"] > 0), default=10**6)
        assert (beaten_best < unbeaten_worst) is expect_inversion, slug
