"""The immutable weekly release: what it gathers, what it hashes, what it refuses.

No test here touches the network. The `gh` leg is a single injected callable, so
the two behaviours that actually matter - "refuse when the tag exists" and "ask
before you upload, never after" - are asserted rather than described.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import polars as pl
import pytest

from cfbpoll.publish import release as rel


def _run_directory(path: Path, *, recipe: str = "house", week: int = 15) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    ranking = [
        {"rank": 1, "team": "Washington", "wins": 13, "losses": 0},
        {"rank": 2, "team": "Michigan", "wins": 13, "losses": 0},
    ]
    (path / "poll.json").write_text(
        json.dumps({"provisional": False, "top25": ranking, "ranking": ranking}), encoding="utf-8"
    )
    (path / "poll.csv").write_text("rank,team\n1,Washington\n2,Michigan\n", encoding="utf-8")
    (path / "model_params.json").write_text(
        json.dumps(
            {
                "season": 2023,
                "through": {"season_type": "regular", "week": week},
                "headline_ordering": "schedule_odds",
            }
        ),
        encoding="utf-8",
    )
    (path / "_run.json").write_text(
        json.dumps(
            {
                "season": 2023,
                "through_week": week,
                "recipe": recipe,
                "git_sha": "f33aa7c55941096d388632f6f4669dcb01ec0ad9",
                "config_hash": "37d52aa3d0ccca4a7630995031ccba6b22b8bb224b04f4dc2696c9785bd5c9af",
                "archive_manifest_sha256": "manifest:abc",
                "fit_window_sha256": "def",
            }
        ),
        encoding="utf-8",
    )
    pl.DataFrame({"team": ["Washington", "Michigan"], "power": [23.7, 31.9]}).write_parquet(
        path / "ratings_live.parquet"
    )
    return path


class _FakeGh:
    """Records every `gh` invocation and answers with a canned result."""

    def __init__(self, *, exists: bool = False, create_code: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.exists = exists
        self.create_code = create_code

    def __call__(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        if args[1] == "view":
            return subprocess.CompletedProcess(
                list(args),
                0 if self.exists else 1,
                stdout='{"tagName":"poll-2023-w15"}' if self.exists else "",
                stderr="" if self.exists else "release not found",
            )
        return subprocess.CompletedProcess(
            list(args),
            self.create_code,
            stdout="https://github.com/vyhlidal/cfb-poll/releases/tag/poll-2023-w15\n",
            stderr="" if self.create_code == 0 else "boom",
        )


def _never_called(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    raise AssertionError(f"the network was touched: gh {' '.join(args)}")


# ------------------------------------------------------------------- the bundle


def test_the_tag_is_the_one_naming_rule() -> None:
    assert rel.tag_for(2023, 15) == "poll-2023-w15"
    assert rel.tag_for(2026, 3) == "poll-2026-w03"


def test_build_gathers_hashes_and_verifies_every_run_file(tmp_path: Path) -> None:
    run = _run_directory(tmp_path / "out")
    bundle = rel.build(run)

    assert bundle.tag == "poll-2023-w15"
    assert bundle.directory == run / "release" / "poll-2023-w15"
    names = [a.name for a in bundle.assets]
    assert names == sorted(names), "assets must be ordered by name, never by dict order"
    assert set(names) == {"_run.json", "model_params.json", "poll.csv", "poll.json",
                          "ratings_live.parquet"}
    assert rel.verify(bundle) == []

    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert manifest["asset_count"] == 5
    assert manifest["season"] == 2023 and manifest["week"] == 15
    assert manifest["git_sha"].startswith("f33aa7c")
    # What the run did NOT write is reported, never faked.
    assert "backtest_metrics.json" in manifest["not_present_in_run"]

    lines = bundle.checksum_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    for asset, line in zip(bundle.assets, lines, strict=True):
        assert line == f"{asset.sha256}  {asset.name}"
        staged = bundle.directory / asset.name
        assert staged.read_bytes() == (run / asset.name).read_bytes()


def test_two_builds_of_one_run_are_byte_identical(tmp_path: Path) -> None:
    """The property `--dry-run` is worth running for (report 03 §9.3).

    No wall-clock, no host, no dict ordering: stage the same run twice and the
    manifest, the checksum file and the notes are the same bytes. If they were
    not, "verify the download against the manifest" would be advice nobody could
    follow twice.
    """
    run = _run_directory(tmp_path / "out")
    first = rel.build(run)
    digests = {
        name: (first.directory / name).read_bytes()
        for name in (rel.MANIFEST_NAME, rel.CHECKSUM_NAME, rel.NOTES_NAME)
    }
    second = rel.build(run)
    for name, blob in digests.items():
        assert (second.directory / name).read_bytes() == blob, f"{name} is not deterministic"
    assert first.manifest_sha256() == second.manifest_sha256()


def test_a_run_directory_without_the_four_files_is_refused(tmp_path: Path) -> None:
    run = _run_directory(tmp_path / "out")
    (run / "poll.csv").unlink()
    with pytest.raises(rel.MissingArtifactError) as error:
        rel.build(run)
    assert "poll.csv" in str(error.value)


def test_an_empty_directory_is_refused_before_anything_is_staged(tmp_path: Path) -> None:
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(rel.MissingArtifactError):
        rel.build(empty)
    assert not (empty / "release").exists()


def test_an_alternate_lens_may_not_inherit_the_house_tag(tmp_path: Path) -> None:
    """ADR 0011: only `house` is the published poll."""
    run = _run_directory(tmp_path / "out", recipe="just-win")
    with pytest.raises(rel.ReleaseError) as error:
        rel.build(run)
    assert "--tag" in str(error.value)

    bundle = rel.build(run, tag="poll-2023-w15-just-win")
    assert bundle.tag == "poll-2023-w15-just-win"
    assert bundle.manifest["recipe"] == "just-win"


def test_fixtures_and_cards_are_flattened_into_prefixed_asset_names(tmp_path: Path) -> None:
    run = _run_directory(tmp_path / "out")
    fixtures = tmp_path / "site" / "2023"
    (fixtures / "variants" / "beta").mkdir(parents=True)
    (fixtures / "week-15.json").write_text("{}", encoding="utf-8")
    (fixtures / "variants" / "beta" / "week-15.json").write_text("{}", encoding="utf-8")
    cards = tmp_path / "share"
    cards.mkdir()
    (cards / "top5.svg").write_text("<svg/>", encoding="utf-8")

    bundle = rel.build(run, fixtures=fixtures, cards=cards)
    names = {a.name for a in bundle.assets}
    assert "fixtures-week-15.json" in names
    assert "fixtures-variants-beta-week-15.json" in names
    assert "card-top5.svg" in names


def test_a_stale_asset_from_a_previous_staging_does_not_survive(tmp_path: Path) -> None:
    run = _run_directory(tmp_path / "out")
    first = rel.build(run)
    (run / "ratings_live.parquet").unlink()
    second = rel.build(run)
    assert not (second.directory / "ratings_live.parquet").exists()
    assert "ratings_live.parquet" not in {a.name for a in second.assets}
    assert first.directory == second.directory


def test_verify_catches_a_tampered_asset(tmp_path: Path) -> None:
    run = _run_directory(tmp_path / "out")
    bundle = rel.build(run)
    (bundle.directory / "poll.csv").write_text("rank,team\n1,Somebody Else\n", encoding="utf-8")
    problems = rel.verify(bundle)
    assert problems and "poll.csv" in problems[0]


def test_an_oversized_asset_is_refused_before_github_refuses_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rel, "MAX_ASSET_BYTES", 10)
    run = _run_directory(tmp_path / "out")
    with pytest.raises(rel.ReleaseError) as error:
        rel.build(run)
    assert "caps a release asset" in str(error.value)


# -------------------------------------------------------------- immutability


def test_publish_refuses_a_tag_that_already_exists(tmp_path: Path) -> None:
    run = _run_directory(tmp_path / "out")
    gh = _FakeGh(exists=True)
    with pytest.raises(rel.ReleaseExistsError) as error:
        rel.publish(run, runner=gh)
    message = str(error.value)
    assert "already exists" in message
    assert "--force" in message and "new tag" in message
    # It asked, and having been told, it did not upload.
    assert [c[1] for c in gh.calls] == ["view"]


def test_publish_creates_the_release_once_when_the_tag_is_free(tmp_path: Path) -> None:
    run = _run_directory(tmp_path / "out")
    gh = _FakeGh(exists=False)
    bundle, url = rel.publish(run, runner=gh)
    assert url.endswith("poll-2023-w15")
    assert [c[1] for c in gh.calls] == ["view", "create"]
    create = gh.calls[1]
    assert create[2] == "poll-2023-w15"
    # Every asset, plus the checksum file and the manifest, in ONE upload.
    for asset in bundle.assets:
        assert str(bundle.directory / asset.name) in create
    assert str(bundle.checksum_path) in create
    assert str(bundle.manifest_path) in create
    assert str(bundle.notes_path) in create  # as --notes-file


def test_a_failed_upload_is_an_error_not_a_shrug(tmp_path: Path) -> None:
    run = _run_directory(tmp_path / "out")
    with pytest.raises(rel.ReleaseError) as error:
        rel.publish(run, runner=_FakeGh(create_code=1))
    assert "gh release create failed" in str(error.value)


def test_could_not_tell_is_never_read_as_safe_to_publish(tmp_path: Path) -> None:
    """An auth or network failure must raise, not return False."""

    def confused(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(args), 4, stdout="", stderr="gh: not logged in")

    with pytest.raises(rel.ReleaseError) as error:
        rel.release_exists("poll-2023-w15", runner=confused)
    assert "could not determine" in str(error.value)


def test_release_not_found_is_a_real_answer() -> None:
    def missing(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(args), 1, stdout="", stderr="release not found")

    assert rel.release_exists("poll-2023-w15", runner=missing) is False


def test_dry_run_builds_the_real_bundle_and_touches_no_network(tmp_path: Path) -> None:
    run = _run_directory(tmp_path / "out")
    bundle, url = rel.publish(run, dry_run=True, runner=_never_called)
    assert url is None
    assert bundle.manifest_path.exists()
    assert rel.verify(bundle) == []


def test_dry_run_and_the_real_run_stage_the_same_bytes(tmp_path: Path) -> None:
    """--dry-run is the artifact with the network left out, not a rehearsal of it."""
    run = _run_directory(tmp_path / "out")
    dry, _ = rel.publish(run, dry_run=True, runner=_never_called)
    blob = dry.manifest_path.read_bytes()
    wet, _ = rel.publish(run, runner=_FakeGh(exists=False))
    assert wet.manifest_path.read_bytes() == blob
