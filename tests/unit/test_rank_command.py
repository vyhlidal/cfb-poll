"""`cfbpoll rank` end to end, against the real archive.

Asserts the file list report 03 §5.3 fixes, the honesty of the labelling (the
headline is schedule odds, opponent quality is L3, the résumé is published beside
both, and every artifact must say so), and that the published numbers are the ones
the fits produced.

Several assertions here changed on 2026-08-12 when the headline ordering did
(docs/adr/0005-headline-ordering.md). Each one that changed carries the reason in
its own docstring, because "the test moved" and "the truth moved" are different
events and a reader should be able to tell which happened.
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
from cfbpoll.model import l4_resume, retro, schedule_odds
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


def test_the_headline_is_schedule_odds_and_the_power_source_is_declared(ranked: Path) -> None:
    """The headline ordering, the résumé beside it, and the Power source that fed
    both - every one of them named on the artifact, because no artifact is allowed
    to be coy about what produced a number (constraint 5).

    ADAPTED TWICE, and both times the asserted truth genuinely changed while the
    shape of the assertion did not:

      * when L1/L3 landed, `power_source` went from "L2" to "L3" and
        `layers_missing` lost ["L1", "L3"];
      * on 2026-08-12 the headline ordering went from the wins-based résumé to
        schedule odds, on the evidence of
        docs/analysis/headline-ordering-study.md (docs/adr/0005-headline-ordering
        .md). `layer` is now the ordering that ranks the poll and the résumé's own
        layer name moved to `resume_layer` - it is still computed, still on every
        row, and still published here.

    The load-bearing part throughout: whatever produced the ranking says so, in
    the file, by name."""
    params = json.loads((ranked / "model_params.json").read_text())
    assert params["layer"] == "C schedule odds"
    assert params["version"] == "v0"
    assert params["headline_ordering"] == "schedule_odds"
    assert params["headline_layer"] == "C_schedule_odds"
    assert params["resume_layer"] == "L4 resume rating"
    assert params["layers_implemented"] == ["L1", "L2", "L3", "L4", "bootstrap"]
    assert params["layers_missing"] == []
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
    assert poll["headline_ordering"] == "schedule_odds"


def test_the_one_free_constant_is_published_with_the_team_it_came_from(ranked: Path) -> None:
    """q_ref is the only free constant the headline ordering has, so it is on the
    poll and on every row rather than in a footnote - a reader can look that team
    up in the same week's table and check the number against it (constraint 5).

    Study §9 measured what it is worth worrying about: across a 16-point swing in
    reference quality the ordering's Kendall tau never fell below 0.985 and at
    most one team entered or left the top 25. It is a convention, not a dial - but
    it is a published one."""
    params = json.loads((ranked / "model_params.json").read_text())
    assert params["q_ref_method"] == "power_rank_25"
    assert params["q_ref_team"]  # a nameable team, which is why this method is default
    assert params["tail_method"] == "exact_poisson_binomial_dp"
    assert "margin never enters" in params["ranking_key"]

    poll = pl.read_csv(ranked / "poll.csv")
    assert poll["q_ref"].n_unique() == 1
    assert poll["q_ref_team"].unique().to_list() == [params["q_ref_team"]]
    assert poll.filter(pl.col("team") == params["q_ref_team"])["power"].item() == pytest.approx(
        params["q_ref"], abs=1e-9
    )


def test_the_poll_is_ordered_by_the_tail_probability(ranked: Path) -> None:
    """The rank key, asserted on the published file rather than trusted.

    Rank 1 is the least probable record: ascending `tail_p`, which is the same
    order as descending `odds_key = -log10(tail_p)` wherever the key is not
    clamped. Both are checked, because the file publishes both."""
    poll = pl.read_csv(ranked / "poll.csv")
    assert poll["tail_p"].is_sorted()
    assert poll["odds_key"].is_sorted(descending=True)
    assert (poll["odds_key"] + poll["tail_p"].log10()).abs().max() < 1e-9


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
    """The published numbers reproduce from the library, not just from the CLI.

    ADAPTED TWICE:

      * when L3 landed, the direct fit had to start walking the season forward to
        get the same out-of-sample blend weights the CLI used, because that is
        what "the Power rating live at week 10" means (report 02 §3.3). Fitting
        the blend on the week-10 window instead would be in-sample and would not -
        and should not - reproduce.
      * on 2026-08-12 the top row of the week-10 2023 poll stopped being Michigan
        and became Ohio State. That is not a regression and it is not arbitrary:
        both were 8-0 at that point, the wins-based résumé had them both saturated
        at the same q bound and separated them on the margin tie-break, and the
        headline ordering now separates them on which 8-0 was less probable
        against the schedule that produced it. The assertion that reproduces the
        two fits is unchanged; only the name it lands on moved.

    Both fits are checked, because both are published on every row."""
    cfg = load_config()
    games = load_games([2023], universe="model")
    plays = load_plays([2023])
    buckets = windows.season_buckets(games, 2023)
    evaluated = next(b for b in buckets if b.season_type == "regular" and b.week == 10)
    powers = retro.season_power(games, 2023, cfg, plays=plays, buckets=buckets)
    window = windows.games_through(games, season=2023, week=10, season_type="regular")
    power = powers[evaluated.order]
    fitted = l4_resume.fit(window, cfg, power=power)
    odds = schedule_odds.fit(
        window, cfg, power=power, classes=poll_mod.team_classes(games)
    )
    poll = pl.read_csv(ranked / "poll.csv")
    top = poll.row(0, named=True)
    assert top["resume"] == pytest.approx(fitted.resume[top["team"]], abs=1e-9)
    assert top["power"] == pytest.approx(fitted.power.rating(top["team"]), abs=1e-9)
    assert top["tail_p"] == pytest.approx(odds.tail[top["team"]], abs=1e-15)
    assert top["odds_key"] == pytest.approx(odds.key[top["team"]], abs=1e-9)
    assert top["team"] == "Ohio State"
    assert top["losses"] == 0


def test_top25_is_football_reality(ranked: Path) -> None:
    poll = pl.read_csv(ranked / "poll.csv")
    top10 = set(poll.head(10)["team"].to_list())
    assert {"Michigan", "Ohio State", "Georgia", "Florida State", "Washington"} <= top10
    # The anti-nonsense clause: nobody outside the plausible set in the top 5.
    assert poll.head(5)["wins"].min() >= 8


def test_undefeated_teams_still_lead_the_wins_based_resume_column(ranked: Path) -> None:
    """A property of the estimator, not of 2023, and still true of the COLUMN: an
    unbeaten résumé is consistent with arbitrarily high quality, so it saturates
    at the bracket and no team with a loss can outrank it on that number
    (model/l4_resume.py).

    ADAPTED 2026-08-12. This previously asserted that the saturated teams occupied
    ranks 1..n of the published poll, which was true only because the poll was
    ordered by the résumé. It is now false, and its being false is the entire
    point of docs/adr/0005-headline-ordering.md: saturation is not a function of
    the schedule, so it cannot respond to the schedule, so a poll ordered on it
    can never say that one 13-0 was harder to achieve than another and can never
    move an unbeaten team in hindsight. The estimator property is unchanged and is
    what is asserted here; what changed is that it no longer decides the poll."""
    poll = pl.read_csv(ranked / "poll.csv")
    saturated = poll.filter(pl.col("saturated") == 1)
    assert saturated.height > 0
    assert saturated["losses"].max() == 0
    # every unbeaten team sits on exactly the same published bound...
    assert saturated["resume"].n_unique() == 1
    assert saturated["resume"].max() == pytest.approx(load_config()["resume"]["q_bounds"][1])
    # ...and every team with a loss is strictly below it, on that column
    beaten = poll.filter(pl.col("saturated") == 0)
    assert beaten["resume"].max() < saturated["resume"].min()
    # but the poll is no longer ordered by it, so unbeaten teams need not be 1..n
    assert saturated["rank"].to_list() != list(range(1, saturated.height + 1))


def test_a_one_loss_team_can_outrank_an_unbeaten_team(ranked: Path) -> None:
    """The price of the decision, asserted rather than left as a surprise.

    Under the résumé ordering this was impossible by construction - the study
    counted the inversions across four seasons and both surfaces and found exactly
    zero, in all eight cells. Under schedule odds it is possible, and in 2023 it
    happens, because a 13-0 against one schedule can be a more probable event than
    a 12-1 against another. That is the promise the poll now makes ("the harder it
    was, the higher you go") and it will need explaining every year, so it is
    pinned here."""
    poll = pl.read_csv(ranked / "poll.csv")
    worst_unbeaten = poll.filter(pl.col("losses") == 0)["rank"].max()
    above = poll.filter((pl.col("losses") >= 1) & (pl.col("rank") < worst_unbeaten))
    assert above.height > 0, "2023 week 10 should have a one-loss team above an unbeaten one"


def test_provisional_weeks_are_labelled(tmp_path: Path) -> None:
    """`--draws 0` here does double duty: it keeps a labelling test fast, and it
    exercises the no-bootstrap path, which must publish EMPTY interval columns
    rather than fabricated ones. A file that quietly omits the interval and a
    file that quietly invents one are both worse than a null."""
    result = runner.invoke(
        app,
        # fmt: off
        [
            "rank", "--season", "2023", "--through-week", "3",
            "--draws", "0", "--out", str(tmp_path),
        ],
        # fmt: on
    )
    assert result.exit_code == 0, result.output
    poll = pl.read_csv(tmp_path / "poll.csv")
    assert poll["rank_lo"].null_count() == poll.height
    assert pl.read_parquet(tmp_path / "rank_intervals.parquet").height == 0
    assert json.loads((tmp_path / "model_params.json").read_text())["bootstrap_draws"] == 0
    assert "PROVISIONAL" in result.output
    params = json.loads((tmp_path / "model_params.json").read_text())
    assert params["provisional"] is True
    assert params["provisional_label"] == load_config()["publication"]["provisional_label"]
    # week 3 is the near-noise regime report 02 §4 declines to publish, and the
    # saturation count is the measurable form of that: half the league is unbeaten
    assert params["n_saturated_high"] > 40


def test_rank_is_reproducible(tmp_path: Path) -> None:
    """Byte-identical across two runs, INTERVALS INCLUDED.

    The intervals come out of a seeded RNG, which is exactly the kind of thing
    that silently stops being reproducible, so `files.canonicalize` covers them
    and this test is what would notice. The draw count is small only to keep the
    suite quick - determinism does not depend on it, and the seeding
    (SeedSequence.spawn per draw) is what makes that true rather than lucky."""
    first, second = tmp_path / "a", tmp_path / "b"
    for out in (first, second):
        assert (
            runner.invoke(
                app,
                # fmt: off
                [
                    "rank", "--season", "2022", "--through-week", "8",
                    "--draws", "40", "--out", str(out),
                ],
                # fmt: on
            ).exit_code
            == 0
        )
    a = files.canonicalize(first, first / "canonical.csv").read_text()
    b = files.canonicalize(second, second / "canonical.csv").read_text()
    assert a == b
    assert "rank_lo" in a and "power_se" in a


def test_every_rank_carries_a_published_interval(ranked: Path) -> None:
    """`[publication].publish_rank_intervals = true  # every week, forever`, and
    this is where that stops being a config line. The review's first line of
    attack was that the poll prints an integer for a quantity that moves by
    dozens of places (S3, §8 item 1); the interval is the honest defence and it
    is on the row rather than in a footnote."""
    poll = pl.read_csv(ranked / "poll.csv")
    intervals = pl.read_parquet(ranked / "rank_intervals.parquet")
    assert intervals.height == poll.height
    assert set(intervals["team"]) == set(poll["team"])

    for lo, hi in (("rank_lo", "rank_hi"), ("resume_rank_lo", "resume_rank_hi")):
        assert poll[lo].null_count() == 0
        assert (poll[lo] <= poll[hi]).all()
        assert poll[lo].min() >= 1 and poll[hi].max() <= poll.height
    assert (poll["power_rank_lo"] <= poll["power_rank_hi"]).all()

    # The interval is WIDE, and that is the finding rather than a defect: a
    # single season is twelve noisy games and the poll should not pretend
    # otherwise (review §9 item 2).
    widths = (poll["rank_hi"] - poll["rank_lo"]).to_list()
    assert sorted(widths)[len(widths) // 2] > 20

    # every Power rating carries the ridge sandwich SE, in points
    assert poll["power_se"].null_count() == 0
    assert poll["power_se"].min() > 0.0

    params = json.loads((ranked / "model_params.json").read_text())
    assert params["bootstrap_scheme"] == "parametric_on_fixed_schedule"
    assert params["bootstrap_draws"] == load_config()["bootstrap"]["draws"]
    assert "resampling them with replacement" in params["bootstrap_note"]
    assert params["power_se_note"]


def test_publication_status_follows_the_config() -> None:
    cfg = load_config()
    start = int(cfg["publication"]["headline_start_week"])
    assert poll_mod.publication_status(start - 1, cfg)[0] is True
    assert poll_mod.publication_status(start, cfg)[0] is False
