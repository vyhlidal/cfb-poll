"""The projection fixture: `cfb-poll-data/<season>/projection.json`.

The site's contract, defined in `src/lib/cfb-poll/projection.ts` in the sandbox
app, and the two rules it binds this module to are the same two the poll's
fixtures already live under:

  1. THE SITE DERIVES NOTHING. Every number that appears on screen appears
     verbatim in a field here. `projected_wins` is a pre-formatted STRING, not a
     float, because a renderer that decides how many decimal places to show is a
     renderer that can disagree with the artifact.
  2. A MISSING FILE IS A LEGITIMATE ANSWER. The card renders "coming this week"
     rather than an error, so this module's failure mode is "write nothing".

`status` IS AUTHORITATIVE and is never inferred from the row count, which is what
lets a complete projection sit on disk, dark, until somebody decides to show it.

`basis` MUST BE A COMPLETE SENTENCE ending in a full stop: the card prints it and
then continues in the same paragraph, so a fragment produces prose that does not
parse. `_assert_sentence` enforces that here rather than trusting it, because the
failure is invisible in JSON and obvious on the page.

THE DISPLAY FIELDS COME FROM THE POLL'S OWN MACHINERY - `ingest/teams.mark_for`
and the `[display]` logo template - so a team's mark and logo cannot differ
between the projection card and the poll table sitting under it. That is not
tidiness: those two surfaces are on the same page, and a school whose colours
change between them would look like a bug in whichever one the reader trusts
less.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from cfbpoll.ingest import cfbd
from cfbpoll.ingest.teams import PALETTE_MARK, load_colors, mark_for
from cfbpoll.projection import PROJECTION_VERSION

__all__ = ["SCHEMA_VERSION", "build", "write"]

SCHEMA_VERSION = 1


def _assert_sentence(field: str, value: str) -> str:
    """A field the card continues from has to end like a sentence."""
    text = value.strip()
    if not text or text[-1] not in ".!?":
        raise ValueError(
            f"`{field}` must be a COMPLETE SENTENCE ending in a full stop - the "
            f"projection card prints it and continues in the same paragraph. Got: "
            f"{value!r}"
        )
    return text


def _conferences(season: int, archive_root: Any = None) -> dict[str, str | None]:
    """school -> conference for one season, from the archived `/teams/fbs` pull."""
    return {
        str(row.get("school")): (row.get("conference") or None)
        for row in cfbd.archived_teams(season, archive_root)
        if row.get("school")
    }


def _display(team: str, colors: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Logo URLs and the generated mark, exactly as `publish/serving.py` builds them."""
    display = config.get("display") or {}
    entry = colors.get(team)
    team_id = (entry or {}).get("team_id")

    urls: dict[str, str | None] = dict.fromkeys(
        ("logo_url", "logo_url_2x", "logo_url_dark", "logo_url_dark_2x")
    )
    if team_id is not None and bool(display.get("logos", True)):
        template = str(display["logo_url_template"])
        size = int(display.get("logo_size", 64))
        size_2x = int(display.get("logo_size_2x", 128))
        dark = str(display.get("logo_dark_variant", "-dark"))
        urls = {
            "logo_url": template.format(variant="", team_id=team_id, size=size),
            "logo_url_2x": template.format(variant="", team_id=team_id, size=size_2x),
            "logo_url_dark": template.format(variant=dark, team_id=team_id, size=size),
            "logo_url_dark_2x": template.format(variant=dark, team_id=team_id, size=size_2x),
        }

    if str(display.get("mark_colors", "team")) == "palette":
        label = ((entry or {}).get("abbreviation") or team)[:4].upper()
        mark = {"bg": PALETTE_MARK["bg"], "fg": PALETTE_MARK["fg"], "label": label}
    else:
        mark = mark_for(entry, (entry or {}).get("abbreviation") or team)

    return {
        "team_id": int(team_id) if team_id is not None else 0,
        **urls,
        "mark_bg": mark["bg"],
        "mark_fg": mark["fg"],
        "mark_label": mark["label"],
    }


def build(
    projection: pl.DataFrame,
    season: int,
    config: dict[str, Any],
    headline: str,
    basis: str,
    note: str | None = None,
    status: str = "published",
    published_at: str | None = None,
    top_n: int = 25,
    archive_root: Any = None,
) -> dict[str, Any]:
    """The fixture document. Every displayed number is a string or a plain scalar."""
    if status not in ("coming", "published"):
        raise ValueError(f"status must be 'coming' or 'published', got {status!r}")

    colors = load_colors()
    conferences = _conferences(season, archive_root)
    ranked = projection.filter(
        pl.col("projected_rank").is_not_null() & (pl.col("projected_rank") <= top_n)
    ).sort("projected_rank")

    rows: list[dict[str, Any]] = []
    for row in ranked.to_dicts():
        team = str(row["team"])
        entry = colors.get(team)
        wins = row.get("projected_wins")
        rows.append(
            {
                "rank": int(row["projected_rank"]),
                "team": team,
                "abbreviation": (entry or {}).get("abbreviation"),
                "conference": conferences.get(team),
                **_display(team, colors, config),
                # PRE-FORMATTED, per the contract. The site formats nothing, so
                # the decimal place is decided here, once, and cannot drift
                # between the card and the JSON a reader downloads.
                "projected_wins": (f"{float(wins):.1f}" if wins is not None else None),
                "note": _note(row),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "season": int(season),
        "status": status,
        "published_at": published_at,
        "grading_start_week": int(config["publication"]["headline_start_week"]),
        "headline": _assert_sentence("headline", headline),
        "basis": _assert_sentence("basis", basis),
        "note": _assert_sentence("note", note) if note else None,
        "rows": rows,
        # Not in the site's interface, and carried anyway: a published guess that
        # cannot say which recipe made it cannot be graded season over season.
        "projection_version": PROJECTION_VERSION,
    }


def _note(row: dict[str, Any]) -> str | None:
    """One templated clause about this team. Never hand-written, per the contract.

    Names the single largest offseason term - the one thing this projection says
    about a team that carrying last season's rating forward would not have said.
    Teams whose projection is pure mean reversion get no clause rather than a
    manufactured one.
    """
    candidates = {
        "Returning production": row.get("contrib_returning_production") or 0.0,
        "A new head coach": row.get("contrib_coaching_change") or 0.0,
        "Net portal flow": row.get("contrib_net_portal") or 0.0,
    }
    name, value = max(candidates.items(), key=lambda item: (abs(item[1]), item[0]))
    points = float(value)
    if abs(points) < 0.5:
        return None
    if points > 0:
        return f"{name} adds {points:.1f} points to the projection."
    return f"{name} costs the projection {abs(points):.1f} points."


def write(document: dict[str, Any], destination: Path) -> Path:
    """Write `<destination>/<season>/projection.json`. Returns the path."""
    target = Path(destination) / str(document["season"]) / "projection.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    return target
