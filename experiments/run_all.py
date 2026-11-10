"""Reproduce every result, table and figure.

Usage:
    python experiments/run_all.py            # full study (about 10 minutes on a laptop CPU)
    python experiments/run_all.py --quick    # smoke run (< 1 minute), writes to results/quick
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402

from fluxtwin import plotting  # noqa: E402
from fluxtwin.experiments import (  # noqa: E402
    budget_to_target,
    device_stats,
    robustness,
    summarise,
    sweep_grid,
)

TARGETS_KHZ = [100.0, 300.0]


def statevector_check() -> dict:
    """Verify the closed-form register fidelity against a Qiskit statevector."""
    from qiskit.circuit import QuantumCircuit
    from qiskit.quantum_info import Statevector

    from fluxtwin.control import register_fidelity

    rng = np.random.default_rng(0)
    phases = 2 * np.pi * rng.normal(0, 1e5, 4) * 50e-9  # 100 kHz rms over 50 ns
    qc = QuantumCircuit(4)
    qc.h(range(4))
    ideal = Statevector(qc)
    for q, ph in enumerate(phases):
        qc.rz(float(ph), q)
    sv_fid = float(abs(ideal.inner(Statevector(qc))) ** 2)
    return {"closed_form": register_fidelity(phases), "statevector": sv_fid}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    torch.set_num_threads(6)
    t0 = time.time()

    out = ROOT / "results" / ("quick" if args.quick else "")
    figs = ROOT / "figures" / ("quick" if args.quick else "")
    out.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)

    if args.quick:
        seeds, sides, Ms = [0, 1], [3, 5], [16, 64]
        mlp_epochs, mlp_Ms = 100, [64]
        abl_sides, abl_Ms = [5], [32, 64]
        rob_side, rob_Ms, sig, par = 5, [32], [25.0, 100.0], [0.0, 0.1]
    else:
        seeds, sides, Ms = [0, 1, 2, 3, 4], [2, 3, 4, 5, 6, 8, 10], [8, 16, 32, 64, 128, 256, 512, 1024]
        mlp_epochs, mlp_Ms = 600, [128, 512]
        abl_sides, abl_Ms = [8], [32, 64, 128, 256]
        rob_side, rob_Ms = 8, [64, 256]
        sig, par = [10.0, 25.0, 50.0, 100.0, 200.0, 400.0], [0.0, 0.01, 0.02, 0.05, 0.1, 0.2]

    main_methods = ["none", "sweep", "dense", "prior", "ridge_flat", "banded_val", "mlp", "mlp_skip"]
    print("[1/4] scaling study", flush=True)
    raw = sweep_grid(sides, Ms, seeds, main_methods, mlp_epochs=mlp_epochs, mlp_Ms=mlp_Ms)
    raw.to_csv(out / "scaling_runs.csv", index=False)
    summ = summarise(raw, ["method", "N", "M"])
    summ.to_csv(out / "scaling_summary.csv", index=False)
    infid = summarise(raw, ["method", "N", "M"], "qubit_infid")
    infid.to_csv(out / "idle_infidelity_summary.csv", index=False)
    star = budget_to_target(summ[summ.method.isin(["sweep", "dense", "prior"])], TARGETS_KHZ)
    star.to_csv(out / "budget_to_target.csv", index=False)
    device_stats(sides, seeds, 0.02).to_csv(out / "device_stats.csv", index=False)

    print("[2/4] ablation of the structural prior", flush=True)
    abl_methods = ["dense", "ridge_flat", "banded_R1.0", "banded_R2.0", "banded_R4.0", "banded_val", "prior"]
    abl = sweep_grid(abl_sides, abl_Ms, seeds, abl_methods)
    abl.to_csv(out / "ablation_runs.csv", index=False)
    abl_s = summarise(abl, ["method", "N", "M"])
    abl_s.to_csv(out / "ablation_summary.csv", index=False)

    print("[3/4] robustness sweeps", flush=True)
    rob_list = [
        robustness(rob_side, M, seeds, sig, par, ["none", "dense", "prior"]) for M in rob_Ms
    ]
    rob = pd.concat(rob_list, ignore_index=True)
    rob.to_csv(out / "robustness_runs.csv", index=False)
    rob_s = summarise(rob, ["sweep", "method", "N", "M", "sigma_f_khz", "p_par"])
    rob_s.to_csv(out / "robustness_summary.csv", index=False)

    print("[4/4] figures and checks", flush=True)
    plotting.fig_scaling(summ, sides if len(sides) <= 6 else sides[1:], figs / "fig1_scaling_small_multiples.png")
    plotting.fig_heatmaps(summ, figs / "fig2_dense_vs_prior_heatmap.png")
    abl_n = abl_sides[0] ** 2
    plotting.fig_ablation(
        abl_s, abl_n, abl_Ms,
        [("dense", "dense LS"), ("ridge_flat", "flat ridge"), ("banded_R1.0", "cutoff R=1"),
         ("banded_R2.0", "cutoff R=2"), ("banded_R4.0", "cutoff R=4"), ("banded_val", "cutoff, validated R"),
         ("prior", "distance prior (proposed)")],
        figs / "fig3_ablation_grouped_bars.png",
    )
    plotting.fig_robustness(rob_s, rob_side * rob_side, rob_Ms, figs / "fig4_robustness_small_multiples.png")
    plotting.fig_budget(star, TARGETS_KHZ, figs / "fig5_budget_to_target.png")

    check = statevector_check()
    (out / "statevector_check.json").write_text(json.dumps(check, indent=2))
    runtime = time.time() - t0
    (out / "runtime.json").write_text(json.dumps({"seconds": round(runtime, 1), "quick": args.quick}, indent=2))
    print(f"done in {runtime:.0f} s; results in {out}", flush=True)


if __name__ == "__main__":
    main()
