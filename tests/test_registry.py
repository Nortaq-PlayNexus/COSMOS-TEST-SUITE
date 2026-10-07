"""
Tests for the COSMOS experiment registry (Sections 7 and 46 of the spec).
"""

from __future__ import annotations

import pytest

from cosmos.registry import DEFAULT_REGISTRY, Registry, get_registry, reset_registry


@pytest.fixture
def registry():
    """A fresh in-memory registry, not the CLI singleton."""
    return Registry()


class TestRegistryPopulation:
    def test_default_registry_has_sixteen_experiments(self, registry):
        assert len(registry.experiments) == 16

    def test_all_ids_follow_exp_nnn_format(self, registry):
        for exp_id in registry.experiments:
            assert exp_id.startswith("EXP-")
            assert len(exp_id.split("-")[1]) == 3

    def test_experiment_ids_are_unique(self, registry):
        ids = [item["exp_id"] for item in DEFAULT_REGISTRY]
        assert len(ids) == len(set(ids))

    def test_orders_are_unique_and_contiguous(self, registry):
        orders = sorted(exp["order"] for exp in registry.experiments.values())
        assert orders == list(range(1, len(orders) + 1))

    def test_every_experiment_has_a_name(self, registry):
        for exp_id, exp in registry.experiments.items():
            assert exp["name"], f"{exp_id} has no name"
            assert exp["name"] is not None

    def test_every_experiment_has_a_description(self, registry):
        for exp_id, exp in registry.experiments.items():
            assert exp.get("description"), f"{exp_id} has no description"

    def test_every_experiment_has_scores(self, registry):
        required = {
            "data_availability",
            "theoretical_importance",
            "observational_leverage",
            "reproducibility",
            "computational_feasibility",
            "falsifiability",
            "potential_impact",
        }
        for exp_id, exp in registry.experiments.items():
            assert required.issubset(exp["scores"].keys()), f"{exp_id} missing scores"

    def test_scores_are_in_unit_interval(self, registry):
        for exp_id, exp in registry.experiments.items():
            for key, val in exp["scores"].items():
                assert 0.0 <= val <= 1.0, f"{exp_id}.{key}={val} out of range"


class TestMachineReadableDefinitions:
    def test_every_experiment_has_a_definition(self, registry):
        """Section 7 requires a machine-readable definition per experiment."""
        for exp_id in registry.experiments:
            definition = registry.get_definition(exp_id)
            assert definition is not None, f"{exp_id} has no definition"
            assert definition["id"] == exp_id

    def test_definitions_declare_hypothesis_and_falsification(self, registry):
        for exp_id in registry.experiments:
            d = registry.get_definition(exp_id)
            for key in ["hypothesis", "null_model", "alternative_models",
                        "assumptions", "datasets", "preprocessing", "prediction",
                        "statistical_test", "expected_result",
                        "falsification_condition", "uncertainty",
                        "systematic_errors", "reproducibility", "status"]:
                assert key in d, f"{exp_id} definition missing '{key}'"

    def test_definition_reproducibility_block(self, registry):
        for exp_id in registry.experiments:
            repro = registry.get_definition(exp_id)["reproducibility"]
            assert "random_seed" in repro, f"{exp_id} missing random_seed"
            assert "software_version" in repro, f"{exp_id} missing software_version"

    def test_exp001_definition_is_substantive(self, registry):
        d = registry.get_definition("EXP-001")
        assert "Lambda CDM" in d["hypothesis"]
        assert len(d["alternative_models"]) >= 2
        assert d["falsification_condition"]

    def test_definitions_are_json_serializable(self, registry):
        import json
        for exp_id in registry.experiments:
            json.dumps(registry.get_definition(exp_id))


class TestScoring:
    def test_score_is_average_of_components(self, registry):
        exp_id = "EXP-008"
        exp = registry.experiments[exp_id]
        expected = sum(exp["scores"].values()) / len(exp["scores"])
        assert registry.score(exp_id) == pytest.approx(expected)

    def test_score_in_unit_interval(self, registry):
        for exp_id in registry.experiments:
            assert 0.0 <= registry.score(exp_id) <= 1.0

    def test_rank_is_sorted_descending(self, registry):
        ranked = registry.rank()
        scores = [s for _, s in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_rank_covers_all_experiments(self, registry):
        assert len(registry.rank()) == len(registry.experiments)

    def test_unknown_experiment_scores_zero(self, registry):
        assert registry.score("EXP-999") == 0.0


class TestNextInLine:
    def test_next_in_line_returns_an_experiment(self, registry):
        assert registry.next_in_line() in registry.experiments

    def test_completed_experiments_are_skipped(self, registry):
        top = registry.next_in_line()
        registry.update_status(top, "completed")
        nxt = registry.next_in_line()
        assert nxt != top

    def test_all_completed_returns_none(self, registry):
        for exp_id in list(registry.experiments):
            registry.update_status(exp_id, "completed")
        assert registry.next_in_line() is None


class TestStatus:
    def test_update_status_sets_timestamps(self, registry):
        registry.update_status("EXP-001", "running")
        assert registry.experiments["EXP-001"]["status"] == "running"
        assert registry.experiments["EXP-001"]["started_at"] is not None

    def test_completion_records_completed_at(self, registry):
        registry.update_status("EXP-001", "completed")
        assert registry.experiments["EXP-001"]["completed_at"] is not None

    def test_update_unknown_experiment_returns_false(self, registry):
        assert registry.update_status("EXP-NOPE", "running") is False

    def test_list_by_status(self, registry):
        registry.update_status("EXP-002", "completed")
        assert "EXP-002" in registry.list_by_status("completed")


class TestYAMPRoundTrip:
    def test_to_yaml_and_load_preserves_ids(self, registry, tmp_path):
        p = tmp_path / "registry.yaml"
        registry.to_yaml(p)
        assert p.exists()
        reloaded = Registry.load_from_file(p)
        assert set(reloaded.experiments) == set(registry.experiments)

    def test_reloaded_registry_preserves_scores(self, registry, tmp_path):
        p = tmp_path / "registry.yaml"
        registry.to_yaml(p)
        reloaded = Registry.load_from_file(p)
        for exp_id in registry.experiments:
            assert reloaded.score(exp_id) == pytest.approx(registry.score(exp_id))

    def test_to_yaml_creates_parent_directories(self, registry, tmp_path):
        p = tmp_path / "nested" / "deeper" / "registry.yaml"
        registry.to_yaml(p)
        assert p.exists()


class TestSingleton:
    def test_get_registry_is_stable(self):
        reset_registry()
        a = get_registry()
        b = get_registry()
        assert a is b
        reset_registry()

    def test_reset_creates_a_new_instance(self):
        reset_registry()
        a = get_registry()
        reset_registry()
        b = get_registry()
        assert a is not b
        reset_registry()


class TestScientificVocabulary:
    def test_no_forbidden_language_in_definitions(self, registry):
        """
        Section 2: the software must never claim to "prove" a theory.
        Definitions should use supports/disfavors/consistent-with wording.
        """
        import re
        for exp_id in registry.experiments:
            d = registry.get_definition(exp_id)
            blob = " ".join(str(v) for v in d.values())
            assert not re.search(r"\bproven\b", blob, re.IGNORECASE), (
                f"{exp_id} uses 'proven'"
            )
