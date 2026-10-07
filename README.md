# COSMOS TEST SUITE

## An Independent Computational Observatory for Testing the Biggest Questions in Cosmology and Fundamental Physics

> **Do not try to prove a theory. Try to find out whether the data can disprove it.**

---

## Status: early-stage framework — read this first

This is an **honest statement of what exists**, not marketing.

| | |
|---|---|
| Experiments defined | 16 |
| Experiments implemented | **1** (EXP-001) |
| Real astronomical data ingested | **none** |
| Research questions answered | **0 of 35** |
| Tests | 188, passing from a clean clone |

**No conclusion has been drawn about the physical universe.** EXP-001 has only
ever consumed synthetic data. It answers a question about itself — *does this
pipeline correctly recover a ΛCDM signal it was given?* — and the answer is
yes, which is what makes it useful as validation before the instrument is
pointed at real data.

Every one of the 35 research questions in the specification remains open.

What *is* finished: the statistical framework, the simulation engine, the
experiment discipline, the provenance and reproducibility machinery, and one
experiment that exercises all of it end to end.

---

## What makes this different

Most analysis code will happily report the most interesting number it finds.
This platform is built to refuse to.

**Pre-registration.** The analysis plan is written before the data are touched.
Enforced by call order, not by convention — a test asserts the ordering.

**Injection and recovery.** Before interpreting any signal, the pipeline plants
a known one and confirms it would have been found. Without this, a null result
is indistinguishable from an instrument that does not work. The false-positive
rate is measured on noise-only realisations.

**Adversarial review.** Every result is attacked before it is reported, with
actual computations rather than a checklist. In the committed EXP-001 run the
verdict is `survived: False`, because the highest-`k` bin carries 69% of the
chi-square. That is reported, not buried.

**Monte Carlo over analytic p-values.** Per-bin Poisson errors ignore the
sampling variance of a single realisation, which for one 400 Mpc/h box dwarfs
the Poisson term. In the committed run the naive chi-square gives p = 0.0 while
the Monte Carlo gives p = 0.295. The naive one is wrong, and the framework is
built to surface exactly that.

**"UNKNOWN" is a valid result.** `NOT_TESTABLE`, `INSUFFICIENT_DATA`, and
`INCONCLUSIVE` are outcomes, not errors. A pipeline that cannot answer says so
and says why.

**Unquantified systematics are declared.** Tabulated with a quantified flag; the
report states the significance is an upper bound on the evidence.

**"Proves" is a banned word.** Asserted by test against the generated report.

---

## Quick start

```bash
git clone https://github.com/<your-org>/COSMOS-TEST-SUITE.git
cd COSMOS-TEST-SUITE

python -m venv .venv
.venv\Scripts\activate          # Windows; `source .venv/bin/activate` elsewhere

pip install -e ".[dev]"

python -m pytest tests/ -q      # 188 passed
python -m cosmos experiment run EXP-001
```

No network access needed. See [docs/INSTALLATION.md](docs/INSTALLATION.md).

---

## The first experiment

**EXP-001 — Is the large-scale universe consistent with ΛCDM?**

```bash
python -m cosmos experiment run EXP-001 --seed 42
python -m cosmos experiment run EXP-001 --dry-run   # print the plan first
```

Pipeline: ingest catalogue → measure P(k) via FFT → generate σ8-normalised BBKS
prediction → measure the bias from the data → χ² goodness-of-fit → Monte Carlo
calibration → injection-and-recovery → adversarial review → classify.

Committed result, from synthetic data:

```
classification : consistent_with_standard_model
p-value        : 0.295   (0.54 sigma)
injection      : detected, false-positive rate 0.016
adversarial    : survived = False  (single-bin dominance at high k)
```

Outputs in `experiments/EXP-001/`: `report/report_EXP-001.md`,
`results/result.json`, `results/analysis.json`, `reproducibility/`.

---

## CLI

```bash
cosmos experiment list                    # all 16, with priority scores
cosmos experiment run EXP-001 --seed 42   # execute
cosmos data list                          # datasets
cosmos simulate lcdm --nside 32           # simulations
cosmos report generate EXP-001
cosmos reproduce run EXP-001              # verify reproducibility
```

Full reference: [docs/CLI.md](docs/CLI.md).

---

## Research questions

Defined in the registry, none yet answered:

| | |
|---|---|
| Is the universe spatially infinite? | Could it have finite topology? |
| Is it homogeneous on large scales? | Is it isotropic? |
| Is there a preferred direction? | Does dark matter behave like a particle? |
| Could modified gravity explain it instead? | Is dark energy constant? |
| Is dark energy evolving? | What is H0? |
| Why do early and late H0 disagree? | Did inflation occur? |
| What signatures did inflation leave? | What happened earliest? |
| Could a Big Bounce be distinguishable? | Do bubble collisions leave CMB traces? |
| Could space contain repetitions? | Are structures larger than ΛCDM predicts? |
| Are there genuine CMB anomalies? | Are fundamental symmetries violated? |
| Does GR hold at cosmological scales? | Do gravitational waves behave as predicted? |
| Can independent datasets agree? | Where does ΛCDM succeed, and where does it fail? |

---

## Architecture

```
cosmos/
  config.py         settings, path resolution, classification vocabulary
  database/         hypothesis graph + provenance chain (ORM)
  statistics/       model comparison, tests, Monte Carlo, look-elsewhere
  simulations/      cosmology calculator, GRFs, mock catalogues, P(k)
  registry/         16 experiments, priority scoring, definitions
  experiments/      ExperimentRunner framework + EXP-001
  data/             dataset registry, downloads, offline mode
  reports.py        report rendering from a result payload
  cli/              command-line interface
experiments/EXP-001/  results, report, reproducibility package
docs/                 documentation
tests/                188 tests
```

Experiment runs are a fixed pipeline. Two stages a normal analysis skips are
made impossible to skip here:

```
setup → register_analysis_plan → prepare_data → predict → simulate_null
      → analyse → assess_systematics → adversarial → classify
      → record → reproduce_package → report
       └── before any data ──┘              └── attacks the result ──┘
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Documentation

| | |
|---|---|
| [INSTALLATION](docs/INSTALLATION.md) | Setup, requirements, troubleshooting |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Modules, schema, data layout |
| [SCIENTIFIC_METHOD](docs/SCIENTIFIC_METHOD.md) | Pre-registration, injection-recovery, adversarial review |
| [DATA_SOURCES](docs/DATA_SOURCES.md) | Datasets, provenance, intended primary sources |
| [EXPERIMENTS](docs/EXPERIMENTS.md) | The 16 experiments, how to implement one |
| [STATISTICS](docs/STATISTICS.md) | Methods, look-elsewhere, significance thresholds |
| [SIMULATIONS](docs/SIMULATIONS.md) | Cosmology, GRFs, mock catalogues, P(k) conventions |
| [REPRODUCIBILITY](docs/REPRODUCIBILITY.md) | Determinism, artifacts, provenance chain |
| [SCIENCE_VALIDATION](docs/SCIENCE_VALIDATION.md) | Internal vs external validation |
| [CLI](docs/CLI.md) | Full command reference |
| [CONTRIBUTING](docs/CONTRIBUTING.md) | Style, testing philosophy, non-negotiable rules |
| [GLOSSARY](docs/GLOSSARY.md) | Plain-language definitions of every term |

---

## Requirements

Python ≥ 3.12. `numpy`, `scipy`, `pandas`, `astropy`, `matplotlib`, `plotly`,
`scikit-learn`, `statsmodels`, `xarray`, `h5py`, `SQLAlchemy`, `pydantic`,
`pyyaml`, `requests`, `networkx`, `sympy`, `numba`, `emcee`, `corner`, `arviz`,
`pytest`. No GPU. No network required.

---

## License

GPL-3.0-only. See [LICENSE](LICENSE).

---

## Before you publish this

Repository-wide placeholders to replace:

- `pyproject.toml` → `authors = [{ name = "...", email = "..." }]`
- `README.md` → the three `<your-org>` URLs in clone and citation
- Git commit author (`git config user.name` / `user.email`)