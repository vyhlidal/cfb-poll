"""Publish out/ as immutable GitHub Release assets.

Specified by report 03 §5.2 and ADR 0003.

Why release assets and not git: GitHub blocks files over 100 MiB, and four of the
five PBP parquet files exceed it.

Why release assets and not Git LFS: LFS bandwidth "always counts against the
repository owner's account" and "forking and pulling a repository counts against
the parent repository's bandwidth usage." At 0.55 GB of objects, roughly 18
clones exhausts the free monthly quota - and the OWNER pays for other people's
forks. For a project whose entire thesis is "please fork this," LFS creates a
direct financial penalty for success.

Release assets: 2 GiB per file, 1000 assets per release, and NO RESTRICTION on
total size or bandwidth. Our largest file is 131 MB. This is also exactly the
mechanism SportsDataverse already uses to ship the same bytes, so we inherit an
operational proof rather than inventing a channel.

Tags:
    archive-v{n}          the republished MIT input archive
    poll-{season}-w{NN}   our derived output for one week

IMMUTABLE MEANS IMMUTABLE. If the tag already exists this refuses and exits
non-zero; it never edits, never re-uploads over an asset, and has no --force.
A corrected week is a NEW tag with its own name, exactly as `cfb_poll_published`
is append-only (ADR 0004): a published number that can be quietly rewritten is
not a published number. The refusal is the feature.

THE MANIFEST IS A PURE FUNCTION OF THE RUN DIRECTORY. No wall-clock timestamp,
no host name, no ordering that depends on a dict - the same run staged twice
produces byte-identical `manifest.json` and `SHA256SUMS` (report 03 §9.3). That
is what makes `--dry-run` worth running: it is not a rehearsal of the upload, it
is the artifact, built and verified, with the network left out.

STATUS: implemented. The upload leg needs `gh` on PATH and a token; `--dry-run`
needs neither and is what CI and a fork can both run.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "Asset",
    "Bundle",
    "MissingArtifactError",
    "ReleaseError",
    "ReleaseExistsError",
    "build",
    "publish",
    "release_exists",
    "tag_for",
    "verify",
]

MANIFEST_NAME = "manifest.json"
CHECKSUM_NAME = "SHA256SUMS"
NOTES_NAME = "notes.md"

#: Not assets. They describe the assets, so hashing them into their own manifest
#: is circular, and `gh release create --notes-file` consumes the notes.
BUNDLE_METADATA: tuple[str, ...] = (MANIFEST_NAME, CHECKSUM_NAME, NOTES_NAME)

DEFAULT_REPO = "vyhlidal/cfb-poll"

#: Without these four there is no published poll, only a directory. `rank` writes
#: all four on every run, so an absence means the wrong directory was pointed at
#: - which is worth failing on before anything reaches a tag that can never be
#: reused.
REQUIRED_FILES: tuple[str, ...] = ("poll.json", "poll.csv", "model_params.json", "_run.json")

#: Everything `rank`, `grid` and `bootstrap` write, in the fixed names of report
#: 03 §5.3. Present files are published; absent ones are reported, never faked.
RUN_FILES: tuple[str, ...] = (
    "_run.json",
    "backtest_metrics.json",
    "model_params.json",
    "poll.csv",
    "poll.json",
    "predictions.parquet",
    "rank_intervals.csv",
    "rank_intervals.parquet",
    "ratings_grid.csv",
    "ratings_grid.parquet",
    "ratings_hindsight.csv",
    "ratings_hindsight.parquet",
    "ratings_live.csv",
    "ratings_live.parquet",
    "retro_movers.csv",
    "validation.json",
)

#: GitHub's own limits (ADR 0003). Checked before the upload rather than
#: discovered halfway through it.
MAX_ASSET_BYTES = 2 * 1024**3
MAX_ASSETS = 1000

MANIFEST_VERSION = 1


class ReleaseError(RuntimeError):
    """Anything that stops a release from being published."""


class ReleaseExistsError(ReleaseError):
    """The tag is already published. A corrected week gets a NEW tag."""


class MissingArtifactError(ReleaseError):
    """The run directory is not a run directory."""


@dataclass(frozen=True, order=True)
class Asset:
    """One published file: its asset name, where it came from, and its digest."""

    name: str
    source: Path
    bytes: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "bytes": self.bytes, "sha256": self.sha256}


@dataclass(frozen=True)
class Bundle:
    """A staged, hashed, verifiable set of assets for exactly one tag."""

    tag: str
    directory: Path
    assets: tuple[Asset, ...]
    manifest: dict[str, Any]
    missing: tuple[str, ...]

    @property
    def total_bytes(self) -> int:
        return sum(a.bytes for a in self.assets)

    @property
    def manifest_path(self) -> Path:
        return self.directory / MANIFEST_NAME

    @property
    def checksum_path(self) -> Path:
        return self.directory / CHECKSUM_NAME

    @property
    def notes_path(self) -> Path:
        return self.directory / NOTES_NAME

    def manifest_sha256(self) -> str:
        return _sha256(self.manifest_path)


def tag_for(season: int, week: int) -> str:
    """`poll-2023-w15`. The one naming rule, in one place (ADR 0003)."""
    return f"poll-{int(season)}-w{int(week):02d}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_dump(path: Path, payload: Any) -> None:
    """Stable JSON: sorted keys, trailing newline. Same rule as publish/files.py."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MissingArtifactError(f"{path} is missing or unreadable: {error}") from error
    if not isinstance(payload, dict):
        raise MissingArtifactError(f"{path} is not a JSON object")
    return payload


def _extra_files(root: Path | None, prefix: str) -> list[tuple[str, Path]]:
    """Every regular file under `root`, flattened to `<prefix>-<relative-path>`.

    Release assets have no directories, so a tree has to be flattened, and it is
    flattened by rule rather than by knowledge of any particular layout: point
    `--fixtures` at the season directory you published and `--cards` at the
    directory the share cards landed in, and what is there is what is attached.
    """
    if root is None:
        return []
    if not root.exists():
        raise MissingArtifactError(f"{root} does not exist")
    if root.is_file():
        return [(f"{prefix}-{root.name}", root)]
    out: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        relative = path.relative_to(root).as_posix().replace("/", "-")
        out.append((f"{prefix}-{relative}", path))
    return out


def _sweep(directory: Path, keep: set[str]) -> None:
    """Drop files a PREVIOUS staging of this same tag left behind.

    Only ever inside a directory we staged before - the marker is its own
    `manifest.json` - and only files, never directories. Without this, a rerun
    that produces fewer artifacts leaves the old ones sitting beside the new
    manifest that does not list them, which is precisely the kind of quiet
    disagreement between a checksum file and a directory that the checksum file
    exists to prevent.
    """
    if not (directory / MANIFEST_NAME).exists():
        return
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name not in keep and path.name not in BUNDLE_METADATA:
            path.unlink()


def _notes(manifest: dict[str, Any], poll: dict[str, Any]) -> str:
    """The release body. Deterministic: every line is read, none is computed now."""
    top = poll.get("top25") or poll.get("ranking") or []
    lines = [
        f"# The Poll — {manifest['season']} week {manifest['week']}",
        "",
        f"Recipe **{manifest['recipe']}**, ordered by `{manifest.get('headline_ordering')}`.",
        "Every constant that produced these numbers is in `model_params.json`;",
        f"`_run.json` names the commit ({manifest['git_sha'][:12]}), the config hash",
        f"({manifest['config_hash'][:12]}) and the archive digest that made them.",
        "",
        "## Top 5",
        "",
    ]
    for row in top[:5]:
        lines.append(
            f"{row.get('rank')}. {row.get('team')} "
            f"({row.get('wins')}-{row.get('losses')})"
        )
    lines += [
        "",
        "## Verify these bytes",
        "",
        "```bash",
        f"gh release download {manifest['tag']} --repo {manifest['repo']}",
        "sha256sum -c SHA256SUMS",
        "```",
        "",
        "## Read them without cloning anything",
        "",
        "```sql",
        "INSTALL httpfs; LOAD httpfs;",
        "SELECT team, rank, power, resume FROM read_parquet(",
        f"  'https://github.com/{manifest['repo']}/releases/download/"
        f"{manifest['tag']}/ratings_live.parquet')",
        "ORDER BY rank LIMIT 25;",
        "```",
        "",
        f"{manifest['asset_count']} assets, {manifest['total_bytes']:,} bytes. "
        "Immutable: a correction is published as a new tag, never as an edit "
        "(ADR 0003, ADR 0004).",
        "",
    ]
    return "\n".join(lines)


def build(
    run: Path,
    dest: Path | None = None,
    *,
    tag: str | None = None,
    repo: str = DEFAULT_REPO,
    fixtures: Path | None = None,
    cards: Path | None = None,
) -> Bundle:
    """Stage and hash every asset for one week. No network, no `gh`, no upload.

    `dest` defaults to `<run>/release`; the bundle lands in `<dest>/<tag>/`. The
    staging directory is a build artifact and is rebuilt in place - immutability
    is a property of the RELEASE, which `publish` refuses to touch when the tag
    exists, not of a directory on somebody's laptop.
    """
    run = Path(run)
    record = _read_json(run / "_run.json")
    params = _read_json(run / "model_params.json")
    poll = _read_json(run / "poll.json")

    missing_required = [name for name in REQUIRED_FILES if not (run / name).exists()]
    if missing_required:
        raise MissingArtifactError(
            f"{run} is missing {missing_required}. A release is the four run files at "
            "minimum (ADR 0003); run `cfbpoll rank --out <dir>` first."
        )

    season = int(record["season"])
    week = int(record["through_week"])
    recipe = str(record.get("recipe", "house"))
    if tag is None:
        # AN ALTERNATE LENS MAY NOT INHERIT THE HOUSE WEEK'S NAME. Only `house`
        # is the published poll (ADR 0011); publishing `just-win` to
        # poll-2023-w15 would put a different value system behind the one URL
        # every downstream reader treats as THE poll for that week.
        if recipe != "house":
            raise ReleaseError(
                f"this run is recipe {recipe!r}, an ALTERNATE LENS, and only the house "
                f"poll may be published as {tag_for(season, week)} (ADR 0011). Pass an "
                "explicit --tag if you mean to publish it under its own name."
            )
        tag = tag_for(season, week)

    named: list[tuple[str, Path]] = [
        (name, run / name) for name in RUN_FILES if (run / name).exists()
    ]
    missing = tuple(sorted(set(RUN_FILES) - {name for name, _ in named}))
    named += _extra_files(fixtures, "fixtures")
    named += _extra_files(cards, "card")

    seen: dict[str, Path] = {}
    for name, source in named:
        if name in seen:
            raise ReleaseError(
                f"two files claim the asset name {name!r}: {seen[name]} and {source}"
            )
        seen[name] = source

    directory = Path(dest) if dest is not None else (run / "release")
    directory = directory / tag
    directory.mkdir(parents=True, exist_ok=True)
    _sweep(directory, {name for name, _ in named})

    assets: list[Asset] = []
    for name, source in sorted(named):
        staged = directory / name
        shutil.copyfile(source, staged)
        digest = _sha256(staged)
        size = staged.stat().st_size
        if size > MAX_ASSET_BYTES:
            raise ReleaseError(
                f"{name} is {size:,} bytes; GitHub caps a release asset at "
                f"{MAX_ASSET_BYTES:,} (ADR 0003)"
            )
        assets.append(Asset(name=name, source=source, bytes=size, sha256=digest))

    if len(assets) > MAX_ASSETS:
        raise ReleaseError(
            f"{len(assets)} assets; GitHub caps a release at {MAX_ASSETS} (ADR 0003)"
        )

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "spec": "research report 03 §5.2; docs/adr/0003-storage.md",
        "tag": tag,
        "repo": repo,
        "season": season,
        "week": week,
        "season_type": str((params.get("through") or {}).get("season_type", "regular")),
        "recipe": recipe,
        "headline_ordering": params.get("headline_ordering"),
        "provisional": bool(poll.get("provisional", False)),
        "git_sha": str(record.get("git_sha", "unknown")),
        "config_hash": str(record.get("config_hash", "unknown")),
        "recipe_config_sha256": record.get("recipe_config_sha256"),
        "archive_manifest_sha256": record.get("archive_manifest_sha256"),
        "fit_window_sha256": record.get("fit_window_sha256"),
        "asset_count": len(assets),
        "total_bytes": sum(a.bytes for a in assets),
        "assets": [a.as_dict() for a in assets],
        "not_present_in_run": list(missing),
    }

    bundle = Bundle(
        tag=tag,
        directory=directory,
        assets=tuple(assets),
        manifest=manifest,
        missing=missing,
    )
    _json_dump(bundle.manifest_path, manifest)
    bundle.checksum_path.write_text(
        "".join(f"{a.sha256}  {a.name}\n" for a in assets), encoding="utf-8"
    )
    bundle.notes_path.write_text(_notes(manifest, poll), encoding="utf-8")
    return bundle


def verify(bundle: Bundle) -> list[str]:
    """Re-read every staged byte and re-hash it. Returns the disagreements.

    Not ceremony: the manifest is what a stranger checks the download against,
    so it has to be a digest of the file that is actually in the directory
    rather than of the frame we had in memory a moment earlier.
    """
    problems: list[str] = []
    for asset in bundle.assets:
        staged = bundle.directory / asset.name
        if not staged.exists():
            problems.append(f"{asset.name}: staged file is missing")
            continue
        if staged.stat().st_size != asset.bytes:
            problems.append(f"{asset.name}: size changed after staging")
            continue
        digest = _sha256(staged)
        if digest != asset.sha256:
            problems.append(f"{asset.name}: sha256 {digest} != manifest {asset.sha256}")
    return problems


def _run_gh(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gh", *args], capture_output=True, text=True, check=False
        )
    except FileNotFoundError as error:  # pragma: no cover - environment dependent
        raise ReleaseError(
            "`gh` is not on PATH. The GitHub CLI is what uploads release assets "
            "(report 03 §5.2); `--dry-run` builds and verifies the bundle without it."
        ) from error


#: Injected rather than imported at call sites, so a test can answer for `gh`
#: without a network, a token or a monkeypatched subprocess. Resolved at CALL
#: time (`runner or _run_gh`), never bound as a default argument, because a
#: default is captured when the function is defined and would silently ignore
#: anyone who replaced it afterwards.
Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def release_exists(
    tag: str,
    repo: str = DEFAULT_REPO,
    runner: Runner | None = None,
) -> bool:
    """Does this tag already have a release? The immutability check.

    `gh release view` exits 1 with "release not found" when it does not exist,
    which is a real answer; any OTHER failure (no auth, no network, no repo) is
    NOT an answer and raises, because "we could not tell" must never be read as
    "it is safe to publish".
    """
    done = (runner or _run_gh)(["release", "view", tag, "--repo", repo, "--json", "tagName"])
    if done.returncode == 0:
        return True
    blob = f"{done.stdout}\n{done.stderr}".lower()
    if "release not found" in blob or "not found" in blob:
        return False
    raise ReleaseError(
        f"could not determine whether {repo}@{tag} exists (gh exit {done.returncode}): "
        f"{done.stderr.strip() or done.stdout.strip()}"
    )


def publish(
    out: Path,
    tag: str | None = None,
    *,
    repo: str = DEFAULT_REPO,
    dest: Path | None = None,
    fixtures: Path | None = None,
    cards: Path | None = None,
    dry_run: bool = False,
    runner: Runner | None = None,
) -> tuple[Bundle, str | None]:
    """Build the bundle and, unless `dry_run`, create the release. Returns (bundle, url).

    The order is not negotiable: build, verify, THEN ask whether the tag exists,
    THEN upload. A bundle that cannot be built is a failure that costs nothing;
    a tag that is already published is a refusal; and the upload happens once,
    with every asset in one `gh release create`, so a half-published release is
    not a state this can reach on the happy path.
    """
    bundle = build(Path(out), dest, tag=tag, repo=repo, fixtures=fixtures, cards=cards)
    problems = verify(bundle)
    if problems:
        raise ReleaseError(
            f"the staged bundle does not match its own manifest: {problems}"
        )
    if dry_run:
        return bundle, None

    if release_exists(bundle.tag, repo, runner):
        raise ReleaseExistsError(
            f"{repo}@{bundle.tag} already exists. A published week is IMMUTABLE: this "
            "command will not overwrite it and has no --force. If the week needs "
            "correcting, publish a new tag (`--tag "
            f"{bundle.tag}-r2`) so both the original and the correction stay on the "
            "record (ADR 0003, ADR 0004)."
        )

    done = (runner or _run_gh)(
        [
            "release",
            "create",
            bundle.tag,
            "--repo",
            repo,
            "--title",
            f"The Poll — {bundle.manifest['season']} week {bundle.manifest['week']}",
            "--notes-file",
            str(bundle.notes_path),
            *[str(bundle.directory / a.name) for a in bundle.assets],
            str(bundle.checksum_path),
            str(bundle.manifest_path),
        ]
    )
    if done.returncode != 0:
        raise ReleaseError(
            f"gh release create failed (exit {done.returncode}): "
            f"{done.stderr.strip() or done.stdout.strip()}"
        )
    url = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    return bundle, url or f"https://github.com/{repo}/releases/tag/{bundle.tag}"
