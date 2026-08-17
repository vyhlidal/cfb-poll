"""The lever registry as a contract rather than a config file.

`src/cfbpoll/levers.py` makes four promises that only a test can keep honest:

  * a shipped default is always a value the reader could have chosen themselves,
    so it must sit inside the range published beside it;
  * every knob arrives with football words and a citation - a lever with a blank
    `evidence` field is an assertion with a slider attached, which is the exact
    thing this registry exists to replace;
  * a typo in a lever name is an ERROR, never a silent fallback to the default,
    because a silently ignored key produces a board the reader thinks they
    changed and did not;
  * and `model.conference_identity` is off, published so the refusal is
    checkable. If somebody moves that default this file fails loudly.
"""

from __future__ import annotations

import json

import pytest

from cfbpoll import levers

# ------------------------------------------------------------------- the invariants


def test_every_default_sits_inside_its_own_published_range() -> None:
    """A default outside its range would make the published slider unable to
    reproduce the published board - the reader's first move would change the
    answer before they had chosen anything.

    A CATEGORICAL LEVER ANSWERS THE SAME QUESTION WITH MEMBERSHIP. There is no
    range, so "inside it" means "one of the strings on offer", and the round trip
    through `clamp` has to hold either way.
    """
    for lever in levers.LEVERS:
        if lever.is_categorical:
            assert lever.low is None and lever.high is None, lever.key
            assert lever.default in lever.values, lever.key
            assert len(lever.values) >= 2, lever.key
            assert len(set(lever.values)) == len(lever.values), lever.key
        else:
            assert lever.low is not None and lever.high is not None, lever.key
            assert lever.low <= lever.default <= lever.high, lever.key
            assert lever.low < lever.high, lever.key
        assert lever.clamp(lever.default) == lever.default, lever.key


def test_the_ordering_lever_offers_all_three_legal_strings_and_nothing_else() -> None:
    """The ruling of 2026-08-17, as an assertion rather than a comment.

    It was a 0-or-1 float, which could express two of the three orderings and had
    no way to name `L4_resume_margin` - the one `configs/recipes/full-merit.toml`
    ships. A registry that cannot name a board the project publishes is not a
    registry of what a reader may change.
    """
    from cfbpoll.publish.poll import ORDERING_LAYER

    lever = levers.get("publication.headline_ordering")
    assert lever.is_categorical
    assert set(lever.values) == set(ORDERING_LAYER)
    assert lever.values == ("schedule_odds", "L4_resume", "L4_resume_margin")
    assert lever.default == "schedule_odds"
    assert levers.defaults()["publication.headline_ordering"] == "schedule_odds"


def test_the_ordering_lever_refuses_a_string_it_does_not_offer() -> None:
    """There is no nearest legal ordering, so there is nothing to clamp toward.

    Silently picking one would hand back a board answering a question the reader
    did not ask, which is the same failure an ignored typo produces one level up.
    """
    lever = levers.get("publication.headline_ordering")
    with pytest.raises(ValueError, match="L4_resume_margin"):
        lever.clamp("L4_resume_marginal")
    with pytest.raises(ValueError):
        levers.validate({"publication.headline_ordering": "colley"})


def test_the_margin_c_floor_reaches_the_recipe_this_project_ships() -> None:
    """The other half of the same ruling.

    `configs/recipes/just-win.toml` is a published recipe at c = 1.0 and the
    `margin-c-1` playground variant publishes a board at it. A floor of 18
    excluded a ranking this project already serves.
    """
    from cfbpoll import recipes

    lever = levers.get("margin.c")
    assert lever.low == 1.0
    shipped, _ = recipes.resolve("just-win")
    assert shipped["margin"]["c"] == lever.low
    assert lever.clamp(shipped["margin"]["c"]) == shipped["margin"]["c"]


def test_no_lever_ships_without_words_and_a_citation() -> None:
    """The module's own promise, in its docstring: `evidence` names what measured
    the default and is "never blank". A knob with no evidence is a preference
    wearing a measurement's clothes, so this is the test that stops one shipping.
    """
    for lever in levers.LEVERS:
        assert lever.label.strip(), lever.key
        assert lever.plain.strip(), lever.key
        assert lever.evidence.strip(), lever.key
        # Football words, not Greek. A label that is only a symbol has failed the
        # one job the registry gave it.
        assert len(lever.label.split()) >= 3, lever.key


def test_lever_keys_are_unique() -> None:
    """The key is also the config path, so a duplicate would mean one lever
    silently shadowing another in `_BY_KEY` and a published slider wired to the
    wrong number."""
    keys = [lever.key for lever in levers.LEVERS]
    assert len(keys) == len(set(keys))
    assert len(keys) == len(levers.defaults())


def test_every_surface_is_one_of_the_three_published_words() -> None:
    """`surface` decides which product a knob appears on. A fourth value would
    put a lever on neither page and nobody would notice."""
    assert {lever.surface for lever in levers.LEVERS} <= {"poll", "projection", "both"}


# ------------------------------------------------------------------- the accessors


def test_get_on_an_unknown_key_raises_and_names_what_does_exist() -> None:
    """The error has to be actionable: a reader who mistyped a lever wants the
    list of real ones, not a stack trace."""
    assert levers.get("margin.beta_w").default == 7.0

    with pytest.raises(KeyError) as caught:
        levers.get("margin.beta_wins")
    message = str(caught.value)
    assert "margin.beta_wins" in message
    assert "margin.beta_w" in message  # the list of registered keys came along


def test_defaults_returns_one_entry_per_lever() -> None:
    """`defaults()` is what the published board says it was produced with, so it
    has to cover the registry exactly - no extras, nothing missing."""
    shipped = levers.defaults()
    assert set(shipped) == {lever.key for lever in levers.LEVERS}
    assert len(shipped) == len(levers.LEVERS)
    for lever in levers.LEVERS:
        assert shipped[lever.key] == lever.default


def test_each_surface_includes_the_levers_that_act_on_both() -> None:
    """A lever marked `both` has to appear on BOTH pages. Dropping it from either
    would hide the conference switch from whichever product the reader opened,
    and the refusal is only worth anything where it is visible."""
    poll = levers.for_surface("poll")
    projection = levers.for_surface("projection")
    shared = tuple(lv for lv in levers.LEVERS if lv.surface == "both")

    assert shared  # otherwise this test proves nothing
    for lever in shared:
        assert lever in poll
        assert lever in projection

    assert {lv.key for lv in poll} == {
        lv.key for lv in levers.LEVERS if lv.surface in ("poll", "both")
    }
    assert {lv.key for lv in projection} == {
        lv.key for lv in levers.LEVERS if lv.surface in ("projection", "both")
    }
    # Nothing acting only on the poll may leak onto the projection page.
    assert "margin.beta_w" not in {lv.key for lv in projection}
    assert "projection.long_memory" not in {lv.key for lv in poll}


# -------------------------------------------------------------------- validate()


def test_validate_clamps_out_of_range_values() -> None:
    """Outside the published range "the answer stops being a poll", so a value
    past either end is pulled back to the end rather than honoured."""
    clamped = levers.validate(
        {
            "projection.long_memory": 9.9,  # high is 0.6
            "projection.cross_division_gap": -4.0,  # low is 0.0
            "margin.beta_w": 5.0,  # already inside [0, 12]
        }
    )
    assert clamped["projection.long_memory"] == 0.6
    assert clamped["projection.cross_division_gap"] == 0.0
    assert clamped["margin.beta_w"] == 5.0
    # Only the keys handed in come back. Validation is not a merge with defaults.
    assert set(clamped) == {
        "projection.long_memory",
        "projection.cross_division_gap",
        "margin.beta_w",
    }


def test_validate_refuses_an_unknown_key_instead_of_ignoring_it() -> None:
    """The docstring's reason, as an assertion: the likeliest cause of an unknown
    key is a typo in a lever name, and a typo that silently leaves the default in
    place hands the reader a board they believe they changed."""
    with pytest.raises(KeyError) as caught:
        levers.validate({"margin.beta_w": 3.0, "projection.long_memoryy": 0.3})
    message = str(caught.value)
    assert "projection.long_memoryy" in message  # the offending key is named
    assert "projection.long_memory" in message  # ...and so is the one they meant


def test_validate_accepts_the_shipped_defaults_unchanged() -> None:
    """The board that was published must survive a round trip through its own
    validator, or the registry and the artifact disagree about what ran."""
    assert levers.validate(levers.defaults()) == levers.defaults()


# ---------------------------------------------------------- the published document


def test_the_registry_document_is_json_and_keeps_both_untouchables() -> None:
    """The registry ships beside a board as JSON, and the two untouchables ride
    with it. They are NOT levers - there is no slider for reading a human poll or
    reading the future - so the document is where a reader checks that the
    refusals are still stated rather than quietly dropped."""
    document = levers.registry_document()
    restored = json.loads(json.dumps(document))
    assert restored["levers"]
    assert len(restored["levers"]) == len(levers.LEVERS)

    untouchable = restored["untouchable"]
    assert len(untouchable) == 2
    text = " ".join(entry["rule"] + " " + entry["detail"] for entry in untouchable).lower()
    assert "poll" in text and "human" in text
    assert "future" in text
    assert all(entry["rule"].strip() and entry["detail"].strip() for entry in untouchable)

    # Every lever survives the trip with the fields that make it a product.
    for row in restored["levers"]:
        assert set(row) == {
            "key",
            "label",
            "surface",
            "range",
            "unbounded_above",
            "default",
            "plain",
            "evidence",
            "sweep",
            "values",
            "measured_effect",
        }
        low, high = row["range"]
        # `values` IS ON EVERY ROW, empty for a quantity. A consumer that has to
        # test for a field's existence to learn a lever's kind will one day forget.
        assert isinstance(row["values"], list)
        if row["values"]:
            # Categorical: no range at all, and the default is one of the strings.
            assert low is None and high is None
            assert row["unbounded_above"] is False
            assert row["default"] in row["values"]
            assert row["sweep"] == []
            continue
        # An unbounded top is `null` in the document, never the bare `Infinity`
        # token, because that is not JSON and a browser refuses the whole file.
        assert low is not None
        assert (high is None) == row["unbounded_above"]
        assert low <= row["default"]
        if high is not None:
            assert row["default"] <= high


# ------------------------------------------------------------- the fairness spine


def test_the_conference_lever_ships_off_and_this_test_is_the_lock() -> None:
    """THE FAIRNESS SPINE. Nothing in the base model knows what a conference is,
    and conference strength has to be earned on the field rather than assumed
    from the letters on the jersey.

    The switch is published so the refusal is checkable, which only means
    something while the default is zero. If somebody moves it, this fails - and
    it should fail here, loudly, rather than being discovered in a board that
    already went out.
    """
    lever = levers.get("model.conference_identity")
    assert lever.default == 0.0
    assert lever.surface == "both"
    assert lever.sweep == (0.0,)  # the only value the site may offer
    assert levers.defaults()["model.conference_identity"] == 0.0
    assert lever.evidence.strip()
    assert lever.measured_effect.strip()


# ------------------------------------------------------------------------- clamp


def test_clamp_holds_at_both_ends_including_the_infinite_ceiling() -> None:
    """`margin.c` is the one lever with no upper bound - "set it as high as you
    like and margin counts all the way up" - so the clamp has to survive an
    infinite `high` without turning a legitimate number into one."""
    c = levers.get("margin.c")
    assert c.low == 1.0
    assert c.high == float("inf")

    assert c.clamp(0.0) == 1.0  # under the floor, pulled up
    assert c.clamp(1.0) == 1.0  # exactly the floor - `just-win`'s constant - kept
    assert c.clamp(18.0) == 18.0  # inside the range now, no longer the floor
    assert c.clamp(32.0) == 32.0  # the shipped default, untouched
    assert c.clamp(1e9) == 1e9  # nothing above is out of range
    assert c.clamp(float("inf")) == float("inf")  # margin counts all the way up

    bounded = levers.get("weights.recency_gamma")
    assert bounded.clamp(-5.0) == bounded.low
    assert bounded.clamp(5.0) == bounded.high
    assert bounded.clamp(bounded.low) == bounded.low
    assert bounded.clamp(bounded.high) == bounded.high
    # Integers and strings-of-numbers both come back as floats, so a config file
    # cannot smuggle a non-float into a design matrix.
    assert isinstance(bounded.clamp(1), float)
