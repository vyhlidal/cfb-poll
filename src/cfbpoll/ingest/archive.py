"""The append-only, content-addressed raw archive.

Specified by report 01 §5.4 - "the single most important engineering decision in
this report" - and given physical homes by report 03 §5.1-§5.3.

PRINCIPLE: files are the source of truth. Postgres is a cache that can be dropped
and rebuilt. Object storage holds what the license says we cannot publish.

Three classes, three homes:
  A. MIT SportsDataverse raw   publishable  ~0.55 GB   GitHub Release assets
  B. CFBD raw JSON             NOT publishable  MBs    private Cloudflare R2
  C. our derived output        publishable  50-300 MB  GitHub Release assets

NEVER OVERWRITE. A re-pull writes a new timestamped file. That is what makes late
upstream stat corrections OBSERVABLE - diff Sunday's pull against Wednesday's and
see exactly what changed. For a project whose credibility rests on transparency,
that is an analytical asset, not bookkeeping.

Layout (report 03 §5.3):
    archive/sportsdataverse/{pbp,schedules,ratings,crosswalk}/...
    archive/cfbd/{season}/week-{NN}/{ISO8601}__{endpoint}__{params}.json
Each directory carries a _manifest.json: url, params, http status, bytes, sha256,
fetched_at. The manifests are what make this content-addressed rather than a pile
of files.

APPEND-ONLY IS ENFORCED, NOT DOCUMENTED. `write_raw` refuses to overwrite a
file - a second write inside the same second gets a `-2` suffix rather than
clobbering the first - and it refuses to drop or rewrite a manifest entry. A
manifest is only ever extended. If a caller tries to re-register a path that is
already recorded with a different digest, that is a corrupted archive and it
raises.

WHAT NEVER REACHES THE ARCHIVE: the API key. The recorded `url` is the request
URL with its query string, and CFBD's key travels in an `Authorization` header
precisely so that it cannot appear there (report 01 §3.2: "Do not commit it,
place it in a URL, or include it in a public browser application"). `write_raw`
asserts this rather than trusting it.

R2 IS NOT YET PROVISIONED. The push target is a stub: no Cloudflare account, no
bucket, no credentials. The zero-new-accounts alternative on the table is the
Hostinger VPS disk plus one off-box copy (report 03 §5.2).

STATUS: `write_raw` and `verify` are real. `push_r2` remains a stub.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "MANIFEST_NAME",
    "R2_BUCKET",
    "manifest_entries",
    "param_slug",
    "push_r2",
    "verify",
    "write_raw",
]

R2_BUCKET = "cfb-poll-archive"  # PLANNED, not created. See report 03 §5.2.

MANIFEST_NAME = "_manifest.json"

#: Anything that looks like a credential in a URL. A key in a query string would
#: be archived forever in a file we intend to keep forever, so this is checked on
#: every write rather than left to reviewer attention.
_SECRET_IN_URL = re.compile(r"(?i)[?&](api[_-]?key|key|token|access[_-]?token)=")


def param_slug(params: Mapping[str, Any]) -> str:
    """`{'year': 2021, 'week': 3}` -> `week=3&year=2021`. Sorted, so it is stable.

    Sorted by key rather than by call order: the filename is an identity, and two
    calls that requested the same thing must produce the same identity regardless
    of how the dict was built.
    """
    items = [(str(k), str(v)) for k, v in params.items() if v is not None]
    if not items:
        return "none"
    return "&".join(f"{k}={v}" for k, v in sorted(items))


def _endpoint_slug(endpoint: str) -> str:
    """`/games/teams` -> `games_teams`. Filesystem-safe and still readable."""
    return re.sub(r"[^A-Za-z0-9]+", "_", endpoint.strip("/")) or "root"


def _stamp(when: datetime) -> str:
    """`2026-09-13T060112Z` - the report 01 §5.4 filename convention, verbatim."""
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H%M%SZ")


def manifest_entries(manifest_path: str | Path) -> list[dict[str, Any]]:
    """Every entry in a manifest, or an empty list when there is no manifest yet."""
    path = Path(manifest_path)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("entries", []))


def _write_manifest(path: Path, entries: list[dict[str, Any]]) -> None:
    """Stable JSON, same rule as every other artifact this project writes."""
    path.write_text(
        json.dumps(
            {"schema": 1, "entries": sorted(entries, key=lambda e: str(e["file"]))},
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_raw(
    payload: bytes,
    endpoint: str,
    params: Mapping[str, Any],
    root: str | Path,
    *,
    bucket: str = "",
    url: str | None = None,
    status: int = 200,
    fetched_at: datetime | None = None,
) -> dict[str, Any]:
    """Write one raw response immutably and return its manifest entry.

    `payload` is the response body EXACTLY as it arrived - not parsed, not
    reserialised, not pretty-printed. Re-deriving differently later is only
    possible if the bytes on disk are the bytes upstream sent (report 01 §5.4).

    `bucket` is the sub-path under `root`, e.g. `2021/postseason` or `_meta`.
    Season-scoped pulls carry a season; `/info` does not, and pretending it does
    would put a lie in the layout.
    """
    if not isinstance(payload, bytes | bytearray):
        raise TypeError("write_raw stores response BYTES; pass the body unparsed")
    if url is not None and _SECRET_IN_URL.search(url):
        raise ValueError(
            "refusing to archive a URL carrying a credential in its query string "
            "(report 01 §3.2). The CFBD key belongs in an Authorization header."
        )

    when = fetched_at or datetime.now(UTC)
    directory = Path(root) / bucket if bucket else Path(root)
    directory.mkdir(parents=True, exist_ok=True)

    stem = f"{_stamp(when)}__{_endpoint_slug(endpoint)}__{param_slug(params)}"
    path = directory / f"{stem}.json"
    # Never overwrite. Two pulls inside the same second are a re-pull, and a
    # re-pull is exactly the event this archive exists to make visible.
    dupe = 2
    while path.exists():
        path = directory / f"{stem}-{dupe}.json"
        dupe += 1

    path.write_bytes(bytes(payload))

    entry: dict[str, Any] = {
        "file": path.name,
        "endpoint": endpoint,
        "params": {str(k): v for k, v in sorted(params.items())},
        "url": url,
        "status": int(status),
        "bytes": len(payload),
        "sha256": hashlib.sha256(bytes(payload)).hexdigest(),
        "fetched_at": when.astimezone(UTC).isoformat().replace("+00:00", "Z"),
    }

    manifest_path = directory / MANIFEST_NAME
    entries = manifest_entries(manifest_path)
    for existing in entries:
        if existing["file"] == entry["file"] and existing["sha256"] != entry["sha256"]:
            raise RuntimeError(
                f"manifest already records {entry['file']} with a different digest; "
                "the archive is append-only and this would rewrite history"
            )
    if all(existing["file"] != entry["file"] for existing in entries):
        entries.append(entry)
    _write_manifest(manifest_path, entries)
    return entry


def verify(manifest_path: str | Path) -> bool:
    """sha256-check every file against the manifest. Mismatch is a hard failure.

    Returns True or raises. A boolean-returning checker that returns False on
    corruption invites a caller that ignores it; report 01 §5.4 wants a
    checksum mismatch to stop the run.
    """
    path = Path(manifest_path)
    directory = path.parent
    for entry in manifest_entries(path):
        target = directory / str(entry["file"])
        if not target.exists():
            raise FileNotFoundError(f"manifest lists a file that is not there: {target}")
        raw = target.read_bytes()
        if len(raw) != int(entry["bytes"]):
            raise RuntimeError(f"size mismatch for {target}: {len(raw)} != {entry['bytes']}")
        digest = hashlib.sha256(raw).hexdigest()
        if digest != entry["sha256"]:
            raise RuntimeError(f"sha256 mismatch for {target}: {digest} != {entry['sha256']}")
    return True


def push_r2(scope: str = "cfbd") -> None:
    """Push the private archive class to Cloudflare R2 (append-only, never overwrite)."""
    raise NotImplementedError("ingest.archive.push_r2 - scaffold; R2 not yet provisioned")
