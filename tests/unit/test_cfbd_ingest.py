"""The CFBD leg: the append-only raw archive, the quota guard, and the ID finding.

Three groups of tests, and the middle one is the point of the module.

1. `ingest/archive.py` — append-only is a claim about behaviour, so it is tested
   as behaviour: a re-pull must not overwrite, a manifest must not lose an entry,
   and a byte that changes underneath the manifest must fail `verify`.

2. THE ID RECONCILIATION, settled empirically and pinned here. docs/data-findings
   §3 corrected report 01 §3.10 (the MIT crosswalk maps ESPN/Fox/Yahoo and has no
   CFBD column) and left the question open with an explicit "verify empirically
   before the first cross-source check, and do not assume". These tests are that
   verification, run against archived bodies rather than the network, so the
   finding is re-checked on every build and cannot rot.

3. The cross-source check report 01 §5.5 asked for, made concrete: the 80 CFBD
   postseason rows the loader merges into 2021-2022 are reconstructed from the
   MIT-licensed play-by-play and compared. This is what makes a private-archive
   supplement auditable by someone who cannot have the private archive.

Everything here is offline. No test in this file opens a socket.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx
import polars as pl
import pytest

from cfbpoll.config import REPO_ROOT
from cfbpoll.ingest import archive, cfbd
from cfbpoll.ingest.sportsdataverse import (
    DEFAULT_ARCHIVE as SDV_ARCHIVE,
)
from cfbpoll.ingest.sportsdataverse import (
    canonical_games,
    cfbd_supplement,
)

CFBD_ARCHIVE = cfbd.DEFAULT_ARCHIVE

#: The two seasons whose postseason is absent from `cfb_schedules_*` entirely.
BACKFILLED = (2021, 2022)

needs_cfbd_archive = pytest.mark.skipif(
    not cfbd.archived_games(2021, "postseason"),
    reason="private CFBD archive not materialised; run `cfbpoll ingest cfbd --postseason`",
)
needs_sdv_archive = pytest.mark.skipif(
    not (SDV_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised; run `cfbpoll archive sync`",
)


# --------------------------------------------------------------- the raw archive


def test_write_raw_never_overwrites(tmp_path: Path) -> None:
    """A re-pull writes a NEW file. That is what makes a stat correction visible."""
    stamp = archive.write_raw(b'{"a":1}', "/games", {"year": 2021}, tmp_path, bucket="2021/x")
    again = archive.write_raw(b'{"a":2}', "/games", {"year": 2021}, tmp_path, bucket="2021/x")
    assert stamp["file"] != again["file"]
    assert stamp["sha256"] != again["sha256"]
    bodies = sorted(
        p.name
        for p in (tmp_path / "2021" / "x").glob("*.json")
        if p.name != archive.MANIFEST_NAME
    )
    assert len(bodies) == 2
    assert (tmp_path / "2021" / "x" / stamp["file"]).read_bytes() == b'{"a":1}'


def test_manifest_records_url_status_bytes_sha_and_time(tmp_path: Path) -> None:
    entry = archive.write_raw(
        b"[]",
        "/games/teams",
        {"year": 2022, "week": 1},
        tmp_path,
        bucket="2022/postseason",
        url="https://api.collegefootballdata.com/games/teams?year=2022&week=1",
        status=200,
    )
    assert set(entry) >= {"url", "params", "status", "bytes", "sha256", "fetched_at", "file"}
    assert entry["bytes"] == 2
    assert entry["status"] == 200
    entries = archive.manifest_entries(tmp_path / "2022" / "postseason" / archive.MANIFEST_NAME)
    assert [e["file"] for e in entries] == [entry["file"]]
    assert archive.verify(tmp_path / "2022" / "postseason" / archive.MANIFEST_NAME) is True


def test_manifest_is_append_only_across_writes(tmp_path: Path) -> None:
    first = archive.write_raw(b"1", "/info", {}, tmp_path, bucket="_meta")
    second = archive.write_raw(b"2", "/calendar", {"year": 2026}, tmp_path, bucket="_meta")
    names = {e["file"] for e in archive.manifest_entries(tmp_path / "_meta" / "_manifest.json")}
    assert names == {first["file"], second["file"]}


def test_verify_fails_when_a_byte_changes(tmp_path: Path) -> None:
    entry = archive.write_raw(b'{"ok":1}', "/info", {}, tmp_path, bucket="_meta")
    (tmp_path / "_meta" / entry["file"]).write_bytes(b'{"ok":0}')
    with pytest.raises(RuntimeError, match="sha256 mismatch"):
        archive.verify(tmp_path / "_meta" / "_manifest.json")


def test_a_credential_in_a_url_is_refused(tmp_path: Path) -> None:
    """report 01 §3.2: never place the key in a URL. Asserted, not trusted."""
    with pytest.raises(ValueError, match="credential"):
        archive.write_raw(
            b"{}", "/info", {}, tmp_path, bucket="_meta", url="https://x/info?apiKey=secret"
        )


def test_param_slug_is_order_independent() -> None:
    assert archive.param_slug({"week": 3, "year": 2021}) == archive.param_slug(
        {"year": 2021, "week": 3}
    )
    assert archive.param_slug({}) == "none"


def test_the_cfbd_archive_subtree_is_not_tracked_by_git() -> None:
    """CFBD terms §3: raw API responses are never published. Enforced, not promised."""
    tracked = subprocess.run(
        ["git", "ls-files", "archive/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert tracked.strip() == ""
    if CFBD_ARCHIVE.exists():
        # `git check-ignore` refuses any path "beyond a symbolic link", and the
        # archive root IS a symlink in the layout .gitignore documents: one
        # checkout holds the 0.55 GB and the others point at it. Probing the
        # symlink itself is the same question - the bare `archive` line in
        # .gitignore exists for exactly this case - and it is a question git will
        # actually answer. Without this branch the test fails on a worktree while
        # the property it guards is perfectly intact.
        root = REPO_ROOT / "archive"
        probe = root if root.is_symlink() else CFBD_ARCHIVE / "_meta"
        ignored = subprocess.run(
            ["git", "check-ignore", str(probe)], cwd=REPO_ROOT, capture_output=True, text=True
        )
        assert ignored.returncode == 0, f"{probe} must be gitignored"


def test_gitignore_covers_the_archive_as_a_symlink_and_not_only_as_a_directory() -> None:
    """THE PREMISE OF THE BRANCH ABOVE, pinned where every environment runs it.

    The symlink probe only executes on a checkout whose `archive` IS a symlink,
    which is a worktree and is not the checkout CI runs in. So the branch that
    fixed the failure is exercised by nobody on the machine most likely to delete
    it, and the line it depends on is one word in a file with no tests.

    `archive/` matches a directory and nothing else: git will not follow a
    symbolic link to decide whether what is behind it is ignored, so the bare
    `archive` line is what makes the symlinked layout ignorable at all. Both lines
    have to be there, and this says so in a place a reader will find before
    deleting one as a duplicate.
    """
    lines = {
        line.strip()
        for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    assert "archive/" in lines, "the directory form, for the checkout that holds the bytes"
    assert "archive" in lines, "the bare form, for the checkouts that symlink to it"


# ------------------------------------------------------------------ the quota guard


def _stub_session(tmp_path: Path, payload: dict, status: int = 200) -> cfbd.Session:
    session = cfbd.Session(archive_root=tmp_path, key="test-key")
    session._client = httpx.Client(  # noqa: SLF001 - deliberate injection point
        base_url=cfbd.BASE_URL,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json=payload, request=request)
        ),
    )
    return session


def test_quota_guard_aborts_below_the_floor(tmp_path: Path) -> None:
    with _stub_session(tmp_path, {"remainingCalls": 120, "tierName": "Free"}) as session:
        with pytest.raises(cfbd.QuotaError, match="floor is 700"):
            session.check_quota(700)


def test_quota_guard_passes_above_the_floor(tmp_path: Path) -> None:
    with _stub_session(tmp_path, {"remainingCalls": 990, "tierName": "Free"}) as session:
        assert session.check_quota(700)["remainingCalls"] == 990
        assert session.calls == 1


def test_429_is_a_quota_error_not_a_retryable_failure(tmp_path: Path) -> None:
    """report 01 §5.2: retrying a quota error fixes nothing, so it gets its own type."""
    with _stub_session(tmp_path, {"message": "Monthly call quota exceeded"}, status=429) as s:
        with pytest.raises(cfbd.QuotaError):
            s.fetch("/games", {"year": 2021})


def test_a_body_is_archived_even_when_the_request_fails(tmp_path: Path) -> None:
    """Archive BEFORE parse: a 400 must be diagnosable without spending a second call."""
    with _stub_session(tmp_path, {"message": "Validation Failed"}, status=400) as s:
        assert (
            s.fetch("/games/teams", {"year": 2021}, bucket="2021/postseason", required=False)
            is None
        )
    entries = archive.manifest_entries(tmp_path / "2021" / "postseason" / "_manifest.json")
    assert [e["status"] for e in entries] == [400]


def test_missing_cfbd_archive_is_a_degraded_run_not_a_failure(tmp_path: Path) -> None:
    """The fork's normal state: no private archive, no error, no CFBD rows."""
    assert cfbd.archived_games(2021, "postseason", tmp_path) == []
    assert cfbd_supplement(2021, tmp_path) is None


# ------------------------------------------------- THE ID FINDING, pinned to data


@needs_cfbd_archive
@needs_sdv_archive
@pytest.mark.parametrize(("season", "week"), [(2021, 5), (2023, 10)])
def test_cfbd_game_ids_are_espn_game_ids(season: int, week: int) -> None:
    """docs/data-findings.md §3, settled: the two sources share ONE id space.

    Every CFBD `id` for a sampled regular-season week is present as a
    SportsDataverse `game_id`, and the row it lands on is the same game — same
    teams, same scores, same date, same neutral-site flag. That is what licenses
    `game_id` as the merge key and retires the (season, date, home, away)
    fallback the findings held open.
    """
    bodies = cfbd.archived_bodies(
        "/games",
        f"{season}/week-{week:02d}",
        params={"year": season, "week": week, "seasonType": "regular", "classification": "fbs"},
    )
    assert bodies, "sampled week is not in the archive"
    api = {int(g["id"]): g for g in json.loads(bodies[-1].read_text(encoding="utf-8"))}
    assert len(api) >= 60

    frame = canonical_games([season], include_cfbd=False).filter(
        (pl.col("season_type") == "regular") & (pl.col("week") == week)
    )
    parquet = {int(r["game_id"]): r for r in frame.iter_rows(named=True)}

    assert set(api) <= set(parquet), "a CFBD id with no SportsDataverse row"
    for gid, game in api.items():
        row = parquet[gid]
        assert (game["homeTeam"], game["awayTeam"]) == (row["home_team"], row["away_team"])
        assert (game["homePoints"], game["awayPoints"]) == (row["home_points"], row["away_points"])
        assert bool(game["neutralSite"]) is bool(row["neutral_site"])
        assert game["startDate"][:10] == str(row["start_date"])[:10]


@needs_cfbd_archive
@needs_sdv_archive
def test_team_names_need_no_normalisation_table() -> None:
    """Both pipelines are ESPN-derived, so the school strings are identical."""
    for season in BACKFILLED:
        rows = cfbd.archived_games(season, "postseason")
        names = {g["homeTeam"] for g in rows} | {g["awayTeam"] for g in rows}
        frame = canonical_games([season], include_cfbd=False)
        vocabulary = set(frame["home_team"].to_list()) | set(frame["away_team"].to_list())
        assert names <= vocabulary, sorted(names - vocabulary)


# --------------------------------------------------- the 2021-2022 postseason merge


@needs_cfbd_archive
@needs_sdv_archive
def test_the_supplement_only_ever_fills_holes() -> None:
    """Zero of the 80 postseason ids already existed. The parquet keeps every tie."""
    for season, expected in ((2021, 38), (2022, 42)):
        supplement = cfbd_supplement(season)
        assert supplement is not None and supplement.height == expected
        parquet_ids = set(canonical_games([season], include_cfbd=False)["game_id"].to_list())
        assert set(supplement["game_id"].to_list()).isdisjoint(parquet_ids)


@needs_cfbd_archive
@needs_sdv_archive
def test_merged_rows_carry_their_source() -> None:
    frame = canonical_games([2021, 2022])
    counts = dict(frame.group_by("source").len().sort("source").iter_rows())
    assert counts["cfbd"] == 80
    assert counts["sportsdataverse"] > 6000
    cfbd_rows = frame.filter(pl.col("source") == "cfbd")
    assert set(cfbd_rows["season_type"].to_list()) == {"postseason"}
    assert set(cfbd_rows["game_type"].to_list()) == {"cfp", "bowl_non_cfp"}


@needs_cfbd_archive
@needs_sdv_archive
def test_cfbd_postseason_scores_reproduce_from_the_MIT_play_by_play() -> None:
    """The cross-source check of report 01 §5.5, on data a fork can hold.

    All 80 merged games are present in the MIT play-by-play — they are 80 of the
    86 orphan `game_id`s docs/data-findings.md §10 recorded. Reconstructing each
    final score from the play-level scoreboard reproduces CFBD in 79 of 80. The
    single residual is 2022 Mississippi State–Illinois, decided in overtime,
    which is exactly the limitation §12 already documented for this column.
    """
    disagreements: list[int] = []
    total = 0
    for season in BACKFILLED:
        api = {int(g["id"]): g for g in cfbd.archived_games(season, "postseason")}
        total += len(api)
        plays = (
            pl.scan_parquet(SDV_ARCHIVE / "pbp" / f"play_by_play_{season}.parquet")
            .select("game_id", "pos_team", "def_pos_team", "pos_team_score", "def_pos_team_score")
            .filter(pl.col("game_id").is_in(sorted(api)))
            .collect()
        )
        assert plays["game_id"].n_unique() == len(api), "a merged game with no MIT play-by-play"

        offense = plays.select(pl.col("game_id"), team="pos_team", score="pos_team_score")
        defense = plays.select(pl.col("game_id"), team="def_pos_team", score="def_pos_team_score")
        final = (
            pl.concat([offense, defense])
            .drop_nulls()
            .group_by(["game_id", "team"])
            .agg(pl.col("score").max())
        )
        board: dict[int, dict[str, int]] = {}
        for row in final.iter_rows(named=True):
            board.setdefault(int(row["game_id"]), {})[row["team"]] = int(row["score"])

        for gid, game in api.items():
            seen = board.get(gid, {})
            if (
                seen.get(game["homeTeam"]) != game["homePoints"]
                or seen.get(game["awayTeam"]) != game["awayPoints"]
            ):
                disagreements.append(gid)

    assert total == 80
    # 401442011 — 2022 ReliaQuest Bowl, Mississippi State 19 Illinois 10 in
    # overtime. Pinned by id: a SECOND disagreement is a real signal and must
    # fail the build rather than widen a tolerance.
    assert disagreements == [401442011]
