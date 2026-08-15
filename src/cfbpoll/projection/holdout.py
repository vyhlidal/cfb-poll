"""`projection_source_season` - the one named path that reads a locked season.

THE PROBLEM, STATED SO IT CANNOT BE WAVED AWAY. 2025 is this project's sealed
holdout (`[backtest].holdout_seasons`, `holdout_locked = true`). The 2026
Projection needs a prior-season rating to regress toward, and the only prior
season is 2025. So the Projection has to read a fitted quantity out of the season
the backtest is forbidden to touch.

WHY THAT IS NOT A BREACH, and why the argument is narrow rather than convenient.
A holdout protects ONE thing: the integrity of hyperparameter tuning. Its promise
is "no number in `configs/default.toml` was chosen after seeing 2025." Two acts
are being distinguished, and they are genuinely different:

  SCORING on 2025      running the walk-forward harness over 2025 games and
                       reading MAE / SU / Brier / calibration off the result.
                       This is what would burn the single shot, because a metric
                       read is what a human then tunes against. STILL LOCKED, by
                       `walkforward.HoldoutLocked`, which this module does not
                       touch and cannot reach.

  READING 2025's       taking the L3 Power ratings that the 2025 season produced
  FITTED RATINGS       and using them as an INPUT to a different product, whose
  AS AN INPUT          coefficients were fitted on 2021-2024 and are frozen
                       before 2025 is opened. Nothing about 2025 selects a
                       constant. No metric is read. The holdout's promise is
                       untouched.

The test that separates them is mechanical and it is `assert_no_target_is_locked`
below: the recipe may READ a locked season, and it may never FIT ON one. A design
transition whose TARGET season is locked would mean coefficients chosen against
2025 outcomes, which is exactly the tuning act the lock exists to prevent, and it
raises `HoldoutLocked` - the same exception type the backtest raises, deliberately,
because it is the same breach.

THE HONESTY CLAUSE, AND IT IS THE IMPORTANT ONE. The recipe published for 2026 is
designed on the 2021->2022, 2022->2023 and 2023->2024 transitions. 2025 is not
among the target seasons and the 2024->2025 transition IS NOT FITTED, precisely
so this paragraph can say what it says. Anyone extending this must keep that
true or must change this sentence, in public, in the same commit. If a future
version validates the recipe on a window that includes 2025, the artifact has to
say so in the same breath as the ranking, because "we tuned nothing on 2025" and
"we checked ourselves against 2025" are different claims and only one of them is
being made here.

ADR 0010 carries the full argument and the owner's decision.
"""

from __future__ import annotations

from typing import Any

from cfbpoll.backtest.walkforward import HoldoutLocked

__all__ = [
    "HOLDOUT_USE",
    "assert_no_target_is_locked",
    "holdout_seasons",
    "source_season_note",
]

#: The single sanctioned use, recorded verbatim on every artifact that touches a
#: locked season. A string is not a safeguard; the safeguard is
#: `assert_no_target_is_locked`. This exists so a reader of a published file can
#: tell, without reading this module, exactly which act was performed.
HOLDOUT_USE = "fitted_ratings_as_projection_input"


def holdout_seasons(config: dict[str, Any]) -> set[int]:
    """The locked seasons, or an empty set when the lock is off."""
    backtest = config.get("backtest") or {}
    if not bool(backtest.get("holdout_locked", False)):
        return set()
    return {int(s) for s in (backtest.get("holdout_seasons") or [])}


def assert_no_target_is_locked(
    transitions: list[tuple[int, int]], config: dict[str, Any]
) -> None:
    """Refuse to FIT the recipe on a locked season. Reading one is a different act.

    `transitions` is the list of (source_season, target_season) pairs the recipe
    is about to fit coefficients on. The TARGET is where the response comes from,
    so a locked target means a coefficient chosen against holdout outcomes. The
    SOURCE is only an input and is deliberately not checked - that permission is
    the whole point of this module, and it is documented in ADR 0010 rather than
    inferred from silence.
    """
    locked = holdout_seasons(config)
    trespass = sorted({int(target) for _, target in transitions if int(target) in locked})
    if trespass:
        raise HoldoutLocked(
            f"the projection recipe would fit on held-out season(s) {trespass}. "
            "Reading a locked season's fitted ratings as a projection INPUT is "
            "sanctioned (projection_source_season, ADR 0010); fitting a "
            "coefficient against a locked season's OUTCOMES is the tuning act "
            "the holdout exists to prevent, and it is the same breach the "
            "backtest refuses. Design the recipe on unlocked transitions."
        )


def source_season_note(source_season: int, config: dict[str, Any]) -> dict[str, Any]:
    """The provenance block every projection artifact carries. Never silent.

    When the source season is locked this says so IN THE ARTIFACT, names the
    sanctioned use, and states the claim the reader is entitled to hold us to.
    When it is not locked the same block is emitted with `locked: false`, so the
    field's absence can never be mistaken for the field being false.
    """
    locked = holdout_seasons(config)
    is_locked = int(source_season) in locked
    return {
        "projection_source_season": int(source_season),
        "source_season_is_holdout": is_locked,
        "holdout_use": HOLDOUT_USE if is_locked else None,
        "holdout_seasons": sorted(locked),
        "claim": (
            "The recipe's coefficients were fitted on transitions whose target "
            "seasons exclude every locked season; this season's fitted ratings "
            "enter only as an input. No metric was read off it and no constant "
            "was chosen against it. See docs/adr/0010-projection-and-poll.md."
            if is_locked
            else "The source season is not held out; no special provenance applies."
        ),
    }
