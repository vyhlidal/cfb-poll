# The fixture contract: the Projection

`cfb-poll-data/<season>/projection.json`, written by `cfbpoll projection fixture
--to <dir>` and read by `src/lib/cfb-poll/projection.ts` in the sandbox app.

This document is the producer's half. The consumer's half is the TypeScript
interface, and where the two disagree the TypeScript is authoritative about
SHAPE and this document is authoritative about MEANING.

**The Projection is not the Poll.** It is a labelled prediction, published to be
graded in public by a poll whose math it is forbidden to touch. Everything in
this file is banned from every poll layer, mechanically, by
`PROJECTION_INPUT_PATTERNS` in `src/cfbpoll/validate/leakage.py`. See
[ADR 0010](adr/0010-projection-and-poll.md).

---

## 1. The two rules that bind every field

1. **The site derives nothing.** Every number that appears on screen appears
   verbatim in a field here. Displayed quantities are **pre-formatted strings**,
   not floats, because a renderer that decides the decimal place is a renderer
   that can disagree with the artifact a reader downloads.
2. **A missing file is a legitimate answer.** The loader returns `null` on
   ENOENT and the card renders its "coming this week" state. The producer's
   failure mode is to write nothing, never to write a placeholder.

Two corollaries the pipeline enforces rather than remembers:

- `headline`, `basis`, `note` and every generated sentence must be **complete
  sentences** ending in terminal punctuation. The card prints `basis` and
  continues in the same paragraph, so a fragment produces prose that does not
  parse. `_assert_sentence` raises.
- No **em dashes, en dashes or double hyphens** in any copy field. Report 08
  bans them from the front door's visible text; `_assert_no_em_dash` raises. The
  companion rule against "X, not Y" constructions cannot be linted and is a
  matter of writing the sentence affirmatively.

`schema_version` is **1**. Everything in §4 and §7 was added additively, so a
consumer written against the original field set stays valid: new keys appeared,
none changed meaning, none were removed.

**The 2026-08-17 change is the row count, and it is not a schema change.** This
document shipped 25 rows and now ships the whole ranked board, about 138 rows.
Nothing about a row changed; there are simply more of them, and every consumer
already slices: `ProjectionBoard` and `ProjectionFigureTable` take `limit={25}`,
and every share-card variant takes its own count from `BUILDERS`. A consumer that
renders `rows` unsliced was already relying on the producer to do its limiting,
which is not something this contract ever promised.

Why it changed: the front door tells a reader that the promotion ceiling holds
North Dakota State at 33rd, and a reader who went to check found a board that
stopped eight rows short. Copy that invites checking has to be followed by a
document the check can be done in. It also makes the `projection_grid` card
buildable, which needs a board wider than 25 by definition.

---

## 2. Document-level fields

| field | type | meaning |
|---|---|---|
| `schema_version` | int | 1 |
| `season` | int | the season being projected |
| `status` | `"coming"` \| `"published"` | **authoritative**, never inferred from `rows`. A complete projection may sit on disk dark |
| `published_at` | str \| null | ISO 8601 |
| `grading_start_week` | int | the week the poll begins grading this in public. Read from `[publication].headline_start_week`, never typed |
| `label` | str | **the marker every surface showing this document must display**, in the same words everywhere. `projection.PROJECTION_LABEL` |
| `headline` | str | the one sentence the card leads with, verbatim |
| `basis` | str | what the projection was built from. The card continues from it |
| `note` | str \| null | optional second sentence |
| `backtest` | object \| null | §3 |
| `schedule` | object \| null | §4 |
| `rows` | array | **every ranked team**, about 138 of them. The site renders 25 |
| `projection_version` | str | the recipe that produced this. Not rendered |
| `provenance` | object | §7. **Never null** |

`projection_version` exists because the grading loop is season-over-season: a
published projection that cannot say which recipe made it cannot be graded
across years.

`label` is the projection's counterpart to `recipes.ALTERNATE_LABEL`
(`docs/fixture-contract-recipes.md` §4): a document that is not the published
poll says so, in the same string, on every surface that shows it. It is a FIELD
rather than copy in a renderer because the surface most likely to arrive with no
context at all is a share card in somebody's timeline, and a card cannot draw the
board without also being handed the sentence that says what the board is. The
share-card variants `projection_top10` and `projection_top25` print it in the
accent slab above the headline; a site that shows the board without it is not
honouring this contract.

### The share cards

`cfbpoll publish cards --variant projection_top10 --projection <path>` writes
`<season>-projection-top10.{svg,png}`, and `projection_top25` writes the 25-row
version. No week is in the filename because a preseason projection is one claim
about a whole season. Both draw ONLY from this document: the right-hand column is
`projected_wins` printed verbatim, the banner is `label`, the thesis is
`headline`, and the footer is `projection_version`, `grading_start_week` and the
three `backtest` hit counts. One top 25 rather than the poll's two, on the
1200x628 `summary_large_image` canvas, because the projection ships once a year
and its job is to be the image that embeds anywhere.

A card is refused when `status` is not `"published"`. `status` is authoritative,
so drawing one from a dark document would publish the thing the field exists to
keep unpublished.

---

## 3. `backtest` — the honest result, and it is not gated

Present whenever the backtest has been run; `null` when it has not, because a
card must never carry a quality claim nobody measured.

| field | type |
|---|---|
| `headline` | str, one to three sentences |
| `ap_top25_hits`, `projection_top25_hits`, `naive_top25_hits` | str, 1dp |
| `transitions` | int |
| `source` | str, a repo path |

**The sentence is templated from the measured values, never written out.** Typing
it would put the same figure in two places that drift apart the first time the
recipe is refitted. It reports a win as readily as a loss; a template that could
only phrase a defeat would be a disclaimer wearing a measurement's clothes.

The block **is not gated on `status`**. It describes how the METHOD has scored
across past seasons rather than how this particular projection turned out, so it is
equally true while the card is dark. Gating it would make the one unflattering
fact on the card the last thing to appear.

---

## 4. `schedule` — why the board's order is what it is

The projection **ranks on projected power** and **displays win totals**, and
those two disagree: on the 2026 projection Ohio State is first on 8.8 projected
wins while Texas Tech is fifth on 9.6. (These are the live values under
`projection-3.0.0`. The block is templated from whatever the run measures, so a
regeneration that reorders the board rewrites this sentence with it — which is
the reason it is a block rather than prose.) Without this block a reader cannot tell
a deliberate ordering from a broken one, and they are right not to.

| field | type | meaning |
|---|---|---|
| `median_schedule_team` | str | whose calendar every team is scored against |
| `median_schedule_strength` | str, 1dp | that calendar's opponent quality |
| `median_schedule_games` | int | how many games it has |
| `field_size` | int | teams with a full schedule, i.e. the denominator of every rank |
| `note` | str \| null | the gloss line |
| `uncertainty_note` | str \| null | the sigma caveat, §5 |
| `promotion_note` | str \| null | the FCS-promotion caveat, §5 |
| `promoted_teams` | str \| null | who was promoted, already joined for printing. §5 |
| `contrast` | object \| null | the gloss pair, below |

`contrast` carries `higher_team`, `higher_rank`, `higher_wins`,
`higher_on_lower_schedule`, the four `lower_*` counterparts, and a templated
`headline`. Every number is a 1dp string; the ranks are ints.

**It is anchored on the top-ranked team**, and the partner is the top-25 team
with the most projected wins. The card's question is "why is the team you put
first, first", not "why is 19th ahead of 23rd". The obvious alternative rule,
maximise the inversion anywhere, selects a pair nobody asked about and stakes the
showcase example on a promoted FCS team the artifact separately warns about.

**`contrast` is `null` when the top team also wins the most.** A season where the
board and the win column agree needs no gloss, and a device that could only
phrase a paradox would manufacture one the first year there is not one.

### The three schedule quantities do different jobs

| row field | what it is | what it cannot do |
|---|---|---|
| `schedule_strength` | mean opponent projected power, **neutral field** | say what that is worth in wins, the unit beside it |
| `wins_on_median_schedule` | this team scored against `median_schedule_team`'s calendar. **The load-bearing field** | nothing; this is the column that makes the ordering self-evident |
| `contrast` | the pairwise swap, most vivid of the three | scale. It is O(n²) and needs two named teams, so it is a gloss and never a column |

`schedule_strength` is **neutral field by decision**: opponent quality only, with
no home-field term in it. One number blending "who you play" with "where you play
them" can be checked against neither, and home field is 3.95 points across six or
seven home games, so this is material rather than a rounding question. Venue
ships as `home_games` beside it. `wins_on_median_schedule` **does** carry site,
because it is a win total and one that ignored venue would be wrong.

The median schedule is **a real team's calendar**, not a synthetic one. A
"median opponent repeated twelve times" would be easier and would invent a
schedule nobody plays. This one is nameable, so a reader can go and check it.

---

## 5. `opponent_source`, and the three caveats that ship as fields

### `opponent_source` semantics

`forward.expected_wins` resolves every opponent's rating through one function,
`forward.rating_resolver`, which returns a provenance string:

- **`"projection"`** — the recipe could see this team: it has a
  returning-production row, a portal row and a coaching row. All FBS teams.
- **`"mean_reversion_only"`** — the recipe could not. CFBD publishes no
  offseason data for FCS teams, so they get `intercept + phi × (prior rating −
  centre)`: the recipe with its three offseason terms silent, which is what "we
  know last season and nothing else" should produce.

A team's `opponent_source` on the win table is `"projection"` when every opponent
resolved the first way and `"mixed"` when any resolved the second. On the fixture
this surfaces per row as the boolean **`schedule_is_mixed`**.

**It is not a defect flag.** It says the mean contains two kinds of number, and a
card is entitled to know that before it prints a schedule-strength figure to one
decimal place. Most FBS teams schedule at least one FCS opponent, so most rows
are `true`.

### The caveats are fields, not component copy

All three are templated from live values, so they go stale with the data or not
at all. A caution the site hard-codes stops being true the first time the numbers
move and nobody re-reads the JSX.

- **`uncertainty_note`** — every win total comes from a distribution ~20 points
  wide, because in August both teams in a game are projections rather than
  measurements. `sd(margin | projection) = sqrt(sigma_game² + 2 × residual_sd²)`.
  This compresses the spread: teams differ by less in these columns than they
  will by December. That is the correct statement of how little is known in
  August, not a defect being confessed.
- **`promotion_note`** — teams promoted from FCS carry a prior rating earned
  against FCS opposition, and this note says what the model does about it:
  the crossover games price the move, the games promoted programs have actually
  played give part of it back, and a ceiling stops the correction extrapolating
  past the best first FBS season on record. Every figure is templated from the
  live `DivisionCalibration`, so the sentence cannot outlive the constants.
  `null` in a season with no promotions. **`promoted_teams`** carries the names
  beside it, joined and ready to print, so no renderer has to hard-code two
  schools that change the season a third program comes up.

  **This note was rewritten on 2026-08-17 and the old one is worth naming.** It
  said any schedule containing a promoted team "is measured against a softer
  standard than the one they are about to be held to, and the bottom of the
  schedule ranking is correspondingly less firm than the numbers make it look".
  That was true until [ADR 0014](adr/0014-the-liberation.md) measured the
  boundary. Afterwards it described an unfixed softness that had been fixed,
  which undersells the work and is false, and false is the half that matters.
  A calibration that could not be measured, in a fork whose archive holds too few
  crossover games, carries the ratings across unchanged, and there the old
  sentence is true again and is the one that ships.
- **`schedule_is_mixed`** — above, per row.

---

## 6. Row fields

| field | type | notes |
|---|---|---|
| `rank`, `team_id` | int | |
| `team`, `abbreviation`, `conference` | str / str \| null | |
| `logo_url`, `logo_url_2x`, `logo_url_dark`, `logo_url_dark_2x` | str \| null | null when `[display].logos` is false |
| `mark_bg`, `mark_fg`, `mark_label` | str | the generated mark, contrast-repaired upstream |
| `projected_wins` | str, 1dp \| null | |
| `projected_power` | str, 1dp \| null | **the column the board sorts on** |
| `schedule_strength` | str, 1dp \| null | neutral field |
| `schedule_strength_rank` | int \| null | 1 = hardest. Null below the game floor |
| `schedule_field_size` | int \| null | the denominator of that rank |
| `home_games` | int \| null | |
| `schedule_is_mixed` | bool \| null | §5 |
| `wins_on_median_schedule` | str, 1dp \| null | |
| `note` | str \| null | one templated clause, never hand-written. Null when no term moved the team by half a point |

Display fields come from the poll's own machinery (`ingest/teams.mark_for`, the
`[display]` logo template) because the projection card and the poll table share a
page, and a school whose colours changed between them would read as a bug in
whichever the reader trusts less.

---

## 7. `provenance` — the Projection's own receipt

Added 2026-08-17, additively, and **never null**. `schedule` and `backtest` are
absent when nobody measured the thing they describe, which is the right answer for
an unmeasured claim. Something produced this file either way, so provenance always
has an answer; fields the producer could not supply are null individually.

| field | type | meaning |
|---|---|---|
| `projection_version` | str | the recipe that produced this board |
| `source_season` | int \| null | the season whose final ratings every team starts from |
| `fitted_on_transitions` | array of [int, int] \| null | the fit window, pair by pair |
| `fit_window` | str \| null | the same window in one line, e.g. `2021 to 2022 through 2024 to 2025` |
| `fit_rule` | str \| null | ADR 0014's discipline, stated about this season. A complete sentence |
| `generated_at` | str \| null | ISO 8601. Defaults to `published_at` |
| `git_sha` | str \| null | the commit, from the same helper the poll's `_run.json` uses |
| `config_hash` | str \| null | sha256 of `configs/default.toml` |
| `rebuild` | str | `publish.REBUILD_COMMAND`, the command that rebuilds THIS document |

**The failure this block exists for is on the published site.** The front door
prints one provenance footer on every route, and in August the board above it is
the Projection while the footer is the Poll's: the poll's hashes, and "the one
command that rebuilds it" naming a `cfbpoll rank` of a different season by a
different machine. Every word of it is true about a document the reader is not
looking at. The renderer was not wrong to print what it had; it had nothing else.

`rebuild` names the **make target**, not the bare verb, because this document
fits: an OLS solve over the design transitions on top of the walk-forward L3 that
the carried ratings come off. `make projection-fixture` carries the
single-threaded BLAS pin; `uv run cfbpoll projection fixture` does not.

`fit_rule` is templated rather than written, because the sentence it replaces
went stale. "Nothing in this model has ever been tuned after 2023" stopped being
true when `design_transitions` gained 2024 to 2025, and the rule ADR 0014 states
instead is both true and stronger: a recipe projecting season Y may fit on
transitions whose target season finished before Y, and on nothing else.

---

## 8. Where this contract is weak

- **`schedule_strength` is a mean, so it hides shape.** Two teams with the same
  figure can face very different distributions: one with twelve average opponents
  and one with three elite and nine poor. `wins_on_median_schedule` is partly
  immune, because a win total is nonlinear in opponent quality, but nothing here
  publishes the variance.
- **`MIN_FULL_SCHEDULE_GAMES` is 10 and is not tuned.** It exists so a
  four-game fragment in the archive does not get ranked against twelve-game
  schedules and make `field_size` a lie. No search chose the number.
- **The median schedule is one team's calendar, so it inherits that team's
  quirks** — its bye weeks, its home-and-away split, its conference. A different
  median team in a future season will shift every `wins_on_median_schedule`
  slightly, which is why the team is named on the artifact rather than implied.
- **Schedules change after August.** The projection is frozen and is not re-run
  when they do, so a late cancellation leaves `schedule_strength` describing a
  calendar that no longer exists. The artifact states the game count it was
  built from.
