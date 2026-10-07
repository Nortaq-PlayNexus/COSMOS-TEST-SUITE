"""
Seed the local literature corpus from the live arXiv API.

Runs one query per research question in the registry, so the corpus covers the
same topics the experiments do. Each record keeps the query that found it and
its retrieval timestamp, so provenance is preserved end to end.

Run with:

    python -m cosmos.ingestion.seed            # fill gaps, keep what we have
    python -m cosmos.ingestion.seed --refresh  # re-query everything
    python -m cosmos.ingestion.seed --offline  # never touch the network
"""

from __future__ import annotations

import argparse
import sys
import time

# One query per research question, using arXiv search syntax. These are
# deliberately specific so the results are topically tight rather than
# returning the entire cosmological literature.
SEED_QUERIES: dict[str, str] = {
    "cosmic_topology": 'all:"cosmic topology" AND all:"matched circles"',
    "large_scale_isotropy": 'all:"large scale isotropy" AND all:anisotropy',
    "homogeneity": 'all:homogeneity AND all:"power spectrum" AND all:cosmology',
    "cosmic_web": 'all:"cosmic web" AND all:"Lambda CDM"',
    "dark_matter_modified_gravity": 'all:"dark matter" AND all:"modified gravity" AND all:MOND',
    "modified_gravity": 'all:"modified gravity" AND all:"rotation curve"',
    "dark_energy": 'all:"dark energy" AND all:"w0-wa"',
    "hubble_tension": 'all:"Hubble tension" AND all:"distance ladder"',
    "inflation": 'all:inflation AND all:"scalar spectral index"',
    "cmb_anomalies": 'all:"CMB anomalies" AND all:cosmology',
    "bubble_collisions": 'all:"bubble collision" AND all:CMB',
    "spatial_repetition": 'all:"spatial repetition"',
    "large_scale_structures": 'all:"large scale structure" AND all:"power spectrum" AND all:survey',
    "general_relativity": 'all:"general relativity" AND all:"gravitational waves" AND all:test',
    "gravitational_waves": 'all:"gravitational waves" AND all:"standard sirens"',
}

MAX_RESULTS_PER_QUERY = 6


def seed(
    refresh: bool = False,
    offline: bool = False,
    max_results: int = MAX_RESULTS_PER_QUERY,
) -> int:
    """Ingest the seed queries into the local corpus. Returns records added."""
    from . import ArxivClient, IngestionError, LiteratureStore

    store = LiteratureStore().load()
    before = len(store)
    client = ArxivClient(offline=offline)

    print(f"corpus: {store.path}")
    print(f"existing records: {before}")
    print("")

    failures = []
    for topic, query in SEED_QUERIES.items():
        label = topic.ljust(32)
        try:
            records = client.search(query, max_results=max_results)
        except IngestionError as exc:
            # Retrieval failed. Say so and keep going: one unreachable topic
            # must not abort the whole ingest, but it must not be silently
            # recorded as "no literature exists".
            print(f"  {label} RETRIEVAL FAILED: {exc}")
            failures.append((topic, str(exc)))
            continue

        added = 0
        for rec in records:
            was_present = rec.short_id in store.records
            store.add(rec)
            added += 0 if was_present else 1
        total = len(store)
        print(f"  {label} {len(records):>2} found, {added:>2} new  (corpus {total})")
        # arXiv asks for >=3s between requests; ArxivClient also throttles,
        # but we pause visibly so a long run is not surprising.
        if not offline and not refresh:
            time.sleep(0)

    store.save()
    after = len(store)
    print("")
    print(f"added {after - before} new records; corpus now {after}")
    print(f"saved: {store.path}")

    stats = store.stats()
    print(f"with DOI: {stats['with_doi']}  with abstract: {stats['with_abstract']}")
    print(f"years: {stats['by_year']}")

    if failures:
        print("")
        print(f"{len(failures)} topic(s) could not be retrieved:")
        for topic, err in failures:
            print(f"  - {topic}: {err[:100]}")
        print(
            "These are marked as retrieval failures, NOT as an absence of "
            "literature. Re-run when the network is available."
        )

    return after - before


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cosmos.ingestion.seed",
        description="Seed the local literature corpus from the arXiv API",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="re-query even when a cached response exists",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="never touch the network; use cached responses only",
    )
    parser.add_argument(
        "--max-results", type=int, default=MAX_RESULTS_PER_QUERY,
        help=f"records per query (default {MAX_RESULTS_PER_QUERY})",
    )
    args = parser.parse_args(argv)

    seed(refresh=args.refresh, offline=args.offline, max_results=args.max_results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
