"""The weekly share card: SVG in the pipeline, PNG beside it, no logos ever.

Specified by report 05 §6 and report 06 §8.3.

WHY THE PYTHON JOB RENDERS THIS AND NOT NEXT.JS (report 05 §6.1, four reasons,
the first two of which decide it):

  1. The static fork needs the image and a Next route cannot give it one.
     `ImageResponse` runs on the edge runtime and "Edge runtime does not support
     static rendering"; `output: export` needs everything prerenderable. A file in
     `out/` ships identically with no Node toolchain at all.
  2. A share card is a published claim and must be immutable. `cfb_poll_published`
     is append-only because "a poll that can be quietly rewritten is not a
     published record". An og-image route regenerates from whatever is in the
     database now; a hashed PNG in a release asset is frozen at publication and
     can be checked against its sha256 years later. The card should have the same
     integrity property as the poll it depicts.

NO SCHOOL LOGO, EVER, AND THE RULE IS TESTED (report 06 §8.3, §8.4). The renderer
draws GENERATED MARKS ONLY - a disc in the team's primary colour from
`data/team-colors.csv` - and issues no network request of any kind. There is no
`<image>` element in a card, no external href, and no path to one:
`tests/unit/test_share_cards.py` is the CI guard report 06 §8.4 asked for, and it
fails the build on an `<image>` element, on any external host in a card SVG, and
on an image file appearing anywhere in the tree outside a named allow-list. The
tempting mistake it exists to catch is someone adding a logo "just for the top 3".

DETERMINISM, precisely, because the honest claim is narrower than "deterministic":

  - THE SVG IS A PURE FUNCTION OF THE PUBLISHED DOCUMENTS, byte for byte, on any
    machine. No wall clock, no RNG, no dict iteration order, every float formatted
    to a fixed precision, every collection sorted before it is drawn. This is the
    artifact that gets diffed and reviewed.
  - THE PNG IS DETERMINISTIC GIVEN THE SAME RENDERER AND THE SAME FONTS. resvg
    resolves `font-family` against the host's installed fonts, so a machine with a
    different font stack produces different glyph rasterisation. The test asserts
    byte-identity across two renders in one environment and checks the committed
    sample structurally rather than by hash, which is what can honestly be
    asserted rather than what would be nice to claim.

WHICH VARIANT THIS BUILDS. Report 05 §6.2's headline card is a top-ten table, and
there is no headline poll to put on one yet. What exists is the weeks 1-4 launch
product - the schedule graph and its diagnostics, report 05 §6.2's
`share/2026-w03-connectivity.png` - so that is the variant implemented here, and
it is also the more interesting one to publish first: no other poll's share image
shows you the graph its ranking is standing on.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from cfbpoll.publish.serving import Bundle, build

__all__ = [
    "BUILDERS",
    "CARD_HEIGHT",
    "CARD_WIDTH",
    "FONT_DIR",
    "PALETTE",
    "SAFE_TOP",
    "TALL_HEIGHT",
    "VARIANTS",
    "connectivity_svg",
    "export",
    "fonts_are_vendored",
    "render_png",
    "stripe_colour",
    "top10_svg",
    "top25_instagram_svg",
    "top25_x_svg",
]

#: 1200x628 is the `summary_large_image` ratio (report 05 §6.2). The 5 MB ceiling
#: is a hard build failure in Next.js and we are three orders of magnitude inside
#: it, because this card is flat colour and straight lines.
CARD_WIDTH = 1200
CARD_HEIGHT = 628

#: 1200x1500 is 4:5, the tallest ratio Instagram serves in feed. X renders 4:5
#: as a tap-to-expand thumbnail rather than inline, which is why the top 25
#: ships on BOTH this canvas and the 628 one rather than picking a compromise
#: that is native to neither.
TALL_HEIGHT = 1500

#: X crops the top and bottom on mobile, so the essential content lives in the
#: middle ~60% (report 05 §6.2). The title band and the constants footer sit
#: OUTSIDE it deliberately - they are the signature, not the message, and a reader
#: who sees only the middle still gets the whole point.
SAFE_TOP = 126
SAFE_BOTTOM = CARD_HEIGHT - 126

#: `top25_x` and `top25_instagram` are the same table on two canvases and are
#: separate variants rather than one variant with an option, because each is a
#: published artifact with its own sha256 and neither is a derivative of the
#: other.
VARIANTS: tuple[str, ...] = ("connectivity", "top10", "top25_x", "top25_instagram")

#: One dark palette, fixed. A share card has no theme toggle: it is a PNG in
#: somebody else's timeline, and it has to hold up against both a white and a
#: black surrounding page, which a dark card with high-contrast type does.
#:
#: THE ACCENT IS GOLD AND IT OBEYS ONE RULE: it is either a filled slab with
#: `brand_ink` drawn on top of it, or it is the odds/key numeral. Never a
#: hairline, never a border, never body text. That single rule is what keeps a
#: card carrying big numbers from reading as a betting advertisement, which is
#: the failure mode nearest to this design.
PALETTE: dict[str, str] = {
    "bg": "#0B0C0F",
    "panel": "#15181D",
    "rule": "#262A31",
    "ink": "#F4F2ED",
    "ink_dim": "#A2A8B0",
    "ink_faint": "#6C737C",
    "edge": "#3A4048",
    "accent": "#F0B429",
    # Ink drawn ON an accent slab. `ink` on gold fails contrast; this does not.
    "brand_ink": "#0B0C0F",
    # The team stripe when a row carries no colour. Drawn either way, never
    # omitted: a missing box would misalign the row grid on exactly the rows
    # whose data is weakest.
    "stripe_fallback": "#3A4048",
    # The uncertainty rail is EVIDENCE and is deliberately not gold. Gold is the
    # key. A rail in the accent colour would read as the thing being celebrated
    # rather than the thing being admitted.
    "rail_track": "#2A2F36",
    "rail_band": "#C9D0D8",
}

#: Four roles rather than two, because the card now has a voice: a condensed
#: display face for the wordmark and rank numerals, a text face for team names,
#: a mono for every number, and a serif for the one prose line.
#:
#: THE PRIMARY FAMILIES ARE SHIPPED IN-REPO AND THE RASTER NO LONGER DEPENDS ON
#: THE HOST, which fixes a latent defect rather than adding a feature. The old
#: stack led with "DejaVu Sans", which is not installed on the machine that has
#: been rendering these cards, so every card this project ever produced was
#: rasterised in Helvetica while the SVG claimed DejaVu. A published artifact
#: with a sha256 should not be able to say that. `render_png` pins
#: `skip_system_fonts=True` and loads `FONT_DIR`, so the same bytes come out on
#: any machine with the repo.
#:
#: The fallbacks after the primary are kept in the stack for one reason: the SVG
#: is also read directly, in a browser, by anybody reviewing a diff, and there
#: it should degrade to something with the right proportions rather than to a
#: default serif.
#: EVERY MULTI-WORD FAMILY IS QUOTED, AND THAT IS A BUG FIX RATHER THAN A STYLE
#: CHOICE. An unquoted CSS family name is a sequence of IDENTIFIERS, and an
#: identifier may not begin with a digit - so `Source Serif 4` is not merely an
#: unusual spelling, it is invalid, and a parser that meets the bare `4` discards
#: THE WHOLE DECLARATION rather than that one family. The prose line on every
#: share card was therefore rendering as nothing at all: not in Source Serif, not
#: in the DejaVu Serif sitting next in the stack, not in Georgia - blank, because
#: the list never got parsed and the fallbacks never got their turn. Measured
#: against the vendored fonts, `Source Serif 4, DejaVu Serif, Georgia, ...`
#: rasterises to the identical bytes as a family name that does not exist, and
#: `'Source Serif 4', DejaVu Serif, ...` rasterises to Source Serif.
#:
#: The other three stacks were parsing correctly, since a multi-word name with no
#: digit is valid unquoted. They are quoted anyway: the rule "quote the family
#: name" is one a reader can apply, and "quote it unless every word happens to
#: start with a letter" is a rule that will be got wrong the next time a family
#: with a number in its name is added - which, for a typeface, is often.
FONT_DISPLAY = "'Archivo SemiCondensed', Archivo, 'DejaVu Sans Condensed', Helvetica, sans-serif"
FONT_UI = "Archivo, 'DejaVu Sans', Helvetica, Arial, sans-serif"
FONT_MONO = "'JetBrains Mono', 'DejaVu Sans Mono', Menlo, Consolas, monospace"
FONT_PROSE = "'Source Serif 4', 'DejaVu Serif', Georgia, 'Times New Roman', serif"

#: Backwards-compatible alias. `connectivity_svg` was written against these two
#: names and its layout is tuned to their metrics, so it keeps them rather than
#: being re-tuned in a commit that is about a different card.
FONT_STACK = FONT_UI

#: Where the shipped families live. Kept as a module constant so the renderer,
#: the test and the packaging step cannot disagree about the path.
#:
#: DEJAVU CONTRIBUTES ZERO BYTES TO EVERY CARD THIS PROJECT CURRENTLY RENDERS, and
#: it stays anyway. Measured: rasterising a card with the DejaVu directory removed
#: produces identical bytes, because Archivo, JetBrains Mono and Source Serif 4
#: cover every glyph in every team name and every number on the board today. So a
#: reader auditing `assets/` will find 1.5 MB of apparent dead weight and be
#: tempted to delete it. Do not.
#:
#: It is the MISSING-GLYPH FALLBACK, and the thing it protects against is not
#: visible until it happens. `skip_system_fonts=True` means there is no host font
#: to catch a character the three primaries lack: the renderer draws a tofu box,
#: onto a 1200x628 PNG, which is then hashed, published and shared. School names
#: travel through these cards and the FBS roster is not a closed set - a promoted
#: programme, a diacritic, a punctuation mark somebody types into a note field.
#: The cost of carrying the fallback is 1.5 MB in a repository whose heavy data
#: already ships as release assets rather than in the tree. The cost of not
#: carrying it is a published artifact with a box in the middle of a team's name.
FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"


def _esc(value: Any) -> str:
    """XML-escape. Team names carry apostrophes (`Hawai'i`) and ampersands."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _n(value: float) -> str:
    """Fixed-precision coordinate. Never `repr(float)`, which is platform-shaped."""
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def _clip(text: str, limit: int) -> str:
    """Hard character budget per line. The card has no reflow and must not overrun."""
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _wrap(text: str, limit: int, lines: int) -> list[str]:
    """Greedy word wrap to a character budget. The card has no text layout engine.

    A character budget rather than a measured width because the raster's font is
    the host's and its metrics are not knowable here. The budgets are set from the
    widest plausible glyph run, so a line is short before it is ever long.
    """
    words, out, current = str(text).split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        out.append(current)
        current = word
        if len(out) == lines:
            break
    if current and len(out) < lines:
        out.append(current)
    if len(out) == lines and len(" ".join(out)) < len(str(text).strip()):
        out[-1] = _clip(out[-1] + " …", limit)
    return out


def _text(
    x: float,
    y: float,
    content: str,
    *,
    size: float,
    fill: str,
    weight: str = "normal",
    anchor: str = "start",
    family: str = FONT_STACK,
    spacing: float | None = None,
) -> str:
    attrs = [
        f'x="{_n(x)}"',
        f'y="{_n(y)}"',
        f'font-family="{family}"',
        f'font-size="{_n(size)}"',
        f'fill="{fill}"',
    ]
    if weight != "normal":
        attrs.append(f'font-weight="{weight}"')
    if anchor != "start":
        attrs.append(f'text-anchor="{anchor}"')
    if spacing is not None:
        attrs.append(f'letter-spacing="{_n(spacing)}"')
    return f"<text {' '.join(attrs)}>{_esc(content)}</text>"


def _srgb_to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(value: float) -> float:
    return value * 12.92 if value <= 0.0031308 else 1.055 * (value ** (1 / 2.4)) - 0.055


def _hex_to_oklch(colour: str) -> tuple[float, float, float]:
    """sRGB hex -> OKLCH. Pure arithmetic, no dependency, deterministic."""
    text = colour.lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    r, g, b = (_srgb_to_linear(int(text[i : i + 2], 16) / 255.0) for i in (0, 2, 4))

    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)

    lightness = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_axis = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return lightness, math.hypot(a, b_axis), math.atan2(b_axis, a)


def _oklch_to_hex(lightness: float, chroma: float, hue: float) -> str:
    a, b_axis = chroma * math.cos(hue), chroma * math.sin(hue)
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b_axis) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b_axis) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b_axis) ** 3

    r = +4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    b = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_

    out = []
    for channel in (r, g, b):
        srgb = _linear_to_srgb(max(0.0, min(1.0, channel)))
        out.append(f"{round(max(0.0, min(1.0, srgb)) * 255):02x}")
    return "#" + "".join(out)


#: The legibility band a team stripe is clamped into, on THIS background.
#: Navy sits near black on #0B0C0F and vanishes; a neon green shouts over every
#: number beside it. Clamping lightness into a band and capping chroma puts every
#: school in the same visual register while keeping each one recognisably itself.
STRIPE_L_RANGE = (0.55, 0.74)
STRIPE_C_MAX = 0.16


def stripe_colour(mark_bg: Any) -> str:
    """A team's primary, clamped into the card's legibility band. Never fails.

    A null, blank or unparseable value returns `stripe_fallback` rather than
    raising: the stripe is drawn on every row either way, because a row that
    omitted its box would break the grid on exactly the rows whose data is
    weakest.
    """
    text = str(mark_bg or "").strip()
    if not text.startswith("#") or len(text.lstrip("#")) not in (3, 6):
        return PALETTE["stripe_fallback"]
    try:
        lightness, chroma, hue = _hex_to_oklch(text)
    except (ValueError, ZeroDivisionError):
        return PALETTE["stripe_fallback"]
    lightness = max(STRIPE_L_RANGE[0], min(STRIPE_L_RANGE[1], lightness))
    return _oklch_to_hex(lightness, min(chroma, STRIPE_C_MAX), hue)


def _mark_disc(x: float, y: float, radius: float, row: dict[str, Any]) -> str:
    """The generated mark. NO SCHOOL LOGO, EVER, and the CI guard enforces it.

    `tests/unit/test_share_cards.py` fails the build on an `<image>` element or
    an external host in a card. Hotlinking a logo for identification is the
    site's position and it rests on the disclaimer strip, the licence footer and
    a link back to the source; a PNG in somebody's timeline carries none of those
    and travels further than all of them.
    """
    label = _clip(str(row.get("mark_label") or row.get("abbreviation") or "")[:4], 4)
    return (
        f'<circle cx="{_n(x)}" cy="{_n(y)}" r="{_n(radius)}" '
        f'fill="{_esc(row.get("mark_bg") or PALETTE["stripe_fallback"])}"/>'
        + _text(
            x,
            y + radius * 0.34,
            label,
            size=radius * 0.86,
            fill=_esc(row.get("mark_fg") or PALETTE["ink"]),
            weight="700",
            anchor="middle",
            family=FONT_DISPLAY,
        )
    )


def _lens_banner(week_view: dict[str, Any]) -> str | None:
    """The alternate-lens marker, verbatim, or None for the published poll.

    REQUIRED BY CONTRACT AND NOT A STYLE CHOICE. `docs/fixture-contract-recipes.md`
    §4: `label` is non-null exactly when the document is not the published poll,
    it is "the same string in both publication targets and on the share cards",
    and when non-null the surface must show it. A card is the artifact most
    likely to arrive with no context at all, so this is the surface where
    dropping it would do the most damage.
    """
    label = ((week_view.get("recipe") or {}).get("label")) or None
    return str(label) if label else None


def _slab(x: float, y: float, width: float, height: float, fill: str) -> str:
    return (
        f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(width)}" height="{_n(height)}" fill="{fill}"/>'
    )


def _left_panel(
    week_view: dict[str, Any], panel_w: float, height: float, thesis_size: float
) -> list[str]:
    """Wordmark, gold bar, eyebrow, lens marker, thesis. Shared by both variants.

    THE THESIS IS `recipe.one_liner`, WHICH IS A PUBLISHED FIELD. It is not copy
    typed into this renderer, so a card made under an alternate lens states that
    lens's own argument rather than the house one, and nobody has to remember to
    change a string here when a recipe's prose changes.
    """
    season, week = int(week_view["season"]), int(week_view["week"])
    parts: list[str] = [_slab(0, 0, panel_w, height, PALETTE["panel"])]
    parts.append(
        f'<line x1="{_n(panel_w)}" y1="0" x2="{_n(panel_w)}" y2="{_n(height)}" '
        f'stroke="{PALETTE["rule"]}" stroke-width="1"/>'
    )

    x, y = 32.0, 96.0
    parts.append(
        _text(x, y, "THE POLL", size=30, fill=PALETTE["ink"], weight="800",
              anchor="start", family=FONT_DISPLAY, spacing=1.8)
    )
    # The gold bar under the wordmark: a filled slab, which is one of the two
    # sanctioned uses of the accent. Width is measured off the type size rather
    # than guessed, so it tracks the wordmark on any face.
    parts.append(_slab(x, y + 12, 30 * 0.62 * len("THE POLL"), 6, PALETTE["accent"]))

    y += 56
    parts.append(
        _text(x, y, f"{season} · WEEK {week}", size=16, fill=PALETTE["ink_dim"],
              weight="700", family=FONT_DISPLAY, spacing=1.6)
    )

    banner = _lens_banner(week_view)
    if banner:
        y += 30
        # An accent slab with brand_ink on it: the second sanctioned use.
        parts.append(_slab(x - 6, y - 14, panel_w - (x - 6) - 26, 24, PALETTE["accent"]))
        parts.append(
            _text(x, y + 3, _clip(banner, 34), size=13, fill=PALETTE["brand_ink"],
                  weight="700", family=FONT_DISPLAY, spacing=0.8)
        )

    thesis = str((week_view.get("recipe") or {}).get("one_liner") or "")
    if thesis:
        y += 58
        budget = max(12, int((panel_w - x - 26) / (thesis_size * 0.46)))
        for line in _wrap(thesis, budget, 5):
            parts.append(
                _text(x, y, line, size=thesis_size, fill=PALETTE["ink"], family=FONT_PROSE)
            )
            y += thesis_size * 1.09
    return parts


def _top_banner(week_view: dict[str, Any], width: float, height: float) -> list[str]:
    """The header as a full-width band, for the tall canvas.

    A 4:5 card cannot use the 16:9 card's left panel: a 392px column beside a
    1500px-tall page is a stripe of empty space, and it squeezes the table into
    three columns so narrow that a team name collides with its own odds. That is
    exactly what the first attempt did. Portrait wants a banner across the top
    and the full width for the rows underneath.
    """
    season, week = int(week_view["season"]), int(week_view["week"])
    parts: list[str] = [
        _slab(0, 0, width, height, PALETTE["panel"]),
        f'<line x1="0" y1="{_n(height)}" x2="{_n(width)}" y2="{_n(height)}" '
        f'stroke="{PALETTE["rule"]}" stroke-width="1"/>',
    ]
    x, y = 40.0, 104.0
    parts.append(
        _text(x, y, "THE POLL", size=46, fill=PALETTE["ink"], weight="800",
              family=FONT_DISPLAY, spacing=2.6)
    )
    parts.append(_slab(x, y + 18, 46 * 0.62 * len("THE POLL"), 8, PALETTE["accent"]))
    parts.append(
        _text(width - 40, y, f"{season} · WEEK {week}", size=22, fill=PALETTE["ink_dim"],
              weight="700", anchor="end", family=FONT_DISPLAY, spacing=2.0)
    )

    y += 78
    banner = _lens_banner(week_view)
    if banner:
        parts.append(_slab(x - 8, y - 18, min(width - 80, 13 * len(banner) + 16), 30,
                           PALETTE["accent"]))
        parts.append(
            _text(x, y + 3, _clip(banner, 60), size=16, fill=PALETTE["brand_ink"],
                  weight="700", family=FONT_DISPLAY, spacing=1.0)
        )
        y += 48

    thesis = str((week_view.get("recipe") or {}).get("one_liner") or "")
    if thesis:
        for line in _wrap(thesis, int((width - 80) / (30 * 0.46)), 2):
            parts.append(_text(x, y, line, size=30, fill=PALETTE["ink"], family=FONT_PROSE))
            y += 34
    return parts


def _constants_strip(week_view: dict[str, Any], width: float, height: float) -> list[str]:
    """The constants footer. NEVER DROPPED FOR SPACE, on either variant.

    No other poll's share image carries its model constants. That line is the
    signature, and the X variant is the one most likely to get squeezed until it
    falls off, so it is drawn from the same function on both canvases.
    """
    footer = list((week_view.get("params") or {}).get("footer_lines") or [])
    top = height - 60
    parts = [
        _slab(0, top, width, 60, PALETTE["panel"]),
        f'<line x1="0" y1="{_n(top)}" x2="{_n(width)}" y2="{_n(top)}" '
        f'stroke="{PALETTE["rule"]}" stroke-width="1"/>',
    ]
    y = top + 24
    for line in footer[:2]:
        parts.append(
            _text(32, y, _clip(line, 118), size=15, fill=PALETTE["ink_faint"], family=FONT_MONO)
        )
        y += 19
    parts.append(
        _text(width - 32, top + 24, "sb.unleashepic.com/cfb-poll", size=15,
              fill=PALETTE["ink_dim"], anchor="end", family=FONT_MONO)
    )
    return parts


def _graph_panel(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    teams: dict[str, dict[str, Any]],
    box: tuple[float, float, float, float],
    named_bridges: set[frozenset[int]],
) -> list[str]:
    """The schedule graph, drawn from the published layout. No layout is computed.

    `connectivity.nodes` already carries `x`/`y` in [0, 1] from the serving
    contract, so this function places rather than solves - the same rule the
    website obeys, applied to a raster. A card that ran its own force-directed
    layout would show a different graph from the site's, which is precisely the
    class of drift report 05 §7.2 exists to prevent.

    FBS teams take their generated mark's background colour. Everyone else is
    drawn faint: an FCS opponent is a real node of the schedule graph and hiding
    it would misrepresent what the fit is standing on, but it is not what the
    reader is looking for.

    `named_bridges` IS NOT `edge["bridge"]`, AND THE DIFFERENCE IS THE WHOLE
    REASON THIS ARGUMENT EXISTS. The edge flag is the raw graph-theoretic cut set;
    the `bridge games` diagnostic beside the graph counts only the cut edges that
    strand at least two teams, because "a cut edge that strands one team is
    arithmetic; a cut edge that strands forty is a headline". In 2023 week 10
    those are 34 and 0 respectively. Highlighting the raw flag would put 34
    accented lines on a card whose own rail reads BRIDGE GAMES 0, which is a
    contradiction a reader can see in one glance, on the single artifact most
    likely to travel without its context.
    """
    left, top, width, height = box
    out: list[str] = [f'<g clip-path="url(#panel)" transform="translate({_n(left)},{_n(top)})">']

    place = {}
    for node in sorted(nodes, key=lambda n: str(n["team"])):
        place[int(node["team_id"])] = (
            float(node["x"]) * width,
            float(node["y"]) * height,
            str(node.get("classification") or "unknown"),
            str(node["team"]),
            int(node.get("degree") or 0),
        )

    # Edges first, so no line crosses a node. Sorted so the file is stable.
    lines: list[str] = []
    for edge in sorted(edges, key=lambda e: (int(e["source"]), int(e["target"]))):
        a, b = place.get(int(edge["source"])), place.get(int(edge["target"]))
        if a is None or b is None:
            continue
        named = frozenset((int(edge["source"]), int(edge["target"]))) in named_bridges
        stroke = PALETTE["accent"] if named else PALETTE["edge"]
        opacity = "0.95" if named else "0.5"
        lines.append(
            f'<line x1="{_n(a[0])}" y1="{_n(a[1])}" x2="{_n(b[0])}" y2="{_n(b[1])}" '
            f'stroke="{stroke}" stroke-opacity="{opacity}"/>'
        )
    out.append(f'<g stroke-width="0.7">{"".join(lines)}</g>')

    discs: list[str] = []
    for _, (x, y, klass, team, degree) in sorted(place.items()):
        if klass == "fbs":
            fill = (teams.get(team) or {}).get("mark_bg") or PALETTE["ink_dim"]
            radius = 3.4 if degree < 12 else 4.2
            discs.append(
                f'<circle cx="{_n(x)}" cy="{_n(y)}" r="{_n(radius)}" fill="{fill}" '
                f'stroke="{PALETTE["bg"]}" stroke-width="0.8"/>'
            )
        else:
            discs.append(
                f'<circle cx="{_n(x)}" cy="{_n(y)}" r="2" fill="{PALETTE["ink_faint"]}" '
                f'fill-opacity="0.55"/>'
            )
    out.append("".join(discs))
    out.append("</g>")
    return out


def connectivity_svg(bundle: Bundle) -> str:
    """The weeks 1-4 card: the schedule graph, its diagnostics, and the constants.

    Every number on it is read out of the published documents. Nothing here
    computes a derived quantity, for the same reason no renderer may (report 05
    §7.2): a share card that disagreed with the page it links to would be the
    single most damaging kind of inconsistency this project could ship.
    """
    conn = bundle.views["connectivity"]
    week_view = bundle.views["week"]
    teams = {row["school"]: row for row in bundle.tables["cfb_teams"]}
    params = week_view.get("params") or {}
    footer = list(params.get("footer_lines") or [])

    season, week = int(conn["season"]), int(conn["week"])
    provisional = bool(week_view.get("provisional"))
    label = str(conn.get("provisional_label") or week_view.get("provisional_label") or "")

    panel = (54.0, 148.0, 700.0, 316.0)
    by_name = {str(n["team"]): int(n["team_id"]) for n in conn["nodes"]}
    named_bridges = {
        frozenset((by_name[g["home"]], by_name[g["away"]]))
        for g in (conn.get("bridge_games") or [])
        if g.get("home") in by_name and g.get("away") in by_name
    }
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" '
        f'viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img" '
        f'aria-label="{_esc(f"Schedule connectivity, {season} week {week}")}">',
        "<defs>"
        f'<clipPath id="panel"><rect x="0" y="0" width="{_n(panel[2])}" '
        f'height="{_n(panel[3])}" rx="10"/></clipPath>'
        "</defs>",
        f'<rect width="{CARD_WIDTH}" height="{CARD_HEIGHT}" fill="{PALETTE["bg"]}"/>',
    ]

    # --- title band. Outside the mobile-safe zone on purpose (report 05 §6.2).
    parts.append(
        _text(
            54,
            58,
            f"THE POLL · {season} · WEEK {week}",
            size=27,
            fill=PALETTE["ink"],
            weight="bold",
            spacing=2.2,
        )
    )
    parts.append(
        _text(
            CARD_WIDTH - 54,
            58,
            _clip(label, 58) if provisional and label else "SCHEDULE CONNECTIVITY",
            size=15,
            fill=PALETTE["accent"] if provisional else PALETTE["ink_dim"],
            weight="bold",
            anchor="end",
            spacing=1.4 if provisional else 1.8,
        )
    )
    # THE COUNTER GOES ABOVE THE GRAPH, not below it, and that is not a taste
    # call. The published sentence says "the schedule graph BELOW is what the
    # ranking is standing on" — it is written for the web page, and a card that
    # prints it under the graph makes the project's own copy wrong on the one
    # artifact most likely to be read without its page. Placing rather than
    # rewriting is the same rule every other number on this card obeys.
    y = 88
    for line in _wrap(str(conn.get("counter") or ""), 112, 2):
        parts.append(_text(54, y, line, size=15, fill=PALETTE["ink_dim"]))
        y += 20
    parts.append(
        f'<line x1="54" y1="124" x2="{CARD_WIDTH - 54}" y2="124" '
        f'stroke="{PALETTE["rule"]}" stroke-width="1"/>'
    )

    # --- the graph, and the diagnostics rail beside it.
    parts.append(
        f'<rect x="{_n(panel[0])}" y="{_n(panel[1])}" width="{_n(panel[2])}" '
        f'height="{_n(panel[3])}" rx="10" fill="{PALETTE["panel"]}"/>'
    )
    parts.extend(_graph_panel(conn["nodes"], conn["edges"], teams, panel, named_bridges))

    rail_x = panel[0] + panel[2] + 40
    y = panel[1] + 22
    # Five, because six do not fit above the counter rule and a diagnostic that
    # overlaps the line under it is worse than one that is not on the card.
    for row in list(conn.get("diagnostics") or [])[:5]:
        parts.append(
            _text(
                rail_x,
                y,
                _clip(str(row["label"]).upper(), 34),
                size=12,
                fill=PALETTE["ink_faint"],
                spacing=1.4,
            )
        )
        parts.append(
            _text(
                rail_x,
                y + 27,
                _clip(str(row["display"]), 22),
                size=24,
                fill=PALETTE["ink"],
                weight="bold",
            )
        )
        y += 58

    # --- what would have to be true, inside the safe zone. This is the sentence
    # that makes the graph mean something to a reader who has never seen the site.
    parts.append(
        f'<line x1="54" y1="480" x2="{CARD_WIDTH - 54}" y2="480" '
        f'stroke="{PALETTE["rule"]}" stroke-width="1"/>'
    )
    claims = list(conn.get("what_would_have_to_be_true") or [])
    y = 502
    for line in _wrap(claims[0] if claims else "", 114, 3):
        parts.append(_text(54, y, line, size=15, fill=PALETTE["ink"]))
        y += 21

    # --- THE CONSTANTS FOOTER IS ON THE CARD AND IS NEVER DROPPED FOR SPACE
    # (report 05 §6.2). No other poll's share image carries its model constants;
    # that line is the signature.
    y = CARD_HEIGHT - 32
    for line in reversed(footer[:2]):
        parts.append(
            _text(54, y, _clip(line, 132), size=12, fill=PALETTE["ink_faint"], family=FONT_MONO)
        )
        y -= 18
    parts.append(
        _text(
            CARD_WIDTH - 54,
            CARD_HEIGHT - 32,
            "sb.unleashepic.com/cfb-poll",
            size=13,
            fill=PALETTE["ink_dim"],
            anchor="end",
        )
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _poll_row(
    row: dict[str, Any],
    x: float,
    y: float,
    width: float,
    *,
    height: float,
    rank_size: float,
    name_size: float,
    odds_size: float,
    use_abbreviation: bool,
) -> list[str]:
    """One team, on Look's row grid. Every value is printed, none is derived.

    `one_in` is published; it is never recomputed from `tail_p`. The rank, the
    record and the odds key are fields. This function does arithmetic on pixels
    and on nothing else.
    """
    mid = y + height / 2
    parts: list[str] = [
        # The team stripe, clamped. Full row height, 4px, always drawn.
        _slab(x, y + 3, 4, height - 6, stripe_colour(row.get("mark_bg"))),
    ]

    rank_x = x + 16
    parts.append(
        _text(rank_x, mid + rank_size * 0.34, str(int(row["rank"])), size=rank_size,
              fill=PALETTE["ink"], weight="800", family=FONT_MONO)
    )

    mark_r = height * 0.35
    mark_cx = rank_x + rank_size * 1.7 + mark_r
    parts.append(_mark_disc(mark_cx, mid, mark_r, row))

    name = str(row.get("abbreviation") if use_abbreviation else row.get("team") or "")
    name_x = mark_cx + mark_r + 12
    # The odds string is right-aligned to the row's right edge and the name is
    # clipped to what is left, so a long school name can never collide with the
    # number. Budgeted in characters because the raster's metrics are the host's.
    odds = f"1 in {int(row['one_in']):,}"
    odds_w = odds_size * len(odds) * 0.62
    name_budget = max(4, int((width - (name_x - x) - odds_w) / (name_size * 0.56)))
    parts.append(
        _text(name_x, mid + name_size * 0.34, _clip(name, name_budget), size=name_size,
              fill=PALETTE["ink"], weight="600", family=FONT_UI)
    )

    # The odds numeral is the accent's other sanctioned use: the key, in gold.
    parts.append(
        _text(x + width, mid + odds_size * 0.34, odds, size=odds_size,
              fill=PALETTE["accent"], weight="600", anchor="end", family=FONT_MONO)
    )
    return parts


def _row_block(
    rows: list[dict[str, Any]],
    x: float,
    top: float,
    width: float,
    *,
    height: float,
    playoff_after: int | None,
    **row_kwargs: Any,
) -> list[str]:
    """A column of rows, its separators, and the gold playoff rule.

    THE GOLD RULE UNDER ROW 4 IS THE CARD'S LOUDEST SPORTS SIGNAL and it is kept
    on every variant. `playoff_after` is None for a column that does not contain
    that boundary, which is how the multi-column variants avoid drawing it three
    times.
    """
    parts: list[str] = []
    for i, row in enumerate(rows):
        y = top + i * height
        parts.extend(_poll_row(row, x, y, width, height=height, **row_kwargs))
        is_playoff = playoff_after is not None and (i + 1) == playoff_after
        stroke = PALETTE["accent"] if is_playoff else PALETTE["rule"]
        parts.append(
            f'<line x1="{_n(x)}" y1="{_n(y + height)}" x2="{_n(x + width)}" '
            f'y2="{_n(y + height)}" stroke="{stroke}" '
            f'stroke-width="{"2" if is_playoff else "1"}"/>'
        )
    return parts


def _card_open(width: float, height: float, label: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(width)}" height="{_n(height)}" '
        f'viewBox="0 0 {_n(width)} {_n(height)}" role="img" aria-label="{_esc(label)}">',
        f'<rect width="{_n(width)}" height="{_n(height)}" fill="{PALETTE["bg"]}"/>',
    ]


def top10_svg(bundle: Bundle) -> str:
    """The top ten, two-panel split. 1200x628, the `summary_large_image` ratio.

    Ten rows of 34px starting at y=144 puts the whole block inside the mobile
    safe band (126..502), so a reader who sees only the cropped middle on X still
    gets the entire ranking. The wordmark and the constants strip sit outside it
    deliberately: they are the signature, not the message.
    """
    week_view = bundle.views["week"]
    rows = list(week_view.get("poll") or [])[:10]
    season, week = int(week_view["season"]), int(week_view["week"])

    panel_w = 392.0
    parts = _card_open(CARD_WIDTH, CARD_HEIGHT, f"The Poll top ten, {season} week {week}")
    parts.extend(_left_panel(week_view, panel_w, CARD_HEIGHT, thesis_size=30))

    parts.extend(
        _row_block(
            rows,
            panel_w + 32,
            144.0,
            CARD_WIDTH - panel_w - 64,
            height=34.0,
            playoff_after=4,
            rank_size=30,
            name_size=26,
            odds_size=26,
            use_abbreviation=False,
        )
    )
    parts.extend(_constants_strip(week_view, CARD_WIDTH, CARD_HEIGHT))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _top25_columns(
    bundle: Bundle,
    width: float,
    height: float,
    *,
    split: tuple[int, ...],
    row_h: float,
    top: float,
    rank_size: float,
    name_size: float,
    odds_size: float,
) -> str:
    """The top 25 laid into N columns. Shared by the X and Instagram canvases.

    Both carry the gold playoff rule and the constants strip, because those two
    are the card's signature and the narrower canvas is exactly where they would
    otherwise get squeezed out.
    """
    week_view = bundle.views["week"]
    rows = list(week_view.get("poll") or [])[:25]
    season, week = int(week_view["season"]), int(week_view["week"])

    panel_w = 392.0
    parts = _card_open(width, height, f"The Poll top 25, {season} week {week}")
    parts.extend(_left_panel(week_view, panel_w, height, thesis_size=28))

    area_x, area_w = panel_w + 24, width - panel_w - 48
    gutter = 16.0
    col_w = (area_w - gutter * (len(split) - 1)) / len(split)

    start = 0
    for index, count in enumerate(split):
        chunk = rows[start : start + count]
        x = area_x + index * (col_w + gutter)
        # The playoff boundary lives after rank 4, so it belongs to whichever
        # column actually contains rank 4 and to no other.
        after = 4 - start if any(int(r["rank"]) == 4 for r in chunk) else None
        parts.extend(
            _row_block(
                chunk, x, top, col_w, height=row_h, playoff_after=after,
                rank_size=rank_size, name_size=name_size, odds_size=odds_size,
                use_abbreviation=True,
            )
        )
        if index < len(split) - 1:
            gx = x + col_w + gutter / 2
            parts.append(
                f'<line x1="{_n(gx)}" y1="{_n(top)}" x2="{_n(gx)}" '
                f'y2="{_n(top + max(split) * row_h)}" stroke="{PALETTE["rule"]}" '
                f'stroke-width="1"/>'
            )
        start += count

    parts.extend(_constants_strip(week_view, width, height))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def top25_x_svg(bundle: Bundle) -> str:
    """Top 25 on the 1200x628 X canvas: two columns of 13 and 12.

    X renders 4:5 as a tap-to-expand thumbnail, so the timeline-native top 25 has
    to fit the same ratio as everything else. 13 rows of 26px from y=150 ends at
    488, inside the mobile safe band.
    """
    return _top25_columns(
        bundle, CARD_WIDTH, CARD_HEIGHT, split=(13, 12), row_h=26.0, top=150.0,
        rank_size=22, name_size=19, odds_size=19,
    )


def top25_instagram_svg(bundle: Bundle) -> str:
    """Top 25 on the 1200x1500 Instagram canvas: ONE full-width column.

    Portrait gets a single column and the full school names, not the three
    columns and abbreviations the landscape variant needs. 1500px of height is
    enough for 25 rows at 42px with type at reading size, which is the whole
    reason to publish a second canvas: the tall card is not a squeezed wide card,
    it is the version somebody can actually read on a phone held upright.
    """
    week_view = bundle.views["week"]
    rows = list(week_view.get("poll") or [])[:25]
    season, week = int(week_view["season"]), int(week_view["week"])

    parts = _card_open(CARD_WIDTH, TALL_HEIGHT, f"The Poll top 25, {season} week {week}")
    parts.extend(_top_banner(week_view, CARD_WIDTH, 300.0))
    parts.extend(
        _row_block(
            rows, 40.0, 344.0, CARD_WIDTH - 80, height=42.0, playoff_after=4,
            rank_size=28, name_size=26, odds_size=26, use_abbreviation=False,
        )
    )
    parts.extend(_constants_strip(week_view, CARD_WIDTH, TALL_HEIGHT))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_png(svg: str) -> bytes:
    """Rasterise. No network, no headless browser, no system-font surprise hidden.

    resvg is a static Rust rasteriser exposed as a wheel, which is what makes the
    Sunday job hermetic: report 05 §6.1 rejected a Chromium download for one image
    a week, and it was right.
    """
    try:
        import resvg_py
    except ImportError as exc:  # pragma: no cover - dependency is in the lock file
        raise RuntimeError(
            "resvg-py is required to rasterise a share card. The SVG is written "
            "regardless; run `uv sync --locked` to get the renderer."
        ) from exc

    if fonts_are_vendored():
        # THE HOST'S FONTS ARE SHUT OUT ENTIRELY. This is what turns the claim in
        # the module docstring from "deterministic given the same renderer and
        # the same fonts" into "deterministic", and it repairs a real defect: the
        # committed font stack led with DejaVu Sans, which is not installed on
        # the machine that has been rendering these cards, so every card this
        # project ever published was rasterised in Helvetica while its own SVG
        # said otherwise. A hashed, immutable, published artifact must not be
        # able to say that.
        return bytes(
            resvg_py.svg_to_bytes(
                svg_string=svg,
                skip_system_fonts=True,
                font_dirs=[str(FONT_DIR)],
            )
        )
    # No vendored families yet: fall back to the host, and be loud about what
    # that costs rather than producing a card that silently is not reproducible.
    return bytes(resvg_py.svg_to_bytes(svg_string=svg))


def fonts_are_vendored() -> bool:
    """True when `assets/fonts` holds at least one usable font file.

    A directory check rather than a per-family check on purpose: resvg resolves
    families out of whatever is in the fontdb, and asserting the exact set here
    would duplicate a fact that `tests/unit/test_share_cards.py` is a better
    place to pin.

    RECURSIVE, because the families are vendored one directory each - a font file
    has to sit beside the licence that permits redistributing it, and a flat
    directory would put four licences in one place with nothing saying which
    covers which. A non-recursive check found nothing in `assets/fonts/` itself
    and silently reported "no vendored families", which would have left the
    renderer falling back to the host on a machine where the fonts were in fact
    present - the same class of defect as the one vendoring them fixes.
    """
    if not FONT_DIR.is_dir():
        return False
    return any(p.suffix.lower() in (".ttf", ".otf", ".ttc") for p in FONT_DIR.rglob("*"))


#: variant -> the function that draws it, and the canvas it draws on. One table
#: so `export`, the CLI's help text and the CI guard cannot disagree about what
#: a variant is.
BUILDERS: dict[str, Any] = {
    "connectivity": (lambda b: connectivity_svg(b), CARD_WIDTH, CARD_HEIGHT),
    "top10": (lambda b: top10_svg(b), CARD_WIDTH, CARD_HEIGHT),
    "top25_x": (lambda b: top25_x_svg(b), CARD_WIDTH, CARD_HEIGHT),
    "top25_instagram": (lambda b: top25_instagram_svg(b), CARD_WIDTH, TALL_HEIGHT),
}


def export(
    out: Path,
    dest: Path,
    *,
    variant: str = "connectivity",
    archive: Path | None = None,
    backtest: Path | None = None,
    png: bool = True,
) -> list[Path]:
    """Write `<dest>/<season>-w<NN>-<variant>.{svg,png}`. Returns the paths, sorted.

    `out` is the directory `cfbpoll rank` produced. Both files are written: the
    SVG because it is the diffable, reviewable, vector artifact and the thing a
    test can assert about, and the PNG because that is what travels.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown card variant {variant!r}; expected one of {VARIANTS}")
    bundle = build(out, archive=archive, backtest=backtest)
    svg = BUILDERS[variant][0](bundle)

    dest.mkdir(parents=True, exist_ok=True)
    stem = f"{bundle.season}-w{bundle.week:02d}-{variant}"
    written = [dest / f"{stem}.svg"]
    written[0].write_text(svg, encoding="utf-8")
    if png:
        target = dest / f"{stem}.png"
        target.write_bytes(render_png(svg))
        written.append(target)
    return sorted(written)


def sha256_of(path: Path) -> str:
    """The published card's digest. Report 05 §6.1(2): a card is a frozen claim."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
