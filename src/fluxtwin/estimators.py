"""Estimators of the crosstalk matrix (the control-relevant digital twin).

All estimators receive the commanded amplitudes ``V`` (M x n) and the
measured flux shifts ``Y`` (M x n) and return an ``n x n`` estimate of the
crosstalk matrix (or, for the neural twin, a callable forward model).
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

#: Candidate locality radii (lattice constants) for validation-based selection.
RADII: tuple[float, ...] = (1.0, 1.5, 2.0, 3.0, 4.0)


def fit_dense(V: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Unstructured least squares on random parallel excitations.

    Uses the minimum-norm solution when ``M < n`` (under-determined).
    """
    B = np.linalg.lstsq(V, Y, rcond=None)[0]
    return B.T


def fit_banded(V: np.ndarray, Y: np.ndarray, dist: np.ndarray, radius: float) -> np.ndarray:
    """Least squares restricted to entries with lattice distance <= ``radius``."""
    n = V.shape[1]
    C = np.zeros((n, n))
    for i in range(n):
        J = np.flatnonzero(dist[i] <= radius)
        C[i, J] = np.linalg.lstsq(V[:, J], Y[:, i], rcond=None)[0]
    return C


def fit_banded_validated(
    V: np.ndarray,
    Y: np.ndarray,
    dist: np.ndarray,
    rng: np.random.Generator,
    radii: tuple[float, ...] = RADII,
) -> tuple[np.ndarray, float]:
    """Locality-prior twin: pick the radius by hold-out validation, then refit.

    A random 25 % of the experiments is held out; the radius with the lowest
    held-out squared error is used for the final fit on all experiments.

    Returns:
        The estimated matrix and the selected radius.
    """
    M = V.shape[0]
    perm = rng.permutation(M)
    n_val = max(2, M // 4)
    val, tr = perm[:n_val], perm[n_val:]
    best_r, best_err = radii[0], np.inf
    for r in radii:
        C = fit_banded(V[tr], Y[tr], dist, r)
        err = float(np.mean((V[val] @ C.T - Y[val]) ** 2))
        if err < best_err:
            best_r, best_err = r, err
    return fit_banded(V, Y, dist, best_r), best_r


#: Hyper-parameter grids for the distance-prior ridge twin.
KAPPAS: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
LAMBDAS: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0)


def fit_prior_ridge(
    V: np.ndarray,
    Y: np.ndarray,
    dist: np.ndarray,
    kappa_rel: float,
    lam_hat: float | None,
    sigma_v: float,
) -> np.ndarray:
    """Distance-weighted ridge regression (Gaussian prior on crosstalk entries).

    Off-diagonal entry ``(i, j)`` is penalised by
    ``kappa_rel * sigma_v**2 * exp(2 (d_ij - 1) / lam_hat)``, i.e. a prior
    standard deviation that decays with lattice distance. ``lam_hat=None``
    gives a flat (distance-blind) ridge. The diagonal is not penalised.
    """
    n = V.shape[1]
    VtV, VtY = V.T @ V, V.T @ Y
    C = np.zeros((n, n))
    for i in range(n):
        if lam_hat is None:
            prof = np.ones(n)
        else:
            prof = np.exp(2.0 * np.maximum(dist[i] - 1.0, 0.0) / lam_hat)
        pen = kappa_rel * sigma_v**2 * prof
        pen[i] = 0.0
        C[i] = np.linalg.solve(VtV + np.diag(pen) + 1e-12 * np.eye(n), VtY[:, i])
    return C


def fit_prior_ridge_validated(
    V: np.ndarray,
    Y: np.ndarray,
    dist: np.ndarray,
    sigma_v: float,
    rng: np.random.Generator,
    flat: bool = False,
) -> tuple[np.ndarray, float, float | None]:
    """Locality-prior twin: choose (kappa, lam_hat) on 25 % held-out experiments, refit on all.

    With ``flat=True`` only ``kappa`` is searched (distance-blind ablation).
    """
    M = V.shape[0]
    perm = rng.permutation(M)
    n_val = max(2, M // 4)
    val, tr = perm[:n_val], perm[n_val:]
    lams: tuple[float | None, ...] = (None,) if flat else LAMBDAS
    best = (np.inf, KAPPAS[0], lams[0])
    for lam in lams:
        for kap in KAPPAS:
            C = fit_prior_ridge(V[tr], Y[tr], dist, kap, lam, sigma_v)
            err = float(np.mean((V[val] @ C.T - Y[val]) ** 2))
            if err < best[0]:
                best = (err, kap, lam)
    _, kap, lam = best
    return fit_prior_ridge(V, Y, dist, kap, lam, sigma_v), kap, lam


def fit_line_sweep(
    dev_n: int, apply: "callable", M_budget: int, amplitude: float
) -> tuple[np.ndarray, int] | None:
    """Standard one-line-at-a-time sweep.

    Each line is swept over ``K = M_budget // n`` amplitudes while all qubits
    are read in parallel; the column of ``C`` is the least-squares slope.
    Returns ``None`` when the budget is below one point per line.

    Args:
        dev_n: Number of lines/qubits.
        apply: Function mapping a command matrix (K x n) to measured ``Y``.
        M_budget: Total experiment budget.
        amplitude: Sweep half-range for the active line.

    Returns:
        ``(C_hat, experiments_used)`` or ``None``.
    """
    K = M_budget // dev_n
    if K < 1:
        return None
    levels = np.linspace(-amplitude, amplitude, K) if K > 1 else np.array([amplitude])
    C = np.zeros((dev_n, dev_n))
    for j in range(dev_n):
        V = np.zeros((K, dev_n))
        V[:, j] = levels
        Y = apply(V)
        C[:, j] = (V[:, j] @ Y) / (V[:, j] @ V[:, j])
    return C, K * dev_n


class MLPTwin(nn.Module):
    """Generic neural twin: flux-line commands -> effective flux shifts.

    With ``skip=True`` a parallel linear layer is added (a linear-plus-residual
    network), the strongest structure-agnostic variant tested here.
    """

    def __init__(self, n: int, hidden: int = 64, skip: bool = False) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n, hidden), nn.Tanh(), nn.Linear(hidden, hidden), nn.Tanh(), nn.Linear(hidden, n)
        )
        self.lin = nn.Linear(n, n, bias=False) if skip else None

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # noqa: D102
        out = self.net(x)
        return out + self.lin(x) if self.lin is not None else out


def fit_mlp_twin(
    V: np.ndarray, Y: np.ndarray, sigma_v: float, epochs: int, seed: int, skip: bool = False
) -> MLPTwin:
    """Train the unstructured neural twin on the same experiments (full-batch Adam)."""
    torch.manual_seed(seed)
    n = V.shape[1]
    model = MLPTwin(n, skip=skip)
    x = torch.tensor(V / sigma_v, dtype=torch.float32)
    y = torch.tensor(Y / sigma_v, dtype=torch.float32)
    opt = torch.optim.Adam(model.parameters(), lr=3e-3 if not skip else 1e-2, weight_decay=1e-4 if not skip else 0.0)
    for _ in range(epochs):
        opt.zero_grad()
        loss = torch.mean((model(x) - y) ** 2)
        loss.backward()
        opt.step()
    return model


def mlp_control(
    model: MLPTwin, dphi: np.ndarray, sigma_v: float, max_iter: int = 300
) -> np.ndarray:
    """Invert the neural twin (L-BFGS, double precision) to realise target flux shifts."""
    model = model.double()
    for p in model.parameters():
        p.requires_grad_(False)
    target = torch.tensor(dphi / sigma_v, dtype=torch.float64)
    x = target.clone().requires_grad_(True)
    opt = torch.optim.LBFGS([x], lr=1.0, max_iter=max_iter, line_search_fn="strong_wolfe",
                            tolerance_grad=1e-12, tolerance_change=1e-14)

    def closure() -> torch.Tensor:
        opt.zero_grad()
        loss = torch.sum((model(x) - target) ** 2)
        loss.backward()
        return loss

    opt.step(closure)
    return x.detach().numpy() * sigma_v
