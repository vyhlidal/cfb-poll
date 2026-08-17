"""The accuracy scoreboard. Chain the seasons, score the opening weeks, publish all of it.

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
        uv run python scripts/make_chain.py

Writes:

    demo/projection-chain.md      the table, the protocol, and the lever registry
    demo/projection-chain.json    every number in it, machine-readable
    demo/levers.json              the registry on its own, for the site to render

NO NETWORK. Archive only.

THIS IS THE FILE THAT REPLACES THE GATE. The gate was a pass/fail ceremony with a
threshold chosen in advance, and its verdict was a boolean that told a reader
nothing about how good the model actually is. What a reader wants is the
scoreboard: here is what we said in August, here is what happened, here is how
often we were right, and here is the same figure for the sportswriters and for
the do-nothing baseline. Published every time, whatever it says.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cfbpoll import levers as lever_registry
from cfbpoll.config import DEFAULT_CONFIG_PATH, config_hash, load_config
from cfbpoll.ingest.plays import load_plays
from cfbpoll.ingest.sportsdataverse import load_games
from cfbpoll.projection import PROJECTION_VERSION, chain, systems

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"

CFG = load_config()
SEASONS = [2021, 2022, 2023, 2024, 2025]
TARGETS = [2022, 2023, 2024, 2025]
WINDOWS = {"week_1": (1, 1), "weeks_1_4": (1, 4)}

#: How each scored system is described on the page. The order is the column order.
LABELS: dict[str, str] = {
    "carryover": "last season's ratings, unchanged",
    "projection_v2": "the old model (projection-2.0.0)",
    "projection_v3": "this model (projection-3.0.0)",
    "ap_preseason": "the AP writers' August ballot",
}


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def build() -> chain.ChainResult:
    games = load_games(SEASONS)
    plays = load_plays(SEASONS)
    inputs = systems.prepare(games, SEASONS, plays, CFG)
    live = systems.ProjectionLevers.from_config(CFG)
    return chain.run_chain(
        games,
        TARGETS,
        systems.builders(live),
        inputs.power,
        inputs.home_field,
        inputs.fbs,
        windows=WINDOWS,
    )


def _pct(cell: dict[str, Any] | None) -> str:
    if not cell or not cell.get("n_games"):
        return "—"
    return f"{cell['su_accuracy'] * 100:.1f}%"


def _pct_n(cell: dict[str, Any] | None) -> str:
    if not cell or not cell.get("n_games"):
        return "—"
    return f"{cell['su_accuracy'] * 100:.1f}% ({cell['n_games']})"


def write(result: chain.ChainResult) -> None:
    payload = {
        "artifact": "THE ACCURACY SCOREBOARD — walk-forward, every season, every system",
        "projection_version": PROJECTION_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "config_hash": config_hash(DEFAULT_CONFIG_PATH),
        "levers": lever_registry.registry_document(),
        "live_lever_values": systems.ProjectionLevers.from_config(CFG).as_dict(),
        **result.as_dict(),
    }
    (DEMO / "projection-chain.json").write_text(
        json.dumps(payload, indent=1, default=str) + "\n", encoding="utf-8"
    )
    (DEMO / "levers.json").write_text(
        json.dumps(
            {
                "generated_at": payload["generated_at"],
                "git_sha": payload["git_sha"],
                "live_values": payload["live_lever_values"],
                **lever_registry.registry_document(),
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = result.summary
    lines: list[str] = []
    add = lines.append
    add("# The accuracy scoreboard")
    add("")
    add(
        "> This page replaces the gate. The gate was a pass/fail ceremony against a "
        "threshold, and its verdict was a boolean. This is the scoreboard: what the "
        "model said in August, what happened, and how often it was right, beside the "
        "same figure for the sportswriters and for doing nothing at all."
    )
    add("")
    add(
        f"`{PROJECTION_VERSION}` · generated {payload['generated_at']} · "
        f"`{payload['git_sha'][:10]}`"
    )
    add("")
    add("## The protocol, which is the whole of the honesty")
    add("")
    add(result.as_dict()["protocol"])
    add("")
    add(
        "A system with no legal way to exist for a season is reported as absent rather "
        "than given a shortcut. `projection_v2` and `projection_v3` have no 2022 row "
        "because the archive starts in 2021 and there is no completed transition to fit "
        "a recipe on before 2022; fitting one on 2022 itself and then scoring 2022 "
        "would be a description wearing a projection's clothes."
    )
    add("")

    for universe, title, blurb in (
        (
            "all_fbs",
            "Every game with an FBS team in it",
            "This is what a reader means by week 1. Half of week 1 is an FBS team "
            "playing an FCS team, and a model that quietly drops those is scoring "
            "itself on the half of the slate it finds interesting.",
        ),
        (
            "fbs_vs_fbs",
            "FBS against FBS only",
            "The hard subset, where nobody is picking on anybody. Smaller samples, and "
            "the honest headline for anyone comparing this with another rating system.",
        ),
    ):
        add(f"## {title}")
        add("")
        add(blurb)
        add("")
        add("| system | week 1 | weeks 1-4 |")
        add("|---|---:|---:|")
        for system, label in LABELS.items():
            cell = summary[universe].get(system, {})
            add(
                f"| {label} | {_pct_n(cell.get('week_1'))} | "
                f"{_pct_n(cell.get('weeks_1_4'))} |"
            )
        add("")
        add("Season by season, week 1:")
        add("")
        add("| season | " + " | ".join(LABELS.values()) + " |")
        add("|---" * (len(LABELS) + 1) + "|")
        for link in result.links:
            row = [str(link.target_season)]
            for system in LABELS:
                row.append(_pct_n(link.scores.get(system, {}).get(universe, {}).get("week_1")))
            add("| " + " | ".join(row) + " |")
        add("")

    add("## What moved, and what measured it")
    add("")
    add(
        "Three changes separate this model from the one it replaces, and each was "
        "measured before it was adopted rather than after."
    )
    add("")
    add(
        "1. **A rating earned outside FBS no longer transplants at face value.** "
        "602 crossover games price the move at 13.4 points; 68 games from six promoted "
        "programs give 9.8 of it back; and no promoted team is projected above the best "
        "first FBS season a promoted program has actually had. This is the single "
        "largest source of the gain above, and it is almost entirely in the crossover "
        "games — which is exactly where it should be."
    )
    add(
        "2. **A second season of memory.** The year before last counts at 0.2. Worth "
        "about half a point of week-one accuracy, which is inside the noise band on "
        "this many games and is reported as a peak rather than a discovery."
    )
    add(
        "3. **The freeze is gone.** The recipe refits whenever a season closes, so the "
        "2024-to-2025 transition is now in the design. What replaces the freeze is the "
        "vintage record: every board ever published stays up with the coefficients it "
        "ran under, so \"what did you say in August\" is answered by the archive rather "
        "than by refusing to learn."
    )
    add("")
    add("## The levers")
    add("")
    add(
        "Every number below is a choice the model is genuinely uncertain about, and "
        "every default was measured rather than picked. The two things that are not "
        "levers, and never will be, are at the bottom."
    )
    add("")
    add("| lever | what it does | range | default |")
    add("|---|---|---|---:|")
    for lever in lever_registry.LEVERS:
        # A CATEGORICAL LEVER HAS NO RANGE. `publication.headline_ordering` is
        # three named orderings rather than a quantity, and printing "0 to 2" over
        # them would invite a reader to ask for 1.5. This table used to format
        # every lever with `:g` and raised TypeError the moment one of them stopped
        # being a number, which is the useful kind of breakage: the renderer that
        # had a hidden assumption is the renderer that had to be told.
        if lever.is_categorical:
            span = ", ".join(f"`{v}`" for v in lever.values)
            default = f"`{lever.default}`"
        else:
            high = "no limit" if lever.high == float("inf") else f"{lever.high:g}"
            span = f"{lever.low:g} to {high}"
            default = f"{lever.default:g}"
        add(f"| **{lever.label}** | {lever.plain} | {span} | {default} |")
    add("")
    for item in lever_registry.registry_document()["untouchable"]:
        add(f"**{item['rule']}** {item['detail']}")
        add("")

    (DEMO / "projection-chain.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    result = build()
    write(result)
    for universe in ("all_fbs", "fbs_vs_fbs"):
        print(f"  {universe}")
        for system in LABELS:
            cell = result.summary[universe].get(system, {})
            print(
                f"    {system:<16} week1 {_pct(cell.get('week_1')):>7}   "
                f"weeks1-4 {_pct(cell.get('weeks_1_4')):>7}"
            )
    print("wrote demo/projection-chain.{md,json} and demo/levers.json")


if __name__ == "__main__":
    main()
