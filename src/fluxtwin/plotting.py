"""Black-and-grey figures: small multiples, annotated heatmaps and hatched grouped bars."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DPI = 200
STYLE = {
    "none": dict(color="0.65", ls=":", marker="x", label="no compensation"),
    "sweep": dict(color="0.45", ls="-.", marker="s", label="line-by-line sweep"),
    "dense": dict(color="0.0", ls="-", marker="o", label="dense least squares"),
    "prior": dict(color="0.0", ls="--", marker="^", label="distance-prior twin", mfc="white"),
    "mlp": dict(color="0.3", ls=(0, (1, 1)), marker="D", label="MLP twin", mfc="0.7"),
    "mlp_skip": dict(color="0.5", ls=(0, (3, 1, 1, 1)), marker="v", label="MLP twin + linear skip", mfc="0.9"),
}
KHZ = "root-mean-square frequency error (kHz)"


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def fig_scaling(summary: pd.DataFrame, sides: list[int], path: Path) -> None:
    """Small multiples: control error vs experiment budget, one panel per array size."""
    ns = [s * s for s in sides]
    cols = 3
    rows = int(np.ceil(len(ns) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 3.4 * rows), sharey=True, squeeze=False)
    for ax, n in zip(axes.ravel(), ns):
        for m, st in STYLE.items():
            g = summary[(summary.N == n) & (summary.method == m)].sort_values("M")
            if g.empty:
                continue
            ax.errorbar(g.M, g.rms_khz_mean, yerr=g.rms_khz_std.fillna(0), capsize=2, lw=1.2, ms=5, **st)
        ax.axvline(n, color="0.8", lw=1)
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_title(f"{n} qubits (grey line: M = N)", fontsize=10)
        ax.set_xlabel("calibration experiments M")
        ax.grid(alpha=0.25)
    for ax in axes[:, 0]:
        ax.set_ylabel(KHZ)
    for ax in axes.ravel()[len(ns):]:
        ax.axis("off")
    axes[-1, -1].legend(fontsize=7, loc="lower left")
    fig.suptitle("Control error versus calibration budget (mean ± std over seeds)", y=1.0)
    _save(fig, path)


def fig_heatmaps(summary: pd.DataFrame, path: Path) -> None:
    """Annotated heatmaps over (array size, budget): dense, prior and their ratio."""
    def grid(method: str) -> pd.DataFrame:
        g = summary[summary.method == method]
        return g.pivot(index="N", columns="M", values="rms_khz_mean").sort_index()

    d, p = grid("dense"), grid("prior")
    ratio = d / p
    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8))
    panels = [
        (d, "dense least squares: error (kHz)", np.log10(d.clip(lower=1)), "Greys", "{:.0f}"),
        (p, "distance-prior twin: error (kHz)", np.log10(p.clip(lower=1)), "Greys", "{:.0f}"),
        (ratio, "error ratio dense / prior", np.log10(ratio.clip(lower=0.1)), "Greys", "{:.1f}"),
    ]
    for ax, (tab, title, vals, cmap, fmt) in zip(axes, panels):
        im = ax.imshow(vals.values, cmap=cmap, aspect="auto", origin="lower")
        ax.set_xticks(range(tab.shape[1]), [str(c) for c in tab.columns])
        ax.set_yticks(range(tab.shape[0]), [str(i) for i in tab.index])
        lo, hi = np.nanmin(vals.values), np.nanmax(vals.values)
        for i in range(tab.shape[0]):
            for j in range(tab.shape[1]):
                v = tab.values[i, j]
                dark = (vals.values[i, j] - lo) / (hi - lo + 1e-12) > 0.55
                ax.text(j, i, fmt.format(v), ha="center", va="center", fontsize=7, color="white" if dark else "black")
        ax.set_xlabel("calibration experiments M")
        ax.set_ylabel("number of qubits N")
        ax.set_title(title, fontsize=10)
        fig.colorbar(im, ax=ax, label="log10 of annotated value")
    fig.suptitle("Where does the locality prior pay off? (darker = larger value)", y=1.0)
    _save(fig, path)


def fig_ablation(summary: pd.DataFrame, n: int, Ms: list[int], order: list[tuple[str, str]], path: Path) -> None:
    """Grouped bars with hatching: ablation of the structural prior at one array size."""
    hatches = ["", "//", "\\\\", "xx", "..", "++", "oo", "--"]
    greys = ["1.0", "0.85", "0.7", "0.55", "0.4", "0.9", "0.25", "0.75"]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    width = 0.8 / len(order)
    for k, (m, label) in enumerate(order):
        vals, errs = [], []
        for M in Ms:
            g = summary[(summary.N == n) & (summary.method == m) & (summary.M == M)]
            vals.append(g.rms_khz_mean.iloc[0] if len(g) else np.nan)
            errs.append(g.rms_khz_std.iloc[0] if len(g) else 0.0)
        x = np.arange(len(Ms)) + (k - (len(order) - 1) / 2) * width
        ax.bar(x, vals, width * 0.95, yerr=errs, capsize=2, color=greys[k % len(greys)], edgecolor="black",
               hatch=hatches[k % len(hatches)], label=label, lw=0.8)
    ax.set_xticks(range(len(Ms)), [str(m) for m in Ms])
    ax.set_yscale("log")
    ax.set_xlabel("calibration experiments M")
    ax.set_ylabel(KHZ)
    ax.set_title(f"Ablation of the structural prior, {n} qubits (mean ± std over seeds)")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(axis="y", alpha=0.25)
    _save(fig, path)


def fig_robustness(summary: pd.DataFrame, n: int, Ms: list[int], path: Path) -> None:
    """Small multiples: noise and parasitic-density sweeps at two budgets."""
    methods = ["none", "dense", "prior"]
    fig, axes = plt.subplots(len(Ms), 2, figsize=(10, 3.6 * len(Ms)), sharey=True, squeeze=False)
    for r, M in enumerate(Ms):
        for c, (sweep, xcol, xlabel) in enumerate(
            [("noise", "sigma_f_khz", "frequency-readout noise per experiment (kHz)"),
             ("parasitic", "p_par", "density of non-local parasitic couplings")]
        ):
            ax = axes[r, c]
            for m in methods:
                g = summary[(summary.sweep == sweep) & (summary.M == M) & (summary.method == m)].sort_values(xcol)
                st = STYLE[m]
                ax.errorbar(g[xcol], g.rms_khz_mean, yerr=g.rms_khz_std.fillna(0), capsize=2, lw=1.2, ms=5, **st)
            ax.set_yscale("log")
            if sweep == "noise":
                ax.set_xscale("log")
            ax.set_xlabel(xlabel)
            ax.set_title(f"{n} qubits, M = {M}", fontsize=10)
            ax.grid(alpha=0.25)
        axes[r, 0].set_ylabel(KHZ)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle("Robustness of the control error to readout noise and non-local crosstalk", y=1.0)
    _save(fig, path)


def fig_budget(star: pd.DataFrame, targets: list[float], path: Path) -> None:
    """Experiments needed to reach a target control error, versus array size."""
    fig, axes = plt.subplots(1, len(targets), figsize=(5 * len(targets), 3.8), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, t in zip(axes, targets):
        for m in ["sweep", "dense", "prior"]:
            g = star[(star.method == m) & (star.target_khz == t)].sort_values("N")
            ax.plot(g.N, g.M_star, **{k: v for k, v in STYLE[m].items()}, lw=1.2, ms=6)
        ax.plot(star.N.unique(), star.N.unique(), color="0.8", lw=1, label="M = N")
        ax.set_xscale("log")
        ax.set_yscale("log", base=2)
        ax.set_xlabel("number of qubits N")
        ax.set_title(f"target: {t:.0f} kHz (missing point = not reached)", fontsize=10)
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("smallest tested budget M reaching target")
    axes[0].legend(fontsize=7)
    _save(fig, path)
