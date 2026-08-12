# ADR 0002 — GitHub Actions for compute, but NOT GitHub's `schedule:` for the clock

- **Status:** Accepted
- **Date:** 2026-08-12
- **Full reasoning:** research report 03 §1 ("the one finding that changes the
  design"), §4.1–§4.6

## Decision

- **Primary:** GitHub Actions for compute, triggered by `workflow_dispatch` fired
  from n8n on the existing Hostinger VPS at Sunday 06:00 America/New_York.
- **Fallback:** the identical job on the Hostinger VPS under a systemd timer at
  08:30 ET, exiting 0 immediately if the week is already published.
- **Third string:** a `schedule:` cron in the workflow, deliberately early, with
  the same no-op guard.
- **Dead-man's-switch:** if no published row exists for the current week by
  14:00 ET Sunday, alert.

Two independent hosts, one guarded idempotent job, and a check that fires when
*neither* worked. The recurring lesson of report 01 is that the dangerous failure
is the silent one; this design makes silence itself the alert.

**Not yet wired up.** The workflows in this repo currently declare
`workflow_dispatch` only — no `schedule:`, no n8n workflow, no VPS runner — so
that nothing can fire accidentally while the pipeline is a scaffold.

## Why not `schedule:`

**GitHub Actions' scheduled event cannot be trusted as a clock in 2026, and this
is measured, not folklore.** GitHub's docs say scheduled runs "can be delayed
during periods of high loads," which reads as a minor caveat and materially
understates the observed behaviour (community discussion #156282, 70 upvotes):

- A GitHub engineer, 2026-06-04: *"We are aware that the drift on the start of our
  scheduled jobs has got worse… this isn't a fix 'now'."*
- 51 consecutive runs of a weekly `13:37 UTC` job: late-2025 runs started ~10–20
  minutes late; July 2026 runs started 15:32, 15:32, 15:17, 16:12, 15:52 — **about
  two hours late, consistently.**
- 27 consecutive daily runs of a `10:30 UTC` job: delays from +35 to +216 minutes,
  mean ≈ +80.
- A `*/5` job fired **97 times out of ~2,016 slots (≈5%)** — scheduled events are
  not merely late, they are **dropped**.
- `workflow_dispatch` reportedly goes through a different queue and starts within
  seconds.

For a Sunday-morning poll a two-hour drift is survivable; a *dropped* run is not,
and unpredictable variance destroys the ability to answer "did it run yet?" —
exactly the silent-failure pattern that kills weekly publications.

**The seasonal trap.** "In a public repository, scheduled workflows are
automatically disabled when no repository activity has occurred in 60 days." The
season runs late August to mid-January; February through August is a ~7-month
window in which a quiet repo would silently lose its schedule. `workflow_dispatch`
is not subject to that rule.

## Why GitHub Actions is still the right compute host

Free for public repositories on standard runners; 4 vCPU / 16 GB / 14 GB SSD; a
6-hour job ceiling; a 256-job matrix; 10 GB of cache. Against a workload of "a few
minutes on 4 cores and 0.55 GB of input," every limit has one to two orders of
magnitude of headroom.

And one limit is a **feature**: with the exception of `GITHUB_TOKEN`, secrets are
not passed to workflows triggered from a forked repository. A contributor's PR
therefore literally *cannot* touch the CFBD key. That is why the license split is
architectural rather than legal paperwork — the challenge harness runs entirely
from the MIT archive because that is all a fork can reach.

## Why the VPS is the clock and not the compute

The Hostinger VPS (KVM 2, 2 vCPU, 8 GB, Ubuntu 24.04) already runs n8n 24/7. The
entire production scheduler is a two-node n8n workflow: a Schedule Trigger with a
cron expression and a workflow timezone, and one HTTP Request node posting to
`/repos/{owner}/{repo}/actions/workflows/{id}/dispatches`. **Ops burden: close to
zero.** No new daemon, no port, no reverse proxy, no TLS, no database.

Running the *pipeline* there is a materially different proposition — a Python
toolchain to patch, 0.55 GB to keep on disk and back up, log rotation, a systemd
unit, and a second place where results can be produced. Keep that as the fallback,
deliberately, and pay its cost only when the primary is down. Because it runs the
same `--guard`-protected code path, there is no second implementation to drift out
of sync, which is what fallbacks usually die of.

## Rejected

**Vercel cron** — the instinct that "the ecosystem is wrong for scipy" turns out to
be half wrong: numpy/scipy/scikit-learn fit inside the 500 MB Python bundle limit
and a once-daily Hobby cron is within the rules. The real objections are
forkability (a forker would need a Vercel account and configured env vars before
anything runs, against GitHub's `git clone` plus a fork's own free tier), an
ephemeral filesystem that fights the content-addressed archive, and 1,000 bootstrap
refits at 1 vCPU against a 300-second hard ceiling. Keep Vercel for serving the
site, which is what it is good at.

**The Mac** — `launchd` runs a missed job *whenever the lid next opens*, which for
a weekly publication is a coin flip with a silent failure mode, and a laptop is not
something a fork can use. The subtler reason: arm64 and the runner's x86_64 need
not produce bit-identical floating-point results, which is fine for science and
fatal for the byte-match assertion. **Golden fixtures are generated on CI, never on
the Mac.** The Mac remains the right machine for development, the retroactive grid,
hyperparameter search and exploratory DuckDB work.

## Consequences

- A fine-grained GitHub PAT scoped to this repository with Actions read/write must
  be created by a human and stored in n8n's credential store. It does not exist yet.
- Every secret-dependent step in `weekly.yml` must **degrade rather than fail**.
  Forks get no secrets and must still produce rankings; that single rule is most of
  what "forkable" means in practice.
- `concurrency` is set without `cancel-in-progress`: a publication half-written
  because a second trigger cancelled the first is the worst outcome available.
- Runners are pinned to `ubuntu-24.04`, never `ubuntu-latest` — the alias moves and
  reproducibility claims cannot survive that.
