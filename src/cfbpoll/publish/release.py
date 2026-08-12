"""Publish out/ as immutable GitHub Release assets.

Specified by report 03 §5.2.

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

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from pathlib import Path


def publish(out: Path, tag: str) -> str:
    """Create or update the release and attach every artifact. Returns the release URL."""
    raise NotImplementedError("publish.release.publish - scaffold; see report 03 §5.2")
