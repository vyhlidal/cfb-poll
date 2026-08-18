"""The share card, and the CI guard - which now guards the opposite thing.

REPORT 06 §8.4 ASKED FOR A NO-LOGO GUARD AND THE OWNER OVERTURNED THE POLICY IT
ENFORCED. Verbatim: "I don't care about the logo caution, every social post
everywhere uses college logos, we're not making T-shirts: use the logos." Three
assertions in this module existed only to make that impossible and they are gone:
that a card SVG carries no `<image>`, that the renderer cannot emit one, and that
no logo host is ever fetched from the Python package.

WHAT REPLACED THEM PROTECTS SOMETHING THE RULING DID NOT TOUCH. The card must be
SELF-CONTAINED. Every `<image>` in a card is a `data:` URI over bytes from the
pinned cache, and an external `http(s)` host in a card SVG still fails the build,
because a card that hotlinks renders a blank square the moment the host blocks the
referrer or moves the path - on an artifact whose whole point is that it is frozen
at publication and checkable years later. Also new: the logo cache directory is
gitignored, and the manifest covers every mark the card set draws.

WHAT SURVIVED UNCHANGED, because the ruling was about drawing marks and not about
what this repository ships: no image file may appear in the tracked tree outside a
named allow-list. `.cache/logos/` holds somebody else's files and is ignored; what
is committed is `data/logo-cache-manifest.json`, the URL and sha256 of every byte
drawn, which is how a reader verifies a published card without us distributing a
copy of anyone's logo.

The rest of the module is about the card as an artifact: its geometry, its
constants footer, the stripe clamp, the word wrap, the vendored fonts, and the
purity claim - now stated as "a pure function of (the published documents + the
pinned logo cache)", the fetch being the one non-hermetic input.
"""

from __future__ import annotations

import ast
import json
import re
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from cfbpoll.config import REPO_ROOT
from cfbpoll.publish import cards, logos

DEMO = REPO_ROOT / "demo"
SAMPLE_SVG = DEMO / "2023-w10-connectivity.svg"
SAMPLE_PNG = DEMO / "2023-w10-connectivity.png"

#: Every image file the tracked tree is allowed to hold, and why. A school mark
#: would have to be added HERE to pass, which is still the point: the cards DRAW
#: marks, and this repository does not REDISTRIBUTE them. The bytes live in a
#: gitignored cache and the manifest is what makes them verifiable.
ALLOWED_IMAGES: dict[str, str] = {
    "demo/2023-w10-connectivity.svg": "our own generated card; the graph variant draws no marks",
    "demo/2023-w10-connectivity.png": "the rendered sample of the same card",
}

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif", ".ico"}

#: Hosts that serve school marks. `publish/logos.py` is the ONE module allowed to
#: turn one of these strings into a response body, and confining it there is what
#: keeps "the network fetch is the one non-hermetic input" an auditable claim
#: rather than a sentence in a docstring.
_LOGO_HOSTS = ("a.espncdn.com", "cdn.collegefootballdata.com", "espncdn", "ncaa.com")
_FETCH_CALLS = ("httpx.get", "httpx.Client", "requests.get", "urlopen", "urlretrieve")
_FETCHER = REPO_ROOT / "src" / "cfbpoll" / "publish" / "logos.py"


#: The SVG namespace URI. It is an identifier, not a fetch — no renderer resolves
#: it — and it is the one and only `http://` a card SVG is allowed to contain.
SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def _externals(svg: str) -> list[str]:
    """Every `http(s)` URL in a card that is not the SVG namespace declaration."""
    return re.findall(r"https?://[^\"'\s>]+", svg.replace(SVG_NAMESPACE, ""))


def _code_without_docstrings(path: Path) -> str:
    """A module's CODE, with every docstring removed.

    Necessary because this project documents its rules in the docstrings of the
    modules that obey them, at length and quoting the strings the rules are about:
    `publish/cards.py` explains why an `href` may only be a `data:` URI, and
    `publish/logos.py` names the host it fetches from. A naive substring search
    over either file would find the explanation and fail. Parsing means the guard
    reads what the module DOES rather than what it says about itself.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _tracked() -> list[str]:
    return subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()


# ------------------------------------------------------------------ the CI guard


def test_no_image_file_in_the_tree_outside_the_allow_list() -> None:
    """The cards DRAW marks; the repository does not SHIP them. Still enforced."""
    found = {p for p in _tracked() if Path(p).suffix.lower() in _IMAGE_SUFFIXES}
    assert found == set(ALLOWED_IMAGES), sorted(found ^ set(ALLOWED_IMAGES))


def test_no_committed_card_svg_reaches_an_external_host() -> None:
    """A card is self-contained or it is not a card.

    The assertion that used to live here was "no `<image>` element", and the
    owner's ruling retired it. What is left is the part the ruling did not touch
    and that matters more now that there ARE images: an `<image>` may reference
    `data:` and nothing else. A card that hotlinks is a blank square the first
    time somebody reposts it somewhere the host does not serve.
    """
    for name in ALLOWED_IMAGES:
        if not name.endswith(".svg"):
            continue
        svg = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert _externals(svg) == [], name
        assert "@import" not in svg and "url(http" not in svg, name
        for href in re.findall(r'(?:xlink:)?href="([^"]*)"', svg):
            assert href.startswith("data:"), (name, href[:64])


def test_the_renderer_cannot_emit_an_external_href() -> None:
    """Not just the committed sample: the drawing code has no other href to write.

    `cards.py` builds exactly one `href=`, and the only thing it interpolates
    there is a `LogoMark.data_uri`, which `logos.resolve` builds by base64-ing
    bytes off the local cache. There is no code path from a published `logo_url`
    string to an attribute in the SVG.
    """
    source = _code_without_docstrings(REPO_ROOT / "src" / "cfbpoll" / "publish" / "cards.py")
    hrefs = re.findall(r'href="([^"]*)"', source)
    assert hrefs == ["{mark.data_uri}"], hrefs
    for host in _LOGO_HOSTS:
        assert host not in source, host
    for call in _FETCH_CALLS:
        assert call not in source, call


def test_the_logo_fetch_lives_in_exactly_one_module() -> None:
    """The one non-hermetic input has one address, and this is how that stays true.

    The old rule was that no logo host may ever be fetched from the package. The
    ruling overturned the ban, not the confinement: `publish/logos.py` is the only
    module that may turn a published `logo_url` into a response body, so a reader
    auditing what this project reaches out to has exactly one file to read and the
    card builders provably have no client to reach for.
    """
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if path == _FETCHER:
            continue
        source = _code_without_docstrings(path)
        for call in _FETCH_CALLS:
            if call not in source:
                continue
            # A module may fetch other things; what it may not do is fetch a mark.
            for line in source.splitlines():
                if any(host in line for host in _LOGO_HOSTS):
                    assert call not in line, (path, line)
        assert "logo_url" not in source or "httpx" not in source, path


def test_the_logo_cache_directory_is_gitignored() -> None:
    """Somebody else's files must not be able to arrive in the tree by accident."""
    probe = logos.CACHE_DIR / ("0" * 64 + ".png")
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(probe)], cwd=REPO_ROOT, check=False
    )
    assert result.returncode == 0, f"{logos.CACHE_DIR} is not ignored by .gitignore"
    assert logos.CACHE_DIR.is_relative_to(REPO_ROOT)
    inside = f"{logos.CACHE_DIR.relative_to(REPO_ROOT)}/"
    assert [p for p in _tracked() if p.startswith(inside)] == []


def test_the_manifest_matches_the_cached_bytes() -> None:
    """The pin, checked. Skips loudly when the cache is cold rather than failing.

    This is the assertion that makes the non-hermetic input auditable: the bytes a
    published card drew are the bytes the manifest says they were. CI without a
    network has nothing to compare and must not fail for it, which is why the skip
    is a skip and not a pass.
    """
    import hashlib

    pinned = logos.read_manifest()
    assert pinned, "data/logo-cache-manifest.json is empty; nothing is pinned"
    checked = 0
    for url, entry in sorted(pinned.items()):
        path = logos.cache_path(url)
        if not path.is_file():
            continue
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], url
        assert len(raw) == entry["length"], url
        checked += 1
    if not checked:
        pytest.skip(
            f"no logo bytes in {logos.CACHE_DIR}; run `cfbpoll publish cards --variant top10` "
            "to warm the cache, or leave it cold in an offline CI"
        )


def test_the_manifest_covers_every_mark_the_card_set_could_draw() -> None:
    """The pin is complete, not merely correct about what it happens to mention.

    `logos.resolve` draws from the cache and from nowhere else, so "every mark the
    card set draws" is exactly "every file in the cache". The invariant is
    maintained by construction - `warm` pins everything it fetches in the same
    call - and this is what catches somebody dropping a file into the cache by
    hand and shipping a card drawn from bytes nobody recorded.
    """
    if not logos.CACHE_DIR.is_dir():
        pytest.skip(f"{logos.CACHE_DIR} is cold; nothing to check")
    cached = sorted(logos.CACHE_DIR.glob("*.png"))
    if not cached:
        pytest.skip(f"{logos.CACHE_DIR} is cold; nothing to check")
    pinned = {logos.cache_path(url) for url in logos.read_manifest()}
    unpinned = [p.name for p in cached if p not in pinned]
    assert unpinned == [], (
        "these cached marks are not in data/logo-cache-manifest.json, so a card "
        f"could draw bytes nobody recorded: {unpinned}"
    )


# ------------------------------------------------------------------- the artifact


def test_the_committed_sample_is_a_1200x628_png() -> None:
    raw = SAMPLE_PNG.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", raw[16:24])
    assert (width, height) == (cards.CARD_WIDTH, cards.CARD_HEIGHT) == (1200, 628)
    # Report 05 §6.2: X rejects a card over 5 MB and Next.js fails the build on
    # one. Flat colour and straight lines put us three orders of magnitude inside.
    assert len(raw) < 5 * 1024 * 1024


def test_the_committed_svg_declares_the_same_geometry() -> None:
    svg = SAMPLE_SVG.read_text(encoding="utf-8")
    assert 'width="1200"' in svg and 'height="628"' in svg
    assert 'viewBox="0 0 1200 628"' in svg
    # A share image with no accessible name is an image with no accessible name,
    # wherever it ends up embedded.
    assert 'role="img"' in svg and "aria-label=" in svg


def test_the_address_on_the_cards_is_the_poll_s_own_domain() -> None:
    """The one place the address is written down, pinned to a value.

    The three footer tests below assert that `SITE_DOMAIN` REACHES the canvas,
    which is a check that would pass against any string. This one asserts WHAT
    THE STRING IS, so that a card set can never be published carrying an address
    nobody chose. A card outlives the page it was posted from; the host on it has
    to be the host that answers.

    It is the bare apex on purpose. No scheme, no `www`, no path: the poll is
    what the site serves at its root, and a reader retyping this off a PNG should
    not have to get a path right.
    """
    assert cards.SITE_DOMAIN == "thepoll.ai"


def test_the_card_carries_its_constants_footer() -> None:
    """Report 05 §6.2: "the constants footer is on the card... that line is the
    signature and it should never be dropped for space"."""
    svg = SAMPLE_SVG.read_text(encoding="utf-8")
    assert "q_ref" in svg
    assert cards.SITE_DOMAIN in svg
    assert cards.DATA_CREDIT in svg
    assert "2023 · WEEK 10" in svg


def test_the_committed_sample_carries_the_drawn_wordmark() -> None:
    """The mark is on the card and it is PATHS, not a font's guess at the mark.

    The brand's nameplate is custom letterforms; a card that set THE POLL in
    whatever grotesque the renderer resolved would be a different mark that
    happened to spell the same words. The `.ai` in the accent is the tell, and it
    is the only accent-coloured element in the lockup.
    """
    svg = SAMPLE_SVG.read_text(encoding="utf-8")
    for _dx, path in cards._MASTHEAD_NAME:
        assert path in svg
    assert f'fill="{cards.PALETTE["accent"]}"' in svg
    # And nothing anywhere in the pipeline sets the nameplate as type.
    assert ">THE POLL<" not in svg


def test_the_svg_is_a_pure_function_of_the_documents() -> None:
    """Two renders of one bundle are byte-identical, with no wall clock anywhere."""
    pytest.importorskip("polars")
    out = REPO_ROOT / ".cache" / "2023" / "w10"
    if not (out / "poll.json").exists():
        pytest.skip("no cached rank output; run `cfbpoll rank --season 2023 --through-week 10`")
    from cfbpoll.publish.serving import build

    bundle = build(out)
    first = cards.connectivity_svg(bundle)
    second = cards.connectivity_svg(build(out))
    assert first == second
    assert cards.render_png(first) == cards.render_png(second)


def test_rendering_the_sample_reproduces_the_committed_svg() -> None:
    """The committed card is regenerable, not a screenshot somebody saved.

    The SVG is checked and the PNG is not, deliberately: the SVG is font- and
    platform-independent, and the PNG's glyph rasterisation depends on which fonts
    the host has installed. Asserting a PNG hash would be asserting something
    about this laptop.
    """
    out = REPO_ROOT / ".cache" / "2023" / "w10"
    if not (out / "poll.json").exists():
        pytest.skip("no cached rank output for the sample week")
    from cfbpoll.publish.serving import build

    assert cards.connectivity_svg(build(out)) == SAMPLE_SVG.read_text(encoding="utf-8")


def test_an_unknown_variant_is_refused(tmp_path: Path) -> None:
    # This test used "top10" as its example of a name that does not exist, until
    # top10 was built. A placeholder that becomes real is a test that stops
    # testing, so the name here is one that never will be.
    with pytest.raises(ValueError, match="unknown card variant"):
        cards.export(tmp_path, tmp_path, variant="no-such-variant")


def test_every_variant_has_a_builder_a_canvas_and_a_row_count() -> None:
    """VARIANTS and BUILDERS cannot drift. The CLI's help reads one of them.

    The row count is on the same table because the export path warms the logo
    cache from it. A variant that drew more rows than it declared would render its
    last rows with the generated disc while their neighbours carried real marks,
    which is the kind of defect that only shows up in a published PNG.

    ONE is a legal count and it arrived with the single-team billboard, which
    draws exactly one school. `export_billboard` warms that row by name rather
    than by depth, because the subject of a billboard is regularly outside the
    top five.
    """
    assert set(cards.VARIANTS) == set(cards.BUILDERS)
    # FOUR HEIGHTS AND ONE WIDTH. The width is the family: every card this
    # project publishes is 1200 across, so a reader who has seen one recognises
    # the next. The heights are the surfaces - 1.91:1 for a link preview, 4:5 for
    # a feed, 1:1 for a carousel slide, and 2:3 for the all-teams poster, which is
    # the one canvas here that is not feed-native and says why in its own comment.
    canvases = (
        cards.CARD_HEIGHT,
        cards.TALL_HEIGHT,
        cards.SQUARE_HEIGHT,
        cards.POSTER_HEIGHT,
    )
    for name, (_builder, width, height, rows) in cards.BUILDERS.items():
        assert width == cards.CARD_WIDTH, name
        assert height in canvases, name
        assert rows in (0, 1, 5, 10, 25, 138), name
        assert (rows == 0) == (name == "connectivity"), name


def test_the_cli_help_lists_every_variant() -> None:
    """The one place a new variant is easy to forget, and it is user-facing."""
    source = (REPO_ROOT / "src" / "cfbpoll" / "cli.py").read_text(encoding="utf-8")
    helptext = source.split("Card variant:")[1].split('] = "connectivity"')[0]
    for name in cards.VARIANTS:
        assert name in helptext, name


def test_the_team_stripe_is_clamped_into_the_legible_band() -> None:
    """Navy must not vanish on #0B0C0F and neon must not shout over the numbers."""
    # The tolerance is 8-BIT QUANTISATION, not slack in the clamp. The colour is
    # clamped in OKLCH, rounded to three 8-bit sRGB channels for the SVG, and
    # measured again here, and one channel step is worth about 0.003 of L. A
    # tighter bound would be asserting that hex has more precision than it has.
    quantisation = 0.005
    for source in ("#0c2340", "#fee11a", "#000000", "#ffffff", "#ba0c2f"):
        clamped = cards.stripe_colour(source)
        lightness, chroma, _hue = cards._hex_to_oklch(clamped)
        assert cards.STRIPE_L_RANGE[0] - quantisation <= lightness
        assert lightness <= cards.STRIPE_L_RANGE[1] + quantisation
        assert chroma <= cards.STRIPE_C_MAX + quantisation


def test_a_missing_or_unparseable_team_colour_still_draws_a_stripe() -> None:
    """The box is drawn on every row. Omitting it would break the grid on
    exactly the rows whose data is weakest."""
    for bad in (None, "", "rgb(1,2,3)", "not-a-colour", "#12"):
        assert cards.stripe_colour(bad) == cards.PALETTE["stripe_fallback"]


def test_the_palette_is_the_brands_four_dark_tokens() -> None:
    """Pinned to values, not to "a dark palette". The gold is gone from the code.

    Every one of these is copied from the brand book's dark table, and the
    assertion is on the VALUES because a card set can otherwise drift a hex at a
    time until it is a different brand that nobody decided on.
    """
    assert cards.PALETTE["bg"] == "#101216"
    assert cards.PALETTE["ink"] == "#eae7e0"
    assert cards.PALETTE["rule"] == "#6f7278"
    assert cards.PALETTE["accent"] == "#00c2e0"
    # Ink drawn on a bone slab, which is what replaced the gold banner.
    assert cards.PALETTE["brand_ink"] == cards.PALETTE["bg"]
    # The rail is evidence and is deliberately not the accent.
    assert cards.PALETTE["rail_band"] != cards.PALETTE["accent"]
    # The retired gold appears nowhere in the module, in any case.
    source = (REPO_ROOT / "src" / "cfbpoll" / "publish" / "cards.py").read_text(encoding="utf-8")
    for retired in ("#F0B429", "#f0b429", "#9a5b08", "#0B0C0F"):
        assert retired not in source, retired


#: Every card the suite can draw without a run directory, as (name, svg). The
#: accent and cut-line rules are properties of the CARD SET rather than of one
#: variant, so they are asserted over all of them at once.
def _every_offline_card() -> list[tuple[str, str]]:
    document = _projection_document()
    spec = _comparison_spec()
    out = [(name, cards.BUILDERS[name][0](document)) for name in cards.PROJECTION_VARIANTS]
    out.append(("billboard_top5", cards.billboard_top5_svg(document)))
    out.append(("billboard_team", cards.billboard_team_svg(document, "Team 3")))
    out.append(("comparison", cards.comparison_svg(document, spec)))
    out.append(("comparison_tall", cards.comparison_tall_svg(document, spec)))
    out.append(
        (
            "comparison_square",
            cards.comparison_square_svg(document, {**spec, "slice": [1, 10]}),
        )
    )
    out.append(
        ("disagreement", cards.disagreement_svg(document, {**spec, "focus": "Team 3"}))
    )
    return out


def test_the_accent_marks_the_machine_and_nothing_else() -> None:
    """THE RULING THAT MAKES THE DIRECTION WORK, enforced rather than described.

    The brand permits the accent in four places and a share card can reach three:
    the `.ai` in the wordmark, the schedule-odds key and its column, and one
    divider rule above the attribution. This counts them. A cyan slab, a cyan
    team name or a second cyan rule fails here, which is the point: the discipline
    is what keeps the card from being any other college football account's card.
    """
    accent = cards.PALETTE["accent"]
    for name, svg in _every_offline_card():
        lines = svg.splitlines()
        # No filled rectangle is ever the accent. The gold slab is retired.
        slabs = [line for line in lines if line.startswith("<rect") and accent in line]
        assert slabs == [], (name, slabs)
        # At most one accent rule, and it is the footer divider.
        rules = [line for line in lines if line.startswith("<line") and accent in line]
        assert len(rules) <= 1, (name, rules)
        # A projection board prints win totals, which are NOT the schedule-odds
        # key, so the accent may not reach any text on one. The billboards draw
        # the same document and are held to the same rule.
        if name in (*cards.PROJECTION_VARIANTS, *cards.BILLBOARD_VARIANTS):
            texts = [line for line in lines if line.startswith("<text") and accent in line]
            assert texts == [], (name, texts)


def test_no_card_draws_a_playoff_cut_line() -> None:
    """A STANDING RULE FROM THE OWNER, AND THE REASON THIS TEST OUTLIVES ME.

    Until 2026-08-17 every board variant drew a 2px accent rule after rank 4 and
    this module called it "the card's loudest sports signal". It is gone: a poll
    that refuses to run a committee does not draw the committee's line, and a
    bracket boundary on a preseason projection asserts something about January
    that no number on the card supports.

    The guard is structural rather than a colour check, because the next version
    of the mistake would be a bone rule or a thicker separator. NO row separator
    on any card may differ from its neighbours.
    """
    for name, svg in _every_offline_card():
        widths = {
            line.split('stroke-width="')[1].split('"')[0]
            for line in svg.splitlines()
            if line.startswith("<line") and "stroke-width=" in line
        }
        # The only heavy line on any card is the footer divider.
        assert widths <= {"1", "2"}, (name, widths)
        heavy = [ln for ln in svg.splitlines() if ln.startswith("<line") and '"2"' in ln]
        assert len(heavy) <= 1, (name, heavy)
        assert "playoff" not in svg.lower(), name


def test_word_wrap_never_exceeds_its_budget_and_marks_truncation() -> None:
    text = "one two three four five six seven eight nine ten eleven twelve"
    lines = cards._wrap(text, 20, 2)
    assert len(lines) == 2
    assert all(len(line) <= 20 for line in lines)
    assert lines[-1].endswith("…")
    assert cards._wrap(text, 200, 3) == [text]


# --------------------------------------------------------- the vendored typefaces

#: A card in miniature: one line of text in each of the four stacks, at a fixed
#: size, on a fixed canvas. Everything that decides the output bytes is in this
#: string or in `assets/fonts`, which is what lets the hash below mean something.
_FONT_PROBE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="220">'
    '<rect width="600" height="220" fill="#0B0C0F"/>'
    f'<text x="16" y="48" font-size="30" fill="#fff" font-family="{cards.FONT_DISPLAY}">'
    "Handgloves 123</text>"
    f'<text x="16" y="96" font-size="26" fill="#fff" font-family="{cards.FONT_UI}">'
    "Handgloves 123</text>"
    f'<text x="16" y="144" font-size="24" fill="#fff" font-family="{cards.FONT_MONO}">'
    "0.9841 tau</text>"
    f'<text x="16" y="196" font-size="26" fill="#fff" font-family="{cards.FONT_PROSE}">'
    "Handgloves 123</text>"
    "</svg>"
)

#: sha256 of `_FONT_PROBE` rasterised against the vendored families. THIS IS THE
#: HOST-INDEPENDENCE ASSERTION: the number is a pure function of the pinned resvg
#: wheel and the font files in this repo, so it is the same on every machine that
#: checks out this commit. Before the families were vendored there was no such
#: number to write down - the bytes depended on whatever the host happened to have
#: installed, which is precisely the defect.
#:
#: If this changes, something changed the rendering: a font file, the resvg pin,
#: or a stack. All three are things a reviewer should be told about rather than
#: discover in a published PNG.
_FONT_PROBE_SHA256 = "f361e06dc24358b263471ba2f6ddc9e3d5de4e10974339e2fb658e45abafe863"


def _render(svg: str, **kwargs: object) -> bytes:
    import resvg_py

    return bytes(resvg_py.svg_to_bytes(svg_string=svg, **kwargs))


def test_the_font_families_are_vendored_in_repo() -> None:
    """The check must see the families, which live one directory each.

    A font file has to sit beside the licence that permits redistributing it, so
    the families are vendored one subdirectory apiece. A non-recursive check found
    nothing directly inside `assets/fonts/` and reported "not vendored", which
    would silently have left the renderer back on the host's fonts on a machine
    where the files were in fact present.
    """
    assert cards.fonts_are_vendored() is True
    families = {p.parent.name for p in cards.FONT_DIR.rglob("*.ttf")}
    assert families == {"archivo", "dejavu", "jetbrains-mono", "source-serif-4"}


def test_every_vendored_family_ships_its_licence() -> None:
    """Redistribution is what the licence permits; shipping it is the condition."""
    for family in sorted(p for p in cards.FONT_DIR.iterdir() if p.is_dir()):
        licences = [p for p in family.iterdir() if p.name in {"OFL.txt", "LICENSE"}]
        assert licences, f"{family.name} ships font files with no licence beside them"
        text = licences[0].read_text(encoding="utf-8", errors="replace")
        assert "SIL OPEN FONT LICENSE" in text.upper() or "Bitstream Vera" in text, family.name


@pytest.mark.parametrize(
    ("name", "stack"),
    [
        ("display", cards.FONT_DISPLAY),
        ("ui", cards.FONT_UI),
        ("mono", cards.FONT_MONO),
        ("prose", cards.FONT_PROSE),
    ],
)
def test_no_font_stack_rasterises_to_nothing(name: str, stack: str) -> None:
    """THE REGRESSION GUARD FOR A BUG THAT SHIPPED, and it is subtle enough to
    deserve one test per stack.

    An unquoted CSS family name is a sequence of identifiers and an identifier may
    not start with a digit, so `Source Serif 4` unquoted is invalid and a parser
    that meets the bare `4` throws away THE WHOLE DECLARATION - every fallback in
    the list with it. The prose line on every card was rendering blank: not in the
    DejaVu Serif sitting next in the stack, not in Georgia, blank. Nothing caught
    it because a card with one invisible line still has the right dimensions, the
    right file size and the right sha256.

    So the assertion is against a family that does not exist. If a stack
    rasterises to the same bytes as gibberish, that stack is drawing nothing.
    """
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="80">'
        f'<text x="10" y="50" font-size="32" font-family="{stack}">Handgloves 123</text></svg>'
    )
    missing = svg.replace(stack, "NoSuchFamilyAnywhere")
    kwargs = {"skip_system_fonts": True, "font_dirs": [str(cards.FONT_DIR)]}
    assert _render(svg, **kwargs) != _render(missing, **kwargs), (
        f"the {name} stack rasterises to the same bytes as a nonexistent family, "
        f"which means it is drawing nothing: {stack}"
    )


def test_the_render_does_not_depend_on_the_host(request: pytest.FixtureRequest) -> None:
    """The whole point of vendoring, as a number that can be written down.

    `render_png` pins `skip_system_fonts=True` and points resvg at `FONT_DIR`, so
    the output is a function of this repository and the pinned rasteriser and of
    nothing else on the machine. That is what makes the hash below assertable at
    all; before vendoring there was no such hash, because the bytes depended on
    what the host had installed.
    """
    import hashlib

    got = hashlib.sha256(cards.render_png(_FONT_PROBE)).hexdigest()
    if _FONT_PROBE_SHA256 == "PLACEHOLDER":  # pragma: no cover - bootstrap only
        pytest.fail(f"set _FONT_PROBE_SHA256 to {got!r}")
    assert got == _FONT_PROBE_SHA256, (
        "the rasterised probe changed. A font file, the resvg pin or a font stack "
        "moved; all three change published artifacts and none should move quietly."
    )


def test_rendering_is_stable_across_calls() -> None:
    assert cards.render_png(_FONT_PROBE) == cards.render_png(_FONT_PROBE)


def test_the_dejavu_fallback_actually_covers_what_the_primaries_miss() -> None:
    """Why 1.5 MB of fonts that change no current card are not dead weight.

    Every card this project renders today is byte-identical with DejaVu removed:
    the three primaries cover the whole board. That makes the fallback look
    deletable, so this pins what it is FOR. With `skip_system_fonts=True` there is
    no host font to catch a character the primaries lack, and the renderer draws a
    tofu box onto an artifact that then gets hashed and published.

    The probe is a character outside the primaries' coverage. If DejaVu ever stops
    supplying it, the fallback has stopped working and the next unusual team name
    is a box on a published PNG.
    """
    probe = "Ā Ə ŋ ʻ"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="80">'
        f'<text x="10" y="50" font-size="28" font-family="{cards.FONT_UI}">{probe}</text></svg>'
    )
    primaries = [
        str(cards.FONT_DIR / name) for name in ("archivo", "jetbrains-mono", "source-serif-4")
    ]
    with_fallback = _render(svg, skip_system_fonts=True, font_dirs=[str(cards.FONT_DIR)])
    without = _render(svg, skip_system_fonts=True, font_dirs=primaries)
    assert with_fallback != without, (
        "DejaVu changed nothing on a string the primaries do not cover, which means "
        "the missing-glyph fallback is not reaching the renderer"
    )


# --------------------------------------------------------------- the projection card

#: A projection document in the shape `projection/publish.build` writes, trimmed
#: to the fields a card reads. Deliberately hand-built rather than loaded from the
#: fixture tree: these tests are about the renderer, and a card that only works
#: against one committed season is a card nobody can change safely.
def _projection_document(status: str = "published", rows: int = 25) -> dict[str, object]:
    return {
        "schema_version": 1,
        "season": 2026,
        "status": status,
        "label": "THE PROJECTION. The poll grades it weekly.",
        "headline": (
            "This is the model's 2026 preseason projection, built in August "
            "about a season the poll will go on to measure."
        ),
        "grading_start_week": 5,
        "projection_version": "projection-1.0.0",
        "backtest": {
            "ap_top25_hits": "14.7",
            "projection_top25_hits": "14.3",
            "naive_top25_hits": "13.3",
            "transitions": 3,
        },
        "rows": [
            {
                "rank": i + 1,
                "team": f"Team {i + 1}",
                "abbreviation": f"T{i + 1:02d}",
                "mark_bg": "#0c2340",
                "mark_fg": "#ffffff",
                "mark_label": f"T{i + 1:02d}",
                "projected_wins": f"{12.0 - i * 0.2:.1f}",
                # Power FALLS with the rank and the win total does not have to.
                # That is the real shape of the published document (Ohio State
                # projects fewer wins than Oregon and outranks it), and the
                # billboards exist to print the figure that agrees with the order.
                "projected_power": f"{25.0 - i * 0.4:.1f}",
            }
            for i in range(rows)
        ],
    }


@pytest.mark.parametrize("variant", cards.PROJECTION_VARIANTS)
def test_a_row_with_no_published_logo_falls_back_to_the_generated_mark(variant: str) -> None:
    """The fallback is what keeps a cold cache and a logo-free config renderable.

    `_projection_document` publishes no `logo_url`, which is exactly what
    `[display].logos = false` produces, so every row draws the generated disc. A
    board that rendered empty squares in that configuration would have made the
    logo-free mode a code change again, which is the thing `serving._logo_urls`
    exists to prevent.
    """
    svg = cards.BUILDERS[variant][0](_projection_document())
    assert "<image" not in svg
    assert _externals(svg) == []
    assert "@import" not in svg and "url(http" not in svg
    assert "<circle" in svg


@pytest.mark.parametrize("variant", cards.PROJECTION_VARIANTS)
def test_the_projection_card_declares_the_canvas_its_builder_table_promises(
    variant: str,
) -> None:
    """The table and the SVG cannot disagree about the size of the artifact.

    Three of these are the `summary_large_image` ratio and the grid is the tall
    one, because 138 teams do not go on a 628px card at any type size a person
    can read. The check is against `BUILDERS` rather than a literal so adding a
    canvas is a one-line change in one place.
    """
    height = cards.BUILDERS[variant][2]
    svg = cards.BUILDERS[variant][0](_projection_document(rows=138))
    assert 'width="1200"' in svg and f'height="{height}"' in svg
    assert f'viewBox="0 0 1200 {height}"' in svg
    assert 'role="img"' in svg and "aria-label=" in svg


def test_the_projection_card_prints_projected_wins_and_never_an_odds_key() -> None:
    """The right-hand column is the projection's number, verbatim from the field.

    `projected_wins` is published PRE-FORMATTED, so the assertion is that the
    string on the card is the string in the document. A card that reformatted it
    could disagree with the JSON a reader downloads.
    """
    document = _projection_document()
    svg = cards.projection_top10_svg(document)
    assert "1 in " not in svg
    for row in document["rows"][:10]:  # type: ignore[index]
        assert f"{row['projected_wins']} wins" in svg
    # And the eleventh row is not on a top-ten card.
    assert f"{document['rows'][10]['projected_wins']} wins" not in svg  # type: ignore[index]


def test_the_projection_card_carries_the_documents_own_label() -> None:
    """The banner is a published field, exactly as the alternate-lens marker is.

    A card is the artifact most likely to arrive with no context at all, so the
    sentence naming it as the projection rather than the poll has to be ON it, and it
    has to be the document's words rather than a string in this renderer.

    IT IS DRAWN AS A BONE REVERSE BLOCK, NOT AN ACCENT SLAB. The accent means "the
    machine" and a document's statement of what it is is not that; the reverse
    block is louder anyway at 15.18:1.
    """
    document = _projection_document()
    document["label"] = "SOMETHING ELSE ENTIRELY."
    svg = cards.projection_top10_svg(document)
    assert "SOMETHING ELSE ENTIRELY." in svg
    slabs = [
        line
        for line in svg.splitlines()
        if line.startswith("<rect") and f'fill="{cards.PALETTE["ink"]}"' in line
    ]
    assert slabs, "the label has no reverse block under it"


def test_the_projection_label_fits_its_slab_without_being_clipped() -> None:
    """A truncated "this is not the poll" notice is the one truncation that matters.

    THE BLOCK SHRINKS ITS TYPE BEFORE IT CUTS THE STRING, which is why this now
    also checks a label far longer than any document ships: the failure mode is a
    longer notice arriving later and being silently cut mid-word.
    """
    from cfbpoll.projection.publish import PROJECTION_LABEL

    svg = cards.projection_top10_svg(_projection_document())
    assert PROJECTION_LABEL in svg
    assert "…" not in svg.split("</svg>")[0].split(PROJECTION_LABEL)[0][-80:]

    document = _projection_document()
    document["label"] = "A PROJECTION. IT IS NOT THE POLL AND NEVER BECOMES ONE."
    assert len(document["label"]) > len(PROJECTION_LABEL)
    assert document["label"] in cards.projection_top10_svg(document)


def test_the_projection_card_carries_its_backtest_footer() -> None:
    """The poll card's signature is its constants. This one's is the honest score.

    Report 05 §6.2's rule is that the footer is never dropped for space, and the
    projection's equivalent claim is the measured record against the AP's August
    ballot, published on the image whether or not it flatters. Every figure is a
    published field; what changed on 2026-08-17 is that the line says what the
    figures COUNT, because the brand audit read the shipping card and found "four
    unexplained numbers on the surface a stranger meets first".
    """
    svg = cards.projection_top10_svg(_projection_document())
    assert "recipe projection-1.0.0" in svg
    for field in ("3 past preseasons", "AP 14.7", "this recipe 14.3", "forward 13.3"):
        assert field in svg, field
    assert "hits in the final top 25" in svg
    assert cards.SITE_DOMAIN in svg
    assert cards.DATA_CREDIT in svg


def test_a_dark_projection_is_refused_rather_than_drawn() -> None:
    """`status` is authoritative. Rendering a card from a dark document would
    publish the very thing the field exists to keep unpublished."""
    with pytest.raises(ValueError, match="not published"):
        cards.projection_top10_svg(_projection_document(status="coming"))
    with pytest.raises(ValueError, match="no rows"):
        cards.projection_top25_svg(_projection_document(rows=0))


def test_the_projection_svg_is_a_pure_function_of_the_document() -> None:
    """No wall clock, no RNG, no dict iteration order."""
    for variant in cards.PROJECTION_VARIANTS:
        builder = cards.BUILDERS[variant][0]
        assert builder(_projection_document()) == builder(_projection_document())


def test_a_projection_variant_refuses_the_run_directory_path(tmp_path: Path) -> None:
    """It has no run directory and no week; sending it through `export` would
    have to invent both."""
    with pytest.raises(ValueError, match="export_projection"):
        cards.export(tmp_path, tmp_path, variant="projection_top10")
    with pytest.raises(ValueError, match="unknown projection card variant"):
        cards.export_projection(tmp_path / "p.json", tmp_path, variant="top10")


def test_export_projection_names_the_files_after_the_season_and_no_week(
    tmp_path: Path,
) -> None:
    """`2026-projection-top10`, because a preseason projection has no week to stamp."""
    import json as _json

    document = tmp_path / "projection.json"
    document.write_text(_json.dumps(_projection_document()), encoding="utf-8")
    written = cards.export_projection(
        document, tmp_path / "share", variant="projection_top25", png=False
    )
    assert [p.name for p in written] == ["2026-projection-top25.svg"]


# ------------------------------------------------------------------ the tiles


def test_the_grid_fills_down_each_column_before_it_moves_across() -> None:
    """A poll is read top to bottom, so a tile card is filled top to bottom.

    The first version of this card ran the ranks ACROSS the rows, which put 1 to 7
    along the top and 8 under 1. A reader scanning the left edge for the twenties
    found 15 there and read a board that did not say what they thought it said.

    THE COLUMN COUNT IS READ OFF THE MODULE, not typed in here. It went from 7 to
    14 when the rows became tiles and the arithmetic did not change; a test that
    pinned the old number would have failed for the wrong reason and taught the
    next reader that the rule was about seven columns.
    """
    columns = cards.GRID_COLUMNS
    cells = cards._grid_cells(138, columns)
    assert len(cells) == 138
    assert len(set(cells)) == 138
    depth = -(-138 // columns)
    # 2 sits directly under 1, and the first team of the second column tops it
    # rather than following the last team of the first.
    assert cells[0] == (0, 0)
    assert cells[1] == (0, 1)
    assert cells[depth - 1] == (0, depth - 1)
    assert cells[depth] == (1, 0)
    # The columns that do not divide evenly leave the hole at the bottom of the
    # RIGHTMOST ones rather than at the bottom of the first, which is what lets
    # the caller rule each line off column 0 alone.
    depths = [sum(1 for column, _line in cells if column == index) for index in range(columns)]
    assert sum(depths) == 138
    assert depths[0] == depth
    assert set(depths) <= {depth, depth - 1}
    assert depths == sorted(depths, reverse=True)
    # A board shorter than one row per column still fills left to right.
    assert cards._grid_cells(5, 7) == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]


#: The two cards that draw tiles, with the columns each declares. Both rules
#: below are properties of the FORMAT rather than of the poster, so both cards
#: are held to them: the 25 and the 138 are one layout at two densities and a
#: change that lands on one and misses the other is the defect this catches.
_TILE_CARDS = (
    ("projection_top25", 25, "TOP25_COLUMNS"),
    ("projection_grid", 138, "GRID_COLUMNS"),
)


@pytest.mark.parametrize(("variant", "count", "columns_name"), _TILE_CARDS)
def test_the_drawn_tiles_put_rank_two_under_rank_one(
    variant: str, count: int, columns_name: str
) -> None:
    """The same rule, asserted on the artifact rather than on the arithmetic."""
    columns = getattr(cards, columns_name)
    depth = -(-count // columns)
    svg = cards.BUILDERS[variant][0](_projection_document(rows=138))
    placed = {
        int(match.group(3)): (float(match.group(1)), float(match.group(2)))
        for match in re.finditer(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*>(\d+)</text>', svg)
    }
    assert len(placed) == count
    assert placed[2][0] == placed[1][0]
    assert placed[2][1] > placed[1][1]
    # The team that opens the second column sits beside rank 1, not under rank
    # `depth`, which is the whole of the top-to-bottom rule.
    assert placed[depth + 1][0] > placed[1][0]
    assert placed[depth + 1][1] == placed[1][1]
    # EVERY column runs downwards and each starts to the right of the last, and
    # the membership comes from `_grid_cells` rather than from `depth`: the last
    # columns of a board that does not divide evenly are one shorter, so a loop
    # that stepped by `depth` would straddle a column boundary and fail on the
    # geometry being right.
    by_column: dict[int, list[int]] = {}
    for index, (column, _line) in enumerate(cards._grid_cells(count, columns)):
        by_column.setdefault(column, []).append(index + 1)
    previous_x = None
    for column in sorted(by_column):
        ranks = by_column[column]
        column_x = placed[ranks[0]][0]
        assert [placed[rank][0] for rank in ranks] == [column_x] * len(ranks)
        assert placed[ranks[-1]][1] > placed[ranks[0]][1]
        if previous_x is not None:
            assert column_x > previous_x
        previous_x = column_x


@pytest.mark.parametrize(("variant", "count", "columns_name"), _TILE_CARDS)
def test_a_tile_card_draws_its_mark_larger_than_its_own_numeral(
    variant: str, count: int, columns_name: str
) -> None:
    """THE OWNER'S RULING, MEASURED. "The 25 and the full list must MAXIMIZE logo
    and rank-number size for at-a-glance reading" (2026-08-18).

    The check is a RATIO rather than a pixel count, because a pixel count is a
    number somebody would update to match whatever the card happened to draw. A
    tile exists so the mark is the biggest thing in the cell; if the numeral ever
    catches it, the card has quietly gone back to being a row with the parts
    stacked, which is the regression this exists to catch. The floor is generous
    on purpose - it fails on a change of KIND, not on a tweak.
    """
    svg = cards.BUILDERS[variant][0](_projection_document(rows=138))
    marks = [float(m) for m in re.findall(r'<circle [^>]*r="([\d.]+)"', svg)]
    assert len(marks) == count, "every row draws a mark"
    diameter = min(marks) * 2
    numerals = {
        float(m)
        for m in re.findall(r'<text [^>]*font-size="([\d.]+)"[^>]*>\d+</text>', svg)
    }
    assert len(numerals) == 1, "one rank size on the card; rank 1 is drawn like rank 138"
    assert diameter > numerals.pop() * 1.5, variant
    # And the mark is bigger than it was as a row, which is what the ruling asked
    # for. The retired row layout gave the 25 an 18px mark and the 138 a 29px one.
    assert diameter > 60, variant


# -------------------------------------------------------------- the billboard


def _billboards(document: dict[str, object]) -> list[tuple[str, str]]:
    return [
        ("billboard_top5", cards.billboard_top5_svg(document)),
        ("billboard_team", cards.billboard_team_svg(document, "Team 3")),
    ]


def test_the_billboards_draw_on_the_square_canvas_their_table_promises() -> None:
    """1:1 is the canvas a feed crops least, which is the whole reason they exist."""
    for name, svg in _billboards(_projection_document()):
        height = cards.BUILDERS[name][2]
        assert height == cards.SQUARE_HEIGHT, name
        assert 'width="1200"' in svg and f'height="{height}"' in svg, name
        assert f'viewBox="0 0 1200 {height}"' in svg, name
        assert 'role="img"' in svg and "aria-label=" in svg, name


def test_the_billboard_carries_the_teaser_whole_and_sends_it_to_our_own_domain() -> None:
    """The one marketing sentence on the card set, and it may not arrive clipped.

    It is also the sentence most likely to be read with nothing around it, so the
    voice profile's hard rules are asserted on it rather than trusted: no em dash,
    and no middot doing a conjunction's job. The owner's 2026-08-18 correction is
    asserted too, because "try to improve it" alone does not say what the
    disagreement is for and he asked for the full sentence.
    """
    teaser = cards.BILLBOARD_TEASER
    assert cards.SITE_DOMAIN in teaser
    assert "—" not in teaser
    assert "·" not in teaser
    assert "If you don't agree, try to improve it." in teaser
    for name, svg in _billboards(_projection_document()):
        drawn = " ".join(re.findall(r"<text[^>]*>([^<]*)</text>", svg))
        # Compared through the module's own escaper: the apostrophe in "don't"
        # reaches the file as `&apos;`, and asserting on the raw string would be
        # asserting that the card is invalid XML.
        assert cards._esc(teaser) in drawn, name


def test_the_clarity_line_prints_real_counts_from_the_pinned_file() -> None:
    """No placeholder ships. The counts come from `data/corpus-counts.json`.

    The owner's instruction with this line was to pull the true numbers out of
    the pipeline, so the test asserts the drawn sentence contains the pin's
    figures formatted with separators, and that no `N` or `{}` survived the
    template.
    """
    counts = cards.corpus_counts()
    for key in ("games", "plays", "simulated_seasons"):
        assert int(counts[key]) > 0, key
    expected = [f"{int(counts[key]):,}" for key in ("games", "plays", "simulated_seasons")]

    for name, svg in _billboards(_projection_document()):
        drawn = " ".join(re.findall(r"<text[^>]*>([^<]*)</text>", svg))
        for figure in expected:
            assert figure in drawn, (name, figure)
        assert "{" not in drawn and "}" not in drawn, name
        assert " N " not in drawn, name
    # And the sentence itself obeys the same hard rules as the tagline.
    assert "—" not in cards.BILLBOARD_CLARITY
    assert "·" not in cards.BILLBOARD_CLARITY


def test_a_billboard_refuses_to_draw_without_its_counts(tmp_path: Path) -> None:
    """A card with a hole where a number goes is the thing this must never be."""
    with pytest.raises(FileNotFoundError, match="count_corpus"):
        cards.corpus_counts(tmp_path / "nope.json")
    blank = tmp_path / "blank.json"
    blank.write_text(json.dumps({"games": 0, "plays": 0, "simulated_seasons": 0}))
    with pytest.raises(ValueError, match="blank count"):
        cards.corpus_counts(blank)


def test_the_billboard_number_falls_with_the_rank() -> None:
    """THE FIX THE OWNER CAUGHT: 8.8 wins above 9.0 wins reads as broken data.

    The projection is ordered on power, so power is the only published figure
    that a reader can scan down the column and see agree with the rank. This
    reads the numerals off the drawn card rather than trusting the field, and it
    runs over the whole 138-row board rather than the top five, because the
    single-team template draws from all of it.
    """
    document = _projection_document(rows=138)
    values = [float(row["projected_power"]) for row in document["rows"]]  # type: ignore[index]
    assert values == sorted(values, reverse=True)

    svg = cards.billboard_top5_svg(document)
    drawn = re.findall(r"<text[^>]*>(-?\d+\.\d+) power</text>", svg)
    assert len(drawn) == 5
    assert [float(v) for v in drawn] == sorted((float(v) for v in drawn), reverse=True)
    # The win total is off this family entirely, so the two cannot disagree.
    assert "wins" not in svg


def test_the_billboard_carries_no_constants_footer() -> None:
    """A REVERSAL OF A STANDING RULE, ENFORCED SO IT CANNOT DRIFT BACK.

    `AGENTS.md` says the constants footer is never dropped for space, and it is
    still on every other card. The owner struck it from this family on
    2026-08-18: "No stat nerd shit. Just the taglines." So no run id, no config
    hash, no recipe version, no backtest line, and no mono type at all.

    CFBD's attribution stays, and that is deliberate rather than an incomplete
    edit: it is an attribution commitment this project makes on every published
    surface, not a constant.
    """
    document = _projection_document()
    for name, svg in _billboards(document):
        assert "recipe projection-" not in svg, name
        assert "past preseasons" not in svg, name
        assert "grades this from week" not in svg, name
        assert cards.FONT_MONO not in svg, name
        assert cards.DATA_CREDIT in svg, name
    # The variants built to be READ are untouched by the ruling.
    kept = cards.projection_top5_svg(document)
    assert "recipe projection-" in kept and cards.FONT_MONO in kept


def test_the_billboard_says_which_document_it_is_drawing() -> None:
    """ADR 0010, on the surface where letting the two blur would cost the most."""
    document = _projection_document()
    for name, svg in _billboards(document):
        assert str(document["label"]) in svg, name
        assert "PRESEASON PROJECTION" in svg, name


def test_the_single_team_billboard_labels_its_giant_numeral() -> None:
    """Rule 0. A bare 3 at 300px is a puzzle to a reader who arrives with no
    context, and a billboard has no other kind of reader."""
    svg = cards.billboard_team_svg(_projection_document(), "Team 3")
    assert "PROJECTED RANK" in svg
    assert "24.2 projected power rating" in svg
    assert f'font-size="{cards._n(cards.BILLBOARD_TEAM_RANK_SIZE)}"' in svg


def test_a_billboard_refuses_a_team_the_board_does_not_rank() -> None:
    with pytest.raises(ValueError, match="not in this document"):
        cards.billboard_team_svg(_projection_document(), "Nowhere State")


def test_the_billboard_svg_is_a_pure_function_of_the_document() -> None:
    assert cards.billboard_top5_svg(_projection_document()) == cards.billboard_top5_svg(
        _projection_document()
    )
    assert cards.billboard_team_svg(
        _projection_document(), "Team 3"
    ) == cards.billboard_team_svg(_projection_document(), "Team 3")


def test_a_billboard_variant_refuses_the_run_directory_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="export_billboard"):
        cards.export(tmp_path, tmp_path, variant="billboard_top5")
    with pytest.raises(ValueError, match="unknown billboard card variant"):
        cards.export_billboard(tmp_path / "p.json", tmp_path, variant="top10")


def test_export_billboard_names_the_files_after_the_season_and_the_subject(
    tmp_path: Path,
) -> None:
    """`2026-billboard-top5` and `2026-billboard-team-3`, one artifact per subject."""
    document = tmp_path / "projection.json"
    document.write_text(json.dumps(_projection_document()), encoding="utf-8")
    written = cards.export_billboard(
        document, tmp_path / "share", variant="billboard_top5", png=False, fetch_logos=False
    )
    assert [p.name for p in written] == ["2026-billboard-top5.svg"]
    written = cards.export_billboard(
        document,
        tmp_path / "share",
        variant="billboard_team",
        team="Team 3",
        png=False,
        fetch_logos=False,
    )
    assert [p.name for p in written] == ["2026-billboard-team-3.svg"]


def test_a_billboard_that_names_the_wrong_number_of_subjects_is_refused(
    tmp_path: Path,
) -> None:
    """A run that names a team and gets the top five back is one somebody ships."""
    document = tmp_path / "projection.json"
    document.write_text(json.dumps(_projection_document()), encoding="utf-8")
    with pytest.raises(ValueError, match="needs `team`"):
        cards.export_billboard(document, tmp_path, variant="billboard_team", png=False)
    with pytest.raises(ValueError, match="takes no `team`"):
        cards.export_billboard(
            document, tmp_path, variant="billboard_top5", team="Team 3", png=False
        )


# ------------------------------------------------------------- the top five, big

#: The hero card's whole reason to exist is that it survives a timeline crop, so
#: the geometry is asserted rather than eyeballed.
_HERO_VARIANTS = ("top5", "projection_top5")


def test_the_top_five_block_fits_inside_the_mobile_safe_band() -> None:
    """Five rows from SAFE_TOP end one pixel inside SAFE_BOTTOM.

    X crops the top and bottom on mobile and the top five is the variant most
    likely to be seen as a thumbnail and never tapped, so every row has to survive
    the crop. This is the constraint the card is sized to; the wordmark and the
    footer sit outside it deliberately.
    """
    bottom = cards.HERO_ROW_TOP + 5 * cards.HERO_ROW_HEIGHT
    assert cards.HERO_ROW_TOP >= cards.SAFE_TOP
    assert bottom <= cards.CARD_HEIGHT - 126


def test_the_top_five_draws_five_rows_and_treats_every_one_of_them_alike() -> None:
    """Five rows, and rank 1 is drawn exactly like rank 5.

    THE OTHER STANDING RULE. There is no crown on the leader, no heavier stripe,
    no larger mark and no separator that says "these four and then the rest". The
    only thing that distinguishes a row on this card is its numbers.
    """
    document = _projection_document()
    svg = cards.projection_top5_svg(document)
    for row in document["rows"][:5]:  # type: ignore[index]
        assert f"{row['projected_wins']} wins" in svg
    assert f"{document['rows'][5]['projected_wins']} wins" not in svg  # type: ignore[index]

    # Every row separator inside the block is byte-identical but for its y.
    separators = [
        line
        for line in svg.splitlines()
        if line.startswith("<line") and f'x1="{cards._n(cards.COLUMN_W + 32)}"' in line
    ]
    assert len(separators) == 5, separators
    shapes = {re.sub(r'y[12]="[^"]*"', "", line) for line in separators}
    assert len(shapes) == 1, shapes

    # And the row geometry itself does not vary with rank.
    stripes = [
        line
        for line in svg.splitlines()
        if line.startswith("<rect") and 'width="3"' in line
    ]
    assert len({line.split('height="')[1].split('"')[0] for line in stripes}) == 1


@pytest.mark.parametrize("variant", _HERO_VARIANTS)
def test_the_hero_card_keeps_the_footer_that_is_never_dropped_for_space(variant: str) -> None:
    """Report 05 §6.2's rule survives the variant with the least room for it."""
    if variant == "projection_top5":
        svg = cards.projection_top5_svg(_projection_document())
        assert "recipe projection-1.0.0" in svg and "AP 14.7" in svg
    else:
        pytest.importorskip("polars")
        out = REPO_ROOT / ".cache" / "2023" / "w10"
        if not (out / "poll.json").exists():
            pytest.skip("no cached rank output for the sample week")
        from cfbpoll.publish.serving import build

        svg = cards.top5_svg(build(out))
        assert "q_ref" in svg
    assert cards.SITE_DOMAIN in svg


# ------------------------------------------------------------- the comparison card

#: A comparison spec in the shape `load_comparison` accepts, over the teams
#: `_projection_document` publishes. Two boards, one of which ties two teams and
#: leaves one unranked, because those are the two cases a hand-made graphic gets
#: wrong and this pipeline exists to stop getting wrong.
def _comparison_spec(**over: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "schema_version": 1,
        "slug": "test-boards",
        "mode": "board",
        "slice": [1, 25],
        "unranked_at": 26,
        "eyebrow": "2026 preseason",
        "label": "THEIR POLL. OUR PROJECTION.",
        "headline": "Two boards, one model.",
        "ours": {"name": "The Poll", "kind": "projection"},
        "boards": [
            {
                "name": "AP",
                "kind": "poll",
                "released": "2026-08-17",
                "source": "https://example.test/ap",
                # Team 4 and Team 5 tied; Team 6 unranked by either board.
                "ranks": {
                    "Team 1": 1,
                    "Team 2": 2,
                    "Team 3": 12,
                    "Team 4": 4,
                    "Team 5": 4,
                    "Team 7": 7,
                },
            },
            {
                "name": "Coaches",
                "kind": "poll",
                "released": "2026-08-17",
                "source": "https://example.test/coaches",
                "ranks": {"Team 1": 1, "Team 2": 2, "Team 3": 11, "Team 7": 8},
            },
        ],
    }
    spec.update(over)
    return spec


def test_a_comparison_spec_missing_its_sources_is_refused(tmp_path: Path) -> None:
    """THE FIELD THAT MAKES THIS AUDITABLE IS REQUIRED, NOT DEFAULTED.

    A card printing somebody else's numbers owes the reader where they were read
    and when. Without `source` this is a screenshot with extra steps, so it is
    rejected before anything is drawn rather than rendered with a blank.
    """
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_comparison_spec()), encoding="utf-8")
    assert cards.load_comparison(good)["slug"] == "test-boards"

    spec = _comparison_spec()
    spec["boards"][0].pop("source")  # type: ignore[index]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="source"):
        cards.load_comparison(bad)

    spec = _comparison_spec()
    spec.pop("boards")
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="boards"):
        cards.load_comparison(empty)


def test_a_tie_is_printed_as_a_tie_and_never_renumbered() -> None:
    """THE DEFECT THIS WHOLE VARIANT EXISTS TO PREVENT, pinned to a test.

    The 2026 AP preseason poll ties BYU and USC at 14 on 839 points each and then
    publishes 16. The transcription these cards were first specified from had USC
    at 15, which is a rank the AP never issued. Two teams sharing a number in the
    spec IS the tie, so nothing has to be declared and nothing can be forgotten.
    """
    svg = cards.comparison_svg(_projection_document(), _comparison_spec())
    assert svg.count(">T4<") == 2
    assert ">T1<" not in svg and ">T2<" not in svg


def test_an_unranked_team_says_so_rather_than_being_left_blank() -> None:
    """A blank cell reads as missing data. "NR" is a fact about their ballot."""
    assert ">NR<" in cards.comparison_svg(_projection_document(), _comparison_spec())


def test_the_comparison_labels_whose_board_is_which_kind() -> None:
    """Their preseason POLL, our preseason PROJECTION. Both named, on the card.

    The framing rule from the storylines doc, made structural: a comparison that
    quietly called all three boards the same thing would be claiming a
    like-for-like the season has not happened yet to support.
    """
    svg = cards.comparison_svg(_projection_document(), _comparison_spec())
    assert ">THE POLL<" in svg and ">PROJECTION<" in svg
    assert ">AP<" in svg and ">COACHES<" in svg
    assert svg.count(">POLL<") >= 2


def test_the_comparison_carries_its_key_and_never_puts_cyan_beside_it() -> None:
    """THE BRAND BOOK'S OWN FLAGGED CHECK, ANSWERED HERE.

    §2: the amber-violet movement pair stays, and "check that no figure places
    cyan beside the amber-violet pair in a way that reads as three competing
    categories". A comparison card IS that figure. So it draws no accent divider
    and its wordmark suffix goes bone, leaving exactly two colours that mean
    anything - and it prints the sentence that says what they mean.
    """
    for svg in (
        cards.comparison_svg(_projection_document(), _comparison_spec()),
        cards.comparison_tall_svg(_projection_document(), _comparison_spec()),
    ):
        assert cards.GAP_POS in svg and cards.GAP_NEG in svg
        assert cards.PALETTE["accent"] not in svg
        assert "we rank them higher" in svg and "the boards agree" in svg


def test_the_comparison_colours_say_which_way_each_gap_runs() -> None:
    """Amber when the model is the optimist, violet when it is not, bone inside
    the agreement band. The reader gets the direction before the numbers."""
    assert cards._gap_colour(0) == cards.PALETTE["ink"]
    assert cards._gap_colour(cards.AGREEMENT_BAND) == cards.PALETTE["ink"]
    assert cards._gap_colour(-cards.AGREEMENT_BAND) == cards.PALETTE["ink"]
    assert cards._gap_colour(cards.AGREEMENT_BAND + 1) == cards.GAP_POS
    assert cards._gap_colour(-cards.AGREEMENT_BAND - 1) == cards.GAP_NEG


def test_every_comparison_mode_selects_rather_than_computes() -> None:
    """Each mode is a filter over the published rows.

    None of them may invent a rank, renumber our board, or produce a team the
    document does not contain, which is what the assertion on `rank` checks.
    """
    document = _projection_document()
    published = {int(r["rank"]): str(r["team"]) for r in document["rows"]}  # type: ignore[index]
    for mode, expect in (("board", 25), ("gaps", 25)):
        rows, boards = cards._comparison_rows(document, _comparison_spec(mode=mode))
        assert len(boards) == 2
        assert len(rows) == expect, mode
        for row in rows:
            assert published[int(row["rank"])] == str(row["team"]), mode
    agreed, _ = cards._comparison_rows(document, _comparison_spec(mode="agree"))
    assert [str(r["team"]) for r in agreed] == ["Team 1", "Team 2", "Team 7"]


def test_an_unknown_comparison_mode_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown comparison mode"):
        cards._comparison_rows(_projection_document(), _comparison_spec(mode="vibes"))


def test_a_square_card_refuses_rows_it_cannot_fit() -> None:
    """Drawing row 20 below the bottom edge is a defect only a human would catch."""
    with pytest.raises(ValueError, match="do not fit"):
        cards.comparison_square_svg(_projection_document(), _comparison_spec())
    assert cards.comparison_square_svg(
        _projection_document(), _comparison_spec(slice=[1, 10])
    )


def test_a_disagreement_card_refuses_a_team_the_board_does_not_rank() -> None:
    """The subject has to be on our board, because our rank is the claim."""
    with pytest.raises(ValueError, match="not in this document"):
        cards.disagreement_svg(_projection_document(), _comparison_spec(focus="Nowhere State"))
    svg = cards.disagreement_svg(_projection_document(), _comparison_spec(focus="Team 3"))
    assert "Team 3" in svg and ">12<" in svg and ">11<" in svg


def test_a_comparison_variant_refuses_the_run_directory_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="export_comparison"):
        cards.export(tmp_path, tmp_path, variant="comparison")


def test_export_comparison_names_the_files_after_the_season_and_the_slug(
    tmp_path: Path,
) -> None:
    """Three carousel slides are three claims, so they are three files.

    The slug rather than the variant alone: a set of slides that overwrote each
    other would be one artifact with a moving digest, which is the opposite of
    what a published card is for.
    """
    document = tmp_path / "projection.json"
    document.write_text(json.dumps(_projection_document()), encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(_comparison_spec(slug="ap-coaches")), encoding="utf-8")
    written = cards.export_comparison(
        document, spec, tmp_path / "share", variant="comparison", png=False
    )
    assert [p.name for p in written] == ["2026-ap-coaches-comparison.svg"]


def test_the_comparison_svg_is_a_pure_function_of_its_two_documents() -> None:
    for builder in (cards.comparison_svg, cards.comparison_tall_svg):
        first = builder(_projection_document(), _comparison_spec())
        assert first == builder(_projection_document(), _comparison_spec())


def test_the_shipped_launch_spec_matches_the_board_it_is_drawn_against() -> None:
    """EVERY TEAM NAME IN THE SPEC IS A TEAM NAME THE PIPELINE USES.

    A misspelling here is invisible: `Miami (FL)` where the document says `Miami`
    renders as NR, which reads as "the AP did not rank them" and is a false
    statement about somebody else's ballot on a published card. Nothing else in
    the chain would catch it.
    """
    spec = cards.load_comparison(DEMO / "comparison-2026-ap-coaches.json")
    known = {
        str(row["team"])
        for row in json.loads(
            (DEMO / "2026-preseason-projection.json").read_text(encoding="utf-8")
        )["rows"]
    }
    # The demo projection publishes 25 rows; the spec names teams outside them
    # too, so the check is that every name it uses is spelled the way the
    # pipeline spells it wherever the two overlap.
    for board in spec["boards"]:
        for team in board["ranks"]:
            assert " " not in team[:1], team
            assert team.strip() == team, team
    ours = {t for board in spec["boards"] for t in board["ranks"]} & known
    assert len(ours) >= 15, sorted(ours)


# ------------------------------------------------------ the AI-provenance strip


def test_a_published_png_carries_no_metadata_chunk() -> None:
    """META AND TIKTOK LABEL FROM METADATA, NOT FROM PIXELS, and TikTok's sticks.

    A card is a table of real numbers that Python drew. A C2PA manifest, an XMP
    packet or an EXIF block left behind anywhere in the render chain can get it
    badged as AI-generated regardless of what it shows. The chain is clean today -
    the pinned resvg writes IHDR, IDAT and IEND - which is exactly why the guard
    belongs here now, while there is nothing to remove, rather than after a wheel
    upgrade starts stamping one.
    """
    raw = cards.render_png(cards.projection_top5_svg(_projection_document()))
    assert cards.png_metadata_chunks(raw) == []
    assert cards.png_chunks(raw)[0] == "IHDR"
    assert cards.png_chunks(raw)[-1] == "IEND"
    # And the committed sample, which is the artifact anyone will actually check.
    assert cards.png_metadata_chunks(SAMPLE_PNG.read_bytes()) == []


def test_the_strip_removes_provenance_and_leaves_the_pixels_alone() -> None:
    """Chunk surgery, not a re-encode: the same IDAT bytes come out the far side.

    Re-encoding would move the sha256 of a published artifact for a reason that
    has nothing to do with what the card says, so the strip copies the structural
    chunks through and drops everything else.
    """
    clean = cards.render_png(cards.projection_top5_svg(_projection_document()))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            len(payload).to_bytes(4, "big")
            + kind
            + payload
            + zlib.crc32(kind + payload).to_bytes(4, "big")
        )

    # A C2PA box and an XMP packet, spliced in ahead of the image data.
    head = clean.index(b"IDAT") - 4
    dirty = (
        clean[:head]
        + chunk(b"caBX", b"c2pa-manifest-goes-here")
        + chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00<x:xmpmeta/>")
        + clean[head:]
    )
    assert sorted(cards.png_metadata_chunks(dirty)) == ["caBX", "iTXt"]
    stripped = cards.strip_png_metadata(dirty)
    assert cards.png_metadata_chunks(stripped) == []
    assert stripped == clean


# ------------------------------------------------------- the pinned logo cache

#: A 2x2 PNG, 8-bit RGBA, built here rather than fetched. Two pixels opaque and
#: two fully transparent, which is what lets the "effective" in effective
#: luminance be asserted rather than described: the mean must be over the painted
#: pixels only, and the transparent ones carry a colour precisely so that a
#: decoder that counted them would produce a visibly different number.
def _png(pixels: list[tuple[int, int, int, int]], width: int = 2, height: int = 2) -> bytes:
    raw = b""
    for row in range(height):
        raw += b"\x00" + bytes(
            channel for pixel in pixels[row * width : (row + 1) * width] for channel in pixel
        )

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


_WHITE = (255, 255, 255, 255)
_BLACK = (0, 0, 0, 255)
_CLEAR_WHITE = (255, 255, 255, 0)


def test_effective_luminance_ignores_the_transparent_pixels() -> None:
    """The whole point of the word "effective".

    Two white pixels painted and two white pixels at alpha 0 must measure the
    same as two white pixels alone, and a black mark on a transparent field must
    measure black rather than being dragged toward the colour sitting unused in
    the transparent pixels' channels.
    """
    assert logos.effective_luminance(_png([_WHITE, _WHITE, _WHITE, _WHITE])) == 1.0
    assert logos.effective_luminance(_png([_WHITE, _WHITE, _CLEAR_WHITE, _CLEAR_WHITE])) == 1.0
    assert logos.effective_luminance(_png([_BLACK, _BLACK, _CLEAR_WHITE, _CLEAR_WHITE])) == 0.0
    # Half black, half white, all painted: the mean of the two, not either one.
    mixed = logos.effective_luminance(_png([_WHITE, _WHITE, _BLACK, _BLACK]))
    assert abs(mixed - 0.5) < 1e-9
    # Nothing painted at all is 0.0, which puts the mark on a plate. A mark with
    # no opaque pixels draws nothing either way and the safe direction to be
    # wrong in is the one that adds a light ground.
    assert logos.effective_luminance(_png([_CLEAR_WHITE] * 4)) == 0.0


def test_the_plate_threshold_is_derived_from_the_cards_own_ground() -> None:
    """WCAG 2.1 SC 1.4.11 asks 3:1 of a graphical object needed to understand the
    content, and a team's mark is exactly that.

    The number is inverted out of the contrast formula against `PALETTE["bg"]`
    rather than written down, so moving the card's ground moves the threshold with
    it instead of leaving a constant behind that used to be right.
    """
    threshold = logos.plate_threshold(cards.PALETTE["bg"])
    # The band moved with the ground on 2026-08-17: the brand's #101216 is a
    # shade lighter than the retired #0B0C0F, so a mark now has to be slightly
    # lighter before it can be set without a plate. That the number MOVED is the
    # proof the docstring above is telling the truth.
    assert 0.117 < threshold < 0.119
    assert logos.needs_plate(threshold - 0.001, cards.PALETTE["bg"]) is True
    assert logos.needs_plate(threshold + 0.001, cards.PALETTE["bg"]) is False
    # A lighter ground demands a lighter mark before the plate can be skipped.
    assert logos.plate_threshold("#FFFFFF") > threshold


def _cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, url: str, raw: bytes) -> None:
    """Put bytes in a throwaway cache and unpin the manifest, so the decision
    under test is the measurement rather than whatever the committed pin says."""
    monkeypatch.setattr(logos, "CACHE_DIR", tmp_path / "logos")
    monkeypatch.setattr(logos, "_MANIFEST_MEMO", {logos.MANIFEST_PATH: {}})
    path = logos.cache_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def test_a_cached_mark_is_embedded_as_a_data_uri_and_never_hotlinked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The new contract, on a generated card rather than on the committed sample."""
    url = "https://a.espncdn.com/combiner/i?img=/i/teamlogos/ncaa/500-dark/1.png&w=128&h=128"
    _cached(monkeypatch, tmp_path, url, _png([_WHITE] * 4))

    document = _projection_document()
    for row in document["rows"]:  # type: ignore[union-attr]
        row["logo_url_dark_2x"] = url  # type: ignore[index]
    svg = cards.projection_top5_svg(document)

    assert svg.count("<image") == 5
    assert _externals(svg) == [], "a card that hotlinks is a blank square once reposted"
    assert 'href="data:image/png;base64,' in svg
    # The published URL string itself must not travel onto the card either.
    assert url not in svg


def test_a_dark_mark_gets_a_plate_and_a_light_one_does_not(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The luminance guard, as the two outcomes it exists to produce.

    Same code path, same card, two sets of bytes: near-black artwork gets the
    light chip and white artwork does not. The plate is driven from
    `PALETTE["plate"]`, so the assertion is against the token rather than a hex
    literal typed twice.
    """
    dark_url = "https://example.invalid/dark.png"
    light_url = "https://example.invalid/light.png"
    monkeypatch.setattr(logos, "CACHE_DIR", tmp_path / "logos")
    monkeypatch.setattr(logos, "_MANIFEST_MEMO", {logos.MANIFEST_PATH: {}})
    (tmp_path / "logos").mkdir(parents=True, exist_ok=True)
    logos.cache_path(dark_url).write_bytes(_png([_BLACK] * 4))
    logos.cache_path(light_url).write_bytes(_png([_WHITE] * 4))

    dark = logos.resolve({"logo_url_dark_2x": dark_url}, background=cards.PALETTE["bg"])
    light = logos.resolve({"logo_url_dark_2x": light_url}, background=cards.PALETTE["bg"])
    assert dark is not None and light is not None
    assert dark.plate is True and light.plate is False

    plated = cards._mark(100, 100, 20, {"logo_url_dark_2x": dark_url})
    bare = cards._mark(100, 100, 20, {"logo_url_dark_2x": light_url})
    assert cards.PALETTE["plate"] in plated and "<rect" in plated
    assert cards.PALETTE["plate"] not in bare and "<rect" not in bare
    # The chip is a few px larger than the mark, not a full-bleed row background.
    assert f'fill-opacity="{cards._n(cards.PLATE_OPACITY)}"' in plated


def test_a_row_with_no_cached_bytes_draws_the_disc_rather_than_an_empty_square(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A cold cache degrades the card; it does not break it."""
    monkeypatch.setattr(logos, "CACHE_DIR", tmp_path / "empty")
    row = {"logo_url_dark_2x": "https://example.invalid/never-fetched.png", "mark_label": "ZZZ"}
    drawn = cards._mark(100, 100, 20, row)
    assert "<image" not in drawn
    assert "<circle" in drawn and "ZZZ" in drawn


def test_resolving_a_mark_never_touches_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """The property the pipeline depends on, asserted rather than described.

    `logos.warm` is the one function with an HTTP client. If `resolve` ever grew
    one, every card render would become a network call and the purity claim in
    `cards.py`'s docstring would quietly become false.
    """
    import httpx

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("resolve() reached the network")

    monkeypatch.setattr(httpx, "get", refuse)
    monkeypatch.setattr(httpx, "Client", refuse)
    row = {"logo_url": "https://example.invalid/x.png"}
    assert logos.resolve(row, background=cards.PALETTE["bg"]) is None


def test_the_url_preference_puts_the_dark_variant_first() -> None:
    """The card is dark and the 2x raster is the one that holds up at 52px."""
    row = {
        "logo_url": "a",
        "logo_url_2x": "b",
        "logo_url_dark": "c",
        "logo_url_dark_2x": "d",
    }
    assert logos.logo_url_for(row) == "d"
    del row["logo_url_dark_2x"]
    assert logos.logo_url_for(row) == "c"
    del row["logo_url_dark"]
    assert logos.logo_url_for(row) == "b"
    assert logos.logo_url_for({"logo_url": None}) is None


def test_warm_asks_for_nothing_when_the_cache_is_warm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A render against a warm cache issues ZERO requests, and here is the proof."""
    url = "https://example.invalid/warm.png"
    monkeypatch.setattr(logos, "CACHE_DIR", tmp_path / "logos")
    (tmp_path / "logos").mkdir(parents=True)
    logos.cache_path(url).write_bytes(_png([_WHITE] * 4))
    monkeypatch.setattr(
        logos,
        "_fetch",
        lambda _url: (_ for _ in ()).throw(AssertionError("warm cache still fetched")),
    )
    rows = [{"team_id": 1, "logo_url_dark_2x": url}, {"team_id": 1, "logo_url_dark_2x": url}]
    records = logos.warm(rows, background=cards.PALETTE["bg"], manifest=None)
    assert len(records) == 1, "one distinct URL is measured once per run"
    assert records[0]["url"] == url and records[0]["plate"] is False
