#!/usr/bin/env python3
"""Create the Zenodo deposit for COSMOS Test Suite.

Draft-first by default. The deposit is created and the archive uploaded, but
nothing is published unless --publish is passed, because publishing mints an
immutable DOI that cannot be undone.

Two things this script will not do, deliberately:

  * It never deletes a deposit. Every deposit is a real record with a real ID;
    discarding one is a decision to make out loud, not automatically.

  * It never publishes without --publish.

The token is read from ZENODO_ACCESS_TOKEN if set, otherwise from the token
file used by the other project on this machine. It is never printed, never
logged, and never written into the deposit metadata.

Zenodo's API requires every metadata field nested under a `metadata` key. A flat
payload is rejected with "Unknown field" for every key at once, which reads like
the API being broken rather than the payload being wrong.

Note on subjects: the previous deposit in this account had `subjects` supplied,
accepted, and silently not persisted. They are omitted here and must be set in
the web form if wanted.

Usage:
    python tools/upload_to_zenodo.py --metadata docs/ZENODO_METADATA.json \\
        --description docs/ZENODO_DESCRIPTION.md \\
        --archive ../cosmos-test-suite-0.1.0.tar.gz
    python tools/upload_to_zenodo.py ... --publish
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://zenodo.org/api"
FALLBACK_TOKEN_FILE = (
    Path.home() / "ScientificDiscoveryLab" / "zenodo" / ".zenodo_token"
)


def token() -> str:
    """Read the access token from the environment, or the shared token file."""
    env = os.environ.get("ZENODO_ACCESS_TOKEN")
    if env and env.strip():
        return env.strip()
    if FALLBACK_TOKEN_FILE.is_file():
        found = FALLBACK_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if found:
            return found
    sys.exit(
        "ERROR: no Zenodo token.\n"
        "Set ZENODO_ACCESS_TOKEN, or create one at\n"
        "  https://zenodo.org/account/settings/applications/tokens/new\n"
        "For this deposit the scope needs zenodo:zenodo_deposit."
    )


def request(
    method: str,
    url: str,
    tok: str,
    body: bytes | None = None,
    content_type: str | None = None,
) -> dict:
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {tok}")
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        sys.exit(f"HTTP {exc.code} on {method} {url}\n{detail}")
    except urllib.error.URLError as exc:
        sys.exit(f"network error: {exc}")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build_metadata(meta: dict, description: str) -> dict:
    """Wrap the local metadata in the shape the API accepts.

    Optional blocks are included only when the local metadata defines them, so a
    field Zenodo rejects costs nothing to leave out. A rejected PUT would discard
    the entire update, including the fields that did validate.
    """
    payload: dict = {
        "upload_type": meta["upload_type"],
        "title": meta["title"],
        "description": description,
        "version": meta["version"],
        "license": meta["license"],
        "language": meta.get("language", "eng"),
        "creators": [
            {"name": c["name"], "affiliation": c.get("affiliation", "independent")}
            for c in meta["creators"]
        ],
        "keywords": meta["keywords"],
        "related_identifiers": meta.get("related_identifiers", []),
        "notes": meta["notes"],
    }
    if "access_right" in meta:
        payload["access_right"] = meta["access_right"]
    if meta.get("grants"):
        payload["grants"] = meta["grants"]
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata", required=True)
    ap.add_argument("--description", required=True)
    ap.add_argument("--archive", required=True)
    ap.add_argument(
        "--reuse",
        type=int,
        default=None,
        help="resume an existing deposit id instead of creating one. Use after a "
        "partial failure so no deposit is orphaned; never delete a deposit to "
        "recover from one.",
    )
    ap.add_argument(
        "--publish",
        action="store_true",
        help="publish immediately (mints an immutable DOI)",
    )
    args = ap.parse_args()

    tok = token()
    meta = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    description = Path(args.description).read_text(encoding="utf-8")
    archive = Path(args.archive).resolve()

    if not archive.is_file():
        sys.exit(f"ERROR: archive not found: {archive}")

    size = archive.stat().st_size
    sha = digest(archive)
    print(f"archive : {archive.name}")
    print(f"bytes   : {size:,}")
    print(f"sha256  : {sha}")

    files_state: list = []
    if args.reuse:
        deposit_id = args.reuse
        print(f"\nreusing deposit {deposit_id}")
    else:
        created = request("POST", f"{BASE}/deposit/depositions", tok,
                          json.dumps({"metadata": {}}).encode(),
                          "application/json")
        deposit_id = created["id"]
        bucket_url = created["links"]["bucket"]
        print(f"\ndeposit created: {deposit_id}")

    state = request("GET", f"{BASE}/deposit/depositions/{deposit_id}", tok)
    bucket_url = state["links"]["bucket"].rstrip("/")

    # The bucket is a PUT target with the filename in the path, not a POST target
    # carrying a JSON map of names to paths. POSTing to the bare bucket returns
    # 405 Method Not Allowed, which reads like a permissions problem rather than
    # a verb mismatch. The bucket accepts only application/octet-stream.
    print("\nuploading...")
    target = f"{bucket_url}/{urllib.parse.quote(archive.name)}"
    uploaded = request("PUT", target, tok, archive.read_bytes(),
                       "application/octet-stream")
    print(f"  file id {uploaded.get('id')}  checksum {uploaded.get('checksum')}")

    payload = {"metadata": build_metadata(meta, description)}
    print("setting metadata...")
    request("PUT", f"{BASE}/deposit/depositions/{deposit_id}", tok,
            json.dumps(payload).encode(), "application/json")

    state = request("GET", f"{BASE}/deposit/depositions/{deposit_id}", tok)
    files_state = [uploaded] if uploaded else []

    print("\n--- deposit state ---")
    print(f"id          : {state['id']}")
    print(f"state       : {state.get('state')}")
    print(f"title       : {state['metadata']['title']}")
    print(f"version     : {state['metadata']['version']}")
    print(f"license     : {state['metadata'].get('license')}")
    print(f"creators    : {[c['name'] for c in state['metadata']['creators']]}")
    print(f"keywords    : {len(state['metadata'].get('keywords', []))}")
    print(f"files       : {[f['key'] for f in files_state]}")
    for f in files_state:
        print(f"  {f['key']}: {f['size']:,} bytes  checksum={f.get('checksum')}")

    if state.get("doi"):
        print(f"doi (draft) : {state['doi']}")

    print(f"\narchive sha256 recorded locally: {sha}")

    if not args.publish:
        print("\nDRAFT ONLY. Nothing published, no DOI minted.")
        print("Review at https://zenodo.org/deposit/" + str(deposit_id))
        print("Publish from that page, or re-run with --publish.")
        return 0

    print("\npublishing...")
    request("POST", f"{BASE}/deposit/depositions/{deposit_id}/actions/publish",
            tok, b"{}", "application/json")
    final = request("GET", f"{BASE}/deposit/depositions/{deposit_id}", tok)
    print(f"state       : {final.get('state')}")
    print(f"DOI         : {final.get('doi')}")
    print(f"concept DOI : {final.get('conceptdoi')}")
    print(f"record      : {final.get('links', {}).get('record_html')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
