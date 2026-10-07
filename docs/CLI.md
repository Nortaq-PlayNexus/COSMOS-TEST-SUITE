# CLI Reference

```bash
python -m cosmos <command> [options]
# or, after `pip install -e .`:
cosmos <command> [options]
```

## Global options

| Option | Effect |
|---|---|
| `-d, --database URL` | Use a specific database (default `sqlite:///cosmos.db`) |
| `--offline` | Disable all data downloads |
| `-v, --verbose` | Verbose output |
| `--help` | Command help |

```bash
cosmos --offline experiment run EXP-001
cosmos -d sqlite:///scratch.db experiment list
```

## Full command tree

```
analyze cmb                          analyze galaxy-catalog       analyze rotation-curve
compare-models                      data download                data list
experiment delete                   experiment list              experiment run
experiment status                   papers ingest                papers search
papers stats                        replicate                    report generate
reproduce run                       research search              simulate bubble-collision
simulate lcdm                       simulate mock-galaxy         simulate topology
verify                               version
```

## version

```bash
cosmos version
```

## experiment list

```bash
cosmos experiment list
cosmos experiment list --status completed
```

```
exp_id     name                                          status           score
--------------------------------------------------------------------------------
EXP-001    Cosmic web and large-scale structure vs Lamb  completed        0.84
EXP-002    Large-scale isotropy and preferred direction  not_started      0.86
...
NEXT IN LINE: EXP-008 - Hubble tension analysis
```

Status is read live from the database, so a completed run shows as completed.

## experiment status

```bash
cosmos experiment status EXP-001
```

Prints name, status, priority score, timestamps, hypothesis, falsification
condition, and registered datasets.

## experiment run

```bash
cosmos experiment run EXP-001
cosmos experiment run EXP-001 --seed 777
cosmos experiment run EXP-001 --dry-run
```

| Option | Default | Effect |
|---|---|---|
| `--seed` | 42 | Random seed; fully determines the run |
| `--dry-run` | off | Print the pre-registered pipeline without executing |

`--dry-run` is worth reading before a long run: it prints the analysis plan
exactly as it will be registered.

Exit codes: `0` success, `2` experiment not implemented.

## data list / data download

```bash
cosmos data list
cosmos data list --type cmb
cosmos data list --status offline
cosmos data download desi_dr1_bao
cosmos data download desi_dr1_bao --url https://...
```

## simulate

```bash
cosmos simulate lcdm --nside 32 --seed 42
cosmos simulate topology --L 500
cosmos simulate bubble-collision --resolution 64 --r0 0.15
cosmos simulate mock-galaxy --n-galaxies 5000 --z-max 0.8
```

## analyze

```bash
cosmos analyze cmb --data sample_cmb_map
cosmos analyze galaxy-catalog --data sample_galaxy_catalog
cosmos analyze rotation-curve --data sample_rotation_curves
```

## report / reproduce / verify

```bash
cosmos report generate EXP-001
cosmos reproduce run EXP-001
cosmos verify EXP-001
```

## research / papers

```bash
cosmos research search "cosmic topology"
cosmos papers search "Hubble tension distance ladder"
cosmos papers search "dark energy" --doi        # only records with a DOI
cosmos papers search "cosmic topology" --full    # include abstracts
cosmos papers stats                             # corpus composition
cosmos papers ingest                            # grow the corpus from arXiv
```

These query the local corpus of 86 records ingested from the live arXiv API.
All search terms must match (AND semantics).

A zero-result search says the **local index** has no match. It does not say no
such paper exists, and the CLI says so explicitly.

## compare-models / replicate

```bash
cosmos compare-models --data sample_rotation_curves
cosmos replicate PAPER-ID
```

Also placeholders. `replicate` is the intended entry point for independently
reproducing a published analysis from its methodology.

## Literature ingestion

`cosmos papers ingest` queries the arXiv API, one request per research
question in the registry, honouring the API's three-second rate limit.
Responses are cached under `papers/cache/`, so re-running is cheap and
offline mode works from cache.

```bash
cosmos papers ingest                    # fill gaps in the corpus
cosmos papers ingest --offline          # cached responses only
cosmos papers ingest --max-results 10
```

Ingestion never invents a citation. Every record carries the arXiv ID the API
returned, the query that found it, and a retrieval timestamp. A retrieval
failure is reported as a failure — never as "no such paper exists".

Numbers are deliberately **not** extracted from abstracts into results tables.
Scraping "67.4 ± 0.5" out of prose has no error detection, so abstracts are
stored verbatim for later verified extraction. That keeps §2's separation of
observation from inference intact.

## Scripts and pipelines

Because unimplemented experiments exit non-zero, a pipeline can distinguish
"not built" from "ran and found nothing":

```bash
set -e
for exp in EXP-001 EXP-002; do
  if cosmos experiment run "$exp"; then
    echo "$exp complete"
  else
    echo "$exp skipped (exit $?)"
  fi
done
```