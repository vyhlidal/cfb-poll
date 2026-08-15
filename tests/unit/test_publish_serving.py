"""The serving contract, both publication targets, and the rules they enforce.

The point of these tests is not that JSON gets written. It is that the two
targets cannot drift, that the site is never handed a number it would have to
compute, and that the two integrity properties the schema exists to protect —
idempotence and the append-only publication record — are mechanical rather than
remembered.

Everything here runs against a hand-built `out/` directory, so the suite stays
offline, fast, and independent of the archive.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE as SDV_ARCHIVE
from cfbpoll.publish import fixtures, postgres, serving


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    """A schedule parquet with the columns `team_dimension` reads, and no more."""
    root = tmp_path / "archive"
    (root / "schedules").mkdir(parents=True)
    pl.DataFrame(
        {
            "game_id": [1, 2, 3],
            "season": [2023, 2023, 2023],
            "week": [1, 1, 2],
            "season_type": ["regular"] * 3,
            "start_date": [
                "2023-09-02T16:00:00.000Z",
                "2023-09-02T20:00:00.000Z",
                "2023-09-09T16:00:00.000Z",
            ],
            "completed": [True, True, True],
            "neutral_site": [False, False, False],
            "conference_game": [True, False, False],
            "home_id": [194, 333, 194],
            "home_team": ["Ohio State", "Alabama", "Ohio State"],
            "home_conference": ["Big Ten", "SEC", "Big Ten"],
            "home_division": ["fbs", "fbs", "fbs"],
            "away_id": [2005, 194, 333],
            "away_team": ["Akron", "Ohio State", "Alabama"],
            "away_conference": ["MAC", "Big Ten", "SEC"],
            "away_division": ["fbs", "fbs", "fbs"],
            "home_points": [42, 21, 17],
            "away_points": [7, 24, 14],
            "notes": [None, None, None],
        }
    ).write_parquet(root / "schedules" / "cfb_schedules_2023.parquet")

    # The MIT crosswalk. Report 06 §8.1 sources the ESPN id from here; the join is
    # on the integer, so Akron (2005) is deliberately absent to exercise the
    # generated-mark path for an unresolved team.
    (root / "crosswalk").mkdir(parents=True)
    pl.DataFrame(
        {
            "espn_team_id": [194, 333],
            "espn_abbreviation": ["OSU", "ALA"],
        }
    ).write_parquet(root / "crosswalk" / "cfb_teams_crosswalk_2023.parquet")
    return root


def _row(rank: int, team: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "rank": rank,
        "team": team,
        "team_class": "fbs",
        "wins": 3,
        "losses": 0,
        "odds_key": 2.281,
        "tail_p": 0.0052,
        "mid_p": 0.004,
        "expected_wins": 1.5,
        "surprise": 1.5,
        "q_ref": 14.26,
        "q_ref_team": "SMU",
        "resume": 60.0,
        "resume_margin": 30.0,
        "resume_rank_lo": 1,
        "resume_rank_hi": 20,
        "power": 28.10,
        "power_se": 3.0,
        "power_rank_lo": 1,
        "power_rank_hi": 9,
        "gap": 31.90,
        "saturated": 1,
        "rank_lo": 1,
        "rank_hi": 26,
        "rank_median": 8,
        "rank_hindsight": rank + 1,
        "odds_key_hindsight": 2.0,
        "tail_p_hindsight": 0.01,
        "resume_hindsight": 59.0,
        "resume_margin_hindsight": 29.0,
        "power_hindsight": 27.0,
        "gap_hindsight": 32.0,
        "rank_delta": -1,
    }
    base.update(over)
    return base


@pytest.fixture
def out(tmp_path: Path) -> Path:
    """A minimal but complete `cfbpoll rank` output directory."""
    directory = tmp_path / "out"
    directory.mkdir()
    ranking = [
        _row(1, "Ohio State"),
        _row(2, "Alabama", power=20.0, gap=40.0, rank_delta=2, rank_hindsight=0),
        _row(3, "Akron", power=-5.0, gap=65.0, tail_p=0.5, rank_lo=None, rank_hi=None),
    ]
    (directory / "poll.json").write_text(
        json.dumps(
            {
                "season": 2023,
                "through": {"season_type": "regular", "week": 2},
                "provisional": False,
                "provisional_label": None,
                "ranking": ranking,
                "top25": ranking,
            }
        )
    )
    (directory / "model_params.json").write_text(
        json.dumps(
            {
                "season": 2023,
                "q_ref": 14.26,
                "q_ref_team": "SMU",
                "beta_w": 3.0,
                "C": 24.0,
                "h_points": 2.495,
                "sigma": 17.442,
                "lambda_l1": 200.0,
                "lambda_l2": 0.5,
                "k_points_per_unit": 77.19,
                "w1_efficiency": 0.4606,
                "w2_results": 0.4976,
                "headline_ordering": "schedule_odds",
                "hindsight_is_live": False,
            }
        )
    )
    (directory / "_run.json").write_text(
        json.dumps(
            {
                "season": 2023,
                "through_week": 2,
                "git_sha": "c3132c9ffffffffffffffffffffffffffffffffff",
                "config_hash": "ab906806deadbeef",
                "archive_manifest_sha256": "fd57f550",
                "generated_at": "2026-11-08T06:04:00+00:00",
            }
        )
    )
    pl.DataFrame(
        {
            "team": ["Ohio State", "Alabama", "Akron"],
            "power": [28.10, 20.0, -5.0],
            "resume": [60.0, 55.0, 10.0],
        }
    ).write_parquet(directory / "ratings_live.parquet")
    return directory


class TestTeamDimension:
    def test_reads_ids_and_conferences(self, archive: Path) -> None:
        teams = serving.team_dimension(2023, archive)
        assert teams["Ohio State"]["team_id"] == 194
        assert teams["Ohio State"]["conference"] == "Big Ten"

    def test_the_abbreviation_comes_from_the_crosswalk(self, archive: Path) -> None:
        """It is what the generated mark carries, so it is published whether or
        not logos are."""
        teams = serving.team_dimension(2023, archive, {"logos": False})
        assert teams["Ohio State"]["abbreviation"] == "OSU"
        assert teams["Ohio State"]["logo_url"] is None

    def test_conference_is_display_only_and_never_reaches_the_model(self) -> None:
        """Report 02 §3.10 bans conference as a feature and `audit-features`
        enforces it. The guarantee that keeps holding is that the MODEL's loader
        never reads the column at all — only this publication-layer function does."""
        from cfbpoll.ingest.sportsdataverse import RAW_COLUMNS

        assert "home_conference" not in RAW_COLUMNS
        assert "away_conference" not in RAW_COLUMNS


class TestBuild:
    def test_every_serving_table_is_present(self, out: Path, archive: Path) -> None:
        bundle = serving.build(out, archive=archive)
        for table in ("cfb_teams", "cfb_runs", "cfb_model_params", "cfb_poll_published"):
            assert bundle.tables[table], table

    def test_run_id_is_a_pure_function_of_the_run(self, out: Path, archive: Path) -> None:
        """Idempotence rests on this: the same out/ must produce the same run_id
        or `publish postgres` would accumulate a new run on every invocation."""
        first = serving.build(out, archive=archive).run_id
        assert first == serving.build(out, archive=archive).run_id

    def test_a_different_code_version_is_a_different_run(self, out: Path, archive: Path) -> None:
        first = serving.build(out, archive=archive).run_id
        run = json.loads((out / "_run.json").read_text())
        run["git_sha"] = "0000000000000000000000000000000000000000"
        (out / "_run.json").write_text(json.dumps(run))
        assert serving.build(out, archive=archive).run_id != first

    def test_status_is_published(self, out: Path, archive: Path) -> None:
        """Report 03 §7.2: the site must never render a poll whose run is not
        published, so the loader has to be able to see the status."""
        assert serving.build(out, archive=archive).tables["cfb_runs"][0]["status"] == "published"


class TestTheSiteNeverComputes:
    """Report 05 §7.2: neither renderer may derive a quantity. Every number the
    page prints has to arrive already computed, and these are the ones a React
    component would otherwise be tempted to work out for itself."""

    def test_one_in_is_published_not_derived(self, out: Path, archive: Path) -> None:
        rows = serving.build(out, archive=archive).views["week"]["poll"]
        assert rows[0]["one_in"] == 192  # 1 / 0.0052

    def test_one_in_is_null_for_an_impossible_tail(self, out: Path, archive: Path) -> None:
        poll = json.loads((out / "poll.json").read_text())
        poll["ranking"][0]["tail_p"] = 0.0
        (out / "poll.json").write_text(json.dumps(poll))
        rows = serving.build(out, archive=archive).views["week"]["poll"]
        assert rows[0]["one_in"] is None

    def test_interval_width_is_published(self, out: Path, archive: Path) -> None:
        rows = serving.build(out, archive=archive).views["week"]["poll"]
        assert rows[0]["interval_width"] == 25  # 26 - 1

    def test_a_missing_interval_stays_missing(self, out: Path, archive: Path) -> None:
        """A run with no bootstrap must publish an empty column, never a
        fabricated one."""
        rows = serving.build(out, archive=archive).views["week"]["poll"]
        assert rows[2]["rank_lo90"] is None
        assert rows[2]["interval_width"] is None

    def test_power_and_resume_ranks_are_published(self, out: Path, archive: Path) -> None:
        """KenPom's value-with-rank pair — `28.10 (3)` — is a sort, so it happens
        upstream (report 05 §3.2)."""
        rows = serving.build(out, archive=archive).views["week"]["poll"]
        assert [r["power_rank"] for r in rows] == [1, 2, 3]
        assert [r["resume_rank"] for r in rows] == [1, 2, 3]

    def test_record_is_pre_formatted(self, out: Path, archive: Path) -> None:
        assert serving.build(out, archive=archive).views["week"]["poll"][0]["record"] == "3-0"

    def test_max_abs_gap_is_published(self, out: Path, archive: Path) -> None:
        """The Gap bars scale against the week's largest |gap|, which is a
        reduction over the whole table and so cannot happen in a component."""
        assert serving.build(out, archive=archive).views["week"]["max_abs_gap"] == 65.0

    def test_median_interval_width_is_published(self, out: Path, archive: Path) -> None:
        """§5.1: "1-26" alone is alarming; "1-26, against a league median width of
        87" is impressive, and it is the same fact."""
        assert serving.build(out, archive=archive).views["week"]["median_interval_width"] == 25

    def test_the_constants_footer_is_pre_rendered(self, out: Path, archive: Path) -> None:
        params = serving.build(out, archive=archive).views["week"]["params"]
        assert len(params["footer_lines"]) == 2
        assert "q_ref 14.26 (SMU)" in params["footer_lines"][1]
        assert "β_w 3" in params["footer_lines"][1]
        assert params["reproduce"].startswith("uv run cfbpoll rank --season 2023 --through-week 2")

    def test_no_nan_reaches_a_document(self, out: Path, archive: Path) -> None:
        """JSON cannot carry NaN and neither can a reader. A missing number must
        arrive as missing."""
        poll = json.loads((out / "poll.json").read_text())
        poll["ranking"][0]["gap"] = float("nan")
        (out / "poll.json").write_text(json.dumps(poll))
        bundle = serving.build(out, archive=archive)
        assert bundle.views["week"]["poll"][0]["gap"] is None
        json.dumps(bundle.views["week"], allow_nan=False)  # must not raise


class TestBothSurfaces:
    def test_hindsight_lands_in_ratings_at_window_99(self, out: Path, archive: Path) -> None:
        """Report 02 §3.6: publish both surfaces. K = N is live, K = 99 is
        hindsight, and the Δ column reads the difference."""
        rows = serving.build(out, archive=archive).tables["cfb_ratings"]
        windows = {r["data_window"] for r in rows}
        assert windows == {2, 99}

    def test_rank_delta_is_carried_onto_the_view(self, out: Path, archive: Path) -> None:
        view = serving.build(out, archive=archive).views["week"]["poll"]
        assert view[0]["rank_delta"] == -1
        assert view[0]["hindsight_rank"] == 2


class TestDivergence:
    def test_mean_and_max_absolute_delta(self, out: Path, archive: Path) -> None:
        row = serving.build(out, archive=archive).tables["cfb_divergence"][0]
        assert row["mean_abs_delta"] == pytest.approx((1 + 2 + 1) / 3)
        assert row["max_abs_delta"] == 2


class TestSectionExtraction:
    def test_a_wrapper_heading_keeps_its_subsections(self) -> None:
        """ADR 0007's "The two uncomfortable results" is a `##` whose entire body
        is two `###` subsections. Publishing it as empty would be the worst
        possible failure for a block whose job is to carry recorded doubts."""
        markdown = "## Wrapper\n\n### One\n\nbody one\n\n### Two\n\nbody two\n\n## Next\n\nafter\n"
        body = serving._extract_section(markdown, "Wrapper")
        assert body is not None
        assert "body one" in body and "body two" in body and "after" not in body

    def test_a_missing_heading_returns_none(self) -> None:
        assert serving._extract_section("## Something\n\nbody\n", "Absent") is None


class TestFixtures:
    def test_export_writes_the_four_documents_and_the_index(
        self, out: Path, archive: Path, tmp_path: Path
    ) -> None:
        dest = tmp_path / "data"
        written = fixtures.export(out, dest, archive=archive)
        names = {p.name for p in written}
        wanted = {"week-02.json", "connectivity-02.json", "methodology-02.json", "data-02.json"}
        assert wanted <= names
        assert (dest / "index.json").exists()

    def test_export_is_idempotent(self, out: Path, archive: Path, tmp_path: Path) -> None:
        dest = tmp_path / "data"
        fixtures.export(out, dest, archive=archive)
        first = (dest / "2023" / "week-02.json").read_text()
        fixtures.export(out, dest, archive=archive)
        assert (dest / "2023" / "week-02.json").read_text() == first

    def test_the_index_marks_unplayed_weeks(self, out: Path, archive: Path, tmp_path: Path) -> None:
        """§2.2: weeks not yet played are dimmed and unclickable, not hidden.
        Seeing the empty right-hand side of the strip is part of the narrative."""
        dest = tmp_path / "data"
        fixtures.export(out, dest, archive=archive)
        index = json.loads((dest / "index.json").read_text())
        weeks = {w["week"]: w for w in index["seasons"][0]["weeks"]}
        assert weeks[2]["played"] is True
        assert weeks[1]["played"] is False
        assert weeks[1]["n_ranked"] == 0

    def test_a_projection_only_season_is_indexed_with_every_week_unplayed(
        self, out: Path, archive: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A season with a projection and no poll gets a strip of unplayed weeks.

        `cfbpoll projection publish` writes `<season>/projection.json` for a season
        that has not kicked off, so a digit-named directory with no `week-*.json`
        in it is a normal state of this tree once both products ship. It used to be
        skipped outright, because the site read the current season as
        `max(seasons[].season)` and its current week as the last PLAYED one, so a
        2026 entry made the front door resolve a season it could find no poll for
        and 404.

        THAT GUARD MOVED TO THE SITE, where it belongs, and this is the half that
        pays for it: report 05 §2.2 wants the unplayed right-hand side of the strip
        visible from day one, and a season indexed nowhere has no strip to dim. If
        the 404 ever comes back, check `frontDoorBoards` first and this second.
        """
        monkeypatch.setattr(serving, "scheduled_weeks", lambda season, arch: [1, 2, 3])
        dest = tmp_path / "data"
        fixtures.export(out, dest, archive=archive)
        (dest / "2026").mkdir()
        (dest / "2026" / "projection.json").write_text('{"season": 2026}\n', encoding="utf-8")

        fixtures.rebuild_index(dest, archive=archive)
        index = json.loads((dest / "index.json").read_text())

        assert [s["season"] for s in index["seasons"]] == [2023, 2026]
        entry = next(s for s in index["seasons"] if s["season"] == 2026)
        assert [w["week"] for w in entry["weeks"]] == [1, 2, 3]
        assert all(w["played"] is False for w in entry["weeks"])
        assert all(w["n_ranked"] == 0 for w in entry["weeks"])
        assert all(w["published_at"] is None for w in entry["weeks"])
        # No lens has ever been computed for a season with no games in it.
        assert entry["recipes"] == []
        # And no empty curve left behind for a season with nothing to diverge.
        assert not (dest / "2026" / "divergence.json").exists()
        # `generated_at` is the newest PUBLICATION; a season of unplayed weeks
        # contributes none and must not blank it.
        assert index["generated_at"] is not None

    def test_a_bare_digit_directory_with_neither_poll_nor_projection_is_not_indexed(
        self, out: Path, archive: Path, tmp_path: Path
    ) -> None:
        """Relaxing the guard must not turn any digit-named directory into a season."""
        dest = tmp_path / "data"
        fixtures.export(out, dest, archive=archive)
        (dest / "2031").mkdir()
        fixtures.rebuild_index(dest, archive=archive)
        index = json.loads((dest / "index.json").read_text())
        assert [s["season"] for s in index["seasons"]] == [2023]

    def test_the_unplayed_week_stub_has_one_definition(self) -> None:
        """The strip must describe an unplayed week identically either way it is
        built: as the tail of a season in progress, or as the whole of one that has
        not started."""
        from_merge = serving.merge_season_index(
            [], {"season": 2026, "week": 1, "played": True}, [1, 2], headline_start=5
        )
        unplayed = next(w for w in from_merge if w["week"] == 2)
        assert unplayed == serving.unplayed_week(2026, 2, 5)

    def test_the_schema_version_is_stamped(self, out: Path, archive: Path, tmp_path: Path) -> None:
        dest = tmp_path / "data"
        fixtures.export(out, dest, archive=archive)
        index = json.loads((dest / "index.json").read_text())
        assert index["schema_version"] == fixtures.SCHEMA_VERSION

    def test_documents_are_stable_json(self, out: Path, archive: Path, tmp_path: Path) -> None:
        """Sorted keys and a trailing newline, same rule as publish/files.py: the
        bytes must be a pure function of the computation so a fixture set diffs."""
        dest = tmp_path / "data"
        fixtures.export(out, dest, archive=archive)
        text = (dest / "2023" / "week-02.json").read_text()
        assert text.endswith("\n")
        assert json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n" == text


class TestPostgres:
    def test_load_is_a_no_op_without_a_database(
        self, out: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fork has no database and must still produce a ranking. Skipping is a
        success, not an error."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("POSTGRES_URL", raising=False)
        assert postgres.load(out) == {}

    def test_every_serving_table_has_a_conflict_rule(self) -> None:
        for table in postgres.UPSERTS:
            assert table in postgres._CONFLICT, table

    def test_the_publication_record_is_append_only(self, out: Path, archive: Path) -> None:
        """cfb_poll_published: never UPDATE, never DELETE. The first publication
        of a (season, week, rank) wins forever."""
        bundle = serving.build(out, archive=archive)
        plan = dict(zip(postgres.tables_present(bundle), postgres.statements(bundle), strict=True))
        sql = plan["cfb_poll_published"][0]
        assert "ON CONFLICT (season, week, rank) DO NOTHING" in sql
        assert "DO UPDATE" not in sql

    def test_mutable_tables_upsert(self, out: Path, archive: Path) -> None:
        bundle = serving.build(out, archive=archive)
        plan = dict(zip(postgres.tables_present(bundle), postgres.statements(bundle), strict=True))
        assert "DO UPDATE SET" in plan["cfb_runs"][0]
        assert "DO UPDATE SET" in plan["cfb_ratings"][0]

    def test_tables_are_written_in_foreign_key_order(self, out: Path, archive: Path) -> None:
        bundle = serving.build(out, archive=archive)
        order = postgres.tables_present(bundle)
        assert order.index("cfb_runs") < order.index("cfb_model_params")
        assert order.index("cfb_runs") < order.index("cfb_poll_published")
        assert order.index("cfb_runs") < order.index("cfb_ratings")

    def test_json_columns_are_serialised(self, out: Path, archive: Path) -> None:
        bundle = serving.build(out, archive=archive)
        plan = dict(zip(postgres.tables_present(bundle), postgres.statements(bundle), strict=True))
        _, params = plan["cfb_views"]
        payload = params[0][postgres_column_index(bundle, "cfb_views", "payload")]
        assert isinstance(payload, str)
        assert json.loads(payload)["week"] == 2

    def test_the_ddl_covers_every_serving_table(self) -> None:
        ddl = " ".join(postgres.DDL)
        for table in serving.SERVING_TABLES:
            assert f"CREATE TABLE IF NOT EXISTS {table}" in ddl, table

    def test_the_ddl_is_rerunnable(self) -> None:
        """`publish postgres` must be safe against an established database."""
        for statement in postgres.DDL:
            assert "IF NOT EXISTS" in statement


def postgres_column_index(bundle: Any, table: str, column: str) -> int:
    """Where `column` lands in the parameter tuple. Columns are sorted by name."""
    return sorted(bundle.tables[table][0]).index(column)


class TestParity:
    """The two backends must be able to answer the same questions. If a document
    exists in the fixture set with no table behind it, the Postgres surface has a
    hole in it and a page will render against one backend and not the other."""

    def test_every_view_has_a_table_behind_it(self, out: Path, archive: Path) -> None:
        bundle = serving.build(out, archive=archive)
        assert set(bundle.views) == set(serving.VIEW_KINDS)
        stored = {row["kind"]: row["payload"] for row in bundle.tables["cfb_views"]}
        assert stored == bundle.views
        assert bundle.tables["cfb_artifacts"]
        assert bundle.tables["cfb_divergence"]

    def test_the_view_kinds_match_the_fixture_filenames(self) -> None:
        """The same string is the fixture filename stem, the `kind` in cfb_views
        and the method name on the site's PollSource interface. Deliberately."""
        assert set(fixtures.DOCUMENTS) == set(serving.VIEW_KINDS)

    def test_the_season_index_merge_is_shared_and_idempotent(self) -> None:
        """Both backends fold weeks in with the same function, so the strip cannot
        differ between them, and publishing week 12 before week 3 is harmless."""
        stub = {
            "season": 2023, "week": 3, "season_type": "regular", "provisional": True,
            "played": True, "published_at": "x", "n_ranked": 133,
        }
        once = serving.merge_season_index([], stub, [1, 2, 3, 4], 5)
        twice = serving.merge_season_index(once, stub, [1, 2, 3, 4], 5)
        assert once == twice
        assert [w["week"] for w in once] == [1, 2, 3, 4]
        assert [w["played"] for w in once] == [False, False, True, False]


class TestLogos:
    """Report 06: hotlink only, never possess the bytes, and make the whole thing
    reversible with one flag."""

    DISPLAY = {
        "logos": True,
        "logo_url_template": (
            "https://a.espncdn.com/combiner/i?img=/i/teamlogos/ncaa/500{variant}/"
            "{team_id}.png&w={size}&h={size}"
        ),
        "logo_size": 64,
        "logo_size_2x": 128,
        "logo_dark_variant": "-dark",
    }

    def test_all_four_variants_are_published(self, archive: Path) -> None:
        """The site never computes, and that includes building a string."""
        row = serving.team_dimension(2023, archive, self.DISPLAY)["Ohio State"]
        assert row["logo_url"].endswith("500/194.png&w=64&h=64")
        assert row["logo_url_2x"].endswith("500/194.png&w=128&h=128")
        assert row["logo_url_dark"].endswith("500-dark/194.png&w=64&h=64")
        assert row["logo_url_dark_2x"].endswith("500-dark/194.png&w=128&h=128")

    def test_every_url_is_https(self, archive: Path) -> None:
        """CFBD's own logos[] field mixes http and https, which silently breaks
        ~40% of logos through mixed-content blocking. Building the string from an
        integer means the scheme is ours and the bug cannot happen."""
        row = serving.team_dimension(2023, archive, self.DISPLAY)["Ohio State"]
        for key in ("logo_url", "logo_url_2x", "logo_url_dark", "logo_url_dark_2x"):
            assert row[key].startswith("https://")

    def test_an_unresolved_team_gets_no_url_rather_than_an_error(self, archive: Path) -> None:
        """A name-matching failure must not break a Sunday build; it must produce
        a team that renders the generated mark."""
        row = serving.team_dimension(2023, archive, self.DISPLAY)["Akron"]
        assert row["espn_team_id"] is None
        assert row["logo_url"] is None
        assert row["team_id"] == 2005  # still a real team, still ranked

    def test_the_flag_turns_every_logo_off(self, archive: Path) -> None:
        """Rule 5: the logo-free mode is a config change, not a weekend."""
        row = serving.team_dimension(2023, archive, {**self.DISPLAY, "logos": False})
        assert row["Ohio State"]["logo_url"] is None
        assert row["Ohio State"]["logo_url_dark_2x"] is None
        assert row["Ohio State"]["espn_team_id"] == 194  # the id is still the record

    def test_the_live_config_carries_the_display_block(self) -> None:
        from cfbpoll.config import DEFAULT_CONFIG_PATH, load_config

        display = load_config(DEFAULT_CONFIG_PATH)["display"]
        assert display["logos"] is True
        assert "a.espncdn.com" in display["logo_url_template"]

    def test_the_trademark_disclaimer_is_published(self) -> None:
        """It is not a credit — no aggregator can grant these rights, and naming
        one would advertise a source that disclaims the ability to. It is a
        disclaimer, and it is doing real work."""
        body = " ".join(entry["body"] for entry in serving._licenses())
        assert "trademarks of their respective institutions" in body
        assert "identification only" in body
        assert "not affiliated with, endorsed by, or sponsored by" in body
        assert "no logo files are hosted or redistributed" in body

    def test_no_aggregator_is_credited(self) -> None:
        text = " ".join(entry["body"] + entry["name"] for entry in serving._licenses()).lower()
        for forbidden in ("sports logo history", "sportslogos.net", "powered by espn"):
            assert forbidden not in text

    def test_the_package_never_fetches_a_logo(self) -> None:
        """RULE 1, made mechanical (report 06 §8.4). A rule that depends on
        everyone remembering it is not a rule. The CDN host may appear in this
        package only as a URL template that is handed to a browser — never as
        something our own code retrieves."""
        import cfbpoll

        root = Path(cfbpoll.__file__).parent
        offenders: list[str] = []
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "espncdn" not in text:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if "espncdn" not in line:
                    continue
                verbs = ("httpx", "requests", "urlopen", "get(", "download")
                if any(verb in line for verb in verbs):
                    offenders.append(f"{path.name}:{number}")
        assert offenders == [], f"a logo fetch reached the package: {offenders}"

    def test_no_image_bytes_are_committed_to_the_package(self) -> None:
        import cfbpoll

        root = Path(cfbpoll.__file__).parent
        images = [
            p.name
            for suffix in ("*.png", "*.svg", "*.webp", "*.jpg", "*.gif")
            for p in root.rglob(suffix)
        ]
        assert images == [], f"image assets in the package: {images}"


class TestRunDirectoryContract:
    """The guard that turns a stale `out/` into a sentence instead of a stack trace.

    THE DEFECT THIS EXISTS FOR. `publish fixtures` defaults to `--from out`, and
    `out/` is gitignored regenerable scratch, so a working copy routinely holds a
    directory written by an older checkout. One did: a pre-L3 run whose
    `ratings_live.parquet` carried `rating` and no `power`. `build` read it, six
    frames later polars raised `ColumnNotFoundError: unable to find column
    "power"`, and nothing in the suite covered the default invocation because
    every test and every session command passed an explicit `--from`.
    """

    def _stale(self, out: Path) -> Path:
        """The exact shape that failed: valid files, pre-L3 rating schema."""
        pl.DataFrame(
            {
                "team": ["Ohio State", "Alabama", "Akron"],
                "team_class": ["fbs"] * 3,
                "rating": [28.1, 20.0, -5.0],
                "wins": [9, 8, 2],
                "losses": [0, 1, 7],
            }
        ).write_parquet(out / "ratings_live.parquet")
        return out

    def test_a_pre_l3_run_directory_is_refused_with_an_actionable_message(
        self, out: Path
    ) -> None:
        self._stale(out)
        with pytest.raises(serving.StaleRunError) as caught:
            serving.check_run_directory(out)
        message = str(caught.value)
        assert "power" in message and "resume" in message
        assert "cfbpoll rank" in message, "the message must say what to run"
        assert "2023" in message and "--through-week 2" in message

    def test_build_refuses_before_polars_ever_sees_the_frame(self, out: Path) -> None:
        """The failure must not surface as a ColumnNotFoundError again."""
        self._stale(out)
        with pytest.raises(serving.StaleRunError):
            serving.build(out)

    def test_export_refuses_the_same_way(self, out: Path, tmp_path: Path) -> None:
        self._stale(out)
        with pytest.raises(serving.StaleRunError):
            fixtures.export(out, tmp_path / "data")

    def test_a_missing_file_names_the_file(self, out: Path) -> None:
        (out / "model_params.json").unlink()
        with pytest.raises(serving.StaleRunError, match="model_params.json"):
            serving.check_run_directory(out)

    def test_a_directory_that_is_not_there_at_all(self, tmp_path: Path) -> None:
        with pytest.raises(serving.StaleRunError, match="not a directory"):
            serving.check_run_directory(tmp_path / "nope")

    def test_a_current_run_passes(self, out: Path) -> None:
        assert serving.check_run_directory(out) is None


class TestSeasonWideExport:
    """`--from` takes a directory of runs, which is how the site's tree is made.

    THE SECOND HALF OF THE SAME DEFECT. `export` publishes ONE week; the site
    reads a whole season; so the published tree was regenerated by hand-looping a
    shell over fifteen run directories. That procedure lived in a terminal
    history, which meant it could not be reviewed, could not be repeated, and
    gave nobody a way to notice when it was skipped — and it was skipped, leaving
    the site serving a fixture set with none of the fields the pipeline had
    started publishing.
    """

    def _season(self, out: Path, tmp_path: Path, weeks: tuple[int, ...]) -> Path:
        root = tmp_path / "runs"
        root.mkdir()
        for week in weeks:
            run = root / f"w{week:02d}"
            run.mkdir()
            for name in ("poll.json", "model_params.json", "_run.json"):
                payload = json.loads((out / name).read_text())
                if name == "poll.json":
                    payload["through"]["week"] = week
                if name == "_run.json":
                    payload["through_week"] = week
                (run / name).write_text(json.dumps(payload))
            (run / "ratings_live.parquet").write_bytes(
                (out / "ratings_live.parquet").read_bytes()
            )
        return root

    def test_one_run_directory_is_still_one_run(self, out: Path) -> None:
        assert fixtures.run_directories(out) == [out]

    def test_a_directory_of_runs_is_found_and_ordered_by_week(
        self, out: Path, tmp_path: Path
    ) -> None:
        root = self._season(out, tmp_path, (3, 1, 2))
        assert [p.name for p in fixtures.run_directories(root)] == ["w01", "w02", "w03"]

    def test_neither_is_refused(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(serving.StaleRunError, match="neither a run directory"):
            fixtures.run_directories(empty)

    def test_export_all_publishes_every_week_and_one_index(
        self, out: Path, archive: Path, tmp_path: Path
    ) -> None:
        # Weeks 1 and 2 only: the test archive's schedule holds two weeks, and a
        # run for a week with no games is not a thing `rank` can produce.
        root = self._season(out, tmp_path, (1, 2))
        dest = tmp_path / "data"
        written = fixtures.export_all(root, dest, archive=archive)
        for week in (1, 2):
            for stem in ("week", "connectivity", "methodology", "data"):
                assert (dest / "2023" / f"{stem}-{week:02d}.json").exists()
        assert sum(1 for p in written if p.name == "index.json") == 1
        index = json.loads((dest / "index.json").read_text())
        played = [w for w in index["seasons"][0]["weeks"] if w["played"]]
        assert [w["week"] for w in played] == [1, 2]

    def test_export_all_is_idempotent(self, out: Path, archive: Path, tmp_path: Path) -> None:
        root = self._season(out, tmp_path, (1, 2))
        dest = tmp_path / "data"
        fixtures.export_all(root, dest, archive=archive)
        before = {p: p.read_bytes() for p in sorted(dest.rglob("*.json"))}
        fixtures.export_all(root, dest, archive=archive)
        assert {p: p.read_bytes() for p in sorted(dest.rglob("*.json"))} == before


class TestPublishedMarksReachTheDocuments:
    """The assertion whose absence let a mark-less fixture tree ship.

    `tests/unit/test_team_marks.py` checks `team_dimension`, which is upstream of
    the documents. Nothing checked the bytes the SITE reads, so the pipeline could
    publish marks into a dataclass and write JSON without them and every test
    stayed green. These assert the emitted document.
    """

    def test_every_poll_row_in_the_written_week_document_carries_a_mark(
        self, out: Path, archive: Path, tmp_path: Path
    ) -> None:
        dest = tmp_path / "data"
        fixtures.export(out, dest, archive=archive)
        payload = json.loads((dest / "2023" / "week-02.json").read_text())
        assert payload["poll"]
        for row in payload["poll"]:
            for field in ("mark_bg", "mark_fg", "mark_label"):
                assert row.get(field), (row["team"], field)
            assert row["mark_bg"].startswith("#") and len(row["mark_bg"]) == 7
            assert row["mark_fg"].startswith("#") and len(row["mark_fg"]) == 7

    def test_the_teams_table_carries_the_same_marks(self, out: Path, archive: Path) -> None:
        bundle = serving.build(out, archive=archive)
        by_name = {row["school"]: row for row in bundle.tables["cfb_teams"]}
        for row in bundle.views["week"]["poll"]:
            dim = by_name[row["team"]]
            assert (row["mark_bg"], row["mark_fg"]) == (dim["mark_bg"], dim["mark_fg"])

    def test_a_team_with_no_crosswalk_id_still_gets_a_mark(
        self, out: Path, archive: Path
    ) -> None:
        """Akron is absent from the test crosswalk: no logo, mark regardless."""
        bundle = serving.build(out, archive=archive)
        akron = next(r for r in bundle.views["week"]["poll"] if r["team"] == "Akron")
        assert akron["logo_url"] is None
        assert akron["mark_bg"] and akron["mark_fg"] and akron["mark_label"]


class TestSchemaCoversWhatTheBuilderEmits:
    """Every column the builder emits must exist in the DDL. No database needed.

    THE SAME DEFECT AS THE OTHERS, one layer down. `postgres.load` builds its
    INSERT from `sorted(rows[0])` — literally every key of the dict `serving`
    produced — so adding a field to a serving row silently adds a column name to
    an INSERT statement. Adding `mark_bg` to `cfb_teams` without touching the DDL
    would have shipped a loader that fails on the first live run with
    `column "mark_bg" of relation "cfb_teams" does not exist`, and nothing would
    have caught it because the Postgres path has no live database in CI.

    This test needs none. It parses the column names out of the DDL and compares
    them against the keys the builder actually produced.
    """

    def _declared(self, table: str) -> set[str]:
        create = next(
            stmt for stmt in postgres.DDL if f"CREATE TABLE IF NOT EXISTS {table} (" in stmt
        )
        body = create.split("(", 1)[1].rsplit(")", 1)[0]
        names: set[str] = set()
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("--"):
                continue
            head = line.split()[0]
            if head.upper() in {"PRIMARY", "FOREIGN", "UNIQUE", "CONSTRAINT", "CHECK"}:
                continue
            names.add(head.strip(","))
        for stmt in postgres.DDL:
            marker = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
            if stmt.startswith(marker):
                names.add(stmt[len(marker) :].split()[0])
        return names

    def test_cfb_teams_declares_every_key_the_builder_emits(
        self, out: Path, archive: Path
    ) -> None:
        bundle = serving.build(out, archive=archive)
        emitted = set(bundle.tables["cfb_teams"][0])
        missing = emitted - self._declared("cfb_teams")
        assert missing == set(), f"cfb_teams rows carry columns the DDL lacks: {sorted(missing)}"

    def test_the_mark_columns_are_declared_and_updatable(self) -> None:
        declared = self._declared("cfb_teams")
        updatable = set(postgres._CONFLICT["cfb_teams"][1])
        for column in ("mark_bg", "mark_fg", "mark_label", "team_color", "team_alt_color"):
            assert column in declared, column
            # An upsert that does not update a column means a rebrand never
            # reaches an established database.
            assert column in updatable, column

    @pytest.mark.parametrize("table", ["cfb_teams", "cfb_games", "cfb_runs"])
    def test_every_built_table_matches_its_schema(
        self, out: Path, archive: Path, table: str
    ) -> None:
        bundle = serving.build(out, archive=archive)
        rows = bundle.tables.get(table) or []
        if not rows:
            pytest.skip(f"{table} is empty for this fixture")
        missing = set(rows[0]) - self._declared(table)
        assert missing == set(), f"{table}: {sorted(missing)}"


class TestScheduledWeeks:
    """Where the week strip's cells come from, and why there are two sources."""

    def test_the_parquet_is_preferred_whenever_it_has_anything(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No played season may change its week list because of the fallback."""
        monkeypatch.setattr(
            "cfbpoll.ingest.sportsdataverse.canonical_games",
            lambda seasons, arch: pl.DataFrame(
                {"season_type": ["regular"] * 3 + ["postseason"], "week": [1, 2, 3, 1]}
            ),
        )
        monkeypatch.setattr(
            "cfbpoll.projection.forward.schedule",
            lambda season, *a, **k: pytest.fail("the parquet had weeks; do not fall back"),
        )
        assert serving.scheduled_weeks(2023, None) == [1, 2, 3]

    def test_a_season_with_no_parquet_resolves_its_schedule_from_the_cfbd_pull(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE 2026 CASE. The sportsdataverse parquet is the archive of PLAYED
        football and does not exist for a season in the future, so a projection-only
        season had zero scheduled weeks and its strip rendered no cells - while the
        projection sitting in the same directory had been built from a schedule the
        archive plainly held, as the CFBD `/games` pull."""
        monkeypatch.setattr(
            "cfbpoll.ingest.sportsdataverse.canonical_games",
            lambda seasons, arch: (_ for _ in ()).throw(FileNotFoundError("no parquet")),
        )
        monkeypatch.setattr(
            "cfbpoll.projection.forward.schedule",
            lambda season, *a, **k: pl.DataFrame({"week": [1, 2, 3, 12]}),
        )
        assert serving.scheduled_weeks(2026, None) == [1, 2, 3, 12]

    def test_no_schedule_anywhere_is_an_empty_list_not_an_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fixture set shipped without an archive still indexes."""
        monkeypatch.setattr(
            "cfbpoll.ingest.sportsdataverse.canonical_games",
            lambda seasons, arch: (_ for _ in ()).throw(FileNotFoundError("no parquet")),
        )
        monkeypatch.setattr(
            "cfbpoll.projection.forward.schedule",
            lambda season, *a, **k: pl.DataFrame({"week": []}, schema={"week": pl.Int32}),
        )
        assert serving.scheduled_weeks(2026, None) == []

    @pytest.mark.skipif(
        not (SDV_ARCHIVE / "schedules").exists(), reason="local archive not materialised"
    )
    def test_the_real_2026_schedule_resolves_to_a_non_empty_strip(self) -> None:
        """The integration half: against the archive actually on disk, 2026 has
        weeks. Deliberately not asserting WHICH weeks - the 2026 pull is a future
        schedule and will fill in - only that the strip is no longer empty."""
        weeks = serving.scheduled_weeks(2026, None)
        assert weeks
        assert min(weeks) == 1
