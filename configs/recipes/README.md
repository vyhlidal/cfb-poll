# configs/recipes/

**A ranking is a value system.** It is not a fact about football. It is an
argument about what football results are *for*, and every constant in
[`configs/default.toml`](../default.toml) is a sentence in that argument. This
directory makes the argument selectable.

```bash
uv run cfbpoll recipes                                     # the roster, with costs
uv run cfbpoll rank --season 2023 --through-week 15 --recipe full-merit
```

## The axis, in the project owner's words

> One end is fully meritocratic. Best team wins, we measure as fairly as we can,
> nothing else matters, and margin counts for exactly what it is worth. The other
> end protects sportsmanship, because if point differential pays, teams **will**
> run up the score on an overmatched opponent. Everyone has seen it. But ignoring
> margin entirely throws away the information in a 70 point win against a 1 point
> win, and that information is real.

Three recipes span it. The side-by-side board is
[`demo/2023-recipes.md`](../../demo/2023-recipes.md).

| | recipe | margin in the engine | headline ordering | what it is |
|---|---|---|---|---|
| 0 | **Full Merit** | `C = uncapped`, `β_w = 12` | margin-aware résumé | the meritocratic end |
| 1 | **The House Poll** | `C = 32`, `β_w = 7` | schedule odds | **the published poll** |
| 2 | **Just Win** | `C = 1`, `β_w = 7` | wins-based résumé | the sportsmanship end |

Only **The House Poll** is published as *the poll*. The other two are **alternate
lenses** and every artifact they touch says so, in the same words, in both
publication targets.

## The rule that makes this honest rather than a toy

**A recipe changes VALUES. It never changes EVIDENCE.**

Every recipe reads the same archive, through the same walk-forward window, under
the same constraints, and passes the same leakage audit. That is not a convention:
`recipes.EVIDENCE_KEYS` lists the config keys a recipe may never touch, and
`assert_values_only` **refuses the file at load time** if it names one. The list
covers the fit universe, the walk-forward flags, the holdout, the EP fit scope,
the FCS policy, `[constraints]` and `[weights]`.

`[weights]` is on that list and it looks like a value. It is not. The non-CFP bowl
weight is 0.25 because 78+ opt-outs and 431 portal entries hit the 2021-22
postseason and Florida State lost 33 players before the 2023 Orange Bowl. That is
a statement about how well a game **measures** a team, and it is the same
statement under every value system. Recipes disagree about what to do with a
measurement. They do not get to disagree about how good it is.

[`tests/unit/test_recipes.py`](../../tests/unit/test_recipes.py) proves the
consequence directly rather than restating it: it digests the ingested frames
under all three recipes and asserts the bytes are identical, and it runs the
leakage audit under all three and asserts zero violations in each.

## The house recipe overrides nothing

[`house.toml`](house.toml) carries a `[recipe]` block and **not one constant**.
`recipes.load` raises if it ever carries one. So `resolve("house")` is
`configs/default.toml`, byte for byte, and "adding recipes did not change the
published poll" is a property of the files that is checked on every test run
rather than a promise in a paragraph.

To change the published poll, change `configs/default.toml` and write an ADR
beside it, exactly as before. `house.toml` follows automatically, because it *is*
that file.

## Writing one

A recipe file is a `[recipe]` block plus **only** the constants it changes. Same
shape as [`configs/challengers/`](../challengers/), for the same reason: a diff on
disk cannot drift from the default config, and `config.merge_overlay` **refuses**
a key the default does not define, so a misspelled `beta_w` fails loudly instead
of publishing a poll under constants nobody set.

```toml
[recipe]
slug = "my-recipe"        # must equal the filename
name = "My Recipe"
stance = 0                # 0 merit .. 2 sportsmanship; display order only
one_liner = "One sentence a reader can pick between recipes on."
manifesto = """One paragraph, in your own voice, saying what you believe."""
tradeoffs = [
    "At least one. What this recipe gets wrong, in your own words.",
]

[margin]
c = 24.0
```

**The `tradeoffs` list is required and must be non-empty.** A value system that
will not state its own cost is a marketing page, and `recipes.load` refuses to
load one. What a run then publishes is the **resolved** config in full, hashed on
`_run.json` as `recipe_config_sha256`, because constraint 5 says the config is the
methodology and a methodology a reader has to reconstruct by applying a diff in
their head is not published.

## Where this is weak

- **Two of the three recipes are not tuned and do not claim to be.** `just-win`'s
  `C = 1` sits far outside anything either campaign searched: campaign 1's grid
  opened at 18 and campaign 2 only widened it upward. It is a value judgement
  taken to its logical end. `full-merit`'s constants *are* campaign 2's lead 1,
  which beat the incumbent on margin MAE on both the tune seasons and 2024 and was
  blocked by an interaction rather than by its own result, but that is one
  objective and it has no opinion about desert.
- **No recipe has been backtested end to end as a system.**
  `demo/2023-recipes.md` is one season's final board, which is a comparison of
  outputs and not an evaluation. `cfbpoll backtest` scores orderings, not recipes,
  and pointing it at a recipe is the obvious next piece of work.
- **The gate is not applied per recipe.** `[gate]` is written against the
  published poll. A page that showed three recipes and three gate verdicts would
  be more honest than one that shows three rankings and one verdict, and it does
  not exist yet.
