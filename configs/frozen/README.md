# configs/frozen/

**Rules never change mid-season.**

When week 1 of a season publishes, `configs/default.toml` is copied here as
`<season>.toml` and that copy governs every published poll for that season. The
frozen file is immutable: a change to it is a change to history, and history is
append-only in this project (report 01 §5.4(2), report 03 §5.6).

Empty right now — no season has been published. Expected first entry: `2026.toml`.

## Why this directory exists

Two reasons, both from the research:

1. **Integrity.** A poll whose constants can be quietly retuned mid-season is not
   a published record, it is an opinion with a changelog. Report 02 §7.6 says the
   game rules "should be written down before the season, and they should never
   change mid-season."
2. **Replay.** The reproducibility job (`.github/workflows/reproducibility.yml`)
   recomputes a historical week with `--config configs/frozen/<season>.toml` and
   asserts a byte-match against `data/manifests/golden/<season>-w<NN>.sha256`. That
   assertion is only meaningful if the frozen config is genuinely frozen.

## Rules

- One file per season, named `<season>.toml`, with `frozen = true` under `[meta]`.
- Never edit a frozen file. If a constant was wrong, publish a correction as a new
  run with a new `run_id` and leave the old rows in place.
- Between seasons, changes go into `configs/default.toml` with the reasoning in a
  commit message and, if the change is material, an ADR in `docs/adr/`.
