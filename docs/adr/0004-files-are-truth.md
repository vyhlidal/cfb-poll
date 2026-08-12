# ADR 0004 — Files are the source of truth. Postgres is a cache.

- **Status:** Accepted
- **Date:** 2026-08-12
- **Full reasoning:** research report 03 §5.1, §5.4, §7.1–§7.3, §9

## Decision

> **Files are the source of truth. Postgres is a cache that can be dropped and
> rebuilt. Object storage holds what the license says we cannot publish.**

The pipeline writes `out/`. Everything downstream — the GitHub Release, the
Postgres serving tables, the Next.js sandbox app, the static site — reads from
those files. Nothing renders a number that is not in a published artifact.

```
CFBD ─┐
      ├─► ingest ─► archive ─► validate ─► rank + bootstrap ─► out/   ◄── TRUTH
SDV ──┘                            │ fail: publish nothing, say so
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
   release assets (canonical)  Postgres load     site build
                │                  │                  │
      anyone: DuckDB/curl   Next.js sandbox app   GitHub Pages (fork-runnable)
```

## Why

**Because every number on the page must be independently recomputable by a
stranger.** That is constraint 5, and it only holds if the artifact a stranger can
download is the same artifact the site renders. A database as the source of truth
breaks that: the numbers become a thing you have to be granted access to.

**Because Postgres is the wrong size.** Neon's free tier is 0.5 GB per project.
The full retroactive grid — 5 seasons × 15 evaluation weeks × 15 data windows ×
~264 teams × 6 layers ≈ **1.78 million rows** — lands at 250–400 MB with indexes.
That is most of the free tier, before the sandbox's other apps get anything, for
data the website renders perhaps 1% of.

**The rule: Postgres holds only what a page actually renders.**

| Data | Home |
|---|---|
| Raw plays (~850k rows × 5 seasons) | parquet only |
| The full N × K retro grid, all layers | parquet only (release asset) |
| Bootstrap draws (1,000 × teams × weeks) | parquet only |
| Live `R(N,N)` + hindsight `R(N,final)`, L3 and L4 only | **Postgres** |
| The published weekly poll (immutable record) | **Postgres** |
| Games, teams, predictions, model params, run metadata | **Postgres** |

That is well under 150 MB with indexes. Nothing is hidden by the split: the full
grid stays downloadable and DuckDB-queryable in place. It is just not in the wrong
engine.

**Because the failure mode should be visible.** If the pipeline stops, the site
shows stale data with a visible "last updated." That is the correct behaviour, and
it is exactly report 01 §5.2's rule: keep the previous week's published ranking; if
this week fails validation, publish nothing and say so.

## Append-only, and why that is an integrity choice

`cfb_poll_published` is **APPEND ONLY. Never UPDATE, never DELETE.** A poll that
can be quietly rewritten is not a published record. Corrections get a new row set at
a new `run_id` with the old one retained — the same argument report 01 §5.4 makes
for the raw archive.

The primary key on `(season, week, rank)` also turns a double-publish by two hosts
into an error rather than a duplicate.

## The dependency direction, enforced

**The standalone repo never imports from the sandbox. The sandbox never computes
anything.** The contract between them is the `cfb_*` schema and the published-artifact
JSON schema, both versioned here. If the sandbox site disappears, the pipeline is
unaffected.

## What this buys, concretely

**The fork promise is a file promise.** `git clone && make rankings` works because
the inputs are MIT-licensed files in release assets and the outputs are files on
disk — no Vercel account, no Neon account, no API key, no permission from anyone.
A fork that required a database before showing a single ranking would not be a
fork, it would be a demo.

**Byte-match replay is possible at all.** `reproducibility.yml` recomputes a known
historical week with the network disabled and asserts a sha256 match against a
golden fixture. That assertion only exists because the output is a file.

Five things break byte-matching in numerical pipelines and all five are cheap now
and expensive to retrofit (report 03 §9.3): multi-threaded BLAS reduction order
(pin threads to 1), RNG (explicit `Generator(PCG64(seed))` with `SeedSequence.spawn`,
never `np.random.seed`), row ordering (sort before writing; iteration order must
never reach a file), parquet's embedded `created_by` writer string (hash the
**canonicalized CSV**, not the file), and platform float differences (fixtures
generated on CI, ~1e-12 agreement expected on a Mac).

## What we can and cannot claim

| Claim | Status |
|---|---|
| Anyone can recompute every published ranking from public, MIT-licensed inputs | **Yes** |
| Byte-identical replay of a historical week on the CI platform | **Yes** — enforced on every push |
| Byte-identical replay on arbitrary hardware (arm64, other BLAS) | **No** — expect ~1e-12. Say so; do not claim otherwise |
| Reproducible without any CFBD access | **Yes** for history; **no** for the current week before SportsDataverse's Sunday ~02:30 ET refresh |
| The raw CFBD archive is publishable | **No** — checksums and derived output are published instead |

Overclaiming here would be precisely the failure the project exists to avoid.
