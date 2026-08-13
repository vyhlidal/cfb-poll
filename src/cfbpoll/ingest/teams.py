"""Team colours, and the generated mark built from them.

Report 06 §9.1 asked for one thing on day one: "a rounded square in the team's
primary color carrying its 2-4 letter abbreviation in the alternate color", built
as the fallback for every logo slot and as the ONLY mark the share cards may ever
use (§8.3). This module is the data half of that. It costs two hex values per
team, and report 06 §8.1 notes they ride along on a `/teams/fbs` request the
weekly job already makes, so they cost no extra call.

WHY THIS FILE IS COMMITTED WHEN `archive/cfbd/` IS NOT.
CFBD terms §3 bars redistributing raw API responses, and `archive/cfbd/` is
gitignored accordingly. `data/team-colors.csv` is not a raw response: it is a
seven-column derived table of a team's name, its id, its abbreviation and two hex
colours. Those are facts about institutions - uncopyrightable under *Feist*, the
same position LICENSE-DATA.md §2 already takes for scores and opponents - and the
file is committed for the reason report 06 §8.1 gives: "resolve the crosswalk join
once, commit the resulting map as a small CSV, and treat an unresolved team as a
fallback-mark team rather than an error." Committing it is what keeps a fork's
marks identical to ours without a key.

NO BYTES, EVER (report 06 §6 rule 1, which does all the legal work). This file
stores an id and two colours. `logo_light`/`logo_dark` are URLs, recorded because
report 06 §9.2 rates "ESPN blocks hotlinking" as the single most likely risk in the
whole design and a second independent source is worth two columns. Nothing here
downloads, caches, commits or serves an image.

ONE CORRECTION TO REPORT 06 §8.1, measured 2026-08-12. It warned that CFBD's
`logos[]` "passes through a mix of `http://` and `https://` URLs - 346 against 492"
and that rendering the field raw causes mixed-content failures on ~40% of teams.
That is no longer true: CFBD now serves logos from its own CDN
(`cdn.collegefootballdata.com`) and every URL in all 138 teams' `logos[]` is
https. The recommendation still stands for a different reason - storing the id and
building the URL is what makes the size and theme variants derivable - but the
mixed-content bug it was defending against is gone.

WHAT THE THREE PULLS MEASURED (2021, 2023, 2026 - one call each, 130 / 133 / 138
teams, 138 distinct schools):

  - colour coverage 138/138, every value a well-formed `#rrggbb`
  - all 136 FBS team names our loader produces for 2021-2025 resolve; zero misses,
    so the fallback-mark-for-unresolved-team path is untested by real data and
    exists for the seasons ahead
  - team ids identical across all three pulls
  - colours identical across all three pulls - not one school drifted

STATUS: real, offline. Reads archived `/teams/fbs` bodies; never opens a socket.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from cfbpoll.config import REPO_ROOT

__all__ = [
    "COLOR_MAP_PATH",
    "FIELDS",
    "PALETTE_MARK",
    "build_color_map",
    "contrast_ratio",
    "load_colors",
    "mark_for",
    "relative_luminance",
]

COLOR_MAP_PATH = REPO_ROOT / "data" / "team-colors.csv"

FIELDS: tuple[str, ...] = (
    "team",
    "team_id",
    "abbreviation",
    "color",
    "alt_color",
    "logo_light",
    "logo_dark",
    "seasons",
)

#: The mark a team with no colour entry gets. Neutral on purpose: it must be
#: obviously "we do not have this team's colours" rather than a plausible-looking
#: wrong guess, and it must be legible in both themes.
PALETTE_MARK = {"bg": "#3f4650", "fg": "#ffffff"}

#: WCAG AA for large text. The abbreviation in a 28px disc is large text, and a
#: mark that fails it is a mark a reader cannot use. Report 06 §9.1's argument for
#: the generated mark is that it is MORE legible at 28px than a mascot logo, which
#: is only true if we enforce it.
MIN_CONTRAST = 3.0

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clean_hex(value: Any) -> str | None:
    """`'#003594'` or `'003594'` -> `'#003594'`; anything else -> None."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if candidate and not candidate.startswith("#"):
        candidate = "#" + candidate
    return candidate.lower() if _HEX.match(candidate) else None


def relative_luminance(hex_color: str) -> float:
    """WCAG 2.x relative luminance of an `#rrggbb` string."""
    raw = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(raw[i : i + 2], 16) / 255.0
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two `#rrggbb` strings, 1.0 to 21.0."""
    la, lb = relative_luminance(a), relative_luminance(b)
    lo, hi = sorted((la, lb))
    return (hi + 0.05) / (lo + 0.05)


def mark_for(entry: dict[str, Any] | None, label: str | None = None) -> dict[str, Any]:
    """The generated mark for one team: background, foreground, and the label.

    PUBLISHED, NOT DERIVED IN THE BROWSER. Report 05 §7.2 forbids either renderer
    computing a derived quantity, and "which of these two hex values is legible on
    the other" is exactly such a quantity. Computing it here means the site, the
    static fork and the share card cannot disagree about what a team's mark looks
    like.

    The contrast repair is the whole reason this is a function rather than two
    columns. A team's own two colours are frequently a poor pair - one school
    publishes the same value twice - and a mark whose letters vanish into its
    background is worse than no mark. Where the pair fails `MIN_CONTRAST` the
    foreground falls back to whichever of black or white passes, and the
    background, which carries the team's identity, is never changed.
    """
    text = (label or (entry or {}).get("abbreviation") or "")[:4].upper()
    bg = _clean_hex((entry or {}).get("color"))
    if bg is None:
        return {**PALETTE_MARK, "label": text, "repaired": False}
    fg = _clean_hex((entry or {}).get("alt_color"))
    if fg is not None and contrast_ratio(bg, fg) >= MIN_CONTRAST:
        return {"bg": bg, "fg": fg, "label": text, "repaired": False}
    white, black = "#ffffff", "#000000"
    best = white if contrast_ratio(bg, white) >= contrast_ratio(bg, black) else black
    return {"bg": bg, "fg": best, "label": text, "repaired": True}


def load_colors(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """The committed map, team name -> row. `{}` when the file is not there."""
    target = Path(path or COLOR_MAP_PATH)
    if not target.exists():
        return {}
    with target.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out[row["team"]] = {
            "team": row["team"],
            "team_id": int(row["team_id"]) if row["team_id"] else None,
            "abbreviation": row["abbreviation"] or None,
            "color": row["color"] or None,
            "alt_color": row["alt_color"] or None,
            "logo_light": row["logo_light"] or None,
            "logo_dark": row["logo_dark"] or None,
            "seasons": row["seasons"],
        }
    return out


def _pick_logo(logos: Any, dark: bool) -> str | None:
    """The 500px light or dark logo URL from CFBD's `logos[]`, or None.

    Selected by path rather than by index: the array's order is not documented and
    an index would break silently if it changed.
    """
    if not isinstance(logos, list):
        return None
    want = "/logos-dark/500/" if dark else "/logos/500/"
    for url in logos:
        if isinstance(url, str) and want in url and url.startswith("https://"):
            return url
    return None


def build_color_map(
    seasons: list[int] | tuple[int, ...] | None = None,
    archive_root: str | Path | None = None,
    dest: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Rebuild `data/team-colors.csv` from every archived `/teams/fbs` body.

    A LATER SEASON WINS on any field, because a rebrand should propagate and a
    stale colour should not. `seasons` is recorded per team so a reader can see
    which pulls a row was built from without opening the private archive.

    Idempotent: running it twice over the same archive writes the same bytes.
    """
    from cfbpoll.ingest import cfbd

    years = sorted(int(s) for s in (seasons or (2021, 2023, 2026)))
    merged: dict[str, dict[str, Any]] = {}
    seen: dict[str, list[int]] = {}
    for year in years:
        for row in cfbd.archived_teams(year, archive_root):
            school = row.get("school")
            if not school:
                continue
            seen.setdefault(school, []).append(year)
            merged[school] = {
                "team": school,
                "team_id": row.get("id"),
                "abbreviation": row.get("abbreviation") or "",
                "color": _clean_hex(row.get("color")) or "",
                "alt_color": _clean_hex(row.get("alternateColor")) or "",
                "logo_light": _pick_logo(row.get("logos"), dark=False) or "",
                "logo_dark": _pick_logo(row.get("logos"), dark=True) or "",
            }

    rows = []
    for school in sorted(merged):
        entry = dict(merged[school])
        entry["seasons"] = "|".join(str(y) for y in sorted(seen[school]))
        rows.append(entry)

    target = Path(dest or COLOR_MAP_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="" plus an explicit "\n" terminator: csv would otherwise emit CRLF
    # and the file would diff differently on Windows, which is the same
    # determinism rule publish/files.py obeys (report 03 §9.3).
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows
