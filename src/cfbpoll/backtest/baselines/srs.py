"""Baseline: SRS with the Sports-Reference college football convention.

Specified by report 02 §2.2 and §5.3.

    R_i = MOV_i + (1/n_i) * sum_j R_j        average team = 0

Sports-Reference's CFB handling exactly: margin CAPPED at 24 and FLOORED at +/-7,
so a 1-point win is treated the same as a 7-point win. That floor is the direct
precedent for our win premium beta_w ~ 3.0 (report 02 §3.2).

Uncapped SRS IS the Massey least-squares rating - multiply by n_i and it is
row-for-row Massey's normal equations, with the zero-mean convention playing the
role of Massey's replaced all-ones row. Capped/floored CFB SRS is not plain least
squares.

This baseline keeps the failure mode we designed around: with a disconnected
schedule graph the matrix is singular and the solve simply fails (2020), and it
is near-singular in weeks 1-3. Our ridge term is exactly what removes that,
without importing reputation. Expect this baseline to fail early-season fits;
that is informative, and the harness should record it rather than paper over it.

Note this baseline also LUMPS non-major opponents into one team, per
Sports-Reference. We reject that convention for our own model (report 02 §3.7)
but keep it here so the baseline is the real thing.

The cap, the floor and the lumping rule live in configs/default.toml
under [baselines.srs].
"""

from __future__ import annotations

import numpy as np
import polars as pl

from cfbpoll.config import load_config

__all__ = ["NON_MAJOR", "rate"]

NON_MAJOR = "NON-MAJOR"


def rate(
    games: pl.DataFrame,
    plays: pl.DataFrame | None = None,
    through_week: int | None = None,
    config: dict | None = None,
    state: object = None,
) -> dict[str, float]:
    """SRS ratings (challenger protocol, report 03 §7.3). `plays` unused.

    Solves n_i*R_i - sum_j g_ij*R_j = pd_i, which is Massey's normal equations
    row-for-row with Sports-Reference's zero-mean convention playing the role of
    Massey's replaced all-ones row (report 02 §2.2).

    The system is a graph Laplacian and therefore singular by construction, so it
    is solved in the minimum-norm least-squares sense. On a CONNECTED schedule
    that is exactly the sum-to-zero solution Massey prescribes. On a DISCONNECTED
    one - weeks 1-3 of any season, or 2020 - plain SRS is undefined and this is
    the most charitable available reading of it; the published workaround
    (conference-level offsets) is a reputation prior and is not used here. Our
    own model needs no such rescue: L + lambda*I is positive definite for any
    lambda > 0 (report 02 §3.2). That contrast is the point of running this
    baseline at all, so it is stated rather than hidden.
    """
    del plays, through_week, state
    cfg = config if config is not None else load_config()
    srs = cfg["baselines"]["srs"]
    cap = float(srs["mov_cap"])
    floor = float(srs["mov_floor"])
    lump = bool(srs["lump_non_fbs"])

    def label(team: str, klass: str) -> str:
        return NON_MAJOR if (lump and klass != "fbs") else team

    home = [
        label(t, k)
        for t, k in zip(games["home_team"].to_list(), games["home_class"].to_list(), strict=True)
    ]
    away = [
        label(t, k)
        for t, k in zip(games["away_team"].to_list(), games["away_class"].to_list(), strict=True)
    ]
    margin = (games["home_points"] - games["away_points"]).to_numpy().astype(np.float64)

    # Cap at +/-24 and floor at +/-7: a 1-point win counts as a 7-point win.
    mov = np.sign(margin) * np.clip(np.abs(margin), floor, cap)

    keep = [i for i, (h, a) in enumerate(zip(home, away, strict=True)) if h != a]
    if not keep:
        return {}
    home = [home[i] for i in keep]
    away = [away[i] for i in keep]
    mov = mov[keep]

    teams = tuple(sorted(set(home) | set(away)))
    index = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    m = np.zeros((n, n), dtype=np.float64)
    pd_ = np.zeros(n, dtype=np.float64)
    for h, a, d in zip(home, away, mov, strict=True):
        i, j = index[h], index[a]
        m[i, i] += 1.0
        m[j, j] += 1.0
        m[i, j] -= 1.0
        m[j, i] -= 1.0
        pd_[i] += d
        pd_[j] -= d

    r, *_ = np.linalg.lstsq(m, pd_, rcond=None)
    r = r - r.mean()  # average team = 0, per Sports-Reference
    return {team: float(r[i]) for i, team in enumerate(teams)}
