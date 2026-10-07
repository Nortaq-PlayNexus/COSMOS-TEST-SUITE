# Reproducibility

Every result must be reproducible from a clean environment.

## What a run writes

```
experiments/EXP-001/reproducibility/
  environment.lock    exact package versions (pip freeze)
  experiment.lock     seed, commit, classification, command
  data.manifest       datasets used and their versions
  README.md           the pre-registered analysis plan, embedded
```

Plus, in the run's output directory:

```
results/analysis.json   statistical output of each stage
results/result.json     classification, systematics, adversarial, provenance
report/report_EXP-001.md
```

## Determinism

A run is fully determined by its seed.

**Verified behaviour.** From a clean clone on a different machine,
`experiment run EXP-001 --seed 42` reproduces the classification, p-value,
significance, and chi-square exactly. Only wall-clock timestamps differ.

```bash
git clone <repo> && cd COSMOS-TEST-SUITE
python -m cosmos experiment run EXP-001 --seed 42
python -c "import json; r=json.load(open('experiments/EXP-001/results/result.json')); \
           print(r['classification'], r['p_value'])"
```

Check against the committed artifact:

```bash
python -c "import json,subprocess; \
  old=json.loads(subprocess.check_output(['git','show','HEAD:experiments/EXP-001/results/result.json'],text=True)); \
  new=json.load(open('experiments/EXP-001/results/result.json')); \
  print('match' if old['p_value']==new['p_value'] else 'MISMATCH')"
```

If that prints `MISMATCH` with the same seed, something is wrong. This is a
real check, not a formality: during development the committed artifacts were
once left over from a different seed, and it surfaced immediately.

## The reproducibility package

### `experiment.lock`

```json
{
  "experiment_id": "EXP-001",
  "commit": "abc1234",
  "analysis_version": "v1",
  "random_seed": 42,
  "cosmos_version": "0.1.0",
  "classification": "consistent_with_standard_model",
  "command": "cosmos experiment run EXP-001"
}
```

### `data.manifest`

Every dataset with its version and checksum. A dataset that cannot be traced to
a version cannot be reproduced.

## Data provenance chain

Every reported number should be traceable:

```
RESULT → ANALYSIS → CODE VERSION → PROCESSED DATA → RAW DATA
       → ORIGINAL SOURCE → PAPER/MISSION DOCUMENTATION
```

This is recorded as a `ProvenanceLink` chain and rendered as a table in the
report's Provenance section. Each entry carries a type, an identifier, a
description, and a timestamp.

## Integrity

`raw/` is append-only. Derived products always land in `processed/`, so original
bytes survive every analysis. Re-downloading never overwrites existing data —
it creates a new version.

Checksums are enforced on download where a dataset provides one. A mismatch
raises rather than proceeding.

## Statistical integrity

Recorded with every run:

| Item | Where |
|---|---|
| Analysis plan | `reproducibility/README.md`, `result.json` |
| Timestamp | `experiment.lock` |
| Software commit | `experiment.lock` |
| Dataset version | `data.manifest` |
| Parameters | analysis plan |
| Random seed | `experiment.lock` |
| Null-simulation hash | `result.json` |

The plan is written **before** the data are examined. This is enforced by call
order in `ExperimentRunner.run()` and asserted by a test, not by convention.

## Reproducing on another machine

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -e .
pip install -r experiments/EXP-001/reproducibility/environment.lock
python -m cosmos experiment run EXP-001 --seed 42
```

Then compare the result JSON against the committed one. See
[SCIENCE_VALIDATION.md](SCIENCE_VALIDATION.md) for comparing against published
values rather than against our own prior output.

## CI

The test suite runs on every push via GitHub Actions
(`.github/workflows/tests.yml`), across Python 3.12, 3.13, and 3.14 on Linux,
macOS, and Windows. The "221 tests pass" claim is verifiable rather than
asserted — check the badge, or the Actions tab.