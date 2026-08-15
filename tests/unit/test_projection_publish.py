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

HEADLINE = "This is the model's 2026 preseason projection, and it is a projection."
BASIS = "It is the model's August guess, built from last season's final ratings."


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
    """Not in the site's interface, and carried anyway: a published guess that
    cannot say which recipe made it cannot be graded season over season."""
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
