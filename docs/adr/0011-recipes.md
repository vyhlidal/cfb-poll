# ADR 0011 — A ranking is a value system, so the value systems are named and selectable

- **Status:** Accepted
- **Date:** 2026-08-15
- **Decided by:** the project owner
- **Depends on:** [ADR 0005](0005-headline-ordering.md) (the headline ordering study
  and its three candidates), [ADR 0007](0007-tuned-constants.md) and
  [`docs/analysis/campaign-2.md`](../analysis/campaign-2.md) (the constants)
- **Contract for the site:** [`docs/fixture-contract-recipes.md`](../fixture-contract-recipes.md)
- **The files:** [`configs/recipes/`](../../configs/recipes/)

## Decision

> **A ranking is a value system. This project ships three of them, by name, with
> their manifestos and their costs, and lets a reader see the poll under each. The
> House Poll is the default and the only one published as *the poll*. The others
> are alternate lenses and every artifact they touch says so.**
>
> **A recipe changes VALUES. It never changes EVIDENCE.**

## The owner's framing, preserved

> One end is fully meritocratic. Best team wins, we measure as fairly as we can,
> nothing else matters, and margin counts for exactly what it is worth. The other
> end protects sportsmanship, because if point differential pays, teams **will**
> run up the score on an overmatched opponent. Everyone has seen it. But ignoring
> margin entirely throws away the information in a 70 point win against a 1 point
> win, and that information is real.

That is not a modelling question with an answer. It is a disagreement about what a
poll is *for*, and both ends of it are held sincerely by people who understand the
sport. The house poll's compromise, `C = 32` in the engine and margin out of the
headline, is a defensible position and it is *a position*. Presenting it as though
it were the only one is the failure this project exists to avoid, one level up from
where the project usually looks for it.

## The three recipes

| | recipe | `[margin].c` | `β_w` | headline ordering | ADR 0005 candidate |
|---|---|---|---|---|---|
| 0 | **Full Merit** | `inf` (uncapped) | 12 | margin-aware résumé | **B** |
| 1 | **The House Poll** | 32 | 7 | schedule odds | **C**, published |
| 2 | **Just Win** | 1 | 7 | wins-based résumé | **A** |

**Every one of these was already measured.** This is the decision's strongest
property and it is why the feature is small. ADR 0005 studied exactly these three
orderings, off the identical Power source, fits and windows, and every number they
need has been computed on every published row since the L4 build. Campaign 2
pre-registered and searched `c = inf`, and `C uncapped, β_w = 12` is its **lead 1**:
it beat the incumbent on margin MAE on the tune seasons (13.0039 against 13.0102)
and again on 2024 (12.8536 against 12.9096), cleared its own pre-registered rule,
and was **blocked by an interaction with the accumulation window rather than by its
own result**. The meritocratic end has empirical support on one objective, and that
objective is margin MAE, which has no opinion about desert whatsoever.

Nothing here is a new model. Two of the three recipes are a config diff of three
lines, and the third is a config diff of zero.

## The rule that makes this honest rather than a toy

**Values, never evidence**, enforced three ways rather than documented once:

1. **`recipes.EVIDENCE_KEYS` refuses at load time.** A recipe file naming
   `model.fit_universe`, `backtest.walk_forward_strict`, `backtest.holdout_seasons`,
   `ep.fit_scope`, `[fcs]`, `[constraints]` or `[weights]` does not load. Matching
   is by prefix, so naming a table locks every key added to it later.
2. **`config.merge_overlay` refuses an unknown key.** A recipe that misspells
   `beta_w` fails loudly rather than publishing a poll under constants nobody set.
3. **The tests measure the consequence.**
   [`tests/unit/test_recipes.py`](../../tests/unit/test_recipes.py) digests the
   frames each recipe actually fits on and asserts byte-identity, and runs the real
   pre-fit leakage audit under every recipe with `fail_on_banned` set.

And it is published per week per recipe, so a reader can check it on the page:
`archive_manifest_sha256`, `fit_window_sha256` and `n_games_in_fit` travel on every
recipe's week document and are identical across lenses.

### `[weights]` is locked, and it looks like a value

The non-CFP bowl weight is 0.25 because 78+ opt-outs and 431 portal entries hit the
2021-22 postseason and Florida State lost 33 players before the 2023 Orange Bowl
(report 02 §3.8). That is a statement about how well a game **measures** a team.
Recipes disagree about what to do with a measurement. They do not get to disagree
about how good it is, and a recipe that could down-weight the games it dislikes
would be able to manufacture any ranking it wanted while still calling itself a
value system.

## The house recipe overrides nothing

`configs/recipes/house.toml` carries a `[recipe]` block and **not one constant**,
and `recipes.load` raises if it ever carries one. So `resolve("house")` is
`configs/default.toml` byte for byte, and "adding recipes did not change the
published poll" is a property of the files, checked on every test run, rather than
a promise in a paragraph.

`test_omitting_the_flag_publishes_the_house_poll_to_the_last_byte` diffs `poll.csv`
between a house run and a run with no flag at all. Adding recipes moved no
published number.

## What this changed in the code, and the defect it found

Small, and of a known shape:

- `publish/poll.ORDER_KEYS` gains `L4_resume_margin`, keyed on the margin-aware
  résumé alone rather than as a tie-break. That is what makes it a different
  *ordering* rather than a different tie-break.
- `model/bootstrap.ORDERINGS` gains `resume_margin`.
- `rank` takes `--recipe`; `model_params.json`, `poll.json` and `_run.json` all
  carry which value system produced the number, including the house run.
- `publish fixtures` writes lenses to a new subtree. `schema_version` does not move.

**And it surfaced a defect that was always there.** `rank_lo` and `rank_hi` sit
beside `rank` on every published row precisely because "#4" and "#4, 90% interval
2-66" are different claims. The wiring that filled them was hard-coded to the
schedule-odds bootstrap ordering, so under any other headline the poll would have
published an interval computed on a *different ordering* from the rank it
qualifies. That is not a weaker version of the promise, it is a false one. The poll
only ever ran one headline in anger, so it was invisible; `headline_ordering =
"L4_resume"` has been a supported config value since ADR 0005 and would have hit
it. `HEADLINE_INTERVAL_ORDERING` makes the mapping explicit.

`C = inf` also had to become publishable. JSON has no infinity, `json.dumps` emits
the invalid literal `Infinity`, and `publish/fixtures.py` writes with
`allow_nan=False` and would raise. The limit is published under the name campaign 2
gave it, `"uncapped"`, rather than dropped: `model_params.json` publishes every
constant every week without exception, and the one week `C` may not go missing is
the week `C` is the entire argument.

## The price, stated plainly

1. **Two of the three recipes are not tuned and do not claim to be.**
   `just-win`'s `C = 1` sits far outside anything either campaign searched:
   campaign 1's grid opened at 18 and campaign 2 only widened it upward. It is a
   value judgement taken to its logical end and nothing here claims it predicts
   well.
2. **No recipe has been backtested end to end as a system.**
   [`demo/2023-recipes.md`](../../demo/2023-recipes.md) is one season's final board,
   which compares outputs and does not evaluate them. `cfbpoll backtest` scores
   orderings, not recipes.
3. **The gate is not applied per recipe.** `[gate]` is written against the
   published poll, so an alternate lens publishes no gate verdict and its
   methodology document says why. A page showing three rankings and one verdict
   would be less honest than one showing three verdicts, and the second does not
   exist yet.
4. **Selectable value systems are a rhetorical risk.** "Here are three rankings,
   pick the one you like" is the opposite of what this project is for, and the only
   thing separating this feature from that sentence is the labelling: one recipe is
   published, the other two are lenses, and each one carries its own costs in its
   own words on the same page as its ranking. If the site ever presents the three
   as equals, this ADR should be reopened.
5. **`full-merit` is an ordering this project rejected on the evidence and still
   rejects.** B lost the résumé axis in 16 of 16 season × surface cells and ranks
   teams with losses above unbeaten ones. Shipping it as a selectable lens does not
   relitigate ADR 0005. It makes ADR 0005 checkable: "we measured it and it lost"
   was a claim a reader had to take on trust, because B was the one candidate the
   pipeline could not be pointed at.

## Where this decision is weak

- **Three recipes is a curated set and curation is a value judgement too.** The
  axis has infinitely many points on it and this project picked three, including
  its own. Anyone can add a fourth: `configs/recipes/` takes a file, and the
  refusals in `recipes.load` are the only gatekeeping there is.
- **The manifesto prose is versioned by nothing.** `recipe_config_sha256` changes
  when a constant changes; editing a manifesto changes no hash anywhere.
- **One season of comparison.** `demo/2023-recipes.md` is 2023. The structural
  claims (`just-win` can never rank a beaten team above an unbeaten one;
  `full-merit` routinely does) are properties of the orderings and hold in every
  season; the specific movers are one season's.
- **2025 is untouched and stays locked**, under every recipe. `EVIDENCE_KEYS`
  includes `backtest.holdout_seasons` and `backtest.holdout_locked` precisely so a
  recipe cannot be the thing that opens it.

## How to revisit it

```
uv run cfbpoll recipes
uv run cfbpoll rank --season 2023 --through-week 15 --recipe full-merit --out out/
make recipe-fixtures
```

If the site ever presents the three recipes as equally published, or if a recipe
appears that moves a key `EVIDENCE_KEYS` does not yet cover, reopen this.
