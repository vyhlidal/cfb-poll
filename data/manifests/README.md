# data/manifests/

Checksums and provenance. These files are small, they are committed to git, and
they are what makes the archive **content-addressed** rather than a pile of files
(report 01 §5.4, report 03 §5.3).

Empty right now — the backfill has not been run. That is step 1 of the build order
(report 03 §10) and it is the step most likely to be lost forever if delayed:
every day without a local archive is a day an upstream outage costs us the
backtest.

## Expected contents

### `sportsdataverse.lock.json`
One entry per MIT-licensed input asset: `url`, `bytes`, `sha256`, `fetched_at`,
`upstream_updated_at`. `cfbpoll archive sync --verify` checks every file against
this before any consumer reads it, and a mismatch is a hard failure, not a
warning. `weekly.yml` also keys its archive cache on `hashFiles()` of this file.

Expected to cover, for 2021-2025 (report 01 §3.10):

| Asset series | Source | Notes |
|---|---|---|
| `play_by_play_{2021..2025}.parquet` | `sportsdataverse/sportsdataverse-data`, tag `cfbfastR_cfb_pbp` | ~0.55 GB total (73.7 / 108.8 / 110.7 / 120.8 / 131.2 MB) |
| `cfb_schedules_{2021..2025}.parquet` | same org | **`cfb_schedules_*`, not `schedules_*`** — they are different series |
| `cfb_ratings_weekly_*.csv` | same org | benchmarks only, never model inputs |
| `cfb_crosswalk_*.csv` | same org | ESPN ↔ CFBD id mapping |

Validate the backfill against the published counts before trusting it: 3,864
FBS-vs-FBS games, coverage 100/100/100/100/99.9%.

### `golden/`
Replay fixtures for `.github/workflows/reproducibility.yml`, e.g.
`golden/2023-w10.sha256`.

**These must be generated on the CI platform, never on the Mac** (report 03 §4.5).
Apple Silicon arm64 and the x86_64 runner do not necessarily produce bit-identical
floating-point results, because different BLAS kernels reduce in different orders.
A local replay is expected to agree to ~1e-12, not bit-for-bit; that is what
`make replay-tolerant` is for.

The hash covers the **canonicalized CSV**, not the parquet files. Parquet embeds a
`created_by` writer-version string, so byte-identical data can produce different
file bytes (report 03 §9.3 item 4).

### What never goes here
Raw CFBD response bodies, or any file large enough to matter. The archive itself
lives in GitHub Release assets (public, MIT) and Cloudflare R2 (private, CFBD).
