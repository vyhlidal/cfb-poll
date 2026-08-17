#!/usr/bin/env bash
#
# THE DELIVERY STEP. The published fixture tree, into the site repository.
#
# John ruled the delivery gap on 2026-08-17: GitHub's robot holds the key. So a
# publishing run pushes `<FIXTURES>` into github.com/vyhlidal/sandbox under
# `cfb-poll-data/`, using a second fine-grained PAT scoped to that repository and
# nothing else.
#
# PUSHING TO THAT REPO DEPLOYS THE PUBLIC SITE. sandbox's `main` auto-deploys, so
# a successful push here is thepoll.ai changing a minute later. There is no
# staging environment between this script and the internet. Everything below is
# shaped by that one fact.
#
# ---------------------------------------------------------------- two subcommands
#
#   prepare   Clone the site repo and print, on STDOUT, the directory the weekly
#             job should publish its fixtures INTO. Prints nothing if delivery is
#             disarmed or unconfigured, which is how the caller knows to fall
#             back to its own FIXTURES. All logging goes to stderr.
#
#   push      Commit and push whatever `publish fixtures` wrote into that clone.
#
# WHY IT IS TWO STEPS AND NOT ONE, which is the least obvious decision here.
#
# `publish fixtures` rebuilds index.json from WHATEVER IS ON DISK in its
# destination. A GitHub runner starts empty, so publishing one week into a fresh
# directory produces an index listing exactly one week and one season. Copying
# that over the site's index.json would delete 2023 and 2025 from the site's
# index while every week document sat there untouched - a silent, total loss of
# the season strip, caused by a step that looked like it only added a file.
#
# So the clone happens BEFORE the publish, and the publish writes straight into
# the real tree. `rebuild_index` then sees every season it should see, and the
# thing we push is a tree that was correct when it was built rather than a
# fragment we hoped would merge.
#
# THE REMOTE IS UNTOUCHED UNTIL `push`. Cloning and writing into a local working
# copy changes nothing anybody can see. That is what lets the caller run
# `prepare` early - it has to, for the reason above - while still honouring the
# rule that a failed data-quality gate leaves the site repository alone. If
# `validate` or `publish release` fails, `set -e` in the caller means `push`
# never runs, and the only casualty is a temporary directory.
#
# ---------------------------------------------------------------- environment
#
#   SANDBOX_CONTENTS_PAT   the fine-grained PAT. Contents read+write on
#                          vyhlidal/sandbox and NOTHING else. Absent => skip.
#   SANDBOX_REMOTE         default https://github.com/vyhlidal/sandbox.git
#                          A local path here is how the rehearsal works.
#   SANDBOX_BRANCH         default main
#   SANDBOX_SUBDIR         default cfb-poll-data
#   DELIVERY_CLONE         default .cache/site-repo
#   FIXTURES               the tree to deliver (used by `push` as a fallback)
#   SEASON WEEK SEASON_TYPE  stamped into the commit message
#   DRY_RUN                true => do everything except the push itself
#
# GitHub Actions also supplies GITHUB_SHA, GITHUB_SERVER_URL, GITHUB_REPOSITORY
# and GITHUB_RUN_ID, which become the provenance chain in the commit message.
#
# THE TOKEN NEVER REACHES DISK, A COMMAND LINE, OR A LOG. It is handed to git
# through GIT_ASKPASS, so it is not in `.git/config` (where a tokenised remote
# URL would persist), not in `ps` output, and not in the transcript. The askpass
# helper contains no secret of its own: it reads the environment when git calls
# it.

set -euo pipefail

MODE="${1:-}"
if [ "$MODE" != "prepare" ] && [ "$MODE" != "push" ]; then
  echo "usage: deliver-fixtures.sh prepare|push" >&2
  exit 2
fi

SANDBOX_REMOTE="${SANDBOX_REMOTE:-https://github.com/vyhlidal/sandbox.git}"
SANDBOX_BRANCH="${SANDBOX_BRANCH:-main}"
SANDBOX_SUBDIR="${SANDBOX_SUBDIR:-cfb-poll-data}"
DELIVERY_CLONE="${DELIVERY_CLONE:-.cache/site-repo}"
DRY_RUN="${DRY_RUN:-false}"
UV="${UV:-uv}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Everything this script says goes to stderr, because `prepare`'s stdout is a
# value the caller captures. A log line on stdout would become a directory path.
log() { printf '    %s\n' "$*" >&2; }

skip() {
  log "DELIVERY SKIPPED: $*"
  log "The fixture tree is still written locally; nothing was sent anywhere."
  exit 0
}

# --------------------------------------------------------------- the two gates

# Gate 1: the arming switch. Note there is no human exemption here, unlike
# [triggers] - see ops/arming.toml.
# ARMING_FILE overrides which switch is read, matching `cfbpoll guard --arming`.
# It exists so the whole delivery path can be rehearsed against a stand-in
# remote without committing an armed switch, which is the only way to test this
# script honestly. It is not a security boundary and is not pretending to be
# one: anyone who can set it can edit the file. What keeps production safe is
# that CI reads the committed file and nothing sets this there.
ARMED="$($UV run python -c \
  "import os; from cfbpoll.ops import guard; \
   a = guard.load_arming(os.environ.get('ARMING_FILE') or None); \
   print(str(a.allows_step('delivery')).lower()); print(a.step_reason('delivery'))")"
ARMED_OK="$(printf '%s' "$ARMED" | head -1)"
ARMED_WHY="$(printf '%s' "$ARMED" | tail -1)"
log "arming: $ARMED_WHY"
[ "$ARMED_OK" = "true" ] || skip "delivery is disarmed in ops/arming.toml"

# Gate 2: the credential. A missing secret is a skip and not a failure, the same
# posture DATABASE_URL gets, so a fork or a rehearsal machine runs the whole job
# and simply delivers nothing.
[ -n "${SANDBOX_CONTENTS_PAT:-}" ] || skip "SANDBOX_CONTENTS_PAT is not set"

# ------------------------------------------------------------------ git plumbing

ASKPASS="$(mktemp "${TMPDIR:-/tmp}/cfbpoll-askpass.XXXXXX")"
cleanup() { rm -f "$ASKPASS"; }
trap cleanup EXIT
cat > "$ASKPASS" <<'ASK'
#!/bin/sh
# Reads the environment when git calls it. Holds no secret of its own.
case "$1" in
  Username*) printf '%s' "x-access-token" ;;
  *)         printf '%s' "$SANDBOX_CONTENTS_PAT" ;;
esac
ASK
chmod 0700 "$ASKPASS"
export GIT_ASKPASS="$ASKPASS"
export GIT_TERMINAL_PROMPT=0   # never hang waiting for a human that is not there

site_git() { git -C "$DELIVERY_CLONE" "$@"; }

# ---------------------------------------------------------------------- prepare

if [ "$MODE" = "prepare" ]; then
  rm -rf "$DELIVERY_CLONE"
  mkdir -p "$(dirname "$DELIVERY_CLONE")"
  log "cloning $SANDBOX_REMOTE ($SANDBOX_BRANCH) into $DELIVERY_CLONE"
  # --depth 1: we only ever add a commit on top of the tip. The full history of
  # a Next.js app is not something a poll run needs to download every week.
  git clone --quiet --depth 1 --single-branch --branch "$SANDBOX_BRANCH" \
    "$SANDBOX_REMOTE" "$DELIVERY_CLONE" >&2

  site_git config user.name  "cfb-poll robot"
  site_git config user.email "noreply@thepoll.ai"

  TARGET="$DELIVERY_CLONE/$SANDBOX_SUBDIR"
  mkdir -p "$TARGET"
  # ABSOLUTE, and resolved rather than assembled. DELIVERY_CLONE may already be
  # absolute, and blindly prefixing the repo root produced a path like
  # `/repo//tmp/clone/...` that existed nowhere - a bug this script's own
  # rehearsal caught, which is the argument for having a rehearsal.
  TARGET_ABS="$(cd "$TARGET" && pwd)"
  log "publish into: $TARGET_ABS"
  log "existing seasons there: $(find "$TARGET_ABS" -maxdepth 1 -type d -name '[0-9]*' \
        -exec basename {} \; 2>/dev/null | sort | tr '\n' ' ')"
  # THE ONE LINE OF STDOUT. This is the value the caller assigns to FIXTURES.
  printf '%s\n' "$TARGET_ABS"
  exit 0
fi

# ------------------------------------------------------------------------- push

[ -d "$DELIVERY_CLONE/.git" ] || skip "$DELIVERY_CLONE is not a clone; prepare did not run"

SEASON="${SEASON:-}"
WEEK="${WEEK:-}"
SEASON_TYPE="${SEASON_TYPE:-regular}"
WEEK_LABEL="$(printf '%02d' "${WEEK:-0}" 2>/dev/null || printf '%s' "$WEEK")"

# Stage BY EXPLICIT PATHSPEC. The site repository is somebody else's working
# tree with its own untracked scratch in it; `git add -A` there would sweep up
# whatever a human left lying around and publish it under a poll commit.
site_git add -- "$SANDBOX_SUBDIR"

# IDEMPOTENCE. Re-delivering an unchanged week must not leave a marker in the
# site's history. The fixture documents are a deterministic function of the run
# directory - `serving.py` takes published_at from the run record's generated_at
# rather than the wall clock, and `fixtures.py` derives index.json's
# generated_at from the newest publication in the set rather than from now - so
# an unchanged week really does produce identical bytes, and this check really
# does fire.
CHANGED="$(site_git diff --cached --name-only | wc -l | tr -d ' ')"
if [ "$CHANGED" = "0" ]; then
  log "nothing changed under $SANDBOX_SUBDIR: the site already has this week"
else
  log "$CHANGED file(s) changed under $SANDBOX_SUBDIR"
fi

# PROVENANCE. The site repo's history has to answer "which poll run put this
# here" without anybody having to remember. Season, week, the model commit that
# produced it, and the workflow run that carried it.
MODEL_SHA="${GITHUB_SHA:-$(git -C "$REPO_ROOT" rev-parse HEAD)}"
if [ -n "${GITHUB_RUN_ID:-}" ]; then
  RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-vyhlidal/cfb-poll}/actions/runs/${GITHUB_RUN_ID}"
else
  # The VPS fallback has no workflow run to point at. Say where it came from
  # rather than leaving the line off, so a gap in the chain is never ambiguous.
  RUN_URL="not a workflow run: ops/bin/weekly.sh on $(hostname 2>/dev/null || echo unknown-host)"
fi

MESSAGE="$(cat <<MSG
Poll ${SEASON} week ${WEEK_LABEL} (${SEASON_TYPE})

Published by the cfb-poll weekly job.

  season:     ${SEASON}
  week:       ${WEEK} (${SEASON_TYPE})
  model sha:  ${MODEL_SHA}
  run:        ${RUN_URL}
  files:      ${CHANGED} changed under ${SANDBOX_SUBDIR}/

The board, the constants and the archive digest that produced it are pinned in
that commit of vyhlidal/cfb-poll. This message is the only link between a file
on thepoll.ai and the run that made it, so it is written even when nothing else
about the week is interesting.
MSG
)"

if [ "$CHANGED" != "0" ]; then
  site_git commit --quiet -m "$MESSAGE"
  log "committed: $(site_git log -1 --format='%h %s')"
fi

# THE SECOND HALF OF IDEMPOTENCE, and the demo is what found it. "Nothing is
# staged" is not the same question as "nothing is left to deliver": a previous
# invocation can have committed without pushing - a dry run does exactly that -
# and returning early on the staged check alone would strand that commit in a
# clone nobody looks at, reporting success. Ask the remote instead.
AHEAD="$(site_git rev-list --count "origin/$SANDBOX_BRANCH..HEAD" 2>/dev/null || echo 1)"
if [ "$AHEAD" = "0" ]; then
  log "nothing to push: $SANDBOX_BRANCH already has this week"
  log "Re-running a week is free and leaves no trace in the site's history."
  exit 0
fi
log "$AHEAD commit(s) ahead of origin/$SANDBOX_BRANCH"

if [ "$DRY_RUN" = "true" ]; then
  log "DRY RUN: stopping before the push. The commit above exists only in"
  log "$DELIVERY_CLONE, which is scratch. The real step would run:"
  log "  git -C $DELIVERY_CLONE push origin HEAD:$SANDBOX_BRANCH"
  exit 0
fi

log "pushing to $SANDBOX_BRANCH"
site_git push --quiet origin "HEAD:$SANDBOX_BRANCH" >&2
log "PUSHED. The site auto-deploys from $SANDBOX_BRANCH, so thepoll.ai is"
log "changing now. Nothing else in this job can take that back."
