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

.PHONY: help rankings archive archive-lock backtest cards demos fixtures replay replay-tolerant grid site test lint clean

help:
	@echo "cfb-poll — PARTIAL BUILD. 'rankings', 'archive', 'backtest', 'grid', 'demos' work."
	@echo
	@echo "  make .venv            uv sync --locked  (installs Python 3.12 + pinned wheels)"
	@echo "  make rankings         archive sync -> rank -> the poll in out/"
	@echo "  make archive          fetch + sha256-verify the MIT archive (~0.55 GB)"
	@echo "  make archive-lock     regenerate the committed lockfile from a backfill"
	@echo "  make backtest         walk-forward 2021-2023 vs every baseline"
	@echo "  make grid             the R(N,K) retroactive triangle for one season"
	@echo "  make cards            render the weekly share card (SVG + PNG)"
	@echo "  make fixtures         rank every week of a season -> publish the JSON tree"
	@echo "  make demos            regenerate demo/ from the local archive"
	@echo "  make replay           offline byte-match replay of a known week   [stub]"
	@echo "  make replay-tolerant  same replay, ~1e-12 tolerance (for a Mac)   [stub]"
	@echo "  make site             build the static site into site/_build      [stub]"
	@echo "  make test / make lint pytest / ruff"

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
RANK_SEASON ?= 2023
RANK_WEEK   ?= 15
rankings: .venv archive
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run cfbpoll rank --config $(CONFIG) --season $(RANK_SEASON) \
	    --through-week $(RANK_WEEK) --seed $(SEED) --draws $(DRAWS) --out $(OUT)
	@echo
	@echo "The poll is $(OUT)/poll.csv and $(OUT)/poll.json; the run record, with"
	@echo "which archives it read and every constant it used, is $(OUT)/_run.json."
	@echo "`cfbpoll rank` ran the leakage audit BEFORE it fit anything."
	@echo
	@echo "STILL A STUB: `cfbpoll site build`. There is no static site yet, so the"
	@echo "poll is files rather than a page (report 03 §7.1)."

# Real. ~0.55 GB from OUR release assets, every file sha256-checked against the
# committed lockfile before any consumer reads it. Add SEASONS=2023 to pull one
# season, or ONLY=schedules,crosswalk for a scores-only run that skips the 0.52 GB
# of play-by-play.
ARCHIVE_ARGS ?=
archive: .venv
	$(UV) run cfbpoll archive sync --source sportsdataverse --verify $(ARCHIVE_ARGS)

# Regenerate data/manifests/sportsdataverse.lock.json from a completed backfill.
# Only needed after a backfill or a new release tag; the lockfile is committed.
archive-lock: .venv
	$(UV) run cfbpoll archive lock

# Real. Single-threaded BLAS is not optional: multi-threaded reductions sum in a
# nondeterministic order and the replay job asserts byte-equality (report 03 §9.3).
# With L1 and L3 in the systems list this reads the play archive (~0.3 GB for the
# tune seasons) and takes about a minute; scores-only runs never touch it.
backtest: .venv
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run cfbpoll backtest --config $(CONFIG) \
	    --systems schedule_odds,resume,l3,l2,l1,colley,srs,elo,walker,winpct \
	    --seasons 2021-2023 --out $(OUT)
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

# Real. The weekly share card. No logos, no network, no headless browser: a
# Jinja-free SVG template rendered by resvg, which is what keeps the Sunday job
# hermetic (report 05 §6.1, report 06 §8.3).
CARD_FROM ?= $(OUT)
cards: .venv
	$(UV) run cfbpoll publish cards --from $(CARD_FROM) --out $(OUT)/share

# Real. Regenerates the committed demo/ artifacts from the local archive.
demos: .venv
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
	  $(UV) run python scripts/make_demos.py

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

site: .venv
	@echo "[stub] uv run cfbpoll site build --from $(OUT)/ --to site/_build"
	@echo "       Zero accounts: opens with python -m http.server -d site/_build"
	@echo "NOT IMPLEMENTED — report 03 §7.1."

test: .venv
	$(UV) run pytest

lint: .venv
	$(UV) run ruff check .

clean:
	rm -rf $(OUT) site/_build .pytest_cache .ruff_cache
