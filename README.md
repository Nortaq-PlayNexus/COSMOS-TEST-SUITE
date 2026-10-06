# COSMOS TEST SUITE

## An Independent Computational Observatory for Testing the Biggest Questions in Cosmology and Fundamental Physics

[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue)

---

### Mission

COSMOS is a **serious, research-grade scientific software platform**. It is NOT a fictional
visualization project, NOT merely a dashboard, and NOT a collection of random astronomy facts.
COSMOS is an actual computational research environment capable of:

- downloading/ingesting public scientific data and papers
- running simulations and statistical analyses
- comparing competing cosmological models
- recording hypotheses and predictions
- generating figures, tables, and reports
- preserving full metadata so every result can be reproduced

### Core Principle

> **DO NOT TRY TO PROVE A THEORY. TRY TO FIND OUT WHETHER THE DATA CAN DISPROVE IT.**

---

## Research Questions

COSMOS investigates some of humanity's biggest questions about the universe, including:

1. Is the universe spatially infinite? Could it have a finite topology?
2. Is the universe homogeneous on sufficiently large scales? Is it isotropic?
3. Is there a preferred cosmic direction?
4. Does dark matter behave like a particle component, or can modified gravity explain observations?
5. Is dark energy actually constant, or is it evolving?
6. What is the Hubble constant, and why do early- and late-universe measurements disagree?
7. Did cosmic inflation occur? What observable signatures did it leave?
8. What happened during the earliest observable phases of the universe? Could a Big Bounce be observationally distinguishable?
9. Could bubble universes (or their collisions) leave observable signatures?
10. Are there structures larger or more unusual than ΛCDM predicts? Are there genuine CMB anomalies?
11. Does General Relativity continue to describe gravity at cosmological scales? Do gravitational waves behave as predicted?
12. Can independent datasets consistently describe the same cosmological model? Where does ΛCDM succeed? Where does it fail?

---

## Scientific Philosophy

COSMOS strictly separates **observation** (what was measured), **inference** (what models suggest),
**hypothesis** (a proposed explanation), and **speculation** (a theoretical possibility without
currently testable evidence). Every result is labeled: *observed / reproduced / statistically
significant / theoretically predicted / speculative / unresolved / contradicted / unsupported /
consistent with existing models*.

Words like "proves" are avoided unless a mathematical proof is literally being discussed.

---

## Architecture

```
COSMOS-TEST-SUITE/
├── cosmos/                  # Core Python package
│   ├── cli/                 # Command-line interface
│   ├── database/            # Research database (SQLite) + provenance graph
│   ├── registry/            # Experiment registry
│   ├── ingestion/           # Paper/dataset ingestion
│   ├── data/                # Dataset registry & management
│   ├── simulations/         # Simulation engine
│   ├── statistics/          # Statistical framework
│   ├── cosmology/           # Cosmological models & calculations
│   ├── anomaly_detection/   # Anomaly engine
│   ├── visualization/       # Scientific figures
│   └── report.py            # Report generation
├── config/                  # YAML configuration
├── data/                    # Downloaded datasets (raw/processed/metadata/manifests)
├── papers/                  # Downloaded papers & metadata
├── experiments/             # EXP001 ... EXP015 -- each a self-contained experiment
├── simulations/             # Simulation outputs
├── reports/                 # Generated reports
├── tests/                   # Automated tests
├── docs/                    # Documentation
└── pyproject.toml           # Project config
```

---

## Installation

```bash
git clone https://github.com/your-org/COSMOS-TEST-SUITE.git
cd COSMOS-TEST-SUITE
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
pip install -e .[dev]
```

Dependencies: `numpy`, `scipy`, `pandas`, `astropy`, `matplotlib`, `plotly`,
`scikit-learn`, `statsmodels`, `xarray`, `h5py`, `pyarrow`, `SQLAlchemy`,
`pydantic`, `PyYAML`, `requests`, `httpx`, `networkx`, `sympy`, `numba`,
`pooch`, `click`, `tqdm`, `rich`, `emcee`, `corner`, `arviz`, `pycosat`, `pytest`.

For CMB analysis, install `healpy` and `NaMaster` separately:

```bash
pip install healpy namaster pymaster
```

---

## CLI Usage

```bash
# Research search
cosmos research search "cosmic topology matched circles Planck"
cosmos papers search "dark energy DESI"
cosmos papers search "Hubble tension distance ladder"

# Data management
cosmos data list
cosmos data download desi
cosmos data download cmb-planck

# Experiments
cosmos experiment list
cosmos experiment status EXP-001
cosmos experiment run EXP-001
cosmos experiment run EXP-008   # Hubble tension

# Simulations
cosmos simulate lcdm
cosmos simulate modified-gravity

# Analysis
cosmos analyze cmb
cosmos analyze galaxy-catalog
cosmos analyze lensing
cosmos analyze gravitational-waves

# Model comparison & reporting
cosmos compare-models
cosmos report EXP-001
cosmos reproduce EXP-001
cosmos verify EXP-001

# Replication
cosmos replicate PAPER-ID
```

---

## Experiment Registry

```
EXP-001  Cosmic web & large-scale structure vs ΛCDM   (FIRST IMPLEMENTATION)
EXP-002  Large-scale isotropy / preferred direction
EXP-003  Homogeneity scale
EXP-004  Cosmic web reconstruction
EXP-005  Dark matter: particle vs modified gravity
EXP-006  Modified gravity (MOND, scalar-tensor)
EXP-007  Dark energy: w, w0-wa, evolving models
EXP-008  Hubble tension
EXP-009  Inflation signatures
EXP-010  CMB anomalies (with look-elsewhere correction)
EXP-011  Multiverse / bubble collision signatures
EXP-012  Cosmic topology (matched circles)
EXP-013  Spatial repetition under various assumptions
EXP-014  Large cosmic structures (superclusters, walls)
EXP-015  General Relativity tests at cosmological scales
EXP-016  Gravitational-wave observations
```

Each experiment is self-contained in `experiments/EXP###/` with:

- `experiment.json` — machine-readable experiment definition (hypothesis, null model,
  competing models, datasets, predictions, tests, falsification conditions, systematics)
- `data/` — processed data (with provenance chain back to raw data)
- `results/` — outputs, figures, posterior distributions
- `report/` — auto-generated Markdown report
- `environment.lock` — exact environment for reproduction
- `reproducibility.md` — exact command needed to reproduce the result

---

## The Anomaly Engine

Every anomaly must pass six validation stages before classification:

1. Statistical test
2. Systematic-error test
3. Simulation test
4. Alternative-analysis test
5. Independent-data test
6. Replication test

And it must survive an automated **"try to kill it"** adversarial stage:

- Is this caused by galactic dust?
- Is survey coverage asymmetric?
- Is the telescope calibration responsible?
- Is there a coordinate-system artifact?
- Does the anomaly disappear with another estimator?
- Does it exist in another dataset?
- Does it occur in simulated ΛCDM universes?
- Was the analysis selected after looking at the data?

Only after surviving all stages is something marked **HIGH PRIORITY ANOMALY**.

---

## Reproducibility

Every experiment is reproducible from a clean environment:

- `environment.lock` — environment lockfile
- `dataset.manifest` — dataset manifest with hashes
- `experiment.json` — experiment configuration
- random seeds, code commit, command used, output hashes

```bash
cosmos reproduce EXP-001   # recreates the published result from scratch
```

---

## Current Status

**This is an early implementation.** The repository contains:

- [x] Project initialization (pyproject.toml, LICENSE, README)
- [x] Directory architecture
- [x] Database schema & provenance graph model
- [x] Experiment registry
- [x] Core statistical framework (sampling, model comparison, Bayesian inference)
- [x] Simulation engine (ΛCDM toy models, CMB realizations)
- [ ] Dataset ingestion (offline mode with curated sample data)
- [ ] CLI (fully wired)
- [ ] Web dashboard
- [ ] EXP-001 ... EXP-016 implementation
- [ ] Automated test suite

The **FIRST REAL EXPERIMENT (EXP-001)** uses only small, curated sample datasets that ship
with the repository so the full pipeline runs without network access. Real data downloads
(`cosmos data download ...`) require internet access.

---

## Documentation

- `docs/INSTALLATION.md` — detailed installation instructions
- `docs/ARCHITECTURE.md` — system architecture
- `docs/SCIENTIFIC_METHOD.md` — scientific methodology
- `docs/DATA_SOURCES.md` — data sources and availability
- `docs/EXPERIMENTS.md` — experiment specifications
- `docs/STATISTICS.md` — statistical methods
- `docs/SIMULATIONS.md` — simulation engine
- `docs/REPRODUCIBILITY.md` — reproducibility protocol
- `docs/CLI.md` — CLI reference
- `docs/CONTRIBUTING.md` — how to contribute
- `docs/GLOSSARY.md` — plain-English glossary

---

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0). See LICENSE.

## Citation

COSMOS Test Suite (2025). An Independent Computational Observatory for Testing the Biggest
Questions in Cosmology and Fundamental Physics. Available at: https://github.com/your-org/COSMOS-TEST-SUITE
