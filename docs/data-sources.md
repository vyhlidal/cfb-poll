# Data Sources

Condensed from research report 01 (`01-data-sources.md`). Read that for the
verified detail; this page is the operating summary.

## Two sources, deliberately split

| Job | Source | Why |
|---|---|---|
| **Historical backfill 2021–2025** | SportsDataverse `sportsdataverse-data` release assets (parquet over HTTPS) | Free, **MIT-licensed**, no API key, bulk download, verified 100% FBS play-by-play coverage 2021–2024 and 99.9% for 2025. Costs zero API quota, and MIT means we may legally republish it |
| **Weekly in-season pull** | CollegeFootballData.com REST API v2, Patreon Tier 1 ($1/month) | Authoritative, licensed, documented latency of "within minutes after game completion," and direct control over timing rather than depending on a volunteer's cron |
| **Cross-validation** | Each against the other | Two substantially independent pipelines over the same games is a real data-quality check |

Total data cost: **$1/month**. Total infrastructure cost on top of that: $0.

## The rule that matters most

**Every third-party rating is a benchmark, never an input.**

CFBD documents PPA, win probability, WEPA, Elo, SRS and CORE as proprietary models
with undisclosed formulas. SP+ and FPI are third-party models CFBD mirrors. The
SportsDataverse play-by-play files ship precomputed `EPA` and `wpa`, and the
schedules ship `home_pregame_elo` and `excitement_index`.

Feeding any of that into the ranking would make an "open" ranking partly a black
box and would import exactly the priors the project exists to eliminate. The
enforcement is `cfbpoll audit-features --fail-on-banned`; the full table is in
[constraints.md](./constraints.md).

Build the ranking exclusively from **raw observables** — scores, dates, sites,
opponents, drives, plays, box scores — which are verifiable facts.

## Terms, in one paragraph each

**CFBD** (Rad Sports Analytics LLC, terms effective 2025-07-01). Publishing free
derived rankings is permitted; §5 explicitly names "published products… academic
papers, visualizations, or social media content" and asks only for credit.
Attribution is **not required, and we give it anyway** — everywhere, on every poll.
The one genuine constraint is §3: "Reselling or redistributing data obtained from
the API without explicit permission," which is why **raw CFBD JSON never enters
the public repo**. Terms can change effective immediately and access is revocable
at their discretion, which is why we keep a dated snapshot (see
[terms-snapshots/](./terms-snapshots/)) and why the archive exists.

**SportsDataverse** — MIT, and the strongest license position available. It permits
republishing the data archive, which no other source in the evaluation allows.
Two honest caveats: the sibling repo `cfbfastR-data` carries no license file at
all (prefer `sportsdataverse-data` release assets for anything we republish), and
MIT covers their *compilation*, not an upstream rights transfer — our cleanest
legal position is that scores, dates, sites and opponents are facts, and our
published output is model results, not a data feed.

**Everything else was evaluated and rejected**: ESPN's undocumented APIs are
technically excellent and disqualified by Disney's terms; Sports-Reference returns
403 and its "material substitute" clause targets exactly this project; the NCAA
endpoints are 403 or dead; the commercial vendors bar redistribution or never
publish a price.

## The durability plan

Report 01 §5.4 calls the append-only raw archive "the single most important
engineering decision in this report," and the principle is one line:

> **Every source is a transport, not a dependency.**

Every byte a source delivers is written to our own storage, immutably, before
anything else touches it — raw and unmodified, never overwritten, with a
`_manifest.json` carrying url, params, status, bytes, sha256 and fetched_at.
A re-pull writes a new timestamped file, which makes late upstream stat
corrections *observable*.

If both sources vanished tomorrow we would lose the ability to add new weeks. We
would not lose our history, our backtests, our published record, or our ability to
reproduce any past poll. That is the difference between an inconvenience and a
project-ending event.

Where those bytes physically live is [ADR 0003](./adr/0003-storage.md).

## Validation, before anything publishes

Because CFBD's terms disclaim all warranty on accuracy, validation is our job
(report 01 §5.5). Before publishing: completed flags and non-null scores on every
FBS-vs-FBS game; sane week counts and no team twice; box scores reconciling to
final scores; bounded week-over-week rating movement; a cross-source CFBD ↔
SportsDataverse score diff; and the known-bug guard that no December or January
game is bucketed into week 1.

**On failure: halt, alert, publish nothing.** For a project whose value
proposition is trustworthiness, publishing a wrong poll costs far more than
publishing late.
