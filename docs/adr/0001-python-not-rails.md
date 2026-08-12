# ADR 0001 — Python 3.12 managed by uv. Not Rails, not TypeScript, not Julia.

- **Status:** Accepted
- **Date:** 2026-08-12
- **Full reasoning:** research report 03 §3 (the stack) and §8 (Rails, honestly)

## Decision

The model is **Python 3.12**, pinned by `.python-version`, with dependencies
resolved and locked by **uv** (`uv.lock`, committed). The dependency set is fixed:
numpy, scipy, scikit-learn, polars, pyarrow, duckdb, httpx, typer, psycopg, boto3.

TypeScript stays where it is already right — the web surface. Ruby/Rails is
rejected.

## Why

**Every piece of the required math is one import.** Sparse CSR design matrices,
ridge with a custom penalty matrix and unpenalized intercept, `GroupKFold` grouped
on `game_id`, `brentq`, the normal CDF, 20-node Gauss-Hermite quadrature, a seeded
parallel bootstrap, and a MILP solver for the MinV bound — all of them exist,
maintained, in this stack.

That is the whole argument, and it is a credibility argument rather than a
convenience one: in a project whose credibility rests entirely on its math being
auditable and correct, every hand-rolled Cholesky, normal CDF and quadrature rule
is a place a silent numerical bug can live, and a place a reviewer has to check.
**Reviewers can audit `scipy.optimize.brentq`; they cannot audit your bisection.**

**uv is why this is Python now rather than three years ago.** `uv.lock` is a
universal, cross-platform lockfile that resolves identically on Apple Silicon, the
x86_64 CI runner and a contributor's Windows box; `uv sync --locked` hard-fails on
drift rather than silently updating. For a weekly CI job and for a stranger
running one command, that difference is the entire onboarding experience.

## The alternatives, honestly

**R — the strongest runner-up, and it deserves better than a dismissal.** This
project's data lineage *is* R: `cfbfastR` produces the archive we consume, and the
sports-analytics public skews R. `glmnet` does sparse ridge properly, `arrow` reads
parquet, `renv` is a real lockfile tool. It loses on three counts: the pipeline is
only ~30% statistics (the rest is HTTP ingest with quota guards, content-addressed
archive management, checksum manifests, CLI ergonomics, Postgres loading, static
site generation and CI plumbing, where Python is materially stronger); `renv`
restores from CRAN and compiles from source on Linux where `uv sync --locked`
restores pinned wheels in seconds; and the contributor pool for "fork this and beat
my model" is wider in Python.

**The mitigation is real and we commit to it:** publish every output as **parquet
and CSV**. An R contributor can then do their entire analysis in R against our
artifacts without touching our pipeline. Reproducibility does not require language
monoculture — it requires open, plain-format data, and that costs nothing.

**TypeScript** is appealing for one reason (one language across model, site and
the sandbox repo) and it is not enough. There is no maintained sparse ridge, no
`brentq`, no Gauss-Hermite rule, no `GroupKFold`, no MILP solver, no `norm.cdf`.
Each becomes hand-written numerical code — a multi-week detour producing a *less*
trustworthy artifact than 40 lines of scipy.

**Julia** is the right answer to a question we do not have. The workload is already
sub-second, so its speed advantage buys nothing, and its ecosystem is an order of
magnitude smaller by every measure checked. For a project whose product feature is
strangers forking it, ecosystem size is first-order.

**Rails — and the reason is not that Rails is bad.** Rails is the best tool
available for a database-backed application with users, forms, sessions and CRUD.
This project is a batch numerical pipeline plus a near-read-only publication
surface: no users to authenticate, no forms, no records to create. The checkable
problems: Ruby's numerics are thin and partly stale (`daru`, the closest thing to
pandas, last pushed 2023); parquet runs through Arrow GLib system libraries;
sports analytics is an R and Python community, so a Rails choice would draw
challengers from a population that mostly does not exist; and it would be a third
stack duplicating what Next.js already does.

If the underlying pull is "I want a server-rendered thing I control rather than a
serverless platform," the honest answer is not Rails — it is the static site
(ADR 0004 and report 03 §7.1), served from anywhere, with no framework at all.

## Consequences

- One new toolchain, and only one. Contributors need `uv` and nothing else.
- Golden fixtures must be generated on the CI platform, never on the Mac: arm64
  and x86_64 may differ in the last bits because BLAS kernels reduce in different
  orders (report 03 §4.5, §9.3).
- Thread counts are pinned to 1 in CI for deterministic summation order. The fits
  are sub-second; the threads buy nothing and determinism is worth more.
- Every published artifact ships as parquet **and** CSV. This is a commitment, not
  a nice-to-have — it is what keeps the R half of the field in the conversation.
