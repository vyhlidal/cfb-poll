# The fixture contract: recipes

**Audience: whoever builds the recipe selector on the site.** This is the whole
data contract for [ADR 0011](adr/0011-recipes.md). Everything below is written by
`cfbpoll publish fixtures` and read by `FixtureSource`; the Postgres backend
rebuilds the identical documents with SELECTs, so a page cannot work against one
backend and quietly break against the other.

The pipeline does not import from the site and the site does not compute
(report 03 §6.3, report 05 §7.2). If a number, a label or a sentence appears on a
recipe page, it is in a document below.

---

## 1. The one-paragraph version

`<season>/week-NN.json` is still the published poll, still at the path it has
always been, still the house recipe. Alternate lenses appear beneath it at
`<season>/recipes/<slug>/week-NN.json` in the **same document shape**. Nothing
moves, `schema_version` does not change, and a site that has never heard of a
recipe keeps working unchanged.

---

## 2. What is new on disk

```
<dir>/index.json                                     + recipes, + recipes_contract_version,
                                                     + seasons[].recipes
<dir>/<season>/week-NN.json                          UNCHANGED PATH. The published poll.
                                                     + recipe (block, §4)
<dir>/<season>/methodology-NN.json                   + recipe, + gate_note
<dir>/<season>/connectivity-NN.json                  unchanged
<dir>/<season>/data-NN.json                          unchanged
<dir>/<season>/divergence.json                       unchanged

<dir>/<season>/recipes/<slug>/week-NN.json           NEW. One week under one lens.
<dir>/<season>/recipes/<slug>/methodology-NN.json    NEW. That lens's constants.
<dir>/<season>/recipes/<slug>/divergence.json        NEW. That lens's retro curve.
```

`<slug>` is `full-merit` or `just-win` today. It is the filename stem in
`configs/recipes/` and it is URL-safe by construction.

**There is no `recipes/house/`.** The house recipe *is* the season directory. A
duplicate copy under a slug would be two files that must agree forever, and the
first time they disagreed the site would show the published poll twice, differently.

### Why connectivity and /data are house-only

They are not missing. They are not applicable.

- **`connectivity-NN.json` is a function of the schedule graph**, and the schedule
  graph is *evidence*. Evidence is identical under every recipe by construction
  (§5), so writing it three times would publish the same bytes three times and
  invite a reader to wonder which copy is right. **A recipe page should link to
  the season's one connectivity report, not to its own.**
- **`data-NN.json` indexes the artifacts of a published run**, and exactly one
  recipe is published.

---

## 3. `index.json`

Three additions. `schema_version` is **still `1`** and the loader's existing
equality check must stay as it is.

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-08-15T...",
  "generator": "cfbpoll publish fixtures",

  "recipes_contract_version": 1,        // NEW
  "recipes": [ /* roster, below */ ],   // NEW

  "seasons": [
    {
      "season": 2023,
      "headline_start_week": 5,
      "weeks": [ /* unchanged */ ],
      "recipes": [                      // NEW
        { "slug": "full-merit", "weeks": [1, 2, ..., 15] },
        { "slug": "just-win",   "weeks": [1, 2, ..., 15] }
      ]
    }
  ]
}
```

**Why `schema_version` did not move.** It exists so the loader fails loudly rather
than rendering nulls when a document changes shape. No document changed shape:
every path, field and type the site reads today is untouched, and everything here
is additive. Bumping it would make the loader throw on a set that is strictly more
capable than the one it was written against, which is the opposite of what the
check is for. The extension carries its own version instead, so a site can ask
*"which recipe contract is this"* without asking *"did the poll change shape"*.

**`recipes_contract_version` is what to branch on.** Absent or `0` means a fixture
set with no lenses: render the poll exactly as today and do not draw the selector.

**`seasons[].recipes` is presence, not description.** It says which lenses this
season actually carries and for which weeks, so the selector can disable a lens
for a week that was never published rather than 404 on click. The prose lives in
the roster, once.

### The roster: `index.json.recipes[]`

Everything a selector needs, in one document, so a page never opens a week file to
find out what it is offering and never holds its own copy of prose that would then
drift from the config it describes.

| field | type | what it is |
|---|---|---|
| `slug` | string | the identifier in every path and URL |
| `name` | string | display name, e.g. `"Full Merit"` |
| `one_liner` | string | one sentence a reader can choose on |
| `manifesto` | string | **one paragraph**, the owner's voice, already whitespace-collapsed. Render as a single `<p>`. |
| `tradeoffs` | string[] | **non-empty.** What this recipe gets wrong, in its own words. |
| `stance` | int | `0` merit … `2` sportsmanship. **Display order only.** No number reads it. |
| `is_house` | bool | exactly one recipe is `true` |
| `default` | bool | the recipe to open on. Identical to `is_house` today; kept separate so the two can be argued about separately. |
| `label` | string \| null | `null` for the house recipe, otherwise `"ALTERNATE LENS. Not the published poll."` |
| `changes` | object | dotted config key → value, e.g. `{"margin.c": "uncapped", "margin.beta_w": 12.0}`. `{}` for the house recipe. |
| `source` | string | the config file, e.g. `configs/recipes/full-merit.toml` |

**`tradeoffs` is required to be non-empty and the page must render it.** A recipe
file that omits it does not load. A page that shows the manifesto and hides the
costs converts a measurement into an advertisement, which is the thing this
project exists not to be.

**`changes` values can be strings where you expect numbers.** `margin.c` is
`"uncapped"` under `full-merit`. JSON has no infinity, `C = inf` is a real value of
the parameter and the limit of the tanh family, and dropping it would remove the
constant that *is* that recipe's argument. Render the value as given.

---

## 4. The `recipe` block on `week-NN.json` and `methodology-NN.json`

Every week document carries it, including the house one, so a page can always name
the value system it is rendering without inspecting its own URL.

```jsonc
"recipe": {
  "slug": "full-merit",
  "name": "Full Merit",
  "one_liner": "...",
  "manifesto": "...",
  "tradeoffs": ["...", "..."],
  "stance": 0,
  "is_house": false,
  "label": "ALTERNATE LENS. Not the published poll.",
  "changes": { "margin.c": "uncapped", "margin.beta_w": 12.0,
               "publication.headline_ordering": "L4_resume_margin" },
  "source": "configs/recipes/full-merit.toml",
  "config_sha256": "…",       // hash of the RESOLVED config, not of a file
  "evidence": {               // §5
    "archive_manifest_sha256": "manifest:…",
    "fit_window_sha256": "…",
    "n_games_in_fit": 1557
  }
}
```

`label` is non-null exactly when the document is **not** the published poll, and
it is the same string in both publication targets and on the share cards. **When
it is non-null the page must show it**, above the table, not in a footnote.

### `poll[]` is unchanged, and one field means something different

Every column is the same as on the published poll. `rank_lo90` / `rank_hi90` /
`rank_median` are the 90% rank interval **on the ordering that sorted this table**,
which differs between recipes. That is the fix, not a caveat: an interval computed
on a different ordering from the rank it sits beside is a false claim, not a weaker
one. `resume_rank_*` and `power_rank_*` mean the same thing under every recipe.

`odds_key`, `tail_p`, `one_in`, `resume`, `resume_margin`, `power` and `gap` are on
every row under every recipe. Nothing was removed to make a lens; a lens changes
which column sorts the table.

### `methodology-NN.json`

Gains `recipe` (identical object) and `gate_note`.

**An alternate lens has no gate verdict**: `gate` is `[]` and `metrics` is `[]`,
and `gate_note` says why. `[gate]` is written against the published poll, and
`cfbpoll backtest` scores orderings under the default config, so attaching those
numbers to a lens would print the *house* poll's verdict on a page describing a
different value system. Render `gate_note` where the gate table would go. Do not
fall back to the season's house gate.

---

## 5. The integrity block, and what the page should do with it

**A recipe changes values. It never changes evidence.** That is the claim the
whole feature rests on, and a claim a reader cannot check is a slogan. So it is
published per week, per recipe:

- `archive_manifest_sha256` — which archive bytes the run read
- `fit_window_sha256` — a digest of the exact frame that was fit
- `n_games_in_fit`

**These three fields are identical across every recipe of a given week.** A page
comparing two lenses can print "same data, same 1,557 games, same digest" from the
documents themselves rather than from a promise in the copy. If they ever differ,
the comparison is between two different measurements and the page should say so
loudly rather than render it.

The enforcement is upstream and does not depend on anyone reading this:
`recipes.EVIDENCE_KEYS` refuses a recipe file that names a key deciding what the
model sees, at load time, before any fit;
[`tests/unit/test_recipes.py`](../tests/unit/test_recipes.py) digests the ingested
frames under all three recipes and asserts byte-identity, and runs the leakage
audit under all three and asserts zero violations in each.

---

## 6. Suggested routes

Not binding. The contract is the documents; this is what they were shaped for.

```
/cfb-poll/2023/week/15                        the published poll (unchanged)
/cfb-poll/2023/week/15?recipe=full-merit      one lens
/cfb-poll/2023/week/15/compare                all three, side by side
```

A query parameter rather than a path segment, for one reason: the published poll
must keep the canonical URL. A lens is a way of *looking at* week 15, not a
different week 15, and a path segment would make three equal-looking URLs where
one of them is the poll and two are not.

---

## 7. Where this contract is weak

- **The gate is house-only.** A page showing three rankings and one gate verdict
  is less honest than one showing three verdicts. Backtesting per recipe is real
  work that has not been done, and `gate_note` is the interim answer.
- **`seasons[].recipes[].weeks` will be sparse in practice.** Alternate lenses are
  precomputed rather than published weekly. Check membership before linking.
- **The roster travels in `index.json` only.** A site that caches `index.json`
  aggressively and a week document lazily can render a manifesto that no longer
  matches the constants in the week doc it is beside. Cache them together, or
  prefer the week document's own `recipe` block when rendering a week.
- **Nothing versions the prose.** `config_sha256` changes when a constant changes;
  editing a manifesto changes no hash anywhere. If that becomes a problem the
  roster needs its own digest.
