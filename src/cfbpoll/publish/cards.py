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
from pathlib import Path
from typing import Any

from cfbpoll.publish.serving import Bundle, build

__all__ = [
    "CARD_HEIGHT",
    "CARD_WIDTH",
    "PALETTE",
    "SAFE_TOP",
    "VARIANTS",
    "connectivity_svg",
    "export",
    "render_png",
]

#: 1200x628 is the `summary_large_image` ratio (report 05 §6.2). The 5 MB ceiling
#: is a hard build failure in Next.js and we are three orders of magnitude inside
#: it, because this card is flat colour and straight lines.
CARD_WIDTH = 1200
CARD_HEIGHT = 628

#: X crops the top and bottom on mobile, so the essential content lives in the
#: middle ~60% (report 05 §6.2). The title band and the constants footer sit
#: OUTSIDE it deliberately - they are the signature, not the message, and a reader
#: who sees only the middle still gets the whole point.
SAFE_TOP = 126
SAFE_BOTTOM = CARD_HEIGHT - 126

VARIANTS: tuple[str, ...] = ("connectivity",)

#: One dark palette, fixed. A share card has no theme toggle: it is a PNG in
#: somebody else's timeline, and it has to hold up against both a white and a
#: black surrounding page, which a dark card with high-contrast type does.
PALETTE: dict[str, str] = {
    "bg": "#0e1116",
    "panel": "#161b22",
    "rule": "#2b3138",
    "ink": "#f2f5f8",
    "ink_dim": "#98a3af",
    "ink_faint": "#5c6874",
    "edge": "#2f3944",
    "accent": "#e8b23a",
}

#: Deliberately a stack rather than one family. The card is rendered by whatever
#: font the host has, and naming a chain of widely-installed grotesques means the
#: metrics land close on any of them. The SVG records the stack, so the file is
#: honest about the fact that the raster is environment-dependent.
FONT_STACK = "DejaVu Sans, Helvetica Neue, Helvetica, Arial, Liberation Sans, sans-serif"
FONT_MONO = "DejaVu Sans Mono, Menlo, Consolas, Liberation Mono, monospace"


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
    return bytes(resvg_py.svg_to_bytes(svg_string=svg))


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
    svg = connectivity_svg(bundle)

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
