"""
Configuration management for COSMOS TEST SUITE.

Uses Pydantic Settings loaded from pyproject.toml, environment variables, and
an optional config.yaml. Provides type-safe, validated access to project
settings with clear defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExperimentStatus(str, Enum):
    """Status values for experiments in the registry."""

    NOT_STARTED = "not_started"
    PLANNED = "planned"
    DATA_AWAITING = "data_awaiting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ResultClassification(str, Enum):
    """Final classification for experiment results (Section 51 of spec)."""

    SUPPORTED = "supported"
    DISFAVORED = "disfavored"
    INCONCLUSIVE = "inconclusive"
    CONSISTENT_WITH_STANDARD_MODEL = "consistent_with_standard_model"
    STATISTICALLY_SIGNIFICANT_ANOMALY = "statistically_significant_anomaly"
    LIKELY_SYSTEMATIC = "likely_systematic"
    REQUIRES_REPLICATION = "requires_replication"
    NOT_TESTABLE = "not_testable"
    INSUFFICIENT_DATA = "insufficient_data"
    UNKNOWN = "unknown"


class ObservationType(str, Enum):
    """Category of an observation in the provenance graph."""

    OBSERVED = "observed"
    REPRODUCED = "reproduced"
    STATISTICALLY_SIGNIFICANT = "statistically_significant"
    THEORETICALLY_PREDICTED = "theoretically_predicted"
    SPECULATIVE = "speculative"
    UNRESOLVED = "unresolved"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    CONSISTENT_WITH_EXISTING_MODELS = "consistent_with_existing_models"


@dataclass
class ResourceSpec:
    """Computational resource specification."""

    cpu_count: Optional[int] = None
    ram_gb: Optional[float] = None
    gpu: bool = False
    gpu_memory_gb: Optional[float] = None
    disk_gb: Optional[float] = None
    network_available: bool = True

    def check_availability(self, **kwargs: Any) -> bool:
        """Check whether the requested resources are available."""
        if kwargs.get("min_cpu") and self.cpu_count < kwargs["min_cpu"]:
            return False
        if kwargs.get("min_ram_gb") and self.ram_gb < kwargs["min_ram_gb"]:
            return False
        if kwargs.get("requires_gpu") and not self.gpu:
            return False
        return True


class Settings(BaseSettings):
    """
    Global COSMOS settings.

    Priority order: env vars > config.yaml > pyproject.toml defaults.
    """

    model_config = SettingsConfigDict(
        env_prefix="COSMOS_",
        env_nested_delimiter="__",
        env_file=".env",
        pyproject_toml={"table": {"tool": {"cosmos"}}},
        extra = "ignore",
    )

    # -- Core identity --
    project_name: str = Field(default="COSMOS TEST SUITE", description="Project name")
    version: str = Field(default="0.1.0.dev0", description="Software version")

    # -- Paths (auto-resolved relative to project root) --
    root: Path = Field(default=None, description="Project root (auto-detected)")

    data_dir: Path = Field(default_factory=lambda: Path("data"), description="Data directory")
    papers_dir: Path = Field(default_factory=lambda: Path("papers"), description="Papers directory")
    experiments_dir: Path = Field(default_factory=lambda: Path("experiments"), description="Experiments directory")
    simulations_dir: Path = Field(default_factory=lambda: Path("simulations"), description="Simulations directory")
    reports_dir: Path = Field(default_factory=lambda: Path("reports"), description="Reports directory")
    config_dir: Path = Field(default_factory=lambda: Path("config"), description="Config directory")
    docs_dir: Path = Field(default_factory=lambda: Path("docs"), description="Docs directory")
    logs_dir: Path = Field(default_factory=lambda: Path("logs"), description="Logs directory")
    reproducibility_dir: Path = Field(default_factory=lambda: Path("reproducibility"), description="Reproducibility outputs")

    # -- Database --
    database_url: str = Field(default="sqlite:///cosmos.db", description="Database URL")
    database_echo: bool = Field(default=False, description="Echo SQL statements")
    database_pool_size: int = Field(default=5, description="SQLAlchemy connection pool size")
    database_max_overflow: int = Field(default=10, description="SQLAlchemy max overflow")

    # -- Experiment registry --
    registry_file: Path = Field(default_factory=lambda: Path("config") / "experiment_registry.yaml", description="Experiment registry file")

    # -- Data acquisition --
    network_timeout: int = Field(default=60, description="Network request timeout (seconds)")
    allow_data_download: bool = Field(default=True, description="Allow downloading data (off = offline mode)")
    auto_download_data: bool = Field(default=False, description="Automatically download data when required")
    data_cache_dir: Path = Field(default_factory=lambda: Path("data") / "cache", description="Data cache directory")
    max_data_size_gb: Optional[float] = Field(default=100.0, description="Maximum total data size (GB)")

    # -- Logging --
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        description="Log format string",
    )
    log_json: bool = Field(default=False, description="Log as JSON")

    # -- Simulation --
    simulation_default_seed: int = Field(default=42, description="Default random seed for simulations")
    simulation_max_memory_gb: Optional[float] = Field(default=None, description="Max memory per simulation job (GB)")
    simulation_parallel_jobs: int = Field(default=1, description="Default parallel simulation jobs")

    # -- Statistics --
    statistics_default_n_samps: int = Field(default=2000, description="Default MCMC samples")
    statistics_default_n_burnin: int = Field(default=500, description="Default MCMC burnin")
    statistics_default_n_chains: int = Field(default=4, description="Default Mcmc chains")
    statistics_significance_sigma: float = Field(default=5.0, description="Discovery threshold in sigma")
    statistics_correction_method: str = Field(default="bonferroni", description="Multiple comparison correction")

    # -- Resources --
    resources_auto_detect: bool = Field(default=True, description="Auto-detect resources")

    # -- Reproducibility --
    reproducibility_auto_lock: bool = Field(default=True, description="Auto-generate lockfiles")

    @field_validator("root", mode="before")
    @classmethod
    def _resolve_root(cls, v: Any) -> Any:
        if v is None:
            # Project root: the directory containing the `cosmos` package
            # (i.e. .../COSMOS-TEST-SUITE), since this file is cosmos/config.py.
            return Path(__file__).resolve().parent.parent
        return Path(v)

    def model_post_init(self, __context: Any) -> None:
        """
        Pydantic v2 hook (replaces __post_init__ for BaseSettings).

        Resolves relative paths against the project root and ensures the
        output directories exist so downstream code can write artifacts
        without additional mkdir logic.
        """
        for attr in [
            "data_dir", "papers_dir", "experiments_dir", "simulations_dir",
            "reports_dir", "config_dir", "docs_dir", "logs_dir",
            "reproducibility_dir", "data_cache_dir", "registry_file",
        ]:
            val = getattr(self, attr)
            if isinstance(val, Path) and not val.is_absolute():
                setattr(self, attr, self.root / val)
        for p in [self.data_dir, self.papers_dir, self.experiments_dir, self.reports_dir]:
            p.mkdir(parents=True, exist_ok=True)

    def resolve(self, path: Path | str) -> Path:
        """Resolve a path relative to project root or return as-is."""
        p = Path(path)
        return p if p.is_absolute() else self.root / p

    @property
    def resource_spec(self) -> ResourceSpec:
        """Auto-detected resource specification."""
        if not self.resources_auto_detect:
            return ResourceSpec()
        try:
            import psutil
            mem = psutil.virtual_memory()
            return ResourceSpec(
                cpu_count=os.cpu_count(),
                ram_gb=mem.total / (1024**3),
                gpu=False,
                disk_gb=self._disk_free(),
            )
        except Exception:
            return ResourceSpec(cpu_count=os.cpu_count(), ram_gb=16.0, gpu=False)

    def _disk_free(self) -> float:
        try:
            free = psutil.disk_usage(self.root).free
            return free / (1024**3)
        except Exception:
            return 100.0

    @classmethod
    def from_file(cls, path: Path) -> Settings:
        """Load settings from a YAML file, merging with defaults."""
        with open(path) as f:
            overrides = yaml.safe_load(f) or {}
        return cls(**overrides)

    @property
    def database_engine_url(self) -> str:
        """Return the database URL with proper quoting for SQLite paths."""
        return self.database_url


settings = Settings()
