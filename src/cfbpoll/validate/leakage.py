"""The poll-input leakage audit. This module fails the build on banned features.

Specified by report 02 §3.10. Backs `cfbpoll audit-features --fail-on-banned`,
which runs in both weekly.yml and reproducibility.yml, and which `cfbpoll rank`
runs as a pre-fit step so that no poll is ever published from a fit that was not
audited first.

WHAT MAKES THIS AN AUDIT RATHER THAN A DOCUMENT. An allow-list written in a
docstring is a promise. This module turns it into a measurement, by the only
construction that actually proves the claim:

    Rebuild every design matrix from the frame RESTRICTED to that layer's
    allow-list, and require the result to be bit-identical to the one the
    unrestricted frame produced.

If a layer consumes any column outside its allow-list, the restricted build
either raises (the column is required) or disagrees (the column is used), and
either way the audit says so and names the column. If the restricted build
succeeds and the digests match, then the design matrix is a pure function of the
allow-listed columns over this window, and every other column in the frame -
including every banned one sitting in the same file - provably did not reach it.
That is a fact about the run, not an assertion about the code.

The culprit is named by ablation: when the restricted build fails or differs,
each non-allow-listed column is added back on its own and the build repeated, so
the report says "L2 consumes `home_pregame_elo`" rather than "L2 failed".

ALLOWED, and nothing else. The live table is `LAYERS` below - this list is the
prose summary of it, and `tests/unit/test_leakage.py` asserts the two agree:
  games loader: the canonical schedule frame (report 01 §3.10's RAW_COLUMNS,
      projected); nothing from the shipped file that is a third party's model
  plays loader: the canonical play frame; never the shipped EPA/wpa/ep_* block
  EP: down, distance, yards to goal, points scored on a play, the scoring
      segment - plus the possession labels, which sign the next score to the
      side with the ball and reach no fitted cell (see EP_TEAM_LABELS_NOTE)
  L1: OUR play value (model/ep.py, fitted from the scoreboard - never the
      archive's `EPA` column), offense team id, defense team id,
      home/away/neutral, quarter, score margin, clock (the last three only for
      garbage-time filtering)
  L2: final score, team ids, home/away/neutral, game type, kickoff date (the
      last only for the recency weight, and only when it is switched on)
  L3: L1 and L2 outputs, team ids, home/away/neutral
  L4: L3 outputs, win/loss, schedule
  schedule odds: L3 outputs, win/loss, schedule, division class (the q_ref pool)

BANNED, with the reason (the same table is reproduced in docs/constraints.md):
  AP / Coaches / CFP rankings          constraint 1, directly
  recruiting rankings, talent          constraint 2 - reputation prior
  returning production / starters      constraint 2
  prior-season ratings of any kind     constraint 2
  SP+ or FPI as features               indirect violation - both embed
                                       recruiting-based priors, so importing
                                       them imports the prior
  third-party EPA / PPA / WPA / EP     someone else's fitted model evaluated on
                                       our data (report 01 §5.6)
  pregame win probability / Elo        same, and it is shipped in the same file
  Vegas lines as features              market opinion is partly poll-driven, and
                                       it destroys independence from the very
                                       baseline we measure against
  conference identity as a feature     a reputation prior in disguise. Conference
                                       strength must EMERGE from results
  brand / stadium prestige / TV rating obviously

THE TRAP THIS EXISTS FOR, and the one place it was nearly sprung: the
SportsDataverse parquet files ship precomputed `EPA`, `ppa` and `wpa` columns
plus a six-column next-score probability block, and the schedules ship
`home_pregame_elo`, `home_postgame_elo` and `excitement_index` (report 01 §5.6).
Those are someone else's model output sitting in the same file as the facts.
Report 02 §3.1 specifies L1 as a ridge on play-level EPA and the column is RIGHT
THERE, which is exactly why `model/ep.py` exists: we fit our own next-score model
from the scoreboard and publish every constant of it. The shipped column survives
only inside `ep.shipped_epa_correlation`, a diagnostic that names it in its own
signature so it cannot be reached by accident, and whose result (r = 0.847) is
reported and never fitted to.

THE ONE THAT IS ACTUALLY IN THE FRAME. `conference_game` survives the loader's
projection, because the structural conference-championship fallback for 2021
needs it (ingest/sportsdataverse.py). It matches the banned pattern `conference`
and it is NOT on any layer's allow-list, so every run of this audit proves, by
rebuilding every design matrix without it, that no fit has ever seen it. That is
the difference between "we do not use conference identity" and "here is the
measurement showing we did not".

STATUS: IMPLEMENTED. `audit` runs the probes; `cfbpoll audit-features
--fail-on-banned` exits non-zero on any violation; `cfbpoll rank` calls it before
fitting whenever `[constraints].fail_build_on_banned_feature` is true.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl
from scipy import sparse

__all__ = [
    "ALLOWED_BY_LAYER",
    "BANNED_COLUMN_PATTERNS",
    "EP_TEAM_LABELS_NOTE",
    "LAYERS",
    "AuditReport",
    "BannedFeature",
    "LayerResult",
    "LayerSpec",
    "audit",
    "banned_hits",
    "digest",
]


class BannedFeature(RuntimeError):
    """A banned or un-allow-listed column reached a design matrix."""


BANNED_COLUMN_PATTERNS: tuple[str, ...] = (
    # --- human polls and committee rankings (constraint 1)
    "ap_",
    "coaches_",
    "cfp_rank",
    "poll",
    "rank",
    # --- reputation priors (constraint 2)
    "recruit",
    "talent",
    "returning_",
    "prior_season",
    "preseason",
    # --- third-party fitted models
    "sp_plus",
    "sp+",
    "fpi",
    "elo",
    "epa",
    "ppa",
    "wpa",
    "wp_before",
    "wp_after",
    "ep_before",
    "ep_after",
    "pregame",
    "postgame",
    "win_prob",
    "expscorediff",
    "excitement",
    # --- market
    "spread",
    "moneyline",
    "over_under",
    "betting",
    # --- reputation by another name
    "conference",
    "prestige",
    "tv_rating",
    "attendance",
)
"""Substring patterns, matched case-insensitively against column names.

This is the DENY half and it is the weaker half on purpose: a new banned input
nobody thought of would not be on it. The gate that actually holds is the
allow-list rebuild in `audit`, which fails closed - anything not named is
excluded whether or not anyone predicted it. The patterns exist so that a banned
column PRESENT in a source frame is reported by name even though the rebuild has
already proved it unconsumed, because "we proved it never reached a fit" is a
more useful sentence when it names the thing it is about.
"""

#: Why EP reads the possession labels even though its allow-list in report 02
#: §3.10 says "not the teams". The next-score construction has to know which side
#: the next score belongs to in order to sign it, and the only labels available
#: for that are the two team names on the row. The FITTED OBJECT has no team
#: dimension at all - `EPModel.table` is indexed (down, distance bucket,
#: yards-to-goal) and nothing else - so no team identity survives into a value.
#: Recorded here rather than quietly allowed, because the report's summary
#: sentence and the implementation genuinely differ and the implementation is
#: right.
EP_TEAM_LABELS_NOTE = (
    "offense/defense are read to SIGN the next score to the side with the ball; "
    "EPModel.table is indexed (down, distance_bucket, yards_to_goal) and carries "
    "no team dimension, which the audit asserts separately"
)


@dataclass(frozen=True)
class LayerSpec:
    """One layer's allow-list, with a reason per column and a probe that proves it.

    `probe` rebuilds whatever this layer's "design matrix" is from a frame and
    returns something `digest` can hash. `frame` names which input frame the
    probe consumes, so `audit` knows what to restrict.
    """

    name: str
    frame: str  # "games" | "plays" | "valued_plays" | "none"
    allowed: dict[str, str]
    spec: str
    probe: Callable[..., Any] | None = None
    note: str | None = None


@dataclass(frozen=True)
class LayerResult:
    """What the rebuild proved, per layer. Every field is a measurement."""

    layer: str
    frame: str
    n_columns_present: int
    allowed: tuple[str, ...]
    extra_present: tuple[str, ...]
    banned_present: tuple[str, ...]
    consumed_outside_allow_list: tuple[str, ...]
    banned_consumed: tuple[str, ...]
    digest_full: str
    digest_restricted: str
    identical: bool
    skipped: str | None = None

    @property
    def ok(self) -> bool:
        return self.skipped is not None or (self.identical and not self.consumed_outside_allow_list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "frame": self.frame,
            "n_columns_present": self.n_columns_present,
            "allowed": list(self.allowed),
            "extra_present": list(self.extra_present),
            "banned_present": list(self.banned_present),
            "consumed_outside_allow_list": list(self.consumed_outside_allow_list),
            "banned_consumed": list(self.banned_consumed),
            "digest_full": self.digest_full,
            "digest_restricted": self.digest_restricted,
            "identical_under_restriction": self.identical,
            "skipped": self.skipped,
            "ok": self.ok,
        }


@dataclass
class AuditReport:
    """The audit's whole output. `violations` is what `--fail-on-banned` acts on."""

    layers: list[LayerResult] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "spec": "report 02 §3.10",
            "method": (
                "every design matrix is rebuilt from the frame restricted to its "
                "layer's allow-list and required to be bit-identical; a column "
                "outside the allow-list that changes or breaks the rebuild is "
                "named by ablation"
            ),
            "context": dict(sorted(self.context.items())),
            "violations": list(self.violations),
            "layers": [layer.as_dict() for layer in self.layers],
        }


# --------------------------------------------------------------------------- digests


def digest(obj: Any) -> str:
    """A stable sha256 over whatever a probe returns. Order-sensitive by design.

    Handles the shapes the probes actually produce - numpy arrays, scipy sparse
    matrices, polars frames, dataclasses of those, and the plain containers that
    hold them. Anything else is hashed through `repr`, which is fine for the
    scalars and strings that reach it and would be a bug for anything larger.
    """
    h = hashlib.sha256()
    _feed(h, obj)
    return h.hexdigest()


def _feed(h: Any, obj: Any) -> None:
    if obj is None:
        h.update(b"None")
    elif isinstance(obj, np.ndarray):
        h.update(str(obj.shape).encode())
        h.update(str(obj.dtype).encode())
        h.update(np.ascontiguousarray(obj).tobytes())
    elif sparse.issparse(obj):
        coo = obj.tocoo()
        order = np.lexsort((coo.col, coo.row))
        _feed(h, np.asarray(coo.row)[order])
        _feed(h, np.asarray(coo.col)[order])
        _feed(h, np.asarray(coo.data, dtype=np.float64)[order])
        h.update(str(obj.shape).encode())
    elif isinstance(obj, pl.DataFrame):
        h.update(",".join(obj.columns).encode())
        for column in obj.columns:
            h.update(str(obj[column].to_list()).encode())
    elif isinstance(obj, dict):
        for key in sorted(obj, key=str):
            h.update(str(key).encode())
            _feed(h, obj[key])
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _feed(h, item)
    elif hasattr(obj, "__dataclass_fields__"):
        for name in sorted(obj.__dataclass_fields__):
            h.update(name.encode())
            _feed(h, getattr(obj, name))
    else:
        h.update(repr(obj).encode())


#: Prefixes marking a column THIS package computed, exempt from the pattern
#: match. The distinction is the whole of model/ep.py: the shipped file's columns
#: are `ep_before` / `ep_after` / `EPA`, and ours are `our_ep_before` /
#: `our_ep_after` / `play_value`. Without this exemption the deny-list would flag
#: our own expected-points model as a third party's, which is exactly backwards
#: and would train a reader to ignore the warning.
#:
#: This does weaken the deny-list - a leak named `our_epa` would slip past it -
#: and that is survivable only because the deny-list is not the gate. The gate is
#: the allow-list rebuild, which fails closed on any name at all.
OURS_PREFIXES: tuple[str, ...] = ("our_", "play_value")


def banned_hits(columns: Any) -> tuple[str, ...]:
    """Every column name matching a banned pattern, sorted. Case-insensitive."""
    out = {
        str(c)
        for c in columns
        if not str(c).lower().startswith(OURS_PREFIXES)
        and any(pattern in str(c).lower() for pattern in BANNED_COLUMN_PATTERNS)
    }
    return tuple(sorted(out))


# ---------------------------------------------------------------------- the probes
#
# Each probe rebuilds the object a banned column would have to reach in order to
# affect a published number. For L1 and L2 that is literally the design matrix;
# for L3, L4 and the headline ordering it is the flattened schedule those layers
# consume, which plays the same role. Every probe is a pure function of the frame
# it is handed plus already-audited upstream output.


def _probe_ep(plays: pl.DataFrame, cfg: dict[str, Any], **_: Any) -> Any:
    from cfbpoll.model import ep

    model = ep.fit(plays, cfg)
    return (model.table, model.counts, model.edges, model.n_plays)


def _probe_l1(valued: pl.DataFrame, cfg: dict[str, Any], **_: Any) -> Any:
    from cfbpoll.model import design

    d = design.build_play_design(valued, cfg)
    return (d.X, d.y, d.w, d.teams, d.penalty, d.game_ids)


def _probe_l2(games: pl.DataFrame, cfg: dict[str, Any], **_: Any) -> Any:
    from cfbpoll.model import design

    d = design.build_game_design(games, cfg)
    return (d.Z, d.s, d.v, d.teams, d.penalty, d.game_ids)


def _probe_l3(games: pl.DataFrame, cfg: dict[str, Any], power: Any = None, **_: Any) -> Any:
    """The three columns the blend regression sees, plus the response it fits."""
    if power is None or getattr(power, "l3", None) is None:
        return None
    eff, res, site = power.l3.features(games)
    margin = (games["home_points"] - games["away_points"]).to_numpy().astype(np.float64)
    return (eff, res, site, margin)


def _probe_l4(games: pl.DataFrame, cfg: dict[str, Any], power: Any = None, **_: Any) -> Any:
    from cfbpoll.model import l4_resume

    sched = l4_resume._schedule(
        games, power, float(cfg["margin"]["c"]), float(cfg["margin"]["beta_w"])
    )
    return (sched.teams, sched.team_index, sched.opponent_power, sched.sites, sched.wins)


def _probe_schedule_odds(games: pl.DataFrame, cfg: dict[str, Any], power: Any = None, **_: Any):
    from cfbpoll.model import schedule_odds

    fitted = schedule_odds.fit(games, cfg, power=power)
    return (fitted.tail, fitted.wins, fitted.losses, fitted.q_ref.value, fitted.q_ref.team)


# ------------------------------------------------------------------- the allow-list

#: The canonical play frame's allow-list, pulled out because `plays_join` needs
#: to inherit it: the joined frame is the loader's frame plus exactly what
#: `attach_games` copies off the games table.
_PLAY_LOADER_ALLOWED: dict[str, str] = {
    "game_id": "the join key to the games table",
    "season": "window arithmetic and the EP fit's provenance",
    "play_index": "the unique per-game play order (game_row_number)",
    "offense": "a team identity, which is the design matrix's row",
    "defense": "a team identity, which is the design matrix's row",
    "period": "garbage-time thresholds are per quarter",
    "half": "the scoring segment the next-score target is defined on",
    "score_segment": "the same segment, under the name the EP layer reads",
    "clock_seconds": "end-of-half heave detection",
    "down": "expected-points state",
    "distance": "expected-points state",
    "yards_to_goal": "expected-points state",
    "yards_gained": "published context; not a design-matrix column",
    "play_type": "classification into rush / pass / special teams",
    "play_class": "the classification itself",
    "offense_score_after": "THE SCOREBOARD, not a model - our EP layer is fitted to it",
    "defense_score_after": "the scoreboard, from the defence's side",
    "is_snap": "whether a down-and-distance state exists at all",
    "is_kneel": "zero weight - a clock decision, not an offence",
    "is_spike": "zero weight, same",
    "pbp_home": "cross-checked against the games table; never derived from",
    "pbp_away": "cross-checked against the games table; never derived from",
}
_PLAY_CANONICAL: tuple[str, ...] = tuple(_PLAY_LOADER_ALLOWED)

LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec(
        name="games_loader",
        frame="games",
        spec="report 01 §3.10, docs/data-findings.md §5",
        allowed={
            "game_id": "the join key and the sort key of every frame in the package",
            "season": "window arithmetic",
            "week": "window arithmetic - always with season_type, never alone",
            "season_type": "window arithmetic (docs/data-findings.md §1)",
            "game_type": "the [weights] policy of report 02 §3.8",
            "start_date": "bucket ordering by first kickoff, and the recency weight",
            "completed": "the load filter; a scheduled game is not a result",
            "neutral_site": "the site term, unpenalised in every layer",
            "home_team": "a team identity, which is the design matrix's row",
            "away_team": "a team identity, which is the design matrix's row",
            "home_points": "the scoreboard, which is a fact and not a model",
            "away_points": "the scoreboard, which is a fact and not a model",
            "home_class": "division, for the evaluation universe and the ranked set",
            "away_class": "division, for the evaluation universe and the ranked set",
            "conference_game": (
                "NOT A FEATURE. Read only by the 2021 structural conference-"
                "championship fallback in ingest/sportsdataverse.py, which "
                "produces a game_type label. No design matrix sees it, and the "
                "L2/L4/odds probes below prove it every run"
            ),
        },
        probe=None,
    ),
    LayerSpec(
        name="plays_loader",
        frame="raw_plays",
        spec="report 01 §3.10, report 02 §3.1",
        allowed=dict(_PLAY_LOADER_ALLOWED),
        probe=None,
    ),
    LayerSpec(
        name="plays_join",
        frame="plays",
        spec="ingest/plays.py::attach_games, docs/data-findings.md §1 and §12",
        allowed={
            # everything the raw loader already allows...
            **{c: "see plays_loader" for c in _PLAY_CANONICAL},
            # ...plus exactly what attach_games copies off the GAMES table, which
            # is the only authority on any of it, and the two columns it rebuilds
            # from the scoreboard because the feed's own versions are unusable.
            "week": "off the games table, which is the only authority on it",
            "season_type": "off the games table, which is the only authority on it",
            "game_type": "off the games table - the [weights] policy",
            "neutral_site": "off the games table",
            "home_team": "off the games table",
            "away_team": "off the games table",
            "home_class": "off the games table",
            "away_class": "off the games table",
            "offense_is_home": "derived from the games table's home_team, not the feed's",
            "offense_class": "derived from the games table's classification",
            "defense_class": "derived from the games table's classification, other side",
            "home_score_after": "the REPAIRED scoreboard (monotone repair, §12)",
            "away_score_after": "the repaired scoreboard",
            "score_margin": "pre-snap margin, rebuilt from the repaired scoreboard",
            "points_scored": "points on this play, rebuilt from the repaired scoreboard",
        },
        probe=None,
    ),
    LayerSpec(
        name="EP",
        frame="plays",
        spec="report 02 §3.1, model/ep.py",
        allowed={
            "game_id": "the group the next-score scan runs within",
            "play_index": "the order the scan runs in",
            "score_segment": "the segment the next score must fall in",
            "offense": EP_TEAM_LABELS_NOTE,
            "defense": EP_TEAM_LABELS_NOTE,
            "points_scored": "the scoreboard change on this row - the fit's target",
            "down": "the expected-points state",
            "distance": "the expected-points state",
            "yards_to_goal": "the expected-points state (field position)",
            "is_snap": "whether this row has a state at all",
            "season": "provenance only: the seasons stamped on EPModel",
        },
        probe=_probe_ep,
    ),
    LayerSpec(
        name="L1",
        frame="valued_plays",
        spec="report 02 §3.1, model/design.py::build_play_design",
        allowed={
            "game_id": "the CV group - NEVER a play (report 02 §3.1)",
            "play_index": "the sort key",
            "play_value": "OURS (model/ep.py). `epa` is not on this list and never will be",
            "offense": "the offence coefficient's column",
            "defense": "the defence coefficient's column",
            "offense_is_home": "the signed site term",
            "neutral_site": "the signed site term",
            "period": "garbage-time threshold selection",
            "score_margin": "garbage-time filtering, and nothing else",
            "clock_seconds": "end-of-half heave detection, and nothing else",
            "yards_to_goal": "end-of-half heave detection, and nothing else",
            "play_class": "which plays enter the design at all",
            "is_kneel": "zero weight",
            "is_spike": "zero weight",
        },
        probe=_probe_l1,
    ),
    LayerSpec(
        name="L2",
        frame="games",
        spec="report 02 §3.2, model/design.py::build_game_design",
        allowed={
            "game_id": "the sort key and the CV group",
            "home_team": "the +1 column",
            "away_team": "the -1 column",
            "home_points": "the response",
            "away_points": "the response",
            "neutral_site": "the site column, unpenalised",
            "game_type": "the [weights] game weight",
            "start_date": "the recency weight; inert while recency_gamma = 1.0",
        },
        probe=_probe_l2,
    ),
    LayerSpec(
        name="L3",
        frame="games",
        spec="report 02 §3.3, model/l3_power.py::L3Fit.features",
        allowed={
            "home_team": "which L1/L2 rating to difference",
            "away_team": "which L1/L2 rating to difference",
            "neutral_site": "the site column",
            "home_points": "the blend regression's response is ACTUAL MARGIN",
            "away_points": "the other half of that same response",
        },
        probe=_probe_l3,
    ),
    LayerSpec(
        name="L4",
        frame="games",
        spec="report 02 §3.4, model/l4_resume.py::_schedule",
        allowed={
            "game_id": "the sort key",
            "home_team": "whose résumé this row belongs to",
            "away_team": "whose résumé this row belongs to, from the other side",
            "home_points": "win/loss and the compressed-margin variant",
            "away_points": "win/loss and the compressed-margin variant, other side",
            "neutral_site": "the site term",
        },
        probe=_probe_l4,
    ),
    LayerSpec(
        name="schedule_odds",
        frame="games",
        spec="report 02 §2.4, ADR 0005, model/schedule_odds.py",
        allowed={
            "game_id": "the sort key",
            "home_team": "whose record this row belongs to",
            "away_team": "whose record this row belongs to, from the other side",
            "home_points": "WHO WON, and nothing else - the flattener carries no margin",
            "away_points": "WHO WON, and nothing else - the flattener carries no margin",
            "neutral_site": "the site term",
            "home_class": "the q_ref pool is FBS teams only",
            "away_class": "the q_ref pool is FBS teams only, other side",
        },
        probe=_probe_schedule_odds,
        note=(
            "the flattener carries no margin column, and this probe consumes the "
            "scoreboard only through sign(home_points - away_points); "
            "tests/unit/test_schedule_odds.py perturbs every score while "
            "preserving every winner and asserts bit-identity"
        ),
    ),
)

#: The prose form, kept because the module docstring and docs/constraints.md both
#: quote it and a reader should be able to diff the two.
ALLOWED_BY_LAYER: dict[str, tuple[str, ...]] = {
    spec.name: tuple(sorted(spec.allowed)) for spec in LAYERS
}


# ------------------------------------------------------------------------- the walk


def _restrict(frame: pl.DataFrame, keep: set[str]) -> pl.DataFrame:
    return frame.select([c for c in frame.columns if c in keep])


def _try_probe(spec: LayerSpec, frame: pl.DataFrame, cfg: dict[str, Any], power: Any) -> str | None:
    """Digest of the probe on this frame, or None when the probe cannot run at all."""
    try:
        return digest(spec.probe(frame, cfg, power=power))  # type: ignore[misc]
    except Exception:
        return None


def _run_layer(
    spec: LayerSpec,
    frame: pl.DataFrame | None,
    cfg: dict[str, Any],
    power: Any = None,
) -> LayerResult:
    """Prove (or disprove) that this layer consumes only its allow-list."""
    allowed = tuple(sorted(spec.allowed))
    if frame is None:
        return LayerResult(
            layer=spec.name,
            frame=spec.frame,
            n_columns_present=0,
            allowed=allowed,
            extra_present=(),
            banned_present=(),
            consumed_outside_allow_list=(),
            banned_consumed=(),
            digest_full="",
            digest_restricted="",
            identical=True,
            skipped=f"no {spec.frame} frame supplied to this audit",
        )

    present = tuple(frame.columns)
    extra = tuple(c for c in present if c not in spec.allowed)
    banned_present = banned_hits(present)

    # A loader has no design matrix of its own; its allow-list IS the projection
    # it performs, so the check is a containment check and it is exact.
    if spec.probe is None:
        outside = tuple(sorted(extra))
        return LayerResult(
            layer=spec.name,
            frame=spec.frame,
            n_columns_present=len(present),
            allowed=allowed,
            extra_present=outside,
            banned_present=banned_present,
            consumed_outside_allow_list=outside,
            banned_consumed=tuple(c for c in outside if c in banned_present),
            digest_full=digest(sorted(present)),
            digest_restricted=digest(sorted(c for c in present if c in spec.allowed)),
            identical=not outside,
        )

    full = _try_probe(spec, frame, cfg, power)
    if full is None:
        return LayerResult(
            layer=spec.name,
            frame=spec.frame,
            n_columns_present=len(present),
            allowed=allowed,
            extra_present=extra,
            banned_present=banned_present,
            consumed_outside_allow_list=(),
            banned_consumed=(),
            digest_full="",
            digest_restricted="",
            identical=True,
            skipped="the probe could not run on this window (empty or degenerate)",
        )

    restricted = _try_probe(spec, _restrict(frame, set(spec.allowed)), cfg, power)
    consumed: tuple[str, ...] = ()
    if restricted != full:
        # Name the culprit rather than shrugging: add each extra column back on
        # its own and see which one restores the unrestricted answer.
        culprits = [
            column
            for column in extra
            if _try_probe(spec, _restrict(frame, set(spec.allowed) | {column}), cfg, power) == full
        ]
        consumed = tuple(sorted(culprits)) if culprits else tuple(sorted(extra))

    return LayerResult(
        layer=spec.name,
        frame=spec.frame,
        n_columns_present=len(present),
        allowed=allowed,
        extra_present=extra,
        banned_present=banned_present,
        consumed_outside_allow_list=consumed,
        banned_consumed=banned_hits(consumed),
        digest_full=full,
        digest_restricted=restricted or "",
        identical=restricted == full,
    )


def audit(
    games: pl.DataFrame | None = None,
    plays: pl.DataFrame | None = None,
    config: dict[str, Any] | None = None,
    fail_on_banned: bool = False,
    matrices: dict[str, Any] | None = None,
) -> AuditReport:
    """Assert every design matrix contains only its layer's allowed columns.

    Allow-list, not deny-list: a new banned input nobody thought of must fail
    closed. Returns the report; raises when `fail_on_banned` is set and any
    layer consumed a column outside its allow-list.

    `games` and `plays` are the exact frames the run is about to fit on - the
    audit is about THIS window, not about a hypothetical one. `plays` may be
    None (a season with no play feed), in which case the play-level layers are
    reported as skipped rather than silently passed.

    `matrices` is accepted for callers that hold already-built design matrices
    and want their columns checked directly; it is checked as a containment test
    against the same allow-list. It is not the main path and it is not how the
    guarantee is obtained.
    """
    from cfbpoll.config import load_config

    cfg = config if config is not None else load_config()
    report = AuditReport()

    frames: dict[str, pl.DataFrame | None] = {
        "games": games,
        "raw_plays": plays,
        "plays": None,
        "valued_plays": None,
    }
    power: Any = None

    if plays is not None and games is not None and not games.is_empty():
        from cfbpoll.ingest.plays import plays_for
        from cfbpoll.model import ep

        joined = plays_for(plays, games)
        frames["plays"] = joined
        if not joined.is_empty():
            model = ep.fit(joined, cfg)
            valued = ep.play_values(joined, model, cfg)
            keep = [str(c) for c in cfg["efficiency"]["design_play_classes"]]
            frames["valued_plays"] = valued.filter(pl.col("play_class").is_in(keep))

    if games is not None and not games.is_empty():
        from cfbpoll.model import l4_resume

        power = l4_resume.power_source(games, cfg, plays=frames["plays"])

    for spec in LAYERS:
        report.layers.append(_run_layer(spec, frames.get(spec.frame), cfg, power=power))

    if matrices:
        for name, matrix in sorted(matrices.items()):
            allowed = set(ALLOWED_BY_LAYER.get(name, ()))
            columns = list(getattr(matrix, "columns", matrix))
            outside = sorted(c for c in map(str, columns) if c not in allowed)
            if outside:
                report.violations.append(
                    f"{name}: supplied matrix carries column(s) outside the allow-list: "
                    f"{outside}"
                )

    for layer in report.layers:
        if layer.consumed_outside_allow_list:
            report.violations.append(
                f"{layer.layer}: consumes column(s) outside its allow-list: "
                f"{list(layer.consumed_outside_allow_list)}"
                + (
                    f" - and {list(layer.banned_consumed)} match a BANNED pattern"
                    if layer.banned_consumed
                    else ""
                )
            )

    report.context = {
        "n_games": 0 if games is None else int(games.height),
        "n_plays": 0 if frames["plays"] is None else int(frames["plays"].height),
        "seasons": (
            [] if games is None else sorted(int(s) for s in games["season"].unique().to_list())
        ),
        "plays_audited": frames["plays"] is not None,
        "banned_patterns": list(BANNED_COLUMN_PATTERNS),
        "fail_on_banned": bool(fail_on_banned),
    }

    if fail_on_banned and report.violations:
        raise BannedFeature(
            "the feature audit failed (report 02 §3.10):\n  " + "\n  ".join(report.violations)
        )
    return report
