# Data Sources

## Current status

**No real survey data has been ingested.** Every dataset registered for analysis is
synthetic and generated locally. EXP-001 has never consumed an observation.

| Dataset | Origin | Type | Availability | URL |
|---|---|---|---|---|
| `sample_galaxy_catalog` | COSMOS-curated | galaxy_catalog | offline | none |
| `sample_cmb_map` | COSMOS-curated | cmb | offline | none |
| `sample_rotation_curves` | COSMOS-curated | rotation_curve | offline | none |

These exist so the pipeline can be exercised and validated without network
access. They are labelled as synthetic in every report they touch.

### What *is* real: the literature corpus

`papers/metadata/corpus.json` holds **86 records retrieved from the live arXiv
API**, covering 1991–2026, 58 of them with a DOI. Every record carries its
arXiv ID, authors, publication date, verbatim abstract, and the query and
timestamp that retrieved it.

```bash
cosmos papers stats
cosmos papers search "cosmic topology"
python -m cosmos.ingestion.seed          # grow it
```

These are genuine primary-source records, not fixtures. Section 6 of the
specification asks for exactly this.

### What is *not* real: survey data

Reachability was probed from the development environment:

| Source | Reachable |
|---|---|
| arXiv API | yes |
| NASA LAMBDA (root) | yes, but Planck data paths return 404 |
| ESA Cosmos (Planck) | yes |
| DESI portal | yes |
| ESA Euclid | yes |
| SDSS SkyServer | **blocked** |
| SDSS DR12 BOSS data release | **blocked (HTTP 504)** |
| LIGO open data | **blocked** |

So the galaxy power spectra, gravitational-wave strain, and CMB spectra that
would let EXP-001 run on real observations are **unavailable**. Per §60 of the
specification these are marked unavailable rather than substituted with
invented numbers. `docs/SCIENCE_VALIDATION.md` records that no external
validation has been performed for the same reason.

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