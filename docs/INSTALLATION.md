# Installation

## Requirements

- **Python 3.12 or newer** (developed and tested on 3.14.7)
- Allow space for the scientific Python environment; size varies by platform and resolved packages
- No GPU required. Package installation requires network access or a pre-populated wheel cache; the default synthetic workflow runs offline afterward.
- A C compiler may be needed for pycosat when no compatible wheel is available. Use your platform compiler and matching Python development headers.

## Quick start

```bash
git clone https://github.com/Nortaq-PlayNexus/COSMOS-TEST-SUITE.git
cd COSMOS-TEST-SUITE

python -m venv .venv
```

Activate it:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (cmd)
.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate
```

Then install:

```bash
pip install -e .
```

For development (tests, linting, type checking):

```bash
pip install -e ".[dev]"
```

## Verify the installation

```bash
python -m cosmos version
python -m pytest tests/ -q
```

Use the actual test output, rather than a fixed count, to assess your checkout. See the [dated verification record](VERIFICATION_2026-11-10.md). Diagnose failures from their tracebacks; do not assume every failure is a missing package.

If a pycosat source build reports a missing compiler, install a compiler or select one that exists. For example, on a Linux system with GCC installed: `CC=gcc CXX=g++ python -m pip install -e ".[dev]"`. This is platform-specific, not required on every machine.

## Running the first experiment

```bash
python -m cosmos experiment run EXP-001
```

This writes to `experiments/EXP-001/`:

| Path | Contents |
|---|---|
| `report/report_EXP-001.md` | Human-readable report with all required sections |
| `results/result.json` | Machine-readable result, analysis, systematics, provenance |
| `results/analysis.json` | Statistical output of each stage |
| `reproducibility/` | `environment.lock`, `experiment.lock`, `data.manifest`, `README.md` |

## Optional: CMB tooling

The default workflow does not need these. They are only required for full-sky
CMB analyses (EX-010 anomalies, EXP-012 topology):

```bash
pip install healpy pymaster
```

## Installing as a command

Installing with `pip install -e .` puts a `cosmos` executable on your path:

```bash
cosmos version
cosmos experiment list
```

If you prefer not to install, every command works as `python -m cosmos ...`.

## Offline operation

The platform is designed to run with no network access. The default workflow
uses only synthetic data generated locally.

```bash
python -m cosmos --offline experiment run EXP-001
```

To attach real data later, see [DATA_SOURCES.md](DATA_SOURCES.md).

## Troubleshooting

**`ModuleNotFoundError: No module named 'cosmos'`**
Run from the repository root, or set `PYTHONPATH` to it, or install the package.

**`AttributeError: 'Settings' object has no attribute ...` on a very new NumPy**
Pin to a known-good set: `pip install "numpy>=2.0" "scipy>=1.14"`.

**Unicode errors when writing reports**
The codebase writes all text files as UTF-8 explicitly. If you have overridden
that, restore UTF-8 — the reports contain Greek letters and the symbol Λ.

**Tests fail on `test_anisotropy_direction_is_respected`**
Cosmological realisations depend on the RNG. Confirm you have not modified
`numpy.random` seeding or the test's fixed seed of 12.