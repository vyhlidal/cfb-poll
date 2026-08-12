# ADR 0003 — GitHub Release assets for the archive. Not git, not Git LFS.

- **Status:** Accepted (R2 leg not yet provisioned)
- **Date:** 2026-08-12
- **Full reasoning:** research report 03 §5.1–§5.3, §5.5; report 01 §4.1, §5.4

## Decision

Three classes of bytes, three homes, split by what the license permits:

| Class | Publishable? | Size | Home |
|---|---|---|---|
| **A. MIT raw archive** (SportsDataverse parquet, schedules, ratings CSVs) | Yes — MIT | ~0.55 GB, +~130 MB/season | **GitHub Release assets** in this repo |
| **B. CFBD raw archive** (exact JSON bodies, weekly) | **No** — CFBD terms §3 | a few MB/week | **Cloudflare R2**, private bucket, plus one off-platform copy |
| **C. Our derived output** (ratings, intervals, backtests) | Yes — our own work | ~50–300 MB/season | **GitHub Release assets** → Postgres subset for serving |

DuckDB queries all of it in place, locally and over HTTPS.

## Why not plain git

A hard limit: GitHub blocks files larger than 100 MiB, and four of the five
play-by-play parquet files exceed it (108.8, 110.7, 120.8, 131.2 MB). GitHub also
recommends repositories stay ideally under 1 GB; committing the archive would blow
past that within three seasons of growth.

## Why not Git LFS — the non-obvious one

LFS is disqualified by its **billing model**, not its size limits. GitHub Free and
Pro include 10 GiB of storage and 10 GiB of bandwidth, and the attribution rule is
the problem:

> "When you **download** a Git LFS file, the bandwidth you use is included in the
> **repository owner's bandwidth usage**." … "**Forking and pulling a repository
> counts against the parent repository's bandwidth usage.**"

At 0.55 GB of objects, **roughly 18 clones exhausts the monthly quota — and the
owner pays for other people's forks.** For a project whose entire product thesis is
"please fork this," Git LFS creates a direct financial penalty for success.

## Why release assets

- Each file must be under 2 GiB. Our largest is 131 MB.
- Up to 1000 assets per release.
- **No restriction on total combined size or bandwidth usage.**

And the upstream project already proved it at exactly this scale: SportsDataverse
distributes these same bytes as release assets. We are not inventing a distribution
channel, we are mirroring one that works — which means we inherit its operational
proof.

Tags: `archive-v{n}` for the republished MIT inputs, `poll-{season}-w{NN}` for our
weekly output.

## Why R2 for the private class

CFBD terms §3 prohibit "reselling or redistributing data obtained from the API
without explicit permission," so raw CFBD JSON must never reach the public repo.
Cloudflare R2 gives 10 GB-month of storage free, 1M Class A and 10M Class B
operations free, and **zero egress charges** — so pulling the whole archive back
for a rebuild is free. Our CFBD archive is tens of MB per season and a few hundred
writes a year; it will not leave the free tier this decade.

Backblaze B2 is an acceptable alternative (first 10 GB free, free API calls, free
egress up to 3× stored). R2 wins narrowly on unconditional free egress.

**NOT YET PROVISIONED.** No Cloudflare account, no bucket, no credentials. The
`cfbpoll archive push --target r2` command is a stub. The zero-new-accounts
alternative on the table is the VPS's 100 GB disk plus one off-box copy, which
satisfies the durability requirement but concentrates risk on one machine.

## The archive layout, and why the manifests matter

```
archive/sportsdataverse/{pbp,schedules,ratings,crosswalk}/…   + _manifest.json
archive/cfbd/{season}/week-{NN}/{ISO8601}__{endpoint}__{params}.json + _manifest.json
out/  ratings_live.parquet  ratings_hindsight.parquet  ratings_grid.parquet
      rank_intervals.parquet  model_params.json  predictions.parquet
      poll.json  poll.csv  backtest_metrics.json  _run.json
```

`_manifest.json` (url, params, status, bytes, sha256, fetched_at) is what makes the
archive content-addressed rather than a pile of files. `_run.json` (git_sha,
config_hash, archive_sha, timestamps) is what makes any published poll traceable to
the exact code, config and inputs that produced it. Both are cheap, and both are
the difference between "open source" and "auditable."

**Never overwrite.** A re-pull writes a new timestamped file, which makes late
upstream stat corrections observable — diff Sunday's pull against Wednesday's and
see exactly what changed.

## DuckDB's role is bigger than "nice to have"

It queries parquet directly, reads over HTTPS, and pushes projection *and* filter
down into the reader — which matters when the play-by-play files have 362 columns
and we need about 15. Three jobs: local analytics on the Mac, the SQL layer of the
walk-forward backtest, and forkability. A stranger with no Python, no clone and no
account can run:

```sql
INSTALL httpfs; LOAD httpfs;
SELECT team, resume_rating, rank, rank_lo90, rank_hi90
FROM read_parquet('https://github.com/<owner>/cfb-poll/releases/download/poll-2026-w10/ratings_live.parquet')
WHERE layer = 'L4_resume' ORDER BY rank LIMIT 25;
```

That single query is a stronger openness claim than any README paragraph.

## Consequences

- The public repo stays small. Only code, configs, docs and checksum manifests.
- A popular fork costs us nothing in bandwidth, which is the failure mode LFS would
  have created.
- Rebuilding from scratch requires only the release assets plus the manifests.
- The R2 leg is a stub until someone creates the account; until then the CFBD
  archive has no off-box home, which is a live gap and is recorded as one.
