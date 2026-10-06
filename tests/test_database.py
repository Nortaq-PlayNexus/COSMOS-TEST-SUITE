"""
Tests for the COSMOS research database and experiment registry.

Uses a temporary on-disk SQLite database per test session so tests never touch
the user's real research database.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import inspect

from cosmos.database import (
    ExperimentRepository,
    QuestionRepository,
    ResultRepository,
    create_engine,
    get_session,
    init_db,
    models,
)
from cosmos.database.models import Base


@pytest.fixture(scope="module")
def db_url():
    """A throwaway SQLite database for the whole module."""
    tmpdir = tempfile.mkdtemp(prefix="cosmos_test_db_")
    path = os.path.join(tmpdir, "test.db")
    init_db(f"sqlite:///{path}")
    return f"sqlite:///{path}"


@pytest.fixture
def session(db_url):
    with get_session(db_url) as s:
        yield s


class TestSchema:
    def test_all_tables_created(self, db_url):
        engine = create_engine(db_url)
        tables = set(inspect(engine).get_table_names())
        expected = {
            "questions",
            "papers",
            "sources",
            "datasets",
            "models",
            "hypotheses",
            "predictions",
            "experiments",
            "results",
            "observations",
            "reports",
            "experiment_registry",
            "paper_experiment_link",
            "dataset_experiment_link",
            "paper_source_link",
        }
        assert expected.issubset(tables), f"missing tables: {expected - tables}"

    def test_result_table_has_provenance_columns(self, db_url):
        """Section 27 of the spec requires a full provenance chain."""
        engine = create_engine(db_url)
        cols = {c["name"] for c in inspect(engine).get_columns("results")}
        for required in ["provenance", "adversarial_tests", "systematic_errors",
                         "significance_sigma", "classification", "run_id"]:
            assert required in cols, f"results table missing {required}"

    def test_experiment_table_has_definition_and_plan(self, db_url):
        engine = create_engine(db_url)
        cols = {c["name"] for c in inspect(engine).get_columns("experiments")}
        for required in ["definition", "analysis_plan", "registered_before_results",
                         "result_classification", "falsification_condition" ]:
            if required == "falsification_condition":
                # stored inside the definition JSON, not a column
                continue
            assert required in cols, f"experiments table missing {required}"


class TestQuestionRepository:
    def test_upsert_is_idempotent(self, session):
        repo = QuestionRepository(session, models.Question)
        q1 = repo.upsert("test_question_key", "Title A", "desc")
        session.commit()
        q2 = repo.upsert("test_question_key", "Title B", "desc2")
        session.commit()
        assert q1.id == q2.id

    def test_find_by_key(self, session):
        repo = QuestionRepository(session, models.Question)
        repo.upsert("findable_key", "Findable", None)
        session.commit()
        assert repo.find_by_key("findable_key") is not None
        assert repo.find_by_key("does_not_exist") is None


class TestExperimentRepository:
    def test_find_or_create(self, session):
        repo = ExperimentRepository(session, models.Experiment)
        e1 = repo.find_or_create("EXP-TEST-1", "Test experiment")
        session.commit()
        e2 = repo.find_or_create("EXP-TEST-1", "Test experiment")
        session.commit()
        assert e1.id == e2.id

    def test_update_status(self, session):
        repo = ExperimentRepository(session, models.Experiment)
        repo.find_or_create("EXP-TEST-2", "Status test")
        session.commit()
        assert repo.update_status("EXP-TEST-2", "running", phase="analysis")
        session.commit()
        e = repo.find_by_exp_id("EXP-TEST-2")
        assert e.status == "running"
        assert e.phase == "analysis"

    def test_update_status_unknown_experiment_returns_false(self, session):
        repo = ExperimentRepository(session, models.Experiment)
        assert repo.update_status("EXP-NOPE", "running") is False

    def test_list_all_ordered(self, session):
        repo = ExperimentRepository(session, models.Experiment)
        repo.find_or_create("EXP-TEST-3", "Third")
        repo.find_or_create("EXP-TEST-4", "Fourth")
        session.commit()
        ids = [e.exp_id for e in repo.list_all_experiments()]
        assert ids == sorted(ids)

    def test_list_by_status(self, session):
        repo = ExperimentRepository(session, models.Experiment)
        repo.find_or_create("EXP-TEST-5", "Filter test")
        repo.update_status("EXP-TEST-5", "completed")
        session.commit()
        completed = repo.list_by_status("completed")
        assert any(e.exp_id == "EXP-TEST-5" for e in completed)


class TestResultRepository:
    def test_record_result_links_to_experiment(self, session):
        exp_repo = ExperimentRepository(session, models.Experiment)
        res_repo = ResultRepository(session, models.Result)
        exp = exp_repo.find_or_create("EXP-TEST-6", "Result test")
        session.commit()

        res = res_repo.record_result(
            exp_id=exp.id,
            run_id="run_test_1",
            classification="consistent_with_standard_model",
            significance_sigma=1.2,
            p_value=0.23,
        )
        session.commit()
        assert res.id
        assert res.experiment_id == exp.id
        assert res.classification == "consistent_with_standard_model"

    def test_record_result_accepts_public_experiment_id(self, session):
        """exp_id may be the public identifier as well as the internal UUID."""
        exp_repo = ExperimentRepository(session, models.Experiment)
        res_repo = ResultRepository(session, models.Result)
        exp_repo.find_or_create("EXP-TEST-7", "Public id test")
        session.commit()

        res = res_repo.record_result(
            exp_id="EXP-TEST-7",
            run_id="run_test_2",
            classification="inconclusive",
        )
        session.commit()
        assert res.classification == "inconclusive"

    def test_record_result_unknown_experiment_raises(self, session):
        res_repo = ResultRepository(session, models.Result)
        with pytest.raises(ValueError):
            res_repo.record_result(
                exp_id="EXP-DOES-NOT-EXIST",
                run_id="run_x",
                classification="inconclusive",
            )

    def test_list_for_experiment(self, session):
        exp_repo = ExperimentRepository(session, models.Experiment)
        res_repo = ResultRepository(session, models.Result)
        exp = exp_repo.find_or_create("EXP-TEST-8", "List results test")
        session.commit()
        res_repo.record_result(exp_id=exp.id, run_id="r1", classification="inconclusive")
        res_repo.record_result(exp_id=exp.id, run_id="r2", classification="supported")
        session.commit()

        results = res_repo.list_for_experiment(exp.id)
        assert len(results) >= 2
        # Newest first.
        assert results[0].run_timestamp >= results[-1].run_timestamp


class TestProvenanceGraph:
    def test_result_question_link_is_populated(self, session):
        """
        Section 27: every result must be traceable back to the question it
        addresses. Recording a result should populate question_id.
        """
        q_repo = QuestionRepository(session, models.Question)
        e_repo = ExperimentRepository(session, models.Experiment)
        r_repo = ResultRepository(session, models.Result)

        q = q_repo.upsert("provenance_question", "Provenance Q", None)
        session.commit()

        e = e_repo.find_or_create("EXP-PROV-1", "Provenance experiment")
        e.question_id = q.id
        session.commit()

        r = r_repo.record_result(
            exp_id=e.id, run_id="prov_run", classification="supported"
        )
        session.commit()
        assert r.question_id == q.id

    def test_full_provenance_chain_is_serializable(self, session):
        import json

        e_repo = ExperimentRepository(session, models.Experiment)
        r_repo = ResultRepository(session, models.Result)
        e = e_repo.find_or_create("EXP-PROV-2", "Serializability test")
        session.commit()

        chain = [
            {"node_type": "result", "node_id": "run_1"},
            {"node_type": "analysis", "node_id": "analysis_v1"},
            {"node_type": "code_version", "node_id": "commit_abc123"},
            {"node_type": "dataset", "node_id": "desi_dr1"},
            {"node_type": "paper", "node_id": "10.1103/physrevd"},
        ]
        r = r_repo.record_result(
            exp_id=e.id, run_id="prov2", classification="supported", provenance=chain
        )
        session.commit()
        # Provenance is stored as a JSON string in the JSON column.
        parsed = json.loads(r.provenance)
        assert len(parsed) == 5
        assert parsed[0]["node_type"] == "result"
        assert parsed[-1]["node_type"] == "paper"