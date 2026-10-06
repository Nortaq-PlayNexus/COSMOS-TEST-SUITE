"""
Tests for COSMOS configuration (Section: project config).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cosmos.config import ExperimentStatus, ObservationType, ResultClassification, Settings


class TestSettings:
    def test_default_settings_load(self):
        s = Settings()
        assert s.project_name == "COSMOS TEST SUITE"
        assert s.version

    def test_paths_are_absolute(self):
        s = Settings()
        for attr in ["data_dir", "papers_dir", "experiments_dir", "reports_dir"]:
            assert Path(getattr(s, attr)).is_absolute(), f"{attr} should be absolute"

    def test_resolve_relative_path(self):
        s = Settings()
        resolved = s.resolve("data/raw")
        assert resolved.is_absolute()
        assert resolved == s.root / "data" / "raw"
        assert resolved.parent.name == "data"
        assert resolved.name == "raw"

    def test_resolve_absolute_path_unchanged(self):
        s = Settings()
        p = Path("C:/tmp/foo")
        assert s.resolve(p) == p

    def test_directories_created(self):
        s = Settings()
        assert s.data_dir.exists()
        assert s.experiments_dir.exists()


class TestEnums:
    """Classification vocabulary must match the specification (Sections 2 & 51)."""

    def test_result_classification_values(self):
        expected = {
            "supported",
            "disfavored",
            "inconclusive",
            "consistent_with_standard_model",
            "statistically_significant_anomaly",
            "likely_systematic",
            "requires_replication",
            "not_testable",
            "insufficient_data",
        }
        actual = {e.value for e in ResultClassification}
        # Spec list must be a subset of our vocabulary (extra "unknown" allowed).
        assert expected.issubset(actual)

    def test_observation_types_present(self):
        for label in ["observed", "reproduced", "unresolved", "speculative"]:
            assert label in {e.value for e in ObservationType}

    def test_experiment_status_values(self):
        for label in ["not_started", "running", "completed", "failed"]:
            assert label in {e.value for e in ExperimentStatus}