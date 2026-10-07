# COSMOS Test Suite v0.1.0

A research platform for testing cosmological and fundamental-physics hypotheses
by attempting to **falsify** them rather than confirm them.

## No scientific findings are claimed

This is stated first, and deliberately, because it is the single most important
thing to know about this deposit.

At the time of this release:

- **None of the 35 registered research questions has been answered.** All remain open.
- **The one implemented experiment (EXP-001) has only ever consumed synthetic
  data.** No experiment in this suite has fitted a cosmological model to an
  observation.
- **What is released here is the machinery for trying to produce falsifiable
  results**, not results.

If you cite this work, please cite it as a platform. Citing it as evidence for or
against a cosmological claim would misrepresent it.

## What the platform provides

| Capability | Description |
|---|---|
| Pre-registration | Analysis plans fixed before data are examined; the registration timestamp is recorded in every result |
| Adversarial review | A "try to kill it" stage that asks what else could produce the same outcome |
| Look-elsewhere correction | Scans across wavenumber bins and locations are corrected for, so a peak is not mistaken for a discovery |
| Provenance chain | Every result records its inputs, seed, code version, and commit |
| Reproducibility packages | `--seed 42` reproduces the committed EXP-001 result exactly |
| Honest classification | Results are labelled with a fixed vocabulary that distinguishes observation, inference, hypothesis, and speculation |

The governing principle is that the goal is not to prove a theory but to
determine whether the data can **disprove** it.

## Validation status

**Internal validation.** 247 tests. The physics code has had real bugs found by
this suite, each now pinned by a regression test:

- a missing BBKS transfer-function prefactor
- GRF Fourier amplitudes off by a factor of √N
- absent Hermitian symmetry, which silently made generated fields white noise
- P(k) divided by box volume instead of cell volume
- a false-positive threshold that ignored bin count, giving a 99.5% false-positive rate
- the Hubble distance computed as c/h rather than c/(100h), overstating every distance 100-fold

**External validation: one component performed.** The BAO distance measures
(`cosmos/cosmology.py`) were checked against real DESI DR2 baryon acoustic
oscillation vectors (arXiv:2503.14738, arXiv:2503.14739). The D_H column was
reproduced to 1.1% at z = 2.330. This comparison found both the factor-100
distance bug listed above and an unresolved labelling problem: values in a
column marked `DM_over_rs` in a third-party mirror are numerically consistent
with the comoving distance D_C/r_s rather than the transverse distance D_M/r_s.
No cosmological fit was performed on that dataset.

**External validation: not performed for any parameter inference.** No
cosmological parameter has been fitted to an observation and checked against a
published result.

## Data sources

The literature corpus in `papers/metadata/corpus.json` holds 86 genuine records
retrieved from the live arXiv API, spanning 1991–2026, 58 with DOIs.

Survey data ingestion is incomplete. Reachability was probed from the development
environment: SDSS SkyServer and the SDSS DR12 BOSS release were blocked, LIGO
open data was blocked, and NASA LAMBDA's Planck data paths returned 404. Those
datasets are marked unavailable rather than substituted with invented values.
See `docs/DATA_SOURCES.md` for the full table.

## Known limitations

- 15 of the 16 registered experiments are defined but not implemented; they exit
  with a nonzero status rather than returning placeholder results.
- The verification subcommand reports that its runner is not yet implemented.
- Spatial curvature and neutrino-mass extensions are not modelled.
- The reported BAO sound horizon is taken from the published Planck 2018 value
  rather than recomputed; the rationale is recorded in `cosmos/cosmology.py`.

## Reproducing

```bash
git clone https://github.com/Nortaq-PlayNexus/COSMOS-TEST-SUITE.git
cd COSMOS-TEST-SUITE
pip install -e ".[dev]"
python -m pytest -q          # 247 tests
python -m cosmos experiment run EXP-001 --seed 42
```

The committed result is reproducible bit-for-bit in its scientific content. A
clean checkout at this tag with `--seed 42` yields the same classification,
p-value (0.295), significance (0.54σ), χ², σ₈ test, injection-recovery and
Monte Carlo results. Only timestamps and the commit hash differ.

## Licence

GPL-3.0-only. See `LICENSE`.
