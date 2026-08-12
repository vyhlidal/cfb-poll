"""Play-by-play: the canonical play frame, keyed to games.

Specified by report 02 §3.1 (L1 needs one row per play with offense, defense,
value, site, quarter, score margin and clock); the binding data rules are
docs/data-findings.md.

WHERE THE DATA IS. `archive/sportsdataverse/pbp/play_by_play_<season>.parquet`,
362 columns, 163k-293k rows per season. Coverage of the FBS-vs-FBS evaluation
universe is COMPLETE for 2021-2023 (732/732, 734/734, 792/792); coverage of the
wider model universe is not (849/1526, 1411/1552, 1492/1603) because FCS-vs-FCS
games frequently have no play feed. A team with no plays keeps its L2
coefficient and gets an L1 coefficient of zero, i.e. league average, which is
the honest default and exactly what ridge would shrink it to anyway.

The traffic runs the other way too: 15,353 plays across 86 game_ids in the
2021-2023 files belong to games that appear in NO row of `cfb_schedules_*`. The
schedule series is the authority on which games exist (docs/data-findings.md §5),
so `attach_games` drops them on an inner join and `join_report` counts them. A
silent play-to-game join failure is not possible here.

WHAT WE REFUSE TO READ, AND WHY IT MATTERS MORE HERE THAN ANYWHERE ELSE.
These files ship `EPA`, `ep_before`, `ep_after`, `ppa`, `wpa`, `wp_before`,
`wp_after`, `ExpScoreDiff`, `fg_make_prob`, the six `*_before`/`*_after`
next-score probability columns, `home_team_pregame_elo`, `spread` and
`over_under`. Every one of those is a third party's fitted model evaluated on
our data. Report 01 §5.6 and report 02 §3.10 ban them as model inputs, and the
ban is the whole thesis: a ranking that imports someone else's expected-points
model cannot claim its numbers are derived from published rules and public data
alone. `RAW_COLUMNS` below is the complete allow-list this module will read from
the parquet, it is deliberately short, and `cfbpoll audit-features` enforces it.

The precomputed EPA is used in exactly one place - `model/ep.py` reports the
correlation between our per-play value and theirs as a DIAGNOSTIC - and that
path is a separate, explicitly named function that no fit calls.

BINDING RULE 1 (docs/data-findings.md §1) IS WHY `attach_games` EXISTS.
Every week-scoped operation must key on (season, season_type, week), and the
authoritative source of that triple is the GAMES table, never the PBP file's own
`week`/`season_type` columns. So this module reads neither: `load_plays` returns
a frame with no week at all, and `attach_games` joins the week, the season type,
the game type, the site and the division classes off the canonical games frame.
A play whose game is not in the games frame is dropped and counted, so a silent
join failure is impossible.

PLAY ORDER. `game_row_number` is the only per-game ordering key in the file that
is unique: `row` restarts each half, `id_play` collides, and `game_play_number`
repeats when a play carries a penalty. Ordering is (game_id, game_row_number)
everywhere in this package.

DUPLICATE ROWS IN 2021, found while building this module and not previously
recorded. `play_by_play_2021.parquet` contains 4,810 rows that are EXACT
duplicates of another row in the same game - 8,949 rows collapse to 4,139
distinct plays, across 343 games. They are byte-identical repeats, not a pair of
plays that happen to look alike, so keeping one of each is lossless. Left in,
they would double the weight of a random 3% of 2021's plays in the L1 fit.
`load_plays` de-duplicates on (game_id, game_row_number) and `DUPLICATE_PLAY_ROWS`
below records the expected count so a change fails the test suite. 2022-2025 are
clean.

DETERMINISM. No RNG, no network, no clock. Frames are sorted on an explicit key
before they are returned.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from cfbpoll.config import REPO_ROOT

__all__ = [
    "CANONICAL_COLUMNS",
    "DEFAULT_ARCHIVE",
    "DUPLICATE_PLAY_ROWS",
    "PLAY_CLASSES",
    "PLAY_TYPE_CLASS",
    "RAW_COLUMNS",
    "attach_games",
    "join_report",
    "load_plays",
    "plays_for",
]

#: Exact-duplicate rows dropped per season by the de-duplication above. Recorded
#: rather than merely handled, so that a silent upstream fix or a silent upstream
#: worsening both show up as a failing test.
DUPLICATE_PLAY_ROWS: dict[int, int] = {2021: 4810, 2022: 0, 2023: 0, 2024: 0, 2025: 0}

DEFAULT_ARCHIVE = REPO_ROOT / "archive" / "sportsdataverse"

#: The ONLY columns read out of the play-by-play parquet. See the module
#: docstring: everything omitted here that looks useful is a third party's model
#: output and is banned as a model input (report 01 §5.6, report 02 §3.10).
#:
#: Why each one is here:
#:   game_id           the join key to the games table
#:   game_row_number   the unique per-game play order (see the docstring)
#:   pos_team          the offense - one of the two design-matrix columns
#:   def_pos_team      the defense - the other one
#:   home, away        cross-checked against the games table in `join_report`,
#:                     never used to derive anything the model reads
#:   period            garbage-time thresholds are per quarter (report 02 §3.1)
#:   clock_minutes     end-of-half heave detection, and published context
#:   clock_seconds     same
#:   down              expected-points state
#:   distance          expected-points state
#:   yards_to_goal     expected-points state (field position)
#:   yards_gained      published context and the fallback play value
#:   play_type         classification: rush / pass / special teams / not a play
#:   play_text         kneel and spike detection (report 02 §3.1, zero weight)
#:   score_pts         points scored ON this play, signed to the offense. This is
#:                     the SCOREBOARD, not a model: it is what our own
#:                     expected-points layer is fitted to.
#:   score_diff_start  score margin BEFORE the snap, offense's perspective - the
#:                     garbage-time input. Using the post-play score would let a
#:                     touchdown put its own scoring play into garbage time.
RAW_COLUMNS: tuple[str, ...] = (
    "game_id",
    "game_row_number",
    "pos_team",
    "def_pos_team",
    "home",
    "away",
    "period",
    "clock_minutes",
    "clock_seconds",
    "down",
    "distance",
    "yards_to_goal",
    "yards_gained",
    "play_type",
    "play_text",
    "score_pts",
    "score_diff_start",
)

CANONICAL_COLUMNS: tuple[str, ...] = (
    "game_id",
    "season",
    "play_index",
    "offense",
    "defense",
    "period",
    "half",
    "score_segment",
    "clock_seconds",
    "down",
    "distance",
    "yards_to_goal",
    "yards_gained",
    "play_type",
    "play_class",
    "points_scored",
    "score_margin",
    "is_snap",
    "is_kneel",
    "is_spike",
    "pbp_home",
    "pbp_away",
)

#: Play classes. `is_snap` (a genuine down-and-distance snap, which is what the
#: expected-points state is defined on) is true for rush, pass, scrimmage_other,
#: penalty, punt and field_goal; false for kickoff, two_point and non_play.
PLAY_CLASSES: tuple[str, ...] = (
    "rush",
    "pass",
    "scrimmage_other",
    "penalty",
    "punt",
    "field_goal",
    "kickoff",
    "two_point",
    "non_play",
)

#: The complete play_type vocabulary of the 2021-2025 archive (48 values,
#: including the null), classified. `tests/unit/test_plays.py` asserts the
#: archive contains no play_type this table does not know, so a vocabulary drift
#: in a future season fails loudly instead of silently landing in "non_play".
PLAY_TYPE_CLASS: dict[str | None, str] = {
    # --- rush
    "Rush": "rush",
    "Rushing Touchdown": "rush",
    # --- pass
    "Pass Reception": "pass",
    "Pass Incompletion": "pass",
    "Pass Completion": "pass",
    "Pass": "pass",
    "Passing Touchdown": "pass",
    "Sack": "pass",
    "Interception Return": "pass",
    "Interception Return Touchdown": "pass",
    # --- scrimmage, unit unknown (a fumble can follow either)
    "Fumble": "scrimmage_other",
    "Fumble Recovery (Own)": "scrimmage_other",
    "Fumble Recovery (Opponent)": "scrimmage_other",
    "Fumble Recovery (Opponent) Touchdown": "scrimmage_other",
    "Fumble Return Touchdown": "scrimmage_other",
    "Safety": "scrimmage_other",
    # --- penalty rows: real state transitions, but not an execution play
    "Penalty": "penalty",
    "Penalty Touchdown": "penalty",
    "Penalty (Safety)": "penalty",
    # --- punt (a 4th-down snap; special teams)
    "Punt": "punt",
    "Punt Return": "punt",
    "Punt Return Touchdown": "punt",
    "Punt Team Fumble Recovery": "punt",
    "Punt Team Fumble Recovery Touchdown": "punt",
    "Punt (Safety)": "punt",
    "Blocked Punt": "punt",
    "Blocked Punt Touchdown": "punt",
    "Blocked Punt (Safety)": "punt",
    # --- field goal (also a snap)
    "Field Goal Good": "field_goal",
    "Field Goal Missed": "field_goal",
    "Blocked Field Goal": "field_goal",
    "Blocked Field Goal Touchdown": "field_goal",
    "Missed Field Goal Return": "field_goal",
    "Missed Field Goal Return Touchdown": "field_goal",
    # --- kickoff: NOT a snap, no down-and-distance state
    "Kickoff": "kickoff",
    "Kickoff Return (Offense)": "kickoff",
    "Kickoff Return Touchdown": "kickoff",
    "Kickoff Team Fumble Recovery": "kickoff",
    "Kickoff Team Fumble Recovery Touchdown": "kickoff",
    # --- conversion attempts: untimed, no field position, excluded everywhere
    "Two Point Pass": "two_point",
    "Two Point Rush": "two_point",
    "Defensive 2pt Conversion": "two_point",
    # --- administrative rows
    "Timeout": "non_play",
    "End Period": "non_play",
    "End of Half": "non_play",
    "End of Game": "non_play",
    "End of Regulation": "non_play",
    "Uncategorized": "non_play",
    "placeholder": "non_play",
    None: "non_play",
}

_SNAP_CLASSES = ("rush", "pass", "scrimmage_other", "penalty", "punt", "field_goal")

#: Overtime is its own scoring segment. `half` in the source file is 1 or 2 and
#: folds every overtime period into the second half, which would let a
#: fourth-quarter play's "next score in this half" be an overtime score. Regulation
#: ends at the end of the fourth quarter and the expected-points target ends with
#: it, which is the standard construction and the only one that is well defined.
_OVERTIME_SEGMENT = 3


def _read_season(season: int, archive: Path) -> pl.DataFrame:
    path = archive / "pbp" / f"play_by_play_{season}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"missing play-by-play parquet for {season}: {path}. "
            "Run `cfbpoll archive sync --verify` (report 01 §3.10)."
        )
    return pl.read_parquet(path, columns=list(RAW_COLUMNS)).with_columns(
        pl.col("game_id").cast(pl.Int64),
        pl.col("game_row_number").cast(pl.Int32),
        pl.col("period").cast(pl.Int32),
        pl.col("clock_minutes").cast(pl.Int32),
        pl.col("clock_seconds").cast(pl.Int32),
        pl.lit(season, dtype=pl.Int32).alias("season"),
    )


def load_plays(
    seasons: list[int] | tuple[int, ...],
    archive: str | Path | None = None,
) -> pl.DataFrame:
    """The canonical play frame for one or more seasons. No week, by design.

    Week and season type are NOT returned: docs/data-findings.md §1 makes the
    games table the only authority on them, and `attach_games` is the only way to
    get them onto a play. This function is otherwise a pure, sorted projection of
    the archive.
    """
    root = Path(archive) if archive is not None else DEFAULT_ARCHIVE
    frames = [_read_season(int(s), root) for s in sorted({int(s) for s in seasons})]
    df = pl.concat(frames, how="vertical")
    # See DUPLICATE ROWS IN 2021 in the module docstring. `keep="first"` on a
    # frame already sorted by the ordering key is deterministic, and the dropped
    # rows are byte-identical to the kept ones, so nothing is lost.
    df = df.sort(["game_id", "game_row_number"]).unique(
        subset=["game_id", "game_row_number"], keep="first", maintain_order=True
    )

    play_class = pl.col("play_type").replace_strict(
        PLAY_TYPE_CLASS, default="non_play", return_dtype=pl.String
    )
    text = pl.col("play_text").fill_null("").str.to_lowercase()

    df = df.with_columns(
        play_class=play_class,
        is_kneel=text.str.contains("kneel"),
        is_spike=text.str.contains("spike"),
        clock_seconds_remaining=(
            pl.col("clock_minutes").fill_null(0) * 60 + pl.col("clock_seconds").fill_null(0)
        ).cast(pl.Int32),
        half=pl.when(pl.col("period") <= 2)
        .then(1)
        .when(pl.col("period") <= 4)
        .then(2)
        .otherwise(_OVERTIME_SEGMENT)
        .cast(pl.Int32),
    )

    df = df.with_columns(
        is_snap=(
            pl.col("play_class").is_in(_SNAP_CLASSES)
            & pl.col("down").is_between(1, 4)
            & pl.col("yards_to_goal").is_between(1, 99)
            & (pl.col("period") <= 4)
        )
    )

    return (
        df.with_columns(
            play_index=pl.col("game_row_number"),
            offense=pl.col("pos_team"),
            defense=pl.col("def_pos_team"),
            score_segment=pl.col("half"),
            clock_seconds=pl.col("clock_seconds_remaining"),
            down=pl.col("down").cast(pl.Int32),
            distance=pl.col("distance").cast(pl.Int32),
            yards_to_goal=pl.col("yards_to_goal").cast(pl.Int32),
            yards_gained=pl.col("yards_gained").cast(pl.Float64),
            # `+ 0.0` normalises the source's occasional -0.0 to 0.0 so that a
            # written artifact never differs from another only in a sign bit.
            points_scored=(pl.col("score_pts").fill_null(0.0) + 0.0).cast(pl.Float64),
            score_margin=(pl.col("score_diff_start").fill_null(0.0) + 0.0).cast(pl.Float64),
            pbp_home=pl.col("home"),
            pbp_away=pl.col("away"),
        )
        .select(CANONICAL_COLUMNS)
        .sort(["game_id", "play_index"])
    )


#: The columns `attach_games` copies off the canonical games frame. Every one of
#: them is authoritative there and nowhere else (docs/data-findings.md §1, §5).
_GAME_COLUMNS: tuple[str, ...] = (
    "game_id",
    "week",
    "season_type",
    "game_type",
    "neutral_site",
    "home_team",
    "away_team",
    "home_class",
    "away_class",
)


def attach_games(plays: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """Join week, season type, game type and site off the GAMES table. Inner join.

    Inner is the point: a play whose game is not in `games` must not reach a fit,
    and a game the harness has not released yet is exactly such a play. This is
    the walk-forward guarantee at the play level - `plays_for` is the thin
    wrapper the harness actually calls, and `tests/property` plants a future play
    and asserts it never arrives.

    `offense_is_home` is derived from the GAMES table's `home_team`, not from the
    play file's own `home` column, for the same reason: one authority per fact.
    `join_report` cross-checks the two and the test suite asserts they agree.
    """
    joined = plays.join(games.select(_GAME_COLUMNS), on="game_id", how="inner")
    return joined.with_columns(
        offense_is_home=(pl.col("offense") == pl.col("home_team")),
        offense_class=pl.when(pl.col("offense") == pl.col("home_team"))
        .then(pl.col("home_class"))
        .otherwise(pl.col("away_class")),
        defense_class=pl.when(pl.col("offense") == pl.col("home_team"))
        .then(pl.col("away_class"))
        .otherwise(pl.col("home_class")),
    ).sort(["game_id", "play_index"])


def plays_for(plays: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """Exactly the plays belonging to `games`, joined to them. The walk-forward slice.

    No model module is allowed to select its own play rows, for the same reason
    no model module selects its own games (report 02 §5.1): the guarantee is a
    property of one function, and this is it at the play level.
    """
    return attach_games(plays, games)


def join_report(plays: pl.DataFrame, games: pl.DataFrame) -> dict[str, object]:
    """Integrity of the play-to-game join, as numbers rather than as a promise.

    Reports orphan plays (a play whose game is absent from the games frame),
    games with no play coverage, and any disagreement between the play file's own
    home/away labels and the games table's. Every count should be zero except
    `games_without_plays`, which is a real and documented coverage gap in
    FCS-vs-FCS scheduling (see the module docstring).
    """
    game_ids = games.select("game_id")
    orphans = plays.join(game_ids, on="game_id", how="anti")
    joined = attach_games(plays, games)
    covered = joined.select("game_id").unique()
    uncovered = game_ids.join(covered, on="game_id", how="anti")

    disagree = joined.filter(
        (pl.col("pbp_home") != pl.col("home_team")) | (pl.col("pbp_away") != pl.col("away_team"))
    )
    unknown_types = (
        plays.filter(~pl.col("play_type").is_in(sorted(t for t in PLAY_TYPE_CLASS if t is not None)))
        .filter(pl.col("play_type").is_not_null())
        .select("play_type")
        .unique()
        .to_series()
        .to_list()
    )
    return {
        "n_plays": int(plays.height),
        "n_games": int(games.height),
        "orphan_plays": int(orphans.height),
        "orphan_game_ids": sorted(orphans["game_id"].unique().to_list()),
        "games_with_plays": int(covered.height),
        "games_without_plays": int(uncovered.height),
        "home_away_disagreements": int(disagree.height),
        "unknown_play_types": sorted(str(t) for t in unknown_types),
    }
