#!/usr/bin/env python3
"""Re-hash every file in a CFBD archive copy against its `_manifest.json`.

Run it through the project environment (`uv run python ops/bin/verify_cfbd_archive.py`)
or with any interpreter that can import `cfbpoll`; the `sys.path` line below is
what makes the second case work from a bare checkout.

WHY THIS EXISTS. John's ruling of 2026-08-17 removed the R2 bucket, so the
private CFBD archive's durability comes from living on two machines instead of
in an object store (docs/adr/0015-cfbd-archive-no-r2.md). Two machines is only
durability if the second copy is known-good, and rsync proves that bytes arrived,
not that they are the bytes CFBD sent. This proves the second one.

It is a thin wrapper: `cfbpoll.ingest.archive.verify` already does the check for
one manifest and raises on the first mismatch. All this adds is the walk, a
count, and an exit code an ops script can branch on. No new hashing logic, so
there is nothing here that can disagree with the writer.

    ops/bin/verify_cfbd_archive.py archive/cfbd

Exit 0 when every listed file is present and correct, 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from cfbpoll.ingest import archive  # noqa: E402


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else REPO_ROOT / "archive" / "cfbd"
    if not root.is_dir():
        print(f"no archive at {root}", file=sys.stderr)
        return 1

    manifests = sorted(root.rglob(archive.MANIFEST_NAME))
    if not manifests:
        print(f"no {archive.MANIFEST_NAME} anywhere under {root}.", file=sys.stderr)
        print(
            "An archive with no manifests is a pile of files. Either the sync "
            "pulled nothing, or it pulled from the wrong directory.",
            file=sys.stderr,
        )
        return 1

    checked = 0
    failures: list[str] = []
    for manifest in manifests:
        entries = archive.manifest_entries(manifest)
        try:
            archive.verify(manifest)
        except (RuntimeError, FileNotFoundError) as exc:
            failures.append(f"{manifest.parent.relative_to(root)}: {exc}")
            continue
        checked += len(entries)
        print(f"  ok  {manifest.parent.relative_to(root)}  ({len(entries)} files)")

    print(f"\n{checked} files verified across {len(manifests)} buckets under {root}")
    if failures:
        print(f"\n{len(failures)} bucket(s) FAILED:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nA mismatch is a hard failure by design, not a warning. Do not "
            "'fix' it by copying over the local file: find out which copy is "
            "wrong first, because the archive is append-only and the whole point "
            "of the digest is that nobody has to trust either machine.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
