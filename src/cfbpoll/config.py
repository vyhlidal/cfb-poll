"""Config loading. The config IS the methodology (constraint 5).

Every constant the model uses is read from `configs/default.toml` through this
module. Nothing numeric may be hard-coded in a model or backtest path: if a
number appears in the code and not in the config, that is a bug, because
`model_params.json` is published every week and it is generated from the config.

Rules never change mid-season. Once week 1 of a season publishes, the live config
is copied to `configs/frozen/<season>.toml` and that copy governs the season.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "REPO_ROOT",
    "config_hash",
    "load_config",
    "merge_overlay",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "default.toml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Parse a model config TOML into a plain dict."""
    p = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with p.open("rb") as fh:
        return tomllib.load(fh)


def config_hash(path: str | Path | None = None) -> str:
    """sha256 of the config file bytes, for `_run.json` traceability (report 03 §5.3)."""
    p = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    return hashlib.sha256(p.read_bytes()).hexdigest()


def merge_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge a sparse override onto a full config. Neither input is mutated.

    This exists for `configs/challengers/`, whose front door tells a challenger to
    ship "only the keys you want to change". Two rules make that safe rather than
    convenient:

      * A key the base config does not define is REFUSED. A challenger who
        misspells `beta_w` as `betaw` would otherwise be scored on the default
        constants while believing they had changed one, and would then publish a
        finding about a model nobody ran. Failing on an unknown key is the whole
        difference between a harness and a formality.
      * Tables merge, scalars and arrays replace. A list is a value here (the
        gate's rival list, the holdout seasons), never something to append to.
    """
    merged = dict(base)
    for key, value in overlay.items():
        if key not in base:
            raise KeyError(
                f"config override sets {key!r}, which `configs/default.toml` does not "
                "define. An override that names nothing changes nothing, silently."
            )
        if isinstance(value, dict) and isinstance(base[key], dict):
            merged[key] = merge_overlay(base[key], value)
        else:
            merged[key] = value
    return merged
