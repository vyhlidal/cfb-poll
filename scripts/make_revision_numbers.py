"""The flagship revision figures, computed from the PUBLISHED fixture tree.

    uv run python scripts/make_revision_numbers.py --data ../sandbox/cfb-poll-data

Writes:

    <data>/<season>/revision.json      the published field the site quotes
    demo/<season>-revision-numbers.md  the same table, for a reader

WHY IT READS THE FIXTURES AND NOT THE MODEL. The site copy quotes these figures
in prose - "of the twenty-five teams in the week-5 top 25, N were in the wrong
place" - and a number in copy has to come off a published field or it is a claim
nobody can check. So this script opens `<season>/week-NN.json`, the same documents
the page renders, and counts. Every input is `rank`, `hindsight_rank` and
`rank_delta`, all of which are already on every row.

It is counting, not modelling. Nothing here fits, searches or selects anything,
and the script cannot reach the archive at all.

THE TWO SLICES, AND WHY BOTH ARE PUBLISHED. `divergence.json` carries the mean and
maximum across every ranked team, which is the right league-wide measure and is
the one the falsification test is written against. It is also, for a reader, the
wrong slice: nobody argues about rank 96. The top-25 tally beside it is the slice
people actually look at, and the document labels which is which so the two can
never be quoted as though they were the same number.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def tally(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The counting, on rows that carry a hindsight rank."""
    deltas = [int(r["rank_delta"]) for r in rows if r.get("rank_delta") is not None]
    if not deltas:
        return {
            "n": len(rows),
            "n_graded": 0,
            "n_moved": None,
            "share_moved": None,
            "mean_abs_delta": None,
            "max_abs_delta": None,
        }
    moved = [d for d in deltas if d != 0]
    return {
        "n": len(rows),
        "n_graded": len(deltas),
        "n_moved": len(moved),
        "share_moved": len(moved) / len(deltas),
        "mean_abs_delta": sum(abs(d) for d in deltas) / len(deltas),
        "max_abs_delta": max(abs(d) for d in deltas),
    }


def biggest_move(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    graded = [r for r in rows if r.get("rank_delta") is not None]
    if not graded:
        return None
    row = max(graded, key=lambda r: (abs(int(r["rank_delta"])), -int(r["rank"])))
    delta = int(row["rank_delta"])
    return {
        "team": row.get("team"),
        "rank": int(row["rank"]),
        "hindsight_rank": int(row["hindsight_rank"]),
        "rank_delta": delta,
        "record": row.get("record"),
        # `rank_delta` is rank minus hindsight rank, so a NEGATIVE delta means the
        # hindsight number is larger, which means the live poll had them too high.
        "direction": "over-rated live" if delta < 0 else "under-rated live",
    }


def build(data: Path, season: int) -> dict[str, Any]:
    season_dir = data / str(season)
    index = _read(data / "index.json")
    entry = next(s for s in index["seasons"] if int(s["season"]) == season)
    headline_start = int(entry["headline_start_week"])
    divergence = {int(d["week"]): d for d in _read(season_dir / "divergence.json")}

    by_week: list[dict[str, Any]] = []
    for week_meta in entry["weeks"]:
        week = int(week_meta["week"])
        path = season_dir / f"week-{week:02d}.json"
        if not path.exists():
            continue
        poll = _read(path)["poll"]
        league = divergence.get(week)
        by_week.append(
            {
                "week": week,
                "published": not bool(week_meta.get("provisional")),
                "top25": tally(poll[:25]),
                "league": {
                    "mean_abs_delta": (league or {}).get("mean_abs_delta"),
                    "max_abs_delta": (league or {}).get("max_abs_delta"),
                    "n_ranked": int(week_meta.get("n_ranked") or 0),
                },
                "biggest_move_in_top25": biggest_move(poll[:25]),
            }
        )

    headline = next((w for w in by_week if w["week"] == headline_start), None)
    published = [w for w in by_week if w["published"] and w["top25"]["mean_abs_delta"] is not None]
    settled = min(published, key=lambda w: w["top25"]["mean_abs_delta"]) if published else None
    last = published[-1] if published else None

    return {
        "schema_version": 1,
        "season": season,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "the published fixture tree; every input is a field on a poll row",
        "headline_start_week": headline_start,
        "definitions": {
            "rank_delta": (
                "rank minus hindsight_rank, published on every row. Negative means "
                "the hindsight surface has the team lower than the live poll did, "
                "which is to say the live poll had them too high."
            ),
            "top25": "the twenty-five rows the page shows, on the LIVE ordering.",
            "league": (
                "every ranked team, from divergence.json. This is the slice the "
                "stability criterion is written against and it is not the slice a "
                "reader is looking at."
            ),
        },
        "headline": headline,
        "settled": (
            {"week": settled["week"], "top25": settled["top25"]} if settled else None
        ),
        "last_published": ({"week": last["week"], "top25": last["top25"]} if last else None),
        "by_week": by_week,
    }


def render(payload: dict[str, Any], others: dict[int, dict[str, Any]]) -> str:
    season = payload["season"]
    headline = payload["headline"]
    start = payload["headline_start_week"]
    lines: list[str] = []
    add = lines.append

    add(f"# The {season} revision, in numbers")
    add("")
    add(
        f"Every figure on this page is a field in "
        f"`cfb-poll-data/{season}/revision.json`, and every field in that file was "
        f"counted off the published week documents the site renders. Nothing here "
        "is recomputed from the model."
    )
    add("")

    top = headline["top25"]
    add(f"## Week {start}, the first published poll")
    add("")
    add(
        f"**{top['n_moved']} of the {top['n_graded']} teams in the week-{start} top "
        "25 are in a different place once the season's answers are substituted "
        f"in.** The average miss is **{top['mean_abs_delta']:.2f} places** and the "
        f"largest is **{top['max_abs_delta']}**."
    )
    add("")
    mover = headline["biggest_move_in_top25"]
    if mover:
        add(
            f"The largest single move inside that 25 is {mover['team']} "
            f"({mover['record']}), ranked #{mover['rank']} live and #"
            f"{mover['hindsight_rank']} in hindsight: {mover['direction']} by "
            f"{abs(mover['rank_delta'])} places."
        )
        add("")
    add(
        f"Across the whole league that week the mean absolute rank change is "
        f"{headline['league']['mean_abs_delta']:.2f} places over "
        f"{headline['league']['n_ranked']} ranked teams, with a maximum of "
        f"{headline['league']['max_abs_delta']}. The league number is larger than "
        "the top-25 number and that is the finding rather than a caveat: the poll "
        "revises hardest exactly where it is least confident, which is the bottom "
        "of the table, where schedules are thin and opponents are unknown."
    )
    add("")

    add("## Convergence, week by week")
    add("")
    add(
        "The top-25 columns are the slice a reader looks at. The league columns "
        "are the slice the stability criterion is written against. They are "
        "different numbers and the table keeps them apart."
    )
    add("")
    add(
        "| week | published | top 25 moved | top 25 mean \\|Δ\\| | top 25 max "
        "| league mean \\|Δ\\| | league max |"
    )
    add("|---|:---:|---:|---:|---:|---:|---:|")
    for week in payload["by_week"]:
        t, lg = week["top25"], week["league"]
        add(
            f"| {week['week']} | {'yes' if week['published'] else 'no'} | "
            f"{t['n_moved'] if t['n_moved'] is not None else '—'} of {t['n_graded']} | "
            f"{_num(t['mean_abs_delta'])} | "
            f"{t['max_abs_delta'] if t['max_abs_delta'] is not None else '—'} | "
            f"{_num(lg['mean_abs_delta'])} | "
            f"{lg['max_abs_delta'] if lg['max_abs_delta'] is not None else '—'} |"
        )
    add("")

    settled, last = payload["settled"], payload["last_published"]
    if settled and last:
        add(
            f"The top-25 curve falls from {headline['top25']['mean_abs_delta']:.2f} "
            f"places at week {start} to {last['top25']['mean_abs_delta']:.2f} at "
            f"week {last['week']}, and its quietest published week is week "
            f"{settled['week']} at {settled['top25']['mean_abs_delta']:.2f}. That "
            "shape is the thing to check, not any individual row: a poll whose "
            "week-12 top 25 still moved several places in hindsight would be "
            "telling you its week-12 top 25 was never worth reading."
        )
        add("")

    if others:
        add("## The same figures on the other published seasons")
        add("")
        add("| season | week-5 top 25 moved | week-5 mean \\|Δ\\| | final top 25 mean \\|Δ\\| |")
        add("|---|---:|---:|---:|")
        for other_season, other in sorted(others.items()):
            oh = other["headline"]["top25"]
            ol = (other["last_published"] or {}).get("top25") or {}
            add(
                f"| {other_season} | {oh['n_moved']} of {oh['n_graded']} | "
                f"{_num(oh['mean_abs_delta'])} | {_num(ol.get('mean_abs_delta'))} |"
            )
        this = payload["headline"]["top25"]
        this_last = (payload["last_published"] or {}).get("top25") or {}
        add(
            f"| **{season}** | **{this['n_moved']} of {this['n_graded']}** | "
            f"**{_num(this['mean_abs_delta'])}** | "
            f"**{_num(this_last.get('mean_abs_delta'))}** |"
        )
        add("")
        add(
            "Two seasons is two seasons. The table is here so a reader can see that "
            "the shape repeats, and it is not enough to claim that it always will."
        )
        add("")

    add(f"Generated by `scripts/make_revision_numbers.py` at {payload['generated_at']}.")
    return "\n".join(lines) + "\n"


def _num(value: float | None, places: int = 2) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT.parent / "sandbox" / "cfb-poll-data")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument(
        "--compare", type=int, nargs="*", default=[2023], help="Seasons for the contrast table."
    )
    args = parser.parse_args()

    payload = build(args.data, args.season)
    out = args.data / str(args.season) / "revision.json"
    out.write_text(
        json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )

    others = {}
    for other in args.compare:
        if other == args.season:
            continue
        if (args.data / str(other) / "divergence.json").exists():
            others[other] = build(args.data, other)

    (DEMO / f"{args.season}-revision-numbers.md").write_text(
        render(payload, others), encoding="utf-8"
    )

    head = payload["headline"]["top25"]
    print(
        f"{args.season} week {payload['headline_start_week']}: {head['n_moved']} of "
        f"{head['n_graded']} top-25 teams in a different hindsight spot, mean "
        f"|delta| {head['mean_abs_delta']:.2f}, max {head['max_abs_delta']}"
    )
    print(f"wrote: {out}")
    print(f"wrote: demo/{args.season}-revision-numbers.md")


if __name__ == "__main__":
    main()
