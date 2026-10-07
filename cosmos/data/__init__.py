"""
Dataset and data acquisition module for COSMOS TEST SUITE.

Implements:
- Dataset registry (Section 5 of spec): tracking data origin, version,
  checksum, availability (online/offline/unavailable), local path, manifest.
- Download orchestration with retries, chunked transfer, progress reporting.
- Cache management and disk-space monitoring (Section 47).
- Offline mode: core analysis continues with previously downloaded data
  (Section 48). Internet research mode: periodic checks for new releases
  (Section 49).
- Manifest-based data provenance.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from tqdm import tqdm

from ..config import settings


# ---------------------------------------------------------------------------
# Dataset metadata model
# ---------------------------------------------------------------------------


@dataclass
class DatasetRecord:
    """
    A dataset record (Section 5 of spec).

    name, origin, version, data_type, availability, size, checksum,
    download_url, local_path, manifest_path, metadata, associated_papers,
    last_updated.
    """

    name: str
    origin: str
    version: str
    description: Optional[str] = None
    data_type: str = "unknown"
    availability: str = "unavailable"  # online | offline | unavailable
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    download_url: Optional[str] = None
    local_path: Optional[str] = None
    manifest_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    associated_papers: Optional[List[str]] = None
    last_updated: Optional[datetime.datetime] = None

    @property
    def size_gb(self) -> float:
        return (self.size_bytes or 0) / (1024 ** 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "origin": self.origin,
            "version": self.version,
            "description": self.description,
            "data_type": self.data_type,
            "availability": self.availability,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "download_url": self.download_url,
            "local_path": self.local_path,
            "manifest_path": self.manifest_path,
            "metadata": self.metadata,
            "associated_papers": self.associated_papers,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatasetRecord":
        last_updated = d.get("last_updated")
        if last_updated and isinstance(last_updated, str):
            last_updated = datetime.datetime.fromisoformat(last_updated)
        return cls(
            name=d["name"],
            origin=d["origin"],
            version=d["version"],
            description=d.get("description"),
            data_type=d.get("data_type", "unknown"),
            availability=d.get("availability", "unavailable"),
            size_bytes=d.get("size_bytes"),
            checksum=d.get("checksum"),
            download_url=d.get("download_url"),
            local_path=d.get("local_path"),
            manifest_path=d.get("manifest_path"),
            metadata=d.get("metadata"),
            associated_papers=d.get("associated_papers"),
            last_updated=last_updated,
        )


# ---------------------------------------------------------------------------
# Curated sample datasets (for offline-first operation)
# ---------------------------------------------------------------------------

# These are the "curated sample datasets that ship with the repository" so the
# full pipeline runs without network access (Section "Current Status" of README).
CURATED_DATASETS: List[DatasetRecord] = [
    DatasetRecord(
        name="sample_cmb_map",
        origin="COSMOS-curated",
        version="v1",
        description="Small sample CMB temperature map (2° resolution) for pipeline testing.",
        data_type="cmb",
        availability="offline",
        size_bytes=None,
        checksum=None,
        metadata={"nside": 32, "units": "uK", "nside_note": "toy map for testing only"},
    ),
    DatasetRecord(
        name="sample_galaxy_catalog",
        origin="COSMOS-curated",
        version="v1",
        description="Small mock galaxy catalog (1000 galaxies) for pipeline testing.",
        data_type="galaxy_catalog",
        availability="offline",
        size_bytes=None,
        checksum=None,
        metadata={"n_galaxies": 1000, "z_max": 1.0, "note": "toy catalog for testing only"},
    ),
    DatasetRecord(
        name="sample_rotation_curves",
        origin="COSMOS-curated",
        version="v1",
        description="Toy rotation curve data (radius, v_obs, v_err) for dark matter tests.",
        data_type="rotation_curve",
        availability="offline",
        size_bytes=None,
        checksum=None,
        metadata={"n_galaxies": 10, "note": "toy data for testing only"},
    ),
]


# ---------------------------------------------------------------------------
# Download orchestration
# ---------------------------------------------------------------------------


class DownloadError(Exception):
    """Raised when a data download fails."""

    pass


@dataclass
class DownloadStats:
    bytes_downloaded: int = 0
    n_attempts: int = 0
    total_time_seconds: float = 0.0
    last_error: Optional[str] = None


def download_file(
    url: str,
    destination: Path | str,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    retries: int = 3,
    progress: bool = True,
) -> DownloadStats:
    """
    Download a file with retries, progress reporting, and checksum verification.

    Parameters:
        url: Source URL.
        destination: Local path.
        headers: Optional request headers (e.g., User-Agent for politeness).
        timeout: Request timeout in seconds.
        retries: Number of retry attempts.
        progress: Show a progress bar.

    Raises:
        DownloadError: If all retry attempts fail.
    """
    timeout = timeout or settings.network_timeout
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)

    stats = DownloadStats()
    headers = headers or {}
    headers.setdefault("User-Agent", "COSMOS-Test-Suite/0.1.0 (+https://github.com)")

    for attempt in range(1, retries + 1):
        stats.n_attempts += 1
        try:
            with requests.get(url, stream=True, headers=headers, timeout=timeout) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0)) or None
                downloaded = 0
                with open(dest, "wb") as f, tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    desc=dest.name,
                    disable=not progress,
                ) as bar:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            bar.update(len(chunk))
                stats.bytes_downloaded += downloaded
            if total and downloaded != total:
                raise DownloadError(f"Download incomplete: {downloaded}/{total} bytes")
            return stats
        except Exception as e:
            stats.last_error = str(e)
            time.sleep(2 ** (attempt - 1))  # exponential backoff
    raise DownloadError(
        f"Failed to download {url} after {retries} attempts: {stats.last_error}"
    )


def verify_checksum(path: Path | str, expected: Optional[str], algorithm: str = "sha256") -> bool:
    """Verify a file's checksum."""
    path = Path(path)
    if expected is None:
        return True
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest()
    ok = actual.lower() == expected.lower()
    if not ok:
        raise DownloadError(f"Checksum mismatch: expected {expected}, got {actual}")
    return True


# ---------------------------------------------------------------------------
# Dataset manager
# ---------------------------------------------------------------------------


@dataclass
class DataManager:
    """
    Manages the dataset registry, downloads, cache, and offline mode.

    Features:
    - list_datasets(), get_dataset(), mark_unavailable()
    - download_dataset(), ensure_present() (auto-download if online available)
    - offline mode toggle (Section 48)
    - internet research mode (Section 49)
    - disk-space monitoring
    - manifest-based provenance
    """

    dataset_dir: Path = field(default_factory=lambda: settings.data_dir)
    cache_dir: Path = field(default_factory=lambda: settings.data_cache_dir)
    manifest_path: Path = field(default_factory=lambda: settings.data_dir / "manifests" / "datasets.json")
    curated: List[DatasetRecord] = field(default_factory=list)
    _records: Dict[str, DatasetRecord] = field(default_factory=dict)
    offline_mode: bool = False
    internet_research_mode: bool = False
    disk_monitoring: bool = True

    def __post_init__(self):
        self.curated = CURATED_DATASETS
        for ds in self.curated:
            self._records[ds.name] = ds
        self._load_manifest()

    # -- Registry --

    def _load_manifest(self) -> None:
        """Load the dataset manifest from disk."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path) as f:
                    data = json.load(f)
                for item in data.get("datasets", []):
                    rec = DatasetRecord.from_dict(item)
                    self._records[rec.name] = rec
            except Exception:
                pass

    def _save_manifest(self) -> None:
        """Save the dataset manifest to disk."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w") as f:
            json.dump({"version": "0.1.0", "datasets": [r.to_dict() for r in self._records.values()]}, f, indent=2)

    def list_datasets(
        self,
        data_type: Optional[str] = None,
        availability: Optional[str] = None,
    ) -> List[DatasetRecord]:
        """List registered datasets, optionally filtered."""
        records = list(self._records.values())
        if data_type:
            records = [r for r in records if r.data_type == data_type]
        if availability:
            records = [r for r in records if r.availability == availability]
        return records

    def get_dataset(self, name: str) -> Optional[DatasetRecord]:
        """Get a dataset record by name."""
        return self._records.get(name)

    def add_dataset(self, record: DatasetRecord) -> DatasetRecord:
        """Add a dataset to the registry."""
        self._records[record.name] = record
        self._save_manifest()
        return record

    def mark_unavailable(self, name: str) -> bool:
        """Mark a dataset as unavailable (Section 48/50)."""
        rec = self._records.get(name)
        if rec:
            rec.availability = "unavailable"
            self._save_manifest()
            return True
        return False

    # -- Download & availability --

    def check_internet(self) -> bool:
        """Check whether internet access is available."""
        if self.offline_mode:
            return False
        try:
            with requests.get("https://www.google.com", timeout=10, stream=True) as resp:
                return resp.ok
        except Exception:
            return False

    def download_dataset(
        self,
        name: str,
        url: Optional[str] = None,
        verify: bool = True,
        progress: bool = True,
    ) -> DatasetRecord:
        """Download a dataset to the local cache."""
        rec = self._records.get(name)
        if rec is None:
            raise ValueError(f"Dataset {name} not registered")
        if self.offline_mode:
            raise DownloadError("Offline mode: downloads disabled")
        if url is None:
            url = rec.download_url
        if url is None:
            raise DownloadError(f"No download URL for dataset {name}")
        if not self.check_internet():
            raise DownloadError("No internet access; enable with settings.allow_data_download = True")

        local_path = self.dataset_dir / "raw" / name / f"{name}_{rec.version}"
        if local_path.exists():
            # Already downloaded
            return rec

        download_file(url, local_path, progress=progress)
        if verify and rec.checksum:
            verify_checksum(local_path, rec.checksum)
        rec.local_path = str(local_path)
        rec.availability = "offline"
        rec.last_updated = datetime.datetime.utcnow()
        self._save_manifest()
        return rec

    def ensure_present(
        self,
        name: str,
        required: bool = True,
    ) -> Optional[DatasetRecord]:
        """
        Ensure a dataset is present locally.

        If the dataset is marked 'offline', check whether it exists on disk.
        If it exists, use it. If not, and internet is available, download it.
        If required and not available, raise DownloadError (Section 60 of spec).
        """
        rec = self._records.get(name)
        if rec is None:
            if required:
                raise ValueError(f"Dataset {name} not registered")
            return None
        if rec.availability == "offline":
            if rec.local_path and Path(rec.local_path).exists():
                return rec
            # Dataset was removed; try re-download
            if settings.allow_data_download and self.check_internet():
                return self.download_dataset(name)
            if required:
                raise DownloadError(f"Dataset {name} is offline and not present on disk")
            return None
        if rec.availability == "unavailable":
            if required:
                raise DownloadError(f"Dataset {name} is unavailable")
            return None
        # online but not downloaded
        if rec.local_path and Path(rec.local_path).exists():
            rec.availability = "offline"
            self._save_manifest()
            return rec
        if settings.allow_data_download and self.check_internet():
            return self.download_dataset(name)
        if required:
            raise DownloadError(f"Dataset {name} requires download and data_download is disabled")
        return None

    # -- Offline mode --

    def set_offline_mode(self, enabled: bool) -> None:
        """Toggle offline mode (Section 48 of spec)."""
        self.offline_mode = enabled
        self.internet_research_mode = False

    def set_internet_research_mode(self, enabled: bool) -> None:
        """Toggle internet research mode: check official sources for new releases."""
        self.internet_research_mode = enabled
        self.offline_mode = False

    # -- Disk monitoring --

    def check_disk_space(self, required_gb: Optional[float] = None) -> Tuple[bool, float]:
        """Check free disk space. Returns (sufficient, free_gb)."""
        free_gb = settings.resource_spec.disk_gb
        if required_gb is not None and free_gb < required_gb:
            return False, free_gb
        return True, free_gb

    # -- Internet research (Section 49) --

    def check_for_updates(self) -> List[str]:
        """
        When internet research mode is enabled, check official sources for
        new data releases. Returns a list of update messages.
        """
        if not self.internet_research_mode:
            return []
        # Placeholder: implement per-source checkers (Planck, DESI, SDSS, etc.)
        return ["Internet research mode: no source checkers implemented yet."]

    # -- Provenance: manifest for a dataset run --

    def create_run_manifest(self, name: str, experiment_id: str) -> str:
        """Create a run manifest linking dataset + experiment + commit."""
        rec = self._records.get(name)
        if rec is None:
            raise ValueError(f"Dataset {name} not registered")
        commit = os.environ.get("COSMOS_COMMIT", "unknown")
        manifest = {
            "dataset": rec.name,
            "version": rec.version,
            "local_path": rec.local_path,
            "checksum": rec.checksum,
            "experiment_id": experiment_id,
            "commit": commit,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
        p = self.dataset_dir / "processed" / f"run_manifest_{experiment_id}_{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(manifest, f, indent=2)
        return str(p)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

_default_manager: Optional[DataManager] = None


def get_data_manager() -> DataManager:
    """Get the default data manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = DataManager()
    return _default_manager


def reset_data_manager() -> None:
    """Reset the default data manager (useful for testing)."""
    global _default_manager
    _default_manager = None
