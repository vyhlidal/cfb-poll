"""The pinned logo cache: the one non-hermetic input a share card has.

THE OWNER OVERTURNED THE NO-LOGO POLICY. Verbatim: "I don't care about the logo
caution, every social post everywhere uses college logos, we're not making
T-shirts: use the logos." What follows is the machinery that makes that decision
safe to ship rather than merely possible.

The trademark reasoning is restated rather than deleted, because it is still the
thing that makes this defensible: a school's mark is drawn UNALTERED, at the size
a mark is drawn at, to IDENTIFY the team the row is about and for no other
purpose. No merchandise, no implied endorsement, no recolouring, no clipping into
a shape the school does not use. The site carries the disclaimer and the licence
footer, and the card carries a link back to it. What changed is the risk
assessment, not the facts, and the owner owns that call.

WHY A CACHE AND NOT A HOTLINK. A card is a PNG in somebody else's timeline. An
`<image href="https://...">` in the SVG would rasterise to a blank square the
moment the host blocked the referrer or moved the path, and the SVG itself is a
published artifact that a reader may open years from now. So the bytes are
fetched once, hashed, and embedded as a `data:` URI. A published card is
self-contained or it is not published.

THE HERMETICITY CLAIM, STATED PRECISELY, because it is narrower than it was:

  - THE SVG IS A PURE FUNCTION OF (the published documents + the pinned logo
    cache). Given the same documents and the same cache directory, two renders on
    two machines produce the same bytes. `resolve` NEVER touches the network.
  - THE NETWORK FETCH IS THE ONE NON-HERMETIC INPUT, and it happens in exactly
    one function, `warm`, which the pipeline calls before it renders. A render
    against a warm cache issues zero requests. That is a property, not a hope:
    `resolve` has no HTTP client to reach for.
  - `data/logo-cache-manifest.json` IS WHAT MAKES THE NON-HERMETIC INPUT
    VERIFIABLE. Every URL ever fetched is recorded with the sha256 of the bytes,
    their length, and the measured luminance. A reviewer can re-fetch and diff; a
    CI job with a warm cache can check the bytes against the manifest without a
    network of its own. Upstream can change what it serves at a URL and the
    manifest is where that becomes visible instead of silently changing a card.

THE LUMINANCE MEASUREMENT AND WHY IT IS "EFFECTIVE". The card ground is
`PALETTE["bg"]`, which is nearly black, and a mark that is itself nearly black
disappears on it. Some schools have no genuine dark-mode variant at all: the host
serves a byte-identical file for the `-dark` path, so asking for the dark variant
is not a guarantee of getting one. So the decision is made from the pixels rather
than from the URL: decode the PNG and take the mean WCAG relative luminance over
ONLY the pixels that are actually painted (alpha above a floor). Averaging the
transparent pixels too would drag every mark's number toward whatever the decoder
happens to leave in the colour channels of a fully transparent pixel, which is
undefined in practice and is not what a reader sees.
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cfbpoll.config import REPO_ROOT

__all__ = [
    "ALPHA_FLOOR",
    "CACHE_DIR",
    "MANIFEST_PATH",
    "MIN_CONTRAST",
    "LogoMark",
    "cache_path",
    "effective_luminance",
    "logo_url_for",
    "needs_plate",
    "plate_threshold",
    "read_manifest",
    "resolve",
    "warm",
]

#: Where fetched bytes live. GITIGNORED, and that is the point: these are
#: somebody else's files and this repository does not distribute them. `.cache/`
#: is already ignored wholesale, and `.gitignore` names this path explicitly
#: anyway so that a reader grepping for "logos" finds the rule rather than having
#: to infer it from a parent directory.
CACHE_DIR = REPO_ROOT / ".cache" / "logos"

#: The pin. Committed, unlike the bytes it describes.
MANIFEST_PATH = REPO_ROOT / "data" / "logo-cache-manifest.json"

#: A pixel below this alpha is not painted and does not vote on the mean. 32/255
#: is about 12%: high enough to drop antialiasing fringes, which are the school's
#: colour blended toward nothing and would bias the mean downward on every mark
#: with a soft edge; low enough to keep genuinely translucent artwork.
ALPHA_FLOOR = 32

#: WCAG 2.1 SC 1.4.11 (Non-text Contrast) asks 3:1 of "graphical objects required
#: to understand the content". The mark IS the identification of the row, so that
#: is the right clause and 3:1 is the right number: it is a published minimum a
#: reviewer can check rather than a value somebody liked the look of.
MIN_CONTRAST = 3.0

#: Fetch politeness. A normal identifying User-Agent, a real timeout, and two
#: retries; each distinct URL is requested at most once per run because `warm`
#: dedupes before it asks for anything.
USER_AGENT = "cfb-poll/0.0.1 (+https://github.com/vyhlidal/cfb-poll)"
TIMEOUT_SECONDS = 20.0
RETRIES = 2

#: The order the four published URL fields are tried in. THE CARD IS DARK, so the
#: dark variant comes first, and the 2x size comes before the 1x within each
#: theme: the mark is drawn at up to ~46px on the top-five card and a 64px source
#: would be visibly soft there. Never construct one of these strings here; the
#: fields are published on the row and this module only chooses among them.
URL_PREFERENCE: tuple[str, ...] = (
    "logo_url_dark_2x",
    "logo_url_dark",
    "logo_url_2x",
    "logo_url",
)


# ------------------------------------------------------------------ colour maths

#: sRGB byte -> linear, precomputed. 256 entries, so the decode loop does a table
#: lookup instead of a pow() per channel per pixel.
_LINEAR = tuple(
    (v / 255.0 / 12.92) if (v / 255.0) <= 0.04045 else (((v / 255.0) + 0.055) / 1.055) ** 2.4
    for v in range(256)
)


def _relative_luminance(r: int, g: int, b: int) -> float:
    """WCAG relative luminance of one 8-bit sRGB triple."""
    return 0.2126 * _LINEAR[r] + 0.7152 * _LINEAR[g] + 0.0722 * _LINEAR[b]


def _luminance_of_hex(colour: str) -> float:
    text = colour.lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    return _relative_luminance(*(int(text[i : i + 2], 16) for i in (0, 2, 4)))


def plate_threshold(background: str) -> float:
    """The luminance a mark must clear to sit unaided on `background`.

    Inverts the WCAG contrast formula `(L1 + 0.05) / (L2 + 0.05)` for L1 at
    `MIN_CONTRAST`. Derived from the palette rather than written down as a
    constant, so moving the card's ground moves the threshold with it instead of
    leaving a number behind that used to be right.

    On the current `#0B0C0F` ground this comes out at about 0.111.
    """
    return MIN_CONTRAST * (_luminance_of_hex(background) + 0.05) - 0.05


def needs_plate(luminance: float, background: str) -> bool:
    """True when the mark is too dark to be seen on the card's own ground."""
    return luminance < plate_threshold(background)


# --------------------------------------------------------------------- PNG decode

#: A minimal, dependency-free PNG reader. Pillow is not a dependency and adding
#: one for a mean over 16k pixels would be a poor trade; numpy is a dependency but
#: the filter pass is inherently sequential per scanline and vectorising it buys
#: nothing at this size. zlib and struct are the standard library, the arithmetic
#: is integer, and the result is identical on every machine, which is the property
#: that actually matters here.


def _idat(raw: bytes) -> tuple[dict[str, Any], bytes, bytes | None, bytes | None]:
    """Walk the chunk stream. Returns (header, IDAT bytes, PLTE, tRNS)."""
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG: bad signature")
    pos, header, idat, plte, trns = 8, {}, bytearray(), None, None
    while pos + 8 <= len(raw):
        length, kind = struct.unpack(">I4s", raw[pos : pos + 8])
        body = raw[pos + 8 : pos + 8 + length]
        pos += 12 + length  # 4 length + 4 type + body + 4 CRC
        if kind == b"IHDR":
            width, height, depth, colour, compression, filt, interlace = struct.unpack(
                ">IIBBBBB", body
            )
            header = {
                "width": width,
                "height": height,
                "depth": depth,
                "colour": colour,
                "compression": compression,
                "filter": filt,
                "interlace": interlace,
            }
        elif kind == b"IDAT":
            idat += body
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IEND":
            break
    if not header:
        raise ValueError("PNG has no IHDR")
    return header, bytes(idat), plte, trns


def _unfilter(data: bytes, width: int, height: int, depth: int, channels: int) -> list[bytes]:
    """Undo the per-scanline filter. PNG spec §9, the five filter types."""
    bits = depth * channels
    step = max(1, bits // 8)
    stride = (width * bits + 7) // 8
    rows: list[bytes] = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        kind = data[pos]
        pos += 1
        line = bytearray(data[pos : pos + stride])
        pos += stride
        if kind == 1:
            for i in range(step, stride):
                line[i] = (line[i] + line[i - step]) & 0xFF
        elif kind == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif kind == 3:
            for i in range(stride):
                left = line[i - step] if i >= step else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(stride):
                a = line[i - step] if i >= step else 0
                b = prev[i]
                c = prev[i - step] if i >= step else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        elif kind != 0:
            raise ValueError(f"unknown PNG filter type {kind}")
        rows.append(bytes(line))
        prev = line
    return rows


def _samples(row: bytes, width: int, depth: int, channels: int) -> list[int]:
    """One scanline as a flat list of 8-bit samples, `channels` per pixel.

    16-bit sources are reduced to their high byte. That loses the low byte of
    precision on a measurement whose threshold sits at 0.111 of a 0..1 range,
    which is nothing, and it keeps one code path for every depth this ever meets.
    """
    if depth == 8:
        return list(row[: width * channels])
    if depth == 16:
        return list(row[: width * channels * 2 : 2])
    if depth in (1, 2, 4):
        out: list[int] = []
        per_byte = 8 // depth
        mask = (1 << depth) - 1
        for byte in row:
            for slot in range(per_byte):
                out.append((byte >> (8 - depth * (slot + 1))) & mask)
        return out[: width * channels]
    raise ValueError(f"unsupported PNG bit depth {depth}")


def effective_luminance(raw: bytes, *, alpha_floor: int = ALPHA_FLOOR) -> float:
    """Mean WCAG relative luminance over the PAINTED pixels of a PNG.

    "Effective" is the whole idea: a mark is mostly transparent, and averaging the
    empty space would measure the file rather than the thing a reader sees. Only
    pixels with alpha above `alpha_floor` vote.

    Returns 0.0 for an image with nothing painted in it, which puts it on the
    plate. A mark with no opaque pixels draws nothing either way, and the safe
    direction to be wrong in is the one that adds a light ground.
    """
    header, idat, plte, trns = _idat(raw)
    if header["interlace"]:
        raise ValueError("interlaced PNGs are not supported by this decoder")
    depth, colour = int(header["depth"]), int(header["colour"])
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
    if channels is None:
        raise ValueError(f"unknown PNG colour type {colour}")

    width, height = int(header["width"]), int(header["height"])
    rows = _unfilter(zlib.decompress(idat), width, height, depth, channels)

    # tRNS for the non-palette colour types names ONE fully transparent sample
    # value rather than an alpha channel. Reduced to 8 bits to match `_samples`.
    keyed: tuple[int, ...] | None = None
    if trns and colour in (0, 2):
        values = struct.unpack(f">{len(trns) // 2}H", trns)
        keyed = tuple(v >> 8 if depth == 16 else v for v in values)

    scale = 255 // ((1 << depth) - 1) if colour == 3 and depth < 8 else 1
    total, count = 0.0, 0
    for row in rows:
        flat = _samples(row, width, depth, channels)
        for i in range(0, len(flat), channels):
            if colour == 6:
                r, g, b, a = flat[i], flat[i + 1], flat[i + 2], flat[i + 3]
            elif colour == 2:
                r, g, b = flat[i], flat[i + 1], flat[i + 2]
                a = 0 if keyed is not None and (r, g, b) == keyed else 255
            elif colour == 4:
                r = g = b = flat[i]
                a = flat[i + 1]
            elif colour == 0:
                r = g = b = flat[i] * (scale if depth < 8 else 1)
                a = 0 if keyed is not None and (flat[i],) == keyed else 255
            else:  # palette
                index = flat[i]
                if plte is None or index * 3 + 2 >= len(plte):
                    continue
                r, g, b = plte[index * 3], plte[index * 3 + 1], plte[index * 3 + 2]
                a = trns[index] if trns is not None and index < len(trns) else 255
            if a <= alpha_floor:
                continue
            total += _relative_luminance(r, g, b)
            count += 1
    return total / count if count else 0.0


# ------------------------------------------------------------------- the cache


def logo_url_for(row: dict[str, Any]) -> str | None:
    """The URL this row's mark should be drawn from, or None.

    NEVER CONSTRUCTS A URL. The four fields are published on every poll row and
    every projection row by `publish/serving.py` and `projection/publish.py`, and
    a renderer that built its own string would be a second place for the host's
    path scheme to live. None means the row published no logo, which is what
    `[display].logos = false` produces, and the caller falls back to the
    generated mark.
    """
    for field in URL_PREFERENCE:
        value = row.get(field)
        if value:
            return str(value)
    return None


def cache_path(url: str) -> Path:
    """Content-addressed by URL. Same URL, same file, on every machine.

    The URL rather than the bytes, because the lookup has to happen BEFORE the
    bytes exist. The bytes get their own hash in the manifest, which is where
    "did upstream change what it serves here" becomes answerable.
    """
    return CACHE_DIR / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.png"


@dataclass(frozen=True)
class LogoMark:
    """One school's mark, resolved from the cache and measured.

    `data_uri` is what goes in the SVG. `plate` is the decision, made once here
    and recorded in the manifest, so the renderer does not re-measure and CI does
    not need the pixels to know what the card did.
    """

    url: str
    sha256: str
    length: int
    luminance: float
    plate: bool
    data_uri: str


def _measure(raw: bytes, background: str) -> tuple[float, bool]:
    luminance = round(effective_luminance(raw), 6)
    return luminance, needs_plate(luminance, background)


def resolve(row: dict[str, Any], *, background: str) -> LogoMark | None:
    """The row's mark from the CACHE ONLY. Never touches the network.

    Returns None when the row publishes no logo URL or the cache has no bytes for
    it, and the caller draws the generated mark instead. That fallback is what
    keeps the renderer usable in a fork with a cold cache and no network, and it
    is why this function has no HTTP client to reach for: "a render with a warm
    cache issues zero requests" is a property of the code rather than a promise.

    THE PLATE DECISION COMES FROM THE MANIFEST WHEN THE MANIFEST STILL DESCRIBES
    THESE BYTES. That is the point of pinning it: CI does not re-derive a
    published decision from pixels, it checks that the pixels are the ones the
    decision was made from. The sha256 has to match and the background has to
    match; if either has moved, the pin no longer describes this card and the
    mark is measured again rather than trusted.
    """
    url = logo_url_for(row)
    if not url:
        return None
    path = cache_path(url)
    if not path.is_file():
        return None
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()

    pinned = read_manifest().get(url)
    if pinned and pinned.get("sha256") == digest and pinned.get("background") == background:
        luminance, plate = float(pinned["luminance"]), bool(pinned["plate"])
    else:
        try:
            luminance, plate = _measure(raw, background)
        except (ValueError, zlib.error):
            # A cached file that will not decode is a cached file we should not draw.
            return None
    return LogoMark(
        url=url,
        sha256=digest,
        length=len(raw),
        luminance=luminance,
        plate=plate,
        data_uri="data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
    )


#: Read once per process. The manifest is consulted for every row of every card
#: and re-reading a JSON file 25 times to render one image is silly. `warm` drops
#: the memo when it rewrites the file, which is the only thing that changes it.
_MANIFEST_MEMO: dict[Path, dict[str, dict[str, Any]]] = {}


def read_manifest(path: Path = MANIFEST_PATH) -> dict[str, dict[str, Any]]:
    """The pin, keyed by URL. An absent manifest is an empty one, not an error."""
    memo = _MANIFEST_MEMO.get(path)
    if memo is not None:
        return memo
    if not path.is_file():
        _MANIFEST_MEMO[path] = {}
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = {str(entry["url"]): entry for entry in payload.get("logos", [])}
    _MANIFEST_MEMO[path] = entries
    return entries


def _write_manifest(entries: dict[str, dict[str, Any]], path: Path) -> None:
    """Sorted by team then URL, fixed precision, trailing newline. Diffable."""
    ordered = sorted(entries.values(), key=lambda e: (int(e["team_id"]), str(e["url"])))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "note": (
                    "The pin for the one non-hermetic input a share card has. The bytes "
                    "themselves are not in this repository; .cache/logos/ is gitignored. "
                    "Re-fetch and compare sha256 to verify what a published card drew."
                ),
                "min_contrast": MIN_CONTRAST,
                "alpha_floor": ALPHA_FLOOR,
                "logos": ordered,
            },
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _fetch(url: str) -> bytes:
    """One URL, with a timeout and a couple of retries. The only network in here."""
    import httpx

    last: Exception | None = None
    for _ in range(RETRIES + 1):
        try:
            response = httpx.get(
                url,
                timeout=TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "image/png,image/*"},
            )
            response.raise_for_status()
            return bytes(response.content)
        except Exception as exc:  # noqa: BLE001 - retried, then reported
            last = exc
    raise RuntimeError(f"could not fetch {url}: {last}") from last


def warm(
    rows: list[dict[str, Any]],
    *,
    background: str,
    fetch: bool = True,
    manifest: Path | None = MANIFEST_PATH,
) -> list[dict[str, Any]]:
    """Fill the cache for these rows and pin what was fetched. THE ONE NON-HERMETIC STEP.

    Every distinct URL is requested AT MOST ONCE per run: the rows are reduced to
    a set of URLs before anything is asked for, and a URL already on disk is not
    asked for at all. A warm cache therefore issues no requests, which is the
    property the pipeline depends on.

    A fetch that fails is SWALLOWED rather than raised. The card falls back to the
    generated mark for that row, which is a degraded card; a raised exception
    would be no card, which is worse, and the failure is visible in the returned
    records because the URL will be missing from them.

    The manifest is rewritten only when it would change. Writing it from the same
    function that fetches is deliberate: a pin maintained by hand is a pin that
    goes stale, and the whole argument for the manifest is that it cannot.
    """
    wanted: dict[str, int] = {}
    for row in rows:
        url = logo_url_for(row)
        if not url:
            continue
        # First writer wins, and rows are visited in board order, so the pairing
        # of URL to team id is a function of the document rather than of dict
        # iteration. Two teams cannot share a URL in practice; this is belt.
        wanted.setdefault(url, int(row.get("team_id") or 0))

    records: list[dict[str, Any]] = []
    for url in sorted(wanted):
        path = cache_path(url)
        if not path.is_file():
            if not fetch:
                continue
            try:
                raw = _fetch(url)
            except RuntimeError:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        raw = path.read_bytes()
        try:
            luminance, plate = _measure(raw, background)
        except (ValueError, zlib.error):
            continue
        records.append(
            {
                "team_id": wanted[url],
                "url": url,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "length": len(raw),
                "background": background,
                "luminance": luminance,
                "plate": plate,
            }
        )

    if manifest is not None and records:
        merged = dict(read_manifest(manifest))
        merged.update({record["url"]: record for record in records})
        _write_manifest(merged, manifest)
        _MANIFEST_MEMO.pop(manifest, None)
    return records
