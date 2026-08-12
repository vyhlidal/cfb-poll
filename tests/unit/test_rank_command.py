"""`cfbpoll rank` end to end, against the real archive.

Asserts the file list report 03 §5.3 fixes, the honesty of the labelling (the
headline is the résumé but opponent quality is still L2, and every artifact must
say so), and that the published numbers are the ones the fit produced.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from cfbpoll.cli import app
from cfbpoll.config import load_config
from cfbpoll.ingest import windows
from cfbpoll.ingest.plays import load_plays
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE, load_games
from cfbpoll.model import l4_resume, retro
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
    assert got == set(files.RANK_OUTPUTS)


def test_the_headline_is_the_resume_and_the_power_source_is_declared(ranked: Path) -> None:
    """Report 02 §3.5 makes the résumé the poll. Report 02 §3.4 reads opponent
    quality off L3, which now exists - so Power is the blend, and no artifact is
    allowed to be coy about which one produced it.

    ADAPTED when L1/L3 landed: this test previously asserted power_source == "L2"
    and layers_missing == ["L1", "L3", "bootstrap"], which were true statements
    about a build in which those layers were scaffolds. They are not scaffolds
    now. The shape of the assertion - every artifact declares its Power source -
    is unchanged, and that is the part that was ever load-bearing."""
    params = json.loads((ranked / "model_params.json").read_text())
    assert params["layer"] == "L4 resume rating"
    assert params["version"] == "v0"
    assert params["headline_layer"] == "L4_resume"
    assert params["layers_implemented"] == ["L1", "L2", "L3", "L4"]
    assert params["layers_missing"] == ["bootstrap"]
    assert params["power_source"] == "L3"
    assert params["power_version"] == "v1"
    assert params["provisional"] is False  # week 10 >= headline_start_week
    # report 02 §3.3: w1, w2 and k are published EVERY week
    assert params["w1_efficiency"] > 0.0
    assert params["w2_results"] > 0.0
    assert 55.0 < params["k_points_per_unit"] < 85.0
    assert params["blend_weight_source"] == "out_of_sample"

    poll = json.loads((ranked / "poll.json").read_text())
    assert poll["power_source"] == "L3" and poll["power_version"] == "v1"
    assert poll["hindsight_variant"] == retro.HINDSIGHT_VARIANT


def test_params_carry_every_published_constant(ranked: Path) -> None:
    """Both layers' constants, in one file, every week (constraint 5)."""
    params = json.loads((ranked / "model_params.json").read_text())
    cfg = load_config()
    assert params["beta_w"] == cfg["margin"]["beta_w"]
    assert params["C"] == cfg["margin"]["c"]
    assert params["lambda"] in cfg["ridge"]["l2_grid"]
    assert params["cv"]["grid"] == sorted(float(x) for x in cfg["ridge"]["l2_grid"])
    assert params["weight_bowl_non_cfp"] == cfg["weights"]["bowl_non_cfp"]
    assert params["sigma"] == cfg["resume"]["sigma"]
    assert params["q_bounds"] == cfg["resume"]["q_bounds"]
    assert params["saturation_tiebreak"] == cfg["resume"]["saturation_tiebreak"]
    # The units bridge, published rather than implicit. With Power = L3 there is
    # nothing to rescale - the blend regression's response IS actual margin - so
    # the scale is exactly 1.0 and the home field is the blend's own h.
    assert params["power_scale_b"] == 1.0
    assert params["power_home_field_points"] > 0.0


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


def test_power_and_the_gap_are_beside_every_team(ranked: Path) -> None:
    """report 02 §3.5: the power number is never hidden, and the gap is the answer
    to both of the two commonest complaints about a computer poll."""
    poll = pl.read_csv(ranked / "poll.csv")
    assert list(poll.columns) == list(poll_mod.HEADLINE_COLUMNS)
    assert poll["power"].null_count() == 0
    assert (poll["gap"] - (poll["resume"] - poll["power"])).abs().max() < 1e-9


def test_both_surfaces_are_published(ranked: Path) -> None:
    """Live R(N,N) and hindsight R(N,final), in the files and in the poll table."""
    live = pl.read_parquet(ranked / "ratings_live.parquet")
    hindsight = pl.read_parquet(ranked / "ratings_hindsight.parquet")
    assert live["is_live"].all()
    assert hindsight["is_hindsight"].all()
    assert live["data_label"].unique().to_list() != hindsight["data_label"].unique().to_list()
    # the résumé window is the SAME for both: frozen form (report 02 §3.6 A)
    assert live["eval_label"].unique().to_list() == hindsight["eval_label"].unique().to_list()
    assert live.sort("team")["wins"].to_list() == hindsight.sort("team")["wins"].to_list()

    poll = pl.read_csv(ranked / "poll.csv")
    assert poll["resume_hindsight"].null_count() == 0
    assert (poll["rank_delta"] - (poll["rank"] - poll["rank_hindsight"])).abs().max() == 0


def test_published_numbers_match_a_direct_fit(ranked: Path) -> None:
    """The published number reproduces from the library, not just from the CLI.

    ADAPTED when L3 landed: the direct fit now has to walk the season forward to
    get the same out-of-sample blend weights the CLI used, because that is what
    "the Power rating live at week 10" means (report 02 §3.3). Fitting the blend
    on the week-10 window instead would be in-sample and would not - and should
    not - reproduce."""
    cfg = load_config()
    games = load_games([2023], universe="model")
    plays = load_plays([2023])
    buckets = windows.season_buckets(games, 2023)
    evaluated = next(b for b in buckets if b.season_type == "regular" and b.week == 10)
    powers = retro.season_power(games, 2023, cfg, plays=plays, buckets=buckets)
    window = windows.games_through(games, season=2023, week=10, season_type="regular")
    fitted = l4_resume.fit(window, cfg, power=powers[evaluated.order])
    poll = pl.read_csv(ranked / "poll.csv")
    top = poll.row(0, named=True)
    assert top["resume"] == pytest.approx(fitted.resume[top["team"]], abs=1e-9)
    assert top["power"] == pytest.approx(fitted.power.rating(top["team"]), abs=1e-9)
    assert top["team"] == "Michigan"


def test_top25_is_football_reality(ranked: Path) -> None:
    poll = pl.read_csv(ranked / "poll.csv")
    top10 = set(poll.head(10)["team"].to_list())
    assert {"Michigan", "Ohio State", "Georgia", "Florida State", "Washington"} <= top10
    # The anti-nonsense clause: nobody outside the plausible set in the top 5.
    assert poll.head(5)["wins"].min() >= 8


def test_undefeated_teams_lead_the_wins_based_resume(ranked: Path) -> None:
    """A property of the estimator, not of 2023: an unbeaten résumé is consistent
    with arbitrarily high quality, so it saturates at the bracket and no team with
    a loss can outrank it on this number (model/l4_resume.py)."""
    poll = pl.read_csv(ranked / "poll.csv")
    saturated = poll.filter(pl.col("saturated") == 1)
    assert saturated.height > 0
    assert saturated["losses"].max() == 0
    assert saturated["rank"].to_list() == list(range(1, saturated.height + 1))
    # and the order among them is the margin variant, strictly descending
    assert saturated["resume_margin"].is_sorted(descending=True)


def test_provisional_weeks_are_labelled(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["rank", "--season", "2023", "--through-week", "3", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "PROVISIONAL" in result.output
    params = json.loads((tmp_path / "model_params.json").read_text())
    assert params["provisional"] is True
    assert params["provisional_label"] == load_config()["publication"]["provisional_label"]
    # week 3 is the near-noise regime report 02 §4 declines to publish, and the
    # saturation count is the measurable form of that: half the league is unbeaten
    assert params["n_saturated_high"] > 40


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
