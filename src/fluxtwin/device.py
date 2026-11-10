"""Physical model of a flux-tunable transmon array with control-line crosstalk.

The device is a square grid of ``n = side**2`` qubits. Qubit ``i`` has a
single-qubit frequency-versus-flux curve ``F_i`` (a transmon-like
``f_max * sqrt(cos(pi * phi))`` branch) and is driven by its own flux line.
Line ``j`` couples into qubit ``i`` with the *crosstalk matrix* ``C[i, j]``::

    phi_i = phi0_i + sum_j C[i, j] * v_j

where ``v`` is the vector of commanded flux-line amplitudes (in units of the
flux quantum). ``C`` is dominated by a distance-decaying term plus a small
number of non-local "parasitic" entries (shared ground, package modes).
All frequencies are in GHz, fluxes in units of the flux quantum.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Nearest-neighbour crosstalk amplitude (fraction of the diagonal gain).
C0 = 0.01
#: Decay length of the local crosstalk, in lattice constants.
LAMBDA = 0.8
#: Typical amplitude of a non-local parasitic entry.
PARASITIC_AMP = 0.002


def freq(phi: np.ndarray, fmax: np.ndarray) -> np.ndarray:
    """Qubit frequency (GHz) at flux ``phi``: ``fmax * sqrt(cos(pi * phi))``."""
    return fmax * np.sqrt(np.clip(np.cos(np.pi * phi), 0.0, None))


def freq_inv(f: np.ndarray, fmax: np.ndarray) -> np.ndarray:
    """Inverse of :func:`freq` on the branch ``0 <= phi < 0.5``."""
    ratio = np.clip((f / fmax) ** 2, -1.0, 1.0)
    return np.arccos(ratio) / np.pi


@dataclass
class Device:
    """A simulated array: geometry, true crosstalk matrix and qubit curves."""

    side: int
    dist: np.ndarray  # (n, n) Euclidean lattice distances
    C: np.ndarray  # (n, n) true crosstalk matrix
    phi0: np.ndarray  # (n,) bias flux at zero command
    fmax: np.ndarray  # (n,) maximum frequency (GHz)

    @property
    def n(self) -> int:
        """Number of qubits."""
        return self.side * self.side


def grid_distances(side: int) -> np.ndarray:
    """Pairwise Euclidean distances on a ``side x side`` square lattice."""
    rr, cc = np.divmod(np.arange(side * side), side)
    pos = np.stack([rr, cc], axis=1).astype(float)
    diff = pos[:, None, :] - pos[None, :, :]
    return np.sqrt((diff**2).sum(-1))


def make_device(side: int, p_par: float, rng: np.random.Generator) -> Device:
    """Draw a random device.

    Args:
        side: Lattice side length (``n = side**2`` qubits).
        p_par: Probability that an off-diagonal pair carries a non-local
            parasitic crosstalk entry of amplitude ``~PARASITIC_AMP``.
        rng: Random generator (controls the whole device).
    """
    n = side * side
    dist = grid_distances(side)
    local = C0 * np.exp(-(dist - 1.0) / LAMBDA) * (1.0 + 0.3 * rng.standard_normal((n, n)))
    off = ~np.eye(n, dtype=bool)
    C = np.where(off, local, 0.0)
    parasitic = (rng.random((n, n)) < p_par) & off
    C = C + parasitic * PARASITIC_AMP * rng.uniform(0.5, 1.5, (n, n)) * rng.choice([-1, 1], (n, n))
    C[np.diag_indices(n)] = 1.0 + 0.05 * rng.standard_normal(n)
    phi0 = rng.uniform(0.12, 0.28, n)
    fmax = 6.0 + 0.2 * rng.standard_normal(n)
    return Device(side=side, dist=dist, C=C, phi0=phi0, fmax=fmax)


def run_calibration_experiments(
    dev: Device,
    v: np.ndarray,
    sigma_f_khz: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Apply command vectors ``v`` (M x n) and return measured flux shifts.

    Every experiment drives all lines at once and reads all qubits in
    parallel. Each qubit frequency is measured with Gaussian noise of
    ``sigma_f_khz`` (a stand-in for finite-shot Ramsey estimation); the
    measured frequency is converted to an effective flux shift with the
    known single-qubit curve, giving ``Y`` (M x n) with
    ``Y ~= v @ C.T + noise``.
    """
    phi = dev.phi0 + v @ dev.C.T
    f_meas = freq(phi, dev.fmax) + sigma_f_khz * 1e-6 * rng.standard_normal(phi.shape)
    return freq_inv(f_meas, dev.fmax) - dev.phi0


def condition_stats(dev: Device, radius: float) -> dict[str, float]:
    """Condition number of ``C`` and relative size of the part outside ``radius``."""
    sv = np.linalg.svd(dev.C, compute_uv=False)
    outside = np.where(dev.dist <= radius, 0.0, dev.C)
    return {
        "cond_C": float(sv[0] / sv[-1]),
        "outside_rel_norm": float(np.linalg.norm(outside, 2) / sv[0]),
    }
