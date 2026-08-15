"""The grading loop: the deltas, the attribution, and the sentences.

The loop is the product, so the tests are about whether it can be READ correctly
rather than only whether it runs. Two properties carry most of the weight:

  * the sign convention. `delta_vs_hindsight` is positive when we UNDER-rated a
    team, matching `retro.movers` exactly, because two tables with opposite
    conventions is how a reader ends up quoting the wrong direction.
  * the attribution's verdict must read the same way for a term that hands out
    CREDITS and one that hands out DEBITS. That is the bug this file exists to
    prevent: reading the verdict off the coefficient's own sign inverts the
    sentence on the coaching-change penalty, which is the term a reader is most
    likely to quote.

Everything here runs on synthetic surfaces. The loop's arithmetic is a join and a
regression; wiring it to a real season would make these tests slow and would test
`retro` rather than `grade`.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from cfbpoll.projection import grade, recipe

TEAMS = [f"Team {i:03d}" for i in range(40)]


def _surface(ranks: dict[str, int], powers: dict[str, float], eval_order: int = 5):
    teams = sorted(ranks)
    return pl.DataFrame(
        {
            "eval_order": pl.Series([eval_order] * len(teams), dtype=pl.Int32),
            "eval_label": ["2024-regu-w05"] * len(teams),
            "team": teams,
            "rank": pl.Series([ranks[t] for t in teams], dtype=pl.Int32),
            "power": [powers.get(t, 0.0) for t in teams],
        }
    )


@pytest.fixture
def projection() -> pl.DataFrame:
    rng = np.random.default_rng(11)
    frame = pl.DataFrame(
        {
            "team": TEAMS,
            "season": pl.Series([2024] * len(TEAMS), dtype=pl.Int32),
            "prior_power_centered": rng.normal(0.0, 12.0, len(TEAMS)),
            "returning_usage_centered": rng.normal(0.0, 0.15, len(TEAMS)),
            "coach_change": (rng.random(len(TEAMS)) < 0.25).astype(float),
            "portal_net_z": rng.normal(0.0, 1.0, len(TEAMS)),
        }
    )
    fitted = recipe.Recipe(
        intercept=15.0,
        coefficients={
            "prior_power": 0.68,
            "returning_production": 7.08,
            "coaching_change": -2.33,
            "net_portal": -0.41,
        },
        se=dict.fromkeys(recipe.TERMS, 0.5),
        intercept_se=0.5,
        transitions=((2023, 2024),),
        n_teams=len(TEAMS),
        r_squared=0.5,
        residual_sd=9.2,
    )
    return recipe.project(fitted, frame, TEAMS)


# ---------------------------------------------------------------- the sign convention


def test_a_positive_delta_means_we_under_rated_them(projection: pl.DataFrame) -> None:
    """Same convention as `retro.movers`: positive = the poll has them higher than
    we did = we under-rated them."""
    teams = projection["team"].to_list()
    projected = dict(
        zip(teams, projection["projected_rank"].to_list(), strict=True)
    )
    riser = teams[30]
    hindsight_ranks = {t: projected[t] for t in teams}
    hindsight_ranks[riser] = 1
    powers = dict.fromkeys(teams, 20.0)

    graded = grade.grade_week(
        projection,
        _surface(projected, powers),
        _surface(hindsight_ranks, powers),
        eval_order=5,
        eval_label="2024-regu-w05",
        season=2024,
    )
    row = graded.filter(pl.col("team") == riser).to_dicts()[0]
    assert row["delta_vs_hindsight"] == projected[riser] - 1
    assert row["delta_vs_hindsight"] > 0
    assert row["delta_vs_live"] == 0


def test_only_teams_the_poll_ranked_are_graded(projection: pl.DataFrame) -> None:
    """A rank delta against a team the poll never ranked is not a number."""
    ranked = projection["team"].to_list()[:10]
    ranks = {t: i + 1 for i, t in enumerate(ranked)}
    graded = grade.grade_week(
        projection, _surface(ranks, {}), _surface(ranks, {}), 5, "2024-regu-w05", 2024
    )
    assert sorted(graded["team"].to_list()) == sorted(ranked)


# ------------------------------------------------------------------ the attribution


def _graded_with(errors: dict[str, float], projection: pl.DataFrame) -> pl.DataFrame:
    teams = projection["team"].to_list()
    ranks = {t: i + 1 for i, t in enumerate(teams)}
    projected_power = dict(
        zip(teams, projection["projected_power"].to_list(), strict=True)
    )
    powers = {t: projected_power[t] + errors.get(t, 0.0) for t in teams}
    return grade.grade_week(
        projection, _surface(ranks, powers), _surface(ranks, powers), 5, "w", 2024
    )


def test_a_term_that_moved_teams_too_far_is_called_too_strong(
    projection: pl.DataFrame,
) -> None:
    """Plant the failure: make every team land halfway back toward the intercept
    along the returning-production term. The attribution must convict THAT term."""
    contributions = dict(
        zip(
            projection["team"].to_list(),
            projection["contrib_returning_production"].to_list(),
            strict=True,
        )
    )
    errors = {team: -0.5 * value for team, value in contributions.items()}
    result = grade.attribution(_graded_with(errors, projection))

    term = result["terms"]["returning_production"]
    assert term["verdict"] == "TOO STRONG"
    assert term["coefficient"] == pytest.approx(-0.5, abs=0.02)
    assert term["implied_multiplier"] == pytest.approx(0.5, abs=0.02)
    assert "TOO STRONG" in term["sentence"]
    assert "the other way" in term["sentence"]


def test_the_verdict_reads_the_same_way_for_a_debit_as_for_a_credit(
    projection: pl.DataFrame,
) -> None:
    """THE BUG THIS FILE EXISTS FOR.

    The coaching-change term hands out a DEBIT (-2.33 for every school that
    changed). Plant teams landing further down than that debit predicted - the
    penalty was too small - and the verdict must be TOO WEAK, exactly as it would
    be for a credit that was too small. A verdict read off the coefficient's own
    sign gets this backwards."""
    contributions = dict(
        zip(
            projection["team"].to_list(),
            projection["contrib_coaching_change"].to_list(),
            strict=True,
        )
    )
    # Every changed school lands 3x its (negative) debit further down.
    errors = {team: 3.0 * value for team, value in contributions.items()}
    result = grade.attribution(_graded_with(errors, projection))

    term = result["terms"]["coaching_change"]
    assert term["verdict"] == "TOO WEAK"
    assert term["coefficient"] == pytest.approx(3.0, abs=0.05)
    assert term["implied_multiplier"] == pytest.approx(4.0, abs=0.05)
    assert "TOO WEAK" in term["sentence"]
    assert "further in the same direction" in term["sentence"]
    assert term["n_teams_moved"] < len(TEAMS)  # only the schools that changed


def test_a_term_priced_right_is_not_convicted(projection: pl.DataFrame) -> None:
    """Noise must not produce a verdict. A loop that finds a guilty term every
    season is a loop nobody believes by season three."""
    rng = np.random.default_rng(5)
    teams = projection["team"].to_list()
    errors = dict(zip(teams, rng.normal(0.0, 6.0, len(teams)), strict=True))
    result = grade.attribution(_graded_with(errors, projection))
    verdicts = {t: v["verdict"] for t, v in result["terms"].items()}
    assert all(v == "priced about right" for v in verdicts.values()), verdicts
    assert "cumulative" in result["health_warning"]


def test_attribution_declines_when_there_are_too_few_teams() -> None:
    """Four terms and an intercept need more than five rows. Refusing is better
    than fitting a saturated regression and publishing its coefficients."""
    frame = pl.DataFrame(
        {
            "power_error": [1.0, 2.0],
            **{f"contrib_{t}": [0.5, 1.5] for t in recipe.TERMS},
        }
    )
    result = grade.attribution(frame)
    assert result["terms"] == {}
    assert "too few" in result["note"]


# ---------------------------------------------------------------------- the sentences


def test_story_lines_are_about_the_top_of_the_poll(projection: pl.DataFrame) -> None:
    """Without the rank filter this table is permanently owned by the bottom of
    the league, where a nine-win improvement is worth ninety places and a
    top-25-relevant miss of twenty is invisible."""
    teams = projection["team"].to_list()
    projected = dict(zip(teams, projection["projected_rank"].to_list(), strict=True))
    by_rank = {rank: team for team, rank in projected.items()}

    # Two disturbances, deliberately unequal. The BIG one is entirely outside the
    # top 25 - ranks 30-40 reversed among themselves, up to ten places - which is
    # the bottom-of-the-league churn the filter exists to suppress. The SMALL one
    # is a five-place swap inside the top ten, which is what a poll reader
    # actually wants to be told about.
    hindsight = dict(projected)
    for rank in range(30, 41):
        hindsight[by_rank[rank]] = 70 - rank
    hindsight[by_rank[3]], hindsight[by_rank[8]] = 8, 3

    powers = dict.fromkeys(teams, 20.0)
    graded = grade.grade_week(
        projection, _surface(projected, powers), _surface(hindsight, powers), 5, "w", 2024
    )

    unfiltered = grade.story_lines(graded, 5, top_n=5, within_rank=0)
    filtered = grade.story_lines(graded, 5, top_n=5, within_rank=25)
    assert len(unfiltered) == 5
    assert len(filtered) == 5

    # Unfiltered is owned by the churn; filtered is about the two teams a reader
    # of a top-25 poll is entitled to hear about.
    assert all(by_rank[3] not in line and by_rank[8] not in line for line in unfiltered)
    assert any(by_rank[3] in line for line in filtered)
    assert any(by_rank[8] in line for line in filtered)
    assert all(by_rank[35] not in line for line in filtered)

    for line in filtered:
        assert "The projection had" in line
        assert "The poll now has them at" in line
        assert ("under-rated" in line) or ("over-rated" in line)


def test_every_story_line_names_itself_a_projection(projection: pl.DataFrame) -> None:
    """A line that gets screenshotted has to carry its own label. The header is
    not enough, because the header is not in the screenshot."""
    teams = projection["team"].to_list()
    projected = dict(zip(teams, projection["projected_rank"].to_list(), strict=True))
    hindsight = {t: len(teams) + 1 - projected[t] for t in teams}
    graded = grade.grade_week(
        projection,
        _surface(projected, dict.fromkeys(teams, 20.0)),
        _surface(hindsight, dict.fromkeys(teams, 20.0)),
        5,
        "w",
        2024,
    )
    lines = grade.story_lines(graded, 5, top_n=8)
    assert lines
    for line in lines:
        assert "projection" in line.lower()


# ------------------------------------------------- the voice, and the copy rules

#: The same set `publish/serving.py` and `projection/publish.py` enforce. The
#: grading document reaches the site as prose, so it is bound by the same rules
#: as the card copy that sits one page away from it.
BANNED_PUNCTUATION = ("—", "–", "--")

#: THE SITE'S VOICE IS THE BUILDER'S "I" AND THE MODEL IS "THE MODEL". A generated
#: sentence saying "we" imports a pipeline's voice into a first-person page, and
#: the attribution sentence did exactly that: "this season wanted about 0.66x the
#: coefficient we used" was published under a page written in the singular.
_FIRST_PERSON_PLURAL = (" we ", "We ", " our ", "Our ", " us ", " we.", " we,")


def _all_published_sentences(projection: pl.DataFrame) -> list[str]:
    teams = projection["team"].to_list()
    projected = dict(zip(teams, projection["projected_rank"].to_list(), strict=True))
    hindsight = {t: len(teams) + 1 - projected[t] for t in teams}
    powers = {t: 20.0 - 0.3 * projected[t] for t in teams}
    graded = grade.grade_week(
        projection, _surface(projected, powers), _surface(hindsight, powers), 5, "w", 2024
    )
    attribution = grade.attribution(graded)
    sentences = [term["sentence"] for term in attribution["terms"].values()]
    sentences.extend(grade.story_lines(graded, 5, top_n=8))
    # Both branches of the attribution template, whichever this fixture happened
    # to exercise: a verdict that never fires in the fixture is still published
    # copy the first season it does.
    for value, verdict in ((-0.34, "TOO STRONG"), (0.42, "TOO WEAK"), (0.01, "priced about right")):
        sentences.append(
            grade._attribution_sentence("prior_power", value, 4.4, verdict, 136)  # noqa: SLF001
        )
    return sentences


def test_no_graded_sentence_carries_banned_punctuation(projection: pl.DataFrame) -> None:
    for sentence in _all_published_sentences(projection):
        for character in BANNED_PUNCTUATION:
            assert character not in sentence, sentence


def test_no_graded_sentence_speaks_in_the_first_person_plural(
    projection: pl.DataFrame,
) -> None:
    """The model is the actor, and it is named. "We" is the pipeline talking."""
    for sentence in _all_published_sentences(projection):
        padded = f" {sentence} "
        for token in _FIRST_PERSON_PLURAL:
            assert token not in padded, sentence


def test_the_attribution_sentence_names_the_model_and_states_the_multiplier() -> None:
    """The verdict token, the actor and the number a reader would quote."""
    sentence = grade._attribution_sentence(  # noqa: SLF001
        "prior_power", -0.344457263344027, -4.407270999908184, "TOO STRONG", 136
    )
    assert sentence == (
        "The model weighted last season's rating TOO STRONG. For every point of "
        "Power it moved a team's projection, that team finished 0.34 points the "
        "other way (4.4 standard errors over 136 teams). This season wanted about "
        "0.66x the model's coefficient."
    )
