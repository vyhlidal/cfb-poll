# demo/recipe-fixtures/

**The 2023 season under the two alternate lenses, precomputed.** Weeks 5 to 15,
live and hindsight, in the published fixture contract. The full contract for the
site is [`docs/fixture-contract-recipes.md`](../../docs/fixture-contract-recipes.md);
the decision is [ADR 0011](../../docs/adr/0011-recipes.md).

```
2023/recipes/full-merit/week-NN.json         weeks 05-15
2023/recipes/full-merit/methodology-NN.json
2023/recipes/full-merit/divergence.json
2023/recipes/just-win/…                      the same
```

## This is an OVERLAY, not a fixture set

**There is no `index.json` here and no `2023/week-NN.json`, on purpose.** Both are
functions of the *whole* tree, and this directory holds only the half of it that
the published poll's own regeneration does not produce. An `index.json` written
against a directory with no house weeks would say the 2023 season has zero weeks
played, which is a document that looks correct and is wrong, and that is the worst
failure mode a fixture set has.

To install it into the site's data directory:

```bash
cp -R demo/recipe-fixtures/2023/recipes  <site>/cfb-poll-data/2023/
uv run cfbpoll publish fixtures --out <site>/cfb-poll-data --index-only
```

The second line is not optional and it is not a formality. `index.json` is a pure
function of what is on disk (report 03 §9.3), so rebuilding it against the merged
tree is what produces a correct `seasons[].recipes`, a correct week strip, and the
recipe roster the selector reads. Running it is idempotent and it converges.

`--index-only` also rebuilds each lens's `divergence.json`, so the copies here are
belt and braces rather than the source of truth.

## Regenerating

```bash
make recipe-fixtures FIXTURES=demo/recipe-fixtures
rm demo/recipe-fixtures/index.json demo/recipe-fixtures/2023/divergence.json
```

The two removals are why this file exists: the target writes a complete tree,
because writing a complete tree is what it does when pointed at the real
destination, and only the lens subtrees belong in git.

`make recipe-fixtures` defaults `FIXTURES` to the site's own data directory, which
is the command an operator actually wants. It does **not** regenerate the published
poll: that is `make fixtures`' job, and writing the house tree from two commands
would be two procedures that have to agree forever.

### What regeneration is allowed to change, and what it is not

Regenerated on the recipes merge (2026-08-15). **Every ranked number is identical**:
the 44 documents differ only in `run.{git_sha,run_id,ran_at,published_at}`, in
`run.config_hash` and `recipe.config_sha256` — and in one paragraph of prose.

The two hashes moved for a reason that has nothing to do with recipes.
`configs/default.toml` grew a `[projection]` section for the second product
(ADR 0010), so the base config's bytes changed and so did the resolved config's.
Neither table is read by anything a recipe touches, every rank, interval and
digest below them is unchanged, and `fit_window_sha256` is the field that says so:
same archive, same 1,557 games, same frame, under both lenses. **A moving config
hash with a still fit-window digest is exactly the pair of facts this tree exists
to make checkable**, and this is the first time they have disagreed on purpose.

The prose is the interesting one. Three `just-win` documents — weeks 5, 6 and 7 —
carried a **superseded** fourth tradeoff, the one that called the saturation
tie-break a defensible compromise. The board found otherwise: at `C = 1` the
tie-break compresses too, every unbeaten team saturates on both columns, and 2023's
top four falls through to alphabetical order. `configs/recipes/just-win.toml` was
rewritten to say so, and the eight later weeks picked the new text up because they
were generated after it. The first three were not, and shipped disagreeing with
their own config about what the recipe gets wrong.

That is the failure `docs/fixture-contract-recipes.md` §7 predicts in the abstract
("nothing versions the prose") arriving in the concrete, and it is a reason to
regenerate this tree in **one** pass rather than to hand-patch three files: the
overlay is only worth committing if every document in it was written by one
version of the code against one version of the configs.

## Why weeks 5 to 15 and not 1 to 15

The same reason `[publication].headline_start_week` is 5. Weeks 1 to 4 are
explicitly not the poll: they publish a connectivity report and clearly-labelled
provisional output. Offering a reader three value systems to rank a provisional
table with is offering a choice about something that is not yet a ranking.

## What is not here

- **No `recipes/house/`.** The house recipe *is* the season directory. A duplicate
  copy under a slug would be two files that must agree forever, and the first time
  they disagreed the site would show the published poll twice, differently.
- **No connectivity document per lens.** It is a function of the schedule graph,
  which is *evidence*, and evidence is identical under every recipe by
  construction. A recipe page should link to the season's one connectivity report.
- **No gate verdict.** `[gate]` is written against the published poll, so each
  lens's `methodology-NN.json` carries `gate: []` and a `gate_note` saying why.
