#!/usr/bin/env bash
#
# THE SUNDAY JOB. One implementation, three clocks.
#
# ADR 0002's fallback design says the VPS runs "the identical job ... same
# --guard-protected code path; no second implementation", and the only way to
# actually get that is for there to be exactly one script. This is it.
# .github/workflows/weekly.yml calls it. ops/systemd/cfb-poll-weekly.service
# calls it. A change to the publication sequence is a change to this file, and
# there is nowhere else for the two paths to drift apart.
#
# IT NEVER PUBLISHES BY ACCIDENT. Three separate things have to be true:
#   1. `cfbpoll guard` says the trigger is armed in ops/arming.toml, and
#   2. the guard resolves a week, and that week is not already published, and
#   3. PUBLISH=true is passed in.
# Any one of them false and this exits 0 having written nothing. Exit 0 is
# correct: "there was nothing to do" is the expected outcome on most Sundays,
# and a job that goes red for it is a job somebody mutes.
#
# ENVIRONMENT, all optional, all with defaults:
#
#   TRIGGER=manual|n8n|schedule|vps_timer   who is asking (default: manual)
#   SEASON=                                 blank = ops.guard.current_season()
#   WEEK=                                   blank = CFBD /calendar (needs the key)
#   PUBLISH=false                           false = fit and write out/, publish nothing
#   DRY_RUN=false                           true  = print every command, run none
#   FIXTURES=../sandbox/cfb-poll-data       the published JSON tree
#   OUT=out                                 the run directory
#   PUBLISHED_URL=                          base URL of the published tree, if served
#   SEED=20260812  DRAWS=1000               bootstrap determinism
#   STRICT_PREFLIGHT=true                   refuse to start a publication with stub verbs
#   SKIP_SYNC=false                         true = trust the existing .venv
#
# THE ONE SECRET. CFBD_API_KEY, and only for two things: resolving the live week
# (`/calendar`) and pulling the week's raw results. Absent, this degrades to the
# MIT SportsDataverse archive and says so, because a fork gets no secrets and
# must still produce a ranking. It is read from the environment or from the
# repo's gitignored .env, and it is never echoed.

set -euo pipefail

TRIGGER="${TRIGGER:-manual}"
SEASON="${SEASON:-}"
WEEK="${WEEK:-}"
PUBLISH="${PUBLISH:-false}"
DRY_RUN="${DRY_RUN:-false}"
FIXTURES="${FIXTURES:-../sandbox/cfb-poll-data}"
OUT="${OUT:-out}"
PUBLISHED_URL="${PUBLISHED_URL:-}"
SEED="${SEED:-20260812}"
DRAWS="${DRAWS:-1000}"
STRICT_PREFLIGHT="${STRICT_PREFLIGHT:-true}"
SKIP_SYNC="${SKIP_SYNC:-false}"
UV="${UV:-uv}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Single-threaded BLAS is not a performance setting, it is the determinism
# contract: multi-threaded reductions sum in a nondeterministic order and the
# replay job asserts byte-equality. Every make target sets these; this script is
# not a make target, so it sets them itself rather than inheriting a hope.
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTHONHASHSEED=0

say()  { printf '\n=== %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }

run() {
  if [ "$DRY_RUN" = "true" ]; then
    printf '    [dry-run] %s\n' "$*"
    return 0
  fi
  printf '    $ %s\n' "$*"
  "$@"
}

# Which verbs are still stubs, asked once and reused. Derived from the source by
# ops/preflight.py, so implementing a verb un-skips its step here with no edit.
MISSING="$($UV run python -c \
  "from cfbpoll.ops import preflight; print('|'.join(preflight.missing(required_only=False)))")"

stubbed() {
  case "|$MISSING|" in
    *"|$1|"*) return 0 ;;
    *) return 1 ;;
  esac
}

# A step whose verb does not exist yet: say so once, loudly, in the runner's log
# and in the Actions annotation stream, and carry on. The alternative is a job
# that always fails at the same step and teaches everyone to ignore it.
step() {
  local verb="$1"; shift
  if stubbed "$verb"; then
    note "SKIPPED: \`cfbpoll $verb\` is still a stub (cli._stub). See \`cfbpoll preflight\`."
    printf '::warning title=stubbed verb::cfbpoll %s is not implemented; the Sunday job skipped it\n' \
      "$verb"
    return 0
  fi
  run "$@"
}

say "cfb-poll weekly | trigger=$TRIGGER publish=$PUBLISH dry_run=$DRY_RUN"
note "repo:     $REPO_ROOT"
note "out:      $OUT"
note "fixtures: $FIXTURES"
note "stubs:    ${MISSING:-none}"

if [ "$SKIP_SYNC" != "true" ]; then
  say "Sync the locked environment"
  run $UV sync --locked
fi

say "Preflight: which verbs the job needs, and which are still stubs"
if [ "$PUBLISH" = "true" ] && [ "$STRICT_PREFLIGHT" = "true" ]; then
  # Refuse BEFORE the 0.55 GB download and the fit, not after. A publication run
  # that cannot finish a publication should cost seconds, not forty minutes.
  run $UV run cfbpoll preflight --fail-on-missing
else
  run $UV run cfbpoll preflight
fi

say "Guard: is this trigger armed, and is the week already published?"
# `mktemp -t NAME` means different things on GNU and BSD. The explicit template
# form means the same thing on the Ubuntu runner and on the Mac.
GUARD_FILE="$(mktemp "${TMPDIR:-/tmp}/cfbpoll-guard.XXXXXX")"
trap 'rm -f "$GUARD_FILE"' EXIT

GUARD_ARGS=(--trigger "$TRIGGER" --outputs "$GUARD_FILE" --fixtures "$FIXTURES")
if [ -n "$SEASON" ]; then GUARD_ARGS+=(--season "$SEASON"); fi
if [ -n "$WEEK" ]; then GUARD_ARGS+=(--week "$WEEK"); fi
if [ -n "$PUBLISHED_URL" ]; then GUARD_ARGS+=(--published-url "$PUBLISHED_URL"); fi

if [ "$DRY_RUN" = "true" ]; then
  # The guard is read-only and cheap, so a dry run still asks it for real: the
  # whole point of the rehearsal is to find out what the decision WOULD be.
  printf '    $ %s\n' "$UV run cfbpoll guard ${GUARD_ARGS[*]}"
fi
$UV run cfbpoll guard "${GUARD_ARGS[@]}"

read_guard() { grep -m1 "^$1=" "$GUARD_FILE" | cut -d= -f2- || true; }
SHOULD_RUN="$(read_guard should_run)"
SEASON="$(read_guard season)"
WEEK="$(read_guard week)"

if [ "$SHOULD_RUN" != "true" ]; then
  say "Nothing to do. Exiting 0."
  note "The guard's reasons are printed above. This is the normal outcome for two"
  note "of the three clocks on any Sunday where the first one worked."
  exit 0
fi

say "Season $SEASON, week $WEEK"

say "Archive: the MIT SportsDataverse leg, sha256-verified (no key needed)"
step "archive sync" $UV run cfbpoll archive sync --source sportsdataverse --verify

say "Ingest: the private CFBD leg, quota-guarded"
if [ -n "${CFBD_API_KEY:-}" ] || [ -f "$REPO_ROOT/.env" ]; then
  step "ingest cfbd" $UV run cfbpoll ingest cfbd \
    --season "$SEASON" --week "$WEEK" --abort-if-remaining-calls-below 200
else
  note "No CFBD key (expected in a fork). Running on the MIT archive alone."
  note "Fewer games, a real ranking, and every artifact says which archives it read."
fi

# THE CFBD RAW ARCHIVE STAYS ON DISK. John's ruling of 2026-08-17 removed the R2
# leg (docs/adr/0015-cfbd-archive-no-r2.md). archive/cfbd/ lives on the VPS disk
# and is pulled to the Mac by ops/bin/pull-cfbd-archive.sh. There is deliberately
# no `cfbpoll archive push` call in this job any more.

say "Data-quality gate: halt and publish nothing on failure"
step "validate" $UV run cfbpoll validate --season "$SEASON" --week "$WEEK"

say "Leakage audit: prove no banned input reached a design matrix"
step "audit-features" $UV run cfbpoll audit-features --season "$SEASON" --fail-on-banned

say "Fit L1-L4 and rank"
step "rank" $UV run cfbpoll rank --config configs/default.toml \
  --season "$SEASON" --through-week "$WEEK" --seed "$SEED" --draws "$DRAWS" --out "$OUT"

say "Bootstrap the 90% rank intervals"
step "bootstrap" $UV run cfbpoll bootstrap --season "$SEASON" \
  --draws "$DRAWS" --jobs 4 --seed "$SEED" --out "$OUT"

if [ "$PUBLISH" != "true" ]; then
  say "PUBLISH=false: the board is in $OUT and nothing was published."
  exit 0
fi

say "Publish the JSON fixture tree the site reads"
step "publish fixtures" $UV run cfbpoll publish fixtures --from "$OUT" --out "$FIXTURES"

say "Publish the share cards"
step "publish cards" $UV run cfbpoll publish cards --from "$OUT" --out "$OUT/share"

say "Publish the immutable release asset (the canonical copy of this week)"
step "publish release" $UV run cfbpoll publish release --out "$OUT"

say "Load the serving tables (skips cleanly with no DATABASE_URL)"
step "publish postgres" $UV run cfbpoll publish postgres --from "$OUT"

say "Done. Season $SEASON week $WEEK published."
