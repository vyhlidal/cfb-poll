"""Team colours and the generated mark (report 06 §9.1).

The mark is the fallback for every logo slot, the whole site's rendering when
`[display].logos = false`, and the ONLY mark a share card may carry (§8.3). So it
is not decoration and it gets the same treatment as a published number: computed
once, published on the row, identical across both backends, and legible.

The committed `data/team-colors.csv` is checked as data, not as a file that
exists: coverage against every FBS team the loader produces, hex well-formedness,
and — the one that matters — that no published mark is illegible.
"""

from __future__ import annotations

import polars as pl
import pytest

from cfbpoll.config import load_config
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, canonical_games
from cfbpoll.ingest.teams import (
    COLOR_MAP_PATH,
    FIELDS,
    MIN_CONTRAST,
    PALETTE_MARK,
    contrast_ratio,
    load_colors,
    mark_for,
    relative_luminance,
)
from cfbpoll.publish.serving import team_dimension

COLORS = load_colors()

needs_archive = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised; run `cfbpoll archive sync`",
)


# ------------------------------------------------------------------ the committed map


def test_the_colour_map_is_committed_and_complete() -> None:
    assert COLOR_MAP_PATH.exists(), "data/team-colors.csv is a committed fact table"
    assert len(COLORS) == 138  # the three /teams/fbs pulls: 2021, 2023, 2026
    header = COLOR_MAP_PATH.read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(FIELDS)


def test_every_colour_is_a_well_formed_hex_pair() -> None:
    for team, entry in COLORS.items():
        for field in ("color", "alt_color"):
            value = entry[field]
            assert value and value.startswith("#") and len(value) == 7, (team, field, value)
            int(value[1:], 16)  # raises on a malformed digit


def test_no_logo_url_is_insecure_or_a_local_path() -> None:
    """Report 06 rule 1: we store references, never bytes — and never http://."""
    for team, entry in COLORS.items():
        for field in ("logo_light", "logo_dark"):
            url = entry[field]
            assert url and url.startswith("https://"), (team, field, url)


@needs_archive
def test_every_ranked_team_resolves_to_a_colour() -> None:
    """136 FBS team names across 2021-2025; the map covers all of them."""
    frame = canonical_games([2021, 2022, 2023, 2024, 2025])
    fbs = set(
        frame.filter(pl.col("home_class") == "fbs")["home_team"].to_list()
    ) | set(frame.filter(pl.col("away_class") == "fbs")["away_team"].to_list())
    assert len(fbs) == 136
    assert not (fbs - set(COLORS)), sorted(fbs - set(COLORS))


# ---------------------------------------------------------------------- the mark


def test_relative_luminance_endpoints() -> None:
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert relative_luminance("#ffffff") == pytest.approx(1.0)
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)


def test_every_published_mark_is_legible() -> None:
    """The point of the contrast repair, asserted over all 138 schools.

    23 of them publish a primary/alternate pair that fails at 28px — Washington
    State's own two colours sit at a contrast ratio of 1.1 — and a mark whose
    letters vanish is worse than no mark at all.
    """
    repaired = 0
    for team, entry in COLORS.items():
        mark = mark_for(entry)
        assert contrast_ratio(mark["bg"], mark["fg"]) >= MIN_CONTRAST, team
        repaired += int(mark["repaired"])
    assert repaired == 23


def test_the_repair_never_changes_the_background() -> None:
    """The background carries the identity; only the letters may move."""
    for entry in COLORS.values():
        assert mark_for(entry)["bg"] == entry["color"]


def test_an_unknown_team_gets_the_neutral_mark_not_an_error() -> None:
    """Report 06 §8.1: an unresolved team is a fallback-mark team, never a failure."""
    mark = mark_for(None, "Some New FBS Team")
    assert mark["bg"] == PALETTE_MARK["bg"]
    assert mark["fg"] == PALETTE_MARK["fg"]
    assert mark["label"] == "SOME"


def test_labels_are_short_and_upper_case() -> None:
    for entry in COLORS.values():
        label = mark_for(entry)["label"]
        assert 1 <= len(label) <= 4
        assert label == label.upper()


# --------------------------------------------------------- wired into the contract


@needs_archive
def test_team_dimension_publishes_the_mark() -> None:
    display = dict(load_config()["display"])
    assert display["mark_colors"] == "team"
    dimension = team_dimension(2023, DEFAULT_ARCHIVE, display)
    ohio = dimension["Ohio State"]
    assert ohio["mark_bg"] == COLORS["Ohio State"]["color"]
    assert ohio["mark_label"] == "OSU"
    assert ohio["team_color"] and ohio["team_alt_color"]
    fbs = [row for row in dimension.values() if row["classification"] == "fbs"]
    assert len(fbs) >= 130
    assert all(row["mark_bg"] and row["mark_fg"] and row["mark_label"] for row in fbs)


@needs_archive
def test_palette_mode_is_a_config_change_not_a_code_change() -> None:
    """Report 06 §6 rule 5: the reversible mode is built first and is one line."""
    display = dict(load_config()["display"])
    display["mark_colors"] = "palette"
    dimension = team_dimension(2023, DEFAULT_ARCHIVE, display)
    marks = {(row["mark_bg"], row["mark_fg"]) for row in dimension.values()}
    assert marks == {(PALETTE_MARK["bg"], PALETTE_MARK["fg"])}
    assert all(row["team_color"] is None for row in dimension.values())
    # The label survives, because it is what the neutral mark carries.
    assert dimension["Ohio State"]["mark_label"] == "OSU"


@needs_archive
def test_an_unknown_mark_mode_fails_loudly() -> None:
    display = dict(load_config()["display"])
    display["mark_colors"] = "rainbow"
    with pytest.raises(ValueError, match="mark_colors"):
        team_dimension(2023, DEFAULT_ARCHIVE, display)


def test_colours_are_display_only_and_banned_as_features() -> None:
    """A colour is as banned a feature as a conference name (report 02 §3.10)."""
    from cfbpoll.validate import leakage

    colour_fields = {"color", "alt_color", "mark_bg", "mark_fg", "mark_label"}
    for layer in leakage.LAYERS:
        assert not (set(layer.allowed) & colour_fields), layer.name
    assert "conference" in leakage.BANNED_COLUMN_PATTERNS
