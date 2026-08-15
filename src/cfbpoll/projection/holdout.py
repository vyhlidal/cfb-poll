"""The rule the holdout was always for: a season may be READ, never FITTED ON.

WHAT A HOLDOUT BANS. Tuning. Only tuning. Its promise is exactly one sentence -
"no number in `configs/default.toml` was chosen after seeing this season" - and
it says nothing whatever about whether the season may be ranked, rendered,
published or graded. This module was written on 2026-08-12 when that distinction
had to be argued carefully, because 2025 was sealed and the 2026 Projection
needed 2025's fitted ratings to regress toward. ADR 0010 §3 made the argument.
ADR 0012 made it unnecessary and left the mechanism in place.

WHERE THINGS STAND, and it is simpler than what it replaced:

  2021-2023   the constants were fitted here.
  2024        validated, twice, both times announced.
  2025        SCORED ONCE on 2026-08-15, with the constants already frozen. The
              scorecard is `demo/2025-holdout-scorecard.md`, published whatever
              it said. The season is now open: rank it, render it, grade against
              it. `holdout_seasons` is empty and `walkforward` no longer refuses
              it, because the shot it was protecting has been taken.
  2026        ranked every week and fitted to never. The site publishes a 2026
              board weekly and grades the 2026 Projection against 2026 results,
              so "sealed" would be a public contradiction. `no_fit_seasons`
              carries the narrow, mechanical version of the ban instead.

THE TEST THAT DOES THE WORK is `assert_no_target_is_locked` below, and its
semantics never changed: the recipe may READ any season, and it may never FIT ON
a no-fit one. A design transition whose TARGET season is locked would mean
coefficients chosen against that season's outcomes, and it raises `HoldoutLocked`
- the same exception type the backtest raises, deliberately, because it is the
same breach. Only the list it reads got wider and better named.

THE HONESTY CLAUSE, AND IT IS STILL THE IMPORTANT ONE. The recipe published for
2026 is designed on the 2021->2022, 2022->2023 and 2023->2024 transitions.
**That list did not move when 2025 opened.** The 2024->2025 transition was absent
while 2025 was sealed and it is absent now, which is what lets the 2025
Projection published beside it claim to be an out-of-sample application of a
frozen recipe rather than a fit wearing a projection's clothes. Anyone extending
this must keep that true or must change this paragraph, in public, in the same
commit.

ADR 0010 carries the original argument; ADR 0012 carries the transition.
"""

from __future__ import annotations

from typing import Any

from cfbpoll.backtest.walkforward import HoldoutLocked

__all__ = [
    "HOLDOUT_USE",
    "assert_no_target_is_locked",
    "holdout_seasons",
    "no_fit_seasons",
    "scored_holdouts",
    "source_season_note",
]

#: The single sanctioned use, recorded verbatim on every artifact that touches a
#: locked season. A string is not a safeguard; the safeguard is
#: `assert_no_target_is_locked`. This exists so a reader of a published file can
#: tell, without reading this module, exactly which act was performed.
HOLDOUT_USE = "fitted_ratings_as_projection_input"


def no_fit_seasons(config: dict[str, Any]) -> set[int]:
    """Every season no fitting path may take as its RESPONSE.

    The union of two lists, because they are the same ban arriving from two
    directions and a caller should never have to know which one caught it:

      `holdout_seasons` when `holdout_locked`   a season sealed against SCORING,
                                                which implies it is sealed
                                                against fitting too.
      `no_fit_seasons`  when `no_fit_locked`    a season that is scored, ranked
                                                and published every week and
                                                must still never be fitted on.
                                                2026 is this case and it is the
                                                one the project actually lives
                                                in now (ADR 0012).

    An empty set is a legitimate answer and means no season is barred, which is
    not the same as the guard being off - `assert_no_target_is_locked` still runs
    and still has nothing to catch.
    """
    backtest = config.get("backtest") or {}
    locked: set[int] = set()
    if bool(backtest.get("holdout_locked", False)):
        locked |= {int(s) for s in (backtest.get("holdout_seasons") or [])}
    if bool(backtest.get("no_fit_locked", False)):
        locked |= {int(s) for s in (backtest.get("no_fit_seasons") or [])}
    return locked


#: The name this function had before ADR 0012, kept because it is the name every
#: caller and every published provenance block already uses. It was never really
#: about the holdout: it was about what may be fitted on, which is what the
#: holdout happened to imply while one existed.
holdout_seasons = no_fit_seasons


def scored_holdouts(config: dict[str, Any]) -> dict[int, str | None]:
    """Seasons that WERE sealed and have since been scored, with the date.

    Published rather than dropped. A season that stops being a holdout does not
    stop having been one, and a reader of a 2026 artifact that regresses toward
    2025 is owed the sentence "this was the holdout, it was scored once on this
    date, here is the scorecard" instead of a silence where the provenance used
    to be.
    """
    backtest = config.get("backtest") or {}
    when = backtest.get("holdout_scored_on")
    return {int(s): (str(when) if when else None) for s in (backtest.get("holdout_scored") or [])}


def assert_no_target_is_locked(
    transitions: list[tuple[int, int]], config: dict[str, Any]
) -> None:
    """Refuse to FIT the recipe on a locked season. Reading one is a different act.

    `transitions` is the list of (source_season, target_season) pairs the recipe
    is about to fit coefficients on. The TARGET is where the response comes from,
    so a locked target means a coefficient chosen against that season's outcomes.
    The SOURCE is only an input and is deliberately not checked - that permission
    is the whole point of this module, and it is documented in ADR 0010 and ADR
    0012 rather than inferred from silence.

    Today the list this guards is `[backtest].no_fit_seasons = [2026]`, the season
    the recipe PREDICTS. Fitting on it would turn a projection into a description
    of what already happened, which is the same failure the holdout guarded
    against and is why it raises the same exception.
    """
    locked = no_fit_seasons(config)
    trespass = sorted({int(target) for _, target in transitions if int(target) in locked})
    if trespass:
        raise HoldoutLocked(
            f"the projection recipe would fit on no-fit season(s) {trespass}. "
            "READING a season's fitted ratings as a projection INPUT is always "
            "allowed (projection_source_season, ADR 0010); FITTING a coefficient "
            "against a season's OUTCOMES when that season is one the project "
            "publishes a live board and a live grade for is the tuning act the "
            "holdout existed to prevent, and it is the same breach the backtest "
            "refuses. Design the recipe on transitions that target a settled "
            "season. See docs/adr/0012-2025-opens.md."
        )


def source_season_note(source_season: int, config: dict[str, Any]) -> dict[str, Any]:
    """The provenance block every projection artifact carries. Never silent.

    When the source season is locked this says so IN THE ARTIFACT, names the
    sanctioned use, and states the claim the reader is entitled to hold us to.
    When it is not locked the same block is emitted with `locked: false`, so the
    field's absence can never be mistaken for the field being false.

    A season that USED to be the holdout gets a third case, and it is the one
    that matters today. 2025 is no longer locked, so the careful ADR 0010 §3
    argument no longer has to be made - but a reader looking at a 2026 projection
    built on 2025's ratings should still be told that 2025 was the sealed season,
    that it was scored exactly once on a stated date, and where the scorecard is.
    Dropping that sentence the moment it stopped being legally required would be
    the quiet kind of dishonesty.
    """
    locked = no_fit_seasons(config)
    is_locked = int(source_season) in locked
    scored = scored_holdouts(config)
    was_holdout = int(source_season) in scored

    if is_locked:
        claim = (
            "The recipe's coefficients were fitted on transitions whose target "
            "seasons exclude every locked season; this season's fitted ratings "
            "enter only as an input. No metric was read off it and no constant "
            "was chosen against it. See docs/adr/0010-projection-and-poll.md."
        )
    elif was_holdout:
        claim = (
            f"This season was the project's sealed holdout. It was scored exactly "
            f"once, on {scored[int(source_season)]}, with every constant already "
            "frozen, and the result is published at "
            "demo/2025-holdout-scorecard.md whatever it says. The recipe's "
            "coefficients were fitted on transitions that exclude it and were not "
            "touched when it opened. See docs/adr/0012-2025-opens.md."
        )
    else:
        claim = "The source season is not held out; no special provenance applies."

    return {
        "projection_source_season": int(source_season),
        "source_season_is_holdout": is_locked,
        "source_season_was_scored_holdout": was_holdout,
        "scored_on": scored.get(int(source_season)),
        "holdout_use": HOLDOUT_USE if is_locked else None,
        "holdout_seasons": sorted(locked),
        "claim": claim,
    }
