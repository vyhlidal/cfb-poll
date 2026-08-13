"""The lockfile and `archive sync` - the fork promise, tested without a network.

This is the file that decides whether a stranger can run this project, so the
tests are about the two ways that goes wrong rather than about the happy path:

  1. THE LOCKFILE LIES. It names an asset that is not what it says it is, or two
     files flatten onto the same release asset name and one silently wins.
  2. THE SYNC ACCEPTS BAD BYTES. A truncated download, a corrupted local file, or
     an upstream asset that changed under a tag, any of which would put wrong
     data behind a ranking that claims to be reproducible.

Every test here injects a fake fetcher. There is no network call on any path in
this file, which is the same rule the model and backtest paths already follow.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cfbpoll.ingest import archive

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_LOCK = REPO_ROOT / "data" / "manifests" / "sportsdataverse.lock.json"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def manifest(files: dict[str, bytes]) -> dict:
    """An archive `_manifest.json` in the shape the backfill actually writes."""
    return {
        "archive": "sportsdataverse",
        "license": "MIT (test)",
        "sources": {"pbp": "https://example.invalid/pbp/"},
        "seasons": [2021],
        "files": [
            {
                "file": name,
                "url": f"https://example.invalid/{name}",
                "bytes": len(payload),
                "sha256": _digest(payload),
                "fetched_at": "2026-08-12T07:07:39Z",
            }
            for name, payload in sorted(files.items())
        ],
    }


def fake_fetcher(bodies: dict[str, bytes], *, calls: list[str] | None = None):
    """A `fetcher(url, dest)` that serves `bodies` keyed by asset basename."""

    def fetch(url: str, dest: Path) -> None:
        if calls is not None:
            calls.append(url)
        name = url.rsplit("/", 1)[-1]
        if name not in bodies:
            raise AssertionError(f"the sync asked for an asset the release has not got: {name}")
        dest.write_bytes(bodies[name])

    return fetch


# ------------------------------------------------------------------ build_lock


def test_lock_carries_provenance_and_the_release_asset_for_every_file() -> None:
    bodies = {
        "pbp/play_by_play_2021.parquet": b"plays",
        "schedules/cfb_schedules_2021.parquet": b"s",
    }
    lock = archive.build_lock(manifest(bodies), repo="owner/name", tag="archive-v1")

    assert lock["schema"] == archive.LOCK_SCHEMA
    assert lock["file_count"] == 2
    assert lock["total_bytes"] == sum(len(v) for v in bodies.values())
    assert lock["release"]["asset_base"] == (
        "https://github.com/owner/name/releases/download/archive-v1/"
    )
    entry = next(f for f in lock["files"] if f["path"].startswith("pbp/"))
    # `path` is where it goes, `asset` is what the release calls it. Both are
    # needed: release assets are one flat namespace and the archive is a tree.
    assert entry["asset"] == "play_by_play_2021.parquet"
    assert entry["sha256"] == _digest(b"plays")
    assert entry["upstream_url"] == "https://example.invalid/pbp/play_by_play_2021.parquet"


def test_a_collision_in_the_flat_release_namespace_is_refused() -> None:
    """Two files, one asset name. Silently, one of them would never be downloaded."""
    payload = manifest({"a/same.parquet": b"one", "b/same.parquet": b"two"})
    with pytest.raises(ValueError, match="asset name collision"):
        archive.build_lock(payload, repo="owner/name", tag="archive-v1")


def test_an_empty_manifest_does_not_produce_an_empty_promise() -> None:
    with pytest.raises(ValueError, match="refusing to write an empty lockfile"):
        archive.build_lock(manifest({}), repo="owner/name", tag="archive-v1")


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    lock = archive.build_lock(manifest({"x.csv": b"x"}), repo="o/n", tag="t")
    path = archive.write_lock(lock, tmp_path / "nested" / "lock.json")
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert archive.read_lock(path) == lock


def test_a_missing_lockfile_names_the_command_that_makes_one(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="archive lock"):
        archive.read_lock(tmp_path / "nope.json")


def test_a_lockfile_from_a_future_schema_is_refused_rather_than_guessed(tmp_path: Path) -> None:
    path = tmp_path / "lock.json"
    path.write_text(json.dumps({"schema": archive.LOCK_SCHEMA + 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        archive.read_lock(path)


# ---------------------------------------------------------------- sync_from_lock


def test_sync_downloads_what_is_missing_and_lands_it_at_the_right_path(tmp_path: Path) -> None:
    bodies = {"pbp/play_by_play_2021.parquet": b"plays" * 100, "notes.txt": b"hello"}
    lock = archive.build_lock(manifest(bodies), repo="o/n", tag="t")
    calls: list[str] = []

    summary = archive.sync_from_lock(
        lock,
        tmp_path,
        fetcher=fake_fetcher(
            {
                "play_by_play_2021.parquet": bodies["pbp/play_by_play_2021.parquet"],
                "notes.txt": bodies["notes.txt"],
            },
            calls=calls,
        ),
    )

    assert summary["downloaded"] == 2
    assert summary["ok"] == 2
    assert (tmp_path / "pbp" / "play_by_play_2021.parquet").read_bytes() == bodies[
        "pbp/play_by_play_2021.parquet"
    ]
    assert all(url.startswith("https://github.com/o/n/releases/download/t/") for url in calls)


def test_a_second_sync_downloads_nothing(tmp_path: Path) -> None:
    bodies = {"a.txt": b"aaaa"}
    lock = archive.build_lock(manifest(bodies), repo="o/n", tag="t")
    fetch = fake_fetcher({"a.txt": b"aaaa"})
    archive.sync_from_lock(lock, tmp_path, fetcher=fetch)

    def refuse(url: str, dest: Path) -> None:
        raise AssertionError("a file that is already correct must not be fetched again")

    summary = archive.sync_from_lock(lock, tmp_path, verify=True, fetcher=refuse)
    assert (summary["checked"], summary["downloaded"], summary["ok"]) == (1, 0, 1)


def test_wrong_bytes_from_the_release_never_reach_the_archive(tmp_path: Path) -> None:
    """The whole point. A digest that does not match must stop the run."""
    lock = archive.build_lock(manifest({"a.txt": b"the real bytes"}), repo="o/n", tag="t")

    with pytest.raises(archive.AssetMismatch, match="sha256"):
        archive.sync_from_lock(lock, tmp_path, fetcher=fake_fetcher({"a.txt": b"the real byteS"}))

    # Not the file, and not a half-written `.part` either: an interrupted or
    # rejected download must leave nothing a consumer could pick up.
    assert list(tmp_path.rglob("*")) == []


def test_a_truncated_download_is_caught_on_size_before_it_is_hashed(tmp_path: Path) -> None:
    lock = archive.build_lock(manifest({"a.txt": b"0123456789"}), repo="o/n", tag="t")
    with pytest.raises(archive.AssetMismatch, match="bytes"):
        archive.sync_from_lock(lock, tmp_path, fetcher=fake_fetcher({"a.txt": b"01234"}))


def test_a_corrupt_local_file_raises_rather_than_being_overwritten(tmp_path: Path) -> None:
    """`--verify` exists to FIND this, and finding it silently is not finding it.

    A local file whose digest disagrees with the lock is either corruption or an
    archive that no longer matches what was published, and both are worth being
    told about. Overwriting on sight would destroy the evidence.
    """
    lock = archive.build_lock(manifest({"a.txt": b"good"}), repo="o/n", tag="t")
    (tmp_path / "a.txt").write_bytes(b"bad!")  # same length, different bytes

    with pytest.raises(archive.AssetMismatch, match="--repair"):
        archive.sync_from_lock(
            lock, tmp_path, verify=True, fetcher=fake_fetcher({"a.txt": b"good"})
        )
    assert (tmp_path / "a.txt").read_bytes() == b"bad!"

    summary = archive.sync_from_lock(
        lock, tmp_path, verify=True, repair=True, fetcher=fake_fetcher({"a.txt": b"good"})
    )
    assert summary["repaired"] == 1
    assert (tmp_path / "a.txt").read_bytes() == b"good"


def test_a_shallow_sync_still_catches_a_wrong_size(tmp_path: Path) -> None:
    """Without --verify the check is size-only, which is the cheap half of the job."""
    lock = archive.build_lock(manifest({"a.txt": b"0123456789"}), repo="o/n", tag="t")
    (tmp_path / "a.txt").write_bytes(b"short")
    summary = archive.sync_from_lock(
        lock, tmp_path, fetcher=fake_fetcher({"a.txt": b"0123456789"})
    )
    assert summary["downloaded"] == 1
    assert (tmp_path / "a.txt").read_bytes() == b"0123456789"


def test_only_narrows_the_pull_to_the_prefixes_asked_for(tmp_path: Path) -> None:
    """A scores-only run does not need 0.52 GB of play-by-play."""
    bodies = {"pbp/p.parquet": b"pbp", "schedules/s.parquet": b"sched"}
    lock = archive.build_lock(manifest(bodies), repo="o/n", tag="t")
    summary = archive.sync_from_lock(
        lock, tmp_path, only=["schedules"], fetcher=fake_fetcher({"s.parquet": b"sched"})
    )
    assert summary["checked"] == 1
    assert not (tmp_path / "pbp").exists()


# ---------------------------------------------------- the lockfile we actually ship


@pytest.mark.skipif(not COMMITTED_LOCK.exists(), reason="lockfile not generated yet")
def test_the_committed_lockfile_is_coherent() -> None:
    """A guard on the one file a stranger's whole experience depends on."""
    lock = archive.read_lock(COMMITTED_LOCK)

    assert lock["file_count"] == len(lock["files"])
    assert lock["total_bytes"] == sum(int(f["bytes"]) for f in lock["files"])
    assert lock["release"]["asset_base"].startswith("https://github.com/")
    assert lock["release"]["asset_base"].endswith(f"/{lock['release']['tag']}/")

    assets = [f["asset"] for f in lock["files"]]
    assert len(set(assets)) == len(assets), "two files would collide as release assets"
    for entry in lock["files"]:
        assert entry["asset"] == archive.asset_name(entry["path"])
        assert len(entry["sha256"]) == 64
        assert int(entry["bytes"]) > 0
        # GitHub's per-asset limit is 2 GiB. The largest here is ~131 MB, and the
        # day that stops being true is the day this stops working silently.
        assert int(entry["bytes"]) < 2 * 1024**3

    # The licence notice MIT requires must be in what we republish.
    assert any("LICENSE" in f["asset"] for f in lock["files"])


@pytest.mark.skipif(not COMMITTED_LOCK.exists(), reason="lockfile not generated yet")
def test_the_lockfile_republishes_only_the_mit_class() -> None:
    """CFBD's terms forbid a mirror. Nothing from `archive/cfbd/` may be in here."""
    lock = archive.read_lock(COMMITTED_LOCK)
    assert lock["archive"] == "sportsdataverse"
    for entry in lock["files"]:
        upstream = str(entry.get("upstream_url") or "")
        assert "collegefootballdata.com" not in upstream, entry["path"]
