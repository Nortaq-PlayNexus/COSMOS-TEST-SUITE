# Architecture

## Layering

COSMOS is a pipeline. Each stage writes its output to disk and records how it
got there, so a result can always be traced back through the chain that produced
it.

```
              ┌──────────────┐
              │    data      │  raw survey data / synthetic mock
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │ preprocessing│  redshift→distance, gridding, P(k)
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │   model      │  ΛCDM prediction, σ8 normalisation
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │  statistics  │  χ², Monte Carlo, model comparison
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │ adversarial  │  injection-recovery, "try to kill it"
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │classification│  SUPPORTED / ANOMALY / NOT_TESTABLE …
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │   report     │  Markdown + JSON + provenance
              └──────────────┘
```

## Modules

| Module | Responsibility |
|---|---|
| `cosmos/config.py` | Settings, project-root resolution, classification vocabularies |
| `cosmos/database/` | ORM schema, repositories, session management |
| `cosmos/statistics/` | Model comparison, hypothesis tests, Monte Carlo, look-elsewhere |
| `cosmos/simulations/` | Cosmology calculator, Gaussian random fields, mock catalogues |
| `cosmos/registry/` | Experiment registry, priority scoring, machine-readable definitions |
| `cosmos/experiments/` | `ExperimentRunner` base class and concrete experiments |
| `cosmos/data/` | Dataset registry, download orchestration, offline mode |
| `cosmos/reports.py` | Report rendering from a result payload |
| `cosmos/cli/` | Command-line interface |

## The experiment framework

`ExperimentRunner` enforces a fixed order of operations. This ordering is the
scientific point of the design, not an implementation detail:

1. `setup()` — create output directories
2. `register_analysis_plan()` — **before** any data is touched (§26 of spec)
3. `_prepare_data()` — ingest and preprocess
4. `_predict_lcdm()` — generate the model prediction
5. `_simulate_null()` — build the null distribution
6. `_run_analysis()` — the statistical test
7. `_assess_systematics()` — enumerate systematics, flag unquantified ones
8. `_adversarial()` — attempt to destroy the result (§36)
9. `_classify()` — map onto the sanctioned vocabulary (§51)
10. record to database, write reproducibility package, render report

Steps 2 and 8 are the two that a normal analysis skips and that this framework
makes impossible to skip: the plan is written down first, and every result is
attacked before it is reported.

### Subclassing

```python
class EXP00XExperiment(ExperimentRunner):
    def _analysis_steps(self) -> list[str]: ...
    def _prepare_data(self) -> dict: ...
    def _predict_lcdm(self, data) -> dict: ...
    def _simulate_null(self) -> dict: ...
    def _run_analysis(self, data, prediction, null_dist) -> dict: ...
    def _assess_systematics(self, data, analysis) -> dict: ...
    def _adversarial(self, data, analysis, systematics) -> dict: ...
    def _classify(self, analysis, systematics, adversarial) -> dict: ...
```

Register it in `cosmos/cli/__init__.py::IMPLEMENTED_EXPERIMENTS` to make it
runnable via the CLI.

## Database schema

The schema encodes the hypothesis graph and the provenance chain as foreign
keys, so the relationships cannot drift out of sync with the code.

```
Question ─┬─< Hypothesis ──< Model
          ├─< Experiment ─┬─< Observation ──< Dataset
          │               ├─< Result
          │               ├─< Prediction
          │               └─< Report
          └─< Report
Model ─┬─< Hypothesis
       └─< Result
Paper >──< Experiment >──< Dataset
Paper >──< Source
```

`Result` carries a denormalised `question_id` so results can be queried by
question without a join through `Experiment`. `Experiment.null_model_id` and
`Result.null_model_id` reference `Model`, recording which model was treated as
the null in each run.

## Data layout

```
data/
  raw/          downloaded data, never modified
  processed/    derived products, one layer up from raw
  metadata/     dataset descriptions
  manifests/    dataset.json — the registry
  cache/        transient downloads
experiments/
  EXP-001/
    results/    analysis.json, result.json
    report/     report_EXP-001.md
    reproducibility/  environment.lock, experiment.lock, data.manifest, README.md
```

`raw/` is append-only. Derived data always lands in `processed/`, so the
original bytes survive every analysis (§50 of spec).

## Reproducibility

Every run writes four files to `reproducibility/`:

- **`environment.lock`** — `pip freeze` output
- **`experiment.lock`** — seed, commit, classification, command
- **`data.manifest`** — datasets used and their versions
- **`README.md`** — the pre-registered analysis plan, embedded

The seed makes a run bit-reproducible. Verified behaviour: re-running
`experiment run EXP-001 --seed 42` on a different machine reproduces the
classification, p-value, significance, and chi-square exactly. Only wall-clock
timestamps differ between runs.