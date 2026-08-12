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
    def test_reads_ids_conferences_and_logos(self, archive: Path) -> None:
        teams = serving.team_dimension(2023, archive)
        assert teams["Ohio State"]["team_id"] == 194
        assert teams["Ohio State"]["conference"] == "Big Ten"
        assert teams["Ohio State"]["logo_url"].endswith("/194.png")

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
        _, params = plan["cfb_connectivity"]
        payload = params[0][postgres_column_index(bundle, "cfb_connectivity", "payload")]
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
        assert set(bundle.views) == {"week", "connectivity", "methodology", "data"}
        assert bundle.tables["cfb_connectivity"]
        assert bundle.tables["cfb_artifacts"]
        assert bundle.tables["cfb_divergence"]

    def test_the_connectivity_document_is_stored_whole(self, out: Path, archive: Path) -> None:
        bundle = serving.build(out, archive=archive)
        assert bundle.tables["cfb_connectivity"][0]["payload"] == bundle.views["connectivity"]
