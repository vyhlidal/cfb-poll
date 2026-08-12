# tests/property/

Property-based tests — invariants that must hold for *any* valid input, not just
the cases someone thought to write down. **Empty — nothing to test yet.**

## The invariants the research already hands us

- **Colley conserves ratings exactly.** `Σ r_i / N = 1/2`, with no renormalisation,
  for any schedule (report 02 §2.1). This is a sharp, cheap correctness check on
  the baseline implementation and it is the reason `colley.py` is worth having
  beyond comparison.
- **Massey/SRS offense-defense consistency.** `r_i = o_i + d_i` exactly, by
  construction, when the 2n × 2n system collapses (report 02 §2.2).
- **Ridge is invertible on a disconnected schedule graph.** `L + λI` is positive
  definite for any `λ > 0`, so a fit on a deliberately disconnected fixture (the
  2020 conference-internal case, or any week-2 schedule) must succeed where plain
  least squares fails. This is the property that lets us keep constraint 2.
- **`E[W | q]` is strictly increasing and continuous in q** (report 02 §3.4), which
  is what guarantees the résumé root is unique.
- **Bootstrap determinism.** The same seed produces identical output regardless of
  `--jobs` (report 03 §9.3). Worth a property test rather than a single fixture,
  because the failure only shows up at certain worker counts.
- **Walk-forward never sees the future.** For any season and week N, the row set
  handed to a rater contains no game after week N−1. Generate schedules, assert it.
