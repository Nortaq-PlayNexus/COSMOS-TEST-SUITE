"""
SQLAlchemy ORM models for the COSMOS research database.

The core schema implements the hypothesis graph and provenance chain described
in Section 34/27 of the project specification:

    QUESTION -> HYPOTHESIS -> MODEL -> PREDICTION -> OBSERVATION
         -> DATASET -> EXPERIMENT -> RESULT -> PAPER

Every experiment is self-contained yet linked to shared research resources
(papers, datasets, models, other experiments).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, relationship, sessionmaker

Base = declarative_base()


# ---------------------------------------------------------------------------
# Enum-like reference tables
# ---------------------------------------------------------------------------

# Result classification (Section 51 of spec)
RESULT_CLASSIFICATION = [
    "supported",
    "disfavored",
    "inconclusive",
    "consistent_with_standard_model",
    "statistically_significant_anomaly",
    "likely_systematic",
    "requires_replication",
    "not_testable",
    "insufficient_data",
    "unknown",
]

# Observation type (Section 2 of spec)
OBSERVATION_TYPE = [
    "observed",
    "reproduced",
    "statistically_significant",
    "theoretically_predicted",
    "speculative",
    "unresolved",
    "contradicted",
    "unsupported",
    "consistent_with_existing_models",
]

# Experiment status
EXPERIMENT_STATUS = [
    "not_started",
    "planned",
    "data_awaiting",
    "running",
    "completed",
    "failed",
    "blocked",
]

# Testability status (Section 17 of spec)
TESTABILITY_STATUS = [
    "testable_now",
    "testable_with_future_data",
    "indirectly_testable",
    "not_currently_testable",
    "no_unique_prediction",
]


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------

class Question(Base):
    """
    A scientific question being investigated (Section 1 of spec).

    Big questions such as "Is the universe infinite?", "What is dark energy?",
    etc.
    """

    __tablename__ = "questions"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    key: Mapped[str] = Column(String(200), unique=True, nullable=False, index=True)
    title: Mapped[str] = Column(String(500), nullable=False)
    description: Mapped[str] = Column(Text, nullable=True)
    consensus: Mapped[str] = Column(Text, nullable=True)
    status: Mapped[str] = Column(String(100), default="open")

    experiments: Mapped[List["Experiment"]] = relationship(
        back_populates="question", lazy="selectin"
    )
    hypotheses: Mapped[List["Hypothesis"]] = relationship(
        back_populates="question", lazy="selectin"
    )
    results: Mapped[List["Result"]] = relationship(
        back_populates="question", lazy="selectin"
    )
    reports: Mapped[List["Report"]] = relationship(
        back_populates="question", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Question key={self.key!r} title={self.title!r}>"


class Paper(Base):
    """
    A scientific source: paper, mission documentation, dataset release note.

    Metadata follows Section 5 of the spec: title, authors, publication date,
    journal, DOI, arXiv ID, URL, source organization, methodology, claims,
    limitations, relevant equations, relevant observations, citations, etc.
    """

    __tablename__ = "papers"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Identifiers
    doi: Mapped[str] = Column(String(200), index=True, nullable=True)
    arxiv_id: Mapped[str] = Column(String(50), index=True, nullable=True)
    title: Mapped[str] = Column(String(1000), nullable=False)
    # Authors as JSON array of {name, affiliation, orcid?}
    authors: Mapped[str] = Column(JSON, nullable=True)
    publication_date: Mapped[Optional[datetime.date]] = Column(DateTime, nullable=True)
    journal: Mapped[Optional[str]] = Column(String(500), nullable=True)
    volume: Mapped[Optional[str]] = Column(String(100), nullable=True)
    pages: Mapped[Optional[str]] = Column(String(100), nullable=True)
    # Source tracking
    source: Mapped[str] = Column(String(100), nullable=True)
    url: Mapped[Optional[str]] = Column(String(1000), nullable=True)
    local_path: Mapped[Optional[str]] = Column(String(1000), nullable=True)
    # Content extraction
    abstract: Mapped[Optional[str]] = Column(Text, nullable=True)
    methodology: Mapped[Optional[str]] = Column(Text, nullable=True)
    claims: Mapped[str] = Column(JSON, nullable=True)
    limitations: Mapped[str] = Column(JSON, nullable=True)
    equations: Mapped[str] = Column(JSON, nullable=True)
    observations: Mapped[str] = Column(JSON, nullable=True)
    # Relationships
    citations: Mapped[str] = Column(JSON, nullable=True)
    replication_status: Mapped[str] = Column(String(100), default="not_replicated")
    tags: Mapped[str] = Column(JSON, nullable=True)

    experiments: Mapped[List["Experiment"]] = relationship(
        "Experiment", secondary="paper_experiment_link", back_populates="papers"
    )
    sources: Mapped[List["Source"]] = relationship(
        "Source", secondary="paper_source_link", back_populates="papers", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Paper doi={self.doi!r} arxiv={self.arxiv_id!r} title={self.title!r}>"


class Source(Base):
    """
    A source URL / archive used to collect data or papers (Section 5 of spec).

    Includes NASA, ESA, CERN, Planck, WMAP, DESI, SDSS, Euclid, Rubin, LIGO,
    Virgo, KAGRA, NIST, NASA ADS, arXiv, peer-reviewed journals, observatory
    archives, and official mission documentation.
    """

    __tablename__ = "sources"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = Column(String(200), nullable=False, index=True)
    url: Mapped[str] = Column(String(1000), nullable=False, unique=True)
    source_type: Mapped[str] = Column(String(100), default="archive")
    description: Mapped[Optional[str]] = Column(Text, nullable=True)

    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_source_link", back_populates="sources", lazy="selectin"
    )


class Dataset(Base):
    """
    A dataset available to the platform (Section 5 of spec).

    Track primary sources: Planck, WMAP, DESI, SDSS, Euclid, Rubin, LIGO, etc.
    Includes metadata: origin, version, checksum, availability (online/offline),
    size, access method, associated papers.
    """

    __tablename__ = "datasets"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = Column(String(300), nullable=False, index=True)
    origin: Mapped[str] = Column(String(200), nullable=False)  # e.g., "Planck", "DESI", "SDSS"
    version: Mapped[str] = Column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = Column(Text, nullable=True)
    data_type: Mapped[str] = Column(String(100))  # "cmb", "galaxy_catalog", "lensing", "supernova", "gw", etc.
    availability: Mapped[str] = Column(String(50), default="offline")  # online | offline | unavailable
    size_bytes: Mapped[int] = Column(Integer, nullable=True)
    checksum: Mapped[Optional[str]] = Column(String(100), nullable=True)
    download_url: Mapped[Optional[str]] = Column(String(2000), nullable=True)
    local_path: Mapped[Optional[str]] = Column(String(1000), nullable=True)
    manifest_path: Mapped[Optional[str]] = Column(String(1000), nullable=True)
    # Schema / structure description
    dataset_schema: Mapped[str] = Column(JSON, nullable=True)
    associated_papers: Mapped[str] = Column(JSON, nullable=True)  # list of paper ids
    last_updated: Mapped[Optional[datetime.datetime]] = Column(DateTime, nullable=True)

    experiments: Mapped[List["Experiment"]] = relationship(
        "Experiment", secondary="dataset_experiment_link", back_populates="datasets"
    )
    observations: Mapped[List["Observation"]] = relationship(
        back_populates="dataset", lazy="selectin"
    )


class Model(Base):
    """
    A cosmological/theoretical model being compared (Section 37 of spec).

    Includes null model, standard model (Lambda CDM), and alternative models
    (MOND, scalar-tensor, evolving dark energy w0-wa, modified gravity, etc.).
    """

    __tablename__ = "models"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = Column(String(200), nullable=False, index=True)
    model_type: Mapped[str] = Column(String(100), nullable=False)  # "null", "standard", "alternative"
    description: Mapped[str] = Column(Text, nullable=True)
    category: Mapped[str] = Column(String(100))  # "dark_matter", "dark_energy", "inflation", "gravity", etc.
    # Free parameters with prior ranges
    parameters: Mapped[str] = Column(JSON, nullable=True)
    equations: Mapped[str] = Column(JSON, nullable=True)
    assumptions: Mapped[str] = Column(JSON, nullable=True)
    predictions: Mapped[str] = Column(JSON, nullable=True)
    associated_papers: Mapped[str] = Column(JSON, nullable=True)
    # Model performance summary
    summary: Mapped[Optional[str]] = Column(Text, nullable=True)

    hypotheses: Mapped[List["Hypothesis"]] = relationship(
        back_populates="model", lazy="selectin"
    )
    results: Mapped[List["Result"]] = relationship(
        back_populates="model", lazy="selectin"
    )
    experiments_as_null: Mapped[List["Experiment"]] = relationship(
        "Experiment", back_populates="null_model", lazy="selectin"
    )


class Hypothesis(Base):
    """
    A proposed explanation for a question (Section 2 of spec).

    Distinct from speculation: must make testable predictions.
    """

    __tablename__ = "hypotheses"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question_id: Mapped[str] = Column(
        String(36), ForeignKey("questions.id"), nullable=False, index=True
    )
    description: Mapped[str] = Column(Text, nullable=False)
    model_id: Mapped[Optional[str]] = Column(
        String(36), ForeignKey("models.id"), nullable=True
    )
    predictions: Mapped[str] = Column(JSON, nullable=True)
    testability: Mapped[str] = Column(
        String(100), default="not_currently_testable"
    )
    evidence_for: Mapped[str] = Column(JSON, nullable=True)
    evidence_against: Mapped[str] = Column(JSON, nullable=True)

    question: Mapped["Question"] = relationship(
        back_populates="hypotheses", lazy="joined"
    )
    model: Mapped[Optional["Model"]] = relationship(
        back_populates="hypotheses", lazy="joined"
    )
    experiments: Mapped[List["Experiment"]] = relationship(
        "Experiment", back_populates="hypothesis", lazy="selectin"
    )


class Prediction(Base):
    """
    An explicit, quantitative prediction of a hypothesis/model (Sections 16/17 of spec).

    Each prediction is traceable and, where possible, forecasted before data
    arrives (future-data mode, Section 43).
    """

    __tablename__ = "predictions"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[Optional[str]] = Column(
        String(36), ForeignKey("experiments.id"), nullable=True, index=True
    )
    hypothesis_id: Mapped[str] = Column(
        String(36), ForeignKey("hypotheses.id"), nullable=False, index=True
    )
    description: Mapped[str] = Column(Text, nullable=False)
    value: Mapped[Optional[float]] = Column(Float, nullable=True)
    value_unit: Mapped[Optional[str]] = Column(String(50), nullable=True)
    predicted_range_low: Mapped[Optional[float]] = Column(Float, nullable=True)
    predicted_range_high: Mapped[Optional[float]] = Column(Float, nullable=True)
    predicted_range_unit: Mapped[Optional[str]] = Column(String(50), nullable=True)
    confidence: Mapped[str] = Column(String(100), default="speculative")
    forecast_for_survey: Mapped[Optional[str]] = Column(String(200), nullable=True)
    forecast_date: Mapped[Optional[datetime.date]] = Column(DateTime, nullable=True)
    verified: Mapped[bool] = Column(Boolean, default=False)
    verification_result: Mapped[Optional[str]] = Column(String(100), nullable=True)

    experiment: Mapped[Optional["Experiment"]] = relationship(
        back_populates="predictions", lazy="joined"
    )


class Experiment(Base):
    """
    A complete, self-contained experiment (Section 7 of spec).

    Machine-readable definition with hypothesis, baseline/null model,
    competing models, assumptions, datasets, preprocessing, prediction,
    statistical test, expected result, falsification condition, uncertainty,
    systematic errors, result, confidence/significance, reproducibility info.
    """

    __tablename__ = "experiments"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    exp_id: Mapped[str] = Column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = Column(String(300), nullable=False)
    question_id: Mapped[Optional[str]] = Column(
        String(36), ForeignKey("questions.id"), nullable=True, index=True
    )
    status: Mapped[str] = Column(String(50), default="not_started")
    phase: Mapped[str] = Column(String(100), default="not_started")
    priority_score: Mapped[float] = Column(Float, default=0.0)
    start_date: Mapped[Optional[datetime.datetime]] = Column(DateTime, nullable=True)
    end_date: Mapped[Optional[datetime.datetime]] = Column(DateTime, nullable=True)
    last_run: Mapped[Optional[datetime.datetime]] = Column(DateTime, nullable=True)
    commit: Mapped[Optional[str]] = Column(String(40), nullable=True)
    software_version: Mapped[str] = Column(String(50), default="0.1.0")
    analysis_version: Mapped[str] = Column(String(50), default="v1")

    # Analysis plan (registered before results examined, Section 26)
    analysis_plan: Mapped[Optional[str]] = Column(Text, nullable=True)
    registered_before_results: Mapped[bool] = Column(Boolean, default=False)

    # Hypothesis / models / datasets
    hypothesis_id: Mapped[Optional[str]] = Column(
        String(36), ForeignKey("hypotheses.id"), nullable=True
    )
    null_model_id: Mapped[Optional[str]] = Column(
        String(36), ForeignKey("models.id"), nullable=True
    )
    alternative_model_ids: Mapped[str] = Column(JSON, nullable=True)
    competing_models: Mapped[str] = Column(JSON, nullable=True)

    # Full experiment definition
    definition: Mapped[str] = Column(JSON, nullable=True)

    # Results and classification
    result_classification: Mapped[str] = Column(
        String(100), default="not_testable", index=True
    )
    result_summary: Mapped[Optional[str]] = Column(Text, nullable=True)
    result_summary_level1: Mapped[Optional[str]] = Column(Text, nullable=True)  # plain English
    result_summary_level2: Mapped[Optional[str]] = Column(Text, nullable=True)  # technical
    result_summary_level3: Mapped[Optional[str]] = Column(Text, nullable=True)  # mathematical
    result_summary_level4: Mapped[Optional[str]] = Column(Text, nullable=True)  # research
    significance_sigma: Mapped[Optional[float]] = Column(Float, nullable=True)
    p_value: Mapped[Optional[float]] = Column(Float, nullable=True)

    # Reproducibility
    reproducible: Mapped[bool] = Column(Boolean, default=False)
    reproducibility_hash: Mapped[Optional[str]] = Column(String(64), nullable=True)
    random_seed: Mapped[Optional[int]] = Column(Integer, nullable=True)
    environment_lock: Mapped[Optional[str]] = Column(String(1000), nullable=True)

    # Relationships (many-to-many via association tables)
    datasets: Mapped[List["Dataset"]] = relationship(
        "Dataset", secondary="dataset_experiment_link", back_populates="experiments"
    )
    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_experiment_link", back_populates="experiments"
    )

    # Back-references
    question: Mapped[Optional["Question"]] = relationship(
        back_populates="experiments", lazy="joined"
    )
    hypothesis: Mapped[Optional["Hypothesis"]] = relationship(
        back_populates="experiments", lazy="joined"
    )
    null_model: Mapped[Optional["Model"]] = relationship(
        back_populates="experiments_as_null", lazy="joined"
    )
    results: Mapped[List["Result"]] = relationship(
        back_populates="experiment", lazy="selectin"
    )
    predictions: Mapped[List["Prediction"]] = relationship(
        back_populates="experiment", lazy="selectin"
    )
    observations: Mapped[List["Observation"]] = relationship(
        back_populates="experiment", lazy="selectin"
    )
    reports: Mapped[List["Report"]] = relationship(
        back_populates="experiment", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Experiment id={self.exp_id!r} name={self.name!r} status={self.status!r}>"


class Result(Base):
    """
    The outcome of an experiment run (Section 35/51 of spec).

    Every result is classified, annotated with uncertainty, significance,
    systematic-error assessment, and full provenance.
    """

    __tablename__ = "results"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = Column(
        String(36), ForeignKey("experiments.id"), nullable=False, index=True
    )
    question_id: Mapped[Optional[str]] = Column(
        String(36), ForeignKey("questions.id"), nullable=True, index=True
    )
    null_model_id: Mapped[Optional[str]] = Column(
        String(36), ForeignKey("models.id"), nullable=True, index=True
    )
    run_id: Mapped[str] = Column(String(36), nullable=False)
    run_timestamp: Mapped[datetime.datetime] = Column(DateTime, nullable=False)
    classification: Mapped[str] = Column(String(100), nullable=False)

    # Hypothesis / model performance
    hypothesis_supported: Mapped[bool] = Column(Boolean, nullable=True)
    null_model_fitted: Mapped[bool] = Column(Boolean, nullable=True)
    alternative_models_fitted: Mapped[str] = Column(JSON, nullable=True)

    # Statistical summary
    significance_sigma: Mapped[Optional[float]] = Column(Float, nullable=True)
    p_value: Mapped[Optional[float]] = Column(Float, nullable=True)
    corrected_p_value: Mapped[Optional[float]] = Column(Float, nullable=True)
    aic: Mapped[Optional[float]] = Column(Float, nullable=True)
    bic: Mapped[Optional[float]] = Column(Float, nullable=True)
    bayesian_evidence: Mapped[Optional[float]] = Column(Float, nullable=True)
    posterior_parameters: Mapped[str] = Column(JSON, nullable=True)
    confidence_interval: Mapped[str] = Column(JSON, nullable=True)

    # Systematic errors and adversarial tests (Section 36)
    systematic_errors: Mapped[str] = Column(JSON, nullable=True)
    adversarial_tests: Mapped[str] = Column(JSON, nullable=True)
    survived_adversarial: Mapped[bool] = Column(Boolean, default=False)
    looked_for_bias: Mapped[bool] = Column(Boolean, default=True)

    # Provenance chain (Section 27 of spec)
    provenance: Mapped[str] = Column(JSON, nullable=True)

    # Labels for classification (Section 2/29 of spec)
    observation_types: Mapped[str] = Column(JSON, nullable=True)

    # Summary text at four levels (Section 57 of spec)
    summary: Mapped[Optional[str]] = Column(Text, nullable=True)
    summary_level1: Mapped[Optional[str]] = Column(Text, nullable=True)
    summary_level2: Mapped[Optional[str]] = Column(Text, nullable=True)
    summary_level3: Mapped[Optional[str]] = Column(Text, nullable=True)
    summary_level4: Mapped[Optional[str]] = Column(Text, nullable=True)

    # Limitations and "what we cannot conclude"
    limitations: Mapped[str] = Column(JSON, nullable=True)
    unresolved_questions: Mapped[str] = Column(JSON, nullable=True)

    # Replication
    independently_replicated: Mapped[bool] = Column(Boolean, default=False)
    replication_status: Mapped[str] = Column(String(100), default="not_replicated")

    # Where the output lives
    output_dir: Mapped[Optional[str]] = Column(String(1000), nullable=True)
    report_path: Mapped[Optional[str]] = Column(String(1000), nullable=True)

    experiment: Mapped["Experiment"] = relationship(
        back_populates="results", lazy="joined"
    )
    model: Mapped[Optional["Model"]] = relationship(
        back_populates="results", lazy="joined"
    )
    question: Mapped[Optional["Question"]] = relationship(
        back_populates="results", lazy="joined"
    )

class Observation(Base):
    """
    An observation entry: what was actually measured (Section 2 of spec).

    Distinct from inference — observational facts only.
    """

    __tablename__ = "observations"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = Column(
        String(36), ForeignKey("experiments.id"), nullable=False, index=True
    )
    dataset_id: Mapped[Optional[str]] = Column(
        String(36), ForeignKey("datasets.id"), nullable=True
    )
    label: Mapped[str] = Column(String(300), nullable=False)
    description: Mapped[str] = Column(Text, nullable=False)
    observation_type: Mapped[str] = Column(String(100), nullable=False)
    value: Mapped[Optional[float]] = Column(Float, nullable=True)
    value_low: Mapped[Optional[float]] = Column(Float, nullable=True)
    value_high: Mapped[Optional[float]] = Column(Float, nullable=True)
    value_unit: Mapped[str] = Column(String(50), nullable=True)
    measurement_error: Mapped[Optional[float]] = Column(Float, nullable=True)
    systematic_error: Mapped[Optional[float]] = Column(Float, nullable=True)
    coordinate_system: Mapped[Optional[str]] = Column(String(100), nullable=True)
    survey_geometry: Mapped[Optional[str]] = Column(JSON, nullable=True)
    reference: Mapped[Optional[str]] = Column(String(1000), nullable=True)  # paper DOI
    timestamp_created: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.utcnow)

    dataset: Mapped[Optional["Dataset"]] = relationship(
        back_populates="observations", lazy="joined"
    )
    experiment: Mapped["Experiment"] = relationship(
        back_populates="observations", lazy="joined"
    )


class Report(Base):
    """
    A generated report for an experiment or question (Section 28 of spec).

    Contains: executive summary, scientific question, hypotheses, data,
    method, results, statistical significance, systematics, robustness,
    replication, interpretation, limitations, references, reproducibility.
    """

    __tablename__ = "reports"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[Optional[str]] = Column(
        String(36), ForeignKey("experiments.id"), nullable=True, index=True
    )
    question_id: Mapped[Optional[str]] = Column(
        String(36), ForeignKey("questions.id"), nullable=True, index=True
    )
    report_type: Mapped[str] = Column(String(100), default="experiment")
    title: Mapped[str] = Column(String(500), nullable=False)
    format: Mapped[str] = Column(String(20), default="markdown")
    content: Mapped[str] = Column(Text, nullable=True)
    level: Mapped[str] = Column(String(10), default="level2")  # level1-4
    generated_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.utcnow)
    path: Mapped[Optional[str]] = Column(String(1000), nullable=True)

    experiment: Mapped[Optional["Experiment"]] = relationship(
        back_populates="reports", lazy="joined"
    )
    question: Mapped[Optional["Question"]] = relationship(
        back_populates="reports", lazy="joined"
    )


# Association tables for many-to-many relationships
paper_experiment_link = Table(
    "paper_experiment_link",
    Base.metadata,
    Column("paper_id", String(36), ForeignKey("papers.id"), primary_key=True),
    Column("experiment_id", String(36), ForeignKey("experiments.id"), primary_key=True),
)

dataset_experiment_link = Table(
    "dataset_experiment_link",
    Base.metadata,
    Column("dataset_id", String(36), ForeignKey("datasets.id"), primary_key=True),
    Column("experiment_id", String(36), ForeignKey("experiments.id"), primary_key=True),
)

paper_source_link = Table(
    "paper_source_link",
    Base.metadata,
    Column("paper_id", String(36), ForeignKey("papers.id"), primary_key=True),
    Column("source_id", String(36), ForeignKey("sources.id"), primary_key=True),
)


class ExperimentRegistry(Base):
    """
    The experiment registry: ordered list of experiments with priority scores
    (Section 7 and 46 of spec).
    """

    __tablename__ = "experiment_registry"

    id: Mapped[str] = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    exp_id: Mapped[str] = Column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = Column(String(300), nullable=False)
    description: Mapped[Optional[str]] = Column(Text, nullable=True)
    status: Mapped[str] = Column(String(50), default="not_started")
    priority_score: Mapped[float] = Column(Float, default=0.0)
    data_availability: Mapped[float] = Column(Float, default=0.0)  # 0-1 score
    theoretical_importance: Mapped[float] = Column(Float, default=0.0)  # 0-1
    observational_leverage: Mapped[float] = Column(Float, default=0.0)  # 0-1
    reproducibility: Mapped[float] = Column(Float, default=0.0)  # 0-1
    computational_feasibility: Mapped[float] = Column(Float, default=0.0)  # 0-1
    falsifiability: Mapped[float] = Column(Float, default=0.0)  # 0-1
    potential_impact: Mapped[float] = Column(Float, default=0.0)  # 0-1
    order: Mapped[int] = Column(Integer, default=0)
    recommended: Mapped[bool] = Column(Boolean, default=False)
    next_in_line: Mapped[bool] = Column(Boolean, default=False)

    def total_priority(self) -> float:
        return (
            self.data_availability
            + self.theoretical_importance
            + self.observational_leverage
            + self.reproducibility
            + self.computational_feasibility
            + self.falsifiability
            + self.potential_impact
        ) / 7


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------


def create_engine_from_url(url: str, echo: bool = False) -> Any:
    """Create a SQLAlchemy engine from a database URL."""
    if url.startswith("sqlite:///"):
        import os
        db_path = url.replace("sqlite:///", "")
        if not os.path.isabs(db_path):
            from cosmos.config import settings
            db_path = str(settings.root / db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        url = f"sqlite:///{db_path}"
    engine = create_engine(url, echo=echo, pool_pre_ping=True)
    return engine


def create_db_engine(database_url: Optional[str] = None, echo: bool = False) -> Any:
    """Create and configure the database engine."""
    from cosmos.config import settings
    url = database_url or settings.database_url
    return create_engine_from_url(url, echo)


def init_db(database_url: Optional[str] = None, echo: bool = False) -> Any:
    """Create all tables and return the engine + base metadata."""
    engine = create_db_engine(database_url, echo)
    Base.metadata.create_all(engine)
    return engine


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=None)
