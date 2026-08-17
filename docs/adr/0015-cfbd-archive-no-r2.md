# ADR 0015 — The private CFBD archive gets two disks, not an object store

- **Status:** **PROPOSED.** An amendment to
  [ADR 0003](0003-storage.md), which is otherwise unchanged and not edited.
- **Decision:** **John, 2026-08-17: no Cloudflare R2.** The private CFBD raw
  archive lives on the Hostinger VPS disk with a synced second copy on the Mac.
- **Amends:** ADR 0003's class B row and its "Why R2 for the private class"
  section. Classes A and C are untouched.
- **Implemented by:** [`ops/bin/pull-cfbd-archive.sh`](../../ops/bin/pull-cfbd-archive.sh),
  [`ops/bin/verify_cfbd_archive.py`](../../ops/bin/verify_cfbd_archive.py),
  [`docs/runbooks/cfbd-archive-sync.md`](../runbooks/cfbd-archive-sync.md).

---

## What changes

ADR 0003 split the bytes three ways and gave each class a home. Exactly one row
moves.

| Class | ADR 0003 said | This amendment says |
|---|---|---|
| **A. MIT raw archive** | GitHub Release assets | **unchanged** |
| **B. CFBD raw archive** | Cloudflare R2, private bucket, plus one off-platform copy | **VPS disk, plus a synced copy on the Mac** |
| **C. Our derived output** | GitHub Release assets | **unchanged** |

Nothing about the licence split changes, and that is the part worth saying
plainly, because it is the part that could be misread. CFBD terms §3 still bar
republishing raw API responses, `archive/` is still gitignored, and the CFBD
archive still never reaches a public repository or a release asset. What changed
is where the private copy sleeps, not whether it is private.

## Why

ADR 0003 already named the alternative and already named its cost:

> **NOT YET PROVISIONED.** No Cloudflare account, no bucket, no credentials. …
> The zero-new-accounts alternative on the table is the VPS's 100 GB disk plus
> one off-box copy, which satisfies the durability requirement but concentrates
> risk on one machine.

So this is not a new idea, it is the ruling on an option the original record
raised. Three things decided it.

**The account is the cost.** R2 means a Cloudflare account, an API token, three
more secrets in two more places, a bucket lifecycle nobody owns, and one more
console to remember the password for. The archive is tens of megabytes a season
and a few hundred writes a year. Paying an account's worth of ongoing attention
for that is the wrong trade, and it is the same trade this project already
refused for Vercel cron in ADR 0002.

**The critical path is a week away.** The 2026 season opens 2026-08-29. Every
credential that has to exist before week 1 is a thing that can be missing at
06:00 on a Sunday morning. The Sunday job now has exactly one secret in it, the
CFBD key, and cutting the R2 leg is what got it to one.

**The archive is already reproducible in the way that matters.** Class B is the
raw response bodies. Losing them does not lose a published poll: `_run.json`
pins the git sha, the config hash and the archive digest, class A and class C
both live in release assets, and every published board stays up. What class B
buys is the ability to re-derive from source and to audit an upstream stat
correction after the fact. That is worth two disks. It is not obviously worth a
fourth account.

## What this costs, stated rather than implied

An honest amendment says what it gave up.

1. **No object-store durability.** R2 publishes eleven nines. Two consumer-grade
   disks in two buildings do not, and nothing here should be described as if
   they do.
2. **The sync is manual, so it can silently lag.** `ops/bin/pull-cfbd-archive.sh`
   runs when a human runs it. A daemon was deliberately not installed, because a
   daemon that stops is the exact silent failure this project keeps meeting, but
   the honest reading is that the mitigation is a habit rather than a mechanism.
   The runbook therefore ends with a verification that prints file counts, so
   "when did I last do this" has an answer on disk.
3. **Two copies, one operator.** Both machines are John's. There is no
   third-party copy at all now, where ADR 0003's design had one.
4. **Geographic redundancy is thinner than it looks.** A Hostinger VPS and a Mac
   are two buildings, not two regions with independent failure domains.

None of these is fatal for a class of bytes whose loss costs re-derivation
ability rather than a published artifact. All of them are reasons to revisit
this if the CFBD archive ever becomes the only source of something published.

## Consequences

- **The Sunday job has one secret.** `.github/workflows/weekly.yml` and
  `ops/bin/weekly.sh` reference `CFBD_API_KEY` and, optionally, `DATABASE_URL`.
  There is no `archive push` step and no R2 credential anywhere in this
  repository. A test asserts that
  (`tests/unit/test_ops_automation.py::test_no_r2_credential_survives_johns_ruling`).
- **The VPS is now load-bearing for a second reason.** It was the clock; it is
  now also the origin of class B. The fallback design already put a systemd
  timer there, so the machine's health was already worth watching, but the
  consequence of losing it grew.
- **The sync runs Mac-side, pulling.** The VPS needs no credential for the Mac
  and the Mac needs no inbound access. A compromised laptop reads a copy; it
  does not delete the original. `--ignore-existing` and never `--delete`, because
  ADR 0003's "never overwrite" rule makes an append-only archive sync by adding
  files and by nothing else.
- **`cfbpoll archive push --target r2` and the `boto3` dependency are now dead
  weight.** They are left in place rather than removed in this change: `boto3`
  is pinned in `uv.lock` and pulling it means regenerating the lock, which is a
  separate, reviewable commit and not something to bundle into a storage
  decision. Recorded here so the next person knows it is deliberate leftovers
  rather than an oversight.

## Alternatives rejected

- **Provision R2 anyway, because the design already said so.** The design also
  already said the VPS-plus-one-copy option satisfies the durability requirement.
  Following a written decision past the point where its author flagged the
  cheaper option is deference, not rigour.
- **Backblaze B2 instead.** Same objection. The cost was never the vendor, it was
  the account and the three secrets.
- **Put class B in a private GitHub repository.** It would be free, versioned and
  already authenticated. Rejected because "never let raw CFBD bodies near a
  GitHub repository" is a rule that is worth keeping absolute: private repos get
  made public by accident, and the failure is unrecoverable and public.
- **Install an rsync daemon or a cron job on the Mac.** A scheduled sync that
  stops is worse than a manual one that is obviously manual, because it converts
  a known habit into an assumed guarantee. The laptop is also asleep most of the
  time, which is the same argument ADR 0002 used to refuse the Mac as a clock.
- **Drop the second copy entirely and rely on the VPS.** That is one disk. ADR
  0003 called concentrating on one machine a risk while recommending against it;
  this amendment accepts the machine and refuses the concentration.
