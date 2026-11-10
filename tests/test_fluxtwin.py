"""Fast unit tests for the flux-crosstalk digital-twin package."""

import numpy as np
import pytest

from fluxtwin.control import compensate, qubit_infidelity, register_fidelity
from fluxtwin.device import freq, freq_inv, grid_distances, make_device, run_calibration_experiments
from fluxtwin.estimators import fit_banded, fit_dense, fit_prior_ridge
from fluxtwin.experiments import run_trial


def test_freq_roundtrip() -> None:
    phi = np.linspace(0.05, 0.4, 7)
    fmax = np.full(7, 6.0)
    assert np.allclose(freq_inv(freq(phi, fmax), fmax), phi)


def test_grid_distances_symmetry() -> None:
    d = grid_distances(4)
    assert d.shape == (16, 16) and np.allclose(d, d.T) and np.allclose(np.diag(d), 0)
    assert np.isclose(d[0, 1], 1.0) and np.isclose(d[0, 5], np.sqrt(2))


def test_noiseless_dense_recovers_crosstalk() -> None:
    rng = np.random.default_rng(1)
    dev = make_device(3, 0.05, rng)
    V = 0.03 * rng.standard_normal((40, dev.n))
    Y = run_calibration_experiments(dev, V, 0.0, rng)
    assert np.allclose(fit_dense(V, Y), dev.C, atol=1e-8)


def test_noiseless_compensation_is_exact() -> None:
    rng = np.random.default_rng(2)
    dev = make_device(3, 0.0, rng)
    dphi = 0.03 * rng.standard_normal((5, dev.n))
    v = compensate(dev.C, dphi)
    assert np.allclose(v @ dev.C.T, dphi)


def test_banded_with_full_radius_equals_dense() -> None:
    rng = np.random.default_rng(3)
    dev = make_device(3, 0.0, rng)
    V = 0.03 * rng.standard_normal((30, dev.n))
    Y = run_calibration_experiments(dev, V, 20.0, rng)
    assert np.allclose(fit_banded(V, Y, dev.dist, 10.0), fit_dense(V, Y))


def test_prior_ridge_limits() -> None:
    rng = np.random.default_rng(4)
    dev = make_device(3, 0.0, rng)
    V = 0.03 * rng.standard_normal((30, dev.n))
    Y = run_calibration_experiments(dev, V, 20.0, rng)
    weak = fit_prior_ridge(V, Y, dev.dist, 1e-9, 1.0, 0.03)
    assert np.allclose(weak, fit_dense(V, Y), atol=1e-4)
    strong = fit_prior_ridge(V, Y, dev.dist, 1e9, 1.0, 0.03)
    off = ~np.eye(dev.n, dtype=bool)
    assert np.abs(strong[off]).max() < 1e-3


def test_register_fidelity_matches_statevector() -> None:
    qiskit = pytest.importorskip("qiskit")
    from qiskit.quantum_info import Statevector

    phases = np.array([0.3, -0.5, 0.2])
    qc = qiskit.QuantumCircuit(3)
    qc.h(range(3))
    ideal = Statevector(qc)
    for q, p in enumerate(phases):
        qc.rz(float(p), q)
    assert np.isclose(abs(ideal.inner(Statevector(qc))) ** 2, register_fidelity(phases))


def test_infidelity_scales_quadratically() -> None:
    a, b = qubit_infidelity(np.array([50.0])), qubit_infidelity(np.array([100.0]))
    assert np.isclose(b / a, 4.0, rtol=1e-3)


def test_run_trial_ordering_and_determinism() -> None:
    kw = dict(side=3, M=64, sigma_f_khz=50.0, p_par=0.02, seed=0, methods=["none", "dense", "prior"])
    r1, r2 = run_trial(**kw), run_trial(**kw)
    e = {r["method"]: r["rms_khz"] for r in r1}
    assert e["dense"] < e["none"] and e["prior"] < e["none"]
    assert [r["rms_khz"] for r in r1] == [r["rms_khz"] for r in r2]
