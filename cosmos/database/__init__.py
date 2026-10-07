"""
Database module for COSMOS TEST SUITE.

Provides:
- Engine/session management (SQLite by default, extensible to PostgreSQL)
- Repository classes for clean access to ORM entities
- Schema initialization with default data (questions, experiments, models)

The provenance graph connects:
    QUESTION -> HYPOTHESIS -> MODEL -> PREDICTION -> OBSERVATION
         -> DATASET -> EXPERIMENT -> RESULT -> PAPER
"""

from __future__ import annotations

import datetime
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Type

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from . import models

# ---------------------------------------------------------------------------
# Engine & session management
# ---------------------------------------------------------------------------


def create_engine(database_url: Optional[str] = None, echo: bool = False) -> Any:
    """Create the database engine."""
    return models.create_db_engine(database_url, echo)


def init_db(database_url: Optional[str] = None, echo: bool = False) -> Any:
    """
    Create all ORM tables in the database.

    Tables: questions, papers, sources, datasets, models, hypotheses,
    predictions, experiments, results, observations, reports,
    experiment_registry.
    """
    engine = models.init_db(database_url, echo)
    return engine


# Default global session factory (binds lazily)
SessionLocal = models.SessionLocal


@contextmanager
def get_session(database_url: Optional[str] = None) -> Generator[Session, None, None]:
    """
    Context manager yielding a database session.

    Usage:
        with get_session() as session:
            session.query(Paper).all()

    Commits on successful exit, rolls back on exception.
    Initializes the database (tables + default data) on first use.
    """
    engine = create_engine(database_url)
    # Initialize tables if they don't exist
    if not _tables_exist(engine):
        init_db(database_url, echo=False)
    session = SessionLocal(bind=engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _tables_exist(engine: Any) -> bool:
    """Check whether the Cosmos tables exist in the database."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    return "experiments" in tables and "questions" in tables


def get_db(database_url: Optional[str] = None) -> Session:
    """Factory for a database session (usable with FastAPI-style dependency injection)."""
    return SessionLocal(bind=create_engine(database_url))


# ---------------------------------------------------------------------------
# Repository layer
# ---------------------------------------------------------------------------


class Repository:
    """Base repository providing common CRUD operations."""

    def __init__(self, session: Session, model: Type[Any]):
        self.session = session
        self.model = model

    def get(self, id: str) -> Optional[Any]:
        return self.session.get(self.model, id)

    def get_by(self, **kwargs: Any) -> Optional[Any]:
        stmt = select(self.model).filter_by(**kwargs)
        return self.session.execute(stmt).scalars().first()

    def list_all(self, limit: int = 1000, order_by: Optional[str] = None) -> List[Any]:
        stmt = select(self.model).limit(limit)
        if order_by:
            stmt = stmt.order_by(getattr(self.model, order_by))
        return list(self.session.execute(stmt).scalars().all())

    def add(self, obj: Any) -> Any:
        self.session.add(obj)
        return obj

    def add_all(self, objs: List[Any]) -> None:
        self.session.add_all(objs)

    def delete(self, obj: Any) -> None:
        self.session.delete(obj)

    def count(self) -> int:
        return self.session.query(self.model).count()


class QuestionRepository(Repository):
    """Repository for scientific questions."""

    def list_open(self) -> List[models.Question]:
        stmt = select(models.Question).filter(models.Question.status == "open")
        return list(self.session.execute(stmt).scalars().all())

    def find_by_key(self, key: str) -> Optional[models.Question]:
        return self.get_by(key=key)

    def upsert(self, key: str, title: str, description: Optional[str] = None) -> models.Question:
        q = self.find_by_key(key)
        if q is None:
            q = models.Question(key=key, title=title, description=description)
            self.add(q)
        return q


class PaperRepository(Repository):
    """Repository for scientific papers/sources."""

    def find_by_doi(self, doi: str) -> Optional[models.Paper]:
        return self.get_by(doi=doi)

    def find_by_arxiv(self, arxiv_id: str) -> Optional[models.Paper]:
        return self.get_by(arxiv_id=arxiv_id)

    def search(self, query: str, limit: int = 50) -> List[models.Paper]:
        """
        Search papers by title, abstract, or text stored in the JSON 'claims' field.
        """
        term = f"%{query}%"
        stmt = (
            select(models.Paper)
            .filter(
                models.Paper.title.ilike(term)
                | models.Paper.abstract.ilike(term)
                | models.Paper.claims.ilike(term)
            )
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())


class DatasetRepository(Repository):
    """Repository for datasets."""

    def list_available(self, data_type: Optional[str] = None) -> List[models.Dataset]:
        stmt = select(models.Dataset).filter(models.Dataset.availability == "offline")
        if data_type:
            stmt = stmt.filter(models.Dataset.data_type == data_type)
        return list(self.session.execute(stmt).scalars().all())

    def mark_unavailable(self, dataset_id: str) -> None:
        ds = self.get(dataset_id)
        if ds:
            ds.availability = "unavailable"

    def get_with_path(self, dataset_id: str) -> Optional[models.Dataset]:
        ds = self.get(dataset_id)
        if ds and ds.local_path:
            from pathlib import Path
            if Path(ds.local_path).exists():
                return ds
        return None


class ExperimentRepository(Repository):
    """Repository for experiments."""

    def find_by_exp_id(self, exp_id: str) -> Optional[models.Experiment]:
        return self.get_by(exp_id=exp_id)

    def list_by_status(self, status: str, limit: int = 1000) -> List[models.Experiment]:
        stmt = select(models.Experiment).filter(models.Experiment.status == status).limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def list_all_experiments(self) -> List[models.Experiment]:
        stmt = select(models.Experiment).order_by(models.Experiment.exp_id)
        return list(self.session.execute(stmt).scalars().all())

    def find_or_create(self, exp_id: str, name: str) -> models.Experiment:
        """
        Return the experiment with this identifier, creating it if absent.

        The insert is flushed so that the returned object is immediately
        visible to subsequent queries in the same transaction (e.g. a
        follow-up update_status call).
        """
        exp = self.find_by_exp_id(exp_id)
        if exp is None:
            exp = models.Experiment(exp_id=exp_id, name=name)
            self.add(exp)
            self.session.flush()
        return exp

    def update_status(self, exp_id: str, status: str, phase: Optional[str] = None) -> bool:
        exp = self.find_by_exp_id(exp_id)
        if exp is None:
            return False
        exp.status = status
        if phase:
            exp.phase = phase
        return True

    def mark_completed(
        self,
        exp_id: str,
        classification: str,
        result_summary: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> bool:
        exp = self.find_by_exp_id(exp_id)
        if exp is None:
            return False
        exp.status = "completed"
        exp.result_classification = classification
        exp.end_date = datetime.datetime.utcnow()
        exp.result_summary = result_summary
        if output_dir:
            exp.output_dir = output_dir
        return True


class ResultRepository(Repository):
    """Repository for experiment results."""

    def list_for_experiment(self, exp_id: str, limit: int = 100) -> List[models.Result]:
        """List results for an experiment, newest first.

        exp_id may be the internal Experiment UUID or the public identifier
        such as "EXP-001".
        """
        exp = self.session.get(models.Experiment, exp_id)
        if exp is None:
            exp = ExperimentRepository(self.session, models.Experiment).find_by_exp_id(exp_id)
        if exp is None:
            return []
        stmt = (
            select(models.Result)
            .filter(models.Result.experiment_id == exp.id)
            .order_by(models.Result.run_timestamp.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def record_result(
        self,
        exp_id: str,
        run_id: str,
        classification: str,
        significance_sigma: Optional[float] = None,
        p_value: Optional[float] = None,
        result_summary: Optional[str] = None,
        posterior_parameters: Optional[Dict[str, Any]] = None,
        confidence_interval: Optional[Dict[str, Any]] = None,
        systematic_errors: Optional[List[str]] = None,
        adversarial_tests: Optional[List[str]] = None,
        survived_adversarial: bool = False,
        summary_level1: Optional[str] = None,
        summary_level2: Optional[str] = None,
        summary_level3: Optional[str] = None,
        summary_level4: Optional[str] = None,
        limitations: Optional[List[str]] = None,
        unresolved_questions: Optional[List[str]] = None,
        output_dir: Optional[str] = None,
        provenance: Optional[List[Dict[str, str]]] = None,
    ) -> models.Result:
        # exp_id may be either the internal UUID (primary key) or the public
        # experiment identifier (e.g. "EXP-001"). Resolve both cases.
        exp = self.session.get(models.Experiment, exp_id)
        if exp is None:
            exp = ExperimentRepository(self.session, models.Experiment).find_by_exp_id(exp_id)
        if exp is None:
            raise ValueError(f"Experiment {exp_id} not found")
        run_id = run_id or str(uuid.uuid4())
        run = models.Result(
            experiment_id=exp.id,
            question_id=exp.question_id,
            run_id=run_id,
            run_timestamp=datetime.datetime.utcnow(),
            classification=classification,
            significance_sigma=significance_sigma,
            p_value=p_value,
            summary=result_summary,
            posterior_parameters=(
                __json__(posterior_parameters) if posterior_parameters else None
            ),
            confidence_interval=__json__(confidence_interval) if confidence_interval else None,
            systematic_errors=__json__(systematic_errors) if systematic_errors else None,
            adversarial_tests=__json__(adversarial_tests) if adversarial_tests else None,
            survived_adversarial=survived_adversarial,
            summary_level1=summary_level1,
            summary_level2=summary_level2,
            summary_level3=summary_level3,
            summary_level4=summary_level4,
            limitations=__json__(limitations) if limitations else None,
            unresolved_questions=__json__(unresolved_questions) if unresolved_questions else None,
            output_dir=output_dir,
            provenance=__json__(provenance) if provenance else None,
        )
        self.add(run)
        return run


# ---------------------------------------------------------------------------
# Registry repository
# ---------------------------------------------------------------------------


class ExperimentRegistryRepository(Repository):
    """Repository for the experiment registry (Section 46 of spec)."""

    def all_experiments(self) -> List[models.ExperimentRegistry]:
        return self.list_all(order_by="order")

    def get_next_recommended(self) -> Optional[models.ExperimentRegistry]:
        stmt = (
            select(models.ExperimentRegistry)
            .filter(models.ExperimentRegistry.recommended)
            .order_by(models.ExperimentRegistry.total_priority(), models.ExperimentRegistry.order)
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def add_experiment(
        self,
        exp_id: str,
        name: str,
        description: Optional[str] = None,
        order: int = 0,
        scores: Optional[Dict[str, float]] = None,
    ) -> models.ExperimentRegistry:
        reg = self.find_by_exp_id(exp_id)
        if reg is None:
            reg = models.ExperimentRegistry(
                exp_id=exp_id, name=name, description=description, order=order
            )
            self.add(reg)
        if scores:
            for key, val in scores.items():
                if hasattr(reg, key):
                    setattr(reg, key, val)
        reg.recommended = reg.total_priority() > 0.5
        return reg

    def find_by_exp_id(self, exp_id: str) -> Optional[models.ExperimentRegistry]:
        return self.get_by(exp_id=exp_id)


# ---------------------------------------------------------------------------
# Schema initialization with default data
# ---------------------------------------------------------------------------


def init_schema(
    database_url: Optional[str] = None,
    populate_default_data: bool = True,
) -> Any:
    """Initialize the database schema and optionally populate default data."""
    engine = init_db(database_url)
    if populate_default_data:
        _populate_default_data(database_url, engine)
    return engine


def _populate_default_data(
    database_url: Optional[str] = None, engine: Any = None
) -> None:
    """
    Populate the database with default questions, models, and registry entries.

    `database_url` must be threaded through so that the session opened here
    targets the same database as the engine that was just created. An earlier
    version referenced an undefined name and raised NameError whenever this
    function ran.
    """
    if database_url is None and engine is not None:
        database_url = str(engine.url)
    questions = [
        ("is_the_universe_infinite",
         "Is the universe spatially infinite?",
         "Can we observe the full extent of space, or does the universe extend beyond our observable horizon indefinitely?"),
        ("universe_topology",
         "Could the universe have a finite topology?",
         "Is space simply connected, or could it have a compact, multi-connected topology like a 3-torus?"),
        ("large_scale_homogeneity",
         "Is the universe homogeneous on sufficiently large scales?",
         "Do density fluctuations average out at large enough scales, as required by the Cosmological Principle?"),
        ("large_scale_isotropy",
         "Is the universe isotropic?",
         "Does the universe look the same in all directions, or is there a preferred cosmic axis?"),
        ("preferred_direction",
         "Is there a preferred cosmic direction?",
         "Do observations show evidence for a 'axis of evil', dipole anisotropy, or other preferred direction?"),
        ("dark_matter_particle",
         "Does dark matter behave like a particle component?",
         "Do observations require an unseen particle component, or can modified gravity explain them?"),
        ("modified_gravity",
         "Could modified gravity explain observations attributed to dark matter?",
         "Can MOND-like or other modified-gravity theories explain galaxy rotation curves, lensing, and cluster dynamics?"),
        ("dark_energy_constant",
         "Is dark energy actually constant (a cosmological constant)?",
         "Is w = -1, or does dark energy evolve with time?"),
        ("dark_energy_evolving",
         "Is dark energy evolving?",
         "Do the data prefer w0-wa or other time-dependent dark energy models over a pure cosmological constant?"),
        ("hubble_constant",
         "What is the Hubble constant?",
         "What is the current expansion rate of the universe, and why do early- and late-universe measurements disagree?"),
        ("hubble_tension",
         "Why do early- and late-universe H0 measurements disagree?",
         "Is the Hubble tension real, and if so, what physical explanation resolves it?"),
        ("cosmic_inflation",
         "Did cosmic inflation occur?",
         "Do observations support a period of exponential expansion in the early universe?"),
        ("inflation_signatures",
         "What observable signatures could inflation have left?",
         "Can we detect the primordial power spectrum tilt, tensor modes (B-modes), or non-Gaussianity predicted by inflation?"),
        ("earliest_phases",
         "What happened during the earliest observable phases of the universe?",
         "What can we say about reheating, the earliest moments after the Big Bang, and the limits of observability?"),
        ("big_bounce",
         "Could a Big Bounce be observationally distinguishable?",
         "Can cyclic or bouncing cosmologies make predictions that differ from the hot Big Bang + inflation paradigm?"),
        ("bubble_collision",
         "Could bubble collisions leave observable CMB signatures?",
         "Can eternal inflation produce bubble universes whose collisions leave detectable circles in the CMB?"),
        ("spatial_repetition",
         "Could the universe contain spatial repetitions?",
         "Under what assumptions about curvature, topology, and entropy would distant regions contain copies of local configurations?"),
        ("large_structures",
         "Are there structures larger or more unusual than Lambda CDM predicts?",
         "Do giant arcs, superclusters, and large voids exceed the expected maximum sizes in Lambda CDM simulations?"),
        ("cmb_anomalies",
         "Are there genuine anomalies in the CMB?",
         "Do large-scale CMB anomalies survive look-elsewhere corrections, foreground subtraction, and independent analyses?"),
        ("fundamental_symmetries",
         "Are there violations of fundamental symmetries?",
         "Do observations reveal any violation of CPT, Lorentz invariance, or other fundamental symmetries?"),
        ("gr_at_cosmological_scales",
         "Does General Relativity describe gravity at cosmological scales?",
         "Do cosmological observations confirm GR, or do they point toward modified gravity?"),
        ("gravitational_waves",
         "Do gravitational waves behave as predicted by GR?",
         "Do GW observations confirm GR predictions for propagation speed, polarization, and damping?"),
        ("independent_datasets",
         "Can independent datasets consistently describe the same cosmological model?",
         "Do CMB, BAO, supernova, lensing, and growth data all converge on a consistent Lambda CDM cosmology?"),
        ("lcdm_success",
         "Where does Lambda CDM succeed?",
         "What observations does the standard model explain well?"),
        ("lcdm_failure",
         "Where does Lambda CDM fail?",
         "What observations challenge the standard model (e.g., H0 tension, sigma8 tension, CMB anomalies)?"),
        ("hubble_value",
         "What is the Hubble constant?",
         "A focused investigation of H0 combining all available measurements."),
    ]

    with get_session(database_url) as session:
        repo = QuestionRepository(session, models.Question)
        for key, title, description in questions:
            q = repo.upsert(key, title, description)
            print(f"  question: {q.key}")

        # Standard and alternative models (Section 37 of spec)
        models_data = [
            ("lcdm", "null", "Lambda-CDM: the standard cosmological model (Planck 2018/2023 parameters).",
             "dark_energy"),
            ("w_const", "alternative", "Dark energy with constant equation of state w != -1.", "dark_energy"),
            ("w0wa", "alternative", "Dark energy with time-varying equation of state w(z) = w0 + wa*z/(1+z).", "dark_energy"),
            ("mond", "alternative", "MOND and relativistic extensions (TeVeS, MOG).", "dark_matter"),
            ("scalar_tensor", "alternative", "Scalar-tensor theories of modified gravity.", "gravity"),
            ("inflation_powerlaw", "alternative", "Power-law inflation models.", "inflation"),
            ("big_bounce_toy", "alternative", "Toy bouncing universe model.", "early_universe"),
            ("compact_topology", "alternative", "Compact multi-connected topology (e.g., 3-torus).", "topology"),
        ]
        for name, mtype, desc, cat in models_data:
            m = models.Model(
                name=name,
                model_type=mtype,
                description=desc,
                category=cat,
                parameters=None,
                equations=None,
                assumptions=None,
                predictions=None,
                associated_papers=None,
            )
            session.add(m)
        print("  models added")

        # Experiment registry (Sections 7, 46 of spec)
        registry_items = [
            ("EXP-001", "Cosmic web and large-scale structure vs Lambda CDM", 1),
            ("EXP-002", "Large-scale isotropy and preferred direction", 2),
            ("EXP-003", "Homogeneity scale measurement", 3),
            ("EXP-004", "Cosmic web reconstruction and statistics", 4),
            ("EXP-005", "Dark matter: particle vs modified gravity", 5),
            ("EXP-006", "Modified gravity model comparison", 6),
            ("EXP-007", "Dark energy: w, w0-wa, evolving models", 7),
            ("EXP-008", "Hubble tension analysis", 8),
            ("EXP-009", "Inflation signatures", 9),
            ("EXP-010", "CMB anomalies with look-elsewhere correction", 10),
            ("EXP-011", "Multiverse / bubble collision signatures", 11),
            ("EXP-012", "Cosmic topology (matched circles)", 12),
            ("EXP-013", "Spatial repetition under various assumptions", 13),
            ("EXP-014", "Large cosmic structures (superclusters, walls)", 14),
            ("EXP-015", "General Relativity tests at cosmological scales", 15),
            ("EXP-016", "Gravitational-wave observations", 16),
        ]
        registry = ExperimentRegistryRepository(session, models.ExperimentRegistry)
        for exp_id, name, order in registry_items:
            registry.add_experiment(exp_id, name, order=order)
        print("  experiment registry populated")

        session.commit()


def __json__(obj: Any) -> str:
    """Helper to serialize JSON, used in record_result()."""
    import json
    return json.dumps(obj)
