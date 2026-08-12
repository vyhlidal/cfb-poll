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
