"""The lever registry: every tunable this project will let a reader touch, named in football.

WHY THIS FILE EXISTS. The model has one constraint - be as accurate as the data
allows - and two things it will never do (read a human poll, read the future).
Everything between those is a CHOICE, and a choice that only the author can make
is not transparency, it is an assertion with the source code attached. This
registry turns each of those choices into a named, bounded, defaulted knob that
the site can expose one layer deep, and it is the machine-readable half of
`docs/constraints.md`.

WHAT A LEVER IS, AND WHAT IT IS NOT

A lever is a number the model is genuinely uncertain about, where a reasonable
person could want a different value and the whole pipeline still means something
afterwards. `win_premium` is a lever: how much a win is worth over and above the
scoreboard is a question about football, not about arithmetic. The two
untouchables are NOT levers and do not appear here, because a knob labelled
"include the AP poll: off" is an invitation rather than a guarantee.

EVERY LEVER CARRIES SIX THINGS, and the last two are what make it a product
rather than a config file:

    key          the machine name, which is also the config path
    label        PLAIN FOOTBALL WORDS. Not "phi", not "beta_w". A reader who has
                 never opened a stats book has to know what moving it means.
    surface      which product it acts on - the poll, the projection, or both.
    range        (low, high). Outside it the answer stops being a poll.
    default      the shipped value, and every default here was MEASURED rather
                 than chosen; `evidence` names what measured it.
    sweep        the precomputed values the site may offer without refitting.

WHY conference_identity IS HERE AT ALL, SET TO OFF

Because the honest place for a refusal is beside the thing being refused. Nothing
in the base model knows what a conference is, and that is the fairness spine of
the whole product: conference strength has to EMERGE from results or it is a
brand ranking. But "we could have and did not" is only worth saying if the reader
can see the switch, so it ships as a lever, defaulted off, with the measured cost
of turning it on published beside it rather than asserted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "LEVERS",
    "Lever",
    "defaults",
    "for_surface",
    "get",
    "registry_document",
    "validate",
]

Surface = Literal["poll", "projection", "both"]


def _finite(value: Any) -> Any:
    """`inf` -> None, so a published registry is strict JSON a browser can parse.

    A categorical lever's value is a string and passes through untouched: there is
    no infinity to name and nothing to round.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    return None if value in (float("inf"), float("-inf")) else float(value)


@dataclass(frozen=True)
class Lever:
    """One published knob. Every field is displayed; none is internal bookkeeping.

    TWO KINDS, AND THE SECOND ONE IS NOT A NUMBER. Most levers are a quantity with
    a range: `margin.beta_w` is any points value between 0 and 12 and the ones
    between the detents mean something. `publication.headline_ordering` is not
    that. It is three named orderings, and there is no value between
    `schedule_odds` and `L4_resume` any more than there is a number between two
    questions. A lever with `values` set is CATEGORICAL: `values` is its whole
    domain and also its sweep, `low` and `high` are `None`, and `default` is one of
    the strings.

    IT USED TO BE A 0-OR-1 SWITCH AND THAT WAS WRONG. Encoding the ordering as a
    float meant the registry could express two of the three legal strings and had
    no way at all to say `L4_resume_margin`, which is the ordering
    `configs/recipes/full-merit.toml` ships. A registry that cannot name a board
    the project publishes is not a registry of what a reader may change. Ruled by
    the orchestrator on John's delegation, 2026-08-17, together with the
    `margin.c` floor below.
    """

    key: str
    label: str
    surface: Surface
    #: `None` on a categorical lever, which has no ends to sit between.
    low: float | None
    high: float | None
    default: float | str
    #: What the number means in one sentence, in the second person, no jargon.
    plain: str
    #: What measured the default. A citation to a document or a sample size, never
    #: "chosen" and never blank.
    evidence: str
    #: Values the site may offer without a refit. Empty means continuous-only, or
    #: categorical, in which case `values` is the sweep.
    sweep: tuple[float, ...] = ()
    #: The whole domain of a CATEGORICAL lever, in display order. Empty means the
    #: lever is a quantity and `low`/`high` describe it instead.
    values: tuple[str, ...] = ()
    #: What moving it costs, when that has been measured. Published so a reader
    #: can tell a free choice from an expensive one.
    measured_effect: str = ""

    @property
    def is_categorical(self) -> bool:
        return bool(self.values)

    @property
    def choices(self) -> tuple[Any, ...]:
        """What the site may offer without a refit, whichever kind this lever is."""
        return self.values if self.is_categorical else self.sweep

    def clamp(self, value: Any) -> Any:
        """Pull a quantity back inside its range; REFUSE an illegal category.

        A categorical lever has nothing to clamp toward. The three orderings are
        three different questions rather than three points on a scale, so there is
        no nearest legal value, and silently picking one would answer a question
        the reader did not ask. `configs/default.toml` refuses an unknown ordering
        loudly for the same reason, and this refuses it one layer earlier.
        """
        if self.is_categorical:
            text = str(value)
            if text not in self.values:
                raise ValueError(
                    f"{self.key} is one of {list(self.values)}; got {value!r}. "
                    f"These are named orderings rather than points on a scale, so "
                    f"there is no nearest legal value to fall back to."
                )
            return text
        assert self.low is not None and self.high is not None  # noqa: S101
        return float(min(max(float(value), self.low), self.high))

    def as_dict(self) -> dict[str, Any]:
        # An unbounded top is emitted as `null` rather than `Infinity`. Python's
        # json module will happily write the bare token `Infinity`, which is not
        # JSON, and a browser's JSON.parse rejects the whole document - so the one
        # lever with no upper limit would have taken the registry down with it.
        #
        # `values` is on EVERY row, empty for a quantity, because a consumer that
        # has to test for a field's existence to learn a lever's kind will one day
        # forget to.
        return {
            "key": self.key,
            "label": self.label,
            "surface": self.surface,
            "range": [_finite(self.low), _finite(self.high)],
            "unbounded_above": self.high == float("inf"),
            "default": _finite(self.default),
            "plain": self.plain,
            "evidence": self.evidence,
            "sweep": [_finite(v) for v in self.sweep],
            "values": list(self.values),
            "measured_effect": self.measured_effect,
        }


LEVERS: tuple[Lever, ...] = (
    # ------------------------------------------------------------- the projection
    Lever(
        key="projection.long_memory",
        label="How much the year before last still counts",
        surface="projection",
        low=0.0,
        high=0.6,
        default=0.2,
        plain=(
            "Programs are not rebuilt every August. At 0 the projection only looks at "
            "last season. Turn it up and the season before last gets a say too, which "
            "steadies a team whose one bad year looks like an accident."
        ),
        evidence=(
            "Swept over a 216-cell grid on walk-forward week-1 and weeks-1-to-4 "
            "accuracy, 2022-2025. The marginal gain is monotone but small - about "
            "0.5 points of week-1 accuracy from 0 to 0.4 - and it turns the other way "
            "on FBS-vs-FBS games over four weeks. 0.2 is where the pooled objective "
            "peaks."
        ),
        sweep=(0.0, 0.1, 0.2, 0.25, 0.3, 0.4, 0.5),
        measured_effect=(
            "About +0.5 points of week-1 accuracy against a one-season memory. Inside "
            "the noise band on this many games, and published as such."
        ),
    ),
    Lever(
        key="projection.cross_division_gap",
        label="How far an FCS rating falls when it meets FBS",
        surface="projection",
        low=0.0,
        high=1.5,
        default=1.0,
        plain=(
            "A team that earned its rating against FCS opponents does not carry it "
            "intact into an FBS game. At 1 the projection applies the full gap the "
            "crossover games measured. At 0 it takes the FCS rating at face value, "
            "which is what this poll did until the 2026 board put North Dakota State "
            "tenth."
        ),
        evidence=(
            "13.4 points, standard error 0.6, from 602 FBS-vs-FCS games 2021-2025, "
            "measured net of the model's general under-prediction of mismatches. "
            "src/cfbpoll/projection/crossdivision.py"
        ),
        sweep=(0.0, 0.25, 0.5, 0.75, 1.0, 1.25),
        measured_effect=(
            "Bridge-game accuracy over weeks 1-4 rises from 87.6% to about 94% when "
            "this goes from 0 to 1."
        ),
    ),
    Lever(
        key="projection.promotion_credit",
        label="Credit for being the kind of program that moves up",
        surface="projection",
        low=0.0,
        high=1.5,
        default=1.0,
        plain=(
            "A program that is promoted to FBS is not a random FCS team. It spent "
            "years buying its way to FBS rosters and staff, and the six programs that "
            "have made the jump won back most of the gap in their first season. At 0 "
            "a promoted team is treated like any other FCS team."
        ),
        evidence=(
            "9.8 points, standard error 1.9, from the 68 games six promoted programs "
            "played against FBS opponents in their first FBS season, 2022-2025."
        ),
        sweep=(0.0, 0.25, 0.5, 0.75, 1.0),
        measured_effect=(
            "THIS ONE IS THIN AND THE THINNESS IS THE POINT. Six programs, none rated "
            "within eleven points of North Dakota State, and the accuracy chain cannot "
            "arbitrate it either way: moving it from 0 to 1 changes pooled week-one "
            "accuracy by less than a tenth of a point, because it touches one or two "
            "teams. It is a fairness question wearing a coefficient's clothes, which "
            "is exactly why it is a published lever and why the ceiling below exists."
        ),
    ),
    Lever(
        key="projection.promotion_ceiling",
        label="Cap a promoted team at the best any promoted team has done",
        surface="projection",
        low=0.0,
        high=1.0,
        default=1.0,
        plain=(
            "On, no promoted team is projected above the best first FBS season a "
            "promoted program has actually had. Off, a program rated far above every "
            "previous promotion gets the full credit anyway."
        ),
        evidence=(
            "James Madison in 2022 holds the ceiling at +5.75 against the FBS mean, "
            "which was 32nd in FBS. The credit it guards is fitted on programs whose "
            "FCS-year ratings topped out at +6.0, and North Dakota State sits at +17.4."
        ),
        sweep=(0.0, 1.0),
        measured_effect=(
            "On, North Dakota State projects 33rd for 2026. Off, 16th. This one switch "
            "is the difference between the two defensible answers, and it is an "
            "extrapolation guard rather than an opinion about North Dakota State."
        ),
    ),
    Lever(
        key="projection.returning_production",
        label="How much a returning offence is worth",
        surface="projection",
        low=0.0,
        high=2.0,
        default=1.0,
        plain=(
            "The share of last season's offensive snaps, carries and targets that is "
            "back on the roster. It is offence only, because nobody publishes the "
            "defensive half."
        ),
        evidence="Fitted every run by ordinary least squares; the standard error ships beside it.",
        sweep=(0.0, 0.5, 1.0, 1.5, 2.0),
    ),
    Lever(
        key="projection.coaching_change",
        label="The cost of a new head coach",
        surface="projection",
        low=0.0,
        high=2.0,
        default=1.0,
        plain=(
            "One number for every school that changed head coach. It does not know "
            "whether the new man is any good, and there is no term for how long "
            "anyone has been in the job."
        ),
        evidence=(
            "Fitted every run; on the published fits it has never cleared two "
            "standard errors."
        ),
        sweep=(0.0, 0.5, 1.0, 1.5, 2.0),
    ),
    Lever(
        key="projection.portal",
        label="How much the transfer portal moves a team",
        surface="projection",
        low=0.0,
        high=2.0,
        default=1.0,
        plain=(
            "Bodies out minus bodies in, counted rather than rated. Departures are "
            "recorded well and arrivals are not, so this term is the weakest thing on "
            "the board."
        ),
        evidence="Fitted every run; not distinguishable from zero on any fit yet published.",
        sweep=(0.0, 0.5, 1.0, 1.5, 2.0),
    ),
    Lever(
        key="projection.home_field",
        label="How much home field is worth in August",
        surface="projection",
        low=0.0,
        high=2.0,
        default=1.5,
        plain=(
            "A multiplier on the home-field advantage the projection uses to turn "
            "ratings into game calls. At 1 it believes last season's fitted value "
            "exactly. Above 1 it leans on home field harder, which is the right "
            "direction when the ratings themselves are carried over from a season "
            "that is finished and are therefore spread wider than this season's "
            "truth."
        ),
        evidence=(
            "Swept 0.75 / 1.0 / 1.5 / 2.0 over the same 216-cell grid. Accuracy rises "
            "to 1.5 on three of the four published metrics and falls again at 2.0 on "
            "the largest of them."
        ),
        sweep=(0.0, 0.5, 0.75, 1.0, 1.5, 2.0),
        measured_effect=(
            "About +0.7 points from 1.0 to 1.5, which is inside the noise band on "
            "1,251 games and is reported as a peak rather than a discovery."
        ),
    ),
    # -------------------------------------------------------------------- the poll
    Lever(
        key="margin.c",
        label="Where a blowout stops counting extra",
        surface="poll",
        # THE FLOOR IS 1.0 BECAUSE A PUBLISHED RECIPE SHIPS THERE.
        # `configs/recipes/just-win.toml` sets c = 1.0 and the `margin-c-1`
        # playground variant publishes a board at it, so a registry floor of 18
        # excluded a ranking this project ships and told a reader they could not
        # reach a page they can already open. Ruled by the orchestrator on John's
        # delegation, 2026-08-17. The value is still far outside anything the
        # tuning campaigns searched, and `just-win`'s own tradeoffs say so; a
        # published range is what a reader may choose, not what was fitted.
        low=1.0,
        high=float("inf"),
        default=32.0,
        plain=(
            "Winning by 40 is better than winning by 20. Winning by 60 is barely "
            "better than winning by 40. This is where the curve flattens; set it as "
            "high as you like and margin counts all the way up, or drop it to 1 and "
            "beating somebody by 70 is worth about what beating them by 1 is worth."
        ),
        evidence=(
            "Fitted 2026-08-12 over a 416-cell factorial on the tune seasons. ADR 0007. "
            "The floor of the published range is `just-win`'s shipped constant rather "
            "than a searched value."
        ),
        # THE SWEEP IS THE LEVER GRID'S DETENTS, EXACTLY. This field's promise is
        # "values the site may offer without a refit", and since the lever grid
        # exists that promise is a fact about files on disk rather than an
        # intention. `tests/unit/test_lever_grid.py` asserts the two are equal.
        sweep=(1.0, 18.0, 24.0, 32.0, 48.0, float("inf")),
        measured_effect=(
            "The whole published grid is worth 0.135 points of margin error, best "
            "cell to worst. On 2025 week 16, moving it alone to 24 or 48 leaves a "
            "board the 0.985 tau line calls a convention; 1 and uncapped are dials."
        ),
    ),
    Lever(
        key="margin.beta_w",
        label="How much a win is worth on its own",
        surface="poll",
        low=0.0,
        high=12.0,
        default=7.0,
        plain=(
            "Points added to the winner for the simple fact of winning, before any "
            "margin counts. At 0 this is a scoring-margin ranking. Turn it up and a "
            "one-point win starts to look like a comfortable one."
        ),
        evidence="Fitted 2026-08-12 on the same factorial. ADR 0007.",
        sweep=(0.0, 3.0, 7.0, 12.0),
        measured_effect=(
            "Doubling it moved Kendall's tau against the incumbent no lower than 0.994."
        ),
    ),
    Lever(
        key="weights.recency_gamma",
        label="Whether September still counts in December",
        surface="poll",
        low=0.5,
        high=1.0,
        default=1.0,
        plain=(
            "At 1 every game counts the same all season, which is what a poll about "
            "what you earned should do. Below 1 the season decays and recent form "
            "takes over."
        ),
        evidence="Available and off. Report 02 section 3.1.",
        sweep=(0.7, 0.8, 0.9, 0.95, 1.0),
    ),
    Lever(
        key="publication.headline_ordering",
        label="What sorts the table",
        surface="poll",
        # CATEGORICAL, AND ALL THREE LEGAL STRINGS. It was a 0-or-1 float, which
        # could express two of the three and had no way to say `L4_resume_margin`
        # at all - the ordering `configs/recipes/full-merit.toml` ships. Ruled by
        # the orchestrator on John's delegation, 2026-08-17. The strings are
        # `publish/poll.ORDERING_LAYER`'s keys and nothing else is accepted
        # anywhere in the pipeline.
        low=None,
        high=None,
        default="schedule_odds",
        values=("schedule_odds", "L4_resume", "L4_resume_margin"),
        plain=(
            "Three different questions, and you pick which one the table answers. "
            "Schedule odds asks how hard that season was to survive, and it is what "
            "the published poll sorts on. The wins-based resume asks what your record "
            "earned against that schedule, which puts every unbeaten team above every "
            "team with a loss. The margin-aware resume asks how good the results say "
            "you are, which will rank a good team with losses above an unbeaten one."
        ),
        evidence=(
            "ADR 0005 and docs/analysis/headline-ordering-study.md, which is where "
            "the house choice came from. The two alternates are that study's "
            "candidates A and B, and both ship today: `just-win` sorts on the "
            "wins-based resume and `full-merit` on the margin-aware one."
        ),
        measured_effect=(
            "Under the resume ordering, retroactive re-ranking moved no unbeaten team "
            "a single place from week 11 of 2023 onward. On 2025 week 16 both "
            "alternates are dials against the 0.985 line: the wins-based resume at "
            "tau 0.9793, the margin-aware one at 0.8425, which is the largest single-"
            "knob move any published lever makes."
        ),
    ),
    # ------------------------------------------------------- the one that stays off
    Lever(
        key="model.conference_identity",
        label="Let the model know which conference a team is in",
        surface="both",
        low=0.0,
        high=1.0,
        default=0.0,
        plain=(
            "Off. Nothing in the base model knows what a conference is, and that is "
            "the point: conference strength has to be earned on the field and read "
            "off the results, never assumed from the letters on the jersey. The "
            "switch is published so the refusal is checkable rather than claimed."
        ),
        evidence=(
            "`cfbpoll audit-features` rebuilds all seven design matrices without "
            "`conference_game` before every fit and requires bit-identical output. "
            "The refusal is a result, recomputed, not a promise."
        ),
        sweep=(0.0,),
        measured_effect=(
            "Not adopted. Any accuracy it might buy has to be measured and shown to "
            "the owner before this default may move off zero."
        ),
    ),
)

_BY_KEY: dict[str, Lever] = {lever.key: lever for lever in LEVERS}


def get(key: str) -> Lever:
    """The lever, or a KeyError naming every key that does exist."""
    try:
        return _BY_KEY[key]
    except KeyError:
        raise KeyError(f"unknown lever {key!r}; registered: {sorted(_BY_KEY)}") from None


def defaults() -> dict[str, float | str]:
    """key -> shipped value. What the published board was produced with.

    A categorical lever contributes its string, so this dict now agrees with
    `configs/default.toml` field for field. It did not while the ordering was
    encoded as `1.0`, and a registry whose "shipped value" is a number the config
    has never held is a registry a reader cannot check against the config.
    """
    return {lever.key: lever.default for lever in LEVERS}


def for_surface(surface: Surface) -> tuple[Lever, ...]:
    """Every lever acting on one product, `both` included."""
    return tuple(
        lever for lever in LEVERS if lever.surface in (surface, "both")
    )


def validate(settings: dict[str, Any]) -> dict[str, Any]:
    """Clamp to published ranges and reject unknown keys. Never silently ignores one.

    An unknown key is an error rather than a no-op because the most likely cause
    is a typo in a lever name, and a typo that silently leaves the default in
    place produces a board the reader thinks they changed and did not.

    An unknown VALUE on a categorical lever is an error for the same reason and
    raises `ValueError` out of `Lever.clamp`. A quantity outside its range is
    clamped rather than refused, because there the ends are real settings and
    "as far as this poll will go" is a meaningful answer.
    """
    unknown = sorted(set(settings) - set(_BY_KEY))
    if unknown:
        raise KeyError(f"unknown lever(s) {unknown}; registered: {sorted(_BY_KEY)}")
    return {key: _BY_KEY[key].clamp(value) for key, value in settings.items()}


def registry_document() -> dict[str, Any]:
    """The whole registry, ready to ship as JSON beside a board."""
    return {
        "levers": [lever.as_dict() for lever in LEVERS],
        "untouchable": [
            {
                "rule": "No human polls, ever.",
                "detail": (
                    "No AP, coaches or committee ranking may reach any design matrix "
                    "of either product. They are comparison targets and never fitting "
                    "targets. There is no lever for this and there will not be one."
                ),
            },
            {
                "rule": "No future data, ever.",
                "detail": (
                    "Every published number for a given week is computable from games "
                    "played before it. Walk-forward honesty is not a ceremony here, it "
                    "is what makes an accuracy figure mean anything."
                ),
            },
        ],
        "note": (
            "Defaults are measured, not chosen. Every lever carries what measured it "
            "and, where it has been swept, what moving it costs."
        ),
    }
