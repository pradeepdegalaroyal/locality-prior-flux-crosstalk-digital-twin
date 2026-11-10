"""Experiment drivers: one trial = one random device, one calibration, one control test."""

from __future__ import annotations

import time
from typing import Iterable

import numpy as np
import pandas as pd

from .control import (
    SIGMA_V,
    compensate,
    draw_targets,
    qubit_infidelity,
    realised_frequency_error_khz,
    rms_khz,
)
from .device import condition_stats, make_device, run_calibration_experiments
from .estimators import (
    RADII,
    fit_banded,
    fit_banded_validated,
    fit_dense,
    fit_line_sweep,
    fit_mlp_twin,
    fit_prior_ridge_validated,
    mlp_control,
)

FIXED_RADII = RADII


def run_trial(
    side: int,
    M: int,
    sigma_f_khz: float,
    p_par: float,
    seed: int,
    methods: Iterable[str],
    mlp_epochs: int = 600,
    n_targets: int = 64,
) -> list[dict]:
    """Run all ``methods`` on one random device with a shared experiment set.

    Method names: ``none`` (no compensation), ``diag`` (gain only),
    ``sweep`` (one-line-at-a-time), ``dense`` (unstructured least squares),
    ``prior`` (locality-prior twin: distance-weighted ridge, validated),
    ``ridge_flat`` (distance-blind ridge), ``banded_val`` (hard cutoff, validated radius), ``banded_R<r>``
    (fixed radius), ``mlp`` / ``mlp_skip`` (unstructured neural twins).
    """
    rng = np.random.default_rng(seed)
    dev = make_device(side, p_par, rng)
    n = dev.n
    cal_rng = np.random.default_rng(seed + 10_000)
    V = SIGMA_V * cal_rng.standard_normal((M, n))
    Y = run_calibration_experiments(dev, V, sigma_f_khz, cal_rng)
    dphi, f_target = draw_targets(dev, n_targets, np.random.default_rng(seed + 20_000))
    rows: list[dict] = []

    def record(method: str, v: np.ndarray | None, extra: dict | None = None) -> None:
        if v is None:
            return
        err = realised_frequency_error_khz(dev, v, f_target)
        rows.append(
            {
                "N": n, "M": M, "sigma_f_khz": sigma_f_khz, "p_par": p_par, "seed": seed,
                "method": method, "rms_khz": rms_khz(err), "qubit_infid": qubit_infidelity(err),
                **(extra or {}),
            }
        )

    for m in methods:
        if m == "none":
            record(m, dphi)
        elif m == "diag":
            record(m, dphi / np.diag(fit_banded(V, Y, dev.dist, 0.0))[None, :])
        elif m == "sweep":
            res = fit_line_sweep(n, lambda Vs: run_calibration_experiments(dev, Vs, sigma_f_khz, cal_rng), M, 1.5 * SIGMA_V)
            if res is not None:
                record(m, compensate(res[0], dphi), {"M_used": res[1]})
        elif m == "dense":
            record(m, compensate(fit_dense(V, Y), dphi))
        elif m in ("prior", "ridge_flat"):
            C_hat, kap, lam = fit_prior_ridge_validated(
                V, Y, dev.dist, SIGMA_V, np.random.default_rng(seed + 30_000), flat=(m == "ridge_flat")
            )
            record(m, compensate(C_hat, dphi), {"kappa": kap, "lam_hat": -1.0 if lam is None else lam})
        elif m == "banded_val":
            C_hat, r = fit_banded_validated(V, Y, dev.dist, np.random.default_rng(seed + 30_000))
            record(m, compensate(C_hat, dphi), {"radius": r})
        elif m.startswith("banded_R"):
            r = float(m[len("banded_R"):])
            record(m, compensate(fit_banded(V, Y, dev.dist, r), dphi), {"radius": r})
        elif m in ("mlp", "mlp_skip"):
            model = fit_mlp_twin(V, Y, SIGMA_V, mlp_epochs, seed, skip=(m == "mlp_skip"))
            record(m, mlp_control(model, dphi, SIGMA_V))
        else:
            raise ValueError(f"unknown method {m}")
    return rows


def sweep_grid(
    sides: Iterable[int],
    Ms: Iterable[int],
    seeds: Iterable[int],
    methods: Iterable[str],
    sigma_f_khz: float = 50.0,
    p_par: float = 0.02,
    mlp_epochs: int = 600,
    mlp_max_n: int = 25,
    mlp_Ms: Iterable[int] | None = None,
) -> pd.DataFrame:
    """Scaling study over lattice side, experiment budget and seeds."""
    rows: list[dict] = []
    methods = list(methods)
    mlp_Ms = set(mlp_Ms) if mlp_Ms is not None else None
    for side in sides:
        for M in Ms:
            ms = [
                m for m in methods
                if not m.startswith("mlp") or (side * side <= mlp_max_n and (mlp_Ms is None or M in mlp_Ms))
            ]
            for s in seeds:
                rows += run_trial(side, M, sigma_f_khz, p_par, s, ms, mlp_epochs)
    return pd.DataFrame(rows)


def robustness(
    side: int,
    M: int,
    seeds: Iterable[int],
    sigmas: Iterable[float],
    p_pars: Iterable[float],
    methods: Iterable[str],
    base_sigma: float = 50.0,
    base_p: float = 0.02,
) -> pd.DataFrame:
    """Noise (``sigma_f``) and parasitic-density (``p_par``) sweeps at fixed size and budget."""
    rows: list[dict] = []
    methods = list(methods)
    for sg in sigmas:
        for s in seeds:
            for r in run_trial(side, M, sg, base_p, s, methods):
                rows.append({**r, "sweep": "noise"})
    for pp in p_pars:
        for s in seeds:
            for r in run_trial(side, M, base_sigma, pp, s, methods):
                rows.append({**r, "sweep": "parasitic"})
    return pd.DataFrame(rows)


def device_stats(sides: Iterable[int], seeds: Iterable[int], p_par: float, radius: float = 2.0) -> pd.DataFrame:
    """Condition number of ``C`` and fraction of it lying outside a locality radius."""
    rows = []
    for side in sides:
        for s in seeds:
            dev = make_device(side, p_par, np.random.default_rng(s))
            rows.append({"N": dev.n, "seed": s, **condition_stats(dev, radius)})
    return pd.DataFrame(rows)


def summarise(df: pd.DataFrame, keys: list[str], value: str = "rms_khz") -> pd.DataFrame:
    """Mean and standard deviation of ``value`` over seeds, grouped by ``keys``."""
    g = df.groupby(keys)[value]
    out = g.agg(["mean", "std", "count"]).reset_index()
    return out.rename(columns={"mean": f"{value}_mean", "std": f"{value}_std", "count": "n_seeds"})


def budget_to_target(summary: pd.DataFrame, targets: Iterable[float]) -> pd.DataFrame:
    """Smallest tested budget ``M`` whose seed-mean error is below each target (NaN if none)."""
    rows = []
    for t in targets:
        for (method, n), g in summary.groupby(["method", "N"]):
            ok = g[g["rms_khz_mean"] <= t].sort_values("M")
            rows.append({"method": method, "N": n, "target_khz": t,
                         "M_star": float(ok["M"].iloc[0]) if len(ok) else np.nan})
    return pd.DataFrame(rows)


class Timer:
    """Tiny wall-clock helper."""

    def __enter__(self) -> "Timer":
        self.t0 = time.time()
        return self

    def __exit__(self, *a: object) -> None:
        self.dt = time.time() - self.t0
