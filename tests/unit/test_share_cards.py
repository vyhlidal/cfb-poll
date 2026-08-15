"""The share card, and the CI guard report 06 §8.4 asked for.

Report 06 §8.4, verbatim on what to enforce:

    - no file matching *.png|*.svg|*.webp under site/, public/, or src/ that is
      not in a small explicitly allow-listed set (our own icons, the wordmark)
    - no HTTP fetch of a.espncdn.com anywhere in the Python package
    - out/ share-card PNGs are rendered from SVG containing no <image> element

    That third check is the one that catches the tempting mistake — someone
    adding a logo to the share card "just for the top 3."

All three are here, and the tree check is widened from "under site/, public/,
src/" to the WHOLE tracked tree, because a logo committed to `docs/` would be
exactly as much of a copy as one committed to `src/`. The allow-list holds the
cards this project generates itself and nothing else.

The rest of the module is about the card as an artifact: it is 1200x628, its SVG
is a pure function of the published documents, and every number on it is read out
of those documents rather than recomputed.
"""

from __future__ import annotations

import ast
import re
import struct
import subprocess
from pathlib import Path

import pytest

from cfbpoll.config import REPO_ROOT
from cfbpoll.publish import cards

DEMO = REPO_ROOT / "demo"
SAMPLE_SVG = DEMO / "2023-w10-connectivity.svg"
SAMPLE_PNG = DEMO / "2023-w10-connectivity.png"

#: Every image file the tracked tree is allowed to hold, and why. A logo would
#: have to be added HERE to pass, which is the point: the guard converts "someone
#: quietly committed a mark" into "someone edited an allow-list in a test file
#: whose docstring says not to".
ALLOWED_IMAGES: dict[str, str] = {
    "demo/2023-w10-connectivity.svg": "our own generated card; no <image>, no external host",
    "demo/2023-w10-connectivity.png": "the rendered sample of the same card",
}

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif", ".ico"}

#: Hosts that serve school marks. Constructing one of these URLs as a string is
#: fine and is what `publish/serving.py` does; FETCHING one from Python would make
#: a copy on our infrastructure and forfeit the whole report 06 §2.4 argument.
_LOGO_HOSTS = ("a.espncdn.com", "cdn.collegefootballdata.com", "espncdn", "ncaa.com")
_FETCH_CALLS = ("httpx.get", "httpx.Client", "requests.get", "urlopen", "urlretrieve")


#: The SVG namespace URI. It is an identifier, not a fetch — no renderer resolves
#: it — and it is the one and only `http://` a card SVG is allowed to contain.
SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def _code_without_docstrings(path: Path) -> str:
    """A module's CODE, with every docstring removed.

    Necessary because this project documents its rules in the docstrings of the
    modules that obey them: `publish/cards.py` explains at length that it emits no
    `<image>` element, and a naive substring search over the file would find that
    sentence and fail. Parsing means the guard reads what the module DOES.
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
    found = {p for p in _tracked() if Path(p).suffix.lower() in _IMAGE_SUFFIXES}
    assert found == set(ALLOWED_IMAGES), sorted(found ^ set(ALLOWED_IMAGES))


def test_no_card_svg_carries_an_image_element_or_an_external_host() -> None:
    """The tempting mistake, made impossible to land quietly."""
    for name in ALLOWED_IMAGES:
        if not name.endswith(".svg"):
            continue
        svg = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "<image" not in svg, name
        assert "xlink:href" not in svg, name
        body = svg.replace(SVG_NAMESPACE, "")
        externals = re.findall(r"https?://[^\"'\s>]+", body)
        assert externals == [], (name, externals)
        assert "@import" not in svg and "url(http" not in svg, name


def test_the_generated_card_is_logo_free_by_construction() -> None:
    """Not just the committed sample: the renderer itself cannot emit one."""
    source = _code_without_docstrings(REPO_ROOT / "src" / "cfbpoll" / "publish" / "cards.py")
    assert "<image" not in source
    for host in _LOGO_HOSTS:
        assert host not in source, host
    for call in _FETCH_CALLS:
        assert call not in source, call


def test_no_logo_host_is_ever_fetched_from_the_python_package() -> None:
    """Report 06 §8.4 rule 2. Building the URL is fine; fetching it is not.

    `serving.py` and `data/team-colors.csv` both hold logo URLs, and that is the
    whole design (report 06 §6 rule 1: never possess the bytes). What must not
    exist anywhere in the package is a line that turns one of those strings into
    a response body.
    """
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        for line in _code_without_docstrings(path).splitlines():
            if any(host in line for host in _LOGO_HOSTS):
                assert not any(call in line for call in _FETCH_CALLS), (path, line)


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


def test_the_card_carries_its_constants_footer() -> None:
    """Report 05 §6.2: "the constants footer is on the card... that line is the
    signature and it should never be dropped for space"."""
    svg = SAMPLE_SVG.read_text(encoding="utf-8")
    assert "q_ref" in svg
    assert "sb.unleashepic.com/cfb-poll" in svg
    assert "THE POLL · 2023 · WEEK 10" in svg


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


def test_every_variant_has_a_builder_and_a_declared_canvas() -> None:
    """VARIANTS and BUILDERS cannot drift. The CLI's help reads one of them."""
    assert set(cards.VARIANTS) == set(cards.BUILDERS)
    for name, (_builder, width, height) in cards.BUILDERS.items():
        assert width == cards.CARD_WIDTH, name
        assert height in (cards.CARD_HEIGHT, cards.TALL_HEIGHT), name


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


def test_the_accent_is_never_a_hairline_or_a_border() -> None:
    """Gold is a filled slab or the odds numeral. Never a stroke.

    The one exception is the playoff rule under rank 4, which is a deliberate
    2px accent line and the card's loudest sports signal.
    """
    assert cards.PALETTE["accent"] == "#F0B429"
    assert cards.PALETTE["brand_ink"] == "#0B0C0F"
    # The rail is evidence and is deliberately not the accent.
    assert cards.PALETTE["rail_band"] != cards.PALETTE["accent"]


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
