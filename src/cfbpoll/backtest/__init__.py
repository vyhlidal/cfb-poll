"""Walk-forward backtest harness, metrics, baselines, and the MinV bound.

Specified by report 02 §5. BUILD THIS SECOND, NOT LAST (report 02 Appendix B
step 2): "Every subsequent decision depends on it."

Data split, chosen before looking at any result (report 02 §5.1):
    tune     2021-2023   hyperparameters: C, beta_w, lambda grids, w1/w2,
                         garbage-time thresholds, bowl weights
    validate 2024
    holdout  2025        SINGLE SHOT. Touch it once. If hyperparameters are
                         re-tuned after seeing 2025, say so publicly and
                         re-designate.

The harness must also refuse to score community challengers on 2025 by default,
and say why (report 03 §7.3).

STATUS: SCAFFOLD.
"""
