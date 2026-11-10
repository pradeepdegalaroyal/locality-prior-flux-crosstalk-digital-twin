"""Crosstalk-compensated frequency control and its quantum-level consequence."""

from __future__ import annotations

import numpy as np

from .device import Device, freq

#: Standard deviation of the commanded flux shifts (also the calibration excitation).
SIGMA_V = 0.03
#: Idle window used to convert frequency errors into phase errors (ns).
IDLE_NS = 50.0


def draw_targets(dev: Device, n_targets: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Random target flux shifts and the corresponding target frequencies (GHz)."""
    dphi = SIGMA_V * rng.standard_normal((n_targets, dev.n))
    return dphi, freq(dev.phi0 + dphi, dev.fmax)


def compensate(C_hat: np.ndarray, dphi: np.ndarray) -> np.ndarray:
    """Commands that realise ``dphi`` if the crosstalk matrix were ``C_hat``."""
    return dphi @ np.linalg.pinv(C_hat).T


def realised_frequency_error_khz(
    dev: Device, v: np.ndarray, f_target: np.ndarray
) -> np.ndarray:
    """Per-qubit frequency error (kHz) of commands ``v`` on the true device."""
    f_act = freq(dev.phi0 + v @ dev.C.T, dev.fmax)
    return (f_act - f_target) * 1e6


def rms_khz(err_khz: np.ndarray) -> float:
    """Root-mean-square over targets and qubits."""
    return float(np.sqrt(np.mean(err_khz**2)))


def qubit_infidelity(err_khz: np.ndarray, idle_ns: float = IDLE_NS) -> float:
    """Mean single-qubit infidelity of an equator state idling for ``idle_ns``.

    A frequency error ``d`` accumulates the phase ``2 pi d t``; the overlap
    with the intended state is ``cos^2(phi / 2)``, so the infidelity is
    ``sin^2(phi / 2)``.
    """
    phi = 2.0 * np.pi * err_khz * 1e3 * idle_ns * 1e-9
    return float(np.mean(np.sin(phi / 2.0) ** 2))


def register_fidelity(phases: np.ndarray) -> float:
    """Fidelity of an n-qubit ``|+>`` product state after Z phases ``phases``.

    Closed form ``prod_i cos^2(phi_i / 2)``; tests compare it with a
    statevector simulation.
    """
    return float(np.prod(np.cos(phases / 2.0) ** 2))
