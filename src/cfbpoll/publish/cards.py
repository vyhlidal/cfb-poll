"""The weekly share card: SVG in the pipeline, PNG beside it, school marks on it.

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

THE CARDS CARRY REAL SCHOOL MARKS, AND THAT IS A REVERSAL. Report 06 §8.3 said
never, this module said never at length, and the project owner overturned it:
"I don't care about the logo caution, every social post everywhere uses college
logos, we're not making T-shirts: use the logos."

The reasoning behind the old rule is restated rather than deleted, because it is
what still makes this defensible. A mark is drawn UNALTERED, at the size a mark is
drawn at, to IDENTIFY the team whose row it sits on and for no other purpose: no
merchandise, no implied endorsement, no recolouring, no clipping into a silhouette
the school does not use. The site carries the disclaimer and the licence footer,
and every card carries a link back to it. What changed is the owner's assessment
of the risk, which is his to make.

THE GUARD DID NOT GO AWAY, IT CHANGED SIDES. A card must still be SELF-CONTAINED:
every `<image>` on it is a `data:` URI over bytes from the pinned cache, and an
external `http(s)` href in a card is a build failure, because a card that hotlinks
is a card that renders a blank square the moment it is posted somewhere the host
does not like. `tests/unit/test_share_cards.py` enforces that, that the cache
directory is gitignored, and that the manifest covers every mark the card set
draws.

DETERMINISM, precisely, because the honest claim is narrower than "deterministic":

  - THE SVG IS A PURE FUNCTION OF (THE PUBLISHED DOCUMENTS + THE PINNED LOGO
    CACHE), byte for byte, on any machine. No wall clock, no RNG, no dict
    iteration order, every float formatted to a fixed precision, every collection
    sorted before it is drawn. THE NETWORK FETCH IS THE ONE NON-HERMETIC INPUT and
    it lives in `publish/logos.warm`, which the export path calls BEFORE it
    renders; the builders themselves read the cache and cannot reach the network.
    `data/logo-cache-manifest.json` is the pin that makes that input auditable.
  - THE PNG IS DETERMINISTIC GIVEN THE SAME RENDERER AND THE SAME FONTS. resvg
    resolves `font-family` against the host's installed fonts, so a machine with a
    different font stack produces different glyph rasterisation. `render_png` pins
    `skip_system_fonts=True` and points resvg at the vendored families, which is
    what turns that conditional into an unconditional one.

WHICH VARIANTS THIS BUILDS. `connectivity` is the weeks 1-4 launch product, the
schedule graph and its diagnostics, and no other poll's share image shows you the
graph its ranking is standing on. `top5`, `top10` and the two `top25` canvases are
the board itself, and the projection has its own four. The top five is the hero:
five rows means the rank numeral and the mark can be drawn at a size that reads at
thumbnail scale, which is where most of these are actually seen. The three
`comparison` canvases put our board beside one or two NAMED EXTERNAL BOARDS, which
is what turns a disagreement graphic from a hand-made image into a published
artifact with a digest like every other card. The two `billboard` canvases are
the newest and they invert the usual assumption: every other card here is built
to be READ by somebody who stopped scrolling, and a billboard is built to survive
being scrolled PAST by a stranger, which is why the ranks are drawn at twice the
hero card's scale and why it is the only card carrying a line of marketing copy.

THE SHAREABLE SET IS FOUR CARDS AND THE OWNER NAMED THEM on 2026-08-18: the top
five, the top ten, the top 25 and the whole 138. TWO OF THEM ARE ROWS AND TWO OF
THEM ARE TILES, and the split is the ruling rather than a preference - "the 25 and
the full list must MAXIMIZE logo and rank-number size for at-a-glance reading".

  - `projection_top5` and `projection_top10` are ROWS on 1.91:1, unchanged. Five
    and ten rows already buy a 52px numeral and a 52px mark, and the wide canvas
    is the one a link preview and an embed are cut to. They keep the masthead
    column, which runs the document's own headline beside the board.
  - `projection_top25` (4:5) and `projection_grid` (2:3) are TILES: the mark
    centred and as large as the cell allows, the rank under it, the name a
    caption. A row caps the mark at the row's height while the rank lane and the
    name eat its width, which is how a 25 ended up with an 18px logo. Stacking
    frees the width and the same board area draws 105px and 65px marks.
  - THERE IS NO SINGLE-TEAM HERO CARD IN THE SET. `billboard_team` still exists as
    a season template; it is not one of the four, by ruling: "not that
    interesting".

The two tile cards are also the only boards that carry `BILLBOARD_TEASER`, for
the reason `TEASER_HEIGHT` gives: they are the cards posted to be LOOKED at, so
they meet the same stranger the billboards were written for.

THE BRAND IS THE MASTHEAD, AND THE ACCENT RULE IS A DISCIPLINE RATHER THAN A
COLOUR. The gold-on-near-black palette this module shipped through 2026-08-17 is
retired whole. What replaced it:

  - GROUND `#101216`, INK `#eae7e0`, RULE `#6f7278`, ACCENT `#00c2e0`. Those four
    are the brand's dark tokens and are not negotiable here. Everything else in
    `PALETTE` is DERIVED from two of them by a stated blend, so a reader can check
    every value on the card with arithmetic instead of taking it on faith.
  - THE ACCENT MARKS THE MACHINE AND NOTHING ELSE. The brand permits exactly four
    uses and a share card can reach three of them: the `.ai` in the wordmark, the
    schedule-odds key and the column it labels, and ONE divider rule between the
    board and the attribution. Everything that is the poll stays monochrome. A
    cyan slab, a cyan team name, a cyan hairline anywhere else is the failure this
    palette exists to prevent, and `tests/unit/test_share_cards.py` counts them.
  - THE WORDMARK IS DRAWN AS PATHS, from `MASTHEAD_GLYPHS` below, so the mark on a
    card is the mark and not a font's approximation of it. No image file, no
    dependency on a family being installed, and it rasterises identically on any
    machine, which is the same property the rest of the card already had.
  - NUMBERS ARE NOT TERMINAL OUTPUT. Rank numerals, win totals and the odds key
    are set in the BOARD face, not the mono. Mono is provenance only - run ids,
    config hashes, the constants footer - which is the one place looking like
    machine output is the point.

TWO OF JOHN'S STANDING RULES ARE ENFORCED HERE RATHER THAN REMEMBERED. There is
NO PLAYOFF CUT LINE on any card: the accent rule that used to fall under rank 4 is
gone from every variant, because a poll that refuses to run a committee should not
draw a committee's line, and the rule was the loudest thing on the hero card. And
every row gets the SAME TREATMENT: rank 1 is drawn exactly like rank 25.

AND NO PUBLISHED PNG CARRIES AI-PROVENANCE METADATA. Meta and TikTok apply
AI-generated labels from file metadata rather than from what an image shows, and
TikTok's cannot be removed, so a bar chart Python drew can be badged by a field
nobody looked at. `render_png` strips every chunk outside a small allow-list and
`png_metadata_chunks` is what a test and a human both read to check it.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from cfbpoll.publish import logos
from cfbpoll.publish.serving import Bundle, build

__all__ = [
    "AGREEMENT_BAND",
    "BILLBOARD_CLARITY",
    "BILLBOARD_TEASER",
    "BILLBOARD_VARIANTS",
    "BUILDERS",
    "CORPUS_COUNTS_PATH",
    "CARD_HEIGHT",
    "CARD_WIDTH",
    "COMPARISON_VARIANTS",
    "DATA_CREDIT",
    "FONT_DIR",
    "GAP_NEG",
    "GAP_POS",
    "PALETTE",
    "PLATE_OPACITY",
    "PNG_ALLOWED_CHUNKS",
    "POSTER_HEIGHT",
    "PROJECTION_VARIANTS",
    "SAFE_TOP",
    "SQUARE_HEIGHT",
    "TALL_HEIGHT",
    "TEASER_HEIGHT",
    "VARIANTS",
    "billboard_team_svg",
    "billboard_top5_svg",
    "comparison_square_svg",
    "comparison_svg",
    "comparison_tall_svg",
    "connectivity_svg",
    "corpus_counts",
    "disagreement_svg",
    "export",
    "export_billboard",
    "export_comparison",
    "export_projection",
    "fonts_are_vendored",
    "load_comparison",
    "masthead_height",
    "png_chunks",
    "png_metadata_chunks",
    "projection_top5_svg",
    "projection_top10_svg",
    "grid_svg",
    "projection_top25_svg",
    "render_png",
    "stripe_colour",
    "strip_png_metadata",
    "top5_svg",
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

#: 1200x1200 is 1:1, the carousel slide. It exists because GFX-10 asks for the
#: comparison as three slides rather than one long card, and a square is what
#: every platform crops least: Instagram shows it whole, X shows it whole, and a
#: LinkedIn or Reddit thumbnail does not letterbox it.
SQUARE_HEIGHT = 1200

#: 1200x1800 is 2:3, and it is the ALL-TEAMS POSTER. It is the one canvas here
#: that is not native to a feed, and that is the honest trade rather than an
#: oversight: 138 teams drawn large enough to recognise from a logo do not fit in
#: a feed-native ratio at 1200px wide, and a card nobody can read at a glance has
#: already failed whatever ratio it is cut to.
#:
#: THE ARITHMETIC IS WHY, AND IT IS NOT NEGOTIABLE BY TASTE. The drawable board on
#: the 4:5 canvas is 1120x1088, which is 8,800 square pixels per team. A school
#: mark and a rank numeral that read at arm's length need roughly twice that. 2:3
#: buys the second half. It is still one file, still self-contained, still under
#: the 5 MB ceiling by three orders of magnitude, and it is the artifact somebody
#: taps to expand rather than the one that has to survive being scrolled past.
POSTER_HEIGHT = 1800

#: X crops the top and bottom on mobile, so the essential content lives in the
#: middle ~60% (report 05 §6.2). The title band and the constants footer sit
#: OUTSIDE it deliberately - they are the signature, not the message, and a reader
#: who sees only the middle still gets the whole point.
SAFE_TOP = 126
SAFE_BOTTOM = CARD_HEIGHT - 126

#: THE ADDRESS ON EVERY CARD, IN ONE PLACE. Each canvas draws this in its footer,
#: opposite the constants line, and it is the only route a reader has from a
#: reposted PNG back to the poll it came from - so it is a constant rather than
#: three string literals that can drift apart one card at a time.
#:
#: It is the bare host, with no scheme and no path, because the card is read at
#: thumbnail scale and typed into a phone by hand. `thepoll.ai` is the whole
#: address: the site serves the poll at its root, so there is nothing after the
#: slash for a reader to get wrong.
SITE_DOMAIN = "thepoll.ai"

#: THE ATTRIBUTION, ON EVERY CARD, AND IT WAS NOT THERE BEFORE. CFBD's terms say
#: attribution is "not required but strongly encouraged"; the site's own
#: disclaimer already says "it is owed and it costs a line", and until now the
#: share cards - the artifacts most likely to travel with no page attached - were
#: the one surface that did not pay it. A line costs 12px.
DATA_CREDIT = "data: collegefootballdata.com"

#: How tall the signature strip is. Two constants lines on the left, the address
#: and the data credit on the right.
FOOTER_HEIGHT = 66.0

#: `top25_x` and `top25_instagram` are the same table on two canvases and are
#: separate variants rather than one variant with an option, because each is a
#: published artifact with its own sha256 and neither is a derivative of the
#: other.
#: The variants that draw THE PROJECTION rather than a week of the poll. They are
#: named apart rather than flagged because they read a DIFFERENT DOCUMENT: a week
#: of the poll comes out of a run directory through `serving.build`, and the
#: projection is one JSON file with no run behind it at all. Their files are
#: `<season>-projection-<name>` rather than `<season>-wNN-<name>`, since a
#: preseason projection has no week and stamping one on it would be inventing a fact.
PROJECTION_VARIANTS: tuple[str, ...] = (
    "projection_top5",
    "projection_top10",
    "projection_top25",
    # The all-teams grid. Same input as the three above and the same refusal on a
    # dark document, so it belongs in the same family; what it needs that they do
    # not is a document published with more than 25 rows.
    "projection_grid",
)

#: The variants that draw OUR BOARD BESIDE SOMEBODY ELSE'S. They take two inputs -
#: the published projection document and a comparison spec naming each external
#: board and its ranks - so they are named apart for the same reason the
#: projection variants are: a variant is defined by what it reads.
#:
#: Their files are `<season>-<slug>-<variant>`, where the slug comes from the spec.
#: Not the variant alone: three carousel slides are three different claims about
#: three different slices of the board, and three published artifacts that
#: overwrote each other would be one artifact with a moving digest.
COMPARISON_VARIANTS: tuple[str, ...] = (
    "comparison",
    "comparison_tall",
    "comparison_square",
    "disagreement",
)

#: THE FEED VARIANTS. They read the same projection document the `projection_*`
#: family does and they are named apart because they are a different product: a
#: board card is built to be read by somebody who stopped, and a billboard is
#: built to survive being scrolled past at thumbnail size by a stranger. That is
#: why they carry a teaser line and nothing else does, and why the single-team one
#: takes a second argument naming its subject.
BILLBOARD_VARIANTS: tuple[str, ...] = (
    "billboard_top5",
    "billboard_team",
)

VARIANTS: tuple[str, ...] = (
    "connectivity",
    "top5",
    "top10",
    "top25_x",
    "top25_instagram",
    *PROJECTION_VARIANTS,
    *BILLBOARD_VARIANTS,
    *COMPARISON_VARIANTS,
)

#: One dark palette, fixed. A share card has no theme toggle: it is a PNG in
#: somebody else's timeline, and it has to hold up against both a white and a
#: black surrounding page, which a dark card with high-contrast type does. The
#: brand says the same thing for a second reason: "a bright card in a timeline
#: reads as an advertisement and a dark one reads as a broadcast graphic".
#:
#: FOUR TOKENS ARE THE BRAND'S AND THE REST ARE ARITHMETIC. `bg`, `ink`, `rule`
#: and `accent` are the brand book's dark values, copied. Every other entry is
#: `ink` composited over `bg` at a stated fraction, so there is no colour on this
#: card that a reader cannot reproduce, and no opportunity for a fifth hue to
#: arrive because somebody needed "a slightly lighter grey". The measured contrast
#: against the ground is on each line.
#:
#: THE ACCENT MARKS THE MACHINE AND NOTHING ELSE. On a card it may appear in
#: exactly three places: the `.ai` of the wordmark, the schedule-odds key and the
#: column it labels, and one divider rule above the attribution. It is never a
#: slab, never a team name, never a row separator, never a border. The old gold
#: could be a filled slab and that is what made the label banners loud; the
#: replacement for that loudness is a BONE slab with `brand_ink` on it, which is a
#: newspaper reverse block and costs the palette nothing.
PALETTE: dict[str, str] = {
    # --- the brand's own dark tokens.
    "bg": "#101216",
    "ink": "#eae7e0",  # 15.18:1 on the ground. AAA.
    "rule": "#6f7278",  # 3.89:1. Hairlines and separators; large text at a push.
    "accent": "#00c2e0",  # 8.74:1. THE MACHINE. Three permitted uses, see above.
    # --- derived: ink over bg at the stated fraction.
    "panel": "#15171b",  # the brand's ink tile, the one plate the graph card draws
    "ink_dim": "#a09f9b",  # 0.66 -> 7.08:1. Datelines, secondary numbers, the address.
    "ink_faint": "#6f7278",  # 0.44, which lands on the rule token. The constants whisper.
    "edge": "#404142",  # 0.22 -> 1.83:1. Graph edges. A mark, never text.
    # Ink drawn ON a bone slab. The reverse block that replaced the gold banner.
    "brand_ink": "#101216",
    # The team stripe when a row carries no colour. Drawn either way, never
    # omitted: a missing box would misalign the row grid on exactly the rows
    # whose data is weakest.
    "stripe_fallback": "#6f7278",
    # The uncertainty rail is EVIDENCE and is deliberately not the accent. Cyan is
    # the key. A rail in the accent colour would read as the thing being
    # celebrated rather than the thing being admitted.
    "rail_track": "#2a2c2e",  # 0.12
    "rail_band": "#c9c4b8",  # the brand's LIGHT rule token, used here as a neutral band
    # The ground a near-black school mark is set on so it does not vanish into
    # the card. The brand's bone rather than a white: at this size a #FFFFFF chip
    # is a hole punched in the card, and this one reads as paper.
    "plate": "#eae7e0",
}

#: THE ONE PLACE A SECOND AND THIRD HUE ARE ALLOWED, and they are not brand accent.
#: The brand book keeps a diverging pair for MOVEMENT FIGURES - amber against
#: violet, chosen so a red-green colourblind reader can still read direction - and
#: rules it "data encoding rather than brand accent". A comparison card is a
#: movement figure: the whole point is that a reader sees which way each
#: disagreement runs without reading a number.
#:
#: THE BRAND BOOK ALSO FLAGS THE RISK THIS CREATES, and the flag is answered in
#: `_comparison_rules`: cyan must not appear beside the amber-violet pair in a way
#: that reads as three competing categories, so a comparison card draws NO accent
#: divider. Its only cyan is the `.ai` in the mark, which is identity rather than a
#: data category and sits in the masthead rather than in the figure.
GAP_POS = "#dc9440"  # 7.46:1. We rank this team HIGHER than they do.
GAP_NEG = "#9c8fd6"  # 6.53:1. We rank it LOWER.

#: Inside this many places, two boards agree and the card says so in bone. The
#: number is not arbitrary: a one-place difference between a 25-team ballot and a
#: 138-team model is noise, and colouring it would make every row a story.
AGREEMENT_BAND = 2

#: How solid that plate is. NOT "subtle" in the sense of nearly invisible: the
#: plate exists to deliver contrast a near-black mark cannot get from the ground, and
#: a 15% white wash over a near-black ground is still a near-black ground. At 0.92
#: the composite sits around #D6D4D0, which gives a black mark better than 13:1
#: and still reads as a soft chip rather than a glaring white square. Subtlety is
#: bought in the SHAPE and the SIZE instead: a small rounded rect, a few px larger
#: than the mark, drawn only on the rows that need it.
PLATE_OPACITY = 0.92

#: Four roles, and the brand cut two of them back hard.
#:
#: THE BOARD FACE DOES THE BOARD, ALL OF IT. Brand book §3: "Board numbers, rank
#: numerals, win totals and schedule ranks are set in the board face with tabular
#: figures. Monospace is for provenance only, where looking like machine output is
#: the point." Every rank numeral and every value on this card used to be mono,
#: which made a ranking look like a log file. They are the display face now, and
#: `_num` asks for tabular figures.
#:
#: THE SERIF LEFT THE CARD. The same table assigns "headlines, share cards,
#: endcards" to the board face and reserves the prose serif for "long answers,
#: paragraphs a person reads sitting down". A share card is not that. `FONT_PROSE`
#: stays defined because the vendored family is still shipped and still tested,
#: and because other surfaces in this project do run prose.
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

#: TABULAR FIGURES ARE ASKED FOR AND ARE NOT DELIVERED, AND THE CARD IS BUILT FOR
#: THAT. The brand book flagged honest uncertainty about whether the shipped
#: Archivo carries a `tnum` feature. It does - reading the GSUB feature list off
#: `assets/fonts/archivo/Archivo-Variable.ttf` finds `tnum` among 21 tags. The
#: renderer is the problem: rasterising the same numerals with and without
#: `font-feature-settings="tnum"` and `font-variant-numeric: tabular-nums`
#: produces BYTE-IDENTICAL output under the pinned resvg, so the feature is
#: requested and ignored.
#:
#: So the card takes the fallback the brand book names: FIXED-WIDTH,
#: RIGHT-ALIGNED COLUMNS. Every rank numeral is anchored to the right edge of a
#: lane sized from the type, so 1 and 25 end in the same place and the marks
#: beside them line up down the card. The attribute is still emitted, because the
#: SVG is also read in a browser, where it works.
TABULAR = 'font-feature-settings="tnum" style="font-variant-numeric:tabular-nums"'

#: THE MASTHEAD, AS PATHS. Taken from `brand/logo/wordmark-dark.svg`, which is
#: drawn as paths precisely so no surface has to have a font installed to set the
#: name correctly.
#:
#: WHY THE GEOMETRY IS IN THIS FILE RATHER THAN AN ASSET. A card must be
#: self-contained and this repository does not ship image files outside a named
#: allow-list, which is the guard that keeps school marks out of the tree. Copying
#: four path strings in is 1.5 KB and keeps both rules intact; adding an SVG to
#: `assets/` would have meant widening the allow-list for a decoration, and the
#: next thing through that hole would not be a decoration.
#:
#: THE CONSTRUCTION IS THE BRAND AND IT IS NOT ADJUSTABLE HERE. A heavy rule
#: across the top, THE POLL set light and wide beneath it on a 100-unit cap
#: height, `.ai` inline on the same baseline at 0.48 of that cap height in the
#: accent, and a hairline closing the block. No badge, no pill, no container, no
#: enclosed suffix - "that is deliberate and permanent". `_masthead` scales the
#: whole lockup as one unit, so nothing in this module can restack it, recolour
#: the nameplate, or set THE smaller than POLL.
MASTHEAD_WIDTH = 740.56
MASTHEAD_HEIGHT = 166.0
#: One cap height on every side, and the cap height is 100 of the 166 above.
MASTHEAD_CLEAR = 100.0 / MASTHEAD_HEIGHT
#: Below this the hairline and the `.ai` both stop resolving. Use the compact mark.
MASTHEAD_MIN_WIDTH = 200.0

_MASTHEAD_NAME: tuple[tuple[float, str], ...] = (
    (0.0, "M0 0H64V16H0ZM24 16H40V100H24Z"),
    (94.0, "M0 0H16V100H0ZM48 0H64V100H48ZM16 42H48V58H16Z"),
    (188.0, "M0 0H16V100H0ZM16 0H64V16H16ZM16 42H58V58H16ZM16 84H64V100H16Z"),
    (
        308.0,
        "M0 0H16V100H0ZM16 0H36A30 30 0 0 1 66 30V32A30 30 0 0 1 36 62H16Z"
        "M16 15H36A15 15 0 0 1 51 30V32A15 15 0 0 1 36 47H16Z",
    ),
    (
        404.0,
        "M36 0H36A36 36 0 0 1 72 36V64A36 36 0 0 1 36 100H36A36 36 0 0 1 0 64V36"
        "A36 36 0 0 1 36 0ZM36 15H36A21 21 0 0 1 57 36V64A21 21 0 0 1 36 85H36"
        "A21 21 0 0 1 15 64V36A21 21 0 0 1 36 15Z",
    ),
    (506.0, "M0 0H16V100H0ZM16 84H64V100H16Z"),
    (600.0, "M0 0H16V100H0ZM16 84H64V100H16Z"),
)

_MASTHEAD_SUFFIX: tuple[tuple[float, str], ...] = (
    (0.0, "M0 85H15V100H0Z"),
    (
        31.0,
        "M34 28H60V100H34A34 34 0 0 1 0 66V62A34 34 0 0 1 34 28Z"
        "M34 42H46V86H34A20 20 0 0 1 14 66V62A20 20 0 0 1 34 42Z",
    ),
    (107.0, "M0 28H15V100H0ZM0 6H15V21H0Z"),
)


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
#: Navy sits near black on the ground and vanishes; a neon green shouts over every
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
    """The generated mark: a coloured disc with the school's initials on it.

    NO LONGER THE ONLY MARK A CARD MAY CARRY, and still the one every card falls
    back to. A row whose document published no `logo_url` (which is what
    `[display].logos = false` produces) and a row whose bytes are not in the
    pinned cache both land here, so a fork with a cold cache and no network still
    renders a complete, legible board rather than a column of empty squares.
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


def _mark(x: float, y: float, radius: float, row: dict[str, Any]) -> str:
    """The school's real mark, on a plate if it needs one, or the generated disc.

    THE BYTES COME FROM THE PINNED CACHE AND ARE EMBEDDED, never referenced. A
    `data:` URI makes the SVG self-contained, which is the only form a share card
    can safely take: an `<image href="https://...">` renders as a blank square the
    moment the host blocks the referrer, and the SVG is itself a published
    artifact somebody may open in five years.

    THE PLATE IS THE LUMINANCE GUARD, and it is the same defect the website has in
    the other direction. `logos.resolve` measures the mark's effective luminance
    over its painted pixels and compares it against what the ground needs for WCAG's
    3:1 non-text contrast. Below that the mark is set on a light neutral chip a
    few px larger than itself. Asking the host for the `-dark` variant is not
    enough on its own: some schools have no genuine dark file and the same
    near-black artwork comes back under both URLs, which is exactly the case this
    catches.

    The mark is drawn into a SQUARE box with `xMidYMid meet`, so a wordmark that
    is not square is letterboxed inside its slot rather than stretched. Altering a
    school's mark is the thing the identification argument does not permit, and
    "we squashed it to fit the row" would be altering it.
    """
    mark = logos.resolve(row, background=PALETTE["bg"])
    if mark is None:
        return _mark_disc(x, y, radius, row)

    parts: list[str] = []
    if mark.plate:
        pad = max(2.0, radius * 0.18)
        side = (radius + pad) * 2
        parts.append(
            f'<rect x="{_n(x - radius - pad)}" y="{_n(y - radius - pad)}" '
            f'width="{_n(side)}" height="{_n(side)}" rx="{_n(side * 0.24)}" '
            f'fill="{PALETTE["plate"]}" fill-opacity="{_n(PLATE_OPACITY)}"/>'
        )
    parts.append(
        f'<image x="{_n(x - radius)}" y="{_n(y - radius)}" width="{_n(radius * 2)}" '
        f'height="{_n(radius * 2)}" preserveAspectRatio="xMidYMid meet" '
        f'href="{mark.data_uri}"/>'
    )
    return "".join(parts)


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


def _rule(
    x: float, y: float, width: float, *, stroke: str, weight: float = 1.0, opacity: float = 1.0
) -> str:
    """A horizontal hairline. The masthead brand's most-used element by far.

    Opacity rather than a second grey, and that is a palette decision made once:
    the brand's dark rule token is 3.89:1 against the ground, which is right for
    the structural rules and far too loud repeated 25 times down a board. Drawing
    the same token lighter keeps the palette at four colours instead of five.
    """
    attrs = f'stroke="{stroke}" stroke-width="{_n(weight)}"'
    if opacity < 1.0:
        attrs += f' stroke-opacity="{_n(opacity)}"'
    return (
        f'<line x1="{_n(x)}" y1="{_n(y)}" x2="{_n(x + width)}" y2="{_n(y)}" {attrs}/>'
    )


def _num(
    x: float, y: float, content: str, *, size: float, fill: str, weight: str = "700",
    anchor: str = "end",
) -> str:
    """A board numeral: the board face, tabular figures asked for, right-anchored.

    THE ANCHOR IS THE POINT. resvg ignores the tabular-figures request (see
    `TABULAR`), so the column is made to line up by geometry instead of by font
    feature. Right-anchored means the units digit of 1 sits under the units digit
    of 25, which is the whole of what tabular figures would have bought.
    """
    return (
        f'<text x="{_n(x)}" y="{_n(y)}" font-family="{FONT_DISPLAY}" '
        f'font-size="{_n(size)}" fill="{fill}" font-weight="{weight}" '
        f'text-anchor="{anchor}" {TABULAR}>{_esc(content)}</text>'
    )


def _masthead(x: float, y: float, width: float, *, accent: str | None = None) -> list[str]:
    """The Poll.ai, drawn as paths, scaled as one unit. The card's signature.

    `width` is the lockup's full width and everything else follows from it, so a
    caller cannot stretch the name, restack it, or set THE smaller than POLL. The
    nameplate is always `ink`: the brand permits no coloured wordmark, and the ONLY
    coloured element in the whole mark is the `.ai`.

    `accent=None` draws a monochrome mark. That exists for one case and it is a
    real one: a comparison card encodes direction in the brand's amber-violet
    movement pair, and the brand book flags that cyan must not sit beside that pair
    reading as a third category. On those cards the suffix goes bone.
    """
    if width < MASTHEAD_MIN_WIDTH:
        raise ValueError(
            f"the wordmark is drawn at {width:.0f}px and its minimum is "
            f"{MASTHEAD_MIN_WIDTH:.0f}px, below which the hairline and the .ai stop "
            "resolving. Use the compact mark rather than shrinking this one."
        )
    scale = width / MASTHEAD_WIDTH
    ink = PALETTE["ink"]
    suffix_fill = accent if accent is not None else ink
    body = [
        f'<g transform="translate({_n(x)},{_n(y)}) scale({scale:.6f})">',
        f'<rect x="0" y="0" width="{_n(MASTHEAD_WIDTH)}" height="7" fill="{ink}"/>',
        f'<g fill="{ink}" fill-rule="evenodd" transform="translate(0 37)">',
    ]
    body += [
        f'<path d="{d}" transform="translate({_n(dx)} 0)"/>' for dx, d in _MASTHEAD_NAME
    ]
    body.append("</g>")
    body.append(
        f'<g fill="{suffix_fill}" fill-rule="evenodd" '
        f'transform="translate(682 89) scale(0.48)">'
    )
    body += [
        f'<path d="{d}" transform="translate({_n(dx)} 0)"/>' for dx, d in _MASTHEAD_SUFFIX
    ]
    body.append("</g>")
    body.append(
        f'<rect x="0" y="163" width="{_n(MASTHEAD_WIDTH)}" height="3" '
        f'fill="{PALETTE["rule"]}"/>'
    )
    body.append("</g>")
    return body


def masthead_height(width: float) -> float:
    """How tall the lockup is at that width, so a caller can lay out beneath it."""
    return MASTHEAD_HEIGHT * (width / MASTHEAD_WIDTH)


def _eyebrow(
    x: float,
    y: float,
    text: str,
    *,
    size: float = 15.0,
    fill: str | None = None,
    anchor: str = "start",
) -> str:
    """The dateline under the mark. Board face, tracked, upper case."""
    return _text(
        x, y, str(text).upper(), size=size, fill=fill or PALETTE["ink_dim"],
        weight="700", family=FONT_DISPLAY, spacing=size * 0.12, anchor=anchor,
    )


#: How wide one character of the board face is, as a fraction of its type size,
#: measured off the widest plausible run of capitals rather than assumed. Used
#: wherever text has to be fitted to a box without a layout engine.
CAP_ADVANCE = 0.62


def _reverse_block(
    x: float, y: float, width: float, text: str, *, size: float = 13.0, min_size: float = 9.0
) -> list[str]:
    """A bone slab with ground-coloured type on it. What replaced the gold banner.

    THE LABEL HAS TO BE UNMISSABLE AND IT MAY NOT BE CYAN. The old banner was an
    accent slab, which the brand retired: the accent means "the machine", and a
    document's own statement of what it is is not the machine. A reverse block is
    the newspaper answer, it is louder than the gold ever was at 15.18:1, and it
    costs the palette nothing.

    IT SHRINKS BEFORE IT CLIPS, and that is the whole reason this function does
    arithmetic instead of taking a character budget. The string it draws is a
    document's statement of what the document IS - "THE PROJECTION. It is not the
    poll" - and a truncated version of that sentence is worse than no sentence.
    The old code took a fixed budget and cut the label mid-word the first time a
    longer one arrived, which is exactly what happened.
    """
    height = size * 1.85
    inner = width - size
    fitted = size
    while fitted > min_size and len(text) * fitted * CAP_ADVANCE > inner:
        fitted -= 0.25
    budget = max(8, int(inner / (fitted * CAP_ADVANCE)))
    return [
        _slab(x, y, width, height, PALETTE["ink"]),
        _text(
            x + size * 0.5,
            y + height - size * 0.62,
            _clip(text, budget),
            size=fitted,
            fill=PALETTE["brand_ink"],
            weight="700",
            family=FONT_DISPLAY,
            spacing=fitted * 0.03,
        ),
    ]


#: The masthead column: where the wordmark sits and where the board starts.
#: 392 was the old panel's width and it survives the rebrand because the number
#: was never about the panel - it is what leaves the board enough room for a long
#: school name and a value beside it on a 1200px canvas. What changed is that the
#: column is no longer a filled box. The ground runs edge to edge and a single
#: vertical hairline divides the two, which is the masthead brand's whole idea:
#: a document is organised by rules, not by boxes.
COLUMN_W = 392.0
COLUMN_X = 32.0
#: The lockup's drawn width in that column. 300 is comfortably over the 200px
#: minimum and leaves the column's right margin clear of the closing hairline.
COLUMN_MARK_W = 300.0


def _masthead_column(
    panel_w: float,
    height: float,
    *,
    eyebrow: str,
    label: str | None,
    thesis: str,
    thesis_size: float,
    thesis_lines: int = 5,
    accent: str | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    """The card's left column: the mark, the dateline, the label, the thesis.

    ONE FUNCTION FOR EVERY CARD THAT HAS A COLUMN, and the arguments are strings
    the CALLER read out of a document. The poll's dateline is its season and week,
    the projection's is its season and the word PRESEASON, a comparison card's is
    whatever its input says - and none of those sentences is typed in here. That is
    the same rule the thesis has always obeyed and it now covers the whole column.
    """
    # THE COLUMN RULE STOPS AT THE SIGNATURE STRIP. A vertical hairline that runs
    # into the footer divider makes a cross, and a cross in the corner of a card
    # is the one shape that reads as a mistake rather than as a grid.
    parts: list[str] = [
        f'<line x1="{_n(panel_w)}" y1="0" x2="{_n(panel_w)}" y2="{_n(footer_top(height))}" '
        f'stroke="{PALETTE["rule"]}" stroke-width="1"/>'
    ]

    y = 54.0
    parts.extend(_masthead(COLUMN_X, y, COLUMN_MARK_W, accent=accent))
    y += masthead_height(COLUMN_MARK_W) + 28

    parts.append(_eyebrow(COLUMN_X, y, eyebrow))
    y += 30

    inner = panel_w - COLUMN_X * 2
    if label:
        parts.extend(_reverse_block(COLUMN_X, y, inner, label))
        y += 13.0 * 1.85 + 30
    else:
        y += 8

    if thesis:
        budget = max(12, int(inner / (thesis_size * 0.44)))
        for line in _wrap(thesis, budget, thesis_lines):
            parts.append(
                _text(COLUMN_X, y, line, size=thesis_size, fill=PALETTE["ink"],
                      family=FONT_DISPLAY, weight="500")
            )
            y += thesis_size * 1.24

    if extra:
        parts.extend(extra)
    return parts


def _top_banner(
    width: float,
    height: float,
    *,
    eyebrow: str,
    label: str | None,
    thesis: str,
    thesis_size: float = 28.0,
    thesis_lines: int = 2,
    accent: str | None = None,
) -> list[str]:
    """The header as a full-width band, for the tall canvas.

    A 4:5 card cannot use the 16:9 card's left column: a 392px column beside a
    1500px-tall page is a stripe of empty space, and it squeezes the table into
    three columns so narrow that a team name collides with its own odds. That is
    exactly what the first attempt did. Portrait wants a banner across the top
    and the full width for the rows underneath.

    THIS IS THE MASTHEAD IN ITS NATIVE ORIENTATION. The lockup already carries a
    heavy rule above it and a hairline below it, so the band needs no box: it is
    the nameplate, the dateline set against it, and the rule the mark brought with
    it, which is what a front page looks like.
    """
    mark_w = 420.0
    parts: list[str] = list(_masthead(40.0, 52.0, mark_w, accent=accent))
    y = 52.0 + masthead_height(mark_w)

    # The dateline sits on the mark's own closing hairline, at the far side of it.
    parts.append(
        _text(width - 40, y - 12, str(eyebrow).upper(), size=20, fill=PALETTE["ink_dim"],
              weight="700", anchor="end", family=FONT_DISPLAY, spacing=2.2)
    )
    y += 34

    if label:
        parts.extend(_reverse_block(40.0, y, width - 80, label, size=17))
        y += 17 * 1.85 + 26

    if thesis:
        for line in _wrap(thesis, int((width - 80) / (thesis_size * 0.44)), thesis_lines):
            parts.append(
                _text(40.0, y + thesis_size, line, size=thesis_size, fill=PALETTE["ink"],
                      family=FONT_DISPLAY, weight="500")
            )
            y += thesis_size * 1.24

    parts.append(_rule(0, height, width, stroke=PALETTE["rule"]))
    return parts


def _footer(
    lines: list[str], width: float, height: float, *, accent_divider: bool = True
) -> list[str]:
    """The signature strip: the divider, the constants, the address.

    NEVER DROPPED FOR SPACE, ON ANY VARIANT. No other poll's share image carries
    its model constants. That line is the signature, and the 16:9 canvas is the
    one most likely to get squeezed until it falls off, so every card draws it
    from this one function.

    THE DIVIDER IS THE CARD'S ONE PERMITTED ACCENT RULE. The brand allows exactly
    one on a share card, "separating the board from the attribution", which is
    this line and no other. `accent_divider=False` is for the comparison cards,
    whose figures already carry the amber-violet movement pair and which the brand
    book flags must not put cyan beside it.

    THE CONSTANTS ARE MONO AND THE ADDRESS IS NOT. Mono is provenance - run ids,
    config hashes, the numbers a person would paste into a shell. `thepoll.ai` is
    an address a person types into a phone, so it is set in the board face like
    the rest of the card.
    """
    top = height - FOOTER_HEIGHT
    parts = [
        _rule(0, top, width, stroke=PALETTE["accent"] if accent_divider else PALETTE["rule"],
              weight=2 if accent_divider else 1),
    ]
    y = top + 26
    for line in lines[:2]:
        parts.append(
            _text(32, y, _clip(line, 118), size=14, fill=PALETTE["ink_faint"], family=FONT_MONO)
        )
        y += 19
    parts.append(
        _text(width - 32, top + 26, SITE_DOMAIN, size=17,
              fill=PALETTE["ink"], anchor="end", family=FONT_UI, weight="600")
    )
    parts.append(
        _text(width - 32, top + 45, DATA_CREDIT, size=12,
              fill=PALETTE["ink_faint"], anchor="end", family=FONT_UI)
    )
    return parts


def footer_top(height: float) -> float:
    """Where the signature strip begins. Anything above it must stop here."""
    return height - FOOTER_HEIGHT


def _constants_strip(week_view: dict[str, Any], width: float, height: float) -> list[str]:
    """The poll's footer: `params.footer_lines`, which is where the constants are."""
    return _footer(
        list((week_view.get("params") or {}).get("footer_lines") or []), width, height
    )


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
        # A NAMED BRIDGE IS DRAWN IN BONE AND NOT IN THE ACCENT. It used to be
        # gold. The brand permits the accent in four places and a graph edge is
        # not one of them, so the highlight is carried by value instead: bone at
        # full strength against `edge` at half, which separates further than the
        # gold did on this ground anyway.
        named = frozenset((int(edge["source"]), int(edge["target"]))) in named_bridges
        stroke = PALETTE["ink"] if named else PALETTE["edge"]
        opacity = "0.95" if named else "0.55"
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

    # --- the masthead band. Outside the mobile-safe zone on purpose (report 05
    # §6.2): the mark is the signature and the graph is the message.
    parts.extend(_masthead(54, 26, 236.0, accent=PALETTE["accent"]))
    # THE PROVISIONAL LABEL USED TO GO GOLD AND NOW IT GOES BONE. It is a fact
    # about the document, not a number the model produced, so it is not an accent
    # use; full ink against the dim dateline beside it is the louder signal here
    # anyway.
    parts.append(
        _eyebrow(
            CARD_WIDTH - 54,
            60,
            _clip(label, 58) if provisional and label else "SCHEDULE CONNECTIVITY",
            fill=PALETTE["ink"] if provisional and label else PALETTE["ink_dim"],
            anchor="end",
        )
    )
    parts.append(_eyebrow(CARD_WIDTH - 54, 82, f"{season} · WEEK {week}", anchor="end"))
    # THE COUNTER GOES ABOVE THE GRAPH, not below it, and that is not a taste
    # call. The published sentence says "the schedule graph BELOW is what the
    # ranking is standing on" — it is written for the web page, and a card that
    # prints it under the graph makes the project's own copy wrong on the one
    # artifact most likely to be read without its page. Placing rather than
    # rewriting is the same rule every other number on this card obeys.
    y = 100
    for line in _wrap(str(conn.get("counter") or ""), 112, 2):
        parts.append(_text(54, y, line, size=15, fill=PALETTE["ink_dim"], family=FONT_DISPLAY))
        y += 20
    parts.append(_rule(54, 130, CARD_WIDTH - 108, stroke=PALETTE["rule"]))

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
            _eyebrow(rail_x, y, _clip(str(row["label"]), 34), size=12, fill=PALETTE["ink_faint"])
        )
        parts.append(
            _num(
                rail_x,
                y + 28,
                _clip(str(row["display"]), 22),
                size=24,
                fill=PALETTE["ink"],
                anchor="start",
            )
        )
        y += 58

    # --- what would have to be true, inside the safe zone. This is the sentence
    # that makes the graph mean something to a reader who has never seen the site.
    parts.append(_rule(54, 476, CARD_WIDTH - 108, stroke=PALETTE["rule"]))
    claims = list(conn.get("what_would_have_to_be_true") or [])
    y = 500
    for line in _wrap(claims[0] if claims else "", 110, 3):
        parts.append(_text(54, y, line, size=16, fill=PALETTE["ink"], family=FONT_DISPLAY))
        y += 22

    # --- THE CONSTANTS FOOTER IS ON THE CARD AND IS NEVER DROPPED FOR SPACE
    # (report 05 §6.2). No other poll's share image carries its model constants;
    # that line is the signature. Drawn from `_footer` like every other card, so
    # the accent divider and the address cannot drift between variants.
    parts.extend(_footer(footer, CARD_WIDTH, CARD_HEIGHT))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _odds_key(row: dict[str, Any]) -> str:
    """The poll board's right-hand column: the published odds key.

    THE ONE COLUMN ON A BOARD THAT TAKES THE ACCENT, because the brand names it:
    "the schedule-odds key on the board, and the odds column it labels". It is the
    number the model produced, and cyan means the machine.

    `one_in` is published; it is never recomputed from `tail_p`.
    """
    return f"1 in {int(row['one_in']):,}"


def _projected_power(row: dict[str, Any]) -> str:
    """The billboard's right-hand column, and it is the one that SORTS.

    THIS REPLACED `projected_wins` ON THE BILLBOARDS AND THE REASON IS THE ONLY
    reason that matters: the win total does not move with the rank. Ohio State
    projects 8.8 wins at number 1 and Oregon projects 9.0 at number 2, which is
    the whole point of the board (Ohio State's schedule is far harder) and which
    reads at a glance as broken data. The owner caught it on the first render:
    "8.8 above 9.0 reads as broken data."

    Power is the engine's own number and the projection's rows are ordered by it,
    so a reader scanning down the column sees it fall on every row. That is
    checkable rather than asserted: `projected_power` is non-increasing over all
    138 rows of the published document, and a test asserts it on the drawn card.

    `projected_power` arrives PRE-FORMATTED, like every other published figure, so
    the unit is the only thing this adds.
    """
    return f"{row['projected_power']} power"


def _projected_wins(row: dict[str, Any]) -> str:
    """The projection board's right-hand column.

    `projected_wins` arrives PRE-FORMATTED to one decimal place (the fixture
    contract §6), so the unit is the only thing this adds. A card that reformatted
    the number could disagree with the JSON a reader downloads, which is the whole
    reason the field is a string.
    """
    return f"{row['projected_wins']} wins"


def _poll_row(
    row: dict[str, Any],
    x: float,
    y: float,
    width: float,
    *,
    height: float,
    rank_size: float,
    name_size: float,
    value_size: float,
    use_abbreviation: bool,
    value_of: Any = _odds_key,
    value_fill: str | None = None,
    mark_ratio: float = 0.35,
) -> list[str]:
    """One team, on the board's row grid. Every value is printed, none is derived.

    The rank, the record and the right-hand value are fields. This function does
    arithmetic on pixels and on nothing else.

    ONE UNIFORM ROW TREATMENT, AND THAT IS A STANDING RULE RATHER THAN A DEFAULT.
    Rank 1 is drawn exactly like rank 25: same stripe, same numeral weight, same
    mark radius, no crown, no highlight, no heavier separator. A poll whose claim
    is that it has no favourites should not draw one on its own card.

    `value_of` is what makes the row shared between the products: the poll prints
    its odds key and the projection prints its win total, on the same grid, in the
    same slot. `value_fill` is bone unless the caller has a published reason - the
    poll's odds key is the schedule-odds key and takes the accent, and nothing
    else on a row ever does.

    `mark_ratio` is how much of the row's height the school's mark takes. It is a
    knob rather than a constant for exactly one caller: a billboard is read at
    thumbnail scale, where the mark is doing as much identifying work as the
    numeral, so it is drawn larger there than on a board somebody taps into.
    """
    mid = y + height / 2
    parts: list[str] = [
        # The team stripe, clamped. Full row height, 3px, always drawn.
        _slab(x, y + 3, 3, height - 6, stripe_colour(row.get("mark_bg"))),
    ]

    # THE RANK LANE IS FIXED-WIDTH AND THE NUMERAL IS RIGHT-ANCHORED IN IT. Two
    # digits wide, always, so 1 and 25 end in the same column and every mark on
    # the card starts at the same x. This is the tabular-figures fallback the
    # brand book asks for when the renderer will not honour `tnum`, and it is why
    # `_num` exists.
    rank_lane = rank_size * 1.32
    rank_x = x + 14
    parts.append(
        _num(rank_x + rank_lane, mid + rank_size * 0.34, str(int(row["rank"])),
             size=rank_size, fill=PALETTE["ink"])
    )

    mark_r = height * mark_ratio
    mark_cx = rank_x + rank_lane + 14 + mark_r
    parts.append(_mark(mark_cx, mid, mark_r, row))

    name = str(row.get("abbreviation") if use_abbreviation else row.get("team") or "")
    name_x = mark_cx + mark_r + 12
    # The value is right-aligned to the row's right edge and the name is clipped
    # to what is left, so a long school name can never collide with the number.
    # Budgeted in characters because the raster's metrics are the host's.
    value = value_of(row)
    value_w = value_size * len(value) * 0.58
    name_budget = max(4, int((width - (name_x - x) - value_w) / (name_size * 0.52)))
    parts.append(
        _text(name_x, mid + name_size * 0.34, _clip(name, name_budget), size=name_size,
              fill=PALETTE["ink"], weight="600", family=FONT_DISPLAY)
    )

    parts.append(
        _num(x + width, mid + value_size * 0.34, value, size=value_size,
             fill=value_fill or PALETTE["ink"], weight="600")
    )
    return parts


#: How hard a row separator is drawn. The brand's rule token at full strength is
#: 3.89:1, which is right for the structural rules and shouts when it is repeated
#: twenty-five times down a board.
ROW_RULE_OPACITY = 0.38


def _row_block(
    rows: list[dict[str, Any]],
    x: float,
    top: float,
    width: float,
    *,
    height: float,
    **row_kwargs: Any,
) -> list[str]:
    """A column of rows and its separators. Identical treatment on every row.

    THERE IS NO PLAYOFF CUT LINE HERE AND THERE WILL NOT BE ONE. Until
    2026-08-17 this function drew a 2px accent rule after rank 4 on every variant,
    and the module called it "the card's loudest sports signal", which it was: on
    the five-row hero card the cut line WAS the card. It is gone by ruling.

    The argument is not that it looked bad. A poll that publishes its own misses
    and refuses to run a committee has no business drawing the committee's line,
    and a bracket boundary on a preseason projection asserts a claim about
    January that no number on the card supports. The rule is enforced by a test,
    not by this comment: nothing in this module may draw an accent stroke on the
    board.
    """
    parts: list[str] = []
    for i, row in enumerate(rows):
        y = top + i * height
        parts.extend(_poll_row(row, x, y, width, height=height, **row_kwargs))
        parts.append(
            _rule(x, y + height, width, stroke=PALETTE["rule"], opacity=ROW_RULE_OPACITY)
        )
    return parts


def _card_open(width: float, height: float, label: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(width)}" height="{_n(height)}" '
        f'viewBox="0 0 {_n(width)} {_n(height)}" role="img" aria-label="{_esc(label)}">',
        f'<rect width="{_n(width)}" height="{_n(height)}" fill="{PALETTE["bg"]}"/>',
    ]


#: How much of a row's height a school's mark takes on the two SHAREABLE ROW
#: CARDS, and it is a fraction rather than a size because the two rows differ.
#:
#: 0.42 IS THE CEILING THAT GRID ALLOWS, not a taste. A row's separator is drawn
#: at its foot, so a mark of more than 0.42 of the row height starts touching the
#: rule under it, and at 0.5 it crosses into the neighbouring row. The old 0.35
#: left 15% of every row empty above and below the mark, which cost the top ten a
#: third of its logo for nothing. Neither the row heights nor the mobile safe band
#: moved to buy this: the block is the same block and the marks fill it.
#:
#: THE 25 AND THE 138 DO NOT USE THIS. They are tiles, where the mark is capped by
#: the CELL rather than by a row, which is the entire reason they became tiles.
BOARD_MARK_RATIO = 0.42

#: The hero card's row grid, and every number on it is one decision.
#:
#: FIVE ROWS OF 75 STARTING AT `SAFE_TOP` END AT 501, ONE PIXEL INSIDE
#: `SAFE_BOTTOM`. That is the constraint the whole card is built around: X crops
#: the top and bottom on mobile, and the top five is the variant most likely to be
#: seen as a timeline thumbnail and never tapped. Every row has to survive the
#: crop, so the block is sized to the safe band rather than to the canvas, and the
#: wordmark and the constants footer sit outside it as the signature.
#:
#: 75px per row is 2.2x the top ten's 34, which is what buys the card its
#: presence: a 52px mark and a 54px rank numeral are legible at the size a
#: timeline actually shows this, and that is the entire argument for a five-row
#: variant existing beside a ten-row one.
HERO_ROW_HEIGHT = 75.0
HERO_ROW_TOP = float(SAFE_TOP)


def _poll_column(week_view: dict[str, Any], height: float, thesis_size: float) -> list[str]:
    """The poll's masthead column. Every string on it is a published field.

    THE THESIS IS `recipe.one_liner`, WHICH IS PUBLISHED. It is not copy typed
    into this renderer, so a card made under an alternate lens states that lens's
    own argument rather than the house one, and nobody has to remember to change a
    string here when a recipe's prose changes. The label is `recipe.label` for the
    same reason: `docs/fixture-contract-recipes.md` §4 requires the surface to
    show it whenever it is non-null.
    """
    season, week = int(week_view["season"]), int(week_view["week"])
    return _masthead_column(
        COLUMN_W,
        height,
        eyebrow=f"{season} · WEEK {week}",
        label=_lens_banner(week_view),
        thesis=str((week_view.get("recipe") or {}).get("one_liner") or ""),
        thesis_size=thesis_size,
        accent=PALETTE["accent"],
    )


def top5_svg(bundle: Bundle) -> str:
    """The top five, at hero scale. 1200x628, the `summary_large_image` ratio.

    Same structure as the top ten, deliberately: these are the same board and a
    reader should be comparing numbers, not noticing that the card changed shape.
    What changes is the scale.

    THE VARIANT USED TO BE INTERESTING FOR THE WRONG REASON. It was built around
    the cut line falling after rank 4, so that a five-row card was "the whole card
    is the cut line and the one team sitting on the wrong side of it". The cut
    line is gone. What is left is the reason the hero exists in the first place:
    five rows buy a 52px mark and a 54px numeral, and that is what reads in a
    timeline thumbnail, which is where most of these are actually seen.
    """
    week_view = bundle.views["week"]
    rows = list(week_view.get("poll") or [])[:5]
    season, week = int(week_view["season"]), int(week_view["week"])

    parts = _card_open(CARD_WIDTH, CARD_HEIGHT, f"The Poll top five, {season} week {week}")
    parts.extend(_poll_column(week_view, CARD_HEIGHT, thesis_size=25))
    parts.extend(
        _row_block(
            rows,
            COLUMN_W + 32,
            HERO_ROW_TOP,
            CARD_WIDTH - COLUMN_W - 64,
            height=HERO_ROW_HEIGHT,
            rank_size=52,
            name_size=40,
            value_size=32,
            use_abbreviation=False,
            value_fill=PALETTE["accent"],
        )
    )
    parts.extend(_constants_strip(week_view, CARD_WIDTH, CARD_HEIGHT))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def top10_svg(bundle: Bundle) -> str:
    """The top ten. 1200x628, the `summary_large_image` ratio.

    Ten rows of 34px starting at y=144 puts the whole block inside the mobile
    safe band (126..502), so a reader who sees only the cropped middle on X still
    gets the entire ranking. The wordmark and the constants strip sit outside it
    deliberately: they are the signature, not the message.
    """
    week_view = bundle.views["week"]
    rows = list(week_view.get("poll") or [])[:10]
    season, week = int(week_view["season"]), int(week_view["week"])

    parts = _card_open(CARD_WIDTH, CARD_HEIGHT, f"The Poll top ten, {season} week {week}")
    parts.extend(_poll_column(week_view, CARD_HEIGHT, thesis_size=25))
    parts.extend(
        _row_block(
            rows,
            COLUMN_W + 32,
            144.0,
            CARD_WIDTH - COLUMN_W - 64,
            height=34.0,
            rank_size=28,
            name_size=25,
            value_size=24,
            use_abbreviation=False,
            value_fill=PALETTE["accent"],
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
    value_size: float,
) -> str:
    """The top 25 laid into N columns, with the constants strip under it.

    The footer is drawn on the narrow canvas from the same function as everywhere
    else, because the narrow canvas is exactly where it would otherwise get
    squeezed out, and it is the signature.
    """
    week_view = bundle.views["week"]
    rows = list(week_view.get("poll") or [])[:25]
    season, week = int(week_view["season"]), int(week_view["week"])

    parts = _card_open(width, height, f"The Poll top 25, {season} week {week}")
    parts.extend(_poll_column(week_view, height, thesis_size=22))

    area_x, area_w = COLUMN_W + 24, width - COLUMN_W - 48
    gutter = 16.0
    col_w = (area_w - gutter * (len(split) - 1)) / len(split)

    start = 0
    for index, count in enumerate(split):
        chunk = rows[start : start + count]
        x = area_x + index * (col_w + gutter)
        parts.extend(
            _row_block(
                chunk, x, top, col_w, height=row_h,
                rank_size=rank_size, name_size=name_size, value_size=value_size,
                use_abbreviation=True, value_fill=PALETTE["accent"],
            )
        )
        if index < len(split) - 1:
            gx = x + col_w + gutter / 2
            parts.append(
                f'<line x1="{_n(gx)}" y1="{_n(top)}" x2="{_n(gx)}" '
                f'y2="{_n(top + max(split) * row_h)}" stroke="{PALETTE["rule"]}" '
                f'stroke-width="1" stroke-opacity="{_n(ROW_RULE_OPACITY)}"/>'
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
        rank_size=21, name_size=19, value_size=18,
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
    parts.extend(
        _top_banner(
            CARD_WIDTH,
            300.0,
            eyebrow=f"{season} · WEEK {week}",
            label=_lens_banner(week_view),
            thesis=str((week_view.get("recipe") or {}).get("one_liner") or ""),
            accent=PALETTE["accent"],
        )
    )
    parts.extend(
        _row_block(
            rows, 40.0, 344.0, CARD_WIDTH - 80, height=42.0,
            rank_size=30, name_size=27, value_size=25, use_abbreviation=False,
            value_fill=PALETTE["accent"],
        )
    )
    parts.extend(_constants_strip(week_view, CARD_WIDTH, TALL_HEIGHT))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# ------------------------------------------------------------------- the tiles
#
# WHAT A TILE IS AND WHY TWO CARDS NOW SHARE ONE. A ROW is built to be read: the
# eye runs left to right along it and collects a rank, a mark, a name and a
# number. A TILE is built to be recognised: the mark is the biggest thing in the
# cell, the rank sits under it, and the name is a caption rather than the label.
#
# THE OWNER RULED FOR TILES ON THE 25 AND THE 138, on 2026-08-18: those two "must
# MAXIMIZE logo and rank-number size for at-a-glance reading". A row cannot do
# that and the reason is arithmetic rather than taste. On a row, the mark's
# diameter is capped by the row's HEIGHT while the rank lane and the name eat the
# row's WIDTH, so at 25 rows on the wide canvas the mark had 18px and at 138 it
# had 29px - a smudge and a stamp. Stacking the same three things frees the whole
# cell width for the mark, and the same board area draws it at 105px and 65px.
#
# WHAT DOES NOT CHANGE, because it is the brand rather than the layout. We never
# flood a cell with a school's colour: the reference graphics do, and a card of
# 138 team-coloured tiles belongs to the schools rather than to the poll that made
# it. Ours keeps our own ground, sets the numeral in the board face, and gives the
# school's colour the same 3px stripe every row on every other card here gets.
# Rank 1 is drawn exactly like rank 138, and there is no cut line.

#: How many teams sit across each tile card, and both numbers are the answer to
#: the same optimisation rather than a preference.
#:
#: A tile's mark is capped by its cell in both directions: by the width outright,
#: and by the height minus the two lines of caption under it. Columns trade one
#: against the other - more columns give shorter, narrower cells with more of them
#: stacked, fewer give the reverse - so the mark is largest where the two caps
#: meet. On the 2:3 poster that is 14 columns and a 65px mark; at 7 columns the
#: cells are wide and squat and the mark is back to 40px, and at 20 they are too
#: narrow to hold a five-character abbreviation.
#:
#: FOURTEEN ALSO READS AS DECADES, which is a free property rather than the
#: reason: ten deep means a column is 1-10, the next is 11-20, and a reader
#: hunting the fifties goes to the sixth column instead of counting.
GRID_COLUMNS = 14
TOP25_COLUMNS = 5

#: The caption under the mark, as fractions of the cell's height. The rank is
#: more than twice the name because the rank is the number the card is FOR and
#: the name is the confirmation a reader checks after the mark has already told
#: them who it is.
TILE_RANK_RATIO = 0.26
TILE_NAME_RATIO = 0.11
#: Breathing room inside a cell, on every side. Small on purpose: every pixel
#: spent here comes off the mark's diameter.
TILE_PAD = 6.0


def _grid_cells(total: int, columns: int) -> list[tuple[int, int]]:
    """Where each rank sits on the grid, as `(column, line)`, in rank order.

    THE ORDER IS DOWN EACH COLUMN AND THEN ACROSS, WHICH IS A CORRECTION. The
    first version of this card filled the grid across the rows: 1 to 7 along the
    top, 8 to 14 under it. Every poll a football fan has ever read runs
    top-to-bottom, so a reader looking for the teams around 20th scanned the
    left edge, found 15, and read a board that did not mean what they thought it
    meant. Filling down the columns puts 1 to 20 under each other and moves 21 to
    the top of the next column, which is a newspaper agate page.

    THE SHORT COLUMNS ARE ON THE RIGHT AND THE HOLE IS AT THE BOTTOM. 138 teams
    over fourteen columns is 10 rows with two short of a full grid, so the first
    twelve columns carry 10 and the last two carry 9. Column 0 is always one of
    the full ones, which is what lets the caller draw a horizontal rule per line
    off that column alone.
    """
    lines = -(-total // columns)
    tall = total - columns * (lines - 1)
    return [
        (column, line)
        for column in range(columns)
        for line in range(lines if column < tall else lines - 1)
    ]


def _tile(
    row: dict[str, Any],
    cx: float,
    cy: float,
    cell_w: float,
    cell_h: float,
    *,
    mark_r: float,
    rank_size: float,
    name_size: float,
    use_abbreviation: bool,
) -> list[str]:
    """One team in one cell: the stripe, the mark, the rank under it, the name.

    THE MARK IS CENTRED AND SO IS THE NUMERAL, WHICH SUSPENDS THE RIGHT-ANCHOR
    RULE AND ONLY HERE. Everywhere else on this card set a rank is right-anchored
    in a fixed lane, because that is the fallback for a renderer that ignores
    `tnum` and it is what makes 1 and 25 end in the same column down a row block.
    A tile has no such column: the thing a reader lines up on is the mark's own
    axis, and a numeral pinned to a lane while the mark above it is centred reads
    as a misprint. Centred on the same axis as the mark, 1 and 138 both sit under
    their school.
    """
    mid = cx + cell_w / 2
    parts: list[str] = [
        _slab(cx, cy + 3, 3, cell_h - 6, stripe_colour(row.get("mark_bg"))),
        *(_mark(mid, cy + TILE_PAD + mark_r, mark_r, row),),
    ]

    rank_y = cy + TILE_PAD + mark_r * 2 + rank_size
    parts.append(
        _num(mid, rank_y, str(int(row["rank"])), size=rank_size,
             fill=PALETTE["ink"], anchor="middle")
    )

    name = str(row.get("abbreviation") if use_abbreviation else row.get("team") or "")
    budget = max(3, int((cell_w - TILE_PAD * 2) / (name_size * 0.52)))
    parts.append(
        _text(mid, rank_y + name_size * 1.2, _clip(name, budget), size=name_size,
              fill=PALETTE["ink_dim"], weight="600", anchor="middle", family=FONT_DISPLAY)
    )
    return parts


def _tile_block(
    rows: list[dict[str, Any]],
    x: float,
    top: float,
    width: float,
    height: float,
    *,
    columns: int,
    use_abbreviation: bool,
) -> list[str]:
    """A tile grid filling the box, sized so the marks are as large as it allows.

    NOTHING HERE IS A TYPE SIZE SOMEBODY CHOSE. The caller hands over a box and a
    column count; the cell falls out of those, the caption falls out of the cell,
    and the mark takes whatever the cell has left in its tighter direction. That
    is what makes "maximise the logo" a property of the function rather than a
    number a later edit can quietly walk back.
    """
    cells = _grid_cells(len(rows), columns)
    lines = max(line for _column, line in cells) + 1
    cell_w = width / columns
    cell_h = height / lines

    rank_size = cell_h * TILE_RANK_RATIO
    name_size = cell_h * TILE_NAME_RATIO
    caption = rank_size * 1.12 + name_size * 1.30
    mark_r = max(
        6.0,
        min(cell_w - TILE_PAD * 2, cell_h - caption - TILE_PAD * 2) / 2,
    )

    parts: list[str] = []
    for index, row in enumerate(rows):
        column, line = cells[index]
        cx, cy = x + column * cell_w, top + line * cell_h
        parts.extend(
            _tile(row, cx, cy, cell_w, cell_h, mark_r=mark_r, rank_size=rank_size,
                  name_size=name_size, use_abbreviation=use_abbreviation)
        )
        if column < columns - 1:
            parts.append(
                f'<line x1="{_n(cx + cell_w)}" y1="{_n(cy + 4)}" x2="{_n(cx + cell_w)}" '
                f'y2="{_n(cy + cell_h - 4)}" stroke="{PALETTE["rule"]}" stroke-width="1" '
                f'stroke-opacity="{_n(ROW_RULE_OPACITY)}"/>'
            )
        if column == 0 and line:
            parts.append(_rule(x, cy, width, stroke=PALETTE["rule"], opacity=ROW_RULE_OPACITY))
    return parts


#: The band the tagline sits in, between the board and the signature strip, on
#: the two cards whose layout has room for a sentence.
#:
#: THIS IS THE BILLBOARD'S LINE ON A CARD THAT IS NOT A BILLBOARD, and it is the
#: owner's call of 2026-08-18: the teaser goes "where the layout carries copy".
#: The reasoning transfers cleanly. A tile card is the one somebody posts to be
#: looked at rather than read, so it meets the same stranger the billboards were
#: written for, and that stranger needs one sentence telling him what he is
#: looking at and where to go next. The wide cards keep their masthead column,
#: which already runs the document's own headline, and get no teaser: a second
#: piece of prose beside the first would be two arguments in one corner.
#:
#: WHAT DOES NOT COME WITH IT IS THE CLARITY LINE OR THE BILLBOARD'S FOOTER. The
#: counts sentence is 200 characters and belongs to a card with nothing else on
#: it, and the constants footer stays exactly where `AGENTS.md` puts it, because
#: these are cards built to be READ and the owner's "no stat nerd shit" ruling was
#: confined to the billboards by name.
TEASER_HEIGHT = 68.0
TEASER_SIZE = 22.0


def _teaser(width: float, height: float) -> list[str]:
    """The tagline, above the signature strip. Drawn from the module constant."""
    top = footer_top(height) - TEASER_HEIGHT
    parts = [_rule(40, top, width - 80, stroke=PALETTE["rule"], opacity=ROW_RULE_OPACITY)]
    y = top + 32
    budget = max(24, int((width - 80) / (TEASER_SIZE * 0.44)))
    for line in _wrap(BILLBOARD_TEASER, budget, 2):
        parts.append(
            _text(40, y, line, size=TEASER_SIZE, fill=PALETTE["ink"],
                  family=FONT_DISPLAY, weight="600")
        )
        y += TEASER_SIZE * 1.28
    return parts


# ------------------------------------------------------------------ the projection


def _projection_rows(document: dict[str, Any], top_n: int) -> list[dict[str, Any]]:
    """The board, refused rather than half-drawn when the document is not one.

    A share card is a published claim (report 05 §6.1(2)), so drawing one from a
    document whose own `status` says it is dark would publish the thing the status
    field exists to keep unpublished. `status` is authoritative and is never
    inferred from the row count, which is exactly why it has to be READ.
    """
    status = str(document.get("status") or "")
    if status != "published":
        raise ValueError(
            f"the projection's status is {status!r}; a share card is a published "
            "claim and this document says it is not published yet"
        )
    rows = list(document.get("rows") or [])
    if not rows:
        raise ValueError("the projection carries no rows to draw")
    return rows[:top_n]


def _field_size(document: dict[str, Any]) -> int:
    """HOW MANY TEAMS THE MODEL RANKS. Read from the document, never counted off
    the slice a card happens to be drawing.

    This exists because the sentence it feeds is the one the project keeps
    getting wrong in both directions. A card showing 25 rows that says "25 teams"
    has told a stranger the model ranks a quarter of the sport; the truth is that
    it ranks the whole of it and shows the top of it. `schedule.field_size` is the
    published field for exactly this and is preferred; the row count is the
    fallback for a document written before that field existed, and it is right
    only because the full document carries every ranked team.
    """
    size = (document.get("schedule") or {}).get("field_size")
    return int(size) if size else len(document.get("rows") or [])


#: WHAT THE PROJECTION CARD CALLS ITSELF, in the dateline, on every canvas.
#: The old card set THE PROJECTION where the poll set THE POLL, as a drawn
#: wordmark. That cannot survive the brand: there is one mark, it is The Poll.ai,
#: and it may not be restacked, relettered or recoloured. So the mark goes on the
#: card as the mark and the artifact names itself in the dateline underneath,
#: which is exactly how a newspaper distinguishes a nameplate from a headline.
#:
#: ADR 0010'S CONCERN IS ANSWERED MORE STRONGLY THAN BEFORE, not weakened. What
#: kept the projection from being read as the poll was never the wordmark: it was
#: the document's own `label`, which says "This is a PROJECTION. It is not the
#: poll, it never becomes the poll". That string is still drawn from the document
#: and is now set as a bone reverse block at 15.18:1, where it used to be 12px on
#: a gold bar. The dateline says PROJECTION and the block says what that means.
PROJECTION_EYEBROW = "{season} PRESEASON PROJECTION"


def _projection_column(
    document: dict[str, Any], panel_w: float, height: float, thesis_size: float
) -> list[str]:
    """The projection's masthead column. Every string is read from the document."""
    return _masthead_column(
        panel_w,
        height,
        eyebrow=PROJECTION_EYEBROW.format(season=int(document["season"])),
        label=str(document.get("label") or "") or None,
        thesis=str(document.get("headline") or ""),
        thesis_size=thesis_size,
        thesis_lines=7,
        accent=PALETTE["accent"],
    )


def _projection_footer_lines(document: dict[str, Any]) -> list[str]:
    """The projection's signature: provenance, then the backtest that lost.

    The poll card's footer carries the model constants because no other poll's
    share image does. The projection's equivalent is the measured record of the
    method against the AP's August ballot, published on the image itself, whether
    or not it flatters. Every figure is a published field printed verbatim.

    THE SECOND LINE IS REWRITTEN AND NOT ONE NUMBER MOVED. The brand audit read
    the shipping card and found `backtest, 3 transitions: AP 13.8 top 25 hits,
    this projection 12.8, carry forward 13.0` - "four unexplained numbers on the
    surface a stranger meets first". A footer nobody can parse is not a signature,
    it is noise wearing one. So the same four fields now say what they are: how
    many past Augusts, what was counted, and who did better. The AP still beats
    us on this line, which is the point of printing it.
    """
    lines = [
        f"recipe {document.get('projection_version')} · the poll grades this from "
        f"week {document.get('grading_start_week')}"
    ]
    backtest = document.get("backtest") or {}
    if backtest:
        lines.append(
            f"{backtest.get('transitions')} past preseasons, hits in the final top 25: "
            f"AP {backtest.get('ap_top25_hits')} · this recipe "
            f"{backtest.get('projection_top25_hits')} · last year's board carried "
            f"forward {backtest.get('naive_top25_hits')}"
        )
    return lines


def _projection_footer(document: dict[str, Any], width: float, height: float) -> list[str]:
    return _footer(_projection_footer_lines(document), width, height)


def projection_top5_svg(document: dict[str, Any]) -> str:
    """The projected top five, on the poll hero card's grid exactly.

    Same 75px rows, same 52px numerals, same safe-band block, because the two
    boards get posted side by side and the only thing that should differ between
    them is what they say. What differs: the dateline reads PRESEASON PROJECTION,
    the right-hand column is `projected_wins`, and the footer is the backtest
    rather than the model constants.

    THE WIN COLUMN IS BONE AND THE POLL'S ODDS COLUMN IS CYAN, and that is the
    accent rule doing real work rather than decoration. The brand permits the
    accent on "the schedule-odds key and the odds column it labels". A projected
    win total is not the schedule-odds key. So the difference a reader sees
    between the two boards is not a shape or a wordmark; it is that one of them
    has the key on it and the other does not.
    """
    rows = _projection_rows(document, 5)
    season = int(document["season"])

    parts = _card_open(CARD_WIDTH, CARD_HEIGHT, f"The Projection top five, {season} preseason")
    parts.extend(_projection_column(document, COLUMN_W, CARD_HEIGHT, thesis_size=21))
    parts.extend(
        _row_block(
            rows,
            COLUMN_W + 32,
            HERO_ROW_TOP,
            CARD_WIDTH - COLUMN_W - 64,
            height=HERO_ROW_HEIGHT,
            rank_size=52,
            name_size=40,
            value_size=32,
            use_abbreviation=False,
            value_of=_projected_wins,
            mark_ratio=BOARD_MARK_RATIO,
        )
    )
    parts.extend(_projection_footer(document, CARD_WIDTH, CARD_HEIGHT))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def projection_top10_svg(document: dict[str, Any]) -> str:
    """The projected top ten. Same canvas and same grid as the poll's top ten.

    Deliberately the same geometry: the two boards sit on one page and a reader
    comparing them should be comparing the numbers, not noticing that one card's
    rows are taller. What differs is what the card says it is, and the column on
    the right: `projected_wins` where the poll prints its odds key.
    """
    rows = _projection_rows(document, 10)
    season = int(document["season"])

    parts = _card_open(CARD_WIDTH, CARD_HEIGHT, f"The Projection top ten, {season} preseason")
    parts.extend(_projection_column(document, COLUMN_W, CARD_HEIGHT, thesis_size=21))
    parts.extend(
        _row_block(
            rows,
            COLUMN_W + 32,
            144.0,
            CARD_WIDTH - COLUMN_W - 64,
            height=34.0,
            rank_size=28,
            name_size=25,
            value_size=24,
            use_abbreviation=False,
            value_of=_projected_wins,
            mark_ratio=BOARD_MARK_RATIO,
        )
    )
    parts.extend(_projection_footer(document, CARD_WIDTH, CARD_HEIGHT))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


#: Where a tile card's board begins and how tall its header band is. Shared by
#: the 25 and the 138 so the two read as one format at two densities: same
#: banner, same first line of tiles, same tagline band, same signature strip.
TILE_BANNER_H = 300.0
TILE_BOARD_TOP = 336.0


def _tile_card(
    document: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    height: float,
    columns: int,
    label: str,
    thesis: str,
    use_abbreviation: bool,
) -> str:
    """A tile card end to end: banner, tiles, tagline, signature. Both callers.

    The 25 and the 138 differ in three arguments and in nothing else, which is
    the point: a reader who has learned to read one of them has learned the
    other, and a change to the format cannot land on one card and miss its twin.
    """
    season = int(document["season"])
    parts = _card_open(CARD_WIDTH, height, label)
    parts.extend(
        _top_banner(
            CARD_WIDTH,
            TILE_BANNER_H,
            eyebrow=PROJECTION_EYEBROW.format(season=season),
            label=str(document.get("label") or "") or None,
            thesis=thesis,
            thesis_size=26,
            thesis_lines=1,
            accent=PALETTE["accent"],
        )
    )
    board_bottom = footer_top(height) - TEASER_HEIGHT - 12
    parts.extend(
        _tile_block(
            rows,
            40.0,
            TILE_BOARD_TOP,
            CARD_WIDTH - 80,
            board_bottom - TILE_BOARD_TOP,
            columns=columns,
            use_abbreviation=use_abbreviation,
        )
    )
    parts.extend(_teaser(CARD_WIDTH, height))
    parts.extend(_projection_footer(document, CARD_WIDTH, height))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def projection_top25_svg(document: dict[str, Any]) -> str:
    """The projected top 25 as a 5x5 tile grid on the 1200x1500 canvas.

    IT LEFT THE 16:9 CANVAS AND THAT IS A REVERSAL WITH A PRICE. The previous
    version of this card argued for `summary_large_image` because "its job is to
    be the image that embeds anywhere", and it drew 25 rows of 26px to get there:
    a 21px rank numeral and an 18px school mark, on the card the owner named as
    the one that has to read at a glance. Both jobs do not fit on one canvas. The
    ruling of 2026-08-18 chose the glance, so the 25 goes portrait and the top
    ten - same board, same brand, native to 1.91:1 - is what the link preview
    picks up. See `share.ts`, which selects the widest ranking rather than a
    variant name, so nothing had to be told about this.

    WHAT THE CANVAS BOUGHT: the mark goes from 18px to about 105px and the rank
    numeral from 21px to about 49px. That is the whole change. Same rows, same
    fields, same uniform treatment, same footer.

    THE FULL SCHOOL NAME RATHER THAN THE ABBREVIATION, unlike the 138. A 224px
    cell holds `Mississippi State` at caption size and the mark has already done
    the identifying anyway; the poster's 80px cells have room for four letters and
    no more, which is the only reason that card abbreviates.
    """
    rows = _projection_rows(document, 25)
    season = int(document["season"])
    return _tile_card(
        document,
        rows,
        height=TALL_HEIGHT,
        columns=TOP25_COLUMNS,
        label=f"The Projection top 25, {season} preseason",
        thesis=f"The top {len(rows)} of the {_field_size(document)} teams the model ranks.",
        use_abbreviation=False,
    )


#: THE ONLY PNG CHUNKS A PUBLISHED CARD MAY CARRY. Everything else is stripped,
#: whether or not this renderer is the thing that put it there.
#:
#: THIS IS A DISTRIBUTION REQUIREMENT AND NOT TIDINESS. Meta and TikTok apply
#: AI-generated labels from FILE METADATA rather than from what the image shows,
#: and on TikTok that label cannot be removed once applied. A card is a table of
#: real numbers that Python drew; a C2PA manifest (`caBX`), an XMP packet (`iTXt`)
#: or an EXIF block (`eXIf`) left behind by any tool in the chain can get it
#: badged as generated anyway. The chain today is clean - the pinned resvg writes
#: IHDR, IDAT, IEND and nothing else - and that is exactly why the guard belongs
#: in the code now, while there is nothing to remove, rather than after a wheel
#: upgrade quietly starts stamping one.
#:
#: WHAT IS KEPT AND WHY: the four structural chunks a decoder needs, plus the
#: three colour-space chunks, which describe how to display the pixels and carry
#: no provenance. `tIME`, `tEXt`, `zTXt`, `iTXt`, `eXIf`, `caBX` and anything
#: unrecognised are dropped.
PNG_ALLOWED_CHUNKS: frozenset[bytes] = frozenset(
    {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND", b"sRGB", b"gAMA", b"cHRM"}
)


def png_chunks(raw: bytes) -> list[str]:
    """Every chunk type in a PNG, in file order. What the metadata check reads."""
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    out: list[str] = []
    offset = 8
    while offset + 8 <= len(raw):
        length = int.from_bytes(raw[offset : offset + 4], "big")
        kind = raw[offset + 4 : offset + 8]
        out.append(kind.decode("latin-1"))
        if kind == b"IEND":
            break
        offset += 12 + length
    return out


def png_metadata_chunks(raw: bytes) -> list[str]:
    """The chunks in this PNG that are NOT on the allow-list. Empty is the pass."""
    return [kind for kind in png_chunks(raw) if kind.encode("latin-1") not in PNG_ALLOWED_CHUNKS]


def strip_png_metadata(raw: bytes) -> bytes:
    """Drop every chunk outside `PNG_ALLOWED_CHUNKS`. Pixels are untouched.

    Chunk-level surgery rather than a re-encode, deliberately: re-encoding would
    change the IDAT bytes and therefore the sha256 of a published artifact for a
    reason that has nothing to do with what the card says. Copying the structural
    chunks through leaves an identical image and a file that cannot be labelled
    off its own metadata, because it has none.
    """
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    out = bytearray(raw[:8])
    offset = 8
    while offset + 8 <= len(raw):
        length = int.from_bytes(raw[offset : offset + 4], "big")
        kind = raw[offset + 4 : offset + 8]
        end = offset + 12 + length
        if kind in PNG_ALLOWED_CHUNKS:
            out += raw[offset:end]
        if kind == b"IEND":
            break
        offset = end
    return bytes(out)


# ------------------------------------------------------------------- the poster


def grid_svg(document: dict[str, Any]) -> str:
    """Every ranked team on one card. The format this brand had to survive.

    THE ONE DECISION THAT GOVERNS THIS CARD, and it is the brand book's: **we
    never flood a cell with a school's colour.** The graphics this format is
    borrowed from fill every tile with team colours, and the result belongs to the
    schools rather than to the poll that made it - 138 colour schemes fighting,
    and a card that could be any conference's promo. Ours keeps our own ground,
    sets the rank numeral in the board face, draws the school's mark as the
    biggest thing in the cell, and gives the school's colour exactly the 3px
    stripe every board on this card set already gives it.

    That is what keeps the card ours, and it is the same independence promise the
    site prints above the board: a poll with no favourites does not wear
    anybody's palette, not even 138 of them at once.

    IT IS A POSTER NOW AND IT USED TO BE AN AGATE PAGE. Until 2026-08-18 this drew
    138 rows of rank-mark-name across seven columns of the 4:5 canvas, which put
    the mark at 29px: identifiable if you already knew which logo you were looking
    for, and a smudge if you did not. The owner's ruling was to maximise the mark
    and the numeral, so the row became a tile, the seven columns became fourteen,
    and the canvas went to 2:3. The mark is about 65px and the numeral about 34px.
    `_tile_block` derives both from the box rather than naming them, so the claim
    survives the next edit.

    ORDERED BY RANK, DOWN EACH COLUMN AND THEN ACROSS, which is how a poll is
    read. `_grid_cells` holds that arithmetic and says why. An alphabetical grid
    would serve a reader hunting for one school better and a reader looking at the
    shape of the board not at all, and the second is what a ranking card is for.
    """
    rows = _projection_rows(document, 138)
    season = int(document["season"])
    return _tile_card(
        document,
        rows,
        height=POSTER_HEIGHT,
        columns=GRID_COLUMNS,
        label=f"All {len(rows)} teams, {season} preseason",
        thesis=f"Every one of the {len(rows)} teams the model ranks, in order.",
        use_abbreviation=True,
    )


# ---------------------------------------------------------------- the billboard
#
# WHAT A BILLBOARD IS FOR, AND WHY IT IS NOT JUST A BIGGER TOP FIVE. Every other
# card in this set is built to be READ: it assumes somebody stopped, tapped, and
# is now looking at a table. A billboard assumes the opposite. It is seen at
# thumbnail size, in a feed, by somebody scrolling past who has never heard of
# this project, and it has to survive that with the rank numerals and the school
# marks alone. So the numbers are drawn at roughly twice the hero card's scale on
# the square canvas every platform crops least, and the only prose on it is one
# teaser that says what this is and where to find it.
#
# THE OWNER ASKED FOR THIS DIRECTLY, on 2026-08-17, having looked at the launch
# set and found it legible and silent: huge ranks, real logos, and one short line
# for the curious. The copy below is his, tightened against the voice profile
# rather than rewritten.
#
# AND THE CONSTANTS FOOTER COMES OFF THIS FAMILY, WHICH IS A REVERSAL OF A
# STANDING RULE. `AGENTS.md` says the footer "is on every card and is never
# dropped for space", the voice profile carves it out of the banned-strings rule
# by name, and this module has argued for it at length. The owner overruled it for
# the billboards on 2026-08-18, verbatim: "No stat nerd shit. Just the taglines."
#
# The old reasoning is restated rather than deleted, because it still governs
# every other card here: a share card that argues with the published poll should
# argue with its own constants visible, and no other poll's share image publishes
# the numbers that produced it. What changed is the audience. A billboard is aimed
# at somebody who has never heard of this project, where a run id and a backtest
# line are not a signature, they are the reason he keeps scrolling. Every card
# built to be READ still carries the footer, and `_projection_footer` is untouched;
# the receipts are one tap away on the site the tagline names. That is the owner's
# call on his own project, and it is confined to this family by construction:
# `BILLBOARD_VARIANTS` is the only place `_billboard_credit` is drawn.


#: THE CLARITY LINE, AND EVERY NUMBER IN IT COMES OUT OF A FILE. The owner's draft
#: was "AI used 5 seasons of publicly available football stats - N stats, N games,
#: N simulations - to build a projection and a poll that follows the data", with
#: the counts left as N and one instruction attached: pull the true numbers from
#: the pipeline, no placeholders ship.
#:
#: SO NOTHING HERE IS TYPED. `data/corpus-counts.json` is written by
#: `scripts/count_corpus.py`, which counts through the pipeline's own loaders, and
#: this template is filled from it at render time. A number typed into a renderer
#: is the number that goes stale the first week of the season, and `AGENTS.md` is
#: explicit that a run-produced figure is regenerated rather than quoted.
#:
#: WHAT WAS TIGHTENED. The em dashes are banned outright, so the counts become an
#: appositive between commas. "N stats" is not a thing anybody counts, and the
#: measurable quantity underneath it is plays, so the card says plays. And
#: "simulations" needed checking rather than repeating: the headline tail is an
#: exact Poisson-binomial convolution and simulates nothing, but `bootstrap.simulate`
#: genuinely does "simulate `draws` seasons on the fixed schedule and re-rank each
#: one", so the word is honest as long as it points at the bootstrap. It does.
BILLBOARD_CLARITY = (
    "An AI read five seasons of public college football data, {games} games and "
    "{plays} plays, and simulated {simulated_seasons} seasons to build a "
    "projection and a poll that follow the data."
)

#: THE TAGLINE. The owner's four beats, and his 2026-08-18 correction to the last
#: one: "If you don't agree, try to improve it" beats "try to improve it", because
#: clarity beats compression and the reader needs to be told what the disagreement
#: is FOR. The voice profile picked the same fix up as an addendum the same day.
#:
#: "Fully unbiased" is still not what this says. It is an absolute claim about our
#: own work, which this project makes nowhere else about itself; the checkable
#: version is that no ballot enters either product, and that is what ships. The
#: address is `SITE_DOMAIN` rather than a second typed copy of the host.
BILLBOARD_TEASER = (
    "No human vote goes into either one. The code is open at "
    f"{SITE_DOMAIN}. If you don't agree, try to improve it."
)

#: Where the counts come from. A second pinned input beside the logo cache, and
#: the same property: the card is a pure function of files a reader can open.
CORPUS_COUNTS_PATH = Path(__file__).resolve().parents[3] / "data" / "corpus-counts.json"

#: The billboard's grid, on the 1200x1200 canvas.
#:
#: FIVE ROWS OF 138 FROM 286 END AT 976, which leaves the copy its own band at the
#: foot of the card and nothing else on it at all. 138px per row is 1.84x the hero
#: card's 75 and about 5.3x the top 25's 26: the rank numeral lands at 96px and the
#: school mark at 121px across, which is what still reads when a 1200px card is
#: drawn 300px wide in somebody's feed.
BILLBOARD_BANNER_H = 250.0
BILLBOARD_ROW_TOP = 286.0
BILLBOARD_ROW_HEIGHT = 138.0

#: The copy band, identical on both billboards so the pair reads as one family.
#: The clarity line explains and the tagline invites, so the tagline is the larger
#: of the two and sits last, where a reader who got that far is ready to be asked
#: for something. Two lines each at these sizes finish at 1113, which clears the
#: attribution strip. The hairline above the band is the last row's separator on
#: the top-five card, and the single-team card draws the same line at the same y.
BILLBOARD_TEASER_RULE = BILLBOARD_ROW_TOP + 5 * BILLBOARD_ROW_HEIGHT
BILLBOARD_CLARITY_TOP = 1012.0
BILLBOARD_CLARITY_SIZE = 22.0
BILLBOARD_TEASER_TOP = 1082.0
BILLBOARD_TEASER_SIZE = 25.0


def _billboard_banner(document: dict[str, Any]) -> list[str]:
    """The billboard's header: the mark, the dateline, and the document's label.

    THE LABEL IS NOT OPTIONAL HERE AND IT IS THE ONE THING A BILLBOARD MAY NOT
    DROP FOR SPACE. `docs/fixture-contract-recipes.md` §4 requires the surface to
    show `label` whenever it is non-null, and on the projection that string is
    "THE PROJECTION. The poll grades it weekly." A card built to be seen by people
    who have never heard of this project is exactly the surface where letting a
    projection pass for the poll would do the most damage, which is ADR 0010's
    whole concern.

    The document's `headline` is the one field a billboard leaves behind. Every
    other projection card runs it as the thesis; here the teaser has that slot,
    because a reader who has not stopped scrolling has room for one sentence and
    it needs to be the one that says where to go next.
    """
    return _top_banner(
        CARD_WIDTH,
        BILLBOARD_BANNER_H,
        eyebrow=PROJECTION_EYEBROW.format(season=int(document["season"])),
        label=str(document.get("label") or "") or None,
        thesis="",
        accent=PALETTE["accent"],
    )


def corpus_counts(path: Path | None = None) -> dict[str, Any]:
    """The pinned counts the clarity line is filled from. Read, never computed.

    A missing or unreadable pin is a HARD FAILURE rather than a card with a gap
    in the sentence, because the whole instruction attached to this line was that
    no placeholder ships. `scripts/count_corpus.py` writes the file.
    """
    target = Path(path) if path is not None else CORPUS_COUNTS_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"{target} is missing and a billboard prints its counts. Run "
            "`uv run python scripts/count_corpus.py` to regenerate the pin."
        ) from exc
    missing = [k for k in ("games", "plays", "simulated_seasons") if not payload.get(k)]
    if missing:
        raise ValueError(f"{target} is missing {missing}; a billboard cannot print a blank count")
    return payload


def _billboard_copy(width: float, counts: dict[str, Any] | None = None) -> list[str]:
    """The clarity line and the tagline. The only prose on the card.

    THE COUNTS ARE FORMATTED HERE AND NOWHERE ELSE, with thousands separators,
    because a bare 1235232 on a card is a number nobody can read at a glance and
    an exact 1,235,232 is more credible than a rounded 1.2 million. Both are true;
    only one of them sounds like somebody counted.
    """
    figures = counts if counts is not None else corpus_counts()
    clarity = BILLBOARD_CLARITY.format(
        games=f"{int(figures['games']):,}",
        plays=f"{int(figures['plays']):,}",
        simulated_seasons=f"{int(figures['simulated_seasons']):,}",
    )

    parts: list[str] = []
    y = BILLBOARD_CLARITY_TOP
    budget = max(24, int((width - 80) / (BILLBOARD_CLARITY_SIZE * 0.44)))
    for line in _wrap(clarity, budget, 2):
        parts.append(
            _text(40.0, y, line, size=BILLBOARD_CLARITY_SIZE, fill=PALETTE["ink_dim"],
                  family=FONT_DISPLAY)
        )
        y += BILLBOARD_CLARITY_SIZE * 1.28

    y = BILLBOARD_TEASER_TOP
    budget = max(24, int((width - 80) / (BILLBOARD_TEASER_SIZE * 0.44)))
    for line in _wrap(BILLBOARD_TEASER, budget, 2):
        parts.append(
            _text(40.0, y, line, size=BILLBOARD_TEASER_SIZE, fill=PALETTE["ink"],
                  family=FONT_DISPLAY, weight="600")
        )
        y += BILLBOARD_TEASER_SIZE * 1.28
    return parts


#: The attribution strip that stands where the constants footer stands on every
#: other card: one accent divider and one line of credit, 44px instead of 66.
BILLBOARD_CREDIT_H = 44.0


def _billboard_credit(width: float, height: float) -> list[str]:
    """The billboard's foot: the permitted divider, and CFBD's name. Nothing else.

    WHAT IS NOT HERE IS THE POINT. No run id, no config hash, no recipe version,
    no backtest line, no constants. The owner struck all of it from this family
    on 2026-08-18 and the section comment above records why the rule it broke
    existed in the first place.

    THE ONE LINE THAT SURVIVED IS NOT A CONSTANT AND IS NOT NEGOTIABLE THE SAME
    WAY. `AGENTS.md` puts CFBD's attribution at the top rather than in a footnote,
    their terms call it strongly encouraged, and this project gives it "on every
    published poll and every post". It is 12px, it names a person's work, and it
    is not the stat-nerd material that was struck. The address is not repeated
    here either: the tagline says it in a sentence, which is where somebody
    reading a billboard will actually meet it.
    """
    top = height - BILLBOARD_CREDIT_H
    return [
        _rule(0, top, width, stroke=PALETTE["accent"], weight=2),
        _text(width - 32, top + 26, DATA_CREDIT, size=12,
              fill=PALETTE["ink_faint"], anchor="end", family=FONT_UI),
    ]


def billboard_top5_svg(document: dict[str, Any]) -> str:
    """The projected top five at billboard scale. 1200x1200, the square canvas.

    THE SQUARE IS THE FEED CANVAS AND THAT IS WHY THIS IS NOT THE HERO CARD AGAIN.
    Instagram shows a 1:1 whole, X shows it whole, and a Reddit or LinkedIn
    thumbnail does not letterbox it, so a square is the shape that arrives intact
    wherever it is posted. The 1200x628 hero exists for the link preview, where the
    ratio is fixed for us; this one exists for the post itself.

    Same rows, same fields, same uniform treatment as every other board here: rank
    1 is drawn exactly like rank 5, and the power column is bone because power is
    not the schedule-odds key.

    THE COLUMN IS POWER AND NOT PROJECTED WINS, which is the difference between a
    board that reads and a board that reads as broken. See `_projected_power`.
    """
    rows = _projection_rows(document, 5)
    season = int(document["season"])

    parts = _card_open(
        CARD_WIDTH, SQUARE_HEIGHT, f"The Projection top five, {season} preseason"
    )
    parts.extend(_billboard_banner(document))
    parts.extend(
        _row_block(
            rows,
            40.0,
            BILLBOARD_ROW_TOP,
            CARD_WIDTH - 80,
            height=BILLBOARD_ROW_HEIGHT,
            rank_size=96,
            name_size=62,
            value_size=44,
            use_abbreviation=False,
            value_of=_projected_power,
            mark_ratio=0.44,
        )
    )
    parts.extend(_billboard_copy(CARD_WIDTH))
    parts.extend(_billboard_credit(CARD_WIDTH, SQUARE_HEIGHT))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


#: The single-team billboard's numeral and mark, which are the whole card.
#: A 340px numeral beside a 340px mark is the largest pair the square canvas holds
#: with the banner above it and the school beneath it, and it is the size at which
#: a THREE-DIGIT rank still fits: 138 advances about 632px, which leaves the mark
#: its 340 and still clears the right margin. The board runs to 138 and a card
#: that only composed for the top 25 would be a card for a quarter of the league.
BILLBOARD_TEAM_RANK_SIZE = 340.0
BILLBOARD_TEAM_MARK_R = 170.0
BILLBOARD_TEAM_BASELINE = 640.0


def billboard_team_svg(document: dict[str, Any], team: str) -> str:
    """ONE team, one rank, at poster scale. The template a season of posts runs on.

    A template rather than a card, like the disagreement variant: `team` names the
    school and every other string comes out of the published document, so the next
    one of these is one argument changed rather than an afternoon in an editor.

    THE NUMERAL IS LABELLED AND THAT IS RULE 0 RATHER THAN DECORATION. A bare 5
    at 340px is a puzzle to somebody who arrives with no context, so the eyebrow
    over it says PROJECTED RANK and the line under the school says what the second
    number is. The card is built to be read by a stranger, which is the only kind
    of reader a billboard has.

    THAT SECOND NUMBER IS THE POWER RATING RATHER THAN THE WIN TOTAL, and on this
    card the reason is sharper than it is on the top five. Two of these posted
    side by side ARE a board: Texas Tech at 5 with 9.6 projected wins beside Ohio
    State at 1 with 8.8 is the same broken-looking pair the owner caught, split
    across two images where no column header can explain it.

    THE ROW'S OWN `note` IS DRAWN WHEN THE DOCUMENT PUBLISHES ONE. It is the one
    football sentence on the card ("Returning production adds 1.4 points to the
    projection"), it is a published field printed verbatim, and a document without
    it simply draws nothing there.
    """
    rows = _projection_rows(document, len(document.get("rows") or []))
    board = {str(row["team"]): row for row in rows}
    if team not in board:
        raise ValueError(
            f"{team!r} is not in this document. A billboard is drawn from the "
            "published board, so a team it does not rank cannot be the subject."
        )
    row = board[team]
    season = int(document["season"])
    rank = str(int(row["rank"]))

    parts = _card_open(CARD_WIDTH, SQUARE_HEIGHT, f"{team}, {season} preseason projection")
    parts.extend(_billboard_banner(document))

    parts.append(_eyebrow(40.0, 340.0, "projected rank", size=22))
    parts.append(
        _num(40.0, BILLBOARD_TEAM_BASELINE, rank, size=BILLBOARD_TEAM_RANK_SIZE,
             fill=PALETTE["ink"], anchor="start")
    )
    # The mark sits beside the numeral, on the numeral's optical middle, at the
    # far end of however wide the digits ran. Sized from the type rather than
    # placed at a fixed x, so a 138 does not print through the school's logo.
    numeral_w = BILLBOARD_TEAM_RANK_SIZE * CAP_ADVANCE * len(rank)
    parts.append(
        _mark(
            40.0 + numeral_w + 56.0 + BILLBOARD_TEAM_MARK_R,
            BILLBOARD_TEAM_BASELINE - BILLBOARD_TEAM_RANK_SIZE * 0.34,
            BILLBOARD_TEAM_MARK_R,
            row,
        )
    )

    name_size = 84.0
    parts.append(
        _text(40.0, 780.0, _clip(team, max(6, int((CARD_WIDTH - 96) / (name_size * 0.52)))),
              size=name_size, fill=PALETTE["ink"], weight="700", family=FONT_DISPLAY)
    )
    parts.append(
        _text(40.0, 840.0, f"{row['projected_power']} projected power rating", size=34,
              fill=PALETTE["ink_dim"], weight="600", family=FONT_DISPLAY)
    )

    y = 888.0
    for line in _wrap(str(row.get("note") or ""), 104, 2):
        parts.append(_text(40.0, y, line, size=24, fill=PALETTE["ink_dim"], family=FONT_DISPLAY))
        y += 30

    # The same hairline the top-five billboard gets from its last row, at the same
    # y, so the two cards are one family: banner, block, rule, teaser, signature.
    parts.append(
        _rule(40.0, BILLBOARD_TEASER_RULE, CARD_WIDTH - 80, stroke=PALETTE["rule"],
              opacity=ROW_RULE_OPACITY)
    )
    parts.extend(_billboard_copy(CARD_WIDTH))
    parts.extend(_billboard_credit(CARD_WIDTH, SQUARE_HEIGHT))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------- the comparison
#
# THE DISAGREEMENT CARD IS A PIPELINE PRODUCT, WHICH IS THE WHOLE POINT OF THIS
# SECTION. Every board this project has ever been compared against was compared
# in somebody's image editor, once, by hand, off a screenshot. That produces an
# artifact with no digest, no input file, no way to re-derive it and no way to
# find out later which numbers were wrong. It is also the exact shape of artifact
# that gets a number wrong: the transcription these cards were first specified
# from had USC at AP 15, and USC is tied at 14 with no 15 in the poll at all.
#
# So: OUR COLUMN COMES OUT OF THE PUBLISHED DOCUMENT and their columns come out of
# a small JSON file that names each board, gives its ranks, and carries the URL it
# was read from. The card cannot say we had a team 3rd unless the projection says
# so, the input file is committed beside whatever is published, and the next
# disagreement card is a new JSON rather than a new afternoon.
#
# FRAMING IS DATA AND NOT DEFAULTS. "Their preseason poll, our preseason
# projection" is a labelling rule this renderer cannot get right on its own, so
# `ours.kind` and each board's `kind` are required fields. A card that called our
# projection a poll would be the one dishonest thing on it.


#: The longest board name a column head has to hold without colliding with its
#: neighbour. "COACHES" is seven characters and it is the one that broke the first
#: attempt: a column sized to hold `T14` is not a column sized to hold the word
#: over it, and the heads ran into each other.
#: What one tracked BOLD CAPITAL of the board face actually advances, as a
#: fraction of the type size. Measured off the rendered heads rather than assumed:
#: `CAP_ADVANCE` describes mixed-case text at normal weight and is far too narrow
#: for `_eyebrow`, which sets caps at weight 700 with 0.12 of tracking on top.
#: Using the wrong one is what printed APCOACHES on the first two renders.
HEAD_ADVANCE = 1.0

#: The column head is this fraction of the numbers under it. Smaller, because the
#: numbers are the message and the head is the reference.
HEAD_RATIO = 0.62

#: Clear space between the last board's numbers and the gap lane. Without it the
#: word COACHES ends exactly where THE GAP begins, which is how the first tall
#: render read as one word.
GAP_GUTTER = 20.0


def _lane(gap_lane: float) -> float:
    """How much of the row's right edge the gap bar and its clear space take."""
    return gap_lane + GAP_GUTTER if gap_lane else 0.0


def _board_head_size(value_size: float) -> float:
    return value_size * HEAD_RATIO


def _board_column_w(value_size: float, boards: list[dict[str, Any]]) -> float:
    """How wide one external board's column is: the wider of its numbers and its name.

    Sized from THE ACTUAL NAMES rather than a fixed character budget, so a spec
    naming a board `Coaches` and a spec naming one `BCS` do not both pay for the
    longer word.
    """
    longest = max((len(str(b.get("name") or "")) for b in boards), default=2)
    return max(
        value_size * 3.1,
        longest * _board_head_size(value_size) * HEAD_ADVANCE + value_size * 0.6,
    )


def _comparison_ranks(board: dict[str, Any]) -> dict[str, int]:
    return {str(team): int(rank) for team, rank in (board.get("ranks") or {}).items()}


def _comparison_display(ranks: dict[str, int], team: str) -> str:
    """Their rank as it should be PRINTED, ties included, or an em-less dash.

    A TIE IS PRINTED AS A TIE. The 2026 AP preseason poll ties BYU and USC at 14
    on 839 points each and then goes to 16, so a card that renders 14/15 has
    invented a ranking the AP did not publish. Two teams sharing a number in the
    input is the definition of the tie, so nothing has to be declared: the shared
    rank is detected here and printed as `T14` on both rows, which is AP's own
    presentation.
    """
    rank = ranks.get(team)
    if rank is None:
        return "NR"
    tied = sum(1 for value in ranks.values() if value == rank) > 1
    return f"T{rank}" if tied else str(rank)


def _gap(ours: int, theirs: int | None, *, unranked_at: int) -> int:
    """How far apart the two boards are, with an unranked team pinned to a floor.

    `unranked_at` is where a team a board did not rank is treated as sitting. It
    is one past the ballot rather than infinity, because a 25-team ballot cannot
    say how much it dislikes a team, only that it is outside - and drawing an
    unbounded bar for "outside 25" would make the least informative rows the
    loudest ones on the card.
    """
    return (unranked_at if theirs is None else theirs) - ours


def _gap_colour(gap: int) -> str:
    """Bone inside the agreement band, otherwise the brand's movement pair."""
    if abs(gap) <= AGREEMENT_BAND:
        return PALETTE["ink"]
    return GAP_POS if gap > 0 else GAP_NEG


def _comparison_rows(
    document: dict[str, Any], spec: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The rows this card draws and the boards it draws beside them.

    `mode` decides which rows, and every mode is a SELECTION over the published
    document rather than a computation on it:

      - `board`   our board in our order, sliced by `slice`. GFX-01 and GFX-10.
      - `gaps`    the rows the two sides disagree about most. GFX-10 slide 3.
      - `agree`   the rows every board lands on together. GFX-03.
      - `missing` the teams THEY rank that our top 25 does not, with the rank our
                  full list actually gives them. GFX-11, and it needs a document
                  published with more than 25 rows or it has nothing to say.
    """
    rows = list(document.get("rows") or [])
    by_team = {str(r["team"]): r for r in rows}
    boards = list(spec.get("boards") or [])
    if not boards:
        raise ValueError("a comparison card needs at least one external board")
    mode = str(spec.get("mode") or "board")
    unranked_at = int(spec.get("unranked_at") or 26)

    def worst_gap(row: dict[str, Any]) -> int:
        ours = int(row["rank"])
        return max(
            abs(_gap(ours, _comparison_ranks(b).get(str(row["team"])), unranked_at=unranked_at))
            for b in boards
        )

    if mode == "missing":
        wanted: list[str] = []
        for board in boards:
            for team, _rank in sorted(_comparison_ranks(board).items(), key=lambda kv: kv[1]):
                if team not in wanted and team in by_team and int(by_team[team]["rank"]) > 25:
                    wanted.append(team)
        picked = [by_team[team] for team in wanted]
    elif mode == "gaps":
        picked = sorted(rows, key=lambda r: (-worst_gap(r), int(r["rank"])))
    elif mode == "agree":
        # EVERY BOARD HAS TO HAVE ACTUALLY RANKED THE TEAM. Without this, a team
        # we have 24th that nobody else ranked scores a 2-place "gap" against the
        # unranked floor and lands on the agreement card, which would put a
        # sentence on a published graphic - "the AP agrees" - about a team the AP
        # left off its ballot. The floor is a drawing device; it is not a rank
        # somebody issued, and only modes that are ABOUT the gap may use it.
        picked = [
            r
            for r in rows
            if worst_gap(r) <= AGREEMENT_BAND
            and all(str(r["team"]) in _comparison_ranks(b) for b in boards)
        ]
    elif mode == "board":
        picked = rows
    else:
        raise ValueError(f"unknown comparison mode {mode!r}")

    if mode in ("board", "agree"):
        lo, hi = spec.get("slice") or [1, 25]
        picked = [r for r in picked if int(lo) <= int(r["rank"]) <= int(hi)]
    return picked[: int(spec.get("limit") or 25)], boards


def _comparison_row(
    row: dict[str, Any],
    boards: list[dict[str, Any]],
    x: float,
    y: float,
    width: float,
    *,
    height: float,
    rank_size: float,
    name_size: float,
    value_size: float,
    use_abbreviation: bool,
    unranked_at: int,
    gap_lane: float = 0.0,
) -> list[str]:
    """One team across every board. Their numbers are printed, never derived.

    THE COLOUR IS THE MESSAGE AND THE NUMBER IS THE RECEIPT. A reader scanning
    this card should see which way each disagreement runs before reading a single
    figure, which is what the storylines doc asks for in as many words; the amber
    and violet do that and the bone says "these two agree". The numeral beside the
    colour is what makes the claim checkable.
    """
    mid = y + height / 2
    ours = int(row["rank"])
    parts: list[str] = [_slab(x, y + 3, 3, height - 6, stripe_colour(row.get("mark_bg")))]

    rank_lane = rank_size * 1.32
    rank_x = x + 14
    parts.append(
        _num(rank_x + rank_lane, mid + rank_size * 0.34, str(ours), size=rank_size,
             fill=PALETTE["ink"])
    )

    mark_r = height * 0.34
    mark_cx = rank_x + rank_lane + 13 + mark_r
    parts.append(_mark(mark_cx, mid, mark_r, row))

    # Every board column is the same width so the numbers form columns down the
    # card, which is the only way "find your team, then look right" works.
    board_w = _board_column_w(value_size, boards)
    columns_w = board_w * len(boards) + _lane(gap_lane)
    name_x = mark_cx + mark_r + 12
    name_budget = max(3, int((width - (name_x - x) - columns_w - 8) / (name_size * 0.52)))
    name = str(row.get("abbreviation") if use_abbreviation else row.get("team") or "")
    parts.append(
        _text(name_x, mid + name_size * 0.34, _clip(name, name_budget), size=name_size,
              fill=PALETTE["ink"], weight="600", family=FONT_DISPLAY)
    )

    worst = 0
    for index, board in enumerate(boards):
        ranks = _comparison_ranks(board)
        theirs = ranks.get(str(row["team"]))
        gap = _gap(ours, theirs, unranked_at=unranked_at)
        worst = gap if abs(gap) > abs(worst) else worst
        right = x + width - _lane(gap_lane) - board_w * (len(boards) - 1 - index)
        parts.append(
            _num(right, mid + value_size * 0.34, _comparison_display(ranks, str(row["team"])),
                 size=value_size, fill=_gap_colour(gap), weight="700")
        )

    if gap_lane:
        # The bar is the "without reading a word" half of the brief. Length is the
        # gap, capped at the lane, and its direction is which side of the row it
        # grows from, so a reader sees the shape of the disagreement before any
        # number resolves.
        span = min(abs(worst), unranked_at - 1) / float(unranked_at - 1)
        bar = max(2.0, span * (gap_lane - 14))
        left = x + width - gap_lane + 8
        parts.append(_slab(left, mid - 4, gap_lane - 14, 8, PALETTE["rail_track"]))
        if worst:
            parts.append(_slab(left, mid - 4, bar, 8, _gap_colour(worst)))
    return parts


def _comparison_legend(
    x: float,
    y: float,
    width: float,
    boards: list[dict[str, Any]],
    *,
    horizontal: bool = False,
    size: float = 13.0,
) -> list[str]:
    """Three swatches and the sentences that say what they mean.

    A DIVERGING PAIR WITH NO KEY IS DECORATION. The card uses the brand's movement
    colours to carry direction, so it owes the reader the sentence that decodes
    them, on the card, in words rather than in a caption somebody has to have read
    first. It is never dropped for space: a card that runs out of room for its own
    key has run out of room for its argument.
    """
    names = " and ".join(str(b.get("name") or "?") for b in boards)
    entries = [
        (GAP_POS, f"we rank them higher than {names}"),
        (GAP_NEG, "we rank them lower"),
        (PALETTE["ink"], f"within {AGREEMENT_BAND}: the boards agree"),
    ]
    parts: list[str] = []
    if horizontal:
        cell = width / len(entries)
        for index, (colour, text) in enumerate(entries):
            cx = x + cell * index
            parts.append(_slab(cx, y - size * 0.7, size * 1.3, size * 0.62, colour))
            parts.append(
                _text(cx + size * 1.9, y, _clip(text, int((cell - size * 2.4) / (size * 0.5))),
                      size=size, fill=PALETTE["ink_dim"], family=FONT_DISPLAY)
            )
        return parts
    for index, (colour, text) in enumerate(entries):
        row_y = y + index * (size * 1.7)
        parts.append(_slab(x, row_y - size * 0.7, size * 1.3, size * 0.62, colour))
        parts.append(
            _text(x + size * 1.9, row_y, _clip(text, int((width - size * 2) / (size * 0.5))),
                  size=size, fill=PALETTE["ink_dim"], family=FONT_DISPLAY)
        )
    return parts


def _comparison_headers(
    boards: list[dict[str, Any]],
    spec: dict[str, Any],
    x: float,
    y: float,
    width: float,
    *,
    value_size: float,
    gap_lane: float = 0.0,
) -> list[str]:
    """The column heads: every board's name over its numbers, and what kind it is.

    THE KIND IS ON THE CARD BECAUSE THE LABELLING RULE SAYS SO, AND IT IS ON OURS
    FIRST. Ours is a projection and theirs are polls. A comparison that named only
    the other two boards, or that quietly called all three the same thing, would
    be claiming a like-for-like the season has not happened yet to support. So the
    left-hand head says whose column the ranks belong to and what kind of claim it
    is, in the same type as theirs.
    """
    board_w = _board_column_w(value_size, boards)
    head = _board_head_size(value_size)
    ours = spec.get("ours") or {}
    parts: list[str] = [
        _eyebrow(x + 14, y, str(ours.get("name") or "The Poll"), size=head, fill=PALETTE["ink"]),
        _eyebrow(x + 14, y + head + 2, str(ours.get("kind") or ""), size=head * 0.78),
    ]
    for index, board in enumerate(boards):
        right = x + width - _lane(gap_lane) - board_w * (len(boards) - 1 - index)
        parts.append(
            _eyebrow(right, y, str(board.get("name") or "?"), size=head, fill=PALETTE["ink"],
                     anchor="end")
        )
        parts.append(
            _eyebrow(right, y + head + 2, str(board.get("kind") or ""), size=head * 0.78,
                     anchor="end")
        )
    return parts


def _comparison_footer_lines(document: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    """Our provenance, then theirs. Both, on the card, every time.

    THE SECOND LINE IS THE PART THAT MAKES THIS PUBLISHABLE. A card that prints
    somebody else's numbers owes the reader where they came from and when they
    were read, because a poll moves every week and a screenshot does not say which
    week it is. `source` is required on every board for that reason.
    """
    lines = list(spec.get("footer_lines") or [])
    if lines:
        return lines
    lines = [
        f"recipe {document.get('projection_version')} · the poll grades this from "
        f"week {document.get('grading_start_week')}"
    ]
    parts = [
        f"{board.get('name')} {board.get('released') or ''}".strip()
        for board in (spec.get("boards") or [])
    ]
    source = str((spec.get("boards") or [{}])[0].get("source") or "")
    host = source.split("//")[-1].split("/")[0]
    lines.append(f"their ranks as published: {' · '.join(parts)}" + (f" · {host}" if host else ""))
    return lines


def _comparison_column(
    document: dict[str, Any],
    spec: dict[str, Any],
    boards: list[dict[str, Any]],
    height: float,
) -> list[str]:
    """The masthead column for a comparison card: mark, dateline, label, legend.

    THE MARK IS MONOCHROME HERE, AND THAT IS THE FLAGGED CHECK BEING ANSWERED.
    The brand book keeps the amber-violet movement pair and warns that no figure
    may place cyan beside it "in a way that reads as three competing categories".
    This card is that figure. So the `.ai` goes bone and the footer divider goes
    bone, and the only colours on the card are the two that mean direction.
    """
    return _masthead_column(
        COLUMN_W,
        height,
        eyebrow=str(spec.get("eyebrow") or f"{int(document['season'])} preseason"),
        label=str(spec.get("label") or "") or None,
        thesis=str(spec.get("headline") or ""),
        thesis_size=21,
        thesis_lines=6,
        accent=None,
        extra=_comparison_legend(COLUMN_X, height - FOOTER_HEIGHT - 96, COLUMN_W - COLUMN_X * 2,
                                 boards),
    )


def comparison_svg(document: dict[str, Any], spec: dict[str, Any]) -> str:
    """The comparison on the 1200x628 X canvas: two columns of 13 and 12.

    Abbreviations and no gap bar, because five fields in a 360px column is what
    fits and the colour already carries the direction. The tall canvas is where
    the full names and the bars live.
    """
    rows, boards = _comparison_rows(document, spec)
    unranked_at = int(spec.get("unranked_at") or 26)
    season = int(document["season"])

    parts = _card_open(CARD_WIDTH, CARD_HEIGHT, _comparison_label(spec, season))
    parts.extend(_comparison_column(document, spec, boards, CARD_HEIGHT))

    area_x, area_w = COLUMN_W + 24, CARD_WIDTH - COLUMN_W - 48
    gutter = 16.0
    col_w = (area_w - gutter) / 2
    split = (13, 12)
    top = 168.0
    start = 0
    for index, count in enumerate(split):
        chunk = rows[start : start + count]
        x = area_x + index * (col_w + gutter)
        parts.extend(_comparison_headers(boards, spec, x, top - 32, col_w, value_size=18))
        parts.append(_rule(x, top - 8, col_w, stroke=PALETTE["rule"]))
        for i, row in enumerate(chunk):
            y = top + i * 26.0
            parts.extend(
                _comparison_row(
                    row, boards, x, y, col_w, height=26.0, rank_size=21, name_size=19,
                    value_size=18, use_abbreviation=True, unranked_at=unranked_at,
                )
            )
            parts.append(
                _rule(x, y + 26.0, col_w, stroke=PALETTE["rule"], opacity=ROW_RULE_OPACITY)
            )
        start += count

    parts.extend(
        _footer(
            _comparison_footer_lines(document, spec), CARD_WIDTH, CARD_HEIGHT,
            accent_divider=False,
        )
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _comparison_label(spec: dict[str, Any], season: int) -> str:
    names = ", ".join(str(b.get("name") or "?") for b in (spec.get("boards") or []))
    return f"The Poll {season} projection compared with {names}"


def _comparison_wide(
    document: dict[str, Any],
    spec: dict[str, Any],
    *,
    height: float,
    row_h: float,
    top: float,
    banner_h: float,
) -> str:
    """The comparison on a full-width canvas: one column, full names, gap bars.

    Shared by the 4:5 Instagram card and the 1:1 square, which differ in nothing
    but how many pixels they have. Portrait is not a squeezed landscape card and a
    square is not a cropped portrait one; each gets its own row height and each
    draws the same rows from the same document.
    """
    rows, boards = _comparison_rows(document, spec)
    unranked_at = int(spec.get("unranked_at") or 26)
    season = int(document["season"])

    # REFUSED RATHER THAN DRAWN OFF THE BOTTOM. A square canvas holds a slice, not
    # a whole board, and the failure mode this catches is silent: 25 rows on a
    # 1200-tall card renders happily and puts the last eight below the edge, which
    # nothing but a human looking at the PNG would notice.
    available = height - FOOTER_HEIGHT - 16 - top
    room = int(available // row_h)
    if len(rows) > room:
        raise ValueError(
            f"{len(rows)} rows do not fit this canvas; it holds {room}. Narrow the "
            "spec's `slice` or `limit`, or render the taller variant."
        )
    # A SHORT LIST GETS TALLER ROWS RATHER THAN A HALF-EMPTY CARD. The "not on the
    # board" card is four teams; drawn on the 25-row grid it is four lines at the
    # top of a poster and 500px of nothing, which reads as a card that failed to
    # load. Growing the rows to fill, capped at three times the nominal so a
    # two-row card does not become two billboards, makes the same layout serve
    # both without a second set of variants.
    if rows:
        row_h = min(available / len(rows), row_h * 3.0, 130.0)

    parts = _card_open(CARD_WIDTH, height, _comparison_label(spec, season))
    parts.extend(
        _top_banner(
            CARD_WIDTH,
            banner_h,
            eyebrow=str(spec.get("eyebrow") or f"{season} preseason"),
            label=str(spec.get("label") or "") or None,
            thesis=str(spec.get("headline") or ""),
            thesis_size=26,
            accent=None,
        )
    )

    x, width = 40.0, CARD_WIDTH - 80
    gap_lane = 150.0
    parts.extend(_comparison_legend(x, banner_h + 30, width, boards, horizontal=True, size=15))
    parts.extend(
        _comparison_headers(boards, spec, x, top - 44, width, value_size=25, gap_lane=gap_lane)
    )
    parts.append(
        _eyebrow(x + width - gap_lane + 8, top - 44, "the gap",
                 size=_board_head_size(25), fill=PALETTE["ink"])
    )
    parts.append(_rule(x, top - 8, width, stroke=PALETTE["rule"]))
    for i, row in enumerate(rows):
        y = top + i * row_h
        parts.extend(
            _comparison_row(
                row, boards, x, y, width, height=row_h, rank_size=30, name_size=27,
                value_size=25, use_abbreviation=False, unranked_at=unranked_at,
                gap_lane=gap_lane,
            )
        )
        parts.append(_rule(x, y + row_h, width, stroke=PALETTE["rule"], opacity=ROW_RULE_OPACITY))

    parts.extend(
        _footer(_comparison_footer_lines(document, spec), CARD_WIDTH, height,
                accent_divider=False)
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def comparison_tall_svg(document: dict[str, Any], spec: dict[str, Any]) -> str:
    """1200x1500, the tallest ratio Instagram serves in feed. 25 rows at 42px."""
    return _comparison_wide(document, spec, height=TALL_HEIGHT, row_h=40.0, top=418.0,
                            banner_h=318.0)


def comparison_square_svg(document: dict[str, Any], spec: dict[str, Any]) -> str:
    """1200x1200. The carousel slide, which is why it exists.

    A square holds thirteen rows comfortably and twenty-five not at all, so this
    canvas is built for a SLICE of the board and the input file says which - top
    ten, eleven to twenty-five, or the widest gaps. Three input files and three
    calls make the three-slide carousel, with no option flag anywhere and three
    separate digests, which is what a published artifact needs.
    """
    return _comparison_wide(document, spec, height=SQUARE_HEIGHT, row_h=46.0, top=418.0,
                            banner_h=318.0)


def disagreement_svg(document: dict[str, Any], spec: dict[str, Any]) -> str:
    """ONE team, at poster scale, with every board's number on it. The template.

    GFX-02 in the launch queue, and it is a template rather than a card: `focus`
    names the team and `sentence` is the one football line that explains the
    disagreement. Texas, Vanderbilt, Utah, Texas Tech and the rest are the same
    JSON with two fields changed.

    THE SENTENCE IS AN INPUT AND NOT A COMPUTATION, on purpose. A model can say
    that it has Texas 13th and the AP has them 5th. It cannot say why in football
    words, and a renderer that generated that line would be putting a claim on a
    published card that nothing in the pipeline stands behind.
    """
    focus = str(spec.get("focus") or "")
    rows = {str(r["team"]): r for r in (document.get("rows") or [])}
    if focus not in rows:
        raise ValueError(
            f"{focus!r} is not in this document. A disagreement card is drawn from "
            "the published board, so a team it does not rank cannot be the subject."
        )
    row = rows[focus]
    boards = list(spec.get("boards") or [])
    unranked_at = int(spec.get("unranked_at") or 26)
    season = int(document["season"])
    ours = int(row["rank"])

    parts = _card_open(CARD_WIDTH, CARD_HEIGHT, f"{focus}, {season}: where the boards disagree")
    parts.extend(_masthead(COLUMN_X, 44, 246.0, accent=None))
    parts.append(
        _eyebrow(CARD_WIDTH - 40, 60, str(spec.get("eyebrow") or f"{season} preseason"),
                 anchor="end")
    )
    parts.append(_rule(COLUMN_X, 132, CARD_WIDTH - COLUMN_X * 2, stroke=PALETTE["rule"]))

    # The team, at the size the card is for.
    parts.append(_mark(COLUMN_X + 46, 200, 46, row))
    name_budget = max(6, int((CARD_WIDTH - COLUMN_X - 120) / 30))
    parts.append(
        _text(COLUMN_X + 112, 216, _clip(focus, name_budget), size=58, fill=PALETTE["ink"],
              weight="700", family=FONT_DISPLAY)
    )

    # Three cells across: ours, then theirs, each with its kind under it.
    cells: list[tuple[str, str, str, str]] = [
        (str(ours), str((spec.get("ours") or {}).get("name") or "The Poll"),
         str((spec.get("ours") or {}).get("kind") or ""), PALETTE["ink"])
    ]
    for board in boards:
        ranks = _comparison_ranks(board)
        gap = _gap(ours, ranks.get(focus), unranked_at=unranked_at)
        cells.append(
            (
                _comparison_display(ranks, focus),
                str(board.get("name") or "?"),
                str(board.get("kind") or ""),
                _gap_colour(gap),
            )
        )

    cell_w = (CARD_WIDTH - COLUMN_X * 2) / len(cells)
    for index, (value, name, kind, colour) in enumerate(cells):
        cx = COLUMN_X + cell_w * index
        parts.append(_eyebrow(cx, 288, name, size=15, fill=PALETTE["ink"]))
        parts.append(_eyebrow(cx, 306, kind, size=11))
        # Left-anchored under its own label rather than right-anchored in the
        # cell: these are three separate claims side by side, not a column of
        # figures to be compared digit by digit, and a numeral that has drifted
        # 200px from the name over it belongs to nothing.
        parts.append(_num(cx, 392, value, size=92, fill=colour, anchor="start"))
        if index:
            parts.append(
                f'<line x1="{_n(cx - 12)}" y1="270" x2="{_n(cx - 12)}" y2="400" '
                f'stroke="{PALETTE["rule"]}" stroke-width="1" '
                f'stroke-opacity="{_n(ROW_RULE_OPACITY)}"/>'
            )

    parts.append(_rule(COLUMN_X, 414, CARD_WIDTH - COLUMN_X * 2, stroke=PALETTE["rule"]))
    # THE SENTENCE ENDS INSIDE THE MOBILE SAFE BAND. Three lines from 444 at
    # 26px leading finish at 496, six pixels above the crop X takes on a phone.
    # A one-football-sentence card whose last line is cropped off is a card
    # with no sentence on it.
    y = 444.0
    for line in _wrap(str(spec.get("sentence") or ""), 92, 3):
        parts.append(_text(COLUMN_X, y, line, size=22, fill=PALETTE["ink"], family=FONT_DISPLAY))
        y += 26

    parts.extend(
        _footer(_comparison_footer_lines(document, spec), CARD_WIDTH, CARD_HEIGHT,
                accent_divider=False)
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_png(svg: str) -> bytes:
    """Rasterise, then strip. No network, no headless browser, no hidden metadata.

    resvg is a static Rust rasteriser exposed as a wheel, which is what makes the
    Sunday job hermetic: report 05 §6.1 rejected a Chromium download for one image
    a week, and it was right.

    EVERY PNG THIS FUNCTION RETURNS HAS BEEN THROUGH `strip_png_metadata`, so the
    guarantee is a property of the one place cards are rasterised rather than a
    step somebody has to remember before posting.
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
        return strip_png_metadata(
            bytes(
                resvg_py.svg_to_bytes(
                    svg_string=svg,
                    skip_system_fonts=True,
                    font_dirs=[str(FONT_DIR)],
                )
            )
        )
    # No vendored families yet: fall back to the host, and be loud about what
    # that costs rather than producing a card that silently is not reproducible.
    return strip_png_metadata(bytes(resvg_py.svg_to_bytes(svg_string=svg)))


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


#: variant -> the function that draws it, the canvas it draws on, and HOW MANY
#: ROWS IT DRAWS. One table so `export`, the CLI's help text and the CI guard
#: cannot disagree about what a variant is.
#:
#: The row count is on this table rather than in a second dictionary because it is
#: what the export path warms the logo cache from: fetching bytes for teams a card
#: does not draw would pull marks onto our disk for no reason, and warming fewer
#: than it draws would leave a row with the generated disc while its neighbours
#: carry marks. `connectivity` draws none, because its team nodes are 4px wide and
#: a school mark at 4px is a smudge.
BUILDERS: dict[str, Any] = {
    "connectivity": (lambda b: connectivity_svg(b), CARD_WIDTH, CARD_HEIGHT, 0),
    "top5": (lambda b: top5_svg(b), CARD_WIDTH, CARD_HEIGHT, 5),
    "top10": (lambda b: top10_svg(b), CARD_WIDTH, CARD_HEIGHT, 10),
    "top25_x": (lambda b: top25_x_svg(b), CARD_WIDTH, CARD_HEIGHT, 25),
    "top25_instagram": (lambda b: top25_instagram_svg(b), CARD_WIDTH, TALL_HEIGHT, 25),
    # The projection variants take a DOCUMENT rather than a bundle. Same table
    # anyway, so the CLI's help, the CI guard and `export` still cannot disagree
    # about what a variant is; `export` reads PROJECTION_VARIANTS to know which
    # argument to hand the builder.
    "projection_top5": (lambda d: projection_top5_svg(d), CARD_WIDTH, CARD_HEIGHT, 5),
    "projection_top10": (lambda d: projection_top10_svg(d), CARD_WIDTH, CARD_HEIGHT, 10),
    # THE TWO TILE CARDS ARE THE ONES THAT LEFT 1.91:1, and each went to the
    # shortest canvas that holds its marks at a size somebody can recognise
    # across a room: 4:5 for 25 tiles, 2:3 for 138. The top ten is still on the
    # wide canvas and is what a link preview picks up.
    "projection_top25": (lambda d: projection_top25_svg(d), CARD_WIDTH, TALL_HEIGHT, 25),
    # 138, AND THE COST IS ACCEPTED RATHER THAN AVOIDED. The row count is what
    # the export path warms the cache from, and a grid warmed to 25 draws the top
    # of the board with real marks and the rest with generated discs - which reads
    # as a card that failed to load rather than as a design. The owner's rule is
    # real school logos everywhere, so this variant pays for a hundred-odd extra
    # fetches, once, into a cache every later card reuses.
    "projection_grid": (lambda d: grid_svg(d), CARD_WIDTH, POSTER_HEIGHT, 138),
    # The billboards read the same document and draw on the square canvas. The
    # single-team one declares ONE row, which is the truth: `export_billboard`
    # warms the cache for the row it was asked for rather than for the top of the
    # board, because the subject of a billboard is often not in the top five.
    "billboard_top5": (lambda d: billboard_top5_svg(d), CARD_WIDTH, SQUARE_HEIGHT, 5),
    "billboard_team": (billboard_team_svg, CARD_WIDTH, SQUARE_HEIGHT, 1),
    # The comparison variants take TWO documents. Same table anyway, and their
    # row count is 25 because that is the most rows any of them can draw and the
    # count is what the export path warms the logo cache from - warming fewer than
    # a card draws leaves a row with the generated disc beside neighbours carrying
    # real marks, which only shows up in a published PNG.
    "comparison": (comparison_svg, CARD_WIDTH, CARD_HEIGHT, 25),
    "comparison_tall": (comparison_tall_svg, CARD_WIDTH, TALL_HEIGHT, 25),
    "comparison_square": (comparison_square_svg, CARD_WIDTH, SQUARE_HEIGHT, 25),
    "disagreement": (disagreement_svg, CARD_WIDTH, CARD_HEIGHT, 25),
}


def _write(dest: Path, stem: str, svg: str, *, png: bool) -> list[Path]:
    """Both files, and the SVG always. Returns the paths, sorted.

    The SVG because it is the diffable, reviewable, vector artifact and the thing
    a test can assert about; the PNG because that is what travels.
    """
    dest.mkdir(parents=True, exist_ok=True)
    written = [dest / f"{stem}.svg"]
    written[0].write_text(svg, encoding="utf-8")
    if png:
        target = dest / f"{stem}.png"
        target.write_bytes(render_png(svg))
        written.append(target)
    return sorted(written)


def export(
    out: Path,
    dest: Path,
    *,
    variant: str = "connectivity",
    archive: Path | None = None,
    backtest: Path | None = None,
    png: bool = True,
    fetch_logos: bool = True,
) -> list[Path]:
    """Write `<dest>/<season>-w<NN>-<variant>.{svg,png}`. Returns the paths, sorted.

    `out` is the directory `cfbpoll rank` produced. A projection variant has no
    run directory and no week, so it goes through `export_projection` instead and
    is refused here rather than being handed a bundle it cannot read.

    THE ONE NETWORK CALL IN THE WHOLE CARD PIPELINE IS HERE, in `logos.warm`,
    before a single glyph is placed. It fills the cache for exactly the rows this
    variant draws, skips anything already on disk, and pins what it fetched in
    `data/logo-cache-manifest.json`. `fetch_logos=False` renders from whatever is
    already cached, which is what an offline build wants: every uncached row falls
    back to the generated mark rather than failing.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown card variant {variant!r}; expected one of {VARIANTS}")
    if variant in PROJECTION_VARIANTS:
        raise ValueError(
            f"{variant!r} draws the projection document, which has no run directory "
            "and no week. Use `export_projection`, or `publish cards --projection "
            "<path>` from the CLI."
        )
    if variant in BILLBOARD_VARIANTS:
        raise ValueError(
            f"{variant!r} draws the projection document, which has no run directory "
            "and no week. Use `export_billboard`, or `publish cards --projection "
            "<path>` from the CLI."
        )
    if variant in COMPARISON_VARIANTS:
        raise ValueError(
            f"{variant!r} draws a published board beside one or more external boards "
            "and needs both documents. Use `export_comparison`, or `publish cards "
            "--projection <path> --compare <path>` from the CLI."
        )
    bundle = build(out, archive=archive, backtest=backtest)
    drawn = int(BUILDERS[variant][3])
    if drawn:
        logos.warm(
            list(bundle.views["week"].get("poll") or [])[:drawn],
            background=PALETTE["bg"],
            fetch=fetch_logos,
        )
    svg = BUILDERS[variant][0](bundle)
    return _write(dest, f"{bundle.season}-w{bundle.week:02d}-{variant}", svg, png=png)


def export_projection(
    document: Path,
    dest: Path,
    *,
    variant: str = "projection_top10",
    png: bool = True,
    fetch_logos: bool = True,
) -> list[Path]:
    """Write `<dest>/<season>-projection-<name>.{svg,png}`. Returns the paths, sorted.

    `document` is `cfb-poll-data/<season>/projection.json`, the published fixture,
    and it is the ONLY input. Not the model, not a run directory, not a refit: the
    card is drawn from the artifact a reader can download, so the two cannot
    disagree, and the projection is frozen at publication anyway.

    NO WEEK IN THE FILENAME. A preseason projection is a single claim about a
    whole season, so `2026-projection-top10` says exactly what it is, where
    `2026-w00-projection_top10` would have invented a week that does not exist.
    """
    if variant not in PROJECTION_VARIANTS:
        raise ValueError(
            f"unknown projection card variant {variant!r}; expected one of "
            f"{PROJECTION_VARIANTS}"
        )
    payload = json.loads(Path(document).read_text(encoding="utf-8"))
    drawn = int(BUILDERS[variant][3])
    if drawn:
        logos.warm(
            list(payload.get("rows") or [])[:drawn],
            background=PALETTE["bg"],
            fetch=fetch_logos,
        )
    svg = BUILDERS[variant][0](payload)
    stem = f"{int(payload['season'])}-projection-{variant.removeprefix('projection_')}"
    return _write(dest, stem, svg, png=png)


def _team_slug(team: str) -> str:
    """`Ohio State` -> `ohio-state`. The filename half of a single-team card.

    Lower case, runs of anything that is not a letter or a digit collapsed to one
    dash, no leading or trailing dash. `Texas A&M` becomes `texas-a-m`, which is
    ugly and is a filename rather than a label, so it is allowed to be.
    """
    out: list[str] = []
    for character in str(team).lower():
        if character.isalnum():
            out.append(character)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-") or "team"


def export_billboard(
    document: Path,
    dest: Path,
    *,
    variant: str = "billboard_top5",
    team: str | None = None,
    png: bool = True,
    fetch_logos: bool = True,
) -> list[Path]:
    """Write `<dest>/<season>-billboard-<name>.{svg,png}`. Returns the paths, sorted.

    Same single input as `export_projection` and the same reason: the card is
    drawn from the artifact a reader can download, so the two cannot disagree.

    `team` is required by `billboard_team` and refused by the other one, rather
    than being quietly ignored, because a run that names a team and gets the top
    five back is a run somebody publishes without noticing.

    THE CACHE IS WARMED FOR THE ROW THIS CARD ACTUALLY DRAWS. The top-five
    billboard warms the top five; the single-team billboard warms its subject,
    which is frequently nowhere near the top of the board. Warming from the
    builder table's row count instead would have left every billboard of a team
    outside the top five carrying the generated disc while its neighbours on other
    cards carried real marks.
    """
    if variant not in BILLBOARD_VARIANTS:
        raise ValueError(
            f"unknown billboard card variant {variant!r}; expected one of "
            f"{BILLBOARD_VARIANTS}"
        )
    if variant == "billboard_team" and not team:
        raise ValueError("billboard_team draws one school and needs `team` naming it")
    if variant != "billboard_team" and team:
        raise ValueError(f"{variant!r} draws the top of the board and takes no `team`")

    payload = json.loads(Path(document).read_text(encoding="utf-8"))
    rows = list(payload.get("rows") or [])
    if team:
        drawn = [row for row in rows if str(row.get("team")) == team]
        stem = f"{int(payload['season'])}-billboard-{_team_slug(team)}"
    else:
        drawn = rows[: int(BUILDERS[variant][3])]
        stem = f"{int(payload['season'])}-billboard-{variant.removeprefix('billboard_')}"
    # Warm BEFORE anything is drawn, exactly as the other two export paths do:
    # the builders read the cache and cannot reach the network themselves.
    logos.warm(drawn, background=PALETTE["bg"], fetch=fetch_logos)
    svg = (
        billboard_team_svg(payload, team) if team else BUILDERS[variant][0](payload)
    )
    return _write(dest, stem, svg, png=png)


#: Every field a comparison spec must carry, and why each one is not optional.
#: `boards[].source` is the load-bearing one: a card printing somebody else's
#: numbers has to say where they were read and when, because a poll moves every
#: week and the image it was transcribed from does not say which week it is.
COMPARISON_REQUIRED: tuple[str, ...] = ("slug", "boards")
COMPARISON_BOARD_REQUIRED: tuple[str, ...] = ("name", "kind", "ranks", "source")


def load_comparison(path: Path) -> dict[str, Any]:
    """Read and CHECK a comparison spec. A missing field is refused, not defaulted.

    The whole argument for this file existing is that the numbers on a
    disagreement card become auditable. A spec with no `source` on a board is a
    screenshot with extra steps, so it is rejected here rather than rendered.
    """
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [field for field in COMPARISON_REQUIRED if not spec.get(field)]
    if missing:
        raise ValueError(f"the comparison spec is missing {missing}")
    for index, board in enumerate(spec.get("boards") or []):
        absent = [field for field in COMPARISON_BOARD_REQUIRED if not board.get(field)]
        if absent:
            raise ValueError(f"board {index} ({board.get('name')!r}) is missing {absent}")
    return spec


def export_comparison(
    document: Path,
    spec_path: Path,
    dest: Path,
    *,
    variant: str = "comparison",
    png: bool = True,
    fetch_logos: bool = True,
) -> list[Path]:
    """Write `<dest>/<season>-<slug>-<variant>.{svg,png}`. Returns the paths, sorted.

    TWO INPUTS AND BOTH ARE FILES ON DISK. `document` is the published board, so
    our column cannot disagree with what a reader downloads; `spec_path` is the
    external boards, so their columns cannot disagree with what was verified. A
    card whose inputs are both files is a card somebody can re-render in a year
    and get the same bytes.
    """
    if variant not in COMPARISON_VARIANTS:
        raise ValueError(
            f"unknown comparison card variant {variant!r}; expected one of "
            f"{COMPARISON_VARIANTS}"
        )
    payload = json.loads(Path(document).read_text(encoding="utf-8"))
    spec = load_comparison(spec_path)
    rows, _boards = _comparison_rows(payload, spec)
    if variant == "disagreement":
        rows = [r for r in (payload.get("rows") or []) if str(r["team"]) == spec.get("focus")]
    logos.warm(rows, background=PALETTE["bg"], fetch=fetch_logos)
    svg = BUILDERS[variant][0](payload, spec)
    stem = f"{int(payload['season'])}-{spec['slug']}-{variant}"
    return _write(dest, stem, svg, png=png)


def sha256_of(path: Path) -> str:
    """The published card's digest. Report 05 §6.1(2): a card is a frozen claim."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
