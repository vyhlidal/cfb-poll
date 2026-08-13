"""Ingest adapters. Every source is a TRANSPORT, not a dependency.

The organising principle is report 01 §5.4: every byte a source delivers is
written to our own storage, immutably, BEFORE anything else touches it. Archive
raw and unmodified - the exact JSON body, the exact parquet bytes. Transform
before store loses the ability to re-derive differently later.

Two sources, deliberately split (report 01 §1):
  cfbd.py            - the weekly in-season pull. PRIVATE archive: CFBD terms §3
                       bar redistributing raw API data without permission.
  sportsdataverse.py - the 2021-2025 backfill and the standing fallback. MIT, so
                       this archive CAN be republished, which is what makes the
                       reproducibility claim independent of anyone's permission.

Each is cross-validation for the other; two substantially independent pipelines
over the same games is a real data-quality check, not a redundant cost. That
check has now been run rather than promised: the 80 postseason games CFBD supplies
for 2021-2022 reproduce from the MIT play-by-play in 79 of 80, and the one
residual is an overtime game whose limitation docs/data-findings.md §12 already
documented.

The two pipelines also turn out to share an id space - CFBD game ids ARE ESPN
game ids, measured 126/126 - so reconciliation is an integer join and not a
crosswalk (docs/data-findings.md §13).

STATUS: real. `cfbd.py` (client, quota guard, offline archive readers),
`archive.py` (append-only write and verify), `sportsdataverse.py` (the games
loader), `plays.py`, `teams.py` (colours and the generated mark) and `windows.py`
all work. `download_season`/`backfill`/`push_r2` remain stubs.
"""
