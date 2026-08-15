# The fixture contract: what 2025 added

**Audience: whoever builds the 2025 pages.** Everything here is additive.
`schema_version` on `index.json` and on every week document is **still `1`**, no
existing path or field changed type, and a site written against the 2023 tree
renders the 2025 tree unchanged and simply does not draw the new modules.

Companion documents: [`fixture-contract-recipes.md`](./fixture-contract-recipes.md)
for the alternate lenses, [`fixture-contract-projection.md`](./fixture-contract-projection.md)
for the projection card. The decision that produced all of this is
[ADR 0012](./adr/0012-2025-opens.md).

---

## 1. The tree

```
<dir>/2025/week-NN.json              weeks 01-16. NOT 01-15: 2025 has a week 16.
                                     + same_record_pair       (§2)
                                     + same_record_candidates (§2)
<dir>/2025/methodology-NN.json       carries the 2025 HOLDOUT gate, not a tune gate (§4)
<dir>/2025/connectivity-NN.json      unchanged
<dir>/2025/data-NN.json              unchanged
<dir>/2025/divergence.json           unchanged
<dir>/2025/recipes/full-merit/…      weeks 05-16
<dir>/2025/recipes/just-win/…        weeks 05-16

<dir>/2025/revision.json             NEW. The figures the copy quotes.        (§3)
<dir>/2025/projection.json           NEW. Retrospective projection card.      (§5)
<dir>/2025/projection-grading.json   NEW. Projection vs live vs hindsight.    (§5)
```

**Read the week list off `index.json`.** 2023 has 15 regular weeks and 2025 has
16. A hard-coded fifteen anywhere is a bug that only shows up on one season.

---

## 2. `same_record_pair` and `same_record_candidates` on `week-NN.json`

The front door's same-record comparison module. Two teams with identical records
and different numbers beside them is the clearest single demonstration this poll
makes, and **which two is an editorial decision made in the pipeline**, not on the
page.

```jsonc
"same_record_pair": {              // or null
  "pinned": true,
  "why": "Both finished 12-1. …",  // render it; it is the argument
  "excluded_teams": ["Washington"],
  "leader": { "team": "Georgia", "rank": 3, "record": "12-1", "one_in": 86,
              "tail_p": 0.01168, "power": 22.56, "q_ref_team": "…",
              "mark_bg": "…", "mark_fg": "…", "mark_label": "…",
              "logo_url": "…", "logo_url_2x": "…",
              "logo_url_dark": "…", "logo_url_dark_2x": "…" },
  "foil":   { "team": "James Madison", "rank": 14, "record": "12-1", "one_in": 7, … }
},
"same_record_candidates": [
  { "record": "11-2", "leader": "BYU", "leader_rank": 6, "leader_one_in": 45,
    "foil": "North Texas", "foil_rank": 21, "foil_one_in": 4,
    "rank_gap": 15, "excluded": false }
]
```

- **`same_record_pair` is null on most weeks and that is normal.** Only pinned
  weeks carry one. Today that is 2025 week 16. Render nothing when it is null;
  do not fall back to deriving a pair.
- **Both slots carry their own display fields**, so the module never opens the
  poll array to find a logo.
- **`why` is the module's body copy.** A pair shown without its reason is two
  numbers with no argument attached.
- **`same_record_candidates` is every pair in the published top 25 that shares a
  record**, widest rank gap first, with `excluded` flagging any pair touching the
  exclusion list. It exists so the pin can be second-guessed from the document.
  A page need not render it; a reader auditing the choice needs it to exist.

### Why a pin rather than a rule

The first version of this module took the #1 team and the lowest-ranked team
sharing its record. On 2025's final board that returns **nothing**: Indiana
finished 13-0 and no other team in the country shares that record. A rule that
goes silent exactly when the season is most interesting is not a good rule.

The pin lives in `[[publication.pinned_same_record_pairs]]` and
`publish/serving.py` **validates it and refuses to write** if it names a team
outside the top 25, two teams with different records, or an excluded team. The
failure mode being guarded against is silence: a comparison module that quietly
renders nothing is how a claim gets dropped without anybody deciding to drop it.

---

## 3. `revision.json`

The figures the site's copy quotes in prose, counted off the published week
documents rather than recomputed. Written by
`scripts/make_revision_numbers.py`, which reads the fixture tree and cannot reach
the archive.

```jsonc
{
  "schema_version": 1,
  "season": 2025,
  "headline_start_week": 5,
  "definitions": { "rank_delta": "…", "top25": "…", "league": "…" },
  "headline": {                       // the headline_start_week entry, lifted
    "week": 5, "published": true,
    "top25":  { "n": 25, "n_graded": 25, "n_moved": 25,
                "share_moved": 1.0, "mean_abs_delta": 5.24, "max_abs_delta": 18 },
    "league": { "mean_abs_delta": 7.18, "max_abs_delta": 28, "n_ranked": 136 },
    "biggest_move_in_top25": { "team": "Navy", "rank": 22, "hindsight_rank": 40,
                               "rank_delta": -18, "record": "4-0",
                               "direction": "over-rated live" }
  },
  "settled":        { "week": 15, "top25": { … } },   // quietest published week
  "last_published": { "week": 16, "top25": { … } },
  "by_week": [ { "week": 1, "published": false, "top25": {…}, "league": {…},
                 "biggest_move_in_top25": {…} } ]
}
```

**`top25` and `league` are different numbers and must never be quoted as one.**
`league` is every ranked team and is the slice the stability criterion is written
against. `top25` is the slice a reader is looking at. In 2025 week 5 they are 7.18
and 5.24 respectively, and the league figure being the larger of the two is the
finding rather than a caveat.

**`n_moved` may be null**, which means the week has no hindsight surface yet. That
is every week of a live season. Render "not graded yet", never "moved zero".

---

## 4. The gate on `methodology-NN.json` is 2025's own

2025's methodology pages carry the verdict from the **holdout evaluation of 2025**,
not from the tune seasons. Two consequences for a renderer:

- `metrics[].split` reads `holdout_2025_2025`. It read `tune_<min>_<max>`
  unconditionally before ADR 0012, which would have shipped the holdout's numbers
  labelled as tune-season numbers. If a page prints the split, print it verbatim.
- `gate[]` has seven rows and **two of them have status `"not yet decided"`**
  (`brier_beats_all_baselines`, `retro_vs_live_monotone`). Render them as
  undecided. They are not passes and they are deliberately not failures either;
  [`demo/2025-holdout-scorecard.md`](../demo/2025-holdout-scorecard.md) publishes
  the evidence for both and explains why neither is adjudicated.

The verdict is **FAIL**, on four of five decided criteria. Any page rendering 2025
should link the scorecard rather than show a gate table with no way in.

---

## 5. `projection.json` and `projection-grading.json`

`2025/projection.json` is the **identical contract** as `2026/projection.json`,
including the schedule block, so one component renders both. Three additive fields
mark it as retrospective:

```jsonc
"retrospective": true,
"source_season": 2024,
"schedule_source": "The 2025 regular-season calendar from the MIT schedule parquet, …",
"recipe_provenance": { "checked": true, "against": "demo/2026-preseason-projection.json",
                       "identical": true, "note": "…" },
"grading": "2025/projection-grading.json"
```

`recipe_provenance.identical` is the load-bearing one. The coefficients that
produced this card are the coefficients on the published 2026 card, to 1e-9, and
`scripts/make_projection_2025.py` refuses to write the file if they ever differ.
Nothing was refitted or excluded to make 2025 out of sample: `2024 -> 2025` has
never been in `[projection].design_transitions`.

`projection-grading.json` is the "we projected X, the season said Y" document:

```jsonc
{
  "schema_version": 1, "season": 2025, "source_season": 2024,
  "headline_start_week": 5, "headline_eval_label": "2025-regu-w05",
  "surfaces": { "projected_rank": "…", "live_rank": "R(N, N) …",
                "hindsight_rank": "R(N, final) …" },
  "weeks": [ { "eval_label": "2025-regu-w05", "published": true,
               "mean_abs_delta_vs_live": 32.56,
               "mean_abs_delta_vs_hindsight": 30.93,
               "mean_abs_delta_vs_hindsight_top25": 31.00,
               "top25_hits": 13 } ],
  "final": { "eval_label": "2025-post-w01", "rows": [ { "projected_rank": 1,
             "team": "Ohio State", "live_rank": 5, "hindsight_rank": 5,
             "delta_vs_live": -4, "delta_vs_hindsight": -4,
             "projected_power": 34.44, "actual_power": 29.45,
             "power_error": -4.99, "suspect_term": "…",
             "suspect_contribution": … } ] },
  "story_lines": [ "The projection had Colorado at #21. The poll now has them at #102 …" ],
  "attribution": { "prior_power": { "coefficient": -0.34, "verdict": "TOO STRONG", … } },
  "attribution_health_warning": "…"
}
```

- **Sign convention, and it matches `retro.movers` on purpose:** `delta` is
  `projected_rank - poll_rank`. **Positive means the poll has them higher than we
  projected, so we under-rated them.** Two tables with opposite conventions is how
  a reader ends up quoting the wrong direction.
- **`vs_live` and `vs_hindsight` answer different questions** and must not be
  merged. `vs_live` is "how wrong were we about what had happened by week N".
  `vs_hindsight` is "how wrong were we about what these teams turned out to be",
  which is the fairer early reading because a week-5 live poll is itself
  provisional.
- **At the final bucket the two surfaces are the same ranking**, because R(N, N)
  and R(N, final) coincide when N is final. That is arithmetic, not agreement, and
  a page showing the final table should say so or show only one column.
- **`attribution_health_warning` is required rendering** wherever the attribution
  block is shown. One season is one data point about the recipe.
