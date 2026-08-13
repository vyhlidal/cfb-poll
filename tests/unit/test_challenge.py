"""The challenge harness: the front door, and the ways an entry gets rejected.

The valuable tests here are the refusals. A challenge harness that accepts a
malformed entry and scores it anyway produces a number about a model nobody ran,
and publishes it under a stranger's name - which is worse than having no harness
at all, because it looks like a measurement.

The one integration test runs a real walk over one season and is skipped without
the local archive, like every other test that needs data.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from cfbpoll.backtest import challenge, walkforward
from cfbpoll.config import load_config, merge_overlay
from cfbpoll.ingest.sportsdataverse import DEFAULT_ARCHIVE

REPO_ROOT = Path(__file__).resolve().parents[2]
CHALLENGERS = REPO_ROOT / "configs" / "challengers"
CONFIG = load_config()

needs_archive = pytest.mark.skipif(
    not (DEFAULT_ARCHIVE / "schedules").exists(), reason="local archive not materialised"
)


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


# -------------------------------------------------------------- merge_overlay


def test_an_override_merges_tables_and_replaces_values() -> None:
    base = {"margin": {"c": 32.0, "beta_w": 7.0}, "gate": {"mae_max": 12.8}}
    merged = merge_overlay(base, {"margin": {"beta_w": 4.0}})
    assert merged == {"margin": {"c": 32.0, "beta_w": 4.0}, "gate": {"mae_max": 12.8}}
    assert base["margin"]["beta_w"] == 7.0, "merge_overlay must not mutate its inputs"


def test_an_override_that_names_a_key_nobody_defined_is_refused() -> None:
    """The whole reason this is not `dict.update`.

    A challenger who types `betaw` instead of `beta_w` would otherwise be scored
    on the default constants while believing they had changed one, and would then
    publish a finding about a model nobody ran.
    """
    with pytest.raises(KeyError, match="does not"):
        merge_overlay({"margin": {"beta_w": 7.0}}, {"margin": {"betaw": 4.0}})
    with pytest.raises(KeyError, match="does not"):
        merge_overlay({"margin": {"beta_w": 7.0}}, {"marginn": {"beta_w": 4.0}})


def test_a_list_is_a_value_rather_than_something_to_append_to() -> None:
    base = {"backtest": {"holdout_seasons": [2025]}}
    assert merge_overlay(base, {"backtest": {"holdout_seasons": [2024, 2025]}}) == {
        "backtest": {"holdout_seasons": [2024, 2025]}
    }


# ------------------------------------------------------------ the two examples


def test_the_committed_parameter_example_loads_and_changes_something() -> None:
    who = challenge.load_challenger(CHALLENGERS / "beta-w-4.toml")
    assert (who.name, who.kind, who.system) == ("beta-w-4", "parameter", "schedule_odds")
    assert who.overlay == {"margin": {"beta_w": 4.0}}
    # And the key it names really is a key the model reads.
    assert merge_overlay(CONFIG, who.overlay)["margin"]["beta_w"] == 4.0


def test_the_committed_structural_example_loads_and_rates_a_frame() -> None:
    who = challenge.load_challenger(CHALLENGERS / "iterative_margin.py")
    assert (who.name, who.kind, who.system) == ("iterative-margin", "structural", "challenger")
    assert who.needs_plays is False

    games = pl.DataFrame(
        {
            "home_team": ["A", "B", "A"],
            "away_team": ["B", "C", "C"],
            "home_points": pl.Series([31, 28, 42], dtype=pl.Int32),
            "away_points": pl.Series([10, 24, 7], dtype=pl.Int32),
        }
    )
    ratings = who.rate(games, None, 3)
    assert set(ratings) == {"A", "B", "C"}
    assert ratings["A"] > ratings["B"] > ratings["C"]
    # The zero point is fixed every round, so the ratings are centred.
    assert sum(ratings.values()) == pytest.approx(0.0, abs=1e-9)


def test_the_structural_example_is_deterministic_and_row_order_independent() -> None:
    who = challenge.load_challenger(CHALLENGERS / "iterative_margin.py")
    games = pl.DataFrame(
        {
            "home_team": ["A", "B", "A", "C"],
            "away_team": ["B", "C", "C", "A"],
            "home_points": pl.Series([31, 28, 42, 3], dtype=pl.Int32),
            "away_points": pl.Series([10, 24, 7, 17], dtype=pl.Int32),
        }
    )
    base = who.rate(games, None, 4)
    assert base == who.rate(games, None, 4)
    shuffled = who.rate(games.sample(fraction=1.0, shuffle=True, seed=7), None, 4)
    for team, value in base.items():
        assert shuffled[team] == pytest.approx(value, abs=1e-12)


# ------------------------------------------------------------------- refusals


def test_an_entry_that_does_not_exist_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        challenge.load_challenger(tmp_path / "nope.toml")


def test_an_entry_with_no_challenger_block_is_refused(tmp_path: Path) -> None:
    path = write(tmp_path, "x.toml", "[margin]\nbeta_w = 4.0\n")
    with pytest.raises(ValueError, match="missing"):
        challenge.load_challenger(path)


def test_a_parameter_entry_that_overrides_nothing_is_refused(tmp_path: Path) -> None:
    """Scoring the incumbent against itself would report a tie as a finding."""
    path = write(tmp_path, "x.toml", '[challenger]\nname = "x"\nkind = "parameter"\n')
    with pytest.raises(ValueError, match="overrides nothing"):
        challenge.load_challenger(path)


def test_a_parameter_entry_naming_an_unknown_constant_fails_before_any_fitting(
    tmp_path: Path,
) -> None:
    path = write(
        tmp_path,
        "x.toml",
        '[challenger]\nname = "x"\nkind = "parameter"\n\n[margin]\nbetaw = 4.0\n',
    )
    with pytest.raises(KeyError, match="does not"):
        challenge.load_challenger(path)


def test_a_module_with_no_rate_function_is_refused(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "x.py",
        'CHALLENGER = {"name": "x", "kind": "structural"}\n\ndef score():\n    return {}\n',
    )
    with pytest.raises(ValueError, match="no `rate` function"):
        challenge.load_challenger(path)


def test_the_kind_must_match_the_file_extension(tmp_path: Path) -> None:
    toml = write(tmp_path, "x.toml", '[challenger]\nname = "x"\nkind = "structural"\n')
    with pytest.raises(ValueError, match="parameter variant"):
        challenge.load_challenger(toml)
    py = write(tmp_path, "y.py", 'CHALLENGER = {"name": "y", "kind": "parameter"}\n')
    with pytest.raises(ValueError, match="structural variant"):
        challenge.load_challenger(py)


def test_an_unknown_extension_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="\\.toml parameter variant or a \\.py module"):
        challenge.load_challenger(write(tmp_path, "x.json", "{}"))


# ---------------------------------------------------- the harness accepts one


def test_the_harness_accepts_a_challenger_as_one_more_system() -> None:
    """`resolve` must know a name it has never heard of, and only when told."""
    extra = {"challenger": lambda *a, **k: {}}
    assert walkforward.baselines.resolve("challenger", extra=extra) == "challenger"
    with pytest.raises(KeyError, match="unknown system"):
        walkforward.baselines.resolve("challenger")


@needs_archive
def test_a_challenger_is_walked_by_the_same_harness_over_the_same_frames() -> None:
    """The claim the whole moat rests on, checked on one real season.

    A rater that records every frame it is handed shows the harness treating a
    stranger's module exactly as it treats its own baselines: sliced frames that
    grow one bucket at a time, the same keyword arguments, and a gate object of
    its own at the end. The leakage guard itself is pinned by
    `test_walkforward.py::test_walk_forward_never_sees_a_planted_future_game`,
    which is the right place for it - a challenger inherits that property rather
    than being asked to implement it.
    """
    seen: list[int] = []

    def rate(games, plays=None, through_week=None, config=None, state=None):  # noqa: ANN001
        seen.append(games.height)
        return dict.fromkeys(games["home_team"].unique().to_list(), 0.0)

    result = walkforward.run_backtest(
        [2023], ["winpct", "challenger"], extra_raters={"challenger": rate}
    )
    assert len(seen) > 5, "the harness never walked the challenger forward"
    assert seen[0] < seen[-1], "every bucket handed the challenger the same frame"
    assert seen == sorted(seen), "the training window must only ever grow"

    assert "challenger" in result["systems"]
    assert result["systems"]["challenger"]["gate"]["passed"] is False
    # A flat rater has no spread, so it cannot beat anything. What matters is
    # that it was SCORED, by the same code, against the same thresholds.
    assert (
        result["systems"]["challenger"]["gate"]["thresholds"]
        == result["systems"]["winpct"]["gate"]["thresholds"]
    )


# ------------------------------------------------------------ the scorecard


def _fake_result() -> dict:
    gate = {
        "passed": False,
        "thresholds": {
            "su_accuracy_min": 0.7,
            "mae_max": 12.8,
            "rmse_max": 15.8,
            "calibration_max_decile_deviation_pp": 5.0,
            "violations_must_beat": "all_scored_systems",
        },
        "window": "FBS-vs-FBS, weeks >= 5",
    }
    return {
        "challenger": {
            "name": "example",
            "kind": "parameter",
            "entry": "configs/challengers/example.toml",
            "author": "",
        },
        "protocol": {
            "seasons": [2021],
            "window": gate["window"],
            "note": "TWO RUNS",
            "holdout_seasons": [2025],
            "holdout_touched": False,
            "gate_thresholds": gate["thresholds"],
        },
        "scorecard": [
            {
                "metric": "mae",
                "label": "Margin MAE",
                "incumbent": 13.0,
                "challenger": 12.5,
                "delta": -0.5,
                "better": True,
                "higher_is_better": False,
            },
            {
                "metric": "su_accuracy",
                "label": "Straight-up %",
                "incumbent": 0.69,
                "challenger": 0.68,
                "delta": -0.01,
                "better": False,
                "higher_is_better": True,
            },
        ],
        "verdict": {
            "beats_incumbent_on": ["Margin MAE"],
            "loses_to_incumbent_on": ["Straight-up %"],
            "challenger_clears_gate": False,
            "incumbent_clears_gate": False,
        },
        "gates": {"schedule_odds": gate},
        "baselines": {"srs": {"mae": 13.2, "retrodictive_violation_rate": 0.22}},
    }


def test_the_scorecard_names_the_entry_and_reports_both_directions() -> None:
    text = challenge.scorecard_markdown(_fake_result())
    assert "example" in text
    assert "1 of 2 metrics beat the incumbent" in text
    assert "**better**" in text and "worse" in text
    assert "12.500" in text and "13.000" in text


def test_a_challenger_that_beats_us_still_has_to_clear_the_gate() -> None:
    """The distinction the harness exists to keep. Winning != clearing."""
    result = _fake_result()
    result["verdict"]["beats_incumbent_on"] = ["Margin MAE", "Straight-up %"]
    result["verdict"]["loses_to_incumbent_on"] = []
    text = challenge.scorecard_markdown(result)
    assert "does not clear the publication gate" in text
    assert "Beating the incumbent on a metric is a finding" in text


def test_the_scorecard_says_whether_the_holdout_was_touched() -> None:
    assert "Holdout [2025] touched: **False**" in challenge.scorecard_markdown(_fake_result())


def test_write_scorecard_keeps_the_summary_small_and_the_trees_beside_it(
    tmp_path: Path,
) -> None:
    result = _fake_result()
    result["runs"] = {"reference": {"big": ["tree"] * 100}, "variant": None}
    written = challenge.write_scorecard(result, tmp_path)
    assert written["markdown"].exists() and written["json"].exists()
    assert '"runs":' not in written["json"].read_text()
    assert (tmp_path / "backtest_metrics_reference.json").exists()
    assert not (tmp_path / "backtest_metrics_variant.json").exists()


# -------------------------------------------------- the committed sample card


def test_the_committed_sample_scorecard_is_the_one_the_readme_describes() -> None:
    """The README claims a specific, unflattering result. Pin it.

    A worked example that quietly stops matching its own documentation is the
    same failure as a hand-written summary of a generated table, one directory
    over.
    """
    card = REPO_ROOT / "demo" / "challenge-iterative-margin" / "scorecard.md"
    assert card.exists(), "the sample scorecard is the proof the harness ran"
    text = card.read_text(encoding="utf-8")
    assert "iterative-margin" in text
    assert "metrics beat the incumbent" in text
    assert "Holdout [2025] touched: **False**" in text
