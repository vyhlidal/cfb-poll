# The fixture contract: the lever grid

**Audience: whoever builds the "tune it yourself" panel on the site.** This is the
whole data contract for a precomputed grid of boards. A reader moves three levers,
the page fetches one small document, and a real alternative poll appears beside the
published one.

Everything below is additive. `index.json` does not change, `schema_version` on
every existing document is **still `1`**, no path or field changes type, and a site
that has never heard of the lever grid renders the tree exactly as it does today.

Companion documents: [`fixture-contract-recipes.md`](./fixture-contract-recipes.md)
for the three named value systems, [`fixture-contract-season-2025.md`](./fixture-contract-season-2025.md)
for what 2025 added. The playground this grid generalises is
[`src/cfbpoll/publish/variants.py`](../src/cfbpoll/publish/variants.py), and the
registry that decides what a reader may touch at all is
[`src/cfbpoll/levers.py`](../src/cfbpoll/levers.py).

---

## 1. The one-paragraph version, and the rule that shapes all of it

**The site does not compute.** There is no JavaScript reimplementation of this
model and there will not be one, because two implementations drift and drift breaks
the only promise this project makes: that an argument about a ranking gets settled
by running one. So every board a reader can reach was produced by the same
`cfbpoll rank` that produced the published poll, fitted ahead of time, and the page
does nothing but fetch the one it was asked for. That is why this is a **grid** and
not a slider: a continuous knob would need a fit per request, and a fit per request
is a model in the browser.

Seventy-two boards, one per combination of three levers. **Eleven of them reproduce
something this project has already published**, which is how you check that the
grid is the pipeline and not a second pipeline.

---

## 2. The three levers and their detents

| lever | config key | detents | count |
|---|---|---|---:|
| Where a blowout stops counting extra | `margin.c` | `1`, `18`, `24`, `32`, `48`, `uncapped` | 6 |
| How much a win is worth on its own | `margin.beta_w` | `0`, `3`, `7`, `12` | 4 |
| What sorts the table | `publication.headline_ordering` | `schedule_odds`, `L4_resume`, `L4_resume_margin` | 3 |

6 x 4 x 3 = **72 combinations**. The published poll is one of them
(`margin.c = 32`, `margin.beta_w = 7`, `schedule_odds`).

The labels are `levers.py`'s own, lifted rather than rewritten, so a panel never
holds a second copy of a plain-football name that could drift from the registry.

### Why these values and not others

**Every detent is a value some document in this repository already argues for.**
That is the whole test, and it is the one `publish/variants.py` set for the eight
shipped variants: "every one of these is a value some defensible poll does use". A
grid that invents settings would be publishing seventy-two boards, most of them
answering nobody's question.

| detent | where it comes from |
|---|---|
| `margin.c = 1` | `configs/recipes/just-win.toml`, and the `margin-c-1` playground variant |
| `margin.c = 18` | the floor of campaign 1's grid, and the `margin-c-18` variant |
| `margin.c = 24` | this project's own value before ADR 0007 replaced it |
| `margin.c = 32` | fitted 2026-08-12 over a 416-cell factorial. ADR 0007. The published poll |
| `margin.c = 48` | `levers.get("margin.c").sweep` |
| `margin.c = uncapped` | `configs/recipes/full-merit.toml`, the `margin-c-uncapped` variant, and the top of the grid campaign 2 pre-registered |
| `margin.beta_w = 0`, `3`, `7`, `12` | `levers.get("margin.beta_w").sweep` exactly, and the same four values the shipped variants use. `3` is Sports-Reference CFB SRS's margin floor in these units |
| the three orderings | the only three strings `[publication].headline_ordering` accepts. `L4_resume` is `just-win`'s, `L4_resume_margin` is `full-merit`'s, and both are candidates from the headline ordering study |

**The brief that commissioned this proposed `margin.c = 8` and it is not here.**
Nothing in this repository argues for 8. It would sit between `just-win`'s 1 and
campaign 1's floor of 18 with no citation under it, and a reader who moved the
lever to 8 would get a board no document explains. `24` and `48` are in its place,
and both have a paper trail.

### Two places where `levers.py` and the shipped artifacts disagree

Both are real and neither is resolved here. They are written down because a
contract that hides a contradiction in its own inputs is worth less than one that
names it.

1. **`levers.get("margin.c").low` is `18`, and two shipped artifacts sit below
   it.** `just-win` is a published recipe at `c = 1.0` and `margin-c-1` is a
   published playground variant at the same value. Either the registry's floor is
   wrong or those two artifacts are outside the range the project will stand
   behind. This grid includes `c = 1` on the strength of the shipped recipe, and
   **a panel that clamps to the registry range would silently refuse a board this
   project publishes**. Flagged for the owner; see §10.
2. **`levers.get("publication.headline_ordering")` is a two-point switch**, `0.0`
   or `1.0`, which can express `L4_resume` and `schedule_odds` and cannot express
   `L4_resume_margin` at all. The config accepts three strings, `full-merit` uses
   the third, and this grid carries all three. **Read the ordering off this
   manifest, not off the registry sweep.**

---

## 3. What is new on disk

```
<dir>/<season>/lever-grid/manifest.json              NEW. The whole board, one fetch.
<dir>/<season>/lever-grid/<cell-id>/week-NN.json     NEW. One combination, one week.

<dir>/index.json                                     UNCHANGED. See below.
<dir>/<season>/week-NN.json                          UNCHANGED. The published poll.
<dir>/<season>/variants/…                            UNCHANGED.
<dir>/<season>/recipes/…                             UNCHANGED.
```

**`index.json` gains nothing, deliberately.** A lever combination is not a recipe
and never enters `recipes.roster()`, exactly as a playground variant does not. The
manifest is the index of this feature and it lives beside the documents it
indexes, so a site can cache the two together and cannot render a stale roster
against fresh boards. Branch on whether `<season>/lever-grid/manifest.json` fetches.

**Today the grid carries one week: 2025 week 16**, the final board of the site's
example season. The path carries the week anyway so that adding a week is adding a
file. See §8.

---

## 4. `manifest.json`

One fetch, and after it the panel knows every lever, every detent, every file and
which one is the poll. It never opens a cell document to find out what a cell is.

```jsonc
{
  "schema_version": 1,
  "generator": "cfbpoll publish lever-grid",
  "season": 2025,
  "weeks": [16],                       // ascending. Every cell carries every week here.
  "n_cells": 72,
  "top_n": 40,                         // rows per cell document (§5)
  "tau_floor": 0.985,

  "published": {                       // the poll, addressed like any other cell
    "cell_id": "c-32-bw-7-odds",
    "detents": { "margin.c": 32.0, "margin.beta_w": 7.0,
                 "publication.headline_ordering": "schedule_odds" },
    "note": "This combination is the published poll. Its board is <season>/week-NN.json."
  },

  "axes": [
    {
      "key": "margin.c",                       // the config key, and the lever key
      "label": "Where a blowout stops counting extra",
      "plain": "Winning by 40 is better than winning by 20. …",
      "evidence": "Fitted 2026-08-12 over a 416-cell factorial …",
      "slug_prefix": "c",
      "detents": [
        { "value": 1.0,        "slug": "1",        "default": false },
        { "value": 18.0,       "slug": "18",       "default": false },
        { "value": 24.0,       "slug": "24",       "default": false },
        { "value": 32.0,       "slug": "32",       "default": true  },
        { "value": 48.0,       "slug": "48",       "default": false },
        { "value": "uncapped", "slug": "uncapped", "default": false }
      ]
    },
    { "key": "margin.beta_w", "slug_prefix": "bw", "detents": [ … ] },
    { "key": "publication.headline_ordering", "slug_prefix": "", "detents": [
        { "value": "schedule_odds",    "slug": "odds",          "default": true  },
        { "value": "L4_resume",        "slug": "resume",        "default": false },
        { "value": "L4_resume_margin", "slug": "resume-margin", "default": false } ] }
  ],

  "cells": [
    {
      "id": "c-32-bw-7-odds",
      "detents": { "margin.c": 32.0, "margin.beta_w": 7.0,
                   "publication.headline_ordering": "schedule_odds" },
      "slugs": { "margin.c": "32", "margin.beta_w": "7",
                 "publication.headline_ordering": "odds" },
      "changes": {},                     // only what differs from the poll
      "n_knobs_moved": 0,
      "is_published": true,
      "files": { "16": "lever-grid/c-32-bw-7-odds/week-16.json" },
      "equivalent_to": { "kind": "house", "id": "house",
                         "path": "2025/week-16.json" }
    }
  ]
}
```

**`cells[].files` is keyed by week as a string**, because JSON object keys are
strings and a page that builds the path by hand will get the zero padding wrong
once. Paths are relative to `<dir>/<season>/`.

**`weeks` never names a week the whole grid does not carry.** A week counts only
when all seventy-two cells have it, so an interrupted generation produces no
manifest at all rather than one whose slider positions 404. A panel cannot tell a
missing file from a network fault, so it is never shown one.

**`equivalent_to` is `null` on most cells and is the interesting field on twelve of
them.** It names something this project has already published at exactly these
constants, so a panel can say "this is `Just Win`" instead of showing an unlabelled
board, and so anybody can check the grid against the tree beside it:

| kind | `id` | `path` | how many |
|---|---|---|---:|
| `house` | `house` | `<season>/week-NN.json` | 1 |
| `recipe` | `full-merit`, `just-win` | `<season>/recipes/<slug>/week-NN.json` | 2 |
| `variant` | the eight ids in `publish/variants.py` | `<season>/variants/<id>/week-NN.json` | 8 |

Eleven cells in total, the house cell included, and every one of them is checked by
`scripts/check_lever_grid.py` (§9). The other sixty-one carry `null`, which is not
a defect: they are combinations nobody has published before, which is the entire
reason to precompute them.

---

## 5. The cell document

`<dir>/<season>/lever-grid/<cell-id>/week-NN.json`. **It is the playground variant
shape**, field for field, because a reader comparing a lever board with a shipped
variant must not find the same number spelled two ways. About 8 KB.

Field values in this block are illustrative except `n_games_in_fit`, which is
2025 week 16's real figure and is the same on every cell and on the published poll.

```jsonc
{
  "schema_version": 1,
  "generator": "cfbpoll publish lever-grid",
  "season": 2025,
  "week": 16,
  "season_type": "regular",

  "cell": {
    "id": "c-1-bw-7-resume",
    "base": "house",
    "detents": { "margin.c": 1.0, "margin.beta_w": 7.0,
                 "publication.headline_ordering": "L4_resume" },
    "changes": { "margin.c": 1.0,
                 "publication.headline_ordering": "L4_resume" },  // vs house only
    "config_sha256": "…",
    "evidence": { "archive_manifest_sha256": "manifest:…",
                  "fit_window_sha256": "…", "n_games_in_fit": 1637 }
  },

  "agreement": {
    "kendall_tau_vs_house": 0.9219,
    "n_moved_5_or_more": 31,
    "n_teams_compared": 136,
    "tau_floor": 0.985,
    "n_knobs_moved": 2,
    "verdict": null
  },

  "rows": [ { "team_id": 84, "rank": 1, "one_in": 1232, "odds_key": 3.090549,
              "resume": 60.0, "resume_margin": 60.0, "power": 26.898623,
              "power_rank": 2, "gap": 33.101377,
              "rank_lo90": 1, "rank_hi90": 23 } ]
}
```

**`detents` is all three levers. `changes` is only what differs from the published
poll.** They are different questions and a panel wants both: `detents` positions
the sliders, `changes` is what the page says changed.

**`rows` carries the top 40, sorted by `rank`, eleven columns.** Same `ROW_FIELDS`,
same order, same six-decimal rounding as a variant document, for the reason
`variants.py` gives: this pipeline reproduces to about 1e-12 on Apple Silicon
rather than bit for bit, so publishing seventeen significant digits would invite a
reader to diff two boards at a precision the arithmetic does not have.

**There are no team names, logos or records on a row.** Join on `team_id` against
the season's week document, which is what a page already has open. Repeating the
display fields seventy-two times would be 72 copies of a mark that has one source.

### `agreement.verdict` is `null` unless exactly one knob moved

This is the one place the lever grid deliberately publishes less than the
playground does.

`dial` and `convention` are a **labelling standard with a fixed meaning**: ADR 0006
fixed the 0.985 tau line against one-knob sweeps, and `publish/variants.py` exists
precisely so that a tau can be attributed to a single constant. A cell that moved
two knobs has a tau nobody can assign to either, and stamping the word `dial` on it
would publish a second, looser definition of a term this project has used
unchanged since ADR 0006.

So:

- `n_knobs_moved == 0` (the published poll): `verdict` is `null`, `tau` is `1.0`.
- `n_knobs_moved == 1`: `verdict` is `"dial"` or `"convention"`, computed exactly
  as `variants.agreement` computes it, and **equal to the shipped variant's
  verdict** for the eleven cells that are shipped variants.
- `n_knobs_moved >= 2`: `verdict` is `null`. `tau` and `n_moved_5_or_more` are
  still published, because "how different is this board" is a fair question at any
  number of knobs. It is the *word* that is unattributable, not the number.

**A panel must render `null` as no verdict, never as "convention".** Absence of a
label is not a finding of no effect.

**`n_moved_5_or_more` is a legibility count and not a significance test**, and the
same warning `variants.py` carries applies here: the published 90% rank intervals
on this poll have a median width of 75 places, so a five-place move is deep inside
the uncertainty the project already publishes. It answers "would a reader notice",
not "does the model claim to know".

---

## 6. Addressing a combination

**The id is a pure function of the three detent slugs**, so a panel computes it
from slider positions and never scans `cells`:

```
cell_id = "c-" + slug(margin.c) + "-bw-" + slug(margin.beta_w) + "-" + slug(ordering)
```

```
c-32-bw-7-odds              the published poll
c-1-bw-7-resume             just-win
c-uncapped-bw-12-resume-margin   full-merit
c-32-bw-0-odds              the margin-beta-w-0 variant
```

The slugs are published in `axes[].detents[].slug` so the page never holds its own
copy of the mapping. **`margin.c = inf` is spelled `uncapped` everywhere**, in the
slug and in every published value, the same word `recipes._jsonable` and
`variants._jsonable` use, because JSON has no infinity and `c = inf` is a real
setting rather than a missing one.

Suggested routes, not binding:

```
/cfb-poll/2025/week/16                                  the published poll
/cfb-poll/2025/week/16/tune                             the panel, opening on the poll
/cfb-poll/2025/week/16/tune?c=1&bw=7&order=resume       one combination
```

Query parameters rather than path segments, for the reason the recipe contract
gives: the published poll keeps the canonical URL. A tuned board is a way of
looking at week 16, not a different week 16.

---

## 7. The integrity block, and what a panel should do with it

**A lever moves values. It never moves evidence.** The grid's overlays are loaded
through `recipes.load`, which runs `assert_values_only` against
`recipes.EVIDENCE_KEYS` before any fit, and resolved through `config.merge_overlay`,
which refuses a key `configs/default.toml` does not define. So the claim is
published per cell rather than promised:

- `archive_manifest_sha256` which archive bytes the run read
- `fit_window_sha256` a digest of the exact frame that was fit
- `n_games_in_fit`

**These three are identical across all 72 cells and identical to the house week's.**
A panel can print "same games, same digest, 72 different answers" off the documents
themselves. If they ever differ, the comparison is between two different
measurements and the page should say so loudly rather than render it.
`scripts/check_lever_grid.py` asserts the equality across every cell and against
the published week document.

---

## 8. Cost, and the 2026 hook

**Timed before the grid was generated, not estimated after.** One `cfbpoll rank`
of 2025 through week 16, single-threaded BLAS, 1000 bootstrap draws, on the
author's machine:

```
real 50.72   user 42.68   sys 6.25
```

So the grid is **72 runs x about 51 seconds, a little over an hour of wall clock**,
serial, plus a few seconds for the publish pass. That is a background job and not
an interactive one. The whole published grid is about 0.6 MB on disk (72 documents
of roughly 8 KB plus the manifest), so a panel that prefetches everything pays
about the same as three weeks of the poll.

**If the grid ever has to get cheaper, cut detents and not levers.** Dropping
`margin.c` to `{1, 18, 32, uncapped}` takes it to 48 runs and 41 minutes while
leaving every lever in place and every shipped artifact still reproduced. Dropping
a lever instead would remove a whole question a reader can ask, and the ordering
lever in particular is the one argument this sport has most often.

**The Sunday hook, which is described here and deliberately not built.** The grid
is generated by `make lever-grid`, whose season and weeks are variables:

```bash
make lever-grid LEVER_SEASON=2026 LEVER_WEEKS=8 FIXTURES=/path/to/data
```

A weekly 2026 regeneration is therefore one line with two variables changed, and it
is additive: it writes `2026/lever-grid/<cell-id>/week-08.json` for every cell and
rewrites `2026/lever-grid/manifest.json` with `weeks` extended. It does not touch
the published poll, the recipes tree, the variants tree or `index.json`, so it
composes with `make fixtures` and neither overwrites the other. **It depends on the
house week being published first**, because a cell's `agreement` block is defined
against the house board and `publish lever-grid` refuses rather than inventing a
baseline. An hour per week is the number whoever schedules it has to plan around,
and it is the reason nothing here assumes the grid is regenerated on the same clock
as the poll.

---

## 9. How to check this contract against the tree

**This is the merge gate for this feature.** It is committed on the branch that
introduces the grid and it is meant to be run by whoever merges or deploys, not
only by whoever generated. It fits nothing, reads no archive and needs no BLAS
pin, so it costs about a second.

```bash
uv run python scripts/check_lever_grid.py --data <dir> --season 2025
```

It opens the manifest and then every file the manifest names, and it fails on any
of:

- **a file whose bytes are not the bytes `publish lever-grid` writes.** Every
  document here is written by one function, which emits sorted keys, compact
  separators and a trailing newline, so the bytes are a pure function of the
  computation. This runs before every other check, because a document that did not
  come out of the pipeline can carry any field you like, including a `generator`
  string that says it did.
- a cell whose file is missing, unreadable or not the shape above
- a cell whose `detents` disagree with the id its own slugs compose
- a cell whose `evidence` block differs from any other cell's or from the house
  week's
- a `verdict` that is non-null with `n_knobs_moved != 1`
- a one-knob cell whose rows differ from the shipped playground variant at the same
  constants, or a recipe-equivalent cell whose ordering differs from the published
  recipe board
- the published cell's rows differing from `<season>/week-NN.json` over the rows
  they share

The last two are the ones worth understanding: they are what makes "the grid is the
pipeline" checkable rather than asserted.

### Why the byte check exists

On 2026-08-17, while this grid was being generated, seventy-one cell documents and
a `manifest.json` were written into the published tree carrying
`"generator": "cfbpoll publish lever-grid"`, placeholder evidence digests, and
`n_games_in_fit: 1608`, which is a number that never existed in any run: it was a
placeholder in the first draft of this document, corrected to the real 1637 before
any board was published. They were pretty-printed and unsorted, and that is what
gave them away first.

Two lessons are worth writing down rather than fixing quietly. **A generator field
is a claim and not a provenance record**, so the check that matters is the one a
writer cannot assert. And **this contract is readable by anything that can read a
file**, so its example JSON will occasionally be mistaken for, or dressed up as,
real output. The example blocks are labelled illustrative for that reason, and the
byte check is what stops the mistake from reaching a reader.

---

## 10. Where this contract is weak

- **`levers.py` disagrees with this grid in two places** (§2). The registry's
  `margin.c` floor of 18 excludes a shipped recipe, and its ordering lever cannot
  express the third legal value. A panel built off the registry and a panel built
  off this manifest would offer different sets of boards. The registry is the
  document that should move, and moving it is the owner's call.
- **Three levers is not "the levers".** `levers.py` publishes thirteen, eight of
  them on the projection and one, `weights.recency_gamma`, on the poll. Recency is
  a genuine football conviction ("does September still count in December") and it
  is not in this grid, because a fourth axis at five detents multiplies the cost by
  five. Say "three levers" on the page rather than "the levers".
- **One week.** The grid is 2025 week 16 only. A reader cannot tune week 9. The
  path is shaped for more weeks and the cost is an hour each.
- **No gate verdict, no backtest, and no scorecard.** Same as a recipe and a
  variant: `[gate]` is written against the published poll and none of these
  seventy-two boards was scored against it. A panel must not borrow the house
  poll's verdict for a tuned board.
- **`equivalent_to` is computed from the constants, not from a diff of the
  documents.** It says "these are `just-win`'s constants", and the check script
  then proves the boards agree. If somebody edits `configs/recipes/just-win.toml`
  without regenerating the grid, the label goes stale and only the check script
  will notice.
- **Nothing versions the axis prose.** The labels and `plain` strings are lifted
  from `levers.py` at generation time. Editing them there changes no hash here.
