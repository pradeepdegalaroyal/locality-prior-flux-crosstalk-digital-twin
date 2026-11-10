# Research gap: calibration cost of a crosstalk digital twin as the array grows

## 1. State of the art (from the supplied literature)

The supplied literature set contains eight papers (one recent, three landmark, four review; no adjacent-role papers). Digital Object Identifiers (DOIs) are given for every citation. None of the eight studies control-system modelling or digital twins of a device directly, so the gap below is derived from what they say about *scale*, *precision of control* and *noise-limited practicality*, not from a claim that they leave this exact question open.

* Hardware has reached tens of qubits: Wu et al., 2021 (DOI 10.1103/PhysRevLett.127.180501) report a 66-qubit programmable superconducting processor with tunable couplers, and state that scaling to many qubits with high-precision control is essential. How the control model is *obtained* at that scale is outside the abstract.
* Algorithms demand precise single-qubit control: Low and Chuang, 2017 (DOI 10.1103/PhysRevLett.118.010501) obtain optimal Hamiltonian simulation from sequences of single-qubit rotations (quantum signal processing, QSP), so residual single-qubit control error enters directly.
* Resource estimates assume an error-corrected architecture: Blunt et al., 2022 (DOI 10.1021/acs.jctc.2c00574) cost molecular simulations on a fault-tolerant machine; Outeiral et al., 2021 (DOI 10.1002/wcms.1481) stress hype and caveats and that useful quantum computation has not yet arrived.
* The newest survey, Pereira et al., 2027 (DOI 10.1007/978-3-032-27834-0_47), lists trainability, generalisation, error mitigation in the Noisy Intermediate-Scale Quantum (NISQ) regime and *automated circuit design* as open challenges. Li et al., 2020 (DOI 10.1109/ACCESS.2020.2970105) survey quantum optimisation and learning.

## 2. Related work table

| Paper (DOI) | Year | Role | What it does | What it does NOT cover |
|---|---|---|---|---|
| Pereira et al. (10.1007/978-3-032-27834-0_47) | 2027 | recent | Survey of quantum machine learning (QML) architectures, encodings, NISQ trainability | Learning models of the *device control layer*; calibration cost |
| Wu et al. (10.1103/PhysRevLett.127.180501) | 2021 | landmark | 66-qubit tunable-coupler processor, random-circuit sampling advantage | How the control/crosstalk model is learned or how its cost scales |
| Low and Chuang (10.1103/PhysRevLett.118.010501) | 2017 | landmark | Optimal Hamiltonian simulation from single-qubit rotation sequences | Realistic control error on the rotations |
| Bernstein and Lange (10.1038/nature23461) | 2017 | landmark | Post-quantum cryptography overview | Device modelling (different problem) |
| Outeiral et al. (10.1002/wcms.1481) | 2021 | review | Quantum computing for computational biology, with caveats | Hardware control scaling |
| Blunt et al. (10.1021/acs.jctc.2c00574) | 2022 | review | Fault-tolerant resource estimates for drug-discovery chemistry | Pre-fault-tolerant control and calibration burden |
| Li et al. (10.1109/ACCESS.2020.2970105) | 2020 | review | Survey of quantum optimisation and quantum learning | Control-system level models |
| Asif (10.3390/iot2010005) | 2021 | review | Lattice-based cryptography for Internet-of-Things devices | Not about quantum hardware control |

Only eight papers were supplied, so the table cannot reach ten rows without inventing references; no reference outside the brief is used.

## 3. The gap

Read together, the landmark hardware paper (many qubits need high-precision control), the algorithmic landmark (precision of single-qubit rotations matters) and the newest survey (scalability, automation and noise-aware practicality are unresolved) point at one unquantified item: **the experimental cost of building the control model itself**. A flux-tunable array has an `N x N` crosstalk matrix between control lines and qubit frequencies. The textbook calibration estimates it without structure (line by line, or by dense regression), which needs at least `N` experiments, and the error of a dense estimate grows with `N` at a fixed budget. Locality of crosstalk is a physical fact that machine-learning (ML) twins rarely exploit, and generic neural twins are not designed for few-experiment regimes.

**Testable gap (simulation scale, `N` = 4-100 qubits on a square lattice):** how does the control error of a crosstalk-compensated frequency controller scale with array size at a fixed calibration budget, and does a distance-weighted Bayesian prior (a locality-structured digital twin) lower the budget needed relative to unstructured estimators?

**Novelty in one sentence:** a budget-versus-size study that treats the *calibration experiments themselves* as the scarce resource and compares a locality-prior twin with the line-sweep standard, dense least squares and a generic neural twin on identical experiments.

## 4. Hypotheses and success metrics (fixed before the final run)

The metric is the root-mean-square (RMS) frequency error, in kHz, between realised and target qubit frequencies over 64 random targets, averaged over seeds 0-4. Parameters were tuned on separate pilot seeds (1000-1002), never on the reported seeds.

* **H1.** At a fixed budget `M <= N`, the distance-prior twin has a lower RMS error than dense least squares; the ratio grows with `N`.
* **H2.** The smallest budget `M*` that reaches 300 kHz (and 100 kHz) is smaller for the prior twin than for dense least squares and the sweep.
* **H3.** The advantage over dense least squares disappears when the budget is large (`M >> N`) or when non-local parasitic couplings are dense; the prior must not be worse than dense in that regime beyond seed noise.
* **H4 (negative control).** A generic multilayer-perceptron (MLP) twin does not close the gap.

H1-H4 are falsifiable: any of them can fail in the tables of `results/`.

## 5. Scale caveat

All numbers come from a classical simulation of the flux-line/frequency physics (the quantum level enters only through the phase error of idling qubits, checked against a statevector). Crosstalk amplitudes (1 % nearest neighbour, decay length 0.8 lattice constants, 0.2 % parasitic entries) are assumed, plausible values and not fitted to any device.
