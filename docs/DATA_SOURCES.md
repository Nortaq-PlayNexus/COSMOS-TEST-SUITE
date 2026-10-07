# Data Sources

## Current status

**No real survey data has been ingested.** Every dataset currently registered is
synthetic and generated locally. EXP-001 has never consumed an observation.

| Dataset | Origin | Type | Availability | URL |
|---|---|---|---|---|
| `sample_galaxy_catalog` | COSMOS-curated | galaxy_catalog | offline | none |
| `sample_cmb_map` | COSMOS-curated | cmb | offline | none |
| `sample_rotation_curves` | COSMOS-curated | rotation_curve | offline | none |

These exist so the pipeline can be exercised and validated without network
access. They are labelled as synthetic in every report they touch.

## Intended primary sources

The specification prioritises primary sources over derivative summaries. When
ingestion is wired up, the intended order is:

| Source | Data | Access |
|---|---|---|
| Planck (ESA) | CMB temperature & polarization maps | ESA archive |
| WMAP (NASA) | CMB maps (legacy, useful for systematics cross-checks) | NASA LAMBDA |
| DESI | BAO, clustering, luminous matter tracers | DESI public data release |
| SDSS | Galaxy clustering, spectroscopic redshifts | SDSS SkyServer |
| Euclid | Weak lensing, galaxy clustering | ESA archive |
| Rubin / LSST | Transient and weak-lensing alerts | IPAC / Rubin archive |
| LIGO / Virgo / KAGRA | Gravitational-wave strain | LIGO/Virgo open data |
| NIST | Reference constants | public |
| NASA ADS, arXiv | Literature metadata | public APIs |

Blogs, aggregator sites, and Wikipedia are **not** acceptable as scientific
evidence. If a number cannot be traced to a primary source, it does not enter
the analysis.

## Adding a dataset

```python
from cosmos.data import DatasetRecord, get_data_manager

get_data_manager().add_dataset(DatasetRecord(
    name="desi_dr1_bao",
    origin="DESI",
    version="DR1",
    description="DESI first data release BAO summary table.",
    data_type="bao",
    availability="online",
    download_url="https://data.example/desi_dr1_bao.csv",
    size_bytes=None,
    metadata={"columns": ["z", "dA", "1/DA", "dz"], "units": "Mpc, h/Mpc"},
))
```

Then:

```bash
cosmos data list
cosmos data download desi_dr1_bao
```

The registry writes `data/manifests/datasets.json`. `raw/` is append-only: a
re-download never overwrites existing bytes, so an analysis run against a
dataset version keeps working after a new release lands.

## Integrity

Every dataset record can carry a checksum. `verify_checksum()` enforces it on
download, so a truncated or substituted file is rejected rather than silently
analysed.

```python
from cosmos.data import verify_checksum
verify_checksum(path, expected="sha256:abc123...")
```

## Offline mode

```bash
cosmos --offline experiment run EXP-001
```

Disables all downloads. Analyses continue against whatever is already local.
This is the default posture for the current implementation: the core analysis
must never depend on network access.

## Attaching a real catalogue to EXP-001

EXP-001's `_prepare_data()` looks for a dataset named `sample_galaxy_catalog`.
To run it on real data, register a catalogue under that name with `x`, `y`,
`z_cart` (Mpc/h, periodic box) and `box` fields, then rerun. The bias is
measured from the data rather than assumed, so no prior knowledge is required.

Data placed anywhere other than `raw/` must be documented with its provenance
before use — what it is, where it came from, what version, and what processing
was applied. See [REPRODUCIBILITY.md](REPRODUCIBILITY.md).