# Method

## Device model

`N = side^2` flux-tunable transmons on a square lattice. Qubit `i` has frequency `f_i(phi) = fmax_i * sqrt(cos(pi * phi))` (`fmax` about 6 GHz, bias flux `phi0_i` in 0.12-0.28 flux quanta). Control line `j` acts on qubit `i` through the crosstalk matrix `C[i, j]`: `phi = phi0 + C v`. `C` has a gain of about 1 on the diagonal, a distance-decaying local part `0.01 * exp(-(d - 1) / 0.8)` with 30 % multiplicative scatter, and non-local parasitic entries (probability `p_par` = 0.02 per pair, amplitude about 0.002). Random devices are drawn per seed. The single-qubit curve `f_i(phi)` is assumed known (it is measured once per qubit by spectroscopy).

## Calibration experiments (the scarce resource)

One experiment applies a random command vector `v ~ N(0, 0.03^2 I)` to all lines and reads all qubits in parallel. Each measured frequency carries Gaussian noise (default 50 kHz, a stand-in for finite-shot Ramsey estimation). The frequency is converted to a flux shift with the known curve, giving `Y = V C^T + noise`. A budget is `M` such experiments.

## Estimators (all use the same `V, Y`)

| Name | Description |
|---|---|
| `none` | no crosstalk compensation (reference) |
| `sweep` | **standard practice**: one line at a time, `M // N` amplitudes per line, slope fit (needs `M >= N`) |
| `dense` | **strong classical baseline**: unstructured least squares on random parallel excitations (minimum-norm when `M < N`) |
| `prior` | **proposed locality-prior twin**: ridge regression with prior variance of entry `(i, j)` decaying as `exp(-2 (d_ij - 1) / lam)`; strength `kappa` and decay `lam` chosen by 25 % hold-out validation (6 x 4 grid), then refit on all data |
| `ridge_flat` | ablation: same, but distance-blind (`kappa` only) |
| `banded_R<r>`, `banded_val` | ablation: hard cutoff of the support at lattice distance `r` (fixed, or chosen by validation) |
| `mlp`, `mlp_skip` | **generic machine-learning (ML) twins**: multilayer perceptron (MLP, two tanh layers of 64 units) trained with Adam for 600 epochs on the same experiments, optionally with a parallel linear skip layer; commands are found by inverting the network with L-BFGS (limited-memory Broyden-Fletcher-Goldfarb-Shanno). Fixed default settings, not tuned |

The "standard quantum baseline" of this problem is the line-by-line sweep used to characterise superconducting arrays; the dense estimator is the strongest unstructured classical alternative.

## Control test and metrics

For 64 random target flux shifts (`0.03` standard deviation, up to about 200 MHz), commands `v = C_hat^+ dphi` are applied to the *true* device and the realised frequencies are compared with the targets. **Metric: root-mean-square (RMS) frequency error in kHz.** Secondary metrics: smallest tested budget `M*` reaching 300 kHz or 100 kHz (seed-mean error), and mean single-qubit idle infidelity `sin^2(pi * err * 50 ns)` for an equatorial state. The closed-form product-state fidelity is verified against a Qiskit statevector (`results/statevector_check.json`).

## Experiments

1. **Scaling**: `N` = 4, 9, 16, 25, 36, 64, 100; `M` = 8 ... 1024; seeds 0-4. The MLP twins are run for `N <= 25` and `M` in {128, 512} (training cost).
2. **Ablation**: structural prior (distance profile, hard cutoff radius 1, 2, 4, validated radius, flat ridge) at `N` = 64, `M` = 32 ... 256.
3. **Noise robustness**: readout noise 10-400 kHz at `N` = 64, `M` = 64 and 256.
4. **Model-mismatch robustness**: parasitic coupling density 0-0.2 at the same sizes.
5. **Device diagnostics**: condition number of `C` and the share of `C` outside radius 2 (`results/device_stats.csv`).

## Seeds and statistics

Seeds 0-4 control the device, calibration noise and targets jointly. Tables report the mean and standard deviation over the five seeds. Pilot tuning used seeds 1000-1002 only.
