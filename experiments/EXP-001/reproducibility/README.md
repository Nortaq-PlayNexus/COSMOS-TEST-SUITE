# Reproducibility package for EXP-001

## How to reproduce

```bash
cosmos reproduce EXP-001
```

## Configuration

- Random seed: 42
- Analysis version: v1
- Cosmos version: 0.1.0.dev0
- Commit: a9c597b
- Classification: consistent_with_standard_model

## Files

- `environment.lock` - exact Python package versions
- `experiment.lock` - experiment configuration
- `data.manifest` - datasets used

## Analysis plan (registered before results were examined)

{
  "experiment_id": "EXP-001",
  "timestamp": "2026-10-07T03:28:00.150129",
  "commit": "a9c597b",
  "dataset_version": "sample_cmb_map@v1, sample_galaxy_catalog@v1, sample_rotation_curves@v1",
  "parameters": {
    "seed": 42,
    "cosmos_version": "0.1.0.dev0"
  },
  "random_seed": 42,
  "analysis_steps": [
    "Ingest the galaxy catalog (real survey data if available, otherwise a documented synthetic catalog so the pipeline runs offline).",
    "Preprocess: convert redshifts to comoving distances and 3D coordinates.",
    "Measure P(k) on a log k-grid via FFT of the galaxy density field, with per-bin Poisson and sampling uncertainties.",
    "Generate the Lambda CDM (BBKS) prediction, normalised to sigma8 = 0.81.",
    "Chi-square goodness-of-fit of the measured P(k) against the prediction.",
    "Calibrate the chi-square by Monte Carlo over synthetic Lambda CDM realisations, so the p-value accounts for correlated P(k) structure.",
    "Injection and recovery: plant a known 20% feature and confirm the pipeline detects it before interpreting any real signal.",
    "Assess systematics: survey geometry, selection function, nonlinear clustering, cosmic variance.",
    "Adversarial review: ask what else could produce this result.",
    "Classify using the decision rule fixed in advance (Section 51 vocabulary)."
  ],
  "registered_before_results": true
}
