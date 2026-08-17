"""THE PROJECTION. A labelled prediction. It is not the Poll, and it never will be.

This package is a SECOND PRODUCT, and the whole reason it can exist inside a
repository whose first constraint is "no reputation priors" is that it is
separate all the way down: separate inputs, separate module, separate artifact,
separate sentence on every rendered surface, and a separate half of the leakage
audit that is mechanically hostile to the other half.

  THE POLL       ranks what a team HAS DONE, from on-field results only, with
                 nothing carried across a season boundary. Constraints 1-5,
                 docs/constraints.md. Its design matrices may not contain a
                 single column this package produces.

  THE PROJECTION ranks what a team is EXPECTED TO DO, before anyone has played,
                 from last season's fitted ratings plus every knowable offseason
                 change. It is a modeled prediction, it is labelled as one
                 everywhere it appears, and its job in the product is to BE
                 GRADED IN PUBLIC by the Poll it is not allowed to touch.

ADR 0010 records the separation and the holdout reasoning. `docs/constraints.md`
is unchanged by this package, because nothing here is allowed near it.

WHY THIS IS NOT A BACK DOOR INTO CONSTRAINT 2. The banned-input table bans
returning production, prior-season ratings and coaching tenure *from the poll's
published rankings*. This package uses all three, and the audit in
`validate/leakage.py` is what keeps that from being a slogan: a projection input
appearing anywhere near a poll layer's frame is a VIOLATION, not a warning, and
`tests/unit/test_projection_separation.py` plants one in a poll design matrix and
asserts the audit names it.

WHAT THE PROJECTION MAY NOT USE EITHER, and this is the line that shows the
separation is a design and not an excuse: human polls. The AP preseason top 25 is
this product's headline BASELINE - the thing we are trying to beat - and a
baseline that is also an input measures nothing. `PROJECTION_BANNED` in the audit
enforces it, along with the third-party fitted ratings (SP+, FPI, CFBD's PPA and
CORE) that the poll already refuses, for the same reason it refuses them: a
projection resting on somebody else's retrained model is not our projection.

THE ROUGH-BY-DESIGN CLAUSE. This is v1 and it is a four-term linear recipe with
every coefficient published. It will be wrong. The product is not the ranking;
the product is the ranking PLUS the grading loop in `grade.py` that says, week by
week, "we thought this, here is what we now know, and here is which offseason
assumption was wrong."
"""

from __future__ import annotations

__all__ = ["PROJECTION_VERSION"]

#: Stamped on every artifact this package writes, exactly as each model layer
#: stamps its own. A projection published under one recipe must never be
#: mistakable for one published under another - the grading loop is season-over-
#: season and a silent recipe change would make the whole record meaningless.
#:
#: 2.0.0 (ADR 0013) is a MAJOR bump and it is loud on purpose. Two measurement
#: defects were repaired and both moved every published number:
#:
#:   the Power definition   1.0.0 fitted and predicted `l4_resume.power_source`
#:                          over a whole season at once and graded against
#:                          `retro.season_power[final]`, the walk-forward surface
#:                          the poll publishes. Two scales, one arrow. 2.0.0 uses
#:                          the published one on all three sides.
#:   the coaching term      1.0.0 read `/coaches?year=Y` after season Y and
#:                          picked the school's coach by games played, so a
#:                          mid-season interim who worked more games than the man
#:                          he replaced turned an October firing into an August
#:                          coaching change. 2.0.0 decides the August head coach
#:                          from prior-season continuity, which is knowable in
#:                          August, and `validate/leakage.py` now has a TEMPORAL
#:                          guard that fails the build on a repeat.
#:
#: The coefficients moved, so every artifact under 1.0.0 is superseded rather
#: than corrected in place. `demo/2025-projection-grading.md` under 1.0.0 said
#: last season's rating was weighted TOO STRONG; on the corrected surfaces all
#: four terms come back priced about right.
PROJECTION_VERSION = "projection-3.0.0"

#: 3.0.0 (ADR 0014, the liberation) is the second MAJOR bump and it moves every
#: number on the board. Three changes, each measured before it was adopted:
#:
#:   the cross-division gap   an FCS-earned rating no longer transplants to FBS at
#:                            face value. 602 crossover games price the move at
#:                            13.4 points; 68 games from six promoted programs give
#:                            9.8 of it back; and no promoted team is projected
#:                            above the best first FBS season any promoted program
#:                            has actually had. North Dakota State goes from 9th to
#:                            33rd. `projection/crossdivision.py`.
#:   a second season of memory the projection reads the year before last at weight
#:                            0.2 as well as last season.
#:   the freeze dies          the recipe refits whenever a season closes, so
#:                            2024->2025 is now a design transition. The vintage
#:                            record replaces the freeze: every board ever
#:                            published stays up with the coefficients it ran under.
#:
#: Measured, walk-forward, 2022-2025: week-one accuracy over every game with an FBS
#: team in it goes from 82.4% to 86.9%, against 82.3% for the AP's August ballot.
