#!/usr/bin/env bash
#
# THE SECOND COPY OF THE PRIVATE CFBD ARCHIVE. Run from the Mac, pulls from the
# VPS, never the other way round.
#
# John ruled on 2026-08-17 that the CFBD raw archive gets no Cloudflare R2 bucket
# (docs/adr/0015-cfbd-archive-no-r2.md). Durability therefore comes from two
# machines rather than from an object store, and this script is the second
# machine. It is a runbook you can execute, not a daemon: nothing is installed,
# nothing runs on a schedule, and the only way bytes move is a person typing
# this. That is a deliberate trade - a daemon that silently stops is exactly the
# failure mode this project keeps meeting.
#
# WHY PULL AND NOT PUSH. The VPS is the machine holding the key and doing the
# weekly writes, so it is the origin. A pull means the Mac needs no inbound
# access and the VPS needs no credential for the Mac; the blast radius of a
# compromised laptop is "somebody read a copy", not "somebody deleted the
# original".
#
# WHY --ignore-existing AND NEVER --delete. ADR 0003: "Never overwrite. A re-pull
# writes a new timestamped file, which makes late upstream stat corrections
# observable." An append-only archive syncs by adding files and by nothing else.
# A `--delete` here would let one bad afternoon on the VPS erase the only other
# copy, which is the precise thing having two copies is for.
#
# USAGE
#   ops/bin/pull-cfbd-archive.sh                  # sync, then verify
#   DRY_RUN=true ops/bin/pull-cfbd-archive.sh     # show what would move
#   VERIFY_ONLY=true ops/bin/pull-cfbd-archive.sh # re-hash the local copy only
#
# CONFIGURE ONCE, in your shell profile or on the command line:
#   VPS_HOST=cfbpoll@vps.example.com   (an ssh alias from ~/.ssh/config is better)
#   VPS_ARCHIVE=/opt/cfb-poll/archive/cfbd
#   LOCAL_ARCHIVE=archive/cfbd

set -euo pipefail

VPS_HOST="${VPS_HOST:-}"
VPS_ARCHIVE="${VPS_ARCHIVE:-/opt/cfb-poll/archive/cfbd}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCAL_ARCHIVE="${LOCAL_ARCHIVE:-$REPO_ROOT/archive/cfbd}"
DRY_RUN="${DRY_RUN:-false}"
VERIFY_ONLY="${VERIFY_ONLY:-false}"

say() { printf '\n=== %s\n' "$*"; }

if [ "$VERIFY_ONLY" != "true" ]; then
  if [ -z "$VPS_HOST" ]; then
    echo "VPS_HOST is not set. Example:" >&2
    echo "  VPS_HOST=cfbpoll@vps.example.com ops/bin/pull-cfbd-archive.sh" >&2
    echo "An ssh alias in ~/.ssh/config is better than a hostname here, because it" >&2
    echo "keeps the port, the key and the user out of shell history." >&2
    exit 2
  fi

  mkdir -p "$LOCAL_ARCHIVE"

  RSYNC_ARGS=(
    --archive              # times, modes, symlinks: the archive is content-addressed
    --human-readable
    --itemize-changes      # print exactly which files arrived
    --partial              # a dropped connection costs nothing
    --ignore-existing      # append-only: never overwrite a byte we already hold
    --prune-empty-dirs
    -e ssh
  )
  if [ "$DRY_RUN" = "true" ]; then
    RSYNC_ARGS+=(--dry-run)
    say "DRY RUN. Nothing will be written."
  fi

  say "Pull $VPS_HOST:$VPS_ARCHIVE/ -> $LOCAL_ARCHIVE/"
  rsync "${RSYNC_ARGS[@]}" "$VPS_HOST:$VPS_ARCHIVE/" "$LOCAL_ARCHIVE/"
fi

if [ "$DRY_RUN" = "true" ]; then
  say "Dry run: skipping verification, since nothing moved."
  exit 0
fi

# THE COPY IS ONLY A BACKUP IF IT IS READABLE. rsync proves bytes arrived; the
# manifests prove they are the bytes CFBD sent. Re-hashing is cheap here (tens of
# MB a season) and is the difference between a backup and a directory.
say "Verify every local file against its _manifest.json"
"${UV:-uv}" run python "$REPO_ROOT/ops/bin/verify_cfbd_archive.py" "$LOCAL_ARCHIVE"

say "Done. The private CFBD archive now exists on two machines."
echo "    Neither copy is in git: archive/ is gitignored, and CFBD terms section 3"
echo "    bar republishing raw API responses. That is why this script exists."
