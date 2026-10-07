# Experiments

Sixteen experiments are defined in the registry. **One is implemented.**

```bash
cosmos experiment list
```

| ID | Name | Score | Implemented |
|---|---|---|---|
| EXP-001 | Cosmic web and large-scale structure vs ΛCDM | 0.84 | **yes** |
| EXP-002 | Large-scale isotropy and preferred direction | 0.86 | no |
| EXP-003 | Homogeneity scale measurement | 0.83 | no |
| EXP-004 | Cosmic web reconstruction | 0.77 | no |
| EXP-005 | Dark matter: particle vs modified gravity | 0.90 | no |
| EXP-006 | Modified gravity model comparison | 0.83 | no |
| EXP-007 | Dark energy: w, w0-wa, evolving models | 0.90 | no |
| EXP-008 | Hubble tension analysis | 0.97 | no |
| EXP-009 | Inflation signatures | 0.79 | no |
| EXP-010 | CMB anomalies with look-elsewhere correction | 0.86 | no |
| EXP-011 | Multiverse / bubble collision signatures | 0.66 | no |
| EXP-012 | Cosmic topology (matched circles) | 0.80 | no |
| EXP-013 | Spatial repetition under various assumptions | 0.61 | no |
| EXP-014 | Large cosmic structures | 0.84 | no |
| EXP-015 | General Relativity tests at cosmological scales | 0.91 | no |
| EXP-016 | Gravitational-wave observations | 0.86 | no |

Running an unimplemented experiment exits with code 2 and says so:

```console
$ cosmos experiment run EXP-008
Experiment EXP-008 not implemented yet.
```

This is deliberate. A stub that prints "not yet implemented" but exits 0 is
indistinguishable from a working analysis in a pipeline script.

## Priority scoring

Each experiment is scored 0–1 on seven axes, averaged:

`data_availability`, `theoretical_importance`, `observational_leverage`,
`reproducibility`, `computational_feasibility`, `falsifiability`,
`potential_impact`

The score orders work, it does not gate it. EXP-008 (Hubble tension) scores
highest because it has excellent data availability and genuine falsifiability.
`cosmos experiment list` reports the current `next_in_line`.

## Machine-readable definitions

Every experiment carries a definition with these keys:

```json
{
  "id": "EXP-001",
  "name": "...",
  "hypothesis": "...",
  "null_model": "...",
  "alternative_models": [],
  "assumptions": [],
  "datasets": [],
  "preprocessing": [],
  "prediction": "...",
  "statistical_test": "...",
  "expected_result": "...",
  "falsification_condition": "...",
  "uncertainty": [],
  "systematic_errors": [],
  "reproducibility": {"random_seed": 42, "software_version": "0.1.0.dev0"},
  "status": "data_awaiting"
}
```

`cosmos experiment status EXP-001` prints this. A test asserts every experiment
defines a hypothesis, a null model, a falsification condition, and a
reproducibility block — so an under-specified experiment cannot be added.

## EXP-001 in detail

**Question.** Is the large-scale universe consistent with ΛCDM?

**Pipeline.**

1. Ingest a galaxy catalogue — real if one is registered, otherwise a documented
   synthetic one
2. Preprocess into 3D coordinates and a density field
3. Measure P(k) on a log k grid via FFT, with Poisson and sampling uncertainties
4. Generate the ΛCDM (BBKS) prediction, σ8-normalised
5. Measure the galaxy bias from the fields rather than assuming it
6. χ² goodness-of-fit
7. Calibrate the χ² by Monte Carlo over synthetic ΛCDM skies
8. Injection-and-recovery of a known feature
9. Adversarial review
10. Classify using the pre-registered decision rule

**Result classification vocabulary** (from the specification):

```
SUPPORTED            DISFAVORED              INCONCLUSIVE
CONSISTENT_WITH_STANDARD_MODEL     STATISTICALLY_SIGNIFICANT_ANOMALY
LIKELY_SYSTEMATIC    REQUIRES_REPLICATION     NOT_TESTABLE
INSUFFICIENT_DATA    UNKNOWN
```

**Falsification condition.** P(k) deviates from ΛCDM by more than 5σ after
systematics and look-elsewhere corrections; or homogeneity is not achieved by
R = 250 h⁻¹ Mpc.

## Implementing a new experiment

```python
from cosmos.experiments import ExperimentRunner

class EXP002Experiment(ExperimentRunner):
    def _analysis_steps(self) -> list[str]:
        return ["...", "..."]

    def _prepare_data(self) -> dict: ...
    def _predict_lcdm(self, data) -> dict: ...
    def _simulate_null(self) -> dict: ...
    def _run_analysis(self, data, prediction, null_dist) -> dict: ...
    def _assess_systematics(self, data, analysis) -> dict: ...
    def _adversarial(self, data, analysis, systematics) -> dict: ...
    def _classify(self, analysis, systematics, adversarial) -> dict: ...
```

Register it:

```python
IMPLEMENTED_EXPERIMENTS = {
    "EXP-001": "cosmos.experiments:EXP001Experiment",
    "EXP-002": "cosmos.experiments:EXP002Experiment",
}
```

Add tests for the physics, not just the plumbing. The most valuable tests are
the ones that would catch a wrong answer — see
[test_experiments.py](../tests/test_experiments.py), which validates the power
spectrum estimator against the field it sampled.