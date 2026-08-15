"""The challenge harness - "did it beat the model" with a mechanical answer.

Report 03 §7.3 and §10 step 14. This is the moat, and until now it was a
paragraph: `CONTRIBUTING.md` said in as many words that the harness did not
exist, and `configs/challengers/` said "empty right now". An invitation to
challenge a model that requires you to build your own evaluation is not an
invitation.

THE ONE RULE THAT MAKES IT MEAN ANYTHING: a challenger is scored by the SAME
`run_backtest`, on the SAME frames, over the SAME seasons, against the SAME
baselines, with the SAME publication gate. Nothing here re-implements a metric.
If it did, the answer would be a number produced by code that only challengers
run, and the comparison would be worth exactly nothing.

TWO KINDS OF CHALLENGER (report 03 §7.3), and the difference is real:

  1. PARAMETER VARIANT - a TOML in `configs/challengers/` holding only the keys
     it changes. This is a claim about a constant, so the model is the same
     model and the harness runs it twice: once under `configs/default.toml` for
     the incumbent and every baseline, once under the merged config for the
     challenger's row. Comparing a row from one run to a row from the other is
     legitimate here precisely because the walk, the frames and the metric code
     are byte-identical between them.

  2. STRUCTURAL VARIANT - a module exposing
     `rate(games, plays, through_week) -> {team: rating}`. This is a claim about
     a different model, so it is registered as one more system in a SINGLE run
     alongside the incumbent and every baseline. One walk, one set of frames, no
     merge, nothing to argue about.

2025 IS REFUSED. `run_backtest` raises `HoldoutLocked` for it and this module
never passes `unlock_holdout`. A challenger who tunes against the holdout and
says nothing produces a meaningless result; the harness does not rely on their
restraint.

WHAT A CHALLENGER CANNOT DO HERE. It receives frames that are already truncated
to `through_week`, so the walk-forward guard lives in the harness rather than in
their code. A parameter variant that names a key `configs/default.toml` does not
define is refused by `config.merge_overlay`, because an override that names
nothing changes nothing, silently.
"""

from __future__ import annotations

import importlib.util
import json
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cfbpoll.backtest import walkforward
from cfbpoll.config import DEFAULT_CONFIG_PATH, config_hash, load_config, merge_overlay

__all__ = [
    "CHALLENGER_SYSTEM",
    "DEFAULT_SYSTEMS",
    "Challenger",
    "load_challenger",
    "run_challenge",
    "scorecard_markdown",
    "write_scorecard",
]

#: The name a structural challenger is scored under. One reserved name, so a
#: scorecard reader never has to wonder which row is the entry.
CHALLENGER_SYSTEM = "challenger"

#: The comparison set. Identical to `make backtest`'s, on purpose: a challenger
#: is measured against exactly what the published table is measured against.
DEFAULT_SYSTEMS = (
    "schedule_odds",
    "resume",
    "l3",
    "l2",
    "l1",
    "colley",
    "srs",
    "elo",
    "walker",
    "winpct",
    "home_team",
)

#: The metrics a scorecard reports, and which direction is better. The gate's
#: five criteria plus the two that describe the size of the error, because a
#: challenger that improves MAE and loses the gate has still told us something.
SCORE_METRICS: tuple[tuple[str, str, bool], ...] = (
    ("su_accuracy", "Straight-up %", True),
    ("mae", "Margin MAE", False),
    ("rmse", "Margin RMSE", False),
    ("brier", "Brier", False),
    ("log_loss", "Log loss", False),
    ("max_calibration_deviation_pp", "Max calib. dev. (pp)", False),
)


@dataclass(frozen=True)
class Challenger:
    """One entry, loaded and validated before a single game is fitted."""

    name: str
    kind: str  # "parameter" | "structural"
    entry: Path
    author: str = ""
    notes: str = ""
    needs_plays: bool = False
    overlay: dict[str, Any] = field(default_factory=dict)
    rate: Callable[..., dict[str, float]] | None = None

    @property
    def system(self) -> str:
        """The system name this challenger's row appears under."""
        return CHALLENGER_SYSTEM if self.kind == "structural" else "schedule_odds"


def _meta(payload: dict[str, Any], entry: Path) -> dict[str, Any]:
    block = dict(payload.get("challenger") or {})
    missing = [k for k in ("name", "kind") if not block.get(k)]
    if missing:
        raise ValueError(
            f"{entry}: the [challenger] block is missing {missing}. Every entry "
            "must name itself and declare its kind, so a scorecard can say what "
            "it scored without the reader opening the file."
        )
    if block["kind"] not in ("parameter", "structural"):
        raise ValueError(
            f"{entry}: kind must be 'parameter' or 'structural', not {block['kind']!r}"
        )
    return block


def load_challenger(entry: str | Path, config_path: str | Path | None = None) -> Challenger:
    """Load a `.toml` parameter variant or a `.py` structural variant.

    Validation happens HERE rather than at first use, because a challenger who
    misspelled a config key deserves to find out in a second rather than after a
    ten-minute walk over three seasons - and because a harness that discovers a
    bad entry halfway through has already spent the compute.
    """
    path = Path(entry)
    if not path.exists():
        raise FileNotFoundError(f"no challenger entry at {path}")

    if path.suffix == ".toml":
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        block = _meta(payload, path)
        if block["kind"] != "parameter":
            raise ValueError(f"{path}: a .toml entry is a parameter variant, not {block['kind']!r}")
        overlay = {k: v for k, v in payload.items() if k != "challenger"}
        if not overlay:
            raise ValueError(
                f"{path}: overrides nothing. A parameter variant that changes no "
                "constant is the incumbent, and scoring it would report a tie as a "
                "finding."
            )
        # Merge now, so an unknown key raises before any fitting happens.
        base = load_config(config_path or DEFAULT_CONFIG_PATH)
        merge_overlay(base, overlay)
        return Challenger(
            name=str(block["name"]),
            kind="parameter",
            entry=path,
            author=str(block.get("author", "")),
            notes=str(block.get("notes", "")),
            needs_plays=bool(block.get("needs_plays", False)),
            overlay=overlay,
        )

    if path.suffix == ".py":
        spec = importlib.util.spec_from_file_location(f"challenger_{path.stem}", path)
        if spec is None or spec.loader is None:  # pragma: no cover - unimportable path
            raise ImportError(f"{path} is not importable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        block = _meta({"challenger": getattr(module, "CHALLENGER", {})}, path)
        if block["kind"] != "structural":
            raise ValueError(f"{path}: a .py entry is a structural variant, not {block['kind']!r}")
        rate = getattr(module, "rate", None)
        if not callable(rate):
            raise ValueError(
                f"{path}: no `rate` function. The protocol is "
                "`rate(games, plays, through_week) -> dict[team, float]`, fixed in "
                "src/cfbpoll/model/__init__.py as `Rater`."
            )
        return Challenger(
            name=str(block["name"]),
            kind="structural",
            entry=path,
            author=str(block.get("author", "")),
            notes=str(block.get("notes", "")),
            needs_plays=bool(block.get("needs_plays", False)),
            rate=rate,
        )

    raise ValueError(f"{path}: a challenger is a .toml parameter variant or a .py module")


def _headline(block: dict[str, Any]) -> dict[str, Any]:
    return block["segments_from_headline_week"]["fbs_vs_fbs"]


def run_challenge(
    challenger: Challenger,
    seasons: list[int],
    *,
    systems: list[str] | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Score one challenger against the incumbent and every baseline.

    Returns the scorecard payload. The two full metrics trees are kept under
    `runs`, so nothing in the summary is unfalsifiable from the artifact itself.
    """
    wanted = list(systems or DEFAULT_SYSTEMS)
    base_config = load_config(config_path or DEFAULT_CONFIG_PATH)

    if challenger.kind == "structural":
        reference = walkforward.run_backtest(
            seasons=seasons,
            systems=[*wanted, CHALLENGER_SYSTEM],
            config=base_config,
            extra_raters={CHALLENGER_SYSTEM: challenger.rate},
            needs_plays_extra=challenger.needs_plays,
        )
        variant = reference
        protocol_note = (
            "ONE RUN. The challenger is registered as one more system in the same "
            "walk, so every row in this scorecard came out of a single call to "
            "`run_backtest` over identical frames."
        )
    else:
        reference = walkforward.run_backtest(
            seasons=seasons, systems=wanted, config=base_config
        )
        variant = walkforward.run_backtest(
            seasons=seasons,
            systems=wanted,
            config=merge_overlay(base_config, challenger.overlay),
        )
        protocol_note = (
            "TWO RUNS, one per config, over the same seasons and the same systems. "
            "A parameter variant is a claim about a constant, so the incumbent row "
            "comes from the default config and the challenger row from the merged "
            "one. The walk, the frames and every line of metric code are identical "
            "between them; only the constants differ."
        )

    incumbent_block = reference["systems"]["schedule_odds"]
    challenger_block = variant["systems"][challenger.system]

    rows = []
    for key, label, higher_is_better in SCORE_METRICS:
        ours = _headline(incumbent_block).get(key)
        theirs = _headline(challenger_block).get(key)
        if ours is None or theirs is None:  # pragma: no cover - a metric not computed
            continue
        delta = theirs - ours
        rows.append(
            {
                "metric": key,
                "label": label,
                "incumbent": ours,
                "challenger": theirs,
                "delta": delta,
                "better": bool(delta > 0) if higher_is_better else bool(delta < 0),
                "higher_is_better": higher_is_better,
            }
        )

    ours_v = incumbent_block["retrodictive_violation_rate"]
    theirs_v = challenger_block["retrodictive_violation_rate"]
    if ours_v is not None and theirs_v is not None:
        rows.append(
            {
                "metric": "retrodictive_violation_rate",
                "label": "Retrodictive violations",
                "incumbent": ours_v,
                "challenger": theirs_v,
                "delta": theirs_v - ours_v,
                "better": bool(theirs_v < ours_v),
                "higher_is_better": False,
            }
        )

    won = [r["label"] for r in rows if r["better"]]
    lost = [r["label"] for r in rows if not r["better"]]
    gate = challenger_block["gate"]

    return {
        "challenger": {
            "name": challenger.name,
            "kind": challenger.kind,
            "entry": str(challenger.entry),
            "author": challenger.author,
            "notes": challenger.notes,
            "system": challenger.system,
            "needs_plays": challenger.needs_plays,
            "overlay": challenger.overlay,
            "base_config_sha256": config_hash(config_path or DEFAULT_CONFIG_PATH),
        },
        "protocol": {
            "seasons": sorted(int(s) for s in seasons),
            "systems": wanted,
            "note": protocol_note,
            "window": gate["window"],
            "holdout_seasons": reference["protocol"]["holdout_seasons"],
            "holdout_touched": reference["protocol"]["holdout_touched"],
            "gate_thresholds": gate["thresholds"],
        },
        "scorecard": rows,
        "verdict": {
            # A challenger "wins" only by clearing the gate the incumbent does not.
            # Beating the incumbent on a metric is a finding; clearing the bar is
            # the thing the gate exists to decide, and conflating them is how a
            # leaderboard becomes a marketing surface.
            "beats_incumbent_on": won,
            "loses_to_incumbent_on": lost,
            "challenger_clears_gate": bool(gate["passed"]),
            "incumbent_clears_gate": bool(incumbent_block["gate"]["passed"]),
        },
        "gates": {
            name: block["gate"]
            for name, block in sorted(variant["systems"].items())
            if block.get("gate")
        },
        # The challenger's own row is reported once, under its name, at the top of
        # the board. Leaving the raw `challenger` system in here as well printed
        # the same numbers twice under two labels, which is the sort of thing a
        # reader is entitled to read as padding.
        "baselines": {
            name: {
                **{k: _headline(block).get(k) for k, _, _ in SCORE_METRICS},
                "retrodictive_violation_rate": block["retrodictive_violation_rate"],
            }
            for name, block in sorted(reference["systems"].items())
            if name != CHALLENGER_SYSTEM
            and block.get("segments_from_headline_week", {}).get("fbs_vs_fbs")
        },
        "runs": {"reference": reference, "variant": variant if variant is not reference else None},
    }


def _fmt(key: str, value: float | None) -> str:
    if value is None:
        return "-"
    if key == "su_accuracy":
        return f"{value:.2%}"
    if key in ("brier", "log_loss", "retrodictive_violation_rate"):
        return f"{value:.4f}"
    if key == "max_calibration_deviation_pp":
        return f"{value:.2f}"
    return f"{value:.3f}"


def scorecard_markdown(result: dict[str, Any]) -> str:
    """The comment CI posts on a pull request. Side by side, and unflattering."""
    who = result["challenger"]
    verdict = result["verdict"]
    rows = result["scorecard"]
    protocol = result["protocol"]

    won, lost = len(verdict["beats_incumbent_on"]), len(verdict["loses_to_incumbent_on"])
    lines = [
        f"## Challenger scorecard: `{who['name']}`",
        "",
        f"**{won} of {won + lost} metrics beat the incumbent.** "
        + (
            "It clears the publication gate, which the incumbent does not."
            if verdict["challenger_clears_gate"] and not verdict["incumbent_clears_gate"]
            else (
                "It clears the publication gate."
                if verdict["challenger_clears_gate"]
                else "It does not clear the publication gate. Neither does the incumbent."
                if not verdict["incumbent_clears_gate"]
                else "It does not clear the publication gate."
            )
        ),
        "",
        f"- Entry: `{who['entry']}` ({who['kind']} variant"
        + (f", by {who['author']}" if who["author"] else "")
        + ")",
        f"- Seasons: {protocol['seasons']}; window: {protocol['window']}",
        f"- Holdout {protocol['holdout_seasons']} touched: "
        f"**{protocol['holdout_touched']}**",
        "",
        f"> {protocol['note']}",
        "",
        "### Challenger vs the incumbent",
        "",
        "| Metric | Incumbent | Challenger | Delta | |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows:
        arrow = "better" if row["better"] else "worse"
        lines.append(
            f"| {row['label']} | {_fmt(row['metric'], row['incumbent'])} "
            f"| {_fmt(row['metric'], row['challenger'])} "
            f"| {row['delta']:+.4f} | {'**' + arrow + '**' if row['better'] else arrow} |"
        )

    lines += [
        "",
        "### The same board, every system in the comparison",
        "",
        "| System | SU % | MAE | RMSE | Brier | Log loss | Calib. dev. | Violations |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    board = {
        f"**CHALLENGER — {who['name']}**": {row["metric"]: row["challenger"] for row in rows},
        **result["baselines"],
    }
    for name, block in board.items():
        cells = [_fmt(key, block.get(key)) for key, _, _ in SCORE_METRICS]
        cells.append(_fmt("retrodictive_violation_rate", block.get("retrodictive_violation_rate")))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    thresholds = protocol["gate_thresholds"]
    cleared = sorted(n for n, g in result["gates"].items() if g["passed"])
    lines += [
        "",
        "### The publication gate",
        "",
        f"Thresholds: SU ≥ {thresholds['su_accuracy_min']:.2%}, "
        f"MAE ≤ {thresholds['mae_max']}, RMSE ≤ {thresholds['rmse_max']}, "
        f"calibration ≤ {thresholds['calibration_max_decile_deviation_pp']} pp, "
        f"violations at or below `{thresholds['violations_must_beat']}`.",
        "",
        f"**Systems clearing it: {cleared if cleared else 'none, including ours'}.**",
        "",
        "Beating the incumbent on a metric is a finding. Clearing the gate is the",
        "thing the gate exists to decide, and this scorecard keeps them apart on",
        "purpose - a leaderboard that conflates them becomes a marketing surface.",
        "",
        "---",
        "",
        "Generated by `cfbpoll challenge run`. Same harness, same frames, same",
        "seasons, same baselines, same gate as `demo/backtest-2021-2023.md`.",
        "`--seasons` is fixed to the tune seasons, so an entry is compared with",
        "the incumbent on the seasons the incumbent was fitted on and on no",
        "others. 2025 was the sealed holdout, was scored once on 2026-08-15 and",
        "is open (ADR 0012); scoring an entry on it is a decision a human makes",
        "in a pull request, never something this command does by default.",
    ]
    return "\n".join(lines) + "\n"


def write_scorecard(result: dict[str, Any], out: str | Path) -> dict[str, Path]:
    """Write the scorecard, and the full metrics trees beside it.

    The trees are ~0.5 MB each and they are NOT folded into `scorecard.json`, for
    a reason that is about review rather than about disk: a summary a reviewer
    cannot diff is a summary a reviewer will not read, and a scorecard that is
    99% appendix is exactly that. The appendix ships as its own file, so nothing
    in the summary is unfalsifiable and the summary stays readable in a diff.
    """
    directory = Path(out)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in result.items() if k != "runs"}
    runs = result.get("runs") or {}

    written: dict[str, Path] = {}
    md = directory / "scorecard.md"
    md.write_text(scorecard_markdown(result), encoding="utf-8")
    written["markdown"] = md

    js = directory / "scorecard.json"
    payload["runs_written_to"] = sorted(
        f"backtest_metrics_{name}.json" for name, tree in runs.items() if tree
    )
    js.write_text(json.dumps(payload, indent=2, sort_keys=True, default=float) + "\n")
    written["json"] = js

    for name, tree in runs.items():
        if not tree:
            continue
        path = directory / f"backtest_metrics_{name}.json"
        path.write_text(json.dumps(tree, indent=2, sort_keys=True, default=float) + "\n")
        written[name] = path
    return written
