"""The serving contract — the ONE place that turns `out/` into rows a page renders.

Report 03 §6.3 fixes the dependency direction: **the standalone repo never
imports from the sandbox; the sandbox never computes anything.** §7.2 says it
again from the other side — every rendered number is a SELECT. This module is
what makes that enforceable rather than aspirational, because both publication
targets are built from it and cannot drift:

    postgres.py   loads these rows into the cfb_* schema of report 03 §5.6
    fixtures.py   writes the same rows as JSON for the fork and for site dev

If a number is going to appear on the website, it is computed HERE and it lands
in both. Report 05 §7.2 states the rule the two renderers have to obey — "Neither
renderer may compute a derived quantity. Not a gap, not an interval width, not a
percentage" — and the only way to honour it is to compute those quantities
upstream and publish them. That is why the published row carries `one_in`
alongside `tail_p`, `interval_width` alongside its two bounds, and `power_rank`
alongside `power`. Every one of those is a division or a sort that would
otherwise happen in a React component, where it could silently disagree with the
static build and with Postgres.

FOUR TABLES HERE ARE NOT IN REPORT 03 §5.6, and each is a direct consequence of
that same rule:

    cfb_views          the rendered view documents, one JSONB payload per
                       (season, week, kind). See below — this is the one that
                       needs an argument.
    cfb_season_index   the week strip: every week of a season, played or not.
                       An aggregate ACROSS weeks, so no week's row can hold it.
    cfb_divergence     mean |Δrank| per evaluation week — the curve report 05
                       §4.1 wants on the methodology page. Also across weeks.
    cfb_artifacts      filename, size and sha256 per run, for the /data page.
                       A page that prints a checksum it computed itself is not
                       publishing a checksum.

WHY cfb_views EXISTS, stated plainly, because it looks like giving up on the
relational schema and it is not.

Report 03 §5.6 was written before ADR 0005 changed the headline ordering, and
`cfb_poll_published` there carries seven columns. Report 05 §3.1 records what
the published row ACTUALLY contains now — "the published row gains `odds_key`,
`tail_p`, `mid_p`, `expected_wins`, `surprise`, `q_ref` and `q_ref_team`. It
loses nothing" — which is twenty-plus fields, several of them (the interval
rail's domain, the league median width, the `1 in N`) properties of the WEEK
rather than of any team. Reconstructing that in SQL means either widening the
append-only publication record every time the row changes, or a five-way join
whose output the two surfaces would then have to agree about independently.

So: the §5.6 tables are written exactly as specified and stay the analytical
surface — that is what a stranger runs SQL against, and what the team pages and
cross-season comparisons of v2 will read. `cfb_views` is the SERVING surface: the
same documents `publish fixtures` writes to disk, stored so the Postgres backend
returns byte-identical objects. Two backends, one interface, and parity that can
be checked by comparing two JSON documents rather than by trusting two
independent renderers to have agreed.

Postgres is a cache that can be dropped and rebuilt from files at any time
(report 03 §5.4), so storing a derived document in it costs nothing that matters.

TEAM IDENTITY comes from the raw schedule parquet, not from the model. The model
keys on team NAME throughout; the serving schema keys on `team_id` because a
website needs a stable key and a logo. The ids are ESPN's (cfbfastR is built on
ESPN's feed), which is what makes LOGO_TEMPLATE work. `conference` is read from
the same file and is annotated DISPLAY ONLY in §5.6 for a reason: report 02 §3.10
bans it as a feature and `cfbpoll audit-features` enforces that. Reading it here,
in the publication layer, downstream of every fit, is the only place it is safe.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from cfbpoll.config import REPO_ROOT
from cfbpoll.ingest.teams import PALETTE_MARK

__all__ = [
    "Bundle",
    "LOGO_TEMPLATE",
    "PALETTE_MARK",
    "REQUIRED_FILES",
    "REQUIRED_RATING_COLUMNS",
    "StaleRunError",
    "check_run_directory",
    "SERVING_TABLES",
    "VIEW_KINDS",
    "build",
    "headline_start_week",
    "merge_season_index",
    "scheduled_weeks",
    "team_dimension",
]

#: The cfb_* tables this project serves. The first eight are report 03 §5.6
#: verbatim; the last four are the documented extensions above.
SERVING_TABLES: tuple[str, ...] = (
    "cfb_teams",
    "cfb_games",
    "cfb_runs",
    "cfb_model_params",
    "cfb_ratings",
    "cfb_poll_published",
    "cfb_predictions",
    "cfb_backtest_metrics",
    "cfb_views",
    "cfb_season_index",
    "cfb_divergence",
    "cfb_artifacts",
)

#: The four per-week documents. Filename stem in the fixture set, `kind` in
#: `cfb_views`, and the name of the method on the site's PollSource interface —
#: deliberately the same string in all three places.
VIEW_KINDS: tuple[str, ...] = ("week", "connectivity", "methodology", "data")

#: Fallback logo template, used only when `[display].logo_url_template` is absent
#: from a config. The live value is the combiner endpoint in configs/default.toml;
#: see report 06 §8.1 and the `[display]` block for why the combiner and not the
#: raw path.
LOGO_TEMPLATE = (
    "https://a.espncdn.com/combiner/i?img=/i/teamlogos/ncaa/500{variant}/{team_id}.png"
    "&w={size}&h={size}"
)

#: uuid5 namespace for run ids. A run id must be a pure function of what produced
#: the run, or `publish postgres` could not be idempotent: re-running it against
#: the same out/ has to hit the same primary keys rather than accumulate a new
#: run every time. Content-addressed, exactly like the archive.
RUN_NAMESPACE = uuid.UUID("6f1d0b1a-2f2e-5a3c-9d44-cfb0011ca511")

#: `1 in N` is a display transform of `tail_p` (report 05 §3.2). Below this tail
#: the integer stops being meaningful to a reader and starts being an artifact of
#: float underflow, so it is clamped and the clamp is published.
MAX_ONE_IN = 10**15

#: Sections lifted verbatim out of the ADRs for the methodology page's "where
#: this is weak" (report 05 §9.1). Verbatim is the point: a project that
#: paraphrases its own recorded doubts is editing them.
WEAKNESS_SECTIONS: tuple[tuple[str, str], ...] = (
    ("0005-headline-ordering.md", "Where this decision is weak"),
    ("0005-headline-ordering.md", "The price of C, stated plainly"),
    ("0007-tuned-constants.md", "The two uncomfortable results"),
    ("0007-tuned-constants.md", "The calibration diagnosis: diagnosed, and deliberately unfixed"),
    ("0007-tuned-constants.md", "What this does not settle"),
    ("0006-fit-universe.md", "Consequences, including the uncomfortable ones"),
    # ADR 0011's costs go on the methodology page under every recipe, including the
    # published one. "Selectable value systems are a rhetorical risk" is the most
    # important sentence this feature produced and the page it least wants to be on
    # is the one it therefore has to be on.
    ("0011-recipes.md", "The price, stated plainly"),
    ("0011-recipes.md", "Where this decision is weak"),
)

#: The artifact index's human column. Report 03 §5.3 fixes the filenames; this
#: fixes what each one is, so /data is a readable page and not a directory listing.
ARTIFACT_NOTES: dict[str, str] = {
    "ratings_live.parquet": "R(N,N) — every team in the fit, as of this week, every layer.",
    "ratings_live.csv": "The same rows as CSV, for readers with no parquet reader.",
    "ratings_hindsight.parquet": "R(N,final) — the same week re-scored with the season's answers.",
    "ratings_hindsight.csv": "The same rows as CSV.",
    "rank_intervals.parquet": "The bootstrap: 90% rank and rating intervals, 1,000 draws.",
    "rank_intervals.csv": "The same rows as CSV.",
    "poll.json": "The published poll: every column, top 25 and all ranked teams.",
    "poll.csv": "The published poll as CSV.",
    "model_params.json": "Every constant this run used. Every week, without exception.",
    "backtest_metrics.json": "Walk-forward scores against every baseline, and the gate.",
    "_run.json": "git sha, config hash, input manifest hash, timestamps. The receipt.",
}


# --------------------------------------------------------------------------- helpers


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _f(value: Any) -> float | None:
    """A float, or None for null/NaN/inf. JSON cannot carry NaN and neither can a
    reader; a missing number must arrive as missing rather than as `NaN`."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _i(value: Any) -> int | None:
    return None if value is None else int(value)


def _one_in(tail_p: float | None) -> int | None:
    """`1 in N`, the natural-frequency rendering of the tail (report 05 §3.2).

    KenPom's own redesign rationale is the argument: rescale a quantity so the
    number is humanly meaningful. A reader can rank `1 in 192` against `1 in 29`
    instantly and cannot rank `0.0052` against `0.0344`.
    """
    if tail_p is None or tail_p <= 0.0:
        return None
    return min(int(round(1.0 / tail_p)), MAX_ONE_IN)


def _is_house(recipe: dict[str, Any] | None) -> bool:
    return bool((recipe or {}).get("is_house", True))


def _house_recipe_block() -> dict[str, Any]:
    """The house recipe's published block, for a run that predates recipes.

    Read from `configs/recipes/house.toml` rather than hard-coded, so there is
    exactly one place the house poll describes itself. A stripped checkout with no
    recipe directory gets the minimum a renderer needs and no invented prose.
    """
    try:
        from cfbpoll import recipes as recipes_mod

        return recipes_mod.load(recipes_mod.HOUSE).as_dict()
    except Exception:  # pragma: no cover - a checkout without configs/recipes/
        return {"slug": "house", "name": "The House Poll", "is_house": True, "label": None}


def _rank_map(frame: pl.DataFrame, column: str, teams: set[str]) -> dict[str, int]:
    """Dense 1..n rank of `column`, descending, restricted to `teams`.

    This is the parenthetical in KenPom's value-with-rank pair — `28.10 (3)` —
    and report 05 §3.2 says it is what makes the Gap column readable. It is a
    sort, which means it is a computation, which means it happens here.
    """
    narrow = (
        frame.filter(pl.col("team").is_in(sorted(teams)))
        .select(["team", column])
        .drop_nulls(column)
        .sort([column, "team"], descending=[True, False])
    )
    return {team: i + 1 for i, team in enumerate(narrow["team"].to_list())}


def _extract_section(markdown: str, heading: str) -> str | None:
    """The body of one heading, up to the next heading of the SAME OR HIGHER level.

    Same-or-higher rather than "any heading" matters: `## The two uncomfortable
    results` in ADR 0007 is a wrapper whose entire content is two `###`
    subsections, and a naive stop-at-any-heading rule would publish it as empty —
    which is the worst possible failure for a block whose whole job is to carry
    the project's recorded doubts onto the page.
    """
    opener = re.compile(r"^(#{2,4})\s+" + re.escape(heading) + r"\s*$", re.MULTILINE)
    found = opener.search(markdown)
    if not found:
        return None
    level = len(found.group(1))
    rest = markdown[found.end() :]
    closer = re.compile(r"^#{1," + str(level) + r"}\s", re.MULTILINE)
    end = closer.search(rest)
    body = rest[: end.start()] if end else rest
    return body.strip() or None


# -------------------------------------------------------------------- season index


def headline_start_week() -> int:
    """`[publication].headline_start_week`. Published in advance and never moved."""
    from cfbpoll.config import load_config

    cfg = load_config(REPO_ROOT / "configs" / "default.toml")
    return int(cfg["publication"]["headline_start_week"])


def scheduled_weeks(season: int, archive: Path | None) -> list[int]:
    """Every regular-season week the schedule knows about, from either source.

    Empty when neither is there, so a fixture set shipped without an archive
    still indexes rather than failing.

    TWO SOURCES, BECAUSE A SEASON THAT HAS NOT KICKED OFF ONLY HAS THE SECOND.
    The sportsdataverse parquet is the archive of PLAYED football and is the right
    source for any season that has any; it does not exist for a season in the
    future. The 2026 schedule exists only as the archived CFBD `/games` pull, which
    `projection.forward.schedule` already reads offline to build the projection's
    win totals - so the fixture tree held a 2026 projection built from a schedule
    that `index.json` insisted had zero weeks in it, and the site's week strip for
    2026 rendered no cells at all.

    The parquet wins when it has anything, so no season that has been played
    changes its week list because of this fallback, and the CFBD pull is consulted
    only where the parquet is silent.
    """
    weeks: list[int] = []
    try:
        from cfbpoll.ingest.sportsdataverse import canonical_games

        frame = canonical_games([season], archive)
        regular = frame.filter(pl.col("season_type") == "regular")
        weeks = sorted({int(w) for w in regular["week"].to_list()})
    except Exception:  # pragma: no cover - a stripped checkout has no archive
        weeks = []
    if weeks:
        return weeks

    try:
        from cfbpoll.projection import forward

        future = forward.schedule(season)
    except Exception:  # pragma: no cover - no CFBD pull archived either
        return []
    if future.is_empty():
        return []
    return sorted({int(w) for w in future["week"].to_list() if int(w) > 0})


def unplayed_week(season: int, week: int, headline_start: int) -> dict[str, Any]:
    """The week-strip entry for a week that has not been played.

    ONE DEFINITION, TWO CALLERS. `merge_season_index` fills the right-hand side of
    a season in progress with these, and `fixtures.rebuild_index` builds an entire
    season out of them when the season has not started. Two copies of this dict
    would be two chances for the strip to describe an unplayed week differently
    depending on whether any week of that season had been played yet.
    """
    return {
        "season": int(season),
        "week": int(week),
        "season_type": "regular",
        "provisional": week < headline_start,
        "played": False,
        "published_at": None,
        "n_ranked": 0,
    }


def merge_season_index(
    existing: list[dict[str, Any]],
    stub: dict[str, Any],
    scheduled: list[int],
    headline_start: int,
) -> list[dict[str, Any]]:
    """Fold one week's stub into a season's week list. Idempotent, order-free.

    Shared by both publication targets so the week strip is identical whichever
    backend serves it. THE STRIP SHOWS UNPLAYED WEEKS (report 05 §2.2): "Weeks
    not yet played are dimmed and unclickable, not hidden. Seeing the empty
    right-hand side of the strip is part of the season narrative." So every week
    the schedule knows about appears, and `played` is what separates them.
    """
    weeks: dict[int, dict[str, Any]] = {int(w["week"]): dict(w) for w in existing}
    weeks[int(stub["week"])] = dict(stub)
    for week in scheduled:
        weeks.setdefault(week, unplayed_week(int(stub["season"]), week, headline_start))
    return [weeks[w] for w in sorted(weeks)]


# --------------------------------------------------------------------------- teams


def _logo_urls(
    espn_team_id: int | None, display: dict[str, Any] | None
) -> dict[str, str | None]:
    """The four logo URLs for one team, or four nulls.

    NEVER POSSESSES THE BYTES (report 06 §6 rule 1, which does all the legal
    work). This builds strings from an integer we already own, offline: no
    network call, no CFBD quota, works in a fork, and — because the scheme is
    ours rather than passed through from an upstream field that mixes http and
    https — it cannot produce the mixed-content failure that silently breaks
    ~40% of logos on sites that render CFBD's `logos[]` raw.

    All four variants are published rather than derived in the browser, for the
    same reason as every other field on the row: the site never computes.

    Returns nulls when `[display].logos` is false, which is the whole point of
    that flag — the logo-free mode is a config change, not a code change, and
    every slot falls through to the project's own generated mark.
    """
    off = {"logo_url": None, "logo_url_2x": None, "logo_url_dark": None, "logo_url_dark_2x": None}
    if espn_team_id is None or display is None or not bool(display.get("logos", True)):
        return off
    template = str(display.get("logo_url_template") or LOGO_TEMPLATE)
    size = int(display.get("logo_size", 64))
    size_2x = int(display.get("logo_size_2x", 128))
    dark = str(display.get("logo_dark_variant", "-dark"))

    def url(variant: str, px: int) -> str:
        return template.format(variant=variant, team_id=espn_team_id, size=px)

    return {
        "logo_url": url("", size),
        "logo_url_2x": url("", size_2x),
        "logo_url_dark": url(dark, size),
        "logo_url_dark_2x": url(dark, size_2x),
    }


def _mark(
    name: str, colors: dict[str, Any], abbreviation: str | None, mode: str
) -> dict[str, Any]:
    """The generated team mark: three published strings, never a browser computation.

    Report 06 §9.1 asked for the generated mark "on day one... as the fallback for
    every logo slot", and §8.3 makes it the only mark a share card may carry. This
    is where it becomes data. `mark_bg`, `mark_fg` and `mark_label` are published
    on `cfb_teams` and on every poll row, because report 05 §7.2 forbids either
    renderer deriving a quantity - and "is this school's secondary colour legible
    on its primary" is a derivation with a right answer that both surfaces must
    agree on.

    `mode` is `[display].mark_colors`. `"team"` uses the school's own colours with
    a contrast repair; `"palette"` publishes one neutral mark for every team, which
    is the switch to throw if the team-coloured version ever looks like a fan blog.
    It is a config change, not a code change, for the same reason `[display].logos`
    is (report 06 §6 rule 5: build the reversible mode first).
    """
    from cfbpoll.ingest.teams import PALETTE_MARK, mark_for

    entry = colors.get(name)
    label = abbreviation or (entry or {}).get("abbreviation")
    if mode == "palette":
        text = (label or name)[:4].upper()
        return {
            "mark_bg": PALETTE_MARK["bg"],
            "mark_fg": PALETTE_MARK["fg"],
            "mark_label": text,
            "team_color": None,
            "team_alt_color": None,
        }
    mark = mark_for(entry, label or name)
    return {
        "mark_bg": mark["bg"],
        "mark_fg": mark["fg"],
        "mark_label": mark["label"],
        # The raw pair is published beside the repaired one so a reader can see
        # WHICH marks were repaired and why, rather than being handed two hex
        # values that silently are not the school's.
        "team_color": (entry or {}).get("color"),
        "team_alt_color": (entry or {}).get("alt_color"),
    }


def _espn_crosswalk(season: int, archive: Path) -> dict[int, str | None]:
    """ESPN team id -> abbreviation, from the MIT-licensed crosswalk archive.

    Report 06 §8.1 expects a name-matching step here and warns that its own crude
    normalisation missed five teams. It is not needed: the SportsDataverse
    schedule's `home_id`/`away_id` ARE ESPN ids (cfbfastR wraps ESPN's feed), so
    this is an exact integer join and 671 of 2023's 680 scheduled teams resolve
    with no string comparison anywhere. A team that does not resolve gets the
    generated mark, never an error — a name-matching failure must not break a
    Sunday build.

    The abbreviation is what the generated fallback mark carries, so it is worth
    having even for teams whose logo will never load.
    """
    path = archive / "crosswalk" / f"cfb_teams_crosswalk_{season}.parquet"
    if not path.exists():
        return {}
    frame = pl.read_parquet(path, columns=["espn_team_id", "espn_abbreviation"])
    return {
        int(tid): abbr
        for tid, abbr in zip(
            frame["espn_team_id"].to_list(), frame["espn_abbreviation"].to_list(), strict=True
        )
        if tid is not None
    }


def team_dimension(
    season: int, archive: Path, display: dict[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
    """Team name -> the `cfb_teams` row, read from the raw schedule parquet.

    Deliberately NOT read through `ingest.sportsdataverse.canonical_games`: that
    loader's RAW_COLUMNS allow-list exists to keep `home_conference` and friends
    out of every code path that could reach a design matrix (report 01 §5.6). The
    columns are safe HERE and nowhere upstream, so this is the one function that
    opens the file for them, and it is downstream of every fit by construction.

    The same is true of `espn_team_id` and the logo URLs built from it: they are
    publication data, they are audited as banned features upstream, and this is
    the only place they exist.
    """
    from cfbpoll.ingest import teams as team_colors

    crosswalk = _espn_crosswalk(season, archive)
    colors = team_colors.load_colors()
    mark_mode = str((display or {}).get("mark_colors", "team")).lower()
    if mark_mode not in {"team", "palette"}:
        raise ValueError(
            f"[display].mark_colors must be 'team' or 'palette', got {mark_mode!r}"
        )
    path = archive / "schedules" / f"cfb_schedules_{season}.parquet"
    frame = pl.read_parquet(
        path,
        columns=[
            "home_id",
            "home_team",
            "home_conference",
            "home_division",
            "away_id",
            "away_team",
            "away_conference",
            "away_division",
        ],
    )
    out: dict[str, dict[str, Any]] = {}
    order = {"fbs": 0, "fcs": 1, "ii": 2, "iii": 3}
    for side in ("home", "away"):
        for tid, name, conf, div in zip(
            frame[f"{side}_id"].to_list(),
            frame[f"{side}_team"].to_list(),
            frame[f"{side}_conference"].to_list(),
            frame[f"{side}_division"].to_list(),
            strict=True,
        ):
            if name is None or tid is None:
                continue
            klass = div or "unknown"
            prior = out.get(name)
            if prior is not None and order.get(klass, 4) >= order.get(prior["classification"], 4):
                continue
            out[name] = {
                "season": int(season),
                "team_id": int(tid),
                # ESPN's id, stored as the integer rather than only as a URL:
                # it survives ESPN changing its path scheme, and it makes every
                # size and theme variant derivable (report 06 §8.1).
                "espn_team_id": int(tid) if int(tid) in crosswalk else None,
                "school": name,
                "abbreviation": crosswalk.get(int(tid)),
                "classification": klass,
                # DISPLAY ONLY. Never a model feature (report 02 §3.10).
                "conference": conf,
                **_logo_urls(int(tid) if int(tid) in crosswalk else None, display),
                **_mark(name, colors, crosswalk.get(int(tid)), mark_mode),
            }
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------- bundle


@dataclass
class Bundle:
    """One run's serving rows, and the view documents assembled from them.

    `tables` is the relational form that `publish postgres` writes. `views` is the
    document form that `publish fixtures` writes and that the site's typed loader
    returns from EITHER backend — the Postgres backend rebuilds exactly these
    documents with SELECTs. Keeping both in one object is what stops the two
    surfaces from disagreeing about what a week is.
    """

    season: int
    week: int
    season_type: str
    run_id: str
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    views: dict[str, Any] = field(default_factory=dict)
    #: The recipe this run was produced under (ADR 0011). `publish fixtures` reads
    #: it off the bundle rather than off a command-line flag, so the tree a run
    #: lands in is decided by what the run actually IS and an operator cannot file
    #: an alternate lens as the published poll by mistyping an option.
    recipe: dict[str, Any] = field(default_factory=dict)

    @property
    def recipe_slug(self) -> str:
        return str(self.recipe.get("slug") or "house")

    @property
    def is_house(self) -> bool:
        return bool(self.recipe.get("is_house", True))

    def week_stub(self) -> dict[str, Any]:
        """This week's entry in the season index (report 05 §2.2's week strip)."""
        view = self.views["week"]
        return {
            "season": self.season,
            "week": self.week,
            "season_type": self.season_type,
            "provisional": bool(view["provisional"]),
            "played": True,
            "published_at": view["run"]["published_at"],
            "n_ranked": len(view["poll"]),
        }


class StaleRunError(RuntimeError):
    """`out/` was written by a version of this code that predates the contract.

    Its own type because it is not a bug report, it is an instruction: re-run
    `cfbpoll rank`. `out/` is gitignored regenerable scratch, so a directory left
    over from an older checkout is an ordinary thing to find on a working copy
    and a confusing thing to hit six frames deep inside polars.
    """


#: What `serving.build` needs out of a run directory, and which command writes it.
#: Checked BEFORE anything is read, so a stale directory produces one sentence
#: naming what is missing rather than a ColumnNotFoundError from a lazy scan.
REQUIRED_FILES: tuple[str, ...] = (
    "poll.json",
    "model_params.json",
    "_run.json",
    "ratings_live.parquet",
)

#: Columns `build` reads off `ratings_live.parquet`. `power` and `resume` arrived
#: with L3 and L4; a pre-L3 run carries `rating` and nothing else, which is
#: exactly the shape that used to fail unreadably.
REQUIRED_RATING_COLUMNS: tuple[str, ...] = ("team", "power", "resume")


def check_run_directory(out: Path) -> None:
    """Raise `StaleRunError` unless `out` satisfies the current serving contract.

    Called first thing in `build`. The check is cheap - a directory listing and a
    parquet schema read, no data - and it converts the single most likely
    operational failure on a working copy into an actionable message.
    """
    out = Path(out)
    if not out.is_dir():
        raise StaleRunError(
            f"{out} is not a directory. `publish fixtures` reads what `cfbpoll rank` "
            f"wrote; run `cfbpoll rank --season <season> --through-week <week> "
            f"--out {out}` first."
        )
    missing = [name for name in REQUIRED_FILES if not (out / name).exists()]
    if missing:
        raise StaleRunError(
            f"{out} is missing {', '.join(missing)}. It is not a run directory, or it "
            f"is a partial one. Re-run `cfbpoll rank --out {out}`."
        )

    columns = set(pl.read_parquet_schema(out / "ratings_live.parquet"))
    absent = [c for c in REQUIRED_RATING_COLUMNS if c not in columns]
    if absent:
        run_meta = _read_json(out / "_run.json")
        raise StaleRunError(
            f"{out}/ratings_live.parquet is missing {', '.join(absent)} "
            f"(it carries {sorted(columns)}). That directory was written by an older "
            f"version of this code"
            + (f" at git {run_meta.get('git_sha', '?')[:7]}" if run_meta.get("git_sha") else "")
            + f", before the columns the published poll row now needs existed. `out/` is "
            f"regenerable scratch: re-run `cfbpoll rank --season "
            f"{run_meta.get('season', '<season>')} --through-week "
            f"{run_meta.get('through_week', '<week>')} --out {out}`."
        )


def build(
    out: Path,
    archive: Path | None = None,
    backtest: Path | None = None,
    upcoming_weeks: int = 1,
) -> Bundle:
    """Turn one `out/` directory into its serving rows and view documents.

    `out` is what `cfbpoll rank` wrote: poll.json, model_params.json, _run.json,
    ratings_live.parquet, rank_intervals.parquet. `backtest` is an optional
    backtest_metrics.json — the methodology page's gate and baseline table come
    from it, and a run without one publishes a methodology page that says so
    rather than one that invents numbers.
    """
    from cfbpoll.config import load_config
    from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE

    check_run_directory(out)

    archive = archive or DEFAULT_ARCHIVE
    config = load_config(REPO_ROOT / "configs" / "default.toml")
    display = dict(config.get("display") or {})
    poll = _read_json(out / "poll.json")
    params = _read_json(out / "model_params.json")
    run_meta = _read_json(out / "_run.json")

    season = int(poll["season"])
    week = int(poll["through"]["week"])
    season_type = str(poll["through"]["season_type"])

    # WHICH VALUE SYSTEM PRODUCED THESE ROWS (ADR 0011). A run without a recipe
    # block predates `configs/recipes/` and is the house poll by definition, which
    # is what the fallback says rather than leaving the field null.
    recipe = params.get("recipe") or _house_recipe_block()

    run_id = str(
        uuid.uuid5(
            RUN_NAMESPACE,
            "|".join(
                [
                    str(season),
                    str(week),
                    season_type,
                    str(run_meta.get("git_sha", "unknown")),
                    str(run_meta.get("config_hash", "")),
                    str(run_meta.get("archive_manifest_sha256", "")),
                    str(params.get("headline_ordering", "")),
                    # THE HOUSE RECIPE CONTRIBUTES NOTHING TO THE RUN ID, on
                    # purpose. It IS `configs/default.toml`, so `config_hash`
                    # above already determines it completely and appending a
                    # constant string would change every published run id for a
                    # fact that was already there. An alternate lens is a genuine
                    # additional input and gets its own id, which is what stops
                    # two lenses of one week colliding on a primary key.
                    *([] if _is_house(recipe) else [str(recipe.get("slug"))]),
                ]
            ),
        )
    )
    published_at = str(run_meta.get("generated_at") or datetime.now(UTC).isoformat())

    teams = team_dimension(season, archive, display)
    live = pl.read_parquet(out / "ratings_live.parquet")
    ranked = {row["team"] for row in poll["ranking"]}
    power_rank = _rank_map(live, "power", ranked)
    resume_rank = _rank_map(live, "resume", ranked)

    bundle = Bundle(
        season=season,
        week=week,
        season_type=season_type,
        run_id=run_id,
        tables={},
        views={},
        recipe=dict(recipe),
    )

    # ---------------------------------------------------------------- dimensions
    bundle.tables["cfb_teams"] = list(teams.values())
    bundle.tables["cfb_games"] = _games_rows(season, archive)

    # ---------------------------------------------------------------- provenance
    run_row = {
        "run_id": run_id,
        "ran_at": published_at,
        "season": season,
        "through_week": week,
        "git_sha": str(run_meta.get("git_sha", "unknown")),
        "config_hash": str(run_meta.get("config_hash", "")),
        "archive_hash": run_meta.get("archive_manifest_sha256"),
        "trigger": "manual",
        # Report 03 §7.2: the site must NEVER render a poll whose run is not
        # published. Every run this command writes is published by definition —
        # `rank` refuses to write one that failed the feature audit — so the
        # status is stated rather than guessed.
        "status": "published",
        "notes": None,
        "published_at": published_at,
    }
    bundle.tables["cfb_runs"] = [run_row]
    numeric, labels = _split_params(params)
    bundle.tables["cfb_model_params"] = [
        {"run_id": run_id, "name": name, "value": value} for name, value in sorted(numeric.items())
    ]

    # ---------------------------------------------------------------- the poll
    poll_rows, published_rows, rating_rows = _poll_rows(
        poll, teams, power_rank, resume_rank, run_id, season, week, published_at
    )
    bundle.tables["cfb_poll_published"] = published_rows
    bundle.tables["cfb_ratings"] = rating_rows
    bundle.tables["cfb_predictions"] = []

    widths = sorted(r["interval_width"] for r in poll_rows if r["interval_width"] is not None)
    median_width = float(_median(widths)) if widths else None
    deltas = [abs(r["rank_delta"]) for r in poll_rows if r["rank_delta"] is not None]
    # The Gap column's diverging bars are scaled against the week's own largest
    # |gap| (report 05 §3.2). That maximum is a reduction over the table, so it
    # is published rather than worked out in a React component.
    gaps = [abs(r["gap"]) for r in poll_rows if r["gap"] is not None]
    max_abs_gap = max(gaps) if gaps else 0.0

    model_params_doc = _params_doc(
        numeric, labels, run_row, season, week, params, poll.get("provisional", False)
    )

    bundle.views["week"] = {
        "season": season,
        "week": week,
        "season_type": season_type,
        "run": run_row,
        "params": model_params_doc,
        # THE RECIPE BLOCK. Name, manifesto, honest costs, the constants it
        # changed, and the label an alternate lens carries. Published on the week
        # document because the page that renders a ranking has to be able to say
        # which value system it is rendering, in that value system's own words,
        # without computing anything (report 05 §7.2). See
        # docs/fixture-contract-recipes.md.
        "recipe": {
            **recipe,
            "config_sha256": params.get("recipe_config_sha256"),
            # THE INTEGRITY BLOCK, and the reason it is on the row rather than in
            # a footnote: "recipes change values, never evidence" is a claim, and a
            # claim a reader cannot check is a slogan. These three fields are
            # identical across every recipe of a given week, by construction, so
            # two lenses can be compared field by field on the page itself.
            "evidence": {
                "archive_manifest_sha256": run_meta.get("archive_manifest_sha256"),
                "fit_window_sha256": run_meta.get("fit_window_sha256"),
                "n_games_in_fit": _i(run_meta.get("n_games_in_fit")),
            },
        },
        "provisional": bool(poll.get("provisional", False)),
        "provisional_label": poll.get("provisional_label"),
        "league_size": len(poll_rows),
        "median_interval_width": median_width,
        "max_abs_gap": max_abs_gap,
        "hindsight_is_live": bool(params.get("hindsight_is_live", False)),
        # THE SAME-RECORD COMPARISON, decided here and never on the page. Two
        # teams with identical records and different numbers beside them is the
        # single clearest demonstration this poll can make, and which two it
        # makes it with is an editorial decision that has to be reviewable. Both
        # fields may be null, which is a legitimate week rather than a fault.
        "same_record_pair": _pinned_same_record_pair(poll_rows, season, week, config),
        "same_record_candidates": _same_record_candidates(poll_rows, config),
        "poll": poll_rows,
    }

    # ---------------------------------------------------------------- divergence
    bundle.tables["cfb_divergence"] = [
        {
            "run_id": run_id,
            "season": season,
            "eval_week": week,
            "mean_abs_delta": (sum(deltas) / len(deltas)) if deltas else None,
            "max_abs_delta": max(deltas) if deltas else None,
            "n_teams": len(poll_rows),
        }
    ]

    # ---------------------------------------------------------------- connectivity
    connectivity = _connectivity_view(
        season, week, season_type, archive, params, poll, poll_rows, median_width, upcoming_weeks
    )
    bundle.views["connectivity"] = connectivity

    # ---------------------------------------------------------------- methodology
    metrics, gate = _backtest_rows(backtest, run_id)
    bundle.tables["cfb_backtest_metrics"] = metrics
    bundle.views["methodology"] = {
        "season": season,
        "week": week,
        "params": model_params_doc,
        "run": run_row,
        "recipe": bundle.views["week"]["recipe"],
        "metrics": [
            {k: v for k, v in row.items() if k != "run_id"} for row in metrics
        ],
        "gate": gate,
        # WHY THERE IS NO GATE VERDICT, when there is none. An empty list renders
        # as an empty table and an empty table reads as an oversight, so the
        # absence carries its own reason. The two reasons are genuinely different:
        # a house run with no metrics file is an operational gap somebody can
        # close by running `cfbpoll backtest`, and an alternate lens has no gate
        # verdict because `[gate]` is written against the PUBLISHED poll and has
        # never been applied per recipe. Inventing one for a lens would be worse
        # than saying so (ADR 0011, "where this is weak").
        "gate_note": (
            None
            if gate
            else (
                "The publication gate is written against the published poll and is not "
                "applied per recipe. This is an alternate lens: its constants are below, "
                "and it has no gate verdict of its own."
                if not _is_house(recipe)
                else "No backtest accompanied this run, so the gate has not been evaluated."
            )
        ),
        "weaknesses": _weaknesses(),
        "divergence": [],  # filled by the fixture writer across weeks; see fixtures.py
    }

    # ---------------------------------------------------------------- artifacts
    artifacts = _artifact_rows(out, run_id)
    bundle.tables["cfb_artifacts"] = artifacts
    bundle.views["data"] = {
        "season": season,
        "week": week,
        "run": run_row,
        "artifacts": [{k: v for k, v in row.items() if k != "run_id"} for row in artifacts],
        "duckdb": _duckdb_one_liner(season, week),
        "licenses": _licenses(),
    }

    # ---------------------------------------------------------------- the views
    # The serving surface. Same documents `publish fixtures` writes to disk, so
    # the two backends return byte-identical objects and parity is a diff rather
    # than a hope.
    bundle.tables["cfb_views"] = [
        {
            "season": season,
            "week": week,
            "kind": kind,
            "run_id": run_id,
            "payload": bundle.views[kind],
        }
        for kind in VIEW_KINDS
    ]
    bundle.tables["cfb_season_index"] = []  # merged across weeks by each target
    return bundle


def _same_record_slot(row: dict[str, Any]) -> dict[str, Any]:
    """One side of the comparison, carrying only what the module prints."""
    return {
        "team": row.get("team"),
        "team_id": row.get("team_id"),
        "rank": row.get("rank"),
        "record": row.get("record"),
        "one_in": row.get("one_in"),
        "tail_p": row.get("tail_p"),
        "power": row.get("power"),
        "q_ref_team": row.get("q_ref_team"),
        "mark_bg": row.get("mark_bg"),
        "mark_fg": row.get("mark_fg"),
        "mark_label": row.get("mark_label"),
        "logo_url": row.get("logo_url"),
        "logo_url_2x": row.get("logo_url_2x"),
        "logo_url_dark": row.get("logo_url_dark"),
        "logo_url_dark_2x": row.get("logo_url_dark_2x"),
    }


def _same_record_candidates(
    poll_rows: list[dict[str, Any]], config: dict[str, Any], limit: int = 25
) -> list[dict[str, Any]]:
    """Every pair inside the published top N that shares a record, with its gap.

    Published so the PIN is reviewable. An editorial choice a reader cannot see
    the alternatives to is indistinguishable from a cherry-pick, and this module
    exists to make the opposite point.
    """
    exclude = {
        str(t) for t in ((config.get("publication") or {}).get("same_record_pair_exclude") or [])
    }
    rows = [r for r in poll_rows[:limit] if r.get("record") and r.get("rank") is not None]
    out: list[dict[str, Any]] = []
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            if a["record"] != b["record"] or a.get("one_in") == b.get("one_in"):
                continue
            out.append(
                {
                    "record": a["record"],
                    "leader": a.get("team"),
                    "leader_rank": a.get("rank"),
                    "leader_one_in": a.get("one_in"),
                    "foil": b.get("team"),
                    "foil_rank": b.get("rank"),
                    "foil_one_in": b.get("one_in"),
                    "rank_gap": int(b["rank"]) - int(a["rank"]),
                    "excluded": bool({str(a.get("team")), str(b.get("team"))} & exclude),
                }
            )
    out.sort(key=lambda p: (-p["rank_gap"], str(p["leader"]), str(p["foil"])))
    return out


def _pinned_same_record_pair(
    poll_rows: list[dict[str, Any]], season: int, week: int, config: dict[str, Any]
) -> dict[str, Any] | None:
    """The pair the front door's same-record module renders, PINNED, never derived.

    WHY A PIN AND NOT A RULE. The site's first version took the #1 team and the
    lowest-ranked team sharing its record. That is a rule, it is reproducible, and
    it returns NOTHING in most weeks that matter: 2025 finishes with a 13-0
    Indiana at the top, whose record nobody else in the country shares, so the
    single clearest demonstration this poll can make would simply not render on
    the final board. A rule that goes silent exactly when the season is most
    interesting is not a good rule.

    So the pair is an editorial decision, written down in
    `[[publication.pinned_same_record_pairs]]` with the reason attached, and
    VALIDATED here against the published rows: both teams must be in the top 25,
    they must genuinely share a record, and neither may be on the exclusion list.
    A pin that fails any of those raises rather than silently disappearing,
    because a comparison module that quietly renders nothing is how a claim gets
    dropped without anybody deciding to drop it.

    `same_record_candidates` beside this field lists every pair the pin was chosen
    from, so the choice can be second-guessed from the document itself.
    """
    publication = config.get("publication") or {}
    pins = publication.get("pinned_same_record_pairs") or []
    exclude = {str(t) for t in (publication.get("same_record_pair_exclude") or [])}
    pin = next(
        (
            p
            for p in pins
            if int(p.get("season", -1)) == int(season) and int(p.get("week", -1)) == int(week)
        ),
        None,
    )
    if pin is None:
        return None

    by_team = {str(r.get("team")): r for r in poll_rows[:25]}
    leader, foil = str(pin["leader"]), str(pin["foil"])
    missing = [t for t in (leader, foil) if t not in by_team]
    if missing:
        raise ValueError(
            f"pinned same-record pair for {season} week {week} names {missing}, which "
            "is not in the published top 25. A pin that cannot be rendered must be "
            "corrected in configs/default.toml rather than silently dropped."
        )
    if by_team[leader]["record"] != by_team[foil]["record"]:
        raise ValueError(
            f"pinned same-record pair for {season} week {week} is "
            f"{leader} ({by_team[leader]['record']}) and {foil} "
            f"({by_team[foil]['record']}), which are not the same record."
        )
    if {leader, foil} & exclude:
        raise ValueError(
            f"pinned same-record pair for {season} week {week} names an excluded "
            f"team: {sorted({leader, foil} & exclude)}."
        )

    return {
        "pinned": True,
        "why": str(pin.get("why", "")),
        "excluded_teams": sorted(exclude),
        "leader": _same_record_slot(by_team[leader]),
        "foil": _same_record_slot(by_team[foil]),
    }


def _median(values: list[float]) -> float:
    n = len(values)
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2.0


def _split_params(params: dict[str, Any]) -> tuple[dict[str, float], dict[str, str]]:
    """`cfb_model_params` takes doubles; the layer names and the ordering are
    strings and cannot live in that table. Both halves are published."""
    numeric: dict[str, float] = {}
    labels: dict[str, str] = {}
    for name, value in params.items():
        if isinstance(value, bool):
            labels[name] = "true" if value else "false"
        elif isinstance(value, (int, float)):
            got = _f(value)
            if got is not None:
                numeric[name] = got
        elif isinstance(value, str):
            labels[name] = value
    return numeric, labels


def _fmt(value: float | None, places: int = 3) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def _params_doc(
    numeric: dict[str, float],
    labels: dict[str, str],
    run: dict[str, Any],
    season: int,
    week: int,
    params: dict[str, Any],
    provisional: bool,
) -> dict[str, Any]:
    """The permanent constants footer of report 05 §2.3, PRE-RENDERED.

    Two lines, and the report is explicit that this block is a brand asset: no
    other rankings site in the sport carries one, and its presence on every page
    is the fastest way to communicate what kind of instrument this is. It is
    rendered here rather than in the browser for the same reason as everything
    else — the static build, the share card and the Next.js app must print the
    same characters.
    """
    q_ref = _f(params.get("q_ref"))
    q_team = params.get("q_ref_team")
    published = str(run["published_at"])[:19].replace("T", " ")
    line1 = (
        f"run {run['run_id'][:8]} · published {published} UTC · "
        f"code {str(run['git_sha'])[:7]} · config {str(run['config_hash'])[:8]}…"
    )
    line2 = " · ".join(
        [
            f"q_ref {_fmt(q_ref, 2)}" + (f" ({q_team})" if q_team else ""),
            f"β_w {_fmt(_f(numeric.get('beta_w')), 0)}",
            # C is a LABEL rather than a number under `full-merit`, where it is the
            # limit of the tanh family and JSON cannot carry infinity
            # (model/l2_results._publishable). The constants footer prints every
            # constant every week; the one week C is the entire argument is not the
            # week it may render as an em dash.
            f"C {labels.get('C') or _fmt(_f(numeric.get('C')), 0)}",
            f"h {_fmt(_f(numeric.get('h_points')), 3)}",
            f"σ {_fmt(_f(numeric.get('sigma')), 3)}",
            f"λ₁ {_fmt(_f(numeric.get('lambda_l1')), 0)}",
            f"λ₂ {_fmt(_f(numeric.get('lambda_l2')), 1)}",
            f"k {_fmt(_f(numeric.get('k_points_per_unit')), 2)}",
            f"w₁ {_fmt(_f(numeric.get('w1_efficiency')), 4)}",
            f"w₂ {_fmt(_f(numeric.get('w2_results')), 4)}",
        ]
    )
    reproduce = f"uv run cfbpoll rank --season {season} --through-week {week} --out out/"
    del provisional
    return {
        "numeric": numeric,
        "labels": labels,
        "footer_lines": [line1, line2],
        "reproduce": reproduce,
    }


def _poll_rows(
    poll: dict[str, Any],
    teams: dict[str, dict[str, Any]],
    power_rank: dict[str, int],
    resume_rank: dict[str, int],
    run_id: str,
    season: int,
    week: int,
    published_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The published row, three ways: the view, `cfb_poll_published`, `cfb_ratings`."""
    view: list[dict[str, Any]] = []
    published: list[dict[str, Any]] = []
    ratings: list[dict[str, Any]] = []

    for row in poll["ranking"]:
        team = row["team"]
        dim = teams.get(team)
        team_id = int(dim["team_id"]) if dim else -abs(hash(team)) % 10**8
        lo, hi = _i(row.get("rank_lo")), _i(row.get("rank_hi"))
        wins, losses = int(row["wins"]), int(row["losses"])
        tail = _f(row.get("tail_p"))

        view.append(
            {
                "rank": int(row["rank"]),
                "team_id": team_id,
                "espn_team_id": dim["espn_team_id"] if dim else None,
                "team": team,
                # The generated fallback mark carries this when a logo does not
                # load, and when [display].logos is off it is the only mark there
                # is — so it is published whether or not logos are.
                "abbreviation": dim["abbreviation"] if dim else None,
                "conference": dim["conference"] if dim else None,
                # The generated mark, published on the row so the poll table can
                # render a team without a second lookup and without computing.
                "mark_bg": dim["mark_bg"] if dim else PALETTE_MARK["bg"],
                "mark_fg": dim["mark_fg"] if dim else PALETTE_MARK["fg"],
                "mark_label": dim["mark_label"] if dim else team[:4].upper(),
                "logo_url": dim["logo_url"] if dim else None,
                "logo_url_2x": dim["logo_url_2x"] if dim else None,
                "logo_url_dark": dim["logo_url_dark"] if dim else None,
                "logo_url_dark_2x": dim["logo_url_dark_2x"] if dim else None,
                "wins": wins,
                "losses": losses,
                "record": f"{wins}-{losses}",
                "odds_key": _f(row.get("odds_key")),
                "tail_p": tail,
                "one_in": _one_in(tail),
                "mid_p": _f(row.get("mid_p")),
                "expected_wins": _f(row.get("expected_wins")),
                "surprise": _f(row.get("surprise")),
                "resume": _f(row.get("resume")),
                "resume_margin": _f(row.get("resume_margin")),
                "resume_rank": resume_rank.get(team),
                "saturated": int(row.get("saturated") or 0),
                "power": _f(row.get("power")),
                "power_se": _f(row.get("power_se")),
                "power_rank": power_rank.get(team),
                "gap": _f(row.get("gap")),
                "rank_lo90": lo,
                "rank_hi90": hi,
                "rank_median": _i(row.get("rank_median")),
                "interval_width": (hi - lo) if (lo is not None and hi is not None) else None,
                "hindsight_rank": _i(row.get("rank_hindsight")),
                "rank_delta": _i(row.get("rank_delta")),
                "q_ref": _f(row.get("q_ref")),
                "q_ref_team": row.get("q_ref_team"),
            }
        )
        published.append(
            {
                "season": season,
                "week": week,
                "rank": int(row["rank"]),
                "team_id": team_id,
                "resume_rating": _f(row.get("resume")),
                "power_rating": _f(row.get("power")),
                "rank_lo90": lo,
                "rank_hi90": hi,
                "prev_rank": None,
                "wins": wins,
                "losses": losses,
                "run_id": run_id,
                "published_at": published_at,
            }
        )
        for layer, rating, rank, rlo, rhi in (
            ("C_schedule_odds", _f(row.get("odds_key")), int(row["rank"]), lo, hi),
            ("L3_power", _f(row.get("power")), power_rank.get(team), None, None),
            ("L4_resume", _f(row.get("resume")), resume_rank.get(team), None, None),
        ):
            if rating is None:
                continue
            ratings.append(
                {
                    "run_id": run_id,
                    "season": season,
                    "eval_week": week,
                    "data_window": week,  # K = N: the live surface
                    "team_id": team_id,
                    "layer": layer,
                    "rating": rating,
                    "rank": rank,
                    "rating_lo90": None,
                    "rating_hi90": None,
                    "rank_lo90": rlo,
                    "rank_hi90": rhi,
                }
            )
        # The hindsight surface, K = 99, is the other half of the retro product
        # (report 02 §3.6) and is what the Δ column reads.
        hind = _f(row.get("odds_key_hindsight"))
        if hind is not None:
            ratings.append(
                {
                    "run_id": run_id,
                    "season": season,
                    "eval_week": week,
                    "data_window": 99,
                    "team_id": team_id,
                    "layer": "C_schedule_odds",
                    "rating": hind,
                    "rank": _i(row.get("rank_hindsight")),
                    "rating_lo90": None,
                    "rating_hi90": None,
                    "rank_lo90": None,
                    "rank_hi90": None,
                }
            )
    return view, published, ratings


def _games_rows(season: int, archive: Path) -> list[dict[str, Any]]:
    from cfbpoll.ingest.sportsdataverse import canonical_games

    teams = team_dimension(season, archive)
    frame = canonical_games([season], archive)
    ingested = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    for row in frame.iter_rows(named=True):
        home = teams.get(row["home_team"])
        away = teams.get(row["away_team"])
        if home is None or away is None:
            continue
        start = row["start_date"]
        rows.append(
            {
                "game_id": int(row["game_id"]),
                "season": int(row["season"]),
                "week": int(row["week"]),
                "season_type": row["season_type"],
                "game_type": row["game_type"],
                "start_date": start.isoformat() if start is not None else None,
                "completed": bool(row["completed"]),
                "neutral_site": bool(row["neutral_site"]),
                "conference_game": row["conference_game"],
                "home_team_id": int(home["team_id"]),
                "away_team_id": int(away["team_id"]),
                "home_points": _i(row["home_points"]),
                "away_points": _i(row["away_points"]),
                "home_class": row["home_class"],
                "away_class": row["away_class"],
                "source": "sportsdataverse",
                "ingested_at": ingested,
            }
        )
    return rows


# --------------------------------------------------------------------- connectivity


def _connectivity_view(
    season: int,
    week: int,
    season_type: str,
    archive: Path,
    params: dict[str, Any],
    poll: dict[str, Any],
    poll_rows: list[dict[str, Any]],
    median_width: float | None,
    upcoming_weeks: int,
) -> dict[str, Any]:
    """The weeks 1-4 launch product, computed in full so the site draws it blind."""
    from cfbpoll.config import load_config
    from cfbpoll.ingest import windows
    from cfbpoll.ingest.sportsdataverse import canonical_games, load_games
    from cfbpoll.model import connectivity as conn

    cfg = load_config(REPO_ROOT / "configs" / "default.toml")
    headline_start = int(cfg["publication"]["headline_start_week"])

    games = load_games([season], archive, universe="model")
    window = windows.games_through(games, season=season, week=week, season_type=season_type)
    graph = conn.build_graph(window)
    comp = conn.components(graph)
    cut = conn.bridges(graph)
    positions = conn.layout(graph, comp)

    sizes: dict[int, int] = {}
    for cid in comp:
        sizes[cid] = sizes.get(cid, 0) + 1
    component_sizes = [sizes[c] for c in sorted(sizes)]
    # Week 1 has 125 components and a caption that prints all of them is twelve
    # lines of "2 · 2 · 2". Pre-format it here, like every other string the page
    # prints, so the two renderers cannot summarise it differently.
    if len(component_sizes) <= 10:
        sizes_display = " · ".join(str(n) for n in component_sizes)
    else:
        head = " · ".join(str(n) for n in component_sizes[:8])
        rest = component_sizes[8:]
        sizes_display = (
            f"{head} · and {len(rest)} more, none larger than {max(rest)}"
        )
    largest_share = (component_sizes[0] / graph.n) if graph.n else 0.0

    degrees = graph.degrees()
    teams_dim = team_dimension(season, archive)
    nodes = [
        {
            "team_id": int(teams_dim[t]["team_id"]) if t in teams_dim else -i - 1,
            "team": t,
            "classification": graph.classification.get(t, "unknown"),
            "component": comp[i],
            "x": positions.x[i],
            "y": positions.y[i],
            "degree": degrees[i],
        }
        for i, t in enumerate(graph.teams)
    ]
    edges = [
        {"source": a, "target": b, "component": comp[a], "bridge": ei in cut}
        for ei, (a, b) in enumerate(graph.edges)
    ]

    # The bridges worth naming: the ones holding a non-trivial cluster on. A cut
    # edge that strands one team is arithmetic; a cut edge that strands forty is
    # a headline.
    bridge_games: list[dict[str, Any]] = []
    for ei in sorted(cut):
        near, far = conn.component_split(graph, ei)
        smaller = min(near, far)
        if smaller < 2:
            continue
        a, b = graph.edges[ei]
        bridge_games.append(
            {
                "game_id": graph.game_ids[ei],
                "week": graph.weeks[ei],
                "home": graph.teams[a],
                "away": graph.teams[b],
                "splits": [near, far],
                "note": (
                    f"{graph.teams[a]}–{graph.teams[b]} is the only game linking "
                    f"{smaller} teams to the other {max(near, far)}. Undo that one result "
                    "and the graph splits in two."
                ),
            }
        )
    bridge_games.sort(key=lambda g: (-min(g["splits"]), g["game_id"]))
    # In week 2 there are 230 of these. The page names the dozen holding the most
    # teams on, so the total has to travel with them or the prose ("there are N")
    # and the list under it disagree — which is exactly the kind of small
    # inconsistency that makes a reader stop trusting the big numbers.
    bridge_games_total = len(bridge_games)
    bridge_games_shown = min(12, bridge_games_total)

    # What would have to be true: next week's slate, restricted to games that
    # would weld two currently-separate components.
    played_ids = set(window["game_id"].to_list())
    everything = canonical_games([season], archive)
    horizon = week + max(1, upcoming_weeks)
    upcoming = everything.filter(
        (pl.col("season_type") == "regular")
        & (pl.col("week") > week)
        & (pl.col("week") <= horizon)
        & ~pl.col("game_id").is_in(sorted(played_ids))
    )
    connectors = conn.would_connect(graph, upcoming, comp)[:12]
    for game in connectors:
        smaller = min(game["home_component_size"], game["away_component_size"])
        bigger = max(game["home_component_size"], game["away_component_size"])
        game["note"] = (
            f"{game['away']} at {game['home']}, week {game['week']}: the first game on the "
            f"schedule that would connect a group of {smaller} to the group of {bigger}. "
            "It is worth more to this poll than its TV slot suggests."
        )

    top_group = [r["team"] for r in poll_rows[:10]]
    distance = conn.distance_from(graph, top_group)
    far_from_top = sum(1 for d in distance.values() if d < 0 or d > 2)

    league = len(poll_rows)
    spanning = sum(
        1
        for r in poll_rows
        if r["interval_width"] is not None and league and r["interval_width"] >= 0.9 * (league - 1)
    )

    diagnostics = [
        {
            "label": "teams in the fit",
            "display": f"{graph.n}",
            "value": float(graph.n),
            "note": "Every team with at least one game against an FBS or FCS opponent.",
        },
        {
            "label": "games played",
            "display": f"{len(graph.edges)}",
            "value": float(len(graph.edges)),
            "note": None,
        },
        {
            "label": "connected components",
            "display": f"{len(component_sizes)}",
            "value": float(len(component_sizes)),
            "note": (
                "Separate islands of the schedule graph. Two teams in different components "
                "have no chain of results connecting them at all, at any length."
            ),
        },
        {
            "label": "largest component",
            "display": f"{component_sizes[0] if component_sizes else 0} teams "
            f"({largest_share * 100:.1f}%)",
            "value": largest_share,
            "note": "Share of the field that is mutually comparable through played games.",
        },
        {
            "label": "bridge games",
            "display": f"{len(bridge_games)}",
            "value": float(len(bridge_games)),
            "note": (
                "Single games whose removal would split the graph in two, each holding at "
                "least two teams on. Every rating on the far side rests on that one result."
            ),
        },
        {
            "label": "fitted λ₂ (results core)",
            "display": _fmt(_f(params.get("lambda_l2")), 3),
            "value": _f(params.get("lambda_l2")) or 0.0,
            "note": (
                "Chosen by cross-validation every week. λ is a ratio of variances — a "
                "statement about how much we do not know, containing no team-specific "
                "information whatsoever. It is large when the data is thin and falls as "
                "the season accumulates. Regularization is not a reputation prior."
            ),
        },
        {
            "label": "median 90% rank-interval width",
            "display": "—" if median_width is None else f"{median_width:.0f} places",
            "value": median_width or 0.0,
            "note": (
                f"Out of {league} ranked teams, from 1,000 replays of this exact schedule. "
                "This is the number that says whether the season has settled."
            ),
        },
        {
            "label": "teams whose interval spans the league",
            "display": f"{spanning}",
            "value": float(spanning),
            "note": "90% interval at least 90% as wide as the whole field.",
        },
        {
            "label": "teams no closer than three hops to the top ten",
            "display": f"{far_from_top}",
            "value": float(far_from_top),
            "note": (
                "They have not played a top-ten team and share no opponent with one. "
                "Their position relative to the top of the poll is an extrapolation."
            ),
        },
    ]

    provisional = bool(poll.get("provisional", False))
    counter = (
        f"The poll opens in Week {headline_start}. That date was published before the "
        "season and does not move. This is week "
        f"{week}, and what follows is a description of what is not yet knowable."
        if provisional
        else f"The poll opened in Week {headline_start}. This is week {week}; the schedule "
        "graph below is what the ranking is standing on."
    )

    sentences: list[str] = []
    if len(component_sizes) > 1:
        sentences.append(
            f"The field is in {len(component_sizes)} separate pieces. "
            f"{component_sizes[0]} teams are mutually comparable through played games; "
            f"the other {graph.n - component_sizes[0]} are not comparable to them at all yet, "
            "and no amount of arithmetic changes that."
        )
    else:
        sentences.append(
            "The graph is welded: every team is connected to every other through some chain "
            "of results. That is the condition under which a ranking is a measurement rather "
            "than an extrapolation, and it is why the opening week is week "
            f"{headline_start} and not week 1."
        )
    for game in connectors[:3]:
        sentences.append(game["note"])
    if bridge_games:
        sentences.append(bridge_games[0]["note"])

    return {
        "season": season,
        "week": week,
        "headline_start_week": headline_start,
        "counter": counter,
        "provisional_label": poll.get("provisional_label"),
        "diagnostics": diagnostics,
        "nodes": nodes,
        "edges": edges,
        "component_sizes": component_sizes,
        "component_sizes_display": sizes_display,
        # The shape of the box the coordinates above belong in. The site sets its
        # viewBox from this rather than guessing, or the rings become ellipses.
        "layout_aspect": positions.aspect,
        "bridge_games": bridge_games[:bridge_games_shown],
        "bridge_games_total": bridge_games_total,
        "would_connect": connectors,
        "what_would_have_to_be_true": sentences,
    }


# --------------------------------------------------------------------- methodology


def _split_label(protocol: dict[str, Any], seasons: list[Any]) -> str:
    """What kind of evaluation these numbers came from, off the run's OWN record.

    This read `tune_<min>_<max>` unconditionally until 2026-08-15, which was fine
    while the only backtest anybody published was the tune-season one. The 2025
    holdout evaluation broke it: those rows would have shipped to the site
    labelled `tune_2025_2025`, which is not a formatting slip but a false claim
    about how a number was produced, printed under a poll whose entire pitch is
    that it does not make those.

    `protocol.split` is written by the harness from the config's own season
    roles, so the label is derived from the run rather than from what the caller
    believed it was running. The fallback keeps older metrics files - which have
    no `split` - rendering exactly as they did.
    """
    stated = protocol.get("split")
    if stated:
        return str(stated)
    if not seasons:
        return "tune"
    lo, hi = min(int(s) for s in seasons), max(int(s) for s in seasons)
    kind = "holdout" if bool(protocol.get("holdout_touched")) else "tune"
    return f"{kind}_{lo}_{hi}"


def _backtest_rows(
    backtest: Path | None, run_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`cfb_backtest_metrics` rows and the publication gate, from the harness JSON."""
    if backtest is None or not backtest.exists():
        return [], []
    payload = _read_json(backtest)
    protocol = payload.get("protocol", {})
    seasons = protocol.get("seasons") or []
    split = _split_label(protocol, seasons)

    rows: list[dict[str, Any]] = []
    wanted = ("n_games", "su_accuracy", "mae", "rmse", "brier", "log_loss")
    for system, block in sorted(payload.get("systems", {}).items()):
        segment = (block.get("segments_from_headline_week") or {}).get("fbs_vs_fbs") or {}
        for metric in wanted:
            value = _f(segment.get(metric))
            if value is not None:
                rows.append(
                    {
                        "run_id": run_id,
                        "split": split,
                        "system": system,
                        "metric": metric,
                        "value": value,
                    }
                )
        violations = _f(block.get("retrodictive_violation_rate"))
        if violations is not None:
            rows.append(
                {
                    "run_id": run_id,
                    "split": split,
                    "system": system,
                    "metric": "violations",
                    "value": violations,
                }
            )

    ours = (payload.get("systems", {}).get("schedule_odds") or {}).get("gate") or {}
    thresholds = ours.get("thresholds") or {}
    observed = ours.get("observed") or {}
    criteria = [
        ("su_accuracy", "Straight-up accuracy at or above the floor", "su_accuracy_min"),
        ("mae", "Mean absolute error at or below the ceiling", "mae_max"),
        ("rmse", "Root mean squared error at or below the ceiling", "rmse_max"),
        (
            "calibration",
            "Worst decile calibration deviation within tolerance",
            "calibration_max_decile_deviation_pp",
        ),
        ("violations_vs_baselines", "Retrodictive violations at or below every baseline", None),
        ("brier_beats_all_baselines", "Brier score beats every baseline", None),
        ("retro_vs_live_monotone", "Retro-vs-live divergence declines monotonically", None),
    ]
    gate: list[dict[str, Any]] = []
    for name, statement, threshold_key in criteria:
        verdict = ours.get(name)
        status = "not yet decided" if verdict is None else ("pass" if verdict else "FAIL")
        detail_bits: list[str] = []
        if threshold_key and thresholds.get(threshold_key) is not None:
            detail_bits.append(f"threshold {thresholds[threshold_key]}")
        obs = observed.get(
            {
                "su_accuracy": "su_accuracy",
                "mae": "mae",
                "rmse": "rmse",
                "calibration": "max_calibration_deviation_pp",
                "violations_vs_baselines": "retrodictive_violation_rate",
            }.get(name, "")
        )
        got = _f(obs)
        if got is not None:
            detail_bits.append(f"observed {got:.4g}")
        gate.append(
            {
                "name": name,
                "statement": statement,
                "status": status,
                "detail": "; ".join(detail_bits) or None,
            }
        )
    if ours:
        gate.append(
            {
                "name": "passed",
                "statement": "Every decided criterion passes",
                "status": "pass" if ours.get("passed") else "FAIL",
                "detail": (
                    "Undecided criteria are reported as undecided, never as passes: "
                    + ", ".join(ours.get("undecided") or ["none"])
                ),
            }
        )
    return rows, gate


def _weaknesses() -> list[dict[str, str]]:
    """The "where this is weak" blocks, lifted verbatim out of the ADRs (report 05 §9.1)."""
    out: list[dict[str, str]] = []
    for filename, heading in WEAKNESS_SECTIONS:
        path = REPO_ROOT / "docs" / "adr" / filename
        if not path.exists():
            continue
        body = _extract_section(path.read_text(encoding="utf-8"), heading)
        if body:
            out.append({"heading": heading, "body": body, "source": f"docs/adr/{filename}"})
    return out


# ---------------------------------------------------------------------------- data


def _artifact_rows(out: Path, run_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(out.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        rows.append(
            {
                "run_id": run_id,
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "description": ARTIFACT_NOTES.get(path.name, ""),
            }
        )
    return rows


def _duckdb_one_liner(season: int, week: int) -> str:
    """One line, copy-pasteable, no account, no clone (report 05 §9.1)."""
    tag = f"poll-{season}-w{week:02d}"
    url = f"https://github.com/vyhlidal/cfb-poll/releases/download/{tag}/ratings_live.parquet"
    return (
        f"duckdb -c \"SELECT team, rank, odds_key, power, gap FROM '{url}' "
        'WHERE rank IS NOT NULL ORDER BY rank LIMIT 25"'
    )


def _licenses() -> list[dict[str, str]]:
    return [
        {
            "name": "Our ratings and rankings — CC BY 4.0",
            "body": (
                "Everything this project computes and publishes is released under CC BY 4.0. "
                "Share and adapt it, including commercially, with credit and a link. "
                "Attribution: Ratings from cfb-poll (https://github.com/vyhlidal/cfb-poll), "
                "CC BY 4.0. We chose attribution over public domain for one reason: a ranking "
                "that travels without its methodology is exactly the thing this project exists "
                "to replace."
            ),
        },
        {
            "name": "Upstream inputs — SportsDataverse, MIT",
            "body": (
                "The input archive is republished from SportsDataverse under the MIT license, "
                "and that single fact is load-bearing for the whole project: it means a "
                "stranger can reproduce every ranking we have ever published with no API key, "
                "no account, and no permission from anyone."
            ),
        },
        {
            "name": "Code — MIT",
            "body": "The pipeline is MIT licensed. See LICENSE in the repository.",
        },
        {
            "name": "Team names and logos — trademarks of their institutions",
            "body": (
                "Team names and logos are trademarks of their respective institutions and are "
                "used here for identification only. This site is independent and is not "
                "affiliated with, endorsed by, or sponsored by any school, conference, the "
                "NCAA, or the College Football Playoff. Logo images are served by third "
                "parties; no logo files are hosted or redistributed by this project. Marks "
                "are shown unaltered, at small size, inside the rankings, and are never used "
                "as this site's own mark. Any rights holder who would prefer their mark not "
                "appear here can say so at github.com/vyhlidal/cfb-poll/issues and it will be "
                "removed — the logo-free mode is a single configuration flag that was built "
                "before the logos were, and the share cards this project publishes carry no "
                "school logo at all."
            ),
        },
        {
            "name": "Data — College Football Data",
            "body": (
                "Some inputs come from collegefootballdata.com, whose terms say attribution "
                "is not required but strongly encouraged. It is owed and it costs a line. "
                "CFBD supplied data and supplied no rights in any trademark."
            ),
        },
    ]
