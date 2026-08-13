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
    with pytest.raises(ValueError, match="unknown card variant"):
        cards.export(tmp_path, tmp_path, variant="top10")


def test_word_wrap_never_exceeds_its_budget_and_marks_truncation() -> None:
    text = "one two three four five six seven eight nine ten eleven twelve"
    lines = cards._wrap(text, 20, 2)
    assert len(lines) == 2
    assert all(len(line) <= 20 for line in lines)
    assert lines[-1].endswith("…")
    assert cards._wrap(text, 200, 3) == [text]
