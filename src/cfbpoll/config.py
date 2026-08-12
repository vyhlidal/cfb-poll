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

__all__ = ["DEFAULT_CONFIG_PATH", "REPO_ROOT", "config_hash", "load_config"]

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
