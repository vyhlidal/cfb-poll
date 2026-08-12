# The optional exact-environment path (research report 03 §9.4).
#
# `make rankings` on a bare machine with uv is the HEADLINE path and always will
# be: requiring Docker to get a ranking on screen adds a multi-GB dependency and
# an install step that would lose more contributors than reproducibility gains.
# This file is here for the case where you want byte-level environment control.
#
# NOT EXERCISED IN CI, and not exercised at all yet - the pipeline it would run
# does not exist. Treat it as a starting point, not a tested artifact.
#
# Deliberately does NOT vendor the 0.55 GB archive into a layer. The manifest plus
# checksums is the reproducible reference; the release asset is the transport.

FROM python:3.12-slim-bookworm

# uv, pinned by digest-free tag on purpose: bump it deliberately, in a PR.
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/

WORKDIR /app

# Determinism knobs, same as the CI workflows (report 03 §9.3).
ENV OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    PYTHONHASHSEED=0 \
    TZ=UTC \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project

COPY . .
RUN uv sync --locked

ENTRYPOINT ["uv", "run", "cfbpoll"]
CMD ["--help"]
