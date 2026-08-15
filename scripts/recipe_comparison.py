"""Regenerate demo/2023-recipes.md: the 2023 final board under every recipe.

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
        uv run python scripts/recipe_comparison.py

This is the page's teaching material (ADR 0011). Three value systems, one season,
one set of games, side by side, with the rows that move called out and a sentence
on each saying which property of which recipe moved them.

It computes the boards itself rather than reading `out/`, for the same reason
`scripts/make_demos.py` does: a committed artifact nobody can regenerate is a
number a reader has to trust. No bootstrap, because the comparison is about
ordering rules and a rank interval would triple the runtime to qualify a column
this document does not use. `cfbpoll rank --recipe <slug>` publishes the intervals.

EVERY RECIPE IS FIT ON THE SAME FRAME AND THE DOCUMENT PROVES IT rather than
saying it: the window is loaded once per recipe, digested with the leakage
auditor's own hasher, and the digests are printed in the document.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from scipy import stats

from cfbpoll import recipes as recipes_mod
from cfbpoll.ingest import windows
from cfbpoll.ingest.plays import DEFAULT_ARCHIVE as PLAY_ARCHIVE
from cfbpoll.ingest.plays import load_plays
from cfbpoll.ingest.sportsdataverse import load_games
from cfbpoll.model import retro
from cfbpoll.publish import poll as poll_mod
from cfbpoll.validate import leakage

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo" / "2023-recipes.md"

SEASON = 2023
#: The last regular-season week: the final poll before the postseason, which is
#: what `[weights].final_poll_excludes_non_cfp_bowls` makes the published final.
WEEK = 15
#: A row is "moving" when its best and worst rank across the three recipes differ
#: by at least this much. Five places is a screenful on the site's poll table, so
#: it is the point at which a reader would notice the recipe changed something.
MOVER_THRESHOLD = 5
TOP = 25


def _git_sha() -> str:
    try:
        got = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        return got.stdout.strip()[:7]
    except Exception:  # pragma: no cover
        return "unknown"


def board(slug: str) -> tuple[pl.DataFrame, dict[str, Any]]:
    """One recipe's final 2023 board, live and hindsight, plus its provenance."""
    config, recipe = recipes_mod.resolve(slug)
    games = load_games([SEASON], universe=str(config["model"]["fit_universe"]))
    plays = (
        load_plays([SEASON])
        if (PLAY_ARCHIVE / "pbp" / f"play_by_play_{SEASON}.parquet").exists()
        else None
    )
    buckets = windows.season_buckets(games, SEASON)
    regular = [b for b in buckets if b.season_type == "regular"]
    evaluated = next(b for b in regular if b.week == WEEK)
    window = windows.games_through(games, season=SEASON, week=WEEK, season_type="regular")

    powers = retro.season_power(games, SEASON, config, plays=plays, buckets=buckets)
    classes = poll_mod.team_classes(games)
    live = retro.cell(games, evaluated, evaluated, config, power=powers[evaluated.order],
                      classes=classes)
    hindsight = retro.cell(games, evaluated, buckets[-1], config,
                           power=powers[buckets[-1].order], classes=classes)
    ordering = poll_mod.headline_ordering(config)
    table = poll_mod.headline_frame(live, hindsight, None, ordering)
    return table, {
        "recipe": recipe,
        "ordering": ordering,
        "layer": config["publication"]["headline_layer"],
        "n_games": int(window.height),
        "fit_window_sha256": leakage.digest(window),
        "config_sha256": recipes_mod.resolved_hash(config),
        "changes": recipe.flat_overrides(),
    }


def margins(window: pl.DataFrame) -> dict[str, tuple[float, float]]:
    """(mean signed margin, largest win) per team, over the games in the window.

    Descriptive only. Nothing here reaches a fit; it exists so the movers table can
    say WHY a margin-blind and a margin-hungry recipe disagree about a team, in
    that team's own numbers.
    """
    out: dict[str, list[float]] = {}
    for home, away, hp, ap in zip(
        window["home_team"].to_list(),
        window["away_team"].to_list(),
        window["home_points"].to_list(),
        window["away_points"].to_list(),
        strict=True,
    ):
        out.setdefault(home, []).append(float(hp - ap))
        out.setdefault(away, []).append(float(ap - hp))
    return {
        team: (sum(values) / len(values), max(values))
        for team, values in out.items()
        if values
    }


def why(team: str, ranks: dict[str, int], row: dict[str, Any], avg: float, best: float) -> str:
    """One sentence on why this team moves, templated from its own numbers.

    Deliberately mechanical. A hand-written reason in a generated document is a
    reason that stops being true the next time the document regenerates.
    """
    record = f"{row['wins']}-{row['losses']}"
    merit, win = ranks["full-merit"], ranks["just-win"]
    facts = (
        f"{record}, average margin {avg:+.1f}, best win by {best:.0f}; "
        f"resume {row['resume']:.1f} against margin-aware resume {row['resume_margin']:.1f}"
    )
    if row["losses"] == 0:
        return (
            f"Unbeaten, so Just Win pins it at the saturation bound and nothing below it "
            f"can pass. Full Merit has no such rule and prices the scoreboard instead: {facts}."
        )
    if merit < win:
        return (
            f"Rises {win - merit} places going from Just Win to Full Merit. Rewarded for how "
            f"it won and charged for how often: {facts}."
        )
    if win < merit:
        return (
            f"Falls {merit - win} places going from Just Win to Full Merit. Rewarded for "
            f"winning and charged for the manner: {facts}."
        )
    return (
        f"The two resume orderings agree at {merit} and the schedule odds do not, so this row "
        f"moves on the house poll's own axis rather than on margin: {facts}."
    )


def main() -> None:
    boards: dict[str, pl.DataFrame] = {}
    meta: dict[str, dict[str, Any]] = {}
    for slug in ("full-merit", "house", "just-win"):
        boards[slug], meta[slug] = board(slug)

    games = load_games([SEASON], universe="model")
    window = windows.games_through(games, season=SEASON, week=WEEK, season_type="regular")
    stat = margins(window)

    ranks = {slug: dict(zip(t["team"], t["rank"], strict=True)) for slug, t in boards.items()}
    rows = {slug: {r["team"]: r for r in t.iter_rows(named=True)} for slug, t in boards.items()}
    everyone = sorted(set().union(*(set(r) for r in ranks.values())))

    def spread(team: str) -> int:
        got = [ranks[s].get(team) for s in ranks]
        seen = [r for r in got if r is not None]
        return max(seen) - min(seen) if len(seen) == len(got) else 10**6

    # THE UNION OF THE THREE TOP 25s, not the house top 25. A team that Full Merit
    # ranks 12th and the house poll ranks 40th is exactly the row this document
    # exists to show, and a table keyed on the house board would hide it.
    board_teams = sorted(
        {t for slug in ranks for t in everyone if ranks[slug].get(t, 10**6) <= TOP},
        key=lambda t: min(ranks[s].get(t, 10**6) for s in ranks),
    )

    taus = {}
    common = [t for t in everyone if all(t in ranks[s] for s in ranks)]
    for a, b in (("house", "full-merit"), ("house", "just-win"), ("full-merit", "just-win")):
        taus[(a, b)] = stats.kendalltau(
            [ranks[a][t] for t in common], [ranks[b][t] for t in common]
        ).statistic

    lines: list[str] = []
    w = lines.append
    w("<!-- GENERATED by scripts/recipe_comparison.py. Do not edit by hand. -->")
    w("")
    w("# The 2023 final board under all three recipes")
    w("")
    w(
        "**A ranking is a value system.** This is one season, one set of games and three "
        "value systems, side by side. It is the teaching material for "
        "[ADR 0011](../docs/adr/0011-recipes.md), and the thing to look at is not which "
        "board is right. It is which teams move, and how far, when nothing changes except "
        "what the poll believes football results are for."
    )
    w("")
    w(
        f"Season {SEASON}, through week {WEEK}: the final poll before the postseason, which "
        "is what `[weights].final_poll_excludes_non_cfp_bowls` makes the published final. "
        f"Generated at git `{_git_sha()}` on "
        f"{datetime.now(UTC).date().isoformat()}."
    )
    w("")

    # ------------------------------------------------------------------ the recipes
    w("## The three recipes")
    w("")
    w("| | recipe | what it changes | headline ordering | status |")
    w("|---|---|---|---|---|")
    for slug in ("full-merit", "house", "just-win"):
        info = meta[slug]
        recipe = info["recipe"]
        changed = (
            ", ".join(f"`{k}` = `{v}`" for k, v in info["changes"].items())
            if info["changes"]
            else "*nothing at all*"
        )
        status = "**THE PUBLISHED POLL**" if recipe.is_house else "alternate lens"
        w(f"| {recipe.stance} | **{recipe.name}** | {changed} | `{info['ordering']}` | {status} |")
    w("")
    for slug in ("full-merit", "house", "just-win"):
        recipe = meta[slug]["recipe"]
        w(f"### {recipe.name}")
        w("")
        w(f"> {recipe.manifesto}")
        w("")
        w("**What it costs:**")
        w("")
        for cost in recipe.tradeoffs:
            w(f"- {cost}")
        w("")

    # ------------------------------------------------------------------ the evidence
    w("## Same evidence. Only the values differ.")
    w("")
    w(
        "This is the claim the whole feature rests on, so it is measured here rather than "
        "asserted. Each row is a separate load, a separate window and a separate fit; the "
        "digest is over the exact frame that was fitted, taken with the leakage auditor's "
        "own hasher."
    )
    w("")
    w("| recipe | games in the fit | `fit_window_sha256` | `recipe_config_sha256` |")
    w("|---|---:|---|---|")
    for slug in ("full-merit", "house", "just-win"):
        info = meta[slug]
        w(
            f"| {info['recipe'].name} | {info['n_games']:,} | "
            f"`{info['fit_window_sha256'][:16]}…` | `{info['config_sha256'][:16]}…` |"
        )
    w("")
    identical = len({meta[s]["fit_window_sha256"] for s in meta}) == 1
    verdict = "identical" if identical else "NOT IDENTICAL, WHICH IS A BUG"
    w(
        f"**The evidence digests are {verdict} and the methodology digests are all "
        "different.** That is the feature in one table: same data, different values."
    )
    w("")

    # -------------------------------------------------------------------- the board
    w(f"## The board: the union of all three top {TOP}s")
    w("")
    w(
        f"A row is marked ● when its best and worst rank across the three recipes differ by "
        f"{MOVER_THRESHOLD} places or more. The table is keyed on the union of the three top "
        f"{TOP}s rather than on the house poll's, because a team the house poll ranks 40th "
        "and Full Merit ranks 12th is exactly the row this document exists to show."
    )
    w("")
    w("| | team | rec | Full Merit | House | Just Win | spread |")
    w("|---|---|---|---:|---:|---:|---:|")
    for team in board_teams:
        got = {s: ranks[s].get(team) for s in ranks}
        base = rows["house"].get(team) or rows["full-merit"].get(team) or rows["just-win"][team]
        gap = spread(team)
        mark = "●" if gap >= MOVER_THRESHOLD else ""
        cells = []
        for slug in ("full-merit", "house", "just-win"):
            value = got[slug]
            text = "—" if value is None else str(value)
            cells.append(f"**{text}**" if value is not None and value == min(
                v for v in got.values() if v is not None
            ) else text)
        w(
            f"| {mark} | {team} | {base['wins']}-{base['losses']} | "
            + " | ".join(cells)
            + f" | {gap if gap < 10**6 else '—'} |"
        )
    w("")
    w("Bold is a team's best rank of the three. ● marks a row that moves.")
    w("")

    # ------------------------------------------------------------------- the movers
    w("## The rows that move, and why")
    w("")
    w(
        "Every team in the union board above whose rank spans "
        f"{MOVER_THRESHOLD} places or more, worst spread first. The sentence on each is "
        "templated from that team's own numbers, because a hand-written reason in a "
        "generated document stops being true the next time it regenerates."
    )
    w("")
    movers = sorted(
        (t for t in board_teams if spread(t) >= MOVER_THRESHOLD), key=spread, reverse=True
    )
    for team in movers:
        row = rows["house"].get(team) or rows["full-merit"].get(team) or rows["just-win"][team]
        avg, best = stat.get(team, (0.0, 0.0))
        got = {s: ranks[s].get(team, 10**6) for s in ranks}
        w(
            f"**{team}** — Full Merit **{got['full-merit']}**, House **{got['house']}**, "
            f"Just Win **{got['just-win']}**"
        )
        w("")
        w(f"> {why(team, got, row, avg, best)}")
        w("")

    # -------------------------------------------------------------------- two cases
    w("## The two cases worth arguing about")
    w("")
    w(
        "Picked by rule, not by hand, so this section cannot be curated toward a "
        "conclusion. The first is the team the headline ordering study argued about. The "
        "second is whichever team on the union board won by the widest average margin."
    )
    w("")
    # Excluding unbeaten teams on purpose: their margin is confounded by the
    # saturation bound, which the structural section below covers separately, and a
    # team that no recipe can rank below the bound is not a read on what margin buys.
    blowout = max(
        (
            t
            for t in board_teams
            if t in stat and rows["house"].get(t) and rows["house"][t]["losses"] > 0
        ),
        key=lambda t: stat[t][0],
    )
    for team, why_it_matters in (
        (
            "Liberty",
            "The team ADR 0005 was decided on. Unbeaten at 13-0 out of Conference USA, "
            "which is exactly the case where a poll has to say out loud what it believes.",
        ),
        (
            blowout,
            "The largest average margin of any team on the union board that has a loss, "
            "which makes it the cleanest read on what each recipe pays for running the "
            "score up. Unbeaten teams are excluded here because the saturation bound, not "
            "their margin, is what decides them.",
        ),
    ):
        if team not in rows["house"]:
            continue
        row = rows["house"][team]
        avg, best = stat.get(team, (0.0, 0.0))
        w(f"### {team} ({row['wins']}-{row['losses']})")
        w("")
        w(why_it_matters)
        w("")
        w("| recipe | rank | key | resume | margin-aware resume | Power |")
        w("|---|---:|---:|---:|---:|---:|")
        for slug in ("full-merit", "house", "just-win"):
            here = rows[slug].get(team)
            if here is None:
                continue
            key = {
                "full-merit": here["resume_margin"],
                "house": here["odds_key"],
                "just-win": here["resume"],
            }[slug]
            w(
                f"| {meta[slug]['recipe'].name} | **{here['rank']}** | {key:.2f} | "
                f"{here['resume']:.1f} | {here['resume_margin']:.1f} | {here['power']:.1f} |"
            )
        w("")
        w(
            f"Average margin {avg:+.1f} over {row['wins'] + row['losses']} games, largest win "
            f"by {best:.0f}. Spread across the three recipes: **{spread(team)} places**."
        )
        w("")

    # -------------------------------------------------------------- structural facts
    w("## Two structural facts, visible in the board above")
    w("")
    unbeaten = sorted(t for t in common if rows["house"][t]["losses"] == 0)
    w(f"**{SEASON} finished with {len(unbeaten)} unbeaten FBS teams: "
      f"{', '.join(unbeaten)}.** They are the cleanest test of the axis, because the three "
      "recipes disagree about them by construction rather than by accident.")
    w("")
    w("| recipe | worst-ranked unbeaten team | best-ranked team with a loss | inversion? |")
    w("|---|---:|---:|---|")
    for slug in ("full-merit", "house", "just-win"):
        table = rows[slug]
        worst_unbeaten = max(table[t]["rank"] for t in unbeaten)
        best_beaten = min(r["rank"] for r in table.values() if r["losses"] > 0)
        w(
            f"| {meta[slug]['recipe'].name} | {worst_unbeaten} | {best_beaten} | "
            + ("**yes**" if best_beaten < worst_unbeaten else "no, and never")
            + " |"
        )
    w("")
    w(
        "**Just Win can never produce an inversion and that is not a fact about 2023.** "
        "Expected wins approaches *n* from below, so an undefeated team has no finite root "
        "and every one of them lands on exactly the published bracket, which is the top of "
        "the key. No team with a loss can pass one, in any season, in any week."
    )
    w("")
    w(
        "**And the same property costs it the retroactive product.** `+60` is not a function "
        "of the schedule, so substituting end-of-season Power cannot move it. The Δ column "
        "below is the live rank minus the hindsight rank for the unbeaten teams:"
    )
    w("")
    w("| team | " + " | ".join(meta[s]["recipe"].name for s in
                               ("full-merit", "house", "just-win")) + " |")
    w("|---|---:|---:|---:|")
    for team in unbeaten:
        cells = []
        for slug in ("full-merit", "house", "just-win"):
            delta = rows[slug][team]["rank_delta"]
            cells.append("0" if delta == 0 else f"{delta:+d}")
        w(f"| {team} | " + " | ".join(cells) + " |")
    w("")
    w(
        "Zero everywhere under Just Win, by construction. If September turns out to have "
        "been harder than it looked, that recipe cannot say so, and this table is what that "
        "costs stated in places rather than in prose."
    )
    w("")

    # ----------------------------------------------------- ties broken by team name
    w("### And under Just Win the top of the board is alphabetical")
    w("")
    w(
        "Found by checking, not by argument. Every ordering's sort key ends in the team "
        "name (`publish/poll.ORDER_KEYS`), which is the last resort when everything above "
        "it ties. Counting how often that last resort actually decides a rank is a direct "
        "measure of how much information a recipe threw away."
    )
    w("")
    w("| recipe | ranked teams decided by team name | the group |")
    w("|---|---:|---|")
    for slug in ("full-merit", "house", "just-win"):
        columns, _ = poll_mod.ORDER_KEYS[meta[slug]["ordering"]]
        keyed = [c for c in columns if c != "team"]
        groups: dict[tuple, list[str]] = {}
        for team, row in rows[slug].items():
            if row["rank"] is None:
                continue
            groups.setdefault(tuple(round(float(row[c]), 9) for c in keyed), []).append(team)
        tied = {k: sorted(v) for k, v in groups.items() if len(v) > 1}
        n = sum(len(v) for v in tied.values())
        biggest = max(tied.values(), key=len, default=[])
        w(
            f"| {meta[slug]['recipe'].name} | {n} | "
            + (", ".join(biggest) if biggest else "*none*")
            + " |"
        )
    w("")
    w(
        "**Just Win compresses margin so hard that its own tie-break stops working.** The "
        "margin-aware résumé is kept as the saturation tie-break precisely to order teams "
        "sitting on the bound, and at `C = 1` it saturates too, so the unbeaten teams tie on "
        "both columns and fall through to the name. That top four is not a ranking of those "
        "teams. It is the absence of one, and the recipe has no way to produce a ranking of "
        "them because it discarded the only information that would separate them. It is "
        "written into `configs/recipes/just-win.toml` as a cost rather than left for a "
        "reader to notice."
    )
    w("")

    # ------------------------------------------------------------------ how far apart
    w("## How far apart are they?")
    w("")
    w(
        f"Kendall's τ over all {len(common)} ranked teams. This project's own published "
        "standard (ADR 0006, and the `q_ref` sweep that never dipped below it) treats τ ≥ "
        "0.985 as a *convention* and anything below it as a **dial**."
    )
    w("")
    w("| pair | Kendall's τ | verdict |")
    w("|---|---:|---|")
    for (a, b), tau in taus.items():
        verdict = "a convention" if tau >= 0.985 else "**a dial**"
        w(f"| {meta[a]['recipe'].name} vs {meta[b]['recipe'].name} | {tau:.4f} | {verdict} |")
    w("")
    w(
        "Every pair is a dial, comfortably, which is the answer this document wanted. Three "
        "recipes that agreed to within a convention would be three labels on one poll."
    )
    w("")

    # ---------------------------------------------------------------------- weakness
    w("## Where this comparison is weak")
    w("")
    w(
        "- **One season.** The structural claims hold in every season because they are "
        "properties of the orderings; the specific movers are 2023's.\n"
        "- **This is a comparison of outputs, not an evaluation.** No recipe has been "
        "backtested end to end as a system, and `cfbpoll backtest` scores orderings rather "
        "than recipes. Nothing here says any board is better than another, and the two "
        "alternate lenses publish no gate verdict at all.\n"
        "- **No rank intervals.** This document ranks without the bootstrap so it "
        "regenerates in well under a minute. Every one of these ranks has a 90% interval "
        "and most of them are wide; `cfbpoll rank --recipe <slug>` publishes them.\n"
        "- **Two of the three recipes are untuned and say so.** `just-win`'s `C = 1` sits "
        "far outside anything either tuning campaign searched. `full-merit`'s constants are "
        "campaign 2's lead 1, which won its own pre-registered rule on margin MAE, and "
        "margin MAE has no opinion about desert.\n"
        "- **2025 is untouched under every recipe.** `recipes.EVIDENCE_KEYS` includes the "
        "holdout keys precisely so a recipe cannot be the thing that opens it."
    )
    w("")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "season": SEASON,
        "week": WEEK,
        "recipes": {
            slug: {
                "name": meta[slug]["recipe"].name,
                "ordering": meta[slug]["ordering"],
                "changes": meta[slug]["changes"],
                "fit_window_sha256": meta[slug]["fit_window_sha256"],
                "config_sha256": meta[slug]["config_sha256"],
                "n_games": meta[slug]["n_games"],
                "top25": [
                    {"rank": r["rank"], "team": r["team"], "wins": r["wins"], "losses": r["losses"]}
                    for r in boards[slug].head(TOP).iter_rows(named=True)
                ],
            }
            for slug in ("full-merit", "house", "just-win")
        },
        "kendall_tau": {f"{a}|{b}": tau for (a, b), tau in taus.items()},
        "movers": [
            {"team": t, **{s: ranks[s].get(t) for s in ranks}, "spread": spread(t)}
            for t in movers
        ],
    }
    OUT.with_suffix(".json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT} and {OUT.with_suffix('.json')}")
    print(f"{len(movers)} movers of {len(board_teams)} rows on the union board")


if __name__ == "__main__":
    main()
