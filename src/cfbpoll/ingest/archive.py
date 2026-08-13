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

STATUS: `write_raw`, `verify`, and the lockfile half at the bottom of this file
(`build_lock`, `write_lock`, `read_lock`, `sync_from_lock`) are real - class A now
round-trips from our own release assets with a digest check on every byte, which
is what makes `make rankings` work on a clone with no accounts. `push_r2` remains
a stub; class B still has nowhere to go but this laptop.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "LOCK_SCHEMA",
    "MANIFEST_NAME",
    "R2_BUCKET",
    "AssetMismatch",
    "asset_name",
    "build_lock",
    "local_state",
    "manifest_entries",
    "param_slug",
    "push_r2",
    "read_lock",
    "sync_from_lock",
    "verify",
    "write_lock",
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


# ------------------------------------------------------------------ the lockfile
#
# THE FORK PROMISE, MADE OPERATIONAL. Everything above concerns bytes we pulled.
# Everything below concerns bytes a STRANGER pulls, from a release we publish, and
# it is the difference between a repository that works for one person on one
# laptop and one that works for anybody.
#
# The split that makes it legal is not incidental. The SportsDataverse archive is
# MIT-licensed, so it may be republished; CFBD's terms forbid operating "a raw
# feed, public database mirror, proxy, substitute API", so `archive/cfbd/` may
# not be. Only class A reaches a release asset. `LICENSE-MIT-sportsdataverse.txt`
# rides along in the release for the same reason it sits in the archive: an MIT
# redistribution has to carry the notice.
#
# A LOCKFILE, NOT A LIST OF URLS. `_manifest.json` records where each file came
# from upstream. The lockfile records, for each file, both the upstream provenance
# and the release asset a fork downloads, plus bytes and sha256. `archive sync`
# checks the digest BEFORE any consumer reads a file, and a mismatch stops the
# run. That is what makes the archive content-addressed for a stranger and not
# merely for us.

LOCK_SCHEMA = 1

#: The lockfile the Makefile, the workflows and `docs/` all name. Relative to the
#: repository root.
LOCK_PATH = Path("data/manifests/sportsdataverse.lock.json")


class AssetMismatch(RuntimeError):
    """A file's bytes are not the bytes the lockfile says they must be."""


def asset_name(relative_path: str) -> str:
    """`pbp/play_by_play_2021.parquet` -> `play_by_play_2021.parquet`.

    Release assets live in one flat namespace, so the archive's directory tree
    has to survive the round trip some other way: the lockfile carries `path`
    (where the file goes) beside `asset` (what it is called in the release).
    `build_lock` refuses to emit a lock whose asset names collide, which is the
    only way this flattening can go wrong.
    """
    return relative_path.rsplit("/", 1)[-1]


def build_lock(
    manifest: Mapping[str, Any],
    *,
    repo: str,
    tag: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Turn an archive `_manifest.json` into the committed lockfile.

    The manifest is the record of a backfill that happened on one machine. The
    lockfile is a promise to everyone else, so it carries the release coordinates
    and re-states every digest in a form `archive sync` can act on without
    reading the archive it is about to create.
    """
    files = list(manifest.get("files", []))
    if not files:
        raise ValueError("manifest lists no files; refusing to write an empty lockfile")

    entries = []
    for record in sorted(files, key=lambda f: str(f["file"])):
        path = str(record["file"])
        entries.append(
            {
                "path": path,
                "asset": asset_name(path),
                "bytes": int(record["bytes"]),
                "sha256": str(record["sha256"]),
                "upstream_url": record.get("url"),
                "fetched_at": record.get("fetched_at"),
            }
        )

    seen: dict[str, str] = {}
    for entry in entries:
        if entry["asset"] in seen:
            raise ValueError(
                f"asset name collision in the release namespace: {entry['asset']!r} "
                f"is produced by both {seen[entry['asset']]!r} and {entry['path']!r}. "
                "Release assets are flat; rename one of them upstream of here."
            )
        seen[entry["asset"]] = entry["path"]

    when = (generated_at or datetime.now(UTC)).astimezone(UTC)
    return {
        "schema": LOCK_SCHEMA,
        "archive": str(manifest.get("archive", "sportsdataverse")),
        "description": (
            "Every MIT-licensed input asset this project reads, with the release "
            "asset that serves it and the sha256 that proves it arrived intact. "
            "`cfbpoll archive sync --verify` checks every digest before any "
            "consumer reads a file; a mismatch is a hard failure, not a warning."
        ),
        "license": str(manifest.get("license", "")),
        "release": {
            "repo": repo,
            "tag": tag,
            "asset_base": f"https://github.com/{repo}/releases/download/{tag}/",
            "note": (
                "Public, no account, no token. GitHub serves release assets "
                "anonymously, which is the whole point: a fork needs no secrets."
            ),
        },
        "upstream": dict(manifest.get("sources", {})),
        "seasons": list(manifest.get("seasons", [])),
        "generated_at": when.isoformat().replace("+00:00", "Z"),
        "file_count": len(entries),
        "total_bytes": sum(e["bytes"] for e in entries),
        "files": entries,
    }


def write_lock(lock: Mapping[str, Any], path: str | Path) -> Path:
    """Stable JSON, sorted keys, trailing newline. Same rule as every artifact."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(lock, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return target


def read_lock(path: str | Path = LOCK_PATH) -> dict[str, Any]:
    """Load the lockfile, or say plainly which step of the build order is missing."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(
            f"{target} does not exist. It is generated by "
            "`cfbpoll archive lock` from a completed backfill and committed to "
            "git; without it there is nothing for a fork to verify against."
        )
    lock = json.loads(target.read_text(encoding="utf-8"))
    if int(lock.get("schema", 0)) != LOCK_SCHEMA:
        raise ValueError(f"{target}: lockfile schema {lock.get('schema')!r} != {LOCK_SCHEMA}")
    return lock


def _digest(path: Path, chunk: int = 1 << 20) -> str:
    """sha256 of a file, streamed. The play-by-play files are 130 MB apiece."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            hasher.update(block)
    return hasher.hexdigest()


def local_state(target: Path, entry: Mapping[str, Any], *, deep: bool) -> str:
    """`missing` | `size` | `digest` | `ok`, for one lockfile entry.

    `deep` hashes; shallow only compares size. Shallow exists because re-hashing
    0.55 GB on every invocation would make `make rankings` feel broken, and the
    download path always hashes what it just wrote regardless.
    """
    if not target.exists():
        return "missing"
    if target.stat().st_size != int(entry["bytes"]):
        return "size"
    if deep and _digest(target) != str(entry["sha256"]):
        return "digest"
    return "ok"


def _https_fetch(url: str, dest: Path) -> None:
    """Stream one release asset to disk. The only network call on this path."""
    import httpx

    with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as response:
        response.raise_for_status()
        with dest.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)


def sync_from_lock(
    lock: Mapping[str, Any],
    root: str | Path,
    *,
    verify: bool = False,
    repair: bool = False,
    only: Iterable[str] | None = None,
    fetcher: Callable[[str, Path], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Materialise the MIT archive from our release assets, digest-checked.

    Returns a summary; raises `AssetMismatch` on any digest that does not match
    after a download. Never leaves a half-written file where a consumer can read
    it: every download lands on `<name>.part` and is renamed only after its
    digest matches, so an interrupted sync is resumable and a file that IS there
    is a file that was checked.

    `repair` is required to replace a local file whose digest disagrees with the
    lock. Without it that case raises, because the alternative - silently
    overwriting - would let this command destroy the very evidence that something
    upstream, or on disk, changed underneath us.
    """
    root = Path(root)
    fetcher = fetcher or _https_fetch
    say = log or (lambda _message: None)
    wanted = set(only) if only is not None else None

    base = str(lock["release"]["asset_base"])
    summary: dict[str, Any] = {
        "checked": 0,
        "ok": 0,
        "downloaded": 0,
        "bytes_downloaded": 0,
        "repaired": 0,
        "root": str(root),
        "tag": lock["release"]["tag"],
    }

    for entry in lock["files"]:
        path = str(entry["path"])
        if wanted is not None and not any(path.startswith(prefix) for prefix in wanted):
            continue
        summary["checked"] += 1
        target = root / path
        state = local_state(target, entry, deep=verify)

        if state == "ok":
            summary["ok"] += 1
            continue
        if state == "digest" and not repair:
            raise AssetMismatch(
                f"{target} exists with the wrong sha256. The lockfile says "
                f"{entry['sha256']}. This is either local corruption or an "
                "archive that no longer matches the published lock, and both are "
                "worth knowing about. Re-run with --repair to replace it."
            )
        if state == "digest":
            summary["repaired"] += 1

        url = base + str(entry["asset"])
        say(f"fetch {path} ({int(entry['bytes']):,} bytes)")
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        try:
            fetcher(url, part)
            got = part.stat().st_size
            if got != int(entry["bytes"]):
                raise AssetMismatch(
                    f"{url}: got {got:,} bytes, lockfile says {int(entry['bytes']):,}"
                )
            digest = _digest(part)
            if digest != str(entry["sha256"]):
                raise AssetMismatch(
                    f"{url}: sha256 {digest} != {entry['sha256']} from the lockfile. "
                    "Refusing to place it in the archive."
                )
            part.replace(target)
        finally:
            part.unlink(missing_ok=True)

        summary["downloaded"] += 1
        summary["bytes_downloaded"] += int(entry["bytes"])
        summary["ok"] += 1

    return summary
