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

R2 IS NOT YET PROVISIONED. The push target is a stub: no Cloudflare account, no
bucket, no credentials. The zero-new-accounts alternative on the table is the
Hostinger VPS disk plus one off-box copy (report 03 §5.2).

STATUS: SCAFFOLD.
"""

from __future__ import annotations

from typing import Any

R2_BUCKET = "cfb-poll-archive"  # PLANNED, not created. See report 03 §5.2.


def write_raw(payload: bytes, endpoint: str, params: dict[str, Any], root: Any) -> Any:
    """Write one raw response immutably and return its manifest entry."""
    raise NotImplementedError("ingest.archive.write_raw - scaffold; see report 01 §5.4")


def verify(manifest_path: Any) -> bool:
    """sha256-check every file against the manifest. Mismatch is a hard failure."""
    raise NotImplementedError("ingest.archive.verify - scaffold; see report 01 §5.4")


def push_r2(scope: str = "cfbd") -> None:
    """Push the private archive class to Cloudflare R2 (append-only, never overwrite)."""
    raise NotImplementedError("ingest.archive.push_r2 - scaffold; R2 not yet provisioned")
