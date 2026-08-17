# Runbook: the Mac's copy of the private CFBD archive

**Why this exists.** John ruled on 2026-08-17 that the private CFBD raw archive
gets no Cloudflare R2 bucket ([ADR 0015](../adr/0015-cfbd-archive-no-r2.md)). Its
durability is therefore two machines instead of an object store: the Hostinger
VPS writes it every Sunday, and this Mac holds the second copy. This is how the
second copy gets made.

**It is a runbook and not a daemon, deliberately.** Nothing is installed, nothing
runs on a schedule, and the only way bytes move is a person typing a command.
A scheduled sync that stops is worse than a manual one that is obviously manual,
because it converts a habit you know you have into a guarantee you only think you
have. The Mac is also asleep most of the time, which is the same argument ADR 0002
used to refuse it as a clock.

**What is being copied.** `archive/cfbd/` — the exact JSON bodies CFBD returned,
written before anything parsed them. Tens of megabytes a season. It is gitignored
and it must stay that way: CFBD terms §3 bar republishing raw API data, which is
the whole reason this class of bytes has its own home.

---

## Configure once

Put a host block in `~/.ssh/config` rather than passing a hostname:

```
Host cfbpoll-vps
    HostName <the Hostinger address>
    User cfbpoll
    IdentityFile ~/.ssh/id_ed25519_cfbpoll
    IdentitiesOnly yes
```

Then in your shell profile:

```bash
export VPS_HOST=cfbpoll-vps
export VPS_ARCHIVE=/opt/cfb-poll/archive/cfbd
```

An alias keeps the port, the user and the key path out of shell history, and it
means the script's command line carries nothing worth stealing.

## Run it

```bash
cd ~/claude/projects/cfb-poll

DRY_RUN=true ops/bin/pull-cfbd-archive.sh    # what would move
ops/bin/pull-cfbd-archive.sh                 # move it, then verify
VERIFY_ONLY=true ops/bin/pull-cfbd-archive.sh # re-hash what is already here
```

A healthy run ends like this:

```
=== Verify every local file against its _manifest.json
  ok  2026/week-07  (22 files)
  ...
  56 files verified across 11 buckets under /Users/…/cfb-poll/archive/cfbd
```

**When to run it.** After any Sunday the job pulled from CFBD, which in season is
every Sunday. The archive is append-only, so a late sync loses nothing except the
window in which only one copy existed.

## What the flags mean, and why they are not negotiable

- **`--ignore-existing`.** ADR 0003: *"Never overwrite. A re-pull writes a new
  timestamped file, which makes late upstream stat corrections observable."* An
  append-only archive syncs by adding files and by nothing else. If a file exists
  locally, the local copy is authoritative and rsync does not touch it.
- **No `--delete`, ever.** With it, one bad afternoon on the VPS erases the only
  other copy. Two copies exist precisely so that one machine's mistake is
  survivable, and `--delete` hands that property back.
- **Pull, never push.** The VPS is the origin: it holds the key and does the
  weekly writes. Pulling means the Mac needs no inbound access and the VPS holds
  no credential for the Mac, so a compromised laptop reads a copy rather than
  deleting an original.
- **Verify after every sync.** rsync proves bytes arrived. `_manifest.json` proves
  they are the bytes CFBD sent. A backup nobody has checked is a directory.

## When the verification fails

```
1 bucket(s) FAILED:
  2026/week-07: sha256 mismatch for …/2026-…__games__year-2026.json: abc… != def…
```

**Do not fix it by copying over the local file.** Find out which copy is wrong
first. The archive is content-addressed exactly so that neither machine has to be
trusted:

1. Hash the same file on the VPS: `sha256sum <path>` and compare with what that
   machine's `_manifest.json` records for it. If they agree there and disagree
   here, the local file is damaged and can be removed and re-pulled.
2. If the VPS's own file disagrees with the VPS's own manifest, the damage is
   upstream of the sync and the Mac's copy is the good one. Do not overwrite it.
3. `archive.write_raw` refuses to record a second digest for a filename it has
   already seen, so a manifest that disagrees with itself is a genuine anomaly
   and worth understanding before anything is deleted.

## What this does not cover, stated plainly

Both copies are John's, in two buildings, on ordinary disks. There is no
third-party copy at all and no versioning; a file deleted on both machines is
gone. ADR 0015 lists that cost in full rather than burying it. It is an
acceptable trade for a class of bytes whose loss costs *re-derivation ability*
and not a published artifact — every published board stays up, because class A
and class C both live in GitHub Release assets and `_run.json` pins the sha, the
config hash and the archive digest of every run.

If the CFBD archive ever becomes the only source of something published, that
trade stops being acceptable and ADR 0015 should be revisited.
