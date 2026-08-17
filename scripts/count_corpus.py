#!/usr/bin/env python
"""Count what the model actually read, and pin it in `data/corpus-counts.json`.

WHY THIS EXISTS. A share card says "8,117 games and 1,235,232 plays" on it, in
front of people who have never heard of this project, and those two numbers are
the whole reason to believe the sentence around them. `AGENTS.md` is explicit
that anything a run produced is regenerated rather than quoted from a file
somebody wrote once, and a number typed into a renderer is exactly the number
that goes stale the first time a season lands.

So the card reads a committed JSON pin, and this script is the only thing that
writes it. Re-run it after an archive sync and the card's sentence is true again
without anybody editing a Python string:

    uv run python scripts/count_corpus.py

IT COUNTS THROUGH THE PIPELINE'S OWN LOADERS AND NOT THROUGH THE PARQUET FILES.
`sportsdataverse.load_games(..., universe="model")` is what a fit is handed, so
it applies the fit universe from `configs/default.toml` (at least one FBS or FCS
participant, ADR 0006) and drops anything not completed with a score. Counting
raw rows instead would publish a bigger, easier number that describes a file
rather than the model: the schedules feed carries about 17,400 rows over these
five seasons, and the model reads 8,117 of them. The smaller number is the honest
one and it is the one that ships.

THE THIRD FIGURE IS NOT A COUNT OF ANYTHING ON DISK. `[bootstrap] draws` is a
committed constant, and `model/bootstrap.simulate` reads it to "simulate `draws`
seasons on the fixed schedule and re-rank each one". It is copied here so a
surface can print all three figures from one file, and it is labelled as a
config constant rather than as a measurement.

IT FITS NOTHING, so it needs no BLAS pin. It does read the play archive, which is
a couple of gigabytes off disk and takes a minute.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cfbpoll.config import REPO_ROOT, load_config
from cfbpoll.ingest import plays as plays_ingest
from cfbpoll.ingest import sportsdataverse as sdv

#: The seasons the published model stands on: fitted on 2021-2023, validated once
#: on 2024, and 2025 scored as the holdout. Five, and the card says five.
DEFAULT_SEASONS: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025)

DEFAULT_OUT = REPO_ROOT / "data" / "corpus-counts.json"


def count(seasons: tuple[int, ...], archive: Path | None = None) -> dict[str, Any]:
    """The three figures, plus the per-season split that makes them checkable."""
    games = sdv.load_games(list(seasons), archive, universe="model")
    per_season = {
        str(int(row["season"])): int(row["len"])
        for row in games.group_by("season").len().sort("season").to_dicts()
    }

    plays_total = 0
    plays_by_season: dict[str, int] = {}
    for season in seasons:
        frame = plays_ingest.load_plays([season], archive)
        plays_by_season[str(season)] = frame.height
        plays_total += frame.height
        del frame

    config = load_config()
    draws = int(config["bootstrap"]["draws"])

    return {
        "schema_version": 1,
        "note": (
            "What the model read, counted through the pipeline's own loaders. "
            "Regenerate with `uv run python scripts/count_corpus.py` after an "
            "archive sync. Surfaces print these; nothing types them by hand."
        ),
        "seasons": list(seasons),
        "games": int(games.height),
        "games_universe": "model",
        "games_by_season": per_season,
        "plays": int(plays_total),
        "plays_by_season": plays_by_season,
        "simulated_seasons": draws,
        "simulated_seasons_source": "configs/default.toml [bootstrap] draws",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--archive", type=Path, default=None)
    parser.add_argument(
        "--seasons",
        type=str,
        default=",".join(str(s) for s in DEFAULT_SEASONS),
        help="Comma-separated. Defaults to the five the published model stands on.",
    )
    args = parser.parse_args()

    seasons = tuple(int(s) for s in str(args.seasons).split(",") if s.strip())
    payload = count(seasons, args.archive)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"wrote {args.out}")
    print(f"  seasons           {seasons}")
    print(f"  games  (model)    {payload['games']:,}")
    print(f"  plays             {payload['plays']:,}")
    print(f"  simulated seasons {payload['simulated_seasons']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
