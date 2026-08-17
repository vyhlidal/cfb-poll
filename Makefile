# cfb-poll — the one-command fork story (research report 03 §9.1), and as of
# 2026-08-13 it is a story that runs.
#
#     git clone https://github.com/vyhlidal/cfb-poll && cd cfb-poll
#     make .venv && make rankings
#
# `.venv`, `archive`, `rankings`, `backtest`, `grid`, `cards`, `fixtures`,
# `demos`, `test` and `lint` do real work on a fresh clone with no accounts and no
# keys. `replay`, `replay-tolerant` and `site` still print exactly what they will
# do and exit 0, so the contract stays readable before those parts exist. Each
# stub maps 1:1 to a `cfbpoll` CLI verb.

UV ?= uv
CONFIG ?= configs/default.toml
OUT ?= out
SEED ?= 20260812
DRAWS ?= 1000
JOBS ?= 4

.PHONY: help rankings archive archive-lock backtest cards demos fixtures \
        recipe-fixtures variants projection projection-audit projection-2025 \
        projection-chain projection-fixture projection-cards projection-all levers \
        lever-grid holdout-scorecard revision-numbers replay replay-tolerant grid \
        challenge site guard preflight weekly-dry-run test lint clean

help:
	@echo "cfb-poll — PARTIAL BUILD. 'rankings', 'archive', 'backtest', 'grid', 'demos' work."
	@echo
	@echo "  make .venv            uv sync --locked  (installs Python 3.12 + pinned wheels)"
	@echo "  make rankings         archive sync -> rank -> the poll in out/"
	@echo "  make archive          fetch + sha256-verify the MIT archive (~0.55 GB)"
	@echo "  make archive-lock     regenerate the committed lockfile from a backfill"
	@echo "  make backtest         walk-forward 2021-2023 vs every baseline"
	@echo "  make challenge        score ONE community entry on the same harness"
	@echo "  make grid             the R(N,K) retroactive triangle for one season"
	@echo "  make cards            render the weekly share card (SVG + PNG)"
	@echo "  make fixtures         rank every week of a season -> publish the JSON tree"
	@echo "  make recipe-fixtures  the same weeks under each ALTERNATE LENS (ADR 0011)"
	@echo "  make variants         eight one-knob variants -> thin ordering documents"
	@echo "  make lever-grid       72 precomputed boards, one per lever combination"
	@echo "  make demos            regenerate demo/ from the local archive"
	@echo "  make projection       the 2026 Projection - a PREDICTION, never the poll"
	@echo "  make projection-audit prove the Projection and the Poll stay separate"
	@echo "  make projection-2025  the shipped recipe applied to 2024->2025, and graded"
	@echo "  make holdout-scorecard re-render the 2025 verdict (ADR 0012; scores nothing)"
	@echo "  make revision-numbers the flagship figures, off the published fixtures"
	@echo "  make replay           offline byte-match replay of a known week   [stub]"
	@echo "  make replay-tolerant  same replay, ~1e-12 tolerance (for a Mac)   [stub]"
	@echo "  make site             build the static site into site/_build      [stub]"
	@echo
	@echo "  THE SUNDAY AUTOMATION (ADR 0002). Nothing below fires on its own:"
	@echo "  every trigger in ops/arming.toml is committed false."
	@echo "  make guard            would the Sunday job run right now, and why not"
	@echo "  make preflight        which verbs the Sunday job needs are still stubs"
	@echo "  make weekly-dry-run   the whole job, printed, executing nothing"
	@echo
	@echo "  make test / make lint pytest / ruff"
	@echo
	@echo "VARIABLES, with their defaults. A default you did not know about is the"
	@echo "most common way a first command surprises you, so they are printed here."
	@echo
	@echo "  OUT=$(OUT)   CONFIG=$(CONFIG)"
	@echo "  archive:   SEASONS=$(SEASONS)<all>  ONLY=$(ONLY)<everything, incl. play-by-play>"
	@echo "  rankings:  RANK_SEASON=$(RANK_SEASON)  RANK_WEEK=$(RANK_WEEK)  RANK_RECIPE=$(RANK_RECIPE)"
	@echo "  backtest:  BACKTEST_SEASONS=$(BACKTEST_SEASONS)"
	@echo "             SYSTEMS=$(SYSTEMS)"
	@echo "             (SYSTEMS=schedule_odds,resume settles an ORDERING argument;"
	@echo "              read retrodictive_violation_rate, not MAE)"
	@echo "  challenge: CHALLENGE_ENTRY=$(CHALLENGE_ENTRY)"
	@echo "             CHALLENGE_SEASONS=$(CHALLENGE_SEASONS)"
	@echo "  grid:      GRID_SEASON=$(GRID_SEASON)"
	@echo "  fixtures:  FIXTURES=$(FIXTURES)   <- OUTSIDE this repo; always override"
	@echo "             FIXTURE_SEASON=$(FIXTURE_SEASON)"
	@echo "  variants:  VARIANT_SEASON=$(VARIANT_SEASON)"
	@echo "  lever-grid: LEVER_SEASON=$(LEVER_SEASON)  LEVER_WEEKS=$(LEVER_WEEKS)"
	@echo "             (72 fits per week, about an hour. Background it.)"

# The only target that works today. `uv sync --locked` errors instead of
# updating if uv.lock is stale, which is exactly what CI and a stranger both want.
.venv:
	$(UV) sync --locked

# Real, and it is THE FORK PROMISE (report 03 §9.1). Clone, `make .venv`,
# `make rankings`, and a poll comes out. No account, no API key, no Docker, no
# sudo - not ours, not anyone's - because `archive` pulls from a public GitHub
# release of MIT-licensed data and everything after it is local compute.
#
# RANK_SEASON DEFAULTS TO A COMPLETE HISTORICAL SEASON ON PURPOSE. Ranking "now"
# means resolving the current week, which needs CFBD's /calendar, which needs a
# key - so a keyless default that pretends otherwise would fail on the one
# command a stranger types first. 2025 is the sealed holdout and is not the
# default either. Override both freely: `make rankings RANK_SEASON=2022
# RANK_WEEK=12`.
#
# RANK_RECIPE EXISTS SO A FORK NEVER HAS TO LEAVE THE MAKE TARGET. It defaults to
# `house`, which is `cfbpoll rank`'s own default, so this target's behaviour is
# unchanged. It is here because the one thing a fork does constantly is run its
# own value system, and without a variable the only way to do that was the bare
# CLI - which does not carry the single-threaded BLAS prefix above, so the
# obvious next step after writing a recipe was a nondeterministic run. Pair it
# with OUT to keep two boards side by side:
#
#     make rankings RANK_RECIPE=just-win OUT=out/just-win
RANK_SEASON ?= 2023
RANK_WEEK   ?= 15
RANK_RECIPE ?= house
rankings: .venv archive
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run cfbpoll rank --config $(CONFIG) --recipe $(RANK_RECIPE) \
	    --season $(RANK_SEASON) \
	    --through-week $(RANK_WEEK) --seed $(SEED) --draws $(DRAWS) --out $(OUT)
	@echo
	@echo "The poll is $(OUT)/poll.csv and $(OUT)/poll.json; the run record, with"
	@echo "which archives it read and every constant it used, is $(OUT)/_run.json."
	@echo "'cfbpoll rank' ran the leakage audit BEFORE it fit anything."
	@echo
	@echo "STILL A STUB: 'cfbpoll site build'. There is no static site yet, so the"
	@echo "poll is files rather than a page (report 03 §7.1)."

# Real. ~0.55 GB from OUR release assets, every file sha256-checked against the
# committed lockfile before any consumer reads it. Add SEASONS=2023 to pull one
# season, or ONLY=schedules,crosswalk for a scores-only run that skips the 0.52 GB
# of play-by-play.
#
# SEASONS AND ONLY ARE WIRED IN RATHER THAN DOCUMENTED, WHICH THEY WERE NOT.
# The comment above has promised `SEASONS=2023` since this target was written and
# the variable was never passed to the command, so `make archive SEASONS=2023`
# silently pulled all 0.55 GB. That is the worst possible place for a silent
# no-op: it is the narrowing flag, on the slowest target, and it is the first
# thing anybody trying to iterate quickly reaches for. Empty stays empty, so the
# default behaviour is unchanged.
ARCHIVE_ARGS ?=
SEASONS      ?=
ONLY         ?=
archive: .venv
	$(UV) run cfbpoll archive sync --source sportsdataverse --verify \
	  $(if $(SEASONS),--seasons $(SEASONS)) $(if $(ONLY),--only $(ONLY)) \
	  $(ARCHIVE_ARGS)

# Regenerate data/manifests/sportsdataverse.lock.json from a completed backfill.
# Only needed after a backfill or a new release tag; the lockfile is committed.
archive-lock: .venv
	$(UV) run cfbpoll archive lock

# Real. Single-threaded BLAS is not optional: multi-threaded reductions sum in a
# nondeterministic order and the replay job asserts byte-equality (report 03 §9.3).
# With L1 and L3 in the systems list this reads the play archive (~0.3 GB for the
# tune seasons) and takes about a minute; scores-only runs never touch it.
#
# SYSTEMS AND BACKTEST_SEASONS ARE OVERRIDABLE, AND SYSTEMS IS THE ONLY WAY TO
# SETTLE AN ORDERING ARGUMENT. `challenge run` scores a rating METHOD; it cannot
# score a headline ordering, because a parameter entry is always filed under the
# `schedule_odds` row. Comparing orderings means naming them here:
#
#     make backtest SYSTEMS=schedule_odds,resume
#
# and reading `retrodictive_violation_rate`, which is the metric those two rows
# exist for. Without this variable that comparison had no BLAS-safe path at all.
# Valid names: schedule_odds, resume, l3, l2, l1, home_team, winpct, colley, srs,
# elo, random_walker (alias `walker`), closing_line, cfp. Comma-separated, no
# spaces. The home-team floor is always included whether or not it is named.
SYSTEMS          ?= schedule_odds,resume,l3,l2,l1,colley,srs,elo,walker,winpct
BACKTEST_SEASONS ?= 2021-2023
backtest: .venv
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run cfbpoll backtest --config $(CONFIG) \
	    --systems $(SYSTEMS) \
	    --seasons $(BACKTEST_SEASONS) --out $(OUT)
	@echo
	@echo "2024 (validate) and 2025 (holdout) are NOT scored here. 2025 is a"
	@echo "single-shot test and the harness refuses it without --unlock-holdout."

# Real, and it is the ONLY supported way to regenerate the tree the website reads.
#
# This target exists because its absence caused a real failure. `publish fixtures`
# publishes one week; the site reads a whole season; so regenerating the published
# tree meant looping a shell over fifteen run directories by hand. A procedure
# that lives in a terminal history cannot be reviewed, cannot be repeated by the
# next person, and gives nobody a way to notice it was skipped - and it was
# skipped, leaving the site serving a fixture set two model versions old while a
# session reported it regenerated.
#
# FIXTURES points at the sandbox app's data directory by default, because that is
# the tree the site actually reads. Override it to publish somewhere else.
#
# The per-week runs land directly in $(OUT), one directory per week, so that the
# no-argument `cfbpoll publish fixtures` — whose `--from` defaults to out/ —
# republishes the whole season. The command an operator is most likely to type is
# the command that does the right thing.
#
# IT DEPENDS ON `backtest` ON PURPOSE, and that is not belt-and-braces. The
# methodology page's gate table and baseline comparison are read out of
# backtest_metrics.json, so publishing against a stale one puts numbers on the
# site that no longer describe the model - the same failure as a stale fixture
# set, one document over. It costs a couple of minutes, once, at publication.
FIXTURE_SEASON ?= 2023
FIXTURE_WEEKS  ?= 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15
RUNS           ?= $(OUT)
FIXTURES       ?= ../sandbox/cfb-poll-data
fixtures: .venv backtest
	@for w in $(FIXTURE_WEEKS); do \
	  printf 'rank %s week %s\n' "$(FIXTURE_SEASON)" "$$w"; \
	  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	    $(UV) run cfbpoll rank --config $(CONFIG) --season $(FIXTURE_SEASON) \
	      --through-week $$w --seed $(SEED) --draws $(DRAWS) \
	      --out $(RUNS)/w$$(printf '%02d' $$w) >/dev/null || exit 1; \
	done
	$(UV) run cfbpoll publish fixtures --from $(RUNS) --out $(FIXTURES) \
	  --backtest $(OUT)/backtest_metrics.json

# Real, and it is the ONLY supported way to regenerate the ALTERNATE LENSES
# (configs/recipes/, ADR 0011, docs/fixture-contract-recipes.md).
#
# IT DOES NOT REGENERATE THE PUBLISHED POLL. That is `make fixtures`' job, and
# writing the house tree from two commands would be two procedures that have to
# agree forever. This one writes only `<season>/recipes/<slug>/`, into the same
# destination, additively, so the two targets compose and neither overwrites the
# other's files. Run `make fixtures` first if the house tree is stale.
#
# IT ALSO DOES NOT DEPEND ON `backtest`, and that is not an oversight. An
# alternate lens publishes no gate verdict at all: `[gate]` is written against the
# published poll, and attaching the house poll's numbers to a page describing a
# different value system would be worse than publishing none. The document says so
# in `gate_note` rather than leaving an empty table to read as a mistake.
#
# WEEKS 5-15, NOT 1-15, AND THE REASON IS THE SAME ONE THAT SETS
# `headline_start_week`. Weeks 1-4 are explicitly not the poll: they ship a
# connectivity report and provisional output. Offering a reader three value
# systems to rank a table with is offering a choice about something that is not yet
# a ranking, so the lenses start where the poll starts.
RECIPES       ?= full-merit just-win
RECIPE_SEASON ?= 2023
RECIPE_WEEKS  ?= 5 6 7 8 9 10 11 12 13 14 15
RECIPE_RUNS   ?= .cache/recipes
recipe-fixtures: .venv archive
	@for r in $(RECIPES); do \
	  for w in $(RECIPE_WEEKS); do \
	    printf 'rank %s %s week %s\n' "$$r" "$(RECIPE_SEASON)" "$$w"; \
	    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	      $(UV) run cfbpoll rank --config $(CONFIG) --recipe $$r \
	        --season $(RECIPE_SEASON) --through-week $$w --seed $(SEED) \
	        --draws $(DRAWS) --out $(RECIPE_RUNS)/$$r/w$$(printf '%02d' $$w) \
	        >/dev/null || exit 1; \
	  done; \
	  $(UV) run cfbpoll publish fixtures --from $(RECIPE_RUNS)/$$r --out $(FIXTURES) || exit 1; \
	done
	@echo
	@echo "The lenses are $(FIXTURES)/$(RECIPE_SEASON)/recipes/<slug>/. The published"
	@echo "poll is untouched at $(FIXTURES)/$(RECIPE_SEASON)/week-NN.json."

# Real, and it is the ONLY supported way to regenerate the KNOB PLAYGROUND
# (src/cfbpoll/publish/variants.py).
#
# WHAT IT MAKES. Eight one-knob perturbations of the published poll across three
# axes, each ranked for every week in VARIANT_WEEKS and published as a THIN
# ordering document at `<season>/variants/<id>/week-NN.json` — top 40 rows, eleven
# columns, and an agreement block whose `verdict` is the word `dial` or
# `convention`, chosen by the pipeline against the 0.985 tau line ADR 0006 fixed.
# About 5 KB each, against 200 KB for a week of the poll.
#
# IT DOES NOT REGENERATE THE PUBLISHED POLL AND IT DEPENDS ON IT. A variant is
# defined as a difference from the house board, so `<season>/week-NN.json` must
# already be in FIXTURES or `publish variants` refuses rather than inventing a
# baseline. Run `make fixtures` first if the house tree is stale. Like
# `recipe-fixtures` this writes only into its own subtree, so the three targets
# compose and none overwrites another's files.
#
# IT DOES NOT DEPEND ON `backtest`, for the same reason `recipe-fixtures` does
# not: a variant publishes no gate verdict at all. `[gate]` is written against the
# published poll, and putting the house poll's numbers beside a board produced by
# different constants would be worse than publishing none.
#
# THE OVERLAYS ARE GENERATED, NOT COMMITTED. `write_overlays` writes one real
# recipe file per variant into scratch, so `cfbpoll rank` loads them through the
# same `assert_values_only` and `merge_overlay` a hand-written recipe goes through
# and stamps the variant's own id on the run. They land under `--recipe-dir`
# rather than in configs/recipes/, so `recipes.roster()` never sees them and the
# site's recipe selector is untouched.
#
# WEEKS 5-16, NOT 1-16, and it is the same reason `recipe-fixtures` starts at 5.
# Weeks 1-4 are explicitly not the poll; asking whether a knob reorders a table
# that is not yet a ranking is asking about nothing.
VARIANT_SEASON ?= 2025
VARIANT_WEEKS  ?= 5 6 7 8 9 10 11 12 13 14 15 16
VARIANT_RUNS   ?= .cache/variants/runs
VARIANT_CONFIGS ?= .cache/variants/overlays
variants: .venv archive
	$(UV) run python -c "from pathlib import Path; from cfbpoll.publish import variants; \
	  print('overlays:', len(variants.write_overlays(Path('$(VARIANT_CONFIGS)'))))"
	@for v in $$($(UV) run python -c "from cfbpoll.publish import variants; \
	  print(' '.join(x.id for x in variants.VARIANTS))"); do \
	  for w in $(VARIANT_WEEKS); do \
	    printf 'rank %s %s week %s\n' "$$v" "$(VARIANT_SEASON)" "$$w"; \
	    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	      $(UV) run cfbpoll rank --config $(CONFIG) --recipe $$v \
	        --recipe-dir $(VARIANT_CONFIGS) \
	        --season $(VARIANT_SEASON) --through-week $$w --seed $(SEED) \
	        --draws $(DRAWS) --out $(VARIANT_RUNS)/$$v/w$$(printf '%02d' $$w) \
	        >/dev/null || exit 1; \
	  done; \
	  $(UV) run cfbpoll publish variants --from $(VARIANT_RUNS)/$$v --out $(FIXTURES) \
	    --variant $$v || exit 1; \
	done
	@echo
	@echo "The playground is $(FIXTURES)/$(VARIANT_SEASON)/variants/<id>/. The published"
	@echo "poll is untouched at $(FIXTURES)/$(VARIANT_SEASON)/week-NN.json, and so is"
	@echo "index.json: a variant is not a recipe and never enters the roster."

# Real, and it is the ONLY supported way to regenerate the LEVER GRID
# (src/cfbpoll/publish/lever_grid.py, docs/fixture-contract-levers.md).
#
# WHAT IT MAKES. Every combination of three published levers - `margin.c` at six
# detents, `margin.beta_w` at four, `[publication].headline_ordering` at all three
# of its legal values - ranked for every week in LEVER_WEEKS and published as a
# THIN ordering document at `<season>/lever-grid/<cell-id>/week-NN.json`, plus one
# `manifest.json` naming every cell, its detents, its file, and which cell is the
# published poll. Seventy-two boards, about 8 KB each.
#
# IT COSTS AN HOUR PER WEEK AND THAT IS THE NUMBER TO PLAN AROUND. One rank of
# 2025 through week 16 was timed at 50.7s wall on the author's machine, so 72
# cells is a little over an hour, serial. Background it. If it ever has to get
# cheaper, cut DETENTS and not levers: dropping margin.c to {1, 18, 32, uncapped}
# is 48 runs and still reproduces every shipped recipe and variant.
#
# IT DOES NOT REGENERATE THE PUBLISHED POLL AND IT DEPENDS ON IT, exactly as
# `variants` does. A cell's agreement block is defined against the house board, so
# `<season>/week-NN.json` must already be in FIXTURES or `publish lever-grid`
# refuses rather than inventing a baseline. Like `recipe-fixtures` and `variants`
# this writes only into its own subtree, so the four targets compose and none
# overwrites another's files. `index.json` is untouched: a grid cell is not a
# recipe and never enters the roster.
#
# THE MANIFEST IS WRITTEN ONCE, LAST. It is a statement about the whole grid, and
# a manifest written per cell would be seventy-two manifests, seventy-one of which
# described a grid that was not finished. It also refuses to name a week that not
# every cell carries, so an interrupted run leaves no manifest that 404s.
#
# THE 2026 HOOK IS THESE TWO VARIABLES AND NOTHING ELSE. A weekly regeneration is
# `make lever-grid LEVER_SEASON=2026 LEVER_WEEKS=8`; it writes a new week beside
# the existing ones and rewrites the manifest with `weeks` extended. Nothing here
# schedules it, on purpose.
LEVER_SEASON  ?= 2025
LEVER_WEEKS   ?= 16
LEVER_RUNS    ?= .cache/lever-grid/runs
LEVER_CONFIGS ?= .cache/lever-grid/overlays
lever-grid: .venv archive
	$(UV) run python -c "from pathlib import Path; from cfbpoll.publish import lever_grid; \
	  print('overlays:', len(lever_grid.write_overlays(Path('$(LEVER_CONFIGS)'))))"
	@for c in $$($(UV) run python -c "from cfbpoll.publish import lever_grid; \
	  print(' '.join(x.id for x in lever_grid.CELLS))"); do \
	  for w in $(LEVER_WEEKS); do \
	    printf 'rank %s %s week %s\n' "$$c" "$(LEVER_SEASON)" "$$w"; \
	    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	      $(UV) run cfbpoll rank --config $(CONFIG) --recipe $$c \
	        --recipe-dir $(LEVER_CONFIGS) \
	        --season $(LEVER_SEASON) --through-week $$w --seed $(SEED) \
	        --draws $(DRAWS) --out $(LEVER_RUNS)/$$c/w$$(printf '%02d' $$w) \
	        >/dev/null || exit 1; \
	  done; \
	  $(UV) run cfbpoll publish lever-grid --from $(LEVER_RUNS)/$$c --out $(FIXTURES) \
	    --cell $$c || exit 1; \
	done
	$(UV) run cfbpoll publish lever-grid --manifest --out $(FIXTURES) \
	  --season $(LEVER_SEASON)
	$(UV) run python scripts/check_lever_grid.py --data $(FIXTURES) --season $(LEVER_SEASON)
	@echo
	@echo "The grid is $(FIXTURES)/$(LEVER_SEASON)/lever-grid/, indexed by its own"
	@echo "manifest.json. The published poll is untouched at"
	@echo "$(FIXTURES)/$(LEVER_SEASON)/week-NN.json, and so is index.json."

# Real. The weekly share card. No headless browser: a Jinja-free SVG template
# rendered by resvg, which is what keeps the Sunday job cheap (report 05 §6.1).
#
# ONE NETWORK CALL, AND ONLY WHEN THE CACHE IS COLD. The cards carry the schools'
# real marks since the owner overturned report 06 §8.3, and `publish/logos.py`
# fetches each one once into a gitignored .cache/logos/, pins it in
# data/logo-cache-manifest.json and embeds it as a data: URI. A warm cache renders
# with no network at all; `--no-fetch-logos` forces that and falls back to the
# generated marks for anything missing.
PROJECTION_SOURCE ?= 2025
PROJECTION_TARGET ?= 2026
CARD_FROM ?= $(OUT)
cards: .venv
	$(UV) run cfbpoll publish cards --from $(CARD_FROM) --out $(OUT)/share

# Real. Regenerates the committed demo/ artifacts from the local archive.
demos: .venv
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run python scripts/make_demos.py

# Real. The PROJECTION - a labelled prediction, and never the poll (ADR 0010).
# Regenerates demo/2026-preseason-projection.md and friends from the archive.
projection: .venv
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run python scripts/make_projection.py

# THE ACCURACY SCOREBOARD, which replaced the gate (ADR 0014). Chains the seasons,
# scores every system's August call against what happened, and writes the lever
# registry beside it.
projection-chain: .venv
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run python scripts/make_chain.py

# The site's 2026 card. This had no target at all until 2026-08-17 and had to be
# remembered by hand, which is how a published board goes stale while the demo
# beside it is current.
#
# IT PINS BLAS BECAUSE IT FITS, and it did not until 2026-08-17. `projection
# fixture` runs the whole recipe: an OLS solve over the design transitions on top
# of the walk-forward L3 power the carried ratings come off. That is a fitting
# target under rule 3, and a multi-threaded reduction summing in a different order
# would move a PUBLISHED rating by a digit nobody could explain. The omission was
# silent, which is the only kind of determinism bug this project ever gets.
#
# It publishes the WHOLE BOARD, ~138 rows. The site renders 25; the rest exist so
# that a claim about a row below the fold is a claim a reader can go and check.
projection-fixture: .venv
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run cfbpoll projection fixture --to $(FIXTURES)

# And its share cards, which had the same problem.
projection-cards: .venv
	for v in projection_top5 projection_top10 projection_top25; do \
	  $(UV) run cfbpoll publish cards --variant $$v \
	    --projection $(FIXTURES)/$(PROJECTION_TARGET)/projection.json \
	    --out $(FIXTURES)/$(PROJECTION_TARGET)/share || exit 1; \
	done

# Everything the board touches, in the order the guards require: the demo build
# first (it is what `projection-fixture` reads), then the site card, then the 2025
# grading surface, then the cards, then the scoreboard.
projection-all: projection projection-fixture projection-2025 projection-cards projection-chain

levers: .venv
	$(UV) run cfbpoll levers

# The separation proof: both products, both deny-lists, one report. Exits
# non-zero if a projection input is anywhere near a poll layer.
projection-audit: .venv
	$(UV) run cfbpoll projection audit --season $(PROJECTION_SOURCE) --fail-on-banned

# Real. THE 2025 SEASON, which since ADR 0012 is the site's example season.
#
# THE SCORECARD IS NOT REGENERATED BY A MAKE TARGET, deliberately. 2025 was scored
# ONCE, by a human passing --unlock-holdout, and the run is recorded in
# .cache/holdout-2025.log with its command and its git sha. This target only
# re-renders the document from the metrics tree that run produced. A make target
# that could re-run the test is a make target somebody eventually runs in a loop.
holdout-scorecard: .venv
	$(UV) run python scripts/make_holdout_scorecard.py

# The retrospective Projection: the SHIPPED recipe, applied to 2024->2025, which
# it was never fitted on, plus the grading surfaces against R(N,live) and
# R(N,final). Refuses to write if its coefficients differ from the published 2026
# card's by more than 1e-9.
projection-2025: .venv
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run python scripts/make_projection_2025.py --to $(FIXTURES)

# The flagship revision figures, counted off the PUBLISHED fixture documents.
# Depends on nothing but the tree, because the site's copy quotes these numbers
# and a number in copy has to come off a published field.
revision-numbers: .venv
	$(UV) run python scripts/make_revision_numbers.py --data $(FIXTURES) --season 2025

replay: .venv
	@echo "[stub] uv run --frozen --offline cfbpoll rank --season 2023 --through-week 10 \\"
	@echo "         --config configs/frozen/2023.toml --seed 20231105 --out /tmp/replay"
	@echo "[stub] uv run cfbpoll canonicalize /tmp/replay --to /tmp/replay/canonical.csv"
	@echo "[stub] sha256sum -c data/manifests/golden/2023-w10.sha256"
	@echo "NOT IMPLEMENTED. Byte-match is asserted on the CI platform only;"
	@echo "on Apple Silicon expect ~1e-12 agreement, not bit-for-bit (report 03 §9.3)."

replay-tolerant: .venv
	@echo "[stub] the same replay with a ~1e-12 tolerance, for local Mac use."
	@echo "NOT IMPLEMENTED — report 03 §9.3 item 5."

# Real. The full retroactive triangle for one season: every evaluation week N
# against every data window K >= N, storing R(N,N), R(N,final) and the delta.
# Stays in parquet as a release asset; never loaded into Postgres (report 03 §5.4).
GRID_SEASON ?= 2023
grid: .venv
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run cfbpoll grid --config $(CONFIG) --season $(GRID_SEASON) --out $(OUT)
	@echo
	@echo "2021 and 2022 carry no postseason rows in the MIT parquet. With the"
	@echo "private CFBD backfill present they do, and \"final\" means final; without"
	@echo "it, \"final\" means through conference championships. The run record's"
	@echo "game_sources says which one you got."

# Real, and it is THE ANSWER TO "DID IT BEAT THE MODEL". Scores one community
# entry through the identical walk-forward harness against the identical
# baselines and writes a scorecard.
#
# IT EXISTS BECAUSE THE BARE CLI CALL IS A DETERMINISM TRAP. `challenge run`
# fits models, so it needs the single-threaded BLAS prefix for the same reason
# `rank` and `backtest` do - and it is the one command the whole contribution
# story points at, so it was the worst one to leave without a target. Without
# this, the documented path to a published finding ran multi-threaded reductions
# in a nondeterministic order.
#
# CHALLENGE_SEASONS MATCHES `cfbpoll challenge run`'s OWN DEFAULT. It is a
# variable because the archive can legitimately hold fewer seasons than that: a
# fork iterating under `make archive SEASONS=2023` must pass a matching
# `CHALLENGE_SEASONS=2023` or the run asks for seasons that are not on disk.
CHALLENGE_ENTRY   ?= configs/challengers/iterative_margin.py
CHALLENGE_SEASONS ?= 2021-2023
challenge: .venv archive
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run cfbpoll challenge run --entry $(CHALLENGE_ENTRY) \
	    --config $(CONFIG) --seasons $(CHALLENGE_SEASONS) --out $(OUT)/challenge
	@echo
	@echo "The scorecard is $(OUT)/challenge/. It is the same run_backtest, the same"
	@echo "frames and the same publication gate as demo/backtest-2021-2023.md."

site: .venv
	@echo "[stub] uv run cfbpoll site build --from $(OUT)/ --to site/_build"
	@echo "       Zero accounts: opens with python -m http.server -d site/_build"
	@echo "NOT IMPLEMENTED — report 03 §7.1."

# --------------------------------------------------------------------- ops
#
# The Sunday automation (ADR 0002). None of these fits a model, so none of them
# needs the single-threaded BLAS prefix.
#
# THEY ARE HERE BECAUSE THE ALTERNATIVE IS A TERMINAL HISTORY. The whole design
# rests on being able to answer "is the Sunday job armed, and would it run right
# now?" without reading three files, and a question that important should be one
# command.
TRIGGER ?= manual

# What the job would decide right now: armed or not, published or not, and why.
# Read-only. Costs at most one CFBD call, to resolve the live week.
guard: .venv
	$(UV) run cfbpoll guard --trigger $(TRIGGER) --fixtures $(FIXTURES)

# Which verbs the Sunday job calls are still stubs. Derived from the source, so
# it goes green on its own the day somebody implements one.
preflight: .venv
	$(UV) run cfbpoll preflight

# The whole Sunday job, printing every command and running none of them - except
# the guard, which is read-only and is the part you want a real answer from.
weekly-dry-run: .venv
	DRY_RUN=true SKIP_SYNC=true PUBLISH=false TRIGGER=$(TRIGGER) \
	  FIXTURES=$(FIXTURES) ops/bin/weekly.sh

test: .venv
	$(UV) run pytest

lint: .venv
	$(UV) run ruff check .

clean:
	rm -rf $(OUT) site/_build .pytest_cache .ruff_cache
