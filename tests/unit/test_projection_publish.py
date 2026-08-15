"""The site fixture, tested against the contract the card actually enforces.

`src/lib/cfb-poll/projection.ts` in the sandbox app binds this module to rules
whose violations are invisible in JSON and obvious on the page, which is exactly
the class of bug a test is for:

  * the site DERIVES NOTHING, so `projected_wins` must be a pre-formatted string;
  * `basis` and `headline` must be complete sentences, because the card continues
    from `basis` in the same paragraph;
  * `status` is authoritative and never inferred from the row count, so a
    finished projection can ship dark.
"""

from __future__ import annotations

import json

import polars as pl
import pytest

from cfbpoll.config import load_config
from cfbpoll.projection import publish

CONFIG = load_config()

HEADLINE = "This is the model's 2026 preseason projection, built in August."
BASIS = "It runs last season's final ratings through a four-term recipe."

#: The shape `fit.run(...)["summary"]` returns, trimmed to what `_backtest_block`
#: reads. Real values from the published backtest, so a change to the recipe that
#: flips the verdict shows up here as a failing assertion rather than as prose on
#: a website that nobody re-read.
_SUMMARY = {
    "out_of_sample": {
        "projection": {"top25_overlap": 14.333333},
        "ap_preseason": {"top25_overlap": 14.666667},
        "naive_carryover": {"top25_overlap": 13.333333},
    },
    "early_season": {
        "projection": {"su_accuracy": 0.713442},
        "ap_preseason": {"su_accuracy": 0.689945},
    },
}


@pytest.fixture
def projection() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "team": ["Ohio State", "Oregon", "Indiana", "Nowhere State"],
            "projected_rank": pl.Series([1, 2, 3, 4], dtype=pl.Int32),
            "projected_power": [37.9, 37.6, 37.2, 5.0],
            "projected_wins": [9.13, 9.47, 9.62, None],
            "contrib_returning_production": [1.9, 1.63, -2.28, 0.1],
            "contrib_coaching_change": [0.0, 0.0, 0.0, -2.33],
            "contrib_net_portal": [1.0, 0.88, -0.2, 0.0],
        }
    )


def test_projected_wins_ships_pre_formatted(projection: pl.DataFrame) -> None:
    """Rule 1 of the contract. A renderer that decides the decimal place is a
    renderer that can disagree with the artifact a reader downloads."""
    document = publish.build(projection, 2026, CONFIG, HEADLINE, BASIS)
    values = [row["projected_wins"] for row in document["rows"]]
    assert values[:3] == ["9.1", "9.5", "9.6"]
    assert all(v is None or isinstance(v, str) for v in values)


def test_a_fragment_is_refused_where_the_card_continues_from_it() -> None:
    """The failure this catches is invisible in JSON and obvious on the page: the
    card prints `basis` and then continues in the same paragraph."""
    frame = pl.DataFrame(
        {
            "team": ["Ohio State"],
            "projected_rank": pl.Series([1], dtype=pl.Int32),
            "projected_power": [30.0],
            "projected_wins": [9.0],
            "contrib_returning_production": [1.0],
            "contrib_coaching_change": [0.0],
            "contrib_net_portal": [0.0],
        }
    )
    with pytest.raises(ValueError, match="COMPLETE SENTENCE"):
        publish.build(frame, 2026, CONFIG, HEADLINE, "2025 ratings plus offseason changes")
    with pytest.raises(ValueError, match="COMPLETE SENTENCE"):
        publish.build(frame, 2026, CONFIG, "the 2026 projection", BASIS)
    # And a good one goes through.
    assert publish.build(frame, 2026, CONFIG, HEADLINE, BASIS)["basis"].endswith(".")


def test_an_em_dash_is_refused_in_every_copy_field(projection: pl.DataFrame) -> None:
    """REPORT 08'S RULE, AND THIS TEST EXISTS BECAUSE THE RULE WAS BROKEN ONCE.

    The first headline this module shipped carried an em dash. It was printed
    verbatim in the largest type on the card and was the only em dash in the
    front door's entire visible text, so the one sentence the page led with read
    as the one sentence somebody else wrote. A rule the pipeline knows is a rule
    the pipeline keeps."""
    dashed = "This is the 2026 projection — the poll will grade it."
    for field, kwargs in (
        ("headline", {"headline": dashed, "basis": BASIS}),
        ("basis", {"headline": HEADLINE, "basis": dashed}),
        ("note", {"headline": HEADLINE, "basis": BASIS, "note": dashed}),
    ):
        with pytest.raises(ValueError, match="em dash"):
            publish.build(projection, 2026, CONFIG, **kwargs)  # type: ignore[arg-type]
        assert field  # names the field under test in the failure output

    # The shapes an em dash arrives under when somebody routes around a linter.
    for bad in ("The projection – graded weekly.", "The projection -- graded weekly."):
        with pytest.raises(ValueError, match="dash|hyphen"):
            publish.build(projection, 2026, CONFIG, HEADLINE, bad)


def test_the_shipped_copy_carries_no_banned_punctuation(
    projection: pl.DataFrame,
) -> None:
    """The whole document, not only the fields the builder happens to check."""
    document = publish.build(
        projection,
        2026,
        CONFIG,
        HEADLINE,
        BASIS,
        note="It is frozen the moment it publishes.",
        backtest=_SUMMARY,
    )
    blob = json.dumps(document, ensure_ascii=False)
    for character in ("—", "–"):
        assert character not in blob, character


def test_status_is_authoritative_and_not_inferred_from_rows(
    projection: pl.DataFrame,
) -> None:
    """A complete projection may sit on disk, dark, until somebody shows it."""
    dark = publish.build(projection, 2026, CONFIG, HEADLINE, BASIS, status="coming")
    assert dark["status"] == "coming"
    assert len(dark["rows"]) == 4
    with pytest.raises(ValueError, match="status"):
        publish.build(projection, 2026, CONFIG, HEADLINE, BASIS, status="live")


def test_the_note_reads_as_english_in_both_directions(projection: pl.DataFrame) -> None:
    """Templated, never hand-written - so the template has to survive a negative
    contribution without producing "-2.3 points of the projection is..."."""
    rows = {r["team"]: r["note"] for r in publish.build(
        projection, 2026, CONFIG, HEADLINE, BASIS
    )["rows"]}
    assert rows["Ohio State"] == "Returning production adds 1.9 points to the projection."
    assert rows["Indiana"] == "Returning production costs the projection 2.3 points."
    assert rows["Nowhere State"] == "A new head coach costs the projection 2.3 points."


def test_a_team_the_recipe_barely_moved_gets_no_manufactured_clause() -> None:
    """No clause is better than a clause about nothing."""
    frame = pl.DataFrame(
        {
            "team": ["Steady State"],
            "projected_rank": pl.Series([1], dtype=pl.Int32),
            "projected_power": [20.0],
            "projected_wins": [6.0],
            "contrib_returning_production": [0.05],
            "contrib_coaching_change": [0.0],
            "contrib_net_portal": [-0.1],
        }
    )
    document = publish.build(frame, 2026, CONFIG, HEADLINE, BASIS)
    assert document["rows"][0]["note"] is None


def test_the_document_carries_the_recipe_version(projection: pl.DataFrame) -> None:
    """Not in the site's interface, and carried anyway: a published projection
    that cannot say which recipe made it cannot be graded season over season."""
    from cfbpoll.projection import PROJECTION_VERSION

    document = publish.build(projection, 2026, CONFIG, HEADLINE, BASIS)
    assert document["projection_version"] == PROJECTION_VERSION
    assert document["schema_version"] == publish.SCHEMA_VERSION
    assert document["grading_start_week"] == CONFIG["publication"]["headline_start_week"]


def test_the_display_fields_are_the_polls_own(projection: pl.DataFrame) -> None:
    """The card and the poll table share a page. A school whose colours changed
    between them would read as a bug in whichever one the reader trusts less."""
    from cfbpoll.ingest.teams import load_colors, mark_for

    colors = load_colors()
    if "Ohio State" not in colors:
        pytest.skip("team-colors.csv not materialised")

    row = publish.build(projection, 2026, CONFIG, HEADLINE, BASIS)["rows"][0]
    entry = colors["Ohio State"]
    expected = mark_for(entry, entry.get("abbreviation") or "Ohio State")
    assert row["mark_bg"] == expected["bg"]
    assert row["mark_fg"] == expected["fg"]
    assert row["mark_label"] == expected["label"]
    assert row["team_id"] == entry["team_id"]
    assert str(entry["team_id"]) in row["logo_url"]
    assert "500-dark" in row["logo_url_dark"]


def test_write_lands_at_the_path_the_loader_reads(projection: pl.DataFrame, tmp_path) -> None:
    """`cfb-poll-data/<season>/projection.json`, matching the fixture convention
    the loader in projection.ts hard-codes."""
    document = publish.build(projection, 2026, CONFIG, HEADLINE, BASIS)
    path = publish.write(document, tmp_path)
    assert path == tmp_path / "2026" / "projection.json"
    assert json.loads(path.read_text()) == document


def test_top_n_is_respected(projection: pl.DataFrame) -> None:
    document = publish.build(projection, 2026, CONFIG, HEADLINE, BASIS, top_n=2)
    assert [row["rank"] for row in document["rows"]] == [1, 2]


# --------------------------------------------------- the honest result, as a field


def test_the_backtest_sentence_is_templated_from_the_measured_numbers(
    projection: pl.DataFrame,
) -> None:
    """"The AP beat us" must not live in a React component, and it must not live
    in a hand-typed paragraph here either. It is composed from the values the
    backtest measured, so it cannot drift from demo/projection-backtest.md the
    first time the recipe is refitted."""
    block = publish.build(
        projection, 2026, CONFIG, HEADLINE, BASIS, backtest=_SUMMARY
    )["backtest"]

    assert "14.7" in block["headline"] and "14.3" in block["headline"]
    assert block["ap_top25_hits"] == "14.7"
    assert block["projection_top25_hits"] == "14.3"
    assert block["naive_top25_hits"] == "13.3"
    assert block["source"] == "demo/projection-backtest.md"
    # The losing half is named first and is not softened away.
    assert block["headline"].startswith("Over three out-of-sample season transitions")
    assert "the AP preseason poll ranked the following season slightly better" in (
        block["headline"]
    )
    assert "71.3% straight up against 69.0%" in block["headline"]


def test_the_sentence_flips_when_the_result_flips(projection: pl.DataFrame) -> None:
    """The template must be able to report a win as readily as a loss, or it is a
    disclaimer rather than a measurement."""
    winning = {
        "out_of_sample": {
            "projection": {"top25_overlap": 17.0},
            "ap_preseason": {"top25_overlap": 14.0},
            "naive_carryover": {"top25_overlap": 13.0},
        },
        "early_season": {
            "projection": {"su_accuracy": 0.60},
            "ap_preseason": {"su_accuracy": 0.70},
        },
    }
    block = publish.build(
        projection, 2026, CONFIG, HEADLINE, BASIS, backtest=winning
    )["backtest"]
    assert "this projection ranked the following season better" in block["headline"]
    assert "17.0 of the final top 25 against 14.0" in block["headline"]
    # And the half we now lose is still reported.
    assert "was worse at predicting September's games" in block["headline"]


# --------------------------------------------------------- the schedule extension


@pytest.fixture
def strength_and_contrast(projection: pl.DataFrame):
    """A real `strengths` / `contrast` pair over a tiny synthetic league."""
    from cfbpoll.projection import forward, recipe, schedule

    fitted = recipe.Recipe(
        intercept=15.0,
        coefficients={
            "prior_power": 0.68,
            "returning_production": 7.08,
            "coaching_change": -2.33,
            "net_portal": -0.41,
        },
        se=dict.fromkeys(recipe.TERMS, 1.0),
        intercept_se=1.0,
        transitions=((2025, 2026),),
        n_teams=4,
        r_squared=0.5,
        residual_sd=9.0,
    )
    teams = projection["team"].to_list()
    games = [
        (a, b, True) for i, a in enumerate(teams) for b in teams[i + 1 :]
    ] * 4  # enough games to clear the ranking floor
    future = pl.DataFrame(
        {
            "game_id": list(range(1, len(games) + 1)),
            "week": pl.Series([1] * len(games), dtype=pl.Int32),
            "neutral_site": [n for _, _, n in games],
            "home_team": [h for h, _, _ in games],
            "away_team": [a for _, a, _ in games],
            "home_class": ["fbs"] * len(games),
            "away_class": ["fbs"] * len(games),
        }
    )
    sigma = forward.projection_sigma(fitted, 15.3)
    strength = schedule.strengths(
        projection, future, fitted, {}, 0.0, sigma, 3.9, promoted=("Nowhere State",)
    )
    contrast = schedule.contrast(projection, future, fitted, {}, 0.0, sigma, 3.9)
    return strength, contrast, sigma


def test_every_schedule_number_ships_pre_formatted(
    projection: pl.DataFrame, strength_and_contrast
) -> None:
    """Contract rule 1 reaches the new columns too. `schedule_strength_rank` and
    `home_games` are counts and stay ints; everything measured is a string."""
    strength, contrast, sigma = strength_and_contrast
    projected = projection.join(strength.table, on="team", how="left")
    document = publish.build(
        projected, 2026, CONFIG, HEADLINE, BASIS,
        strength=strength, contrast=contrast, sigma=sigma,
    )
    for row in document["rows"]:
        for field in (
            "projected_power",
            "schedule_strength",
            "wins_on_median_schedule",
        ):
            assert row[field] is None or isinstance(row[field], str), field
            if isinstance(row[field], str):
                assert row[field].count(".") == 1, (field, row[field])
        for field in ("schedule_strength_rank", "schedule_field_size", "home_games"):
            assert row[field] is None or isinstance(row[field], int), field
        assert row["schedule_is_mixed"] in (True, False, None)


def test_the_schedule_block_carries_all_three_caveats(
    projection: pl.DataFrame, strength_and_contrast
) -> None:
    """Every caveat is a FIELD. A caution the site hard-codes stops being true the
    first time the numbers move and nobody re-reads the JSX."""
    strength, contrast, sigma = strength_and_contrast
    projected = projection.join(strength.table, on="team", how="left")
    block = publish.build(
        projected, 2026, CONFIG, HEADLINE, BASIS,
        strength=strength, contrast=contrast, sigma=sigma,
    )["schedule"]

    assert f"{sigma:.1f}" in block["uncertainty_note"]
    assert "Nowhere State" in block["promotion_note"]
    assert block["median_schedule_team"] == strength.median_schedule_team
    assert block["field_size"] == strength.field_size
    for field in ("note", "uncertainty_note", "promotion_note"):
        assert block[field].endswith(".")


def test_the_promotion_note_is_absent_when_nobody_was_promoted(
    projection: pl.DataFrame, strength_and_contrast
) -> None:
    """Null, not an empty string, and not a sentence about nothing."""
    from dataclasses import replace

    strength, contrast, sigma = strength_and_contrast
    projected = projection.join(strength.table, on="team", how="left")
    block = publish.build(
        projected, 2026, CONFIG, HEADLINE, BASIS,
        strength=replace(strength, promoted=()), contrast=contrast, sigma=sigma,
    )["schedule"]
    assert block["promotion_note"] is None


def test_the_contrast_headline_names_both_teams_and_both_swap_numbers(
    projection: pl.DataFrame, strength_and_contrast
) -> None:
    strength, contrast, sigma = strength_and_contrast
    if contrast is None:
        pytest.skip("this synthetic league has no inversion")
    projected = projection.join(strength.table, on="team", how="left")
    block = publish.build(
        projected, 2026, CONFIG, HEADLINE, BASIS,
        strength=strength, contrast=contrast, sigma=sigma,
    )["schedule"]["contrast"]

    assert contrast.higher_team in block["headline"]
    assert contrast.lower_team in block["headline"]
    assert f"{contrast.higher_on_lower_schedule:.1f}" in block["headline"]
    assert f"{contrast.lower_on_higher_schedule:.1f}" in block["headline"]
    assert block["higher_rank"] == 1


def test_no_schedule_means_no_block(projection: pl.DataFrame) -> None:
    """A fork with no CFBD archive has no schedule, so it has no schedule
    strength either. A card that renders neither is a smaller product."""
    assert publish.build(projection, 2026, CONFIG, HEADLINE, BASIS)["schedule"] is None


def test_the_schedule_extension_is_additive(
    projection: pl.DataFrame, strength_and_contrast
) -> None:
    """schema_version stays 1: keys appeared, none changed meaning, none went
    away. A consumer written against the original field set stays valid."""
    strength, contrast, sigma = strength_and_contrast
    projected = projection.join(strength.table, on="team", how="left")
    before = publish.build(projection, 2026, CONFIG, HEADLINE, BASIS)
    after = publish.build(
        projected, 2026, CONFIG, HEADLINE, BASIS,
        strength=strength, contrast=contrast, sigma=sigma,
    )
    assert after["schema_version"] == before["schema_version"] == publish.SCHEMA_VERSION
    assert set(before) <= set(after)
    for key in ("headline", "basis", "season", "status", "grading_start_week"):
        assert after[key] == before[key]
    assert set(before["rows"][0]) <= set(after["rows"][0])


def test_no_backtest_means_no_claim(projection: pl.DataFrame) -> None:
    """A caller that has not run the backtest gets a card that says nothing about
    quality, which is the correct behaviour for an unmeasured claim."""
    assert publish.build(projection, 2026, CONFIG, HEADLINE, BASIS)["backtest"] is None
    assert (
        publish.build(projection, 2026, CONFIG, HEADLINE, BASIS, backtest={})["backtest"]
        is None
    )
