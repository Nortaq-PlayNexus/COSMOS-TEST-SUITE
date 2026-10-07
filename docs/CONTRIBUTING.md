# Contributing

## Getting set up

```bash
git clone https://github.com/<your-org>/COSMOS-TEST-SUITE.git
cd COSMOS-TEST-SUITE
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -e ".[dev]"
python -m pytest tests/ -q
```

## Before you open a pull request

```bash
python -m pytest tests/ -q     # all tests must pass
ruff check cosmos/ tests/      # lint
```

## What a good test looks like here

The valuable tests are the ones that would catch a **wrong answer**, not just a
crash. Concretely, prefer:

- a value checked against an analytically known result
- an invariant that must hold for physical reasons
- an assertion that a known signal is recovered from known noise

For example, `test_measured_pk_agrees_with_the_field_it_sampled` measures P(k)
from a mock catalogue and checks it against the P(k) of the field the galaxies
were actually drawn from. A wrong FFT convention, a units error, or a bad bias
normalisation all fail it immediately. A test asserting "returns a dict" would
pass while the science was broken.

Real bugs this suite has already caught, for calibration:

| Bug | Test that caught it |
|---|---|
| Fourier amplitudes off by √N | realised P(k) vs input P(k) |
| Missing Hermitian symmetry | field looked like white noise |
| P(k) divided by box volume, not cell volume | σ8 round-trip |
| Density contrast normalised by wrong density | P(k) vs source field |
| BBKS transfer function missing `(2π)³/h³` | spectral slope |
| Growth factor divide-by-zero at a=1 | `D(0) == 1` |
| Bubble template centre from coordinate grid | template shape |
| FP threshold ignoring bin count | false-positive rate ≈ 1.0 |

## Code style

- 4-space indent, ~100 column lines
- Type hints on public functions
- Docstrings that state the **equation**, variables, units, assumptions, and
  numerical method — this is a requirement, not a courtesy, per §58 of the spec
- Comments explaining *why*, especially where a non-obvious normalisation
  constant is involved

## Adding an experiment

See [EXPERIMENTS.md](EXPERIMENTS.md). The short version: subclass
`ExperimentRunner`, implement the seven abstract methods, register it in
`IMPLEMENTED_EXPERIMENTS`, and add tests for the physics.

## Rules that are not negotiable

These come from the specification and are enforced by tests:

1. **Never fabricate.** No invented datasets, results, or citations. If
   something is unavailable, mark it unavailable.
2. **Never claim proof.** Use supports / disfavors / consistent with /
   inconsistent with. `test_report_does_not_claim_proof` enforces this.
3. **Disclose synthetic data.** Any run on simulated data must say so in its
   summary. `test_summary_discloses_synthetic_data_limitation` enforces this.
4. **Register the plan before computing.** `_analysis_steps()` must be complete
   before `_run_analysis` can see a result.
5. **Report unquantified systematics.** Flag them rather than implying coverage.
6. **Do not modify `raw/`.** Derived data goes in `processed/`.

## Reporting bugs

Open an issue with:

- the command you ran
- the full output
- your Python version and OS
- the output of `python -m cosmos version`

If the bug is scientific rather than a crash — a number that looks wrong, a
result that disagrees with published values — say so plainly. Those matter more
than tracebacks.