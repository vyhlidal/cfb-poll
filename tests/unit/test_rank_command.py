"""`cfbpoll rank` end to end, against the real archive.

Asserts the file list report 03 §5.3 fixes, the honesty of the labelling (an
L2-only build must not present itself as the L4 headline poll), and that the
published numbers are the ones the fit produced.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from cfbpoll.cli import app
from cfbpoll.config import load_config
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games
from cfbpoll.model import l2_results
from cfbpoll.publish import files
from cfbpoll.publish import poll as poll_mod

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(),
    reason="local archive not materialised",
)


@pytest.fixture(scope="module")
def ranked(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("rank")
    result = runner.invoke(
        app, ["rank", "--season", "2023", "--through-week", "10", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    return out


def test_writes_the_documented_file_set(ranked: Path) -> None:
    got = {p.name for p in ranked.iterdir()}
    assert got == set(files.L2_OUTPUTS)


def test_output_labels_itself_l2_only(ranked: Path) -> None:
    """No fabricated capability: the config's headline layer is L4 and this is not it."""
    params = json.loads((ranked / "model_params.json").read_text())
    assert params["layer"] == "L2 results core"
    assert params["version"] == "v0"
    assert params["layers_implemented"] == ["L2"]
    assert params["headline_layer_when_complete"] == "L4_resume"
    assert params["provisional"] is False  # week 10 >= headline_start_week


def test_params_carry_every_published_constant(ranked: Path) -> None:
    params = json.loads((ranked / "model_params.json").read_text())
    cfg = load_config()
    assert params["beta_w"] == cfg["margin"]["beta_w"]
    assert params["C"] == cfg["margin"]["c"]
    assert params["lambda"] in cfg["ridge"]["l2_grid"]
    assert params["cv"]["grid"] == sorted(float(x) for x in cfg["ridge"]["l2_grid"])
    assert params["weight_bowl_non_cfp"] == cfg["weights"]["bowl_non_cfp"]


def test_run_record_is_traceable(ranked: Path) -> None:
    run = json.loads((ranked / "_run.json").read_text())
    assert run["season"] == 2023 and run["through_week"] == 10
    assert len(run["config_hash"]) == 64
    assert run["n_games_in_fit"] > 1000


def test_poll_ranks_fbs_only_and_ratings_keep_everyone(ranked: Path) -> None:
    poll = pl.read_csv(ranked / "poll.csv")
    ratings = pl.read_parquet(ranked / "ratings_live.parquet")
    assert set(poll["team_class"].unique().to_list()) == {"fbs"}
    assert "fcs" in set(ratings["team_class"].unique().to_list())
    assert ratings.height > poll.height
    assert poll["rank"].to_list() == list(range(1, poll.height + 1))


def test_published_numbers_match_a_direct_fit(ranked: Path) -> None:
    games = load_games([2023], universe="model")
    fit = l2_results.fit(games, load_config(), through=(2023, "regular", 10))
    poll = pl.read_csv(ranked / "poll.csv")
    top = poll.row(0, named=True)
    assert top["rating"] == pytest.approx(fit.ratings[top["team"]], abs=1e-9)
    assert top["team"] == "Ohio State"


def test_top25_is_football_reality(ranked: Path) -> None:
    poll = pl.read_csv(ranked / "poll.csv")
    top10 = set(poll.head(10)["team"].to_list())
    assert {"Ohio State", "Michigan", "Georgia", "Florida State", "Washington"} <= top10
    # The anti-nonsense clause: nobody outside the plausible set in the top 5.
    assert poll.head(5)["wins"].min() >= 8


def test_provisional_weeks_are_labelled(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["rank", "--season", "2023", "--through-week", "3", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "PROVISIONAL" in result.output
    params = json.loads((tmp_path / "model_params.json").read_text())
    assert params["provisional"] is True
    assert params["provisional_label"] == load_config()["publication"]["provisional_label"]


def test_rank_is_reproducible(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    for out in (first, second):
        assert (
            runner.invoke(
                app, ["rank", "--season", "2022", "--through-week", "8", "--out", str(out)]
            ).exit_code
            == 0
        )
    a = files.canonicalize(first, first / "canonical.csv").read_text()
    b = files.canonicalize(second, second / "canonical.csv").read_text()
    assert a == b


def test_publication_status_follows_the_config() -> None:
    cfg = load_config()
    start = int(cfg["publication"]["headline_start_week"])
    assert poll_mod.publication_status(start - 1, cfg)[0] is True
    assert poll_mod.publication_status(start, cfg)[0] is False
