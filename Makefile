# cfb-poll — the one-command fork story (research report 03 §9.1).
#
# SCAFFOLD: only the `.venv` target does real work today. Every other target
# prints exactly what it will do and exits 0, so the contract is readable before
# the pipeline exists. Each stub maps 1:1 to a `cfbpoll` CLI verb.

UV ?= uv
CONFIG ?= configs/default.toml
OUT ?= out
SEED ?= 20260812
DRAWS ?= 1000
JOBS ?= 4

.PHONY: help rankings archive backtest replay replay-tolerant grid site test lint clean

help:
	@echo "cfb-poll — SCAFFOLD BUILD. Only '.venv' currently does real work."
	@echo
	@echo "  make .venv            uv sync --locked  (installs Python 3.12 + pinned wheels)"
	@echo "  make rankings         archive sync -> rank -> bootstrap -> site  [stub]"
	@echo "  make archive          fetch + sha256-verify the MIT archive       [stub]"
	@echo "  make backtest         walk-forward vs all eight baselines         [stub]"
	@echo "  make replay           offline byte-match replay of a known week   [stub]"
	@echo "  make replay-tolerant  same replay, ~1e-12 tolerance (for a Mac)   [stub]"
	@echo "  make grid             the 5 x 15 x 15 retroactive grid            [stub]"
	@echo "  make site             build the static site into site/_build      [stub]"
	@echo "  make test / make lint pytest / ruff"

# The only target that works today. `uv sync --locked` errors instead of
# updating if uv.lock is stale, which is exactly what CI and a stranger both want.
.venv:
	$(UV) sync --locked

rankings: .venv archive
	@echo "[stub] uv run cfbpoll rank      --config $(CONFIG) --out $(OUT)/"
	@echo "[stub] uv run cfbpoll bootstrap --draws $(DRAWS) --seed $(SEED) --out $(OUT)/"
	@echo "[stub] uv run cfbpoll site build --from $(OUT)/ --to site/_build"
	@echo "[stub] then: python -m http.server -d site/_build"
	@echo
	@echo "NOT IMPLEMENTED. This is the fork promise from report 03 §9.1 and it is"
	@echo "the target the whole project is being built to satisfy. Expected once it"
	@echo "is real: a minute or two of download, then under a minute of compute."

archive: .venv
	@echo "[stub] uv run cfbpoll archive sync --source sportsdataverse --verify"
	@echo "       ~0.55 GB from our release assets; every file sha256-checked"
	@echo "       against data/manifests/sportsdataverse.lock.json before use."
	@echo "NOT IMPLEMENTED — and the manifest does not exist yet either."

backtest: .venv
	@echo "[stub] walk-forward 2021-2023 (tune) and 2024 (validate), FBS-vs-FBS,"
	@echo "       against all eight baselines: home-team, win%, Colley, SRS,"
	@echo "       random-walker, Elo, closing line, CFP committee."
	@echo "       2025 is HELD OUT. Single shot. Do not touch it here."
	@echo "NOT IMPLEMENTED — report 02 §5, Appendix B step 2 (build this second)."

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

grid: .venv
	@echo "[stub] the full retroactive grid: 5 seasons x 15 evaluation weeks x 15"
	@echo "       data windows, storing R(N,N), R(N,final) and the delta."
	@echo "       Stays in parquet as a release asset; never loaded into Postgres."
	@echo "NOT IMPLEMENTED — report 02 §3.6, report 03 §5.4."

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
