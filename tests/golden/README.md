# tests/golden/

Byte-match fixtures for the reproducibility job. **Empty — no fixture exists yet.**

`.github/workflows/reproducibility.yml` recomputes a known historical week with the
network disabled and asserts a sha256 match against a checksum committed in
`data/manifests/golden/`. This directory holds the fixture inputs and the test that
drives them once the model exists.

## Two rules, both from report 03 §4.5 and §9.3

1. **Generate fixtures on the CI platform, never on the Mac.** Apple Silicon arm64
   and the x86_64 runner do not necessarily produce bit-identical floating-point
   results, because different BLAS kernels reduce in different orders. A local
   replay is expected to agree to ~1e-12, not bit-for-bit — that is what
   `make replay-tolerant` is for.
2. **Hash the canonicalized CSV, not the parquet.** Parquet embeds a `created_by`
   writer-version string, so two byte-identical datasets can produce different file
   bytes. `cfbpoll canonicalize` emits a sorted CSV with fixed `%.10g` float
   formatting, and that is what the checksum covers.

## When a fixture changes

If a dependency bump or a deliberate model change alters the numbers, **regenerate
the fixture in the same PR**. The whole value of this job is that a red build on an
unrelated PR means someone changed the numbers. Absorbing that quietly destroys the
signal.
