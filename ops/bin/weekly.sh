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
#   RELEASE_STAGE=.cache/release            where the release bundle is staged.
#                                           MUST NOT be inside OUT; see below.
#   PUBLISHED_URL=                          base URL of the published tree, if served
#   SEED=20260812  DRAWS=1000               bootstrap determinism
#   STRICT_PREFLIGHT=true                   refuse to start a publication with stub verbs
#   STRICT_VALIDATE=false                   treat a SKIPPED data-quality check as failure
#   SKIP_SYNC=false                         true = trust the existing .venv
#   SKIP_DELIVERY=false                     true = never touch the site repo at all
#
# DELIVERY. After a successful publishing run this pushes the fixture tree into
# the site repository, WHICH AUTO-DEPLOYS thepoll.ai. It is gated three ways: the
# `[steps] delivery` line in ops/arming.toml (committed false), the presence of
# SANDBOX_CONTENTS_PAT, and SKIP_DELIVERY here. See ops/bin/deliver-fixtures.sh
# for the rest of its environment, and note that when delivery is on, FIXTURES
# below is REPLACED by a path inside the site clone.
#
# WHY STRICT_VALIDATE DEFAULTS TO FALSE. `cfbpoll validate --strict` turns a
# SKIPPED check into a failure, and four of its eight checks read the private
# CFBD archive or last week's run directory. On week 1 there is no last week,
# and in a fork there is no CFBD archive at all, so strict-by-default would fail
# every season opener and every fork for reasons that are not data-quality
# problems. Turn it on once the season is running on a machine that has the key
# and a previous week; the runbook says so too.
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
STRICT_VALIDATE="${STRICT_VALIDATE:-false}"
RELEASE_STAGE="${RELEASE_STAGE:-.cache/release}"
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

# A staged release bundle carries a poll.json, and `publish fixtures --from OUT`
# reads any subdirectory holding one as a run. Staging inside OUT therefore
# invents a week. Refuse it here rather than discovering it in the published
# index, which is where it would otherwise surface and where it would look like
# anything except a staging-path bug.
#
# The comparison is LEXICAL and never touches the filesystem, deliberately.
# Resolving with `cd` fails on a directory that does not exist yet, and OUT
# normally does not exist this early in the run - which would collapse the
# prefix to the empty string and make this refuse every path there is. A safety
# check whose failure mode is "always fires" gets deleted by the next person.
_abspath() { case "$1" in /*) printf '%s' "$1" ;; *) printf '%s' "$PWD/$1" ;; esac; }
_out_abs="$(_abspath "$OUT")";           _out_abs="${_out_abs%/}"
_release_abs="$(_abspath "$RELEASE_STAGE")"; _release_abs="${_release_abs%/}"
case "$_release_abs/" in
  "$_out_abs"/*)
    echo "RELEASE_STAGE ($RELEASE_STAGE) is inside OUT ($OUT)." >&2
    echo "A staged bundle carries a poll.json and 'publish fixtures --from $OUT'" >&2
    echo "would read it as an extra run. Stage it somewhere else." >&2
    exit 2
    ;;
esac

say "cfb-poll weekly | trigger=$TRIGGER publish=$PUBLISH dry_run=$DRY_RUN"
note "repo:     $REPO_ROOT"
note "out:      $OUT"
note "fixtures: $FIXTURES"
note "release:  $RELEASE_STAGE (staged outside $OUT on purpose)"
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
SEASON_TYPE="$(read_guard season_type)"

if [ "$SHOULD_RUN" != "true" ]; then
  say "Nothing to do. Exiting 0."
  note "The guard's reasons are printed above. This is the normal outcome for two"
  note "of the three clocks on any Sunday where the first one worked."
  exit 0
fi

say "Season $SEASON, week $WEEK ($SEASON_TYPE)"

# A KNOWN LIMIT, NAMED RATHER THAN PAPERED OVER. The guard resolves the season
# TYPE from /calendar and `cfbpoll validate` takes it, but `cfbpoll rank` has no
# --season-type option: it takes --through-week and nothing else. So a
# postseason Sunday ranks through regular week N, which is the behaviour the
# rank verb has always had. If the postseason needs its own board, that is a
# change to `rank`, not something this runner can paper over with a flag that
# does not exist.
if [ "$SEASON_TYPE" != "regular" ]; then
  printf '::warning title=season type::guard resolved season_type=%s; `cfbpoll rank` has no --season-type and will rank through regular week %s\n' \
    "$SEASON_TYPE" "$WEEK"
fi

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

say "Leakage audit: prove no banned input reached a design matrix"
# --through-week, not the bare season: the job ranks through $WEEK, so auditing
# any other window audits a set of matrices this run never builds.
step "audit-features" $UV run cfbpoll audit-features \
  --season "$SEASON" --through-week "$WEEK" --fail-on-banned

say "Fit L1-L4 and rank"
step "rank" $UV run cfbpoll rank --config configs/default.toml \
  --season "$SEASON" --through-week "$WEEK" --seed "$SEED" --draws "$DRAWS" --out "$OUT"

# THE GATE RUNS AFTER THE FIT AND BEFORE ANY PUBLICATION, and that ordering is
# forced rather than chosen: `cfbpoll validate --from` wants THIS WEEK'S RUN
# DIRECTORY, because the bounded week-over-week movement check compares this
# board against last week's. There is no run directory before `rank` writes one.
#
# "Halt and publish nothing on failure" is unchanged by the move. Everything
# that publishes is below this line, and `set -e` means a non-zero verdict stops
# the script before any of it. What the fit costs when the gate fails is a few
# minutes of CPU, which is the right price for a check that can see the board.
say "Data-quality gate: halt and publish nothing on failure"
VALIDATE_ARGS=(--season "$SEASON" --week "$WEEK" --season-type "$SEASON_TYPE" --from "$OUT")
if [ "$STRICT_VALIDATE" = "true" ]; then
  VALIDATE_ARGS+=(--strict)
fi
step "validate" $UV run cfbpoll validate "${VALIDATE_ARGS[@]}"

say "Bootstrap the 90% rank intervals"
# --through-week is NOT optional here even though the flag is. Blank means
# "latest completed week", which is not necessarily the week just ranked, and an
# interval computed over a different window than the board it decorates is a
# published number that describes nothing.
step "bootstrap" $UV run cfbpoll bootstrap --season "$SEASON" --through-week "$WEEK" \
  --draws "$DRAWS" --jobs 4 --seed "$SEED" --out "$OUT"

if [ "$PUBLISH" != "true" ]; then
  say "PUBLISH=false: the board is in $OUT and nothing was published."
  exit 0
fi

# DELIVERY, PART ONE OF TWO: clone the site repo and publish straight into it.
#
# This has to happen BEFORE `publish fixtures`, and the reason is not obvious
# enough to leave implicit. `publish fixtures` rebuilds index.json from whatever
# is on disk at its destination. A GitHub runner starts empty, so publishing one
# week into a fresh directory yields an index naming one week and one season -
# and copying that onto the site would erase 2023 and 2025 from the season strip
# while every week document sat there untouched. Publishing into the real tree
# is what makes the index right.
#
# THE REMOTE IS NOT TOUCHED HERE. This clones and writes locally. Nothing
# reaches the site repository until `deliver-fixtures.sh push` below, which runs
# only after the gate and the release have both passed.
if [ "${SKIP_DELIVERY:-false}" != "true" ]; then
  say "Delivery: clone the site repo so the index is rebuilt against the real tree"
  # No `|| true`. An empty result means "delivery is disarmed or unconfigured",
  # which deliver-fixtures.sh reports by exiting 0 with no stdout. A non-zero
  # exit means the clone actually failed, and that must stop the job: a run that
  # quietly falls back to the local tree would report success while the site
  # never moved, which is the silent failure this whole design exists to refuse.
  DELIVERY_FIXTURES="$(ops/bin/deliver-fixtures.sh prepare)"
  if [ -n "$DELIVERY_FIXTURES" ]; then
    FIXTURES="$DELIVERY_FIXTURES"
    note "publishing into the site clone: $FIXTURES"
  else
    note "not delivering; publishing to the local tree: $FIXTURES"
  fi
fi

say "Publish the JSON fixture tree the site reads"
step "publish fixtures" $UV run cfbpoll publish fixtures --from "$OUT" --out "$FIXTURES"

say "Publish the share cards"
step "publish cards" $UV run cfbpoll publish cards --from "$OUT" --out "$OUT/share"

say "Publish the immutable release asset (the canonical copy of this week)"
# --from is the RUN DIRECTORY; --out is where the bundle is STAGED. Getting
# these the wrong way round is not a cosmetic error: the verb's own default
# stages into `<--from>/release`, and a staged bundle carries a poll.json, so
# leaving it inside out/ hands `publish fixtures --from out` a directory it will
# read as an extra run. That misfire is invisible until a week appears in the
# published index that nobody ranked. RELEASE_STAGE therefore lives outside
# out/, under the already-gitignored .cache/.
#
# The fixture tree and the cards are attached so the release asset is genuinely
# the canonical copy of the week rather than a partial one, which is what ADR
# 0003 meant by it and what makes it a live candidate for the delivery gap.
step "publish release" $UV run cfbpoll publish release \
  --from "$OUT" --out "$RELEASE_STAGE" \
  --fixtures "$FIXTURES/$SEASON" --cards "$OUT/share"

# DELIVERY, PART TWO OF TWO: commit and push. THE SITE DEPLOYS FROM THIS.
#
# ITS POSITION IN THE FILE IS THE REQUIREMENT. Everything that can say "no" has
# already run: the guard, the leakage audit, the data-quality gate and the
# release bundle. `set -e` means any one of them failing ends the script here,
# with the site repository untouched, because up to this line delivery has only
# ever written to a scratch clone.
if [ "${SKIP_DELIVERY:-false}" != "true" ]; then
  say "Delivery: push the published tree to the site repo (THIS DEPLOYS THE SITE)"
  SEASON="$SEASON" WEEK="$WEEK" SEASON_TYPE="$SEASON_TYPE" \
    ops/bin/deliver-fixtures.sh push
fi

say "Load the serving tables (skips cleanly with no DATABASE_URL)"
step "publish postgres" $UV run cfbpoll publish postgres --from "$OUT"

say "Done. Season $SEASON week $WEEK published."
