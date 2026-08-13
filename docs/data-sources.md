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

### The benchmark roster, and why it now exists

The rule above had an enforcement mechanism and no roster: nothing here could say
which third-party series exist or what is known about each, and a rule with no
roster is a rule nobody can check you against. `src/cfbpoll/benchmarks.py` is the
roster and `cfbpoll benchmarks` prints it.

| Series | Author | Open implementation | Publishes error metrics | Scorable on our harness |
|---|---|---|---|---|
| **CORE** | Bill Radjewski (Rad Sports Analytics LLC) | no | no | no |
| SP+ | Bill Connelly | no | yes | no |
| ESPN FPI | ESPN | no | no | no |
| CFBD SRS | Bill Radjewski | no | no | no |
| CFBD Elo | Bill Radjewski | no | no | no |

**CORE** (Context and Opponent-Relative Efficiency) was published on 2026-08-08
and is the closest thing to a peer this project has. Its own positioning sentence
is *"CORE is an efficiency rating. It is not a forecast, point spread, win
probability, résumé ranking, or betting system."* Its methodology is documented
publicly. Two things are true alongside that and both are stated as facts rather
than as complaints: **the implementation is not open**, and **no error metrics
are published for it** — no MAE, no straight-up accuracy, no calibration. Almost
nobody publishes those, which is precisely why this project does.

That is also why "transparent" is no longer the differentiator here and
**"checkable"** is. Seasons 2021–2024 of CORE are archived under `archive/cfbd/`
(private, per the terms below) as `/ratings/core`, one row per team per season:
`overall`, `offense`, `defense`, play counts and `modelVersion`.

**Nothing in that table is scorable on the walk-forward harness, and the reason
matters more than the table.** These series publish one number per team per
*season*. Placing a season-final rating beside systems that saw only through week
N−1 would flatter it and measure nothing. CFBD's Elo is weekly and could in
principle be scored; it is not, because CFBD warns that *"model changes can
affect the comparability of values across periods"*, so a backtest resting on
someone else's derived ratings can drift when they retrain. Where a comparison is
wanted, this project implements the method itself from the scoreboard — the `srs`
and `elo` rows in [the backtest](../demo/backtest-2021-2023.md) are ours, fitted
walk-forward, and are not these.

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
