# Backfill Findings — Corrections and Constraints for Implementation

**Date:** 2026-08-12. Produced during the verified backfill of the SportsDataverse MIT archive (step 1 of the build order). The archive lives at `cfb-poll-data/archive/sportsdataverse/` (relative paths, movable as-is) with per-directory `_manifest.json` checksums. All verification checks passed: 27/27 exact size matches vs the GitHub API, 55/55 sha256 re-reads, PBP 2025 exactly 293,200 × 362, FBS-vs-FBS counts 732/734/792/798/808 = 3,864 (zero delta vs report 01), coverage 100/100/100/100/99.9%.

These findings amend reports 01–03 and are **binding on all implementation work**.

## 1. Week numbering is unreliable — key on (season_type, week), never week alone

Report 01 framed `game_id 401778314` (Dec 2025 bowl labeled `week=1`) as a one-off. It is not:

- 54 such games in 2025, 54 in 2024, 48 in 2023.
- Postseason week numbering mixes two conventions **within the same season**: 2023 postseason contains week 1 *and* weeks 11–15; 2025 contains week 1 *and* weeks 13–14.

**Rule:** every week-scoped query, join, or bucket must condition on `(season, season_type, week)`. A bare `week` filter is a bug.

## 2. The validation guard from report 01 §5.5 must be division-aware

Four `week=1` games dated 2025-12-13 with `season_type='regular'` are D-II/D-III championships. The proposed guard ("no week=1 game with a December start_date") would false-positive on them. **Rule:** apply the guard after classification filtering, or make it division-aware.

## 3. Correction to report 01 §3.10: the crosswalk does NOT map CFBD IDs

`cfb_crosswalk` assets map **ESPN / Fox / Yahoo** IDs only (`espn_team_id`, `fox_team_id`, `yahoo_team_id`, `espn_game_id`, `fox_game_id`, `yahoo_game_id`, `yahoo_global_game_id`). There is no CFBD column. CFBD-vs-SportsDataverse reconciliation therefore still needs a mapping strategy — likely candidates: CFBD game IDs may coincide with ESPN event IDs, or join on (season, week, home_team, away_team) with a team-name normalization table. **Open item for the ingest work: verify empirically before the first cross-source check, and do not assume.**

## 4. The `completed` filter is load-bearing

2024 has 799 *scheduled* FBS-vs-FBS games but 798 *completed*: App State–Liberty (`401640992`, 2024-09-28) was canceled (`completed=False`, null scores). Every game count and every model input must filter `completed=True`.

## 5. The two schedule series converge and diverge by year

`cfb_schedules_2025.parquet` and `schedules_2025.parquet` are byte-identical (same git blob), while the 2024 pair differ sharply (191,897 vs 36,506 bytes). Year-conditional code would behave inconsistently without failing loudly. **Rule stands (report 01 §3.10): always use the `cfb_schedules_*` series and filter divisions ourselves.**

## 6. Crosswalk asset selection

All 26 assets on the `cfb_crosswalk` tag share one timestamp (2026-06-13). The backfill took the 2021–2025 schedule + teams crosswalks plus the two non-season-scoped assets. Rosters crosswalk included for completeness; not a model input.

## 7. Repo hygiene

`/cfb-poll-data/` is gitignored in the sandbox repo: four PBP files exceed GitHub's 100 MB hard-block, and the sandbox's documented `git add -A && git push` workflow would otherwise poison history. The archive's destination is the standalone repo's release assets (report 03 §5.2), never plain git.

## 8. Play-by-play: 2021 contains exact duplicate rows

**Date: 2026-08-12.** Found while building `ingest/plays.py` (step 4 of the build order); amends the findings above.

`play_by_play_2021.parquet` contains **4,810 rows that are byte-identical repeats** of another row in the same game — 8,949 rows collapse to 4,139 distinct plays, spread across 343 games. 2022–2025 are clean (zero duplicates). Left in place they would double the weight of a random ~3% of 2021's plays in any play-level fit.

**Rule:** de-duplicate play rows on `(game_id, game_row_number)` at load. `ingest/plays.py` does this and `tests/unit/test_plays.py::test_exact_duplicate_rows_in_2021_are_dropped` pins the counts, so both a silent upstream fix and a silent upstream worsening fail the build.

## 9. Play ordering: `game_row_number` is the only unique key

`row` restarts at 1 each half, `id_play` collides (102,461 distinct values over 254,090 rows in 2023), and `game_play_number` repeats whenever a play carries a penalty (the play and the penalty are separate rows sharing a number). **Rule:** order plays by `(game_id, game_row_number)`.

## 10. 86 play-file game_ids have no schedule row

15,353 plays across 86 `game_id`s in the 2021–2023 play files match no row of any `cfb_schedules_*` file. The schedule series is the authority on which games exist (§5), so those plays must be dropped. **Rule:** join plays to games with an inner join and count the orphans; never `left`.

## 11. Kickoffs carry a dummy `down = 1`

A `down BETWEEN 1 AND 4` filter is **not** a scrimmage-play filter: kickoff rows are recorded with `down = 1, distance = 10, yards_to_goal = 65`. **Rule:** classify on `play_type` first, then apply the down/field-position guard.

## 12. The play file's own scoring columns are not usable; the scoreboard is

`score_pts` ("points on this play") and `score_diff_start` ("margin before the snap") both depend on the row's possession label, and that label is unreliable on kickoff rows. Worked example, 2023 Vanderbilt–Hawai'i (`401520147`): play 22 is a Vanderbilt kickoff-return touchdown recorded with `score_pts = -8`; play 23 is a kickoff recorded with `score_diff_start = +7` when the offense in fact trailed by 7. Summing `score_pts` to the home side reconciles with the official final score in only **429 of 792** FBS-vs-FBS games in 2023.

`pos_team_score` / `def_pos_team_score` — the scoreboard after the play — are sound, and mapping them to home/away by string-comparing `pos_team` against the **games table's** `home_team` is immune to the possession-label problem. After a monotone repair (a scoreboard never decreases; 792 of 254,090 rows in 2023 record a decrease, concentrated on Timeout, Penalty and Kickoff rows) the reconstruction reaches the official final score in **763 of 792** games; the residual is almost entirely overtime, which every play-level fit excludes anyway.

**Rule:** derive points-on-a-play and pre-snap margin from the repaired scoreboard, never from `score_pts` or `score_diff_start`. `ingest/plays.py::attach_games` is the implementation.

## 13. The CFBD postseason backfill, and the ID question, settled

**Date: 2026-08-12.** Produced while making `ingest/cfbd.py` real. This section
**supersedes §3** and amends §10.

### 13.1 CFBD game ids ARE ESPN game ids

§3 recorded that the MIT `cfb_crosswalk` assets carry `espn_*`, `fox_*` and
`yahoo_*` columns and **no CFBD column**, left reconciliation open, and instructed
that it be verified empirically rather than assumed. It has been.

Measured against archived CFBD `/games` bodies for two regular-season weeks in two
different seasons — 2021 week 5 (61 games) and 2023 week 10 (65 games):

| Check | Result |
|---|---|
| CFBD `id` present as a SportsDataverse `game_id` | **126 / 126** |
| Home team and away team agree | 126 / 126 |
| Both scores agree | 126 / 126 |
| `neutralSite` agrees with `neutral_site` | 126 / 126 |
| Start date agrees to the day | 126 / 126 |
| School strings requiring normalisation | **0** |

**Rule:** join CFBD to SportsDataverse on `game_id` directly. No crosswalk, no
name-normalisation table, and no `(season, date, home, away)` fallback. Both
pipelines are ESPN-derived — cfbfastR wraps ESPN's feed — which is why the id
spaces coincide and why the school strings are byte-identical too.
`tests/unit/test_cfbd_ingest.py::test_cfbd_game_ids_are_espn_game_ids` re-runs this
against the archive on every build, so the finding cannot rot.

### 13.2 The 2021-2022 postseason is in the loader, from CFBD

`cfb_schedules_2021.parquet` and `cfb_schedules_2022.parquet` carry **no postseason
rows at all**. Those two seasons therefore held every regular-season game and every
conference championship and **none of the 38 + 42 bowls, including the entire
College Football Playoff** — which is to say they were missing precisely the games
`[weights]` treats specially (`cfp = 1.0`, `bowl_non_cfp = 0.25`).

Backfilled from CFBD `/games?seasonType=postseason&classification=fbs`, two calls
per season. Merged into `canonical_games` deduplicated on `game_id`; **zero** of the
80 ids were already present, and where both sources hold a game the parquet wins.
Every row now carries a `source` column, and `_run.json` publishes `game_sources`.

**New FBS-vs-FBS totals:**

| Season | Was | Now | Added |
|---|---:|---:|---|
| 2021 | 732 | **770** | 38 (3 CFP, 35 non-CFP bowls) |
| 2022 | 734 | **776** | 42 (3 CFP, 39 non-CFP bowls) |
| 2023-2025 | 792 / 798 / 808 | unchanged | the parquet already covers them |
| **Total** | 3,864 | **3,944** | |

### 13.3 Amends §10: 80 of the 86 "orphan" play-file game_ids are these games

§10 recorded 15,353 plays across 86 `game_id`s in the 2021-2023 play files with no
schedule row, and ruled that they be dropped. **80 of those 86 are the 2021 and 2022
postseason** — 38 and 42, exactly. The MIT play-by-play has had these games all
along; only the schedule series was missing them. The plays now join, so the L1
efficiency fit sees bowl and playoff plays for the tune seasons.

This also makes the merge **auditable without a CFBD key**, which matters because
`archive/cfbd/` is private under CFBD terms §3 and a fork will never hold it.
Reconstructing each final score from the repaired play-level scoreboard reproduces
CFBD in **79 of 80**. The single residual is `401442011` — the 2022 ReliaQuest Bowl,
Mississippi State 19 Illinois 10, decided in **overtime** — which is the exact
limitation §12 already documented for those columns. Pinned by id in
`test_cfbd_postseason_scores_reproduce_from_the_MIT_play_by_play`, so a second
disagreement fails the build rather than widening a tolerance.

### 13.4 Two latent bugs the merge exposed

Both were dormant while 2021 and 2022 had no postseason rows, and both would have
been silent:

1. **The conference-championship fallback asked the wrong rows about notes.**
   `_derive_game_type` skips its structural 2021 fallback when a season has any
   non-null `notes` on an FBS-vs-FBS game. The 38 backfilled bowl rows carry notes,
   so 2021 would have looked like a notes-bearing season, the fallback would not
   have fired, and **all ten of 2021's conference championships would have been
   labelled `regular`**. Fixed: the test now asks regular-season rows only, which is
   also the only place the fallback ever labels anything.
2. **The fallback's games-played tally counted bowls as pre-championship games.**
   Postseason rows carry `week = 1` (§1), so `week < champ_week` admitted every bowl
   game. Fixed with an explicit `season_type == 'regular'` guard.

### 13.5 Post-backfill numbers supersede the campaign documents

**`docs/analysis/` and the ADRs are frozen history and are NOT edited.** They record
what was measured, when, on the archive as it stood. Read them as of their dates.

Every number in them that was computed on 2021 or 2022 was computed on a frame
missing 80 games. `demo/` has been regenerated and its numbers now supersede the
frozen ones. Concretely, on the tune seasons:

| Quantity | Frozen (pre-backfill) | Post-backfill | Why it moved |
|---|---:|---:|---|
| Retrodictive violation window | 2,258 games | **2,338 games** | the 80 postseason games are FBS-vs-FBS and in weeks ≥ 5 |
| Schedule odds violation rate | 0.2015 | **0.2019** | more games, and postseason games are harder to order |
| L4 résumé violation rate | 0.1997 | **0.2015** | same |
| Random walker violation rate | 0.1997 | **0.2023** | it now *loses* to the headline rather than tying it |
| Postseason segment `n` | 39 bowls, 3 CFP | **113 bowls, 9 CFP** | three seasons of postseason instead of one |

**Nothing in the gate verdict changed:** margin MAE, RMSE and calibration are scored
on the `fbs_vs_fbs` segment from the headline week, which the backfill does not
touch, and all three still fail by the same margins. The violations criterion still
reports `False`. The tuned constants are **not** re-fitted here — re-running the
campaign on the widened frame would be a new campaign under a new pre-registered
protocol, and doing it silently, after seeing these numbers, is exactly what the
frozen protocol exists to prevent.

The one number that improves qualitatively rather than marginally is the postseason
segment: 42 games became 122, so `[weights].bowl_non_cfp = 0.25` is now supported by
a sample worth calling a sample.

### 13.6 `/info` does not count against quota, and neither does a 4xx

Measured over the whole backfill, on a free key whose counter started at exactly
`usedCalls: 0`:

| | |
|---|---:|
| HTTP requests actually issued | **15** |
| of which `GET /info` | 4 |
| of which returned 4xx (the season-wide `/games/teams`, twice) | 2 |
| `usedCalls` CFBD reported afterwards | **9** |

15 − 4 − 2 = 9, exactly. **CFBD bills neither `/info` nor a failed request.**

Two consequences for the Sunday job as report 01 §3.7 specified it:

1. **The quota guard is free.** §3.7 counts `GET /info` as call 1 of 22 and
   `GET /info/usage` as call 22; neither is billed, so the steady-state weekly run
   costs **20** billable calls rather than 22. There is no reason to economise on
   the guard, and `check_quota` can be called at the top of every entry point
   rather than once per job.
2. **A validation failure is not a wasted call**, so probing an endpoint's
   required parameters costs nothing but latency. That is how the `/games/teams`
   400 was resolved: ask season-wide, read the archived error body, discover that
   `week` is required, and ask again. Free.

Both figures are worth re-measuring if the key ever moves off the free tier: this
is observed behaviour on one tier and is not documented anywhere.

---

## 14. The 2025 season, as the archive actually has it

**Date:** 2026-08-15. Written while generating the 2025 fixture tree
([ADR 0012](adr/0012-2025-opens.md)), which is the first time this project has
built a full season of published documents out of 2025.

Nothing below blocked anything. All of it changes a count somebody might otherwise
compare against 2023 and find alarming.

### 14.1 Sixteen regular weeks, not fifteen

2023 has regular weeks 1-15 and 2025 has 1-16. Week 15 carries 9 FBS-vs-FBS games
and week 16 carries **one**, the conference-championship straggler. The fixture
tree therefore ships `week-01.json` through `week-16.json`, and any code that
assumed a fifteen-week season - a hard-coded `FIXTURE_WEEKS`, a strip that draws
fifteen tabs - is wrong for 2025 rather than broken by it. `index.json` publishes
the actual week list per season, and that is the field to read.

The one-game week is not a defect and does not need special handling: a bucket is
a bucket, `season_buckets` orders it by first kickoff like every other, and the
divergence curve simply flattens across it (mean |Δrank| is 0.91 at both week 15
and week 16, because one game moved almost nothing).

### 14.2 One bucket of postseason, where 2023 has four

In the model universe (at least one FBS or FCS participant):

| season | postseason buckets | detail |
|---|---|---|
| 2023 | `post-w11`…`post-w15`, `post-w01` | the FCS playoff bracket, 25 FCS-vs-FCS games |
| 2024 | `post-w01` | 4 FCS-vs-FCS games |
| 2025 | `post-w01` | 4 FCS-vs-FCS games |

2025 has 86 postseason rows across all divisions in weeks 1, 13 and 14, but the
32 games in weeks 13 and 14 are **D-II and D-III championships**, which the model
universe excludes. So 2025's season tree has 17 buckets where 2023's has 19, and
the last one is `2025-post-w01`. 2025 matches 2024 here, so this is a property of
how the parquet series carries recent FCS playoffs rather than anything specific
to 2025.

Consequence for the R(N, K) grid: `final` means through the bowls and the CFP for
2025, which is what it should mean, and the hindsight surface for every week is
computed against that window.

### 14.3 The one missing bowl is `game_id 401778314`, and it is missing PLAYS, not the game

This is the game behind the archive's "99.9%" 2025 coverage figure
([§0](#backfill-findings--corrections-and-constraints-for-implementation), the
`100/100/100/100/99.9%` line), and it is worth naming precisely because "a missing
bowl game" reads worse than what it is:

```
game_id 401778314   postseason week 1   New Mexico at Minnesota   17-20
```

The **game is present** in the schedule parquet with both scores, so it is in the
fit universe, it counts toward records, it is scored by the walk-forward harness,
and it appears in the résumé and schedule-odds layers exactly like every other
game. What is absent is its **play-by-play**: it is the only FBS-vs-FBS game of
2025 with zero rows in `play_by_play_2025.parquet`.

The effect is confined to L1, the efficiency layer, which sees one fewer game out
of 808. It cannot reach L2, L4 or the headline ordering, all of which read the
scoreboard. No guard fires and none should.

This is also the game report 01 flagged as a one-off December bowl labelled
`week=1`; [§1](#1-week-numbering-is-unreliable--key-on-season_type-week-never-week-alone)
already established that the label is a convention rather than an error, and 54
games in 2025 share it.

### 14.4 Two rows with `completed = true` and null scores, both D-II

```
401773541  regular w09  Angelo State at Sul Ross State      away 62, home null
401833535  regular w12  Kentucky State at Delta State       both null
```

The `completed` filter is load-bearing ([§4](#4-the-completed-filter-is-load-bearing))
and these two rows are why the loader also requires both score columns to be
non-null. Both are D-II-vs-D-II and neither is in the model universe, so they are
invisible to every layer. They are the whole of 2025's incompleteness: 3,829 of
3,831 canonical rows are complete, and 808/808 FBS-vs-FBS games have scores.

### 14.5 There is no CFBD `/games` pull for 2025 in the archive

`archive/cfbd/2025/season/` holds returning production, the transfer portal,
coaches and the week-1 rankings. It does **not** hold a `/games` response, which
is what `projection.forward.schedule()` reads to find a season's future calendar.
`forward.schedule(2025)` therefore returns an empty frame, which is the documented
answer for a fork with no key and is the correct one.

The 2025 Projection needs a calendar to project wins and schedule strength onto,
so `scripts/make_projection_2025.py` builds one from the MIT schedule parquet
instead: the season's regular-season games, projected to the seven columns
`forward.SCHEDULE_COLUMNS` names, restricted to games with at least one FBS
participant. `home_points` and `away_points` are not among those columns and are
never read, so no result reaches a win projection through that frame. 888 games.

**This is a substitution and it is declared on the artifact** as
`schedule_source`, rather than left for a reader to infer from a count. A schedule
is published months before a season is played, so the season's own calendar is the
honest stand-in for what an August projection would have been given.

### 14.6 Team count moved: 136 ranked teams, where 2023 ranked 133

Straightforward FBS expansion plus the FCS teams the fit universe carries. It
matters only because the divergence curve's denominator changes with it, so a
mean |Δrank| for 2025 is not directly comparable with 2023's at the third decimal.
`divergence.json` publishes the curve and `index.json` publishes `n_ranked` per
week; both are on the documents.
